# -*- coding: utf-8 -*-
"""R19.14 布局修订 · 浏览器验收：隐藏不存在的槽位格子，保留真实空槽。

验收点（任务书第五节 7 项）：
  1 不存在真实槽位的位置没有可见边框/背景/占位卡片
  2 真实存在但未安装配件的槽位仍能显示和交互
  3 隐藏占位后其他真实槽位坐标没有漂移
  4 基础画布仍保持稳定六行九列坐标系统
  5 MPR45 / Nightforce 多层上置展开时不存在的格子仍不显示
  6 新增顶部行后不为每个空坐标创建可见格框
  7 安装/卸载/切枪/加载预设后空槽显示与槽位树一致

用法：python tools/r1915_accept.py --port 9520
输出：docs/r19.14-layout-changes/{slots-visibility.json, screenshots/*.png}
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

with open(os.path.join(ROOT, "tools", "r1915_slots.js"), "r", encoding="utf-8") as f:
    SLOTS_JS = f.read()

URL = "http://127.0.0.1:8787/index.html"


def shot(cdp, name):
    data = base64.b64decode(cdp.call("Page.captureScreenshot", format_="png",
                                     captureBeyondViewport=False)["data"])
    path = os.path.join(SHOTS, name)
    with open(path, "wb") as f:
        f.write(data)
    return path


def measure(cdp):
    raw = cdp.eval(SLOTS_JS)
    return json.loads(raw) if raw else {"ok": False, "why": "empty"}


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
        var s=cs[i].getAttribute('data-slot')||'';
        if(s.split('/').pop()===%s){
          cs[i].scrollIntoView({block:'center'});
          var r=cs[i].getBoundingClientRect();
          return JSON.stringify({x:r.x+r.width/2,y:r.y+r.height/2, slot:s});}}
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
        var bad=rows[i].className.indexOf('tbl-conflict')>=0;
        hits.push({name:nm,bad:bad});
      }
      if(!hits.length) return null;
      // 优先跳过不可装行（红条），避免点中被约束拒绝的候选
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
    time.sleep(0.3)
    cdp.click_at(h["x"], h["y"])
    time.sleep(1.4)
    return h


def summarize(m, coord_ref=None):
    """把测量压成验收摘要；coord_ref 用于坐标漂移比对。"""
    slots = m.get("slots") or []
    real = [s for s in slots if s.get("slot")]
    s = {
        "gunId": m.get("gunId"),
        "rowCount": m.get("rowCount"),
        "colCount": m.get("colCount"),
        "rowHeights": m.get("rowHeights"),
        "gridH": m.get("gridH"),
        "slotCount": len(real),
        "treeSlotCount": m.get("treeSlotCount"),
        "placedCells": m.get("placedCells"),
        "realEmptySlots": m.get("emptySlotCount"),
        "realEmptySlotsVisible": len([e for e in (m.get("emptySlots") or [])
                                      if e.get("w", 0) > 8 and e.get("h", 0) > 8]),
        "emptySlotInteractive": all(e.get("pointer") != "none" for e in (m.get("emptySlots") or [])),
        "phantomCount": m.get("phantomCount"),
        "phantoms": (m.get("phantoms") or [])[:6],
        "slots": slots,
    }
    if coord_ref:
        drift = []
        # 只按真实槽位路径比对（枪身/子弹格没有 slot 路径，不能当 key）
        ref = {(x.get("slot") or ""): (x.get("row"), x.get("col"))
               for x in coord_ref if x.get("slot")}
        for x in real:
            k = x.get("slot") or ""
            if k in ref and ref[k] != (x.get("row"), x.get("col")):
                drift.append({"slot": k, "was": list(ref[k]),
                              "now": [x.get("row"), x.get("col")]})
        s["coordDrift"] = len(drift)
        s["coordDriftDetail"] = drift[:8]
    else:
        s["coordDrift"] = 0
        s["coordDriftDetail"] = []
    return s


def empty_slot_click_test(cdp):
    """点一个真实空槽：右栏应出现候选（证明可交互）。"""
    pos = cdp.eval("""(function(){
      var cs=[].slice.call(document.querySelectorAll('#gw-tree .gw-part.gw-part-empty[data-slot]'));
      if(!cs.length) return null;
      cs[0].scrollIntoView({block:'center'});
      var r=cs[0].getBoundingClientRect();
      return JSON.stringify({x:r.x+r.width/2,y:r.y+r.height/2,
        slot:cs[0].getAttribute('data-slot')});})()""")
    if not pos or pos == "null":
        return {"clicked": False, "why": "no empty slot"}
    p = json.loads(pos)
    time.sleep(0.3)
    cdp.click_at(p["x"], p["y"])
    time.sleep(1.2)
    info = cdp.eval("""(function(){
      var si=document.getElementById('gw-slotinfo');
      var rows=document.querySelectorAll('#gw-table .tbl-row');
      return JSON.stringify({
        slotInfo:(si&&si.textContent||'').slice(0,60),
        candRows:rows.length});})()""")
    d = json.loads(info) if info else {}
    d["clicked"] = True
    d["slot"] = p["slot"]
    d["interactive"] = bool(d.get("candRows", 0) > 0 or "槽位" in (d.get("slotInfo") or ""))
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9520)
    args = ap.parse_args()

    proc, ws = launch(find_chrome(), args.port, 1920, 919,
                      os.path.join(os.environ.get("TEMP", "."), "r1915"))
    rep = {"build": None, "cases": {}, "topExpansion": {}, "flow": {},
           "emptySlotClick": None, "console": []}
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
            "try{var d=JSON.parse(x.responseText);return d.rev}catch(e){return x.responseText.slice(0,80)}})()")
        rep["appSrc"] = cdp.eval("(document.querySelector('script[src*=\"app.js\"]')||{}).src")

        cdp.eval("try{localStorage.removeItem('eftmap.gwmode')}catch(e){}")
        cdp.eval("document.querySelector('[data-view=\"gun\"]').click()")
        time.sleep(2.2)

        ref_coords = None

        # ---- 基础用例 ----
        guns = [
            ("m4a1", "柯尔特 M4A1", "标准装配"),
            ("akm", "AKM 7.62x39", "无独立枪管槽"),
            ("glock", "Glock 17", "手枪结构"),
            ("sa58", "DS Arms SA-58", "多层枪托链"),
            ("hk416", "HK 416A5", "多层枪口"),
        ]
        for key, needle, desc in guns:
            if not pick_gun(cdp, needle):
                rep["cases"][key] = {"error": "pick failed: " + needle}
                continue
            time.sleep(1.4)
            m = measure(cdp)
            s = summarize(m, ref_coords if key == "m4a1" and ref_coords else None)
            # 首个成功用例作为坐标基准
            if ref_coords is None and m.get("slots"):
                ref_coords = m["slots"]
            if key == "m4a1":
                rep["cases"][key] = s
                shot(cdp, "A-m4a1-real-slots-only-1920.png")
            else:
                rep["cases"][key] = s
                shot(cdp, "B-%s-1920.png" % key)
            rep["cases"][key]["desc"] = desc

        # M4A1 坐标漂移专门比对（重选同枪，与首测比）
        if pick_gun(cdp, "柯尔特 M4A1"):
            m2 = measure(cdp)
            s2 = summarize(m2, ref_coords)
            rep["cases"]["m4a1_rerun"] = s2
            rep["cases"]["m4a1"]["coordDriftCross"] = s2["coordDrift"]

        # ---- 空槽可交互 ----
        rep["emptySlotClick"] = empty_slot_click_test(cdp)

        # ---- 顶部扩展：MPR45（SA-58 的 mod_handguard/mod_mount 允许安装该导轨）----
        # 先装 MPR45（锚定 r2c4），再点它的**子槽**装第二层（r2c3 左侧），
        # 验证多层上置展开后空坐标仍不画格框。
        if pick_gun(cdp, "DS Arms SA-58"):
            click_slot(cdp, "mod_mount")
            h = click_candidate(cdp, "MPR45")
            # 子槽路径以 /mod_scope 结尾（挂在 MPR45/导轨下）
            h2 = None
            pos = cdp.eval("""(function(){
              var cs=[].slice.call(document.querySelectorAll('#gw-tree .gw-part[data-slot]'));
              for(var i=0;i<cs.length;i++){
                var s=cs[i].getAttribute('data-slot')||'';
                if(s.indexOf('mod_mount')>=0 && s.split('/').pop()==='mod_scope'){
                  cs[i].scrollIntoView({block:'center'});
                  var r=cs[i].getBoundingClientRect();
                  return JSON.stringify({x:r.x+r.width/2,y:r.y+r.height/2,slot:s});}}
              return null;})()""")
            if pos and pos != "null":
                p = json.loads(pos)
                time.sleep(0.3)
                cdp.click_at(p["x"], p["y"])
                time.sleep(1.1)
                h2 = click_candidate(cdp, index=0)
            m = measure(cdp)
            t = summarize(m)
            t["expanded"] = True
            t["picked"] = (h or {}).get("name")
            t["picked2"] = (h2 or {}).get("name")
            t["childSlotClicked"] = bool(pos and pos != "null")
            rep["topExpansion"]["mpr45"] = t
            shot(cdp, "C-mpr45-top-expand-1920.png")

        # ---- 顶部扩展：Nightforce 多层 ----
        # 真实兼容链：装 Nightforce 基座环会连带卸下照门（gunCompatOf 的「连带卸下」判定
        # 正确标红 ⛔ 不可装，不允许静默拆别的组件）。所以先右键卸下照门，再装环 + 子瞄具。
        if pick_gun(cdp, "SV-98"):
            # 1) 卸下照门（腾出与基座环的互斥位）
            cdp.eval("""(function(){
              var cs=[].slice.call(document.querySelectorAll('#gw-tree .gw-part[data-item]'));
              for(var i=0;i<cs.length;i++){
                var s=cs[i].getAttribute('data-slot')||'';
                if(s.split('/').pop().indexOf('sight_rear')>=0){
                  var r=cs[i].getBoundingClientRect();
                  window.__rmSight={x:r.x+r.width/2,y:r.y+r.height/2};break;}}})()""")
            pos = cdp.eval("JSON.stringify(window.__rmSight||null)")
            if pos and pos != "null":
                p = json.loads(pos)
                cdp.call("Input.dispatchMouseEvent", type="mousePressed", x=p["x"], y=p["y"],
                         button="right", clickCount=1)
                cdp.call("Input.dispatchMouseEvent", type="mouseReleased", x=p["x"], y=p["y"],
                         button="right", clickCount=1)
                time.sleep(1.3)
            # 2) 装 Nightforce 基座环
            click_slot(cdp, "mod_scope")
            h = None
            for name in ("Nightforce MagMount一体式", "Nightforce 30毫米", "Nightforce MagMount Multimount"):
                h = click_candidate(cdp, name)
                m0 = measure(cdp)
                landed = any((s.get("item") or "").find("Nightforce") >= 0
                             for s in (m0.get("slots") or []))
                if landed:
                    break
            # 3) 子瞄具槽再叠一层
            h2 = None
            pos = cdp.eval("""(function(){
              var cs=[].slice.call(document.querySelectorAll('#gw-tree .gw-part[data-slot]'));
              for(var i=0;i<cs.length;i++){
                var s=cs[i].getAttribute('data-slot')||'';
                if(/mod_scope\\/mod_scope/.test(s)){
                  cs[i].scrollIntoView({block:'center'});
                  var r=cs[i].getBoundingClientRect();
                  return JSON.stringify({x:r.x+r.width/2,y:r.y+r.height/2,slot:s});}}
              return null;})()""")
            if pos and pos != "null":
                p = json.loads(pos)
                time.sleep(0.3)
                cdp.click_at(p["x"], p["y"])
                time.sleep(1.1)
                h2 = click_candidate(cdp, "Nightforce ATACR")
                if not h2:
                    h2 = click_candidate(cdp, "Nightforce")
            m = measure(cdp)
            t = summarize(m)
            t["expanded"] = True
            t["uninstalledSightFirst"] = True
            t["picked"] = (h or {}).get("name")
            t["picked2"] = (h2 or {}).get("name")
            t["childSlotClicked"] = bool(pos and pos != "null")
            t["nightforceLayers"] = len([s for s in (m.get("slots") or [])
                                         if (s.get("item") or "").find("Nightforce") >= 0])
            rep["topExpansion"]["nightforce"] = t
            shot(cdp, "D-nightforce-multilayer-1920.png")

        # ---- 流程一致性：装 / 卸 / 切枪 / 预设 ----
        if pick_gun(cdp, "柯尔特 M4A1"):
            # 安装
            click_slot(cdp, "mod_handguard")
            click_candidate(cdp, index=0)
            m = measure(cdp)
            rep["flow"]["afterInstall"] = summarize(m)
            # 卸载（右键第一张已装卡）
            cdp.eval("""(function(){
              var cs=[].slice.call(document.querySelectorAll('#gw-tree .gw-part[data-item]'));
              if(cs.length){var r=cs[cs.length-1].getBoundingClientRect();
                window.__rm={x:r.x+r.width/2,y:r.y+r.height/2};}})()""")
            pos = cdp.eval("JSON.stringify(window.__rm||null)")
            if pos and pos != "null":
                p = json.loads(pos)
                cdp.call("Input.dispatchMouseEvent", type="mousePressed", x=p["x"], y=p["y"],
                         button="right", clickCount=1)
                cdp.call("Input.dispatchMouseEvent", type="mouseReleased", x=p["x"], y=p["y"],
                         button="right", clickCount=1)
                time.sleep(1.4)
            m = measure(cdp)
            rep["flow"]["afterUninstall"] = summarize(m)
            shot(cdp, "E-after-install-uninstall-1920.png")

        # 切枪
        if pick_gun(cdp, "AKM 7.62x39"):
            m = measure(cdp)
            rep["flow"]["afterGunSwitch"] = summarize(m)

        # 加载预设（LOAD VARIANT → 预设下拉选第一项）
        if pick_gun(cdp, "柯尔特 M4A1"):
            cdp.eval("""(function(){
              var sel=document.querySelector('.gw-loadvar select')||document.querySelector('select');
              if(sel && sel.options.length>1){sel.selectedIndex=1;
                sel.dispatchEvent(new Event('change',{bubbles:true}));}})()""")
            time.sleep(1.8)
            m = measure(cdp)
            rep["flow"]["afterPreset"] = summarize(m)
            shot(cdp, "F-after-preset-1920.png")

        cdp.drain()
        rep["console"] = cdp.console[:6]
    finally:
        try:
            proc.terminate()
        except Exception:
            pass

    out = os.path.join(OUT, "slots-visibility.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=2)

    print("build=", rep.get("build"), "app=", rep.get("appSrc"))
    for k, c in rep["cases"].items():
        print(" case", k, "phantom=", c.get("phantomCount"), "rows=", c.get("rowHeights"),
              "slots=", c.get("slotCount"), "/", c.get("treeSlotCount"),
              "empty=", c.get("realEmptySlots"), "vis=", c.get("realEmptySlotsVisible"),
              "click=", c.get("emptySlotInteractive"), "drift=", c.get("coordDrift"))
    print(" emptySlotClick=", rep.get("emptySlotClick"))
    for k, t in rep["topExpansion"].items():
        print(" top", k, "phantom=", t.get("phantomCount"), "rows=", t.get("rowHeights"))
    for k, f in rep["flow"].items():
        print(" flow", k, "phantom=", f.get("phantomCount"),
              "slots=", f.get("slotCount"), "/", f.get("treeSlotCount"))
    print("wrote", out)


if __name__ == "__main__":
    main()
