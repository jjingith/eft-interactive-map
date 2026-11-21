# -*- coding: utf-8 -*-
"""R20.7 参考站交互探针（只读探索用，不写业务代码）。

用途：连接受控 Chrome（CDP），对参考站点做「导航 / 等渲染 / 取语义标签 / 点击 / 局部截图」
这类取证动作，方便逐项核对 db4tarkov preset 界面的按钮行为。

设计原则：
  · 每次调用独立连接，页面状态留在浏览器里，便于人机交替逐步推进；
  · 不注入业务逻辑，只做最小必要的 DOM 读取（Flutter 站点读的是语义层 aria-label）；
  · 所有产物落在 docs/site-integration-audit/ 下，便于审计文档引用。

用法：
    python tools/r207_cdp.py nav https://db4tarkov.com/preset --wait 12
    python tools/r207_cdp.py aria --name after-load
    python tools/r207_cdp.py shot r207-01
    python tools/r207_cdp.py click 320 260 --wait 1.2
    python tools/r207_cdp.py eval tools/_r207_step1.js
    python tools/r207_cdp.py text
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r181_accept import CDP  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "site-integration-audit")
SHOTS = os.path.join(OUT, "screenshots")
RAW = os.path.join(OUT, "raw")

# Flutter 站点的语义树需要用户手势开启；未开启时 aria 只剩 "Enable accessibility"。
JS_SEMANTICS_ON = r"""(function(){
  var ph=document.querySelector('flt-semantics-placeholder');
  if(ph){ ph.click(); return 'clicked'; }
  return 'no-placeholder';})()"""

JS_ARIA = r"""(function(){
  var out=[];
  var els=document.querySelectorAll('[aria-label],[role]');
  for(var i=0;i<els.length;i++){
    var e=els[i];
    var lab=(e.getAttribute('aria-label')||'').replace(/\s+/g,' ').trim();
    if(!lab && e.children.length===0) lab=(e.textContent||'').replace(/\s+/g,' ').trim();
    if(!lab) continue;
    var r=e.getBoundingClientRect();
    if(r.width<2 || r.height<2) continue;
    out.push({role:e.getAttribute('role')||e.tagName.toLowerCase(), label:lab.slice(0,120),
              x:Math.round(r.left+r.width/2), y:Math.round(r.top+r.height/2),
              w:Math.round(r.width), h:Math.round(r.height)});
  }
  return JSON.stringify(out);})()"""

JS_TEXT = r"""(function(){
  var t=(document.body&&document.body.innerText)||'';
  return t.replace(/\n{2,}/g,'\n');})()"""


def connect(port):
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    tabs = json.load(op.open("http://127.0.0.1:%d/json/list" % port, timeout=5))
    page = next((t for t in tabs if t.get("type") == "page"), None)
    if not page:
        raise SystemExit("no page target on port %d" % port)
    cdp = CDP(page["webSocketDebuggerUrl"])
    for m in ("Page.enable", "Runtime.enable", "Log.enable", "Network.enable"):
        cdp.call(m)
    return cdp


def enable_semantics(cdp):
    try:
        if cdp.eval("JSON.stringify(!!document.querySelector('flutter-view, flt-glass-pane'))") == "true":
            r = cdp.eval(JS_SEMANTICS_ON)
            time.sleep(1.2)
            return r
    except Exception:  # noqa: BLE001
        pass
    return None


def cmd_nav(cdp, args):
    cdp.call("Page.navigate", url=args.target)
    time.sleep(args.wait)
    enable_semantics(cdp)
    print("url:", cdp.eval("location.href"))


def cmd_reload(cdp, args):
    # R30.0：--ignore-cache 用于改完 CSS/JS 后的**硬刷新**。
    # 站点 CSS 带 ?v=r19.30 之类的固定版本号，改了文件内容 URL 不变，
    # 普通 reload 会命中 HTTP 缓存拿到旧样式表（实测浏览器里的 cssRules
    # 与磁盘文件长度不一致），改动看起来「没生效」。
    cdp.call("Page.reload", ignoreCache=bool(getattr(args, "ignore_cache", False)))
    time.sleep(args.wait)
    enable_semantics(cdp)
    print("url:", cdp.eval("location.href"))


def cmd_shot(cdp, args):
    os.makedirs(SHOTS, exist_ok=True)
    p = {"format": "png", "captureBeyondViewport": False}
    if args.clip:
        x, y, w, h = (float(v) for v in args.clip.split(","))
        p["clip"] = {"x": x, "y": y, "width": w, "height": h, "scale": args.scale}
    data = base64.b64decode(cdp.call("Page.captureScreenshot", **p)["data"])
    path = os.path.join(SHOTS, args.name + ".png")
    with open(path, "wb") as f:
        f.write(data)
    print("shot:", os.path.relpath(path, ROOT).replace("\\", "/"), len(data), "bytes")


def cmd_aria(cdp, args):
    os.makedirs(RAW, exist_ok=True)
    enable_semantics(cdp)
    items = json.loads(cdp.eval(JS_ARIA) or "[]")
    if args.name:
        with open(os.path.join(RAW, "r207-aria-%s.json" % args.name), "w",
                  encoding="utf-8", newline="") as f:
            json.dump(items, f, ensure_ascii=False, indent=1)
    for i, a in enumerate(items):
        print("%3d %-14s (%4d,%4d) %dx%d  %s" % (i, a["role"], a["x"], a["y"], a["w"], a["h"], a["label"]))
    print("total", len(items))


def cmd_click(cdp, args):
    x, y = float(args.x), float(args.y)
    cdp.mouse(x, y)
    cdp.click_at(x, y)
    time.sleep(args.wait)
    print("clicked", x, y)


def cmd_eval(cdp, args):
    with open(args.file, encoding="utf-8") as f:
        expr = f.read()
    v = cdp.eval(expr, await_promise=args.promise)
    if args.name:
        os.makedirs(RAW, exist_ok=True)
        with open(os.path.join(RAW, "r207-eval-%s.json" % args.name), "w",
                  encoding="utf-8", newline="") as f:
            json.dump(v, f, ensure_ascii=False, indent=1)
    print(json.dumps(v, ensure_ascii=False, indent=1) if not isinstance(v, str) else v)


def cmd_text(cdp, args):
    print(cdp.eval(JS_TEXT))


def cmd_viewport(cdp, args):
    """R20.8：改视口尺寸（不改站点自己的分辨率设置）。

    db4 的插板列等「宽屏才出现」的布局判据是逻辑宽 > 1236，而受控 Chrome 的窗口
    视口常常只有 1080。用 CDP 的 Emulation 覆盖视口比去点站点的
    Change Site Resolution 更可靠，也不会把分辨率偏好写进站点存储。
    """
    cdp.call("Emulation.setDeviceMetricsOverride", width=args.w, height=args.h,
             deviceScaleFactor=1, mobile=False)
    time.sleep(args.wait)
    print("viewport:", cdp.eval("window.innerWidth + 'x' + window.innerHeight"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--connect", type=int, default=9401)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("nav")
    p.add_argument("target")
    p.add_argument("--wait", type=float, default=10.0)

    p = sub.add_parser("reload")
    p.add_argument("--wait", type=float, default=10.0)
    p.add_argument("--ignore-cache", dest="ignore_cache", action="store_true",
                   help="硬刷新：忽略 HTTP 缓存，重新拉取 CSS/JS")

    p = sub.add_parser("shot")
    p.add_argument("name")
    p.add_argument("--clip", default="")
    p.add_argument("--scale", type=float, default=2.0)

    p = sub.add_parser("aria")
    p.add_argument("--name", default="")

    p = sub.add_parser("click")
    p.add_argument("x")
    p.add_argument("y")
    p.add_argument("--wait", type=float, default=0.6)

    p = sub.add_parser("eval")
    p.add_argument("file")
    p.add_argument("--name", default="")
    p.add_argument("--promise", action="store_true")

    p = sub.add_parser("viewport")
    p.add_argument("w", type=int)
    p.add_argument("h", type=int)
    p.add_argument("--wait", type=float, default=1.5)

    sub.add_parser("text")

    args = ap.parse_args()
    cdp = connect(args.connect)
    {"nav": cmd_nav, "reload": cmd_reload, "shot": cmd_shot, "aria": cmd_aria,
     "click": cmd_click, "eval": cmd_eval, "text": cmd_text,
     "viewport": cmd_viewport}[args.cmd](cdp, args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
