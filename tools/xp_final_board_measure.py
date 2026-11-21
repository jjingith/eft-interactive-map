#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""最后一板：逐件精确测量（tol=16，排除键色 AA 毛边）。"""
from __future__ import annotations

import os

from PIL import Image

SRC = r"D:\personal\trae\02-塔科夫\ui图标\xp风格ui\Create ONE single 4K sprite she_881c048f.png"
KEY = (223, 44, 235)
TOL = 16

REGIONS = {
    "current-gun-plate": (100, 560, 1900, 790),
    "version-plate": (1950, 560, 2800, 780),
    "brand-plate": (100, 1100, 1000, 1360),
    "table-frame": (1070, 1040, 1490, 1440),
    "empty-task": (1520, 1660, 1760, 1870),
    "empty-story": (1790, 1660, 1990, 1870),
    "empty-gun": (2540, 1660, 2760, 1870),
    "arrow-normal": (100, 1630, 340, 1900),
    "arrow-hover": (390, 1630, 630, 1900),
    "icon-map": (2000, 1140, 2300, 1360),
    "icon-tasks": (2410, 1140, 2660, 1360),
    "icon-ammo": (2660, 1140, 2880, 1360),
    "icon-gun": (1520, 1130, 1800, 1330),
    "icon-loadout": (2280, 1100, 2560, 1360),
    "sep-horizontal": (690, 1710, 1290, 1800),
    "sep-vertical": (1370, 1630, 1440, 1900),
    "thumb-normal": (100, 2090, 640, 2320),
    "thumb-hover": (690, 2090, 1240, 2320),
    "thumb-pressed": (1290, 2090, 1870, 2320),
}


def bbox(px, reg, tol=TOL):
    x0, y0, x1, y1 = reg
    mnx = mny = 10 ** 9
    mxx = mxy = -1
    for y in range(y0, y1):
        for x in range(x0, x1):
            r, g, b = px[x, y][:3]
            if max(abs(r - KEY[0]), abs(g - KEY[1]), abs(b - KEY[2])) > tol:
                if x < mnx:
                    mnx = x
                if x > mxx:
                    mxx = x
                if y < mny:
                    mny = y
                if y > mxy:
                    mxy = y
    return mnx, mny, mxx, mxy


def main():
    im = Image.open(SRC).convert("RGB")
    px = im.load()
    print("%-28s %-22s %-10s %-8s" % ("name", "bbox", "size", "ratio"))
    for name, reg in REGIONS.items():
        mnx, mny, mxx, mxy = bbox(px, reg)
        w = mxx - mnx + 1
        h = mxy - mny + 1
        print("%-28s (%4d,%4d)-(%4d,%4d) %4dx%-4d %6.2f" % (
            name, mnx, mny, mxx, mxy, w, h, w / float(h)))

    # 三枚滑块：左右边框厚度 + 顶底厚度（取中列/中行扫描）
    print("\n滑块边框扫描（中线位置，逐像素直到米色面）：")
    for name in ("thumb-normal", "thumb-hover", "thumb-pressed"):
        mnx, mny, mxx, mxy = bbox(px, REGIONS[name])
        cy = (mny + mxy) // 2
        cx = (mnx + mxx) // 2
        left = []
        for x in range(mnx, mnx + 14):
            left.append(px[x, cy][:3])
        top = []
        for y in range(mny, mny + 14):
            top.append(px[cx, y][:3])
        print("  [%s] %dx%d" % (name, mxx - mnx + 1, mxy - mny + 1))
        print("    左缘:", left)
        print("    顶缘:", top)

    # 分隔线：横向那条取中段看 y 剖面；纵向那条取中段看 x 剖面
    mnx, mny, mxx, mxy = bbox(px, REGIONS["sep-horizontal"])
    print("\n[sep-horizontal] %dx%d  中段 x=%d 的 y 剖面：" % (
        mxx - mnx + 1, mxy - mny + 1, (mnx + mxx) // 2))
    for y in range(mny, mxy + 1):
        print("   y=%d %s" % (y, px[(mnx + mxx) // 2, y][:3]))

    # 五图标米色占比
    print("\n图标米色占比：")
    for name in ("icon-map", "icon-tasks", "icon-ammo", "icon-gun", "icon-loadout"):
        mnx, mny, mxx, mxy = bbox(px, REGIONS[name])
        w = mxx - mnx + 1
        h = mxy - mny + 1
        cream = 0
        ink = 0
        for y in range(mny, mxy + 1):
            for x in range(mnx, mxx + 1):
                r, g, b = px[x, y][:3]
                if r > 195 and g > 190 and 160 < b < 245:
                    cream += 1
                elif max(r, g, b) < 150:
                    ink += 1
        print("  %-13s %3dx%-3d cream %5.1f%%  ink %5.1f%%" % (
            name, w, h, cream * 100.0 / (w * h), ink * 100.0 / (w * h)))


if __name__ == "__main__":
    main()
