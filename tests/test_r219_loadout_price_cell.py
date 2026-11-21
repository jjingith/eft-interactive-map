# -*- coding: utf-8 -*-
"""R219：配装表价格回到「获取方式」格内，并同时受**模式**与**价格档**两个开关驱动。

用户原话（2026-11-09）：
  「配装栏的右侧装备列表 获取方式不知为何被上一个agent改变了原有样式 还增加了几个价格栏
    我的设想是原本的价格栏那里 跳蚤市场的价格随这点击 pve pvp pvps 切换而改变
    然后还有点击价格是 last 还是均价 而改变」

本文件守住四件事：
  1. 表尾不再有独立价格列（R74 的 p24 / p7d 已撤），价格只在获取方式格内出现一次；
  2. 跳蚤那一枚的价格 = `fleaPriceInfo`：优先当前模式行情快照，缺档才回退构建期快照并标注；
  3. 配装页的价格档 pills 不再隐藏（否则用户点不到 last / 均价）；
  4. 服务端把云端缺的 24h 均价补齐（history?basis=24h → 同模式内置快照），不跨模式、不覆盖已有值。
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import prices_source  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "app.js"
INDEX = ROOT / "index.html"
STYLE = ROOT / "style.css"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


# ---------------------------------------------------------------- 静态契约（列集 / 接线）

def test_no_standalone_price_columns_in_gear_table():
    """配装表列集里不能再有 p24 / p7d 两列；价格只在获取方式格内出现一次。"""
    js = _text(APP)
    assert "var p24Col" not in js, "R74 的 p24 列应已撤掉"
    assert "var p7dCol" not in js, "R74 的 p7d 列应已撤掉"
    assert "p24Col" not in js and "p7dCol" not in js
    assert 'key: "p24"' not in js and 'key: "p7d"' not in js
    # 每个列集都以 srcCol 结尾（价格在它格内）
    sets = re.findall(r"cols = \[[^\]]*srcCol[^\]]*\];", js)
    assert sets, "找不到列集定义"
    for line in sets:
        assert "p24" not in line and "p7d" not in line, "列集里仍有独立价格列：%s" % line


def test_source_cell_renders_price_and_recipe_inline():
    """获取方式格恢复合并样式：图标 + 价格 + 配方摘要 + 商人等级，浮窗保留完整文案。"""
    js = _text(APP)
    assert "function renderSrcCell(cell, row) {" in js
    body = js[js.index("function renderSrcCell(cell, row) {"):]
    body = body[: body.index("\n  /** R22.2 价格来源小图标")] if "\n  /** R22.2 价格来源小图标" in body else body[:4000]
    assert 'className = "lw-src-price"' in body, "价格必须写回格内"
    assert 'className = "lw-src-req"' in body, "兑换配方摘要必须写回格内"
    assert 'className = "lw-src-lv"' in body, "商人等级仍在同一枚里"
    assert "row.fleaInfo" in body, "跳蚤价格必须读行上的口径信息（模式 × 价格档）"
    assert "fleaPriceTitle(row)" in body, "跳蚤价格的浮窗要写清模式 / 档位 / 来源"
    # 不再有「剥掉价格行」的旧辅助函数
    assert "srcTipNoPrice" not in js


def test_price_pills_moved_to_global_toolbar():
    """R265：价格档切换从配装页上移到二级工具条 #vt-prices，且不再 hidden。"""
    html = _text(INDEX)
    assert 'id="lw-prices"' not in html, "配装页不应再有独立的价格档容器（已上移）"
    m = re.search(r'<div[^>]*id="vt-prices"[^>]*>', html)
    assert m, "找不到全局价格口径容器 #vt-prices"
    assert "hidden" not in m.group(0), "#vt-prices 被 hidden，用户点不到 last / 均价"


