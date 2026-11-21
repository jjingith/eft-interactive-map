# -*- coding: utf-8 -*-
"""R20.5c：参考站 db4tarkov 枪械页对齐的自动化测试。

覆盖本轮落地项：
  1. 枪械浏览页改成「左侧口径色块 + 密集网格」（对照参考站每行最左的彩色口径块）；
  2. 口径色块颜色来自 data/caliber-groups.json 的真实弹药类别（不是随意配色）；
  3. 浏览页价格口径切换与工作台候选栏共用同一份 state.priceMode；
  4. 工作台新增「清空配件 / 回退一步」（对照参考站 Remove all attachment / Rollback）；
  5. 回退只改内存态装配，不写业务数据文件。

本轮不联网、不写业务数据；全部断言基于磁盘上的真实文件与静态代码契约。
"""
import hashlib
import io
import json
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "app.js")
HTML = os.path.join(ROOT, "index.html")
CSS = os.path.join(ROOT, "style.css")
CAL_GROUPS = os.path.join(ROOT, "data", "caliber-groups.json")


def _read(path):
    with io.open(path, encoding="utf-8") as fh:
        return fh.read()


def _fn(js, name, nxt=None):
    """截取 app.js 里某个函数的源码片段（到下一个顶层 function 之前）。"""
    m = re.search(r"function %s\s*\(" % re.escape(name), js)
    assert m, "找不到函数 %s" % name
    start = m.start()
    if nxt:
        m2 = re.search(r"function %s\s*\(" % re.escape(nxt), js[start + 10:])
        assert m2, "找不到后续函数 %s" % nxt
        end = start + 10 + m2.start()
    else:
        end = min(len(js), start + 4000)
    return js[start:end]


# ---------------------------------------------------------------- 数据前提
def test_caliber_groups_data_present():
    d = json.loads(_read(CAL_GROUPS))
    assert isinstance(d.get("calibers"), dict) and d["calibers"], "口径表为空"
    assert isinstance(d.get("categories"), list) and d["categories"], "类别表为空"
    for key, rec in d["calibers"].items():
        assert rec.get("caln"), key
        assert rec.get("cat"), key
    ids = set(c["id"] for c in d["categories"])
    for key, rec in d["calibers"].items():
        assert rec["cat"] in ids, (key, rec["cat"])


def test_caliber_color_classes_match_real_categories():
    """色块 CSS 类必须覆盖 caliber-groups.json 里真实存在的每一个类别。"""
    d = json.loads(_read(CAL_GROUPS))
    css = _read(CSS)
    for c in d["categories"]:
        assert (".gw-calcat-%s" % c["id"]) in css, "缺少类别配色：%s" % c["id"]


# ---------------------------------------------------------------- 口径色块 + 密集网格
def test_browse_group_uses_caliber_block_not_wide_header():
    js = _read(APP)
    assert 'blk.className = "gw-calblock "' in js, "口径分组没有左侧色块"
    assert 'className = "gw-browse-hd"' not in js, "仍保留整行标题带（与参考站布局不符）"


def test_browse_grid_is_dense():
    """卡片网格必须比改造前更密（原来 minmax(150px,1fr)，现在 ≤120px）。"""
    css = _read(CSS)
    mats = re.findall(r"grid-template-columns:\s*repeat\(auto-fill,\s*minmax\((\d+)px", css)
    assert mats, "找不到浏览网格的列定义"
    assert min(int(m) for m in mats) <= 120, "浏览网格仍过宽：%s" % mats


def test_browse_group_is_flex_row_with_block():
    css = _read(CSS)
    rules = re.findall(r"\.gun-workbench \.gw-browse-group\s*\{[^}]*\}", css)
    assert rules, "缺少 .gw-browse-group 规则"
    assert any("display: flex" in r for r in rules), \
        "分组不是横向排布（色块与网格应并排）：%s" % rules


# ---------------------------------------------------------------- 浏览页价格口径
def test_browse_page_has_price_pills():
    html = _read(HTML)
    # R265：口径 pills 上移到二级工具条 #vt-prices；浏览页不再单独一份
    assert 'id="gw-browseprices"' not in html
    assert 'id="vt-prices"' in html
    js = _read(APP)
    assert 'el.gwBrowsePrices = $("gw-browseprices")' in js
    assert "function renderGunBrowsePrices" in js


def test_price_pills_share_one_state():
    """浏览页与工作台必须共用 state.priceMode，不能各存各的。"""
    js = _read(APP)
    fn = _fn(js, "renderPricePills", "renderGunPrices")
    assert "state.priceMode = mode.key" in fn
    assert "renderGunBrowsePrices()" in fn
    assert "renderGunPrices()" in fn
    # 不允许出现第二份价格口径状态
    assert not re.search(r"state\.gunPriceMode\s*=", js)


def test_browse_price_pill_click_redraws_cards():
    js = _read(APP)
    fn = _fn(js, "renderGunBrowsePrices")
    assert "renderGunBrowse()" in fn, "切换口径后必须重绘卡片价格"


