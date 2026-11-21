# -*- coding: utf-8 -*-
"""R45 专项测试：账号版本对照卡（data/editions.json + 面板 + edition 作用域）。

锁定：
  A 数据完整性 —— 5 个版本的字段齐全、数值与 docs/r43-account-editions.md 一致
  B 状态诚实   —— EOD 明确停售且无价格；价格标「结算显示价」口径
  C 渠道维度   —— TUE 区分官网版（含 Season Pass）与 Steam 版（不含）
  D 面板渲染   —— 每版本一张卡，字段/状态/价格口径/Nostalgia 入口都出现
  E 不重载     —— edition 切换只重绘卡片，不触发任务、任务点位、价格、实时行情
  F Nostalgia  —— 入口切到任务视图并调用 GWTasks.openTask，且 taskId 在三种模式数据里存在
"""
from __future__ import annotations

import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_JS = os.path.join(ROOT, "app.js")
INDEX_HTML = os.path.join(ROOT, "index.html")
STYLE_CSS = os.path.join(ROOT, "style.css")
EDITIONS = os.path.join(ROOT, "data", "editions.json")
TASKS_DIR = os.path.join(ROOT, "data", "tasks")

REQUIRED_TOP = ["schema", "source", "sources", "fetchedAt", "region", "priceBasis", "editions"]
REQUIRED_ED = [
    "id", "nameEn", "nameZh", "aliases", "status", "channel", "stashCells",
    "secureContainer", "expBonusPct", "traderStanding", "pveIncluded",
    "seasonPass", "arenaRyzhy", "extraPerks", "price", "taskOverrides",
]
ALLOWED_STATUS = {"available", "legacy-discontinued"}


