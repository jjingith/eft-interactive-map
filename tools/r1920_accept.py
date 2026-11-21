# -*- coding: utf-8 -*-
"""R19.15 真实浏览器验收：ASH-12 布局 / 全量抽查 / 连接线移除 / 合成图隐藏 / 按钮橙黄。

输出：docs/r19.15-theme-audit/{browser-check.json, screenshots/after/*.png}
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
OUT = os.path.join(ROOT, "docs", "r19.15-theme-audit")
SHOTS = os.path.join(OUT, "screenshots", "after")
os.makedirs(SHOTS, exist_ok=True)
with open(os.path.join(ROOT, "tools", "r1916_slots.js"), "r", encoding="utf-8") as f:
    SLOTS_JS = f.read()
URL = "http://127.0.0.1:8787/index.html"


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
            time.sleep(1.5)
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
        return JSON.stringify({x:r.x+r.width/2,y:r.y+r.height/2,name:h.name});}
      return null;})()"""
                    % ("true" if needle else "false", json.dumps(needle or "", ensure_ascii=False), index))
    if not info or info == "null":
        return None
    h = json.loads(info)
    cdp.click_at(h["x"], h["y"])
    time.sleep(1.4)
    return h


def main_cells(m):
    """主体行（枪身所在行）格子，按列排序。"""
    body = m.get("bodyCell") or {}
    row = body.get("row")
    return sorted([s for s in (m.get("slots") or []) if s["row"] == row and s.get("slot")],
                  key=lambda x: x["col"])


