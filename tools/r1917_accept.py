# -*- coding: utf-8 -*-
"""R19.14.2 Nightforce 直接槽位专项浏览器验收。

验证（任务书第五节）：
  1 Nightforce 直接槽位严格 2 个（DOM 实测，非数据声明）
  2 两槽用途与兼容物品正确（34mm 光学 / 单倍瞄具·底座）
  3 单倍槽装底座后，其子瞄具槽在底座正上方
  4 多层附件顶部扩展正常
  5 已核实物品槽位数量与数据一致（含 G36 去重后 4=4）
  6 不存在槽位的空白隐藏仍正常
  7 装/卸/预设/枪匠大师 使用一致槽位树（无 _002/_003 残留）
  8 B.A.D r4c6 / MPR45 纵向链 / 六行画布 / 顶部扩展 全部正常

用法：python tools/r1917_accept.py --port 9540
输出：docs/r19.14-layout-changes/nightforce-slot-audit/{browser-check.json, screenshots/*.png}
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
OUT = os.path.join(ROOT, "docs", "r19.14-layout-changes", "nightforce-slot-audit")
SHOTS = os.path.join(OUT, "screenshots")
os.makedirs(SHOTS, exist_ok=True)
with open(os.path.join(ROOT, "tools", "r1916_slots.js"), "r", encoding="utf-8") as f:
    SLOTS_JS = f.read()
URL = "http://127.0.0.1:8787/index.html"
MOUNT_ID = "5aa66c72e5b5b00016327c93"


def shot(cdp, name):
    data = base64.b64decode(cdp.call("Page.captureScreenshot", format_="png",
                                     captureBeyondViewport=False)["data"])
    with open(os.path.join(SHOTS, name), "wb") as f:
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


def uninstall_suffix(cdp, suffix):
    pos = cdp.eval("""(function(){
      var cs=[].slice.call(document.querySelectorAll('#gw-tree .gw-part[data-item][data-slot]'));
      for(var i=0;i<cs.length;i++){
        var s=cs[i].getAttribute('data-slot')||'';
        if(s.split('/').pop()===%s){
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


def mount_children(m):
    """画布上 mod_scope 挂载点的直接子槽（路径深度 = 2）。"""
    out = []
    for s in m.get("slots") or []:
        p = s.get("slot") or ""
        if p.startswith("mod_scope/") and p.count("/") == 1:
            out.append({"slot": p, "sid": p.split("/")[-1], "row": s["row"], "col": s["col"],
                        "item": s.get("item"), "empty": s.get("empty")})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9540)
    args = ap.parse_args()

    proc, ws = launch(find_chrome(), args.port, 1920, 919,
                      os.path.join(os.environ.get("TEMP", "."), "r1917"))
    rep = {"build": None, "mountSlots": {}, "withBase": {}, "extension": {},
           "bad": {}, "mpr45": {}, "phantom": {}, "flow": {}, "console": []}
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

        # ---------- Nightforce：只装底座，数直接槽位 ----------
        if pick_gun(cdp, "SV-98"):
            uninstall_suffix(cdp, "mod_sight_rear")   # 与基座互斥
            click_slot_suffix(cdp, "mod_scope")
            picked = None
            for name in ("Nightforce MagMount Multimount", "Nightforce MagMount一体式", "Nightforce 30毫米"):
                picked = click_candidate(cdp, name)
                mm = measure(cdp)
                if any((s.get("item") or "").find("Nightforce") >= 0 for s in (mm.get("slots") or [])):
                    break
            m1 = measure(cdp)
            kids = mount_children(m1)
            rep["mountSlots"] = {
                "picked": (picked or {}).get("name"),
                "directSlotCount": len(kids),
                "slots": kids,
                "rows": m1.get("rowCount"), "rowHeights": m1.get("rowHeights"),
                "noLegacy002003": not any(
                    ("_002" in (s.get("slot") or "")) or ("_003" in (s.get("slot") or ""))
                    for s in (m1.get("slots") or [])),
                "phantomCount": m1.get("phantomCount"),
            }
            shot(cdp, "N1-nightforce-2-slots-1920.png")

            # ---------- 装 34mm 光学 + 单倍底座，验证方向 ----------
            optics = [s for s in kids if (s.get("slot") or "").endswith("_000")]
            onex = [s for s in kids if (s.get("slot") or "").endswith("_001")]
            h_opt = None
            if optics:
                click_slot_exact(cdp, optics[0]["slot"])
                h_opt = click_candidate(cdp, "ATACR") or click_candidate(cdp, "Nightforce")
            h_base = None
            if onex:
                click_slot_exact(cdp, onex[0]["slot"])
                h_base = click_candidate(cdp, "Aimpoint Micro瞄具基座") or click_candidate(cdp, "瞄具基座")
            m2 = measure(cdp)
            kids2 = mount_children(m2)
            base_cells = [s for s in kids2 if (s.get("slot") or "").endswith("_001")]
            base_child = None
            if base_cells:
                bp = base_cells[0]["slot"]
                for s in (m2.get("slots") or []):
                    if (s.get("slot") or "").startswith(bp + "/") and (s.get("slot") or "").count("/") == bp.count("/") + 1:
                        base_child = {"slot": s["slot"], "row": s["row"], "col": s["col"],
                                      "item": s.get("item")}
                        break
            rep["withBase"] = {
                "opticsPicked": (h_opt or {}).get("name"),
                "basePicked": (h_base or {}).get("name"),
                "directSlotCount": len(kids2),
                "slots": kids2,
                "baseCell": base_cells[0] if base_cells else None,
                "baseChild": base_child,
                "childAboveBase": bool(base_child and base_cells and
                                       base_child["row"] == base_cells[0]["row"] - 1 and
                                       base_child["col"] == base_cells[0]["col"]),
                "opticsAboveMount": bool([s for s in kids2 if (s.get("slot") or "").endswith("_000")] and
                                         [s for s in (m2.get("slots") or []) if (s.get("slot") or "") == "mod_scope"] and
                                         [s for s in kids2 if (s.get("slot") or "").endswith("_000")][0]["row"] <
                                         [s for s in (m2.get("slots") or []) if (s.get("slot") or "") == "mod_scope"][0]["row"]),
                "onexRightOfOptics": bool(
                    [s for s in kids2 if (s.get("slot") or "").endswith("_001")] and
                    [s for s in kids2 if (s.get("slot") or "").endswith("_000")] and
                    [s for s in kids2 if (s.get("slot") or "").endswith("_001")][0]["col"] >
                    [s for s in kids2 if (s.get("slot") or "").endswith("_000")][0]["col"]),
                "rows": m2.get("rowCount"), "topPad": m2.get("topPad"),
                "rowHeights": m2.get("rowHeights"),
                "phantomCount": m2.get("phantomCount"),
            }
            shot(cdp, "N2-nightforce-optics-plus-base-1920.png")

            # 多层：底座子槽再装瞄具 → 顶部扩展
            if base_child:
                click_slot_exact(cdp, base_child["slot"])
                h3 = click_candidate(cdp, "Micro H-2") or click_candidate(cdp, index=0)
                m3 = measure(cdp)
                rep["extension"] = {
                    "picked": (h3 or {}).get("name"),
                    "rows": m3.get("rowCount"), "topPad": m3.get("topPad"),
                    "rowHeights": m3.get("rowHeights"),
                    "cells": [{"slot": s.get("slot"), "row": s["row"], "col": s["col"],
                               "item": s.get("item")}
                              for s in (m3.get("slots") or [])
                              if (s.get("slot") or "").startswith("mod_scope")],
                    "phantomCount": m3.get("phantomCount"),
                }
                shot(cdp, "N3-nightforce-3-layers-top-extend-1920.png")
                # 卸载回退
                uninstall_suffix(cdp, "mod_scope")
                uninstall_suffix(cdp, "mod_scope")
                m4 = measure(cdp)
                rep["extension"]["afterRemoveRows"] = m4.get("rowCount")
                rep["extension"]["afterRemoveTopPad"] = m4.get("topPad")
                shot(cdp, "N4-nightforce-after-remove-1920.png")

        # ---------- B.A.D / MPR45 回归 ----------
        if pick_gun(cdp, "柯尔特 M4A1"):
            m = measure(cdp)
            bad = [s for s in (m.get("slots") or [])
                   if (s.get("slot") or "").split("/")[-1].startswith("mod_charge_001")]
            rep["bad"] = {
                "cells": [{"slot": b["slot"], "row": b["row"], "col": b["col"]} for b in bad],
                "atR4C6": bool(bad) and all(b["row"] == 4 and b["col"] == 6 for b in bad),
                "rows": m.get("rowCount"), "rowHeights": m.get("rowHeights"),
            }
            rep["phantom"] = {
                "phantomCount": m.get("phantomCount"),
                "rows": m.get("rowCount"),
                "emptySlotCount": len(m.get("emptySlots") or []),
            }

        if pick_gun(cdp, "DS Arms SA-58"):
            click_slot_suffix(cdp, "mod_mount")
            click_candidate(cdp, "MPR45")
            m = measure(cdp)
            sub = next((s["slot"] for s in (m.get("slots") or [])
                        if (s.get("slot") or "").startswith("mod_handguard/mod_mount/")
                        and not s.get("item")), None)
            if sub:
                click_slot_exact(cdp, sub)
                click_candidate(cdp, "瞄具基座") or click_candidate(cdp, index=0)
            m2 = measure(cdp)
            chain = [s for s in (m2.get("slots") or [])
                     if (s.get("slot") or "") == "mod_handguard/mod_mount"
                     or (s.get("slot") or "").startswith("mod_handguard/mod_mount/")]
            rep["mpr45"] = {
                "chain": [{"slot": c["slot"], "row": c["row"], "col": c["col"]} for c in
                          sorted(chain, key=lambda x: x["row"])],
                "allSameCol": len({c["col"] for c in chain}) == 1,
                "rows": m2.get("rowCount"),
            }
            shot(cdp, "N5-mpr45-chain-1920.png")

        # ---------- 枪匠大师生成 / 应用：必须使用同一套槽位树 ----------
        if pick_gun(cdp, "SV-98"):
            uninstall_suffix(cdp, "mod_sight_rear")
            click_slot_suffix(cdp, "mod_scope")
            click_candidate(cdp, "Nightforce MagMount Multimount")
            time.sleep(0.6)
            clicked = cdp.eval("""(function(){
              var bs=[].slice.call(document.querySelectorAll('button'));
              for(var i=0;i<bs.length;i++){
                if((bs[i].textContent||'').indexOf('GENERATE')>=0 && !bs[i].disabled){
                  bs[i].click();return true;}}return false;})()""")
            time.sleep(3.0)
            mf = measure(cdp)
            rep["flow"]["afterForge"] = {
                "generated": bool(clicked),
                "slotCount": len([s for s in (mf.get("slots") or []) if s.get("slot")]),
                "treeSlots": mf.get("treeSlots"),
                "hasLegacy002003": any(
                    ("mod_scope_002" in (s.get("slot") or "")) or ("mod_scope_003" in (s.get("slot") or ""))
                    for s in (mf.get("slots") or [])),
                "mountChildren": [s.get("slot") for s in (mf.get("slots") or [])
                                   if (s.get("slot") or "").startswith("mod_scope/")
                                   and (s.get("slot") or "").count("/") == 1],
                "phantomCount": mf.get("phantomCount"),
            }
            shot(cdp, "N6-after-forge-1920.png")

        # ---------- 预设加载：不得出现 _002/_003 ----------
        if pick_gun(cdp, "SV-98"):
            cdp.eval("""(function(){
              var sel=document.querySelector('.gw-loadvar select')||document.querySelector('select');
              if(sel && sel.options.length>1){sel.selectedIndex=1;
                sel.dispatchEvent(new Event('change',{bubbles:true}));}})()""")
            time.sleep(1.8)
            m = measure(cdp)
            rep["flow"]["afterPreset"] = {
                "slotCount": len([s for s in (m.get("slots") or []) if s.get("slot")]),
                "treeSlots": m.get("treeSlots"),
                "hasLegacy002003": any(
                    ("mod_scope_002" in (s.get("slot") or "")) or ("mod_scope_003" in (s.get("slot") or ""))
                    for s in (m.get("slots") or [])),
                "phantomCount": m.get("phantomCount"),
            }

        cdp.drain()
        rep["console"] = cdp.console[:6]
    finally:
        try:
            proc.terminate()
        except Exception:
            pass

    out = os.path.join(OUT, "browser-check.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=2)

    print("build=", rep.get("build"), "app=", rep.get("appSrc"))
    print("mount slots:", json.dumps(rep.get("mountSlots"), ensure_ascii=False)[:400])
    print("with base:", json.dumps(rep.get("withBase"), ensure_ascii=False)[:600])
    print("extension:", json.dumps(rep.get("extension"), ensure_ascii=False)[:400])
    print("bad:", json.dumps(rep.get("bad"), ensure_ascii=False)[:200])
    print("mpr45:", json.dumps(rep.get("mpr45"), ensure_ascii=False)[:300])
    print("phantom:", json.dumps(rep.get("phantom"), ensure_ascii=False)[:200])
    print("flow:", json.dumps(rep.get("flow"), ensure_ascii=False)[:300])
    print("wrote", out)


if __name__ == "__main__":
    main()
