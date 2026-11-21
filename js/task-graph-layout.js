/* ============================================================================
 * task-graph-layout.js —— 任务依赖图布局（R19.25）
 * ----------------------------------------------------------------------------
 * 纯计算模块：**不读 DOM、不碰业务状态、不联网**。输入当前模式的任务表，
 * 输出节点坐标、正交连线折点、商人分带与一组可供测试断言的质量指标。
 *
 * 为什么需要单独一层（R19.25 审计结论）：
 *   旧实现把「层级」= 从前置算出的最长路径，然后把**所有没有前置的任务**都放进
 *   第 0 列。真实数据里 503 个任务中有 300 个没有前置（46% 是孤立点、293 个连通分量），
 *   于是第 0 列塞进 300 个节点、画布高 18000px，连线要横跨整张图 → 视觉上就是"乱"。
 *
 * 本模块的做法（分层 + 分块，Sugiyama 思路的工程化子集）：
 *   1. 用**前置关系**（不含失败分支）求弱连通分量 → 每个分量是一条真实任务线；
 *   2. 分量内做最长路径分层，跨层边补"哑节点"（dummy），使每条边只跨一层；
 *   3. 分量内用中位数/重心启发式多轮扫描，降低相邻层交叉；
 *   4. 分量作为"块"打包：按商人分带（横向一条带 = 一个商人），带内从左到右排块，
 *      超出带宽就换行 —— 每个块内部保持自己的任务线形状，块之间互不穿插；
 *   5. 连线一律正交折线（右→中→下→左），跨层边经过哑节点的折点，
 *      避免斜线穿过卡片；跨商人但同分量的边单独标记 crossTrader。
 *
 * 语义保留：
 *   · 失败分支（failConditions）不参与分层（它不是"解锁"关系），单独作为辅助边渲染；
 *   · OR / AND 语义只影响画法与图例，不影响坐标；
 *   · 真实 ID 唯一映射，一个任务一个节点，多前置连到同一个节点；
 *   · 环（真实数据里前置图无环，失败分支有环）用回边标记兜底，不删边、不死循环。
 * ==========================================================================*/
