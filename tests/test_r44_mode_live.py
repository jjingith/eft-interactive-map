# -*- coding: utf-8 -*-
"""R44 专项测试：显式模式选择器联动 + 在线行情 UI（默认关闭）。

覆盖任务书里的验收点：
  A 模式选择器 —— 顶栏可见、三模式、全局唯一状态（GWGameMode）+ 持久化
  B 联动       —— 切模式立即过滤任务点位、刷新价格视图、按模式读实时缓存
  C 来源诚实   —— PvE 未开实时时仍显示「快照（PvP，构建期）」，不得冒充 PvE
  D 关闭即静默 —— livePrices 关闭时不发任何 fetch、无定时器、立刻回快照
  E 覆盖规则   —— 实时只覆盖命中的 l/a，缺失 / 0 值逐条回退快照
  F 刷新提示   —— POST /refresh 的 403 / 409 / 404 / 网络失败都有可读文案
  G 版本预留   —— state.dataScope.edition + GWDataScope，但无枚举、无 UI 下拉
  H 单一定时器 —— 仅 scheduleLiveTimer 一个 setTimeout，页面隐藏暂停

不启动 Chrome、不访问网络：浏览器取证见 docs/r44-mode-live-ledger.md 的截图。
"""
from __future__ import annotations

import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_JS = os.path.join(ROOT, "app.js")
INDEX_HTML = os.path.join(ROOT, "index.html")
STYLE_CSS = os.path.join(ROOT, "style.css")
GAME_MODE_JS = os.path.join(ROOT, "js", "game-mode.js")


