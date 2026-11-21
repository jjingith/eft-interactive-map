# -*- coding: utf-8 -*-
"""R233：配装栏预设提示改成会员引导文案 + 会员云存储真的接通。

用户原话（2026-11-10 22:08）：
  「预设保存在 %APPDATA%\\EFTMap\\weapon-presets.json（本地离线文件，不上传）。
    配装栏有这个提示 我希望提示改成这个 免费版预设保存在本地 会员享受云存储
    然后你看看能不能做到云存储 并实现这个效果」

结论：云端已有会员鉴权（_require_member）与账号级通用 KV（sync_items +
/v1/sync/{state,push,fetch}），**服务端零改动**；客户端复用同一条增量同步链路，
新增 preset.weapon / preset.loadout 两个键。免费版在 syncNow / scheduleSync /
BFF 三处被挡住，一个云端请求都不发。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

import serve

ROOT = Path(__file__).resolve().parent.parent


def _read(*parts: str) -> str:
    with open(ROOT.joinpath(*parts), encoding="utf-8") as fh:
        return fh.read()


# ------------------------------------------------------------------ 静态契约

def test_old_local_path_note_is_gone():
    app = _read("app.js")
    assert "本地离线文件，不上传" not in app
    assert "预设保存在 %APPDATA%" not in app
    assert "weapon-presets.json（本地离线文件" not in app


def test_loadout_gun_preset_note_is_gone():
    """R299 后续：配装栏不再重复展示枪械预设区，这条提示也一并移除。"""
    app = _read("app.js")
    assert "免费版预设保存在本地 会员享受云存储" not in app
    assert "PRESET_STORAGE_NOTE" not in app
    assert "el.lwGunPresetNote" not in app
    assert "function presetCloudNoteTitle" not in app


def test_preset_save_dispatches_sync_event():
    app = _read("app.js")
    assert 'new CustomEvent("gw:presets-saved"' in app
    assert '"eftmap:presets-remote-applied"' in app
    cloud = _read("js", "cloud.js")
    assert 'document.addEventListener("gw:presets-saved", scheduleSync);' in cloud
    assert 'new window.CustomEvent("eftmap:presets-remote-applied"' in cloud


def test_cloud_uses_existing_sync_kv():
    cloud = _read("js", "cloud.js")
    for token in ('"preset." + PRESET_KINDS[j]', 'PRESET_KINDS = ["weapon", "loadout"]',
                  'action: "replace"', 'PRESET_MAX_CHARS = 240000',
                  '"/api/presets?kind="', 'readPresetPack'):
        assert token in cloud, token
    # 免费版三重拦截仍在（前端）
    assert "if (!state.member) { return; }" in cloud
    # 读不到预设时不能拿空数组冒充本地数据
    assert "catch(function () { return null; })" in cloud


def test_serve_replace_action_is_guarded():
    import re
    src = _read("tools", "serve.py")
    seg = src[src.index('elif action == "replace"'):]
    seg = seg[:seg.index("else:")]
    # 只查代码，注释里为了说明会提到 presets.save（R226 起的老坑）
    code = "\n".join(line.split("#")[0] for line in seg.splitlines())
    assert 'body.get("presets")' in code
    assert "not isinstance(incoming, list)" in code
    assert "PresetError" in code
    assert "presets.save" not in code, "整包交给下面统一的 presets.save（校验 + 原子写）"


# ------------------------------------------------------------------ HTTP 接口

@pytest.fixture
def server(tmp_path):
    httpd = serve.create_server(0, "127.0.0.1", str(ROOT), config_dir=str(tmp_path))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield serve.url_for("127.0.0.1", httpd.server_address[1]), tmp_path
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def get_json(url):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(url, timeout=20) as res:
            return res.status, json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def post_json(url, payload):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with opener.open(req, timeout=20) as res:
            return res.status, json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def test_replace_writes_remote_pack_to_local_file(server):
    base, tmp = server
    status, body = post_json(base + "api/presets", {
        "kind": "weapon", "action": "save",
        "preset": {"name": "本地旧方案", "gunId": "gun-ak", "items": {}}})
    assert status == 200 and body["count"] == 1

    remote = [{"id": "wp_remote1", "name": "云端方案", "gunId": "gun-m4",
               "items": {"muzzle": "mod-9"}}]
    status, body = post_json(base + "api/presets", {
        "kind": "weapon", "action": "replace", "presets": remote})
    assert status == 200, body
    assert body["ok"] is True and body["count"] == 1
    assert body["presets"][0]["id"] == "wp_remote1"
    assert body["presets"][0]["name"] == "云端方案"
    # 落盘的是整包替换，不是追加
    status, got = get_json(base + "api/presets?kind=weapon")
    assert status == 200 and len(got["presets"]) == 1
    assert got["presets"][0]["name"] == "云端方案"
    assert (tmp / "weapon-presets.json").is_file()


def test_replace_rejects_bad_payload_without_touching_local(server):
    base, tmp = server
    status, body = post_json(base + "api/presets", {
        "kind": "loadout", "action": "save",
        "preset": {"name": "本地方案", "slots": {"helmet": "item-a"}}})
    assert status == 200
    before = (tmp / "loadout-presets.json").read_bytes()

    status, body = post_json(base + "api/presets", {
        "kind": "loadout", "action": "replace", "presets": "不是数组"})
    assert status == 400 and body["ok"] is False

    status, body = post_json(base + "api/presets", {
        "kind": "loadout", "action": "replace",
        "presets": [{"id": "x", "name": ""}]})   # 名称为空，归一化应拒绝
    assert status == 400 and body["ok"] is False
    assert (tmp / "loadout-presets.json").read_bytes() == before, "坏整包不能覆盖本地文件"


def test_replace_refuses_corrupt_local_file(server):
    base, tmp = server
    path = tmp / "weapon-presets.json"
    path.write_text('{"presets": [', encoding="utf-8")
    status, body = post_json(base + "api/presets", {
        "kind": "weapon", "action": "replace",
        "presets": [{"id": "wp_ok", "name": "云端", "gunId": "g", "items": {}}]})
    assert status == 409 and body.get("corrupt") is True
    assert path.read_text(encoding="utf-8") == '{"presets": ['


# ------------------------------------------------------------------ Node 实跑

NODE_HARNESS = r"""
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8');

