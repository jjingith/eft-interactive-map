# -*- coding: utf-8 -*-
"""R19.1 浏览器验收：按参考截图重构后的配枪页。

覆盖（对照 docs/r19-gun-builder/reference-screenshots.md）：
  1. Caliber / Class / Table / Gun 四个视图模式（参考站四个视图页签）
  2. 主武器/手枪 + Auto/Single/Burst 筛选芯片
  3. 工作台三栏：FORGE 面板（生成/应用） / 装配卡片（装卸） / 右栏候选表（搜索）
  4. 属性条（基线括号）、弹药卡、底部 Final Cost + 改装时间线
  5. 1920×1080 与 1264×705 两种窗口、无横向溢出、0 控制台错误
产物：docs/r19-gun-builder/_accept.json + screenshots/ + layout-comparison/
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r181_accept import find_chrome, launch, CDP, wait_ready

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_SHOT = os.path.join(ROOT, "docs", "r19-gun-builder", "screenshots")
OUT_CMP = os.path.join(ROOT, "docs", "r19-gun-builder", "layout-comparison")
os.makedirs(OUT_SHOT, exist_ok=True)
os.makedirs(OUT_CMP, exist_ok=True)

JS_MODE = "(function(){var e=document.querySelector('.gw-mode[data-on=\"1\"]');return e?e.dataset.gwmode:null;})()"
JS_CARD = """(function(){
  var out={cards:document.querySelectorAll('#gw-browse .gw-card').length,
           groups:[].map.call(document.querySelectorAll('#gw-browse .gw-browse-hd'),function(h){return h.textContent;}).slice(0,20)};
  return JSON.stringify(out);})()"""


def hscroll(cdp):
    return cdp.eval("document.documentElement.scrollWidth > document.documentElement.clientWidth + 1")


def shot(cdp, name, outdir=OUT_SHOT):
    p = os.path.join(outdir, name)
    data = cdp.call("Page.captureScreenshot", format="png")["data"]
    import base64
    open(p, "wb").write(base64.b64decode(data))
    return name


def set_mode(cdp, mode):
    cdp.eval("(function(){var b=document.querySelector('.gw-mode[data-gwmode=\"%s\"]');if(b){b.click();}})()" % mode)
    time.sleep(1.2)


def main():
    rep = {"console": [], "views": [], "external": None}

    proc, ws = launch(find_chrome(), 9391, 1920, 1080,
                      os.path.join(os.environ.get("TEMP", "."), "r191a-%d" % os.getpid()))
    try:
        cdp = CDP(ws)
        for m in ("Page.enable", "Runtime.enable", "Network.enable", "Log.enable"):
            cdp.call(m)
        cdp.call("Emulation.setDeviceMetricsOverride", width=1920, height=1080,
                 deviceScaleFactor=1, mobile=False)
        cdp.call("Page.navigate", url="http://127.0.0.1:8787/index.html")
        wait_ready(cdp, want_url="index.html")
        time.sleep(2.0)
        cdp.eval("try{localStorage.removeItem('eftmap.gwmode')}catch(e){}")
        cdp.eval("document.querySelector('[data-view=\"gun\"]').click()")
        time.sleep(3.0)

        # ---- 1. 四视图 ----
        for mode, tag in (("caliber", "01-caliber"), ("class", "02-class"), ("table", "03-table")):
            set_mode(cdp, mode)
            info = json.loads(cdp.eval(JS_CARD) or "{}")
            rep["views"].append({
                "mode": mode, "got": cdp.eval(JS_MODE),
                "cards": info.get("cards"), "groups": info.get("groups"),
                "hscroll": hscroll(cdp),
                "shot": shot(cdp, "1920-%s.png" % tag)})

        # ---- 2. 筛选芯片：只留 Single ----
        set_mode(cdp, "caliber")
        before = json.loads(cdp.eval(JS_CARD) or "{}").get("cards")
        cdp.eval("(function(){var c=document.querySelector('#gw-firechips .gw-chip[data-gwfire=\"fullauto\"]');"
                 "if(c){c.click();}})()")
        time.sleep(1.0)
        after_single = json.loads(cdp.eval(JS_CARD) or "{}").get("cards")
        shot(cdp, "1920-04-filter-single.png")
        cdp.eval("(function(){var c=document.querySelector('#gw-firechips .gw-chip[data-gwfire=\"fullauto\"]');"
                 "if(c){c.click();}})()")
        time.sleep(0.8)
        # 手枪开关
        cdp.eval("(function(){var c=document.querySelector('#gw-kindchips .gw-chip[data-gwkind=\"handgun\"]');"
                 "if(c){c.click();}})()")
        time.sleep(1.0)
        only_primary = json.loads(cdp.eval(JS_CARD) or "{}").get("cards")
        cdp.eval("(function(){var c=document.querySelector('#gw-kindchips .gw-chip[data-gwkind=\"handgun\"]');"
                 "if(c){c.click();}})()")
        time.sleep(0.8)
        rep["filters"] = {"all": before, "singleOnly": after_single, "primaryOnly": only_primary}

        # ---- 3. 进工作台（AK-74）----
        picked = cdp.eval("""
          (function(){
            var cards=document.querySelectorAll('#gw-browse .gw-card');
            for(var i=0;i<cards.length;i++){
              var s=cards[i].querySelector('span');
              if(s && /AK-74 5/.test(s.textContent)){ cards[i].click(); return s.textContent; }
            }
            return cards.length? (cards[0].click(), cards[0].querySelector('span').textContent) : null;
          })()""")
        time.sleep(3.0)
        rep["picked"] = picked
        rep["modeAfterPick"] = cdp.eval(JS_MODE)
        rep["parts"] = cdp.eval("document.querySelectorAll('#gw-tree .gw-part').length")
        rep["bars"] = cdp.eval("document.querySelectorAll('#gw-bars .gw-bar').length")
        rep["barsText"] = " | ".join(
            (cdp.eval("(document.querySelectorAll('#gw-bars .gw-bar')[%d].textContent)||''" % i) or "").strip()
            for i in range(5))
        rep["candRows"] = cdp.eval("document.querySelectorAll('#gw-table .tbl-row').length")
        rep["ammoText"] = " ".join((cdp.eval("(document.getElementById('gw-ammo')||{}).textContent") or "").split())[:200]
        rep["bottomText"] = " ".join((cdp.eval("(document.getElementById('gw-bottom')||{}).textContent") or "").split())[:260]
        rep["hscrollBuild"] = hscroll(cdp)
        shot(cdp, "1920-05-builder.png", OUT_SHOT)
        shot(cdp, "ref-gun-builder-vs-local.png", OUT_CMP)

        # ---- 4. 候选面板搜索 ----
        cdp.eval("(function(){var i=document.getElementById('gw-cand-search');"
                 "if(i){i.value='消音';i.dispatchEvent(new Event('input',{bubbles:true}));}})()")
        time.sleep(1.0)
        rep["candSearch"] = {
            "query": "消音",
            "rows": cdp.eval("document.querySelectorAll('#gw-table .tbl-row').length"),
            "first": cdp.eval("(function(){var r=document.querySelector('#gw-table .tbl-row');"
                              "return r?r.textContent.trim().slice(0,50):null;})()")}
        cdp.eval("(function(){var i=document.getElementById('gw-cand-search');"
                 "if(i){i.value='';i.dispatchEvent(new Event('input',{bubbles:true}));}})()")
        time.sleep(0.8)

        # ---- 5. 点一张空槽卡 → 候选 → 装第一件 → 卸下 ----
        slot_picked = cdp.eval("""
          (function(){
            var ps=document.querySelectorAll('#gw-tree .gw-part-empty');
            if(!ps.length){return null;}
            ps[0].click();
            return ps[0].dataset.slot;
          })()""")
        time.sleep(1.6)
        rep["emptySlotPicked"] = slot_picked
        cand_before = cdp.eval("document.querySelectorAll('#gw-table .tbl-row').length")
        equip = cdp.eval("""
          (function(){
            var r=document.querySelector('#gw-table .tbl-row');
            if(!r){return null;}
            var nm=r.textContent.trim().slice(0,40);
            r.click();
            return nm;
          })()""")
        time.sleep(2.0)
        rep["equip"] = {"slot": slot_picked, "candRows": cand_before, "equipped": equip,
                        "partsAfter": cdp.eval("document.querySelectorAll('#gw-tree .gw-part').length")}
        shot(cdp, "1920-06-after-equip.png")
        # 卸下：找该槽位卡片角上的 ×
        removed = cdp.eval("""
          (function(){
            var card=document.querySelector('#gw-tree .gw-part[data-slot=\"%s\"]');
            if(!card){return 'no card';}
            var x=card.querySelector('.gw-slot-x');
            if(!x){return 'no x';}
            x.click();
            return 'removed';
          })()""" % (slot_picked or ""))
        time.sleep(1.6)
        rep["remove"] = removed
        rep["partsAfterRemove"] = cdp.eval("document.querySelectorAll('#gw-tree .gw-part').length")

        # ---- 6. FORGE ----
        cdp.eval("(function(){var b=document.querySelector('.gw-forge-go');if(b){b.click();}})()")
        time.sleep(6.0)
        rep["forge"] = {
            "results": cdp.eval("document.querySelectorAll('.gw-forge-res').length"),
            "note": " ".join((cdp.eval("(document.querySelector('.gw-forge-note')||{}).textContent") or "").split())}
        shot(cdp, "1920-07-forge.png")
        applied = cdp.eval("""
          (function(){
            var b=document.querySelector('.gw-forge-res .gw-btn');
            if(!b){return 'no result';}
            b.click();
            return 'applied';
          })()""")
        time.sleep(2.0)
        rep["forgeApplied"] = applied
        rep["partsAfterForge"] = cdp.eval("document.querySelectorAll('#gw-tree .gw-part').length")
        shot(cdp, "1920-08-forge-applied.png")

        # ---- 7. 表格视图点击行 ----
        set_mode(cdp, "table")
        rows = cdp.eval("document.querySelectorAll('#gw-table2 .gw-tbl tbody tr').length")
        cdp.eval("(function(){var r=document.querySelector('#gw-table2 .gw-tbl tbody tr');"
                 "if(r){r.click();}})()")
        time.sleep(2.0)
        rep["table"] = {"rows": rows, "modeAfterRowClick": cdp.eval(JS_MODE)}
        set_mode(cdp, "build")

        rep["console"] = [c for c in cdp.console if c.get("level") == "error"] + cdp.console[:5]
        ext = [r["url"] for r in cdp.requests
               if not r["url"].startswith("http://127.0.0.1:8787") and not r["url"].startswith("devtools://")]
        rep["external"] = ext[:6]
    finally:
        proc.terminate()

    # ---- 8. 1264×705 ----
    proc, ws = launch(find_chrome(), 9392, 1264, 705,
                      os.path.join(os.environ.get("TEMP", "."), "r191b-%d" % os.getpid()))
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
        time.sleep(3.0)
        small = {"mode": cdp.eval(JS_MODE),
                 "cards": cdp.eval("document.querySelectorAll('#gw-browse .gw-card').length"),
                 "hscroll": hscroll(cdp),
                 "shot": shot(cdp, "1264-01-caliber.png")}
        shot(cdp, "ref-gun-caliber-vs-local.png", OUT_CMP)
        set_mode(cdp, "class")
        small["classShot"] = shot(cdp, "1264-02-class.png")
        set_mode(cdp, "table")
        small["tableShot"] = shot(cdp, "1264-03-table.png")
        cdp.eval("""
          (function(){
            var cards=document.querySelectorAll('#gw-browse .gw-card');
            for(var i=0;i<cards.length;i++){
              var s=cards[i].querySelector('span');
              if(s && /AK-74 5/.test(s.textContent)){ cards[i].click(); return; }
            }
          })()""")
        time.sleep(3.0)
        small["buildShot"] = shot(cdp, "1264-04-builder.png")
        shot(cdp, "ref-gun-builder-vs-local-1264.png", OUT_CMP)
        small["hscrollBuild"] = hscroll(cdp)
        rep["small"] = small
    finally:
        proc.terminate()

    out = os.path.join(ROOT, "docs", "r19-gun-builder", "_accept.json")
    json.dump(rep, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("accept ->", os.path.relpath(out, ROOT))
    print("mode:", rep.get("modeAfterPick"), "picked:", rep.get("picked"))
    print("parts:", rep.get("parts"), "bars:", rep.get("bars"), "candRows:", rep.get("candRows"))
    print("equip:", rep.get("equip"))
    print("remove:", rep.get("remove"), "partsAfterRemove:", rep.get("partsAfterRemove"))
    print("forge:", rep.get("forge"), rep.get("forgeApplied"), "parts:", rep.get("partsAfterForge"))
    print("filters:", rep.get("filters"))
    print("small:", rep.get("small"))
    print("console:", rep.get("console"))
    print("external:", rep.get("external"))


if __name__ == "__main__":
    main()
