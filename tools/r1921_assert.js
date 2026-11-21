// R19.15.1 断言探针：把本轮所有结构规则的判定压成一份可被 pytest 直接读取的 JSON。
// 覆盖：AXMC 上下机匣+后托 / M10 镜座 / 马林击锤链+扳机 / AK 燕尾槽 / 全量 163 把回归。
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
  "\nreturn {gwBuildLayout:gwBuildLayout,gwSidBase:gwSidBase,gwLaneOf:gwLaneOf,gwSlotVisible:gwSlotVisible,gwMainRole:gwMainRole};")(
  function (id) { return items[id] || null; }, items);
const ctx = GB.context(items, stats);

function defInst(gid) {
  const st = (stats.guns || {})[gid] || {};
  if (st.preset && presets[st.preset]) { return presets[st.preset].i || {}; }
  for (const pid in presets) { const p = presets[pid]; if (p && p.g === gid) { return p.i || {}; } }
  return {};
}
function layoutOf(gid) {
  const inst = GB.sanitize(ctx, gid, defInst(gid)).installed;
  const tree = GB.buildTree(ctx, gid, inst);
  const L = api.gwBuildLayout({ gunId: gid, installed: inst, slots: tree });
  const by = {};
  L.cells.forEach(function (c) { by[c.path] = c; });
  return { inst, tree, L, by };
}
const gidOf = function (prefix) {
  return Object.keys(gunslots).find(function (k) { return ((items[k] || {}).n || "").indexOf(prefix) === 0; });
};

const out = { checks: {}, guns: {} };

// ---- AXMC ----
const axmcId = gidOf("Accuracy International AXMC");
const A = layoutOf(axmcId);
const up = A.by["mod_pistol_grip/mod_reciever/mod_reciever"];
const low = A.by["mod_pistol_grip/mod_reciever"];
const stk = A.by["mod_pistol_grip/mod_stock"];
out.guns.axmc = { id: axmcId, rows: A.L.rows, topPad: A.L.topPad,
  upper: up && { r: up.row, c: up.col }, lower: low && { r: low.row, c: low.col },
  stock: stk && { r: stk.row, c: stk.col }, roles: A.L.roles };
out.checks.axmcUpperLeftOfBody = !!(up && up.row === A.L.body.row && up.col === A.L.body.col - 1);
out.checks.axmcLowerBelowUpper = !!(up && low && low.col === up.col && low.row === up.row + 1);
out.checks.axmcStockAtAnchor = !!(stk && stk.row === 3 && stk.col === 9);

// ---- M10 ----
const m10Id = gidOf("Sako TRG M10");
const M = layoutOf(m10Id);
const mm = M.by["mod_reciever/mod_mount"];
const ms = M.by["mod_reciever/mod_mount/mod_scope"];
out.guns.m10 = { id: m10Id, rows: M.L.rows, mount: mm && { r: mm.row, c: mm.col }, scope: ms && { r: ms.row, c: ms.col } };
out.checks.m10MountAboveBody = !!(mm && mm.row === M.L.body.row - 1);
out.checks.m10ScopeAboveMount = !!(mm && ms && ms.col === mm.col && ms.row === mm.row - 1);

// ---- 马林 MXLR ----
const marlinId = gidOf("马林 MXLR");
const R = layoutOf(marlinId);
const hm = R.by["mod_hammer"], cap = R.by["mod_hammer/mod_tactical"],
      trg = R.by["mod_trigger"], st = R.by["mod_stock"], lev = R.by["mod_charge"];
out.guns.marlin = { id: marlinId, rows: R.L.rows, topPad: R.L.topPad,
  hammer: hm && { r: hm.row, c: hm.col }, cap: cap && { r: cap.row, c: cap.col },
  trigger: trg && { r: trg.row, c: trg.col }, stock: st && { r: st.row, c: st.col },
  lever: lev && { r: lev.row, c: lev.col }, roles: R.L.roles,
  exceptions: R.L.exceptions };
