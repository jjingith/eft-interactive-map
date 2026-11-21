// R19.19 任务 B：配件父子布局规则只读审计探针。
// 不修改任何正式数据/布局；输出 docs/r19.19-ak-rear-sight/layout-rules-audit.json
const fs = require("fs"), path = require("path");
const ROOT = path.dirname(__dirname);
const GB = require(path.join(ROOT, "gun_builder.js"));
const items = JSON.parse(fs.readFileSync(path.join(ROOT, "data/items.json"), "utf8")).items;
const stats = JSON.parse(fs.readFileSync(path.join(ROOT, "data/gun-stats.json"), "utf8"));
const presets = JSON.parse(fs.readFileSync(path.join(ROOT, "data/gun-presets.json"), "utf8")).presets || {};
const calib = JSON.parse(fs.readFileSync(path.join(ROOT, "data/gun-layout-calibration.json"), "utf8"));
const src = fs.readFileSync(path.join(ROOT, "app.js"), "utf8");
const block = src.slice(src.indexOf("function gwSidBase("), src.indexOf("function renderGunSkin("));
const api = new Function("itemRec", "GW_ITEM_MAP", block +
  "\nreturn {gwBuildLayout:gwBuildLayout,gwApplyCalibToLayout:gwApplyCalibToLayout," +
  "gwSidBase:gwSidBase,gwSlotVisible:gwSlotVisible};")(
  function (id) { return items[id] || null; }, items);
const ctx = GB.context(items, stats);

function nm(i) { return (items[i] || {}).n || i || ""; }
function defInst(gid) {
  const st = (stats.guns || {})[gid] || {};
  if (st.preset && presets[st.preset]) { return presets[st.preset].i || {}; }
  for (const p in presets) { if (presets[p] && presets[p].g === gid) { return presets[p].i || {}; } }
  return {};
}
function build(gid, instOverride) {
  const inst = GB.sanitize(ctx, gid, instOverride || defInst(gid)).installed;
  const tree = GB.buildTree(ctx, gid, inst);
  const L = api.gwBuildLayout({ gunId: gid, installed: inst, slots: tree, noCalib: true });
  const recs = (calib.guns[gid] || {}).slots || {};
  const L2 = api.gwBuildLayout({ gunId: gid, installed: inst, slots: tree });   // 含校准
  const by = {};
  L.cells.forEach(function (c) {
    by[c.path] = { path: c.path, row: c.row - L.topPad, col: c.col, role: c.role || "", lane: c.lane || "" };
  });
  const by2 = {};
  L2.cells.forEach(function (c) {
    by2[c.path] = { path: c.path, row: c.row - L2.topPad, col: c.col };
  });
  return { inst, tree, L, by, by2, recs };
}
function nodeInfo(b, p) {
  const n = b.tree.nodes[p];
  if (!n) { return null; }
  return { path: p, sid: n.sid, label: n.label, parent: n.parent,
           parentItem: n.parent ? (b.inst[n.parent] || "") : "",
           parentItemName: n.parent ? nm(b.inst[n.parent]) : "",
           base: api.gwSidBase(n.sid),
           children: (n.children || []).slice() };
}
function calibKeyFor(b, p) {
  const n = b.tree.nodes[p];
  if (!n) { return null; }
  const owner = n.parent ? (b.inst[n.parent] || "") : "";
  return p + "|" + n.sid + "|" + owner;
}

const out = { schema: "r19.19-layout-rules-audit/1", cases: [], notes: [] };

function caseEntry(title, gid, paths, ruleExpect, codePath, note, instOverride) {
  const b = build(gid, instOverride);
  const rows = paths.map(function (p) {
    const n = nodeInfo(b, p);
    const cur = b.by[p] || null;
    const cal = b.by2[p] || null;
    const key = calibKeyFor(b, p);
    const rec = b.recs[key] || null;
    return {
      slotPath: p,
      slotName: n ? n.label : null,
      base: n ? n.base : null,
      parentPath: n ? n.parent : null,
      parentItem: n ? n.parentItem : null,
      parentItemName: n ? n.parentItemName : null,
      installedItem: b.inst[p] ? { id: b.inst[p], name: nm(b.inst[p]) } : null,
      autoLogical: cur ? { row: cur.row, col: cur.col, role: cur.role } : null,
      finalWithCalib: cal ? { row: cal.row, col: cal.col } : null,
      calibKey: key,
      calibRecord: rec ? { logicalRow: rec.logicalRow, col: rec.col, note: (rec.note || "").slice(0, 30) } : null,
    };
  });
  out.cases.push({ title, gunId: gid, gunName: (gunslotsName(gid) || nm(gid)),
                   rows, ruleExpect, codePath, note: note || "" });
}
function gunslotsName(gid) {
  try {
    return JSON.parse(fs.readFileSync(path.join(ROOT, "data/gunslots.json"), "utf8")).guns[gid].n;
  } catch (e) { return null; }
}

