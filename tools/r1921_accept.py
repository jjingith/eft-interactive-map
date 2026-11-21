# -*- coding: utf-8 -*-
"""R19.15.1 .338 三把枪：修复前/修复后真实浏览器取证（截图 + DOM 坐标）。

用法：
  python tools/r1921_accept.py --phase before --port 9570
  python tools/r1921_accept.py --phase after  --port 9571

输出：docs/r19.15.1-layout-audit/{before,after}/... 与 layout-dom-<phase>.json
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r181_accept import CDP, find_chrome, launch, wait_ready  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, os.environ.get("GW_OUT_DIR", "docs/r19.15.1-layout-audit"))
URL = "http://127.0.0.1:8787/index.html"

GUNS = [
    ("axmc", "AXMC", "Accuracy International AXMC"),
    ("m10", "TRG M10", "Sako TRG M10"),
    ("mk18", "Mk-18", "SWORD International Mk-18"),
    ("aug", "AUG A3", "Steyr AUG A3"),
    ("saiga", "Saiga-12K 12 铅径自动霰弹枪", "Saiga-12K"),
    ("marlin", "MXLR", "马林 MXLR"),
    ("ak74n", "AK-74N", "AK-74N"),
    ("m4a1", "M4A1", "柯尔特 M4A1"),
    ("ash12", "ASh-12", "ASh-12"),
    ("akm", "AKM", "AKM 7.62x39"),
    ("hk416", "HK 416A5", "HK 416A5"),
    ("spear", "SPEAR", "SIG MCX SPEAR"),
    ("sa58", "SA-58", "DS Arms SA-58"),
    ("sv98", "SV-98", "SV-98"),
]

DOM_JS = r"""
(function(){
  var tree=document.getElementById('gw-tree');
  var body=tree.querySelector('.gw-gun, [data-row][data-col].gw-canvas-gun');
  var cards=[].slice.call(tree.querySelectorAll('.gw-part[data-slot]'));
  var out={ok:true, build:(typeof AM_BUILD!=='undefined')?AM_BUILD:null,
    rowsVar: tree.style.getPropertyValue('--gw-rows'),
    colsVar: tree.style.getPropertyValue('--gw-cols'),
    topPad: tree.getAttribute('data-top-pad'),
    treeSlots: tree.getAttribute('data-tree-slots'),
    placedCells: tree.getAttribute('data-placed-cells'),
    svgCount: tree.querySelectorAll('svg').length,
    connectorPaths: tree.querySelectorAll('.gw-canvas-links path').length,
    skinCount: document.querySelectorAll('.gw-skin').length,
    skinTag: document.querySelectorAll('.gw-skin-tag').length,
    gunCurrent: (document.getElementById('gw-current')||{}).textContent||'',
    slots:[]};
  cards.forEach(function(c){
    var r=c.getBoundingClientRect();
    out.slots.push({
      slot:c.getAttribute('data-slot'),
      row:+(c.getAttribute('data-row')||0),
      col:+(c.getAttribute('data-col')||0),
      item:c.getAttribute('data-item')||'',
      empty:c.className.indexOf('gw-part-empty')>=0,
      w:Math.round(r.width), h:Math.round(r.height),
      x:Math.round(r.x), y:Math.round(r.y)
    });
  });
  var tb=tree.getBoundingClientRect();
  out.treeRect={x:Math.round(tb.x),y:Math.round(tb.y),w:Math.round(tb.width),h:Math.round(tb.height)};
  var rs=getComputedStyle(tree).gridTemplateRows.split(' ').map(parseFloat);
  out.rowHeights=rs;
  out.rowCount=rs.length;
  out.colCount=getComputedStyle(tree).gridTemplateColumns.split(' ').length;
  out.viewport={w:window.innerWidth,h:window.innerHeight};
  return JSON.stringify(out);
})()
"""


def shot(cdp, phase, name):
    folder = os.path.join(OUT, "screenshots", phase)
    os.makedirs(folder, exist_ok=True)
    data = base64.b64decode(cdp.call("Page.captureScreenshot", format_="png",
                                     captureBeyondViewport=False)["data"])
    path = os.path.join(folder, name)
    with open(path, "wb") as f:
        f.write(data)
    return name


def pick_gun(cdp, needle):
    for _ in range(6):
        cdp.eval("""(function(){var b=document.querySelector('.gw-mode[data-gwmode="caliber"]');
          if(b)b.click();})()""")
        time.sleep(0.6)
        pos = cdp.eval("""(function(){var cs=document.querySelectorAll('#gw-browse .gw-card');
          for(var i=0;i<cs.length;i++){var s=cs[i].querySelector('span');
            if(s && s.textContent.indexOf(%s)>=0){cs[i].scrollIntoView({block:'center'});
              var r=cs[i].getBoundingClientRect();
              return JSON.stringify({x:r.x+r.width/2,y:r.y+r.height/2});}}})()"""
                      % json.dumps(needle, ensure_ascii=False))
        if not pos or pos == "null":
            continue
        p = json.loads(pos)
        cdp.click_at(p["x"], p["y"])
        time.sleep(2.0)
        cur = cdp.eval("(document.getElementById('gw-current')||{}).textContent") or ""
        if needle.split(" ")[0] in cur or needle.split(" ")[-1] in cur:
            cdp.eval("document.getElementById('gw-default') && document.getElementById('gw-default').click()")
            time.sleep(1.4)
            return True
    return False


def main():
    global OUT
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", default="after", choices=["before", "after"])
    ap.add_argument("--port", type=int, default=9570)
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=919)
    ap.add_argument("--url", default="index.html")
    ap.add_argument("--only", default="")
    ap.add_argument("--out-dir", default="")
    args = ap.parse_args()
    if args.out_dir:
        OUT = os.path.join(ROOT, args.out_dir)

    prof = os.path.join(os.environ.get("TEMP", "."), "r1921prof_%s_%d" % (args.phase, args.port))
    proc, ws = launch(find_chrome(), args.port, args.width, args.height, prof)
    rep = {"phase": args.phase, "url": URL, "guns": {}, "console": []}
    try:
        cdp = CDP(ws)
        for m in ("Page.enable", "Runtime.enable", "Log.enable", "Network.enable"):
            cdp.call(m)
        cdp.call("Network.setCacheDisabled", cacheDisabled=True)
        cdp.call("Emulation.setDeviceMetricsOverride", width=args.width, height=args.height,
                 deviceScaleFactor=1, mobile=False)
        cdp.call("Page.navigate", url="http://127.0.0.1:8787/" + args.url)
        wait_ready(cdp, want_url=args.url.split("/")[-1].split("?")[0])
        time.sleep(2.6)
        rep["build"] = cdp.eval("(typeof AM_BUILD!=='undefined')?AM_BUILD:null")
        cdp.eval("document.querySelector('[data-view=\"gun\"]').click()")
        time.sleep(2.2)

        only = [x for x in (args.only or "").split(",") if x]
        picked_guns = [g for g in GUNS if (not only or g[0] in only)]
        for key, needle, _full in picked_guns:
            ok = pick_gun(cdp, needle)
            m = json.loads(cdp.eval(DOM_JS) or "{}")
            rec = {"picked": ok, "measure": m}
            if only or key in ("axmc", "m10", "mk18", "m4a1", "ash12", "marlin", "ak74n"):
                rec["shot"] = shot(cdp, args.phase, "%s-%s-%dx%d.png" % (key, args.phase, args.width, args.height))
            rep["guns"][key] = rec

        # 第二视口：1384×805
        if args.width == 1920:
            cdp.call("Emulation.setDeviceMetricsOverride", width=1384, height=805,
                     deviceScaleFactor=1, mobile=False)
            time.sleep(1.2)
            rep["viewports"] = {}
            vp_keys = ["axmc", "m10", "mk18", "marlin", "ak74n", "aug", "saiga", "akm"]
            for key, needle, _full in [g for g in picked_guns if g[0] in vp_keys]:
                ok = pick_gun(cdp, needle)
                m = json.loads(cdp.eval(DOM_JS) or "{}")
                rep["viewports"][key + "_1384"] = {
                    "picked": ok, "measure": m,
                    "shot": shot(cdp, args.phase, "%s-%s-1384x805.png" % (key, args.phase)),
                }

        try:
            rep["console"] = [e for e in (getattr(cdp, "logs", []) or [])][:20]
        except Exception:
            pass
    finally:
        try:
            proc.terminate()
        except Exception:
            pass

    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, "layout-dom-%s.json" % args.phase)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=1)
    print("wrote", path)
    for k, v in rep["guns"].items():
        m = v.get("measure") or {}
        print(" ", k, "picked", v.get("picked"), "rows", m.get("rowCount"),
              "slots", len(m.get("slots") or []))


if __name__ == "__main__":
    main()
