// R19.19 专项引擎审计（任务 A：AK 照门槽位修复）—— 只读，不写正式数据。
// 输出：docs/r19.19-ak-rear-sight/engine-audit.json
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
  "gwCalibKey:gwCalibKey,gwSlotVisible:gwSlotVisible};")(
  function (id) { return items[id] || null; }, items);
const ctx = GB.context(items, stats);

const AKMP_RS = "5a0ed824fcdbcb0176308b0d";
const A1_GUNS = {
  "5ac66d9b5acfc4001633997a": "AK-105",
  "5bf3e03b0db834001d2c4a9c": "AK-74",
  "5644bd2b4bdc2d3b4c8b4572": "AK-74N",
  "5bf3e0490db83400196199af": "AKS-74",
  "5ab8e9fcd8ce870019439434": "AKS-74N",
};
const A2_GUNS = {
  "59d6088586f774275f37482f": "AKM",
  "59ff346386f77477562ff5e2": "AKMS",
  "5a0ec13bfcdbcb00165aa685": "AKMN",
  "5abcbc27d8ce8700182eceeb": "AKMSN",
  "59e6152586f77473dc057aa1": "VPO-136",
};
const CHECK_GUNS = Object.assign({}, A1_GUNS, A2_GUNS, {
  "5ac66d2e5acfc43b321d4b53": "AK-103",
  "5ac66d725acfc43b321d4b60": "AK-104",
  "5ac4cd105acfc40016339859": "AK-74M",
  "59e6687d86f77411d949b251": "VPO-209",
});

function defInst(gid) {
  const st = (stats.guns || {})[gid] || {};
  if (st.preset && presets[st.preset]) { return presets[st.preset].i || {}; }
  for (const p in presets) { if (presets[p] && presets[p].g === gid) { return presets[p].i || {}; } }
  return {};
}
function build(gid, instOverride) {
  const inst = GB.sanitize(ctx, gid, instOverride || defInst(gid)).installed;
  const tree = GB.buildTree(ctx, gid, inst);
  const L = api.gwBuildLayout({ gunId: gid, installed: inst, slots: tree, noCalib: true });
  const recs = (calib.guns[gid] || {}).slots || {};
  const info = api.gwApplyCalibToLayout(L, { gunId: gid, installed: inst, slots: tree }, recs);
  const by = {};
  L.cells.forEach(function (c) { by[c.path] = { row: c.row - L.topPad, col: c.col, path: c.path }; });
  return { inst, tree, L, info, by, recs };
}
function rearSlots(b) {
  return Object.keys(b.tree.nodes).filter(function (p) { return /sight_rear/.test(p); });
}

const checks = {};
const detail = {};
function ok(name, cond, extra) {
  checks[name] = !!cond;
  if (!cond) { checks["FAILED_" + name] = extra === undefined ? true : extra; }
}

// ============================================================ A1：五把枪照门下移一格
const a1rows = [];
for (const gid of Object.keys(A1_GUNS)) {
  const b = build(gid);
  const cell = b.by["mod_sight_rear"];
  const rec = b.recs["mod_sight_rear|mod_sight_rear|"];
  const rear = rearSlots(b);
  a1rows.push({
    gun: A1_GUNS[gid], gunId: gid,
    slotCount: rear.length,
    final: cell ? "r" + cell.row + "c" + cell.col : null,
    calibRecord: rec ? { logicalRow: rec.logicalRow, col: rec.col, note: (rec.note || "").slice(0, 24) } : null,
    autoWouldBe: (function () {
      const inst = GB.sanitize(ctx, gid, defInst(gid)).installed;
      const tree = GB.buildTree(ctx, gid, inst);
      const L0 = api.gwBuildLayout({ gunId: gid, installed: inst, slots: tree, noCalib: true });
      const c0 = L0.cells.filter(function (c) { return c.path === "mod_sight_rear"; })[0];
      return c0 ? "r" + (c0.row - L0.topPad) + "c" + c0.col : null;
    })(),
  });
  ok("a1_" + A1_GUNS[gid] + "_at_r2c6", cell && cell.row === 2 && cell.col === 6, cell);
  // R19.21 升级：AKMP 子槽按实测恢复（AK-74 照门的子配件，父件正上方 r1c6）
  ok("a1_" + A1_GUNS[gid] + "_sight_and_akmp_sub", rear.length === 2, rear);
  ok("a1_" + A1_GUNS[gid] + "_sub_above_parent",
     b.by["mod_sight_rear/mod_sight_rear"] && b.by["mod_sight_rear"] &&
     b.by["mod_sight_rear/mod_sight_rear"].row === b.by["mod_sight_rear"].row - 1 &&
     b.by["mod_sight_rear/mod_sight_rear"].col === b.by["mod_sight_rear"].col,
     b.by);
  ok("a1_" + A1_GUNS[gid] + "_legal_candidates_kept",
     b.tree.nodes["mod_sight_rear"] &&
     b.tree.nodes["mod_sight_rear"].allow.indexOf("5649b0544bdc2d1b2b8b458a") >= 0);
}
detail.a1 = a1rows;