out.checks.marlinHammerAboveStock = !!(hm && st && hm.col === st.col && hm.row === st.row - 1);
out.checks.marlinCapAboveHammer = !!(cap && hm && cap.col === hm.col && cap.row === hm.row - 1);
out.checks.marlinChainSameColumn = !!(hm && cap && st && hm.col === cap.col && hm.col === st.col);
out.checks.marlinTriggerAtR4C8 = !!(trg && trg.row === 4 && trg.col === 8);
out.checks.marlinNoFakeChargeAtR2C9 = !(lev && lev.row === 2 && lev.col === 9);

// ---- AK 燕尾槽：R19.15.3 用户指定固定锚点 r2c8 / 瞄具 r1c8 / 额外槽 r1c9，照门带 r2c6/r2c7 ----
let dvGuns = 0, dvTotal = 0, onAnchor = 0, svdsAtR2C7 = 0, opticAbove = 0, opticTotal = 0;
let sideRight = 0, sideTotal = 0;
let rsGuns = 0, rsAtC6 = 0, rsSecondAtC7 = 0, rsSecondTotal = 0, rsBad = 0;
let fsChecked = 0, fsAligned = 0;
const dvSample = [];
for (const gid of Object.keys(gunslots)) {
  const { L, tree, inst } = layoutOf(gid);
  const dv = L.cells.filter(function (c) { return c.role === "dovetailMount"; })
                    .sort(function (a, b) {
                      const ka = a.extraDovetail ? 1 : 0, kb = b.extraDovetail ? 1 : 0;
                      return ka !== kb ? ka - kb : a.col - b.col;
                    });
  if (!dv.length) { continue; }
  dvGuns++;
  const bodyRow = L.body.row;
  const muzzle = L.cells.filter(function (c) {
    return c.row === bodyRow && api.gwSidBase(tree.nodes[c.path].sid) === "muzzle";
  })[0] || null;
  // 照门带
  const rs = L.cells.filter(function (c) { return c.role === "rearSight" || c.role === "rearSight2"; })
                    .sort(function (a, b) { return a.col - b.col; });
  if (rs.length) {
    rsGuns++;
    if (rs[0].row === bodyRow - 1 && rs[0].col === 6) { rsAtC6++; } else { rsBad++; }
    if (rs[1]) {
      rsSecondTotal++;
      // R19.21：AKMP 子槽（三种父照门的子配件）在父照门正上方同列（如 r1c6）；
      // 其余第二照门相关槽位保持 R19.15.3 的 r2c7 带。两类都算落在规范位。
      const akmpAbove = rs[1].akmpSub || (rs[1].row === rs[0].row - 1 && rs[1].col === rs[0].col);
      if (akmpAbove && rs[1].col === 6 && rs[1].row === rs[0].row - 1) { rsSecondAtC7++; }
      else if (rs[1].row === bodyRow - 1 && rs[1].col === 7) { rsSecondAtC7++; }
      else { rsBad++; }
    }
  }
  // 前照门 = 枪口正上方
  const fsCell = L.cells.filter(function (c) {
    return api.gwSidBase(tree.nodes[c.path].sid) === "sight_front" && c.row === bodyRow - 1;
  })[0] || null;
  if (fsCell && muzzle) {
    fsChecked++;
    if (fsCell.col === muzzle.col) { fsAligned++; }
  }
  dv.forEach(function (c) {
    dvTotal++;
    const isPrimary = !c.extraDovetail;
    // R19.18：SVDS 的燕尾槽基座按用户指定固定在 r2c7（其余枪械仍是 r2c8）
    const isSvds = gid === "5c46fbd72e2216398b5a8c9c";
    if (isPrimary && isSvds && c.row === bodyRow - 1 && c.col === 7) { svdsAtR2C7++; }
    else if (isPrimary && c.row === bodyRow - 1 && c.col === 8) { onAnchor++; }
    const kids = L.cells.filter(function (x) { return x.anchorSlot === c.path; });
    const optic = kids.filter(function (x) { return api.gwSidBase(tree.nodes[x.path].sid) === "scope"; })[0] || null;
    if (optic) {
      opticTotal++;
      if (optic.row === c.row - 1 && optic.col === c.col) { opticAbove++; }
    }
    kids.filter(function (x) { return x !== optic; }).forEach(function (s) {
      sideTotal++;
      if (optic && s.col > optic.col) { sideRight++; }
    });
    if (dvSample.length < 6) {
      dvSample.push({ gun: items[gid].n, slot: c.path, row: c.row, col: c.col,
                      primary: isPrimary,
                      optic: optic ? { r: optic.row, c: optic.col } : null,
                      sides: kids.filter(function (x) { return x !== optic; })
                                 .map(function (x) { return { r: x.row, c: x.col, base: api.gwSidBase(tree.nodes[x.path].sid) }; }),
                      rearSights: rs.map(function (x) { return { r: x.row, c: x.col, role: x.role }; }),
                      item: (items[inst[c.path]] || {}).n || "" });
    }
  });
}
out.guns.dovetail = { guns: dvGuns, cells: dvTotal, onFixedAnchor: onAnchor,
                      svdsAtR2C7: svdsAtR2C7,
                      opticTotal: opticTotal, opticAbove: opticAbove,
                      sideTotal: sideTotal, sideRight: sideRight,
                      rearSightGuns: rsGuns, rearSightAtC6: rsAtC6,
                      secondRearSightTotal: rsSecondTotal, secondRearSightAtC7: rsSecondAtC7,
                      rearSightBad: rsBad,
                      frontSightChecked: fsChecked, frontSightAligned: fsAligned,
                      sample: dvSample };
