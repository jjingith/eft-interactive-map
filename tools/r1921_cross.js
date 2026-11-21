// R19.15.1 三方对照审计：用每把枪**应用真实的默认装配清单**（从 localStorage 抓取）
// 重建真实槽位树 → 重算布局 → 与真实 DOM 渲染坐标逐格比对，并检查结构语义规则。
//
// 输入：docs/r19.15.1-layout-audit/dom-all-after.json（真实 DOM + 真实 installed）
// 输出：docs/r19.15.1-layout-audit/all-gun-layout-audit.json
const fs = require("fs"), path = require("path");
const ROOT = path.resolve(__dirname, "..");
const GB = require(path.join(ROOT, "gun_builder.js"));
const items = JSON.parse(fs.readFileSync(path.join(ROOT, "data/items.json"), "utf8")).items;
const stats = JSON.parse(fs.readFileSync(path.join(ROOT, "data/gun-stats.json"), "utf8"));
const src = fs.readFileSync(path.join(ROOT, process.env.GW_APP || "app.js"), "utf8");
const block = src.slice(src.indexOf("function gwSidBase("), src.indexOf("function renderGunSkin("));
const api = new Function("itemRec", "GW_ITEM_MAP", block +
  "\nreturn {gwBuildLayout:gwBuildLayout,gwSidBase:gwSidBase,gwLaneOf:gwLaneOf,gwSlotVisible:gwSlotVisible,gwMainRole:gwMainRole};")(
  function (id) { return items[id] || null; }, items);

const ctx = GB.context(items, stats);
const AUDIT_DIR = process.env.GW_AUDIT_DIR || "docs/r19.15.1-layout-audit";
const domPath = path.join(ROOT, AUDIT_DIR, "dom-all-after.json");
const dom = JSON.parse(fs.readFileSync(domPath, "utf8"));

const REC = /^(reciever|receiver|slide|frame|upper|lower)$/;
const MAIN_RANK = { muzzle: 0, gas_block: 1, barrel: 2, handguard: 3, receiver: 4 };

function baseOf(tree, p) { return api.gwSidBase(tree.nodes[p].sid); }
function normMain(b) { return b === "reciever" ? "receiver" : b; }

const out = {
  generatedFor: "R19.15.1",
  source: "dom-all-after.json（真实 DOM + localStorage 真实装配清单）+ gun_builder 真实槽位树 + gwBuildLayout 布局计算",
  scanned: 0,
  guns: [],
  anomalies: [],
  summary: {
    domTreeMismatch: 0, domCoordMismatch: 0, duplicatePath: 0, overlapCell: 0, outOfGrid: 0,
    zeroRow: 0, rowsChanged: 0, mainRowViolation: 0, opticBelowBody: 0, stockOffCol9: 0,
    receiverPairViolation: 0, hammerChainViolation: 0, triggerViolation: 0, phantomCard: 0,
    dovetailOffAnchor: 0, dovetailOpticOffColumn: 0, dovetailSideMisplaced: 0,
    dovetailRearSightBand: 0, dovetailFrontSightOffMuzzle: 0
  },
  classes: {
    opticMountsOnNonReceiverParents: [],
    notedExceptions: []
  }
};