(function () {
  "use strict";

  var VERSION = "1.1";

  var DEFAULTS = {
    nodeW: 176,
    nodeH: 48,
    gapX: 54,          // 层间距
    gapY: 14,          // 同层节点间距
    blockGapX: 30,     // 块间距（横）
    blockGapY: 26,     // 块间距（纵）
    bandHeadH: 26,     // 商人带标题高度
    bandGapY: 12,      // 带间距
    maxBandW: 2600,    // 带内换行宽度预算
    dummyH: 10,
    margin: 16
  };

  function assign(target) {
    for (var i = 1; i < arguments.length; i++) {
      var src = arguments[i] || {};
      for (var k in src) { if (Object.prototype.hasOwnProperty.call(src, k)) { target[k] = src[k]; } }
    }
    return target;
  }

  // ---------------------------------------------------------------- 图构建
  /** 只取「前置 → 本任务」的 and/or 边做分层；失败分支单独收集。 */
  function buildEdges(tasks) {
    var ids = Object.keys(tasks);
    var known = {};
    ids.forEach(function (id) { known[id] = true; });
    var layering = [];        // {from,to,kind:'and'|'or'}
    var fail = [];            // {from,to,kind:'fail'}
    var dropped = [];         // 指向不存在任务的边（脏数据），记录但不静默吞掉
    ids.forEach(function (to) {
      var rec = tasks[to] || {};
      (rec.prerequisites || []).forEach(function (p) {
        if (!p || !p.taskId) { return; }
        if (!known[p.taskId]) { dropped.push({ from: p.taskId, to: to, kind: "missing" }); return; }
        if (p.taskId === to) { dropped.push({ from: p.taskId, to: to, kind: "self" }); return; }
        layering.push({ from: p.taskId, to: to, kind: (p.logic === "or" || (p.statuses || []).length > 1) ? "or" : "and" });
      });
      (rec.failedConditions || []).forEach(function (f) {
        if (!f || !f.taskId) { return; }
        if (!known[f.taskId]) { dropped.push({ from: f.taskId, to: to, kind: "fail-missing" }); return; }
        if (f.taskId === to) { return; }
        fail.push({ from: f.taskId, to: to, kind: "fail" });
      });
    });
    return { layering: layering, fail: fail, dropped: dropped };
  }

  /** 弱连通分量（无向），返回 id → compIndex 与每组成员。 */
  function components(ids, edges) {
    var parent = {};
    function find(x) {
      while (parent[x] !== x) { parent[x] = parent[parent[x]]; x = parent[x]; }
      return x;
    }
    ids.forEach(function (id) { parent[id] = id; });
    edges.forEach(function (e) {
      var a = find(e.from), b = find(e.to);
      if (a !== b) { parent[a] = b; }
    });
    var groups = {};
    ids.forEach(function (id) {
      var r = find(id);
      (groups[r] = groups[r] || []).push(id);
    });
    var list = Object.keys(groups).map(function (k) {
      return groups[k].sort();
    });
    list.sort(function (a, b) {
      if (b.length !== a.length) { return b.length - a.length; }
      return a[0] < b[0] ? -1 : 1;
    });
    return list;
  }

  /**
   * 分量内分层：从入度为 0 的节点做最长路径。
   * 有环时用 DFS 找回边并标记（不删边），回边不参与分层。
   */
  function layerize(members, edges) {
    var inComp = {};
    members.forEach(function (id) { inComp[id] = true; });
    var mine = edges.filter(function (e) { return inComp[e.from] && inComp[e.to]; });
    var out = {};
    members.forEach(function (id) { out[id] = []; });
    mine.forEach(function (e) { out[e.from].push(e); });

    // 找回边（DFS 灰白黑），标记 cycle，不让它影响分层
    var color = {}, back = {};
    members.forEach(function (id) { color[id] = 0; });
    var stack = [];
    members.forEach(function (root) {
      if (color[root] !== 0) { return; }
      var frames = [{ id: root, i: 0 }];
      color[root] = 1;
      stack = [root];
      while (frames.length) {
        var f = frames[frames.length - 1];
        var list = out[f.id];
        if (f.i >= list.length) {
          color[f.id] = 2;
          frames.pop();
          stack.pop();
          continue;
        }
        var e = list[f.i++];
        if (color[e.to] === 1) { back[e.from + ">" + e.to] = true; continue; }
        if (color[e.to] === 0) {
          color[e.to] = 1;
          frames.push({ id: e.to, i: 0 });
          stack.push(e.to);
        }
      }
    });

    var forward = mine.filter(function (e) { return !back[e.from + ">" + e.to]; });
    var indeg = {}, layer = {};
    members.forEach(function (id) { indeg[id] = 0; layer[id] = 0; });
    forward.forEach(function (e) { indeg[e.to] += 1; });
    var queue = members.filter(function (id) { return indeg[id] === 0; }).sort();
    var seen = 0;
    while (queue.length) {
      var id = queue.shift();
      seen++;
      forward.forEach(function (e) {
        if (e.from !== id) { return; }
        if (layer[e.to] < layer[id] + 1) { layer[e.to] = layer[id] + 1; }
        indeg[e.to] -= 1;
        if (indeg[e.to] === 0) { queue.push(e.to); }
      });
      queue.sort();
    }
    // 理论上不会有残留（回边已剔除），兜底：剩下的按 0 层处理
    var remaining = members.filter(function (id) { return !(layer[id] >= 0); });
    return {
      layer: layer,
      edges: mine,
      forward: forward,
      cycles: Object.keys(back).map(function (k) { return k.split(">"); }),
      unresolved: remaining,
      seen: seen
    };
  }

  /** 相邻层交叉数（用于挑选最优排序）。 */
  function countCrossings(layers, edges) {
    var pos = {};
    Object.keys(layers).forEach(function (lid) {
      layers[lid].forEach(function (id, i) { pos[id] = i; });
    });
    var n = 0;
    // O(E^2) 足够（单分量最大 29 个节点）
    for (var i = 0; i < edges.length; i++) {
      for (var j = i + 1; j < edges.length; j++) {
        var e1 = edges[i], e2 = edges[j];
        if (e1.from === e2.from || e1.to === e2.to) { continue; }
        var a1 = pos[e1.from], b1 = pos[e1.to], a2 = pos[e2.from], b2 = pos[e2.to];
        if (a1 > a2 && b1 < b2) { n++; }
        if (a1 < a2 && b1 > b2) { n++; }
      }
    }
    return n;
  }

  /** 分量内排序：初始按 (等级, 名称, id)，再做若干轮中位数扫描，保留最优。 */
  function orderLayers(tasks, members, info) {
    var maxLayer = 0;
    members.forEach(function (id) { maxLayer = Math.max(maxLayer, info.layer[id]); });
    var layers = {};
    for (var l = 0; l <= maxLayer; l++) { layers[l] = []; }
    members.forEach(function (id) { layers[info.layer[id]].push(id); });
    for (var k = 0; k <= maxLayer; k++) {
      layers[k].sort(function (a, b) {
        var ra = tasks[a] || {}, rb = tasks[b] || {};
        if ((ra.minLevel || 0) !== (rb.minLevel || 0)) { return (ra.minLevel || 0) - (rb.minLevel || 0); }
        var na = ra.nameZh || a, nb = rb.nameZh || b;
        if (na !== nb) { return na < nb ? -1 : 1; }
        return a < b ? -1 : 1;
      });
    }
    var preds = {}, succs = {};
    members.forEach(function (id) { preds[id] = []; succs[id] = []; });
    info.forward.forEach(function (e) { preds[e.to].push(e.from); succs[e.from].push(e.to); });

    function median(neighborIds, ref) {
      var vals = [];
      neighborIds.forEach(function (n) { if (ref[n] != null) { vals.push(ref[n]); } });
      if (!vals.length) { return null; }
      vals.sort(function (a, b) { return a - b; });
      var m = Math.floor(vals.length / 2);
      return vals.length % 2 ? vals[m] : (vals[m - 1] + vals[m]) / 2;
    }

    function sweep(layers, dir) {
      var order = [];
      for (var l = 0; l <= maxLayer; l++) { order.push(l); }
      if (dir < 0) { order.reverse(); }
      order.forEach(function (l) {
        var ref = {};
        Object.keys(layers).forEach(function (k) {
          if (Math.abs(Number(k) - l) !== 1) { return; }
          layers[k].forEach(function (id, i) { ref[id] = i; });
        });
        var cur = layers[l].slice();
        var keyed = cur.map(function (id, i) {
          var nb = dir > 0 ? preds[id] : succs[id];
          var m = median(nb, ref);
          return { id: id, key: m == null ? i : m, tie: i };
        });
        keyed.sort(function (a, b) {
          if (a.key !== b.key) { return a.key - b.key; }
          return a.tie - b.tie;
        });
        layers[l] = keyed.map(function (x) { return x.id; });
      });
      return layers;
    }

    // 相邻交换（transpose）：当交换同层相邻两点能减少交叉时就交换，直到不再改善
    function transpose(layers) {
      var improved = false;
      for (var l = 0; l <= maxLayer; l++) {
        var arr = layers[l];
        for (var i = 0; i + 1 < arr.length; i++) {
          var before = countCrossings(layers, info.forward);
          var tmp = arr[i]; arr[i] = arr[i + 1]; arr[i + 1] = tmp;
          var after = countCrossings(layers, info.forward);
          if (after < before) { improved = true; } else { tmp = arr[i]; arr[i] = arr[i + 1]; arr[i + 1] = tmp; }
        }
      }
      return improved;
    }

    var best = JSON.parse(JSON.stringify(layers));
    var bestScore = countCrossings(best, info.forward);
    for (var pass = 0; pass < 8; pass++) {
      var dir = pass % 2 === 0 ? 1 : -1;
      var cand = sweep(JSON.parse(JSON.stringify(layers)), dir);
      for (var t = 0; t < 2; t++) { transpose(cand); }
      var score = countCrossings(cand, info.forward);
      if (score < bestScore) { best = cand; bestScore = score; }
      layers = cand;
    }
    return { layers: best, crossings: bestScore, maxLayer: maxLayer };
  }

  /**
   * 为跨层边补哑节点：把 (u, v) 拆成逐层的虚拟点，返回
   *   chain: 每条原始边 → [id...]（含首尾）
   *   virtuals: 每个哑节点的 id
   */
  /**
   * 长边拆成"逐层经过"的哑节点：只占行位、不可见，但让每条实际绘制的线段
   * 都落在相邻两列之间的通道里（比一条横贯整块的长线交叉少得多）。
   */
  function addDummies(info, ordered) {
    var chains = [];
    var virtuals = [];
    info.forward.forEach(function (e) {
      var l1 = info.layer[e.from], l2 = info.layer[e.to];
      if (l2 - l1 <= 1) {
        chains.push({ edge: e, ids: [e.from, e.to] });
        return;
      }
      var ids = [e.from];
      for (var l = l1 + 1; l < l2; l++) {
        var vid = "\u0000d:" + e.from + ">" + e.to + "@" + l;
        virtuals.push({ id: vid, layer: l, edge: e });
        ids.push(vid);
        ordered[l] = ordered[l] || [];
        ordered[l].push(vid);
      }
      ids.push(e.to);
      chains.push({ edge: e, ids: ids });
    });
    return { chains: chains, virtuals: virtuals };
  }

  // ---------------------------------------------------------------- 主流程
  function layout(tasks, options) {
    var opts = assign({}, DEFAULTS, options || {});
    var ids = Object.keys(tasks || {}).sort();
    if (!ids.length) {
      return { nodes: [], edges: [], bands: [], width: 0, height: 0,
               metrics: { nodes: 0, edges: 0 } };
    }
    var built = buildEdges(tasks);
    var comps = components(ids, built.layering.concat(built.fail));

    var traderOrder = {};
    (opts.traderOrder || []).forEach(function (t, i) { traderOrder[t] = i; });
    function traderOf(id) { return (tasks[id] || {}).traderId || ""; }
    function traderRank(id) {
      var t = traderOf(id);
      return traderOrder[t] == null ? 999 : traderOrder[t];
    }

    // ---- 每个分量单独分层 + 排序 + 计算宽高
    // routePad：块内上下各留 10px，让「行间轨道」永远落在块内，不会压到隔壁块
    var routePad = 10;
    var pitchX = opts.nodeW + opts.gapX;
    var pitchY = opts.nodeH + opts.gapY;
    var blocks = comps.map(function (members, ci) {
      var info = layerize(members, built.layering);
      var ordered = orderLayers(tasks, members, info).layers;
      var maxLayer = 0, rows = 0, set = {};
      members.forEach(function (id) { maxLayer = Math.max(maxLayer, info.layer[id]); set[id] = true; });
      var dm = addDummies(info, ordered);
      Object.keys(ordered).forEach(function (l) { rows = Math.max(rows, ordered[l].length); });
      if (!rows) { rows = 1; }
      var width = (maxLayer + 1) * pitchX - opts.gapX;
      var fwd = {};
      info.forward.forEach(function (e) { fwd[e.from + ">" + e.to] = 1; });
      // 母线只服务"不参与分层"的边：失败分支 + 回边（数量少，代价可控）
      var busCount = info.edges.filter(function (e) {
        return !fwd[e.from + ">" + e.to];
      }).length + built.fail.filter(function (f) {
        return set[f.from] && set[f.to];
      }).length;
      var busH = busCount ? Math.min(24, busCount) * 2 + 6 : 0;
      var height = rows * pitchY - opts.gapY + routePad * 2 + busH;
      // 主商人 = 成员里出现最多的商人（并列取层级最浅的）
      var tally = {};
      members.forEach(function (id) { var t = traderOf(id); tally[t] = (tally[t] || 0) + 1; });
      var home = members.slice().sort(function (a, b) {
        var d = (tally[traderOf(b)] || 0) - (tally[traderOf(a)] || 0);
        if (d !== 0) { return d; }
        if (info.layer[a] !== info.layer[b]) { return info.layer[a] - info.layer[b]; }
        return a < b ? -1 : 1;
      })[0];
      var rootLevel = (tasks[home] || {}).minLevel || 0;
      return {
        index: ci, members: members, set: set, info: info, ordered: ordered,
        chains: dm.chains, virtuals: dm.virtuals,
        maxLayer: maxLayer, rows: rows, width: width, height: height,
        busCount: busCount, busH: busH,
        homeTrader: traderOf(home), traderRank: traderRank(home),
        rootLevel: rootLevel, rootName: (tasks[home] || {}).nameZh || home,
        crossings: countCrossings(ordered, info.forward)
      };
    });

    // ---- 按商人分带：先放「任务线块」，再把「孤立任务」密集排在带内
    // 分组优先级：依赖关系 > 商人分带。一个分量（任务线）整体只放一条带里，
    // 所以跨商人的任务线不会被分带截断；带里出现外商人节点时只做标记，不拆线。
    var bandKeys = Object.keys(traderOrder);
    blocks.forEach(function (b) {
      if (bandKeys.indexOf(b.homeTrader) < 0 && b.homeTrader) {
        traderOrder[b.homeTrader] = 900 + bandKeys.length;
        bandKeys.push(b.homeTrader);
      }
    });
    var byBand = {};
    blocks.forEach(function (b) {
      (byBand[b.homeTrader] = byBand[b.homeTrader] || []).push(b);
    });
    var bandList = Object.keys(byBand).sort(function (a, b) {
      return (traderOrder[a] == null ? 999 : traderOrder[a]) - (traderOrder[b] == null ? 999 : traderOrder[b]);
    });

    var nodes = [];
    var edges = [];
    var bands = [];
    var cursorY = opts.margin;

    bandList.forEach(function (trader) {
      var list = byBand[trader].slice();
      var chains = list.filter(function (b) { return b.members.length > 1; });
      var singles = list.filter(function (b) { return b.members.length === 1; });
      var bandTop = cursorY;
      var bandLabelY = bandTop + opts.bandHeadH - 9;

      // 1) 任务线块：高块优先的货架打包（同一行按最高块决定行高）
      chains.sort(function (a, b) {
        if (a.height !== b.height) { return b.height - a.height; }
        if (a.width !== b.width) { return b.width - a.width; }
        if (a.rootLevel !== b.rootLevel) { return a.rootLevel - b.rootLevel; }
        return a.rootName < b.rootName ? -1 : 1;
      });
      var x = opts.margin, y = bandTop + opts.bandHeadH, rowH = 0;
      chains.forEach(function (b) {
        if (x + b.width > opts.margin + opts.maxBandW && rowH > 0) {
          x = opts.margin;
          y += rowH + opts.blockGapY;
          rowH = 0;
        }
        b.originX = x;
        b.originY = y;
        b.nodeTop = y + routePad + b.busH;
        x += b.width + opts.blockGapX;
        rowH = Math.max(rowH, b.height);
      });
      if (rowH > 0) { y += rowH + opts.blockGapY; }

      // 2) 孤立任务：带内密集网格（不再一条"单节点任务线"独占一行）
      var singleGapX = 14, singleGapY = 8;
      var perRow = Math.max(1, Math.floor((opts.maxBandW + singleGapX) / (opts.nodeW + singleGapX)));
      var singlesTop = y;
      singles.forEach(function (b, i) {
        b.originX = opts.margin + (i % perRow) * (opts.nodeW + singleGapX);
        b.originY = singlesTop + Math.floor(i / perRow) * (opts.nodeH + singleGapY);
        b.nodeTop = b.originY;
      });
      var singleRows = Math.ceil(singles.length / perRow);
      var bottomChains = chains.length ? y - opts.blockGapY : bandTop + opts.bandHeadH;
      var bottomSingles = singles.length
        ? singlesTop + singleRows * (opts.nodeH + singleGapY) - singleGapY
        : bottomChains;
      var bandBottom = Math.max(bottomChains, bottomSingles);
      var contentRight = opts.margin;
      list.forEach(function (b) {
        contentRight = Math.max(contentRight, b.originX + Math.max(b.width, opts.nodeW));
      });
      var foreign = list.reduce(function (s, b) {
        return s + b.members.filter(function (id) { return traderOf(id) !== trader; }).length;
      }, 0);
      bands.push({
        trader: trader, y: bandTop, h: bandBottom - bandTop,
        w: Math.ceil(contentRight - opts.margin + 8),
        labelY: bandLabelY,
        blocks: chains.length,
        hasEdges: chains.length,
        singles: singles.length,
        foreign: foreign,
        nodes: list.reduce(function (s, b) { return s + b.members.length; }, 0)
      });
      cursorY = bandBottom + opts.bandGapY;
    });

    // ---- 落坐标（行距 = nodeH + gapY，所有列共用同一套行网格）
    var nodeIndex = {};
    blocks.forEach(function (b) {
      if (b.members.length === 1 && b.nodeTop == null) { b.nodeTop = b.originY; }
      Object.keys(b.ordered).forEach(function (l) {
        b.ordered[l].forEach(function (id, i) {
          var nx = b.originX + Number(l) * pitchX;
          var ny = b.nodeTop + i * pitchY;
          if (id.charAt(0) === "\u0000") {
            nodeIndex[id] = {
              id: id, dummy: true, x: nx, y: ny + (opts.nodeH - opts.dummyH) / 2,
              w: 0, h: opts.dummyH, layer: Number(l), order: i, comp: b.index,
              trader: "", compTrader: b.homeTrader, crossTrader: false
            };
            return;
          }
          var rec = tasks[id] || {};
          nodeIndex[id] = {
            id: id, dummy: false, x: nx, y: ny, w: opts.nodeW, h: opts.nodeH,
            layer: Number(l), order: i, comp: b.index,
            trader: traderOf(id), compTrader: b.homeTrader,
            crossTrader: traderOf(id) !== b.homeTrader
          };
          nodes.push(nodeIndex[id]);
        });
      });
    });

    // ---------------------------------------------------------------- 正交路由
    // 只允许两种走线：
    //   竖向 → 列间通道 x = 层右边界 + gapX/2 + lane*5（通道在节点之间的缝里）
    //   横向 → 行间轨道 y = 行底 + gapY/2 + lane*4（轨道在行与行之间的缝里）
    // 因为节点只占「行区间」，缝里没有节点，所以线段在几何上不可能穿过卡片。
    // 长边（跨多层）走：右出 → 通道 → 轨道 → 入通道 → 左进（4 个转折）
    // 回边（数据成环）：右出 → 块外走廊 → 轨道（横穿本块，仍在缝里）→ 入通道 → 左进
    var lanesByChannel = {};
    var lanesByBus = {};

    function channelX(b, layer, lane) {
      return b.originX + layer * pitchX + opts.nodeW + opts.gapX / 2 + lane * 2.5;
    }
    /** 块顶母线：跨层边/回边共享的水平总线，按 lane 分层，永远在节点上方 */
    function busY(b, lane) {
      return b.originY + routePad + 3 + lane * 2;
    }
    function freeLane(store, key, lo, hi, maxLane, minGap) {
      var used = store[key] || [];
      var order = [0];
      for (var d = 1; d <= maxLane; d++) { order.push(d, -d); }
      for (var oi = 0; oi < order.length; oi++) {
        var lane = order[oi], clash = false;
        for (var i = 0; i < used.length; i++) {
          if (used[i].lane !== lane) { continue; }
          if (Math.min(hi, used[i].hi) - Math.max(lo, used[i].lo) > minGap) { clash = true; break; }
        }
        if (!clash) { return lane; }
      }
      return null;
    }
    function useLane(store, key, lo, hi, lane) {
      (store[key] = store[key] || []).push({ lo: lo, hi: hi, lane: lane });
    }
    function portOffset(i, n) {
      if (n <= 1) { return 0; }
      var v = (i - (n - 1) / 2) * 6;
      return Math.max(-12, Math.min(12, v));
    }
    function cleanPts(pts) {
      var out = [pts[0]];
      for (var i = 1; i < pts.length; i++) {
        var p = pts[i], q = out[out.length - 1];
        if (Math.abs(p[0] - q[0]) < 0.5 && Math.abs(p[1] - q[1]) < 0.5) { continue; }
        if (out.length >= 2) {
          var r = out[out.length - 2];
          if ((Math.abs(r[0] - q[0]) < 0.5 && Math.abs(q[0] - p[0]) < 0.5) ||
              (Math.abs(r[1] - q[1]) < 0.5 && Math.abs(q[1] - p[1]) < 0.5)) {
            out[out.length - 1] = p;
            continue;
          }
        }
        out.push(p);
      }
      return out;
    }

    /** 相邻两列的一跳：右出 → 列间通道 → 左进（2 个转折） */
    function routeHop(b, a, c, outOff, inOff) {
      var ls = a.layer;
      var x1 = a.dummy ? a.x : a.x + a.w;
      var x2 = c.dummy ? c.x : c.x;
      var y1 = a.y + a.h / 2 + (outOff || 0);
      var y2 = c.y + c.h / 2 + (inOff || 0);
      if (!(c.layer === ls + 1)) { return null; }
      var key = b.index + "|" + ls;
      var lo = Math.min(y1, y2), hi = Math.max(y1, y2);
      var lane = freeLane(lanesByChannel, key, lo, hi, 10, 2);
      if (lane === null) { lane = 0; }
      useLane(lanesByChannel, key, lo, hi, lane);
      var cx = channelX(b, ls, lane);
      var pts = Math.abs(y1 - y2) < 0.5 ? [[x1, y1], [x2, y2]]
        : [[x1, y1], [cx, y1], [cx, y2], [x2, y2]];
      return cleanPts(pts);
    }

    /** 跨层/回边：右出 → 通道 → 块顶母线 → 通道 → 左进（4 个转折） */
    function busRoute(b, a, c, y1, y2) {
      var ls = a.layer, lt = c.layer;
      var exitBase = ls <= b.maxLayer - 1 ? channelX(b, ls, 0) : (b.originX + b.width + 8);
      var entryBase = lt >= 1 ? channelX(b, lt - 1, 0) : (b.originX - 8);
      var bl = freeLane(lanesByBus, String(b.index),
        Math.min(exitBase, entryBase), Math.max(exitBase, entryBase), 23, 2);
      if (bl === null) { bl = 0; }
      useLane(lanesByBus, String(b.index),
        Math.min(exitBase, entryBase), Math.max(exitBase, entryBase), bl);
      var by = busY(b, bl);
      var exitX = exitBase;
      if (ls <= b.maxLayer - 1) {
        var ekey = b.index + "|" + ls;   // 与相邻跳共用同一个通道占用表
        var elo = Math.min(y1, by), ehi = Math.max(y1, by);
        var el = freeLane(lanesByChannel, ekey, elo, ehi, 10, 2);
        if (el === null) { el = 0; }
        useLane(lanesByChannel, ekey, elo, ehi, el);
        exitX = channelX(b, ls, el);
      } else {
        // 最后一列没有"右边那条缝"，走块外走廊，同样要分道
        var rk = "corrR@" + Math.round(b.originX + b.width + 8);
        var rlo = Math.min(y1, by), rhi = Math.max(y1, by);
        var rl = freeLane(lanesByChannel, rk, rlo, rhi, 4, 2);
        if (rl === null) { rl = 0; }
        useLane(lanesByChannel, rk, rlo, rhi, rl);
        exitX = b.originX + b.width + 8 + rl * 2;
      }
      var entryX = entryBase;
      if (lt >= 1) {
        var nkey = b.index + "|" + (lt - 1);
        var nlo = Math.min(by, y2), nhi = Math.max(by, y2);
        var nl = freeLane(lanesByChannel, nkey, nlo, nhi, 10, 2);
        if (nl === null) { nl = 0; }
        useLane(lanesByChannel, nkey, nlo, nhi, nl);
        entryX = channelX(b, lt - 1, nl);
      } else {
        var lk = "corrL@" + Math.round(b.originX - 8);
        var llo = Math.min(by, y2), lhi = Math.max(by, y2);
        var ll = freeLane(lanesByChannel, lk, llo, lhi, 4, 2);
        if (ll === null) { ll = 0; }
        useLane(lanesByChannel, lk, llo, lhi, ll);
        entryX = b.originX - 8 - ll * 2;
      }
      return cleanPts([[a.dummy ? a.x : a.x + a.w, y1], [exitX, y1], [exitX, by],
                       [entryX, by], [entryX, y2], [c.dummy ? c.x : c.x, y2]]);
    }

    blocks.forEach(function (b) {
      var reqs = [];
      b.info.edges.forEach(function (e) { reqs.push(e); });
      built.fail.forEach(function (f) { if (b.set[f.from] && b.set[f.to]) { reqs.push(f); } });
      reqs.sort(function (p, q) {
        if (p.from !== q.from) { return p.from < q.from ? -1 : 1; }
        if (p.to !== q.to) { return p.to < q.to ? -1 : 1; }
        return 0;
      });
      var outCount = {}, inCount = {}, outSeen = {}, inSeen = {}, portMap = {};
      reqs.forEach(function (e) {
        outCount[e.from] = (outCount[e.from] || 0) + 1;
        inCount[e.to] = (inCount[e.to] || 0) + 1;
      });
      reqs.forEach(function (e) {
        var iOut = (outSeen[e.from] = (outSeen[e.from] || 0) + 1) - 1;
        var iIn = (inSeen[e.to] = (inSeen[e.to] || 0) + 1) - 1;
        portMap[e.from + ">" + e.to + ">" + e.kind] = {
          outOff: portOffset(iOut, outCount[e.from]),
          inOff: portOffset(iIn, inCount[e.to])
        };
      });
      function portOf(e) {
        return portMap[e.from + ">" + e.to + ">" + e.kind] || { outOff: 0, inOff: 0 };
      }

      // 1) 前置链（长边已由哑节点拆成逐层相邻跳）
      b.chains.forEach(function (ch) {
        var e = ch.edge;
        var p = portOf(e);
        var pts = [];
        for (var i = 0; i < ch.ids.length - 1; i++) {
          var a = nodeIndex[ch.ids[i]], c = nodeIndex[ch.ids[i + 1]];
          if (!a || !c) { pts = null; break; }
          var seg = routeHop(b, a, c, i === 0 ? p.outOff : 0,
            i === ch.ids.length - 2 ? p.inOff : 0);
          if (!seg) { pts = null; break; }
          pts = i === 0 ? seg : pts.concat(seg.slice(1));
        }
        if (!pts) { return; }
        edges.push({
          from: e.from, to: e.to, kind: e.kind,
          span: b.info.layer[e.to] - b.info.layer[e.from], cycle: false,
          points: cleanPts(pts), aux: false,
          crossTrader: traderOf(e.from) !== traderOf(e.to),
          crossBand: traderOf(e.from) !== b.homeTrader || traderOf(e.to) !== b.homeTrader
        });
      });

      // 2) 回边（数据成环）：不参与分层，但必须画出来
      var fwd = {};
      b.info.forward.forEach(function (e) { fwd[e.from + ">" + e.to] = 1; });
      b.info.edges.forEach(function (e) {
        if (fwd[e.from + ">" + e.to]) { return; }
        var a = nodeIndex[e.from], c = nodeIndex[e.to];
        if (!a || !c) { return; }
        var p = portOf(e);
        var pts = busRoute(b, a, c, a.y + a.h / 2 + p.outOff, c.y + c.h / 2 + p.inOff);
        edges.push({
          from: e.from, to: e.to, kind: e.kind, span: 0, cycle: true,
          points: pts, aux: false,
          crossTrader: traderOf(e.from) !== traderOf(e.to),
          crossBand: traderOf(e.from) !== b.homeTrader || traderOf(e.to) !== b.homeTrader
        });
      });

      // 3) 失败分支：辅助边，不参与分层；只是线型不同，语义仍由 kind=fail 保留
      built.fail.forEach(function (f) {
        if (!(b.set[f.from] && b.set[f.to])) { return; }
        var a = nodeIndex[f.from], c = nodeIndex[f.to];
        if (!a || !c) { return; }
        var p = portOf(f);
        var ls = b.info.layer[f.from], lt = b.info.layer[f.to];
        var y1 = a.y + a.h / 2 + p.outOff, y2 = c.y + c.h / 2 + p.inOff;
        var pts = lt === ls + 1 ? routeHop(b, a, c, p.outOff, p.inOff) : busRoute(b, a, c, y1, y2);
        if (!pts) { return; }
        edges.push({
          from: f.from, to: f.to, kind: "fail", span: 0, cycle: false,
          points: cleanPts(pts), aux: true,
          crossTrader: traderOf(f.from) !== traderOf(f.to),
          crossBand: traderOf(f.from) !== b.homeTrader || traderOf(f.to) !== b.homeTrader
        });
      });
    });

    // ---- 尺寸与指标：全部基于"真正生成的折线段"，不是直线近似
    var maxX = 0, maxY = 0;
    nodes.forEach(function (n) { maxX = Math.max(maxX, n.x + n.w); maxY = Math.max(maxY, n.y + n.h); });
    bands.forEach(function (b) { maxY = Math.max(maxY, b.y + b.h); });

    var segs = [];
    var totalBends = 0;
    edges.forEach(function (e) {
      e.bends = 0;
      for (var i = 1; i < e.points.length - 1; i++) {
        var ax = e.points[i][0] - e.points[i - 1][0], ay = e.points[i][1] - e.points[i - 1][1];
        var bx = e.points[i + 1][0] - e.points[i][0], by = e.points[i + 1][1] - e.points[i][1];
        if (Math.abs(ax * by - ay * bx) > 0.5) { e.bends++; }
      }
      totalBends += e.bends;
      for (var s = 0; s < e.points.length - 1; s++) {
        segs.push({ a: e.points[s], b: e.points[s + 1], e: e });
      }
    });

    function ccw(p, q, r) {
      return (r[1] - p[1]) * (q[0] - p[0]) - (q[1] - p[1]) * (r[0] - p[0]);
    }
    function properCross(a, b, c, d) {
      var d1 = ccw(c, d, a), d2 = ccw(c, d, b), d3 = ccw(a, b, c), d4 = ccw(a, b, d);
      return ((d1 > 0) !== (d2 > 0)) && ((d3 > 0) !== (d4 > 0));
    }
    function samePt(p, q) { return Math.abs(p[0] - q[0]) < 0.5 && Math.abs(p[1] - q[1]) < 0.5; }
    /** 线段与矩形内部是否相交（Liang-Barsky；矩形已内缩，避免 1px 贴边误判） */
    function segIntersectsRect(p, q, r) {
      var dx = q[0] - p[0], dy = q[1] - p[1];
      var t0 = 0, t1 = 1;
      var pp = [-dx, dx, -dy, dy];
      var qq = [p[0] - r.x, r.x + r.w - p[0], p[1] - r.y, r.y + r.h - p[1]];
      for (var i = 0; i < 4; i++) {
        if (Math.abs(pp[i]) < 1e-9) { if (qq[i] < 0) { return false; } continue; }
        var t = qq[i] / pp[i];
        if (pp[i] < 0) {
          if (t > t1) { return false; }
          if (t > t0) { t0 = t; }
        } else {
          if (t < t0) { return false; }
          if (t < t1) { t1 = t; }
        }
      }
      return true;
    }

    var segCross = 0, segOverlap = 0, segOverlapLong = 0;
    for (var i2 = 0; i2 < segs.length; i2++) {
      for (var j2 = i2 + 1; j2 < segs.length; j2++) {
        var s1 = segs[i2], s2 = segs[j2];
        if (s1.e === s2.e) { continue; }
        if (samePt(s1.a, s2.a) || samePt(s1.a, s2.b) ||
            samePt(s1.b, s2.a) || samePt(s1.b, s2.b)) { continue; }
        if (properCross(s1.a, s1.b, s2.a, s2.b)) { segCross++; continue; }
        var h1 = Math.abs(s1.a[1] - s1.b[1]) < 0.5;
        var h2 = Math.abs(s2.a[1] - s2.b[1]) < 0.5;
        if (h1 && h2 && Math.abs(s1.a[1] - s2.a[1]) < 0.5) {
          var lo = Math.max(Math.min(s1.a[0], s1.b[0]), Math.min(s2.a[0], s2.b[0]));
          var hi = Math.min(Math.max(s1.a[0], s1.b[0]), Math.max(s2.a[0], s2.b[0]));
          if (hi - lo > 1) { segOverlap++; if (hi - lo > 12) { segOverlapLong++; } }
        } else if (!h1 && !h2 && Math.abs(s1.a[0] - s2.a[0]) < 0.5) {
          var lo2 = Math.max(Math.min(s1.a[1], s1.b[1]), Math.min(s2.a[1], s2.b[1]));
          var hi2 = Math.min(Math.max(s1.a[1], s1.b[1]), Math.max(s2.a[1], s2.b[1]));
          if (hi2 - lo2 > 1) { segOverlap++; if (hi2 - lo2 > 12) { segOverlapLong++; } }
        }
      }
    }

    // 连接线穿过任务卡片：必须为 0（矩形内缩 1.5px，端点贴边不算）
    var hitEdges = 0, hitSegs = 0;
    edges.forEach(function (e) {
      var hit = false;
      for (var s = 0; s < e.points.length - 1; s++) {
        for (var ni = 0; ni < nodes.length; ni++) {
          var n = nodes[ni];
          if (n.id === e.from || n.id === e.to) { continue; }
          if (segIntersectsRect(e.points[s], e.points[s + 1],
              { x: n.x + 1.5, y: n.y + 1.5, w: n.w - 3, h: n.h - 3 })) {
            hitSegs++;
            hit = true;
            break;
          }
        }
      }
      if (hit) { hitEdges++; }
      e.throughNode = hit;
    });

    // 与旧版可比的"直线交叉"指标（旧版画贝塞尔，端点相同，用同一把尺子比）
    var straight = 0;
    var lines = [];
    edges.forEach(function (e) {
      if (e.aux) { return; }
      var a = nodeIndex[e.from], b = nodeIndex[e.to];
      if (!a || !b) { return; }
      lines.push([[a.x + a.w, a.y + a.h / 2], [b.x, b.y + b.h / 2]]);
    });
    for (var li = 0; li < lines.length; li++) {
      for (var lj = li + 1; lj < lines.length; lj++) {
        if (properCross(lines[li][0], lines[li][1], lines[lj][0], lines[lj][1])) { straight++; }
      }
    }

    // 节点重叠（应恒为 0）
    var overlaps = 0;
    for (var a3 = 0; a3 < nodes.length; a3++) {
      for (var b3 = a3 + 1; b3 < nodes.length; b3++) {
        var n1 = nodes[a3], n2 = nodes[b3];
        if (n1.x < n2.x + n2.w && n2.x < n1.x + n1.w &&
            n1.y < n2.y + n2.h && n2.y < n1.y + n1.h) { overlaps++; }
      }
    }

    var canvasW = Math.ceil(maxX + opts.margin);
    var canvasH = Math.ceil(maxY + opts.margin);
    var nodeArea = nodes.reduce(function (s, n) { return s + n.w * n.h; }, 0);

    return {
      version: VERSION,
      nodes: nodes,
      index: nodeIndex,
      edges: edges,
      bands: bands,
      width: canvasW,
      height: canvasH,
      droppedEdges: built.dropped,
      metrics: {
        nodes: nodes.length,
        edges: edges.filter(function (e) { return !e.aux; }).length,
        auxEdges: edges.filter(function (e) { return e.aux; }).length,
        failEdges: edges.filter(function (e) { return e.kind === "fail"; }).length,
        cycleEdges: edges.filter(function (e) { return e.cycle; }).length,
        components: blocks.length,
        isolated: blocks.filter(function (b) { return b.members.length === 1; }).length,
        bands: bands.length,
        layers: blocks.reduce(function (s, b) { return Math.max(s, b.maxLayer + 1); }, 0),
        rows: blocks.reduce(function (s, b) { return Math.max(s, b.rows); }, 0),
        dummies: blocks.reduce(function (s2, b) { return s2 + b.virtuals.length; }, 0),
        segments: segs.length,
        bends: totalBends,
        avgBends: edges.length ? Math.round(totalBends / edges.length * 100) / 100 : 0,
        segmentCrossings: segCross,
        segmentOverlaps: segOverlap,
        segmentOverlapsLong: segOverlapLong,
        edgeNodeHits: hitSegs,
        edgeNodeHitEdges: hitEdges,
        straightCrossings: straight,
        nodeOverlaps: overlaps,
        longEdges: edges.filter(function (e) { return e.span > 1; }).length,
        crossTraderEdges: edges.filter(function (e) { return e.crossTrader; }).length,
        dropped: built.dropped.length,
        cycles: blocks.reduce(function (s, b) { return s + b.info.cycles.length; }, 0),
        canvasArea: canvasW * canvasH,
        nodeArea: nodeArea,
        fillRatio: Math.round(nodeArea / Math.max(canvasW * canvasH, 1) * 1000) / 1000
      }
    };
  }

  window.GWTaskGraph = { version: VERSION, layout: layout, defaults: DEFAULTS };
})();
