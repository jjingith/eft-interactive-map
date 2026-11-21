// R19.28 调试：打印 Saiga-12K 自动版 buildTree 节点父子关系
const fs = require("fs"), path = require("path");
const ROOT = "D:/personal/trae/02-塔科夫/eft-interactive-map";
const GB = require(path.join(ROOT, "gun_builder.js"));
const items = JSON.parse(fs.readFileSync(path.join(ROOT, "data/items.json"), "utf8")).items;
const stats = JSON.parse(fs.readFileSync(path.join(ROOT, "data/gun-stats.json"), "utf8"));
const presets = JSON.parse(fs.readFileSync(path.join(ROOT, "data/gun-presets.json"), "utf8")).presets || {};
const gid = process.argv[2];
const ctx = GB.context(items, stats);
function defInst(g) {
  const st = (stats.guns || {})[g] || {};
  if (st.preset && presets[st.preset]) { return presets[st.preset].i || {}; }
  for (const p in presets) { if (presets[p] && presets[p].g === g) { return presets[p].i || {}; } }
  return {};
}
const inst = GB.sanitize(ctx, gid, defInst(gid)).installed;
const tree = GB.buildTree(ctx, gid, inst);
console.log("=== 顶层 ===");
for (const p of tree.order) {
  const n = tree.nodes[p];
  console.log("  " + p + "  sid=" + n.sid + "  children=" + JSON.stringify(n.children));
}
console.log("=== 所有含 scope/mount 的节点（含路径深度）===");
for (const p of tree.order) {
  const n = tree.nodes[p];
  const base = String(n.sid || "").replace(/_\d+$/, "");
  if (base === "scope" || base === "mount" || base === "sight_rear" || base === "sight_front") {
    const installed = inst[p];
    console.log("  " + p + "  sid=" + n.sid + "  installed=" + (installed || "—") +
      "  children=" + JSON.stringify(n.children));
  }
}
console.log("=== 父->子 关联（仅含 scope/mount 的父）===");
for (const p of tree.order) {
  const n = tree.nodes[p];
  const base = String(n.sid || "").replace(/_\d+$/, "");
  if (n.children && n.children.length && (base === "scope" || base === "mount" || base === "sight_rear" || base === "sight_front")) {
    console.log("  PARENT " + p + " (sid=" + n.sid + ")");
    for (const c of n.children) { console.log("      child " + c + " (sid=" + (tree.nodes[c] || {}).sid + ")"); }
  }
}
