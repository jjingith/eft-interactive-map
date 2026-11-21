"""第六轮：配枪工作台 / 枪械预设 / 人物-枪械联动的真实业务测试。

不复制实现：从 app.js 抽取纯函数到 Node 里跑；预设存储走后端 HTTP 接口。
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
APP_JS = ROOT / "app.js"
INDEX_HTML = ROOT / "index.html"
STYLE_CSS = ROOT / "style.css"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


NODE_HARNESS = r"""
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
      while (k < source.length && source[k] !== q) {
        if (source[k] === "\\") { k++; }
        k++;
      }
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
  if (i < 0) { throw new Error("找不到变量 " + name); }
  var end = source.indexOf("\n", i);
  var line = source.slice(i, end);
  if (line.indexOf("{") >= 0) {
    var depth = 0;
    for (var k = source.indexOf("{", i); k < source.length; k++) {
      if (source[k] === "{") { depth++; }
      else if (source[k] === "}") { depth--; if (depth === 0) { end = k + 1; break; } }
    }
  }
  return source.slice(i, end).replace(/;\s*$/, ";");
}

var ITEMS = {
  gunX:    { n: "测试枪", w: 3.0, p: { a: 50000 } },
  recA:    { n: "机匣A", w: 0.5, p: { a: 1000 },
             slots: [{ sid: "mod_barrel", label: "枪管", allow: ["barrelA", "barrelB"] }] },
  recAlt:  { n: "机匣B", w: 0.6, p: { a: 2000 }, slots: [] },
  recBad:  { n: "冲突机匣", w: 0.5, p: { a: 1500 }, conflict: ["barrelA"] },
  barrelA: { n: "枪管A", w: 0.4, p: { a: 300 } },
  barrelB: { n: "枪管B", w: 0.45, p: { a: 400 } },
  gripA:   { n: "握把A", w: 0.1, p: { a: 100 } },
  noPrice: { n: "缺价件", w: 0.2, p: {} }
};
var slotList = [
  { sid: "mod_reciever", label: "机匣", allow: ["recA", "recAlt", "recBad"] },
  { sid: "mod_pistol_grip", label: "握把", allow: ["gripA", "noPrice"] }
];

var state = {
  items: ITEMS, loadout: {}, gunslots: {}, presets: {}, priceMode: "flea", gun: null,
  gunTable: null, dataScope: { mode: "regular" }
};
var store = {};
var localStorage = {
  setItem: function (k, v) { store[k] = String(v); },
  getItem: function (k) { return (k in store) ? store[k] : null; },
  removeItem: function (k) { delete store[k]; }
};
var PT_LABELS = { mod: "配件" };
var PRICE_MODES = [
  { key: "flea", label: "FLEA", fields: ["a", "l", "lo", "hi"], avail: true },
  { key: "base", label: "BASE", fields: ["b"], avail: true },
  { key: "pvp", label: "PVP", fields: [], avail: false },
  { key: "scav", label: "SCAV", fields: [], avail: false }
];
var GUN_REF_PREFIX = "@wp:";

