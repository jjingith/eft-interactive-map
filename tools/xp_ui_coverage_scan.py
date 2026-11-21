#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R94 覆盖重扫（可见元素级，口径同 docs/xp-ui-coverage.md §6.1）。

用法：
    python tools/xp_ui_coverage_scan.py --port 9801 --base http://127.0.0.1:8791
产物：
    docs/xp-ui-coverage-scan-r94.json
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

JS_SCAN = r"""
(function(){
  var XP = "/assets/xp-ui/";
  var out = {A:0, B:0, C:0, D:0, A_by:{}, B_by:{}, A_file:{}, total:0};
  function bump(map, k){ map[k] = (map[k]||0) + 1; }
  function deco(cs){
    return (cs.backgroundImage && cs.backgroundImage !== "none")
        || (cs.borderImageSource && cs.borderImageSource !== "none")
        || (cs.backgroundColor && cs.backgroundColor !== "rgba(0, 0, 0, 0)")
        || (parseFloat(cs.borderTopWidth) > 0) || (parseFloat(cs.borderLeftWidth) > 0)
        || (cs.boxShadow && cs.boxShadow !== "none")
        || (parseFloat(cs.borderTopLeftRadius) > 0);
  }
  function scrollable(el, cs){
    var oy = cs.overflowY, ox = cs.overflowX;
    function sc(v){ return v === "auto" || v === "scroll"; }
    return (sc(oy) && el.scrollHeight > el.clientHeight + 1)
        || (sc(ox) && el.scrollWidth > el.clientWidth + 1);
  }
  var all = document.body.getElementsByTagName("*");
  for (var i=0;i<all.length;i++){
    var el = all[i];
    var tag = el.tagName.toLowerCase();
    if (tag === "script" || tag === "style" || tag === "link" || tag === "meta"
        || tag === "head" || tag === "option" || tag === "optgroup") { continue; }
    var r = el.getBoundingClientRect();
    if (r.width < 4 || r.height < 4) { continue; }
    var cs = getComputedStyle(el);
    if (cs.visibility === "hidden" || cs.display === "none" || parseFloat(cs.opacity) === 0) { continue; }
    var key = tag + (el.className && typeof el.className === "string"
                     ? "." + el.className.trim().split(/\s+/).slice(0,2).join(".")
                     : (el.id ? "#"+el.id : ""));
    var img = (cs.backgroundImage || "") + (cs.borderImageSource || "");
    if (img.indexOf(XP) >= 0) {
      out.A++; bump(out.A_by, key);
      var m = img.match(/xp-ui\/([^"')]+)/g) || [];
      m.forEach(function(s){ bump(out.A_file, s.replace("xp-ui/", "")); });
    }
    else if ((tag === "select" || tag === "input" || tag === "textarea")
             && cs.appearance !== "none") { out.C++; }
    else if (deco(cs) || scrollable(el, cs)) { out.B++; bump(out.B_by, key); }
    else { out.D++; continue; }
    out.total++;
  }
  return JSON.stringify(out);
})()
"""

VIEWS = ["map", "tasks", "ammo", "gun", "loadout"]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9801)
    ap.add_argument("--base", default="http://127.0.0.1:8791")
    ap.add_argument("--width", type=int, default=1834)
    ap.add_argument("--height", type=int, default=1030)
    args = ap.parse_args(argv)
    base = args.base.rstrip("/")
    prof = os.path.join(os.environ.get("TEMP", "."), "xpui_scan_%d" % args.port)
    proc, ws = launch(find_chrome(), args.port, args.width, args.height, prof)
    cdp = CDP(ws)
    report = {"build": "R94", "base": base, "views": {}}
    try:
        cdp.call("Page.enable")
        cdp.call("Runtime.enable")
        cdp.call("Emulation.setDeviceMetricsOverride", width=args.width, height=args.height,
                 deviceScaleFactor=1, mobile=False)
        cdp.call("Page.navigate", url=base + "/")
        wait_ready(cdp, timeout=60)
        time.sleep(3.0)
        for v in VIEWS:
            ok = cdp.eval("(function(){var b=document.getElementById('view-btn-%s');"
                          "if(!b){return false;} b.click(); return true;})()" % v)
            time.sleep(2.6 if v != "ammo" else 3.6)
            data = json.loads(cdp.eval(JS_SCAN) or "{}")
            report["views"][v] = data
            print("%-9s A=%-5d B=%-4d C=%-3d D=%-4d total=%d" % (
                v, data.get("A", 0), data.get("B", 0), data.get("C", 0),
                data.get("D", 0), data.get("total", 0)))
            top = sorted((data.get("B_by") or {}).items(), key=lambda kv: -kv[1])[:8]
            print("          B top: " + ", ".join("%s x%d" % (k, n) for k, n in top))
        # mini
        cdp.call("Page.navigate", url=base + "/?mini=1")
        wait_ready(cdp, timeout=60)
        time.sleep(3.0)
        data = json.loads(cdp.eval(JS_SCAN) or "{}")
        report["views"]["mini"] = data
        print("%-9s A=%-5d B=%-4d C=%-3d D=%-4d total=%d" % (
            "mini", data.get("A", 0), data.get("B", 0), data.get("C", 0),
            data.get("D", 0), data.get("total", 0)))
    finally:
        proc.terminate()
    json.dump(report, open(os.path.join(ROOT, "docs", "xp-ui-coverage-scan-r94.json"), "w",
                           encoding="utf-8"), ensure_ascii=False, indent=1)
    tot = {"A": 0, "B": 0, "C": 0, "D": 0, "total": 0}
    for v in VIEWS:
        d = report["views"].get(v) or {}
        for k in tot:
            tot[k] += d.get(k, 0)
    print("\n五视图合计 A=%d B=%d C=%d D=%d total=%d  A%%=%.1f" % (
        tot["A"], tot["B"], tot["C"], tot["D"], tot["total"],
        100.0 * tot["A"] / max(1, tot["total"])))
    report["total"] = tot
    json.dump(report, open(os.path.join(ROOT, "docs", "xp-ui-coverage-scan-r94.json"), "w",
                           encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
