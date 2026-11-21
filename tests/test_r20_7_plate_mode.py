# -*- coding: utf-8 -*-
"""R20.7：对照 db4tarkov 预设页「插板」相关按钮的复刻验收。

参考站实况（rea 实测 + main.dart.js 佐证）：
  · 预设页候选表在**逻辑宽度 > 1236** 时才多出 Front / Back / Left / Right 四个插板格；
  · 点某一格 → 弹出按 Plate Class 分组的插板列表，选中后该格显示等级/材质/耐久，
    并且该行的 Mov/Turn/Erg 惩罚与价格立刻跟着变；
  · 顶部 picked / default / priority Plates 三段开关决定「用谁挑的板」：
      picked   = 用户自己挑的（没挑过就留空）
      default  = 护甲默认板（惩罚最重的那组）
      priority = 价格优先（惩罚介于两者之间）
  · 三段开关是**纯计算**：切回 picked，用户原来挑的插板原样还在。

本地对应实现（本轮新增）：
  · `state.plateMode` 1/2/3 + `equippedList()` 在 2/3 模式下并入**虚拟插板行**，
    不写 `state.loadout`，所以切回 picked 不会吞用户选择；
  · `plateSlotState` 里「用户挑的」优先于自动板，自动板带 `st.auto` 标记；
  · 顺带补上参考站表头可点的 Kg / Price 排序，以及 3-slot / 4-slot 的「板位数」筛选。
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import textwrap

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_JS = os.path.join(ROOT, "app.js")
HTML = os.path.join(ROOT, "index.html")
CSS = os.path.join(ROOT, "style.css")


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------- 界面骨架
def test_plate_mode_buttons_in_html():
    html = _read(HTML)
    assert 'id="lw-plate-mode"' in html, "筛选条缺少插板策略按钮组"
    for mode in ("1", "2", "3"):
        assert 'data-lwpmode="%s"' % mode in html, "缺少插板策略按钮 %s" % mode
    # 三段互斥：默认选中 picked
    assert re.search(r'data-lwpmode="1"[^>]*aria-pressed="true"', html), \
        "默认应停在 picked（挑的插板）"


def test_slot_count_filter_in_html():
    html = _read(HTML)
    assert 'id="lw-slots"' in html, "缺少板位数过滤下拉"
    for v in ("2", "3", "4"):
        assert '<option value="%s">%s</option>' % (v, v) in html


def test_kg_price_sort_buttons_in_html():
    html = _read(HTML)
    for key in ("kg", "price"):
        assert 'data-lwsort="%s"' % key in html, "缺少 %s 排序按钮" % key


def test_plate_mode_styles_scoped():
    css = _read(CSS)
    assert ".loadout-workbench .lw-modebtn" in css
    assert ".loadout-workbench .lw-modebtn.is-on" in css
    assert ".loadout-workbench .lw-plate-cell.is-auto" in css, "自动插板需要可区分的视觉标记"
    # 不能漏到全局作用域（会污染地图 / 配枪视图）
    assert "\n.lw-modebtn {" not in css


# ---------------------------------------------------------------- 源码不变量
def test_plate_mode_state_and_scopes():
    js = _read(APP_JS)
    assert "plateMode: 1," in js, "缺少 plateMode 状态"
    assert 'var PLATE_MODE_SCOPES = ["armor", "rig"];' in js


def test_virtual_rows_do_not_write_loadout():
    """自动插板必须是「虚拟行」：只进 equippedList()，绝不落进 state.loadout。

    这是与参考站保持一致的关键——参考站切成 picked 后用户挑的插板还在，
    本地如果切模式时往 loadout 写值，切回来就会把用户的选择覆盖掉。
    """
    js = _read(APP_JS)
    start = js.index("function equippedList()")
    end = js.index("function gearTotals()", start)
    body = js[start:end]
    assert not re.search(r"state\.loadout\[[^\]]+\]\s*=", body), \
        "equippedList 里不允许写 state.loadout（自动板必须是虚拟行）"
    assert "delete state.loadout" not in body


def test_user_pick_wins_over_auto():
    js = _read(APP_JS)
    start = js.index("function effectivePlate(")
    end = js.index("var plateModal", start)
    body = js[start:end]
    assert "var own = plateGet(slotId, armorId);" in body
    assert "if (own) { return { id: own, auto: false }; }" in body, \
        "用户挑的插板必须优先于自动板"


def test_auto_plate_marked_and_right_click_skipped():
    js = _read(APP_JS)
    assert "st.auto = !!(eff && eff.auto);" in js
    # 自动板 / 默认占位都不绑右键卸下（它们不是「用户真装上的板」）
    assert "if (!st.auto && !st.dflt) {" in js


def test_kept_plate_state_for_unequipped_armor():
    """换到别的护甲后，原先那件的插板图标不能清空。

    用独立状态 "kept"（记住的）而不是 "on"（已安装），既满足「图标还在」，
    又守住 R19.26 的老契约：未装备的护甲不能报「已安装」。
    """
    js = _read(APP_JS)
    assert 'st.state = (eff && eff.kept) ? "kept" : "on";' in js
    assert "eff = { id: own, auto: false, kept: !equippedHere };" in js
    # 渲染、点击都要覆盖 kept
    assert 'st.state === "kept"' in js
    assert 'st.state === "default" || st.state === "kept"' in js
    css = _read(CSS)
    assert ".loadout-workbench .lw-plate-cell.is-kept" in css


def test_default_placeholder_when_nothing_picked():
    """没挑过插板时，槽位要显示默认插板的**灰显占位**（不计重量/惩罚）。"""
    js = _read(APP_JS)
    assert 'st.state = "default";' in js
    assert "st.dflt = true;" in js
    assert "灰显占位，尚未启用" in js
    css = _read(CSS)
    assert ".loadout-workbench .lw-plate-cell.is-default .lw-plate-img" in css
    # 去色用 saturate(0)：与 grayscale 视觉等价，但不占用 r18 明令禁止的
    # `filter: grayscale(1)`（那条禁令是为面罩剪影留的），避免两条规则互相打架。
    assert "saturate(0)" in css


def test_slot_filter_only_for_armor_tables():
    js = _read(APP_JS)
    assert 'rootKey === "armor" || rootKey === "rig"' in js
    assert "hardPlateSocketCount(rec) !== state.lwSlots" in js


def test_sorters_registered():
    js = _read(APP_JS)
    for key in ("mov", "turn", "ergo", "kg", "price"):
        assert re.search(r"\b%s: function \(r\)" % key, js), "缺少 %s 排序器" % key


def test_plate_mode_wired_to_full_refresh():
    """切策略要同时刷候选表 + 左侧统计 + 费用（否则会出现「表格变了数字没变」）。"""
    js = _read(APP_JS)
    start = js.index("var mode = Number(b.dataset.lwpmode) || 1;")
    body = js[start:start + 900]
    for fn in ("renderGearFilters", "refreshGearTable", "renderGearSide", "renderGearCost"):
        assert fn + "()" in body, "切插板策略后没有调用 %s()" % fn


# ---------------------------------------------------------------- node 真跑
HARNESS = r"""
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8');

