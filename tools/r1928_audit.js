// R19.20 引擎审计：AKM 照门 / AKMP 并列布局（只读）。
// 输出：docs/r19.20-akm-akmp-parallel/engine-audit.json
const fs = require("fs"), path = require("path");
const ROOT = path.dirname(__dirname);
const GB = require(path.join(ROOT, "gun_builder.js"));
const items = JSON.parse(fs.readFileSync(path.join(ROOT, "data/items.json"), "utf8")).items;
const stats = JSON.parse(fs.readFileSync(path.join(ROOT, "data/gun-stats.json"), "utf8"));
const presets = JSON.parse(fs.readFileSync(path.join(ROOT, "data/gun-presets.json"), "utf8")).presets || {};
const gunslots = JSON.parse(fs.readFileSync(path.join(ROOT, "data/gunslots.json"), "utf8")).guns;
const calib = JSON.parse(fs.readFileSync(path.join(ROOT, "data/gun-layout-calibration.json"), "utf8"));
const src = fs.readFileSync(path.join(ROOT, "app.js"), "utf8");
const block = src.slice(src.indexOf("function gwSidBase("), src.indexOf("function renderGunSkin("));
const api = new Function("itemRec", "GW_ITEM_MAP", block +
  "\nreturn {gwBuildLayout:gwBuildLayout,gwApplyCalibToLayout:gwApplyCalibToLayout," +
  "gwIsAkmpPairSlot:gwIsAkmpPairSlot,gwSlotVisible:gwSlotVisible};")(
  function (id) { return items[id] || null; }, items);
const ctx = GB.context(items, stats);

const AKMP_RS = "5a0ed824fcdbcb0176308b0d";
const AKM_SIGHT = "59d650cf86f7741b846413a4";
const AKMP_SUB_ID = "5a0eda49fcdbcb001912fa61";
const GUNS = {
  "59d6088586f774275f37482f": "AKM",
  "59ff346386f77477562ff5e2": "AKMS",
  "5a0ec13bfcdbcb00165aa685": "AKMN",
  "5abcbc27d8ce8700182eceeb": "AKMSN",
  "59e6152586f77473dc057aa1": "VPO-136",
};

function defInst(gid) {
  const st = (stats.guns || {})[gid] || {};
  if (st.preset && presets[st.preset]) { return presets[st.preset].i || {}; }
  for (const p in presets) { if (presets[p] && presets[p].g === gid) { return presets[p].i || {}; } }
  return {};
}
function build(gid, instOverride, useCalib) {
  const inst = GB.sanitize(ctx, gid, instOverride || defInst(gid)).installed;
  const tree = GB.buildTree(ctx, gid, inst);
  const L = api.gwBuildLayout({ gunId: gid, installed: inst, slots: tree, noCalib: true });
  const recs = (calib.guns[gid] || {}).slots || {};
  let info = null;
  if (useCalib) { info = api.gwApplyCalibToLayout(L, { gunId: gid, installed: inst, slots: tree }, recs); }
  const by = {};
  L.cells.forEach(function (c) { by[c.path] = { row: c.row - L.topPad, col: c.col, path: c.path }; });
  return { inst, tree, L, by, recs, info };
}

const checks = {};
const detail = { guns: {} };
function ok(name, cond, extra) {
  checks[name] = !!cond;
  if (!cond) { checks["FAILED_" + name] = extra === undefined ? true : extra; }
}

