# -*- coding: utf-8 -*-
"""R229/R230：口径按钮「亮 = 当前显示在表格里，灰 = 当前不显示」。

用户原话（2026-11-10 20:02 / 20:22 / 20:23）：
  「子弹页面 右侧的筛选 我希望点击后 如果是不显示的子弹 按钮就变灰
    现在不知道哪些显示 哪些不显示」
  「凡是被口径过滤掉、当前没在显示的口径也一律变灰，只留选中的亮着 要的就是这个啊」
  「而且你现在做的是搜索 我要的是右侧的筛选按钮 按下后就有变化」

R229 做反了（按不含口径过滤的池子算，点口径按钮时侧栏不变）；R230 改向为
按**最终显示行** amFilterByCal(pool) 统计：
  - 没选口径：所有有子弹的口径都亮，0 发的灰；
  - 选中若干口径：只有选中的那几个（且确实有子弹）亮，其余一律灰；
  - 灰有两种原因，title 分别说明；灰不是禁用（点一下就加入选中集合）。
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


# ------------------------------------------------------------------ 静态契约

def test_chip_helpers_exist():
    app = _read("app.js")
    for fn in ("amChipOneHit", "amChipCounts", "amRowsBase", "amFilterByCal",
               "amChipEmptyState", "syncAmmoChipEmpty"):
        assert "function %s(" % fn in app, "缺少 %s" % fn


def test_greying_uses_shown_rows_not_base_pool():
    """R230：亮/灰必须按最终显示行算；只用 base 池会让点口径按钮毫无变化。"""
    app = _read("app.js")
    body = app[app.index("function amRowsBase"):app.index("function amFilterByCal")]
    assert "amChipHit" not in body, "amRowsBase 里不得出现口径过滤"
    sync = app[app.index("function syncAmmoChipEmpty"):app.index("function renderAmmoFilterUI")]
    assert "shownCounts = amChipCounts(shown)" in sync
    assert "baseCounts = amChipCounts(base)" in sync
    assert "shown === 0" in app[app.index("function amChipEmptyState"):]
    assert "syncAmmoChipEmpty(pool, rows)" in app, "renderAmmo 必须传最终显示行"
    assert "amChipCounts(shownRows)" in app, "重建 chips 时也要按最终显示行"


def test_chips_click_path_recomputes_grey():
    """点口径按钮只改 aria-pressed 再调 renderAmmo，灰态必须由 renderAmmo 刷新。"""
    app = _read("app.js")
    seg = app[app.index("el.amGroups.addEventListener(\"click\""):]
    seg = seg[:seg.index("if (node.dataset.act === \"show\"")]
    assert "node.dataset.cal" in seg and "renderAmmo();" in seg
    body = app[app.index("function renderAmmo()"):app.index("function renderAmmoGraph")]
    assert "syncAmmoChipEmpty(pool, rows)" in body


def test_search_path_syncs_grey_state():
    """搜索只走 createTable.setSearch，不重绘表格；亮/灰必须单独同步。"""
    app = _read("app.js")
    seg = app[app.index("el.amSearch.addEventListener(\"input\""):]
    seg = seg[:seg.index("if (el.amGroups)")]
    assert "syncAmmoChipEmpty(pool, shownRows)" in seg
    assert "amFilterByCal(pool)" in seg


def test_chip_render_marks_empty():
    app = _read("app.js")
    assert "amChipEmptyState(chip, it.k, shownCounts[it.k] || 0, baseCounts[it.k] || 0);" in app


def test_grey_is_not_disabled():
    app = _read("app.js")
    body = app[app.index("function amChipEmptyState"):app.index("function syncAmmoChipEmpty")]
    assert "dataset.empty" in body
    assert "disabled" not in body and "aria-disabled" not in body, "置灰不是禁用，按钮仍可点"
    assert "当前筛选下 0 发子弹" in body
    assert "当前未选中" in body and "点击可加入" in body


def test_css_grey_state_in_both_themes():
    css = _read("style.css")
    assert '.am-workbench .am-chip[data-empty="1"]' in css
    assert '.am-chip[data-empty="1"][aria-pressed="true"]' in css
    xp = _read("theme-windows-xp.css")
    assert '.am-chip[data-empty="1"]:not([aria-pressed="true"])' in xp
    assert "opacity: .45" in xp
    assert '.am-chip[data-empty="1"][aria-pressed="true"]' in xp


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

// 桩：口径元数据来自 state.ammo.chips，筛选状态来自 amFilterState()
globalThis.state = {
  amFilter: { cals: {} },
  ammo: {
    chips: [
      { g: 'pistol', items: [{ k: '9x19', cal: 'Caliber9x19' }, { k: '9x18', cal: 'Caliber9x18' }] },
      { g: 'shot', items: [
        { k: '12 号霰弹', cal: 'Caliber12g', atyp: 'buckshot' },
        { k: '12 号独头弹', cal: 'Caliber12g', atyp: 'slug' }
      ] }
    ]
  }
};
globalThis.amFilterState = function () { return state.amFilter; };

const code = ['amChipMeta', 'amChipOneHit', 'amChipHit', 'amAnyCal',
              'amChipCounts', 'amFilterByCal', 'amChipEmptyState']
  .map(extractFn).join('\n');
const run = new Function(code + '\n return { amChipMeta, amChipOneHit, amChipHit, amAnyCal, amChipCounts, amFilterByCal, amChipEmptyState };')();

const rows = [
  { id: 'a', cal: 'Caliber9x19', caln: '9x19', t: 'bullet', pen: 20 },
  { id: 'b', cal: 'Caliber9x19', caln: '9x19', t: 'bullet', pen: 45 },
  { id: 'c', cal: 'Caliber12g', caln: '12/70', t: 'buckshot', pen: 3 },
  { id: 'd', cal: 'Caliber12g', caln: '12/70', t: 'bullet', pen: 5 }
];

const counts = run.amChipCounts(rows);          // base 池（没选口径时等于最终行）
// R230：选中 9x19 之后，按「最终显示行」计数时其余口径必须归零
state.amFilter.cals = { '9x19': true };
const filtered = run.amFilterByCal(rows);
const countsOfShown = run.amChipCounts(filtered);
state.amFilter.cals = {};

// atyp 拆分：霰弹 / 独头弹各自只算自己那一类
const oneHit = {
  shotOnly: run.amChipOneHit('12 号霰弹', rows[2]),
  shotVsSlug: run.amChipOneHit('12 号霰弹', rows[3]),
  slugOnly: run.amChipOneHit('12 号独头弹', rows[3]),
  unknown: run.amChipOneHit('不存在', rows[0])
};

function chip(shownN, baseN) {
  const el = { dataset: {}, title: '' };
  run.amChipEmptyState(el, '9x18', shownN, baseN);
  return { empty: el.dataset.empty, title: el.title };
}

console.log(JSON.stringify({
  counts: counts,
  countsOfShown: countsOfShown,
  filteredIds: filtered.map(r => r.id),
  oneHit: oneHit,
  greyByCal: chip(0, 3),
  greyByZero: chip(0, 0),
  normal: chip(2, 3)
}));
"""


