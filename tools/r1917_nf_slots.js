// R19.14.2 Nightforce 专项：直接槽位定义 + 修复前后槽位树
// 输出：
//   nightforce-direct-slots.json   —— 真实物品 ID、两个直接槽位、用途、allow
//   nightforce-tree-before-after.json —— 修复前（上游 4 槽）与修复后（2 槽）的真实树/布局
const fs = require("fs");
const path = require("path");
const ROOT = path.resolve(__dirname, "..");
const GB = require(path.join(ROOT, "gun_builder.js"));

const items = JSON.parse(fs.readFileSync(path.join(ROOT, "data/items.json"), "utf8")).items;
const stats = JSON.parse(fs.readFileSync(path.join(ROOT, "data/gun-stats.json"), "utf8"));
const presets = JSON.parse(fs.readFileSync(path.join(ROOT, "data/gun-presets.json"), "utf8")).presets || {};
const upstream = JSON.parse(fs.readFileSync(path.join(ROOT, "build-cache/r19-upstream/items.json"), "utf8"));
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

const MOUNT = "5aa66c72e5b5b00016327c93";     // Nightforce MagMount Multimount 34mm
const ATACR = "5aa66be6e5b5b0214e506e97";     // Nightforce ATACR 7-35x56 34mm（34mm 光学槽代表）
const MICRO = "58d39d3d86f77445bb794ae7";     // Aimpoint Micro 底座（单倍槽代表，若有）
const outDir = path.join(ROOT, "docs/r19.14-layout-changes/nightforce-slot-audit");
fs.mkdirSync(outDir, { recursive: true });

// ---------------------------------------------------------- 1. 直接槽位定义
const cur = items[MOUNT];
const upRaw = (((upstream.data || {}).items || {})[MOUNT] || {});
const upSlots = ((upRaw.properties || upRaw.props || {}).slots || []);

const direct = {
  itemId: MOUNT,
  name: cur.n,
  pt: cur.pt,
  evidence: {
    inGame: "2026-10-26 用户游戏内实测：直接槽位恰好 2 个（34mm 光学瞄准镜 / 单倍瞄具·单倍瞄具底座）",
    upstream: "tarkov.dev 快照声明 4 个同名 MOD_SCOPE（其中 _002/_003 allow 完全重复，属重复节点）",
    conflict: true,
    resolution: "以游戏内实测为准；移除两个重复节点，保留 34mm 与单倍槽"
  },
  directSlotCount: (cur.slots || []).length,
  slots: (cur.slots || []).map(function (s, i) {
    return {
      order: i + 1,
      slotId: s.id,
      sid: s.sid,
      label: s.label,
      purpose: i === 0 ? "34mm 光学瞄准镜槽" : "单倍瞄具 / 单倍瞄具底座槽",
      allowCount: (s.allow || []).length,
      allow: (s.allow || []).map(function (a) {
        const rec = items[a] || {};
        return { id: a, name: rec.n || a, pt: rec.pt || null };
      })
    };
  }),
  removedSlots: [
    {
      slotId: "5aa66cabe5b5b055d0630d82", sid: "mod_scope_002",
      reason: "与 mod_scope_001 的 allow 子集完全重复；游戏中不存在第三个直接槽位",
      sameAs: "5aa66c9ce5b5b00015693125"
    },
    {
      slotId: "5aa66cb7e5b5b0214e506e99", sid: "mod_scope_003",
      reason: "与 mod_scope_002 完全相同（互相重复）；游戏中不存在第四个直接槽位",
      sameAs: "5aa66cabe5b5b055d0630d82"
    }
  ]
};
fs.writeFileSync(path.join(outDir, "nightforce-direct-slots.json"),
  JSON.stringify(direct, null, 2), "utf8");

