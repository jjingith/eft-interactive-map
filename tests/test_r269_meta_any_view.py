"""R269：二级工具条上的「获取最新数据 / 数据截止」必须与视图无关。

用户反馈（2026-11-13 09:50）：
  · 徽标一直停在「11-12 23:31（十小时前）」；
  · 在配装 / 配枪 / 子弹页点「获取最新数据」没反应，只有在市场页点才会更新。

根因：徽标与按钮的状态全部写在 market.js 的 `updateCutoff()` 里，而它只在市场表格
渲染路径（applyFilters）被调用；又不巧 `onPricesUpdated()` 在 `!loaded || loading`
时直接 return，所以别的页上即使行情已经拉到，徽标也不会重画。

修法：
  · market.js 暴露 `refreshMeta()`（= 只刷新徽标 / 按钮状态），`pricesUpdated` 先刷徽标；
  · app.js 在行情到达、切换视图、以及 30 秒定时器里都调用 `refreshMeta()`；
  · 数据落后一个采集周期时静默补拉，避免徽标长期停在很久以前。
"""

import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MARKET_JS = os.path.join(ROOT, "js", "market.js")
APP_JS = os.path.join(ROOT, "app.js")


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _block(src, start_marker, end_marker, size=2600):
    i = src.index(start_marker)
    j = src.find(end_marker, i)
    return src[i: j if j > 0 else i + size]


def test_refresh_meta_is_exposed():
    js = _read(MARKET_JS)
    assert "function refreshMeta()" in js
    assert "refreshMeta: refreshMeta" in js, "市场模块要把 refreshMeta 暴露给 app.js"


def test_prices_updated_refreshes_meta_before_early_return():
    js = _read(MARKET_JS)
    block = _block(js, "function onPricesUpdated()", "function refreshMeta()")
    hit_meta = block.index("refreshMeta();")
    early = block.index("if (!root || !api || !loaded || loading)")
    assert hit_meta < early, "必须先把徽标刷新掉，再做「市场列表是否就绪」的早退判断"


def test_manual_fetch_always_resets_and_refreshes():
    js = _read(MARKET_JS)
    block = _block(js, "function manualFetch()", "function showFetchWarn")
    assert "setFetchBusy(false)" in block and "refreshMeta()" in block
    # 成功 / 节流 / 失败三条路径都要走 done()（复位按钮 + 刷徽标）
    assert block.count("done();") >= 2
    assert ".catch(function () {\n      done();" in block
    # 接口没就绪时给提示，不再静默 return（静默 return 就是「没反应」）
    assert "行情接口还没就绪" in block


def test_app_refreshes_meta_on_snapshot_and_view_switch():
    js = _read(APP_JS)
    # 行情到达（notify）里要有 refreshMeta 兜底
    block = _block(js, "var notify = function () {", "return fetch(priceSnapshotEndpoint")
    assert "refreshMeta" in block, "行情落袋后要刷新二级工具条的徽标"
    # setView 结束前要刷一次
    view_block = _block(js, "function setView(name, persist)", "function ensureItems")
    assert "refreshMeta" in view_block, "切换视图时徽标要跟着最新 payload 走"


def test_auto_sync_piggybacks_on_meta_tick():
    app = _read(APP_JS)
    market = _read(MARKET_JS)
    # app.js 不新增定时器（R44 约定：整页只留实时行情那条 setTimeout 链）
    assert "function maybeSyncPrices()" in app
    assert "setInterval(" not in app, "app.js 不新增定时器（R44 约定：只留实时行情那条链）"
    assert "maybeSyncPrices: maybeSyncPrices" in app, "要把按需补拉暴露给市场模块"
    block = _block(app, "function maybeSyncPrices()", "function initDataScope()")
    assert "32 * 60 * 1000" in block, "落后一个采集周期（30 分钟）才补拉"
    assert "5 * 60 * 1000" in block, "同一份旧数据最多每 5 分钟重试一次"
    # 心跳放在徽标自己身上：30 秒重画一次「N 分钟前」，页面不可见时跳过
    assert "function startMetaTick()" in market
    assert "30000" in market
    tick = _block(market, "function startMetaTick()", "function mount()")
    assert "document.hidden" in tick and "maybeSyncPrices" in tick
    assert "startMetaTick();" in market.split("function mount()", 1)[1]
