/* ============================================================================
 * r1925_layout_test.js —— 布局模块的结构性测试（在 Node 里跑，不启动浏览器）
 *
 * 断言的是"结构正确性"，不是像素：
 *   · 一个任务一个节点、ID 唯一
 *   · 每条真实前置边都在结果里（AND / OR / 失败分支一条不少）
 *   · 节点不重叠
 *   · 输出确定性（同一输入两次结果完全一致）
 *   · 菱形（多前置汇合）、环、长边（跨层）、脏边（指向不存在的任务）都能安全处理
 *   · 真实数据三模式的质量门槛（直线交叉数、画布尺寸、分带数）
 *
 * 输出：单行 JSON {ok, results:[{name, ok, detail}]}，由 pytest 解析。
 * 用法：node tools/r1925_layout_test.js
 * ==========================================================================*/
"use strict";

const fs = require("fs");
const path = require("path");

global.window = {};
require(path.join(__dirname, "..", "js", "task-graph-layout.js"));
const G = global.window.GWTaskGraph;

const ROOT = path.join(__dirname, "..");
const results = [];
function check(name, cond, detail) {
  results.push({ name: name, ok: !!cond, detail: detail === undefined ? null : detail });
}
function loadTasks(mode) {
  return JSON.parse(fs.readFileSync(path.join(ROOT, "data", "tasks", "tasks." + mode + ".json"), "utf8")).tasks;
}
const TRADERS = Object.keys(JSON.parse(
  fs.readFileSync(path.join(ROOT, "data", "tasks", "traders.json"), "utf8")).traders);

// ------------------------------------------------------------------ 1 合成用例
(function () {
  const tasks = {
    A: { id: "A", nameZh: "甲", traderId: "T1", minLevel: 1, prerequisites: [] },
    B: { id: "B", nameZh: "乙", traderId: "T1", minLevel: 2, prerequisites: [{ taskId: "A", statuses: ["complete"], logic: "all" }] },
    C: { id: "C", nameZh: "丙", traderId: "T1", minLevel: 2, prerequisites: [{ taskId: "A", statuses: ["complete"], logic: "all" }] },
    D: { id: "D", nameZh: "丁", traderId: "T2", minLevel: 3, prerequisites: [
      { taskId: "B", statuses: ["complete"], logic: "all" },
      { taskId: "C", statuses: ["complete", "active"], logic: "or" }] }
  };
  const r = G.layout(tasks, { traderOrder: ["T1", "T2"] });
  check("菱形：4 个任务 = 4 个节点（多前置不复制节点）", r.nodes.length === 4, r.nodes.length);
  check("菱形：4 条前置边齐全（A→B、A→C、B→D、C→D）", r.metrics.edges === 4, r.metrics.edges);
  const orEdge = r.edges.filter(function (e) { return e.from === "C" && e.to === "D"; })[0];
  check("OR 语义保留（C→D 仍是 or）", orEdge && orEdge.kind === "or", orEdge && orEdge.kind);
  check("菱形：无节点重叠", r.metrics.nodeOverlaps === 0, r.metrics.nodeOverlaps);
  check("菱形：D 的父节点比 D 靠左（层级方向）",
    r.nodes.filter(function (n) { return n.id === "B" || n.id === "C"; })
      .every(function (n) { return n.x < r.nodes.filter(function (m) { return m.id === "D"; })[0].x; }));
})();


// ------------------------------------------------------------------ 1b 失败分支 / 分层 / 分量
(function () {
  const tasks = {
    A: { id: "A", nameZh: "甲", traderId: "T1", prerequisites: [] },
    B: { id: "B", nameZh: "乙", traderId: "T1",
         prerequisites: [{ taskId: "A", statuses: ["complete"] }],
         failedConditions: [{ taskId: "A", statuses: ["complete"] }] },
    C: { id: "C", nameZh: "丙", traderId: "T2", prerequisites: [] },
    D: { id: "D", nameZh: "丁", traderId: "T2",
         failedConditions: [{ taskId: "C", statuses: ["complete"] }] }
  };
  const r = G.layout(tasks, { traderOrder: ["T1", "T2"] });
  const idx = r.index;
  check("失败分支不参与分层：D 仍是 0 层（没被 C 抬高）", idx.D.layer === 0, idx.D.layer);
  check("失败分支不参与分层：B 仍是 1 层（前置 A→B 才是分层依据）", idx.B.layer === 1, idx.B.layer);
  check("失败分支照画：fail 边数 = 2", r.metrics.failEdges === 2, r.metrics.failEdges);
  check("失败分支连的两块仍同一分量（不拆线）", idx.C.comp === idx.D.comp, [idx.C.comp, idx.D.comp]);
  check("失败分支不穿卡片", r.metrics.edgeNodeHitEdges === 0, r.metrics.edgeNodeHitEdges);
  const kinds = r.edges.filter(function (e) { return e.kind === "fail"; });
  check("失败分支保留 fail 语义（kind=fail）", kinds.length === 2 && kinds.every(function (e) { return e.kind === "fail"; }));
  check("所有边的两端都在同一分量（没有跨块线）",
    r.edges.every(function (e) { return idx[e.from].comp === idx[e.to].comp; }));
})();

