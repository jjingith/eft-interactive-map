# -*- coding: utf-8 -*-
"""R19.14.1 画布验收：B.A.D. / MPR45 竖直链 / Nightforce 主链+侧分支 / 顶部扩展 / 外观隐藏。

只认浏览器真实 DOM 坐标与计算样式：
  · B.A.D. 槽位必须落在 r4c6；
  · MPR45 子槽严格同列（c4）向正上方，三层触发顶部扩展；
  · Nightforce Multimount 主光学链在 c5 向上，侧分支在主链右侧；
  · 移除附件后扩展行数收缩回 6；
  · 不存在槽位无可见格框、真实空槽可交互；
  · 实时外观合成区已隐藏且不影响槽位/安装状态。

用法：python tools/r1916_accept.py --port 9530
输出：docs/r19.14-layout-changes/{layout-rules.json, screenshots/*.png}
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
OUT = os.path.join(ROOT, "docs", "r19.14-layout-changes")
SHOTS = os.path.join(OUT, "screenshots")
os.makedirs(SHOTS, exist_ok=True)
with open(os.path.join(ROOT, "tools", "r1916_slots.js"), "r", encoding="utf-8") as f:
    SLOTS_JS = f.read()
URL = "http://127.0.0.1:8787/index.html"


def shot(cdp, name):
    data = base64.b64decode(cdp.call("Page.captureScreenshot", format_="png",
                                     captureBeyondViewport=False)["data"])
    p = os.path.join(SHOTS, name)
    with open(p, "wb") as f:
        f.write(data)
    return name


def measure(cdp):
    raw = cdp.eval(SLOTS_JS)
    return json.loads(raw) if raw else {"ok": False}


def pick_gun(cdp, needle):
    for _ in range(6):
        cdp.eval("""(function(){var b=document.querySelector('.gw-mode[data-gwmode="caliber"]');
          if(b)b.click();})()""")
        time.sleep(0.7)
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
        time.sleep(2.2)
        cur = cdp.eval("(document.getElementById('gw-current')||{}).textContent") or ""
        if needle.split(" ")[0] in cur:
            cdp.eval("document.getElementById('gw-default') && document.getElementById('gw-default').click()")
            time.sleep(1.6)
            return True
    return False


def click_slot_exact(cdp, slot_path):
    pos = cdp.eval("""(function(){
      var cs=[].slice.call(document.querySelectorAll('#gw-tree .gw-part[data-slot]'));
      for(var i=0;i<cs.length;i++){
        if(cs[i].getAttribute('data-slot')===%s){
          cs[i].scrollIntoView({block:'center'});
          var r=cs[i].getBoundingClientRect();
          return JSON.stringify({x:r.x+r.width/2,y:r.y+r.height/2});}}
      return null;})()""" % json.dumps(slot_path))
    if not pos or pos == "null":
        return None
    p = json.loads(pos)
    cdp.click_at(p["x"], p["y"])
    time.sleep(1.2)
    return p


def click_slot_suffix(cdp, suffix):
    pos = cdp.eval("""(function(){
      var cs=[].slice.call(document.querySelectorAll('#gw-tree .gw-part[data-slot]'));
      for(var i=0;i<cs.length;i++){
        var s=cs[i].getAttribute('data-slot')||'';
        if(s.split('/').pop()===%s){
          cs[i].scrollIntoView({block:'center'});
          var r=cs[i].getBoundingClientRect();
          return JSON.stringify({x:r.x+r.width/2,y:r.y+r.height/2,slot:s});}}
      return null;})()""" % json.dumps(suffix))
    if not pos or pos == "null":
        return None
    p = json.loads(pos)
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
        hits.push({name:nm, bad:rows[i].className.indexOf('tbl-conflict')>=0});
      }
      if(!hits.length) return null;
      var good=hits.filter(function(x){return !x.bad;});
      var pool=good.length?good:hits;
      var h=pool[Math.min(%d,pool.length-1)];
      for(var i=0;i<rows.length;i++){
        if(rows[i].className.indexOf('tbl-empty')>=0) continue;
        var nm=(rows[i].querySelector('.gw-row-name b')||{}).textContent||'';
        if(nm!==h.name) continue;
        rows[i].scrollIntoView({block:'center'});
        var r=rows[i].getBoundingClientRect();
        return JSON.stringify({x:r.x+r.width/2,y:r.y+r.height/2,name:h.name,conflict:h.bad});}
      return null;})()"""
                    % ("true" if needle else "false", json.dumps(needle or "", ensure_ascii=False), index))
    if not info or info == "null":
        return None
    h = json.loads(info)
    cdp.click_at(h["x"], h["y"])
    time.sleep(1.5)
    return h


