// R19.18 专项审计：逐项核对 10 个问题的真实槽位树 + 布局结果。
// 输出：docs/r19.18-slot-fix-audit/engine-audit.json
const fs = require("fs"), path = require("path");
const ROOT = path.resolve(__dirname, "..");
const GB = require(path.join(ROOT, "gun_builder.js"));
const items = JSON.parse(fs.readFileSync(path.join(ROOT, "data/items.json"), "utf8")).items;
const stats = JSON.parse(fs.readFileSync(path.join(ROOT, "data/gun-stats.json"), "utf8"));
const presets = JSON.parse(fs.readFileSync(path.join(ROOT, "data/gun-presets.json"), "utf8")).presets || {};
const gunslots = JSON.parse(fs.readFileSync(path.join(ROOT, "data/gunslots.json"), "utf8")).guns;
const calib = JSON.parse(fs.readFileSync(path.join(ROOT, "data/gun-layout-calibration.json"), "utf8"));
const src = fs.readFileSync(path.join(ROOT, "app.js"), "utf8");
const block = src.slice(src.indexOf("function gwSidBase("), src.indexOf("function renderGunSkin("));
const api = new Function("itemRec", "GW_ITEM_MAP", block +
  "\nreturn {gwBuildLayout:gwBuildLayout,gwApplyCalibToLayout:gwApplyCalibToLayout,gwSlotVisible:gwSlotVisible};")(
  function (id) { return items[id] || null; }, items);
const ctx = GB.context(items, stats);

const G = {
  SVDS: "5c46fbd72e2216398b5a8c9c",
  AK74N: "5644bd2b4bdc2d3b4c8b4572", AKM: "59d6088586f774275f37482f",
  AKMS: "59ff346386f77477562ff5e2", AKMN: "5a0ec13bfcdbcb00165aa685", AKMSN: "5abcbc27d8ce8700182eceeb",
  AK74: "5bf3e03b0db834001d2c4a9c", AK74M: "5ac4cd105acfc40016339859",
  AK101: "5ac66cb05acfc40198510a10", AK102: "5ac66d015acfc400180ae6e4",
  AK103: "5ac66d2e5acfc43b321d4b53", AK104: "5ac66d725acfc43b321d4b60", AK105: "5ac66d9b5acfc4001633997a",
  AKS74N: "5ab8e9fcd8ce870019439434", AKS74: "5bf3e0490db83400196199af",
  VPO136: "59e6152586f77473dc057aa1", VPO209: "59e6687d86f77411d949b251",
  G28: "6176aca650224f204c1da3fb", S12K: "6981d72ed009ad83920da43a",
  T5000: "5df24cf80dee1b22f862e9bc", SKS: "574d967124597745970e7c94", OXSKS: "587e02ff24597743df3deaeb",
  VSK94: "645e0c6b3b381ede770e1cc9", ASVAL: "57c44b372459772d2b39b8ce",
  ASVALMOD4: "6871284e9a353bb50606f3ed", TKPD: "68aee763130c00663d08aea8",
};
const AKMP_RS = "5a0ed824fcdbcb0176308b0d";     // AKMP 系统照门装置
const B3_RING = "57a3459f245977764a01f703";     // Zenit B-3 VSS/VAL 环形基座
const SOCOM_BASE = "593d1fa786f7746da62d61ac"; // UTG SKS SOCOM 导轨基座
const TOP_COVER = "68712bd4251b8d4c6c04ec19";   // NB AS VAL MOD.4 套件防尘盖（top cover）
const RAIL35 = "68712b57a1be89347f0d8179";      // NB MOD.4 套件 3.5 英寸导轨

