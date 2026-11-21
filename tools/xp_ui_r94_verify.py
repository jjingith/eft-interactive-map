#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R94 接入点实测：读计算样式 + 截图，确认 16 件素材真的生效。"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r181_accept import CDP, find_chrome, launch, wait_ready  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "xp-ui-r94-shots")

PROBES = r"""
(function(){
  function g(sel, prop){
    var el = document.querySelector(sel);
    if (!el) { return null; }
    var cs = getComputedStyle(el);
    return {w: Math.round(el.getBoundingClientRect().width),
            h: Math.round(el.getBoundingClientRect().height),
            v: cs[prop]};
  }
  var out = {};
  out.plate_gun = g("#gw-current", "borderImageSource") || g(".gw-current-plate", "borderImageSource");
  out.brand = g(".brand h1", "borderImageSource");
  out.version = g("#build-rev", "borderImageSource");
  out.table = g(".lw-table", "borderImageSource");
  out.icon_map = g("#view-btn-map .vt-ico", "backgroundImage");
  out.icon_tasks = g("#view-btn-tasks .vt-ico", "backgroundImage");
  out.icon_ammo = g("#view-btn-ammo .vt-ico", "backgroundImage");
  out.icon_gun = g("#view-btn-gun .vt-ico", "backgroundImage");
  out.icon_loadout = g("#view-btn-loadout .vt-ico", "backgroundImage");
  out.empty_task = g(".task-empty", "backgroundImage");
  out.empty_story = g(".tk-story-empty", "backgroundImage");
  out.empty_gun = g(".gw-empty", "backgroundImage");
  out.thumb = (function(){ var c = getComputedStyle(document.documentElement);
    return c.getPropertyValue("--x-thumb").trim(); })();
  out.radius = g(".gw-prof-box", "borderTopLeftRadius");
  out.modalhead = g(".am-modal-head", "backgroundImage");
  out.legendArrow = g(".legend-group-arrow", "borderTopWidth");
  out.spin = g("input[type=number]", "appearance");
  out.fonts = (function(){
    var set = {};
    [".app-menu-btn", ".cb-label", ".tk-node-name", ".lw-cell-name", ".am-table td", ".sb-rev"]
      .forEach(function(s){ var e = document.querySelector(s);
        if (e) { set[s] = getComputedStyle(e).fontSize; } });
    return set; })();
  return JSON.stringify(out);
})()
"""


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9802)
    ap.add_argument("--base", default="http://127.0.0.1:8791")
    args = ap.parse_args(argv)
    base = args.base.rstrip("/")
    os.makedirs(OUT, exist_ok=True)
    prof = os.path.join(os.environ.get("TEMP", "."), "xpui_verify_%d" % args.port)
    proc, ws = launch(find_chrome(), args.port, 1834, 1030, prof)
    cdp = CDP(ws)
    res = {}
    try:
        cdp.call("Page.enable")
        cdp.call("Runtime.enable")
        cdp.call("Emulation.setDeviceMetricsOverride", width=1834, height=1030,
                 deviceScaleFactor=1, mobile=False)
        cdp.call("Page.navigate", url=base + "/")
        wait_ready(cdp, timeout=60)
        time.sleep(3.2)
        for view in ("loadout", "tasks", "gun", "map"):
            cdp.eval("(function(){var b=document.getElementById('view-btn-%s');"
                     "if(b){b.click();}})()" % view)
            time.sleep(2.4)
            res[view] = json.loads(cdp.eval(PROBES) or "{}")
            cdp.shot(os.path.join(OUT, view + ".png"))
            print("[%s] %s" % (view, json.dumps(res[view], ensure_ascii=False)[:700]))
        cdp.call("Page.navigate", url=base + "/?mini=1")
        wait_ready(cdp, timeout=60)
        time.sleep(3.0)
        cdp.shot(os.path.join(OUT, "mini.png"))
        res["mini"] = json.loads(cdp.eval(PROBES) or "{}")
        print("[mini] %s" % json.dumps(res["mini"], ensure_ascii=False)[:400])
    finally:
        proc.terminate()
    json.dump(res, open(os.path.join(ROOT, "docs", "xp-ui-r94-verify.json"), "w",
                        encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
