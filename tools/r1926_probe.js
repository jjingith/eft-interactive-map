// R19.18 槽位树勘察探针：把 app.js 的槽位树生成 + 布局引擎抠到 node 上，
// 输出指定枪械的「真实槽位树 / 装件 / 布局坐标 / 候选」明细，用于定位 10 项问题。
// 用法：node tools/r1926_probe.js <gunId|名称片段> [...]
const fs = require("fs"), path = require("path");
const ROOT = path.resolve(__dirname, "..");
const GB = require(path.join(ROOT, "gun_builder.js"));
const items = JSON.parse(fs.readFileSync(path.join(ROOT, "data/items.json"), "utf8")).items;
const stats = JSON.parse(fs.readFileSync(path.join(ROOT, "data/gun-stats.json"), "utf8"));
const presets = JSON.parse(fs.readFileSync(path.join(ROOT, "data/gun-presets.json"), "utf8")).presets || {};
const gunslots = JSON.parse(fs.readFileSync(path.join(ROOT, "data/gunslots.json"), "utf8")).guns;
const src = fs.readFileSync(path.join(ROOT, "app.js"), "utf8");
const block = src.slice(src.indexOf("function gwSidBase("), src.indexOf("function renderGunSkin("));
const api = new Function("itemRec", "GW_ITEM_MAP", block +
  "\nreturn {gwBuildLayout:gwBuildLayout,gwApplyCalibToLayout:gwApplyCalibToLayout,gwSidBase:gwSidBase};")(
  function (id) { return items[id] || null; }, items);
const ctx = GB.context(items, stats);

const nameOf = function (id) { return (items[id] || {}).n || id; };

function defInst(gid) {
  const st = (stats.guns || {})[gid] || {};
  if (st.preset && presets[st.preset]) { return presets[st.preset].i || {}; }
  for (const pid in presets) { const p = presets[pid]; if (p && p.g === gid) { return p.i || {}; } }
  return {};
}
function treeOf(gid, instOverride) {
  const inst0 = instOverride || defInst(gid);
  const s = GB.sanitize(ctx, gid, inst0);
  const tree = GB.buildTree(ctx, gid, s.installed);
  return { installed: s.installed, tree: tree };
}
function layoutOf(gid, instOverride) {
  const b = treeOf(gid, instOverride);
  const L = api.gwBuildLayout({ gunId: gid, installed: b.installed, slots: b.tree, noCalib: true });
  const by = {};
  L.cells.forEach(function (c) { by[c.path] = c; });
  return { b: b, L: L, by: by };
}

// 复刻 app.js 的槽位树生成（addGunSlots）：枪械槽位 + 已装件自带子槽
function buildTree(gid, installed) {
  const tree = { nodes: {}, order: [] };
  const rec = gunslots[gid] || null;
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
  })(rec, "", null);
  return tree;
}

function dump(gid, label, instOverride) {
  const b = treeOf(gid, instOverride);
  const appTree = buildTree(gid, b.installed);
  const L = api.gwBuildLayout({ gunId: gid, installed: b.installed, slots: b.tree, noCalib: true });
  const by = {};
  L.cells.forEach(function (c) { by[c.path] = c; });
  console.log("\n=== " + label + "  (" + gid + ") ===");
  console.log("  装件: " + Object.keys(b.installed).length + " 件 | 树节点: " + appTree.order.length +
    " | 布局格: " + L.cells.length + " | rows=" + L.rows + " topPad=" + L.topPad);
  appTree.order.forEach(function (p) {
    const node = appTree.nodes[p];
    const cell = by[p];
    const inst = b.installed[p] || "";
    const allowNames = (node.allow || []).map(function (a) {
      const it = items[a] || {};
      return (it.n || a) + (it.pt ? "[" + it.pt + "]" : "");
    });
    const scopes = allowNames.filter(function (x) { return x.indexOf("[Scope]") >= 0; });
    console.log("  " + (cell ? ("r" + cell.row + "c" + cell.col).padEnd(7) : "--------") +
      " " + p.padEnd(46) +
      " 装:" + (inst ? nameOf(inst).slice(0, 18) : "-").padEnd(20) +
      " allow:" + allowNames.length +
      (scopes.length ? "  Scope候选:" + scopes.slice(0, 3).join(",") : ""));
  });
  console.log("  布局未落位的槽: " + appTree.order.filter(function (p) { return !by[p]; }).join(", "));
  return { b: b, L: L, by: by, appTree: appTree };
}

const args = process.argv.slice(2);
const targets = [];
for (const gid of Object.keys(gunslots)) {
  const n = gunslots[gid].n || "";
  if (!args.length || args.some(function (a) { return a.toLowerCase() === gid.toLowerCase() || n.indexOf(a) >= 0; })) {
    targets.push([gid, n]);
  }
}
if (!targets.length) { console.log("no gun matched:", args); process.exit(1); }
for (const [gid, n] of targets) { dump(gid, n); }