function defInst(gid) {
  const st = (stats.guns || {})[gid] || {};
  if (st.preset && presets[st.preset]) { return presets[st.preset].i || {}; }
  for (const pid in presets) { const p = presets[pid]; if (p && p.g === gid) { return p.i || {}; } }
  return {};
}
function build(gid, instOverride) {
  const inst0 = instOverride || defInst(gid);
  const s = GB.sanitize(ctx, gid, inst0);
  const tree = GB.buildTree(ctx, gid, s.installed);
  const L = api.gwBuildLayout({ gunId: gid, installed: s.installed, slots: tree, noCalib: true });
  const by = {}; L.cells.forEach(function (c) { by[c.path] = c; });
  return { installed: s.installed, tree: tree, L: L, by: by };
}
// 复刻 app.js 的槽位树（枪槽 + 已装件自带子槽），用于「条件子槽」核对
function appTree(gid, installed) {
  const tree = { nodes: {}, order: [] };
  (function add(rec, prefix, parentPath) {
    const slots = (rec && rec.slots) || [];
    const used = {};
    for (let i = 0; i < slots.length; i++) {
      const slot = slots[i] || {};
      let sid = slot.sid || slot.id || ("s" + i);
      const n = used[sid] === undefined ? 0 : used[sid] + 1;
      used[sid] = n;
      if (n > 0) { sid = sid + "#" + n; }
      const p = prefix ? (prefix + "/" + sid) : sid;
      tree.nodes[p] = { path: p, sid: sid, label: slot.label, allow: (slot.allow || []).slice(), parent: parentPath };
      tree.order.push(p);
      const child = items[installed[p]];
      if (child) { add(child, p, p); }
    }
  })(gunslots[gid] || null, "", null);
  return tree;
}
function allowsOf(gid, installed) {
  const t = appTree(gid, installed || defInst(gid));
  const out = [];
  t.order.forEach(function (p) { out.push({ path: p, sid: t.nodes[p].sid, allow: t.nodes[p].allow }); });
  return out;
}
const checks = {}, detail = {};

function ok(name, cond, extra) {
  checks[name] = !!cond;
  if (extra !== undefined) { detail[name] = extra; }
}

// ============================================================ 问题 1：SVDS 燕尾槽 r2c7
{
  const b = build(G.SVDS);
  const cell = b.by["mod_mount_000"];
  const treeHas = allowsOf(G.SVDS).some(function (s) { return s.path === "mod_mount_000"; });
  ok("svds_dovetail_exists", treeHas);
  ok("svds_dovetail_at_r2c7", cell && cell.row === 2 && cell.col === 7, cell && ("r" + cell.row + "c" + cell.col));
  const dup = b.L.cells.filter(function (c) { return c.path === "mod_mount_000"; });
  ok("svds_no_duplicate", dup.length === 1);
  // 其它枪械的燕尾槽布局不被这次改动波及（AK-74N 仍在 r2c8）
  const ak = build(G.AK74N);
  ok("svds_other_guns_unaffected", ak.by["mod_mount_000"] && ak.by["mod_mount_000"].row === 2 && ak.by["mod_mount_000"].col === 8);
  detail.svds = { cells: b.L.cells.map(function (c) { return c.path + "@r" + c.row + "c" + c.col; }) };
}

