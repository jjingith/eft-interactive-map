#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""针对最后一板 19 件的逐件体检（只测量，不改文件）。"""
from __future__ import annotations

import json
import os
import sys

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = r"D:\personal\trae\02-塔科夫\ui图标\xp风格ui\Create ONE single 4K sprite she_881c048f.png"

BOXES = {
    "current-gun-plate": (118, 580, 1877, 765),
    "version-plate": (1973, 580, 2776, 759),
    "brand-plate": (118, 1125, 979, 1345),
    "table-frame": (1091, 1060, 1468, 1420),
    "empty-task": (1554, 1689, 1724, 1838),
    "empty-story": (1826, 1695, 1938, 1834),
    "empty-gun": (2573, 1689, 2732, 1841),
    "arrow-normal": (118, 1649, 316, 1878),
    "arrow-hover": (414, 1654, 610, 1882),
    "sep-horizontal": (713, 1733, 1264, 1781),
    "sep-vertical": (1386, 1654, 1430, 1878),
    "icon-map": (2032, 1155, 2274, 1347),
    "icon-tasks": (2450, 1184, 2776, 1295),
    "thumb-normal": (118, 2118, 610, 2293),
    "thumb-hover": (712, 2110, 1217, 2293),
    "thumb-pressed": (1317, 2113, 1843, 2293),
}


def load():
    im = Image.open(SRC).convert("RGB")
    return im, im.load()


def profile_rows(px, box, axis="row"):
    x0, y0, x1, y1 = box
    if axis == "row":
        for y in range(y0, y1):
            seg = [px[x, y][:3] for x in range(x0, x1)]
            uniq = {}
            for c in seg:
                uniq[c] = uniq.get(c, 0) + 1
            top = sorted(uniq.items(), key=lambda kv: -kv[1])[:3]
            print("   y=%4d %s" % (y, "  ".join("%sx%d" % (c, n) for c, n in top)))
    else:
        for x in range(x0, x1):
            seg = [px[x, y][:3] for y in range(y0, y1)]
            uniq = {}
            for c in seg:
                uniq[c] = uniq.get(c, 0) + 1
            top = sorted(uniq.items(), key=lambda kv: -kv[1])[:3]
            print("   x=%4d %s" % (x, "  ".join("%sx%d" % (c, n) for c, n in top)))


KEY = (223, 44, 235)


def ink_bbox(px, box, tol=8):
    """在 box 内找非键色 bbox。"""
    x0, y0, x1, y1 = box
    mnx, mny, mxx, mxy = 10 ** 9, 10 ** 9, -1, -1
    for y in range(y0, y1):
        for x in range(x0, x1):
            r, g, b = px[x, y][:3]
            if max(abs(r - KEY[0]), abs(g - KEY[1]), abs(b - KEY[2])) > tol:
                mnx = min(mnx, x)
                mxx = max(mxx, x)
                mny = min(mny, y)
                mxy = max(mxy, y)
    return mnx, mny, mxx, mxy


def arrow_metrics(px, box, label):
    mnx, mny, mxx, mxy = ink_bbox(px, box)
    # 三角：找 y 行内最深色（墨 #3B412F 附近）的横向范围
    rows = []
    for y in range(mny, mxy + 1):
        xs = [x for x in range(mnx, mxx + 1)
              if max(abs(px[x, y][0] - 59), abs(px[x, y][1] - 65), abs(px[x, y][2] - 47)) <= 22]
        if xs:
            rows.append((y, min(xs), max(xs), max(xs) - min(xs) + 1))
    print("\n[%s] 底板 bbox %dx%d @ (%d,%d)" % (
        label, mxx - mnx + 1, mxy - mny + 1, mnx, mny))
    if rows:
        print("   墨色三角行数 %d，首行 y=%d 宽 %d，末行 y=%d 宽 %d" % (
            len(rows), rows[0][0], rows[0][3], rows[-1][0], rows[-1][3]))
        print("   三角 ink 宽 %d、高 %d、距底板顶 %d、水平偏移 %d" % (
            max(r[3] for r in rows), rows[-1][0] - rows[0][0] + 1,
            rows[0][0] - mny, rows[0][1] - mnx))
        for r in rows[:14]:
            print("      y=%-4d x=%d..%d w=%d" % r)


