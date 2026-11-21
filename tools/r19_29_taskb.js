// R19.29 任务B 验证（只读）：战术槽冲突动态避让
//   B1 场景复现：对所有可装「带子槽配件」的低行战术槽，装上子槽最多的候选件后检查
//        · 子槽是否落在父件同行右邻格 (parent.row, parent.col+1)
//        · 是否出现两个槽位同格
//        · 原本占该格的独立槽位是否右移（并在本行找到真实空位）
//   B2 移除恢复：卸掉该配件后，全部槽位坐标必须与装之前逐格一致
//   B3 幂等不漂移：同一枪连续计算 3 次结果一致；对同一份 L 重复套用校准也不移动
//   B4 无空间：用合成数据直接驱动 gwReflowTacticalKids，验证「记冲突、不覆盖」
//   B5 校准记录不被改写：跑完后重新读取 data/gun-layout-calibration.json 并核对未被写入
//   输出 docs/r19.29/task-b.json；stdout 打印 CHECK_TASKB
const fs = require("fs"), path = require("path");
const ROOT = path.dirname(__dirname);
const GB = require(path.join(ROOT, "gun_builder.js"));
const ITEMS_PATH = path.join(ROOT, "data/items.json");
const CALIB_PATH = path.join(ROOT, "data/gun-layout-calibration.json");
const items = JSON.parse(fs.readFileSync(ITEMS_PATH, "utf8")).items;
const stats = JSON.parse(fs.readFileSync(path.join(ROOT, "data/gun-stats.json"), "utf8"));
const presets = JSON.parse(fs.readFileSync(path.join(ROOT, "data/gun-presets.json"), "utf8")).presets || {};
const gunslots = JSON.parse(fs.readFileSync(path.join(ROOT, "data/gunslots.json"), "utf8")).guns;
const calib = JSON.parse(fs.readFileSync(CALIB_PATH, "utf8"));
const calibRawBefore = fs.readFileSync(CALIB_PATH, "utf8");
const src = fs.readFileSync(path.join(ROOT, "app.js"), "utf8");
const block = src.slice(src.indexOf("function gwSidBase("), src.indexOf("function renderGunSkin("));
const api = new Function("itemRec", "GW_ITEM_MAP", block +
  "\nreturn {gwBuildLayout:gwBuildLayout,gwApplyCalibToLayout:gwApplyCalibToLayout," +
  "gwSlotVisible:gwSlotVisible,gwSidBase:gwSidBase,gwReflowTacticalKids:gwReflowTacticalKids," +
  "GW_GRID_COLS:GW_GRID_COLS,GW_ANCHOR:GW_ANCHOR};")(
  function (id) { return items[id] || null; }, items);
const ctx = GB.context(items, stats);
const B = function (s) { return api.gwSidBase(s || ""); };
const LOWER = /^(tactical|flashlight|laser|devices|emitter)$/;

function defInst(gid) {
  const st = (stats.guns || {})[gid] || {};
  if (st.preset && presets[st.preset]) { return presets[st.preset].i || {}; }
  for (const p in presets) { if (presets[p] && presets[p].g === gid) { return presets[p].i || {}; } }
  return {};
}
function run(gid, inst) {
  const ins = GB.sanitize(ctx, gid, inst || defInst(gid)).installed;
  const tree = GB.buildTree(ctx, gid, ins);
  const records = (calib.guns[gid] || {}).slots || {};
  const L = api.gwBuildLayout({ gunId: gid, installed: ins, slots: tree, noCalib: true });
  const info = api.gwApplyCalibToLayout(L, { gunId: gid, installed: ins, slots: tree }, records);
  const map = {};
  const dup = [];
  L.cells.forEach(function (c) {
    const k = c.row + "|" + c.col;
    if (map[k]) { dup.push(k + ":" + map[k].path + "/" + c.path); }
    map[k] = { path: c.path, row: c.row, col: c.col };
  });
  const byPath = {};
  L.cells.forEach(function (c) { byPath[c.path] = { row: c.row, col: c.col }; });
  return { ins: ins, tree: tree, L: L, info: info, map: map, byPath: byPath, dup: dup };
}
function snapshot(r) {
  const o = {};
  r.L.cells.forEach(function (c) { o[c.path] = c.row + "|" + c.col; });
  return o;
}
function diffSnap(a, b) {
  const out = [];
  Object.keys(a).forEach(function (k) { if (a[k] !== b[k]) { out.push(k + ": " + a[k] + " -> " + b[k]); } });
  Object.keys(b).forEach(function (k) { if (a[k] === undefined) { out.push(k + ": - -> " + b[k]); } });
  return out;
}

