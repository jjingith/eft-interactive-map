// R19.17 校准接入引擎审计：把 app.js 的 gwBuildLayout / gwApplyCalibToLayout 抠到 node 上，
// 对 data/gun-layout-calibration.json 全量记录做「应用 / 回退」对照，并跑合成用例
// （身份隔离 / 非法坐标 / 本体区 / 争格 / 交换 / 挤位 / topPad 重算 / AMMO 躲让 / noCalib 基线）。
// 产物：docs/r19.17-calibration-integration/engine-apply-audit.json
const fs = require("fs"), path = require("path");
const ROOT = path.resolve(__dirname, "..");
const GB = require(path.join(ROOT, "gun_builder.js"));
const items = JSON.parse(fs.readFileSync(path.join(ROOT, "data/items.json"), "utf8")).items;
const stats = JSON.parse(fs.readFileSync(path.join(ROOT, "data/gun-stats.json"), "utf8"));
const presets = JSON.parse(fs.readFileSync(path.join(ROOT, "data/gun-presets.json"), "utf8")).presets || {};
const calib = JSON.parse(fs.readFileSync(path.join(ROOT, "data/gun-layout-calibration.json"), "utf8"));
const src = fs.readFileSync(path.join(ROOT, "app.js"), "utf8");
const block = src.slice(src.indexOf("function gwSidBase("), src.indexOf("function renderGunSkin("));
const api = new Function("itemRec", "GW_ITEM_MAP", block +
  "\nreturn {gwBuildLayout:gwBuildLayout,gwApplyCalibToLayout:gwApplyCalibToLayout," +
  "gwCalibKey:gwCalibKey,gwCalibRecordsFor:gwCalibRecordsFor,gwSidBase:gwSidBase,gwSlotVisible:gwSlotVisible};")(
  function (id) { return items[id] || null; }, items);
const ctx = GB.context(items, stats);

function defInst(gid) {
  const st = (stats.guns || {})[gid] || {};
  if (st.preset && presets[st.preset]) { return presets[st.preset].i || {}; }
  for (const pid in presets) { const p = presets[pid]; if (p && p.g === gid) { return p.i || {}; } }
  return {};
}
function buildOf(gid, instOverride) {
  const inst0 = instOverride || defInst(gid);
  const s = GB.sanitize(ctx, gid, inst0);
  const tree = GB.buildTree(ctx, gid, s.installed);
  return { installed: s.installed, tree: tree };
}
function autoLayoutOf(gid) {
  const b = buildOf(gid);
  return { b: b, L: api.gwBuildLayout({ gunId: gid, installed: b.installed, slots: b.tree, noCalib: true }) };
}
function keysOf(b) {
  const out = {};   // 槽位路径 -> 身份 key（slotPath|slotId|ownerItemId）
  for (const p of Object.keys(b.tree.nodes)) {
    const n = b.tree.nodes[p];
    out[p] = api.gwCalibKey(p, n, b.installed);
  }
  return out;
}

const checks = {};
const gunsDetail = {};

// ---------------------------------------------------------------- 全量对照
let totalRec = 0, applied = 0, unmatched = 0, fallback = 0, stale = 0, suppressed = 0;
const staleList = [], suppressedList = [];
let exactMatch = 0, mismatched = [];
for (const gid of Object.keys(calib.guns || {})) {
  const recs = (calib.guns[gid].slots || {});
  const nRec = Object.keys(recs).length;
  totalRec += nRec;
  const { b, L } = autoLayoutOf(gid);
  const info = api.gwApplyCalibToLayout(L, { gunId: gid, installed: b.installed, slots: b.tree }, recs);
  applied += info.applied;
  unmatched += info.unmatched.length;
  fallback += info.fallback.length;
  // R19.18：真实条件子槽被修正移除后，旧记录不再有对应槽位 → 归类为「失效记录」
  //（保留在文件里、不生效、不改挂到别的槽位），不算匹配失败。
  info.unmatched.forEach(function (k) {
    const path = (recs[k] && recs[k].slotPath) || k.split("|")[0];
    if (!b.tree.nodes[path]) {
      stale++; staleList.push({ gun: gid, key: k, path: path });
    } else if (!api.gwSlotVisible({ gunId: gid, slots: b.tree, installed: b.installed }, path)) {
      // 槽位还在，但按真实互斥当前不可用（装了 top cover 等）→ 记录保留、卸下后自动恢复
      suppressed++; suppressedList.push({ gun: gid, key: k, path: path });
    } else {
      staleList.push({ gun: gid, key: k, path: path, unexpected: true });
    }
  });
  // 对照：每条已应用记录的落点必须与保存坐标一致（显示行 = 逻辑行 + 重算 topPad）
  const byKey = info.byKey || {};
  let gunExact = 0;
  for (const k of Object.keys(recs)) {
    const got = byKey[k], want = recs[k];
    if (got && got.col === want.col && got.row === want.logicalRow + info.topPad) { gunExact++; }
    else if (got) {
      mismatched.push({ gun: gid, key: k, want: { r: want.logicalRow, c: want.col }, got: got });
    }
  }
  exactMatch += gunExact;
  if (nRec) {
    gunsDetail[gid] = {
      name: (items[gid] || {}).n || gid,
      records: nRec, applied: info.applied,
      unmatched: info.unmatched.length, fallback: info.fallback.length,
      exactMatch: gunExact, topPad: info.topPad,
      ammoRelocated: info.ammoRelocated
    };
  }
}
// R19.18：真实槽位修正后，旧条件子槽的记录变成「失效记录」（保留但不再生效），
// 因此口径是：已应用 + 失效 = 全部记录，且没有任何「匹配不上又还活着」的记录。
checks.corpusAppliedAll = (applied + stale + suppressed === totalRec
  && unmatched === stale + suppressed && fallback === 0);
