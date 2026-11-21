// R19.10 布局探针：把 app.js 里的 gwBuildLayout() 抠到 node 上，用真实槽位树跑。
// 用法：node tools/r1910_layout.js [gunId...]
// 输出每个格子的 row/col/lane/parent + 前握把锚点校验结果（JSON 到 stdout）。
const fs = require("fs");
const path = require("path");
const ROOT = path.resolve(__dirname, "..");
const GB = require(path.join(ROOT, "gun_builder.js"));

const items = JSON.parse(fs.readFileSync(path.join(ROOT, "data/items.json"), "utf8")).items;
const stats = JSON.parse(fs.readFileSync(path.join(ROOT, "data/gun-stats.json"), "utf8"));
const presetFile = JSON.parse(fs.readFileSync(path.join(ROOT, "data/gun-presets.json"), "utf8"));
const presets = presetFile.presets || {};

const src = fs.readFileSync(path.join(ROOT, "app.js"), "utf8");
const a = src.indexOf("function gwSidBase(");
const b = src.indexOf("function gwPartCard(");
const block = src.slice(a, b);
const api = new Function("itemRec", block + "\nreturn {gwBuildLayout:gwBuildLayout, gwSidBase:gwSidBase};")(
  function (id) { return items[id] || null; }
);

const ctx = GB.context(items, stats);
const byGun = {};
Object.keys(presets).forEach(function (k) {
  const p = presets[k];
  (byGun[p.g] = byGun[p.g] || []).push(p);
});

function buildFor(gunId, installedOverride) {
  let inst = installedOverride;
  if (!inst) {
    const list = byGun[gunId] || [];
    const def = (stats.guns[gunId] || {}).preset;
    const p = list.filter(function (x) { return x.id === def; })[0] || list[0];
    inst = (p && p.i) || {};
  }
  const tree = GB.buildTree(ctx, gunId, inst);
  return { tree: tree, installed: inst };
}

function layoutOf(gunId) {
  const env = buildFor(gunId);
  const L = api.gwBuildLayout({ gunId: gunId, installed: env.installed, slots: env.tree });
  return { L: L, tree: env.tree, installed: env.installed };
}

const ids = process.argv.slice(2);
const gunIds = ids.length ? ids : Object.keys(byGun);
const out = { guns: {}, summary: { foregripGuns: 0, direct: 0, viaRail: 0, root: 0, bad: [] } };

gunIds.forEach(function (gid) {
  let r = null;
  try { r = layoutOf(gid); } catch (e) { out.guns[gid] = { error: String((e && e.message) || e) }; return; }
  const L = r.L, tree = r.tree;
  const cells = L.cells.map(function (c) {
    const node = tree.nodes[c.path];
    return {
      slot: c.path, base: api.gwSidBase(node.sid), parent: node.parent || "",
      lane: c.lane, row: c.row, col: c.col, pinned: !!c.pinned, viaRail: !!c.viaRail,
      installed: r.installed[c.path] || ""
    };
  });
  out.guns[gid] = { name: (items[gid] || {}).n, cols: L.cols, rows: L.rows, topPad: L.topPad || 0,
                    ammoRow: L.ammoRow, magCol: L.magCol, body: L.body, cells: cells };
});

// 全局自检：任意两格不得同格、不得越界、不得压住枪身 3 列
Object.keys(out.guns).forEach(function (gid) {
  const G = out.guns[gid];
  if (G.error) { return; }
  const seen = {};
  G.cells.forEach(function (c) {
    const k = c.row + "|" + c.col;
    if (c.col < 1 || c.row < 1) { out.summary.bad.push({ gun: G.name, slot: c.slot, problems: ["坐标越界"] }); }
    if (seen[k]) { out.summary.bad.push({ gun: G.name, slot: c.slot, problems: ["与 " + seen[k] + " 同格"] }); }
    seen[k] = c.slot;
    if (c.row === G.body.row && c.col >= G.body.col && c.col < G.body.col + 3) {
      out.summary.bad.push({ gun: G.name, slot: c.slot, problems: ["压住枪身格"] });
    }
  });
});

// 前握把锚点自检：父件正下方同列、不与弹匣同行、不被其他格占用
Object.keys(out.guns).forEach(function (gid) {
  const G = out.guns[gid];
  if (G.error) { return; }
  const bySlot = {};
  G.cells.forEach(function (c) { bySlot[c.slot] = c; });
  const fore = G.cells.filter(function (c) { return c.base === "foregrip"; });
  if (fore.length) { out.summary.foregripGuns++; }
  fore.forEach(function (c) {
    const p = c.parent ? bySlot[c.parent] : null;
    if (!p) { out.summary.root++; return; }
    if (c.viaRail) { out.summary.viaRail++; } else { out.summary.direct++; }
    const problems = [];
    if (c.col !== p.col) { problems.push("列与父件不齐(" + c.col + "!=" + p.col + ")"); }
    // 父件在顶部轨道时，"正下方"会压在枪身 3 列上 → 允许整行下移到枪身下方（列仍对齐）
    const blockedByBody = (p.row + 1 === G.body.row &&
                           p.col >= G.body.col && p.col < G.body.col + 3);
    const wantRow = blockedByBody ? G.body.row + 1 : p.row + 1;
    if (c.row !== wantRow) { problems.push("不在父件正下方(row " + c.row + " vs 期望 " + wantRow + ")"); }
    const mag = G.cells.filter(function (x) { return x.base === "magazine"; })[0];
    if (mag && mag.row === c.row) { problems.push("与弹匣同一行(" + mag.row + ")"); }
    const grip = G.cells.filter(function (x) { return x.base === "pistol_grip" || x.base === "pistolgrip"; })[0];
    if (grip && grip.row === c.row && grip.col < c.col) { problems.push("在后握把右侧"); }
    const dup = G.cells.filter(function (x) {
      return x !== c && x.row === c.row && x.col === c.col;
    });
    if (dup.length) { problems.push("与其他格重叠"); }
    if (problems.length) {
      out.summary.bad.push({ gun: G.name, slot: c.slot, parent: c.parent, problems: problems });
    }
  });
});

console.log(JSON.stringify(out, null, 1));
