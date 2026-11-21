// R19.13 布局审计：把 app.js 的 gwBuildLayout() 抠到 node 上，用真实槽位树产出四份审计 JSON。
// 用法：node tools/r1913_audit.js   → docs/r19.13-layout-audit/{slot-mapping,foregrip-chains,muzzle-chains,handguard-extras}.json
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

const ctx = GB.context(items, stats);
const byGun = {};
Object.values(presets).forEach(function (p) { (byGun[p.g] = byGun[p.g] || []).push(p); });

function defaultInstalled(gunId) {
  // 预设 map 的**键**才是预设 id（值对象里没有 .id 字段）——必须按 key 取官方默认预设，
  // 否则会退回列表第一项（往往是改型预设，不是出厂默认）。
  const def = (stats.guns[gunId] || {}).preset;
  const p = (def && presets[def] && presets[def].g === gunId) ? presets[def]
    : (byGun[gunId] || [])[0];
  return (p && p.i) || {};
}
function baseOf(tree, p) { return api.gwSidBase(tree.nodes[p].sid); }
function pos(map, p) { return map[p] ? { row: map[p].row, col: map[p].col } : null; }

const slotMapping = {};
const foregripChains = {};
const muzzleChains = {};
const handguardExtras = {};
const summary = {
  guns: 0, frontSightAligned: 0, frontSightMisaligned: [],
  scopeAboveReceiver: 0, scopeMisplaced: [],
  rearSightOk: 0, rearSightMissing: 0,
  mpr45Anchored: 0, mpr45Guns: 0, mpr45ExtraLeftOk: 0, mpr45ExtraMisplaced: [],
  muzzleChains: 0, muzzleChainSameCol: 0, muzzleChainBreaks: [],
  foregrip: { direct: 0, upperLower: 0, viaRail: 0, root: 0, offParent: [], aboveParent: [] },
  handguardExtras: { total: 0, inRow6: 0, spills: [] },
  exceptions: []
};

