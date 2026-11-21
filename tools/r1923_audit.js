// R19.15.3 AK 燕尾槽 / 照门带 / 光学链 专项审计
// 输出（docs/r19.15.3-layout-audit/）：
//   ak-dovetail-final.json        兼容枪械、基座槽位、目标坐标 r2c8 与实际坐标（布局 + DOM）
//   ak-dovetail-optic-chain.json  基座 → 瞄具槽（r1c8）→ 更高层，含同列与顶部扩展
//   ak-dovetail-sight-layout.json 照门带 r2c6/r2c7 + 前照门在枪口正上方
//   layout-conflicts.json         同一把枪第二个燕尾槽类基座、其它无法同时满足的项
const fs = require("fs");
const path = require("path");
const ROOT = path.resolve(__dirname, "..");
const GB = require(path.join(ROOT, "gun_builder.js"));

const AUDIT_DIR = process.env.GW_AUDIT_DIR || "docs/r19.15.3-layout-audit";
const items = JSON.parse(fs.readFileSync(path.join(ROOT, "data/items.json"), "utf8")).items;
const gunslots = JSON.parse(fs.readFileSync(path.join(ROOT, "data/gunslots.json"), "utf8")).guns;
const stats = JSON.parse(fs.readFileSync(path.join(ROOT, "data/gun-stats.json"), "utf8"));
const presets = JSON.parse(fs.readFileSync(path.join(ROOT, "data/gun-presets.json"), "utf8")).presets || {};

const src = fs.readFileSync(path.join(ROOT, "app.js"), "utf8");
const blockSrc = src.slice(src.indexOf("function gwSidBase("), src.indexOf("function renderGunSkin("));
const api = new Function("itemRec", "GW_ITEM_MAP",
  blockSrc + "\nreturn {gwBuildLayout:gwBuildLayout,gwSidBase:gwSidBase,gwSlotVisible:gwSlotVisible};")(
  function (id) { return items[id] || null; }, items);

