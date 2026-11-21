// R19.28 需求四：候选表属性列的确定性单元测试（Node 侧，只读，不依赖浏览器）。
//   从 app.js 里原样抽出本轮新增的纯函数区，在最小桩环境里断言，避免"照抄实现"式测试。
//   输出：docs/r19.28/unit-columns.json
const fs = require("fs"), path = require("path");
const ROOT = path.dirname(__dirname);
const src = fs.readFileSync(path.join(ROOT, "app.js"), "utf8");
let i0 = src.indexOf("  // ==================================================================\n  // R19.28 需求四");
if (i0 < 0) { i0 = src.indexOf("  /** 候选栏类别（按当前选中的槽位判定"); }
const i1 = src.indexOf("  function buildGunTable(");
if (i0 < 0 || i1 < 0 || i1 <= i0) { console.error("无法定位 R19.28 需求四代码区"); process.exit(2); }
const block = src.slice(i0, i1);

// ---- 最小桩：只提供本区依赖的外部函数，行为与 app.js 保持一致 ----
const PT_LABELS = { Scope: "瞄具", Muzzle: "枪口", Barrel: "枪管", Magazine: "弹匣", WeaponMod: "配件" };
function fmtPct(v, d) { return (v * 100).toFixed(d === undefined ? 1 : d) + "%"; }
function fmtNum(v, d) { return v.toFixed(d === undefined ? 2 : d); }
function fmtMoney(v) { return String(Math.round(v)); }
function itemRec(id) { return STUB_ITEMS[id] || null; }
function numOr0(v) { return typeof v === "number" ? v : 0; }
// 与 app.js 的 gwSidBase 逐字一致（strip mod_ 前缀 + 尾号）
function gwSidBase(sid) {
  return String(sid || "").replace(/^mod_/, "").replace(/#\d+$/, "").replace(/_\d{3,}$/, "");
}
function priceModeOf() { return { label: "商人" }; }
function gunNameCell() {}
let STUB_NODE = null, STUB_ITEMS = {}, STUB_AMMO = {}, STUB_GUN = "g1", STUB_AMMOSEL = {};
function gunNode() { return STUB_NODE; }
function ensureGunState() { return { gunId: STUB_GUN, installed: {} }; }
function gunAmmoState() { return STUB_AMMOSEL; }
function defaultAmmoForGun() { return STUB_AMMO[STUB_GUN] || null; }
const state = { ammo: { byId: {} }, priceMode: 0 };
function gunCompat() { return { ok: true, kind: "ok", reason: "" }; }
function itemQuoted() { return true; }
function itemPrice() { return 1; }

const api = new Function(
  "PT_LABELS", "fmtPct", "fmtNum", "fmtMoney", "itemRec", "numOr0", "gwSidBase",
  "priceModeOf", "gunNameCell", "gunNode", "ensureGunState", "gunAmmoState",
  "defaultAmmoForGun", "state", "gunCompat", "itemQuoted", "itemPrice",
  block + "\nreturn {gunTableKind:gunTableKind,gunModVal:gunModVal,gunSizeText:gunSizeText," +
         "gunRE3:gunRE3,gunMagFullWeight:gunMagFullWeight,gunColumns:gunColumns};"
)(PT_LABELS, fmtPct, fmtNum, fmtMoney, itemRec, numOr0, gwSidBase, priceModeOf, gunNameCell,
  gunNode, ensureGunState, gunAmmoState, defaultAmmoForGun, state, gunCompat, itemQuoted, itemPrice);

const results = [];
function ok(name, cond, detail) {
  results.push({ name: name, pass: !!cond, detail: detail === undefined ? null : detail });
}
function keysOf(cols) { return cols.map(function (c) { return c.key; }).join("|"); }

// ---------------------------------------------------------------- A：R+E/3（R19.29 任务 C 修正符号）
//   数据约定（data/items.json 全量核实）：武器配件 mod.r「减少记负数、增加记正数」。
//   R 取正面增益语义：R = -r×100（减少为正、增加为负），再 R + E/3。符号仅反转一次。
{
  // 任务书示例 1：减后坐 3%、人机 +10 → 3 + 10/3 = 6.333
  ok("A1_减后坐3_人机10", api.gunRE3({ mod: { r: -0.03, e: 10 } }).toFixed(3) === "6.333",
     api.gunRE3({ mod: { r: -0.03, e: 10 } }));
  // 任务书示例 2：加后坐 3%、人机 +10 → -3 + 10/3 = 0.333
  ok("A2_加后坐3_人机10", api.gunRE3({ mod: { r: 0.03, e: 10 } }).toFixed(3) === "0.333",
     api.gunRE3({ mod: { r: 0.03, e: 10 } }));
  // 任务书示例 3：加后坐 3%、人机 +6 → -3 + 6/3 = -1.000（综合为负数）
  ok("A3_加后坐3_人机6_负", api.gunRE3({ mod: { r: 0.03, e: 6 } }).toFixed(3) === "-1.000",
     api.gunRE3({ mod: { r: 0.03, e: 6 } }));
  // 任务书示例 4：减后坐 6%、人机 -6 → 6 + (-6)/3 = 4.000
  ok("A4_减后坐6_人机负6", api.gunRE3({ mod: { r: -0.06, e: -6 } }).toFixed(3) === "4.000",
     api.gunRE3({ mod: { r: -0.06, e: -6 } }));
  // 人机为 0（真实零值，不是缺失）
  ok("A5_人机为0", api.gunRE3({ mod: { r: -0.09, e: 0 } }).toFixed(3) === "9.000",
     api.gunRE3({ mod: { r: -0.09, e: 0 } }));
  // 后坐力为 0（真实零值）→ R=0，仅人机/3
  ok("A6_后坐力为0", api.gunRE3({ mod: { r: 0, e: 6 } }).toFixed(3) === "2.000",
     api.gunRE3({ mod: { r: 0, e: 6 } }));
  // 字段缺失 → null（不得输出看似有效的虚假结果）
  ok("A7_缺人机_null", api.gunRE3({ mod: { r: -0.03 } }) === null, api.gunRE3({ mod: { r: -0.03 } }));
  ok("A8_缺后坐_null", api.gunRE3({ mod: { e: 10 } }) === null);
  ok("A9_无mod_null", api.gunRE3({}) === null);
  // 符号只反转一次：减后坐 3%（r=-0.03）→ R=+3（既不是 +0.03 也不是 -3）
  ok("A10_符号仅反一次", Math.abs(api.gunRE3({ mod: { r: -0.03, e: 0 } }) - 3) < 1e-9,
     api.gunRE3({ mod: { r: -0.03, e: 0 } }));
}

// ---------------------------------------------------------------- B：三态取值
{
  ok("B1_真实0非缺失", api.gunModVal({ mod: { e: 0 } }, "e") === 0);
  ok("B2_缺失为null", api.gunModVal({ mod: {} }, "e") === null);
  ok("B3_无mod为null", api.gunModVal({}, "e") === null);
  ok("B4_非数字为null", api.gunModVal({ mod: { e: "3" } }, "e") === null);
  ok("B5_尺寸2x1", api.gunSizeText({ gw: 2, gh: 1 }) === "2×1", api.gunSizeText({ gw: 2, gh: 1 }));
  ok("B6_尺寸缺失null", api.gunSizeText({ gw: 2 }) === null);
}

// ---------------------------------------------------------------- C：弹匣重量
{
  STUB_AMMO["g1"] = { n: "5.45x39毫米 PS", w: 0.011 };
  STUB_AMMOSEL = {};
  // 空重 0.125 + 30 发 × 0.011 = 0.455
  const full = api.gunMagFullWeight({ w: 0.125, cap: 30 }, "g1");
  ok("C1_满重计算", full !== null && Math.abs(full - 0.455) < 1e-9, full);
  ok("C2_缺容量null", api.gunMagFullWeight({ w: 0.125 }, "g1") === null);
  ok("C3_缺空重null", api.gunMagFullWeight({ cap: 30 }, "g1") === null);
  // 无弹种（该枪口径没弹 / 没默认弹）→ null，不伪造
  const old = STUB_AMMO["g1"]; STUB_AMMO["g1"] = null;
  ok("C4_缺弹种null", api.gunMagFullWeight({ w: 0.125, cap: 30 }, "g1") === null);
  STUB_AMMO["g1"] = old;
  // 用户在子弹格选了弹种 → 用选中弹重
  STUB_AMMOSEL["g1"] = "ammo1";
  state.ammo.byId["ammo1"] = { n: "5.45x39毫米 BS", w: 0.021 };
  ok("C5_用选中弹种", Math.abs(api.gunMagFullWeight({ w: 0.125, cap: 30 }, "g1") - 0.755) < 1e-9,
     api.gunMagFullWeight({ w: 0.125, cap: 30 }, "g1"));
  STUB_AMMOSEL = {};
}

// ---------------------------------------------------------------- D：类别判定
{
  STUB_NODE = { sid: "mod_magazine", allow: [] };
  ok("D1_弹匣", api.gunTableKind() === "magazine", api.gunTableKind());
  STUB_NODE = { sid: "mod_barrel", allow: [] };
  ok("D2_枪管", api.gunTableKind() === "barrel");
  STUB_NODE = { sid: "mod_muzzle", allow: [] };
  ok("D3_枪口", api.gunTableKind() === "muzzle");
  STUB_NODE = { sid: "mod_muzzle_000", allow: [] };
  ok("D4_枪口带序号", api.gunTableKind() === "muzzle");
  STUB_NODE = { sid: "mod_handguard", allow: [] };
  ok("D5_其它为一般", api.gunTableKind() === "generic");
  STUB_NODE = null;
  ok("D6_无槽位为一般", api.gunTableKind() === "generic");
}

// ---------------------------------------------------------------- E：列序
function colsFor(sid, rows) {
  STUB_NODE = { sid: sid, allow: [] };
  const c = api.gunColumns(rows);
  STUB_NODE = null;
  return c.map(function (x) { return x.key; });
}
{
  const rows = [{ slots: 2, recoil: -0.03, ergo: 10, re3: 6.667, size: "2×1", w: 0.2, acc: null }];
  ok("E1_一般配件列序",
     colsFor("mod_handguard", rows).join("|") ===
     "n|slots|recoil|ergo|re3|size|w", colsFor("mod_handguard", rows));
  // 枪管：MOA 列缺数据 → 整列隐藏（不编造）
  ok("E2_枪管隐藏MOA",
     colsFor("mod_barrel", rows).join("|") === "n|slots|recoil|ergo|re3|size|w",
     colsFor("mod_barrel", rows));
  // 枪口：有 ACC 时 ACC 必须夹在后坐力与人机之间
  const mrows = [{ slots: 0, recoil: -0.09, acc: 0.03, ergo: -2, re3: 8.333, size: "1×1", w: 0.1 }];
  ok("E3_枪口ACC位置",
     colsFor("mod_muzzle", mrows).join("|") === "n|slots|recoil|acc|ergo|re3|size|w",
     colsFor("mod_muzzle", mrows));
  // 枪口候选全都没有 ACC → ACC 整列隐藏
  ok("E4_枪口无ACC隐藏",
     colsFor("mod_muzzle", rows).join("|") === "n|slots|recoil|ergo|re3|size|w",
     colsFor("mod_muzzle", rows));
  // 弹匣：专属列，且不显示后坐力 / 子槽 / R+E/3
  const mags = [{ ergo: -1, cap: 30, magEmpty: 0.125, magFull: 0.455, w: 0.125 }];
  const mc = colsFor("mod_magazine", mags);
  ok("E5_弹匣列序", mc.join("|") === "n|ergo|cap|w|magFull", mc);
  ok("E6_弹匣无后坐", mc.indexOf("recoil") < 0);
  ok("E7_弹匣无子槽", mc.indexOf("slots") < 0);
  ok("E8_弹匣无RE3", mc.indexOf("re3") < 0);
  ok("E9_弹匣无容量则隐藏",
     colsFor("mod_magazine", [{ ergo: -1, magEmpty: 0.1, magFull: null, w: 0.1 }]).join("|") ===
     "n|ergo|w", colsFor("mod_magazine", [{ ergo: -1, magEmpty: 0.1, magFull: null, w: 0.1 }]));
  // 空候选列表也不能崩，且仍给出表头
  ok("E10_空列表不崩", colsFor("mod_handguard", []).length >= 3);
}

// ---------------------------------------------------------------- F：渲染文本
function textOf(col, row) {
  const cell = { textContent: "", title: "", dataset: {}, className: "" };
  col.render(cell, row);
  return { t: cell.textContent, title: cell.title };
}
{
  const c = api.gunColumns([{ slots: 0, recoil: -0.03, ergo: 10, re3: 6.667, size: "2×1", w: 0.2 }]);
  const by = {};
  c.forEach(function (x) { by[x.key] = x; });
  ok("F1_RE3三位小数", textOf(by.re3, { recoil: -0.03, ergo: 10, re3: 6.667 }).t === "6.667",
     textOf(by.re3, { recoil: -0.03, ergo: 10, re3: 6.667 }));
  ok("F2_后坐力负号", textOf(by.recoil, { recoil: -0.03 }).t === "-3.0%", textOf(by.recoil, { recoil: -0.03 }));
  ok("F3_子槽真实0", textOf(by.slots, { slots: 0 }).t === "0", textOf(by.slots, { slots: 0 }));
  ok("F4_缺失显示破折号", textOf(by.recoil, { recoil: null }).t === "—");
  ok("F5_缺失有说明", textOf(by.recoil, { recoil: null }).title.indexOf("不按 0 计入") >= 0,
     textOf(by.recoil, { recoil: null }).title);
  ok("F6_尺寸文本", textOf(by.size, { size: "2×1" }).t === "2×1");
  // R19.29 任务 C：表格显示结果与 gunRE3 计算结果一致（用实时计算值渲染，而非写死常量）
  {
    const rec = { mod: { r: 0.03, e: 6 } };               // 加后坐 3%、人机 6 → -1.000
    const computed = api.gunRE3(rec);
    const shown = textOf(by.re3, { recoil: 0.03, ergo: 6, re3: computed }).t;
    ok("F7_显示与计算一致", shown === "-1.000" && computed.toFixed(3) === "-1.000",
       { computed: computed, shown: shown });
  }
}

const pass = results.filter(function (r) { return r.pass; }).length;
const fail = results.filter(function (r) { return !r.pass; });
fs.mkdirSync(path.join(ROOT, "docs/r19.28"), { recursive: true });
fs.writeFileSync(path.join(ROOT, "docs/r19.28/unit-columns.json"),
  JSON.stringify({ total: results.length, passed: pass, failed: fail.length, results: results }, null, 2), "utf8");
console.log("R19.28 需求四 / R19.29 任务C 单元测试：" + pass + "/" + results.length + " 通过");
fail.forEach(function (f) { console.log("  FAIL " + f.name + "  " + JSON.stringify(f.detail)); });
process.exit(fail.length ? 1 : 0);