def plate_bevel(px, box, label):
    mnx, mny, mxx, mxy = ink_bbox(px, box)
    w = mxx - mnx + 1
    h = mxy - mny + 1
    midx = (mnx + mxx) // 2
    midy = (mny + mxy) // 2
    print("\n[%s] bbox %dx%d @ (%d,%d)" % (label, w, h, mnx, mny))
    print("   垂直中线 x=%d 自上而下：" % midx)
    for y in range(mny, min(mny + 14, mxy + 1)):
        print("     y+%d %s" % (y - mny, px[midx, y][:3]))
    print("   水平中线 y=%d 自左而右：" % midy)
    for x in range(mnx, min(mnx + 16, mxx + 1)):
        print("     x+%d %s" % (x - mnx, px[x, midy][:3]))
    # 中心区域是否有墨
    ink = 0
    for y in range(mny + h // 4, mny + 3 * h // 4):
        for x in range(mnx + w // 4, mnx + 3 * w // 4):
            r, g, b = px[x, y][:3]
            if abs(r - 236) > 14 or abs(g - 233) > 14 or abs(b - 216) > 14:
                ink += 1
    print("   中心区非米色像素 = %d（0 表示空白）" % ink)


def sep_profile(px, box, label, axis):
    mnx, mny, mxx, mxy = ink_bbox(px, box)
    print("\n[%s] bbox %dx%d @ (%d,%d)" % (
        label, mxx - mnx + 1, mxy - mny + 1, mnx, mny))
    uniq = {}
    for y in range(mny, mxy + 1):
        for x in range(mnx, mxx + 1):
            c = px[x, y][:3]
            uniq[c] = uniq.get(c, 0) + 1
    print("   颜色分布：" + "  ".join("%s x%d" % (c, n)
                                    for c, n in sorted(uniq.items(), key=lambda kv: -kv[1])[:6]))
    if axis == "row":
        for y in range(mny, mxy + 1):
            row = [px[x, y][:3] for x in range(mnx, mxx + 1)]
            uniq2 = {}
            for c in row:
                uniq2[c] = uniq2.get(c, 0) + 1
            print("   y=%d  %s" % (y, "  ".join("%s x%d" % (c, n) for c, n in
                                               sorted(uniq2.items(), key=lambda kv: -kv[1])[:3])))
    else:
        for x in range(mnx, mxx + 1):
            col = [px[x, y][:3] for y in range(mny, mxy + 1)]
            uniq2 = {}
            for c in col:
                uniq2[c] = uniq2.get(c, 0) + 1
            print("   x=%d  %s" % (x, "  ".join("%s x%d" % (c, n) for c, n in
                                               sorted(uniq2.items(), key=lambda kv: -kv[1])[:3])))


def icon_plate_check(px, box, label):
    mnx, mny, mxx, mxy = ink_bbox(px, box)
    w = mxx - mnx + 1
    h = mxy - mny + 1
    cream = 0
    for y in range(mny, mxy + 1):
        for x in range(mnx, mxx + 1):
            r, g, b = px[x, y][:3]
            if r > 200 and g > 195 and b > 170 and b < 240:
                cream += 1
    fill = cream / float(w * h)
    print("[%-12s] bbox %2dx%-2d @(%4d,%4d) 米色占比 %.1f%%  %s" % (
        label, w, h, mnx, mny, fill * 100, "无底板 OK" if fill < 0.02 else "疑似底板"))


def main():
    im, px = load()
    for k in ("current-gun-plate", "version-plate", "brand-plate", "table-frame"):
        plate_bevel(px, BOXES[k], k)
    for k in ("empty-task", "empty-story", "empty-gun"):
        mnx, mny, mxx, mxy = ink_bbox(px, BOXES[k])
        print("\n[%s] bbox %dx%d @(%d,%d)" % (k, mxx - mnx + 1, mxy - mny + 1, mnx, mny))
    arrow_metrics(px, BOXES["arrow-normal"], "arrow-normal")
    arrow_metrics(px, BOXES["arrow-hover"], "arrow-hover")
    for k, lab in (("icon-map", "icon-map"), ("icon-tasks", "icon-tasks")):
        icon_plate_check(px, BOXES[k], lab)
    sep_profile(px, BOXES["sep-horizontal"], "sep-horizontal", "row")
    sep_profile(px, BOXES["sep-vertical"], "sep-vertical", "col")
    for k in ("thumb-normal", "thumb-hover", "thumb-pressed"):
        mnx, mny, mxx, mxy = ink_bbox(px, BOXES[k])
        print("\n[%s] bbox %dx%d @(%d,%d)" % (k, mxx - mnx + 1, mxy - mny + 1, mnx, mny))
        for y in range(mny, min(mny + 8, mxy + 1)):
            print("   y+%d %s" % (y - mny, [px[x, y][:3] for x in (mnx, mnx + 1, mnx + 2,
                                                                  mnx + 3, mnx + 4, mnx + 5)]))


if __name__ == "__main__":
    main()
