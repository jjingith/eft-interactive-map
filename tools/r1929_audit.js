// R19.21 引擎审计：AKMP 真实父子关系 + 正上方布局 + 校准整合（只读）。
// 输出：docs/r19.21-akmp-parent-fix/engine-audit.json
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
  "gwIsAkmpSubSlot:gwIsAkmpSubSlot,gwSlotVisible:gwSlotVisible};")(
  function (id) { return items[id] || null; }, items);
const ctx = GB.context(items, stats);

const AKMP_RS = "5a0ed824fcdbcb0176308b0d";
const PARENTS = {
  "5ac733a45acfc400192630e2": { name: "6P44 Sb.1-30", slotId: "5ac733a45acfc400192630e4" },
  "5ac72e475acfc400180ae6fe": { name: "6P20 Sb.2", slotId: "5ac72e475acfc400180ae700" },
  "5649b0544bdc2d1b2b8b458a": { name: "6P1 Sb.2", slotId: "5a0ee12cfcdbcb001912fa64" },
};
const AKM_SIGHT = "59d650cf86f7741b846413a4";
// 测试 C 清单：枪 → 期望父照门
const CASE_GUNS = {
  "5644bd2b4bdc2d3b4c8b4572": "AK-74N",
  "5bf3e03b0db834001d2c4a9c": "AK-74",
  "5ac66d9b5acfc4001633997a": "AK-105",
  "5ac4cd105acfc40016339859": "AK-74M",
  "5ac66d2e5acfc43b321d4b53": "AK-103",
  "5ac66d725acfc43b321d4b60": "AK-104",
  "5ac66cb05acfc40198510a10": "AK-101",
  "5ac66d015acfc400180ae6e4": "AK-102",
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
  return { inst, tree, L, by, recs, info, topPad: L.topPad };
}

const checks = {};
const detail = {};
function ok(name, cond, extra) {
  checks[name] = !!cond;
  if (!cond) { checks["FAILED_" + name] = extra === undefined ? true : extra; }
}

// ============================================================ A：父照门数据
{
  const rows = [];
  for (const pid of Object.keys(PARENTS)) {
    const it = items[pid] || {};
    const sub = (it.slots || []).filter(function (s) { return s.id === PARENTS[pid].slotId; })[0];
    ok("A_" + PARENTS[pid].name + "_subslot_exists", !!sub);
    ok("A_" + PARENTS[pid].name + "_allow_akmp_only",
       sub && (sub.allow || []).length === 1 && sub.allow[0] === AKMP_RS);
    rows.push({ itemId: pid, name: it.n, pt: it.pt,
                subSlotId: PARENTS[pid].slotId,
                subSid: sub ? sub.sid : null, subAllow: sub ? sub.allow : null });
  }
  // AKM 照门（6P1 Sb.2-1）：错误建模的 AKMP 子槽必须不在
  const akm = items[AKM_SIGHT] || {};
  ok("A_akmsight_no_akmp_subslot",
     !(akm.slots || []).some(function (s) { return (s.allow || [])[0] === AKMP_RS; }));
  // 其他照门不自动获得 AKMP 子槽（抽查 TT01 / AKMB / VPO-209 照门之外的通用照门）
  const leaky = [];
  for (const iid of Object.keys(items)) {
    const it = items[iid];
    if (!it || it.pt === "Weapon") { continue; }
    if (PARENTS[iid] || iid === AKM_SIGHT) { continue; }
    for (const s of (it.slots || [])) {
      if ((s.allow || []).length === 1 && s.allow[0] === AKMP_RS && s.sid === "mod_sight_rear") {
        if (iid !== "59e8977386f77415a553c453") { leaky.push(it.n + "/" + iid); }   // VPO-209照门=已知未决
      }
    }
  }
  ok("A_no_auto_akmp_on_other_sights", leaky.length === 0, leaky);
  detail.A = rows;
}