def uninstall_by_suffix(cdp, suffix):
    pos = cdp.eval("""(function(){
      var cs=[].slice.call(document.querySelectorAll('#gw-tree .gw-part[data-item][data-slot]'));
      for(var i=0;i<cs.length;i++){
        var s=cs[i].getAttribute('data-slot')||'';
        if(s.split('/').pop().indexOf(%s)>=0){
          var r=cs[i].getBoundingClientRect();
          return JSON.stringify({x:r.x+r.width/2,y:r.y+r.height/2,slot:s});}}
      return null;})()""" % json.dumps(suffix))
    if not pos or pos == "null":
        return None
    p = json.loads(pos)
    cdp.call("Input.dispatchMouseEvent", type="mousePressed", x=p["x"], y=p["y"], button="right", clickCount=1)
    cdp.call("Input.dispatchMouseEvent", type="mouseReleased", x=p["x"], y=p["y"], button="right", clickCount=1)
    time.sleep(1.4)
    return p


def chain_of(m, root_slot):
    """取 root 及其所有后代在画布上的 (row,col)。"""
    out = []
    for s in m.get("slots") or []:
        p = s.get("slot") or ""
        if p == root_slot or p.startswith(root_slot + "/"):
            out.append({"slot": p, "row": s["row"], "col": s["col"],
                        "item": s.get("item"), "empty": s.get("empty")})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9530)
    args = ap.parse_args()

    proc, ws = launch(find_chrome(), args.port, 1920, 919,
                      os.path.join(os.environ.get("TEMP", "."), "r1916"))
    rep = {"build": None, "bad": {}, "mpr45": {}, "nightforce": {},
           "contraction": {}, "phantom": {}, "skin": {}, "console": []}
    try:
        cdp = CDP(ws)
        for mth in ("Page.enable", "Runtime.enable", "Log.enable", "Network.enable"):
            cdp.call(mth)
        cdp.call("Network.setCacheDisabled", cacheDisabled=True)
        cdp.call("Emulation.setDeviceMetricsOverride", width=1920, height=919,
                 deviceScaleFactor=1, mobile=False)
        cdp.call("Page.navigate", url=URL)
        wait_ready(cdp, want_url="index.html")
        time.sleep(2.5)

        rep["build"] = cdp.eval(
            "(function(){var x=new XMLHttpRequest();x.open('GET','/api/build',false);x.send();"
            "try{return JSON.parse(x.responseText).rev}catch(e){return x.responseText.slice(0,80)}})()")
        rep["appSrc"] = cdp.eval("(document.querySelector('script[src*=\"app.js\"]')||{}).src")

        cdp.eval("try{localStorage.removeItem('eftmap.gwmode')}catch(e){}")
        cdp.eval("document.querySelector('[data-view=\"gun\"]').click()")
        time.sleep(2.2)

        # ---------- 1) B.A.D. 必须 r4c6 ----------
        if pick_gun(cdp, "柯尔特 M4A1"):
            m = measure(cdp)
            bad = [s for s in (m.get("slots") or [])
                   if (s.get("slot") or "").split("/")[-1].startswith("mod_charge_001")]
            rep["bad"] = {
                "gun": m.get("gunId") or "M4A1",
                "cells": [{"slot": b["slot"], "row": b["row"], "col": b["col"],
                           "item": b.get("item")} for b in bad],
                "atR4C6": bool(bad) and all(b["row"] == 4 and b["col"] == 6 for b in bad),
                "rows": m.get("rowCount"), "rowHeights": m.get("rowHeights"),
            }
            shot(cdp, "G-bad-r4c6-m4a1-1920.png")

        # ---------- 2) MPR45 竖直链 + 三层顶部扩展 ----------
        if pick_gun(cdp, "DS Arms SA-58"):
            # 装 MPR45
            click_slot_suffix(cdp, "mod_mount")
            h1 = click_candidate(cdp, "MPR45")
            m1 = measure(cdp)
            # 二层：MPR45 子槽装基座
            sub = next((s["slot"] for s in (m1.get("slots") or [])
                        if (s.get("slot") or "").startswith("mod_handguard/mod_mount/")
                        and not s.get("item")), None)
            h2 = None
            if sub:
                click_slot_exact(cdp, sub)
                h2 = click_candidate(cdp, "瞄具基座") or click_candidate(cdp, index=0)
            m2 = measure(cdp)
            # 三层：基座子槽装瞄具
            sub2 = next((s["slot"] for s in (m2.get("slots") or [])
                         if (s.get("slot") or "").startswith("mod_handguard/mod_mount/")
                         and not s.get("item")), None)
            h3 = None
            if sub2:
                click_slot_exact(cdp, sub2)
                h3 = click_candidate(cdp, "Micro H-2") or click_candidate(cdp, index=0)
            m3 = measure(cdp)
            ch = chain_of(m3, "mod_handguard/mod_mount")
            # 从上到下（子→父）排序，用于「逐层向上」判定
            ch_desc = sorted(ch, key=lambda c: c["row"])
            cols = sorted({c["col"] for c in ch})
            rep["mpr45"] = {
                "picked": [h1 and h1.get("name"), h2 and h2.get("name"), h3 and h3.get("name")],
                "rows": m3.get("rowCount"), "topPad": m3.get("topPad"),
                "rowHeights": m3.get("rowHeights"),
                "chain": sorted(ch, key=lambda c: c["row"]),
                "allSameCol": len(cols) == 1,
                # 逐层向上：父在下、子在上，行号自下而上每层恰好 -1（如 r3 → r2 → r1）
                "strictlyUpward": all(
                    ch_desc[i + 1]["row"] == ch_desc[i]["row"] + 1
                    for i in range(len(ch_desc) - 1)
                ) if len(ch_desc) > 1 else None,
                "phantomCount": m3.get("phantomCount"),
            }
            shot(cdp, "H-mpr45-vertical-chain-3layers-1920.png")

            # ---------- 3) 移除附件 → 行数收缩 ----------
            for _ in range(2):
                uninstall_by_suffix(cdp, "mod_scope")
            m4 = measure(cdp)
            rep["contraction"] = {
                "rowsAfter": m4.get("rowCount"),
                "topPadAfter": m4.get("topPad"),
                "rowHeights": m4.get("rowHeights"),
                "chain": chain_of(m4, "mod_handguard/mod_mount"),
                "shrunk": (m4.get("rowCount") or 0) < (m3.get("rowCount") or 0),
            }
            shot(cdp, "I-mpr45-after-remove-1920.png")

        # ---------- 4) Nightforce Multimount 主链 + 侧分支 ----------
        if pick_gun(cdp, "SV-98"):
            uninstall_by_suffix(cdp, "sight_rear")
            click_slot_suffix(cdp, "mod_scope")
            h = None
            for name in ("Nightforce MagMount Multimount", "Nightforce MagMount一体式", "Nightforce 30毫米"):
                h = click_candidate(cdp, name)
                mm = measure(cdp)
                if any((s.get("item") or "").find("Nightforce") >= 0 for s in (mm.get("slots") or [])):
                    break
            # 主光学链装 ATACR
            m5 = measure(cdp)
            main_slot = None
            for s in (m5.get("slots") or []):
                if (s.get("slot") or "").startswith("mod_scope/") and not s.get("item"):
                    main_slot = s["slot"]
                    break
            h2 = None
            if main_slot:
                click_slot_exact(cdp, main_slot)
                h2 = click_candidate(cdp, "ATACR") or click_candidate(cdp, "Nightforce")
            m6 = measure(cdp)
            ch = chain_of(m6, "mod_scope")
            scope_cell = next((c for c in ch if c["slot"] == "mod_scope"), None)
            main_cells = [c for c in ch if c["slot"] != "mod_scope"]
            right_of_scope = [c for c in main_cells if scope_cell and c["col"] > scope_cell["col"]]
            above_same_col = [c for c in main_cells if scope_cell and c["col"] == scope_cell["col"]]
            rep["nightforce"] = {
                "picked": [h and h.get("name"), h2 and h2.get("name")],
                "scopeCell": scope_cell,
                "chain": sorted(ch, key=lambda c: (c["col"], c["row"])),
                "mainChainAbove": [{"slot": c["slot"], "row": c["row"], "col": c["col"],
                                    "item": c["item"]} for c in above_same_col],
                "sideBranchesRight": [{"slot": c["slot"], "row": c["row"], "col": c["col"],
                                       "item": c["item"]} for c in right_of_scope],
                "hasMainChain": len(above_same_col) >= 1,
                "hasSideBranch": len(right_of_scope) >= 1,
                "rows": m6.get("rowCount"), "rowHeights": m6.get("rowHeights"),
                "phantomCount": m6.get("phantomCount"),
            }
            shot(cdp, "J-nightforce-main-and-side-1920.png")

        # ---------- 5) 占位格 / 空槽 / 外观隐藏 ----------
        if pick_gun(cdp, "柯尔特 M4A1"):
            m = measure(cdp)
            # 点一个真实空槽验证可交互
            empty = next((s for s in (m.get("slots") or []) if s.get("empty") and s.get("slot")), None)
            click_ok = False
            if empty:
                click_slot_exact(cdp, empty["slot"])
                info = cdp.eval("""(function(){
                  var si=document.getElementById('gw-slotinfo');
                  return JSON.stringify({t:(si&&si.textContent||'').slice(0,40),
                    rows:document.querySelectorAll('#gw-table .tbl-row').length});})()""")
                d = json.loads(info) if info else {}
                click_ok = bool(d.get("rows", 0) > 0)
            rep["phantom"] = {
                "phantomCount": m.get("phantomCount"),
                "phantoms": (m.get("phantoms") or [])[:6],
                "rows": m.get("rowCount"), "rowHeights": m.get("rowHeights"),
                "emptySlotCount": len(m.get("emptySlots") or []),
                "emptySlotClickable": click_ok,
                "emptySlotSample": (empty or {}).get("slot"),
            }
            rep["skin"] = {
                "skinPresent": m.get("skinPresent"),
                "skinTag": m.get("skinTag"),
                "hasBodyCell": bool(m.get("bodyCell")),
                "bodyRow": (m.get("bodyCell") or {}).get("row"),
                "ammoText": m.get("ammoText"),
            }
            shot(cdp, "K-m4a1-no-ghost-no-skin-1920.png")

        cdp.drain()
        rep["console"] = cdp.console[:6]
    finally:
        try:
            proc.terminate()
        except Exception:
            pass

    out = os.path.join(OUT, "layout-rules.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=2)

    print("build=", rep.get("build"), "app=", rep.get("appSrc"))
    print("BAD:", json.dumps(rep.get("bad"), ensure_ascii=False)[:300])
    print("MPR45:", json.dumps({k: v for k, v in rep.get("mpr45", {}).items()
                                if k in ("rows", "topPad", "allSameCol", "strictlyUpward",
                                         "picked", "chain", "phantomCount")}, ensure_ascii=False)[:600])
    print("contraction:", json.dumps(rep.get("contraction"), ensure_ascii=False)[:300])
    print("NF:", json.dumps({k: v for k, v in rep.get("nightforce", {}).items()
                             if k in ("picked", "hasMainChain", "hasSideBranch", "rows",
                                      "mainChainAbove", "sideBranchesRight")}, ensure_ascii=False)[:700])
    print("phantom:", json.dumps(rep.get("phantom"), ensure_ascii=False)[:300])
    print("skin:", json.dumps(rep.get("skin"), ensure_ascii=False)[:200])
    print("wrote", out)


if __name__ == "__main__":
    main()
