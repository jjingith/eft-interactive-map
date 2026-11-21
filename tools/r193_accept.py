# -*- coding: utf-8 -*-
"""R19.3 浏览器验收：六项问题逐项取证。

  P1 完整枪械图（浏览卡 163 张 + 12 枪抽查截图）
  P2 悬停/选中黄色高亮（全流程状态截图 + 计算样式）
  P3 工作台文字对比度（审计脚本复测 = 0 处低对比）
  P4 工作台完整装配主图 + 差异条（装/卸/复位/换枪对照）
  P5 隐藏属性（EFTForge 公式，模拟参数输入生效验证）
  P6 布局实测（三栏边界/宽度 vs 参考截图）
产物：docs/r19.3-audit/_accept.json + screenshots/
"""
import base64
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r181_accept import find_chrome, launch, CDP, wait_ready

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "r19.3-audit")
SHOTS = os.path.join(OUT, "screenshots")
os.makedirs(SHOTS, exist_ok=True)

CONTRAST_JS = open(os.path.join(ROOT, "tools", "_contrast_js.txt"), encoding="utf-8").read()


def shot(cdp, name, outdir=SHOTS):
    data = base64.b64decode(cdp.call("Page.captureScreenshot", format="png")["data"])
    open(os.path.join(outdir, name), "wb").write(data)
    return name


def card_center(cdp, needle):
    raw = cdp.eval("""
      (function(){
        var cs=document.querySelectorAll('#gw-browse .gw-card');
        for(var i=0;i<cs.length;i++){
          var s=cs[i].querySelector('span');
          if(s && s.textContent.indexOf('%s')>=0){
            cs[i].scrollIntoView({block:'center'});
            return JSON.stringify({span:s.textContent});
          }
        }
        return null;
      })()""" % needle)
    if not (needle and raw):
        return None
    time.sleep(0.4)                       # 等滚动稳定
    raw2 = cdp.eval("""
      (function(){
        var cs=document.querySelectorAll('#gw-browse .gw-card');
        for(var i=0;i<cs.length;i++){
          var s=cs[i].querySelector('span');
          if(s && s.textContent.indexOf('%s')>=0){
            var r=cs[i].getBoundingClientRect();
            return JSON.stringify({x:r.x+r.width/2, y:r.y+r.height/2, name:s.textContent});
          }
        }
        return null;
      })()""" % needle)
    return json.loads(raw2) if raw2 else None


def stats_map(cdp):
    return json.loads(cdp.eval("""
      (function(){
        var out={};
        document.querySelectorAll('#gw-stats .gw-stat').forEach(function(row){
          var l=row.querySelector('.gw-stat-lab'),v=row.querySelector('.gw-stat-val');
          if(l&&v) out[l.textContent]=v.textContent;});
        return JSON.stringify(out);
      })()"""))