checks.corpusExactCoords = (exactMatch + stale + suppressed === totalRec && mismatched.length === 0);

// ---------------------------------------------------------------- 合成用例
const AK = "5644bd2b4bdc2d3b4c8b4572";           // AK-74N
function fresh() {
  const a = autoLayoutOf(AK);
  const k = keysOf(a.b);
  const byPath = {};
  a.L.cells.forEach(function (c) { byPath[c.path] = c; });
  return { a: a, k: k, byPath: byPath };
}

// 1) 基线：无校准数据 → 自动布局（探针行为不变）
{
  const f = fresh();
  checks.autoBaseline = f.byPath["mod_mount_000"].row === 2 && f.byPath["mod_mount_000"].col === 8
    && f.a.L.calib === null;
}

// 2) 应用：燕尾槽三条记录落到保存坐标
{
  const f = fresh();
  const recs = (calib.guns[AK].slots || {});
  const info = api.gwApplyCalibToLayout(f.a.L, { gunId: AK, installed: f.a.b.installed, slots: f.a.b.tree }, recs);
  const mount = f.byPath["mod_mount_000"];
  const sr = f.byPath["mod_sight_rear"];
  // R19.18：AK-74 照门的 AKMP 子槽已按真实数据移除 → 该条记录变成失效记录（保留不生效）
  const sr2 = f.byPath["mod_sight_rear/mod_sight_rear"];
  // R19.21：AK-74 照门的 AKMP 子槽已按实测恢复（父件正上方 r1c6），
  // 三条记录（燕尾槽基座 r2c7 / 照门 r2c6 / AKMP 子槽 r1c6）全部生效。
  checks.akApplied = info.applied === 3 && info.unmatched.length === 0
    && mount.row === 2 && mount.col === 7
    && sr.row === 2 && sr.col === 6
    && sr2 && sr2.row === 1 && sr2.col === 6;
}

// 3) 身份隔离：同名槽位不同 ownerItemId 不得串用
{
  const f = fresh();
  const wrongKey = "mod_mount_000|mod_mount_000|5947db3f86f77447880cf76f"; // 假 owner
  const recs = {};
  recs[wrongKey] = { logicalRow: 5, col: 1 };
  const info = api.gwApplyCalibToLayout(f.a.L, { gunId: AK, installed: f.a.b.installed, slots: f.a.b.tree }, recs);
  const mount = f.byPath["mod_mount_000"];
  checks.ownerIsolation = info.applied === 0 && info.unmatched.length === 1
    && mount.row === 2 && mount.col === 8;
}

// 4) 无法匹配（伪造路径）→ 回退自动布局
{
  const f = fresh();
  const recs = { "mod_fake/mod_fake|mod_fake|": { logicalRow: 1, col: 1 } };
  const info = api.gwApplyCalibToLayout(f.a.L, { gunId: AK, installed: f.a.b.installed, slots: f.a.b.tree }, recs);
  checks.unmatchedFallback = info.applied === 0 && info.unmatched.length === 1
    && f.byPath["mod_mount_000"].col === 8;
}