def test_price_and_mode_switches_refresh_the_table():
    """两个开关都必须让表重算：切价格档 → refreshGearTable；切模式 / 行情回包 → 也刷新。"""
    js = _text(APP)
    # 切价格档
    i = js.index("function setPriceMode(key) {")
    block = js[i: js.index("\n  }", i)]
    assert "refreshGearTable()" in block
    # 切模式：refreshPriceViews 里对 loadout 调 refreshGearTable
    i = js.index("function refreshPriceViews() {")
    block = js[i: i + 900]
    assert 'state.view === "loadout"' in block and "refreshGearTable()" in block
    # 行情回包（云端 / 内置异步到达）也要刷新，否则停在构建期兜底值
    # R267：notify 改为统一调 refreshPriceViews()（覆盖配装/配枪/子弹，含 refreshGearTable）
    i = js.index("var notify = function () {")
    block = js[i: i + 700]
    assert "refreshPriceViews()" in block


# ---------------------------------------------------------------- 价格口径（Node 抽函数）

PRICE_JS = r"""
"use strict";
var fs = require("fs");
var src = fs.readFileSync(process.argv[2], "utf8");

function extractFn(source, name) {
  var i = source.indexOf("function " + name + "(");
  if (i < 0) { throw new Error("找不到函数 " + name); }
  var start = source.indexOf("{", i);
  var depth = 0;
  for (var k = start; k < source.length; k++) {
    var c = source[k];
    if (c === '"' || c === "'" || c === "`") {
      var q = c; k++;
      while (k < source.length && source[k] !== q) { if (source[k] === "\\") { k++; } k++; }
      continue;
    }
    if (c === "/" && source[k + 1] === "/") { while (k < source.length && source[k] !== "\n") { k++; } continue; }
    if (c === "/" && source[k + 1] === "*") { k = source.indexOf("*/", k + 2); continue; }
    if (c === "{") { depth++; }
    else if (c === "}") { depth--; if (depth === 0) { return source.slice(i, k + 1); } }
  }
  throw new Error("花括号不平衡：" + name);
}
function extractVar(source, name) {
  var i = source.indexOf("var " + name + " =");
  if (i < 0) { throw new Error("找不到 var " + name); }
  var depth = 0;
  for (var k = source.indexOf("=", i) + 1; k < source.length; k++) {
    var c = source[k];
    if (c === '"' || c === "'" || c === "`") {
      var q = c; k++;
      while (k < source.length && source[k] !== q) { if (source[k] === "\\") { k++; } k++; }
      continue;
    }
    if (c === "/" && source[k + 1] === "/") { while (k < source.length && source[k] !== "\n") { k++; } continue; }
    if (c === "/" && source[k + 1] === "*") { k = source.indexOf("*/", k + 2); continue; }
    if (c === "[" || c === "{" || c === "(") { depth++; }
    else if (c === "]" || c === "}" || c === ")") { depth--; }
    else if (c === ";" && depth === 0) { return source.slice(i, k + 1); }
  }
  throw new Error("找不到 " + name + " 的结尾分号");
}

var chk = [];
function check(name, ok) { chk.push((ok ? "PASS " : "FAIL ") + name); if (!ok) { process.exitCode = 1; } }

var state = { priceMode: "last", dataScope: { mode: "regular" }, items: {} };
/* 真实实现读 state.priceSnap.payload（服务端 /api/price-snapshot）；这里用可替换的桩，
   单测只验证「优先顺序 / 回退标注」，不动服务端契约。 */
/* new Function 的函数体只能看到全局作用域（CommonJS 顶层 var 不是全局），
   所以桩用 globalThis 存，避免「写入模块变量、读取全局变量」的假通过。 */
globalThis.QUOTE = null;
function priceQuoteOf(id) {
  var table = globalThis.QUOTE;
  if (table === null) { return undefined; }
  return Object.prototype.hasOwnProperty.call(table, id) ? table[id] : null;
}

var FN = [
  extractVar(src, "PRICE_MODES"),
  extractVar(src, "MODE_SHORT"),
  extractFn(src, "priceModeOf"),
  extractFn(src, "modeShort"),
  extractFn(src, "fmtMoney"),
  extractFn(src, "fmtMoneyPlain"),
  extractFn(src, "itemPrice"),
  extractFn(src, "fleaPriceInfo"),
  extractFn(src, "modeFleaPrice"),
  extractFn(src, "fleaPriceTitle"),
  "return { fleaPriceInfo: fleaPriceInfo, modeFleaPrice: modeFleaPrice," +
  " fleaPriceTitle: fleaPriceTitle, itemPrice: itemPrice," +
  " state: state, setQuote: function (q) { globalThis.QUOTE = q; } };"
].join("\n");
var api = new Function("state", "priceQuoteOf", FN)(state, priceQuoteOf);

/* 一件带构建期快照的物品：l=100 / a=120（PvP 构建期口径） */
var REC = { id: "rec", p: { l: 100, a: 120, lo: 90, hi: 140 } };

/* ① 快照命中 last：直接用它，来源标 snapshot */
api.setQuote({ rec: { lastLow: 111, avg24h: 222, avg7d: null } });
state.priceMode = "last";
state.dataScope.mode = "pve";
var i1 = api.fleaPriceInfo("rec", REC);
check("① 最新档命中本模式快照", i1.price === 111 && i1.from === "snapshot" &&
  i1.basis === "last" && i1.mode === "pve");

/* ② 切 24h 均价：同一个快照的另一档，不是同一串数字 */
state.priceMode = "avg24h";
var i2 = api.fleaPriceInfo("rec", REC);
check("② 24h 均价档取快照里的 a", i2.price === 222 && i2.from === "snapshot" &&
  i2.basis === "avg24h");

/* ③ 快照缺该档 → 回退构建期快照，并标 build（界面据此写明来源） */
api.setQuote({ rec: { lastLow: 111, avg24h: null, avg7d: null } });
var i3 = api.fleaPriceInfo("rec", REC);
check("③ 快照缺 24h 均价 → 回退构建期快照并标 build",
  i3.price === 120 && i3.from === "build");

/* ④ 两处都没有 → 0 / none，绝不用别的档顶替 */
api.setQuote({ rec: { lastLow: null, avg24h: null, avg7d: null } });
state.priceMode = "avg24h";
var i4 = api.fleaPriceInfo("rec", { p: { l: 100 } });
check("④ 两处都缺 → price=0 / from=none（不拿 last 顶 24h）",
  i4.price === 0 && i4.from === "none");

/* ⑤ 行情还没加载（priceQuoteOf 返回 undefined）→ 直接走构建期快照 */
api.setQuote(null);
state.priceMode = "last";
var i5 = api.fleaPriceInfo("rec", REC);
check("⑤ 行情未加载 → 构建期快照兜底", i5.price === 100 && i5.from === "build");

/* ⑥ 模式不符（真实实现返回 null）→ 不跨模式取数 */
api.setQuote({});
state.priceMode = "last";
var i6 = api.fleaPriceInfo("rec", REC);
check("⑥ 本模式没有该物品 → 不跨模式顶替", i6.price === 100 && i6.from === "build");

/* ⑦ basis 显式覆盖：同一行可以按指定档位问价（排序 / 汇总用） */
api.setQuote({ rec: { lastLow: 111, avg24h: 222, avg7d: 333 } });
check("⑦ basis 显式覆盖时取指定档",
  api.modeFleaPrice("rec", REC, "regular", "avg7d") === 333 &&
  api.modeFleaPrice("rec", REC, "regular", "avg24h") === 222);

/* ⑧ 浮窗文案：写清模式 / 档位 / 来源，缺价时明确说不顶替 */
state.dataScope.mode = "pvps";
state.priceMode = "last";
api.setQuote({ rec: { lastLow: 111, avg24h: null, avg7d: null } });
var tip = api.fleaPriceTitle({ fleaInfo: api.fleaPriceInfo("rec", REC) });
check("⑧a 浮窗含模式与档位名", tip.indexOf("PvPS") >= 0 && tip.indexOf("最新") >= 0);
check("⑧b 浮窗含价格与来源说明", tip.indexOf("111") >= 0 && tip.indexOf("行情快照") >= 0);
api.setQuote({ rec: { lastLow: null, avg24h: null, avg7d: null } });
var tip2 = api.fleaPriceTitle({ fleaInfo: api.fleaPriceInfo("rec", {}) });
check("⑧c 缺价时写明不顶替", tip2.indexOf("不拿别的口径") >= 0);

console.log(chk.join("\n"));
"""