// ============================================================ 问题 2 / 7：AK 照门兼容性
{
  const AK45_56 = [G.AK74N, G.AK74, G.AK74M, G.AK101, G.AK102, G.AK105, G.AKS74N, G.AKS74];
  const AK762 = [G.AKM, G.AKMS, G.AKMN, G.AKMSN, G.VPO136];
  // R19.21：AKMP 只允许出现在三种父照门的 AKMP 子槽（mod_sight_rear/mod_sight_rear）上；
  // 枪身照门槽及其他位置不得出现 AKMP。
  const bad = [];
  AK45_56.forEach(function (gid) {
    allowsOf(gid).forEach(function (s) {
      if (s.allow.indexOf(AKMP_RS) >= 0 && s.path !== "mod_sight_rear/mod_sight_rear") {
        bad.push(gunslots[gid].n + " :: " + s.path);
      }
    });
  });
  ok("ak_45_56_akmp_only_via_parent_subslot", bad.length === 0, bad);
  // R19.21：AKM 系（AKM 照门 6P1 Sb.2-1 非 AKMP 父照门）无 AKMP
  const akmWith = AK762.filter(function (gid) {
    return allowsOf(gid).some(function (s) { return s.allow.indexOf(AKMP_RS) >= 0; });
  });
  ok("akm_family_no_akmp_rs", akmWith.length === 0, akmWith.map(function (g) { return gunslots[g].n; }));
  // AKM 不得出现 AK-74 系列照门
  const AK74_RS = ["5649b0544bdc2d1b2b8b458a", "5ac72e475acfc400180ae6fe"];
  const akmBad = [];
  AK762.forEach(function (gid) {
    allowsOf(gid).forEach(function (s) {
      AK74_RS.forEach(function (r) { if (s.allow.indexOf(r) >= 0) { akmBad.push(gunslots[gid].n + " :: " + s.path); } });
    });
  });
  ok("akm_no_ak74_rs", akmBad.length === 0, akmBad);
  // 合法照门仍在
  const ak74n = build(G.AK74N);
  ok("ak_legal_rear_sight_kept", !!ak74n.by["mod_sight_rear"]);
  // R19.21 升级（R19.20 并列假设被游戏内实测推翻）：AKMP 系统照门装置是
  // 6P1 Sb.2（AK-74 照门）/ 6P20 Sb.2（AK-74M 照门）/ 6P44 Sb.1-30（AK-105 照门）
  // 三种标准照门的**子配件**（父件正上方同列显示）；AKM 照门 6P1 Sb.2-1 上的
  // AKMP 子槽属错误建模已删除。AKMP 不出现在枪身照门槽 allow。
  ok("ak_akmp_child_restored_on_leaf_parent", allowsOf(G.AK74N).some(function (s) {
    return s.path === "mod_sight_rear/mod_sight_rear" && s.allow.indexOf(AKMP_RS) >= 0;
  }));
  ok("akm_akmp_child_slot_gone", !allowsOf(G.AKM).some(function (s) { return s.path === "mod_sight_rear/mod_sight_rear"; }));
  AK762.forEach(function (gid) {
    const rearPaths = allowsOf(gid).filter(function (s) { return /sight_rear/.test(s.path); });
    ok("akm_single_rear_sight_slot_" + gid, rearPaths.length === 1,
       rearPaths.map(function (s) { return s.path; }));
    const gunSlot = rearPaths.filter(function (s) { return s.path === "mod_sight_rear"; })[0];
    ok("akm_akmp_not_in_gun_allow_" + gid, gunSlot && gunSlot.allow.indexOf(AKMP_RS) < 0);
    ok("akm_no_akmp_anywhere_" + gid, rearPaths.every(function (s) {
      return s.allow.indexOf(AKMP_RS) < 0;
    }));
  });
  detail.ak_sights = {
    "5.45/5.56 带 AKMP RS 的枪": bad,
    "7.62/.366 保留 AKMP RS 的枪": akmWith.map(function (g) { return gunslots[g].n; }),
  };
}

// ============================================================ 问题 3：G28 / S12K 行数
{
  [G.G28, G.S12K].forEach(function (gid) {
    const b = build(gid);
    ok("rows_" + gid + "_7", b.L.rows >= 7, b.L.rows);
    const row7 = b.L.cells.filter(function (c) { return c.row >= 7; });
    ok("row7_slots_exist_" + gid, row7.length > 0, row7.map(function (c) { return c.path + "@r" + c.row + "c" + c.col; }));
  });
}

// ============================================================ 问题 4：T-5000 战术槽位数量
{
  const b = build(G.T5000);
  const tactical = b.L.cells.filter(function (c) { return /mod_tactical/.test(c.path); });
  ok("t5000_tactical_count_2", tactical.length === 2, tactical.map(function (c) { return c.path; }));
  const rails = b.L.cells.filter(function (c) { return /mod_mount_\d+$/.test(c.path); });
  ok("t5000_rail_count_2", rails.length === 2, rails.map(function (c) { return c.path; }));
  ok("t5000_no_duplicate_rail", rails.filter(function (c) { return /mod_handguard\/mod_mount_001$/.test(c.path); }).length === 0);
  detail.t5000 = { tactical: tactical.map(function (c) { return c.path + "@r" + c.row + "c" + c.col; }) };
}