// ------------------------------------------------------------------ 2 环
(function () {
  const tasks = {
    A: { id: "A", nameZh: "甲", traderId: "T1", prerequisites: [{ taskId: "B", statuses: ["complete"] }] },
    B: { id: "B", nameZh: "乙", traderId: "T1", prerequisites: [{ taskId: "A", statuses: ["complete"] }] }
  };
  let r = null;
  let threw = null;
  try { r = G.layout(tasks, { traderOrder: ["T1"] }); } catch (e) { threw = String(e); }
  check("环：不抛异常/不死循环", !threw, threw);
  check("环：两个节点都在，两条边都画出来（回边不能丢）",
    r && r.nodes.length === 2 && r.metrics.edges === 2 && r.metrics.cycleEdges === 1,
    r && { n: r.nodes.length, e: r.metrics.edges, cyc: r.metrics.cycleEdges });
  check("环：记录到回边（cycles>0）", r && r.metrics.cycles > 0, r && r.metrics.cycles);
})();

// ------------------------------------------------------------------ 3 长边 + 脏边
(function () {
  const tasks = {
    A: { id: "A", nameZh: "甲", traderId: "T1", prerequisites: [] },
    B: { id: "B", nameZh: "乙", traderId: "T1", prerequisites: [{ taskId: "A", statuses: ["complete"] }] },
    C: { id: "C", nameZh: "丙", traderId: "T1", prerequisites: [{ taskId: "B", statuses: ["complete"] }, { taskId: "A", statuses: ["complete"] }] },
    D: { id: "D", nameZh: "丁", traderId: "T1", prerequisites: [{ taskId: "不存在", statuses: ["complete"] }] }
  };
  const r = G.layout(tasks, { traderOrder: ["T1"] });
  check("长边：A→C 跨 2 层被记录", r.metrics.longEdges >= 1, r.metrics.longEdges);
  check("长边：补了哑节点", r.metrics.dummies >= 1, r.metrics.dummies);
  check("长边：不穿卡片", r.metrics.edgeNodeHitEdges === 0, r.metrics.edgeNodeHitEdges);
  check("长边：逐层经过，转折数 ≥ 2", r.metrics.bends >= 2, r.metrics.bends);
  check("脏边：指向不存在任务的边被记录而不是静默丢弃", r.metrics.dropped === 1, r.metrics.dropped);
  check("脏边：节点数仍等于任务数", r.nodes.length === 4, r.nodes.length);
})();