function extractFn(name) {
  const start = src.indexOf('function ' + name + '(');
  if (start < 0) { throw new Error('no fn ' + name); }
  let i = src.indexOf('{', start), depth = 0, inS = null, esc = false;
  for (let j = i; j < src.length; j++) {
    const c = src[j];
    if (inS) {
      if (esc) { esc = false; continue; }
      if (c === '\\') { esc = true; continue; }
      if (c === inS) { inS = null; }
      continue;
    }
    if (c === '"' || c === "'" || c === '`') { inS = c; continue; }
    if (c === '/' && src[j + 1] === '/') { while (j < src.length && src[j] !== '\n') { j++; } continue; }
    if (c === '{') { depth++; }
    else if (c === '}') { depth--; if (depth === 0) { return src.slice(start, j + 1); } }
  }
  throw new Error('unbalanced ' + name);
}

const code = ['readPresetPack', 'collectValues', 'applyPresetRemote'].map(extractFn).join('\n');

globalThis.__st = { calls: [], events: [], getMode: 'ok' };
const fakeApi = function (path, opts) {
  globalThis.__st.calls.push({ path: path, opts: opts });
  if (!opts || opts.method !== 'POST') {
    if (path.indexOf('/api/presets?kind=') === 0) {
      if (globalThis.__st.getMode === 'fail') { return Promise.reject(new Error('offline')); }
      const kind = path.split('kind=')[1];
      const huge = globalThis.__st.getMode === 'huge' && kind === 'weapon';
      return Promise.resolve({ ok: true, presets: huge
        ? [{ id: 'w', name: 'X'.repeat(250000), gunId: 'g', items: {} }]
        : (kind === 'weapon' ? [{ id: 'w1', name: 'WP', gunId: 'g', items: {} }] : []) });
    }
    return Promise.resolve({ ok: true });
  }
  return Promise.resolve({ ok: true });
};
const fakeWindow = {
  GWTasks: { progress: function () { return { modes: { regular: { a: 1 }, pve: {}, pvps: {} } }; } },
  CustomEvent: function (name, init) { this.name = name; this.detail = init && init.detail; },
  dispatchEvent: function (ev) { globalThis.__st.events.push({ name: ev.name, detail: ev.detail }); }
};

