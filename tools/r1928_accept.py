# -*- coding: utf-8 -*-
"""R19.20 真实浏览器验收：AKM 照门 / AKMP 并列双照门位。

用法：python tools/r1928_accept.py --port 9681
产物：docs/r19.20-akm-akmp-parallel/browser-accept.json + screenshots/

场景（任务五）：默认左右双槽 / 槽数 / 候选分离 / 装卸互不占位 / 刷新 /
校准器独立拖动保存 / R19.19 回归（5.45 照门、SVDS、VPO-209 现状保留）。
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
OUT = os.path.join(ROOT, "docs", "r19.20-akm-akmp-parallel")
BASE = "http://127.0.0.1:8787"

GUNS = [
    ("akm", "59d6088586f774275f37482f", "AKM 7.62x39"),
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


def open_main(cdp):
    cdp.call("Page.navigate", url=BASE + "/index.html")
    wait_ready(cdp, want_url="index.html")
    time.sleep(2.5)
    cdp.eval("(document.querySelector('[data-view=\"gun\"]')||{click:function(){}}).click()")
    time.sleep(1.2)


def canvas_snap(cdp):
    raw = cdp.eval(r"""(function(){
      var t=document.getElementById('gw-tree');
      if(!t) return JSON.stringify({ok:false});
      var cards=[].slice.call(t.querySelectorAll('.gw-part')).filter(function(c){return c.dataset.slot;});
      return JSON.stringify({
        ok:true, topPad:+(t.getAttribute('data-top-pad')||0),
        cards:cards.map(function(c){
          return {slot:c.dataset.slot,row:+c.dataset.row,col:+c.dataset.col,
                  item:c.getAttribute('data-item')||''};
        }),
        gun:(document.getElementById('gw-current')||{textContent:''}).textContent.trim()
      });})()""")
    return json.loads(raw) if raw else {"ok": False}


def slot_candidates(cdp, slot):
    raw = cdp.eval("""(function(){
      var c=document.querySelector('.gw-part[data-slot=%s]');
      if(c) c.click();})()""" % json.dumps(slot))
    time.sleep(0.9)
    raw = cdp.eval(r"""(function(){
      var rows=document.querySelectorAll('#gw-table .tbl-row');
      var out=[];
      for(var i=0;i<rows.length;i++){
        out.push({t:(rows[i].textContent||'').replace(/\s+/g,' ').trim().slice(0,40),
                  conflict:rows[i].className.indexOf('tbl-conflict')>=0,
                  selected:rows[i].getAttribute('aria-selected')==='true'});}
      return JSON.stringify(out);})()""")
    return json.loads(raw) if raw else []


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
    ap.add_argument("--port", type=int, default=9681)
    args = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)

    prof = os.path.join(os.environ.get("TEMP", "."), "r1928acc_%d" % args.port)
    proc, ws = launch(find_chrome(), args.port, 1920, 919, prof)
    cdp = CDP(ws)
    rep = {"pairs": [], "candidates": [], "install": [], "calibrator": {},
           "regression": {}, "reload": {}, "failures": []}

    def fail(msg):
        rep["failures"].append(msg)

    try:
        for m in ("Page.enable", "Runtime.enable", "Log.enable", "Network.enable"):
            cdp.call(m)
        cdp.call("Network.setCacheDisabled", cacheDisabled=True)
        cdp.call("Emulation.setDeviceMetricsOverride", width=1920, height=919,
                 deviceScaleFactor=1, mobile=False)

        # ============================================================ 1/2 默认并列双槽
        open_main(cdp)
        for key, gid, name in GUNS:
            if not pick_gun(cdp, name, gid):
                fail("选枪失败 %s" % name)
                continue
            time.sleep(1.0)
            s = canvas_snap(cdp)
            sight = [c for c in s["cards"] if c["slot"] == "mod_sight_rear"]
            akmp = [c for c in s["cards"] if c["slot"] == "mod_sight_rear/mod_sight_rear"]
            other = [c for c in s["cards"] if "sight_rear" in c["slot"]
                     and c["slot"] not in ("mod_sight_rear", "mod_sight_rear/mod_sight_rear")]
            pair_ok = bool(sight and akmp) and akmp[0]["row"] == sight[0]["row"] and \
                akmp[0]["col"] == sight[0]["col"] + 1
            not_below = bool(sight and akmp) and not (
                akmp[0]["col"] == sight[0]["col"] and akmp[0]["row"] == sight[0]["row"] + 1)
            if not pair_ok:
                fail("%s 未并列（左 r%sc%s / 右 %s）" % (
                    name, sight and sight[0]["row"], sight and sight[0]["col"], akmp))
            if not not_below:
                fail("%s AKMP 在照门正下方" % name)
            if len(sight) != 1 or len(akmp) != 1 or other:
                fail("%s 照门槽数异常 sight=%d akmp=%d other=%s" % (
                    name, len(sight), len(akmp), [c["slot"] for c in other]))
            rep["pairs"].append({
                "gun": name, "sight": sight and sight[0], "akmp": akmp and akmp[0],
                "parallel": pair_ok, "notBelow": not_below,
                "slotCount": len(sight) + len(akmp) + len(other),
            })
            shot(cdp, "pair-%s.png" % key)

        # ============================================================ 3 候选分离
        if pick_gun(cdp, "AKM 7.62x39", "59d6088586f774275f37482f"):
            time.sleep(1.0)
            left = slot_candidates(cdp, "mod_sight_rear")
            left_names = [c["t"] for c in left]
            right = slot_candidates(cdp, "mod_sight_rear/mod_sight_rear")
            right_names = [c["t"] for c in right]
            left_has_akmp = any("AKMP" in t and "照门" in t for t in left_names)
            right_only_akmp = bool(right_names) and all("AKMP" in t for t in right_names)
            if left_has_akmp:
                fail("左槽候选混入 AKMP：%s" % left_names)
            if not right_only_akmp:
                fail("右槽候选异常：%s" % right_names)
            if not any("AKM 照门" in t for t in left_names):
                fail("左槽缺 AKM 照门候选：%s" % left_names)
            rep["candidates"].append({"left": left_names[:8], "right": right_names,
                                      "leftHasAkmp": left_has_akmp,
                                      "rightOnlyAkmp": right_only_akmp})
            shot(cdp, "candidates.png")

            # ============================================================ 4/5 安装 + 卸下
            before = canvas_snap(cdp)
            cdp.eval("""(function(){var c=document.querySelector('.gw-part[data-slot="mod_sight_rear/mod_sight_rear"]');
              if(c)c.click();})()""")
            time.sleep(0.8)
            clicked = click_candidate(cdp, "((r.t.indexOf('AKMP')>=0 && r.t.indexOf('照门')>=0) && !r.conflict)")
            time.sleep(1.8)
            s1 = canvas_snap(cdp)
            sight1 = [c for c in s1["cards"] if c["slot"] == "mod_sight_rear"]
            akmp1 = [c for c in s1["cards"] if c["slot"] == "mod_sight_rear/mod_sight_rear"]
            left_untouched = bool(sight1) and sight1[0].get("item") == \
                [c for c in before["cards"] if c["slot"] == "mod_sight_rear"][0].get("item")
            akmp_installed = bool(akmp1) and akmp1[0].get("item")
            pair1 = bool(sight1 and akmp1) and akmp1[0]["row"] == sight1[0]["row"] and \
                akmp1[0]["col"] == sight1[0]["col"] + 1
            if not akmp_installed:
                fail("AKMP 未装入右槽")
            if not left_untouched:
                fail("装 AKMP 后左槽被改动")
            if not pair1:
                fail("装 AKMP 后并列破坏")
            shot(cdp, "after-install.png")
            # 卸下
            cdp.eval("""(function(){var c=document.querySelector('.gw-part[data-slot="mod_sight_rear/mod_sight_rear"]');
              if(c)c.click();})()""")
            time.sleep(0.8)
            cdp.eval("""(function(){var r=document.querySelector('#gw-table .tbl-row[aria-selected="true"]');
              if(r)r.click();})()""")
            time.sleep(1.8)
            s2 = canvas_snap(cdp)
            sight2 = [c for c in s2["cards"] if c["slot"] == "mod_sight_rear"]
            akmp2 = [c for c in s2["cards"] if c["slot"] == "mod_sight_rear/mod_sight_rear"]
            emptied = bool(akmp2) and not akmp2[0].get("item")
            pair2 = bool(sight2 and akmp2) and akmp2[0]["row"] == sight2[0]["row"] and \
                akmp2[0]["col"] == sight2[0]["col"] + 1
            if not emptied:
                fail("卸下后右槽未清空")
            if not pair2:
                fail("卸下后并列破坏")
            if len(s2["cards"]) != len(before["cards"]):
                fail("卸下后卡片数未复原 %d→%d" % (len(before["cards"]), len(s2["cards"])))
            rep["install"].append({
                "clicked": clicked, "akmpInstalled": akmp_installed,
                "leftUntouched": left_untouched, "parallelAfterInstall": pair1,
                "emptied": emptied, "parallelAfterRemove": pair2,
                "cardsRestored": len(s2["cards"]) == len(before["cards"]),
            })
            shot(cdp, "after-remove.png")

        # ============================================================ 6 刷新
        open_main(cdp)
        if pick_gun(cdp, "AKM 7.62x39", "59d6088586f774275f37482f"):
            time.sleep(1.0)
            s = canvas_snap(cdp)
            sight = [c for c in s["cards"] if c["slot"] == "mod_sight_rear"]
            akmp = [c for c in s["cards"] if c["slot"] == "mod_sight_rear/mod_sight_rear"]
            ok = bool(sight and akmp) and akmp[0]["row"] == sight[0]["row"] and \
                akmp[0]["col"] == sight[0]["col"] + 1
            rep["reload"] = {"parallel": ok, "sight": sight and sight[0], "akmp": akmp and akmp[0]}
            if not ok:
                fail("刷新后并列失效")
            shot(cdp, "reload.png")

        # ============================================================ 7 校准器独立拖动
        cdp.call("Page.navigate", url=BASE + "/index.html?layoutCalibrator=1")
        wait_ready(cdp, want_url="layoutCalibrator=1")
        time.sleep(3.5)
        cdp.eval("""(function(){
          var s=document.getElementById('cal-search');
          if(s){ s.value='AKM 7.62x39'; s.dispatchEvent(new Event('input',{bubbles:true})); }})()""")
        time.sleep(0.8)
        cdp.eval("""(function(){
          var li=document.querySelector('li[data-gun="59d6088586f774275f37482f"]');
          if(li) li.click();})()""")
        time.sleep(1.8)
        raw = cdp.eval(r"""(function(){
          var g=document.getElementById('cal-grid');
          function cardOf(slot){
            var cs=g.querySelectorAll('.cal-card');
            for(var i=0;i<cs.length;i++){ if(cs[i].getAttribute('data-slot')===slot) return cs[i]; }
            return null;
          }
          function info(slot){
            var c=cardOf(slot);
            return c?{row:+c.getAttribute('data-row'),col:+c.getAttribute('data-col')}:null;
          }
          return JSON.stringify({sight:info('mod_sight_rear'),akmp:info('mod_sight_rear/mod_sight_rear')});})()""")
        calib0 = json.loads(raw) if raw else {}
        pair_ok = bool(calib0.get("sight") and calib0.get("akmp")) and \
            calib0["akmp"]["row"] == calib0["sight"]["row"] and \
            calib0["akmp"]["col"] == calib0["sight"]["col"] + 1
        rep["calibrator"]["initial"] = calib0
        rep["calibrator"]["parallel"] = pair_ok
        if not pair_ok:
            fail("校准器双卡未并列：%s" % calib0)
        # 独立拖动 AKMP 卡（r1c7 → r1c8）验证可动且互不联动
        drag = cdp.eval(r"""(function(){
          var g=document.getElementById('cal-grid');
          function cardOf(slot){
            var cs=g.querySelectorAll('.cal-card');
            for(var i=0;i<cs.length;i++){ if(cs[i].getAttribute('data-slot')===slot) return cs[i]; }
            return null;
          }
          function cellCenter(row,col){
            var c=g.querySelector('.cal-gcell[data-row="'+row+'"][data-col="'+col+'"]');
            if(!c) return null; var b=c.getBoundingClientRect();
            return {x:b.x+b.width/2,y:b.y+b.height/2};
          }
          var src=cardOf('mod_sight_rear/mod_sight_rear'), dst=cellCenter(1,8);
          if(!src||!dst) return JSON.stringify({ok:false});
          var b=src.getBoundingClientRect();
          var sx=b.x+b.width/2, sy=b.y+b.height/2;
          function ev(type,x,y,btn){ src.dispatchEvent(new PointerEvent(type,{bubbles:true,clientX:x,clientY:y,button:btn||0,buttons:btn?1:0,pointerId:1})); }
          ev('pointerdown',sx,sy,1);
          for(var i=1;i<=6;i++){ ev('pointermove', sx+(dst.x-sx)*i/6, sy+(dst.y-sy)*i/6, 1); }
          ev('pointerup', dst.x, dst.y, 1);
          return JSON.stringify({ok:true});})()""")
        time.sleep(1.0)
        raw2 = cdp.eval(r"""(function(){
          var g=document.getElementById('cal-grid');
          function info(slot){
            var cs=g.querySelectorAll('.cal-card');
            for(var i=0;i<cs.length;i++){
              if(cs[i].getAttribute('data-slot')===slot)
                return {row:+cs[i].getAttribute('data-row'),col:+cs[i].getAttribute('data-col')};}
            return null;
          }
          return JSON.stringify({sight:info('mod_sight_rear'),akmp:info('mod_sight_rear/mod_sight_rear')});})()""")
        calib1 = json.loads(raw2) if raw2 else {}
        moved = bool(calib1.get("akmp")) and calib1["akmp"] != calib0.get("akmp")
        sight_untouched = calib1.get("sight") == calib0.get("sight")
        rep["calibrator"]["afterDrag"] = calib1
        rep["calibrator"]["akmpMovedIndependently"] = moved
        rep["calibrator"]["sightUntouched"] = sight_untouched
        if not moved:
            fail("校准器 AKMP 卡拖不动")
        if not sight_untouched:
            fail("拖 AKMP 时照门卡被联动")
        shot(cdp, "calibrator-drag.png")
        # 撤销恢复
        cdp.eval("(document.getElementById('cal-undo')||{click:function(){}}).click()")
        time.sleep(0.8)
        raw3 = cdp.eval(r"""(function(){
          var g=document.getElementById('cal-grid');
          var cs=g.querySelectorAll('.cal-card');
          for(var i=0;i<cs.length;i++){
            if(cs[i].getAttribute('data-slot')==='mod_sight_rear/mod_sight_rear')
              return JSON.stringify({row:+cs[i].getAttribute('data-row'),col:+cs[i].getAttribute('data-col')});}
          return null;})()""")
        undone = json.loads(raw3) if raw3 and raw3 != "null" else None
        rep["calibrator"]["afterUndo"] = undone
        if not (undone and undone == calib0.get("akmp")):
            fail("撤销未还原 AKMP 卡")

        # ============================================================ 8 回归
        open_main(cdp)
        if pick_gun(cdp, "AK-74N", "5644bd2b4bdc2d3b4c8b4572"):
            time.sleep(1.0)
            s = canvas_snap(cdp)
            sight = [c for c in s["cards"] if c["slot"] == "mod_sight_rear"]
            mount = [c for c in s["cards"] if c["slot"] == "mod_mount_000"]
            ok = bool(sight) and sight[0]["row"] == 2 and sight[0]["col"] == 6 and len(sight) == 1
            rep["regression"]["ak74n"] = {"sight": sight and sight[0], "ok": ok,
                                          "mount": mount and mount[0]}
            if not ok:
                fail("AK-74N 照门回归（应 r2c6 单槽）")
        if pick_gun(cdp, "VPO-209", "59e6687d86f77411d949b251"):
            time.sleep(1.0)
            s = canvas_snap(cdp)
            sight = [c for c in s["cards"] if c["slot"] == "mod_sight_rear"]
            akmp = [c for c in s["cards"] if c["slot"] == "mod_sight_rear/mod_sight_rear"]
            unchanged = bool(sight and akmp) and sight[0]["row"] == 1 and akmp[0]["row"] == 2
            rep["regression"]["vpo209_unchanged"] = unchanged
            if not unchanged:
                fail("VPO-209 现状被改动")
            shot(cdp, "regression-vpo209.png")

        rep["pass"] = not rep["failures"]
        with open(os.path.join(OUT, "browser-accept.json"), "w", encoding="utf-8", newline="") as f:
            json.dump(rep, f, ensure_ascii=False, indent=1)
        print(json.dumps({"pass": rep["pass"], "failed": rep["failures"]}, ensure_ascii=False))
        return 0 if rep["pass"] else 1
    finally:
        try:
            proc.terminate()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
