# -*- coding: utf-8 -*-
"""R19.26：左侧装备栏纵向布局实测（改造前 / 后各跑一次，--tag 标记）。

量的是真实 DOM 盒模型（不是 CSS 声明）：
  · .lw-side 的可视高 / 内容高
  · .lw-board 总高
  · 每个 .lw-cellbox 的 top / height / 与其上一个盒子的间距
  · 相邻装备行的行间距（top 差 - 上一行高）
产物：docs/r19.26/layout-<tag>.json + 截图
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r181_accept import CDP, find_chrome, launch, wait_ready  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "r19.26")

MEASURE = r"""
(function () {
  function box(el) {
    if (!el) { return null; }
    var r = el.getBoundingClientRect();
    return { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) };
  }
  var side = document.querySelector('.loadout-workbench .lw-side');
  var board = document.querySelector('.loadout-workbench .lw-board');
  var cells = [].slice.call(document.querySelectorAll('.loadout-workbench .lw-cellbox'));
  var rows = cells.map(function (c) {
    var r = c.getBoundingClientRect();
    return { cell: c.getAttribute('data-cell'), y: Math.round(r.y), h: Math.round(r.height) };
  }).sort(function (a, b) { return a.y - b.y; });
  var gaps = [];
  for (var i = 1; i < rows.length; i++) {
    gaps.push({ from: rows[i - 1].cell, to: rows[i].cell, gap: rows[i].y - (rows[i - 1].y + rows[i - 1].h) });
  }
  // 相邻"装备行"（按 y 分组后的行间距）
  var lineTops = [];
  rows.forEach(function (r) {
    if (!lineTops.length || r.y - lineTops[lineTops.length - 1].y > 4) {
      lineTops.push({ y: r.y, cells: [r.cell], bottom: r.y + r.h });
    } else {
      lineTops[lineTops.length - 1].cells.push(r.cell);
      lineTops[lineTops.length - 1].bottom = Math.max(lineTops[lineTops.length - 1].bottom, r.y + r.h);
    }
  });
  var lineGaps = [];
  for (var j = 1; j < lineTops.length; j++) {
    lineGaps.push(lineTops[j].y - lineTops[j - 1].bottom);
  }
  // 控件重叠：相邻 cellbox 若有负间距即重叠
  var overlaps = gaps.filter(function (g) { return g.gap < 0; });
  // 文本是否被裁切（scrollWidth > clientWidth 的名称格）
  var clipped = [];
  [].slice.call(document.querySelectorAll('.lw-cell-label, .lw-node-label, .lw-focus-name')).forEach(function (el) {
    if (el.scrollWidth > el.clientWidth + 1) { clipped.push((el.textContent || '').slice(0, 24)); }
  });
  return JSON.stringify({
    side: box(side),
    sideScrollH: side ? side.scrollHeight : null,
    board: box(board),
    rows: rows,
    gaps: gaps,
    lineGaps: lineGaps,
    lineCount: lineTops.length,
    overlaps: overlaps,
    clippedText: clipped.slice(0, 8)
  });
})()
"""


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9861)
    ap.add_argument("--base", default="http://127.0.0.1:8791")
    ap.add_argument("--tag", default="before")
    args = ap.parse_args(argv)
    os.makedirs(OUT, exist_ok=True)
    prof = os.path.join(os.environ.get("TEMP", "."), "r1926side_%d" % args.port)
    proc, ws = launch(find_chrome(), args.port, 1680, 1050, prof)
    cdp = CDP(ws)
    try:
        for m in ("Page.enable", "Runtime.enable", "Network.enable"):
            cdp.call(m)
        cdp.call("Network.setCacheDisabled", cacheDisabled=True)
        cdp.call("Emulation.setDeviceMetricsOverride", width=1680, height=1050,
                 deviceScaleFactor=1, mobile=False)
        cdp.call("Page.navigate", url=args.base.rstrip("/") + "/index.html?side=%s" % args.tag)
        wait_ready(cdp, want_url="index.html")
        time.sleep(2.5)
        # 配装视图没有 hash 深链，点导航按钮进入
        cdp.eval("(function(){var b=document.querySelector('[data-view=loadout]');if(b)b.click();})()")
        time.sleep(3.0)
        raw = cdp.eval(MEASURE)
        data = json.loads(raw or "{}")
        data["tag"] = args.tag
        data["viewport"] = {"w": 1680, "h": 1050}
        with open(os.path.join(OUT, "layout-%s.json" % args.tag), "w", encoding="utf-8", newline="\n") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=1)
        try:
            cdp.shot(os.path.join(OUT, "side-%s.png" % args.tag))
        except Exception as exc:                     # noqa: BLE001
            print("shot failed:", exc)
        print("tag=%s side=%s scrollH=%s board=%s lines=%s overlaps=%s clipped=%s" % (
            args.tag, data.get("side"), data.get("sideScrollH"), data.get("board"),
            data.get("lineCount"), len(data.get("overlaps") or []), data.get("clippedText")))
        print("行间距:", data.get("lineGaps"))
    finally:
        try:
            proc.terminate()
        except Exception:                           # noqa: BLE001
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
