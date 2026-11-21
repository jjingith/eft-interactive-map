# -*- coding: utf-8 -*-
"""R20 Flutter 站点流程探针：单次加载 + 站内点击导航（不刷新页面）。

db4tarkov.com 是 Flutter Web：每次 URL 导航都会重新初始化并重新下载数据，
因此审计必须「加载一次 → 点导航 → 截图/取语义」的 SPA 内部路由方式。

用法：
    python tools/r20_flow_probe.py --connect 9333 --url https://db4tarkov.com/gun \
        --labels MARKET,SEASON,QUEST,KEEP,PRESET,AMMO,MAP,BARTER,CRAFT,CHANGES,LOGS \
        --prefix db4 --wait 30 --step-wait 5

产物：docs/site-integration-audit/raw/<prefix>-flow.json + screenshots/<prefix>-<label>.png
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
from r181_accept import CDP  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "site-integration-audit")
SHOTS = os.path.join(OUT, "screenshots")
RAW = os.path.join(OUT, "raw")

JS_ENABLE = r"""(function(){var p=document.querySelector('flt-semantics-placeholder');
  if(p){p.click();return 'clicked';}return 'none';})()"""

JS_ARIA = r"""(function(){
  var out=[],seen={};
  var els=document.querySelectorAll('[aria-label]');
  for(var i=0;i<els.length && out.length<600;i++){
    var l=(els[i].getAttribute('aria-label')||'').replace(/\s+/g,' ').trim();
    if(!l) continue;
    var r=els[i].getAttribute('role')||els[i].tagName.toLowerCase();
    var k=r+'|'+l; if(seen[k]) continue; seen[k]=1;
    out.push({role:r,label:l.slice(0,120)});
  }
  return JSON.stringify(out);})()"""


def connect(port):
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    tabs = json.load(op.open("http://127.0.0.1:%d/json/list" % port, timeout=5))
    page = next(t for t in tabs if t.get("type") == "page")
    return CDP(page["webSocketDebuggerUrl"])


def click_label(cdp, label):
    return cdp.eval(r"""(function(){
      var els=document.querySelectorAll('[aria-label]');
      for(var i=0;i<els.length;i++){
        var l=(els[i].getAttribute('aria-label')||'').trim();
        if(l===%s){ els[i].click(); return 'clicked'; }
      }
      for(var j=0;j<els.length;j++){
        var l2=(els[j].getAttribute('aria-label')||'').trim();
        if(l2.indexOf(%s)===0){ els[j].click(); return 'prefix'; }
      }
      return 'notfound';})()""" % (json.dumps(label, ensure_ascii=False),
                                   json.dumps(label, ensure_ascii=False)))


def shot(cdp, name):
    png = base64.b64decode(cdp.call("Page.captureScreenshot", format_="png",
                                    captureBeyondViewport=False)["data"])
    with open(os.path.join(SHOTS, name + ".png"), "wb") as f:
        f.write(png)
    return len(png)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--connect", type=int, required=True)
    ap.add_argument("--url", required=True)
    ap.add_argument("--labels", required=True)
    ap.add_argument("--prefix", required=True)
    ap.add_argument("--wait", type=float, default=30)
    ap.add_argument("--step-wait", type=float, default=5)
    ap.add_argument("--points", default="", help="LABEL:x,y;LABEL:x,y（canvas 站点按坐标点击）")
    args = ap.parse_args()
    os.makedirs(SHOTS, exist_ok=True)
    os.makedirs(RAW, exist_ok=True)

    cdp = connect(args.connect)
    for m in ("Page.enable", "Runtime.enable", "Log.enable", "Network.enable"):
        cdp.call(m)
    cdp.call("Emulation.setDeviceMetricsOverride", width=1600, height=1000, deviceScaleFactor=1, mobile=False)
    cdp.call("Page.navigate", url=args.url)
    time.sleep(args.wait)
    print("enable:", cdp.eval(JS_ENABLE))
    time.sleep(1.5)

    steps = []
    base = {"url": cdp.eval("location.href"), "title": cdp.eval("document.title"),
            "aria": json.loads(cdp.eval(JS_ARIA) or "[]")}
    base["shot_bytes"] = shot(cdp, args.prefix + "-base")
    base["shot"] = "screenshots/%s-base.png" % args.prefix
    steps.append({"step": "base", **base})

    pts = {}
    for part in [x for x in args.points.split(";") if ":" in x]:
        k, v = part.split(":", 1)
        xy = v.split(",")
        pts[k.strip()] = (float(xy[0]), float(xy[1]))

    for label in [x.strip() for x in args.labels.split(",") if x.strip()]:
        before = cdp.eval("location.href")
        if label in pts:
            cdp.click_at(pts[label][0], pts[label][1])
            r = "click(xy)"
        else:
            r = click_label(cdp, label)
        time.sleep(args.step_wait)
        cur = cdp.eval("location.href")
        aria = json.loads(cdp.eval(JS_ARIA) or "[]")
        name = "%s-%s" % (args.prefix, re.sub(r"[^A-Za-z0-9]+", "", label) or "x")
        n = shot(cdp, name)
        labels = [a["label"] for a in aria]
        print("%-10s click=%-9s url=%s->%s  aria=%d  shot=%dB" %
              (label, r, (before or "")[-24:], (cur or "")[-24:], len(aria), n))
        print("     ", " | ".join(labels[:16]))
        steps.append({"step": label, "click": r, "url_before": before, "url": cur,
                      "title": cdp.eval("document.title"), "aria": aria,
                      "shot": "screenshots/%s.png" % name, "shot_bytes": n})

    reqs = cdp.requests
    hosts = {}
    for x in reqs:
        h = re.sub(r"^https?://([^/:]+).*", r"\1", x["url"])
        hosts[h] = hosts.get(h, 0) + 1
    payload = {"prefix": args.prefix, "start_url": args.url, "steps": steps,
               "requests": len(reqs), "hosts": hosts}
    with open(os.path.join(RAW, args.prefix + "-flow.json"), "w", encoding="utf-8", newline="") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    print("\nhosts:", dict(sorted(hosts.items(), key=lambda kv: -kv[1])[:10]))
    print("requests:", len(reqs), "->", "raw/%s-flow.json" % args.prefix)
    return 0


if __name__ == "__main__":
    sys.exit(main())