def test_price_follows_mode_and_basis(tmp_path):
    """R219 核心：同一件物品，价格随「模式 × 价格档」变化，且缺档时如实标注来源。"""
    script = tmp_path / "price_probe.js"
    script.write_text(PRICE_JS, encoding="utf-8")
    node = subprocess.run(
        ["node", str(script), str(APP)],
        capture_output=True, text=True, timeout=60,
    )
    out = (node.stdout or "") + (node.stderr or "")
    assert node.returncode == 0, "价格口径 Node 断言失败：\n%s" % out
    assert "FAIL" not in node.stdout, out


# ---------------------------------------------------------------- 服务端：24h 均价补齐

def test_fill_avg24h_only_fills_missing_and_never_overwrites():
    """history?basis=24h 只补 a 缺失的行；已有值绝不被覆盖；未知形状静默跳过。"""
    class Client:
        def prices_history(self, mode, basis="7d"):
            assert basis == "24h", "必须显式请求 24h 口径"
            return {"items": {"a": {"avg": 111}, "b": {"avg": 222}}}

    items = {"a": {"l": 100, "a": 999}, "b": {"l": 200}, "c": {"l": 300}}
    filled = prices_source._fill_avg24h(Client(), "regular", items)
    assert filled == 1
    assert items["a"]["a"] == 999, "已有 a 不能被覆盖"
    assert items["b"]["a"] == 222, "缺失的 a 应被补上"
    assert "a" not in items["c"], "没取到均价就保持缺失，不按 0 填"

    class Bad:
        def prices_history(self, mode, basis="7d"):
            raise RuntimeError("旧服务端不支持 24h")

    assert prices_source._fill_avg24h(Bad(), "regular", {"x": {"l": 1}}) == 0


