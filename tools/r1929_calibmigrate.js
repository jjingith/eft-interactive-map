// R19.21 校准记录迁移：AKMP 子槽按父照门正上方同列重算 + 并列时代记录标失效。
// 输出：docs/r19.21-akmp-parent-fix/calibration-migration.json
// 原则（任务 5.3）：身份键不变、不串位；旧坐标与变更原因留痕；其余记录一律不动。
const fs = require("fs"), path = require("path");
const ROOT = path.dirname(__dirname);
const GB = require(path.join(ROOT, "gun_builder.js"));
const items = JSON.parse(fs.readFileSync(path.join(ROOT, "data/items.json"), "utf8")).items;
const stats = JSON.parse(fs.readFileSync(path.join(ROOT, "data/gun-stats.json"), "utf8"));
const presets = JSON.parse(fs.readFileSync(path.join(ROOT, "data/gun-presets.json"), "utf8")).presets || {};
const CALIB_PATH = path.join(ROOT, "data", "gun-layout-calibration.json");
const calib = JSON.parse(fs.readFileSync(CALIB_PATH, "utf8"));
const src = fs.readFileSync(path.join(ROOT, "app.js"), "utf8");
const block = src.slice(src.indexOf("function gwSidBase("), src.indexOf("function renderGunSkin("));
const api = new Function("itemRec", "GW_ITEM_MAP", block +
  "\nreturn {gwBuildLayout:gwBuildLayout,gwApplyCalibToLayout:gwApplyCalibToLayout};")(
  function (id) { return items[id] || null; }, items);
const ctx = GB.context(items, stats);

const AKMP_RS = "5a0ed824fcdbcb0176308b0d";
const PARENTS = {
  "5ac733a45acfc400192630e2": "6P44 Sb.1-30（AK-105 照门）",
  "5ac72e475acfc400180ae6fe": "6P20 Sb.2（AK-74M 照门）",
  "5649b0544bdc2d1b2b8b458a": "6P1 Sb.2（AK-74 照门）",
};
const AKM_SIGHT = "59d650cf86f7741b846413a4";   // 6P1 Sb.2-1（并列假设父件）
const SUB_SID = "mod_sight_rear";
const SIGHT_KEY = "mod_sight_rear|mod_sight_rear|";

function defInst(gid) {
  const st = (stats.guns || {})[gid] || {};
  if (st.preset && presets[st.preset]) { return presets[st.preset].i || {}; }
  for (const p in presets) { if (presets[p] && presets[p].g === gid) { return presets[p].i || {}; } }
  return {};
}

const changes = [];
const now = new Date().toISOString().slice(0, 19);
let reviv = 0, stale = 0, skipped = 0;

