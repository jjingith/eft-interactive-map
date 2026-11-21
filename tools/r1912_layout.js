// R19.12 固定 6×9 画布探针：把 app.js 的 gwBuildLayout() 抠到 node 上，用真实槽位树跑。
// 用法：node tools/r1912_layout.js [gunId...]  → JSON 到 stdout
// 校验：行列恒为 6×9、固定锚点坐标、无重叠、无越界、父子锚定关系。
const fs = require("fs");
const path = require("path");
const ROOT = path.resolve(__dirname, "..");
const GB = require(path.join(ROOT, "gun_builder.js"));

const items = JSON.parse(fs.readFileSync(path.join(ROOT, "data/items.json"), "utf8")).items;
const stats = JSON.parse(fs.readFileSync(path.join(ROOT, "data/gun-stats.json"), "utf8"));
const presets = JSON.parse(fs.readFileSync(path.join(ROOT, "data/gun-presets.json"), "utf8")).presets || {};

const src = fs.readFileSync(path.join(ROOT, "app.js"), "utf8");
const block = src.slice(src.indexOf("function gwSidBase("), src.indexOf("function gwPartCard("));
const api = new Function("itemRec", "GW_ITEM_MAP", block + "\nreturn {gwBuildLayout:gwBuildLayout, gwSidBase:gwSidBase};")(
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

const REQ = {
  body: { row: 3, col: 6, span: 3 },
  stock: { row: 3, col: 9 },
  stockChild: { row: 4, col: 9 },
  mag: { row: 4, col: 7 },
  grip: { row: 4, col: 8 },
  ammo: { row: 5, col: 7 },
  charge: { row: 2, col: 9 }
};
const MAIN_COL = { muzzle: [1, 2], gas_block: [2, 3], barrel: [3], handguard: [4], receiver: [5] };

function baseOf(tree, p) { return api.gwSidBase(tree.nodes[p].sid); }

function check(gunId, installed) {
  const tree = GB.buildTree(ctx, gunId, installed);
  const L = api.gwBuildLayout({ gunId: gunId, installed: installed, slots: tree });
  const problems = [];
  const seen = {};
  // R19.14.2：顶部扩展时行数 = 6 + topPad，所有锚点同步下移 topPad
  const pad = L.topPad || 0;
  L.cells.forEach(function (c) {
    if (c.row < 1 || c.row > (6 + pad) || c.col < 1 || c.col > 9) {
      problems.push("越界: " + c.path + " r" + c.row + "c" + c.col);
    }
    const k = c.row + "|" + c.col;
    if (seen[k]) { problems.push("重叠: " + c.path + " 与 " + seen[k] + " @" + k); }
    seen[k] = c.path;
    if (c.row === 3 + pad && c.col >= 6 && c.col <= 8) { problems.push("压住枪身: " + c.path); }
  });
  if (L.rows !== 6 + pad || L.cols !== 9) { problems.push("网格不是 6×9(+pad): " + L.rows + "×" + L.cols); }
  if (L.grid && L.grid.baseRows !== 6) { problems.push("基准行数被改动: " + L.grid.baseRows); }
  if (L.body.row !== 3 + pad || L.body.col !== 6 || L.body.span !== 3) { problems.push("枪身不在 r3c6–c8"); }
  if (L.ammoRow !== 5 + pad || L.magCol !== 7) { problems.push("子弹/弹匣锚点错误"); }

  // 固定锚点：有该槽位时必须在指定坐标
  const find = function (pred) { return L.cells.filter(pred)[0] || null; };
  const stock = find(function (c) { return baseOf(tree, c.path) === "stock" && !tree.nodes[c.path].parent; });
  if (stock && (stock.row !== 3 + pad || stock.col !== 9)) {
    problems.push("枪托不在 r3c9: r" + stock.row + "c" + stock.col);
  }
  const mag = find(function (c) { return baseOf(tree, c.path) === "magazine" && !tree.nodes[c.path].parent; });
  if (mag && (mag.row !== 4 + pad || mag.col !== 7)) { problems.push("弹匣不在 r4c7: r" + mag.row + "c" + mag.col); }
  const grip = find(function (c) {
    return /^(pistol_grip|pistolgrip)$/.test(baseOf(tree, c.path)) && !tree.nodes[c.path].parent;
  });
  if (grip && (grip.row !== 4 + pad || grip.col !== 8)) { problems.push("后握把不在 r4c8: r" + grip.row + "c" + grip.col); }
  const charge = find(function (c) { return baseOf(tree, c.path) === "charge"; });
  // R19.15.1：杠杆步枪（有真实击锤槽）的拉机柄/环状杠杆让位给「击锤帽→击锤→枪托」链，
  // 改锚到枪托正下方 r4c9；其余枪械仍必须严格在 r2c9。
  if (charge) {
    const hasHammer = L.cells.some(function (c) { return baseOf(tree, c.path) === "hammer"; });
    const wantRow = hasHammer ? 4 : 2;
    if (charge.row !== wantRow + pad || charge.col !== 9) {
      problems.push("拉机柄不在 r" + wantRow + "c9: r" + charge.row + "c" + charge.col);
    }
  }

  const hasBarrel = L.cells.some(function (c) { return baseOf(tree, c.path) === "barrel"; });
  // R19.15：主体行改为「向枪身方向连续压缩」，不再固定列号。
  // 断言：① 全部在主体行；② 列号连续；③ 紧邻枪身左缘；④ 相对顺序不变。
  const RANK = { muzzle: 0, gas_block: 1, barrel: 2, handguard: 3, receiver: 4 };
  const mainRow = L.cells.filter(function (c) {
    return c.row === 3 + pad && RANK[gwRole(baseOf(tree, c.path))] !== undefined;
  }).sort(function (a, b) { return a.col - b.col; });
  if (mainRow.length) {
    for (let i = 1; i < mainRow.length; i++) {
      if (mainRow[i].col !== mainRow[i - 1].col + 1) {
        problems.push("主体行不连续: " + mainRow.map(function (x) { return x.col; }).join(","));
        break;
      }
    }
    // 多主体槽位必须压缩到紧邻枪身；只有一个主体槽位时保留规范列（不强行推到锚点上）
    if (mainRow.length >= 2) {
      const last = mainRow[mainRow.length - 1];
      if (last.col !== L.body.col - 1) {
        problems.push("主体行未紧邻枪身: 末列 c" + last.col + " 期望 c" + (L.body.col - 1));
      }
    }
    for (let i = 1; i < mainRow.length; i++) {
      const a = RANK[gwRole(baseOf(tree, mainRow[i - 1].path))];
      const b = RANK[gwRole(baseOf(tree, mainRow[i].path))];
      if (!(a < b)) {
        problems.push("主体行相对顺序错误: " + mainRow[i - 1].path + " → " + mainRow[i].path);
      }
    }
  }
  // 子件锚定：子槽要么在父件正下方，要么在父件同行/后续行（记录，不判错）
  const childOffsets = [];
  L.cells.forEach(function (c) {
    const par = tree.nodes[c.path].parent;
    if (!par) { return; }
    const pc = L.cells.filter(function (x) { return x.path === par; })[0];
    if (!pc) { return; }
    childOffsets.push({ path: c.path, parent: par, dr: c.row - pc.row, dc: c.col - pc.col });
  });

  return {
    gunId: gunId, name: (items[gunId] || {}).n,
    topPad: L.topPad || 0,
    grid: { rows: L.rows, cols: L.cols, baseRows: 6, cells: L.cells.length, emptyAnchors: L.emptyAnchors },
    hasBarrel: hasBarrel,
    cells: L.cells.map(function (c) {
      return { slot: c.path, base: baseOf(tree, c.path), row: c.row, col: c.col, lane: c.lane,
               parent: tree.nodes[c.path].parent, pinned: !!c.pinned, anchorSlot: c.anchorSlot || null };
    }),
    childOffsets: childOffsets,
    overflow: L.overflow,
    problems: problems
  };
}

function gwRole(base) {
  if (base === "muzzle") { return "muzzle"; }
  if (base === "gas_block" || base === "gasblock" || base === "gas") { return "gas_block"; }
  if (base === "barrel") { return "barrel"; }
  if (base === "handguard" || base === "hand_guard") { return "handguard"; }
  if (/^(reciever|receiver|slide|frame|upper|lower)$/.test(base)) { return "receiver"; }
  return null;
}

const ids = process.argv.slice(2);
const gunIds = ids.length ? ids : Object.keys(byGun);
const out = { schema: "eftmap.r19.12.layout/1", guns: {},
  summary: { guns: 0, problems: [], overflow: 0, noBarrelGuns: [],
             foregrip: { guns: 0, direct: 0, viaRail: 0, root: 0, sameRowAsMag: [], offParent: [] } } };

gunIds.forEach(function (gid) {
  try {
    const r = check(gid, GB.sanitize(ctx, gid, defaultInstalled(gid)).installed);
    out.guns[gid] = r;
    out.summary.guns++;
    if (r.problems.length) { out.summary.problems.push({ gun: r.name, id: gid, problems: r.problems }); }
    if (r.overflow.length) { out.summary.overflow += r.overflow.length; }
    if (!r.hasBarrel) { out.summary.noBarrelGuns.push(r.name); }
    // 前握把不变量：列对齐父件、行在父件正下方、不与弹匣同行
    const bySlot = {};
    r.cells.forEach(function (c) { bySlot[c.slot] = c; });
    const mags = r.cells.filter(function (c) { return c.base === "magazine"; });
    const fores = r.cells.filter(function (c) { return c.base === "foregrip"; });
    if (fores.length) { out.summary.foregrip.guns++; }
    fores.forEach(function (f) {
      const par = f.parent ? bySlot[f.parent] : null;
      if (!par) { out.summary.foregrip.root++; return; }
      if (par.base === "mount") { out.summary.foregrip.viaRail++; } else { out.summary.foregrip.direct++; }
      if (f.col !== par.col) {
        out.summary.foregrip.offParent.push({ gun: r.name, slot: f.slot, col: f.col, parentCol: par.col });
      }
      if (mags.length && f.row === mags[0].row) {
        out.summary.foregrip.sameRowAsMag.push({ gun: r.name, slot: f.slot, row: f.row });
      }
    });
  } catch (e) {
    out.guns[gid] = { error: String(e && e.message || e) };
    out.summary.problems.push({ gun: (items[gid] || {}).n, id: gid, problems: ["探针异常: " + e.message] });
  }
});
console.log(JSON.stringify(out, null, 1));