function extract(name) {
  const i = src.indexOf('function ' + name + '(');
  if (i < 0) { throw new Error('missing function ' + name); }
  let k = src.indexOf('{', i), depth = 0;
  for (; k < src.length; k++) {
    const c = src[k];
    if (c === '{') { depth++; }
    else if (c === '}') { depth--; if (depth === 0) { return src.slice(i, k + 1); } }
  }
  throw new Error('unbalanced ' + name);
}

const ITEMS = {
  cheap_light: { id: 'cheap_light', cl: 3, dur: 40, w: 1.0, price: 100 },
  pricey_heavy: { id: 'pricey_heavy', cl: 6, dur: 60, w: 3.0, price: 900 },
  mid: { id: 'mid', cl: 5, dur: 55, w: 2.0, price: 400 },
  noprice: { id: 'noprice', cl: 5, dur: 80, w: 4.0 },
};

global.itemRec = (id) => ITEMS[id] || null;
global.numOr0 = (v) => (typeof v === 'number' && isFinite(v)) ? v : 0;
global.itemPrice = (rec) => (rec && typeof rec.price === 'number') ? rec.price : 0;

eval(extract('autoPlatePick'));

const socket = { plates: ['cheap_light', 'pricey_heavy', 'mid', 'noprice'] };
const out = {
  default: autoPlatePick(socket, 2),
  priority: autoPlatePick(socket, 3),
  empty: autoPlatePick({ plates: [] }, 2),
  missing: autoPlatePick({ plates: ['ghost'] }, 3),
};
console.log(JSON.stringify(out));
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="需要 node 才能跑插板策略动态测试")
def test_auto_plate_pick_dynamic(tmp_path):
    harness = tmp_path / "plate_mode.js"
    harness.write_text(HARNESS, encoding="utf-8")
    proc = subprocess.run(["node", str(harness), APP_JS],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert proc.returncode == 0, "插板策略动态测试失败：\n%s\n%s" % (proc.stdout, proc.stderr)
    out = json.loads(proc.stdout.strip().splitlines()[-1])

    # default：防护等级优先（pricey_heavy 是 cl 6），同级才比耐久
    assert out["default"] == "pricey_heavy", "default 应挑防护最高的插板"
    # priority：价格优先（cheap_light 100 最便宜）
    assert out["priority"] == "cheap_light", "priority 应挑最便宜的插板"
    # 边界：没有合法插板 → null，不抛异常
    assert out["empty"] is None
    assert out["missing"] is None, "数据缺失的插板要跳过，不能返回一个不存在的 id"


# ---------------------------------------------------------------- R20.7c 右栏放不下
def test_liner_detail_toggle_in_html():
    html = _read(HTML)
    assert 'id="lw-liner-detail"' in html, "筛选条缺少「内衬明细」开关"
    assert "内衬明细" in html


def test_liner_detail_defaults_on():
    """R20.7e：内衬九列**默认常驻**。

    R20.7c 曾把九列默认折叠（用户反馈："我要求改成参考站那样，不是删掉"）。
    参考站这九列是在的（窄列 + 两行等级/耐久），所以改回默认显示，
    宽度改由渲染层的紧凑列宽表解决。
    """
    js = _read(APP_JS)
    assert "lwLinerDetail: true," in js, "内衬九列必须默认常驻（用户要求不是删掉）"
    html = _read(HTML)
    assert 'id="lw-liner-detail" checked' in html, "开关的初始勾选状态应与默认一致"


def test_visible_columns_filters_only_at_render_layer():
    """折叠只能在渲染层：gearColumns 必须仍然返回完整 21 列（T24/R11 的契约）。"""
    js = _read(APP_JS)
    # gearColumns 体内不许出现 liner_ 过滤
    start = js.index("function gearColumns(node, mode) {")
    end = js.index("function visibleGearColumns(", start) if "function visibleGearColumns(" in js[start:] else len(js)
    # visibleGearColumns 定义在 gearColumns 之前，按实际位置取段
    gi = js.index("function gearColumns(node, mode) {")
    vi = js.index("function visibleGearColumns(")
    body_gear = js[gi:vi] if vi > gi else js[gi:gi + 6000]
    assert 'indexOf("liner_")' not in body_gear, "gearColumns 里不许过滤 liner_ 列"

    vstart = js.index("function visibleGearColumns(")
    vend = js.index("function gearColumns(node, mode) {", vstart)
    vbody = js[vstart:vend]
    assert 'indexOf("liner_") !== 0' in vbody
    assert "if (state.lwLinerDetail) { return cs; }" in vbody


def test_render_calls_use_visible_columns():
    js = _read(APP_JS)
    assert js.count("visibleGearColumns(") >= 5, "渲染层调用点应改用 visibleGearColumns"
    assert "columns: gearColumns(currentNode(), state.priceMode)" not in js
    assert "state.gearTable.setColumns(gearColumns(" not in js


# ---------------------------------------------------------------- R20.7d 行高 / 名称两行
SHORTNAME_HARNESS = r"""
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8');
function extract(name) {
  const i = src.indexOf('function ' + name + '(');
  if (i < 0) { throw new Error('missing function ' + name); }
  let k = src.indexOf('{', i), depth = 0;
  for (; k < src.length; k++) {
    const c = src[k];
    if (c === '{') { depth++; }
    else if (c === '}') { depth--; if (depth === 0) { return src.slice(i, k + 1); } }
  }
  throw new Error('unbalanced ' + name);
}
eval(extract('shortNameOf'));
const cases = {
  "6B43 屏障-Sh 防弹衣（数码丛林迷彩）": "6B43",
  "FORT Redut-T5（堡垒-T5）防弹衣（烟雾迷彩）": "FORT Redut-T5",
  "LBT 6094A Slick 插板背心（橄榄绿）": "LBT 6094A Slick",
  "5.11 Hexgrid 插板背心": "5.11 Hexgrid",
  "BNTI Zhuk（甲虫）防弹衣（数码丛林迷彩）": "BNTI Zhuk",
  "没有英文名": "",
};
const out = {};
for (const k in cases) { out[k] = shortNameOf(k); }
console.log(JSON.stringify(out));
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="需要 node 才能跑短名推导测试")
def test_short_name_derivation(tmp_path):
    """参考站的名称列是「短名 + 全名」两行；本地 items.json 的 sn 字段不可用，
    只能从中文全名推导短名 —— 规则：截掉第一个中文括号前的内容，取连续的英文/数字片段。"""
    harness = tmp_path / "shortname.js"
    harness.write_text(SHORTNAME_HARNESS, encoding="utf-8")
    proc = subprocess.run(["node", str(harness), APP_JS],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert proc.returncode == 0, "短名推导测试失败：\n%s\n%s" % (proc.stdout, proc.stderr)
    out = json.loads(proc.stdout.strip().splitlines()[-1])
    assert out["6B43 屏障-Sh 防弹衣（数码丛林迷彩）"] == "6B43"
    assert out["FORT Redut-T5（堡垒-T5）防弹衣（烟雾迷彩）"] == "FORT Redut-T5"
    assert out["LBT 6094A Slick 插板背心（橄榄绿）"] == "LBT 6094A Slick"
    assert out["5.11 Hexgrid 插板背心"] == "5.11 Hexgrid"
    assert out["BNTI Zhuk（甲虫）防弹衣（数码丛林迷彩）"] == "BNTI Zhuk"
    assert out["没有英文名"] == "", "没有英文片段时应返回空串（退化成单行全名）"


def test_row_height_matches_reference():
    """R300b：用户要求按 db4 的紧凑行高重排（不再保留 R26.0 的 78px）。

    护甲表 46px、其余单行类别 26px 由 app.js 按类别写入 CSS 变量；
    插板格继续跟随行高变量。
    """
    css = _read(CSS)
    assert "--lw-table-row-height: 46px;" in css
    assert "calc(var(--lw-table-row-height) - 1px)" in css, "插板格高度应跟着行高走"


def test_name_cell_two_lines():
    js = _read(APP_JS)
    assert "function shortNameOf(" in js
    assert 'b.className = "lw-name-short";' in js
    assert 'full.className = "lw-name-full";' in js
    css = _read(CSS)
    assert ".loadout-workbench .lw-name-short" in css
    assert ".loadout-workbench .lw-name-full" in css
    # 两行规则必须压过通用的 `> span`（它更具体），所以要带 .lw-name-plain 再加一层
    assert '.tbl-cell[data-key="n"] > span.lw-name-plain' in css