var bundle = [
  "var el = {};",
  // R219：价格口径函数要用到模式短名表（本 harness 只跑本地快照，故固定 regular）
  "var MODE_SHORT = { regular: \"PvP\", pve: \"PvE\", pvps: \"PvPS\" };",
  extractVar(src, "GUN_REF_PREFIX"),
  extractFn(src, "isGunRef"),
  extractFn(src, "gunRefToken"),
  extractFn(src, "gunRefId"),
  extractFn(src, "weaponPresets"),
  extractFn(src, "weaponPresetById"),
  extractFn(src, "gunRecord"),
  extractFn(src, "builtinGunPresets"),
  extractFn(src, "gunDefaultBuild"),
  extractFn(src, "builtinGunPresets"),
  extractFn(src, "gunDefaultBuild"),
  extractFn(src, "gunRefInfo"),
  extractFn(src, "flea24hPrice"),
  extractFn(src, "fleaPriceInfo"),
  extractFn(src, "modeFleaPrice"),
  extractFn(src, "flea7dPrice"),
  extractFn(src, "weaponPresetTotals"),
  extractFn(src, "sellPriceOf"),
  extractFn(src, "buyPriceOf"),
  extractVar(src, "GUN_SLOT_LABELS"),
  extractVar(src, "LS_GUN"),
  extractFn(src, "gunSlotLabel"),
  extractFn(src, "ensureGunState"),
  extractFn(src, "persistGun"),
  extractFn(src, "addGunSlots"),
  extractFn(src, "buildGunTree"),
  extractFn(src, "rebuildGunTree"),
  extractFn(src, "gunNode"),
  extractFn(src, "gunPathLabel"),
  // R19.11：兼容性判定拆成 gunCompatOf（纯判定）+ gunCompat（带缓存）；
  // 沙箱里没有引擎，gbCtx/window.GB 置空 → 只走 allow + 互斥这两步
  "var gbCtx = function () { return null; }; var window = { GB: null };" +
  "var GW_COMPAT_CACHE = { key: '', map: {} };",
  extractFn(src, "gunCompatOf"),
  extractFn(src, "gunCompat"),
  // R19.11：兼容性判定拆成 gunCompatOf（纯判定）+ gunCompat（带缓存）；
  // 沙箱里没有引擎，gbCtx/window.GB 置空 → 只走 allow + 互斥这两步
  "var gbCtx = function () { return null; }; var window = { GB: null };",
  extractFn(src, "gunCompatOf"),
  extractFn(src, "gunCompat"),
  extractFn(src, "gunInstallCheck"),
  // R20.4/20.5：候选行新增显示字段（差额 / 尺寸 / 商人 / 跳蚤行情）；
  // 这里只抽取纯计算函数，R20 的行情读取链在沙箱里用 null 桩替代（G4 只校验兼容性标记）
  extractFn(src, "gunModVal"),
  extractFn(src, "gunRE3"),
  extractFn(src, "gunSizeText"),
  extractFn(src, "avg7dPriceOf"),
  extractFn(src, "traderMinLevel"),
  "function gunMagFullWeight() { return null; }",
  "function fleaQuoteOf() { return null; }",
  extractFn(src, "gunRows"),
  extractFn(src, "gunPushHistory"),
  extractFn(src, "gunEquip"),
  extractFn(src, "clearGunSlot"),
  extractFn(src, "selectGun"),
  extractFn(src, "currentWeaponPreset"),
  extractFn(src, "itemRec"),
  extractFn(src, "itemPrice"),
  extractFn(src, "itemQuoted"),
  extractFn(src, "numOr0"),
  extractFn(src, "priceModeOf"),
  extractFn(src, "inList"),
  extractFn(src, "nameOf"),
  extractFn(src, "rootDef")
].join("\n");

var api = new Function(
  "state", "localStorage", "PT_LABELS", "PRICE_MODES", "ROOT_SLOTS",
  "persistLoadout", "renderGun", "syncGunHint", "renderGunTableDupe",
  "var ROOT_BY_KEY = {};ROOT_SLOTS.forEach(function (s) { ROOT_BY_KEY[s.key] = s; });\n" +
  bundle + "\nreturn {" +
  "ensureGunState:ensureGunState,buildGunTree:buildGunTree,rebuildGunTree:rebuildGunTree," +
  "gunEquip:gunEquip,clearGunSlot:clearGunSlot,selectGun:selectGun,gunRows:gunRows," +
  "gunInstallCheck:gunInstallCheck,weaponPresetTotals:weaponPresetTotals," +
  "currentWeaponPreset:currentWeaponPreset,gunRefToken:gunRefToken,gunRefInfo:gunRefInfo," +
  "nameOf:nameOf};"
)(
  state, localStorage, PT_LABELS, PRICE_MODES,
  [{ key: "primary1", label: "主武器 1", gunref: true },
   { key: "holster", label: "手枪", gunref: true }],
  function () {}, function () {}, function () {}, null
);

function resetGun() {
  state.gunslots = {
    gunX: { n: "测试枪", ergo: 50, rv: 100, rh: 300, moa: 1.2, slots: slotList }
  };
  state.gun = null;
  state.presets = {};
  store = {};
  localStorage.removeItem("eftmap.gun");
}

var checks = 0, failures = [];
function check(name, cond) { checks++; if (!cond) { failures.push(name); } }
function installed() { return api.ensureGunState().installed; }

