# -*- coding: utf-8 -*-
"""R19.14 紧急修复：配枪画布六行真实高度验收（修复前 before / 修复后 after）。

只认浏览器 computed layout：
  - 六条 grid row track 的计算高度（必须全部 >= 最小可见高度）
  - 每行九列的占位/实格矩形
  - 完整画布截图（能数出六行）
禁止用 GW_GRID_ROWS=6 / CSS repeat(6,...) / 自动化测试通过当作结论。

用法：
    python tools/r1914_accept.py --phase before
    python tools/r1914_accept.py --phase after
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
OUT = os.path.join(ROOT, "docs", "r19.14-six-rows")
JS_PATH = os.path.join(ROOT, "tools", "r1914_rows.js")
URL = "http://127.0.0.1:8787/index.html"

with open(JS_PATH, "r", encoding="utf-8") as f:
    ROWS_JS = f.read()


def shot(cdp, name, shot_dir):
    data = base64.b64decode(cdp.call("Page.captureScreenshot", format_="png",
                                     captureBeyondViewport=False)["data"])
    path = os.path.join(shot_dir, name)
    with open(path, "wb") as f:
        f.write(data)
    return path


def measure(cdp):
    raw = cdp.eval(ROWS_JS)
    if not raw:
        return {"ok": False, "why": "empty measure"}
    return json.loads(raw)


def pick_gun(cdp, needle):
    for _ in range(6):
        cdp.eval("""(function(){var b=document.querySelector('.gw-mode[data-gwmode="caliber"]');
          if(b)b.click();})()""")
        time.sleep(0.8)
        pos = cdp.eval("""(function(){var cs=document.querySelectorAll('#gw-browse .gw-card');
          for(var i=0;i<cs.length;i++){var s=cs[i].querySelector('span');
            if(s && s.textContent.indexOf(%s)>=0){cs[i].scrollIntoView({block:'center'});
              var r=cs[i].getBoundingClientRect();
              return JSON.stringify({x:r.x+r.width/2,y:r.y+r.height/2});}}})()"""
                      % json.dumps(needle, ensure_ascii=False))
        if not pos or pos == "null":
            continue
        p = json.loads(pos)
        time.sleep(0.4)
        cdp.click_at(p["x"], p["y"])
        time.sleep(2.2)
        cur = cdp.eval("(document.getElementById('gw-current')||{}).textContent") or ""
        if needle.split(" ")[0] in cur:
            cdp.eval("document.getElementById('gw-default') && document.getElementById('gw-default').click()")
            time.sleep(1.6)
            return True
    return False


def click_slot(cdp, sid_suffix):
    pos = cdp.eval("""(function(){
      var cs=[].slice.call(document.querySelectorAll('#gw-tree .gw-part[data-slot]'));
      for(var i=0;i<cs.length;i++){
        if(cs[i].getAttribute('data-slot').split('/').pop()===%s){
          cs[i].scrollIntoView({block:'center'});
          var r=cs[i].getBoundingClientRect();
          return JSON.stringify({x:r.x+r.width/2,y:r.y+r.height/2, slot:cs[i].getAttribute('data-slot')});}}
      return null;})()""" % json.dumps(sid_suffix))
    if not pos or pos == "null":
        return None
    p = json.loads(pos)
    time.sleep(0.35)
    cdp.click_at(p["x"], p["y"])
    time.sleep(1.2)
    return p


def click_candidate(cdp, needle=None, index=0):
    info = cdp.eval("""(function(){
      var rows=[].slice.call(document.querySelectorAll('#gw-table .tbl-row'));
      var hits=[];
      for(var i=0;i<rows.length;i++){
        if(rows[i].className.indexOf('tbl-empty')>=0) continue;
        var nm=(rows[i].querySelector('.gw-row-name b')||{}).textContent||'';
        if(%s && nm.indexOf(%s)<0) continue;
        hits.push({name:nm});
      }
      if(!hits.length) return null;
      var h=hits[Math.min(%d,hits.length-1)];
      for(var i=0;i<rows.length;i++){
        if(rows[i].className.indexOf('tbl-empty')>=0) continue;
        var nm=(rows[i].querySelector('.gw-row-name b')||{}).textContent||'';
        if(nm!==h.name) continue;
        rows[i].scrollIntoView({block:'center'});
        var r=rows[i].getBoundingClientRect();
        return JSON.stringify({x:r.x+r.width/2,y:r.y+r.height/2,name:h.name});}
      return null;})()"""
                    % ("true" if needle else "false", json.dumps(needle or "", ensure_ascii=False), index))
    if not info or info == "null":
        return None
    h = json.loads(info)
    time.sleep(0.3)
    cdp.click_at(h["x"], h["y"])
    time.sleep(1.4)
    return h


def verdict(m):
    """六行可见判定：只认 track 计算高度 + 每行列覆盖（枪身跨 3 列算 3 格）。"""
    if not m.get("ok"):
        return {"pass": False, "why": m.get("why")}
    g = m["grid"]
    min_h = 24  # 低于此视为塌缩
    zero = [t for t in g["trackRects"] if t["height"] < min_h]
    cover = m.get("coverCount") or {}
    row_cells = {}
    cover_cells = {}
    for r in range(1, 7):
        row_cells[r] = len(m.get("byRow", {}).get(str(r), []) or [])
        cover_cells[r] = int(cover.get(str(r), 0) or 0)
    # 每行必须盖满 9 列（实格 / 枪身跨列 / 空位占位都算）
    thin_rows = [r for r in range(1, 7) if cover_cells.get(r, 0) < 9]
    return {
        "pass": (g["rowCount"] == 6 and g["colCount"] == 9
                 and not zero and not thin_rows
                 and g["height"] > 200),
        "rowCount": g["rowCount"],
        "colCount": g["colCount"],
        "rowHeights": g["rowSizes"],
        "zeroOrCollapsedTracks": [t["track"] for t in zero],
        "cellsPerRow": row_cells,
        "coverPerRow": cover_cells,
        "rowsWithFewerThan9Cells": thin_rows,
        "gridHeight": g["height"],
        "canvasFullyInViewport": m.get("canvasFullyInViewport"),
        "parent": m.get("parent"),
    }


def run_case(cdp, shot_dir, name, label):
    m = measure(cdp)
    v = verdict(m)
    path = shot(cdp, "%s-%s-1920.png" % (name, label) if "1384" not in label
                else "%s-%s.png" % (name, label), shot_dir)
    return {"measure": m, "verdict": v, "shot": path, "label": label}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", default="after", choices=["before", "after"])
    ap.add_argument("--port", type=int, default=9514)
    args = ap.parse_args()

    shot_dir = os.path.join(OUT, args.phase, "screenshots")
    os.makedirs(shot_dir, exist_ok=True)

    proc, ws = launch(find_chrome(), args.port, 1920, 919,
                      os.path.join(os.environ.get("TEMP", "."), "r1914-" + args.phase))
    rep = {"phase": args.phase, "build": None, "resources": [], "cases": {},
           "viewports": {}, "console": []}
    try:
        cdp = CDP(ws)
        for mth in ("Page.enable", "Runtime.enable", "Log.enable", "Network.enable"):
            cdp.call(mth)
        # 禁用缓存：强制加载当前磁盘上的 app.js / style.css
        cdp.call("Network.setCacheDisabled", cacheDisabled=True)
        cdp.call("Emulation.setDeviceMetricsOverride", width=1920, height=919,
                 deviceScaleFactor=1, mobile=False)
        cdp.call("Page.navigate", url=URL)
        wait_ready(cdp, want_url="index.html")
        time.sleep(2.5)

        rep["build"] = {
            "api": json.loads(cdp.eval(
                "fetch('/api/build').then(function(r){return r.text()})") or "{}"
            ) if False else None,
            "dom": cdp.eval("(document.getElementById('build-rev')||{}).textContent"),
            "appSrc": cdp.eval(
                "(document.querySelector('script[src*=\"app.js\"]')||{}).src"),
            "cssHref": cdp.eval(
                "(document.querySelector('link[href*=\"style.css\"]')||{}).href"),
            "themeHref": cdp.eval(
                "(document.querySelector('link[href*=\"theme-windows-xp\"]')||{}).href"),
        }
        # /api/build 同步取一次（确认服务端 rev 与磁盘资源）
        rep["build"]["apiRaw"] = cdp.eval(
            "(function(){var x=new XMLHttpRequest();x.open('GET','/api/build',false);"
            "x.send();return x.responseText;})()")
        try:
            api = json.loads(rep["build"]["apiRaw"])
            rep["build"]["apiRev"] = api.get("rev")
            rep["build"]["assets"] = [
                {"file": a.get("file"), "size": a.get("size"),
                 "sha": (a.get("sha256") or "")[:12], "mtime": a.get("mtime")}
                for a in api.get("assets") or []]
        except Exception as e:
            rep["build"]["apiError"] = str(e)

        # 确认加载的 JS 里不是旧缓存：检查关键标识
        rep["runtimeFlags"] = cdp.eval("""(function(){
          return JSON.stringify({
            hasGrid: !!document.querySelector('#gw-tree.gw-grid'),
            rowsVar: (document.querySelector('#gw-tree')||{style:{}}).style.getPropertyValue
              ? (document.querySelector('#gw-tree').style.getPropertyValue('--gw-rows')) : null,
            amBuild: (typeof AM_BUILD!=='undefined')?AM_BUILD:null,
            gwRows: (typeof GW_GRID_ROWS!=='undefined')?GW_GRID_ROWS:'inline'
          });})()""")

        # ---- 进入配枪工作台 ----
        cdp.eval("try{localStorage.removeItem('eftmap.gwmode')}catch(e){}")
        cdp.eval("document.querySelector('[data-view=\"gun\"]').click()")
        time.sleep(2.2)

        # ---- 用例 1：默认枪械画布（选中一把枪后点「恢复默认」= 官方默认装配）----
        if pick_gun(cdp, "HK 416A5"):
            rep["cases"]["default"] = run_case(cdp, shot_dir, "A-default", "1920x919")
        else:
            rep["cases"]["default"] = {"error": "pick default gun failed"}

        # ---- 用例 2：M4A1 标准装配 ----
        if pick_gun(cdp, "M4A1"):
            rep["cases"]["m4a1"] = run_case(cdp, shot_dir, "B-m4a1-default", "1920x919")
        else:
            rep["cases"]["m4a1"] = {"error": "pick M4A1 failed"}

        # ---- 用例 3：AKM（无独立枪管槽）----
        if pick_gun(cdp, "AKM"):
            rep["cases"]["akm"] = run_case(cdp, shot_dir, "C-akm", "1920x919")
        else:
            rep["cases"]["akm"] = {"error": "pick AKM failed"}

        # ---- 用例 4：多层枪口（HK 416A5）----
        if pick_gun(cdp, "HK 416A5"):
            ms = click_slot(cdp, "muzzle")
            if ms:
                click_candidate(cdp, index=0)
            ms2 = click_slot(cdp, "muzzle")
            if ms2:
                click_candidate(cdp, index=0)
            rep["cases"]["hk416_muzzle"] = run_case(
                cdp, shot_dir, "D-hk416-muzzle-chain", "1920x919")
        else:
            rep["cases"]["hk416_muzzle"] = {"error": "pick HK416 failed"}

        # ---- 用例 5：M4A1 增删配件前后 ----
        if pick_gun(cdp, "M4A1"):
            rep["cases"]["m4_before_add"] = run_case(
                cdp, shot_dir, "E-m4-before-add", "1920x919")
            click_slot(cdp, "handguard")
            click_candidate(cdp, index=0)
            rep["cases"]["m4_after_add"] = run_case(
                cdp, shot_dir, "F-m4-after-add", "1920x919")
            # 移除配件：右键卸下第一个已装子件
            cdp.eval("""(function(){
              var cs=[].slice.call(document.querySelectorAll('#gw-tree .gw-part[data-item]'));
              if(cs.length){var r=cs[cs.length-1].getBoundingClientRect();
                window.__gwRm={x:r.x+r.width/2,y:r.y+r.height/2};}})()""")
            pos = cdp.eval("JSON.stringify(window.__gwRm||null)")
            if pos and pos != "null":
                p = json.loads(pos)
                cdp.call("Input.dispatchMouseEvent", type="mousePressed", x=p["x"],
                         y=p["y"], button="right", clickCount=1)
                cdp.call("Input.dispatchMouseEvent", type="mouseReleased", x=p["x"],
                         y=p["y"], button="right", clickCount=1)
                time.sleep(1.4)
            rep["cases"]["m4_after_remove"] = run_case(
                cdp, shot_dir, "G-m4-after-remove", "1920x919")

        # ---- 视口 1384×805 ----
        for vp_name, w, h, gun in (("1384x805", 1384, 805, "M4A1"),):
            cdp.call("Emulation.setDeviceMetricsOverride", width=w, height=h,
                     deviceScaleFactor=1, mobile=False)
            time.sleep(0.8)
            pick_gun(cdp, gun)
            m = measure(cdp)
            v = verdict(m)
            path = shot(cdp, "H-m4-%s.png" % vp_name, shot_dir)
            rep["viewports"][vp_name] = {"measure": m, "verdict": v, "shot": path}

        # 回到 1920 再测一次默认（确认视口切换无副作用）
        cdp.call("Emulation.setDeviceMetricsOverride", width=1920, height=919,
                 deviceScaleFactor=1, mobile=False)
        time.sleep(0.6)
        rep["cases"]["back_1920"] = run_case(cdp, shot_dir, "I-back-1920", "1920x919")

        cdp.drain()
        rep["console"] = cdp.console
    finally:
        try:
            proc.terminate()
        except Exception:
            pass

    out_json = os.path.join(OUT, args.phase, "rows-measure.json")
    os.makedirs(os.path.dirname(out_json), exist_ok=True)
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=2)

    # 摘要
    print("phase=", args.phase)
    print("build=", json.dumps(rep.get("build", {}), ensure_ascii=False)[:400])
    for k, c in rep["cases"].items():
        v = c.get("verdict") or {}
        print(" case", k, "pass=", v.get("pass"), "rows=", v.get("rowCount"),
              "heights=", v.get("rowHeights"), "zero=", v.get("zeroOrCollapsedTracks"),
              "cells=", v.get("cellsPerRow"))
    for k, c in rep["viewports"].items():
        v = c.get("verdict") or {}
        print(" vp", k, "pass=", v.get("pass"), "rows=", v.get("rowCount"),
              "heights=", v.get("rowHeights"), "zero=", v.get("zeroOrCollapsedTracks"))
    print("wrote", out_json)


if __name__ == "__main__":
    main()
