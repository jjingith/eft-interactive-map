# -*- coding: utf-8 -*-
"""R19.25 参考站任务树几何探针（真实 Chrome，只读）。

目的：不是"看图猜"，而是量出 EFTarkov 任务树的**排布方式**：
  · 节点是列式分层还是自由散点？列间距 / 行间距多少？
  · 连线是直线、曲线还是正交折线？有没有绕过节点的折点？
  · 同一商人的任务是否聚在一起（横向带 / 纵向带）？
  · 一个节点被多个前置引用时，是合并到同一节点还是复制？
  · 树里有多少节点、多少连线、最大入度/出度？

输出：build-cache/ref-tree-geometry.json
用法：python tools/r1925_ref_tree.py
"""
from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r181_accept import CDP, find_chrome, launch, wait_ready  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "build-cache", "ref-tree-geometry.json")

PROBE = r"""
(function () {
  function txt(e) { return (e && e.textContent || "").replace(/\s+/g, " ").trim(); }
  function vis(e) {
    var r = e.getBoundingClientRect();
    var s = getComputedStyle(e);
    return r.width > 1 && r.height > 1 && s.visibility !== "hidden" && s.display !== "none";
  }
  var nodes = Array.prototype.slice.call(document.querySelectorAll(".task-tree-node-task")).filter(vis);
  var svg = document.querySelector("svg");
  var out = { count: nodes.length, nodes: [], svg: null, paths: [], cls: {} };
  nodes.slice(0, 700).forEach(function (n) {
    var r = n.getBoundingClientRect();
    var t = n.querySelector(".task-tree-card-top");
    var meta = n.querySelector(".task-tree-meta");
    var objs = n.querySelectorAll(".task-tree-objective");
    out.nodes.push({
      x: Math.round(r.left + window.scrollX), y: Math.round(r.top + window.scrollY),
      w: Math.round(r.width), h: Math.round(r.height),
      cls: n.className,
      title: txt(t).slice(0, 40),
      meta: txt(meta).slice(0, 40),
      objCount: objs.length,
      objFirst: objs.length ? txt(objs[0]).slice(0, 40) : ""
    });
  });
  if (svg) {
    var box = svg.getBoundingClientRect();
    out.svg = { w: Math.round(box.width), h: Math.round(box.height),
                vb: svg.getAttribute("viewBox") };
    out.paths = Array.prototype.slice.call(svg.querySelectorAll("path")).slice(0, 400).map(function (p) {
      return { d: (p.getAttribute("d") || "").slice(0, 160),
               cls: p.getAttribute("class") || "",
               stroke: getComputedStyle(p).stroke,
               dash: getComputedStyle(p).strokeDasharray };
    });
  }
  // 连线若用 DOM 元素画：统计其类型
  var lines = Array.prototype.slice.call(document.querySelectorAll("svg line, svg path, .task-tree-link"));
  out.linkEls = lines.length;
  return JSON.stringify(out);
})()
"""


def main():
    chrome = find_chrome(None)
    prof = os.path.join(ROOT, "build-cache", "chrome-r1925-ref")
    proc, ws = launch(chrome, 9821, 1680, 1050, prof)
    cdp = CDP(ws)
    cdp.call("Page.enable")
    cdp.call("Runtime.enable")
    try:
        cdp.call("Page.navigate", url="https://www.eftarkov.com/task-tree")
        wait_ready(cdp, timeout=70)
        time.sleep(8)
        # 先放大，便于观察局部结构
        cdp.eval(r"""(function(){
          var svg=document.querySelector("svg");
          if(!svg) return;
          var b=svg.getBoundingClientRect();
          for(var i=0;i<6;i++){
            svg.dispatchEvent(new WheelEvent("wheel",{deltaY:-120,clientX:b.width/2,clientY:b.height/2,
              bubbles:true,cancelable:true}));
          }})()""")
        time.sleep(1.5)
        data = json.loads(cdp.eval(PROBE) or "{}")
        # 再抓一份"复位后"的全图坐标（用于分析整体分层）
        cdp.eval(r"""(function(){
          var b=[].slice.call(document.querySelectorAll("button")).filter(function(x){
            return (x.textContent||"").indexOf("复位")>=0;})[0];
          if(b) b.click();})()""")
        time.sleep(1.5)
        data["fullView"] = json.loads(cdp.eval(PROBE) or "{}")
    finally:
        try:
            proc.terminate()
        except Exception:               # noqa: BLE001
            pass
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)

    # 就地做几何统计
    def stats(view, label):
        ns = view.get("nodes") or []
        if not ns:
            print(label, "无节点")
            return
        xs = sorted({n["x"] for n in ns})
        ys = [n["y"] for n in ns]
        widths = sorted({n["w"] for n in ns})
        heights = sorted({n["h"] for n in ns})
        # 近似列：x 值聚类（±4px）
        cols = []
        for x in sorted(n["x"] for n in ns):
            if not cols or x - cols[-1] > 4:
                cols.append(x)
        print("%s 节点=%d 列数≈%d 宽度=%s 高度=%s y范围=%d..%d"
              % (label, len(ns), len(cols), widths[:4], heights[:4], min(ys), max(ys)))
        # 列内节点数分布
        from collections import Counter
        cnt = Counter()
        for n in ns:
            key = min(cols, key=lambda c: abs(c - n["x"])) if cols else 0
            cnt[key] += 1
        print("   列内节点数（前 8 列）：%s" % sorted(cnt.items())[:8])
        print("   路径元素=%d 样例=%s" % (view.get("linkEls", 0),
                                       (view.get("paths") or [{}])[0].get("d", "")[:80]))
        # 节点平均宽度/间距
        if len(cols) > 1:
            gaps = [cols[i + 1] - cols[i] for i in range(len(cols) - 1)]
            print("   列间距：min=%d max=%d" % (min(gaps), max(gaps)))
        sample = ns[:3]
        print("   节点样例：", json.dumps(sample, ensure_ascii=False)[:400])

    stats(data, "放大后")
    stats(data.get("fullView") or {}, "复位后")
    print("写入", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