out.checks.dovetailPrimaryAtR2C8 = dvGuns > 0 && onAnchor + svdsAtR2C7 === dvGuns;
out.checks.dovetailSvdsAtR2C7 = svdsAtR2C7 === 1;
out.checks.dovetailOpticAboveSameCol = opticAbove === opticTotal;
out.checks.dovetailSideRightOfOptic = sideRight === sideTotal;
out.checks.dovetailRearSightAtC6 = rsBad === 0 && rsGuns > 0 && rsAtC6 === rsGuns;
out.checks.dovetailSecondRearSightAtC7 = rsSecondAtC7 === rsSecondTotal;
out.checks.dovetailFrontSightAboveMuzzle = fsAligned === fsChecked;

// ---- 全量回归 ----
let clean = 0, bad = [];
for (const gid of Object.keys(gunslots)) {
  const { L, tree } = layoutOf(gid);
  const problems = [];
  const seen = {}, cellsSeen = {};
  L.cells.forEach(function (c) {
    if (seen[c.path]) { problems.push("dup " + c.path); }
    seen[c.path] = 1;
    const k = c.row + "|" + c.col;
    if (cellsSeen[k]) { problems.push("overlap " + k); }
    cellsSeen[k] = c.path;
    if (c.row < 1 || c.row > L.rows || c.col < 1 || c.col > 9) { problems.push("oob " + c.path); }
  });
  const bodyRow = L.body.row;
  L.cells.filter(function (c) { return c.row === bodyRow; }).forEach(function (c) {
    const b = api.gwSidBase(tree.nodes[c.path].sid);
    const ok = /^(muzzle|gas_block|gasblock|gas|barrel|handguard|hand_guard|reciever|receiver|slide|frame|upper|lower|stock)$/
      .test(b) || /^stock_/.test(b);
    if (!ok) { problems.push("非主体链进了本体行: " + c.path + " (" + b + ")"); }
  });
  if (problems.length) { bad.push({ gun: items[gid].n, id: gid, problems: problems }); } else { clean++; }
}
out.guns.all = { total: Object.keys(gunslots).length, clean: clean, bad: bad };
out.checks.allGunsClean = bad.length === 0;

out.ok = Object.keys(out.checks).every(function (k) { return out.checks[k]; });
console.log(JSON.stringify(out, null, 1));