// ------------------------------------------------- 2. 修复前后树 / 布局实测
const gid = Object.keys(items).find(function (k) {
  return String(items[k].n || "").indexOf("SV-98 7.62x54R") === 0;
});
let inst = GB.sanitize(ctx, gid, defInst(gid)).installed;
delete inst["mod_sight_rear"];           // 与导轨基座互斥（上游 conflictingItems 链路）
inst["mod_scope"] = MOUNT;
let s1 = GB.sanitize(ctx, gid, inst);
const tree1 = GB.buildTree(ctx, gid, s1.installed);
const kids1 = (tree1.nodes["mod_scope"] || {}).children || [];

// 装 34mm 光学 + 单倍底座，验证方向
const baseId = (tree1.nodes["mod_scope/mod_scope_001"] || {}).allow
  ? (tree1.nodes["mod_scope/mod_scope_001"].allow).find(function (id) {
      return /Micro瞄具基座/.test(String((items[id] || {}).n || ""));
    })
  : null;
const inst2 = Object.assign({}, s1.installed);
inst2["mod_scope/mod_scope_000"] = ATACR;
if (baseId) inst2["mod_scope/mod_scope_001"] = baseId;
const s2 = GB.sanitize(ctx, gid, inst2);
const tree2 = GB.buildTree(ctx, gid, s2.installed);
const L2 = api.gwBuildLayout({ gunId: gid, installed: s2.installed, slots: tree2 });

function dumpTree(tree, prefix) {
  const out = [];
  (function walk(p) {
    const n = tree.nodes[p]; if (!n) return;
    out.push({
      path: p, sid: n.sid, label: n.label,
      allowCount: (n.allow || []).length,
      installed: s2.installed[p] || null,
      installedName: s2.installed[p] ? ((items[s2.installed[p]] || {}).n || null) : null
    });
    (n.children || []).forEach(walk);
  })(prefix);
  return out;
}

function layoutOf(installed) {
  const t = GB.buildTree(ctx, gid, installed);
  const L = api.gwBuildLayout({ gunId: gid, installed: installed, slots: t });
  return {
    rows: L.rows, topPad: L.topPad,
    mountAndChildren: L.cells.filter(function (c) {
      return c.path === "mod_scope" || c.path.indexOf("mod_scope/") === 0;
    }).map(function (c) {
      return { path: c.path, row: c.row, col: c.col };
    })
  };
}

const bf = {
  gun: { id: gid, name: items[gid].n },
  before: {
    source: "build-cache/r19-upstream/items.json（上游快照）",
    upstreamSlotCount: upSlots.length,
    upstreamSids: upSlots.map(function (x) { return x.name + ":" + x.id; }),
    note: "上游声明 4 个同名 MOD_SCOPE；项目此前直接按 4 个建树，画布出现 4 个直接子槽",
    reconstructedChildren: 4
  },
  after: {
    source: "data/items.json（应用 OPTIC_SLOT_CORRECTIONS 后）",
    declaredSlotCount: (cur.slots || []).length,
    declaredSids: (cur.slots || []).map(function (s) { return s.sid; }),
    treeDirectChildren: kids1.length,
    treeChildren: kids1.map(function (k) {
      return { path: k, sid: tree1.nodes[k].sid, label: tree1.nodes[k].label,
               allowCount: (tree1.nodes[k].allow || []).length };
    }),
    layoutAfterInstall: layoutOf(s2.installed),
    treeWithParts: dumpTree(tree2, "mod_scope")
  },
  checks: {
    declaredEqualsTwo: (cur.slots || []).length === 2,
    treeEqualsTwo: kids1.length === 2,
    layoutDirectEqualsTwo: L2.cells.filter(function (c) {
      return c.path.indexOf("mod_scope/") === 0 && c.path.split("/").length === 2;
    }).length === 2
  }
};
fs.writeFileSync(path.join(outDir, "nightforce-tree-before-after.json"),
  JSON.stringify(bf, null, 2), "utf8");

console.log("direct slots:", direct.directSlotCount, direct.slots.map(function (s) { return s.sid + "=" + s.purpose; }));
console.log("tree children after:", kids1.length, "| checks:", JSON.stringify(bf.checks));
console.log("layout with parts:", JSON.stringify(bf.after.layoutAfterInstall.mountAndChildren));
