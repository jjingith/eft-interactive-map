#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""定位「被拉长」的元素：按 (背景图, background-size, w, h, 路径后缀) 聚合去重。"""
from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r181_accept import CDP, find_chrome, launch, wait_ready  # noqa: E402

JS = r"""
(function(){
  function path(el){
    var p = [], n = el, i = 0;
    while (n && n.nodeType === 1 && i < 5) {
      var s = n.tagName.toLowerCase();
      if (n.id) { s += "#" + n.id; }
      else if (typeof n.className === "string" && n.className.trim()) {
        s += "." + n.className.trim().split(/\s+/).slice(0,2).join(".");
      }
      p.unshift(s); n = n.parentElement; i++;
    }
    return p.join(">");
  }
  var agg = {};
  var all = document.body.getElementsByTagName("*");
  for (var i=0;i<all.length;i++){
    var el = all[i], cs = getComputedStyle(el), r = el.getBoundingClientRect();
    if (r.width < 4 || r.height < 4) { continue; }
    var bg = (cs.backgroundImage === "none") ? "" : cs.backgroundImage.replace(/^url\(".*\/([^\/"]+)"\)$/, "$1");
    var bi = (cs.borderImageSource === "none") ? "" : cs.borderImageSource.replace(/^url\(".*\/([^\/"]+)"\)$/, "$1");
    if (!bg && !bi) { continue; }
    var k = [bg, cs.backgroundSize, Math.round(r.width), Math.round(r.height),
             path(el)].join(" | ");
    agg[k] = (agg[k] || 0) + 1;
  }
  return JSON.stringify(agg);
})()
"""


def main():
    port, base = 9808, "http://127.0.0.1:8791"
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    prof = os.path.join(os.environ.get("TEMP", "."), "xpui_b2_%d" % port)
    proc, ws = launch(find_chrome(), port, 1834, 1030, prof)
    cdp = CDP(ws)
    try:
        cdp.call("Page.enable")
        cdp.call("Runtime.enable")
        cdp.call("Emulation.setDeviceMetricsOverride", width=1834, height=1030,
                 deviceScaleFactor=1, mobile=False)
        cdp.call("Page.navigate", url=base + "/")
        wait_ready(cdp, timeout=60)
        time.sleep(3.0)
        for v in ("loadout", "gun"):
            cdp.eval("(function(){var b=document.getElementById('view-btn-%s');if(b){b.click();}})()" % v)
            time.sleep(2.8)
            data = json.loads(cdp.eval(JS) or "{}")
            print("\n===== %s" % v)
            for k, n in sorted(data.items(), key=lambda kv: -kv[1]):
                if True:
                    print("  x%-3d %s" % (n, k[:150]))
            cdp.shot(os.path.join(root, "docs", "xp-ui-r95-shots", v + ".png"))
    finally:
        proc.terminate()


if __name__ == "__main__":
    main()