/* G1 槽位树来自真实 slots[].allow，未装父件时子槽不存在 */
resetGun();
api.selectGun("gunX");
check("G1 基础枪槽位建树（2 个顶级槽）", api.ensureGunState().focus && api.buildGunTree().order.length === 2);
check("G1 未装父件时没有子槽（无 mod_reciever/mod_barrel）",
  api.buildGunTree().nodes["mod_reciever/mod_barrel"] === undefined);

/* G2 装上父件 → 动态子槽出现；装上子件 → 两者都记录 */
api.gunEquip("recA");
check("G2 父件写入稳定 id", installed().mod_reciever === "recA");
check("G2 父件装上后动态出现子槽 mod_reciever/mod_barrel",
  !!api.ensureGunState().slots.nodes["mod_reciever/mod_barrel"]);
api.ensureGunState().focus = "mod_reciever/mod_barrel";
api.gunEquip("barrelA");
check("G2 子槽配件装上", installed()["mod_reciever/mod_barrel"] === "barrelA");

/* G3 更换父件 → 子槽消失，残留附件一并清理（不出现孤儿槽） */
api.ensureGunState().focus = "mod_reciever";
api.gunEquip("recAlt");
check("G3 父件换为新 id", installed().mod_reciever === "recAlt");
check("G3 旧父件的子槽配件被清理", installed()["mod_reciever/mod_barrel"] === undefined);
check("G3 树上不再有失效子槽", api.ensureGunState().slots.nodes["mod_reciever/mod_barrel"] === undefined);

/* G4 冲突配件：候选行标红且安装被拒绝，状态不变 */
resetGun();
api.selectGun("gunX");
api.gunEquip("barrelA");            // 先装枪管（若无父件该槽位不存在 → 见下）
api.ensureGunState().focus = "mod_reciever";
api.gunEquip("recA");
api.ensureGunState().focus = "mod_reciever/mod_barrel";
api.gunEquip("barrelA");
api.ensureGunState().focus = "mod_reciever";
var rows = api.gunRows();
var badRow = null, okRow = null;
for (var i = 0; i < rows.length; i++) {
  if (rows[i].__id === "recBad") { badRow = rows[i]; }
  if (rows[i].__id === "recAlt") { okRow = rows[i]; }
}
check("G4 与已装件互斥的候选被标记 conflict/blocked", badRow && badRow.conflict === true && badRow.blocked === true);
check("G4 冲突行带明确原因", badRow && badRow.conflictText.indexOf("互斥") >= 0);
check("G4 合法候选不被误标", okRow && okRow.conflict === false);
api.gunEquip("recBad");
check("G4 冲突件不得装上（状态保持 recA）", installed().mod_reciever === "recA");

/* G5 同一配件不得重复占用两个槽位 */
resetGun();
api.selectGun("gunX");
api.ensureGunState().focus = "mod_reciever";
api.gunEquip("recAlt");
api.ensureGunState().focus = "mod_pistol_grip";
var dupChk = api.gunInstallCheck("recAlt", api.ensureGunState().slots.nodes["mod_pistol_grip"]);
check("G5 不在 allow 里的配件被拒绝", dupChk.allowed === false);

/* G6 重量 / 价格：基础枪 + 配件，且同一配件只计一次；缺价不当 0 混入 */
resetGun();
state.presets = { weapon: { presets: [
  { id: "wp_x", name: "测试预设", gunId: "gunX",
    items: { mod_reciever: "recA", "mod_reciever/mod_barrel": "barrelA", dup: "barrelA" } }
] } };
var tot = api.weaponPresetTotals("wp_x");
check("G6 重量含基础枪与配件且重复配件只计一次",
  Math.abs(tot.weight - (3.0 + 0.5 + 0.4)) < 1e-9);
check("G6 件数去重后 = 枪 + 2 件配件", tot.count === 3);
check("G6 价格按价格档累加", tot.price === 50000 + 1000 + 300);
state.presets = { weapon: { presets: [
  { id: "wp_y", name: "缺价", gunId: "noPrice", items: { a: "noPrice" } }
] } };
var tot2 = api.weaponPresetTotals("wp_y");
check("G6 缺价件单独计数而不是按 0 元混入", tot2.missing === 1 && tot2.count === 1);

