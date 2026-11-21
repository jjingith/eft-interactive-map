# -*- coding: utf-8 -*-
"""R227：弹药界面侧栏底部那段说明不再常驻显示。

用户原话（2026-11-10 16:45）：
  「弹药界面的这个也不要显示 隐藏掉「共 200 件弹药 / 31 种口径。价格口径 lastPrice，
    来源 实时不可用，已回退快照（PvP）；C1–C6 为对 1–6 级护甲的穿透概率（公开公式计算）。
    弹道曲线为本地 G1 阻力仿真，非线上行情。」」

这里守三件事：
1. 那四句文案不得复活；
2. `#am-note` 在没有边界提示时必须隐藏（不能留 11px 空隙，也不能只剩空 <p>）；
3. 两种「结果会变空」的边界提示仍要出得来（CRAFT 无来源 / avg7d 无数据）。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*parts: str) -> str:
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


def test_note_copy_is_gone():
    app = _read("app.js")
    for banned in (
        "件弹药 / ",
        "种口径。",
        "C1–C6 为对 1–6 级护甲的穿透概率",
        "弹道曲线为本地 G1 阻力仿真",
        "价格口径 <b>",
    ):
        assert banned not in app, "这段说明应已删除：%s" % banned


def test_am_price_label_helper_removed_with_its_only_caller():
    app = _read("app.js")
    assert "amPriceLabel" not in app, "amPriceLabel 只为那段说明存在，删说明后应一并删除"


def test_note_element_is_hidden_when_no_boundary_warning():
    app = _read("app.js")
    body = app[app.index("function renderAmmo"):]
    body = body[:body.index("\n  function syncAmmoTabs")]
    assert "el.amNote.hidden = !warn;" in body, "没有提示时必须把 #am-note 隐藏"
    assert 'el.amNote.textContent = "";' in body, "没有提示时必须清空文案"
    # 两种边界提示都要保留
    assert "来源选了 CRAFT" in body
    assert "价格口径选了 avg7d" in body


def test_ammo_source_hint_removed():
    """R266：子弹页不再显示「价格来源：实时不可用，已回退快照…」，来源统一由二级工具条表达。"""
    app = _read("app.js")
    assert "价格来源：" not in app
    assert "el.amHint.title = srcInfo.detail;" not in app
    assert "el.amNote.title" not in app


def test_css_hides_empty_note():
    css = _read("style.css")
    assert ".am-workbench .am-note[hidden]" in css and "display: none" in css


# ---------------------------------------------------------------- Node 实跑

NODE_HARNESS = r"""
const fs = require('fs');
const path = require('path');
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

// 只跑 renderAmmo 里「写 #am-note」的那一小段：把上下文需要的桩全挂到 globalThis
globalThis.state = { live: { consent: true } };
globalThis.priceSourceInfo = function () { return { kind: 'snapshot', short: '实时不可用，已回退快照（PvP）', detail: 'detail-xyz' }; };
globalThis.esc = function (s) { return String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); };

const el = {
  amCount: { textContent: '' },
  amHint: { textContent: '', title: '' },
  amNote: { innerHTML: '', textContent: '', hidden: false, title: '' },
  amMaxdist: { value: '' },
};
globalThis.el = el;
globalThis.data = { rows: new Array(200), calibers: new Array(31) };

// 直接取 renderAmmo 里「写 am-hint」到「el.amMaxdist」的那一段，包成函数执行
const body = src.slice(src.indexOf('function renderAmmo'));
const seg = body.slice(body.indexOf('    if (el.amHint) {'), body.indexOf('    if (el.amMaxdist)'));
const fn = new Function('f', seg + '\n return { hint: el.amHint.textContent, note: el.amNote.innerHTML, hidden: el.amNote.hidden, title: el.amHint.title };');

const out = {};
out.plain = fn({ source: 'all', priceMode: 'last' });
out.avg7d = fn({ source: 'all', priceMode: 'avg7d' });
out.craft = fn({ source: 'craft', priceMode: 'last' });
console.log(JSON.stringify(out));
"""


def test_rendered_note_states():
    node = shutil.which("node")
    if not node:
        import pytest
        pytest.skip("node 不在 PATH")
    tmp = tempfile.mkdtemp(prefix="r227_")
    try:
        script = os.path.join(tmp, "h.js")
        with open(script, "w", encoding="utf-8") as fh:
            fh.write(NODE_HARNESS)
        proc = subprocess.run([node, script, os.path.join(ROOT, "app.js")],
                              capture_output=True, text=True, encoding="utf-8", timeout=60)
        assert proc.returncode == 0, proc.stderr[-800:]
        out = json.loads(proc.stdout.strip().splitlines()[-1])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # 默认态：整段不显示，标题文字也没有那四句
    assert out["plain"]["hidden"] is True
    assert out["plain"]["note"] == ""
    for banned in ("种口径", "G1 阻力", "C1–C6", "价格口径"):
        assert banned not in out["plain"]["note"]
    # R266：来源提示已移除，am-hint 为空（来源统一由二级工具条的市场截止徽标表达）
    assert out["plain"]["hint"] == ""
    assert out["plain"]["title"] == ""

    # 边界态：avg7d / craft 必须显示，且只显示那一句
    assert out["avg7d"]["hidden"] is False
    assert "avg7d" in out["avg7d"]["note"]
    assert "种口径" not in out["avg7d"]["note"]
    assert out["craft"]["hidden"] is False
    assert "CRAFT" in out["craft"]["note"]
