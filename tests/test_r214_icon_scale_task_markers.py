# -*- coding: utf-8 -*-
"""R214：左侧「大小调节」完整覆盖任务标 / 剧情标。

常规任务 / 剧情点本来就在 markerScaleNodes 里、随「图标」滑条缩放；这一轮补齐
两处确实漏掉的：任务目标钉点（.task-pin）与任务 / 剧情名字文字（改跟「地名」滑条）。
"""
from __future__ import annotations

import json
import os
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(rel: str) -> str:
    with open(os.path.join(ROOT, rel), "r", encoding="utf-8") as f:
        return f.read()


def _rule(css: str, selector: str) -> str:
    start = css.index(selector + " {")
    return css[start:css.index("}", start) + 1]


def test_task_pin_joins_the_shared_icon_scale():
    app = _read("app.js")
    # 不再用 cx/cy 绝对坐标画钉点；改成与其它标记一致的 translate + scale
    assert 'svgEl("circle", { cx: ux, cy: uy' not in app
    assert 'g.__emkBase = { sx: ux, sy: uy };' in app
    assert 'g.setAttribute("transform", "translate(" + ux + " " + uy + ") scale(1)");' in app
    # 半径补 ICON_SIZE_ANCHOR，抵消统一缩放里的 ICON_SCALE_BASE
    assert "var r = 7 * unit * ICON_SIZE_ANCHOR;" in app
    assert "state.markerScaleNodes.push(g);" in app
    assert "state.labelNodes.push({ node: label, size: size, stroke: stroke, alpha: false });" in app
    # renderOverlay 在 renderTaskPin 之前就跑过 updateCounterScale，末尾要补一次
    assert "// renderOverlay 的 updateCounterScale 在本函数之前已跑过，补一次让新节点立即生效" in app


def test_task_labels_follow_the_label_slider():
    app = _read("app.js")
    assert '"font-size": size * labelScale(),' in app
    assert '"stroke-width": stroke * labelScale()' in app
    # 只共享「大小」，透明度不跟着地名一起被压淡
    assert app.count("alpha: false });") >= 2
    assert 'if (it.alpha !== false) { it.node.setAttribute("opacity", a); }' in app
    # 任务 / 剧情名字与地名共用 labelNodes，滑条拖动时由 applyLabelStyle 就地更新
    assert "state.labelNodes.push({ node: label, size: size, stroke: stroke, alpha: false });" in app
    # 地名图层关闭时 renderLabels 不会跑，labelNodes 必须在 renderOverlay 里无条件清空
    assert "// R214：地名图层关闭时 renderLabels 不会被调用" in app
    assert "state.labelNodes = [];" in app
    rule = _rule(_read("tasks.css"), ".task-pin-label")
    assert "font: 700 12px" not in rule, "font 简写会覆盖 SVG 的 font-size 属性"
    assert "stroke-width: 3px;" not in rule
    assert "font-family:" in rule and "font-weight: 700;" in rule


def test_task_marker_icons_use_the_shared_scale_registration():
    app = _read("app.js")
    # makeMarker 统一登记，任务 / 剧情分支不另设固定尺寸
    assert "state.markerScaleNodes.push(g);" in app
    assert "R214：本节点在下方统一登记到 markerScaleNodes" in app
    assert 'g.appendChild(taskPointIcon(kind, icoUnit, item));' in app
    # 图标滑条与地名滑条各自只更新自己那一组节点
    assert "var inv = iconScale() / state.z;" in app
    assert "it.node.setAttribute(\"font-size\", it.size * s);" in app