for (const gid of Object.keys(GUNS)) {
  const name = GUNS[gid];
  const b0 = build(gid, null, false);        // 自动布局
  const b1 = build(gid, null, true);         // 最终（校准套用）
  const sightAuto = b0.by["mod_sight_rear"];
  const akmpAuto = b0.by["mod_sight_rear/mod_sight_rear"];
  const sightFin = b1.by["mod_sight_rear"];
  const akmpFin = b1.by["mod_sight_rear/mod_sight_rear"];
  const gn = b0.tree.nodes["mod_sight_rear"];
  const kn = b0.tree.nodes["mod_sight_rear/mod_sight_rear"];

  const rearPaths = Object.keys(b0.tree.nodes).filter(function (p) { return /sight_rear/.test(p); });
  ok("r1920_" + name + "_two_sight_slots", rearPaths.length === 2, rearPaths);
  ok("r1920_" + name + "_left_allow_no_akmp",
     gn && gn.allow.indexOf(AKMP_RS) < 0, gn && gn.allow);
  ok("r1920_" + name + "_right_allow_akmp_only",
     kn && kn.allow.length === 1 && kn.allow[0] === AKMP_RS, kn && kn.allow);
  ok("r1920_" + name + "_pair_predicate",
     api.gwIsAkmpPairSlot({ slots: b0.tree, installed: b0.inst }, "mod_sight_rear/mod_sight_rear"));
  ok("r1920_" + name + "_auto_parallel_right",
     sightAuto && akmpAuto && akmpAuto.row === sightAuto.row && akmpAuto.col === sightAuto.col + 1,
     { sightAuto, akmpAuto });
  ok("r1920_" + name + "_auto_not_below",
     sightAuto && akmpAuto && !(akmpAuto.col === sightAuto.col && akmpAuto.row === sightAuto.row + 1),
     { sightAuto, akmpAuto });
  ok("r1920_" + name + "_final_parallel",
     sightFin && akmpFin && sightFin.row === akmpFin.row && akmpFin.col === sightFin.col + 1,
     { sightFin, akmpFin });

  // 装上 AKMP → 槽数不变、不重复；卸下 → 清空
  const inst2 = Object.assign({}, b0.inst);
  inst2["mod_sight_rear/mod_sight_rear"] = AKMP_RS;
  const b2 = build(gid, inst2, true);
  const rear2 = Object.keys(b2.tree.nodes).filter(function (p) { return /sight_rear/.test(p); });
  const cells2 = b2.L.cells.filter(function (c) { return /sight_rear/.test(c.path); });
  ok("r1920_" + name + "_install_akmp_no_dup",
     rear2.length === 2 && cells2.length === 2 && b2.inst["mod_sight_rear/mod_sight_rear"] === AKMP_RS,
     { rear2, cells: cells2.map(function (c) { return c.path + "@r" + c.row + "c" + c.col; }) });
  const s2 = b2.by["mod_sight_rear"], a2 = b2.by["mod_sight_rear/mod_sight_rear"];
  ok("r1920_" + name + "_install_keeps_parallel",
     s2 && a2 && a2.col === s2.col + 1 && a2.row === s2.row, { s2, a2 });

  detail.guns[name] = {
    gunId: gid,
    auto: { sight: sightAuto, akmp: akmpAuto },
    final: { sight: sightFin, akmp: akmpFin },
    leftAllow: (gn ? gn.allow : []).map(function (i) { return (items[i] || {}).n || i; }),
    rightAllow: (kn ? kn.allow : []).map(function (i) { return (items[i] || {}).n || i; }),
    parentOfAkmp: kn ? kn.parent : null,
    parentItem: kn ? (b0.inst[kn.parent] || "") : null,
  };
}

// 数据层：AKM 照门子槽恢复 + 枪身 allow 撤回（两处数据源）
{
  const slot = (items[AKM_SIGHT].slots || []).filter(function (s) { return s.id === AKMP_SUB_ID; })[0];
  ok("r1920_data_akmp_subslot_restored", !!slot && (slot.allow || [])[0] === AKMP_RS, slot);
  for (const gid of Object.keys(GUNS)) {
    const s1 = (items[gid].slots || []).filter(function (s) { return s.sid === "mod_sight_rear"; })[0];
    const s2 = (gunslots[gid].slots || []).filter(function (s) { return s.sid === "mod_sight_rear"; })[0];
    ok("r1920_data_allow_items_" + GUNS[gid], s1 && s1.allow.indexOf(AKMP_RS) < 0);
    ok("r1920_data_allow_gunslots_" + GUNS[gid], s2 && s2.allow.indexOf(AKMP_RS) < 0);
  }
}

