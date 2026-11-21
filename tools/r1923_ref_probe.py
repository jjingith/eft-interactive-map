# -*- coding: utf-8 -*-
"""R19.23 参考网站结构探针（真实 Chrome + CDP，纯标准库）。

用途：在改代码前，把 eftarkov.com/task、/task-tree、db4tarkov.com/quest 三个页面
**真实加载后**的结构、控件、模式切换行为记录下来，作为本轮 UI 取舍的证据。
不做任何推测：所有输出都来自页面 DOM 实测。

用法：
    python tools/r1923_ref_probe.py --out docs/r19.23/ref
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

PROBE_JS = r"""
(function () {
  function txt(el) { return (el && el.textContent || "").replace(/\s+/g, " ").trim(); }
  function vis(el) {
    if (!el) { return false; }
    var r = el.getBoundingClientRect();
    var s = getComputedStyle(el);
    return r.width > 1 && r.height > 1 && s.visibility !== "hidden" && s.display !== "none";
  }
  var out = { url: location.href, title: document.title, ready: document.readyState };
  out.bodyLen = (document.body ? document.body.innerText.length : 0);
  out.headings = Array.prototype.slice.call(document.querySelectorAll("h1,h2,h3"))
    .filter(vis).slice(0, 18).map(function (e) { return e.tagName + ":" + txt(e).slice(0, 40); });
  var btns = Array.prototype.slice.call(document.querySelectorAll("button,[role=tab],a.btn,.btn"))
    .filter(vis).map(function (e) { return txt(e).slice(0, 28); })
    .filter(function (t) { return t; });
  out.buttons = btns.slice(0, 90);
  out.buttonCount = btns.length;
  out.inputs = Array.prototype.slice.call(document.querySelectorAll("input,select"))
    .filter(vis).slice(0, 30).map(function (e) {
      return { tag: e.tagName, type: e.type || "", name: e.name || "", id: e.id || "",
               ph: e.placeholder || "", label: txt(e.closest("label") || {}).slice(0, 30),
               opts: e.tagName === "SELECT" ? Array.prototype.slice.call(e.options).slice(0, 14)
                 .map(function (o) { return txt(o); }) : null };
    });
  out.tables = Array.prototype.slice.call(document.querySelectorAll("table")).filter(vis)
    .slice(0, 4).map(function (t) {
      var heads = Array.prototype.slice.call(t.querySelectorAll("thead th,tr:first-child th,tr:first-child td"))
        .map(function (h) { return txt(h); });
      return { heads: heads, rows: t.querySelectorAll("tbody tr").length || t.querySelectorAll("tr").length };
    });
  // 类名统计：找「任务卡片/行」这类重复结构
  var cls = {};
  Array.prototype.slice.call(document.querySelectorAll("[class]")).forEach(function (e) {
    if (!vis(e)) { return; }
    String(e.className).split(/\s+/).forEach(function (c) {
      if (c && c.length > 2) { cls[c] = (cls[c] || 0) + 1; }
    });
  });
  out.topClasses = Object.keys(cls).map(function (k) { return [k, cls[k]]; })
    .sort(function (a, b) { return b[1] - a[1]; }).slice(0, 26);
  out.svgCount = document.querySelectorAll("svg").length;
  out.canvas = document.querySelectorAll("canvas").length;
  out.textSample = (document.body ? document.body.innerText : "").slice(0, 1200);
  return out;
})()
"""


def probe(cdp, url, shot=None, settle=6.0, clicks=None):
    cdp.call("Page.navigate", url=url)
    ok = wait_ready(cdp, timeout=70)
    time.sleep(settle)
    info = {"loaded": bool(ok), "url": url}
    try:
        info["dom"] = cdp.eval(PROBE_JS)
    except Exception as exc:  # noqa: BLE001
        info["domError"] = str(exc)
    if shot:
        try:
            cdp.shot(shot)
            info["shot"] = shot
        except Exception as exc:  # noqa: BLE001
            info["shotError"] = str(exc)
    if clicks:
        seq = []
        for label in clicks:
            js = r"""
            (function (want) {
              var els = Array.prototype.slice.call(document.querySelectorAll("button,[role=tab],a,label,span,li"));
              for (var i = 0; i < els.length; i++) {
                var t = (els[i].textContent || "").replace(/\s+/g, " ").trim();
                if (t === want && els[i].getBoundingClientRect().width > 1) {
                  els[i].click();
                  return { clicked: t, tag: els[i].tagName };
                }
              }
              return { clicked: null };
            })(%s)
            """ % json.dumps(label)
            try:
                res = cdp.eval(js)
            except Exception as exc:  # noqa: BLE001
                res = {"error": str(exc)}
            time.sleep(3.0)
            state = {}
            try:
                state = cdp.eval(r"""
                (function () {
                  var rows = document.querySelectorAll("table tbody tr").length;
                  var cards = document.querySelectorAll("[class*=task],[class*=quest],[class*=Task]").length;
                  var sel = Array.prototype.slice.call(document.querySelectorAll("[aria-selected=true],[class*=active]"))
                    .filter(function(e){var r=e.getBoundingClientRect();return r.width>1;})
                    .slice(0,10).map(function(e){return (e.textContent||"").replace(/\s+/g," ").trim().slice(0,24);});
                  return { rows: rows, cards: cards, active: sel,
                           len: document.body.innerText.length,
                           head: document.body.innerText.slice(0, 300) };
                })()
                """)
            except Exception:  # noqa: BLE001
                pass
            seq.append({"label": label, "res": res, "state": state})
        info["clicks"] = seq
    return info


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "docs", "r19.23", "ref"))
    ap.add_argument("--port", type=int, default=8931)
    args = ap.parse_args(argv)

    os.makedirs(args.out, exist_ok=True)
    chrome = find_chrome(None)
    profile = os.path.join(ROOT, "build-cache", "chrome-r1923-ref")
    proc, ws = launch(chrome, args.port, 1600, 1000, profile)
    cdp = CDP(ws)
    cdp.call("Page.enable")
    cdp.call("Runtime.enable")
    report = {}
    try:
        report["eftarkov_task"] = probe(
            cdp, "https://www.eftarkov.com/task",
            shot=os.path.join(args.out, "eftarkov-task.png"),
            clicks=["PvE", "Season", "PvP"])
        report["eftarkov_tree"] = probe(
            cdp, "https://www.eftarkov.com/task-tree",
            shot=os.path.join(args.out, "eftarkov-tree.png"),
            clicks=["PvE", "Season"])
        report["db4tarkov_quest"] = probe(
            cdp, "https://db4tarkov.com/quest",
            shot=os.path.join(args.out, "db4tarkov-quest.png"), settle=10.0)
    finally:
        try:
            proc.terminate()
        except Exception:  # noqa: BLE001
            pass

    path = os.path.join(args.out, "ref-probe.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)
    print("wrote", path)
    for k, v in report.items():
        d = v.get("dom") or {}
        print("== %-18s loaded=%s buttons=%s tables=%s svg=%s canvas=%s bodyLen=%s" % (
            k, v.get("loaded"), d.get("buttonCount"), len(d.get("tables") or []),
            d.get("svgCount"), d.get("canvas"), d.get("bodyLen")))
        print("   headings:", (d.get("headings") or [])[:8])
        print("   buttons :", (d.get("buttons") or [])[:26])
        for c in (v.get("clicks") or []):
            print("   click %-8s -> %s | rows=%s cards=%s" % (
                c["label"], c.get("res"), (c.get("state") or {}).get("rows"),
                (c.get("state") or {}).get("cards")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