// ============================================================ 案例 1：上半部分配件的子槽
// AK-74N：TT01 照门导轨（装在照门槽 r2c6）→ 其 mod_scope 子槽应在其正上方
{
  const inst1 = Object.assign({}, defInst("5644bd2b4bdc2d3b4c8b4572"));
  inst1["mod_sight_rear"] = "5649d9a14bdc2d79388b4580";   // TT01 照门导轨（自带 mod_scope 子槽）
  caseEntry("案例1 上半部配件子槽：AK-74N TT01 照门导轨 → 瞄具子槽",
    "5644bd2b4bdc2d3b4c8b4572",
    ["mod_sight_rear", "mod_sight_rear/mod_scope"],
    "父槽 r2c6（上半部）→ 子槽应在其正上方 r1c6（规则1）",
    "gwBuildLayout 阶段8 其余槽位：父件 row<=2 时 nearestInRow(parentRow-1) 向上（app.js ~L11492）",
    "", inst1);
}

// ============================================================ 案例 2：下半部分配件的子槽
// SCAR-L：折叠枪托（r3c9）→ 伸缩枪托子槽（mod_stock_001）
caseEntry("案例2 下半部配件子槽：SCAR-L 折叠枪托 → 伸缩枪托子槽",
  "6184055050224f204c1da540",
  ["mod_stock", "mod_stock/mod_stock_001"],
  "父槽 r3c9（枪托，尾部）→ 子槽正下方 r4c9（规则2）",
  "gwBuildLayout 阶段3 固定锚点：枪托链沿 r4c9→r5c9→r6c9 向下（app.js ~L10860）",
  "");

// ============================================================ 案例 3：枪口—转接器—消音器链
// M4A1（或任意 AR-15）：枪口制退器（装 mod_muzzle）→ 其 mod_muzzle 子槽（消音器）
{
  const gid = "5644bd2b4bdc2d3b4c8b4572";  // 用 AK-74N 也可；这里用 M4 风格枪验证通用枪口链
  // 找一把默认装配带枪口件子槽的枪：AK-74N 默认无 → 合成装配：TT01？改用直接构造
  const inst = Object.assign({}, defInst(gid));
  // 装上 Hexagon Reactor 膛口制退器（自带 mod_muzzle 子槽 → Wafflemaker 消音器）
  inst["mod_muzzle"] = "615d8f5dd92c473c770212ef";
  caseEntry("案例3 枪口链：AK-74N 枪口制退器 → 消音器子槽",
    gid,
    ["mod_muzzle", "mod_muzzle/mod_muzzle"],
    "父槽 r3c1（枪口）→ 沿枪口方向（水平向左）优先延伸；c1 已是网格左缘，无空间 → 回退父件正下方 r4c1（规则3）",
    "gwBuildLayout 阶段5 枪口纵向链：mRow+1+ki 同列向下（app.js ~L11363）",
    "规则3 的『优先沿枪口方向』在实现中完全缺席——直接使用回退位（同列向下）；对枪口在 c1 的枪结果与回退位一致，对一体式枪（muzzle c2）水平 c1 同行位会被主体行护栏排除",
    inst);
}

// ============================================================ 案例 4：枪托及子配件链
{
  // M4A1 类：缓冲管 → 枪托 → 枪托垫（三层）
  // 用柯尔特 M4A1（colt）找 id
  let m4 = null;
  for (const gid of Object.keys(stats.guns || {})) {
    const n = gunslotsName(gid) || "";
    if (n.indexOf("M4A1") >= 0) { m4 = gid; break; }
  }
  if (!m4) { m4 = "5644bd2b4bdc2d3b4c8b4572"; }
  const b0 = build(m4);
  const stockPaths = Object.keys(b0.tree.nodes).filter(function (p) {
    return api.gwSidBase(b0.tree.nodes[p].sid).indexOf("stock") >= 0;
  });
  caseEntry("案例4 枪托链：缓冲管 → 枪托 → 枪托垫/托腮板",
    m4, stockPaths,
    "枪托链优先沿枪托方向（水平向右）延伸，空间不足再向下；c9 已是网格右缘 → 回退 r4c9/r5c9（规则4）",
    "gwBuildLayout 阶段3：只沿枪托链往下排 r4c9→r5c9→r6c9（app.js ~L10860）",
    "『先判断枪托方向空间是否可用』的优先级逻辑未实现（始终向下）；对枪托在 c9 的枪结果与回退位一致");
}

// ============================================================ 案例 5：SCAR-L 托腮板
caseEntry("案例5 托腮板：SCAR-L 折叠枪托 → 托腮板（mod_stock_002）",
  "6184055050224f204c1da540",
  ["mod_stock", "mod_stock/mod_stock_002"],
  "托腮板在枪托上方 → 应在父件正上方 r2c9（规则5）",
  "gwBuildLayout 阶段3 枪托链 / 阶段8 其余槽位（具体以 autoLogical 为准）",
  "");

