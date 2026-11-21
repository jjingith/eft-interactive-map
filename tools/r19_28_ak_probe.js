// R19.28 探针：校验「需求一」——AKM/AK-74/AK-100 系（按真实槽位树结构判定，不看枪名）
// 的照门必须落在 r2c6。判定逻辑与 app.js 内 gwIsAkRearSightGun 逐字一致。
// 输出末尾打印 `CHECK_REQ1: PASS (x/y)` 或 `CHECK_REQ1: FAIL`，供 pytest 解析。
const fs = require("fs");
const path = require("path");
const ROOT = path.resolve(__dirname, "..");
const GB = require(path.join(ROOT, "gun_builder.js"));

const items = JSON.parse(fs.readFileSync(path.join(ROOT, "data/items.json"), "utf8")).items;
const stats = JSON.parse(fs.readFileSync(path.join(ROOT, "data/gun-stats.json"), "utf8"));
const presets = JSON.parse(fs.readFileSync(path.join(ROOT, "data/gun-presets.json"), "utf8")).presets || {};

const src = fs.readFileSync(path.join(ROOT, "app.js"), "utf8");
const block = src.slice(src.indexOf("function gwSidBase("), src.indexOf("function renderGunSkin("));
const api = new Function("itemRec", "GW_ITEM_MAP",
  block + "\nreturn {gwBuildLayout:gwBuildLayout, gwSidBase:gwSidBase};")(
  function (id) { return items[id] || null; }, items
);

// 与 app.js 一致的 AK 标准照门 id（结构签名，不按枪名）
const GW_AK_REAR_SIGHT_IDS = {
  "59d650cf86f7741b846413a4": 1, "5a0eb980fcdbcb001a3b00a6": 1, "5649b0544bdc2d1b2b8b458a": 1,
  "5ac72e475acfc400180ae6fe": 1, "5ac733a45acfc400192630e2": 1, "5bf3f59f0db834001a6fa060": 1,
  "649ec2cec93611967b03495e": 1, "628a7b23b0f75035732dd565": 1
};
function gwSidBase(sid) { return String(sid || "").replace(/^mod_/, "").replace(/#\d+$/, "").replace(/_\d{3,}$/, ""); }
function isAkRearSightGun(g) {
  const nodes = (g && g.slots && g.slots.nodes) || {};
  const order = (g && g.slots && g.slots.order) || [];
  for (let i = 0; i < order.length; i++) {
    const node = nodes[order[i]];
    if (!node || node.parent) { continue; }
    if (gwSidBase(node.sid) !== "sight_rear") { continue; }
    const allow = node.allow || [];
    for (let a = 0; a < allow.length; a++) { if (GW_AK_REAR_SIGHT_IDS[allow[a]]) { return true; } }
  }
  return false;
}

const ctx = GB.context(items, stats);
const byGun = {};
Object.values(presets).forEach(function (p) { (byGun[p.g] = byGun[p.g] || []).push(p); });
function defaultInstalled(gunId) {
  const def = (stats.guns[gunId] || {}).preset;
  const p = (def && presets[def] && presets[def].g === gunId) ? presets[def] : (byGun[gunId] || [])[0];
  return (p && p.i) || {};
}

const inScope = [];   // 结构判定的 AK 照门系
const failures = [];
Object.keys(byGun).forEach(function (gid) {
  const name = (items[gid] || {}).n || (stats.guns[gid] || {}).n || gid;
  // 用真实树判定：buildTree 后的 nodes/order
  const tree = GB.buildTree(ctx, gid, GB.sanitize(ctx, gid, defaultInstalled(gid)).installed);
  if (!isAkRearSightGun({ slots: tree })) { return; }
  const L = api.gwBuildLayout({ gunId: gid, installed: defaultInstalled(gid), slots: tree });
  const byPath = {};
  L.cells.forEach(function (c) { byPath[c.path] = c; });
  const rsPath = L.row2 && L.row2.rearSight;
  const rs = rsPath && byPath[rsPath] ? byPath[rsPath] : null;
  inScope.push({ name: name, rs: rs ? ("r" + rs.row + "c" + rs.col) : "NONE" });
  if (!rs || rs.row !== 2 || rs.col !== 6) { failures.push({ name: name, rs: rs ? ("r" + rs.row + "c" + rs.col) : "NONE" }); }
});

console.log("需求一结构判定的 AK 照门系（必须 r2c6）：");
inScope.forEach(function (r) { console.log("  " + r.name.padEnd(34) + " -> " + r.rs); });
if (failures.length === 0) {
  console.log("CHECK_REQ1: PASS (" + inScope.length + "/" + inScope.length + ")");
} else {
  console.log("CHECK_REQ1: FAIL");
  failures.forEach(function (f) { console.log("  MISS: " + f.name + " -> " + f.rs); });
}
process.exit(failures.length === 0 ? 0 : 1);