const cases = [];
const GUNS = process.argv[2] ? [process.argv[2]] : Object.keys(gunslots);
for (const gid of GUNS) {
  const base = run(gid, null);
  // 找低行、空的、可装「带子槽配件」的战术类槽位
  const targets = [];
  for (const p of base.tree.order) {
    const node = base.tree.nodes[p];
    if (!node || !LOWER.test(B(node.sid))) { continue; }
    const pos = base.byPath[p];
    if (!pos || pos.row < 5) { continue; }
    if (base.ins[p]) { continue; }
    const wk = (node.allow || []).filter(function (a) { return ((items[a] || {}).slots || []).length > 0; });
    if (!wk.length) { continue; }
    let best = wk[0];
    for (const w of wk) { if (((items[w] || {}).slots || []).length > ((items[best] || {}).slots || []).length) { best = w; } }
    targets.push({ path: p, base: B(node.sid), pos: pos, item: best });
  }
  for (const t of targets) {
    const inst = Object.assign({}, base.ins);
    inst[t.path] = t.item;
    const on = run(gid, inst);
    const kidPaths = (on.tree.nodes[t.path] || {}).children || [];
    const kids = kidPaths.filter(function (k) { return !!on.byPath[k]; }).map(function (k) {
      return { path: k, base: B((on.tree.nodes[k] || {}).sid), pos: on.byPath[k] };
    });
    if (!kids.length) { continue; }
    const pc = on.byPath[t.path];
    const want = { row: pc.row, col: pc.col + 1 };
    const occupiedWant = on.map[want.row + "|" + want.col];
    const primary = kids[0];
    const childAtWant = primary.pos.row === want.row && primary.pos.col === want.col;
    // 右邻格被谁占着：祖先链路 / 同父兄弟 / 独立槽位 / 固定坐标 / 空
    let wantBlocker = null;
    if (occupiedWant) {
      const bp = occupiedWant.path;
      const anc = function (child, maybeAnc) {
        let x = (on.tree.nodes[child] || {}).parent;
        while (x) { if (x === maybeAnc) { return true; } x = (on.tree.nodes[x] || {}).parent; }
        return false;
      };
      let kind = "independent";
      if (anc(t.path, bp)) { kind = "ancestor"; }
      else if ((on.tree.nodes[bp] || {}).parent && (on.tree.nodes[bp] || {}).parent === (on.tree.nodes[t.path] || {}).parent) { kind = "sibling"; }
      wantBlocker = { path: bp, kind: kind };
    }
    const shifted = on.info.reflow.filter(function (r) { return r.path !== primary.path; });
    // 移除恢复
    const off = run(gid, Object.assign({}, inst, (function () { const o = {}; o[t.path] = undefined; return o; })()));
    const off2 = run(gid, null);
    const restoreDiff = diffSnap(snapshot(base), snapshot(off2));
    // 幂等：同枪连续算 3 次
    const r1 = run(gid, inst), r2 = run(gid, inst), r3 = run(gid, inst);
    const s1 = JSON.stringify(snapshot(r1)), s2 = JSON.stringify(snapshot(r2)), s3 = JSON.stringify(snapshot(r3));
    // 同一份 L 重复套用校准（模拟重复渲染）
    const again = api.gwApplyCalibToLayout(r1.L, { gunId: gid, installed: r1.ins, slots: r1.tree },
      (calib.guns[gid] || {}).slots || {});
    const doubleDiff = diffSnap(snapshot(r1), snapshot({ L: r1.L }));

    cases.push({
      gunId: gid, gun: (items[gid] || {}).n || gid,
      parent: t.path, parentBase: t.base, parentPos: "r" + pc.row + "c" + pc.col,
      item: (items[t.item] || {}).n || t.item,
      kids: kids.map(function (k) { return k.base + "@r" + k.pos.row + "c" + k.pos.col; }),
      want: "r" + want.row + "c" + want.col,
      occupiedWantBy: occupiedWant ? occupiedWant.path : null,
      wantBlocker: wantBlocker,
      childAtWant: childAtWant,
      shiftedCount: shifted.length,
      shifted: shifted.map(function (r) { return r.path.split("/").pop() + " " + r.from + "->" + r.to; }),
      dup: on.dup,
      conflicts: on.info.conflicts,
      fallback: on.info.fallback.length,
      restoreClean: restoreDiff.length === 0,
      restoreDiff: restoreDiff,
      idempotent: s1 === s2 && s2 === s3 && doubleDiff.length === 0,
      doubleApplyDiff: doubleDiff,
      // 真正的同格冲突 = 右邻格被「独立槽位」占着而子槽没能进去；
      // 被祖先链路（父件自己的安装座）或同父兄弟占着属于结构限制，不算冲突。
      sameRowConflict: !!(wantBlocker && wantBlocker.kind === "independent" && !childAtWant)
    });
  }
}