// 5) 非法坐标 → 回退
{
  const f = fresh();
  const recs = {};
  recs[f.k["mod_mount_000"]] = { logicalRow: 99, col: 3 };
  const recs2 = {};
  recs2[f.k["mod_sight_rear"]] = { logicalRow: 2, col: 0 };
  let ok1 = false, ok2 = false;
  {
    const g1 = fresh();
    const i1 = api.gwApplyCalibToLayout(g1.a.L, { gunId: AK, installed: g1.a.b.installed, slots: g1.a.b.tree }, recs);
    ok1 = i1.applied === 0 && i1.fallback.length === 1 && g1.byPath["mod_mount_000"].col === 8;
  }
  {
    const g2 = fresh();
    const i2 = api.gwApplyCalibToLayout(g2.a.L, { gunId: AK, installed: g2.a.b.installed, slots: g2.a.b.tree }, recs2);
    ok2 = i2.applied === 0 && i2.fallback.length === 1 && g2.byPath["mod_sight_rear"].col === 6;
  }
  checks.invalidCoordsFallback = ok1 && ok2;
}

// 6) 枪械本体区（逻辑 r3c6–c8）→ 回退
{
  const f = fresh();
  const recs = {};
  recs[f.k["mod_mount_000"]] = { logicalRow: 3, col: 7 };
  const info = api.gwApplyCalibToLayout(f.a.L, { gunId: AK, installed: f.a.b.installed, slots: f.a.b.tree }, recs);
  checks.bodyReject = info.applied === 0 && info.fallback.length === 1
    && f.byPath["mod_mount_000"].col === 8;
}

// 7) 两记录争同一格 → 先到先得，后到回退
{
  const f = fresh();
  const recs = {};
  recs[f.k["mod_mount_000"]] = { logicalRow: 1, col: 1 };
  recs[f.k["mod_sight_rear"]] = { logicalRow: 1, col: 1 };
  const info = api.gwApplyCalibToLayout(f.a.L, { gunId: AK, installed: f.a.b.installed, slots: f.a.b.tree }, recs);
  const cellsAt = f.a.L.cells.filter(function (c) { return c.row === 1 && c.col === 1; });
  checks.cellConflict = info.applied === 1 && info.fallback.length === 1 && cellsAt.length === 1;
}

// 8) 交换：两条记录互换坐标 → 双双生效
{
  const f = fresh();
  const recs = {};
  recs[f.k["mod_mount_000"]] = { logicalRow: 2, col: 6 };    // 去照门位
  recs[f.k["mod_sight_rear"]] = { logicalRow: 2, col: 8 };   // 去燕尾槽位
  const info = api.gwApplyCalibToLayout(f.a.L, { gunId: AK, installed: f.a.b.installed, slots: f.a.b.tree }, recs);
  checks.swapApplied = info.applied === 2
    && f.byPath["mod_mount_000"].row === 2 && f.byPath["mod_mount_000"].col === 6
    && f.byPath["mod_sight_rear"].row === 2 && f.byPath["mod_sight_rear"].col === 8;
}

// 9) 挤位：校准格优先，被挤开的自动格挪到最近空格（不丢槽位、不重叠）
{
  const f = fresh();
  const recs = {};
  recs[f.k["mod_charge"]] = { logicalRow: 2, col: 6 };       // 占掉照门自动位
  const info = api.gwApplyCalibToLayout(f.a.L, { gunId: AK, installed: f.a.b.installed, slots: f.a.b.tree }, recs);
  const charge = f.byPath["mod_charge"], sr = f.byPath["mod_sight_rear"];
  const seen = {};
  let overlap = false;
  f.a.L.cells.forEach(function (c) {
    const kk = c.row + "|" + c.col;
    if (seen[kk]) { overlap = true; }
    seen[kk] = 1;
  });
  // R19.21：AK-74 照门的 AKMP 子槽恢复后全枪可见槽位数 13 → 14
  checks.displaceKeepsAll = info.applied === 1
    && charge.row === 2 && charge.col === 6
    && !(sr.row === 2 && sr.col === 6)
    && f.a.L.cells.length === 14 && !overlap;
}

// 10) topPad 重算：逻辑行权威，显示行整体平移
{
  const f = fresh();
  const recs = {};
  recs[f.k["mod_sight_rear"]] = { logicalRow: -1, col: 6 };
  const info = api.gwApplyCalibToLayout(f.a.L, { gunId: AK, installed: f.a.b.installed, slots: f.a.b.tree }, recs);
  const sr = f.byPath["mod_sight_rear"];
  checks.topPadRecomputed = info.applied === 1 && info.topPad === 2
    && sr.row === 1 && sr.col === 6                       // 显示行 = -1 + 2
    && f.a.L.rows === 8 && f.a.L.body.row === 5;          // 本体随 topPad 下移
}