const ctx = GB.context(items, stats);
function defInst(gid) {
  const st = stats.guns[gid] || {};
  if (st.preset && presets[st.preset]) { return presets[st.preset].i || {}; }
  for (const pid in presets) {
    const p = presets[pid];
    if (p && p.g === gid) { return p.i || {}; }
  }
  return {};
}
function baseOf(sid) {
  return String(sid || "").replace(/^mod_/, "").replace(/#\d+$/, "").replace(/_\d{3,}$/, "");
}

// R19.29 任务D：与 app.js gwIsAkRearSightGun 逐字一致的结构判定（不按枪名），
// 供 nonDovetailSample 标注「AK 照门系」——这类枪的照门按 R19.28 需求一锚定 r2c6。
const AK_REAR_IDS = {
  "59d650cf86f7741b846413a4": 1, "5a0eb980fcdbcb001a3b00a6": 1, "5649b0544bdc2d1b2b8b458a": 1,
  "5ac72e475acfc400180ae6fe": 1, "5ac733a45acfc400192630e2": 1, "5bf3f59f0db834001a6fa060": 1,
  "649ec2cec93611967b03495e": 1, "628a7b23b0f75035732dd565": 1
};
function isAkRearSightGun(tree) {
  const N = tree.nodes || {}, order = tree.order || [];
  for (let i = 0; i < order.length; i++) {
    const n = N[order[i]];
    if (!n || n.parent) { continue; }
    if (baseOf(n.sid) !== "sight_rear") { continue; }
    const allow = n.allow || [];
    for (let a = 0; a < allow.length; a++) { if (AK_REAR_IDS[allow[a]]) { return true; } }
  }
  return false;
}

// ---- DOM 侧数据（真实浏览器扫描结果，可选） ----
let dom = null;
const domPath = path.join(ROOT, AUDIT_DIR, "dom-all-after.json");
if (fs.existsSync(domPath)) {
  dom = JSON.parse(fs.readFileSync(domPath, "utf8"));
}
function domOf(gid) {
  if (!dom || !dom.guns) { return null; }
  return dom.guns[gid] || null;
}
function domPos(m, slotPath) {
  if (!m || !m.slots) { return null; }
  const s = m.slots.filter(function (x) { return x.slot === slotPath; })[0];
  if (!s) { return null; }
  return { row: s.row, col: s.col, x: s.x, y: s.y, w: s.w, h: s.h, empty: s.empty, item: s.item };
}

const finalOut = {
  generatedFor: "R19.15.3",
  rule: {
    dovetailMount: "r2c8（本体第三行正上方一行、本体右侧第 3 列）",
    opticSlot: "r1c8（基座正上方同列）",
    sideSlot: "r1c9（瞄具槽右侧）",
    rearSight1: "r2c6",
    rearSight2: "r2c7（仅在真实槽位存在时出现）",
    frontSight: "枪口槽正上方（不受燕尾槽规则影响）",
    evidence: "in-game-confirmed（用户 R19.15.2→R19.15.3 任务书指定的固定坐标）"
  },
  compatibleGuns: [],
  summary: {
    guns: 0, mountSlots: 0, primaryOnR2C8: 0, secondaryMounts: 0,
    domChecked: 0, domMatch: 0, domMismatch: []
  }
};
const chainOut = {
  generatedFor: "R19.15.3",
  rule: { opticAboveMount: "同一列、基座上方的第一行（r2c8 → r1c8）", stacking: "更高层继续向上，超顶部走 topPad" },
  guns: [],
  summary: { gunsWithOpticSlot: 0, sameColumn: 0, childAbove: 0, topPadGuns: 0, mismatches: [] }
};
const sightOut = {
  generatedFor: "R19.15.3",
  rule: {
    rearSight1: "r2c6（仅限真实兼容 AK 燕尾槽的枪械）",
    rearSight2: "r2c7（仅在真实存在第二个照门相关槽位时显示）",
    frontSight: "真实枪口槽正上方（全枪械不变）",
    scope: "不受本规则影响（非燕尾槽枪仍按 r2c5 / r2c8 既有锚点）"
  },
  guns: [],
  nonDovetailSample: [],
  summary: {
    dovetailGuns: 0, withRearSight: 0, rearSightAtC6: 0, secondAtC7: 0,
    frontSightChecked: 0, frontSightAligned: 0, violations: []
  }
};
const conflictOut = {
  generatedFor: "R19.15.3",
  userFixedAnchors: {
    "r2c6": "第一个真实照门相关槽位（仅燕尾槽枪）",
    "r2c7": "第二个真实照门相关槽位（仅燕尾槽枪）",
    "r2c8": "AK 燕尾槽基座",
    "r1c8": "基座对应的光学瞄具槽",
    "r1c9": "光学槽右侧的额外真实配件槽"
  },
  conflicts: [],
  resolvedByDesign: [],
  blocking: []
};

let gunCount = 0;
for (const gid of Object.keys(gunslots)) {
  gunCount++;
  const inst = GB.sanitize(ctx, gid, defInst(gid)).installed;
  const tree = GB.buildTree(ctx, gid, inst);
  const N = tree.nodes;
  const L = api.gwBuildLayout({ gunId: gid, installed: inst, slots: tree });
  const pad = L.topPad || 0;
  const bodyRow = L.body.row;
  const name = items[gid].n;
  const m = domOf(gid);

  // 主基座 = fixedAnchor r2c8 / extraDovetail=false 的那个；其余为第二个真实接口。
  // 不能按列号排序取第一个（第二个接口可能落在 c1，会误判成主基座）。
  const dvCells = L.cells.filter(function (c) { return c.role === "dovetailMount"; })
                         .sort(function (a, b) {
                           var ka = a.extraDovetail ? 1 : 0, kb = b.extraDovetail ? 1 : 0;
                           if (ka !== kb) { return ka - kb; }
                           return a.col - b.col;
                         });
  if (!dvCells.length) {
    // 非燕尾槽枪：记录前照门/照门既有锚点，供「不受影响」对照
    const rs = L.cells.filter(function (c) { return c.role === "rearSight"; })[0];
    const fsCell = L.cells.filter(function (c) {
      return baseOf(N[c.path].sid) === "sight_front" && c.row === 2 + pad;
    })[0];
    const muzzle = L.cells.filter(function (c) {
      return c.row === bodyRow && baseOf(N[c.path].sid) === "muzzle";
    })[0];
    if (sightOut.nonDovetailSample.length < 12 && (rs || fsCell)) {
      sightOut.nonDovetailSample.push({
        gun: name, id: gid,
        akRearFamily: isAkRearSightGun(tree),   // R19.29：AK 照门系 → 需求一锚定 r2c6
        rearSight: rs ? { slot: rs.path, row: rs.row, col: rs.col } : null,
        frontSight: fsCell ? { slot: fsCell.path, row: fsCell.row, col: fsCell.col } : null,
        muzzleCol: muzzle ? muzzle.col : null,
        frontSightAligned: !fsCell || !muzzle || (fsCell.col === muzzle.col && fsCell.row === bodyRow - 1)
      });
    }
    continue;
  }

  // ---------- 基座 ----------
  const gunRec = {
    gun: name, gunId: gid, bodyRow: bodyRow, topPad: pad, rows: L.rows,
    mounts: []
  };
  dvCells.forEach(function (c, i) {
    const node = N[c.path];
    const allow = node.allow || [];
    const scopeAllow = allow.filter(function (a) { return String((items[a] || {}).pt || "") === "Scope"; });
    const kids = L.cells.filter(function (x) { return x.anchorSlot === c.path; });
    const optic = kids.filter(function (x) { return baseOf(N[x.path].sid) === "scope"; })[0] || null;
    const sides = kids.filter(function (x) { return x !== optic; });
    const dp = domPos(m, c.path);
    const primary = !c.extraDovetail;
    const targetRow = 2 + pad, targetCol = 8;
    const rec = {
      slotPath: c.path,
      slotId: node.sid,
      installedItemId: inst[c.path] || null,
      installedItemName: (items[inst[c.path]] || {}).n || "",
      allowScopeIds: scopeAllow,
      allowScopeNames: scopeAllow.map(function (a) { return (items[a] || {}).n; }),
      primary: primary,
      target: primary ? { row: targetRow, col: targetCol, label: "r2c8" }
                      : { row: null, col: null, label: "第二个真实燕尾槽类基座（未在用户坐标表中指定）" },
      actualRow: c.row, actualCol: c.col,
      actualLabel: "r" + c.row + "c" + c.col,
      onFixedAnchor: primary ? (c.row === targetRow && c.col === 8) : null,
      dom: dp ? { row: dp.row, col: dp.col, x: dp.x, y: dp.y, w: dp.w, h: dp.h } : null,
      domMatches: dp ? (dp.row === c.row && dp.col === c.col) : null,
      opticSlot: optic ? optic.path : null,
      sideSlots: sides.map(function (x) { return x.path; }),
      role: c.role
    };
    gunRec.mounts.push(rec);

    finalOut.summary.mountSlots++;
    if (primary) {
      if (rec.onFixedAnchor) { finalOut.summary.primaryOnR2C8++; }
      else {
        conflictOut.blocking.push({
          gun: name, gunId: gid, slotPath: c.path, slotId: node.sid,
          target: "r2c8", actual: rec.actualLabel,
          reason: "主燕尾槽基座未落在用户指定锚点"
        });
      }
    } else {
      finalOut.summary.secondaryMounts++;
      conflictOut.conflicts.push({
        gun: name, gunId: gid,
        kind: "second-dovetail-interface",
        slotPath: c.path, slotId: node.sid,
        target: "用户坐标表只规定主基座 r2c8",
        actual: rec.actualLabel,
        detail: "同一把枪存在第二个真实燕尾槽类接口（另一套独立 allow 清单）。保留该真实槽位不合并，" +
                "按避让规则放到 r2c" + c.col + "，不占用 r2c6/r2c7 照门带与 r2c8 主锚点。",
        status: "resolved-by-rule"
      });
      conflictOut.resolvedByDesign.push({ gun: name, slotPath: c.path, actual: rec.actualLabel });
    }
    if (dp) {
      finalOut.summary.domChecked++;
      if (rec.domMatches) { finalOut.summary.domMatch++; }
      else {
        finalOut.summary.domMismatch.push({
          gun: name, id: gid, slotPath: c.path,
          layout: { row: c.row, col: c.col },
          dom: { row: dp.row, col: dp.col }
        });
      }
    }
  });
  finalOut.compatibleGuns.push(gunRec);
  finalOut.summary.guns++;

  // ---------- 光学链 ----------
  const chainGun = { gun: name, gunId: gid, base: null, optic: null, chain: [], rows: L.rows, topPad: pad };
  const primaryCell = dvCells.filter(function (c) { return !c.extraDovetail; })[0] || dvCells[0];
  chainGun.base = { slot: primaryCell.path, row: primaryCell.row, col: primaryCell.col };
  const primaryKids = L.cells.filter(function (x) { return x.anchorSlot === primaryCell.path; });
  const opticCell = primaryKids.filter(function (x) { return baseOf(N[x.path].sid) === "scope"; })[0] || null;
  if (opticCell) {
    chainOut.summary.gunsWithOpticSlot++;
    chainGun.optic = {
      slot: opticCell.path,
      row: opticCell.row, col: opticCell.col,
      target: { row: primaryCell.row - 1, col: primaryCell.col },
      sameColumn: opticCell.col === primaryCell.col,
      directlyAbove: opticCell.row === primaryCell.row - 1,
      dom: domPos(m, opticCell.path)
    };
    if (chainGun.optic.sameColumn) { chainOut.summary.sameColumn++; }
    if (chainGun.optic.directlyAbove) { chainOut.summary.childAbove++; }
    else {
      chainOut.summary.mismatches.push({
        gun: name, slot: opticCell.path, base: chainGun.base, optic: chainGun.optic
      });
    }
    // 继续向上收集真实子槽（含顶部扩展后的行）
    (function walk(pp, depth) {
      if (depth > 8) { return; }
      (N[pp].children || []).forEach(function (k) {
        const cc = L.cells.filter(function (x) { return x.path === k; })[0];
        if (!cc) { return; }
        chainGun.chain.push({ slot: k, row: cc.row, col: cc.col, depth: depth + 1,
                              item: (items[inst[k]] || {}).n || "" });
        walk(k, depth + 1);
      });
    })(opticCell.path, 0);
    chainGun.chainSameColumn = chainGun.chain.every(function (x) { return x.col === primaryCell.col; });
  }
  const sideCells = primaryKids.filter(function (x) { return x !== opticCell; });
  chainGun.sides = sideCells.map(function (x) {
    return { slot: x.path, row: x.row, col: x.col, base: baseOf(N[x.path].sid),
             rightOfOptic: opticCell ? x.col > opticCell.col : null };
  });
  if (pad > 0) { chainOut.summary.topPadGuns++; }
  chainOut.guns.push(chainGun);

  // ---------- 照门带 + 前照门 ----------
  const rsCells = L.cells.filter(function (c) {
    return c.role === "rearSight" || c.role === "rearSight2";
  }).sort(function (a, b) { return a.col - b.col; });
  const fsCell = L.cells.filter(function (c) {
    return baseOf(N[c.path].sid) === "sight_front" && c.row === bodyRow - 1;
  })[0] || null;
  const muzzleCell = L.cells.filter(function (c) {
    return c.row === bodyRow && baseOf(N[c.path].sid) === "muzzle";
  })[0] || null;
  const sightRec = {
    gun: name, gunId: gid, topPad: pad,
    rearSights: rsCells.map(function (c, i) {
      return {
        slot: c.path, slotId: N[c.path].sid, role: c.role,
        expectedCol: i === 0 ? 6 : 7,
        actualRow: c.row, actualCol: c.col,
        ok: c.row === bodyRow - 1 && c.col === (i === 0 ? 6 : 7),
        dom: domPos(m, c.path)
      };
    }),
    frontSight: fsCell ? { slot: fsCell.path, row: fsCell.row, col: fsCell.col } : null,
    muzzle: muzzleCell ? { slot: muzzleCell.path, col: muzzleCell.col } : null,
    frontSightOk: !fsCell || !muzzleCell || (fsCell.row === bodyRow - 1 && fsCell.col === muzzleCell.col)
  };
  sightOut.summary.dovetailGuns++;
  if (rsCells.length) {
    sightOut.summary.withRearSight++;
    if (rsCells[0].col === 6 && rsCells[0].row === bodyRow - 1) { sightOut.summary.rearSightAtC6++; }
    else {
      sightOut.summary.violations.push({
        gun: name, slot: rsCells[0].path, expected: "r2c6", actual: "r" + rsCells[0].row + "c" + rsCells[0].col
      });
    }
    if (rsCells[1]) {
      const second = rsCells[1];
      // R19.21：AKMP 子槽（rearSight2）应在父照门**正上方同列**（r1cX），不是 r2c7。
      // 旧规则一律要求 r2c7，会把 8 把 AK 的 AKMP 子槽误报成违规——此处按结构区分。
      const isAkmpAbove = second.col === rsCells[0].col && second.row === rsCells[0].row - 1;
      if (isAkmpAbove) {
        sightOut.summary.akmpAbove = (sightOut.summary.akmpAbove || 0) + 1;
      } else if (second.col === 7 && second.row === bodyRow - 1) {
        sightOut.summary.secondAtC7++;
      } else {
        sightOut.summary.violations.push({
          gun: name, slot: second.path, expected: "r2c7 或 父件正上方同列",
          actual: "r" + second.row + "c" + second.col
        });
      }
    }
  }
  if (fsCell) {
    sightOut.summary.frontSightChecked++;
    if (sightRec.frontSightOk) { sightOut.summary.frontSightAligned++; }
    else {
      sightOut.summary.violations.push({
        gun: name, slot: fsCell.path, expected: "枪口 c" + (muzzleCell ? muzzleCell.col : "?"),
        actual: "r" + fsCell.row + "c" + fsCell.col
      });
    }
  }
  sightOut.guns.push(sightRec);

  // ---------- 其它冲突 ----------
  L.exceptions.forEach(function (e) {
    if (/燕尾槽|照门|前照门/.test(e.why || "")) {
      conflictOut.conflicts.push({ gun: name, gunId: gid, kind: "layout-exception", slotPath: e.path, detail: e.why });
    }
  });
}

finalOut.scannedGuns = gunCount;
sightOut.scannedGuns = gunCount;
chainOut.scannedGuns = gunCount;

const outDir = path.join(ROOT, AUDIT_DIR);
fs.mkdirSync(outDir, { recursive: true });
fs.writeFileSync(path.join(outDir, "ak-dovetail-final.json"), JSON.stringify(finalOut, null, 1), "utf8");
fs.writeFileSync(path.join(outDir, "ak-dovetail-optic-chain.json"), JSON.stringify(chainOut, null, 1), "utf8");
fs.writeFileSync(path.join(outDir, "ak-dovetail-sight-layout.json"), JSON.stringify(sightOut, null, 1), "utf8");
fs.writeFileSync(path.join(outDir, "layout-conflicts.json"), JSON.stringify(conflictOut, null, 1), "utf8");

console.log("scanned guns:", gunCount);
console.log("dovetail guns:", finalOut.summary.guns,
  "| mount slots:", finalOut.summary.mountSlots,
  "| primary@r2c8:", finalOut.summary.primaryOnR2C8,
  "| secondary:", finalOut.summary.secondaryMounts);
console.log("DOM:", finalOut.summary.domChecked, "checked /", finalOut.summary.domMatch, "match /",
  finalOut.summary.domMismatch.length, "mismatch");
console.log("optic chain: guns", chainOut.summary.gunsWithOpticSlot, "sameCol", chainOut.summary.sameColumn,
  "above", chainOut.summary.childAbove, "topPad", chainOut.summary.topPadGuns);
console.log("sight band: guns", sightOut.summary.dovetailGuns, "withRS", sightOut.summary.withRearSight,
  "atC6", sightOut.summary.rearSightAtC6, "secondC7", sightOut.summary.secondAtC7,
  "frontSight", sightOut.summary.frontSightAligned + "/" + sightOut.summary.frontSightChecked,
  "violations", sightOut.summary.violations.length);
console.log("conflicts:", conflictOut.conflicts.length, "blocking:", conflictOut.blocking.length);
