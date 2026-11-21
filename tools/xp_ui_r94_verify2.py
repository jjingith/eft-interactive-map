#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""铭牌中心空白校验 + 16 件素材的落地实测（修正选择器）。"""
from __future__ import annotations

import json
import os
import sys
import time

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r181_accept import CDP, find_chrome, launch, wait_ready  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = r"D:\personal\trae\02-塔科夫\ui图标\xp风格ui\Create ONE single 4K sprite she_881c048f.png"

PLATES = {
    "current-gun-plate": (118, 580, 1870, 760),
    "version-plate": (1976, 580, 2774, 754),
    "brand-plate": (118, 1125, 970, 1343),
}

PROBE = r"""
(function(){
  function g(sel){
    var el = document.querySelector(sel); if (!el) { return "ABSENT"; }
    var cs = getComputedStyle(el), r = el.getBoundingClientRect();
    return {w: Math.round(r.width), h: Math.round(r.height),
            bi: (cs.borderImageSource||"none").replace(/^url\(".*\/([^\/"]+)"\)$/, "$1"),
            bg: (cs.backgroundImage||"none").split(",").length === 1
                ? (cs.backgroundImage||"none").replace(/^url\(".*\/([^\/"]+)"\)$/, "$1") : "multi"};
  }
  var out = {};
  [["brand", "#app-brand"], ["version", "#build-rev"], ["plate_gun", ".gun-workbench #gw-current"],
   ["tbl_loadout", ".loadout-workbench .tbl-scroll"], ["tbl_ammo", ".am-workbench .tbl-scroll"],
   ["thumb_rule", "@thumb"], ["cellname", ".lw-cell-name"], ["celllabel", ".lw-cell-label"],
   ["legend_arrow", ".legend-group-arrow"], ["num_in", "input[type=number]"]].forEach(function(p){
     out[p[0]] = p[1] === "@thumb"
       ? getComputedStyle(document.documentElement).getPropertyValue("--x-thumb").trim() || "no-var"
       : g(p[1]);
  });
  out.empty_task = getComputedStyle(document.querySelector(".task-list > .task-empty") || document.body, "::before").backgroundImage;
  out.empty_story = getComputedStyle(document.querySelector(".tk-story-empty") || document.body, "::before").backgroundImage;
  out.empty_gun = getComputedStyle(document.querySelector(".lw-loading") || document.body, "::before").backgroundImage;
  return JSON.stringify(out);
})()
"""


def main():
    im = Image.open(SRC).convert("RGB")
    px = im.load()
    print("== 铭牌中心空白（中心 40% 区域内非米色像素数）")
    for name, (x0, y0, x1, y1) in PLATES.items():
        w = x1 - x0
        h = y1 - y0
        cnt = 0
        for y in range(y0 + int(h * .3), y0 + int(h * .7)):
            for x in range(x0 + int(w * .3), x0 + int(w * .7)):
                r, g, b = px[x, y][:3]
                if not (r > 225 and g > 222 and 190 < b < 250):
                    cnt += 1
        print("  %-20s %5d  %s" % (name, cnt, "空白 OK" if cnt == 0 else "有内容"))

    port, base = 9803, "http://127.0.0.1:8791"
    prof = os.path.join(os.environ.get("TEMP", "."), "xpui_v2_%d" % port)
    proc, ws = launch(find_chrome(), port, 1834, 1030, prof)
    cdp = CDP(ws)
    try:
        cdp.call("Page.enable")
        cdp.call("Runtime.enable")
        cdp.call("Emulation.setDeviceMetricsOverride", width=1834, height=1030,
                 deviceScaleFactor=1, mobile=False)
        cdp.call("Page.navigate", url=base + "/")
        wait_ready(cdp, timeout=60)
        time.sleep(3.2)
        for v in ("loadout", "gun", "ammo"):
            cdp.eval("(function(){var b=document.getElementById('view-btn-%s');if(b){b.click();}})()" % v)
            time.sleep(2.6)
            print("\n== %s" % v)
            print(json.dumps(json.loads(cdp.eval(PROBE) or "{}"), ensure_ascii=False, indent=1))
    finally:
        proc.terminate()


if __name__ == "__main__":
    main()