for (const gid of Object.keys(calib.guns || {})) {
  const gun = calib.guns[gid];
  const recs = gun.slots || {};
  const inst = GB.sanitize(ctx, gid, defInst(gid)).installed;
  const tree = GB.buildTree(ctx, gid, inst);
  const L = api.gwBuildLayout({ gunId: gid, installed: inst, slots: tree, noCalib: true });
  const sightAuto = L.cells.filter(function (c) { return c.path === "mod_sight_rear"; })[0];
  const sightRec = recs[SIGHT_KEY];
  const parentFinal = sightRec
    ? { row: sightRec.logicalRow, col: sightRec.col, source: "record" }
    : (sightAuto ? { row: sightAuto.row - L.topPad, col: sightAuto.col, source: "auto" } : null);

  // ---- 5.3：三个正确父照门的 AKMP 子槽记录 → 按父件最终坐标重算并复活 ----
  for (const owner of Object.keys(PARENTS)) {
    const key = "mod_sight_rear/" + SUB_SID + "|" + SUB_SID + "|" + owner;
    const rec = recs[key];
    if (!rec) { continue; }
    const installedSight = inst["mod_sight_rear"] || "";
    if (installedSight !== owner) {
      // §5.4：当前实际安装的父照门与记录身份不符 → 不恢复、不迁移，报告单列
      skipped++;
      changes.push({ gun: gun.name, gunId: gid, key, status: "parent-mismatch-kept",
                     installedSight, recordOwner: owner });
      continue;
    }
    if (!parentFinal) {
      skipped++;
      changes.push({ gun: gun.name, gunId: gid, key, status: "no-parent-coords" });
      continue;
    }
    const target = { row: parentFinal.row - 1, col: parentFinal.col };
    const old = { logicalRow: rec.logicalRow, col: rec.col, note: (rec.note || "").slice(0, 30) };
    rec.logicalRow = target.row;
    rec.col = target.col;
    rec.displayRow = target.row + (target.row < 1 ? 1 - target.row : 0);
    rec.topPad = target.row < 1 ? 1 - target.row : 0;
    rec.note = ("R19.21：AKMP 子槽按父照门正上方同列重算（原坐标 r" + old.logicalRow + "c" + old.col +
                "，R19.18 失效注记解除）；父=" + PARENTS[owner] + " 最终坐标 r" + parentFinal.row +
                "c" + parentFinal.col + "（" + parentFinal.source + "），子槽=父行-1 同列。");
    rec.updatedAt = now;
    reviv++;
    changes.push({ gun: gun.name, gunId: gid, key, status: "revived-recomputed",
                   owner: PARENTS[owner], before: old,
                   after: { logicalRow: target.row, col: target.col },
                   parentFinal });
  }

  // ---- 5.3 末段：R19.20 并列时代记录（父件=AKM 照门）→ 标失效、保留原坐标、不迁移 ----
  for (const key of Object.keys(recs)) {
    const rec = recs[key];
    if ((rec.ownerItemId || "") !== AKM_SIGHT) { continue; }
    const oldNote = (rec.note || "").slice(0, 30);
    rec.note = ("R19.21：AKM 照门 6P1 Sb.2-1 上的 AKMP 子槽为并列假设的错误建模（已按游戏实测删除；" +
                "AKMP 的真实父照门是 6P1 Sb.2 / 6P20 Sb.2 / 6P44 Sb.1-30）。本条记录保留原坐标 " +
                "r" + rec.logicalRow + "c" + rec.col + " 作历史存档、不再生效，不得迁移到其他槽位。");
    rec.updatedAt = now;
    stale++;
    changes.push({ gun: gun.name, gunId: gid, key, status: "marked-stale-parallel-era",
                   before: { logicalRow: rec.logicalRow, col: rec.col, note: oldNote },
                   coordsPreserved: true });
  }
}

const total = Object.keys(calib.guns || {}).reduce(function (n, gid) {
  return n + Object.keys(calib.guns[gid].slots || {}).length;
}, 0);
calib.updatedAt = calib.updatedAt || now;   // 顶层时间保留用户导出时刻（21:17:53）
fs.writeFileSync(CALIB_PATH, JSON.stringify(calib, null, 1));

const report = {
  schema: "r19.21-calibration-migration/1",
  note: "顶层 updatedAt 保留用户导出时刻；逐条 updatedAt 更新为迁移时刻",
  recordsBefore: total, recordsAfter: total, recordsDeleted: 0,
  revivedRecomputed: reviv, markedStale: stale, skipped,
  changes,
};
fs.mkdirSync(path.join(ROOT, "docs", "r19.21-akmp-parent-fix"), { recursive: true });
fs.writeFileSync(path.join(ROOT, "docs", "r19.21-akmp-parent-fix", "calibration-migration.json"),
  JSON.stringify(report, null, 1));
console.log(JSON.stringify({ recordsBefore: total, recordsAfter: total,
  revivedRecomputed: reviv, markedStale: stale, skipped }));
changes.forEach(function (c) {
  console.log(" ", c.status, "|", (c.gun || "").slice(0, 14), "|", (c.key || "").slice(0, 46),
    c.before ? ("r" + c.before.logicalRow + "c" + c.before.col) : "",
    c.after ? ("-> r" + c.after.logicalRow + "c" + c.after.col) : "");
});