// 其他 AK 不受 A1 影响：AK-103/AK-104/AKM 系记录保持原坐标（r1c6）
// R19.21 口径：A1 之外的照门记录保持现状（AKM/AKMS 为用户 21:17 调整的 r2c6；
// AK-103/AK-104/VPO-136 仍在 r1c6）——R19.19/20/21 均未改动这些坐标。
const othersUnchanged = [];
const OTHERS_EXPECT = {
  "5ac66d2e5acfc43b321d4b53": [1, 6], "5ac66d725acfc43b321d4b60": [1, 6],
  "59d6088586f774275f37482f": [2, 6], "59e6152586f77473dc057aa1": [1, 6],
};
for (const gid of Object.keys(OTHERS_EXPECT)) {
  const rec = ((calib.guns[gid] || {}).slots || {})["mod_sight_rear|mod_sight_rear|"];
  const b = build(gid);
  const cell = b.by["mod_sight_rear"];
  othersUnchanged.push({ gun: CHECK_GUNS[gid], final: cell ? "r" + cell.row + "c" + cell.col : null,
                         rec: rec ? "r" + rec.logicalRow + "c" + rec.col : null });
  ok("a1_others_untouched_" + gid,
     rec && rec.logicalRow === OTHERS_EXPECT[gid][0] && rec.col === OTHERS_EXPECT[gid][1]
     && cell && cell.row === rec.logicalRow && cell.col === rec.col, { rec, cell });
}
detail.a1Others = othersUnchanged;

// ============================================ A2：AKM 照门 / AKMP 并列双照门位（R19.20）
const a2rows = [];
for (const gid of Object.keys(A2_GUNS)) {
  const b = build(gid);
  const rear = rearSlots(b);
  const node = b.tree.nodes["mod_sight_rear"];
  const allowNames = (node ? node.allow : []).map(function (i) { return (items[i] || {}).n || i; });
  a2rows.push({
    gun: A2_GUNS[gid], gunId: gid,
    slotCount: rear.length, slots: rear,
    allow: allowNames,
    akmpInGunSlot: !!(node && node.allow.indexOf(AKMP_RS) >= 0),
  });
  // R19.21 口径（推翻 R19.20 并列假设）：AKM 照门 6P1 Sb.2-1 不是 AKMP 的父照门——
  // AKM 系只有一个照门槽（枪身），AKMP 子槽/allow 均不存在。
  ok("a2_" + A2_GUNS[gid] + "_single_sight_slot", rear.length === 1, rear);
  ok("a2_" + A2_GUNS[gid] + "_no_akmp_sub",
     rear.indexOf("mod_sight_rear/mod_sight_rear") < 0);
  ok("a2_" + A2_GUNS[gid] + "_akmp_not_in_gun_allow",
     !!(node && node.allow.indexOf(AKMP_RS) < 0));
  ok("a2_" + A2_GUNS[gid] + "_legal_kept",
     !!(node && node.allow.indexOf("59d650cf86f7741b846413a4") >= 0 &&   // AKM 照门
        node.allow.indexOf("5a0eb980fcdbcb001a3b00a6") >= 0 &&           // AKMB
        node.allow.indexOf("5649d9a14bdc2d79388b4580") >= 0));          // TT01
  // 装 AKM 照门后也不得生出 AKMP 子槽（错误建模已删）
  const inst2 = Object.assign({}, b.inst);
  inst2["mod_sight_rear"] = "59d650cf86f7741b846413a4";
  const b2 = build(gid, inst2);
  const rear2 = rearSlots(b2);
  ok("a2_" + A2_GUNS[gid] + "_no_dup_after_install", rear2.length === 1, rear2);
}
detail.a2 = a2rows;

// R19.21：AK-103/AK-104/AK-74M 装 AK-74M/AK-105 照门（三种父照门）→ 照门 + AKMP 子槽
for (const gid of ["5ac66d2e5acfc43b321d4b53", "5ac66d725acfc43b321d4b60", "5ac4cd105acfc40016339859"]) {
  const b = build(gid);
  ok("a2_" + CHECK_GUNS[gid] + "_sight_plus_akmp_sub", rearSlots(b).length === 2, rearSlots(b));
  const s = b.by["mod_sight_rear"], k = b.by["mod_sight_rear/mod_sight_rear"];
  ok("a2_" + CHECK_GUNS[gid] + "_sub_above_parent",
     s && k && k.col === s.col && k.row === s.row - 1, { s, k });
}

// ============================================================ A3：回归保护
// 1) R19.21：AKMP 只经三种父照门的子槽出现（5.45/5.56 装这三种照门→有 AKMP 子槽）
const AK45_56 = ["5644bd2b4bdc2d3b4c8b4572", "5bf3e03b0db834001d2c4a9c", "5ac4cd105acfc40016339859",
                 "5ac66d9b5acfc4001633997a", "5ab8e9fcd8ce870019439434", "5bf3e0490db83400196199af"];