// ------------------------------------------------------------------ 4 真实数据
const summary = {};
["regular", "pve", "pvps"].forEach(function (mode) {
  const tasks = loadTasks(mode);
  const ids = Object.keys(tasks);
  let edges = 0, fail = 0;
  ids.forEach(function (id) {
    const rec = tasks[id];
    edges += (rec.prerequisites || []).filter(function (p) { return p.taskId && tasks[p.taskId]; }).length;
    fail += (rec.failedConditions || []).filter(function (f) { return f.taskId && tasks[f.taskId]; }).length;
  });
  const t0 = Date.now();
  const r = G.layout(tasks, { traderOrder: TRADERS });
  const ms = Date.now() - t0;
  summary[mode] = r.metrics;

  check(mode + "：节点数 = 任务数", r.nodes.length === ids.length, { got: r.nodes.length, want: ids.length });
  check(mode + "：节点 ID 唯一", new Set(r.nodes.map(function (n) { return n.id; })).size === ids.length);
  check(mode + "：前置边一条不少", r.metrics.edges === edges, { got: r.metrics.edges, want: edges });
  check(mode + "：失败分支一条不少", r.metrics.auxEdges === fail, { got: r.metrics.auxEdges, want: fail });
  check(mode + "：节点不重叠", r.metrics.nodeOverlaps === 0, r.metrics.nodeOverlaps);
  check(mode + "：连接线不穿卡片（硬门槛）", r.metrics.edgeNodeHitEdges === 0 && r.metrics.edgeNodeHits === 0,
    { hitEdges: r.metrics.edgeNodeHitEdges, hitSegs: r.metrics.edgeNodeHits });
  check(mode + "：长重叠段受控（>12px 重叠 ≤ 30）", r.metrics.segmentOverlapsLong <= 30, r.metrics.segmentOverlapsLong);
  check(mode + "：直线交叉 ≤ 80（旧版 742–1115）", r.metrics.straightCrossings <= 80, r.metrics.straightCrossings);
  check(mode + "：画布高度 < 7000（旧版约 18000）", r.height < 7000, r.height);
  check(mode + "：商人分带 ≥ 8", r.metrics.bands >= 8, r.metrics.bands);
  check(mode + "：存在跨商人依赖边", r.metrics.crossTraderEdges > 0, r.metrics.crossTraderEdges);
  check(mode + "：孤立任务被计入（≥ 200）", r.metrics.isolated >= 200, r.metrics.isolated);
  check(mode + "：孤立任务密集排布（任何一条带高 < 1400）",
    r.bands.every(function (b) { return b.h < 1400; }),
    r.bands.map(function (b) { return b.h; }).slice(0, 12));
  check(mode + "：布局耗时 < 1500ms", ms < 1500, ms);

  // 确定性：同输入两次 + 打乱任务对象键序
  const r2 = G.layout(tasks, { traderOrder: TRADERS });
  let same = true;
  for (let i = 0; i < r.nodes.length && same; i++) {
    if (r.nodes[i].x !== r2.nodes[i].x || r.nodes[i].y !== r2.nodes[i].y || r.nodes[i].id !== r2.nodes[i].id) { same = false; }
  }
  check(mode + "：同一输入两次布局完全一致（确定性）", same);
  const shuffled = {};
  Object.keys(tasks).reverse().forEach(function (k) { shuffled[k] = tasks[k]; });
  const r3 = G.layout(shuffled, { traderOrder: TRADERS });
  let sameOrder = true;
  for (let i = 0; i < r.nodes.length && sameOrder; i++) {
    if (r.nodes[i].x !== r3.nodes[i].x || r.nodes[i].y !== r3.nodes[i].y || r.nodes[i].id !== r3.nodes[i].id) { sameOrder = false; }
  }
  check(mode + "：打乱任务键序后坐标不变（排序稳定）", sameOrder);
  // 依赖边一条不少：每条前置/失败分支都能在结果里找到同 kind 的边
  const seen = {};
  r.edges.forEach(function (e) { seen[e.from + ">" + e.to + ">" + e.kind] = 1; });
  let missing = 0;
  Object.keys(tasks).forEach(function (to) {
    (tasks[to].prerequisites || []).forEach(function (p) {
      if (p.taskId && tasks[p.taskId] && !seen[p.taskId + ">" + to + ">and"] && !seen[p.taskId + ">" + to + ">or"]) { missing++; }
    });
    (tasks[to].failedConditions || []).forEach(function (f) {
      if (f.taskId && tasks[f.taskId] && !seen[f.taskId + ">" + to + ">fail"]) { missing++; }
    });
  });
  check(mode + "：真实依赖边一条不少（按 kind 逐条对账）", missing === 0, missing);
  // 折线：相邻且同行的边本来就 0 转折，所以看总量而不是均值
  check(mode + "：总转折数 ≥ 2×长边数（长边逐层经过）",
    r.metrics.bends >= r.metrics.longEdges * 2, { bends: r.metrics.bends, long: r.metrics.longEdges });
  check(mode + "：段数 ≥ 边数×2（不是一条直线画完）",
    r.metrics.segments >= r.metrics.edges * 2, r.metrics.segments);
});

// ------------------------------------------------------------------ 5 极长名称不炸
(function () {
  const long = "超长任务名称".repeat(20);
  const tasks = { A: { id: "A", nameZh: long, traderId: "T1", prerequisites: [] } };
  const r = G.layout(tasks, { traderOrder: ["T1"] });
  check("超长名称：不改变节点宽高，不抛异常", r.nodes.length === 1 && r.nodes[0].w === 176, r.nodes[0]);
})();

// ------------------------------------------------------------------ 输出
const bad = results.filter(function (r) { return !r.ok; });
process.stdout.write(JSON.stringify({
  ok: bad.length === 0,
  total: results.length,
  failed: bad.length,
  summary: summary,
  results: results
}));
