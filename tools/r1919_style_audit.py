# -*- coding: utf-8 -*-
"""R19.15 视觉审计：真实浏览器读取计算样式（字体/字号/背景/边框/圆角/间距/按钮状态）。

用法：
    python tools/r1919_style_audit.py --phase before
    python tools/r1919_style_audit.py --phase after
输出：docs/r19.15-theme-audit/style-audit-{phase}.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r181_accept import CDP, find_chrome, launch, wait_ready  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "r19.15-theme-audit")
os.makedirs(OUT, exist_ok=True)
URL = "http://127.0.0.1:8787/index.html"

PROBE = r"""
(function(){
  function g(el){ if(!el) return null; var s=getComputedStyle(el); var r=el.getBoundingClientRect();
    return {
      tag: el.tagName.toLowerCase(), cls: String(el.className||'').slice(0,60),
      font: s.fontFamily, size: s.fontSize, weight: s.fontWeight, lineHeight: s.lineHeight,
      color: s.color, bg: s.backgroundColor, bgImage: (s.backgroundImage||'').slice(0,60),
      border: s.borderTopWidth+' '+s.borderTopStyle+' '+s.borderTopColor,
      radius: s.borderTopLeftRadius, pad: s.padding, margin: s.margin,
      w: Math.round(r.width), h: Math.round(r.height)
    };}
  var out={};
  out.body = g(document.body);
  out.pageTitle = g(document.querySelector('.app-title, .topbar-title, h1'));
  out.navBtn = g(document.querySelector('[data-view]'));
  out.panel = g(document.querySelector('.xp-panel, .lw-panel, .gun-workbench, .am-workbench, .tbl, .gw-canvas'));
  out.tableHead = g(document.querySelector('.tbl-head, .tbl thead, .tbl-row.tbl-head'));
  out.tableCell = g(document.querySelector('.tbl-row .tbl-cell'));
  out.button = g(document.querySelector('button:not(:disabled)'));
  out.input = g(document.querySelector('input[type="text"], input:not([type])'));
  out.select = g(document.querySelector('select'));
  out.tab = g(document.querySelector('.gw-mode, .lw-tab, .am-tab'));
  // 圆角分布
  var hist={}, big=[];
  [].slice.call(document.querySelectorAll('*')).forEach(function(el){
    var s=getComputedStyle(el); var r=parseFloat(s.borderTopLeftRadius)||0;
    var k=r.toFixed(1); hist[k]=(hist[k]||0)+1;
    if(r>4 && el.getBoundingClientRect().width>40) big.push({cls:String(el.className||el.tagName).slice(0,50), r:r});
  });
  out.radiusHistogram = hist;
  out.bigRadiusCount = big.length;
  out.bigRadiusSample = big.slice(0,10);
  // 字号分布
  var sizes={};
  [].slice.call(document.querySelectorAll('*')).forEach(function(el){
    var s=getComputedStyle(el); var t=(el.textContent||'').trim();
    if(!t) return; sizes[s.fontSize]=(sizes[s.fontSize]||0)+1;
  });
  out.fontSizeHistogram = sizes;
  // 分数字号明细（用于区分地图 SVG 文本与 HTML 控件）
  var frac=[];
  [].slice.call(document.querySelectorAll('*')).forEach(function(el){
    var s=getComputedStyle(el); var tx=(el.textContent||'').trim();
    if(!tx || s.fontSize.indexOf('.')<0) return;
    frac.push({tag:el.tagName.toLowerCase(), cls:String(el.className||'').slice(0,40), size:s.fontSize});
  });
  out.fractionalSizes = frac.slice(0,40);
  out.fontFamilySet = (function(){
    var set={};
    [].slice.call(document.querySelectorAll('*')).forEach(function(el){
      var f=getComputedStyle(el).fontFamily; if(f) set[f]=(set[f]||0)+1;
    });
    return set;
  })();
  out.appSrc = (document.querySelector('script[src*="app.js"]')||{}).src||'';
  out.themeHref = (document.querySelector('link[href*="theme-windows-xp"]')||{}).href||'';
  return JSON.stringify(out);
})()
"""

HOVER_PROBE = r"""
(function(){
  var out={};
  function bg(el){ if(!el) return null; var s=getComputedStyle(el);
    return {bg:s.backgroundColor, img:(s.backgroundImage||'').slice(0,80), border:s.borderTopColor, color:s.color}; }
  out.before = bg(window.__hoverTarget);
  return JSON.stringify(out);
})()
"""


def pick_button(cdp):
    return cdp.eval(r"""(function(){
      var b=[].slice.call(document.querySelectorAll('button:not(:disabled)')).filter(function(x){
        var r=x.getBoundingClientRect(); return r.width>40 && r.height>18 && r.top>0;})[0];
      if(!b) return null;
      window.__hoverTarget=b;
      var r=b.getBoundingClientRect();
      return JSON.stringify({x:r.x+r.width/2,y:r.y+r.height/2,text:(b.textContent||'').trim().slice(0,20)});
    })()""")


def hover_state(cdp, pos):
    cdp.call("Input.dispatchMouseEvent", type="mouseMoved", x=pos["x"], y=pos["y"], button="none")
    time.sleep(0.45)
    return json.loads(cdp.eval(HOVER_PROBE) or "{}").get("before")


def click_state(cdp, pos):
    cdp.click_at(pos["x"], pos["y"])
    time.sleep(0.5)
    state = json.loads(cdp.eval(HOVER_PROBE) or "{}").get("before")
    # 移开鼠标，检查是否仍然保持高亮
    cdp.call("Input.dispatchMouseEvent", type="mouseMoved", x=4, y=4, button="none")
    time.sleep(0.5)
    after_move = json.loads(cdp.eval(HOVER_PROBE) or "{}").get("before")
    return {"onClick": state, "afterMouseLeave": after_move}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", default="before", choices=["before", "after"])
    ap.add_argument("--port", type=int, default=9550)
    args = ap.parse_args()

    proc, ws = launch(find_chrome(), args.port, 1920, 919,
                      os.path.join(os.environ.get("TEMP", "."), "r1919-" + args.phase))
    rep = {"phase": args.phase, "build": None, "views": {}, "buttons": {}, "console": []}
    try:
        cdp = CDP(ws)
        for mth in ("Page.enable", "Runtime.enable", "Log.enable", "Network.enable"):
            cdp.call(mth)
        cdp.call("Network.setCacheDisabled", cacheDisabled=True)
        cdp.call("Emulation.setDeviceMetricsOverride", width=1920, height=919,
                 deviceScaleFactor=1, mobile=False)
        cdp.call("Page.navigate", url=URL)
        wait_ready(cdp, want_url="index.html")
        time.sleep(2.5)

        rep["build"] = cdp.eval(
            "(function(){var x=new XMLHttpRequest();x.open('GET','/api/build',false);x.send();"
            "try{return JSON.parse(x.responseText).rev}catch(e){return ''}})()")
        rep["views"]["map"] = json.loads(cdp.eval(PROBE))

        # 各视图
        views = [("loadout", "配装"), ("gun", "配枪"), ("ammo", "弹药"), ("sim", "模拟")]
        for key, label in views:
            clicked = cdp.eval("""(function(){
              var b=document.querySelector('[data-view="%s"]');
              if(!b) return false; b.click(); return true;})()""" % key)
            time.sleep(1.6)
            rep["views"][key] = json.loads(cdp.eval(PROBE))
            rep["views"][key]["_clicked"] = bool(clicked)

        # 按钮三态：普通 / 悬停 / 点击后离开
        cdp.eval("""(function(){var b=document.querySelector('[data-view="gun"]'); if(b)b.click();})()""")
        time.sleep(1.2)
        pos_raw = pick_button(cdp)
        if pos_raw:
            pos = json.loads(pos_raw)
            rep["buttons"]["target"] = pos
            rep["buttons"]["normal"] = json.loads(cdp.eval(HOVER_PROBE) or "{}").get("before")
            cdp.call("Input.dispatchMouseEvent", type="mouseMoved", x=4, y=4, button="none")
            time.sleep(0.3)
            rep["buttons"]["hover"] = hover_state(cdp, pos)
            rep["buttons"]["click"] = click_state(cdp, pos)
        # 导航选中态
        cdp.eval("""(function(){var b=document.querySelector('[data-view="ammo"]'); if(b)b.click();})()""")
        time.sleep(1.2)
        rep["navSelected"] = json.loads(cdp.eval("""(function(){
          var b=document.querySelector('[data-view="ammo"]'); if(!b) return '{}';
          var s=getComputedStyle(b);
          return JSON.stringify({sel:b.getAttribute('aria-selected'), bg:s.backgroundColor,
            img:(s.backgroundImage||'').slice(0,80), color:s.color, border:s.borderTopColor});
        })()""") or "{}")

        cdp.drain()
        rep["console"] = cdp.console[:5]
    finally:
        try:
            proc.terminate()
        except Exception:
            pass

    path = os.path.join(OUT, "style-audit-%s.json" % args.phase)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=2)
    print("build:", rep.get("build"))
    for k, v in rep["views"].items():
        print(" view", k, "| font", (v.get("body") or {}).get("font", "")[:30],
              "| radiusHist", dict(list((v.get("radiusHistogram") or {}).items())[:6]),
              "| bigRadius", v.get("bigRadiusCount"))
    print(" buttons:", json.dumps(rep.get("buttons"), ensure_ascii=False)[:400])
    print(" nav:", json.dumps(rep.get("navSelected"), ensure_ascii=False)[:200])
    print("wrote", path)


if __name__ == "__main__":
    main()
