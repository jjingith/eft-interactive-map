"""第十三轮：枪械构建页面（db4tarkov.com/gun 复刻）的自动化测试。

覆盖四层：
1. **数据完整性**：163 把枪 / 373 套可用内置预设；枪、槽位 allow、预设配件 id
   全部能在 `data/items.json` 找到；预设槽位路径的根槽位必须存在于该枪的真实 slots。
2. **口径分组**：直接抽取 app.js 里的 `gunCaliberOf` 在 Node 里跑全部 163 个真实枪名，
   防止型号数字被误判成口径（Glock 19X 9x19、7.62x25 拆成 2x25、5.45x39 拆成 .45 等回归）。
3. **整枪合计**：抽取 `gunTotals` 验证重量 / 价格 / 缺价计数 / 人机工效 / 后坐修正的累加口径。
4. **页面接线（静态）**：index.html 容器、renderGun 调用链、深色表格作用域、无运行期外链。

只读仓库文件，不联网、不引入第三方依赖。
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_JS = ROOT / "app.js"
INDEX_HTML = ROOT / "index.html"
STYLE_CSS = ROOT / "style.css"
GUNSLOTS = ROOT / "data" / "gunslots.json"
GUN_PRESETS = ROOT / "data" / "gun-presets.json"
ITEMS = ROOT / "data" / "items.json"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _guns() -> dict:
    return json.loads(_read(GUNSLOTS))["guns"]


def _presets() -> dict:
    return json.loads(_read(GUN_PRESETS))["presets"]


def _items() -> dict:
    return json.loads(_read(ITEMS))["items"]


# ---------------------------------------------------------------- 数据完整性
def test_gunslots_cover_all_local_guns():
    payload = json.loads(_read(GUNSLOTS))
    guns = payload["guns"]
    assert payload["schema"] == 6
    assert payload["count"] == len(guns) == 163
    items = _items()
    for gid, rec in guns.items():
        assert gid in items, "枪械 %s 不在 items.json" % gid
        assert items[gid].get("pt") == "Weapon", "枪械 %s 的 pt 不是 Weapon" % gid
        assert rec.get("n"), "枪械 %s 缺少名称" % gid
        assert isinstance(rec.get("slots"), list) and rec["slots"], "枪械 %s 没有槽位" % gid
        for slot in rec["slots"]:
            assert slot.get("sid") or slot.get("id"), "槽位缺少 sid/id：%s" % gid
            assert isinstance(slot.get("allow") or [], list)
            for aid in slot.get("allow") or []:
                assert aid in items, "%s 的槽位 %s allow 引用了不存在的物品 %s" % (
                    gid, slot.get("sid"), aid)


def test_builtin_presets_reference_real_guns_and_parts():
    payload = json.loads(_read(GUN_PRESETS))
    presets = payload["presets"]
    assert payload["count"] == len(presets) == 373
    assert payload["unsolvedCount"] == len(payload.get("unsolved") or [])
    guns = _guns()
    items = _items()
    total_parts = 0
    for pid, rec in presets.items():
        gid = rec.get("g")
        assert gid in guns, "预设 %s 指向不存在的枪 %s" % (pid, gid)
        roots = {(s.get("sid") or s.get("id")) for s in guns[gid].get("slots") or []}
        parts = rec.get("i") or {}
        assert parts, "预设 %s 没有任何配件" % pid
        total_parts += len(parts)
        for path, iid in parts.items():
            assert iid in items, "预设 %s 引用了不存在的配件 %s" % (pid, iid)
            assert path.split("/")[0] in roots, "预设 %s 的槽位路径根 %s 不在 %s 的 slots" % (
                pid, path, gid)
    assert total_parts > 3000, "内置预设配件总量异常：%s" % total_parts


# ---------------------------------------------------------------- 口径分组（Node 实跑）
def _extract_js_fragment(src: str, start_marker: str, end_marker: str) -> str:
    i = src.index(start_marker)
    j = src.index(end_marker, i)
    return src[i:j + len(end_marker)]


def _caliber_groups() -> dict:
    js = _read(APP_JS)
    token = _extract_js_fragment(js, "var GUN_CAL_TOKEN = new RegExp(", ");")
    types = _extract_js_fragment(js, "var GUN_CAL_TYPE = new RegExp(", ");")
    fn_start = js.index("function gunCaliberOf(name) {")
    fn_end = js.index("\n  }\n", fn_start) + len("\n  }\n")
    fn = js[fn_start:fn_end]
    harness = "\n".join([
        "var fs = require('fs');",
        token,
        types,
        fn,
        "var guns = JSON.parse(fs.readFileSync(process.argv[1], 'utf8')).guns;",
        "var out = {};",
        "for (var id in guns) { var c = gunCaliberOf(guns[id].n); (out[c] = out[c] || []).push(guns[id].n); }",
        "console.log(JSON.stringify(out));",
    ])
    proc = subprocess.run(["node", "-e", harness, str(GUNSLOTS)],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert proc.returncode == 0, "口径分组 Node 执行失败：\n%s\n%s" % (proc.stdout, proc.stderr)
    return json.loads(proc.stdout)


def test_caliber_grouping_covers_every_gun_without_model_number_fragments():
    groups = _caliber_groups()
    total = sum(len(v) for v in groups.values())
    assert total == 163, "口径分组丢失枪械：%s" % total
    assert len(groups) == 30, "口径分组数量异常：%s" % sorted(groups)
    assert groups.get("其它") == ["FN GL-40 Mk.2 榴弹发射器"]

    def group_of(name: str) -> str:
        for cal, names in groups.items():
            if name in names:
                return cal
        raise AssertionError("枪名未分组：%s" % name)

    # 型号数字不得被当成口径（Glock 19X 9x19 → 9x19）
    assert group_of("Glock 19X 9x19 手枪") == "9x19"
    # 缺口径不得被拆成「2x25 / 2x39 / 2x51 / 2x54 / 3x64 / 6x45」等碎片
    for bogus in ("19X9", "2x25", "2x39", "2x51", "2x54", "3x64", "6x45"):
        assert bogus not in groups, "出现了碎片口径分组：%s" % bogus
    assert group_of("托卡列夫 TT-33 7.62x25 手枪") == "7.62x25"
    assert group_of("RPK-16 5.45x39 轻机枪") == "5.45x39"
    assert group_of("Lone Star TX-15 DML 5.56x45 半自动卡宾枪") == "5.56x45"
    # 主流口径的枪数与本地数据一致
    assert len(groups["9x19"]) == 20
    assert len(groups["5.56x45"]) == 17
    assert len(groups["5.45x39"]) == 15
    assert len(groups["12铅径"]) == 14
    assert group_of("AKM 7.62x39 突击步枪") == "7.62x39"
    assert group_of("MP-133 12 铅径泵动式霰弹枪") == "12铅径"


# ---------------------------------------------------------------- 整枪合计（Node 实跑）
NODE_TOTALS = r"""
var fs = require('fs');
var src = fs.readFileSync(process.argv[2], 'utf8');
function extractFn(source, name) {
  var i = source.indexOf("function " + name + "(");
  if (i < 0) { throw new Error("找不到函数 " + name); }
  var start = source.indexOf("{", i), depth = 0;
  for (var k = start; k < source.length; k++) {
    var c = source[k];
    if (c === '"' || c === "'") { var q = c; k++; while (k < source.length && source[k] !== q) { if (source[k] === "\\") { k++; } k++; } continue; }
    if (c === "/" && source[k + 1] === "/") { while (k < source.length && source[k] !== "\n") { k++; } continue; }
    if (c === "{") { depth++; }
    else if (c === "}") { depth--; if (depth === 0) { return source.slice(i, k + 1); } }
  }
  throw new Error("花括号不平衡：" + name);
}
var PRICE_MODES = [{ key: "flea", label: "FLEA", fields: ["a"] }];
var LS_GUN = "eftmap.gun";
var state = {
  priceMode: "flea",
  items: {
    gunX: { n: "测试枪", w: 3, p: { a: 1000 } },
    partA: { n: "配件A", w: 0.5, p: { a: 200 }, mod: { e: 5, r: -0.1 } },
    partB: { n: "配件B", w: 0.25, p: {}, mod: { e: -2, r: 0.05 } },
    partC: { n: "缺价件", w: 0.2, p: {} }
  },
  gun: { gunId: "gunX", installed: { mod_a: "partA", mod_b: "partB", mod_c: "partC" },
         focus: null, presetId: null, refId: "", pending: [], slots: null }
};
var store = {};
var localStorage = {
  setItem: function (k, v) { store[k] = String(v); },
  getItem: function (k) { return (k in store) ? store[k] : null; }
};
var bundle = [
  extractFn(src, "ensureGunState"),
  extractFn(src, "persistGun"),
  extractFn(src, "itemRec"),
  extractFn(src, "itemPrice"),
  extractFn(src, "priceModeOf"),
  extractFn(src, "numOr0"),
  extractFn(src, "gunTotals")
].join("\n");
var api = new Function("state", "localStorage", "PRICE_MODES", "LS_GUN",
  bundle + "\nreturn { gunTotals: gunTotals, ensureGunState: ensureGunState };"
)(state, localStorage, PRICE_MODES, LS_GUN);
console.log(JSON.stringify(api.gunTotals()));
"""


def test_gun_totals_math(tmp_path):
    harness = tmp_path / "gun_totals.js"
    harness.write_text(NODE_TOTALS, encoding="utf-8")
    proc = subprocess.run(["node", str(harness), str(APP_JS)],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert proc.returncode == 0, "整枪合计 Node 执行失败：\n%s\n%s" % (proc.stdout, proc.stderr)
    tot = json.loads(proc.stdout)
    assert tot["parts"] == 3
    assert abs(tot["weight"] - 3.95) < 1e-9
    assert tot["price"] == 1200, "基础枪 + 有价配件 = 1200"
    assert tot["missing"] == 2, "两件缺价必须单独计数，不得按 0 元吞掉"
    assert tot["ergo"] == 3, "配件人机工效增减应累加（5 - 2）"
    assert abs(tot["recoil"] - (-0.05)) < 1e-9, "后坐修正应累加（-0.1 + 0.05）"


# ---------------------------------------------------------------- 页面接线
def test_index_html_has_gun_browse_and_visual_containers():
    html = _read(INDEX_HTML)
    assert 'id="gw-browse"' in html
    assert 'id="gw-visual"' in html
    assert 'class="gun-workbench"' in html
    assert html.index('id="gw-browse"') < html.index('id="gw-tree"')


def test_render_gun_calls_browse_and_visual():
    js = _read(APP_JS)
    assert "function renderGunBrowse(" in js
    assert "function renderGunVisual(" in js
    assert "function gunTotals(" in js
    start = js.index("function renderGun() {")
    end = js.index("\n  }", start)
    body = js[start:end]
    for call in ("rebuildGunTree();", "renderGunBrowse();", "renderGunVisual();", "renderGunRefOptions();"):
        assert call in body, "renderGun() 未调用 %s" % call
    # 属性栏与展示条必须使用同一套合计口径
    # R19.5：renderGunTreeList 重构为空间画布的 gwPartCard，切片终点随之更新（语义不变：
    # 属性段仍然终止于装配区起点）
    stats = js[js.index("function renderGunStats() {"):js.index("function gwPartCard(")]
    assert "gunTotals()" in stats
    # 口径分组的「其它」固定排最后，不参与字母序
    # （R19.1 浏览卡重写 + R19.4 死代码清理后，renderGunBrowse 位于 gunTotals 之后，
    #   切片终点改为 renderGunTableView —— 断言语义不变）
    browse = js[js.index("function renderGunBrowse() {"):js.index("function renderGunTableView() {")]
    assert 'a === "其它"' in browse


def test_gun_table_dark_scope_and_offline():
    css = _read(STYLE_CSS)
    for needle in (".gun-workbench .gw-browse", ".gun-workbench .gw-visual-img",
                   ".gun-workbench .tbl-scroll", ".gun-workbench .gw-browse-gun"):
        assert needle in css, "缺少配枪作用域样式 %s" % needle
    js = _read(APP_JS)
    urls = re.findall(r"https?://[^\s\"'<>]+", js)
    allowed = ("http://127.0.0.1", "http://www.w3.org/2000/svg")
    bad = [u for u in urls if not u.startswith(allowed)]
    assert not bad, "运行期代码含外部 URL：%s" % bad
    # 枪械图只能走本地图标目录
    assert 'ITEM_ICON_DIR + id + ".webp"' in js
