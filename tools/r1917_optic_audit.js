// R19.14.2 瞄具 / 底座 / 导轨转接件 槽位专项审计
// 输出：docs/r19.14-layout-changes/nightforce-slot-audit/{optic-slot-audit.json,optic-slot-issues.json}
// 口径：只比较「物品数据声明」「上游快照声明」「槽位树直接子节点」「画布实际渲染」四处，
//       不按类别推断其他物品的槽位数量或用途。
const fs = require("fs");
const path = require("path");
const ROOT = path.resolve(__dirname, "..");
const GB = require(path.join(ROOT, "gun_builder.js"));

const items = JSON.parse(fs.readFileSync(path.join(ROOT, "data/items.json"), "utf8")).items;
const gunslots = JSON.parse(fs.readFileSync(path.join(ROOT, "data/gunslots.json"), "utf8")).guns;
const stats = JSON.parse(fs.readFileSync(path.join(ROOT, "data/gun-stats.json"), "utf8"));
const presets = JSON.parse(fs.readFileSync(path.join(ROOT, "data/gun-presets.json"), "utf8")).presets || {};
const upstream = JSON.parse(fs.readFileSync(path.join(ROOT, "build-cache/r19-upstream/items.json"), "utf8"));

const src = fs.readFileSync(path.join(ROOT, "app.js"), "utf8");
const blockSrc = src.slice(src.indexOf("function gwSidBase("), src.indexOf("function renderGunSkin("));
const api = new Function("itemRec", "GW_ITEM_MAP",
  blockSrc + "\nreturn {gwBuildLayout:gwBuildLayout,gwSidBase:gwSidBase,gwSlotVisible:gwSlotVisible};")(
  function (id) { return items[id] || null; }, items);

const ctx = GB.context(items, stats);
const byGun = {};
Object.values(presets).forEach(function (p) { (byGun[p.g] = byGun[p.g] || []).push(p); });
function defInst(gid) {
  // 与 app.js gunDefaultBuild() 一致：先看 gun-stats.preset（不校验 preset.g）
  const st = stats.guns[gid] || {};
  if (st.preset && presets[st.preset]) { return presets[st.preset].i || {}; }
  for (const pid in presets) {
    const p = presets[pid];
    if (p && p.g === gid) { return p.i || {}; }
  }
  return {};
}

// ---------------------------------------------------------------- 筛选范围
// 瞄具（pt=Scope）+ 带瞄具/导轨/基座类槽位的配件（pt=WeaponMod）
const SLOT_RX = /scope|mount|sight|rail|red_dot|reddot/i;
function isOpticFamily(id) {
  const it = items[id];
  if (!it) return false;
  if (String(it.pt || "") === "Scope") return true;
  if (String(it.pt || "") !== "WeaponMod") return false;
  const slots = it.slots || [];
  if (!slots.length) return false;
  return slots.some(function (s) { return SLOT_RX.test(String(s.sid || "")); });
}

function upstreamSlots(id) {
  const it = ((upstream.data || {}).items || {})[id];
  const props = (it && (it.properties || it.props)) || {};
  return props.slots || [];
}

function allowSig(slot) {
  return (slot.allow || []).slice().sort().join(",");
}

// 找到一把能安装该物品的枪与槽位（用于建树 / 布局实测）
function findHost(id) {
  for (const gid of Object.keys(gunslots)) {
    const tree = GB.buildTree(ctx, gid, GB.sanitize(ctx, gid, defInst(gid)).installed);
    for (const p of Object.keys(tree.nodes)) {
      if ((tree.nodes[p].allow || []).indexOf(id) >= 0) {
        return { gunId: gid, slot: p };
      }
    }
  }
  return null;
}

const audit = { generatedFor: "R19.14.2", scope: "瞄具 / 瞄具底座 / 导轨转接件 / 多层安装组件", items: [], summary: {} };
const issues = { duplicates: [], extraDirectSlots: [], mismatchDeclaredVsTree: [], directionIssues: [], notes: [] };

const ids = Object.keys(items).filter(isOpticFamily).sort(function (a, b) {
  return String(items[a].n || "").localeCompare(String(items[b].n || ""), "zh");
});

