# -*- coding: utf-8 -*-
"""R41 专项测试：db4tarkov 任务页复刻 + 商人英文名 / 游戏内头像。

覆盖任务书里的验收点：
  A 任务页结构 —— 搜索条 / 商人头像条 / 按商人分组列表 / 右筛选栏 / exp / Complete
  B 保留能力   —— 任务点位定位（data-db4-loc → GWMapFocus）、搜索含英文名与目标英文
  C 视觉令牌   —— db4 深色变量、右栏居中按钮与选中反白、Complete 为文字链接
  D 商人英文名 —— 16 位商人 nameEn 为游戏内英文名、无中文、核心商人齐全
  E 头像资产   —— portrait 路径存在、webp 可解码、尺寸一致、缺失回退 unknown.svg
  F ES5 约束   —— tasks.js 无 let/const/箭头函数/模板字符串

不启动 Chrome、不访问网络：浏览器取证见 docs/r41-tasks-redesign-ledger.md 的截图。
"""
from __future__ import annotations

import json
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TASKS_JS = os.path.join(ROOT, "tasks.js")
TASKS_CSS = os.path.join(ROOT, "tasks.css")
TRADERS = os.path.join(ROOT, "data", "tasks", "traders.json")
PORTRAITS = os.path.join(ROOT, "assets", "icons-traders", "portraits")
UNKNOWN = os.path.join(ROOT, "assets", "icons-traders", "unknown.svg")

CJK = re.compile(r"[\u4e00-\u9fff]")

# 游戏内英文名（上游 tarkov.dev traders.name / 官方 Wiki 条目名）
EXPECTED_EN = {
    "54cb50c76803fa8b248b4571": "Prapor",
    "54cb57776803fa99248b456e": "Therapist",
    "579dc571d53a0658a154fbec": "Fence",
    "58330581ace78e27b8b10cee": "Skier",
    "5935c25fb3acc3127c3d8cd9": "Peacekeeper",
    "5a7c2eca46aef81a7ca2145d": "Mechanic",
    "5ac3b934156ae10c4430e83c": "Ragman",
    "5c0647fdd443bc2504c2d371": "Jaeger",
    "638f541a29ffd1183d187f57": "Lightkeeper",
    "68fe15910f29ba3fdbba9d54": "Taran",
    "68fe15990f29ba3fdbba9d55": "Radio Station",
    "656f0f98d80a697f855d34b1": "BTR Driver",
    "6617beeaa9cfa777ca915b7c": "Ref",
    "688246518448b05efd61d461": "Mr. Kerman",
    "688246958448b05efd61d462": "Voevoda",
    "69e0d6cc77b63940375b9173": "Survivor",
}