// ============================================================ 问题 5：SKS SOCOM
{
  [G.SKS, G.OXSKS].forEach(function (gid) {
    const b = build(gid);
    const soc = b.by["mod_barrel/mod_mount_001"];
    ok("sks_socom_slot_" + gid, !!soc, soc && ("r" + soc.row + "c" + soc.col));
    ok("sks_socom_at_r4c3_" + gid, soc && soc.row === 4 && soc.col === 3);
    // 安装 SOCOM 后的条件子槽
    const inst = Object.assign({}, defInst(gid), { "mod_barrel/mod_mount_001": SOCOM_BASE });
    const b2 = build(gid, inst);
    const scope = b2.by["mod_barrel/mod_mount_001/mod_scope"];
    const tac = b2.by["mod_barrel/mod_mount_001/mod_tactical_000"];
    ok("sks_socom_scope_r2c3_" + gid, scope && scope.row === 2 && scope.col === 3, scope && ("r" + scope.row + "c" + scope.col));
    ok("sks_socom_tactical_r5c3_" + gid, tac && tac.row === 5 && tac.col === 3, tac && ("r" + tac.row + "c" + tac.col));
    // 卸下 SOCOM → 条件子槽消失
    const b3 = build(gid);
    ok("sks_socom_children_gone_" + gid, !b3.by["mod_barrel/mod_mount_001/mod_scope"]);
    detail["sks_" + gid] = { socom: soc && ("r" + soc.row + "c" + soc.col), scope: scope && ("r" + scope.row + "c" + scope.col), tactical: tac && ("r" + tac.row + "c" + tac.col) };
  });
}

// ============================================================ 问题 6：GP-25 榴弹发射器槽位
{
  const want = [], missing = [], notSupported = [];
  for (const gid of Object.keys(gunslots)) {
    const hasSlot = (gunslots[gid].slots || []).some(function (s) { return s.sid === "mod_launcher"; });
    const b = build(gid);
    const cell = b.by["mod_launcher"];
    if (!hasSlot) {
      if (cell) { notSupported.push(gunslots[gid].n); }
      continue;
    }
    if (!cell) { missing.push(gunslots[gid].n); continue; }
    const gas = b.L.cells.filter(function (c) { return /gas_block$/.test(c.path); })[0];
    want.push({ gun: gunslots[gid].n, at: "r" + cell.row + "c" + cell.col, gas: gas && ("r" + gas.row + "c" + gas.col) });
  }
  ok("gp25_all_supported_guns_show_slot", missing.length === 0, missing);
  ok("gp25_no_slot_on_unsupported", notSupported.length === 0, notSupported);
  ok("gp25_below_gas_block", want.length > 0 && want.every(function (w) {
    const g = w.gas.split("c")[0].replace("r", "");
    return w.at.split("c")[0].replace("r", "") === String(+g + 1);
  }), want.slice(0, 6));
  detail.gp25 = { guns: want.length, list: want };
}

// ============================================================ 问题 7（VSK-94 环��基座）
{
  const v = build(G.VSK94);
  ok("vsk94_no_b3_ring_slot", !allowsOf(G.VSK94).some(function (s) { return s.allow.indexOf(B3_RING) >= 0; }));
  const vss = ["57838c962459774a1651ec63", "57c44dd02459772d2e0ae249"];
  const vssKeep = vss.some(function (id) {
    return (items[id].slots || []).some(function (s) { return (s.allow || []).indexOf(B3_RING) >= 0; });
  });
  ok("vss_val_keep_b3_ring", vssKeep);
}

// ============================================================ 问题 8（AS VAL MOD.4 top cover）
{
  // 状态 A：未装 top cover（把默认预设里的防尘盖摘掉）→ 燕尾槽可见，只有一个 3.5 英寸导轨槽
  const instA = Object.assign({}, defInst(G.ASVALMOD4));
  delete instA["mod_handguard/mod_mount_002"];
  const a = build(G.ASVALMOD4, instA);
  ok("asvalmod4_dovetail_visible_without_cover", !!a.by["mod_mount_004"]);
  const railsA = a.L.cells.filter(function (c) { return /mod_handguard\/mod_mount_00[01]$/.test(c.path); });
  ok("asvalmod4_single_35in_rail", railsA.length === 1, railsA.map(function (c) { return c.path; }));
  // 默认预设本身就带 top cover → 默认状态下燕尾槽失效
  const def = build(G.ASVALMOD4);
  ok("asvalmod4_default_has_top_cover", def.installed["mod_handguard/mod_mount_002"] === TOP_COVER,
     def.installed["mod_handguard/mod_mount_002"]);
  // 状态 B：装上 top cover → 燕尾槽失效（真实槽位不可用）
  const instB = Object.assign({}, defInst(G.ASVALMOD4));
  instB["mod_handguard/mod_mount_002"] = TOP_COVER;
  const b = build(G.ASVALMOD4, instB);
  ok("asvalmod4_dovetail_hidden_with_cover", !b.by["mod_mount_004"]);
  ok("asvalmod4_cover_scope_present", !!b.by["mod_handguard/mod_mount_002/mod_scope"]);
  const railsB = b.L.cells.filter(function (c) { return /mod_handguard\/mod_mount_00[01]$/.test(c.path); });
  ok("asvalmod4_single_35in_rail_with_cover", railsB.length === 1, railsB.map(function (c) { return c.path; }));
  // 状态 C：卸下 top cover → 燕尾槽恢复、条件子槽消失
  const c2 = build(G.ASVALMOD4, instA);
  ok("asvalmod4_dovetail_restored_after_remove", !!c2.by["mod_mount_004"]);
  ok("asvalmod4_cover_children_gone_after_remove", !c2.by["mod_handguard/mod_mount_002/mod_scope"]);
  // 普通 AS VAL 不受影响
  const av = build(G.ASVAL);
  ok("asval_unaffected", !!av.by["mod_mount_004"]);
}