// ============================================================ B：条件生成
{
  const gid = "5644bd2b4bdc2d3b4c8b4572";   // AK-74N
  const rows = [];
  const scenarios = [
    ["uninstall", null],
    ["install_6P1Sb2", "5649b0544bdc2d1b2b8b458a"],
    ["swap_to_akm_sight_unsupported", AKM_SIGHT],
    ["swap_to_6P44", "5ac733a45acfc400192630e2"],
    ["swap_to_6P20", "5ac72e475acfc400180ae6fe"],
  ];
  const prevSub = {};
  for (const sc of scenarios) {
    const inst = Object.assign({}, defInst(gid));
    if (sc[1]) { inst["mod_sight_rear"] = sc[1]; } else { delete inst["mod_sight_rear"]; }
    const b = build(gid, inst, true);
    const subPath = "mod_sight_rear/mod_sight_rear";
    const hasSub = !!b.tree.nodes[subPath];
    const subCells = b.L.cells.filter(function (c) { return c.path === subPath; });
    rows.push({ scenario: sc[0], sight: sc[1], hasSub, subCellCount: subCells.length });
    ok("B_" + sc[0] + "_sub_presence",
       hasSub === (sc[1] !== null && !!PARENTS[sc[1]]), { hasSub, sight: sc[1] });
    ok("B_" + sc[0] + "_single_sub_cell", subCells.length === (hasSub ? 1 : 0), subCells);
    if (hasSub) {
      const node = b.tree.nodes[subPath];
      ok("B_" + sc[0] + "_parent_is_sight", node.parent === "mod_sight_rear" &&
         b.inst[node.parent] === sc[1]);
      ok("B_" + sc[0] + "_candidate_only_akmp",
         (node.allow || []).length === 1 && node.allow[0] === AKMP_RS);
    }
  }
  // 卸下后无残留
  const bClean = build(gid, Object.assign({}, defInst(gid), {}), true);
  const inst0 = Object.assign({}, defInst(gid));
  delete inst0["mod_sight_rear"];
  const bGone = build(gid, inst0, true);
  ok("B_no_residue_after_uninstall",
     !bGone.tree.nodes["mod_sight_rear/mod_sight_rear"] &&
     !bGone.by["mod_sight_rear/mod_sight_rear"]);
  detail.B = rows;
}

// ============================================================ C：布局（正上方同列）
{
  const rows = [];
  for (const gid of Object.keys(CASE_GUNS)) {
    const name = CASE_GUNS[gid];
    const b0 = build(gid, null, false);   // 自动布局
    const b1 = build(gid, null, true);    // 最终（含校准）
    const sub = "mod_sight_rear/mod_sight_rear";
    const s0 = b0.by["mod_sight_rear"], k0 = b0.by[sub];
    const s1 = b1.by["mod_sight_rear"], k1 = b1.by[sub];
    const parentItem = b1.inst["mod_sight_rear"] || "";
    ok("C_" + name + "_parent_is_confirmed", !!PARENTS[parentItem], parentItem);
    ok("C_" + name + "_auto_above_same_col",
       s0 && k0 && k0.col === s0.col && k0.row === s0.row - 1, { s0, k0 });
    ok("C_" + name + "_final_above_same_col",
       s1 && k1 && k1.col === s1.col && k1.row === s1.row - 1, { s1, k1 });
    rows.push({ gun: name, gunId: gid, parentItem: PARENTS[parentItem] ? PARENTS[parentItem].name : parentItem,
                auto: { sight: s0, sub: k0 }, final: { sight: s1, sub: k1 }, topPad: b1.topPad });
  }
  // AK-103/AK-104 父在 r1 → 子槽 r0 + topPad
  const b103 = build("5ac66d2e5acfc43b321d4b53", null, true);
  ok("C_AK103_top_expansion",
     b103.by["mod_sight_rear"].row === 1 && b103.by["mod_sight_rear/mod_sight_rear"].row === 0
     && b103.topPad === 1, b103.by);
  detail.C = rows;
}

// ============================================================ E：自动布局路径（无校准也正确）
{
  const gid = "5644bd2b4bdc2d3b4c8b4572";
  const inst = defInst(gid);
  const b = build(gid, null, false);
  ok("E_auto_without_records", b.by["mod_sight_rear/mod_sight_rear"] &&
     b.by["mod_sight_rear/mod_sight_rear"].row === b.by["mod_sight_rear"].row - 1 &&
     b.by["mod_sight_rear/mod_sight_rear"].col === b.by["mod_sight_rear"].col);
  ok("E_rule_is_parent_item_based", api.gwIsAkmpSubSlot(
    { slots: b.tree, installed: b.inst }, "mod_sight_rear/mod_sight_rear"));
}

// ============================================================ F + 范围保护
{
  // AKM 系：无 AKMP（错误建模已删），候选不含 AKMP
  for (const gid of ["59d6088586f774275f37482f", "59ff346386f77477562ff5e2",
                     "5a0ec13bfcdbcb00165aa685", "5abcbc27d8ce8700182eceeb",
                     "59e6152586f77473dc057aa1"]) {
    const b = build(gid, null, true);
    const name = gunslots[gid].n.split(" ")[0];
    const rearPaths = Object.keys(b.tree.nodes).filter(function (p) { return /sight_rear/.test(p); });
    ok("F_akm_" + name + "_single_sight_slot", rearPaths.length === 1, rearPaths);
    ok("F_akm_" + name + "_no_akmp_anywhere",
       rearPaths.every(function (p) {
         return (b.tree.nodes[p].allow || []).indexOf(AKMP_RS) < 0;
       }));
    // 用户 R19.21 前调整的照门坐标保持（AKM/AKMS r2c6；AKMN/AKMSN/VPO-136 r1c6）
    ok("F_akm_" + name + "_sight_record_kept",
       !!b.recs["mod_sight_rear|mod_sight_rear|"], b.recs["mod_sight_rear|mod_sight_rear|"]);
  }
  // VPO-209 照样子槽（未决）不动
  const v = build("59e6687d86f77411d949b251", null, true);
  ok("F_vpo209_sub_untouched",
     !!v.tree.nodes["mod_sight_rear/mod_sight_rear"] && v.by["mod_sight_rear"].row === 1
     && v.by["mod_sight_rear/mod_sight_rear"].row === 2, v.by);
  ok("F_vpo209_not_in_rule",
     !api.gwIsAkmpSubSlot({ slots: v.tree, installed: v.inst }, "mod_sight_rear/mod_sight_rear"));
  // R19.18/19/20 回归锚点
  const svds = build("5c46fbd72e2216398b5a8c9c", null, true);
  ok("F_svds_dovetail_r2c7",
     !!svds.by["mod_mount_000"] && svds.by["mod_mount_000"].row === 2 && svds.by["mod_mount_000"].col === 7);
  const sks = build("574d967124597745970e7c94", null, true);
  ok("F_sks_socom_r4c3",
     !!sks.by["mod_barrel/mod_mount_001"] && sks.by["mod_barrel/mod_mount_001"].row === 4
     && sks.by["mod_barrel/mod_mount_001"].col === 3);
  const ak = build("5644bd2b4bdc2d3b4c8b4572", null, true);
  ok("F_gp25_kept", !!ak.by["mod_launcher"], ak.by["mod_launcher"]);
}