def _bundle(root: Path, name: str, mode: str, items: dict) -> None:
    path = root / "data" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "meta": {"generatedAt": "2026-11-09T11:50:00+08:00",
                 "sourceUpdatedMax": "2026-11-09T03:50:00Z"},
        "gameMode": mode,
        "items": items,
    }, ensure_ascii=False), encoding="utf-8")


def test_cloud_backfill_uses_same_mode_bundle_only(tmp_path):
    """云端只有最近低价时，用**同模式**内置快照补 24h 均价，并标注条数。"""
    _bundle(tmp_path, "flea-prices.json", "regular",
            {"x": {"lastLowPrice": 10, "avg24hPrice": 11}})
    _bundle(tmp_path, "flea-prices-pve.json", "pve",
            {"x": {"lastLowPrice": 20, "avg24hPrice": 21}})
    prices_source.clear_cache()

    payload = {"items": {"x": {"l": 10}}}
    filled = prices_source._backfill_from_bundle(str(tmp_path), "pve", payload, None)
    assert filled == 1
    assert payload["items"]["x"]["a"] == 21, "PvE 必须读 PvE 文件（不能拿 PvP 的 11）"
    assert payload["avg24hFromBundled"] == 1, "补了多少必须写进载荷，供界面说明来源"

    # 已有 a 时不补、也不标字段
    payload2 = {"items": {"x": {"l": 10, "a": 5}}}
    assert prices_source._backfill_from_bundle(str(tmp_path), "pve", payload2, None) == 0
    assert payload2["items"]["x"]["a"] == 5
    assert "avg24hFromBundled" not in payload2


def test_snapshot_for_cloud_payload_has_avg24h(tmp_path):
    """云端快照里的 market 字段要带 24h 均价（否则「均价」档整列 —）。"""

    class Client:
        def prices_market(self, mode):
            return {
                "status": "ok", "mode": mode, "tier": "member", "member": True,
                "generated_at": "2026-11-17T00:00:00+00:00",
                "delay_seconds": 0,
                "prices": {"x": 20},
                "market": {"x": {"l": 20, "a": 21, "o": 10, "c": 1.0}},
                "quota": {"tier": "member", "daily_limit": None, "used_today": 1},
            }

    payload = prices_source.snapshot_for(
        str(tmp_path), "pve", cloud_client=Client(), member=True,
        app_dir=str(tmp_path / "app"),
    )
    assert payload["source"] == "cloud"
    assert payload["items"]["x"]["l"] == 20
    assert payload["items"]["x"]["a"] == 21, "last=20 / 24h 均价=21 两档都要在"
    assert payload["tier"] == "member"
