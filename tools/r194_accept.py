# -*- coding: utf-8 -*-
"""R19.4 浏览器验收：七项功能 + 全局透明图标。

  F1 模拟参数保存/恢复/重置（localStorage 持久化跨会话）
  F2 FORGE 四类约束（容量/瞄准镜/必含/排除）真实生效 + 冲突报告
  F3 条纹属性条（基线/涨跌/斜纹）
  F4 紧凑属性面板
  F5 方形装配卡 + 浮窗 + 右键卸载
  F6 差异摘要已删除
  F7 属性实时更新（4 枪流程）
  T  透明图标上下文检查（配装/弹药/工作台三底色）
"""
import base64
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r181_accept import find_chrome, launch, CDP, wait_ready

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "r19.4-audit")
SHOTS = os.path.join(OUT, "screenshots")
os.makedirs(SHOTS, exist_ok=True)


def shot(cdp, name):
    data = base64.b64decode(cdp.call("Page.captureScreenshot", format="png")["data"])
    open(os.path.join(SHOTS, name), "wb").write(data)
    return name


def stats_map(cdp):
    return json.loads(cdp.eval("""
      (function(){
        var out={};
        document.querySelectorAll('#gw-stats .gw-stat').forEach(function(row){
          var l=row.querySelector('.gw-stat-lab'),v=row.querySelector('.gw-stat-val');
          if(l&&v) out[l.textContent]=v.textContent;});
        return JSON.stringify(out);
      })()"""))


def pick_gun(cdp, needle):
    cdp.eval("(function(){var b=document.querySelector('.gw-mode[data-gwmode=\"caliber\"]');"
             "if(b)b.click();})()")
    time.sleep(1.2)
    return cdp.eval("""
      (function(){
        var cs=document.querySelectorAll('#gw-browse .gw-card');
        for(var i=0;i<cs.length;i++){
          var s=cs[i].querySelector('span');
          if(s && s.textContent.indexOf('%s')>=0){
            cs[i].scrollIntoView({block:'center'});
            return s.textContent;
          }
        }
        return null;
      })()""" % needle)


def click_gun(cdp, needle):
    pick_gun(cdp, needle)
    time.sleep(0.4)
    cdp.eval("""
      (function(){
        var cs=document.querySelectorAll('#gw-browse .gw-card');
        for(var i=0;i<cs.length;i++){
          var s=cs[i].querySelector('span');
          if(s && s.textContent.indexOf('%s')>=0){ cs[i].click(); return; }
        }
      })()""" % needle)
    time.sleep(2.5)


