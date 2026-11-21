# -*- coding: utf-8 -*-
"""R19 参考站坐标驱动：db4tarkov 是 Flutter Web（canvas 渲染，DOM 不可查），
只能用真实鼠标坐标点击并截图观察。

用法：
  python tools/r19_click.py --steps '[["click",500,250],["shot","03"]]'
  python tools/r19_click.py --steps '[["wait",2],["shot","x"]]'
step 支持: click x y / move x y / wheel x y dy / key KEY / wait sec / shot name / type TEXT
"""
import argparse, base64, json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r181_accept import CDP, find_chrome
from r19_ref_probe import launch_proxied

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "docs", "r19-gun-builder", "reference"))
    ap.add_argument("--url", default="https://db4tarkov.com/gun")
    ap.add_argument("--steps", default='[["shot","shot"]]')
    ap.add_argument("--w", type=int, default=1600)
    ap.add_argument("--h", type=int, default=1000)
    ap.add_argument("--cdp-port", type=int, default=9368)
    ap.add_argument("--boot", type=float, default=14.0)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    steps = json.loads(a.steps)

    proc = None
    try:
        proc, ws = launch_proxied(find_chrome(), a.cdp_port, a.w, a.h,
                                  os.path.join(os.environ.get("TEMP", "."), "r19c-%d" % os.getpid()))
        cdp = CDP(ws)
        for m in ("Page.enable", "Runtime.enable"):
            cdp.call(m)
        cdp.call("Emulation.setDeviceMetricsOverride", width=a.w, height=a.h,
                 deviceScaleFactor=1, mobile=False)
        cdp.call("Page.navigate", url=a.url)
        time.sleep(a.boot)          # Flutter 首帧 + 数据加载
        for st in steps:
            op = st[0]
            if op == "click":
                x, y = st[1], st[2]
                cdp.call("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y, button="none", clickCount=0)
                cdp.call("Input.dispatchMouseEvent", type="mousePressed", x=x, y=y, button="left", clickCount=1)
                cdp.call("Input.dispatchMouseEvent", type="mouseReleased", x=x, y=y, button="left", clickCount=1)
                time.sleep(st[3] if len(st) > 3 else 1.2)
            elif op == "move":
                cdp.call("Input.dispatchMouseEvent", type="mouseMoved", x=st[1], y=st[2], button="none", clickCount=0)
                time.sleep(st[3] if len(st) > 3 else 0.6)
            elif op == "wheel":
                cdp.call("Input.dispatchMouseEvent", type="mouseWheel", x=st[1], y=st[2],
                         deltaX=0, deltaY=st[3], button="none")
                time.sleep(0.8)
            elif op == "key":
                for t in ("keyDown", "keyUp"):
                    cdp.call("Input.dispatchKeyEvent", type=t, key=st[1], windowsVirtualKeyCode=27 if st[1]=="Escape" else 0)
                time.sleep(0.6)
            elif op == "wait":
                time.sleep(st[1])
            elif op == "shot":
                name = st[1] if not st[1].endswith(".png") else st[1]
                p = os.path.join(a.out, name + ("" if name.endswith(".png") else ".png"))
                data = base64.b64decode(cdp.call("Page.captureScreenshot", format="png")["data"])
                open(p, "wb").write(data)
                print("shot ->", os.path.relpath(p, ROOT))
            elif op == "type":
                cdp.call("Input.insertText", text=st[1])
                time.sleep(0.8)
    finally:
        if proc:
            try: proc.terminate()
            except Exception: pass

if __name__ == "__main__":
    main()
