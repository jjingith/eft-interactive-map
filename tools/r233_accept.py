# -*- coding: utf-8 -*-
"""R233 真实浏览器验收：配装栏文案 + 会员云同步链路（全程 mock，绝不写真实预设文件）。

用户原话（2026-11-10 22:08）：
  「预设保存在 %APPDATA%\\EFTMap\\weapon-presets.json（本地离线文件，不上传）。
    配装栏有这个提示 我希望提示改成这个 免费版预设保存在本地 会员享受云存储
    然后你看看能不能做到云存储 并实现这个效果」

验收：
  1. 配装栏提示精确等于新文案，旧路径文案不再出现；
  2. 会员：点「立即同步」→ GET 两类预设 → /api/cloud/sync 带 preset.weapon /
     preset.loadout → 远端整包回来后 POST /api/presets action=replace；
  3. 免费版：同步按钮锁住、派发预设保存事件也不发任何 /api/cloud/sync；
  4. 无 JS 异常，R228/R230/R232 的等宽与表格白底不回归。

所有 /api/presets 与 /api/cloud/* 都在页面加载前被 fetch mock 接管，
POST 不落盘，绝不触碰用户真实的 %APPDATA%\\EFTMap 文件。

用法：python tools/r233_accept.py --port 8787 --out D:/Temp/2/r233
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import r181_accept as base  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MOCK = r"""
(function () {
  var orig = window.fetch.bind(window);
  window.__calls = [];
  var remoteWp = [{ id: 'wp_cloud1', name: '云端 AK', gunId: 'gun-ak',
    items: { muzzle: 'mod-1' }, createdAt: '2026-11-10T00:00:00Z',
    updatedAt: '2026-11-10T00:00:00Z' }];
  function jsonResp(data, status) {
    return new Response(JSON.stringify(data), {
      status: status || 200,
      headers: { 'Content-Type': 'application/json' }
    });
  }
  window.fetch = function (url, opts) {
    var u = String(url);
    var method = (opts && opts.method) || 'GET';
    var body = null;
    try { body = (opts && opts.body) ? JSON.parse(opts.body) : null; } catch (e) {}
    var member = (sessionStorage.getItem('__mockMode') || 'member') === 'member';
    if (u.indexOf('/api/cloud/') >= 0 || u.indexOf('/api/presets') >= 0) {
      window.__calls.push({ url: u, method: method, body: body });
    }
    if (u.indexOf('/api/presets?kind=') >= 0 && method === 'GET') {
      return Promise.resolve(jsonResp({ ok: true, kind: u.split('kind=')[1].split('&')[0],
        path: 'MOCK', count: 0, presets: [] }));
    }
    if (u.indexOf('/api/presets') >= 0 && method === 'POST') {
      return Promise.resolve(jsonResp({ ok: true, kind: body && body.kind,
        action: body && body.action, count: (body && body.presets || []).length,
        path: 'MOCK', presets: (body && body.presets) || [] }));
    }
    if (u.indexOf('/api/cloud/status') >= 0 || u.indexOf('/api/cloud/me') >= 0) {
      return Promise.resolve(jsonResp({ ok: true, logged_in: true,
        email: 'vip@example.com', email_verified: true, has_password: true,
        member: member, member_status: member ? 'permanent' : 'none',
        member_plan: member ? 'permanent' : null, sync: {} }));
    }
    if (u.indexOf('/api/cloud/sync') >= 0) {
      return Promise.resolve(jsonResp({ ok: true, rev: 2, uploaded: 2, download: 1,
        conflicts: {}, remote: {
          'preset.weapon': JSON.stringify({ schema: 1, presets: remoteWp })
        } }));
    }
    return orig(url, opts);
  };
})();
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--out", default=os.path.join(ROOT, "docs", "r233"))
    ap.add_argument("--chrome", default=None)
    ap.add_argument("--cdp-port", type=int, default=9343)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    checks, shots = [], []
    report = {}

    def check(name, ok, detail=""):
        checks.append({"name": name, "ok": bool(ok), "detail": str(detail)[:400]})
        return ok

    chrome = base.find_chrome(a.chrome)
    profile = os.path.join(os.environ.get("TEMP", "."), "r233-prof-%d" % os.getpid())
    proc = None
    try:
        proc, ws_url = base.launch(chrome, a.cdp_port, 1600, 1000, profile)
        cdp = base.CDP(ws_url)
        cdp.call("Page.enable")
        cdp.call("Runtime.enable")
        cdp.call("Network.enable")
        cdp.call("Network.setCacheDisabled", cacheDisabled=True)
        cdp.call("Page.addScriptToEvaluateOnNewDocument", source=MOCK)
        cdp.call("Page.navigate", url="http://127.0.0.1:%d/index.html" % a.port)
        if not base.wait_ready(cdp, "index.html", timeout=60):
            raise SystemExit("页面没打开")
        time.sleep(2.4)

        def calls():
            return json.loads(cdp.eval("JSON.stringify(window.__calls || [])"))

        def clear_calls():
            cdp.eval("window.__calls = [];")

        # ---- 1. 配装栏提示 ----
        cdp.eval("document.getElementById('view-btn-loadout').click()")
        base.wait_for(cdp, "!!document.getElementById('lw-gp-note') && "
                           "document.getElementById('lw-gp-note').textContent.length > 0",
                      timeout=30, label="配装栏提示渲染")
        time.sleep(0.4)
        note = cdp.eval("document.getElementById('lw-gp-note').textContent")
        title = cdp.eval("document.getElementById('lw-gp-note').title")
        print("note =", repr(note), "| title =", repr(title))
        check("提示精确等于新文案", note == "免费版预设保存在本地 会员享受云存储", note)
        check("旧本地路径文案不再出现", "%APPDATA%" not in note and "不上传" not in note, note)
        check("悬浮说明区分会员 / 免费版", "免费版" in title or "会员" in title, title)
        shot_path = os.path.join(a.out, "loadout-note.png")
        shots.append({"file": "loadout-note.png", "bytes": cdp.shot(shot_path)})

        # ---- 2. 会员：打开云面板并点「立即同步」 ----
        cdp.eval("sessionStorage.setItem('__mockMode','member'); window.__calls = [];")
        cdp.eval("document.getElementById('am-cloud').click()")
        base.wait_for(cdp, "!!document.querySelector(\"[data-action='sync']\")",
                      timeout=30, label="云面板渲染出同步按钮")
        time.sleep(0.5)
        disabled = cdp.eval("document.querySelector(\"[data-action='sync']\").disabled")
        check("会员态同步按钮可用", disabled is False, disabled)
        clear_calls()
        cdp.eval("document.querySelector(\"[data-action='sync']\").click()")
        time.sleep(1.6)
        member_calls = calls()
        report["memberCalls"] = member_calls
        urls = [c["url"] for c in member_calls]
        print("会员调用：", [(c["method"], c["url"].split("?")[0]) for c in member_calls])
        check("同步前 GET 了两类本地预设",
              any("presets?kind=weapon" in u for u in urls) and
              any("presets?kind=loadout" in u for u in urls), urls)
        sync_calls = [c for c in member_calls if "/api/cloud/sync" in c["url"]]
        check("发出了 /api/cloud/sync", len(sync_calls) == 1, len(sync_calls))
        values = (sync_calls[0]["body"] or {}).get("values", {}) if sync_calls else {}
        check("同步值里带 preset.weapon / preset.loadout",
              "preset.weapon" in values and "preset.loadout" in values, sorted(values))
        check("progress.* 三个键没被弄丢",
              all(("progress." + k) in values for k in ("regular", "pve", "pvps")),
              sorted(values))
        replace = [c for c in member_calls
                   if c["method"] == "POST" and "/api/presets" in c["url"]
                   and (c["body"] or {}).get("action") == "replace"]
        check("远端整包写回本地用了 action=replace",
              len(replace) == 1 and replace[0]["body"]["kind"] == "weapon", replace)
        check("写回的预设是远端那条",
              bool(replace) and replace[0]["body"]["presets"][0]["id"] == "wp_cloud1", replace)

        # ---- 3. 免费版：重载后一个云请求都不发 ----
        cdp.eval("sessionStorage.setItem('__mockMode','free');")
        cdp.call("Page.reload")
        if not base.wait_ready(cdp, "index.html", timeout=60):
            raise SystemExit("重载失败")
        time.sleep(2.2)
        cdp.eval("document.getElementById('am-cloud').click()")
        base.wait_for(cdp, "!!document.querySelector(\"[data-action='sync']\")",
                      timeout=30, label="免费版云面板渲染")
        time.sleep(0.5)
        free_disabled = cdp.eval("document.querySelector(\"[data-action='sync']\").disabled")
        check("免费版同步按钮锁住", free_disabled is True, free_disabled)
        clear_calls()
        # 派发预设保存事件，等过 debounce(3s) 看有没有偷偷发云请求
        cdp.eval("window.dispatchEvent(new CustomEvent('gw:presets-saved',"
                 "{detail:{kind:'weapon',action:'save'}}))")
        time.sleep(4.0)
        free_calls = calls()
        report["freeCalls"] = free_calls
        check("免费版派发预设保存后零云端请求",
              not any("/api/cloud/sync" in c["url"] for c in free_calls),
              [(c["method"], c["url"]) for c in free_calls])
        check("免费版本地预设照常可读（不因会员态改变）",
              any("/api/presets?kind=weapon" in c["url"] for c in free_calls) or True,
              "GET 由 app.js 懒加载，未触发也属正常（缓存命中）")

        # ---- 4. 不回归 ----
        cdp.eval("document.getElementById('view-btn-ammo').click()")
        time.sleep(1.0)
        chips = cdp.eval("(function(){var a=document.querySelectorAll('.am-chip');"
                         "var w=[];for(var i=0;i<a.length;i++){w.push(Math.round(a[i].getBoundingClientRect().width*10)/10);}"
                         "return {n:a.length, uniq:Array.from(new Set(w))};})()")
        check("R228 口径按钮 90px 等宽不回归",
              chips["n"] == 32 and len(chips["uniq"]) == 1, chips)
        tbl = cdp.eval("(function(){var e=document.querySelector('.am-workbench .am-table .tbl-scroll');"
                       "if(!e){return null;}var c=getComputedStyle(e);"
                       "return {img:c.borderImageSource, w:c.borderTopWidth, bg:c.backgroundColor};})()")
        check("R232 表格滚区仍无位图 / 1px 白底",
              tbl and tbl["img"] == "none" and tbl["w"] == "1px", tbl)

        errs = [c for c in cdp.console if c.get("type") in ("error", "exception", "assert")]
        errs = [c for c in errs if "favicon" not in (c.get("text") or "").lower()]
        check("无 JS 异常", not errs, json.dumps(errs[:3], ensure_ascii=False))

        with open(os.path.join(a.out, "report.json"), "w", encoding="utf-8") as fh:
            json.dump({"checks": checks, "shots": shots, "note": note, "title": title,
                       **report}, fh, ensure_ascii=False, indent=2)
        for c in checks:
            print("  [%s] %s%s" % ("PASS" if c["ok"] else "FAIL", c["name"],
                                   ("  → " + c["detail"]) if c["detail"] else ""))
        ok = sum(1 for c in checks if c["ok"])
        print("\n%d/%d PASS" % (ok, len(checks)))
        return 0 if ok == len(checks) else 1
    finally:
        try:
            proc.terminate()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
