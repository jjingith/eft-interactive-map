# -*- coding: utf-8 -*-
"""R19.6 参考站 DevTools 逆向分析（只读，不修改任何项目源文件）。

通过 CDP 对 https://db4tarkov.com/gun 做等价于 DevTools Elements/Computed/Network 的采集：
  1. 进入 Gun 工作台（点击 AK-74 卡片）
  2. 导出工作台 DOM 骨架（tag/class/rect/深度）
  3. 导出关键区域的计算样式（display/grid/gap/padding/overflow/font/...）
  4. 导出几何（getBoundingClientRect）
  5. 交互记录：点槽位 → 候选表变化 → 选配件 → 中央/属性/成本变化
  6. 网络资源清单（performance entries + CDP Network 事件）

输出：docs/r19.5-layout-audit/devtools-investigation/*.json + reference-screenshots/*.png
"""
import base64
import json
import os
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r181_accept import find_chrome, CDP  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "r19.5-layout-audit", "devtools-investigation")
SHOTS = os.path.join(OUT, "reference-screenshots")
os.makedirs(SHOTS, exist_ok=True)

PROXY = "http://127.0.0.1:7896"
AK74_ID = "5bf3e03b0db834001d2c4a9c"


def launch_proxy(port, w, h, profile):
    args = [find_chrome(), "--headless=new", "--remote-debugging-port=%d" % port,
            "--user-data-dir=%s" % profile, "--no-first-run", "--no-default-browser-check",
            "--disable-gpu", "--hide-scrollbars", "--disable-extensions",
            "--proxy-server=" + PROXY, "--proxy-bypass-list=127.0.0.1;localhost",
            "--disable-background-networking", "--disable-sync", "--disable-component-update",
            "--force-device-scale-factor=1", "--window-size=%d,%d" % (w, h), "about:blank"]
    proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ws_url = None
    for _ in range(160):
        time.sleep(0.25)
        try:
            with urllib.request.urlopen("http://127.0.0.1:%d/json/list" % port, timeout=2) as r:
                tabs = json.loads(r.read())
            for t in tabs:
                if t.get("type") == "page":
                    ws_url = t["webSocketDebuggerUrl"]
                    break
            if ws_url:
                break
        except Exception:
            continue
    if not ws_url:
        proc.terminate()
        raise SystemExit("Chrome CDP 未就绪")
    return proc, ws_url


def shot(cdp, name):
    r = cdp.call("Page.captureScreenshot", format_="png")
    with open(os.path.join(SHOTS, name), "wb") as f:
        f.write(base64.b64decode(r["data"]))
    print("  shot:", name)


# ---------------------------------------------------------------- DOM 骨架
DOM_DUMP_JS = r"""
(function(){
  // 以 LOAD VARIANT 文本为锚点，向上找到同时包含 FORGE 与候选搜索框的工作台根
  function upToCommon(el){
    var e=el;
    for(var i=0;i<12 && e;i++){
      if(e.querySelector && e.querySelector('input') &&
         /GENERATE BUILDS/.test(e.textContent||'') &&
         /LOAD VARIANT/.test(e.textContent||'')) return e;
      e=e.parentElement;
    }
    return document.body;
  }
  var anchors=[].slice.call(document.querySelectorAll('div,span,button,h1,h2'))
    .filter(function(e){return (e.textContent||'').trim().indexOf('LOAD VARIANT')===0;});
  var root=anchors.length?upToCommon(anchors[0]):document.body;
  var out=[];
  function walk(e,depth){
    if(depth>7 || out.length>420) return;
    var r=e.getBoundingClientRect();
    if(r.width<2||r.height<2) return;
    var cls=String(e.className||'').trim().split(/\s+/).slice(0,4).join('.');
    out.push({d:depth, tag:e.tagName.toLowerCase(), cls:cls.slice(0,80),
      x:Math.round(r.x), y:Math.round(r.y), w:Math.round(r.width), h:Math.round(r.height),
      txt:(e.childElementCount===0?(e.textContent||'').trim().slice(0,26):'')});
    for(var i=0;i<e.children.length && i<14;i++) walk(e.children[i],depth+1);
  }
  walk(root,0);
  return JSON.stringify({root:{tag:root.tagName, cls:String(root.className||'').slice(0,80),
    rect:(function(){var r=root.getBoundingClientRect();
      return [Math.round(r.x),Math.round(r.y),Math.round(r.width),Math.round(r.height)];})()},
    viewport:{w:innerWidth,h:innerHeight,dpr:devicePixelRatio},
    nodes:out});
})()
"""