const make = new Function('api', 'window', 'Promise',
  'var MODE_KEYS = ["regular","pve","pvps"];' +
  'var PRESET_KINDS = ["weapon","loadout"];' +
  'var PRESET_SYNC_SCHEMA = 1;' +
  'var PRESET_MAX_CHARS = 240000;' +
  'var presetSyncNote = "";' +
  code +
  '\nreturn { collectValues: collectValues, applyPresetRemote: applyPresetRemote,' +
  ' note: function(){ return presetSyncNote; },' +
  ' setMode: function(m){ globalThis.__st.getMode = m; },' +
  ' reset: function(){ globalThis.__st.calls = []; globalThis.__st.events = []; presetSyncNote = ""; },' +
  ' calls: function(){ return globalThis.__st.calls; },' +
  ' events: function(){ return globalThis.__st.events; } };');

const r = make(fakeApi, fakeWindow, Promise);
const out = {};

r.reset();
r.collectValues().then(function (values) {
  out.normal = { keys: Object.keys(values).sort(),
    weapon: JSON.parse(values['preset.weapon']),
    loadout: JSON.parse(values['preset.loadout']),
    note: r.note() };

  r.setMode('fail'); r.reset();
  return r.collectValues();
}).then(function (values) {
  out.offline = { keys: Object.keys(values).sort(), note: r.note() };

  r.setMode('huge'); r.reset();
  return r.collectValues();
}).then(function (values) {
  out.huge = { keys: Object.keys(values).sort(), note: r.note() };

  r.reset();
  const remote = {
    'preset.weapon': JSON.stringify({ schema: 1, presets: [{ id: 'w2', name: '远端', gunId: 'g', items: {} }] }),
    'preset.bogus': JSON.stringify({ schema: 1, presets: [] }),
    'preset.loadout': '{bad json'
  };
  return r.applyPresetRemote(remote);
}).then(function (done) {
  out.apply = {
    done: done,
    posts: r.calls().filter(function (c) { return c.opts && c.opts.method === 'POST'; })
      .map(function (c) { return { path: c.path, kind: c.opts.body.kind,
        action: c.opts.body.action, n: c.opts.body.presets.length }; }),
    events: r.events()
  };
  console.log(JSON.stringify(out));
}).catch(function (e) { console.error(e.stack); process.exit(1); });
"""


def test_node_sync_logic():
    node = shutil.which("node")
    if not node:
        pytest.skip("node 不在 PATH")
    tmp = tempfile.mkdtemp(prefix="r233_")
    try:
        script = os.path.join(tmp, "h.js")
        with open(script, "w", encoding="utf-8") as fh:
            fh.write(NODE_HARNESS)
        proc = subprocess.run([node, script, str(ROOT / "js" / "cloud.js")],
                              capture_output=True, text=True, encoding="utf-8", timeout=60)
        assert proc.returncode == 0, proc.stderr[-900:]
        out = json.loads(proc.stdout.strip().splitlines()[-1])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # 正常：3 个进度键 + 2 个预设键，值是 schema 1 的整包
    assert out["normal"]["keys"] == ["preset.loadout", "preset.weapon",
                                     "progress.pve", "progress.pvps", "progress.regular"]
    assert out["normal"]["weapon"]["schema"] == 1
    assert out["normal"]["weapon"]["presets"][0]["id"] == "w1"
    assert out["normal"]["note"] == ""
    # 读不到本地预设：跳过该键，任务进度照常同步，绝不拿空数组冒充
    assert out["offline"]["keys"] == ["progress.pve", "progress.pvps", "progress.regular"]
    # 超上限：跳过但明确写出提示，不静默丢
    assert "preset.weapon" not in out["huge"]["keys"]
    assert "超过云端单值上限" in out["huge"]["note"]
    # 远端整包：只处理合法键，POST action=replace，成功后派发刷新事件
    assert out["apply"]["done"] == ["weapon"]
    assert out["apply"]["posts"] == [
        {"path": "/api/presets", "kind": "weapon", "action": "replace", "n": 1}]
    assert out["apply"]["events"] == [
        {"name": "eftmap:presets-remote-applied", "detail": {"kind": "weapon"}}]