# ---------------------------------------------------------------- 清空 / 回退
def test_clear_controls_replaced_by_toolbar_links():
    """R19.91：LOAD VARIANT 行删除，清空配件/回退按钮不再显示；
    清空预设改为「恢复默认」，清空/回退逻辑函数保留但不再挂按钮。"""
    html = _read(HTML)
    assert 'id="gw-clearall"' not in html
    assert 'id="gw-undo"' not in html
    js = _read(APP)
    assert 'el.gwClearAll = $("gw-clearall")' not in js
    assert 'el.gwUndo = $("gw-undo")' not in js
    assert "applyDefaultBuild(false)" in js


def test_clear_all_records_history_and_undo_restores():
    js = _read(APP)
    clear = _fn(js, "clearGunAll", "syncGunHistoryUi")
    assert "gunPushHistory()" in clear, "清空前必须记快照，否则回退恢复不了"
    assert "g.installed = {}" in clear
    undo = _fn(js, "gunUndo", "clearGunAll")
    assert "g.history.pop()" in undo
    assert "g.installed = snap" in undo


def test_history_is_memory_only_and_cleared_on_gun_switch():
    js = _read(APP)
    assert "history: []" in js
    sel = _fn(js, "selectGun")
    assert "g.history = []" in sel, "换枪必须清空回退历史（不能跨枪回退）"
    # 历史不得写进 localStorage：LS_GUN 的序列化里不能出现 history
    m = re.search(r"localStorage\.setItem\(LS_GUN[^;]*;", js)
    if m:
        assert "history" not in m.group(0), "回退历史不应写入本地存储"


def test_undo_button_disabled_without_history():
    js = _read(APP)
    fn = _fn(js, "syncGunHistoryUi")
    assert "el.gwUndo.disabled" in fn


# ---------------------------------------------------------------- 不越界
def test_no_business_data_written_by_this_round():
    """本轮只改前端：前端不得具备任何写盘通道，业务数据只能被读取。"""
    js = _read(APP)
    for bad in ("writeFile", "writeFileSync", "saveJSON", "XMLHttpRequest",
                "fs.write", "require('fs')"):
        assert bad not in js, "前端不应出现写盘能力：%s" % bad
    # 业务数据的取用只能走只读入口（loadJSON / 预置 JS 全局）
    for name in ("data/items.json", "data/gunslots.json", "data/maps.json"):
        hits = [ln.strip() for ln in js.splitlines() if name in ln and "loadJSON(" in ln]
        assert hits, "业务数据 %s 没有任何只读入口" % name
    # 枪械预设由构建期生成的 data/gun-presets.js 以全局变量注入（同样是只读）
    html = _read(HTML)
    assert "gun-presets.js" in html, "缺少 data/gun-presets.js 的只读注入"


def test_business_data_hashes_unchanged():
    """业务数据必须仍与 R20.3 基线一致（本轮没碰过数据文件）。

    基线变更记录：
    - 2026-11-05 r79-eyewear-zones：`data/items.json` 基线从
      `599aef5e…4172d` 更新为 `33af6bd6…a3a9`。原因：R79 眼部防护兜底，
      依据 `data/game-truth/armor_items.json` 的 `props.armorColliders`
      给 16 件 `z` 为空的眼镜/面罩补防护区域（6B34 护目镜 = `["Eyes"]`）。
      已核验差异仅为这 16 件新增 `z` 字段（400 字节），去掉后重新序列化
      可精确复现旧哈希 `599aef5e…4172d`。
    """
    base = {
        # 2026-11-18 R300b：`sn` 从上游本地化键（"<id> ShortName"）替换为中文名表里的
        # 游戏内缩写（6B43 / PACA / ULACH / 帽…），文件因此变小。
        "data/items.json": "5e2c415eb1dcafa264b70b100e9a460a51dd8fbf79ac4579ef4324c28e97dfe0",
        "data/gunslots.json": "29b987b34a931b6ad5ec7587ff70bb36a112688e3303fb6467862fcaf21f8e3e",
        "data/gun-presets.json": "64e29bb5394bbd4a2d0845845f4ffc8748137fb8a8c216e77bd10e7cb452744b",
    }
    for rel, want in base.items():
        p = os.path.join(ROOT, rel)
        got = hashlib.sha256(io.open(p, "rb").read()).hexdigest()
        assert got == want, "%s 内容已变：%s" % (rel, got)


def test_caliber_groups_is_optional():
    """口径数据缺失时只能影响配色，不能让浏览页崩。"""
    js = _read(APP)
    fn = _fn(js, "ensureCaliberGroups")
    assert ".catch(function ()" in fn, "口径数据加载失败必须有兜底"
    assert "state.caliberGroups = null" in fn


@pytest.mark.parametrize("name", ["renderCalLegend", "caliberCatOf", "gwGroupColorKey",
                                  "gunPushHistory", "gunUndo", "clearGunAll"])
def test_new_functions_exist(name):
    js = _read(APP)
    assert "function %s" % name in js, "缺少函数 %s" % name