for (const gid of Object.keys(dom.guns)) {
  const d = dom.guns[gid];
  const installed = d.installed || {};
  const tree = GB.buildTree(ctx, gid, installed);
  const N = tree.nodes;
  const L = api.gwBuildLayout({ gunId: gid, installed: installed, slots: tree });
  const pad = L.topPad || 0;
  const bodyRow = L.body.row;
  const bodyCol = L.body.col;
  const role = L.roles || {};

  const rec = {
    gun: d.gunName || (items[gid] || {}).n, id: gid,
    treeSlots: tree.order ? tree.order.length : Object.keys(N).length,
    visibleSlots: tree.order.filter(function (p) { return api.gwSlotVisible({ installed: installed, slots: tree }, p); }).length,
    renderedCards: (d.slots || []).length,
    domTreeSlotsAttr: d.treeSlots,
    placedCells: d.placedCells,
    installedCount: Object.keys(installed).length,
    rows: L.rows, topPad: pad, cols: L.cols, body: { row: bodyRow, col: bodyCol, span: L.body.span },
    domRows: d.rows, domCols: d.cols, rowHeights: d.rowHeights,
    roles: { receiverUpper: role.receiverUpper || null, receiverLower: role.receiverLower || null,
             stockOnGrip: role.stockOnGrip || null, stockUnderParent: role.stockUnderParent || null,
             hammer: role.hammer || null, trigger: role.trigger || null,
             topOptic: role.topOptic || [] },
    problems: [], moves: []
  };

  // ---- A. 真实树 vs 布局 vs DOM：路径与坐标必须一致 ----
  const engBy = {};
  L.cells.forEach(function (c) { engBy[c.path] = c; });
  const domBy = {};
  (d.slots || []).forEach(function (s) { domBy[s.slot] = s; });

  const onlyEng = Object.keys(engBy).filter(function (p) { return !domBy[p]; });
  const onlyDom = Object.keys(domBy).filter(function (p) { return !engBy[p]; });
  if (onlyEng.length || onlyDom.length) {
    out.summary.domTreeMismatch++;
    rec.problems.push("DOM 与布局不符：仅布局 " + JSON.stringify(onlyEng.slice(0, 3)) +
                      " 仅 DOM " + JSON.stringify(onlyDom.slice(0, 3)));
  }
  Object.keys(engBy).forEach(function (p) {
    const a = engBy[p], b = domBy[p];
    if (!b) { return; }
    if (a.row !== b.row || a.col !== b.col) {
      out.summary.domCoordMismatch++;
      rec.problems.push("坐标不一致 " + p + " 布局 r" + a.row + "c" + a.col + " DOM r" + b.row + "c" + b.col);
    }
  });

  // ---- B. 结构完整性 ----
  const seenPath = {}, seenCell = {};
  L.cells.forEach(function (c) {
    if (seenPath[c.path]) { out.summary.duplicatePath++; rec.problems.push("重复槽位 " + c.path); }
    seenPath[c.path] = 1;
    const k = c.row + "|" + c.col;
    if (seenCell[k]) { out.summary.overlapCell++; rec.problems.push("重叠 " + k + ": " + seenCell[k] + " / " + c.path); }
    seenCell[k] = c.path;
    if (c.row < 1 || c.row > L.rows || c.col < 1 || c.col > 9) {
      out.summary.outOfGrid++; rec.problems.push("越界 " + c.path + " r" + c.row + "c" + c.col);
    }
  });
  if ((d.rowHeights || []).some(function (h) { return h < 8; })) {
    out.summary.zeroRow++; rec.problems.push("存在高度塌缩的行： " + JSON.stringify(d.rowHeights));
  }
  if (L.rows !== 6 + pad) { rec.problems.push("行数不等于 6+topPad"); }

  // ---- C. 主体行：连续、紧邻本体、相对顺序正确 ----
  const mainCells = L.cells.filter(function (c) {
    return c.row === bodyRow && MAIN_RANK[normMain(baseOf(tree, c.path))] !== undefined
      && MAIN_RANK[normMain(baseOf(tree, c.path))] < 4;   // 机匣单独判定
  }).sort(function (a, b) { return a.col - b.col; });
  const recvCell = L.cells.filter(function (c) {
    return c.row === bodyRow && normMain(baseOf(tree, c.path)) === "receiver";
  })[0] || null;
  rec.mainRow = mainCells.map(function (c) {
    return { slot: c.path, base: normMain(baseOf(tree, c.path)), row: c.row, col: c.col };
  });
  const tail = role.receiverUpper ? 2 : 1;
  // 机匣自己占了本体左侧那一列时，主体块必须结束在它左边（否则会与机匣重位）
  const expectEnd = (recvCell ? recvCell.col : bodyCol - tail + 1) - 1;
  if (mainCells.length >= 2) {
    for (let i = 1; i < mainCells.length; i++) {
      if (mainCells[i].col !== mainCells[i - 1].col + 1) {
        out.summary.mainRowViolation++;
        rec.problems.push("主体行不连续：" + mainCells.map(function (x) { return x.col; }).join(","));
        break;
      }
    }
    const last = mainCells[mainCells.length - 1];
    if (last.col !== expectEnd) {
      out.summary.mainRowViolation++;
      rec.problems.push("主体行未紧邻本体：末列 c" + last.col + " 期望 c" + expectEnd);
    }
    const mbase = function (c) { return normMain(baseOf(tree, c.path)); };
    for (let i = 1; i < mainCells.length; i++) {
      const a = MAIN_RANK[mbase(mainCells[i - 1])], b = MAIN_RANK[mbase(mainCells[i])];
      if (!(a < b)) {
        out.summary.mainRowViolation++;
        rec.problems.push("主体行顺序错误：" + mainCells[i - 1].path + "(" + mbase(mainCells[i - 1]) +
                          ") → " + mainCells[i].path + "(" + mbase(mainCells[i]) + ")");
      }
    }
  }
  // 主体行只允许主体链角色
  L.cells.filter(function (c) { return c.row === bodyRow; }).forEach(function (c) {
    const b = normMain(baseOf(tree, c.path));
    const isMain = MAIN_RANK[b] !== undefined || b === "stock" || /^stock_/.test(b) || b === "tactical";
    if (!isMain) {
      // 非主体链角色落在本体行 → 记录（战术装置/瞄具等都不该在本体行）
      out.summary.mainRowViolation++;
      rec.problems.push("非主体链角色进入本体行：" + c.path + " (" + b + ")");
    }
  });

  // ---- D. 上/下机匣 ----
  if (role.receiverUpper) {
    const u = engBy[role.receiverUpper], l = role.receiverLower ? engBy[role.receiverLower] : null;
    rec.receiverUpper = u ? { slot: role.receiverUpper, row: u.row, col: u.col } : null;
    rec.receiverLower = l ? { slot: role.receiverLower, row: l.row, col: l.col } : null;
    if (!u || u.row !== bodyRow || u.col !== bodyCol - 1) {
      out.summary.receiverPairViolation++;
      rec.problems.push("上机匣不在本体左侧相邻列");
    }
    if (!l || !u || l.col !== u.col || l.row !== u.row + 1) {
      out.summary.receiverPairViolation++;
      rec.problems.push("下机匣不在上机匣正下方同列");
    }
  }

  // ---- E. 枪托 / 击锤 / 扳机 ----
  const stockCells = L.cells.filter(function (c) { return baseOf(tree, c.path) === "stock" || /^stock_/.test(baseOf(tree, c.path)); });
  rec.stock = stockCells.map(function (c) { return { slot: c.path, row: c.row, col: c.col, role: c.role || null }; });
  stockCells.forEach(function (c) {
    if (c.col !== 9) {
      out.summary.stockOffCol9++;
      rec.problems.push("枪托不在第 9 列：" + c.path + " r" + c.row + "c" + c.col);
    }
  });
  if (role.hammer) {
    const h = engBy[role.hammer];
    const st = engBy[role.stockOnGrip] || engBy[role.stockUnderParent] ||
               L.cells.filter(function (c) { return baseOf(tree, c.path) === "stock" && c.row === bodyRow; })[0];
    const caps = L.cells.filter(function (c) { return c.role === "hammerCap"; });
    rec.hammer = { slot: role.hammer, row: h ? h.row : null, col: h ? h.col : null,
                   caps: caps.map(function (c) { return { slot: c.path, row: c.row, col: c.col }; }) };
    if (!h || !st || h.col !== st.col || h.row !== st.row - 1) {
      out.summary.hammerChainViolation++;
      rec.problems.push("击锤不在枪托正上方同列");
    }
    caps.forEach(function (c, i) {
      if (c.col !== h.col || c.row !== h.row - 1 - i) {
        out.summary.hammerChainViolation++;
        rec.problems.push("击锤帽不在击锤正上方同列：" + c.path);
      }
    });
  }
  if (role.trigger) {
    const t = engBy[role.trigger];
    rec.trigger = t ? { slot: role.trigger, row: t.row, col: t.col } : null;
    const wantCol = bodyCol + L.body.span - 1;
    if (!t || t.row !== bodyRow + 1 || t.col !== wantCol) {
      out.summary.triggerViolation++;
      rec.problems.push("扳机不在本体正下方三格最右格 r" + (bodyRow + 1) + "c" + wantCol);
    }
  }

  // ---- E2. R19.15.3 AK 燕尾槽：基座 r2c8，照门带 r2c6/r2c7，瞄具 r1c8，额外槽在瞄具右侧 ----
  const dvCells = L.cells.filter(function (c) { return c.role === "dovetailMount"; })
                         .sort(function (a, b) {
                           const ka = a.extraDovetail ? 1 : 0, kb = b.extraDovetail ? 1 : 0;
                           return ka !== kb ? ka - kb : a.col - b.col;
                         });
  const rsCells = L.cells.filter(function (c) { return c.role === "rearSight" || c.role === "rearSight2"; })
                         .sort(function (a, b) { return a.col - b.col; });
  const fsCell = L.cells.filter(function (c) {
    return baseOf(tree, c.path) === "sight_front" && c.row === bodyRow - 1;
  })[0] || null;
  const muzzleCell = L.cells.filter(function (c) {
    return c.row === bodyRow && baseOf(tree, c.path) === "muzzle";
  })[0] || null;
  rec.dovetail = dvCells.map(function (c, i) {
    const kids = L.cells.filter(function (x) { return x.anchorSlot === c.path; });
    const optic = kids.filter(function (x) { return baseOf(tree, x.path) === "scope"; })[0] || null;
    const sides = kids.filter(function (x) { return x !== optic; })
                      .sort(function (a, b) { return a.row - b.row || a.col - b.col; });
    return {
      slot: c.path, row: c.row, col: c.col,
      expected: !c.extraDovetail ? { row: bodyRow - 1, col: 8 } : null,
      onFixedAnchor: !c.extraDovetail ? (c.row === bodyRow - 1 && c.col === 8) : null,
      primary: !c.extraDovetail,
      optic: optic ? { slot: optic.path, row: optic.row, col: optic.col } : null,
      opticAboveBase: !!(optic && optic.row === c.row - 1 && optic.col === c.col),
      sides: sides.map(function (x) {
        return { slot: x.path, base: baseOf(tree, x.path), row: x.row, col: x.col };
      }),
      item: (items[installed[c.path]] || {}).n || ""
    };
  });
  // 照门带只在燕尾槽枪上要求 r2c6/r2c7；非燕尾槽枪仍是既有 r2c8（不受本规则影响）
  rec.rearSightBand = rsCells.map(function (c, i) {
    const expCol = dvCells.length ? (i === 0 ? 6 : 7) : (8 - i);
    return { slot: c.path, row: c.row, col: c.col,
             expectedCol: expCol, isDovetailGun: dvCells.length > 0,
             ok: c.row === bodyRow - 1 && c.col === expCol };
  });
  rec.dovetailFrontSight = {
    slot: fsCell ? fsCell.path : null,
    row: fsCell ? fsCell.row : null,
    col: fsCell ? fsCell.col : null,
    muzzleCol: muzzleCell ? muzzleCell.col : null,
    ok: !fsCell || !muzzleCell || (fsCell.row === bodyRow - 1 && fsCell.col === muzzleCell.col)
  };
  rec.dovetail.forEach(function (d) {
    if (d.primary && !d.onFixedAnchor) {
      out.summary.dovetailOffAnchor++;
      rec.problems.push("燕尾槽基座不在固定锚点 r2c8：实际 r" + d.row + "c" + d.col);
    }
    if (d.optic && !d.opticAboveBase) {
      out.summary.dovetailOpticOffColumn++;
      rec.problems.push("燕尾槽瞄具槽不在基座正上方同列：" + d.optic.slot + " r" + d.optic.row + "c" + d.optic.col);
    }
    d.sides.forEach(function (s) {
      if (d.optic && (s.col <= d.optic.col)) {
        out.summary.dovetailSideMisplaced++;
        rec.problems.push("燕尾槽额外配件槽不在瞄具右侧：" + s.slot + " r" + s.row + "c" + s.col);
      }
    });
  });
  rec.rearSightBand.forEach(function (r) {
    if (!r.isDovetailGun) { return; }
    if (!r.ok) {
      out.summary.dovetailRearSightBand++;
      rec.problems.push("燕尾槽枪械照门槽不在 r2c" + r.expectedCol + "：" + r.slot + " r" + r.row + "c" + r.col);
    }
  });
  if (!rec.dovetailFrontSight.ok) {
    out.summary.dovetailFrontSightOffMuzzle++;
    rec.problems.push("前照门不在枪口正上方：r" + rec.dovetailFrontSight.row + "c" +
                      rec.dovetailFrontSight.col + " vs 枪口 c" + rec.dovetailFrontSight.muzzleCol);
  }

  // ---- F. 光学件不得低于本体行（镜座类）----
  function subtreeHasScope(pp) {
    const ks = (N[pp] && N[pp].children) || [];
    for (const k of ks) {
      if (api.gwSidBase(N[k].sid) === "scope") { return true; }
      if (subtreeHasScope(k)) { return true; }
    }
    return false;
  }
  function allowsOptic(pp) {
    for (const a of (N[pp].allow || [])) {
      const r = items[a] || {};
      for (const sl of (r.slots || [])) { if (api.gwSidBase(sl.sid) === "scope") { return true; } }
    }
    return false;
  }
  rec.optic = [];
  L.cells.forEach(function (c) {
    const b = baseOf(tree, c.path);
    if (b !== "mount" && b !== "scope") { return; }
    const isOptic = b === "scope" || subtreeHasScope(c.path) || allowsOptic(c.path);
    if (!isOptic) { return; }
    const par = N[c.path].parent;
    let pb = par ? baseOf(tree, par) : "";
    // 沿父链看是否挂在护木/枪管/枪口/枪托的附件链上（顶盖、侧导轨及其子槽）
    let anc = par, ancHit = "";
    while (anc) {
      const ab = baseOf(tree, anc);
      if (/^(barrel|gas_block|muzzle|handguard|hand_guard|stock)$/.test(ab) || /^stock_/.test(ab)) {
        ancHit = ab; break;
      }
      anc = N[anc].parent;
    }
    const item = { slot: c.path, base: b, row: c.row, col: c.col, parentBase: pb,
                   itemName: (items[installed[c.path]] || {}).n || "" };
    rec.optic.push(item);
    if (c.row > bodyRow) {
      if (ancHit || /^(barrel|gas_block|muzzle|handguard|hand_guard|stock)$/.test(pb)) {
        out.classes.opticMountsOnNonReceiverParents.push(Object.assign({ gun: rec.gun, id: gid, chainRoot: ancHit || pb }, item));
      } else {
        out.summary.opticBelowBody++;
        rec.problems.push("镜座/瞄具低于本体行：" + c.path + " r" + c.row + "c" + c.col);
      }
    }
  });

  out.scanned++;
  if (rec.problems.length) {
    out.anomalies.push({ gun: rec.gun, id: gid, problems: rec.problems });
  }
  out.guns.push(rec);
}

const o = path.join(ROOT, AUDIT_DIR, "all-gun-layout-audit.json");
fs.writeFileSync(o, JSON.stringify(out, null, 1));
console.log("scanned", out.scanned, "anomalies", out.anomalies.length);
console.log("summary", JSON.stringify(out.summary));
console.log("optic on non-receiver parents:", out.classes.opticMountsOnNonReceiverParents.length);
if (out.anomalies.length) { console.log("first anomalies:", JSON.stringify(out.anomalies.slice(0, 5), null, 1)); }
