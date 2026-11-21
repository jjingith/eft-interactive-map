// R19.28 调试：Saiga-12K 自动版 子槽坐标
const fs = require("fs"), path = require("path");
const ROOT = "D:/personal/trae/02-塔科夫/eft-interactive-map";
const GB = require(path.join(ROOT, "gun_builder.js"));
const items = JSON.parse(fs.readFileSync(path.join(ROOT, "data/items.json"), "utf8")).items;
const stats = JSON.parse(fs.readFileSync(path.join(ROOT, "data/gun-stats.json"), "utf8"));
const presets = JSON.parse(fs.readFileSync(path.join(ROOT, "data/gun-presets.json"), "utf8")).presets || {};
const calib = JSON.parse(fs.readFileSync(path.join(ROOT, "data/gun-layout-calibration.json"), "utf8"));
const src = fs.readFileSync(path.join(ROOT, "app.js"), "utf8");
const block = src.slice(src.indexOf("function gwSidBase("), src.indexOf("function renderGunSkin("));
const api = new Function("itemRec", "GW_ITEM_MAP", block +
  "\nreturn {gwBuildLayout:gwBuildLayout,gwApplyCalibToLayout:gwApplyCalibToLayout,gwSidBase:gwSidBase,gwIsOpticParentPath:gwIsOpticParentPath};")(
  function (id) { return items[id] || null; }, items);
const ctx = GB.context(items, stats);
const gid = process.argv[2];
function defInst(g) {
  const st = (stats.guns || {})[g] || {};
  if (st.preset && presets[st.preset]) { return presets[st.preset].i || {}; }
  for (const p in presets) { if (presets[p] && presets[p].g === g) { return presets[p].i || {}; } }
  return {};
}
const override = {};
for (let i = 3; i < process.argv.length; i += 2) { override[process.argv[i]] = process.argv[i + 1]; }
const base = JSON.parse(JSON.stringify(defInst(gid)));
const inst = GB.sanitize(ctx, gid, Object.assign(base, override)).installed;
const tree = GB.buildTree(ctx, gid, inst);
const L = api.gwBuildLayout({ gunId: gid, installed: inst, slots: tree, noCalib: true });
console.log("--- BUILD (display) topPad=" + L.topPad + " rows=" + L.rows);
L.cells.forEach(function (c) {
  const isP = api.gwIsOpticParentPath({ slots: tree }, c.path);
  if (isP) { console.log("   P " + c.path.slice(-40).padEnd(42) + "r" + c.row + "c" + c.col + "  kids=" + ((tree.nodes[c.path].children || []).length)); }
});
const info = api.gwApplyCalibToLayout(L, { gunId: gid, installed: inst, slots: tree }, (calib.guns[gid] || {}).slots || {});
console.log("--- FINAL (display) topPad=" + L.topPad + " rows=" + L.rows);
L.cells.forEach(function (c) {
  const isP = api.gwIsOpticParentPath({ slots: tree }, c.path);
  console.log("   " + (isP ? "P " : "  ") + c.path.slice(-40).padEnd(42) + "r" + c.row + "c" + c.col + (isP ? "  kids=" + ((tree.nodes[c.path].children || []).length) : ""));
});
console.log("fallback:", JSON.stringify(info.fallback));