ids.forEach(function (id) {
  const it = items[id];
  const declared = it.slots || [];
  const up = upstreamSlots(id);

  // 重复 allow 签名分组（同一物品内）
  const groups = {};
  declared.forEach(function (s) {
    const k = allowSig(s) || ("EMPTY:" + s.id);
    (groups[k] = groups[k] || []).push(s);
  });
  const dupGroups = Object.keys(groups).filter(function (k) { return groups[k].length > 1; })
    .map(function (k) {
      return groups[k].map(function (s) {
        return { id: s.id, sid: s.sid, label: s.label, allowCount: (s.allow || []).length };
      });
    });

  // 树 / 布局实测
  let treeKids = null, layoutCells = null, host = null, exceptionCount = null;
  const h = findHost(id);
  if (h) {
    host = h;
    const inst = Object.assign({}, GB.sanitize(ctx, h.gunId, defInst(h.gunId)).installed);
    inst[h.slot] = id;
    const s = GB.sanitize(ctx, h.gunId, inst);
    if (s.installed[h.slot] === id) {
      const tree = GB.buildTree(ctx, h.gunId, s.installed);
      treeKids = ((tree.nodes[h.slot] || {}).children || []).length;
      const L = api.gwBuildLayout({ gunId: h.gunId, installed: s.installed, slots: tree });
      layoutCells = L.cells.filter(function (c) {
        return c.path.indexOf(h.slot + "/") === 0 && c.path.split("/").length === h.slot.split("/").length + 1;
      }).length;
      exceptionCount = L.exceptions.length;
    }
  }

  const rec = {
    id: id,
    name: it.n,
    pt: it.pt,
    declaredDirectSlots: declared.length,
    upstreamDirectSlots: up.length,
    declaredSlots: declared.map(function (s) {
      return {
        id: s.id, sid: s.sid, label: s.label,
        allowCount: (s.allow || []).length,
        allowNames: (s.allow || []).map(function (a) { return (items[a] || {}).n || a; }).slice(0, 10),
        fix: s.fix || null
      };
    }),
    duplicateAllowGroups: dupGroups,
    host: host,
    treeDirectChildren: treeKids,
    layoutRenderedDirectCells: layoutCells,
    layoutExceptions: exceptionCount,
    evidence: "upstream-snapshot-only",
    verified: "pending"
  };

  // 状态判定：只有拿到游戏内确认的条目才算已核实
  if (id === "5aa66c72e5b5b00016327c93") {
    rec.evidence = "in-game-confirmed + upstream-snapshot";
    rec.verified = "confirmed-2-slots";   // 34mm 光学槽 + 单倍瞄具/底座槽
  }

  if (dupGroups.length) {
    issues.duplicates.push({
      id: id, name: it.n,
      groups: dupGroups,
      declared: declared.length,
      afterFix: id === "5aa66c72e5b5b00016327c93" ? 2 : declared.length,
      status: id === "5aa66c72e5b5b00016327c93" ? "fixed" : "pending-verification"
    });
  }
  if (treeKids !== null && treeKids !== declared.length) {
    issues.mismatchDeclaredVsTree.push({
      id: id, name: it.n, declared: declared.length, treeKids: treeKids
    });
  }
  if (layoutCells !== null && layoutCells !== declared.length) {
    // 分类原因：若少的那些子槽是被 gwSlotVisible 的同基名空副本规则隐藏，则属既有可见性
    // 规则（R19.x）而非本轮数据错误；否则记为待核实的数据/布局不一致。
    let hidden = [];
    if (layoutCells < declared.length && host) {
      const inst = Object.assign({}, GB.sanitize(ctx, host.gunId, defInst(host.gunId)).installed);
      inst[host.slot] = id;
      const s = GB.sanitize(ctx, host.gunId, inst);
      const tr = GB.buildTree(ctx, host.gunId, s.installed);
      const kids = (tr.nodes[host.slot] || {}).children || [];
      hidden = kids.filter(function (k) {
        return !api.gwSlotVisible({ installed: s.installed, slots: tr }, k);
      }).map(function (k) { return tr.nodes[k].sid; });
    }
    issues.mismatchDeclaredVsTree.push({
      id: id, name: it.n,
      declared: declared.length,
      layoutCells: layoutCells,
      hiddenByVisibilityRule: hidden,
      reason: hidden.length ? "gwSlotVisible 隐藏同基名空副本（既有规则，非本轮数据错误）"
                            : "待核实：画布直接格数与数据声明不一致"
    });
  }

  audit.items.push(rec);
});

