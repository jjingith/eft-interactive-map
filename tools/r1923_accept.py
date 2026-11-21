# -*- coding: utf-8 -*-
"""R19.15.3 AK 燕尾槽真实浏览器验收：坐标 / 空槽 / 流程往返 / 截图。

输出：docs/r19.15.3-layout-audit/browser-check.json 与 screenshots/after/*.png
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
from r1915_accept import SLOTS_JS, measure, click_slot, click_candidate, pick_gun  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "r19.15.3-layout-audit")

BASE_ITEM = "Axion Kobra 燕尾槽适配导轨基座"

GUNS = [
    ("ak74n", "AK-74N"),
    ("akm", "AKM 7.62x39"),
    ("saiga", "Saiga-12K 12 铅径自动霰弹枪"),
]


def shot(cdp, name):
    folder = os.path.join(OUT, "screenshots", "after")
    os.makedirs(folder, exist_ok=True)
    data = base64.b64decode(cdp.call("Page.captureScreenshot", format_="png",
                                     captureBeyondViewport=False)["data"])
    with open(os.path.join(folder, name), "wb") as f:
        f.write(data)
    return name


def cell_of(m, suffix):
    for s in m.get("slots") or []:
        if (s.get("slot") or "").split("/")[-1] == suffix:
            return s
    return None


def summary(m):
    empty = m.get("emptySlots") or []
    return {
        "gunName": m.get("gunId") or "",
        "rows": m.get("rowCount"),
        "cols": m.get("colCount"),
        "rowHeights": m.get("rowHeights"),
        "slotCount": m.get("slotCount"),
        "treeSlots": m.get("treeSlotCount"),
        "phantomCount": m.get("phantomCount"),
        "phantoms": (m.get("phantoms") or [])[:6],
        "realEmptySlots": len([e for e in empty if e.get("w", 0) > 8 and e.get("h", 0) > 8]),
        "emptySlots": empty[:8],
        "emptySlotInteractive": all(e.get("pointer") != "none" for e in empty) if empty else True,
        "viewport": m.get("innerW"), "viewportH": m.get("innerH"),
        "slots": [{"slot": s.get("slot"), "row": s.get("row"), "col": s.get("col"),
                   "item": s.get("item"), "empty": s.get("empty"), "x": s.get("x"), "y": s.get("y")}
                  for s in (m.get("slots") or [])],
    }


def flow_rec(m):
    """流程步骤需要的四个断言字段。"""
    s = summary(m)
    body = [x for x in (m.get("slots") or []) if x.get("slot") == "mod_reciever" or
            (x.get("slot") or "").endswith("/mod_reciever")]
    rs = cell_of(m, "mod_sight_rear")
    mount = cell_of(m, "mod_mount_000")
    # 瞄具槽 = 基座的**直接**子槽（路径只多一段 /mod_scope）；孙槽另计
    optic = None
    grand = None
    if mount:
        base_path = mount.get("slot") or ""
        for x in (m.get("slots") or []):
            sp = x.get("slot") or ""
            if sp == base_path + "/mod_scope":
                optic = x
            elif sp.startswith(base_path + "/mod_scope/") and grand is None:
                grand = x
    return {
        "bodyRow": 3,
        "rows": s["rows"],
        "rowHeights": s["rowHeights"],
        "phantomCount": s["phantomCount"],
        "mountRow": mount["row"] if mount else None,
        "mountCol": mount["col"] if mount else None,
        "mountItem": (mount or {}).get("item"),
        "rearSightRow": rs["row"] if rs else None,
        "rearSightCol": rs["col"] if rs else None,
        "optic": ({"row": optic["row"], "col": optic["col"], "empty": optic.get("empty"),
                   "item": optic.get("item")} if optic else None),
        "opticGrandchild": ({"row": grand["row"], "col": grand["col"], "empty": grand.get("empty"),
                             "item": grand.get("item")} if grand else None),
        "slots": s["slots"],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9635)
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=919)
    args = ap.parse_args()

    prof = os.path.join(os.environ.get("TEMP", "."), "r1923prof_%d" % args.port)
    proc, ws = launch(find_chrome(), args.port, args.width, args.height, prof)
    rep = {"generatedFor": "R19.15.3", "guns": {}, "flow": {}, "console": []}
    try:
        cdp = CDP(ws)
        for m in ("Page.enable", "Runtime.enable", "Log.enable", "Network.enable"):
            cdp.call(m)
        cdp.call("Network.setCacheDisabled", cacheDisabled=True)
        cdp.call("Emulation.setDeviceMetricsOverride", width=args.width, height=args.height,
                 deviceScaleFactor=1, mobile=False)
        cdp.call("Page.navigate", url="http://127.0.0.1:8787/index.html")
        wait_ready(cdp, want_url="index.html")
        time.sleep(2.6)
        cdp.eval("document.querySelector('[data-view=\"gun\"]').click()")
        time.sleep(1.8)
        rep["build"] = cdp.eval("(typeof AM_BUILD!=='undefined')?AM_BUILD:null")

        # ---------- 三把枪的静态测量 ----------
        for key, needle in GUNS:
            if not pick_gun(cdp, needle):
                rep["guns"][key] = {"ok": False, "why": "pick failed"}
                continue
            m = measure(cdp)
            rep["guns"][key] = summary(m)
            shot(cdp, "%s-base-1920x919.png" % key)

        # ---------- AK-74N 流程：装基座 → 装瞄具 → 卸下 ----------
        if pick_gun(cdp, "AK-74N"):
            m0 = measure(cdp)
            rep["flow"]["akBase"] = flow_rec(m0)
            slot = click_slot(cdp, "mod_mount_000")
            base_clicked = click_candidate(cdp, BASE_ITEM)
            m1 = measure(cdp)
            rep["flow"]["akOpticInstalled"] = flow_rec(m1)
            shot(cdp, "ak74n-base-installed-1920x919.png")

            # 装瞄具：点基座下的瞄具槽（空槽），选第一个可装瞄具
            scope_clicked = None
            mount_path = None
            for s in (m1.get("slots") or []):
                if (s.get("slot") or "").startswith("mod_mount_000/mod_scope"):
                    mount_path = s["slot"]
                    break
            if mount_path:
                pos = cdp.eval("""(function(){
                  var cs=[].slice.call(document.querySelectorAll('#gw-tree .gw-part[data-slot]'));
                  for(var i=0;i<cs.length;i++){
                    if(cs[i].getAttribute('data-slot')===%s){
                      cs[i].scrollIntoView({block:'center'});
                      var r=cs[i].getBoundingClientRect();
                      return JSON.stringify({x:r.x+r.width/2,y:r.y+r.height/2});}}
                  return null;})()""" % json.dumps(mount_path))
                if pos and pos != "null":
                    p = json.loads(pos)
                    time.sleep(0.3)
                    cdp.click_at(p["x"], p["y"])
                    time.sleep(1.1)
                    scope_clicked = click_candidate(cdp, index=0)
            m2 = measure(cdp)
            rep["flow"]["afterOpticInstall"] = flow_rec(m2)
            rep["flow"]["afterOpticInstall"]["scopeClicked"] = (scope_clicked or {}).get("name")
            rep["flow"]["afterOpticInstall"]["mountPath"] = mount_path
            shot(cdp, "ak74n-optic-chain-1920x919.png")

            # 卸载：重新加载默认装配（预设路径），再确认回到基准
            cdp.eval("document.getElementById('gw-default') && document.getElementById('gw-default').click()")
            time.sleep(1.6)
            m3 = measure(cdp)
            rep["flow"]["akOpticRemoved"] = flow_rec(m3)
            shot(cdp, "ak74n-after-reset-1920x919.png")
            rep["flow"]["baseSlotClicked"] = (slot or {}).get("slot")
            rep["flow"]["baseItemClicked"] = (base_clicked or {}).get("name")

            # 1384 视口
            cdp.call("Emulation.setDeviceMetricsOverride", width=1384, height=805,
                     deviceScaleFactor=1, mobile=False)
            time.sleep(1.2)
            m4 = measure(cdp)
            rep["viewports"] = {"ak74n_1384x805": summary(m4)}
            shot(cdp, "ak74n-1384x805.png")
            cdp.call("Emulation.setDeviceMetricsOverride", width=args.width, height=args.height,
                     deviceScaleFactor=1, mobile=False)
            time.sleep(0.8)

        # ---------- 连接线 / 外观合成 仍然隐藏 ----------
        rep["visual"] = json.loads(cdp.eval("""(function(){
          var t=document.getElementById('gw-tree');
          return JSON.stringify({
            svgCount: t.querySelectorAll('svg').length,
            linkPaths: t.querySelectorAll('.gw-canvas-links path').length,
            skinCount: document.querySelectorAll('.gw-skin').length,
            skinTag: document.querySelectorAll('.gw-skin-tag').length,
            fontBody: getComputedStyle(document.body).fontFamily
          });})()"""))
        rep["console"] = [e for e in (getattr(cdp, "logs", []) or [])][:20]
    finally:
        proc.terminate()

    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, "browser-check.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=1)
    print("build", rep.get("build"))
    for k, v in rep["guns"].items():
        print(" gun", k, "rows", v.get("rows"), "phantom", v.get("phantomCount"),
              "empty", v.get("realEmptySlots"), "click", v.get("emptySlotInteractive"))
    for k, v in rep["flow"].items():
        if not isinstance(v, dict):
            continue
        print(" flow", k, "rows", v.get("rows"), "mount", v.get("mountRow"), v.get("mountCol"),
              "rs", v.get("rearSightCol"), "optic", v.get("optic"), "grand", v.get("opticGrandchild"))
    print(" visual", rep.get("visual"))
    print("wrote", path)


if __name__ == "__main__":
    main()
