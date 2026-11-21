# -*- coding: utf-8 -*-
"""R19.19 真实浏览器验收（任务 A：AK 照门槽位修复）。

用法：python tools/r1927_accept.py --port 9671
产物：docs/r19.19-ak-rear-sight/browser-accept.json + screenshots/

必验：五把 5.45/5.56（AK-105/AK-74/AK-74N/AKS-74/AKS-74N）照门在 r2c6；
     五把 7.62x39（AKM/AKMS/AKMN/AKMSN/VPO-136）唯一照门槽 + AKMP 可装；
     安装/卸下无重复槽；刷新后坐标不变；校准器与主画布一致。
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
OUT = os.path.join(ROOT, "docs", "r19.19-ak-rear-sight")
BASE = "http://127.0.0.1:8787"

A1_GUNS = [
    ("ak105", "5ac66d9b5acfc4001633997a", "AK-105"),
    ("ak74", "5bf3e03b0db834001d2c4a9c", "AK-74"),
    ("ak74n", "5644bd2b4bdc2d3b4c8b4572", "AK-74N"),
    ("aks74", "5bf3e0490db83400196199af", "AKS-74"),
    ("aks74n", "5ab8e9fcd8ce870019439434", "AKS-74N"),
]
A2_GUNS = [
    ("akm", "59d6088586f774275f37482f", "AKM"),
    ("akms", "59ff346386f77477562ff5e2", "AKMS"),
    ("akmn", "5a0ec13bfcdbcb00165aa685", "AKMN"),
    ("akmsn", "5abcbc27d8ce8700182eceeb", "AKMSN"),
    ("vpo136", "59e6152586f77473dc057aa1", "VPO-136"),
]


def shot(cdp, name):
    d = os.path.join(OUT, "screenshots")
    os.makedirs(d, exist_ok=True)
    data = base64.b64decode(cdp.call("Page.captureScreenshot", format_="png",
                                     captureBeyondViewport=False)["data"])
    with open(os.path.join(d, name), "wb") as f:
        f.write(data)


def pick_gun(cdp, needle, want_gid):
    tried = set()
    for _ in range(8):
        cdp.eval("""(function(){var b=document.querySelector('.gw-mode[data-gwmode="caliber"]');
          if(b)b.click();})()""")
        time.sleep(0.5)
        raw = cdp.eval("""(function(){var cs=document.querySelectorAll('#gw-browse .gw-card');
          var out=[];for(var i=0;i<cs.length;i++){var s=cs[i].querySelector('span');
            if(s && s.textContent.indexOf(%s)>=0){out.push(i);}}return JSON.stringify(out);})()"""
                      % json.dumps(needle, ensure_ascii=False))
        idxs = json.loads(raw or "[]")
        nxt = next((i for i in idxs if i not in tried), None)
        if nxt is None:
            return None
        tried.add(nxt)
        pos = cdp.eval("""(function(){var cs=document.querySelectorAll('#gw-browse .gw-card');
          var c=cs[%d]; if(!c) return null; c.scrollIntoView({block:'center'});
          var r=c.getBoundingClientRect();
          return JSON.stringify({x:r.x+r.width/2,y:r.y+r.height/2});})()""" % nxt)
        if not pos or pos == "null":
            continue
        p = json.loads(pos)
        cdp.click_at(p["x"], p["y"])
        time.sleep(1.8)
        gid = cdp.eval("(function(){try{return (JSON.parse(localStorage.getItem('eftmap.gun')||'{}')||{}).gunId||'';}catch(e){return '';}})()") or ""
        if gid == want_gid:
            cdp.eval("document.getElementById('gw-default') && document.getElementById('gw-default').click()")
            time.sleep(1.5)
            return True
    return False


def canvas_snap(cdp):
    raw = cdp.eval(r"""(function(){
      var t=document.getElementById('gw-tree');
      if(!t) return JSON.stringify({ok:false});
      var cards=[].slice.call(t.querySelectorAll('.gw-part')).filter(function(c){return c.dataset.slot;});
      return JSON.stringify({
        ok:true,
        calib:t.getAttribute('data-calib'),
        applied:t.getAttribute('data-calib-applied'),
        topPad:+(t.getAttribute('data-top-pad')||0),
        cards:cards.map(function(c){
          return {slot:c.dataset.slot,row:+c.dataset.row,col:+c.dataset.col,
                  item:c.getAttribute('data-item')||''};
        }),
        gun:(document.getElementById('gw-current')||{textContent:''}).textContent.trim()
      });})()""")
    return json.loads(raw) if raw else {"ok": False}


def click_candidate(cdp, pred_js):
    raw = cdp.eval(r"""(function(){
      var rows=document.querySelectorAll('#gw-table .tbl-row');
      for(var i=0;i<rows.length;i++){
        var r={id:rows[i].dataset.id||'',
               t:(rows[i].textContent||'').replace(/\s+/g,' ').trim().slice(0,50),
               conflict:rows[i].className.indexOf('tbl-conflict')>=0};
        if(%s){ rows[i].click();
          return JSON.stringify({id:r.id,t:r.t});}}
      return null;})()""" % pred_js)
    return json.loads(raw) if raw and raw != "null" else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9671)
    args = ap.parse_args()

    os.makedirs(OUT, exist_ok=True)
    prof = os.path.join(os.environ.get("TEMP", "."), "r1927acc_%d" % args.port)
    proc, ws = launch(find_chrome(), args.port, 1920, 919, prof)
    cdp = CDP(ws)
    try:
        for m in ("Page.enable", "Runtime.enable", "Log.enable", "Network.enable"):
            cdp.call(m)
        cdp.call("Network.setCacheDisabled", cacheDisabled=True)
        cdp.call("Emulation.setDeviceMetricsOverride", width=1920, height=919,
                 deviceScaleFactor=1, mobile=False)
        def open_main():
            cdp.call("Page.navigate", url=BASE + "/index.html")
            wait_ready(cdp, want_url="index.html")
            time.sleep(2.5)
            cdp.eval("(document.querySelector('[data-view=\"gun\"]')||{click:function(){}}).click()")
            time.sleep(1.2)

        open_main()

        rep = {"A1": [], "A2": [], "consistency": {}, "reload": {}}
        fails = []

        def fail(msg):
            fails.append(msg)

        # ============================================================ A1
        for key, gid, name in A1_GUNS:
            if not pick_gun(cdp, name, gid):
                fail("A1 %s 选枪失败" % name)
                continue
            time.sleep(1.0)
            s = canvas_snap(cdp)
            rear = [c for c in s["cards"] if "sight_rear" in c["slot"]]
            main = [c for c in rear if c["slot"] == "mod_sight_rear"]
            ok_row = bool(main) and main[0]["row"] == 2 and main[0]["col"] == 6
            if not ok_row:
                fail("A1 %s 照门不在 r2c6：%s" % (name, main))
            if len(rear) != 1:
                fail("A1 %s 照门槽数量=%d %s" % (name, len(rear), [c["slot"] for c in rear]))
            rep["A1"].append({"gun": name, "cards": len(s["cards"]),
                              "rear": [{"slot": c["slot"], "row": c["row"], "col": c["col"]} for c in rear],
                              "calibApplied": s.get("applied"), "at_r2c6": ok_row})
            shot(cdp, "A1-%s.png" % key)

        # ============================================================ A2
        for key, gid, name in A2_GUNS:
            if not pick_gun(cdp, name, gid):
                fail("A2 %s 选枪失败" % name)
                continue
            time.sleep(1.0)
            s0 = canvas_snap(cdp)
            rear0 = [c for c in s0["cards"] if "sight_rear" in c["slot"]]
            if len(rear0) != 1:
                fail("A2 %s 默认照门槽数量=%d %s" % (name, len(rear0), [c["slot"] for c in rear0]))
            # 打开候选列表，检查 AKMP RS 在唯一照门槽的候选里
            cdp.eval("""(function(){var c=document.querySelector('.gw-part[data-slot="mod_sight_rear"]');
              if(c)c.click();})()""")
            time.sleep(0.9)
            has_akmp = cdp.eval(r"""(function(){
              var rows=document.querySelectorAll('#gw-table .tbl-row');
              for(var i=0;i<rows.length;i++){
                if((rows[i].textContent||'').indexOf('AKMP')>=0 &&
                   (rows[i].textContent||'').indexOf('照门')>=0) return true;}
              return false;})()""")
            if not has_akmp:
                fail("A2 %s 候选列表无 AKMP 系统照门装置" % name)
            # 装上 AKMP RS
            clicked = click_candidate(
                cdp,
                "((r.t.indexOf('AKMP')>=0 && r.t.indexOf('照门')>=0) && !r.conflict)")
            time.sleep(1.6)
            s1 = canvas_snap(cdp)
            rear1 = [c for c in s1["cards"] if "sight_rear" in c["slot"]]
            installed_akmp = bool(rear1 and rear1[0].get("item"))
            if len(rear1) != 1 or not installed_akmp:
                fail("A2 %s 装 AKMP 后槽数=%d installed=%s" % (name, len(rear1), installed_akmp))
            # 卸下
            cdp.eval("""(function(){var c=document.querySelector('.gw-part[data-slot="mod_sight_rear"]');
              if(c)c.click();})()""")
            time.sleep(0.9)
            cdp.eval("""(function(){var r=document.querySelector('#gw-table .tbl-row[aria-selected="true"]');
              if(r)r.click();})()""")
            time.sleep(1.6)
            s2 = canvas_snap(cdp)
            rear2 = [c for c in s2["cards"] if "sight_rear" in c["slot"]]
            emptied = bool(rear2 and not rear2[0].get("item"))
            if len(rear2) != 1 or not emptied:
                fail("A2 %s 卸下后槽数=%d emptied=%s" % (name, len(rear2), emptied))
            rep["A2"].append({"gun": name, "defaultSlots": len(rear0),
                              "akmpInCandidates": bool(has_akmp),
                              "clicked": clicked,
                              "afterInstallSlots": len(rear1), "installedAkmp": installed_akmp,
                              "afterRemoveSlots": len(rear2), "emptied": emptied})
            shot(cdp, "A2-%s.png" % key)

        # ============================================================ 刷新持久
        open_main()
        if pick_gun(cdp, "AK-74N", "5644bd2b4bdc2d3b4c8b4572"):
            time.sleep(1.0)
            s = canvas_snap(cdp)
            main = [c for c in s["cards"] if c["slot"] == "mod_sight_rear"]
            ok = bool(main) and main[0]["row"] == 2 and main[0]["col"] == 6
            rep["reload"]["ak74n_r2c6"] = ok
            if not ok:
                fail("刷新后 AK-74N 照门不在 r2c6：%s" % main)
            shot(cdp, "reload-ak74n.png")

        # ============================================================ 校准器一致性
        cdp.call("Page.navigate", url=BASE + "/index.html?layoutCalibrator=1")
        wait_ready(cdp, want_url="layoutCalibrator=1")
        time.sleep(3.5)
        # 在校准器里选中 AK-74N（搜索 → 点 li[data-gun]）
        cdp.eval("""(function(){
          var s=document.getElementById('cal-search');
          if(s){ s.value='AK-74N'; s.dispatchEvent(new Event('input',{bubbles:true})); }})()""")
        time.sleep(0.8)
        cdp.eval("""(function(){
          var li=document.querySelector('li[data-gun="5644bd2b4bdc2d3b4c8b4572"]');
          if(li) li.click();})()""")
        time.sleep(1.8)
        raw = cdp.eval("""(function(){
          var cs=document.querySelectorAll('#cal-grid .cal-card');
          for(var i=0;i<cs.length;i++){
            if((cs[i].getAttribute('data-slot')||'')==='mod_sight_rear'){
              return JSON.stringify({row:+cs[i].getAttribute('data-row'),col:+cs[i].getAttribute('data-col'),
                                     gun:(document.getElementById('cal-title')||{textContent:''}).textContent});}}
          return null;})()""")
        calib_card = json.loads(raw) if raw and raw != "null" else None
        rep["consistency"]["calibrator_mod_sight_rear"] = calib_card
        if not (calib_card and calib_card["row"] == 2 and calib_card["col"] == 6):
            fail("校准器 AK-74N 照门坐标与主画布不一致：%s" % calib_card)
        shot(cdp, "calibrator-ak74n.png")

        rep["failed"] = fails
        rep["pass"] = not fails
        os.makedirs(OUT, exist_ok=True)
        with open(os.path.join(OUT, "browser-accept.json"), "w", encoding="utf-8", newline="") as f:
            json.dump(rep, f, ensure_ascii=False, indent=1)
        print(json.dumps({"pass": rep["pass"], "failed": fails}, ensure_ascii=False))
        return 0 if rep["pass"] else 1
    finally:
        try:
            proc.terminate()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