def _text(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _body(src, name):
    """按函数名截取 `function name(...) { ... }` 的函数体（大括号配对，跳过字符串里的括号不追求完美）。"""
    m = re.search(r"function\s+" + re.escape(name) + r"\s*\(", src)
    assert m, "缺少函数 " + name
    start = src.index("{", m.end())
    depth = 0
    i = start
    while i < len(src):
        ch = src[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return src[start : i + 1]
        i += 1
    raise AssertionError("函数 %s 的大括号不配对" % name)


def _r44_block(src):
    """R44 主块：从「R44：数据作用域」注释到「启动」注释之间的代码。"""
    a = src.index("R44：数据作用域")
    b = src.index("---------------------------------------------------------------- 启动", a)
    return src[a:b]


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


def _between(src, start_mark, end_mark):
    a = src.index(start_mark)
    b = src.index(end_mark, a)
    return src[a:b]


# ---------------------------------------------------------------- A 选择器


def test_mode_selector_is_visible_in_header():
    html = _text(INDEX_HTML)
    assert 'id="game-mode-bar"' in html
    # 模式条与价格来源徽标成组，窄屏时可整体换行，不挤坏地图/配装主流程
    assert 'class="scope-cluster"' in html
    assert 'id="price-source-badge"' in html
    assert 'role="status"' in html and 'aria-live="polite"' in html
    # 三模式由 game-mode.js 渲染，标签沿用既有控件风格（tk-modebar / tk-mode）
    gm = _text(GAME_MODE_JS)
    for key in ('"regular"', '"pve"', '"pvps"'):
        assert key in gm
    assert "tk-modebar" in gm and "tk-mode" in gm
    assert 'localStorage.setItem(LS_KEY, key)' in gm
    assert 'var LS_KEY = "eftmap.gameMode";' in gm


def test_mode_is_global_single_source_and_persistent():
    app = _text(APP_JS)
    init = _body(app, "initDataScope")
    assert "scopeMode()" in init
    assert "GWGameMode.onChange" in init
    assert "liveConsentLoad()" in init
    # 运行时永远以全局模式为准，不自己另存一份按键
    scope = _body(app, "scopeMode")
    assert "GWGameMode" in scope and "get()" in scope
    # 模式持久化由 game-mode.js 负责；app.js 只持久化「在线行情开关」这一项本地偏好
    assert 'LS_LIVE_CONSENT = "eftmap.livePrices.consent.v1"' in app
    assert "liveConsentSave" in app


# ---------------------------------------------------------------- B 联动


def test_apply_scope_drives_tasks_and_prices():
    app = _text(APP_JS)
    apply = _body(app, "applyDataScope")
    assert "prev !== mode" in apply
    assert "state.live.seq += 1" in apply        # 旧模式在途响应作废
    assert "state.livePrices = null" in apply     # 先回快照口径
    assert "stopLiveTimer()" in apply
    assert "applyTaskPointMode(mode)" in apply
    assert "fetchLivePrices" in apply
    assert "refreshPriceViews()" in apply
    assert "renderPriceSourceBadge()" in apply
    assert "renderLiveSettings()" in apply
    # 全局模式变化 → 统一数据作用域
    on_change = _body(app, "onGlobalModeChange")
    assert "applyDataScope({ mode: scopeMode() })" in on_change


def test_task_points_filter_uses_mode_file():
    app = _text(APP_JS)
    attach = _body(app, "attachTaskPoints")
    assert "map.tasksAll" in attach
    assert "map.tasks = map.tasksAll.slice()" in attach
    assert "applyTaskPointMode(state.dataScope.mode)" in attach
    assert "ensureTaskIdSet(state.dataScope.mode)" in attach

    apply = _body(app, "applyTaskPointMode")
    assert "state.taskIdsByMode[mode]" in apply
    assert "all.filter" in apply
    assert "flattenTaskPoints(kept" in apply
    assert "renderTaskPanel()" in apply

    ensure = _body(app, "ensureTaskIdSet")
    assert '"data/tasks/tasks." + mode + ".json"' in ensure
    assert "Object.keys(tasks)" in ensure
    # 异步返回后，只有仍是当前模式才重过滤（避免旧模式回填）
    assert "state.dataScope.mode === target" in ensure


def test_price_surfaces_read_single_source_of_truth():
    app = _text(APP_JS)
    # 配装 / 物品价：itemPrice 走 priceFieldsFor（含实时覆盖）
    assert "priceFieldsFor(rec)" in _body(app, "itemPrice")
    # 弹药：走跳蚤行情覆盖
    assert "overlayQuoteFields" in _body(app, "amPriceOf")
    # 配枪行情行：同样覆盖
    assert "overlayQuoteFields" in _body(app, "fleaQuoteOf")
    # 状态行与提示全部读 priceSourceInfo
    assert "priceSourceInfo()" in _body(app, "renderQuoteStatus")
    # 来源文案覆盖配装与弹药两处
    assert app.count("priceModeNote(") >= 5
    # R266：弹药页的来源提示已移除（统一由二级工具条的市场截止徽标表达）
    assert "el.amHint.title = srcInfo.detail;" not in app
    assert "价格来源：" not in app


# ---------------------------------------------------------------- C 来源诚实


def test_pve_never_relabels_pvp_snapshot():
    app = _text(APP_JS)
    info = _body(app, "priceSourceInfo")
    # 快照模式取自 flea-prices.json 的 gameMode，而不是当前所选模式
    assert "state.fleaPrices && state.fleaPrices.gameMode" in info
    assert '"快照（" + modeShort(snapMode) + "，构建期）"' in info
    assert 'mode === "pve" && snapMode !== "pve"' in info
    assert "这不是 PvE 价格" in info
    # PvPS 明说没有实时接口、不得联网
    assert 'mode === "pvps"' in info
    assert "没有实时行情接口" in info
    assert "不会为它发起任何联网请求" in info


def test_badge_exposes_kind_for_styling_and_screenreaders():
    app = _text(APP_JS)
    badge = _body(app, "renderPriceSourceBadge")
    assert "info.short" in badge
    assert "info.detail" in badge
    assert '"price-source-badge is-" + info.kind' in badge
    assert "data-kind" in badge
    assert "aria-label" in badge
    css = _text(STYLE_CSS)
    for cls in (".price-source-badge", ".is-live", ".is-fallback", ".is-pending"):
        assert cls in css


# ---------------------------------------------------------------- D 关闭即静默


def test_live_disabled_sends_no_request():
    app = _text(APP_JS)
    can = _body(app, "canLive")
    assert "!!state.live.consent" in can
    assert '"regular"' in can and '"pve"' in can
    assert '"pvps"' not in can

    fetch_live = _body(app, "fetchLivePrices")
    guard = fetch_live.index("if (!canLive())")
    real_fetch = fetch_live.index("fetch(liveEndpoint()")
    assert guard < real_fetch, "关闭时必须先 return，绝不能走到 fetch"
    assert "Promise.resolve(null)" in fetch_live[guard:]
    # 请求本身也带 no-store，避免浏览器缓存冒充实时
    assert 'cache: "no-store"' in fetch_live

    bind = _body(app, "bindLivePricesUI")
    off = bind.index("if (!on)")
    enable = bind.index('fetchLivePrices({ reason: "enable" })')
    assert off < enable
    off_body = bind[off:enable]
    assert "state.live.seq += 1" in off_body
    assert "state.livePrices = null" in off_body
    assert "stopLiveTimer()" in bind[:off]
    assert "return;" in off_body
    assert "fetch(" not in off_body


def test_refresh_button_only_visible_when_enabled():
    app = _text(APP_JS)
    settings = _body(app, "renderLiveSettings")
    assert "el.liveRefresh.hidden = !state.live.consent" in settings
    html = _text(INDEX_HTML)
    assert 'id="live-refresh" hidden' in html
    assert 'id="live-enabled"' in html
    assert "默认<strong>关闭</strong>" in html
    assert "约 10 分钟一次" in html
    assert "失败自动回退本地快照" in html


# ---------------------------------------------------------------- E 覆盖规则


def test_live_overlay_only_replaces_hits_and_falls_back_per_field():
    app = _text(APP_JS)
    pick = _body(app, "pickPriceNum")
    assert 'typeof v === "number" && isFinite(v) && v > 0' in pick

    price = _body(app, "overlayPriceFields")
    assert "out = { a: p.a, l: p.l" in price      # 先抄快照
    assert "if (la !== null) { out.a = la; }" in price
    assert "if (ll !== null) { out.l = ll; }" in price

    quote = _body(app, "overlayQuoteFields")
    assert "out.avg24hPrice = la" in quote
    assert "out.lastLowPrice = ll" in quote
    assert "if (la !== null)" in quote and "if (ll !== null)" in quote

    live_for = _body(app, "livePriceFor")
    assert "L.available" in live_for and "L.prices" in live_for
    assert "L.mode !== state.dataScope.mode" in live_for
    assert 'state.dataScope.mode === "pvps"' in live_for

    count = _body(app, "countPrices")
    assert 'pickPriceNum(v, "l") !== null' in count
    assert 'pickPriceNum(v, "a") !== null' in count


def test_no_live_mode_has_no_endpoint_at_all():
    app = _text(APP_JS)
    endpoint = _body(app, "liveEndpoint")
    assert '"api/live-prices?mode="' in endpoint
    assert '"pve" ? "pve" : "regular"' in endpoint
    assert "pvps" not in endpoint
    # PvPS 开启开关时：不发请求，只给提示
    bind = _body(app, "bindLivePricesUI")
    pvps = bind.index('state.dataScope.mode === "pvps"')
    enable = bind.index('fetchLivePrices({ reason: "enable" })')
    assert pvps < enable
    assert "PvPS 没有实时行情接口" in bind[pvps:enable]


# ---------------------------------------------------------------- F 刷新提示


def test_refresh_failure_is_readable_not_silent():
    app = _text(APP_JS)
    refresh = _body(app, "refreshLiveNow")
    assert '"api/live-prices/refresh"' in refresh
    for code in ("202", "200", "403", "409", "404"):
        assert code in refresh
    assert "刷新被拒绝：请从本机同源页面调用" in refresh
    assert "刷新被拒绝（HTTP 409）" in refresh
    assert "刷新接口不存在（HTTP 404）" in refresh
    # 浏览器模式用客户端标识头，不能带 X-EFTMap-Token
    assert '"X-EFTMap-Client": "web"' in refresh
    assert '"X-EFTMap-Token"' not in refresh
    assert "刷新失败" in refresh
    assert "state.live.lastError" in refresh
    assert "renderLiveSettings()" in refresh
    # 失败后仍然再拉一次 GET，回到可解释状态
    assert refresh.count("fetchLivePrices({ reason: \"manual\" })") >= 2
    # 随后的 GET 若只是 enabled=false 会清空 lastError，被拒原因必须补回，不能被吞掉
    assert "var refusal = null;" in refresh
    assert "if (refusal) {" in refresh
    # 点击期间按钮禁用 + 文案变化，结束后复位
    assert 'el.liveRefresh.textContent = "刷新中…"' in refresh
    assert 'el.liveRefresh.textContent = "刷新行情"' in refresh


# ---------------------------------------------------------------- G 版本预留


def test_edition_extension_point_is_wired_but_stays_out_of_data_paths():
    """R45 起 edition 接上 editions.json 与对照卡；但仍不得触发任务 / 价格重载。"""
    app = _text(APP_JS)
    assert "var DATA_EDITIONS = [];" in app
    assert 'loadJSON("data/editions.json")' in app
    assert "DATA_EDITIONS = doc.editions" in app
    apply = _body(app, "applyDataScope")
    assert 'hasOwnProperty.call(next, "edition")' in apply
    assert "state.dataScope.edition = next.edition" in apply
    # edition 分支只重绘卡片，且位于模式分支之前（不进入 applyTaskPointMode / fetchLivePrices）
    edition_at = apply.index("if (prevEdition !== state.dataScope.edition)")
    mode_at = apply.index("if (prev !== mode)")
    assert edition_at < mode_at
    branch = apply[edition_at:mode_at]
    assert "renderAccountPanel()" in branch
    for forbidden in ("applyTaskPointMode", "fetchLivePrices", "refreshPriceViews", "applyDataScope"):
        assert forbidden not in branch
    scope = _between(app, "window.GWDataScope = {", "// ---------------------------------------------------------------- 启动")
    assert "mode: state.dataScope.mode, edition: state.dataScope.edition" in scope
    assert "editions: DATA_EDITIONS.slice()" in scope
    state_init = _between(app, "dataScope:", "live:")
    assert "edition: null" in state_init
    # 不把版本差异写死在 JS 里：只在 data/editions.json 出现
    assert "白边" not in app and "黑边" not in app and "蓝边" not in app


# ---------------------------------------------------------------- H 单一定时器


def test_single_live_timer_only_when_enabled_and_visible():
    app = _text(APP_JS)
    block = _r44_block(app)
    assert "setInterval" not in block
    assert block.count("state.live.timer = setTimeout") == 1
    sched = _body(app, "scheduleLiveTimer")
    assert "if (!canLive() || (document.hidden === true))" in sched
    assert "ttl * 1000" in sched
    assert "ttl < 60" in sched
    stop = _body(app, "stopLiveTimer")
    assert "clearTimeout(state.live.timer)" in stop
    bind = _body(app, "bindLivePricesUI")
    assert '"visibilitychange"' in bind
    assert "if (document.hidden === true) { stopLiveTimer(); return; }" in bind
    assert "scheduleLiveTimer();" in bind


def test_narrow_screen_layout_keeps_scope_cluster_wrappable():
    css = _text(STYLE_CSS)
    assert re.search(r"\.menubar\s*\{[^}]*flex-wrap:\s*wrap", css), "顶栏必须允许换行"
    assert ".scope-cluster" in css
    assert re.search(r"@media[^{]*max-width:\s*1180px", css)
    assert re.search(r"@media[^{]*max-width:\s*860px", css)
    # 取「包含 .scope-cluster 的 860px 块」：R45 新增的 860px 块不能被误判
    sc_at = css.index(".scope-cluster { width: 100%")
    block = _media_block(css, css[sc_at:sc_at + 40])
    assert "max-width: 860px" in block
    assert "width: 100%" in block
    assert "flex-wrap: wrap" in block
    assert re.search(r"\.price-source-badge\s*\{[^}]*max-width:\s*160px", block)