// 范围保护：VPO-209 不动（同构子槽仍在原位、不进并列规则）
{
  const b = build("59e6687d86f77411d949b251", null, true);
  ok("r1920_vpo209_pair_predicate_false",
     !api.gwIsAkmpPairSlot({ slots: b.tree, installed: b.inst }, "mod_sight_rear/mod_sight_rear"));
  ok("r1920_vpo209_unchanged_below",
     b.by["mod_sight_rear"] && b.by["mod_sight_rear/mod_sight_rear"] &&
     b.by["mod_sight_rear"].row === 1 && b.by["mod_sight_rear/mod_sight_rear"].row === 2,
     b.by);
}

// 范围保护：5.45/5.56 与 AK-103/AK-104 不受影响
{
  const ak74 = build("5644bd2b4bdc2d3b4c8b4572", null, true);
  ok("r1920_ak74n_single_sight_unchanged",
     Object.keys(ak74.tree.nodes).filter(function (p) { return /sight_rear/.test(p); }).length === 1);
  ok("r1920_ak74n_no_akmp",
     Object.keys(ak74.tree.nodes).every(function (p) {
       return (ak74.tree.nodes[p].allow || []).indexOf(AKMP_RS) < 0;
     }));
  for (const gid of ["5ac66d2e5acfc43b321d4b53", "5ac66d725acfc43b321d4b60"]) {
    const b = build(gid, null, true);
    ok("r1920_ak10x_single_sight_" + gid,
       Object.keys(b.tree.nodes).filter(function (p) { return /sight_rear/.test(p); }).length === 1);
  }
}

// 校准语料完整性
{
  let total = 0, applied = 0, unmatched = 0, fallback = 0;
  for (const gid of Object.keys(calib.guns || {})) {
    const recs = calib.guns[gid].slots || {};
    total += Object.keys(recs).length;
    const b = build(gid, null, true);
    applied += b.info ? b.info.applied : 0;
    unmatched += b.info ? b.info.unmatched.length : 0;
    fallback += b.info ? b.info.fallback.length : 0;
  }
  ok("r1920_calib_total_397", total === 397, total);
  ok("r1920_calib_no_fallback", fallback === 0, fallback);
  // 五把枪的并列记录在位
  for (const gid of Object.keys(GUNS)) {
    const rec = (calib.guns[gid].slots || {})["mod_sight_rear/mod_sight_rear|mod_sight_rear|" + AKM_SIGHT];
    ok("r1920_calib_parallel_record_" + GUNS[gid],
       rec && rec.logicalRow === 1 && rec.col === 7, rec);
  }
  detail.calib = { totalRecords: total, applied, unmatched, fallback };
}

const out = {
  generatedAt: new Date().toISOString().slice(0, 19),
  schema: "r19.20-engine-audit/1",
  checks: checks, detail: detail,
  failed: Object.keys(checks).filter(function (k) {
    return k.indexOf("FAILED_") === 0 && checks[k] !== false;
  }).map(function (k) { return k.slice(7); }),
};
fs.mkdirSync(path.join(ROOT, "docs", "r19.20-akm-akmp-parallel"), { recursive: true });
fs.writeFileSync(path.join(ROOT, "docs", "r19.20-akm-akmp-parallel", "engine-audit.json"),
  JSON.stringify(out, null, 1));
const names = Object.keys(checks).filter(function (k) { return k.indexOf("FAILED_") !== 0; });
console.log("checks:", names.length, "failed:", out.failed.length);
names.forEach(function (n) { if (!checks[n]) { console.log("  FAIL:", n, JSON.stringify(checks["FAILED_" + n])); } });