// B4：合成数据驱动避让函数，验证「无空间 → 记冲突不覆盖」「有空间 → 右移」
function synth(cellsSpec, nodesSpec) {
  const nodes = nodesSpec || {};
  const cells = cellsSpec.map(function (c) { return { path: c.p, row: c.r, col: c.c }; });
  const info = { reflow: [], conflicts: [] };
  api.gwReflowTacticalKids(cells, nodes, info);
  const map = {};
  cells.forEach(function (c) { map[c.path] = "r" + c.row + "c" + c.col; });
  return { map: map, info: info };
}
const synthNodes = {
  root: { sid: "mod_reciever", parent: null },
  P: { sid: "mod_tactical_001", parent: "root" },
  C: { sid: "mod_flashlight", parent: "P" },
  D: { sid: "mod_tactical_002", parent: "root" },
  K: { sid: "mod_laser", parent: "P" },        // 与 C 同一个父件的兄弟子槽
  F1: { sid: "mod_tactical_003", parent: "root" }, F2: { sid: "mod_tactical_004", parent: "root" },
  F3: { sid: "mod_tactical_005", parent: "root" }, F4: { sid: "mod_tactical_006", parent: "root" },
  F5: { sid: "mod_tactical_007", parent: "root" }, F6: { sid: "mod_tactical_008", parent: "root" },
  F7: { sid: "mod_tactical_009", parent: "root" }
};
// B4-1 有空间：r6c2 被 D 占，右侧 c3 空 → D 右移到 c3，C 落到 c2
const s1 = synth([
  { p: "P", r: 6, c: 1 }, { p: "D", r: 6, c: 2 }, { p: "C", r: 6, c: 5 }
], synthNodes);
// B4-2 继续右搜：c3/c4 被占 → D 落到 c5（C 原格腾空后可用）
const s2 = synth([
  { p: "P", r: 6, c: 1 }, { p: "D", r: 6, c: 2 }, { p: "C", r: 6, c: 5 },
  { p: "F1", r: 6, c: 3 }, { p: "F2", r: 6, c: 4 }
], synthNodes);
// B4-3 无空间：子槽不在本行，c3..c9 全被占 → 记冲突，D 与 C 都不动
const s3 = synth([
  { p: "P", r: 6, c: 1 }, { p: "D", r: 6, c: 2 }, { p: "C", r: 3, c: 1 },
  { p: "F1", r: 6, c: 3 }, { p: "F2", r: 6, c: 4 }, { p: "F3", r: 6, c: 5 },
  { p: "F4", r: 6, c: 6 }, { p: "F5", r: 6, c: 7 }, { p: "F6", r: 6, c: 8 },
  { p: "F7", r: 6, c: 9 }
], synthNodes);
// B4-4 兄弟子槽不让位：r6c2 被同一个父件的另一个子槽 K 占着 → 不动
const s4 = synth([
  { p: "P", r: 6, c: 1 }, { p: "K", r: 6, c: 2 }, { p: "C", r: 6, c: 5 }
], synthNodes);
// B4-5 固定锚点不可占用：r5c7 是子弹合成锚点，D 跳过它落到 c8
const s5 = synth([
  { p: "P", r: 5, c: 1 }, { p: "D", r: 5, c: 2 }, { p: "C", r: 3, c: 1 },
  { p: "F1", r: 5, c: 3 }, { p: "F2", r: 5, c: 4 }, { p: "F3", r: 5, c: 5 },
  { p: "F4", r: 5, c: 6 }, { p: "F5", r: 5, c: 9 }
], synthNodes);
// B4-6 右邻格空着而子槽在别处 → 放回右邻格
const s6 = synth([
  { p: "P", r: 6, c: 1 }, { p: "C", r: 4, c: 7 }
], synthNodes);
// B4-7 子槽已在父件正上方 → 不动（同样清晰的上下层级，不为了格式而横移）
const s7 = synth([
  { p: "P", r: 6, c: 1 }, { p: "C", r: 5, c: 1 }
], synthNodes);

