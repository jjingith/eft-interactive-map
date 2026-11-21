// R19.28 勘察探针 4（只读）：需求三候选场景 —— 第六行 r6c1/r6c2 两个独立槽
//   目标：找出 r6c1 可装「带子槽的导轨/基座」、且 r6c2 是独立槽的真实枪械
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
  api.gwApplyCalibToLayout(L, { gunId: gid, installed: ins, slots: tree }, (calib.guns[gid] || {}).slots || {});
  const map = {};
  L.cells.forEach(function (c) { map[c.path] = { row: c.row, col: c.col }; });
  return { ins: ins, tree: tree, L: L, map: map };
}

const cands = [];
for (const gid of Object.keys(calib.guns)) {
  const recs = calib.guns[gid].slots || {};
  const r6 = [];
  for (const k of Object.keys(recs)) {
    const s = recs[k];
    if (s.logicalRow === 6 && s.col >= 1 && s.col <= 5) { r6.push({ key: k, col: s.col, path: k.split("|")[0] }); }
  }
  r6.sort(function (a, b) { return a.col - b.col; });
  if (r6.length < 2) { continue; }
  const p1 = r6[0], p2 = r6[1];
  if (p1.col !== 1 || p2.col !== 2) { continue; }
  // 两个槽必须互相独立（不是父子）
  if (p2.path.indexOf(p1.path + "/") === 0) { continue; }
  const f0 = finalCells(gid, null);
  const n1 = f0.tree.nodes[p1.path];
  if (!n1) { continue; }
  const rails = (n1.allow || []).filter(function (a) { return ((items[a] || {}).slots || []).length > 0; });
  cands.push({
    gid: gid, name: calib.guns[gid].name, s1: p1.path, s2: p2.path,
    s1empty: !f0.ins[p1.path], s2empty: !f0.ins[p2.path],
    rails: rails.map(function (a) { return (items[a] || {}).n + "(" + ((items[a] || {}).slots || []).length + ")"; })
  });
}
console.log("=== 需求三候选：r6c1/r6c2 独立 + r6c1 可装带子槽件 ===");
for (const c of cands) {
  console.log(" " + c.name.slice(0, 26).padEnd(28) + " c1=" + c.s1 + (c.s1empty ? "(空)" : "(已装)") +
    " c2=" + c.s2 + (c.s2empty ? "(空)" : "(已装)"));
  console.log("     可装带子槽件: " + (c.rails.slice(0, 6).join(" / ") || "无"));
}
if (!cands.length) { console.log(" （无）"); }

// 逐个复现：装上导轨看 r6c2 是否消失
console.log("\n=== 复现（装 r6c1 的带子槽件后，r6c2 的槽还在不在）===");
const repro = [];
for (const c of cands) {
  if (!c.rails.length) { continue; }
  const f0 = finalCells(c.gid, null);
  // 选子槽最多的一个
  const allow = f0.tree.nodes[c.s1].allow || [];
  let best = null;
  for (const a of allow) {
    if (!((items[a] || {}).slots || []).length) { continue; }
    if (!best || ((items[a] || {}).slots || []).length > ((items[best] || {}).slots || []).length) { best = a; }
  }
  if (!best) { continue; }
  const inst = Object.assign({}, defInst(c.gid));
  inst[c.s1] = best;
  const f1 = finalCells(c.gid, inst);
  const kids = (f1.tree.nodes[c.s1] || {}).children || [];
  const before = f0.map[c.s2] ? ("r" + f0.map[c.s2].row + "c" + f0.map[c.s2].col) : "MISSING";
  const after = f1.map[c.s2] ? ("r" + f1.map[c.s2].row + "c" + f1.map[c.s2].col) : "消失";
  const kidPos = kids.map(function (k) {
    return k + "@" + (f1.map[k] ? ("r" + f1.map[k].row + "c" + f1.map[k].col) : "MISSING");
  });
  // 重叠检测
  const seen = {}; const dup = [];
  f1.L.cells.forEach(function (x) { const k = x.row + "|" + x.col; if (seen[k]) { dup.push(k + ":" + seen[k] + "/" + x.path); } seen[k] = x.path; });
  repro.push({ gun: c.name, item: (items[best] || {}).n, s2before: before, s2after: after, kids: kidPos, dup: dup, rows: f1.L.rows });
  console.log(" " + c.name.slice(0, 24).padEnd(26) + " 装[" + (items[best] || {}).n + "]");
  console.log("    c2 前=" + before + "  后=" + after + "   子槽=" + kidPos.join(" ") + (dup.length ? "  重叠:" + dup.join(",") : ""));
}
fs.mkdirSync(path.join(ROOT, "docs/r19.28"), { recursive: true });
fs.writeFileSync(path.join(ROOT, "docs/r19.28/probe-row6.json"), JSON.stringify({ cands: cands, repro: repro }, null, 2), "utf8");
console.log("\n输出 docs/r19.28/probe-row6.json");