def _text(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _body(src, name):
    m = re.search(r"function\s+" + re.escape(name) + r"\s*\(", src)
    assert m, "缺少函数 " + name
    start = src.index("{", m.end())
    depth = 0
    i = start
    while i < len(src):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                return src[start : i + 1]
        i += 1
    raise AssertionError("函数 %s 的大括号不配对" % name)


def _media_block(css, marker):
    """取某个选择器所在的完整 @media 块（大括号配对，避免正则截断）。"""
    at = css.index(marker)
    start = css.rindex("@media", 0, at)
    brace = css.index("{", start)
    depth = 0
    i = brace
    while i < len(css):
        if css[i] == "{":
            depth += 1
        elif css[i] == "}":
            depth -= 1
            if depth == 0:
                return css[start : i + 1]
        i += 1
    raise AssertionError("media block 不配对")


def _editions():
    doc = _json(EDITIONS)
    return doc, {e["id"]: e for e in doc["editions"]}


# ---------------------------------------------------------------- A 数据完整性


def test_schema_and_required_fields():
    doc, by_id = _editions()
    for key in REQUIRED_TOP:
        assert key in doc, "缺少顶层字段 " + key
    assert doc["schema"] == 1
    assert "r43-account-editions.md" in doc["source"]
    assert re.match(r"2026-11-04T\d{2}:\d{2}:\d{2}\+08:00$", doc["fetchedAt"])
    assert set(by_id) == {
        "standard", "left-behind", "prepare-for-escape", "unheard", "edge-of-darkness"
    }
    for ed in doc["editions"]:
        for key in REQUIRED_ED:
            assert key in ed, "%s 缺少 %s" % (ed.get("id"), key)
        assert ed["status"] in ALLOWED_STATUS
        assert isinstance(ed["aliases"], list) and ed["aliases"]
        assert isinstance(ed["stashCells"], list) and len(ed["stashCells"]) == 2
        assert all(isinstance(v, int) and v > 0 for v in ed["stashCells"])
        sc = ed["secureContainer"]
        assert set(sc) >= {"name", "w", "h"}
        assert isinstance(sc["w"], int) and isinstance(sc["h"], int)
        assert isinstance(ed["expBonusPct"], (int, float)) and ed["expBonusPct"] >= 0
        ts = ed["traderStanding"]
        assert isinstance(ts["allTraders"], (int, float))
        assert isinstance(ts["fenceBonus"], (int, float))
        assert isinstance(ed["pveIncluded"], bool)
        assert isinstance(ed["seasonPass"], bool)
        assert isinstance(ed["arenaRyzhy"], bool)
        assert isinstance(ed["extraPerks"], list)
        assert isinstance(ed["taskOverrides"], list)
        p = ed["price"]
        assert set(p) >= {"currency", "amount", "basis", "checkedAt"}
        assert p["basis"] in doc["priceBasis"]
        assert p["amount"] is None or (isinstance(p["amount"], int) and p["amount"] > 0)


def test_values_match_research_doc():
    doc, by_id = _editions()
    expect = {
        "standard": ([10, 30], "Alpha", 2, 2, 0, 0, 0),
        "left-behind": ([10, 40], "Alpha", 2, 2, 7, 0, 0),
        "prepare-for-escape": ([10, 50], "Beta", 3, 2, 9, 0.2, 0),
        "unheard": ([10, 72], "Gamma TUE", 3, 3, 20, 0.2, 0.5),
        "edge-of-darkness": ([10, 68], "Gamma EOD", 3, 3, 12, 0.2, 0),
    }
    for eid, (cells, cname, w, h, exp, standing, fence) in expect.items():
        ed = by_id[eid]
        assert ed["stashCells"] == cells
        assert ed["secureContainer"]["name"] == cname
        assert ed["secureContainer"]["w"] == w and ed["secureContainer"]["h"] == h
        assert ed["expBonusPct"] == exp
        assert ed["traderStanding"]["allTraders"] == standing
        assert ed["traderStanding"]["fenceBonus"] == fence
    # 在售 4 个 / 停售 1 个
    assert by_id["edge-of-darkness"]["status"] == "legacy-discontinued"
    for eid in ("standard", "left-behind", "prepare-for-escape", "unheard"):
        assert by_id[eid]["status"] == "available"


def test_price_basis_is_checkout_display_not_list_price():
    doc, by_id = _editions()
    amounts = {"standard": 3100, "left-behind": 1100, "prepare-for-escape": 2200, "unheard": 9200}
    for eid, amount in amounts.items():
        p = by_id[eid]["price"]
        assert p["amount"] == amount
        assert p["basis"] == "checkout-display"
        assert p["currency"] == "RUB"
    eod = by_id["edge-of-darkness"]["price"]
    assert eod["amount"] is None and eod["basis"] == "not-for-sale"
    assert "升级" in doc["priceBasis"]["checkout-display"]
    assert "不是绝对售价" in doc["priceBasis"]["checkout-display"]


def test_tue_channel_dimension_steam_has_no_season_pass():
    _, by_id = _editions()
    tue = by_id["unheard"]
    assert tue["seasonPass"] is True          # 官网口径
    variants = {v["channel"]: v for v in tue["channelVariants"]}
    assert set(variants) == {"official-site", "steam"}
    assert variants["official-site"]["seasonPass"] is True
    assert variants["steam"]["seasonPass"] is False
    assert "Steam" in variants["steam"]["note"] and "Season Pass" in variants["steam"]["note"]
    # 其他版本不编造渠道差异
    for eid in ("standard", "left-behind", "prepare-for-escape", "edge-of-darkness"):
        assert "channelVariants" not in by_id[eid]


def test_eod_is_only_edition_with_nostalgia_override():
    _, by_id = _editions()
    for eid, ed in by_id.items():
        if eid == "edge-of-darkness":
            assert len(ed["taskOverrides"]) == 1
            ov = ed["taskOverrides"][0]
            assert ov["taskId"] == "5d25e4ad86f77443e625e387"
            assert ov["nameZh"] == "怀旧之情"
            assert "Nostalgia" in ov["reason"]
        else:
            assert ed["taskOverrides"] == []


def test_nostalgia_task_id_exists_in_every_mode():
    for mode in ("regular", "pve", "pvps"):
        tasks = _json(os.path.join(TASKS_DIR, "tasks.%s.json" % mode))["tasks"]
        assert "5d25e4ad86f77443e625e387" in tasks, mode
        assert tasks["5d25e4ad86f77443e625e387"].get("nameZh") == "怀旧之情"


# ---------------------------------------------------------------- D 面板渲染


def test_panel_markup_and_copy():
    html = _text(INDEX_HTML)
    assert 'id="menu-account"' in html
    assert 'id="account-block"' in html
    assert 'id="account-cards"' in html
    assert 'id="account-clear"' in html
    assert 'id="account-task-status"' in html
    assert "任务与价格不随版本变化" in html
    assert "Nostalgia 怀旧任务链" in html
    assert "不是版本售价" in html
    assert "KB 529 / 534–538" in html
    assert 'class="menu-panel account-panel"' in html


def test_cards_render_every_field_and_status():
    app = _text(APP_JS)
    card = _body(app, "editionCardHTML")
    for label in ("仓库", "安全容器", "商人声望", "经验加成"):
        assert label in card
    assert "acc-status" in card
    assert "editionStatusLabel(ed.status)" in card
    assert "is-legacy" in card
    assert "editionPriceText(ed)" in card
    assert "editionPriceBasis(ed)" in card
    assert "channelVariants" in card
    assert "taskOverrides" in card
    assert "data-edition-task" in card
    render = _body(app, "renderAccountPanel")
    assert "state.editions.editions" in render
    assert "editionCardHTML(item)" in render
    assert "版本数据读取失败" in render
    status = _body(app, "editionStatusLabel")
    assert "available: \"在售\"" in status or 'available: "在售"' in app
    assert '"legacy-discontinued": "停售"' in app
    price = _body(app, "editionPriceText")
    assert "已停售（无价格）" in price


def test_account_entry_is_wired_into_menu_and_boot():
    app = _text(APP_JS)
    assert 'el.menuAccount = $("menu-account")' in app
    assert "bindAccountUI();" in app
    assert "loadEditions();" in app
    assert "{ btn: el.menuAccount, panel: el.accountBlock }" in app
    bind = _body(app, "bindAccountUI")
    assert "applyEdition" in bind
    assert "jumpToEditionTask" in bind
    assert "keydown" in bind
    assert 'LS_ACCOUNT_EDITION = "eftmap.accountEdition"' in app


# ---------------------------------------------------------------- E 不重载


def test_edition_switch_does_not_reload_tasks_or_prices():
    app = _text(APP_JS)
    apply_ed = _body(app, "applyEdition")
    assert "applyDataScope({ edition: next })" in apply_ed
    assert "applyTaskPointMode" not in apply_ed
    assert "refreshPriceViews" not in apply_ed
    assert "fetchLivePrices" not in apply_ed
    assert "fetch(" not in apply_ed
    assert "renderAccountPanel()" in apply_ed

    render = _body(app, "renderAccountPanel")
    for forbidden in ("applyTaskPointMode", "refreshPriceViews", "fetchLivePrices", "refreshGunTable", "renderAmmo"):
        assert forbidden not in render

    load = _body(app, "loadEditions")
    for forbidden in ("applyTaskPointMode", "fetchLivePrices", "refreshPriceViews", "refreshGunTable"):
        assert forbidden not in load
    # applyDataScope：edition 分支在 mode 分支之前，且只调用 renderAccountPanel
    scope = _body(app, "applyDataScope")
    a = scope.index("if (prevEdition !== state.dataScope.edition)")
    b = scope.index("if (prev !== mode)")
    assert a < b
    assert "renderAccountPanel()" in scope[a:b]


def test_edition_selection_persists_and_validates():
    app = _text(APP_JS)
    save = _body(app, "editionChoiceSave")
    assert "localStorage.setItem(LS_ACCOUNT_EDITION, id)" in save
    assert "localStorage.removeItem(LS_ACCOUNT_EDITION)" in save
    load = _body(app, "loadEditions")
    assert "editionChoiceLoad()" in load
    assert "!editionById(saved)" in load
    assert "state.dataScope.edition = saved" in load
    apply_ed = _body(app, "applyEdition")
    assert "if (next && !editionById(next)) { return; }" in apply_ed


# ---------------------------------------------------------------- F Nostalgia


def test_nostalgia_link_opens_task_view_and_task():
    app = _text(APP_JS)
    jump = _body(app, "jumpToEditionTask")
    assert 'setView("tasks")' in jump
    assert "GWTasks.openTask(taskId)" in jump
    assert "GWTasks.mount()" in jump and "GWTasks.open()" in jump
    assert "setTimeout(attempt, 500)" in jump          # 数据未就绪时重试，不是死控件
    assert "本地任务数据里没有找到" in jump
    # 只有 editions.json 里带 taskOverrides 的版本才渲染入口
    card = _body(app, "editionCardHTML")
    assert "ed.taskOverrides || []" in card


def test_account_css_keeps_xp_theme_and_narrow_layout():
    css = _text(STYLE_CSS)
    assert ".account-panel" in css and "width: 500px" in css
    assert ".acc-card.is-current" in css
    assert ".acc-status.is-legacy-discontinued" in css
    narrow = _media_block(css, ".account-panel {\n    position: fixed;")
    assert "max-width: 860px" in narrow
    assert "grid-template-columns: 1fr" in narrow
    # 窄屏把面板钉到视口：挂在账号按钮上的绝对定位会把面板推到屏幕外
    assert "left: 8px" in narrow and "right: 8px" in narrow
