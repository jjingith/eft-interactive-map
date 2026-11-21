# -*- coding: utf-8 -*-
"""R19.2 浏览器验收：四项视觉/数据问题的整改验证。

  P1 浏览页（Caliber/Class）：内容自然增长、占满宽度（实测容器尺寸，不再有 232px 裁切）
  P2 Table：紧凑列宽 + 全左对齐 + 扩展属性（隐藏值）开关
  P3 工作台：三栏对照参考截图 + 隐藏属性行（AK-74 / M4A1 / Glock 17 三枪验证）
  P4 白底图标：浏览卡 / 候选行 / 装配卡 / 摘要 全部指向 icons-transparent
产物：docs/r19.2-ui-audit/_accept.json + 截图
"""
import base64
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r181_accept import find_chrome, launch, CDP, wait_ready

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "r19.2-ui-audit")
os.makedirs(OUT, exist_ok=True)


def shot(cdp, name):
    data = base64.b64decode(cdp.call("Page.captureScreenshot", format="png")["data"])
    open(os.path.join(OUT, name), "wb").write(data)
    return name


def measure(cdp, sel):
    return cdp.eval("""
      (function(){
        var e=document.querySelector('%s');
        if(!e) return null;
        var r=e.getBoundingClientRect();
        var cs=getComputedStyle(e);
        return {w:Math.round(r.width), h:Math.round(r.height),
                maxH:cs.maxHeight, ov:cs.overflow};
      })()""" % sel)


def browse_metrics(cdp):
    return cdp.eval("""
      (function(){
        var page=document.querySelector('#gw-browsepage');
        var browse=document.querySelector('#gw-browse');
        var grids=[].map.call(document.querySelectorAll('.gw-browse-grid'),function(g){
          var r=g.getBoundingClientRect();
          return {w:Math.round(r.width), h:Math.round(r.height),
                  cols:getComputedStyle(g).gridTemplateColumns.split(' ').length};
        });
        var groups=[].map.call(document.querySelectorAll('.gw-browse-group'),function(g){
          return Math.round(g.getBoundingClientRect().height);
        });
        var cs=browse?getComputedStyle(browse):null;
        return JSON.stringify({
          page:{w:Math.round(page.getBoundingClientRect().width),
                h:Math.round(page.getBoundingClientRect().height),
                scrollH:page.scrollHeight},
          browse:browse?{w:Math.round(browse.getBoundingClientRect().width),
                         h:Math.round(browse.getBoundingClientRect().height),
                         maxH:cs.maxHeight, scrollH:browse.scrollHeight}:null,
          groups:groups.length, groupHeights:groups,
          grids:grids.slice(0,6), gridCount:grids.length,
          cards:document.querySelectorAll('.gw-card').length,
          whiteIcons:document.querySelectorAll('.gw-card img[src*="icons-transparent"]').length
        });
      })()""")


def pick_gun(cdp, needle):
    return cdp.eval("""
      (function(){
        var mode=document.querySelector('.gw-mode[data-gwmode="caliber"]');
        if(mode && !mode.dataset.on){ mode.click(); }
        setTimeout(function(){},0);
        var cards=document.querySelectorAll('#gw-browse .gw-card');
        for(var i=0;i<cards.length;i++){
          var s=cards[i].querySelector('span');
          if(s && s.textContent.indexOf('%s')>=0){ cards[i].click(); return s.textContent; }
        }
        return null;
      })()""" % needle)


def stats_values(cdp):
    """属性面板全部行：标签 -> {值, 可信度}"""
    return json.loads(cdp.eval("""
      (function(){
        var out={};
        document.querySelectorAll('#gw-stats .gw-stat').forEach(function(row){
          var lab=row.querySelector('.gw-stat-lab');
          var val=row.querySelector('.gw-stat-val');
          var conf=row.querySelector('.gw-stat-conf');
          if(lab && val){ out[lab.textContent]={v:val.textContent, conf:conf?conf.textContent:''}; }
        });
        return JSON.stringify(out);
      })()"""))


