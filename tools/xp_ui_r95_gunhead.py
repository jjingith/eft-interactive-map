#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""配枪视图：找配件列表顶部信息条（高度 8–60、类名含 head/bar/title/row/top 且有背景）。"""
from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r181_accept import CDP, find_chrome, launch, wait_ready  # noqa: E402

JS = r"""
(function(){
  function p(el){
    var a=[],n=el,i=0;
    while(n&&n.nodeType===1&&i<5){
      var s=n.tagName.toLowerCase();
      if(n.id){s+="#"+n.id;}
      else if(typeof n.className==="string"&&n.className.trim()){
        s+="."+n.className.trim().split(/\s+/).slice(0,2).join(".");
      }
      a.unshift(s);n=n.parentElement;i++;
    }
    return a.join(">");
  }
  var out=[],all=document.body.getElementsByTagName("*");
  for(var i=0;i<all.length;i++){
    var el=all[i],cs=getComputedStyle(el),r=el.getBoundingClientRect();
    if(r.width<60||r.height<8||r.height>60){continue;}
    var cn=(typeof el.className==="string")?el.className:"";
    if(!/head|bar|title|row|top/i.test(cn)){continue;}
    if(cs.backgroundImage==="none"&&cs.borderImageSource==="none"){continue;}
    out.push({c:cn,w:Math.round(r.width),h:Math.round(r.height),
              bg:cs.backgroundImage.slice(0,90),bs:cs.backgroundSize,
              bi:cs.borderImageSource.slice(0,90),p:p(el)});
  }
  return JSON.stringify(out);
})()
"""


def main(view="gun"):
    port = 9810
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    prof = os.path.join(os.environ.get("TEMP", "."), "g2_%d" % port)
    proc, ws = launch(find_chrome(), port, 1834, 1030, prof)
    cdp = CDP(ws)
    try:
        cdp.call("Page.enable")
        cdp.call("Runtime.enable")
        cdp.call("Emulation.setDeviceMetricsOverride", width=1834, height=1030,
                 deviceScaleFactor=1, mobile=False)
        cdp.call("Page.navigate", url="http://127.0.0.1:8791/")
        wait_ready(cdp, timeout=60)
        time.sleep(3)
        cdp.eval("(function(){var b=document.getElementById('view-btn-%s');if(b){b.click();}})()" % view)
        time.sleep(3)
        data = json.loads(cdp.eval(JS) or "[]")
        for x in data[:30]:
            print("%4dx%-3d | %-30s | %-10s | %-42s | %s" % (
                x["w"], x["h"], x["c"][:30], x["bs"], x["bg"][:42], x["p"][:95]))
        cdp.shot(os.path.join(root, "docs", "xp-ui-r95-shots", view + ".png"))
    finally:
        proc.terminate()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "gun")