# ------------------------------------------------- 计算样式（按文本锚点定位）
STYLE_JS = r"""
(function(){
  function findText(re, maxLen){
    var el=[].slice.call(document.querySelectorAll('div,span,button,h1,h2,h3,p,label,input'))
      .find(function(e){
        var t=(e.value!==undefined && e.tagName==='INPUT') ? (e.placeholder||'') : (e.textContent||'');
        t=t.trim();
        return re.test(t) && t.length<=(maxLen||60);
      });
    return el||null;
  }
  var PROPS=['display','position','boxSizing','gridTemplateColumns','gridTemplateRows','gap',
    'rowGap','columnGap','margin','padding','minWidth','maxWidth','minHeight','maxHeight',
    'overflow','overflowY','fontFamily','fontSize','fontWeight','lineHeight','backgroundColor',
    'borderTopWidth','borderColor','zIndex','flexDirection','alignItems','justifyContent',
    'height','width'];
  function snap(el){
    if(!el) return null;
    var cs=getComputedStyle(el);
    var r=el.getBoundingClientRect();
    var o={tag:el.tagName.toLowerCase(), cls:String(el.className||'').slice(0,90),
      rect:[Math.round(r.x),Math.round(r.y),Math.round(r.width),Math.round(r.height)], css:{}};
    PROPS.forEach(function(p){ o.css[p]=cs[p]; });
    return o;
  }
  function up(el,n){ var e=el; for(var i=0;i<(n||0)&&e;i++) e=e.parentElement; return e; }
  var loadvar=findText(/^LOAD VARIANT/);
  var forgeBtn=findText(/^GENERATE BUILDS$/);
  var ergo=findText(/^Ergonomics/);
  var overswing=findText(/^OverSwing/);
  var finalCost=findText(/^Final Cost/);
  var searchInput=[].slice.call(document.querySelectorAll('input'))
    .find(function(e){return /search/i.test(e.placeholder||'');});
  var buy=findText(/^Buy$/);
  var items=findText(/^ITEMS$/);
  var slotLabel=findText(/^(MUZZLE|SCOPE|STOCK|MAGAZINE)$/, 12);
  return JSON.stringify({
    loadvar:{self:snap(loadvar), parent:snap(up(loadvar,1)), gp:snap(up(loadvar,2))},
    forge:{btn:snap(forgeBtn), panel:snap(up(forgeBtn,4)), panel2:snap(up(forgeBtn,5))},
    bars:{label:snap(ergo), box:snap(up(ergo,1)), box2:snap(up(ergo,2)), box3:snap(up(ergo,3))},
    hidden:{label:snap(overswing), box:snap(up(overswing,1)), box2:snap(up(overswing,3))},
    cost:{label:snap(finalCost), box:snap(up(finalCost,1)), box2:snap(up(finalCost,3))},
    tabs:{buy:snap(buy), items:snap(items)},
    cands:{input:snap(searchInput), panel:snap(up(searchInput,3)), panel2:snap(up(searchInput,5))},
    slotLabel:snap(slotLabel)
  });
})()
"""

