# -*- coding: utf-8 -*-
"""R19 参考站走查：启用 Flutter 语义树 -> 按语义节点精确定位 -> 逐步截图 + dump。

db4tarkov 是 Flutter Web，正常 DOM 里没有内容；点击 flt-semantics-placeholder
启用无障碍树后，每个按钮/输入框都会变成带 aria-label 和精确 rect 的 <flt-semantics>，
于是可以像操作普通网页一样定位与点击。

用法：
    python tools/r19_walk.py --plan open,search:AK-74,pick0,shot:gun-builder
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r181_accept import CDP, find_chrome  # noqa: E402
from r19_ref_probe import launch_proxied  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

JS_SEM = r"""
(function () {
  var out = [];
  document.querySelectorAll('flt-semantics,[role],[aria-label],input,button').forEach(function (e) {
    var t = (e.getAttribute('aria-label') || e.textContent || '').replace(/\s+/g, ' ').trim();
    if (!t && e.tagName !== 'INPUT') { return; }
    var r = e.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) { return; }
    out.push({t: t.slice(0, 60), role: e.getAttribute('role') || '', tag: e.tagName,
              x: Math.round(r.x), y: Math.round(r.y),
              w: Math.round(r.width), h: Math.round(r.height)});
  });
  return JSON.stringify(out);
})()
"""


class Ref:
    def __init__(self, cdp, out_dir):
        self.cdp = cdp
        self.out = out_dir
        self.sem = []

    def refresh(self, wait=0.9):
        time.sleep(wait)
        self.sem = json.loads(self.cdp.eval(JS_SEM) or "[]")
        return self.sem

    def find(self, text, exact=False, role=None):
        t = text.lower()
        for s in self.sem:
            if role and s["role"] != role:
                continue
            if (s["t"].lower() == t) if exact else (t in s["t"].lower()):
                return s
        return None

    def center(self, node):
        return node["x"] + node["w"] // 2, node["y"] + node["h"] // 2

    def click_node(self, node, wait=1.4):
        x, y = self.center(node)
        self.click(x, y, wait)

    def click(self, x, y, wait=1.4):
        self.cdp.call("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y,
                      button="none", clickCount=0)
        self.cdp.call("Input.dispatchMouseEvent", type="mousePressed", x=x, y=y,
                      button="left", clickCount=1)
        self.cdp.call("Input.dispatchMouseEvent", type="mouseReleased", x=x, y=y,
                      button="left", clickCount=1)
        time.sleep(wait)

    def shot(self, name):
        p = os.path.join(self.out, name if name.endswith(".png") else name + ".png")
        data = base64.b64decode(self.cdp.call("Page.captureScreenshot", format="png")["data"])
        with open(p, "wb") as f:
            f.write(data)
        print("   shot ->", os.path.relpath(p, ROOT))
        return p

    def dump(self, name):
        p = os.path.join(self.out, name if name.endswith(".json") else name + ".json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(self.sem, f, ensure_ascii=False, indent=1)
        return p

    def text(self):
        return self.cdp.eval("(document.body.innerText||'').slice(0,3000)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "docs", "r19-gun-builder", "reference"))
    ap.add_argument("--url", default="https://db4tarkov.com/gun")
    ap.add_argument("--boot", type=float, default=24.0)
    ap.add_argument("--cdp-port", type=int, default=9371)
    ap.add_argument("--steps", default="[]",
                    help='JSON 数组，元素为 [op, ...]；op: clicktext/clickxy/type/shot/dump/wait/key/esc')
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    steps = json.loads(a.steps)

    proc = None
    try:
        proc, ws = launch_proxied(find_chrome(), a.cdp_port, 1600, 1000,
                                  os.path.join(os.environ.get("TEMP", "."), "r19w-%d" % os.getpid()))
        cdp = CDP(ws)
        for m in ("Page.enable", "Runtime.enable", "Network.enable"):
            cdp.call(m)
        cdp.call("Emulation.setDeviceMetricsOverride", width=1600, height=1000,
                 deviceScaleFactor=1, mobile=False)
        cdp.call("Page.navigate", url=a.url)
        time.sleep(a.boot)
        # 启用语义树
        cdp.eval("(function(){var p=document.querySelector('flt-semantics-placeholder');"
                 "if(p){p.click();return 1;}return 0;})()")
        r = Ref(cdp, a.out)
        sem = r.refresh(2.5)
        print("[boot] semantics:", len(sem), "location:", cdp.eval("location.href"))

        for st in steps:
            op = st[0]
            if op == "clicktext":
                node = r.find(st[1], exact=(len(st) > 2 and st[2] == "exact"))
                if not node:
                    print("   [miss] 找不到控件：", st[1])
                    continue
                r.click_node(node, st[3] if len(st) > 3 else 1.4)
                r.refresh()
                print("   click %r @(%d,%d)" % (node["t"][:30], node["x"], node["y"]))
            elif op == "clickxy":
                r.click(st[1], st[2], st[3] if len(st) > 3 else 1.4)
                r.refresh()
            elif op == "type":
                cdp.call("Input.insertText", text=st[1])
                r.refresh(1.2)
                print("   type %r" % st[1])
            elif op == "key":
                for t in ("keyDown", "keyUp"):
                    cdp.call("Input.dispatchKeyEvent", type=t, key=st[1])
                r.refresh(0.8)
            elif op == "esc":
                for t in ("keyDown", "keyUp"):
                    cdp.call("Input.dispatchKeyEvent", type=t, key="Escape",
                             windowsVirtualKeyCode=27, nativeVirtualKeyCode=27)
                r.refresh(0.8)
            elif op == "wait":
                r.refresh(st[1])
            elif op == "shot":
                r.shot(st[1])
            elif op == "dump":
                r.dump(st[1])
                print("   dump ->", st[1], "(%d nodes)" % len(r.sem))
            elif op == "report":
                for s in r.sem[:60]:
                    print("     %-46s %-10s (%d,%d %dx%d)" % (s["t"][:46], s["role"], s["x"], s["y"], s["w"], s["h"]))
    finally:
        if proc:
            try:
                proc.terminate()
            except Exception:
                pass


if __name__ == "__main__":
    main()
