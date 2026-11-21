# -*- coding: utf-8 -*-
"""R19.6 参考站交互记录（只读）：进入工作台 → 点槽位 → 点候选，三步截图 + 右栏像素差。"""
import base64, json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r181_accept import CDP
from r196_devtools import launch_proxy

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "docs", "r19.5-layout-audit", "devtools-investigation")
SHOTS = os.path.join(OUT, "reference-screenshots")
os.makedirs(SHOTS, exist_ok=True)

def shot(cdp, name):
    r = cdp.call("Page.captureScreenshot", format_="png")
    p = os.path.join(SHOTS, name)
    open(p, "wb").write(base64.b64decode(r["data"]))
    return p

def click(cdp, x, y):
    cdp.call("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y)
    cdp.call("Input.dispatchMouseEvent", type="mousePressed", x=x, y=y, button="left", clickCount=1)
    cdp.call("Input.dispatchMouseEvent", type="mouseReleased", x=x, y=y, button="left", clickCount=1)

proc, ws = launch_proxy(9429, 1920, 919, os.path.join(os.environ.get("TEMP","."), "i196-%d"%os.getpid()))
rep = {}
try:
    cdp = CDP(ws)
    for m in ("Page.enable", "Runtime.enable"):
        cdp.call(m)
    cdp.call("Emulation.setDeviceMetricsOverride", width=1920, height=919, deviceScaleFactor=1, mobile=False)
    cdp.call("Page.navigate", url="https://db4tarkov.com/gun")
    time.sleep(14)
    # 1) 口径页 → 点 AK-74 卡（语义树实测该卡 [654,363,72,72]）
    shot(cdp, "i1-caliber.png")
    click(cdp, 690, 399); time.sleep(9)
    rep["2-workbench"] = shot(cdp, "i2-workbench.png")
    # 2) 点槽位卡实心区（截图实测：卡片 y≈458-507，MUZZLE 卡中心 x≈545）
    click(cdp, 545, 480); time.sleep(4)
    click(cdp, 545, 480); time.sleep(3)
    rep["3-slot"] = shot(cdp, "i3-slot-clicked.png")
    # 3) 点右栏列表首个候选行（搜索框下方）
    click(cdp, 1250, 95); time.sleep(4)
    rep["4-pick"] = shot(cdp, "i4-part-installed.png")
finally:
    proc.terminate()

# 右栏区域像素差（说明候选表确实从 "Pick a mod" 变为列表 / 安装后数据变化）
from PIL import Image, ImageChops
def diff_region(a, b, box):
    ia = Image.open(os.path.join(SHOTS, a)).convert("RGB").crop(box)
    ib = Image.open(os.path.join(SHOTS, b)).convert("RGB").crop(box)
    d = ImageChops.difference(ia, ib)
    hist = d.convert("L").histogram()
    changed = sum(hist[12:])
    return {"changedPx": changed, "totalPx": ia.size[0]*ia.size[1],
            "ratio": round(changed / float(ia.size[0]*ia.size[1]), 4)}
box = (1000, 60, 1860, 700)
rep["rightPanelDiff_workbench_to_slot"] = diff_region("i2-workbench.png", "i3-slot-clicked.png", box)
rep["rightPanelDiff_slot_to_pick"] = diff_region("i3-slot-clicked.png", "i4-part-installed.png", box)
rep["centerDiff_slot_to_pick"] = diff_region("i3-slot-clicked.png", "i4-part-installed.png", (480, 88, 992, 919))
print(json.dumps(rep, ensure_ascii=False, indent=1))
open(os.path.join(OUT, "interaction-shots.json"), "w", encoding="utf-8").write(
    json.dumps(rep, ensure_ascii=False, indent=1))
