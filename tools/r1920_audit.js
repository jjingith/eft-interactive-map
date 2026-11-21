// R19.15 全量枪械槽位审计 + ASH-12 专项 + 上导轨战术车道 + 瞄具槽位
// 输出：docs/r19.15-theme-audit/{all-gun-slot-audit.json, ash12-layout-audit.json,
//                              tactical-slot-lanes.json, optic-slot-audit.json}
const fs = require("fs");
const path = require("path");
const ROOT = path.resolve(__dirname, "..");
const GB = require(path.join(ROOT, "gun_builder.js"));

const items = JSON.parse(fs.readFileSync(path.join(ROOT, "data/items.json"), "utf8")).items;
const stats = JSON.parse(fs.readFileSync(path.join(ROOT, "data/gun-stats.json"), "utf8"));
const presets = JSON.parse(fs.readFileSync(path.join(ROOT, "data/gun-presets.json"), "utf8")).presets || {};
const gunslots = JSON.parse(fs.readFileSync(path.join(ROOT, "data/gunslots.json"), "utf8")).guns;
const src = fs.readFileSync(path.join(ROOT, "app.js"), "utf8");
const block = src.slice(src.indexOf("function gwSidBase("), src.indexOf("function renderGunSkin("));
const api = new Function("itemRec", "GW_ITEM_MAP",
  block + "\nreturn {gwBuildLayout:gwBuildLayout,gwSidBase:gwSidBase,gwSlotVisible:gwSlotVisible,gwLaneOf:gwLaneOf,gwIsBadSlot:gwIsBadSlot};")(
  function (id) { return items[id] || null; }, items);

const ctx = GB.context(items, stats);
const byGun = {};
Object.values(presets).forEach(function (p) { (byGun[p.g] = byGun[p.g] || []).push(p); });
function defInst(gid) {
  const def = (stats.guns[gid] || {}).preset;
  const p = (def && presets[def] && presets[def].g === gid) ? presets[def] : (byGun[gid] || [])[0];
  return (p && p.i) || {};
}

const OUT = path.join(ROOT, "docs/r19.15-theme-audit");
fs.mkdirSync(OUT, { recursive: true });

const MAIN_RANK = { muzzle: 0, gas_block: 1, barrel: 2, handguard: 3, receiver: 4 };
// 上游数据把 receiver 拼成 reciever，审计比较前统一
function mainBase(sid) {
  const b = api.gwSidBase(sid);
  return b === "reciever" ? "receiver" : b;
}
const TACTICAL = /^(tactical|flashlight|laser|devices|emitter)$/;

const allGun = { generatedFor: "R19.15", scanned: 0, anomalies: [], guns: [] };
const ash12 = {};
const tacticalLanes = { generatedFor: "R19.15", guns: [], summary: { rootTacticalGuns: 0, onTopRow: 0, fallbackRow6: 0, orderViolations: 0 } };