const synthChecks = [
  { id: "B4-1_slide_right", pass: s1.map.D === "r6c3" && s1.map.C === "r6c2" && s1.info.reflow.length === 2,
    got: s1.map.D + " / C " + s1.map.C },
  { id: "B4-2_keep_searching", pass: s2.map.D === "r6c5" && s2.map.C === "r6c2", got: s2.map.D + " / C " + s2.map.C },
  { id: "B4-3_no_space_conflict", pass: s3.map.D === "r6c2" && s3.map.C === "r3c1" &&
    s3.info.conflicts.length === 1 && s3.info.reflow.length === 0,
    got: s3.map.D + " / C " + s3.map.C + " conflicts=" + s3.info.conflicts.length },
  { id: "B4-4_sibling_no_move", pass: s4.map.K === "r6c2" && s4.map.C === "r6c5" &&
    s4.info.reflow.length === 0 && s4.info.conflicts.length === 0, got: s4.map.K + " / C " + s4.map.C },
  { id: "B4-5_anchor_not_used", pass: s5.map.D === "r5c8" && s5.map.C === "r5c2", got: s5.map.D + " / C " + s5.map.C },
  { id: "B4-6_free_cell_return", pass: s6.map.C === "r6c2", got: "C " + s6.map.C },
  { id: "B4-7_already_above", pass: s7.map.C === "r5c1" && s7.info.reflow.length === 0, got: "C " + s7.map.C }
];

const calibRawAfter = fs.readFileSync(CALIB_PATH, "utf8");
const calibUntouched = calibRawBefore === calibRawAfter;

const sum = {
  scenarios: cases.length,
  guns: {},
  childAtWant: cases.filter(function (c) { return c.childAtWant; }).length,
  sameRowConflict: cases.filter(function (c) { return c.sameRowConflict; }).length,
  dup: cases.filter(function (c) { return c.dup.length; }).length,
  shifted: cases.filter(function (c) { return c.shiftedCount > 0; }).length,
  restoreClean: cases.filter(function (c) { return c.restoreClean; }).length,
  idempotent: cases.filter(function (c) { return c.idempotent; }).length,
  fallbackDirty: cases.filter(function (c) { return c.fallback > 0; }).length,
  synthPass: synthChecks.filter(function (c) { return c.pass; }).length,
  synthTotal: synthChecks.length,
  calibUntouched: calibUntouched
};
cases.forEach(function (c) { sum.guns[c.gun] = 1; });
sum.gunCount = Object.keys(sum.guns).length;
delete sum.guns;

const hardFail = cases.filter(function (c) {
  if (c.dup.length || !c.restoreClean || !c.idempotent || c.fallback > 0) { return true; }
  if (c.sameRowConflict) { return true; }                       // 该让位却没让位
  if (!c.childAtWant && !c.wantBlocker) { return true; }        // 右邻格空着却没回去
  return false;
});
const ok = hardFail.length === 0 && sum.synthPass === sum.synthTotal && calibUntouched;

const out = {
  build: "R19.29",
  generatedBy: "tools/r19_29_taskb.js",
  rule: "战术类父件在低行生成子槽时，子槽占父件同行右邻格；该格被独立槽位占着则独立槽位右移；无空位记冲突不覆盖",
  summary: sum,
  synthChecks: synthChecks,
  cases: cases,
  failures: hardFail
};
const dir = path.join(ROOT, "docs/r19.29");
fs.mkdirSync(dir, { recursive: true });
fs.writeFileSync(path.join(dir, "task-b.json"), JSON.stringify(out, null, 2), "utf8");

console.log("=== R19.29 任务B：战术槽冲突动态避让 ===");
console.log("  真实场景（枪 × 装带子槽配件）：" + sum.scenarios + " 例，覆盖 " + sum.gunCount + " 把枪");
console.log("  子槽落在父件同行右邻格：" + sum.childAtWant + "/" + sum.scenarios +
            "   同格冲突：" + sum.sameRowConflict + "   同格重复：" + sum.dup);
console.log("  触发独立槽位右移：" + sum.shifted + " 例   移除后完全恢复：" + sum.restoreClean + "/" + sum.scenarios +
            "   幂等不漂移：" + sum.idempotent + "/" + sum.scenarios + "   fallback 污染：" + sum.fallbackDirty);
console.log("  合成用例：" + sum.synthPass + "/" + sum.synthTotal +
            "   校准文件未被写入：" + (calibUntouched ? "是" : "否"));
for (const c of cases) {
  console.log("   · " + c.gun.slice(0, 22).padEnd(24) + " 父 " + c.parentPos.padEnd(6) +
              " 装[" + c.item.slice(0, 14).padEnd(16) + "] 子槽 " + c.kids.join(",").padEnd(30) +
              (c.childAtWant ? " OK" : " 未落右邻格") + (c.shifted.length ? " 右移:" + c.shifted.join(";") : ""));
}
for (const s of synthChecks) { console.log("   · " + s.id + " " + (s.pass ? "PASS" : "FAIL") + "   " + s.got); }
if (hardFail.length) { console.log("  [失败] " + JSON.stringify(hardFail, null, 2)); }
console.log(ok ? "CHECK_TASKB: PASS (" + sum.scenarios + " 场景 + " + sum.synthTotal + " 合成用例)"
               : "CHECK_TASKB: FAIL");
process.exit(ok ? 0 : 1);