// ============================================================ 校准语料
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
  ok("calib_total_397", total === 397, total);
  ok("calib_no_fallback", fallback === 0, fallback);
  // 10 条复活记录 = 父行-1 同列
  let revived = 0;
  for (const gid of Object.keys(CASE_GUNS)) {
    const parentItem = build(gid, null, true).inst["mod_sight_rear"];
    const rec = (calib.guns[gid].slots || {})["mod_sight_rear/mod_sight_rear|mod_sight_rear|" + parentItem];
    const sightRec = (calib.guns[gid].slots || {})["mod_sight_rear|mod_sight_rear|"];
    const parentRow = sightRec ? sightRec.logicalRow : 2, parentCol = sightRec ? sightRec.col : 6;
    ok("calib_revived_" + CASE_GUNS[gid],
       rec && rec.logicalRow === parentRow - 1 && rec.col === parentCol
       && (rec.note || "").indexOf("R19.21") === 0, rec);
    if (rec) { revived++; }
  }
  // 5 条并列时代记录 = 失效注记 + 坐标保留
  let staleMarked = 0;
  for (const gid of ["59d6088586f774275f37482f", "59ff346386f77477562ff5e2",
                     "5a0ec13bfcdbcb00165aa685", "5abcbc27d8ce8700182eceeb",
                     "59e6152586f77473dc057aa1"]) {
    const rec = (calib.guns[gid].slots || {})["mod_sight_rear/mod_sight_rear|mod_sight_rear|" + AKM_SIGHT];
    ok("calib_stale_" + gunslots[gid].n.split(" ")[0],
       rec && (rec.note || "").indexOf("R19.21") === 0 && (rec.note || "").indexOf("不再生效") > 0
       && rec.logicalRow !== undefined, rec);
    if (rec) { staleMarked++; }
  }
  // 案例清单 8 把 + AKS-74/AKS-74N = 迁移共复活 10 条
  for (const gid of ["5bf3e0490db83400196199af", "5ab8e9fcd8ce870019439434"]) {
    const rec = (calib.guns[gid].slots || {})["mod_sight_rear/mod_sight_rear|mod_sight_rear|5649b0544bdc2d1b2b8b458a"];
    const sightRec = (calib.guns[gid].slots || {})["mod_sight_rear|mod_sight_rear|"];
    ok("calib_revived_" + gunslots[gid].n.split(" ")[0],
       rec && sightRec && rec.logicalRow === sightRec.logicalRow - 1 && rec.col === sightRec.col, rec);
    if (rec) { revived++; }
  }
  ok("calib_revived_count_10", revived === 10, revived);
  ok("calib_stale_count_5", staleMarked === 5, staleMarked);
  detail.calib = { totalRecords: total, applied, unmatched, fallback, revived, staleMarked };
}

const out = {
  generatedAt: new Date().toISOString().slice(0, 19),
  schema: "r19.21-engine-audit/1",
  checks: checks, detail: detail,
  failed: Object.keys(checks).filter(function (k) {
    return k.indexOf("FAILED_") === 0 && checks[k] !== false;
  }).map(function (k) { return k.slice(7); }),
};
fs.mkdirSync(path.join(ROOT, "docs", "r19.21-akmp-parent-fix"), { recursive: true });
fs.writeFileSync(path.join(ROOT, "docs", "r19.21-akmp-parent-fix", "engine-audit.json"),
  JSON.stringify(out, null, 1));
const names = Object.keys(checks).filter(function (k) { return k.indexOf("FAILED_") !== 0; });
console.log("checks:", names.length, "failed:", out.failed.length);
names.forEach(function (n) { if (!checks[n]) { console.log("  FAIL:", n, JSON.stringify(checks["FAILED_" + n])); } });