Object.keys(byGun).forEach(function (gid) {
  const tree = GB.buildTree(ctx, gid, GB.sanitize(ctx, gid, defaultInstalled(gid)).installed);
  const L = api.gwBuildLayout({ gunId: gid, installed: defaultInstalled(gid), slots: tree });
  const byPath = {};
  L.cells.forEach(function (c) { byPath[c.path] = c; });
  const pad = L.topPad || 0;   // R19.14.2：顶部扩展后的行偏移
  const name = (items[gid] || {}).n;
  summary.guns++;

  function find(pred) { return L.cells.filter(pred)[0] || null; }
  const muzzle = find(function (c) { return baseOf(tree, c.path) === "muzzle" && !tree.nodes[c.path].parent; }) ||
                 find(function (c) { return baseOf(tree, c.path) === "muzzle"; });
  const frontSight = find(function (c) { return baseOf(tree, c.path) === "sight_front"; });
  const scope = L.row2 && L.row2.scope ? byPath[L.row2.scope] : null;
  const rearSight = L.row2 && L.row2.rearSight ? byPath[L.row2.rearSight] : null;
  const charge = find(function (c) { return baseOf(tree, c.path) === "charge" && c.row === 2 + pad && c.col === 9; });
  const mpr = L.row2 && L.row2.mpr45 ? byPath[L.row2.mpr45] : null;
  const handguard = find(function (c) { return /^(handguard|hand_guard)$/.test(baseOf(tree, c.path)); });
  const foregrips = L.cells.filter(function (c) { return baseOf(tree, c.path) === "foregrip"; });

  // ---- 1) 槽位映射 ----
  slotMapping[gid] = {
    gun: name,
    muzzle: muzzle ? { slot: muzzle.slot, row: muzzle.row, col: muzzle.col } : null,
    frontSight: frontSight ? {
      slot: frontSight.path, row: frontSight.row, col: frontSight.col,
      parent: tree.nodes[frontSight.path].parent,
      alignedWithMuzzle: !!(muzzle && frontSight.col === muzzle.col && frontSight.row === 2 + pad)
    } : null,
    scope: scope ? {
      slot: scope.path, row: scope.row, col: scope.col,
      parent: tree.nodes[scope.path].parent,
      aboveReceiver: scope.row === 2 + pad && scope.col === 5
    } : null,
    rearSight: rearSight ? {
      slot: rearSight.path, row: rearSight.row, col: rearSight.col,
      parent: tree.nodes[rearSight.path].parent,
      leftOfCharge: rearSight.row === 2 + pad && rearSight.col === 8
    } : null,
    charge: charge ? { slot: charge.path, row: charge.row, col: charge.col } : null,
    mpr45Slot: mpr ? {
      slot: mpr.path, row: mpr.row, col: mpr.col,
      parent: tree.nodes[mpr.path].parent,
      aboveHandguard: !!(handguard && mpr.col === handguard.col && mpr.row === 2 + pad)
    } : null,
    handguard: handguard ? { slot: handguard.path, row: handguard.row, col: handguard.col } : null,
    foregrips: foregrips.map(function (f) {
      return { slot: f.path, row: f.row, col: f.col, parent: tree.nodes[f.path].parent };
    }),
    row2: L.row2 ? {
      frontSight: L.row2.frontSight, scope: L.row2.scope,
      rearSight: L.row2.rearSight, mpr45: L.row2.mpr45,
      railExtras: L.row2.railExtras
    } : null,
    exceptions: L.exceptions
  };
  if (L.exceptions && L.exceptions.length) {
    L.exceptions.forEach(function (e) { summary.exceptions.push({ gun: name, path: e.path, why: e.why }); });
  }
  if (frontSight && muzzle) {
    // R19.15.2：燕尾槽基座固定锚点 r2c3 优先。枪口恰好在 c3 时，前照门按规则让位到同行最近空格，
    // 这是**已声明的锚点冲突例外**，单独计数，不算"未对齐"。
    const dvAtMuzzleCol = (L.cells || []).some(function (c) {
      return c.row === 2 + pad && c.col === muzzle.col && c.role === "dovetailMount";
    });
    if (frontSight.col === muzzle.col && frontSight.row === 2 + pad) { summary.frontSightAligned++; }
    else if (dvAtMuzzleCol && frontSight.row === 2 + pad) {
      summary.frontSightYieldedToDovetail = summary.frontSightYieldedToDovetail || [];
      summary.frontSightYieldedToDovetail.push({ gun: name, muzzle: muzzle.col, front: frontSight.col });
    }
    else { summary.frontSightMisaligned.push({ gun: name, muzzle: muzzle.col, front: frontSight.col }); }
  }
  if (scope) {
    if (scope.row === 2 + pad && scope.col === 5) { summary.scopeAboveReceiver++; }
    else { summary.scopeMisplaced.push({ gun: name, row: scope.row, col: scope.col }); }
  }
  if (rearSight) {
    if (rearSight.row === 2 + pad && rearSight.col === 8) { summary.rearSightOk++; }
    summary.rearSightMissing = summary.rearSightMissing; // 占位
  } else { summary.rearSightMissing++; }
  // 上方导轨配件（MPR45 子槽）必须在 MPR45 左侧
  if (mpr) {
    summary.mpr45Guns++;
    if (mpr.row === 2 + pad && mpr.col === 4) { summary.mpr45Anchored++; }
    (L.row2.railExtras || []).forEach(function (p) {
      const c = byPath[p];
      if (c && c.row === 2 + pad && c.col < 4) { summary.mpr45ExtraLeftOk++; }
      else if (c) { summary.mpr45ExtraMisplaced.push({ gun: name, path: p, row: c.row, col: c.col }); }
    });
  }

  // ---- 2) 前握把链 ----
  foregrips.forEach(function (f) {
    const chain = [];
    let cur = tree.nodes[f.path].parent;
    while (cur) {
      chain.unshift({ slot: cur, base: baseOf(tree, cur), pos: pos(byPath, cur) });
      cur = tree.nodes[cur].parent;
    }
    const kind = (function () {
      const bases = chain.map(function (x) { return x.base; });
      if (!chain.length) { return "root"; }
      if (chain[chain.length - 1].base === "mount") { return "viaRail"; }
      if (bases.filter(function (b) { return b === "handguard"; }).length >= 2 ||
          bases.some(function (b) { return b === "handguard_lower" || b === "handguard"; }) &&
          bases.filter(function (b) { return /handguard/.test(b); }).length >= 2) {
        return "upperLower";
      }
      return "direct";
    })();
    summary.foregrip[kind === "upperLower" ? "upperLower" : kind]++;
    const par = chain[chain.length - 1] || null;
    const pc = par ? par.pos : null;
    if (pc) {
      if (f.col !== pc.col) {
        summary.foregrip.offParent.push({ gun: name, slot: f.path, col: f.col, parentCol: pc.col });
      }
      if (f.row < pc.row) {
        summary.foregrip.aboveParent.push({ gun: name, slot: f.path, row: f.row, parentRow: pc.row });
      }
    }
    const forbiddenRow2 = f.row === 2 + pad || (f.row === 2 + pad && (f.col === 3 || f.col === 4));
    const forbiddenRow4 = f.row === 4 + pad && f.col >= 6 && f.col <= 9;
    foregripChains[gid + "|" + f.path] = {
      gun: name, kind: kind,
      chain: chain.concat([{ slot: f.path, base: "foregrip", pos: { row: f.row, col: f.col } }]),
      foregrip: { row: f.row, col: f.col, parent: tree.nodes[f.path].parent },
      sameColumnAsParent: !pc || f.col === pc.col,
      belowParent: !pc || f.row >= pc.row,
      forbiddenZone: forbiddenRow2 || forbiddenRow4,
      ok: (!pc || (f.col === pc.col && f.row >= pc.row)) && !forbiddenRow2 && !forbiddenRow4
    };
  });

  // ---- 3) 枪口链 ----
  if (muzzle) {
    const chain = [];
    (function walk(pp) {
      ((tree.nodes[pp] && tree.nodes[pp].children) || []).forEach(function (k) {
        if (baseOf(tree, k) === "sight_front" || baseOf(tree, k) === "sight_rear") { return; }
        chain.push({ slot: k, base: baseOf(tree, k), parent: tree.nodes[k].parent,
                     pos: pos(byPath, k) });
        walk(k);
      });
    })(muzzle.path);
    summary.muzzleChains++;
    // 未落位（例如同基名空副本被 gwSlotVisible 过滤）不算"链断裂"，单独计数
    const placed = chain.filter(function (c) { return c.pos; });
    const unplaced = chain.filter(function (c) { return !c.pos; });
    let sameCol = placed.length > 0 ? true : null;
    placed.forEach(function (c) {
      if (c.pos.col !== muzzle.col) { sameCol = false; }
    });
    if (sameCol !== false) { summary.muzzleChainSameCol++; }
    else { summary.muzzleChainBreaks.push({ gun: name, chain: chain.map(function (c) { return c.pos; }) }); }
    summary.muzzleUnplaced = (summary.muzzleUnplaced || 0) + unplaced.length;
    muzzleChains[gid] = {
      gun: name,
      muzzle: { slot: muzzle.path, row: muzzle.row, col: muzzle.col },
      chain: chain,
      sameColumn: sameCol,
      levels: chain.map(function (c) { return c.pos ? c.pos.row : null; })
    };
  }

  // ---- 4) 护木其余附件 ----
  if (handguard) {
    const extras = [];
    (function walkEx(pp) {
      ((tree.nodes[pp] && tree.nodes[pp].children) || []).forEach(function (k) {
        const b = baseOf(tree, k);
        if (b === "sight_front") { return; }
        if (L.row2 && (L.row2.mpr45 === k || L.row2.scope === k || L.row2.frontSight === k ||
                       L.row2.rearSight === k || (L.row2.railExtras || []).indexOf(k) >= 0)) { return; }
        // 第三行主体件（某些枪的护木下还嵌一层机匣/枪管）不算"护木其余附件"
        const kc = byPath[k];
        if (kc && kc.row === 3) { walkEx(k); return; }
        // 前握把链上的节点不算"其余附件"
        let onForeChain = false;
        Object.keys(foregripChains).forEach(function (key) {
          const ch = foregripChains[key].chain || [];
          if (ch.some(function (x) { return x.slot === k; })) { onForeChain = true; }
        });
        if (onForeChain) { return; }
        const c = byPath[k];
        extras.push({ slot: k, base: b, parent: tree.nodes[k].parent,
                      pos: c ? { row: c.row, col: c.col } : null });
        walkEx(k);
      });
    })(handguard.path);
    summary.handguardExtras.total += extras.length;
    extras.forEach(function (e) {
      if (e.pos && e.pos.row === 6 + pad) { summary.handguardExtras.inRow6++; }
      else if (e.pos) { summary.handguardExtras.spills.push({ gun: name, slot: e.slot, pos: e.pos }); }
    });
    handguardExtras[gid] = {
      gun: name,
      handguard: { slot: handguard.path, row: handguard.row, col: handguard.col },
      extras: extras,
      row6Count: extras.filter(function (e) { return e.pos && e.pos.row === 6 + pad; }).length
    };
  }
});