Object.keys(gunslots).forEach(function (gid) {
  const inst = GB.sanitize(ctx, gid, defInst(gid)).installed;
  const tree = GB.buildTree(ctx, gid, inst);
  const L = api.gwBuildLayout({ gunId: gid, installed: inst, slots: tree });
  const pad = L.topPad || 0;
  const name = (items[gid] || {}).n || gid;
  allGun.scanned++;

  const visibleTreeSlots = (L.roots || []).length;
  const placed = L.cells.length;
  const problems = [];

  // 1) 每个路径只允许出现一次（不得重复渲染真实槽位）
  const seen = {};
  L.cells.forEach(function (c) {
    if (seen[c.path]) { problems.push("重复槽位: " + c.path); }
    seen[c.path] = c;
  });
  // 2) 越界
  L.cells.forEach(function (c) {
    if (c.row < 1 || c.row > 6 + pad || c.col < 1 || c.col > 9) {
      problems.push("越界: " + c.path + " r" + c.row + "c" + c.col);
    }
  });
  // 3) 主体行：连续 + 紧邻枪身（多槽时）+ 顺序
  const mainRow = L.cells.filter(function (c) {
    return c.row === L.body.row &&
      MAIN_RANK[mainBase(tree.nodes[c.path].sid)] !== undefined;
  }).sort(function (a, b) { return a.col - b.col; });
  for (let i = 1; i < mainRow.length; i++) {
    if (mainRow[i].col !== mainRow[i - 1].col + 1) { problems.push("主体行不连续"); break; }
  }
  if (mainRow.length >= 2 && mainRow[mainRow.length - 1].col !== L.body.col - 1) {
    problems.push("主体行未紧邻枪身: c" + mainRow[mainRow.length - 1].col);
  }
  for (let i = 1; i < mainRow.length; i++) {
    const a = MAIN_RANK[mainBase(tree.nodes[mainRow[i - 1].path].sid)];
    const b = MAIN_RANK[mainBase(tree.nodes[mainRow[i].path].sid)];
    if (!(a < b)) { problems.push("主体行顺序错误"); break; }
  }
  // 4) 战术装置不得落在主体行；根级战术必须在 r2 或 r6
  const rootTact = L.cells.filter(function (c) {
    return TACTICAL.test(api.gwSidBase(tree.nodes[c.path].sid)) && !tree.nodes[c.path].parent;
  });
  rootTact.forEach(function (c) {
    if (c.row === L.body.row) { problems.push("根级战术槽落进主体行: " + c.path); }
    if (c.row !== 2 + pad && c.row !== 6 + pad) {
      problems.push("根级战术槽不在 r2/r6: " + c.path + " r" + c.row);
    }
  });
  // 5) 子槽不得在父件上方（顶部链除外：同列向上是明确规则）
  const aboveViolation = [];
  L.cells.forEach(function (c) {
    const par = tree.nodes[c.path].parent;
    if (!par || !seen[par]) { return; }
    const p = seen[par];
    const base = api.gwSidBase(tree.nodes[c.path].sid);
    const sameNested = api.gwSidBase(tree.nodes[par].sid) === base;
    const optical = /^(scope|mount|sight_rear|sight_front)$/.test(base);
    const mainRole = MAIN_RANK[mainBase(tree.nodes[c.path].sid)] !== undefined;
    if (c.row < p.row && !sameNested && !optical && !mainRole && !c.anchorSlot) {
      aboveViolation.push(c.path + " r" + c.row + " < 父 r" + p.row);
    }
  });
  if (aboveViolation.length) { problems.push("子槽在父件上方: " + aboveViolation[0]); }

  if (problems.length) {
    allGun.anomalies.push({ gun: name, id: gid, problems: problems.slice(0, 6) });
  }
  allGun.guns.push({
    gun: name, id: gid,
    treeSlots: Object.keys(tree.nodes).length,
    visibleSlots: visibleTreeSlots,
    placedCells: placed,
    rows: L.rows, topPad: pad,
    mainRow: mainRow.map(function (c) {
      return { slot: c.path, base: mainBase(tree.nodes[c.path].sid), row: c.row, col: c.col };
    }),
    rootTactical: rootTact.map(function (c) {
      return { slot: c.path, row: c.row, col: c.col };
    }),
    problems: problems.slice(0, 6)
  });

  // ASH-12 专项
  if (gid === "5cadfbf7ae92152ac412eeef") {
    ash12.gun = name; ash12.id = gid;
    ash12.body = L.body;
    ash12.rows = L.rows; ash12.topPad = pad;
    ash12.mainRow = mainRow.map(function (c) {
      return { slot: c.path, base: api.gwSidBase(tree.nodes[c.path].sid),
               row: c.row, col: c.col, item: inst[c.path] ? items[inst[c.path]].n : null };
    });
    ash12.rootTacticalSlots = rootTact.map(function (c) {
      return { slot: c.path, row: c.row, col: c.col };
    });
    ash12.exceptions = L.exceptions;
    ash12.before = {
      note: "修复前实测（docs/r19.14-layout-changes 时期的布局）：根级 mod_tactical_001/002 被塞进主体行 r3c3/r3c1",
      mainRowWas: [
        { slot: "mod_tactical_002", row: 3, col: 1 },
        { slot: "mod_muzzle", row: 3, col: 2 },
        { slot: "mod_tactical_001", row: 3, col: 3 },
        { slot: "mod_handguard", row: 3, col: 4 }
      ]
    };
    ash12.rootSlotData = (items[gid].slots || []).map(function (s) {
      return { sid: s.sid, label: s.label, allowCount: (s.allow || []).length };
    });
  }

  // 上导轨战术车道
  if (rootTact.length) {
    tacticalLanes.summary.rootTacticalGuns++;
    const onTop = rootTact.filter(function (c) { return c.row === 2 + pad; }).length;
    const onRow6 = rootTact.filter(function (c) { return c.row === 6 + pad; }).length;
    if (onTop) { tacticalLanes.summary.onTopRow++; }
    if (onRow6) { tacticalLanes.summary.fallbackRow6++; }
    // 上方行相对顺序：前照门 → 上导轨战术装置 → 瞄具 → 后照门
    const at = function (base, row) {
      return L.cells.filter(function (c) {
        return c.row === row && api.gwSidBase(tree.nodes[c.path].sid) === base;
      })[0] || null;
    };
    const fsC = at("sight_front", 2 + pad);
    const scC = at("scope", 2 + pad);
    const rsC = at("sight_rear", 2 + pad);
    const onTopSlots = rootTact.filter(function (c) { return c.row === 2 + pad; });
    const orderOk = onTopSlots.every(function (c) {
      const afterFront = !fsC || c.col > fsC.col;
      const beforeScope = !scC || c.col < scC.col;
      return afterFront && beforeScope;
    });
    tacticalLanes.guns.push({
      gun: name, id: gid,
      slots: rootTact.map(function (c) {
        return { slot: c.path, row: c.row, col: c.col,
                 lane: c.row === 2 + pad ? "r2 上导轨行" : (c.row === 6 + pad ? "r6 备用车道" : "其他") };
      }),
      topRowOrder: {
        frontSightCol: fsC ? fsC.col : null,
        tacticalCols: onTopSlots.map(function (c) { return c.col; }),
        scopeCol: scC ? scC.col : null,
        rearSightCol: rsC ? rsC.col : null,
        orderOk: orderOk
      },
      exceptions: L.exceptions.filter(function (e) { return /战术/.test(e.why || ""); })
    });
    if (!orderOk) {
      allGun.anomalies.push({ gun: name, id: gid, problems: ["上方行顺序错误（应为 前照门→战术→瞄具→照门）"] });
    }
  }
});