def test_node_chip_logic():
    node = shutil.which("node")
    if not node:
        import pytest
        pytest.skip("node 不在 PATH")
    tmp = tempfile.mkdtemp(prefix="r229_")
    try:
        script = os.path.join(tmp, "h.js")
        with open(script, "w", encoding="utf-8") as fh:
            fh.write(NODE_HARNESS)
        proc = subprocess.run([node, script, os.path.join(ROOT, "app.js")],
                              capture_output=True, text=True, encoding="utf-8", timeout=60)
        assert proc.returncode == 0, proc.stderr[-900:]
        out = json.loads(proc.stdout.strip().splitlines()[-1])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # 每个口径在 base 池里的命中数（用于解释灰的原因）
    assert out["counts"] == {"9x19": 2, "9x18": 0,
                             "12 号霰弹": 1, "12 号独头弹": 1}
    # R230 核心：选中 9x19 后，按最终显示行计数时未选中口径全部归零 → 变灰
    assert out["countsOfShown"] == {"9x19": 2, "9x18": 0,
                                    "12 号霰弹": 0, "12 号独头弹": 0}
    assert out["filteredIds"] == ["a", "b"]
    # 霰弹 / 独头弹的 atyp 语义不能串
    assert out["oneHit"] == {"shotOnly": True, "shotVsSlug": False,
                             "slugOnly": True, "unknown": False}
    # 灰的两种原因分别说明；亮的不加提示
    assert out["greyByCal"]["empty"] == "1" and "当前未选中" in out["greyByCal"]["title"]
    assert out["greyByZero"]["empty"] == "1" and "0 发子弹" in out["greyByZero"]["title"]
    assert out["normal"]["empty"] == "0" and "当前未选中" not in out["normal"]["title"]
