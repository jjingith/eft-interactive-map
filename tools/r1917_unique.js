// R19.14.2 布局去重校验：同一槽位路径不得在画布上出现两次；直接子槽数不得超过数据声明。
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
  block + "\nreturn {gwBuildLayout:gwBuildLayout,gwSidBase:gwSidBase};")(
  function (id) { return items[id] || null; }, items);

const ctx = GB.context(items, stats);
const byGun = {};
Object.values(presets).forEach(function (p) { (byGun[p.g] = byGun[p.g] || []).push(p); });
function defInst(gid) {
  const def = (stats.guns[gid] || {}).preset;
  const p = (def && presets[def] && presets[def].g === gid) ? presets[def] : (byGun[gid] || [])[0];
  return (p && p.i) || {};
}

const dup = [];
let guns = 0, cells = 0;
for (const gid of Object.keys(byGun)) {
  const inst = GB.sanitize(ctx, gid, defInst(gid)).installed;
  const tree = GB.buildTree(ctx, gid, inst);
  const L = api.gwBuildLayout({ gunId: gid, installed: inst, slots: tree });
  guns += 1;
  cells += L.cells.length;
  const seen = {};
  L.cells.forEach(function (c) {
    if (seen[c.path]) {
      dup.push({ gun: items[gid].n, path: c.path,
                 first: { row: seen[c.path].row, col: seen[c.path].col },
                 again: { row: c.row, col: c.col } });
    }
    seen[c.path] = c;
  });
}
// Nightforce 直接子槽数量（数据/树/布局三处）
const MOUNT = "5aa66c72e5b5b00016327c93";
const declared = (items[MOUNT].slots || []).length;
let treeKids = null;
const gid = Object.keys(items).find(function (k) {
  return String(items[k].n || "").indexOf("SV-98 7.62x54R") === 0;
});
let inst = GB.sanitize(ctx, gid, defInst(gid)).installed;
delete inst["mod_sight_rear"];
inst["mod_scope"] = MOUNT;
const s = GB.sanitize(ctx, gid, inst);
const tr = GB.buildTree(ctx, gid, s.installed);
treeKids = ((tr.nodes["mod_scope"] || {}).children || []).length;
const L = api.gwBuildLayout({ gunId: gid, installed: s.installed, slots: tr });
const layoutKids = L.cells.filter(function (c) {
  return c.path.indexOf("mod_scope/") === 0 && c.path.split("/").length === 2;
}).length;

console.log(JSON.stringify({
  guns: guns, cells: cells, duplicates: dup.slice(0, 8), duplicateCount: dup.length,
  nightforce: { declared: declared, treeKids: treeKids, layoutKids: layoutKids }
}, null, 1));
