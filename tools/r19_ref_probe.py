# -*- coding: utf-8 -*-
"""R19 参考站探测：用真实 Chrome（走用户指定代理）打开 db4tarkov.com/gun，
记录 DOM 结构、可见控件、截图，供 reference-audit.md 使用。

与 r181_accept.py 的区别：那个脚本用 --no-proxy-server（只测本地页面），
这里必须走代理访问外网；CDP 本身仍然直连 127.0.0.1。

用法：
    python tools/r19_ref_probe.py --out docs/r19-gun-builder/reference
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r181_accept import CDP, find_chrome  # 复用 WebSocket / CDP 实现

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROXY = "http://127.0.0.1:7896"


def launch_proxied(chrome, port, w, h, profile, proxy=PROXY):
    args = [chrome, "--headless=new", "--remote-debugging-port=%d" % port,
            "--user-data-dir=%s" % profile, "--no-first-run", "--no-default-browser-check",
            "--disable-gpu", "--hide-scrollbars", "--disable-extensions",
            # 外网走代理，本机/CDP 直连（否则 127.0.0.1:port 也会被代理劫持）
            "--proxy-server=%s" % proxy,
            "--proxy-bypass-list=127.0.0.1;localhost;::1",
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


JS_SNAPSHOT = r"""
(function () {
  function txt(el) { return (el.innerText || el.textContent || "").replace(/\s+/g, " ").trim(); }
  function vis(el) {
    var r = el.getBoundingClientRect();
    var cs = getComputedStyle(el);
    return r.width > 2 && r.height > 2 && cs.display !== "none" && cs.visibility !== "hidden"
      && cs.opacity !== "0";
  }
  var out = {
    url: location.href,
    title: document.title,
    bodyLen: (document.body.innerText || "").length,
    bodyHead: txt(document.body).slice(0, 900),
    buttons: [], inputs: [], selects: [], links: [], tabs: [], canvases: [],
    counts: {}
  };
  document.querySelectorAll("button, [role=button], a.btn, .btn").forEach(function (b) {
    if (!vis(b)) { return; }
    if (out.buttons.length < 120) {
      out.buttons.push({t: txt(b).slice(0, 48), cls: String(b.className).slice(0, 70),
                        tag: b.tagName, aria: b.getAttribute("aria-label") || ""});
    }
  });
  document.querySelectorAll("input").forEach(function (i) {
    if (!vis(i)) { return; }
    if (out.inputs.length < 40) {
      out.inputs.push({type: i.type, ph: i.placeholder || "", aria: i.getAttribute("aria-label") || "",
                       cls: String(i.className).slice(0, 60)});
    }
  });
  document.querySelectorAll("select").forEach(function (s) {
    if (!vis(s)) { return; }
    if (out.selects.length < 40) {
      out.selects.push({cls: String(s.className).slice(0, 60),
                        opts: Array.prototype.slice.call(s.options, 0, 8).map(function (o) { return o.textContent.trim(); })});
    }
  });
  document.querySelectorAll("a[href]").forEach(function (a) {
    if (!vis(a)) { return; }
    if (out.links.length < 60) {
      out.links.push({t: txt(a).slice(0, 40), href: a.getAttribute("href")});
    }
  });
  document.querySelectorAll("[role=tab], .tab, .mat-tab-label, .nav-link").forEach(function (t) {
    if (!vis(t)) { return; }
    if (out.tabs.length < 40) { out.tabs.push({t: txt(t).slice(0, 40), cls: String(t.className).slice(0, 60)}); }
  });
  document.querySelectorAll("canvas").forEach(function (c) {
    var r = c.getBoundingClientRect();
    out.canvases.push({w: c.width, h: c.height, css: Math.round(r.width) + "x" + Math.round(r.height)});
  });
  ["table", "svg", "img", "canvas", "select", "input", "button", "mat-select", "mat-option"]
    .forEach(function (tag) { out.counts[tag] = document.querySelectorAll(tag).length; });
  out.textSample = txt(document.body).slice(0, 3000);
  return JSON.stringify(out);
})()
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "docs", "r19-gun-builder", "reference"))
    ap.add_argument("--url", default="https://db4tarkov.com/gun")
    ap.add_argument("--cdp-port", type=int, default=9366)
    ap.add_argument("--wait", type=float, default=18.0)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    proc = None
    try:
        proc, ws = launch_proxied(find_chrome(), a.cdp_port, 1600, 1000,
                                  os.path.join(os.environ.get("TEMP", "."), "r19ref-%d" % os.getpid()))
        cdp = CDP(ws)
        for m in ("Page.enable", "Runtime.enable", "Network.enable", "Log.enable"):
            cdp.call(m)
        cdp.call("Emulation.setDeviceMetricsOverride", width=1600, height=1000,
                 deviceScaleFactor=1, mobile=False)
        cdp.call("Page.navigate", url=a.url)
        # SPA：等 body 出现内容（初次访问可能有缓存初始化提示）
        deadline = time.time() + a.wait
        last = ""
        while time.time() < deadline:
            time.sleep(1.0)
            try:
                n = cdp.eval("(document.body && document.body.innerText || '').length")
            except Exception:
                n = 0
            if n and n > 200:
                break
        time.sleep(2.0)
        snap = json.loads(cdp.eval(JS_SNAPSHOT))
        with open(os.path.join(a.out, "dom-snapshot.json"), "w", encoding="utf-8") as f:
            json.dump(snap, f, ensure_ascii=False, indent=1)

        path = os.path.join(a.out, "01-gun-landing.png")
        data = base64.b64decode(cdp.call("Page.captureScreenshot", format="png")["data"])
        with open(path, "wb") as f:
            f.write(data)

        print("url:", snap["url"])
        print("title:", snap["title"])
        print("bodyLen:", snap["bodyLen"])
        print("counts:", snap["counts"])
        print("buttons:", len(snap["buttons"]), "inputs:", len(snap["inputs"]),
              "selects:", len(snap["selects"]), "links:", len(snap["links"]))
        print("body head:", snap["bodyHead"][:500].replace("\n", " "))
        print("截图:", os.path.relpath(path, ROOT))
        print("网络事件:", len(cdp.requests))
    finally:
        if proc:
            try:
                proc.terminate()
            except Exception:
                pass


if __name__ == "__main__":
    main()