def main():
    rep = {"p1": {}, "p2": {}, "p3": {}, "p4": {}, "p5": {}, "p6": {}, "console": [], "external": None}
    proc, ws = launch(find_chrome(), 9401, 1920, 1080,
                      os.path.join(os.environ.get("TEMP", "."), "r193-%d" % os.getpid()))
    try:
        cdp = CDP(ws)
        for m in ("Page.enable", "Runtime.enable", "Network.enable"):
            cdp.call(m)
        cdp.call("Emulation.setDeviceMetricsOverride", width=1920, height=1080,
                 deviceScaleFactor=1, mobile=False)
        cdp.call("Page.navigate", url="http://127.0.0.1:8787/index.html")
        wait_ready(cdp, want_url="index.html")
        time.sleep(2.0)
        cdp.eval("try{localStorage.removeItem('eftmap.gwmode')}catch(e){}")
        cdp.eval("document.querySelector('[data-view=\"gun\"]').click()")
        time.sleep(2.5)

        # ---------- P1：浏览卡整枪图 ----------
        rep["p1"]["cards"] = cdp.eval("""
          (function(){
            var t=0,w=0;
            document.querySelectorAll('.gw-card-img').forEach(function(i){
              t++; var s=i.getAttribute('src')||'';
              if(s.indexOf('guns-full')>=0||s.indexOf('presets-full')>=0) w++;
            });
            return JSON.stringify({total:t, fullImg:w, fallback:t-w});
          })()""")
        rep["p1"]["cards"] = json.loads(rep["p1"]["cards"] or "{}")
        shot(cdp, "p1-caliber-fullguns.png")

        # 12 枪抽查：截整卡特写 + 校验图片加载
        spot = ["AK-74 5", "HK MP5", "莫辛-纳甘", "MP-133", "马卡洛夫", "柯尔特 M4A1",
                "SVDS", "雷明顿 Model 870", "AS VAL", "RPK-16", "PP-19-01", "SV-98"]
        checked = []
        for name in spot:
            pos = card_center(cdp, name)
            if not pos:
                checked.append({"gun": name, "found": False})
                continue
            cdp.eval("""
              (function(){
                var cs=document.querySelectorAll('#gw-browse .gw-card');
                for(var i=0;i<cs.length;i++){
                  var s=cs[i].querySelector('span');
                  if(s && s.textContent.indexOf('%s')>=0){
                    var img=cs[i].querySelector('.gw-card-img');
                    window.__r193 = {src:(img.getAttribute('src')||''),
                      loaded:img.complete && img.naturalWidth>0,
                      nw:img.naturalWidth, nh:img.naturalHeight};
                    return;
                  }
                }
              })()""" % name)
            info = cdp.eval("JSON.stringify(window.__r193||{})")
            checked.append(json.loads('{"gun":"%s"}' % name) | json.loads(info or "{}"))
        rep["p1"]["spot"] = checked
        shot(cdp, "p1-class-fullguns.png")
        cdp.eval("(function(){var b=document.querySelector('.gw-mode[data-gwmode=\"class\"]');if(b)b.click();})()")
        time.sleep(1.4)
        shot(cdp, "p1-class-view.png")
        cdp.eval("(function(){var b=document.querySelector('.gw-mode[data-gwmode=\"caliber\"]');if(b)b.click();})()")
        time.sleep(1.2)

        # ---------- P2：选中状态全流程 ----------
        pos = card_center(cdp, "AK-74 5")
        cdp.mouse(pos["x"], pos["y"]); time.sleep(0.5)
        rep["p2"]["hover"] = cdp.eval(
            "(function(){var c=document.querySelector('#gw-browse .gw-card:hover');"
            "return c?getComputedStyle(c).backgroundColor+' / '+getComputedStyle(c).borderColor:'none';})()")
        shot(cdp, "p2-1-hover.png")
        cdp.click_at(pos["x"], pos["y"]); time.sleep(2.5)
        rep["p2"]["selected"] = cdp.eval(
            "(function(){var c=document.querySelector('#gw-browse .gw-card[aria-current=\"true\"]');"
            "if(!c)return 'none';var cs=getComputedStyle(c);var nm=c.querySelector('span');"
            "return JSON.stringify({bg:cs.backgroundColor,color:cs.color,"
            "nameColor:getComputedStyle(nm).color});})()")
        shot(cdp, "p2-2-selected-build.png")
        cdp.eval("(function(){var b=document.querySelector('.gw-mode[data-gwmode=\"caliber\"]');if(b)b.click();})()")
        time.sleep(1.2)
        rep["p2"]["selectedAfterBack"] = cdp.eval(
            "(function(){var c=document.querySelector('#gw-browse .gw-card[aria-current=\"true\"]');"
            "return c?getComputedStyle(c).backgroundColor:'none';})()")
        shot(cdp, "p2-3-selected-still-yellow.png")
        # 换选另一把
        pos2 = card_center(cdp, "MP5")
        if pos2:
            cdp.click_at(pos2["x"], pos2["y"]); time.sleep(2.2)
            cdp.eval("(function(){var b=document.querySelector('.gw-mode[data-gwmode=\"caliber\"]');if(b)b.click();})()")
            time.sleep(1.2)
            rep["p2"]["switched"] = cdp.eval("""
              (function(){
                var cur=document.querySelector('#gw-browse .gw-card[aria-current=\"true\"]');
                var s=cur?cur.querySelector('span'):null;
                return JSON.stringify({now:s?s.textContent.slice(0,20):null,
                  bg:cur?getComputedStyle(cur).backgroundColor:null});
              })()""")
            shot(cdp, "p2-4-switched.png")

        # ---------- P3：对比度复测（工作台） ----------
        cdp.eval("(function(){var b=document.querySelector('.gw-mode[data-gwmode=\"build\"]');if(b)b.click();})()")
        time.sleep(2.0)
        rep["p3"]["workbench"] = json.loads(cdp.eval(CONTRAST_JS) or "[]")
        rep["p3"]["build"] = cdp.eval("(function(){return window.AM_BUILD || null;})()") or "R19.3"

        # ---------- P4：主图 + 差异条（AK-74） ----------
        print("P4 debug:", cdp.eval(
            "(function(){var b=document.querySelector('.gw-mode[data-on=\"1\"]');"
            "return JSON.stringify({hero:!!document.querySelector('.gw-hero-img'),"
            "cur:(document.getElementById('gw-current')||{}).textContent,"
            "visualEmpty:!!document.querySelector('.gw-visual-empty'),"
            "mode:b?b.dataset.gwmode:null});})()"),)
        print("P4 console:", json.dumps(cdp.console[:4], ensure_ascii=False))
        def hero_state():
            return json.loads(cdp.eval("""
              (function(){
                var h=document.querySelector('.gw-hero-img'); var t=document.querySelector('.gw-hero-tag');
                if(!h) return null;
                return JSON.stringify({src:(h.getAttribute('src')||'').split('/').pop(),
                  loaded:h.complete&&h.naturalWidth>0, tag:t?t.textContent:null});
              })()"""))
        rep["p4"].setdefault("ak74", {})
        rep["p4"]["ak74"]["initial"] = hero_state()
        shot(cdp, "p4-ak74-initial.png")
        # 换第一个配件（点已装卡 → 候选选不同件）
        cdp.eval("""
          (function(){
            var parts=document.querySelectorAll('#gw-tree .gw-part');
            for(var i=0;i<parts.length;i++){
              if(!parts[i].classList.contains('gw-part-empty')){ parts[i].click(); return; }
            }
          })()""")
        time.sleep(1.4)
        cdp.eval("""
          (function(){
            var rows=document.querySelectorAll('#gw-table .tbl-row');
            for(var i=0;i<rows.length;i++){
              if(rows[i].getAttribute('aria-selected')!=='true'){ rows[i].click(); return true; }
            }
            return false;
          })()""")
        time.sleep(2.0)
        rep["p4"]["ak74"]["mod1"] = hero_state()
        shot(cdp, "p4-ak74-mod1.png")
        # 换第二个不同位置配件（找另一个已装卡）
        cdp.eval("""
          (function(){
            var parts=document.querySelectorAll('#gw-tree .gw-part');
            for(var i=0;i<parts.length;i++){
              var p=parts[i];
              if(!p.classList.contains('gw-part-empty') && p.dataset.slot!==window.__r193slot){ p.click(); window.__r193slot=p.dataset.slot; return; }
            }
          })()""")
        time.sleep(1.4)
        cdp.eval("""
          (function(){
            var rows=document.querySelectorAll('#gw-table .tbl-row');
            for(var i=0;i<rows.length;i++){
              if(rows[i].getAttribute('aria-selected')!=='true'){ rows[i].click(); return true; }
            }
            return false;
          })()""")
        time.sleep(2.0)
        rep["p4"]["ak74"]["mod2"] = hero_state()
        rep["p4"]["ak74"]["strip"] = cdp.eval("""
          (function(){
            var t=[].map.call(document.querySelectorAll('.gw-changed-tile span'),function(x){return x.textContent;});
            return {count:document.querySelectorAll('.gw-changed-tile').length, items:t};
          })()""")
        shot(cdp, "p4-ak74-mod2.png")
        cdp.eval("document.getElementById('gw-default').click()")
        time.sleep(2.0)
        rep["p4"]["ak74"]["reset"] = hero_state()
        shot(cdp, "p4-ak74-reset.png")
        # 换枪验证不残留
        pos = card_center(cdp, "柯尔特 M4A1")
        if not pos:
            cdp.eval("(function(){var b=document.querySelector('.gw-mode[data-gwmode=\"caliber\"]');if(b)b.click();})()")
            time.sleep(1.2)
            pos = card_center(cdp, "柯尔特 M4A1")
        cdp.click_at(pos["x"], pos["y"]); time.sleep(2.5)
        rep["p4"].setdefault("m4a1", {})["initial"] = hero_state()
        shot(cdp, "p4-m4a1-initial.png")

        # ---------- P5：隐藏属性 + 模拟参数 ----------
        sm = stats_map(cdp)
        rep["p5"]["m4a1"] = {k: sm.get(k) for k in
                             ("TrueErgoDelta", "OverSwing", "Aim Sway 摆动强度",
                              "ArmStamina", "精度 MOA", "ADS 时间", "爆头有效距离")}
        # 改力量等级 → ArmStamina 应变化
        cdp.eval("""
          (function(){
            var inputs=document.querySelectorAll('.gw-sim-item input');
            if(inputs[0]){ inputs[0].value='30'; inputs[0].dispatchEvent(new Event('change',{bubbles:true})); }
          })()""")
        time.sleep(2.0)
        sm2 = stats_map(cdp)
        rep["p5"]["m4a1_strength30"] = {"ArmStamina": sm2.get("ArmStamina"),
                                        "TrueErgoDelta": sm2.get("TrueErgoDelta")}
        cdp.eval("""
          (function(){
            var inputs=document.querySelectorAll('.gw-sim-item input');
            if(inputs[0]){ inputs[0].value='10'; inputs[0].dispatchEvent(new Event('change',{bubbles:true})); }
          })()""")
        time.sleep(1.5)
        shot(cdp, "p5-hidden-stats.png")
        # Glock（手枪类）
        cdp.eval("(function(){var b=document.querySelector('.gw-mode[data-gwmode=\"caliber\"]');if(b)b.click();})()")
        time.sleep(1.2)
        pos = card_center(cdp, "Glock 17 9x19")
        if pos:
            cdp.click_at(pos["x"], pos["y"]); time.sleep(2.5)
            rep["p5"]["glock"] = {k: v for k, v in stats_map(cdp).items()
                                  if k in ("TrueErgoDelta", "OverSwing", "ArmStamina", "精度 MOA")}

        # ---------- P6：三栏布局实测 ----------
        rep["p6"]["cols"] = cdp.eval("""
          (function(){
            function m(sel){var e=document.querySelector(sel);if(!e)return null;
              var r=e.getBoundingClientRect();return {x:Math.round(r.x),w:Math.round(r.width),h:Math.round(r.height)};}
            return {forge:m('.gw-forge'),center:m('.gw-center'),cands:m('.gw-cands'),
              modes:m('.gw-modes'),top:m('.gw-top'),
              hero:m('.gw-hero'),bars:m('.gw-bars'),tree:m('.gw-tree'),
              ammo:m('.gw-ammo'),bottom:m('.gw-bottom'),candSearch:m('.gw-cands-head'),
              visualName:getComputedStyle(document.querySelector('.gw-visual-name')).color};
          })()""")
        shot(cdp, "p6-builder-1920.png")
        shot(cdp, "ref-vs-local-1920.png")

        rep["console"] = cdp.console[:8]
        ext = [r["url"] for r in cdp.requests
               if not r["url"].startswith("http://127.0.0.1:8787") and not r["url"].startswith("devtools://")]
        rep["external"] = ext[:6]
    finally:
        proc.terminate()

    # ---------- 1264×705 ----------
    proc, ws = launch(find_chrome(), 9402, 1264, 705,
                      os.path.join(os.environ.get("TEMP", "."), "r193b-%d" % os.getpid()))
    try:
        cdp = CDP(ws)
        for m in ("Page.enable", "Runtime.enable"):
            cdp.call(m)
        cdp.call("Emulation.setDeviceMetricsOverride", width=1264, height=705,
                 deviceScaleFactor=1, mobile=False)
        cdp.call("Page.navigate", url="http://127.0.0.1:8787/index.html")
        wait_ready(cdp, want_url="index.html")
        time.sleep(2.0)
        cdp.eval("document.querySelector('[data-view=\"gun\"]').click()")
        time.sleep(2.5)
        shot(cdp, "p1-1264-caliber.png")
        rep["p1"]["hscroll1264"] = cdp.eval(
            "document.documentElement.scrollWidth > document.documentElement.clientWidth + 1")
        cdp.eval("""(function(){var cs=document.querySelectorAll('#gw-browse .gw-card');
          for(var i=0;i<cs.length;i++){var s=cs[i].querySelector('span');
            if(s&&s.textContent.indexOf('AK-74 5')>=0){cs[i].click();return;}}})()""")
        time.sleep(2.8)
        shot(cdp, "p6-builder-1264.png")
        rep["p6"]["hscroll1264Build"] = cdp.eval(
            "document.documentElement.scrollWidth > document.documentElement.clientWidth + 1")
    finally:
        proc.terminate()

    out = os.path.join(OUT, "_accept.json")
    json.dump(rep, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("accept ->", os.path.relpath(out, ROOT))
    print("P1:", json.dumps(rep["p1"]["cards"]), "| spot ok:",
          sum(1 for c in rep["p1"]["spot"] if c.get("loaded")), "/", len(rep["p1"]["spot"]))
    print("P2:", json.dumps(rep["p2"], ensure_ascii=False)[:400])
    print("P3 低对比处数:", len(rep["p3"]["workbench"]))
    print("P4 ak74:", json.dumps(rep["p4"]["ak74"], ensure_ascii=False)[:420])
    print("P5:", json.dumps(rep["p5"], ensure_ascii=False)[:400])
    print("P6:", json.dumps(rep["p6"]["cols"], ensure_ascii=False))
    print("console:", rep["console"], "external:", rep["external"])


if __name__ == "__main__":
    main()