// Nightforce 专项结论
const nf = audit.items.filter(function (x) { return x.id === "5aa66c72e5b5b00016327c93"; })[0];
audit.summary = {
  opticFamilyItems: audit.items.length,
  withDirectSlots: audit.items.filter(function (x) { return x.declaredDirectSlots > 0; }).length,
  withDuplicateAllowGroups: audit.items.filter(function (x) { return (x.duplicateAllowGroups || []).length; }).length,
  inGameConfirmed: audit.items.filter(function (x) { return x.verified !== "pending"; }).length,
  pendingVerification: audit.items.filter(function (x) { return x.verified === "pending"; }).length,
  nightforce: nf ? {
    declaredDirectSlots: nf.declaredDirectSlots,
    treeDirectChildren: nf.treeDirectChildren,
    layoutRenderedDirectCells: nf.layoutRenderedDirectCells,
    slots: nf.declaredSlots
  } : null
};

// 已修复问题：修复后数据里已无重复，必须显式记录（不能因为「现在没重复」就丢掉证据）
issues.fixed = [
  {
    id: "5aa66c72e5b5b00016327c93",
    name: items["5aa66c72e5b5b00016327c93"].n,
    kind: "duplicate-direct-slots",
    before: {
      declaredDirectSlots: 4,
      sids: ["mod_scope_000", "mod_scope_001", "mod_scope_002", "mod_scope_003"],
      duplicateAllowPairs: [
        ["mod_scope_002", "mod_scope_003"],
        ["mod_scope_001", "mod_scope_002"],
        ["mod_scope_001", "mod_scope_003"]
      ]
    },
    after: { declaredDirectSlots: 2, sids: ["mod_scope_000", "mod_scope_001"] },
    fix: "在 tools/fetch_data.py 增加 OPTIC_SLOT_CORRECTIONS 并在建库时应用；同步修正 data/items.json",
    evidence: "in-game-confirmed",
    status: "fixed"
  },
  {
    id: "hk-g36-mount-double-cell",
    name: "HK G36瞄具基座",
    kind: "layout-duplicate-cell",
    before: { layoutRenderedDirectCells: 6, declaredDirectSlots: 4 },
    after: { layoutRenderedDirectCells: 4 },
    fix: "gwBuildLayout 的 cell() 增加同路径去重；同一槽位只保留首次落位",
    evidence: "code-inferred + browser-measured",
    status: "fixed"
  }
];

issues.notes = [
  "只有 Nightforce MagMount Multimount 34mm 一个条目有游戏内实测确认（2 个直接槽位）。",
  "其余瞄具/底座仅有上游快照单一来源，未做游戏内实测，一律标记 pending，不据此改动数量或用途。",
  "重复 allow 签名只说明数据层出现同构槽位，是否应合并需游戏内确认；本轮不改未确认条目。"
];

const outDir = path.join(ROOT, process.env.GW_AUDIT_DIR || "docs/r19.14-layout-changes/nightforce-slot-audit");
fs.mkdirSync(outDir, { recursive: true });
fs.writeFileSync(path.join(outDir, "optic-slot-audit.json"), JSON.stringify(audit, null, 2), "utf8");
fs.writeFileSync(path.join(outDir, "optic-slot-issues.json"), JSON.stringify(issues, null, 2), "utf8");
console.log("optic family items:", audit.items.length,
  "| with slots:", audit.summary.withDirectSlots,
  "| dup groups:", audit.summary.withDuplicateAllowGroups,
  "| pending:", audit.summary.pendingVerification);
console.log("nightforce:", JSON.stringify(audit.summary.nightforce && {
  declared: audit.summary.nightforce.declaredDirectSlots,
  tree: audit.summary.nightforce.treeDirectChildren,
  layout: audit.summary.nightforce.layoutRenderedDirectCells
}));