# ------------------------------------------------- 交互：候选表与属性快照
SNAP_JS = r"""
(function(){
  function txt(el,n){ return el?((el.textContent||'').replace(/\s+/g,' ').trim().slice(0,n||200)):null; }
  var canvasLike=[].slice.call(document.querySelectorAll('div'))
    .filter(function(e){
      var cs=getComputedStyle(e);
      return cs.backgroundImage && /radial-gradient|linear-gradient|url\(/.test(cs.backgroundImage) &&
             e.getBoundingClientRect().height>60 && e.getBoundingClientRect().height<400;
    });
  var rows=[].slice.call(document.querySelectorAll('div,tr'))
    .filter(function(e){
      var r=e.getBoundingClientRect();
      return r.height>20 && r.height<48 && r.width>500 &&
             /Ergo|Tier|Kg|₽|dps/i.test(e.textContent||'') && e.childElementCount>=2;
    }).slice(0,3);
  return JSON.stringify({
    url: location.href,
    candidates:{
      rowCount: rows.length ? (function(){
        var rc=rows[0].parentElement; return rc?rc.children.length:null;})() : 0,
      firstRows: rows.map(function(r){return txt(r,120);}),
      rowsRect: rows.map(function(r){var b=r.getBoundingClientRect();
        return [Math.round(b.x),Math.round(b.y),Math.round(b.width),Math.round(b.height)];})
    },
    statsText: txt(document.querySelector('body'),0) ? null : null,
    overSwing: txt([].slice.call(document.querySelectorAll('div,span'))
      .filter(function(e){return /^OverSwing/.test((e.textContent||'').trim());})[0], 80),
    finalCost: txt([].slice.call(document.querySelectorAll('div,span'))
      .filter(function(e){return /^Final Cost/.test((e.textContent||'').trim());})[0], 60),
    gunName: txt([].slice.call(document.querySelectorAll('div,span'))
      .filter(function(e){var t=(e.textContent||'').trim();
        return t.length<40 && /AK-74|M4A1|MP5/.test(t) && e.childElementCount<=1;})[0], 40),
    slotCards: [].slice.call(document.querySelectorAll('div'))
      .filter(function(e){
        var r=e.getBoundingClientRect();
        var t=(e.textContent||'').trim();
        return r.width>40 && r.width<90 && r.height>40 && r.height<90 &&
               /^[A-Z0-9 _\-]{3,16}$/.test(t);
      }).slice(0,12).map(function(e){var b=e.getBoundingClientRect();
        return {t:(e.textContent||'').trim(), x:Math.round(b.x), y:Math.round(b.y),
                w:Math.round(b.width), h:Math.round(b.height)};})
  });
})()
"""


