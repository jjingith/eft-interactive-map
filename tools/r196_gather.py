# -*- coding: utf-8 -*-
"""R19.6 参考站逆向采集 v2（只读）。

重要结论：db4tarkov /gun 是 **Flutter Web**（flutter-view + CanvasKit 渲染），
UI 全部画在 canvas 上，**没有可分析的 widget DOM/CSS**。可获取的最接近等价物是
Flutter 语义树（开启 accessibility 后由 flt-semantics 节点暴露 label + 真实边界）。

本脚本采集：
  1. 视口/环境
  2. 全量语义树（label + rect + role）→ 作为 dom-structure 与 geometry 的证据源
  3. 交互：点槽位 → 语义树变化 → 点候选 → 语义树变化（含属性/成本文本）
  4. 网络资源（performance entries）
  5. 每一步截图

输出 docs/r19.5-layout-audit/devtools-investigation/
"""
import base64
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r181_accept import CDP  # noqa: E402
from r196_devtools import launch_proxy  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "r19.5-layout-audit", "devtools-investigation")
SHOTS = os.path.join(OUT, "reference-screenshots")
os.makedirs(SHOTS, exist_ok=True)

SEM_DUMP = r"""
(function(){
  var ns=[].slice.call(document.querySelectorAll('flt-semantics'));
  var out=[];
  ns.forEach(function(e){
    var r=e.getBoundingClientRect();
    if(r.width<6||r.height<6) return;
    var depth=0,p=e.parentElement;
    while(p){ if(p.tagName && p.tagName.toLowerCase()==='flt-semantics') depth++; p=p.parentElement; }
    out.push({d:depth, label:(e.getAttribute('aria-label')||'').trim().slice(0,60),
      role:e.getAttribute('role')||'', x:Math.round(r.x), y:Math.round(r.y),
      w:Math.round(r.width), h:Math.round(r.height)});
  });
  return JSON.stringify(out);
})()
"""


def shot(cdp, name):
    r = cdp.call("Page.captureScreenshot", format_="png")
    with open(os.path.join(SHOTS, name), "wb") as f:
        f.write(base64.b64decode(r["data"]))
    print("  shot:", name)


def enable_semantics(cdp):
    cdp.eval("""(function(){
      var p=document.querySelector('flt-semantics-placeholder');
      if(p) p.click();
      return true;})()""")
    time.sleep(3.5)
    return cdp.eval("document.querySelectorAll('flt-semantics').length")


def sem(cdp):
    raw = cdp.eval(SEM_DUMP)
    return json.loads(raw) if raw else []


def find(nodes, re_txt, min_w=6):
    import re
    for n in nodes:
        if n["w"] >= min_w and re_txt.search(n["label"]):
            return n
    return None