// ============================================================ 案例 6：多层嵌套 + 条件子槽
{
  const inst6 = Object.assign({}, defInst("574d967124597745970e7c94"));
  inst6["mod_barrel/mod_mount_001"] = "593d1fa786f7746da62d61ac";   // UTG SKS SOCOM 导轨基座
  caseEntry("案例6 多层嵌套：SKS SOCOM 导轨座 → 瞄具 + 战术子槽（条件子槽）",
    "574d967124597745970e7c94",
    ["mod_barrel/mod_mount_001",
     "mod_barrel/mod_mount_001/mod_scope",
     "mod_barrel/mod_mount_001/mod_tactical_000",
     "mod_barrel/mod_mount_001/mod_tactical_001",
     "mod_barrel/mod_mount_001/mod_tactical_002",
     "mod_barrel/mod_mount_001/mod_tactical_003"],
    "多子槽应按各自类型/方向分别布局（规则7）；当前：GW_FIXED_SLOT 固定锚点 r4c3/r2c3/r5c3–c6",
    "gwBuildLayout 阶段 2.2) GW_FIXED_SLOT 固定锚点（app.js）+ 阶段8",
    "SKS 的 SOCOM 链坐标由 R19.18 用户指定锚点硬性规定，属于特例而非通用规则", inst6);
}

// ============================================================ 通用关系补充：自动布局 vs 校准覆盖
{
  const gid = "5644bd2b4bdc2d3b4c8b4572";
  const b = build(gid);
  const overrides = [];
  Object.keys(b.by).forEach(function (p) {
    const a = b.by[p], c = b.by2[p];
    if (c && (a.row !== c.row || a.col !== c.col)) {
      overrides.push({ path: p, auto: { row: a.row, col: a.col },
                       final: { row: c.row, col: c.col }, key: calibKeyFor(b, p) });
    }
  });
  out.notes.push({ topic: "calib-override-sample", gun: gunslotsName(gid), overrides });
}

// 全项目统计：子槽相对父件的方向分布（只读统计，帮助判断规则 1/2 的整体符合度）
{
  const stats2 = { above: 0, below: 0, sameRow: 0, other: 0, samples: { above: [], below: [], sameRow: [] } };
  const gunIds = Object.keys(JSON.parse(fs.readFileSync(path.join(ROOT, "data/gunslots.json"), "utf8")).guns);
  for (const gid of gunIds) {
    let b;
    try { b = build(gid); } catch (e) { continue; }
    Object.keys(b.tree.nodes).forEach(function (p) {
      const n = b.tree.nodes[p];
      if (!n.parent) { return; }
      const cur = b.by[p], par = b.by[n.parent];
      if (!cur || !par) { return; }
      if (cur.col === par.col && cur.row < par.row) {
        stats2.above++;
        if (stats2.samples.above.length < 5) { stats2.samples.above.push({ gun: gunslotsName(gid), path: p, r: cur.row, pr: par.row, c: cur.col }); }
      } else if (cur.col === par.col && cur.row > par.row) {
        stats2.below++;
        if (stats2.samples.below.length < 5) { stats2.samples.below.push({ gun: gunslotsName(gid), path: p, r: cur.row, pr: par.row, c: cur.col }); }
      } else if (cur.row === par.row) {
        stats2.sameRow++;
        if (stats2.samples.sameRow.length < 5) { stats2.samples.sameRow.push({ gun: gunslotsName(gid), path: p, r: cur.row, c: cur.col, pc: par.col }); }
      } else { stats2.other++; }
    });
  }
  out.notes.push({ topic: "child-direction-distribution", stats: stats2 });
}

fs.mkdirSync(path.join(ROOT, "docs", "r19.19-ak-rear-sight"), { recursive: true });
fs.writeFileSync(path.join(ROOT, "docs", "r19.19-ak-rear-sight", "layout-rules-audit.json"),
  JSON.stringify(out, null, 1));
console.log("cases:", out.cases.length);
out.cases.forEach(function (c) {
  console.log("==", c.title);
  c.rows.forEach(function (r) {
    console.log("   ", r.slotPath.padEnd(44),
      r.autoLogical ? ("auto r" + r.autoLogical.row + "c" + r.autoLogical.col) : "UNPLACED",
      r.calibRecord ? ("CALIB r" + r.calibRecord.logicalRow + "c" + r.calibRecord.col) : "",
      "| parent:", (r.parentItemName || "-").slice(0, 18));
  });
});
const dist = out.notes.filter(function (n) { return n.topic === "child-direction-distribution"; })[0];
console.log("distribution:", JSON.stringify(dist.stats.above), JSON.stringify(dist.stats.below),
            JSON.stringify(dist.stats.sameRow), JSON.stringify(dist.stats.other));