// 11) AMMO 合成格被真实槽位占用 → 躲让（Milkor camora 实例）
{
  const M = "6275303a9f372d6ea97f9ec7";   // Milkor M32A1
  const a = autoLayoutOf(M);
  const recs = (calib.guns[M].slots || {});
  const info = api.gwApplyCalibToLayout(a.L, { gunId: M, installed: a.b.installed, slots: a.b.tree }, recs);
  const cam = a.L.cells.filter(function (c) { return c.path === "mod_magazine/camora_000"; })[0];
  checks.ammoDodged = !!(cam && cam.row === 5 && cam.col === 7
    && info.ammoRelocated && !info.ammoRelocated.hidden
    && !(a.L.ammoRow === 5 && a.L.magCol === 7));
}

// 12) role 覆盖生效且 L.roles.topOptic 同步
{
  const f = fresh();
  const recs = {};
  recs[f.k["mod_mount_000"]] = { logicalRow: 2, col: 7, role: "topOptic" };
  const info = api.gwApplyCalibToLayout(f.a.L, { gunId: AK, installed: f.a.b.installed, slots: f.a.b.tree }, recs);
  checks.roleOverride = info.applied === 1
    && f.byPath["mod_mount_000"].role === "topOptic"
    && (f.a.L.roles.topOptic || []).indexOf("mod_mount_000") >= 0;
}

// 13) noCalib 基线：即使注入 GW_CALIB_STATE 也不套用（校准器基线一致性）
//     反向：不带 noCalib 时 gwBuildLayout 自己读全局套用（主程序路径）
{
  const recs = {};
  const f0 = fresh();
  recs[f0.k["mod_mount_000"]] = { logicalRow: 2, col: 7 };
  globalThis.GW_CALIB_STATE = { guns: { [AK]: { slots: recs } } };
  try {
    const b = buildOf(AK);
    const Lauto = api.gwBuildLayout({ gunId: AK, installed: b.installed, slots: b.tree, noCalib: true });
    const m1 = Lauto.cells.filter(function (c) { return c.path === "mod_mount_000"; })[0];
    const Lcal = api.gwBuildLayout({ gunId: AK, installed: b.installed, slots: b.tree });
    const m2 = Lcal.cells.filter(function (c) { return c.path === "mod_mount_000"; })[0];
    checks.noCalibBaseline = m1.col === 8 && Lauto.calib === null;
    checks.engineAutoReadsCalib = !!(m2 && m2.col === 7 && Lcal.calib && Lcal.calib.applied === 1);
  } finally {
    delete globalThis.GW_CALIB_STATE;
  }
}

// 14) 卸下/更换父件后（ownerItemId 变化）→ 旧记录不得套到新 owner 上
{
  // AK-74N 换弹匣：mod_magazine 无记录，构造一条挂在“旧弹匣 owner”下的子槽记录
  const f = fresh();
  const recs = {};
  recs["mod_magazine/camora_000|camora_000|DEADBEEF"] = { logicalRow: 1, col: 1 };
  const info = api.gwApplyCalibToLayout(f.a.L, { gunId: AK, installed: f.a.b.installed, slots: f.a.b.tree }, recs);
  checks.ownerChangeNoCross = info.applied === 0 && info.unmatched.length === 1;
}

// 15) 记录缺失的枪械（未校准枪）→ 原样自动布局
{
  const other = Object.keys(items).filter(function (id) {
    return !calib.guns[id] && (items[id] || {}).n && (items[id].n.indexOf("马林") >= 0);
  })[0] || Object.keys(calib.guns)[0];
  const a = autoLayoutOf(other);
  const info = api.gwApplyCalibToLayout(a.L, { gunId: other, installed: a.b.installed, slots: a.b.tree }, {});
  checks.noRecordsNoChange = info.applied === 0 && Object.keys(info.byKey).length > 0;
}

const out = {
  generatedAt: new Date().toISOString().slice(0, 19),
  schema: "r19.17-engine-apply-audit/1",
  calibrationFile: "data/gun-layout-calibration.json",
  corpus: {
    guns: Object.keys(calib.guns || {}).length,
    totalRecords: totalRec,
    applied, unmatched, fallback, stale, suppressed,
    staleRecords: staleList.slice(0, 40),
    suppressedRecords: suppressedList.slice(0, 40),
    exactCoords: exactMatch,
    mismatched: mismatched.slice(0, 20),
    byGun: gunsDetail
  },
  checks
};

const outDir = path.join(ROOT, "docs", "r19.17-calibration-integration");
fs.mkdirSync(outDir, { recursive: true });
fs.writeFileSync(path.join(outDir, "engine-apply-audit.json"), JSON.stringify(out, null, 2));

const failed = Object.keys(checks).filter(function (k) { return !checks[k]; });
console.log(JSON.stringify({ corpus: { totalRecords: totalRec, applied, unmatched, fallback, exactCoords: exactMatch }, checks, failed }, null, 2));
process.exit(failed.length ? 1 : 0);
