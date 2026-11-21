# -*- coding: utf-8 -*-
"""R213：点选轮廓描边、右侧共用搜索栏、收起按钮恢复比例。

静态断言锁定 DOM / 样式结构，再用 Node 抽出 app.js 的半径换算函数验证
「3 屏幕像素」在不同地图缩放下都成立。
"""
from __future__ import annotations

import json
import os
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
XP_CSS = os.path.join("assets", "xp-ui", "xp-ui-app.css")


def _read(rel: str) -> str:
    with open(os.path.join(ROOT, rel), "r", encoding="utf-8") as f:
        return f.read()


def _rule(css: str, selector: str) -> str:
    start = css.index(selector + " {")
    return css[start:css.index("}", start) + 1]


# ---------------------------------------------------------------- 点选轮廓

def test_click_ring_is_replaced_by_alpha_outline_filter():
    app = _read("app.js")
    # 不再创建任何圆圈节点
    assert 'svgEl("circle", { class: "emk-ring"' not in app
    assert 'var ring = svgEl("circle"' not in app
    # 改成给图标本体挂 SVG 滤镜
    assert 'first.setAttribute("filter", "url(#" + OUTLINE_ID + ")");' in app
    assert 'first.classList.add("emk-outline-on");' in app
    assert "clearOutline();" in app
    # 生命周期与旧环一致：3.4s 自删
    assert "}, 3400);" in app


def test_outline_is_three_pixels_gray_white_black_inside_out():
    app = _read("app.js")
    assert 'var OUTLINE_COLORS = ["#9a9a9a", "#ffffff", "#000000"];' in app
    assert "[1, 2, 3].forEach" in app
    assert 'operator: "dilate"' in app
    for k in (1, 2, 3):
        assert 'result: "d" + k' in app
    # 逐层相减取环，外层先画、原图最后画（最上层）
    assert 'in2: "d2", operator: "out", result: "o3"' in app
    assert 'in2: "a0", operator: "out", result: "o1"' in app
    # 抗锯齿边缘必须先二值化，否则三层环 alpha<1 会被混成一片灰，白 / 黑出不来
    assert '"in": "SourceAlpha", result: "a0"' in app
    assert 'svgEl("feFuncA", { type: "linear", slope: "100" })' in app
    assert '[3, 2, 1].forEach(function (k) { merge.appendChild' in app
    assert '"in": "SourceGraphic"' in app
    css = _read("style.css")
    assert ".emk-ring {" not in css
    assert "#emk-select-outline SVG 滤镜" in css


# ---------------------------------------------------------------- 共用搜索栏

def test_only_one_search_input_on_the_right_panel():
    html = _read("index.html")
    assert 'id="search"' not in html, "物资刷新点区不应再有独立输入框"
    assert html.count('id="task-search"') == 1
    assert "搜索任务 / 剧情 / 物资刷新点 / 撤离点" in html
    # 结果容器仍在，只是不再自带输入框
    assert 'id="pinned-list"' in html
    assert 'id="search-results"' in html
    assert 'id="task-search-reset"' in html


def test_both_search_consumers_read_the_same_input():
    app = _read("app.js")
    assert '$("search")' not in app
    assert "el.taskSearch = $(\"task-search\");" in app
    assert "el.search = el.taskSearch;" in app
    # 同一个 input 上挂着两个订阅者
    assert 'el.taskSearch.addEventListener("input", renderTaskPanel);' in app
    assert 'el.search.addEventListener("input", renderSearchResults);' in app
    # 清空 / 回填都走统一入口或直接同步刷新两处
    assert "function syncSharedSearch(value)" in app
    assert 'dispatchEvent(new Event("input", { bubbles: true }));' in app
    assert 'syncSharedSearch("");' in app
    assert "renderTaskPanel();       // R213：共用搜索栏，任务列表也按回填词重算" in app


# ---------------------------------------------------------------- 收起按钮

def test_collapse_button_is_square_again():
    css = _read("style.css")
    base = _rule(css, ".task-panel-collapse")
    assert "width: 30px;" in base
    assert "height: 30px;" in base
    xp = _read(XP_CSS)
    head = _rule(xp, "html body header.task-panel-head")
    assert "height: 34px;" in head
    btn = _rule(xp, "html body header.task-panel-head .task-panel-collapse")
    assert "width: 30px;" in btn
    assert "height: 30px;" in btn
    assert "padding: 0;" in btn
    assert "height: 20px" not in btn


# ---------------------------------------------------------------- Node：半径换算

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

const steps = [1, 2, 3].map(k => ({
  radius: String(k),
  getAttribute(n) { return n === 'data-outline-k' ? String(k) : null; },
  setAttribute(n, v) { if (n === 'radius') this.radius = v; }
}));
let defs = { querySelectorAll() { return steps; } };
function ensureOutlineFilter() { return defs; }
function sizeOutline(target) {
  // 把抽出来的函数体放到这个作用域里执行
  const fn = new Function('ensureOutlineFilter', 'target',
    extractFn('sizeOutlineFilter').replace(/^function sizeOutlineFilter\([^)]*\)\s*\{/, '')
      .replace(/\}\s*$/, ''));
  return fn(ensureOutlineFilter, target);
}
const results = [];
function check(name, cond) { results.push({ name, pass: !!cond }); }

sizeOutline({ getScreenCTM: () => ({ a: 2, b: 0 }) });
check('放大 2x 时三层半径 = 0.5/1/1.5 用户单位',
  steps.map(s => Number(s.radius)).join(',') === '0.5,1,1.5');
sizeOutline({ getScreenCTM: () => ({ a: 0.5, b: 0 }) });
check('缩小 0.5x 时三层半径 = 2/4/6 用户单位',
  steps.map(s => Number(s.radius)).join(',') === '2,4,6');
check('换算后恒为 3 屏幕像素（各层 × scale 相加）',
  [2, 0.5].every(sc => {
    sizeOutline({ getScreenCTM: () => ({ a: sc, b: 0 }) });
    return Math.abs(Number(steps[2].radius) * sc - 3) < 1e-9;
  }));
sizeOutline({ getScreenCTM: () => null });
check('拿不到 CTM 时回落 scale=1，不产生 NaN',
  steps.every(s => Number.isFinite(Number(s.radius)) && Number(s.radius) > 0));

console.log(JSON.stringify(results));
if (results.some(r => !r.pass)) process.exit(2);
"""


def test_outline_radius_is_three_screen_pixels():
    proc = subprocess.run(
        ["node", "-e", JS_HARNESS],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=60,
    )
    assert proc.returncode == 0, "Node 判定失败：\n%s\n%s" % (proc.stdout, proc.stderr)
    rows = json.loads(proc.stdout.strip().splitlines()[-1])
    failed = [r["name"] for r in rows if not r["pass"]]
    assert not failed, "未通过的判定：%s" % failed
    assert len(rows) == 4
