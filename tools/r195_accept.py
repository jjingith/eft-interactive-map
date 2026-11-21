# -*- coding: utf-8 -*-
"""R19.5 验收：空间装配画布真实浏览器验收。

流程（AK-74 / M4A1 / MP5 每枪）：
  加载默认 → 断言画布分区正确（左链/右链/底带/rail 带 + 连接线）→
  点击 3 个不同分区槽位（右栏候选随之切换）→ 安装一个配件 →
  右键卸载 → 有子槽的配件安装（子卡出现）→ 恢复默认 → 切枪无残留。
另：1920/1264 双视口截图、参考图对照、修改前后对照。
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r181_accept import find_chrome, launch, CDP, wait_ready  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "r19.5-layout-audit", "screenshots")
os.makedirs(OUT, exist_ok=True)

JS_MODE = ("(function(){var b=document.querySelector('.gw-mode[data-on=\"1\"]');"
           "return b?b.dataset.gwmode:null;})()")


def pick_card(cdp, needle):
    """滚动到目标枪卡并真实点击；验证 gw-current 真正切换（最多重试 4 次）。

    注意：scrollIntoView 可能是动画滚动，坐标必须等滚动结束后在第二次求值里测，
    并用 elementFromPoint 确认点击点真的落在卡上（否则换 block:'start' 再试）。
    另：重载后 localStorage 会恢复 build 模式、浏览页隐藏——pick 前必须显式切到口径页。"""
    cdp.eval("(function(){var b=document.querySelector('.gw-mode[data-gwmode=\"caliber\"]');"
             "if(b)b.click();})()")
    time.sleep(1.2)
    for attempt in range(4):
        found = cdp.eval("""
          (function(){
            var cs=document.querySelectorAll('#gw-browse .gw-card');
            for(var i=0;i<cs.length;i++){
              var s=cs[i].querySelector('span');
              if(s && s.textContent.indexOf('%s')>=0){
                cs[i].scrollIntoView({block:'%s'});
                return s.textContent;
              }
            }
            return 'null';
          })()""" % (needle, "center" if attempt < 2 else "start"))
        if found == "null":
            return None
        time.sleep(1.2)   # 等滚动动画结束
        pos = cdp.eval("""
          (function(){
            var cs=document.querySelectorAll('#gw-browse .gw-card');
            for(var i=0;i<cs.length;i++){
              var s=cs[i].querySelector('span');
              if(s && s.textContent.indexOf('%s')>=0){
                var r=cs[i].getBoundingClientRect();
                return JSON.stringify({x:r.x+r.width/2, y:r.y+r.height/2, name:s.textContent});
              }
            }
            return 'null';
          })()""" % needle)
        pos = json.loads(pos) if pos and pos != "null" else None
        if not pos:
            return None
        hit = cdp.eval("""
          (function(){
            var e=document.elementFromPoint(%f, %f);
            return !!(e && e.closest && e.closest('#gw-browse .gw-card'));
          })()""" % (pos["x"], pos["y"]))
        if not hit:
            continue
        cdp.click_at(pos["x"], pos["y"])
        time.sleep(2.2)
        cur = cdp.eval("(document.getElementById('gw-current')||{}).textContent") or ""
        if needle.split(" ")[0] in cur:
            return pos["name"]
    return None


def slot_card_center(cdp, prefix):
    raw = cdp.eval("""
      (function(){
        var c=document.querySelector('.gw-part[data-slot^="%s"]');
        if(!c) return 'null';
        c.scrollIntoView({block:'center'});
        var r=c.getBoundingClientRect();
        return JSON.stringify({x:r.x+r.width/2, y:r.y+r.height/2,
          empty:c.classList.contains('gw-part-empty')});
      })()""" % prefix)
    return json.loads(raw) if raw and raw != "null" else None


def canvas_audit():
    JS = """
      (function(){
        var cv=document.querySelector('.gw-canvas'); if(!cv) return 'null';
        var cr=cv.getBoundingClientRect();
        var gun=document.querySelector('.gw-gun'); var gr=gun?gun.getBoundingClientRect():null;
        var links=document.querySelectorAll('.gw-canvas-links path').length;
        var rootCards=document.querySelectorAll('.gw-part-root').length;
        var subCards=document.querySelectorAll('.gw-part-sub').length;
        var emptyLabs=document.querySelectorAll('.gw-part-slotlab').length;
        function info(sel){
          var c=document.querySelector('.gw-part[data-slot^="'+sel+'"]');
          if(!c||!gr) return null;
          var r=c.getBoundingClientRect();
          return {leftOfGun:r.right<gr.left+2, rightOfGun:r.left>gr.right-2,
                  belowGun:r.top>gr.top+8, band:(function(){
                    var b=c.closest('.gw-band,.gw-band-rail');
                    return b?b.className.replace('gw-band ',''):null;})()};
        }
        return JSON.stringify({w:Math.round(cr.width), h:Math.round(cr.height),
          links:links, rootCards:rootCards, subCards:subCards, emptyLabs:emptyLabs,
          muzzle:info('mod_muzzle'), stock:info('mod_stock'), magazine:info('mod_magazine'),
          gasBlock:info('mod_gas_block'), mount:info('mod_mount'), receiver:info('mod_reciever'),
          overflowX: document.documentElement.scrollWidth>window.innerWidth+1,
          gunX:gr?Math.round(gr.left-cr.left):null, gunW:gr?Math.round(gr.width):null});
      })()"""
    return JS


def stats_snapshot():
    JS = """
      (function(){
        var out={parts:document.querySelectorAll('#gw-tree .gw-part').length,
                 focus:(function(){var f=document.querySelector('.gw-part-focus');
                   return f?f.dataset.slot:null;})(),
                 candRows:document.querySelectorAll('#gw-table .tbl-row').length,
                 bars:[].map.call(document.querySelectorAll('#gw-bars .gw-bar'),
                   function(b){return b.textContent.replace(/\\s+/g,' ').trim();})};
        return JSON.stringify(out);
      })()"""
    return JS


def run_viewport(cdp, W, H, rep):
    key = "v1920" if W >= 1900 else "v1264"
    rep[key] = {}
    R = rep[key]
    cdp.call("Emulation.setDeviceMetricsOverride", width=W, height=H,
             deviceScaleFactor=1, mobile=False)
    cdp.call("Page.navigate", url="http://127.0.0.1:8787/index.html")
    wait_ready(cdp, want_url="index.html")
    time.sleep(2.0)
    cdp.eval("try{localStorage.removeItem('eftmap.gwmode')}catch(e){}")
    cdp.eval("document.querySelector('[data-view=\"gun\"]').click()")
    time.sleep(2.5)

    # ---------- AK-74 ----------
    name = pick_card(cdp, "AK-74 5.45x39 突击步枪")
    R["ak74"] = {"picked": name, "mode": cdp.eval(JS_MODE),
                 "current": cdp.eval("(document.getElementById('gw-current')||{}).textContent")}
    time.sleep(1.0)
    R["ak74"]["canvas"] = json.loads(cdp.eval(canvas_audit()) or "null")
    shot = cdp.call("Page.captureScreenshot", format_="png")
    import base64
    with open(os.path.join(OUT, "p-1920-builder-ak74.png" if W >= 1900 else
                           "p-1264-builder-ak74.png"), "wb") as f:
        f.write(base64.b64decode(shot["data"]))

    # 点击 3 个不同分区槽位：mod_muzzle(左链) → mod_stock(右链) → mod_magazine(底带)
    flows = []
    for prefix in ("mod_muzzle", "mod_stock", "mod_magazine"):
        pos = slot_card_center(cdp, prefix)
        if not pos:
            flows.append({"slot": prefix, "missing": True})
            continue
        cdp.click_at(pos["x"], pos["y"])
        time.sleep(1.4)
        flows.append({"slot": prefix, "after": json.loads(cdp.eval(stats_snapshot()))})
    R["ak74"]["slotFlows"] = flows

    # 安装：当前焦点槽位（mod_magazine）点第一行候选；证据=焦点卡图标 URL 变化
    iconBefore = cdp.eval(
        "(function(){var c=document.querySelector('.gw-part-focus .gw-part-ic');"
        "return c?(c.getAttribute('src')||''):'';})()")
    row = cdp.eval("""
      (function(){
        var r=document.querySelector('#gw-table .tbl-row');
        if(!r) return 'null';
        r.scrollIntoView({block:'center'});
        var b=r.getBoundingClientRect();
        return JSON.stringify({x:b.x+b.width/2, y:b.y+b.height/2,
          name:(r.textContent||'').replace(/\\s+/g,' ').slice(0,40)});
      })()""")
    if row and row != "null":
        rc = json.loads(row)
        cdp.click_at(rc["x"], rc["y"])
        time.sleep(1.6)
    iconAfter = cdp.eval(
        "(function(){var c=document.querySelector('.gw-part-focus .gw-part-ic');"
        "return c?(c.getAttribute('src')||''):'';})()")
    R["ak74"]["install"] = {"row": json.loads(row) if row and row != "null" else None,
                            "iconChanged": iconBefore != iconAfter,
                            "iconAfter": (iconAfter or "").split("/").pop()[:36]}

    # 右键卸载（真实 CDP 右键）
    pos = slot_card_center(cdp, "mod_magazine")
    if pos and not pos["empty"]:
        cdp.call("Input.dispatchMouseEvent", type="mouseMoved", x=pos["x"], y=pos["y"])
        cdp.call("Input.dispatchMouseEvent", type="mousePressed", x=pos["x"], y=pos["y"],
                 button="right", clickCount=1)
        cdp.call("Input.dispatchMouseEvent", type="mouseReleased", x=pos["x"], y=pos["y"],
                 button="right", clickCount=1)
        time.sleep(1.6)
    R["ak74"]["afterRightClick"] = json.loads(cdp.eval(stats_snapshot()))
    shot = cdp.call("Page.captureScreenshot", format_="png")
    with open(os.path.join(OUT, "p-1920-after-rightclick.png" if W >= 1900 else
                           "p-1264-after-rightclick.png"), "wb") as f:
        f.write(base64.b64decode(shot["data"]))

    # 有子槽的配件：装 mod_reciever（AK-74 reciever 有子槽）
    pos = slot_card_center(cdp, "mod_reciever")
    if pos:
        cdp.click_at(pos["x"], pos["y"])
        time.sleep(1.4)
        row = cdp.eval("""
          (function(){
            var rows=[].slice.call(document.querySelectorAll('#gw-table .tbl-row'));
            var r=rows[rows.length-1];
            if(!r) return 'null';
            r.scrollIntoView({block:'center'});
            var b=r.getBoundingClientRect();
            return JSON.stringify({x:b.x+b.width/2, y:b.y+b.height/2});
          })()""")
        if row and row != "null":
            rc = json.loads(row)
            cdp.click_at(rc["x"], rc["y"])
            time.sleep(1.6)
    R["ak74"]["subCards"] = cdp.eval(
        "document.querySelectorAll('.gw-part-sub').length")

    # 恢复默认
    cdp.eval("document.getElementById('gw-default').click()")
    time.sleep(1.8)
    R["ak74"]["restored"] = json.loads(cdp.eval("""
      (function(){
        var tag=document.querySelector('.gw-gun .gw-hero-tag');
        return JSON.stringify({tag:tag?tag.textContent:null,
          parts:document.querySelectorAll('#gw-tree .gw-part').length});
      })()"""))

    # ---------- M4A1（切枪无残留 + 子槽验证） ----------
    cdp.eval("(function(){var b=document.querySelector('.gw-mode[data-gwmode=\"caliber\"]');"
             "if(b)b.click();})()")
    time.sleep(1.2)
    name = pick_card(cdp, "M4A1")
    R["m4a1"] = {"picked": name,
                 "current": cdp.eval("(document.getElementById('gw-current')||{}).textContent")}
    time.sleep(1.0)
    R["m4a1"]["canvas"] = json.loads(cdp.eval(canvas_audit()) or "null")
    R["m4a1"]["noResidue"] = cdp.eval("""
      (function(){
        var gname=(document.querySelector('.gw-gun-name')||{}).textContent||'';
        var hasAK=[].some.call(document.querySelectorAll('#gw-tree .gw-part'),
          function(c){return (c.dataset.slot||'').indexOf('mod_gas_block')===0;});
        return JSON.stringify({gun:gname, akGasBlockRoot:hasAK});
      })()""")

    # ---------- MP5 ----------
    cdp.eval("(function(){var b=document.querySelector('.gw-mode[data-gwmode=\"caliber\"]');"
             "if(b)b.click();})()")
    time.sleep(1.2)
    name = pick_card(cdp, "MP5")
    R["mp5"] = {"picked": name,
                 "current": cdp.eval("(document.getElementById('gw-current')||{}).textContent")}
    time.sleep(1.0)
    R["mp5"]["canvas"] = json.loads(cdp.eval(canvas_audit()) or "null")
    R["mp5"]["noResidue"] = cdp.eval("""
      (function(){
        var gname=(document.querySelector('.gw-gun-name')||{}).textContent||'';
        var m4Left=[].some.call(document.querySelectorAll('#gw-tree .gw-part'),
          function(c){return (c.dataset.slot||'').indexOf('mod_gas_block')===0;});
        return JSON.stringify({gun:gname, m4GasBlockRoot:m4Left});
      })()""")
    shot = cdp.call("Page.captureScreenshot", format_="png")
    with open(os.path.join(OUT, "p-1920-builder-mp5.png" if W >= 1900 else
                           "p-1264-builder-mp5.png"), "wb") as f:
        f.write(base64.b64decode(shot["data"]))

    # 全局检查
    R["global"] = cdp.eval("""
      (function(){
        return JSON.stringify({overflowX:document.documentElement.scrollWidth>window.innerWidth+1,
          errors:(window.__errs||[]).length,
          external:[].filter.call(performance.getEntriesByType('resource'),
            function(e){return !/^https?:\\/\\/127\\.0\\.0\\.1/.test(e.name)&&
                              e.name.indexOf('data:')!==0;}).length});
      })()""")
    shot = cdp.call("Page.captureScreenshot", format_="png")
    with open(os.path.join(OUT, "p-1920-full.png" if W >= 1900 else
                           "p-1264-full.png"), "wb") as f:
        f.write(base64.b64decode(shot["data"]))


def main():
    rep = {"console": [], "views": []}
    proc, ws = launch(find_chrome(), 9410, 1920, 1080,
                      os.path.join(os.environ.get("TEMP", "."), "r195-%d" % os.getpid()))
    try:
        cdp = CDP(ws)
        for m in ("Page.enable", "Runtime.enable", "Log.enable", "Network.enable"):
            cdp.call(m)
        run_viewport(cdp, 1920, 1080, rep)
        run_viewport(cdp, 1264, 705, rep)
        rep["console"] = (getattr(cdp, "console", None) or [])[:10]
    finally:
        proc.terminate()

    out = os.path.join(ROOT, "docs", "r19.5-layout-audit", "_accept.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=1)
    for key in ("v1920", "v1264"):
        R = rep.get(key) or {}
        a = R.get("ak74") or {}
        print("====", key, "====")
        print("ak74:", json.dumps({k: a.get(k) for k in ("picked", "current", "canvas")},
                                  ensure_ascii=False)[:500])
        print("flows:", json.dumps(a.get("slotFlows"), ensure_ascii=False)[:700])
        print("install:", a.get("install"), "rightclick:", a.get("afterRightClick"),
              "sub:", a.get("subCards"), "restored:", a.get("restored"))
        for g in ("m4a1", "mp5"):
            d = R.get(g) or {}
            print(g + ":", json.dumps({k: d.get(k) for k in ("picked", "current",
                  "canvas", "noResidue")}, ensure_ascii=False)[:600])
        print("global:", R.get("global"))
    print("console:", json.dumps(rep.get("console"), ensure_ascii=False)[:400])


if __name__ == "__main__":
    main()
