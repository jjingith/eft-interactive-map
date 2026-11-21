# -*- coding: utf-8 -*-
"""R19.23 参考网站细节探针 #2：模式下拉、树节点结构、db4tarkov 加载失败原因。"""
from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r181_accept import CDP, find_chrome, launch, wait_ready  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "r19.23", "ref")


def safe_shot(cdp, path):
    try:
        cdp.shot(path)
        return True
    except Exception as exc:  # noqa: BLE001
        print("shot failed", path, exc)
        return False


def main():
    os.makedirs(OUT, exist_ok=True)
    chrome = find_chrome(None)
    proc, ws = launch(chrome, 8932, 1600, 1000, os.path.join(ROOT, "build-cache", "chrome-r1923-ref2"))
    cdp = CDP(ws)
    cdp.call("Page.enable")
    cdp.call("Runtime.enable")
    cdp.call("Log.enable")
    rep = {}
    try:
        # ---- 1) eftarkov /task：点开右上角 PVP 下拉，读菜单
        cdp.call("Page.navigate", url="https://www.eftarkov.com/task")
        wait_ready(cdp, timeout=70)
        time.sleep(5)
        rep["mode_menu"] = cdp.eval(r"""
        (function () {
          var out = { before: [] };
          var all = Array.prototype.slice.call(document.querySelectorAll("button,div,span,a"));
          var anchor = null;
          all.forEach(function (e) {
            var t = (e.textContent || "").trim();
            if ((t === "PVP" || t === "PvP") && e.getBoundingClientRect().width > 1 && !anchor) { anchor = e; }
          });
          if (!anchor) { return { err: "no pvp button" }; }
          out.anchorHtml = anchor.parentElement.outerHTML.slice(0, 700);
          anchor.click();
          return out;
        })()
        """)
        time.sleep(1.5)
        rep["mode_menu_after"] = cdp.eval(r"""
        (function () {
          var vis = [];
          Array.prototype.slice.call(document.querySelectorAll("a,button,li,div")).forEach(function (e) {
            var r = e.getBoundingClientRect();
            if (r.width < 1 || r.height < 1) { return; }
            var t = (e.textContent || "").replace(/\s+/g, " ").trim();
            if (/^(PvP|PvE|赛季|Season)/i.test(t) && t.length < 40) { vis.push(t); }
          });
          return { candidates: vis.slice(0, 30), len: document.body.innerText.length,
                   head: document.body.innerText.slice(0, 200) };
        })()
        """)
        safe_shot(cdp, os.path.join(OUT, "eftarkov-mode-menu.png"))

        # ---- 2) eftarkov /task-tree：读单个节点的 DOM 结构与缩放控件
        cdp.call("Page.navigate", url="https://www.eftarkov.com/task-tree")
        wait_ready(cdp, timeout=70)
        time.sleep(6)
        rep["tree_structure"] = cdp.eval(r"""
        (function () {
          var best = null, bestN = 0, cls = null;
          var counts = {};
          Array.prototype.slice.call(document.querySelectorAll("div,li")).forEach(function (e) {
            var c = String(e.className || "");
            if (!c || e.getBoundingClientRect().width < 2) { return; }
            counts[c] = (counts[c] || 0) + 1;
          });
          Object.keys(counts).forEach(function (k) {
            if (counts[k] > bestN && counts[k] < 2000) { bestN = counts[k]; cls = k; }
          });
          var sample = document.querySelector("." + String(cls || "").split(/\s+/)[0]);
          return {
            nodeClass: cls, nodeCount: bestN,
            sampleText: sample ? (sample.innerText || "").slice(0, 300) : "",
            sampleHtml: sample ? sample.outerHTML.slice(0, 900) : "",
            topClasses: Object.keys(counts).map(function (k) { return [k, counts[k]]; })
              .sort(function (a, b) { return b[1] - a[1]; }).slice(0, 20),
            toolbar: Array.prototype.slice.call(document.querySelectorAll("button"))
              .slice(0, 12).map(function (b) {
                return (b.textContent || "").replace(/\s+/g, " ").trim().slice(0, 20);
              })
          };
        })()
        """)
        # 放大到能看清节点
        rep["tree_zoom"] = cdp.eval(r"""
        (function () {
          var svg = document.querySelector("svg");
          if (!svg) { return { err: "no svg" }; }
          var g = svg.querySelector("g");
          var before = g ? g.getAttribute("transform") : null;
          var box = svg.getBoundingClientRect();
          for (var i = 0; i < 12; i++) {
            svg.dispatchEvent(new WheelEvent("wheel", { deltaY: -120, clientX: box.width / 2,
              clientY: box.height / 2, bubbles: true, cancelable: true }));
          }
          var g2 = svg.querySelector("g");
          return { before: before, after: g2 ? g2.getAttribute("transform") : null };
        })()
        """)
        time.sleep(1.5)
        safe_shot(cdp, os.path.join(OUT, "eftarkov-tree-zoom.png"))

        # ---- 3) db4tarkov：等更久 + 抓控制台错误
        cdp.call("Page.navigate", url="https://db4tarkov.com/quest")
        time.sleep(14)
        rep["db4"] = cdp.eval(r"""
        (function () {
          return { url: location.href, ready: document.readyState,
                   title: document.title, bodyLen: document.body ? document.body.innerText.length : -1,
                   html: (document.documentElement.outerHTML || "").slice(0, 900),
                   scripts: Array.prototype.slice.call(document.scripts).map(function (s) { return s.src || "(inline)"; }).slice(0, 12) };
        })()
        """)
        try:
            rep["db4_console"] = cdp.drain(0.6)
        except Exception:  # noqa: BLE001
            pass
        safe_shot(cdp, os.path.join(OUT, "db4tarkov-quest-2.png"))
    finally:
        try:
            proc.terminate()
        except Exception:  # noqa: BLE001
            pass
    with open(os.path.join(OUT, "ref-probe2.json"), "w", encoding="utf-8") as fh:
        json.dump(rep, fh, ensure_ascii=False, indent=1, default=str)
    for k, v in rep.items():
        print("==", k, json.dumps(v, ensure_ascii=False, default=str)[:1400])
    return 0


if __name__ == "__main__":
    sys.exit(main())