def main():
    data = {}
    prof = os.path.join(os.environ.get("TEMP", "."), "r196-%d" % os.getpid())
    proc, ws = launch_proxy(9424, 1920, 919, prof)
    try:
        cdp = CDP(ws)
        for m in ("Page.enable", "Runtime.enable", "Network.enable", "Log.enable"):
            cdp.call(m)
        cdp.call("Emulation.setDeviceMetricsOverride", width=1920, height=919,
                 deviceScaleFactor=1, mobile=False)
        cdp.call("Page.navigate", url="https://db4tarkov.com/gun")
        time.sleep(12)
        data["viewport"] = cdp.eval(
            "JSON.stringify({w:innerWidth,h:innerHeight,dpr:devicePixelRatio,url:location.href})")
        print("caliber view:", data["viewport"])
        shot(cdp, "01-caliber-view.png")

        # 进入 AK-74 工作台：按基础图 id 找卡片
        entered = cdp.eval("""
          (function(){
            var img=document.querySelector('img[src*="%s"]');
            if(!img) return 'no-img';
            var e=img;
            for(var i=0;i<5 && e;i++){ e.click(); e=e.parentElement; }
            return 'clicked';
          })()""" % AK74_ID)
        print("enter:", entered)
        time.sleep(9)
        has = cdp.eval("!!document.body && /GENERATE BUILDS/.test(document.body.textContent||'')")
        data["workbenchLoaded"] = bool(has)
        print("workbench loaded:", has)
        if not has:
            # 兜底：坐标点击 5.45x39 行首卡（此前实测位置）
            cdp.call("Input.dispatchMouseEvent", type="mouseMoved", x=93, y=390)
            cdp.call("Input.dispatchMouseEvent", type="mousePressed", x=93, y=390,
                     button="left", clickCount=1)
            cdp.call("Input.dispatchMouseEvent", type="mouseReleased", x=93, y=390,
                     button="left", clickCount=1)
            time.sleep(10)
            data["workbenchLoaded"] = bool(cdp.eval(
                "!!document.body && /GENERATE BUILDS/.test(document.body.textContent||'')"))
            print("workbench loaded(retry):", data["workbenchLoaded"])
        shot(cdp, "02-workbench-ak74.png")

        # ---------- DOM 骨架 + 计算样式 + 几何 ----------
        dom = cdp.eval(DOM_DUMP_JS)
        data["dom"] = json.loads(dom) if dom else None
        styles = cdp.eval(STYLE_JS)
        data["styles"] = json.loads(styles) if styles else None
        print("dom nodes:", len((data["dom"] or {}).get("nodes", [])))

        # ---------- 交互 A：点击槽位 ----------
        data["snap0"] = json.loads(cdp.eval(SNAP_JS) or "{}")
        # 找可点击槽位卡（含 MUZZLE 等短标签的卡）
        slot = cdp.eval("""
          (function(){
            var cands=[].slice.call(document.querySelectorAll('div'))
              .filter(function(e){
                var r=e.getBoundingClientRect(); var t=(e.textContent||'').trim();
                return r.width>40 && r.width<90 && r.height>40 && r.height<90 &&
                       /^(MUZZLE|SCOPE|STOCK|MAGAZINE|GRIP)$/.test(t);
              });
            if(!cands.length) return 'none';
            var e=cands[0]; var r=e.getBoundingClientRect();
            e.click();
            return JSON.stringify({label:(e.textContent||'').trim(),
              x:Math.round(r.x+r.width/2), y:Math.round(r.y+r.height/2)});
          })()""")
        print("slot click:", slot)
        data["slotClicked"] = slot
        time.sleep(4)
        data["snap1_afterSlot"] = json.loads(cdp.eval(SNAP_JS) or "{}")
        shot(cdp, "03-slot-clicked.png")

        # ---------- 交互 B：选择第一个候选配件 ----------
        pick = cdp.eval("""
          (function(){
            var rows=[].slice.call(document.querySelectorAll('div,tr'))
              .filter(function(e){var r=e.getBoundingClientRect();
                return r.height>20 && r.height<48 && r.width>500 &&
                       /Ergo/i.test(e.textContent||'');});
            if(!rows.length) return 'no-rows';
            var e=rows[0]; var r=e.getBoundingClientRect();
            e.click();
            return JSON.stringify({x:Math.round(r.x+r.width/2),y:Math.round(r.y+r.height/2),
              text:(e.textContent||'').replace(/\\s+/g,' ').slice(0,90)});
          })()""")
        print("pick candidate:", pick)
        data["candidatePicked"] = pick
        time.sleep(4)
        data["snap2_afterPick"] = json.loads(cdp.eval(SNAP_JS) or "{}")
        shot(cdp, "04-candidate-applied.png")

        # ---------- 网络资源 ----------
        res = cdp.eval("""
          (function(){
            var out=performance.getEntriesByType('resource').map(function(e){
              return {t:e.initiatorType, n:e.name.replace(/^https?:\\/\\/[^/]+/,''), sz:e.transferSize};
            });
            var byType={};
            out.forEach(function(r){byType[r.t]=(byType[r.t]||0)+1;});
            var js=out.filter(function(r){return /\\.js/.test(r.n);}).slice(0,20);
            var css=out.filter(function(r){return /\\.css/.test(r.n);}).slice(0,10);
            var api=out.filter(function(r){return /\\/api\\/|graphql|\\/_next\\/data/.test(r.n);}).slice(0,20);
            return JSON.stringify({total:out.length, byType:byType, js:js, css:css, api:api});
          })()""")
        data["network"] = json.loads(res) if res else None
        print("network entries:", (data["network"] or {}).get("total"))
    finally:
        proc.terminate()

    with open(os.path.join(OUT, "raw-analysis.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print("saved raw-analysis.json")


if __name__ == "__main__":
    main()