def main():
    rep = {"f1": {}, "f2": {}, "f3": {}, "f4": {}, "f5": {}, "f6": {}, "f7": {}, "t": {},
           "console": [], "external": None}
    proc, ws = launch(find_chrome(), 9410, 1920, 1080,
                      os.path.join(os.environ.get("TEMP", "."), "r194-%d" % os.getpid()))
    try:
        cdp = CDP(ws)
        for m in ("Page.enable", "Runtime.enable", "Network.enable"):
            cdp.call(m)
        cdp.call("Emulation.setDeviceMetricsOverride", width=1920, height=1080,
                 deviceScaleFactor=1, mobile=False)
        cdp.call("Page.navigate", url="http://127.0.0.1:8787/index.html")
        wait_ready(cdp, want_url="index.html")
        time.sleep(2.0)
        cdp.eval("try{localStorage.removeItem('eftmap.gwmode');"
                 "localStorage.removeItem('eftmap.gwsim.v1')}catch(e){}")
        cdp.eval("document.querySelector('[data-view=\"gun\"]').click()")
        time.sleep(2.5)

        # ---------- F1 模拟参数 ----------
        click_gun(cdp, "AK-74 5")
        base = stats_map(cdp)
        rep["f1"]["armDefault"] = base.get("ArmStamina")
        cdp.eval("""
          (function(){
            var i=document.querySelectorAll('.gw-sim-item input')[0];
            i.value='30'; i.dispatchEvent(new Event('change',{bubbles:true}));
          })()""")
        time.sleep(2.0)
        rep["f1"]["armAfterChange"] = stats_map(cdp).get("ArmStamina")
        cdp.eval("(function(){var b=[].filter.call(document.querySelectorAll('.gw-forge-simbtns .gw-btn'),"
                 "function(x){return x.textContent==='保存参数';})[0]; if(b)b.click();})()")
        time.sleep(0.8)
        rep["f1"]["savedStorage"] = cdp.eval(
            "localStorage.getItem('eftmap.gwsim.v1')")
        # 刷新页面
        cdp.call("Page.navigate", url="http://127.0.0.1:8787/index.html")
        wait_ready(cdp, want_url="index.html")
        time.sleep(2.0)
        cdp.eval("document.querySelector('[data-view=\"gun\"]').click()")
        time.sleep(2.5)
        rep["f1"]["armAfterReload"] = cdp.eval("""
          (function(){
            var rows=document.querySelectorAll('#gw-stats .gw-stat');
            for(var i=0;i<rows.length;i++){
              var l=rows[i].querySelector('.gw-stat-lab');
              if(l && l.textContent==='ArmStamina') return rows[i].querySelector('.gw-stat-val').textContent;
            }
            return null;})()""")
        rep["f1"]["inputAfterReload"] = cdp.eval(
            "(document.querySelectorAll('.gw-sim-item input')[0]||{}).value")
        # 换枪后仍在
        click_gun(cdp, "Glock 17 9x19")
        rep["f1"]["inputAfterGunSwitch"] = cdp.eval(
            "(document.querySelectorAll('.gw-sim-item input')[0]||{}).value")
        # 重置
        cdp.eval("(function(){var b=[].filter.call(document.querySelectorAll('.gw-forge-simbtns .gw-btn'),"
                 "function(x){return x.textContent==='恢复默认';})[0]; if(b)b.click();})()")
        time.sleep(1.5)
        rep["f1"]["inputAfterReset"] = cdp.eval(
            "(document.querySelectorAll('.gw-sim-item input')[0]||{}).value")
        rep["f1"]["storageAfterReset"] = cdp.eval("localStorage.getItem('eftmap.gwsim.v1')")
        shot(cdp, "f1-sim-params.png")

        # ---------- F2 FORGE 约束（AK-74）----------
        click_gun(cdp, "AK-74 5")
        rep["f2"]["capsOffered"] = cdp.eval("""
          (function(){
            var chips=[].map.call(document.querySelectorAll('.gw-forge-sec'),
              function(s){return s;})
              .filter(function(s){var b=s.querySelector('b');return b&&b.textContent==='弹匣容量';})[0];
            return chips?[].map.call(chips.querySelectorAll('.gw-chip'),function(c){return c.textContent;}):[];
          })()""")
        # 只允许 30 发
        cdp.eval("""
          (function(){
            var sec=[].filter.call(document.querySelectorAll('.gw-forge-sec'),
              function(s){var b=s.querySelector('b');return b&&b.textContent==='弹匣容量';})[0];
            var chips=sec.querySelectorAll('.gw-chip');
            for(var i=0;i<chips.length;i++){
              if(chips[i].textContent==='30 发' && chips[i].dataset.on!=='1'){ chips[i].click(); return; }
            }
          })()""")
        time.sleep(1.0)
        # 排除一个枪口
        cdp.eval("""
          (function(){
            var sec=[].filter.call(document.querySelectorAll('.gw-forge-sec'),
              function(s){var b=s.querySelector('b');return b&&b.textContent==='排除';})[0];
            var input=sec.querySelector('input');
            input.value='制退器';
            input.dispatchEvent(new Event('input',{bubbles:true}));
          })()""")
        time.sleep(0.8)
        cdp.eval("""
          (function(){
            var sec=[].filter.call(document.querySelectorAll('.gw-forge-sec'),
              function(s){var b=s.querySelector('b');return b&&b.textContent==='排除';})[0];
            var row=sec.querySelector('.gw-forge-poolrow');
            if(row){row.click();}
          })()""")
        time.sleep(1.0)
        rep["f2"]["excludedPinned"] = cdp.eval("""
          (function(){
            var sec=[].filter.call(document.querySelectorAll('.gw-forge-sec'),
              function(s){var b=s.querySelector('b');return b&&b.textContent==='排除';})[0];
            return [].map.call(sec.querySelectorAll('.gw-forge-pin i'),function(x){return x.textContent;});
          })()""")
        # 生成（低后坐力默认）
        cdp.eval("(function(){var b=document.querySelector('.gw-forge-go');if(b)b.click();})()")
        time.sleep(8.0)
        rep["f2"]["caps30"] = cdp.eval("""
          (function(){
            var rows=[].map.call(document.querySelectorAll('.gw-forge-res'),function(r){
              return {ok:!r.classList.contains('gw-forge-bad'),
                      disabled:!!r.querySelector('.gw-btn[disabled]')};
            });
            return JSON.stringify({n:rows.length, allOk:rows.every(function(r){return r.ok;}),
                                   anyDisabled:rows.some(function(r){return r.disabled;})});
          })()""")
        shot(cdp, "f2-forge-caps30-excluded.png")
        # 应用第一个方案并终检
        applied = cdp.eval("""
          (function(){
            var b=document.querySelector('.gw-forge-res .gw-btn');
            if(!b||b.disabled) return 'no-applicable';
            b.click(); return 'applied';
          })()""")
        time.sleep(2.0)
        rep["f2"]["applied"] = applied
        # 终检证据：应用后装配卡里不应再出现排除件（引擎端 checkConstraints 已在
        # 生成与应用两处把关，这里用 DOM 侧写佐证）
        rep["f2"]["partsAfterApply"] = cdp.eval(
            "document.querySelectorAll('#gw-tree .gw-part:not(.gw-part-empty)').length")
        # 冲突：必含=排除同一件
        cdp.eval("""
          (function(){
            function pin(secTitle, name){
              var sec=[].filter.call(document.querySelectorAll('.gw-forge-sec'),
                function(s){var b=s.querySelector('b');return b&&b.textContent===secTitle;})[0];
              var input=sec.querySelector('input');
              input.value=name; input.dispatchEvent(new Event('input',{bubbles:true}));
              var row=sec.querySelector('.gw-forge-poolrow'); if(row)row.click();
            }
            pin('必须包含','制退器');
          })()""")
        time.sleep(1.0)
        cdp.eval("(function(){var b=document.querySelector('.gw-forge-go');if(b)b.click();})()")
        time.sleep(8.0)
        rep["f2"]["conflict"] = cdp.eval("""
          (function(){
            var rows=document.querySelectorAll('.gw-forge-res');
            var bad=[].filter.call(rows,function(r){return r.classList.contains('gw-forge-bad');});
            var v=bad[0]?bad[0].querySelector('.gw-forge-viol'):null;
            return JSON.stringify({rows:rows.length, badRows:bad.length,
                                   why:v?v.textContent.slice(0,60):null});
          })()""")
        shot(cdp, "f2-forge-conflict.png")
        # 清理约束（避免影响后续）
        cdp.eval("""
          (function(){
            document.querySelectorAll('.gw-forge-pin button').forEach(function(b){ if(b.textContent==='×') b.click(); });
            document.querySelectorAll('.gw-forge-pinned .gw-btn').forEach(function(b){ if(b.textContent==='清空') b.click(); });
          })()""")
        time.sleep(0.8)

        # ---------- F5 方形卡 + 右键卸载 ----------
        rep["f5"]["square"] = cdp.eval("""
          (function(){
            var cards=[].map.call(document.querySelectorAll('#gw-tree .gw-part'),function(c){
              var r=c.getBoundingClientRect();
              return {w:Math.round(r.width), h:Math.round(r.height)};
            }).slice(0,8);
            return JSON.stringify({cards:cards,
              allSquare:cards.every(function(c){return Math.abs(c.w-c.h)<=1;})});
          })()""")
        # 右键卸载（对已装件）
        before = stats_map(cdp)
        rc = cdp.eval("""
          (function(){
            var cards=document.querySelectorAll('#gw-tree .gw-part');
            for(var i=0;i<cards.length;i++){
              if(!cards[i].classList.contains('gw-part-empty')){
                var r=cards[i].getBoundingClientRect();
                return JSON.stringify({x:r.x+r.width/2, y:r.y+r.height/2, slot:cards[i].dataset.slot});
              }
            }
            return null;})()""")
        if rc:
            rc = json.loads(rc)
            cdp.call("Input.dispatchMouseEvent", type="mouseMoved", x=rc["x"], y=rc["y"],
                     button="none", clickCount=0)
            cdp.call("Input.dispatchMouseEvent", type="mousePressed", x=rc["x"], y=rc["y"],
                     button="right", clickCount=1)
            cdp.call("Input.dispatchMouseEvent", type="mouseReleased", x=rc["x"], y=rc["y"],
                     button="right", clickCount=1)
            time.sleep(2.0)
            after = stats_map(cdp)
            rep["f5"]["rightClick"] = {
                "slot": rc["slot"],
                "ergoChanged": before.get("人机工效") != after.get("人机工效"),
                "partsBefore": before.get("已装配件"), "partsAfter": after.get("已装配件")}
            shot(cdp, "f5-after-rightclick.png")
        # 悬停浮窗
        cdp.eval("""
          (function(){
            var cards=document.querySelectorAll('#gw-tree .gw-part');
            for(var i=0;i<cards.length;i++){
              if(!cards[i].classList.contains('gw-part-empty')){
                var r=cards[i].getBoundingClientRect();
                window.__hoverAt={x:r.x+r.width/2,y:r.y+r.height/2};
                return;}}})()""")
        hv = cdp.eval("JSON.stringify(window.__hoverAt||null)")
        if hv and hv != "null":
            hv = json.loads(hv)
            cdp.call("Input.dispatchMouseEvent", type="mouseMoved", x=hv["x"], y=hv["y"],
                     button="none", clickCount=0)
            time.sleep(0.8)
            rep["f5"]["tooltip"] = cdp.eval("""
              (function(){
                var t=document.getElementById('gw-tip');
                return t? JSON.stringify({visible:!t.hidden, text:t.textContent.slice(0,50)}) : null;})()""")
            shot(cdp, "f5-tooltip.png")
        rep["f5"]["squareSizes"] = rep["f5"].get("square")

        # ---------- F3 条纹属性条 ----------
        bars = cdp.eval("""
          (function(){
            function info(i){
              var row=document.querySelectorAll('#gw-bars .gw-bar')[i];
              if(!row) return null;
              var segs=[].map.call(row.querySelectorAll('.gw-bar-seg'),function(s){
                return {cls:s.className.replace('gw-bar-seg ',''),
                        left:s.style.left, width:s.style.width};});
              var bv=row.querySelector('.gw-bar-baseval');
              return {segs:segs, base:row.querySelector('.gw-bar-base')?'1':'0',
                      baseVal:bv?bv.textContent:null, dir:bv?bv.dataset.dir:null};
            }
            return JSON.stringify([info(0),info(1),info(2),info(3)]);
          })()""")
        rep["f3"] = json.loads(bars or "[]")
        shot(cdp, "f3-bars.png")

        # ---------- F4 紧凑属性 ----------
        rep["f4"] = json.loads(cdp.eval("""
          (function(){
            var s=document.querySelector('#gw-stats');
            var r=s.getBoundingClientRect();
            var cols=getComputedStyle(s).gridTemplateColumns.split(' ').length;
            var c=document.querySelector('.gw-center').getBoundingClientRect();
            return JSON.stringify({statsW:Math.round(r.width), centerW:Math.round(c.width),
                                   gridCols:cols});
          })()""") or "{}")

        # ---------- F6 差异摘要已删 ----------
        rep["f6"]["diffSummaryGone"] = cdp.eval(
            "document.body.textContent.indexOf('与默认装配的差异') < 0")

        # ---------- F7 换弹匣 → 满弹匣重量影响 TED/耐力 ----------
        sm0 = stats_map(cdp)
        cdp.eval("""
          (function(){
            var parts=document.querySelectorAll('#gw-tree .gw-part');
            for(var i=0;i<parts.length;i++){
              var p=parts[i];
              if(!p.classList.contains('gw-part-empty') && /弹匣|mag/i.test(p.dataset.slot)){
                p.click(); window.__mag=p.dataset.slot; return;}}})()""")
        time.sleep(1.4)
        cdp.eval("""
          (function(){
            var rows=document.querySelectorAll('#gw-table .tbl-row');
            for(var i=0;i<rows.length;i++){
              if(rows[i].getAttribute('aria-selected')!=='true'){ rows[i].click(); return true;}}
            return false;})()""")
        time.sleep(2.0)
        sm1 = stats_map(cdp)
        rep["f7"]["magSwap"] = {"magSlot": cdp.eval("window.__mag||null"),
                                "weight": (sm0.get("重量"), sm1.get("重量")),
                                "TED": (sm0.get("TrueErgoDelta"), sm1.get("TrueErgoDelta")),
                                "arm": (sm0.get("ArmStamina"), sm1.get("ArmStamina"))}

        # ---------- T 透明上下文 ----------
        rep["t"]["loadout"] = cdp.eval("""
          (function(){
            document.querySelector('[data-view=\"loadout\"]').click();
            return 'ok';})()""")
        time.sleep(2.5)
        rep["t"]["loadoutIcons"] = cdp.eval("""
          (function(){
            var t=0,tr=0;
            document.querySelectorAll('.lw-cell-icon,.tbl-icon').forEach(function(i){
              var s=i.getAttribute('src')||''; if(!s)return; t++;
              if(s.indexOf('icons-transparent')>=0) tr++;});
            return JSON.stringify({total:t, transparent:tr});})()""")
        shot(cdp, "t-loadout-transparent.png")
        cdp.eval("document.querySelector('[data-view=\"ammo\"]').click()")
        time.sleep(2.5)
        rep["t"]["ammoIcons"] = cdp.eval("""
          (function(){
            var t=0,tr=0;
            document.querySelectorAll('.am-ic,.am-detail-ic,.am-dot-img').forEach(function(i){
              var s=i.getAttribute('src')||i.getAttribute('href')||''; if(!s)return; t++;
              if(s.indexOf('icons-transparent')>=0) tr++;});
            return JSON.stringify({total:t, transparent:tr});})()""")
        shot(cdp, "t-ammo-transparent.png")
        cdp.eval("document.querySelector('[data-view=\"gun\"]').click()")
        time.sleep(2.5)
        shot(cdp, "t-builder-transparent.png")

        rep["console"] = [c for c in cdp.console if c.get("level") == "error"] + cdp.console[:4]
        ext = [r["url"] for r in cdp.requests
               if not r["url"].startswith("http://127.0.0.1:8787") and not r["url"].startswith("devtools://")]
        rep["external"] = ext[:6]
    finally:
        proc.terminate()

    # 1264 视口快速检查
    proc, ws = launch(find_chrome(), 9411, 1264, 705,
                      os.path.join(os.environ.get("TEMP", "."), "r194b-%d" % os.getpid()))
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
        rep["t"]["hscroll1264"] = cdp.eval(
            "document.documentElement.scrollWidth > document.documentElement.clientWidth + 1")
        shot(cdp, "builder-1264.png")
        rep["f4"]["statsW1264"] = cdp.eval(
            "Math.round(document.querySelector('#gw-stats').getBoundingClientRect().width)")
    finally:
        proc.terminate()

    json.dump(rep, open(os.path.join(OUT, "_accept.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("accept -> docs/r19.4-audit/_accept.json")
    print("F1:", json.dumps(rep["f1"], ensure_ascii=False)[:400])
    print("F2:", json.dumps(rep["f2"], ensure_ascii=False)[:500])
    print("F5:", json.dumps(rep["f5"], ensure_ascii=False)[:400])
    print("F7:", json.dumps(rep["f7"], ensure_ascii=False))
    print("T:", json.dumps(rep["t"], ensure_ascii=False))
    print("console:", rep["console"], "external:", rep["external"])


if __name__ == "__main__":
    main()