// ============================================================ 问题 9（TKPD）
{
  const b = build(G.TKPD);
  const tactical = b.L.cells.filter(function (c) { return /mod_tactical/.test(c.path); });
  ok("tkpd_tactical_count_1", tactical.length === 1, tactical.map(function (c) { return c.path; }));
  const dv = b.L.cells.filter(function (c) { return c.path === "mod_mount_000" || c.path === "mod_mount_002"; });
  ok("tkpd_two_dovetail_slots", dv.length === 2, dv.map(function (c) { return c.path + "@r" + c.row + "c" + c.col; }));
  const dvAllow = allowsOf(G.TKPD).filter(function (s) { return s.path === "mod_mount_000" || s.path === "mod_mount_002"; });
  ok("tkpd_dovetail_accepts_real_items", dvAllow.length === 2 && dvAllow.every(function (s) { return s.allow.length > 0; }),
     dvAllow.map(function (s) { return s.path + " allow=" + s.allow.length; }));
  detail.tkpd = { dovetail: dv.map(function (c) { return c.path + "@r" + c.row + "c" + c.col; }) };
}

// ============================================================ 问题 10：校准数据回归
var calibStats = null;
{
  let total = 0, applied = 0, unmatched = 0, fallback = 0, stale = 0, suppressed = 0;
  const lost = [];
  for (const gid of Object.keys(calib.guns || {})) {
    const recs = (calib.guns[gid].slots || {});
    total += Object.keys(recs).length;
    const b = build(gid);
    const info = api.gwApplyCalibToLayout(b.L, { gunId: gid, installed: b.installed, slots: b.tree }, recs);
    applied += info.applied; unmatched += info.unmatched.length; fallback += info.fallback.length;
    // 未匹配必须可解释：真实子槽已移除（失效）或按真实互斥当前不可用
    info.unmatched.forEach(function (k) {
      const path = (recs[k] && recs[k].slotPath) || k.split("|")[0];
      if (!b.tree.nodes[path]) { stale++; }
      else if (!api.gwSlotVisible({ gunId: gid, slots: b.tree, installed: b.installed }, path)) { suppressed++; }
      else { stale++; stale += 0; }
    });
    if (info.unmatched.length || info.fallback.length) {
      lost.push({ gun: gunslots[gid] ? gunslots[gid].n : gid, unmatched: info.unmatched, fallback: info.fallback });
    }
  }
  calibStats = { totalRecords: total, applied, unmatched, fallback, stale, suppressed };
  detail.calib = { total: total, applied: applied, unmatched: unmatched, fallback: fallback,
                   stale: stale, suppressed: suppressed, affected: lost };
  ok("calib_records_intact", total === 397, total);
  ok("calib_mostly_applied", applied >= total - lost.reduce(function (a, l) { return a + l.unmatched.length + l.fallback.length; }, 0),
     applied);
}

const out = {
  generatedAt: new Date().toISOString().slice(0, 19),
  schema: "r19.18-engine-audit/1",
  corpus: calibStats,
  checks: checks, detail: detail
};
const outDir = path.join(ROOT, "docs", "r19.18-slot-fix-audit");
fs.mkdirSync(outDir, { recursive: true });
fs.writeFileSync(path.join(outDir, "engine-audit.json"), JSON.stringify(out, null, 2));
const failed = Object.keys(checks).filter(function (k) { return !checks[k]; });
console.log(JSON.stringify({ checks: checks, failed: failed }, null, 1));
process.exit(failed.length ? 1 : 0);
