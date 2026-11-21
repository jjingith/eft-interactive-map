// R19.28 勘察探针 3（只读）：瞄具类型父槽 → 子槽 的最终显示坐标审计
//   瞄具类型父槽：scope / sight_rear（照门）/ 燕尾槽基座（直接吃瞄具的机匣级 mount）
//   场景：default = 默认预设；filled = 给空的瞄具父槽装上「子槽最多」的候选件
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
  "gwSlotVisible:gwSlotVisible,gwSidBase:gwSidBase};")(
  function (id) { return items[id] || null; }, items);
const ctx = GB.context(items, stats);
const REC = /^(reciever|receiver|slide|frame|upper|lower)$/;
const B = function (s) { return api.gwSidBase(s || ""); };

function defInst(gid) {
  const st = (stats.guns || {})[gid] || {};
  if (st.preset && presets[st.preset]) { return presets[st.preset].i || {}; }
  for (const p in presets) { if (presets[p] && presets[p].g === gid) { return presets[p].i || {}; } }
  return {};
}
function finalCells(gid, inst) {
  const ins = GB.sanitize(ctx, gid, inst || defInst(gid)).installed;
  const tree = GB.buildTree(ctx, gid, ins);
  const L = api.gwBuildLayout({ gunId: gid, installed: ins, slots: tree, noCalib: true });
  api.gwApplyCalibToLayout(L, { gunId: gid, installed: ins, slots: tree },
    (calib.guns[gid] || {}).slots || {});
  const map = {};
  L.cells.forEach(function (c) { map[c.path] = { row: c.row, col: c.col, role: c.role || "" }; });
  return { ins: ins, tree: tree, L: L, map: map, rows: L.rows };
}
function isOpticParent(path, tree) {
  const node = tree.nodes[path];
  if (!node) { return false; }
  const base = B(node.sid);
  if (base === "scope" || base === "sight_rear") { return true; }
  if (base !== "mount") { return false; }
  const allow = node.allow || [];
  if (!allow.some(function (a) { return (items[a] || {}).pt === "Scope"; })) { return false; }
  const par = node.parent;
  if (par && !REC.test(B((tree.nodes[par] || {}).sid))) { return false; }
  return true;
}

const results = [];
const GUNS = process.argv[2] ? [process.argv[2]] : Object.keys(gunslots);
for (const gid of GUNS) {
  const f0 = finalCells(gid, null);
  const scenarios = [["default", null]];
  let filled = null;
  for (const p of f0.tree.order) {
    if (!isOpticParent(p, f0.tree) || f0.ins[p]) { continue; }
    const wk = (f0.tree.nodes[p].allow || []).filter(function (a) { return ((items[a] || {}).slots || []).length > 0; });
    if (!wk.length) { continue; }
    let best = wk[0];
    for (const w of wk) { if (((items[w] || {}).slots || []).length > ((items[best] || {}).slots || []).length) { best = w; } }
    filled = filled || Object.assign({}, defInst(gid));
    filled[p] = best;
  }
  if (filled) { scenarios.push(["filled", filled]); }
  for (const sc of scenarios) {
    const f = finalCells(gid, sc[1]);
    for (const p of f.tree.order) {
      if (!isOpticParent(p, f.tree)) { continue; }
      const pc = f.map[p];
      if (!pc) { continue; }
      const kids = (f.tree.nodes[p].children || []).filter(function (k) { return !!f.map[k]; });
      if (!kids.length) { continue; }
      const off = [];
      for (const k of kids) {
        const kc = f.map[k];
        if (kc.col !== pc.col) { off.push(B(f.tree.nodes[k].sid) + " 列" + kc.col + "!=" + pc.col); }
        else if (kc.row >= pc.row) { off.push(B(f.tree.nodes[k].sid) + " 行" + kc.row + ">=" + pc.row); }
      }
      results.push({
        gid: gid, gun: (gunslots[gid] || {}).n || gid, scen: sc[0],
        parent: p, pp: "r" + pc.row + "c" + pc.col, nk: kids.length,
        kids: kids.map(function (k) { return B(f.tree.nodes[k].sid) + "@r" + f.map[k].row + "c" + f.map[k].col; }),
        rows: f.L.rows, off: off
      });
    }
  }
}
const bad = results.filter(function (r) { return r.off.length; });
console.log("=== 瞄具类型父槽 → 子槽（最终显示坐标）===");
console.log("总组数 " + results.length + "  违规 " + bad.length +
  "  [default " + results.filter(function (r) { return r.scen === "default"; }).length +
  " 组/违规 " + bad.filter(function (r) { return r.scen === "default"; }).length +
  "]  [filled " + results.filter(function (r) { return r.scen === "filled"; }).length +
  " 组/违规 " + bad.filter(function (r) { return r.scen === "filled"; }).length + "]");
for (const r of bad) {
  console.log(" [" + r.scen + "] " + r.gun.slice(0, 22).padEnd(24) +
    " P=" + r.pp.padEnd(6) + " K=[" + r.kids.join(" ") + "] rows=" + r.rows + "  <<< " + r.off.join("; "));
}
fs.mkdirSync(path.join(ROOT, "docs/r19.28"), { recursive: true });
fs.writeFileSync(path.join(ROOT, "docs/r19.28/probe-child-over.json"),
  JSON.stringify({ total: results.length, bad: bad, all: results }, null, 2), "utf8");
console.log("\n输出 docs/r19.28/probe-child-over.json");