const OUT = path.join(ROOT, "docs", "r19.13-layout-audit");
fs.mkdirSync(path.join(OUT, "screenshots"), { recursive: true });
function write(name, obj) {
  fs.writeFileSync(path.join(OUT, name), JSON.stringify(obj, null, 1), "utf8");
}
write("slot-mapping.json", {
  schema: "eftmap.r19.13.slot-mapping/1",
  rules: {
    frontSight: "r2 · 与实际枪口同列（枪口在 c1 则 r2c1；无独立枪管槽、枪口在 c2 则 r2c2）",
    upperRailExtras: "r2c3 起向左（MPR45 备用导轨槽位的左侧）",
    mpr45: "r2c4（护木正上方；仅当真实槽位树允许安装 NcStar MPR45 时占用）",
    scope: "r2c5（上机匣正上方，不是枪身中间格）",
    rearSight: "r2c8（拉机柄左侧）",
    charge: "r2c9",
    muzzleChain: "枪口正下方同列逐行展开",
    foregrip: "护木正下方同列纵向（下护木/导轨转接件依次向下）",
    handguardExtras: "第六行空闲格，稳定从左到右"
  },
  summary: summary,
  guns: slotMapping
});
write("foregrip-chains.json", {
  schema: "eftmap.r19.13.foregrip-chains/1",
  rule: "A 直接安装：护木→前握把；B 上/下护木：上护木→下护木→前握把；C 导轨转接：…→导轨→前握把。全部同列、在父件正下方，不进 r2，不占 r4c6–c9。",
  summary: summary.foregrip,
  chains: foregripChains
});
write("muzzle-chains.json", {
  schema: "eftmap.r19.13.muzzle-chains/1",
  rule: "枪口 → 转接件 → 消音器… 沿枪口正下方同列逐行展开；层级超过 6 行时记录容量不足，不静默省略。",
  summary: { guns: summary.muzzleChains, sameColumn: summary.muzzleChainSameCol,
             breaks: summary.muzzleChainBreaks.length },
  chains: muzzleChains
});
write("handguard-extras.json", {
  schema: "eftmap.r19.13.handguard-extras/1",
  rule: "护木其余附件（非上方导轨、非前握把链、非前照门）优先放第六行，稳定从左到右；不覆盖枪口链/前握把链/固定锚点。",
  summary: summary.handguardExtras,
  guns: handguardExtras
});
console.log(JSON.stringify({
  written: OUT,
  guns: summary.guns,
  frontSightAligned: summary.frontSightAligned,
  frontSightMisaligned: summary.frontSightMisaligned.length,
  frontSightYieldedToDovetail: (summary.frontSightYieldedToDovetail || []),
  scopeAboveReceiver: summary.scopeAboveReceiver,
  scopeMisplaced: summary.scopeMisplaced.length,
  rearSightOk: summary.rearSightOk,
  mpr45: summary.mpr45Anchored + "/" + summary.mpr45Guns,
  railExtrasLeftOk: summary.mpr45ExtraLeftOk,
  muzzleChains: summary.muzzleChainSameCol + "/" + summary.muzzleChains,
  foregrip: summary.foregrip,
  handguardExtras: summary.handguardExtras
}, null, 1));