def _text(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


@pytest.fixture(scope="module")
def js():
    return _text(TASKS_JS)


@pytest.fixture(scope="module")
def css():
    return _text(TASKS_CSS)


@pytest.fixture(scope="module")
def traders():
    with open(TRADERS, encoding="utf-8") as fh:
        return json.load(fh)["traders"]


# ---------------------------------------------------------------- A 结构
def test_db4_board_structure(js):
    """列表页必须是 db4 的「搜索条 / 商人条 / 分组列表 / 右栏」四块结构。"""
    for token in (
        "db4-board", "db4-bar", "db4-search", "db4-strip",
        "db4-main", "db4-scroll", "db4-groups", "db4-rail",
        "db4-group", "db4-gutter", "db4-gname", "db4-rows",
    ):
        assert token in js, token
    assert 'host.classList.add("db4")' in js
    # R216 迁移：db4 皮肤只属于「任务列表」子页，由 setView() 按子页开关。
    # 旧写法给 .tk-shell 加一次就永不摘除，会把任务树 / 剧情等 XP 子页的页签皮肤压掉。
    assert 'shell.classList.add("db4")' not in js
    assert 'state.el.root.classList.toggle("db4", state.view === "list")' in js


def test_row_anatomy(js):
    """行内：状态勾选、名称、英文名、等级、地图、目标、exp、Complete。"""
    for token in (
        "db4-tick", "db4-name", "db4-en", "db4-lv", "db4-map",
        "db4-obj", "db4-obj-desc", "db4-obj-map", "db4-exp",
        "db4-exp-chip", "db4-exp-val", "db4-complete",
    ):
        assert token in js, token
    assert 'comp.textContent = st === "completed" ? "Completed" : "Complete";' in js


def test_rail_is_centered_buttons(js, css):
    """右栏是整宽居中按钮（无下拉框、无可见计数），选中态反白。"""
    assert "DB4_SORT" in js and "DB4_STATUS" in js
    assert 'b.dataset.db4Sort = o[0];' in js
    assert 'b.dataset.db4Status = o[0];' in js
    assert 'reset.dataset.db4Reset = "1";' in js
    # 计数只放 title，不再拼进按钮文字
    assert 'o[1] + "  " + n' not in js
    assert "db4-select" not in js
    assert "text-align: center" in css
    # R68：任务页由 db4 深色切换为全局 XP 主题，右栏选中态改为 Luna 橙色渐变 + 粗体
    rail_on = css[css.index(".db4-rail-btn.is-on {"):css.index(".db4-switch {")]
    assert "font-weight: 700" in rail_on


def test_complete_is_text_link(css):
    """参考站行尾的 Complete 是纯文字链接（无边框、无底色、无大写）。"""
    block = css[css.index(".db4-complete {"):css.index(".db4-complete:hover")]
    assert "border: 0" in block
    assert "background: none" in block
    assert "text-transform: uppercase" not in block


def test_default_view_is_list(js):
    """进入任务页默认落在列表（db4 的主界面），不再默认任务树。"""
    assert 'view: "list",' in js
    # 持久化恢复路径的兜底值也必须是 list
    assert '? cur.view : "list"' in js
    # 详情页失去选中任务时回落到列表，而不是旧的任务树
    assert 'if (state.view === "detail" && !state.selected) { state.view = "list"; }' in js


def test_db4_tokens(css):
    """R68：db4 深色令牌改为引用全局 XP 主题变量；深色基准值必须全部移除。"""
    assert ".db4 {" in css and ".tk-shell.db4" in css
    for token in (
        "--db4-bg: var(--xp-face",
        "--db4-text: var(--xp-text",
        "--db4-line: var(--xp-border-soft",
        "--db4-orange: var(--xp-btn-hover-border",
    ):
        assert token in css, token
    # 旧深色令牌（#121212 / #151515 / #262626 / #e6e6e6 / #f08a24）不得残留
    for legacy in ("#121212", "#151515", "#262626", "#e6e6e6", "#f08a24"):
        assert legacy not in css, legacy


# ---------------------------------------------------------------- B 能力保留
def test_search_uses_english_name_and_objectives(js):
    """搜 "Punisher" 能命中：搜索域必须含英文任务名、商人英文名、目标英文。"""
    assert "taskEnglishName(rec, id)" in js
    assert "(state.traders[rec.traderId] || {}).nameEn" in js
    assert "(o.descZh || \"\") + \" \" + (o.descEn || \"\")" in js


def test_map_locate_linkage(js):
    """点击目标旁的 ◎ 仍走 GWMapFocus：任务 → 地图聚焦不能被复刻丢掉。"""
    assert "locateByObjective" in js
    assert "data-db4-loc" in js
    assert "window.GWMapFocus" in js
    assert "GWMapFocus(" in js


def test_status_persistence_kept(js):
    """状态切换仍写回 eftmap.tasks.progress.v1（db4 没有的能力也不能删）。"""
    assert 'LS_PROGRESS = "eftmap.tasks.progress.v1"' in js
    assert "saveProgress()" in js


# ---------------------------------------------------------------- C ES5
def test_tasks_js_is_es5(js):
    """原生 ES5：无 let/const/箭头函数/模板字符串/class。"""
    assert not re.search(r"\blet\s", js)
    assert not re.search(r"\bconst\s", js)
    assert "=>" not in js
    assert "`" not in js
    assert not re.search(r"\bclass\s+\w+", js)
    assert not re.search(r"\.\.\.", js)


def test_no_third_party_or_cdn(js, css):
    """零依赖：不得引入 React/Tailwind/任何 CDN 脚本或 @import。"""
    for bad in ("react", "tailwind", "vue", "jquery", "<script", "@import"):
        assert bad.lower() not in js.lower(), bad
    assert "@import" not in css
    assert "cdn." not in css.lower()


# ---------------------------------------------------------------- D 商人英文名
def test_trader_english_names(traders):
    assert len(traders) == 16
    for tid, want in EXPECTED_EN.items():
        rec = traders[tid]
        assert rec["nameEn"] == want, (tid, rec["nameEn"], want)
        assert not CJK.search(rec["nameEn"]), rec["nameEn"]
    # 中文名只作为副标题 / tooltip，不得占据 nameEn
    for rec in traders.values():
        assert rec.get("nameZh"), rec["id"]
        assert rec.get("nameZhNote"), rec["id"]


def test_required_traders_present(traders):
    names = {rec["nameEn"] for rec in traders.values()}
    for want in ("Ragman", "Mechanic", "Jaeger", "Lightkeeper", "BTR Driver", "Ref"):
        assert want in names, want


# ---------------------------------------------------------------- E 头像资产
def test_portrait_paths_exist(traders):
    for rec in traders.values():
        rel = rec.get("portrait")
        assert rel, rec["id"]
        path = os.path.join(ROOT, rel.replace("/", os.sep))
        assert os.path.isfile(path), path
        assert os.path.getsize(path) > 500, path
        assert rel == "assets/icons-traders/portraits/%s.webp" % rec["id"]


def test_portraits_are_game_avatars(traders):
    """16 张头像都能解码，且尺寸一致（128×128 上下的正方形）。"""
    from PIL import Image

    for rec in traders.values():
        path = os.path.join(ROOT, rec["portrait"].replace("/", os.sep))
        with Image.open(path) as im:
            assert im.format == "WEBP", path
            assert im.mode in ("RGB", "RGBA"), (path, im.mode)
            assert abs(im.width - 128) <= 2 and abs(im.height - 128) <= 2, (path, im.size)


def test_portrait_fallback(js):
    """头像缺失时回退到项目内 SVG 图标，不出现破图 / 占位图。"""
    assert 'assets/icons-traders/unknown.svg' in js
    assert os.path.isfile(UNKNOWN)
    assert "this.onerror = null;" in js
    assert "tr.localIcon" in js


def test_strip_covers_all_traders(js):
    """头像条遍历全部商人，而不是写死若干 id。"""
    assert "Object.keys(state.traders).forEach" in js
    assert 'b.dataset.db4Trader = tid;' in js


def test_css_has_no_placeholder_grey(js):
    """禁止用占位图掩盖缺失：头像路径必须来自数据，不得写死占位 URL。"""
    for bad in ("placehold.co", "placehold.it", "via.placeholder", "dummyimage", "fakeimg"):
        assert bad not in js.lower(), bad
