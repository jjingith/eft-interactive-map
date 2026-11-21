# -*- coding: utf-8 -*-
"""R19.18 校准器行数探针：选枪 → 报告校准器网格行数 / 各行卡片是否可见可点。"""
from __future__ import annotations
import json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r181_accept import CDP, find_chrome, launch, wait_ready

BASE = "http://127.0.0.1:8787"
NEEDLE = sys.argv[1] if len(sys.argv) > 1 else "G28"


def cal_pick_gun(cdp, needle):
    cdp.eval("""(function(){var s=document.getElementById('cal-search');
      if(!s) return false; s.value=%s;
      s.dispatchEvent(new Event('input',{bubbles:true})); return true;})()"""
             % json.dumps(needle, ensure_ascii=False))
    time.sleep(0.6)
    raw = cdp.eval("""(function(){var li=document.querySelector('#cal-gunlist li[data-gun]');
      if(!li) return null; li.click(); return li.getAttribute('data-gun');})()""")
    time.sleep(0.6)
    cdp.eval("""(function(){var b=document.querySelector('#cal-modal button[data-choice="drop"]') ||
      document.querySelector('#cal-modal button[data-choice="go"]'); if(b){b.click();} })()""")
    time.sleep(1.2)
    return raw


def main():
    port = 9657
    prof = os.path.join(os.environ.get("TEMP", "."), "r1926cal_%d" % port)
    proc, ws = launch(find_chrome(), port, 1600, 900, prof)
    try:
        cdp = CDP(ws)
        for m in ("Page.enable", "Runtime.enable", "Log.enable"):
            cdp.call(m)
        cdp.call("Emulation.setDeviceMetricsOverride", width=1600, height=900, deviceScaleFactor=1, mobile=False)
        cdp.call("Page.navigate", url=BASE + "/index.html?layoutCalibrator=1")
        wait_ready(cdp, want_url="index.html")
        time.sleep(3.0)
        gid = cal_pick_gun(cdp, NEEDLE)
        time.sleep(1.0)
        info = cdp.eval(r"""(function(){
          var g=document.getElementById('cal-grid'), w=document.getElementById('cal-canvas-wrap');
          var cs=getComputedStyle(g);
          var cards=[].slice.call(g.querySelectorAll('.cal-card'));
          var rows={};
          cards.forEach(function(c){var r=+c.getAttribute('data-row'); rows[r]=(rows[r]||0)+1;});
          var r7=cards.filter(function(c){return +c.getAttribute('data-row')>=7;}).map(function(c){
            var b=c.getBoundingClientRect();
            return {slot:c.getAttribute('data-slot'),row:+c.getAttribute('data-row'),col:+c.getAttribute('data-col'),
                    y:Math.round(b.y),h:Math.round(b.height),inView:(b.y>=w.getBoundingClientRect().top && b.bottom<=w.getBoundingClientRect().bottom),
                    clickable: (function(){var e=c; while(e && e!==document.body){ if(getComputedStyle(e).pointerEvents==='none') return false; e=e.parentElement;} return true;})()};
          });
          return JSON.stringify({
            gun: (document.getElementById('cal-msg')||{textContent:''}).textContent.slice(0,80),
            gridRows: cs.gridTemplateRows.split(' ').length,
            gridTemplate: cs.gridTemplateRows,
            wrapClient: w.clientHeight, wrapScroll: w.scrollHeight,
            cardRows: rows, cards: cards.length, row7plus: r7,
            diff: (document.getElementById('cal-diff')||{textContent:''}).textContent.replace(/\s+/g,' ').slice(0,160)
          });})()""")
        print(json.dumps(json.loads(info or "{}"), ensure_ascii=False, indent=1))

        # 拖动第 7 行卡片（真实指针事件），验证可编辑
        drag = cdp.eval(r"""(function(){
          var g=document.getElementById('cal-grid');
          function cardOf(row,col){
            var cs=g.querySelectorAll('.cal-card');
            for(var i=0;i<cs.length;i++){ if(+cs[i].getAttribute('data-row')===row && +cs[i].getAttribute('data-col')===col) return cs[i]; }
            return null;
          }
          function cellCenter(row,col){
            var c=g.querySelector('.cal-gcell[data-row="'+row+'"][data-col="'+col+'"]');
            if(!c) return null; var b=c.getBoundingClientRect(); return {x:b.x+b.width/2,y:b.y+b.height/2};
          }
          var src=cardOf(7,1), dst=cellCenter(6,1);
          if(!src||!dst) return JSON.stringify({ok:false,why:'no src/dst'});
          var b=src.getBoundingClientRect();
          var sx=b.x+b.width/2, sy=b.y+b.height/2;
          function ev(type,x,y,btn){ src.dispatchEvent(new PointerEvent(type,{bubbles:true,clientX:x,clientY:y,button:btn||0,buttons:btn?1:0,pointerId:1})); }
          ev('pointerdown',sx,sy,1);
          for(var i=1;i<=6;i++){ ev('pointermove', sx+(dst.x-sx)*i/6, sy+(dst.y-sy)*i/6, 1); }
          ev('pointerup', dst.x, dst.y, 1);
          return JSON.stringify({ok:true, srcSlot:src.getAttribute('data-slot'), dst:{x:Math.round(dst.x),y:Math.round(dst.y)}});
        })()""")
        time.sleep(1.0)
        after = cdp.eval(r"""(function(){
          var g=document.getElementById('cal-grid');
          var cs=[].slice.call(g.querySelectorAll('.cal-card'));
          var c=cs.filter(function(x){return (x.getAttribute('data-slot')||'').indexOf('mod_tactical_000')>=0;})[0];
          return JSON.stringify({row:c&&c.getAttribute('data-row'), col:c&&c.getAttribute('data-col'),
            diff:(document.getElementById('cal-diff')||{textContent:''}).textContent.replace(/\s+/g,' ').slice(0,120)});})()""")
        print("drag:", drag)
        print("after:", after)

    finally:
        try:
            cdp.call("Browser.close")
        except Exception:
            pass
        if proc:
            proc.terminate()


if __name__ == "__main__":
    main()