allGun.summary = {
  scanned: allGun.scanned,
  clean: allGun.scanned - allGun.anomalies.length,
  withAnomalies: allGun.anomalies.length,
  totalPlacedCells: allGun.guns.reduce(function (s, g) { return s + g.placedCells; }, 0)
};

const optic = {
  generatedFor: "R19.15",
  confirmedByGameplay: [
    {
      itemId: "5aa66c72e5b5b00016327c93",
      name: "Nightforce MagMount Multimount 34毫米一体式导轨基座",
      directSlots: 2,
      slots: [
        { sid: "mod_scope_000", purpose: "34mm 光学瞄准镜槽" },
        { sid: "mod_scope_001", purpose: "单倍瞄具 / 单倍瞄具底座槽" }
      ],
      evidence: "in-game-confirmed（用户 2026-10-26 实测）",
      dataCheck: (items["5aa66c72e5b5b00016327c93"].slots || []).map(function (s) { return s.sid; })
    }
  ],
  pendingVerification: {
    note: "其余瞄具/底座仅有上游快照单一来源，未做游戏内实测，本轮不改其槽位数量或用途。",
    count: 0,
    items: []
  }
};
Object.keys(items).forEach(function (id) {
  const it = items[id];
  if (String(it.pt || "") !== "Scope" && String(it.pt || "") !== "WeaponMod") { return; }
  const slots = it.slots || [];
  if (!slots.some(function (s) { return /scope|mount|sight/i.test(String(s.sid || "")); })) { return; }
  if (id === "5aa66c72e5b5b00016327c93") { return; }
  optic.pendingVerification.count++;
  if (optic.pendingVerification.items.length < 200) {
    optic.pendingVerification.items.push({
      id: id, name: it.n, declaredDirectSlots: slots.length,
      sids: slots.map(function (s) { return s.sid; })
    });
  }
});

fs.writeFileSync(path.join(OUT, "all-gun-slot-audit.json"), JSON.stringify(allGun, null, 2), "utf8");
fs.writeFileSync(path.join(OUT, "ash12-layout-audit.json"), JSON.stringify(ash12, null, 2), "utf8");
fs.writeFileSync(path.join(OUT, "tactical-slot-lanes.json"), JSON.stringify(tacticalLanes, null, 2), "utf8");
fs.writeFileSync(path.join(OUT, "optic-slot-audit.json"), JSON.stringify(optic, null, 2), "utf8");

console.log("guns:", allGun.scanned, "clean:", allGun.summary.clean, "anomalies:", allGun.summary.withAnomalies);
allGun.anomalies.slice(0, 5).forEach(function (a) { console.log("  ", a.gun, a.problems.slice(0, 2)); });
console.log("ASH-12 mainRow:", JSON.stringify(ash12.mainRow));
console.log("ASH-12 tactical:", JSON.stringify(ash12.rootTacticalSlots));
console.log("tactical lanes:", JSON.stringify(tacticalLanes.summary));
console.log("optic pending:", optic.pendingVerification.count);