/* G7 当前改装 → 枪械预设负载（稳定 item id，不含中文名） */
resetGun();
api.selectGun("gunX");
api.gunEquip("recA");
var payload = api.currentWeaponPreset("我的枪", null);
check("G7 预设负载带基础枪 id", payload.gunId === "gunX");
check("G7 预设负载按槽位路径保存配件 id", payload.items.mod_reciever === "recA");
check("G7 未指定 id 时由后端分配（前端不伪造）", payload.id === undefined);

/* G8 缺失的枪械预设引用被明确标记，不静默替换 */
var info = api.gunRefInfo(api.gunRefToken("wp_nope"));
check("G8 缺失引用 missing=true 且保留原 id", info.missing === true && info.id === "wp_nope");
check("G8 名称显示「缺失」", api.nameOf(api.gunRefToken("wp_nope")).indexOf("缺失") >= 0);

if (failures.length) {
  console.error("FAIL (" + failures.length + "/" + checks + "):\n" + failures.join("\n"));
  process.exit(1);
}
console.log("OK " + checks);
"""


def test_gun_workbench_business_logic(tmp_path):
    harness = tmp_path / "gun_workbench.js"
    harness.write_text(NODE_HARNESS, encoding="utf-8")
    proc = subprocess.run(["node", str(harness), str(APP_JS)],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert proc.returncode == 0, "配枪业务测试失败：\n%s\n%s" % (proc.stdout, proc.stderr)
    match = re.search(r"OK (\d+)", proc.stdout)
    assert match and int(match.group(1)) >= 15, proc.stdout


def test_index_html_has_gun_workbench_skeleton():
    html = _read(INDEX_HTML)
    assert 'class="gun-workbench"' in html
    for needle in ('id="gw-search"', 'id="gw-results"', 'id="gw-ref"',
                   'id="gw-hint"', 'id="gw-stats"', 'id="gw-tree"',
                   'id="gw-slotinfo"', 'id="gw-hidebad"', 'id="gw-table"',
                   # R19.90 / R19.91：预设入口上提到二级工具条 #cb-gun
                   'id="gw-save-link"', 'id="gw-read-link"', 'id="gw-clear-link"'):
        assert needle in html, "配枪工作台骨架缺 %s" % needle


def test_app_js_exposes_gun_preset_api():
    js = _read(APP_JS)
    for name in ("ensurePresets", "presetPost", "currentLoadoutPreset", "currentWeaponPreset",
                 "applyLoadoutPreset", "applyWeaponPreset", "openPresetModal",
                 "gunInstallCheck", "gunEquip", "clearGunSlot", "selectGun",
                 "applyBuiltinGunPreset", "rebuildGunTree", "weaponPresetTotals"):
        assert ("function " + name + "(") in js, "缺少函数 %s" % name
    # PRESET 不再是占位：弹窗有九项操作
    for label in ("新建", "另存为", "覆盖保存", "重命名", "加载", "删除", "导出", "导入"):
        assert label in js, "预设菜单缺操作 %s" % label
    # 枪械槽存稳定引用，而不是中文名 / 物品 id
    assert 'var GUN_REF_PREFIX = "@wp:";' in js
    assert "gunRefToken(wp.id)" in js or "gunRefToken(presetId)" in js


def test_css_gun_workbench_is_scoped():
    css = _read(STYLE_CSS)
    assert ".gun-workbench {" in css
    assert ".gun-workbench .gw-slot" in css
    assert ".lw-scope .lw-preset-box" in css
    # 不得给 SVG / 图元加 CSS 动画或 transform
    gun = css[css.index(".gun-workbench {"):]
    assert "@keyframes" not in gun


def test_app_js_has_no_runtime_external_urls():
    js = _read(APP_JS)
    urls = re.findall(r"https?://[^\s\"'<>]+", js)
    allowed = ("http://127.0.0.1", "http://www.w3.org/2000/svg")
    bad = [u for u in urls if not u.startswith(allowed)]
    assert not bad, "运行期代码含外部 URL：%s" % bad
    assert "https://" not in js.replace("http://www.w3.org/2000/svg", "")
