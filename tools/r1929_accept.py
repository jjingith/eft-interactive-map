# -*- coding: utf-8 -*-
"""R19.21 真实浏览器验收：AKMP 父件正上方布局 + 条件生成 + 校准器 + 回归。

用法：python tools/r1929_accept.py --port 9691
产物：docs/r19.21-akmp-parent-fix/browser-accept.json + screenshots/
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
OUT = os.path.join(ROOT, "docs", "r19.21-akmp-parent-fix")
BASE = "http://127.0.0.1:8787"

CASE_GUNS = [
    ("ak74n", "5644bd2b4bdc2d3b4c8b4572", "AK-74N"),
    ("ak74", "5bf3e03b0db834001d2c4a9c", "AK-74"),
    ("ak105", "5ac66d9b5acfc4001633997a", "AK-105"),
    ("ak74m", "5ac4cd105acfc40016339859", "AK-74M"),
    ("ak103", "5ac66d2e5acfc43b321d4b53", "AK-103"),
    ("ak104", "5ac66d725acfc43b321d4b60", "AK-104"),
    ("ak101", "5ac66cb05acfc40198510a10", "AK-101"),
    ("ak102", "5ac66d015acfc400180ae6e4", "AK-102"),
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
    ap.add_argument("--port", type=int, default=9691)
    args = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)

    prof = os.path.join(os.environ.get("TEMP", "."), "r1929acc_%d" % args.port)
    proc, ws = launch(find_chrome(), args.port, 1920, 919, prof)
    cdp = CDP(ws)
    rep = {"C": [], "B": {}, "D": {}, "F": {}, "failures": []}

    def fail(msg):
        rep["failures"].append(msg)

    try:
        for m in ("Page.enable", "Runtime.enable", "Log.enable", "Network.enable"):
            cdp.call(m)
        cdp.call("Network.setCacheDisabled", cacheDisabled=True)
        cdp.call("Emulation.setDeviceMetricsOverride", width=1920, height=919,
                 deviceScaleFactor=1, mobile=False)

        # ============================================================ C：布局
        open_main(cdp)
        for key, gid, name in CASE_GUNS:
            if not pick_gun(cdp, name, gid):
                fail("C %s 选枪失败" % name)
                continue
            time.sleep(1.0)
            s = canvas_snap(cdp)
            sight = [c for c in s["cards"] if c["slot"] == "mod_sight_rear"]
            sub = [c for c in s["cards"] if c["slot"] == "mod_sight_rear/mod_sight_rear"]
            ok_pair = bool(sight and sub) and sub[0]["col"] == sight[0]["col"] \
                and sub[0]["row"] == sight[0]["row"] - 1
            if not ok_pair:
                fail("C %s 子槽未在父件正上方同列 sight=%s sub=%s" % (name, sight, sub))
            if not (sight and sub):
                fail("C %s 照门/子槽缺失" % name)
            rep["C"].append({"gun": name, "sight": sight and sight[0], "sub": sub and sub[0],
                             "aboveSameCol": ok_pair, "topPad": s.get("topPad")})
            shot(cdp, "C-%s.png" % key)
        # AK-103 topPad 案例
        r103 = [r for r in rep["C"] if r["gun"] == "AK-103"]
        if r103 and not (r103[0]["sight"]["row"] == 2 and r103[0]["sub"]["row"] == 1):
            # 显示行 = 逻辑行 + topPad(1)：sight 逻辑 1→显示 2，sub 逻辑 0→显示 1
            fail("C AK-103 顶部扩展显示行异常：%s" % r103[0])

        # ============================================================ B：条件生成（AK-74N）
        if pick_gun(cdp, "AK-74N", "5644bd2b4bdc2d3b4c8b4572"):
            time.sleep(1.0)
            # 卸下照门 → 子槽消失
            cdp.eval("""(function(){var c=document.querySelector('.gw-part[data-slot="mod_sight_rear"]');
              if(c)c.click();})()""")
            time.sleep(0.8)
            cdp.eval("""(function(){var r=document.querySelector('#gw-table .tbl-row[aria-selected="true"]');
              if(r)r.click();})()""")
            time.sleep(1.6)
            s0 = canvas_snap(cdp)
            gone0 = not [c for c in s0["cards"] if c["slot"] == "mod_sight_rear/mod_sight_rear"]
            if not gone0:
                fail("B 卸下照门后 AKMP 子槽残留")
            # 装 AKM 照门（不支持）→ 仍无子槽
            cdp.eval("""(function(){var c=document.querySelector('.gw-part[data-slot="mod_sight_rear"]');
              if(c)c.click();})()""")
            time.sleep(0.8)
            click_candidate(cdp, "(r.t.indexOf('AKM 照门')>=0 && !r.conflict)")
            time.sleep(1.6)
            s1 = canvas_snap(cdp)
            gone1 = not [c for c in s1["cards"] if c["slot"] == "mod_sight_rear/mod_sight_rear"]
            if not gone1:
                fail("B 装 AKM 照门后不应出现 AKMP 子槽")
            # 换装 AK-74 照门 → 子槽出现于正上方
            cdp.eval("""(function(){var c=document.querySelector('.gw-part[data-slot="mod_sight_rear"]');
              if(c)c.click();})()""")
            time.sleep(0.8)
            click_candidate(cdp, "(r.t.indexOf('AK-74 照门')>=0 && !r.conflict)")
            time.sleep(1.6)
            s2 = canvas_snap(cdp)
            sight2 = [c for c in s2["cards"] if c["slot"] == "mod_sight_rear"]
            sub2 = [c for c in s2["cards"] if c["slot"] == "mod_sight_rear/mod_sight_rear"]
            ok2 = bool(sight2 and sub2) and sub2[0]["row"] == sight2[0]["row"] - 1 \
                and sub2[0]["col"] == sight2[0]["col"]
            if not ok2:
                fail("B 换装 AK-74 照门后子槽未现/未对齐：%s %s" % (sight2, sub2))
            # 装 AKMP 到子槽
            cdp.eval("""(function(){var c=document.querySelector('.gw-part[data-slot="mod_sight_rear/mod_sight_rear"]');
              if(c)c.click();})()""")
            time.sleep(0.8)
            click_candidate(cdp, "(r.t.indexOf('AKMP')>=0 && r.t.indexOf('照门')>=0 && !r.conflict)")
            time.sleep(1.6)
            s3 = canvas_snap(cdp)
            sub3 = [c for c in s3["cards"] if c["slot"] == "mod_sight_rear/mod_sight_rear"]
            installed = bool(sub3 and sub3[0].get("item"))
            if not installed:
                fail("B AKMP 未装入子槽")
            # 卸下 AKMP → 子槽清空但仍在
            cdp.eval("""(function(){var c=document.querySelector('.gw-part[data-slot="mod_sight_rear/mod_sight_rear"]');
              if(c)c.click();})()""")
            time.sleep(0.8)
            cdp.eval("""(function(){var r=document.querySelector('#gw-table .tbl-row[aria-selected="true"]');
              if(r)r.click();})()""")
            time.sleep(1.6)
            s4 = canvas_snap(cdp)
            sub4 = [c for c in s4["cards"] if c["slot"] == "mod_sight_rear/mod_sight_rear"]
            rep["B"] = {"goneAfterSightRemove": gone0, "goneWithAkmSight": gone1,
                        "backOnSwap": ok2, "akmpInstalled": installed,
                        "subKeptAfterAkmpRemove": bool(sub4)}
            if not sub4:
                fail("B 卸 AKMP 后子槽应保留（父件仍在）")
            shot(cdp, "B-conditional.png")

        # ============================================================ D：校准器
        cdp.call("Page.navigate", url=BASE + "/index.html?layoutCalibrator=1")
        wait_ready(cdp, want_url="layoutCalibrator=1")
        time.sleep(3.5)
        cdp.eval("""(function(){
          var s=document.getElementById('cal-search');
          if(s){ s.value='AK-74N'; s.dispatchEvent(new Event('input',{bubbles:true})); }})()""")
        time.sleep(0.8)
        cdp.eval("""(function(){
          var li=document.querySelector('li[data-gun="5644bd2b4bdc2d3b4c8b4572"]');
          if(li) li.click();})()""")
        time.sleep(1.8)
        raw = cdp.eval(r"""(function(){
          var g=document.getElementById('cal-grid');
          function info(slot){
            var cs=g.querySelectorAll('.cal-card');
            for(var i=0;i<cs.length;i++){
              if(cs[i].getAttribute('data-slot')===slot)
                return {row:+cs[i].getAttribute('data-row'),col:+cs[i].getAttribute('data-col')};}
            return null;
          }
          return JSON.stringify({sight:info('mod_sight_rear'),sub:info('mod_sight_rear/mod_sight_rear')});})()""")
        cal0 = json.loads(raw) if raw else {}
        pair_ok = bool(cal0.get("sight") and cal0.get("sub")) and \
            cal0["sub"]["row"] == cal0["sight"]["row"] - 1 and cal0["sub"]["col"] == cal0["sight"]["col"]
        rep["D"]["initial"] = cal0
        rep["D"]["parallelAbove"] = pair_ok
        if not pair_ok:
            fail("D 校准器初始位置非正上方同列：%s" % cal0)
        # 拖动子槽（独立移动，不动父照门）
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
          return JSON.stringify({sight:info('mod_sight_rear'),sub:info('mod_sight_rear/mod_sight_rear')});})()""")
        cal1 = json.loads(raw2) if raw2 else {}
        moved = bool(cal1.get("sub")) and cal1["sub"] != cal0.get("sub")
        sight_untouched = cal1.get("sight") == cal0.get("sight")
        rep["D"]["afterDrag"] = cal1
        rep["D"]["subMovedIndependently"] = moved
        rep["D"]["sightUntouched"] = sight_untouched
        if not moved:
            fail("D 子槽拖不动")
        if not sight_untouched:
            fail("D 拖子槽时父照门被联动")
        # 保存 → 刷新 → 身份与位置保持
        cdp.eval("(document.getElementById('cal-save')||{click:function(){}}).click()")
        time.sleep(1.5)
        cdp.call("Page.navigate", url=BASE + "/index.html?layoutCalibrator=1")
        wait_ready(cdp, want_url="layoutCalibrator=1")
        time.sleep(3.5)
        cdp.eval("""(function(){
          var s=document.getElementById('cal-search');
          if(s){ s.value='AK-74N'; s.dispatchEvent(new Event('input',{bubbles:true})); }})()""")
        time.sleep(0.8)
        cdp.eval("""(function(){
          var li=document.querySelector('li[data-gun="5644bd2b4bdc2d3b4c8b4572"]');
          if(li) li.click();})()""")
        time.sleep(1.8)
        raw3 = cdp.eval(r"""(function(){
          var g=document.getElementById('cal-grid');
          function info(slot){
            var cs=g.querySelectorAll('.cal-card');
            for(var i=0;i<cs.length;i++){
              if(cs[i].getAttribute('data-slot')===slot)
                return {row:+cs[i].getAttribute('data-row'),col:+cs[i].getAttribute('data-col')};}
            return null;
          }
          return JSON.stringify({sight:info('mod_sight_rear'),sub:info('mod_sight_rear/mod_sight_rear')});})()""")
        cal2 = json.loads(raw3) if raw3 else {}
        rep["D"]["afterReload"] = cal2
        persisted = cal2.get("sub") == cal1.get("sub")
        rep["D"]["persistedAfterReload"] = persisted
        if not persisted:
            fail("D 保存刷新后子槽位置未保持：%s %s" % (cal2.get("sub"), cal1.get("sub")))
        shot(cdp, "D-calibrator.png")
        # 主画布一致性：回主程序看 AK-74N（应显示校准器保存的 r1c8）
        open_main(cdp)
        if pick_gun(cdp, "AK-74N", "5644bd2b4bdc2d3b4c8b4572"):
            time.sleep(1.0)
            s = canvas_snap(cdp)
            sub = [c for c in s["cards"] if c["slot"] == "mod_sight_rear/mod_sight_rear"]
            consistent = bool(sub) and sub[0]["col"] == 8 and sub[0]["row"] == 1
            rep["D"]["mainCanvasMatches"] = consistent
            if not consistent:
                fail("D 主画布与校准器保存结果不一致：%s" % sub)
        # 还原：把子槽拖回 r1c6 并保存（不给用户数据留下测试痕迹）
        cdp.call("Page.navigate", url=BASE + "/index.html?layoutCalibrator=1")
        wait_ready(cdp, want_url="layoutCalibrator=1")
        time.sleep(3.5)
        cdp.eval("""(function(){
          var s=document.getElementById('cal-search');
          if(s){ s.value='AK-74N'; s.dispatchEvent(new Event('input',{bubbles:true})); }})()""")
        time.sleep(0.8)
        cdp.eval("""(function(){
          var li=document.querySelector('li[data-gun="5644bd2b4bdc2d3b4c8b4572"]');
          if(li) li.click();})()""")
        time.sleep(1.8)
        cdp.eval(r"""(function(){
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
          var src=cardOf('mod_sight_rear/mod_sight_rear'), dst=cellCenter(1,6);
          if(!src||!dst) return;
          var b=src.getBoundingClientRect();
          var sx=b.x+b.width/2, sy=b.y+b.height/2;
          function ev(type,x,y,btn){ src.dispatchEvent(new PointerEvent(type,{bubbles:true,clientX:x,clientY:y,button:btn||0,buttons:btn?1:0,pointerId:1})); }
          ev('pointerdown',sx,sy,1);
          for(var i=1;i<=6;i++){ ev('pointermove', sx+(dst.x-sx)*i/6, sy+(dst.y-sy)*i/6, 1); }
          ev('pointerup', dst.x, dst.y, 1);})()""")
        time.sleep(1.0)
        cdp.eval("(document.getElementById('cal-save')||{click:function(){}}).click()")
        time.sleep(1.5)
        raw4 = cdp.eval(r"""(function(){
          var g=document.getElementById('cal-grid');
          var cs=g.querySelectorAll('.cal-card');
          for(var i=0;i<cs.length;i++){
            if(cs[i].getAttribute('data-slot')==='mod_sight_rear/mod_sight_rear')
              return JSON.stringify({row:+cs[i].getAttribute('data-row'),col:+cs[i].getAttribute('data-col')});}
          return null;})()""")
        restored = json.loads(raw4) if raw4 and raw4 != "null" else None
        rep["D"]["restoredToR1C6"] = bool(restored and restored["row"] == 1 and restored["col"] == 6)
        if not rep["D"]["restoredToR1C6"]:
            fail("D 测试坐标未还原到 r1c6：%s" % restored)

        # ============================================================ F：回归
        open_main(cdp)
        if pick_gun(cdp, "AKM 7.62x39", "59d6088586f774275f37482f"):
            time.sleep(1.0)
            s = canvas_snap(cdp)
            rear = [c for c in s["cards"] if "sight_rear" in c["slot"]]
            rep["F"]["akmSingleSight"] = len(rear) == 1
            if len(rear) != 1:
                fail("F AKM 照门槽数=%d" % len(rear))
        else:
            fail("F AKM 选枪失败")
        if pick_gun(cdp, "VPO-209", "59e6687d86f77411d949b251"):
            time.sleep(1.0)
            s = canvas_snap(cdp)
            sight = [c for c in s["cards"] if c["slot"] == "mod_sight_rear"]
            sub = [c for c in s["cards"] if c["slot"] == "mod_sight_rear/mod_sight_rear"]
            unchanged = bool(sight and sub) and sight[0]["row"] == 1 and sub[0]["row"] == 2
            rep["F"]["vpo209Unchanged"] = unchanged
            if not unchanged:
                fail("F VPO-209 现状被改动")
            shot(cdp, "F-vpo209.png")
        else:
            fail("F VPO-209 选枪失败")

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
