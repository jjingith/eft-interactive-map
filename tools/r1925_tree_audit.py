# -*- coding: utf-8 -*-
"""R19.25 任务树布局审计：把"乱"变成数字（真实浏览器 + 几何计算）。

提取当前页面的真实布局（节点坐标、真实依赖边），然后计算：
  · 分层交叉数（相邻层之间，经典 layered-crossing 指标）
  · 几何交叉数（任意两条边线段相交）
  · 长边数（跨越多层）、穿节点边数（直线穿过别的节点框）
  · 节点重叠（应为 0）、每层节点数、画布尺寸、最大出入度
  · 环（真实数据里是否存在）

用法：
    python tools/r1925_tree_audit.py --base http://127.0.0.1:8790 --tag before
产物：
    docs/r19.25-task-tree/layout-<tag>.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r181_accept import CDP, find_chrome, launch, wait_ready  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "docs", "r19.25-task-tree")
MODES = ("regular", "pve", "pvps")

EXTRACT = r"""
(function () {
  var st = window.GWTasks && window.GWTasks.state;
  if (!st || !st.graph) { return JSON.stringify({ error: "no graph" }); }
  var g = st.graph;
  var nodes = [];
  Object.keys(g.nodes).forEach(function (id) {
    var n = g.nodes[id];
    var rec = st.tasks[id] || {};
    var pre = (rec.prerequisites || []).map(function (p) {
      return { from: p.taskId, kind: "and", statuses: p.statuses || ["complete"], logic: p.logic || "all" };
    });
    var fail = (rec.failedConditions || []).map(function (f) {
      return { from: f.taskId, kind: "fail", statuses: f.statuses || [] };
    });
    nodes.push({
      // 旧版有 rank/row，新版是 layer/order（分量内层号）；两者都取，便于前后对比
      id: id, x: n.x, y: n.y,
      rank: (n.rank != null ? n.rank : (n.layer != null ? n.layer : 0)),
      row: (n.row != null ? n.row : (n.order != null ? n.order : 0)),
      w: 176, h: 48,
      name: rec.nameZh || "",
      trader: rec.traderId || "",
      level: rec.minLevel || 0,
      edges: pre.concat(fail)
    });
  });
  var paths = [].map.call(document.querySelectorAll("#tk-edges .tk-edge"), function (p) {
    return { d: p.getAttribute("d") || "", kind: p.getAttribute("data-kind") || "",
             from: p.getAttribute("data-from") || "", to: p.getAttribute("data-to") || "" };
  });
  return JSON.stringify({
    mode: st.mode,
    width: g.width, height: g.height,
    paths: paths,
    nodes: nodes,
    domNodes: document.querySelectorAll("#tk-nodes .tk-node").length,
    domEdges: document.querySelectorAll("#tk-edges .tk-edge").length
  });
})()
"""


# ------------------------------------------------------------------ 几何
def seg_intersect(a, b, c, d):
    def ccw(p, q, r):
        return (r[1] - p[1]) * (q[0] - p[0]) - (q[1] - p[1]) * (r[0] - p[0])
    d1, d2 = ccw(c, d, a), ccw(c, d, b)
    d3, d4 = ccw(a, b, c), ccw(a, b, d)
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0))


def seg_hits_box(p, q, box, pad=1.0):
    """线段是否穿过矩形内部（不含端点在内的角点接触）。"""
    x, y, w, h = box
    x0, y0, x1, y1 = x + pad, y + pad, x + w - pad, y + h - pad
    # 线段与矩形四边求交
    edges = [((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)),
             ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))]
    for c, d in edges:
        if seg_intersect(p, q, c, d):
            return True
    # 完全包含
    if x0 < p[0] < x1 and y0 < p[1] < y1:
        return True
    return False


def parse_path(d: str):
    """把 SVG path 的 M/L 指令解析成点列（本项目只输出正交折线）。"""
    pts = []
    for m in re.finditer(r"[ML]\s*(-?\d+(?:\.\d+)?)[ ,]+(-?\d+(?:\.\d+)?)", d or ""):
        pts.append((float(m.group(1)), float(m.group(2))))
    return pts


def orth_metrics(paths, boxes):
    """真实折线段的交叉 / 重叠 / 穿节点 / 转折数（不是直线近似）。"""
    segs = []
    bends = 0
    for it in paths:
        pts = parse_path(it.get("d"))
        for i in range(1, len(pts) - 1):
            ax, ay = pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]
            bx, by = pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]
            if abs(ax * by - ay * bx) > 0.5:
                bends += 1
        for i in range(len(pts) - 1):
            segs.append((pts[i], pts[i + 1], it))
    cross = overlap = overlap_long = 0
    for i in range(len(segs)):
        a1, b1, e1 = segs[i]
        for j in range(i + 1, len(segs)):
            a2, b2, e2 = segs[j]
            if e1 is e2:
                continue
            if a1 in (a2, b2) or b1 in (a2, b2):
                continue
            if seg_intersect(a1, b1, a2, b2):
                cross += 1
                continue
            h1 = abs(a1[1] - b1[1]) < 0.5
            h2 = abs(a2[1] - b2[1]) < 0.5
            if h1 and h2 and abs(a1[1] - a2[1]) < 0.5:
                lo = max(min(a1[0], b1[0]), min(a2[0], b2[0]))
                hi = min(max(a1[0], b1[0]), max(a2[0], b2[0]))
                if hi - lo > 1:
                    overlap += 1
                    if hi - lo > 12:
                        overlap_long += 1
            elif (not h1) and (not h2) and abs(a1[0] - a2[0]) < 0.5:
                lo = max(min(a1[1], b1[1]), min(a2[1], b2[1]))
                hi = min(max(a1[1], b1[1]), max(a2[1], b2[1]))
                if hi - lo > 1:
                    overlap += 1
                    if hi - lo > 12:
                        overlap_long += 1
    hit_edges = 0
    hit_segs = 0
    for it in paths:
        pts = parse_path(it.get("d"))
        hit = False
        for i in range(len(pts) - 1):
            for nid, box in boxes.items():
                if nid in (it.get("from"), it.get("to")):
                    continue
                x, y, w, h = box
                if seg_hits_box(pts[i], pts[i + 1], (x + 1.5, y + 1.5, w - 3, h - 3)):
                    hit_segs += 1
                    hit = True
                    break
        if hit:
            hit_edges += 1
    return {
        "segments": len(segs), "bends": bends,
        "avgBends": round(bends / max(len(paths), 1), 2),
        "segmentCrossings": cross,
        "segmentOverlaps": overlap, "segmentOverlapsLong": overlap_long,
        "edgeNodeHits": hit_segs, "edgeNodeHitEdges": hit_edges,
    }


def analyse(view: dict) -> dict:
    nodes = view.get("nodes") or []
    if not nodes:
        return {"error": "no nodes"}
    by_id = {n["id"]: n for n in nodes}
    boxes = {n["id"]: (n["x"], n["y"], n["w"], n["h"]) for n in nodes}
    edges = []
    for n in nodes:
        for e in n["edges"]:
            if e["from"] in by_id and e["from"] != n["id"]:
                edges.append({"from": e["from"], "to": n["id"], "kind": e["kind"]})
    # 端点：左侧进、右侧出（与渲染一致：父右中 → 子左中）
    def p_out(nid):
        x, y, w, h = boxes[nid]
        return (x + w, y + h / 2.0)

    def p_in(nid):
        x, y, w, h = boxes[nid]
        return (x, y + h / 2.0)

    # 节点重叠
    overlaps = 0
    items = list(boxes.items())
    for i in range(len(items)):
        x1, y1, w1, h1 = items[i][1]
        for j in range(i + 1, len(items)):
            x2, y2, w2, h2 = items[j][1]
            if x1 < x2 + w2 and x2 < x1 + w1 and y1 < y2 + h2 and y2 < y1 + h1:
                overlaps += 1
    # 层
    layers = {}
    for n in nodes:
        layers.setdefault(n["rank"], []).append(n["id"])
    # 相邻层交叉（倒置计数）
    adj_cross = 0
    long_edges = 0
    by_gap = {}
    for e in edges:
        la, lb = by_id[e["from"]]["rank"], by_id[e["to"]]["rank"]
        span = lb - la
        if span <= 0:
            continue
        if span > 1:
            long_edges += 1
        if span == 1:
            by_gap.setdefault(la, []).append(e)
    for gap, es in by_gap.items():
        for i in range(len(es)):
            for j in range(i + 1, len(es)):
                a, b = es[i], es[j]
                if a["from"] == b["from"] or a["to"] == b["to"]:
                    continue
                ya1 = by_id[a["from"]]["row"]
                ya2 = by_id[a["to"]]["row"]
                yb1 = by_id[b["from"]]["row"]
                yb2 = by_id[b["to"]]["row"]
                if (ya1 - yb1) * (ya2 - yb2) < 0:
                    adj_cross += 1
    # 几何交叉（直线近似）
    geo_cross = 0
    segs = [(p_out(e["from"]), p_in(e["to"])) for e in edges]
    for i in range(len(segs)):
        for j in range(i + 1, len(segs)):
            if seg_intersect(segs[i][0], segs[i][1], segs[j][0], segs[j][1]):
                geo_cross += 1
    # 穿节点
    through = 0
    for e in edges:
        p, q = p_out(e["from"]), p_in(e["to"])
        for nid, box in boxes.items():
            if nid in (e["from"], e["to"]):
                continue
            if seg_hits_box(p, q, box):
                through += 1
                break
    deg_in = {}
    deg_out = {}
    for e in edges:
        deg_in[e["to"]] = deg_in.get(e["to"], 0) + 1
        deg_out[e["from"]] = deg_out.get(e["from"], 0) + 1
    per_layer = [len(v) for v in layers.values()]
    orth = orth_metrics(view.get("paths") or [], boxes) if view.get("paths") else None
    return {
        "mode": view.get("mode"),
        "nodes": len(nodes),
        "edges": len(edges),
        "layers": len(layers),
        "perLayerMax": max(per_layer) if per_layer else 0,
        "perLayerAvg": round(sum(per_layer) / len(per_layer), 1) if per_layer else 0,
        "canvas": {"w": view.get("width"), "h": view.get("height")},
        "nodeOverlaps": overlaps,
        "adjacentCrossings": adj_cross,
        "geometricCrossings": geo_cross,
        "longEdges": long_edges,
        "edgesThroughNodes": through,
        "crossingsPerEdge": round(geo_cross / max(len(edges), 1), 2),
        "maxIndegree": max(deg_in.values()) if deg_in else 0,
        "maxOutdegree": max(deg_out.values()) if deg_out else 0,
        "domNodes": view.get("domNodes"),
        "domEdges": view.get("domEdges"),
        "orthogonal": orth,
        "cycles": detect_cycles(edges),
    }


def detect_cycles(edges):
    """真实数据里有没有环（用迭代 DFS 找一条即可）。"""
    graph = {}
    for e in edges:
        graph.setdefault(e["from"], []).append(e["to"])
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {}
    found = []
    for start in list(graph):
        if color.get(start, WHITE) != WHITE:
            continue
        stack = [(start, iter(graph.get(start, [])))]
        color[start] = GRAY
        path = [start]
        while stack:
            node, it = stack[-1]
            advanced = False
            for nxt in it:
                if color.get(nxt, WHITE) == GRAY:
                    found.append(path[path.index(nxt):] + [nxt] if nxt in path else [node, nxt])
                    if len(found) >= 3:
                        return found
                elif color.get(nxt, WHITE) == WHITE:
                    color[nxt] = GRAY
                    stack.append((nxt, iter(graph.get(nxt, []))))
                    path.append(nxt)
                    advanced = True
                    break
            if not advanced:
                color[node] = BLACK
                stack.pop()
                if path:
                    path.pop()
    return found


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8790")
    ap.add_argument("--port", type=int, default=9822)
    ap.add_argument("--tag", default="before")
    args = ap.parse_args(argv)
    base = args.base.rstrip("/")
    os.makedirs(OUT_DIR, exist_ok=True)
    prof = os.path.join(os.environ.get("TEMP", "."), "r1925audit_%d" % args.port)
    proc, ws = launch(find_chrome(), args.port, 1680, 1050, prof)
    cdp = CDP(ws)
    result = {"tag": args.tag, "base": base, "modes": {}}
    try:
        cdp.call("Page.enable")
        cdp.call("Runtime.enable")
        cdp.call("Network.enable")
        cdp.call("Network.setCacheDisabled", cacheDisabled=True)
        cdp.call("Page.navigate", url=base + "/index.html?audit=1#tasks")
        wait_ready(cdp, want_url="index.html")
        time.sleep(5)
        for mode in MODES:
            cdp.eval("(function(){var b=document.querySelector('.tk-modebar [data-tkmode=%s]');"
                     "if(b)b.click();})()" % mode)
            for _ in range(30):
                time.sleep(0.4)
                n = int(cdp.eval("document.querySelectorAll('#tk-nodes .tk-node').length") or 0)
                if n:
                    break
            time.sleep(1.2)
            raw = cdp.eval(EXTRACT)
            view = json.loads(raw or "{}")
            result["modes"][mode] = analyse(view)
            result["modes"][mode]["raw"] = {
                "width": view.get("width"), "height": view.get("height"),
                "nodes": len(view.get("nodes") or []),
            }
            # 原始坐标留档，便于事后复核
            with open(os.path.join(OUT_DIR, "nodes-%s-%s.json" % (args.tag, mode)), "w",
                      encoding="utf-8") as fh:
                json.dump(view, fh, ensure_ascii=False)
    finally:
        try:
            proc.terminate()
        except Exception:                   # noqa: BLE001
            pass
    path = os.path.join(OUT_DIR, "layout-%s.json" % args.tag)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=1)
    print("%-8s %-5s %-6s %-6s %-7s %-8s %-7s %-8s %-10s %s" % (
        "mode", "节点", "边", "层", "跨层交叉", "几何交叉", "长边", "穿节点", "节点重叠", "画布"))
    for mode in MODES:
        m = result["modes"].get(mode) or {}
        print("%-8s %-5s %-6s %-6s %-8s %-8s %-7s %-8s %-10s %sx%s" % (
            mode, m.get("nodes"), m.get("edges"), m.get("layers"),
            m.get("adjacentCrossings"), m.get("geometricCrossings"),
            m.get("longEdges"), m.get("edgesThroughNodes"),
            m.get("nodeOverlaps"), (m.get("canvas") or {}).get("w"), (m.get("canvas") or {}).get("h")))
        o = m.get("orthogonal") or {}
        if o:
            print("         正交实测：段 %s / 交叉 %s / 重叠 %s（>12px %s）/ 穿卡边 %s / 转折 %s" % (
                o.get("segments"), o.get("segmentCrossings"), o.get("segmentOverlaps"),
                o.get("segmentOverlapsLong"), o.get("edgeNodeHitEdges"), o.get("bends")))
        print("         环：%s" % (m.get("cycles") or "无"))
    print("写入", path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