JS_HARNESS = r"""
const fs = require('fs');
const src = fs.readFileSync('app.js', 'utf8');
function extractFn(name) {
  const i = src.indexOf('function ' + name + '(');
  if (i < 0) throw new Error('missing function ' + name);
  let depth = 0, started = false, quote = null;
  for (let k = i; k < src.length; k++) {
    const c = src[k];
    if (quote) { if (c === '\\') { k++; continue; } if (c === quote) quote = null; continue; }
    if (c === '"' || c === "'" || c === '`') { quote = c; continue; }
    if (c === '/' && src[k + 1] === '/') { while (k < src.length && src[k] !== '\n') k++; continue; }
    if (c === '/' && src[k + 1] === '*') { k = src.indexOf('*/', k + 2) + 1; continue; }
    if (c === '{') { depth++; started = true; }
    else if (c === '}') { depth--; if (started && depth === 0) return src.slice(i, k + 1); }
  }
  throw new Error('unbalanced function ' + name);
}
function bodyOf(name) {
  return extractFn(name).replace(/^function\s+\w+\([^)]*\)\s*\{/, '').replace(/\}\s*$/, '');
}
const results = [];
function check(name, cond) { results.push({ name, pass: !!cond }); }

/* 1) updateCounterScale：任务标 / 剧情标 / 任务钉点都吃同一份 scale(iconScale()/z) */
function node(sx, sy) {
  return { __emkBase: sx === null ? {} : { sx, sy }, attrs: {},
    setAttribute(k, v) { this.attrs[k] = v; } };
}
const a = node(100, 200), b = node(300, 400), c = node(null, null);
const state = { z: 2, markerScaleNodes: [a, b, c] };
const updateCounterScale = new Function('state', 'iconScale', bodyOf('updateCounterScale'));
function scaleOf(n) {
  const m = /scale\(([-0-9.e]+)\)/.exec(n.attrs.transform || '');
  return m ? Number(m[1]) : NaN;
}
updateCounterScale(state, () => 0.55 * 1.1);
check('图标滑条按 iconScale()/z 统一写入 transform',
  /^translate\(100 200\) scale\(/.test(a.attrs.transform || '')
  && /^translate\(300 400\) scale\(/.test(b.attrs.transform || '')
  && Math.abs(scaleOf(a) - 0.3025) < 1e-9 && Math.abs(scaleOf(b) - 0.3025) < 1e-9);
check('没有 __emkBase.sx 的节点不被误写', Object.keys(c.attrs).length === 0);
updateCounterScale(state, () => 0.55 * 1.9);
check('滑条调到 190% 后所有已登记标记同步放大',
  Math.abs(scaleOf(a) - 0.5225) < 1e-9 && Math.abs(scaleOf(b) - 0.5225) < 1e-9);

/* 2) applyLabelStyle：任务 / 剧情名字与地名共享字号、描边、透明度更新 */
function tnode() { return { attrs: {}, setAttribute(k, v) { this.attrs[k] = v; } }; }
const t1 = tnode(), t2 = tnode(), t3 = tnode();
const labelState = { labelNodes: [
  { node: t1, size: 10, stroke: 2.2 },
  { node: t2, size: 12, stroke: 2.4 },
  { node: t3, size: 10, stroke: 2.2, alpha: false }
] };
const applyLabelStyle = new Function('state', 'labelScale', 'labelAlpha', bodyOf('applyLabelStyle'));
applyLabelStyle(labelState, () => 1.9, () => 0.3);
check('地名滑条同时改所有文字节点的字号',
  Math.abs(Number(t1.attrs['font-size']) - 19) < 1e-9
  && Math.abs(Number(t2.attrs['font-size']) - 22.8) < 1e-9);
check('描边按同一系数缩放', Math.abs(t1.attrs['stroke-width'] - 4.18) < 1e-9);
check('透明度同步', t1.attrs.opacity === 0.3 && t2.attrs.opacity === 0.3);
check('任务名字只共享大小、不跟透明度',
  t3.attrs.opacity === undefined && Math.abs(Number(t3.attrs['font-size']) - 19) < 1e-9);

/* 3) renderTaskPin：任务目标钉点不再用绝对坐标，纳入统一缩放与文字滑条 */
function fake(tag, attrs) {
  return { tag, attrs: attrs || {}, children: [],
    setAttribute(k, v) { this.attrs[k] = v; },
    appendChild(c) { this.children.push(c); } };
}
const pinState = {
  taskPin: { point: { x: 10, z: 20 }, label: '测试任务目标' },
  fit: 100, z: 1, vb: [0, 0, 1000, 1000],
  markerScaleNodes: [], labelNodes: []
};
const pinEl = { overlay: { added: null, appendChild(n) { this.added = n; } } };
const pinMap = { id: 'm', key: 'm', worldToSvg: { a: 1, b: 0, c: 0, d: 0, e: 1, f: 0 } };
let counterCalls = 0;
const renderTaskPin = new Function(
  'state', 'el', 'map', 'svgEl', 'labelScale', 'labelAlpha',
  'ICON_SIZE_ANCHOR', 'updateCounterScale',
  bodyOf('renderTaskPin'));
renderTaskPin(pinState, pinEl, pinMap, fake, () => 1, () => 1, 2, () => { counterCalls++; });
const pin = pinEl.overlay.added;
check('钉点登记进 markerScaleNodes', pinState.markerScaleNodes.length === 1
  && pinState.markerScaleNodes[0] === pin);
check('钉点补跑一次 updateCounterScale', counterCalls === 1);
check('钉点用 translate+scale 且圆心在原点',
  /^translate\(10 20\) scale\(1\)$/.test(pin.attrs.transform || '')
  && pin.children[0].attrs.cx === undefined && pin.children[0].attrs.r > 0);
check('钉点名字登记进 labelNodes', pinState.labelNodes.length === 1
  && pinState.labelNodes[0].node === pin.children[2]);

console.log(JSON.stringify(results));
if (results.some(r => !r.pass)) process.exit(2);
"""


def test_scale_and_label_functions_are_deterministic():
    proc = subprocess.run(
        ["node", "-e", JS_HARNESS],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=60,
    )
    assert proc.returncode == 0, "Node 判定失败：\n%s\n%s" % (proc.stdout, proc.stderr)
    rows = json.loads(proc.stdout.strip().splitlines()[-1])
    failed = [r["name"] for r in rows if not r["pass"]]
    assert not failed, "未通过的判定：%s" % failed
    assert len(rows) == 11