def click_at(cdp, x, y, button="left"):
    cdp.call("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y)
    cdp.call("Input.dispatchMouseEvent", type="mousePressed", x=x, y=y,
             button=button, clickCount=1)
    cdp.call("Input.dispatchMouseEvent", type="mouseReleased", x=x, y=y,
             button=button, clickCount=1)


def key_values(nodes):
    """从语义标签里提取关键指标文本（属性/成本）。"""
    import re
    out = {}
    for pat, key in ((r"^OverSwing", "overSwing"), (r"^EvoErgo", "evoErgo"),
                     (r"^ArmStamina", "armStamina"), (r"^ADS Time", "adsTime"),
                     (r"^Final Cost", "finalCost"), (r"^Buy", "buy"),
                     (r"^Sell", "sell"), (r"^Ergonomics", "ergonomics"),
                     (r"^Velocity", "velocity"), (r"^Hor Recoil", "horRecoil"),
                     (r"^Ver Recoil", "verRecoil"), (r"^Accuracy", "accuracy")):
        n = find(nodes, re.compile(pat))
        if n:
            out[key] = n["label"]
    return out


def main():
    data = {}
    prof = os.path.join(os.environ.get("TEMP", "."), "r196v2-%d" % os.getpid())
    proc, ws = launch_proxy(9428, 1920, 919, prof)
    try:
        cdp = CDP(ws)
        for m in ("Page.enable", "Runtime.enable", "Network.enable"):
            cdp.call(m)
        cdp.call("Emulation.setDeviceMetricsOverride", width=1920, height=919,
                 deviceScaleFactor=1, mobile=False)
        cdp.call("Page.navigate", url="https://db4tarkov.com/gun")
        time.sleep(14)
        data["env"] = json.loads(cdp.eval(
            "JSON.stringify({w:innerWidth,h:innerHeight,dpr:devicePixelRatio,"
            "ua:navigator.userAgent,url:location.href})"))
        data["flutter"] = {
            "flutterView": bool(cdp.eval("!!document.querySelector('flutter-view')")),
            "glassPane": bool(cdp.eval("!!document.querySelector('flt-glass-pane')")),
            "bodyNodes": cdp.eval("document.body.querySelectorAll('*').length"),
            "canvases": cdp.eval("document.querySelectorAll('canvas').length"),
            "bodyInnerTextLen": cdp.eval("(document.body.innerText||'').length"),
            "scripts": cdp.eval(
                "JSON.stringify([].map.call(document.querySelectorAll('script[src]'),"
                "function(s){return s.src;}))"),
        }
        n = enable_semantics(cdp)
        print("semantics nodes:", n)
        data["semanticsCount"] = n
        shot(cdp, "01-enter.png")
        nodes = sem(cdp)
        data["sem1_enter"] = nodes
        k = key_values(nodes)
        print("enter keys:", json.dumps(k, ensure_ascii=False)[:260])

        # 若非工作台，点第一张 5.45 卡（用语义定位 AK-74 系标签）
        if not any("GENERATE BUILDS" in (x["label"] or "") for x in nodes):
            import re
            c = find(nodes, re.compile(r"AK-74"))
            print("ak node:", c)
            if c:
                click_at(cdp, c["x"] + c["w"] // 2, c["y"] + c["h"] // 2)
                time.sleep(6)
                nodes = sem(cdp)

        data["sem2_workbench"] = nodes
        data["keys2"] = key_values(nodes)
        shot(cdp, "02-workbench.png")

        # ---- 交互：点槽位（MUZZLE/SCOPE/STOCK 语义标签）----
        import re
        slot = find(nodes, re.compile(r"^(MUZZLE|SCOPE|STOCK|MAGAZINE|GRIP)$"))
        print("slot node:", slot)
        if slot:
            click_at(cdp, slot["x"] + slot["w"] // 2, slot["y"] + slot["h"] // 2)
            time.sleep(5)
        nodes3 = sem(cdp)
        data["sem3_afterSlot"] = nodes3
        data["keys3"] = key_values(nodes3)
        data["slotClicked"] = slot
        shot(cdp, "03-slot-clicked.png")

        # ---- 交互：点第一个候选（右侧面板内的条目语义）----
        cands = [x for x in nodes3 if x["x"] > 1000 and 24 <= x["h"] <= 60 and x["label"]]
        cand = cands[0] if cands else None
        print("first candidate:", cand)
        if cand:
            click_at(cdp, cand["x"] + min(120, cand["w"] // 2), cand["y"] + cand["h"] // 2)
            time.sleep(5)
        nodes4 = sem(cdp)
        data["sem4_afterPick"] = nodes4
        data["keys4"] = key_values(nodes4)
        data["candidatePicked"] = cand
        shot(cdp, "04-candidate-applied.png")

        # ---- 网络资源 ----
        res = cdp.eval("""
          (function(){
            var out=performance.getEntriesByType('resource').map(function(e){
              return {t:e.initiatorType, n:e.name, sz:e.transferSize||0};
            });
            var byType={}; out.forEach(function(r){byType[r.t]=(byType[r.t]||0)+1;});
            var pick=function(re){return out.filter(function(r){return re.test(r.n);})
              .slice(0,24).map(function(r){return r.n.replace(/^https?:\\/\\/[^/]+/,'')+' ('+r.sz+'B)';});};
            return JSON.stringify({total:out.length, byType:byType,
              main:pick(/main|flutter|canvaskit/), css:pick(/\\.css/),
              api:pick(/\\/api\\/|graphql|\\/_next\\/data/),
              img:p=null});
          })()""".replace(", img:p=null", ""))
        data["network"] = json.loads(res) if res else None
        print("network:", (data["network"] or {}).get("total"))
    finally:
        proc.terminate()

    with open(os.path.join(OUT, "semantics-raw.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print("saved semantics-raw.json")


if __name__ == "__main__":
    main()