const bad45 = [];
AK45_56.forEach(function (gid) {
  const b = build(gid);
  Object.keys(b.tree.nodes).forEach(function (p) {
    if ((b.tree.nodes[p].allow || []).indexOf(AKMP_RS) >= 0 && p !== "mod_sight_rear/mod_sight_rear") {
      bad45.push(CHECK_GUNS[gid] || gid + "::" + p);
    }
  });
});
ok("a3_akmp_only_via_parent_subslot", bad45.length === 0, bad45);

// 2) R19.21：AKM 系（AKM 照门 6P1 Sb.2-1）无 AKMP（错误建模已删）
const akmClean = Object.keys(A2_GUNS).every(function (gid) {
  const b = build(gid);
  return Object.keys(b.tree.nodes).every(function (p) {
    return (b.tree.nodes[p].allow || []).indexOf(AKMP_RS) < 0;
  });
});
ok("a3_akm_family_no_akmp", akmClean);

// 3) AKM 系不出现 AK-74 系列照门
const AK74_RS = ["5649b0544bdc2d1b2b8b458a", "5ac72e475acfc400180ae6fe"];
const akm74 = [];
Object.keys(A2_GUNS).forEach(function (gid) {
  const b = build(gid);
  Object.keys(b.tree.nodes).forEach(function (p) {
    AK74_RS.forEach(function (r) {
      if ((b.tree.nodes[p].allow || []).indexOf(r) >= 0) { akm74.push(gid + "::" + p); }
    });
  });
});
ok("a3_akm_no_ak74_rs", akm74.length === 0, akm74);

// 4) R19.18 能力不回归：GP-25 / 燕尾槽 / SVDS r2c7 / SKS SOCOM
{
  const ak = build("5644bd2b4bdc2d3b4c8b4572");
  ok("a3_gp25_still_at_gas_below",
     !!ak.by["mod_launcher"] && ak.by["mod_launcher"].col === 3 && ak.by["mod_launcher"].row === 4,
     ak.by["mod_launcher"]);
  const svds = build("5c46fbd72e2216398b5a8c9c");
  ok("a3_svds_dovetail_r2c7",
     !!svds.by["mod_mount_000"] && svds.by["mod_mount_000"].row === 2 && svds.by["mod_mount_000"].col === 7,
     svds.by["mod_mount_000"]);
  const sks = build("574d967124597745970e7c94");
  ok("a3_sks_socom_r4c3",
     !!sks.by["mod_barrel/mod_mount_001"] && sks.by["mod_barrel/mod_mount_001"].row === 4
     && sks.by["mod_barrel/mod_mount_001"].col === 3, sks.by["mod_barrel/mod_mount_001"]);
}

// 5) 校准语料：总数不变、照门记录去向明确
{
  let total = 0, applied = 0, unmatched = 0, fallback = 0, stale = 0, suppressed = 0;
  for (const gid of Object.keys(calib.guns || {})) {
    const recs = (calib.guns[gid].slots || {});
    total += Object.keys(recs).length;
    const b = build(gid);
    const info = api.gwApplyCalibToLayout(b.L, { gunId: gid, installed: b.inst, slots: b.tree }, recs);
    applied += info.applied; unmatched += info.unmatched.length; fallback += info.fallback.length;
    info.unmatched.forEach(function (k) {
      const pathK = (recs[k] && recs[k].slotPath) || k.split("|")[0];
      if (!b.tree.nodes[pathK]) { stale++; }
      else if (!api.gwSlotVisible({ gunId: gid, slots: b.tree, installed: b.inst }, pathK)) { suppressed++; }
      else { stale++; }
    });
  }
  ok("a3_calib_total_unchanged", total === 397, total);
  ok("a3_calib_no_silent_loss", applied + stale + suppressed === total, { applied, stale, suppressed, total });
  ok("a3_calib_no_fallback", fallback === 0, fallback);
  detail.calib = { totalRecords: total, applied, unmatched, fallback, stale, suppressed };
}

const out = {
  generatedAt: new Date().toISOString().slice(0, 19),
  schema: "r19.19-engine-audit/1",
  checks: checks, detail: detail,
  failed: Object.keys(checks).filter(function (k) { return k.indexOf("FAILED_") === 0 && checks[k] !== false; })
    .map(function (k) { return k.slice(7); }),
};
fs.mkdirSync(path.join(ROOT, "docs", "r19.19-ak-rear-sight"), { recursive: true });
fs.writeFileSync(path.join(ROOT, "docs", "r19.19-ak-rear-sight", "engine-audit.json"),
  JSON.stringify(out, null, 1));
const names = Object.keys(checks).filter(function (k) { return k.indexOf("FAILED_") !== 0; });
console.log("checks:", names.length, "failed:", out.failed.length);
names.forEach(function (n) { if (!checks[n]) { console.log("  FAIL:", n, JSON.stringify(checks["FAILED_" + n])); } });