def main():
    rep = {"console": [], "views": {}, "hidden": {}, "icons": {}, "external": None}
    guns = ["AK-74 5.45x39", "柯尔特 M4A1", "Glock 17 9x19"]

    # ---------- 1920×1080 ----------
    proc, ws = launch(find_chrome(), 9396, 1920, 1080,
                      os.path.join(os.environ.get("TEMP", "."), "r192a-%d" % os.getpid()))
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

        # ---- P1：Caliber / Class 布局实测 ----
        for mode, tag in (("caliber", "1920-p1-caliber"), ("class", "1920-p1-class")):
            cdp.eval("(function(){var b=document.querySelector('.gw-mode[data-gwmode=\"%s\"]');"
                     "if(b){b.click();}})()" % mode)
            time.sleep(1.4)
            rep["views"][tag] = json.loads(browse_metrics(cdp))
            shot(cdp, tag + ".png")

        # ---- P2：Table + 扩展属性 ----
        cdp.eval("(function(){var b=document.querySelector('.gw-mode[data-gwmode=\"table\"]');"
                 "if(b){b.click();}})()")
        time.sleep(1.4)
        rep["views"]["1920-p2-table"] = {
            "thAligns": cdp.eval("""
              JSON.stringify([].map.call(document.querySelectorAll('#gw-table2 .gw-tbl th'),
                function(th){return getComputedStyle(th).textAlign;}))"""),
            "thCount": cdp.eval("document.querySelectorAll('#gw-table2 .gw-tbl th').length"),
            "extBar": cdp.eval("!!document.querySelector('#gw-table2 .gw-tbl-ext')")}
        shot(cdp, "1920-p2-table.png")
        cdp.eval("(function(){var cb=document.querySelector('#gw-table2 .gw-tbl-ext input');"
                 "if(cb){cb.click();}})()")
        time.sleep(1.4)
        rep["views"]["1920-p2-table-ext"] = {
            "thCount": cdp.eval("document.querySelectorAll('#gw-table2 .gw-tbl th').length"),
            "firstRow": cdp.eval("(function(){var r=document.querySelector('#gw-table2 .gw-tbl tbody tr');"
                                 "return r?r.textContent.slice(0,120):null;})()")}
        shot(cdp, "1920-p2-table-ext.png")
        cdp.eval("(function(){var cb=document.querySelector('#gw-table2 .gw-tbl-ext input');"
                 "if(cb){cb.click();}})()")
        time.sleep(1.0)

        # ---- P3 + 隐藏属性三枪验证 ----
        for gun in guns:
            pick_gun(cdp, gun)
            time.sleep(2.5)
            base = stats_values(cdp)
            shot(cdp, "1920-p3-hidden-%s.png" % gun.split(" ")[0].replace("柯尔特", "").replace("·", ""))
            # 改一个影响人机的配件：点第一张空槽/或换枪口 —— 用候选表第一行可装项
            mod_info = cdp.eval("""
              (function(){
                var parts=document.querySelectorAll('#gw-tree .gw-part');
                var target=null;
                for(var i=0;i<parts.length;i++){ if(!parts[i].classList.contains('gw-part-empty')){target=parts[i];break;} }
                if(!target){return null;}
                target.click();
                return target.dataset.slot;
              })()""")
            time.sleep(1.5)
            # 装一个候选（与已装不同的第一行）
            equipped = cdp.eval("""
              (function(){
                var rows=document.querySelectorAll('#gw-table .tbl-row');
                for(var i=0;i<rows.length;i++){
                  if(rows[i].getAttribute('aria-selected')!=='true'){ rows[i].click(); return true; }
                }
                return false;
              })()""")
            time.sleep(2.0)
            modded = stats_values(cdp)
            # 恢复默认
            cdp.eval("document.getElementById('gw-default').click()")
            time.sleep(2.0)
            reset = stats_values(cdp)
            rep["hidden"][gun] = {
                "baseAds": (base.get("ADS 时间") or {}).get("v"),
                "modAds": (modded.get("ADS 时间") or {}).get("v"),
                "resetAds": (reset.get("ADS 时间") or {}).get("v"),
                "baseHead": (base.get("爆头有效距离") or {}).get("v"),
                "modHead": (modded.get("爆头有效距离") or {}).get("v"),
                "resetHead": (reset.get("爆头有效距离") or {}).get("v"),
                "overSwing": (base.get("OverSwing") or {}).get("v"),
                "evoErgoDelta": (base.get("EvoErgoDelta") or {}).get("v"),
                "armStamina": (base.get("ArmStamina") or {}).get("v"),
                "cameraSnap": (base.get("相机后坐") or {}).get("v"),
                "modSlot": mod_info, "equipped": equipped,
                "ergoChange": (base.get("人机工效") or {}).get("v")
                              + " -> " + (modded.get("人机工效") or {}).get("v")
                              + " -> " + (reset.get("人机工效") or {}).get("v")}

        # ---- P4：白底图标覆盖检查 ----
        rep["icons"] = json.loads(cdp.eval("""
          (function(){
            function probe(sel, attr){
              // 排除空槽占位的 1px 透明 GIF——它们不是物品图标
              var imgs=document.querySelectorAll(sel), total=0, white=0, other=[];
              [].forEach.call(imgs,function(i){
                var s=i.getAttribute(attr||'src')||'';
                if(!s || s.indexOf('data:image/gif')===0) return;
                total++;
                if(s.indexOf('icons-transparent')>=0) white++;
                else other.push(s.split('/').pop().slice(0,30));
              });
              return {total:total, white:white, other:other.slice(0,4)};
            }
            return JSON.stringify({
              browseCard: probe('.gw-card img'),
              candRow: probe('#gw-table .gw-row-ic'),
              partCard: probe('#gw-tree .gw-part-ic'),
              visual: probe('.gw-visual-img')
            });
          })()"""))
        shot(cdp, "1920-p4-icons.png")

        # ---- 工作台整体对照图 ----
        pick_gun(cdp, "AK-74 5.45x39")
        time.sleep(2.5)
        rep["views"]["1920-p3-builder"] = {
            "forgeW": cdp.eval("Math.round(document.querySelector('.gw-forge').getBoundingClientRect().width)"),
            "centerW": cdp.eval("Math.round(document.querySelector('.gw-center').getBoundingClientRect().width)"),
            "candsW": cdp.eval("Math.round(document.querySelector('.gw-cands').getBoundingClientRect().width)"),
            "costTabs": cdp.eval("(function(){var t=document.querySelectorAll('.gw-cost-tab');"
                                 "return [].map.call(t,function(x){return x.textContent;});})()")}
        shot(cdp, "1920-p3-builder.png")
        shot(cdp, "ref-vs-local-1920.png")
        rep["console"] = cdp.console[:8]
        ext = [r["url"] for r in cdp.requests
               if not r["url"].startswith("http://127.0.0.1:8787") and not r["url"].startswith("devtools://")]
        rep["external"] = ext[:6]
    finally:
        proc.terminate()

    # ---------- 1264×705 ----------
    proc, ws = launch(find_chrome(), 9397, 1264, 705,
                      os.path.join(os.environ.get("TEMP", "."), "r192b-%d" % os.getpid()))
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
        for mode, tag in (("caliber", "1264-p1-caliber"), ("class", "1264-p1-class")):
            cdp.eval("(function(){var b=document.querySelector('.gw-mode[data-gwmode=\"%s\"]');"
                     "if(b){b.click();}})()" % mode)
            time.sleep(1.4)
            rep["views"][tag] = json.loads(browse_metrics(cdp))
            shot(cdp, tag + ".png")
        cdp.eval("(function(){var b=document.querySelector('.gw-mode[data-gwmode=\"table\"]');"
                 "if(b){b.click();}})()")
        time.sleep(1.4)
        shot(cdp, "1264-p2-table.png")
        cdp.eval("""
          (function(){
            var cards=document.querySelectorAll('#gw-browse .gw-card');
            for(var i=0;i<cards.length;i++){
              var s=cards[i].querySelector('span');
              if(s && s.textContent.indexOf('AK-74 5')>=0){ cards[i].click(); return; }
            }
          })()""")
        time.sleep(2.5)
        shot(cdp, "1264-p3-builder.png")
        shot(cdp, "ref-vs-local-1264.png")
        rep["views"]["1264-p3-builder"] = {
            "hscroll": cdp.eval("document.documentElement.scrollWidth > document.documentElement.clientWidth + 1")}
    finally:
        proc.terminate()

    out = os.path.join(OUT, "_accept.json")
    json.dump(rep, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("accept ->", os.path.relpath(out, ROOT))
    print("views:")
    for k in ("1920-p1-caliber", "1920-p1-class", "1264-p1-caliber", "1264-p1-class"):
        v = rep["views"].get(k) or {}
        print("  %-18s cards=%s browse=%s page=%s" % (
            k, v.get("cards"),
            (v.get("browse") or {}).get("maxH"),
            (v.get("page") or {}).get("scrollH")))
    print("table:", json.dumps(rep["views"].get("1920-p2-table-ext"), ensure_ascii=False)[:200])
    for gun, h in rep["hidden"].items():
        print("  %-18s ADS %s -> %s -> %s | head %s -> %s | OS=%s EED=%s AS=%s cam=%s" % (
            gun[:18], h["baseAds"], h["modAds"], h["resetAds"], h["baseHead"], h["modHead"],
            h["overSwing"], h["evoErgoDelta"], h["armStamina"], h["cameraSnap"]))
        print("      ergo:", h["ergoChange"], "| equipped:", h["equipped"], h["modSlot"])
    print("icons:", json.dumps(rep["icons"], ensure_ascii=False))
    print("builder:", json.dumps(rep["views"].get("1920-p3-builder"), ensure_ascii=False))
    print("console:", rep["console"])
    print("external:", rep["external"])


if __name__ == "__main__":
    main()
