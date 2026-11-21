# -*- coding: utf-8 -*-
"""R20 站点研究探针（只读）。

用途：用受控 Chrome（CDP）打开参考网站的任意页面，采集
  · 标题 / 最终 URL / 是否重定向
  · 截图（视口 PNG，落盘）
  · 可访问性标签（对 Flutter Web 站点先点开 semantics 占位符）
  · 链接 / 按钮 / 输入框清单
  · 网络请求（url / type / status）
  · 控制台错误
并写出一份 JSON 供审计文档引用。**不修改目标站点任何状态，不登录，不绕过任何访问控制。**

用法：
    python tools/r20_site_probe.py --url https://db4tarkov.com/ --name db4-home --wait 10
    python tools/r20_site_probe.py --url https://www.eftarkov.com/task/xxx --name eft-task --wait 6
    python tools/r20_site_probe.py --connect 9333 --url ... （复用已有 Chrome）

产物：
    docs/site-integration-audit/screenshots/<name>.png
    docs/site-integration-audit/raw/<name>.json
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r181_accept import CDP, find_chrome, launch  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "site-integration-audit")
SHOTS = os.path.join(OUT, "screenshots")
RAW = os.path.join(OUT, "raw")

JS_LINKS = r"""(function(){
  var out=[], seen={};
  var as=document.querySelectorAll('a[href]');
  for(var i=0;i<as.length && out.length<400;i++){
    var a=as[i], t=(a.textContent||'').replace(/\s+/g,' ').trim().slice(0,80);
    var h=a.getAttribute('href')||'';
    if(!h || h.charAt(0)==='#') continue;
    var k=h+'|'+t; if(seen[k]) continue; seen[k]=1;
    out.push({href:h, text:t, title:(a.getAttribute('title')||'').slice(0,80)});
  }
  return JSON.stringify(out);
})()"""

JS_ARIA = r"""(function(){
  var out=[], seen={};
  var els=document.querySelectorAll('[aria-label],[role="button"],[role="tab"],[role="link"],[data-semantics-role]');
  for(var i=0;i<els.length && out.length<400;i++){
    var e=els[i];
    var lab=(e.getAttribute('aria-label')||e.textContent||'').replace(/\s+/g,' ').trim().slice(0,80);
    var role=e.getAttribute('role')||e.tagName.toLowerCase();
    if(!lab) continue;
    var k=role+'|'+lab; if(seen[k]) continue; seen[k]=1;
    out.push({role:role, label:lab});
  }
  return JSON.stringify(out);})()"""

JS_META = r"""(function(){
  var d={};
  d.url=location.href; d.title=document.title;
  d.ready=document.readyState;
  d.textLen=(document.body&&document.body.innerText||'').length;
  d.htmlLen=(document.body&&document.body.innerHTML||'').length;
  d.canvas=document.querySelectorAll('canvas').length;
  d.flutter=!!document.querySelector('flutter-view, flt-glass-pane');
  d.btn=document.querySelectorAll('button,[role="button"]').length;
  d.input=document.querySelectorAll('input,select,textarea').length;
  d.table=document.querySelectorAll('table').length;
  d.ls=(function(){try{return Object.keys(localStorage).slice(0,30);}catch(e){return [];}})();
  d.meta=(function(){var m=document.querySelector('meta[name="description"]');
    return m?m.getAttribute('content'):'';})();
  return JSON.stringify(d);})()"""

JS_SEMANTICS_ON = r"""(function(){
  var ph=document.querySelector('flt-semantics-placeholder');
  if(ph){ ph.click(); return 'clicked'; }
  return 'no-placeholder';})()"""


def connect(port):
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    tabs = json.load(op.open("http://127.0.0.1:%d/json/list" % port, timeout=5))
    page = next((t for t in tabs if t.get("type") == "page"), None)
    if not page:
        raise SystemExit("no page target on port %d" % port)
    return CDP(page["webSocketDebuggerUrl"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--wait", type=float, default=8.0)
    ap.add_argument("--connect", type=int, default=0, help="复用已有 Chrome 的调试端口")
    ap.add_argument("--semantics", action="store_true", help="Flutter 站点：先点开 semantics 占位符")
    ap.add_argument("--viewport", default="1600x1000")
    args = ap.parse_args()
    os.makedirs(SHOTS, exist_ok=True)
    os.makedirs(RAW, exist_ok=True)
    w, h = (int(x) for x in args.viewport.lower().split("x"))

    proc = None
    if args.connect:
        cdp = connect(args.connect)
        cdp.call("Emulation.setDeviceMetricsOverride", width=w, height=h, deviceScaleFactor=1, mobile=False)
    else:
        port = 9400 + (abs(hash(args.name)) % 200)
        prof = os.path.join(os.environ.get("TEMP", "."), "r20probe_%d" % port)
        proc, ws = launch(find_chrome(), port, w, h, prof)
        cdp = CDP(ws)

    rep = {"name": args.name, "requested_url": args.url, "viewport": [w, h], "errors": []}
    try:
        for m in ("Page.enable", "Runtime.enable", "Log.enable", "Network.enable"):
            cdp.call(m)
        cdp.call("Network.setCacheDisabled", cacheDisabled=True)
        cdp.call("Emulation.setDeviceMetricsOverride", width=w, height=h, deviceScaleFactor=1, mobile=False)
        cdp.call("Page.navigate", url=args.url)
        time.sleep(args.wait)

        if args.semantics:
            rep["semantics_click"] = cdp.eval(JS_SEMANTICS_ON)
            time.sleep(1.5)
        # Flutter 站点每次导航都会重置语义树：自动再点开一次，否则 aria 只剩 "Enable accessibility"
        if json.loads(cdp.eval("JSON.stringify(!!document.querySelector('flutter-view, flt-glass-pane'))") or "false"):
            rep["semantics_auto"] = cdp.eval(JS_SEMANTICS_ON)
            time.sleep(1.5)

        meta = json.loads(cdp.eval(JS_META) or "{}")
        rep.update(meta)
        rep["links"] = json.loads(cdp.eval(JS_LINKS) or "[]")
        rep["aria"] = json.loads(cdp.eval(JS_ARIA) or "[]")
        rep["requests"] = [{"url": r["url"], "host": re.sub(r"^https?://([^/:]+).*", r"\1", r["url"])}
                           for r in cdp.requests][:400]
        rep["console"] = cdp.console[:20]

        png = base64.b64decode(cdp.call("Page.captureScreenshot", format_="png",
                                        captureBeyondViewport=False)["data"])
        with open(os.path.join(SHOTS, args.name + ".png"), "wb") as f:
            f.write(png)
        rep["screenshot"] = "screenshots/%s.png" % args.name
        rep["screenshot_bytes"] = len(png)
    except Exception as exc:                       # noqa: BLE001
        rep["errors"].append("%s: %s" % (type(exc).__name__, str(exc)[:300]))
    finally:
        with open(os.path.join(RAW, args.name + ".json"), "w", encoding="utf-8", newline="") as f:
            json.dump(rep, f, ensure_ascii=False, indent=1)
        if proc is not None:
            try:
                proc.terminate()
            except Exception:                      # noqa: BLE001
                pass

    hosts = {}
    for r in rep.get("requests", []):
        hosts[r["host"]] = hosts.get(r["host"], 0) + 1
    print("=" * 70)
    print("name     :", args.name)
    print("url      :", rep.get("url", "?"), "| title:", rep.get("title", "?"))
    print("dom      : text=%s html=%s canvas=%s flutter=%s table=%s" % (
        rep.get("textLen"), rep.get("htmlLen"), rep.get("canvas"), rep.get("flutter"), rep.get("table")))
    print("controls : links=%d aria=%d btn=%s input=%s" % (
        len(rep.get("links", [])), len(rep.get("aria", [])), rep.get("btn"), rep.get("input")))
    print("hosts    :", dict(sorted(hosts.items(), key=lambda kv: -kv[1])[:8]))
    print("shot     :", rep.get("screenshot"), rep.get("screenshot_bytes"), "bytes")
    if rep.get("errors"):
        print("ERRORS   :", rep["errors"])
    labels = [a["label"] for a in rep.get("aria", [])][:25]
    if labels:
        print("aria[25] :", " | ".join(labels))
    texts = ["%s -> %s" % (l["text"][:26], l["href"][:60]) for l in rep.get("links", [])][:25]
    if texts:
        print("links[25]:")
        for t in texts:
            print("   ", t)
    return 0


if __name__ == "__main__":
    sys.exit(main())