def scope_cells(m):
    return [s for s in (m.get("slots") or []) if (s.get("slot") or "") == "mod_scope"
            or (s.get("slot") or "").startswith("mod_scope/")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9560)
    args = ap.parse_args()

    proc, ws = launch(find_chrome(), args.port, 1920, 919,
                      os.path.join(os.environ.get("TEMP", "."), "r1920"))
    rep = {"build": None, "ash12": {}, "spread": {}, "connector": {}, "skin": {},
           "emptyCoords": {}, "nightforce": {}, "buttons": {}, "viewports": {}, "console": []}
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
            "try{return JSON.parse(x.responseText).rev}catch(e){return ''}})()")
        rep["appSrc"] = cdp.eval("(document.querySelector('script[src*=\"app.js\"]')||{}).src")
        rep["themeHref"] = cdp.eval("(document.querySelector('link[href*=\"theme-windows-xp\"]')||{}).href")

        cdp.eval("try{localStorage.removeItem('eftmap.gwmode')}catch(e){}")
        cdp.eval("document.querySelector('[data-view=\"gun\"]').click()")
        time.sleep(2.2)

        # ---------- ASH-12 ----------
        if pick_gun(cdp, "ASh-12"):
            m = measure(cdp)
            mc = main_cells(m)
            tac = [s for s in (m.get("slots") or [])
                   if (s.get("slot") or "").startswith("mod_tactical")]
            body = m.get("bodyCell") or {}
            rep["ash12"] = {
                "gun": "ASh-12",
                "body": {"row": body.get("row")},
                "mainRow": [{"slot": s["slot"], "col": s["col"], "row": s["row"],
                             "empty": s.get("empty"), "item": s.get("item")} for s in mc],
                "mainBases": [s["slot"] for s in mc],
                "tactical": [{"slot": s["slot"], "row": s["row"], "col": s["col"]} for s in tac],
                "tacticalOnBodyRow": [s["slot"] for s in tac if s["row"] == body.get("row")],
                "mainContiguous": all(mc[i]["col"] + 1 == mc[i + 1]["col"] for i in range(len(mc) - 1)),
                "mainAdjacentToBody": bool(mc) and mc[-1]["col"] == (body.get("col") or 6) - 1,
                "rows": m.get("rowCount"),
                "rowHeights": m.get("rowHeights"),
                "phantomCount": m.get("phantomCount"),
            }
            shot(cdp, "A-ash12-1920.png")

        # ---------- 抽查其他枪 ----------
        for key, needle in [("m4a1", "M4A1"), ("akm", "AKM 7.62x39"), ("hk416", "HK 416A5"),
                            ("spear", "SIG MCX SPEAR"), ("p90", "FN P90")]:
            if not pick_gun(cdp, needle):
                rep["spread"][key] = {"error": "pick failed"}
                continue
            m = measure(cdp)
            mc = main_cells(m)
            body = m.get("bodyCell") or {}
            rep["spread"][key] = {
                "gun": needle,
                "rows": m.get("rowCount"), "rowHeights": m.get("rowHeights"),
                "mainRow": [{"slot": s["slot"], "col": s["col"]} for s in mc],
                "mainContiguous": all(mc[i]["col"] + 1 == mc[i + 1]["col"] for i in range(len(mc) - 1)),
                "mainAdjacentToBody": (not mc) or mc[-1]["col"] == (body.get("col") or 6) - 1 or len(mc) < 2,
                "phantomCount": m.get("phantomCount"),
            }
            shot(cdp, "B-%s-1920.png" % key)

        # ---------- 连接线 / 合成图 / 空坐标 ----------
        if pick_gun(cdp, "M4A1"):
            m = measure(cdp)
            rep["connector"] = json.loads(cdp.eval("""(function(){
              return JSON.stringify({
                svgCount: document.querySelectorAll('#gw-tree svg.gw-canvas-links').length,
                linkPaths: document.querySelectorAll('#gw-tree .gw-link, #gw-tree .gw-canvas-links path').length,
                anySvg: document.querySelectorAll('#gw-tree svg').length
              });})()"""))
            rep["skin"] = json.loads(cdp.eval("""(function(){
              return JSON.stringify({
                skin: document.querySelectorAll('#gw-tree .gw-skin').length,
                tag: document.querySelectorAll('#gw-tree .gw-skin-tag').length,
                tagText: (document.querySelector('#gw-tree .gw-skin-tag')||{}).textContent||null
              });})()"""))
            rep["emptyCoords"] = {"phantomCount": m.get("phantomCount"),
                                  "rows": m.get("rowCount"),
                                  "emptySlots": len(m.get("emptySlots") or [])}

        # ---------- Nightforce 2 槽 ----------
        if pick_gun(cdp, "SV-98"):
            cdp.eval("""(function(){
              var cs=[].slice.call(document.querySelectorAll('#gw-tree .gw-part[data-item][data-slot]'));
              for(var i=0;i<cs.length;i++){
                if((cs[i].getAttribute('data-slot')||'').split('/').pop().indexOf('sight_rear')>=0){
                  var r=cs[i].getBoundingClientRect();
                  window.__rm={x:r.x+r.width/2,y:r.y+r.height/2};break;}}})()""")
            pos = cdp.eval("JSON.stringify(window.__rm||null)")
            if pos and pos != "null":
                p = json.loads(pos)
                cdp.call("Input.dispatchMouseEvent", type="mousePressed", x=p["x"], y=p["y"],
                         button="right", clickCount=1)
                cdp.call("Input.dispatchMouseEvent", type="mouseReleased", x=p["x"], y=p["y"],
                         button="right", clickCount=1)
                time.sleep(1.3)
            click_slot_suffix(cdp, "mod_scope")
            picked = None
            for name in ("Nightforce MagMount Multimount", "Nightforce MagMount一体式"):
                picked = click_candidate(cdp, name)
                mm = measure(cdp)
                if any((s.get("item") or "").find("Nightforce") >= 0 for s in (mm.get("slots") or [])):
                    break
            m = measure(cdp)
            kids = [s for s in scope_cells(m) if (s.get("slot") or "").count("/") == 1]
            rep["nightforce"] = {
                "picked": (picked or {}).get("name"),
                "directSlotCount": len(kids),
                "slots": [{"slot": s["slot"], "row": s["row"], "col": s["col"]} for s in kids],
                "onexRightOfOptics": (len(kids) == 2 and kids[1]["col"] > kids[0]["col"]),
                "phantomCount": m.get("phantomCount"),
            }
            shot(cdp, "C-sv98-nightforce-1920.png")

        # ---------- 按钮橙黄 ----------
        pos_raw = cdp.eval(r"""(function(){
          var bs=[].slice.call(document.querySelectorAll('#gw-tree ~ * button, .gun-workbench button'))
            .filter(function(b){var r=b.getBoundingClientRect();return !b.disabled && r.width>40 && r.height>16;});
          var b=bs[0]; if(!b) return null;
          window.__btn=b; var r=b.getBoundingClientRect();
          return JSON.stringify({x:r.x+r.width/2,y:r.y+r.height/2,text:(b.textContent||'').trim().slice(0,16)});})()""")
        if pos_raw and pos_raw != "null":
            pos = json.loads(pos_raw)
            normal = json.loads(cdp.eval("""(function(){var s=getComputedStyle(window.__btn);
              return JSON.stringify({img:(s.backgroundImage||'').slice(0,90),bg:s.backgroundColor,
                border:s.borderTopColor,color:s.color,attr:window.__btn.getAttribute('data-flash')});})()"""))
            cdp.call("Input.dispatchMouseEvent", type="mouseMoved", x=pos["x"], y=pos["y"], button="none")
            time.sleep(0.4)
            hover = json.loads(cdp.eval("""(function(){var s=getComputedStyle(window.__btn);
              return JSON.stringify({img:(s.backgroundImage||'').slice(0,90),border:s.borderTopColor});})()"""))
            cdp.click_at(pos["x"], pos["y"])
            time.sleep(0.5)
            clicked = json.loads(cdp.eval("""(function(){var s=getComputedStyle(window.__btn);
              var b=window.__btn;
              return JSON.stringify({img:(s.backgroundImage||'').slice(0,90),
                attr:b?b.getAttribute('data-flash'):null});})()"""))
            cdp.call("Input.dispatchMouseEvent", type="mouseMoved", x=3, y=3, button="none")
            time.sleep(0.5)
            after_leave = json.loads(cdp.eval("""(function(){
              var b=window.__btn; if(!b) return '{}';
              var s=getComputedStyle(b);
              return JSON.stringify({img:(s.backgroundImage||'').slice(0,90),attr:b.getAttribute('data-flash')});})()"""))
            rep["buttons"] = {"target": pos, "normal": normal, "hover": hover,
                              "clicked": clicked, "afterLeave": after_leave}
            shot(cdp, "D-button-states-1920.png")

        # ---------- 1384×805 ----------
        # 关闭可能被按钮测试打开的「对比」面板，避免遮挡画布
        cdp.eval("""(function(){
          var bs=[].slice.call(document.querySelectorAll('button'));
          for(var i=0;i<bs.length;i++){
            if((bs[i].textContent||'').trim()==='关闭'){bs[i].click();return true;}}
          return false;})()""")
        time.sleep(1.0)
        cdp.call("Emulation.setDeviceMetricsOverride", width=1384, height=805,
                 deviceScaleFactor=1, mobile=False)
        time.sleep(0.8)
        if pick_gun(cdp, "ASh-12"):
            m = measure(cdp)
            mc = main_cells(m)
            body = m.get("bodyCell") or {}
            rep["viewports"]["1384"] = {
                "ash12Main": [{"slot": s["slot"], "col": s["col"]} for s in mc],
                "mainAdjacentToBody": bool(mc) and mc[-1]["col"] == (body.get("col") or 6) - 1,
                "rows": m.get("rowCount"), "rowHeights": m.get("rowHeights"),
                "phantomCount": m.get("phantomCount"),
            }
            shot(cdp, "E-ash12-1384x805.png")

        cdp.drain()
        rep["console"] = cdp.console[:6]
    finally:
        try:
            proc.terminate()
        except Exception:
            pass

    path = os.path.join(OUT, "browser-check.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=2)
    print("build:", rep.get("build"), "| theme:", rep.get("themeHref"))
    print("ASH12:", json.dumps(rep.get("ash12"), ensure_ascii=False)[:700])
    print("connector:", rep.get("connector"), "| skin:", rep.get("skin"))
    print("nightforce:", json.dumps(rep.get("nightforce"), ensure_ascii=False)[:300])
    print("buttons:", json.dumps(rep.get("buttons"), ensure_ascii=False)[:500])
    print("vp1384:", json.dumps(rep.get("viewports"), ensure_ascii=False)[:300])
    print("wrote", path)


if __name__ == "__main__":
    main()
