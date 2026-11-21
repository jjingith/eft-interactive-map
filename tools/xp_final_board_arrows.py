#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""箭头件三角形精确测量 + 滑块三态几何一致性检查。"""
from __future__ import annotations

from PIL import Image

SRC = r"D:\personal\trae\02-塔科夫\ui图标\xp风格ui\Create ONE single 4K sprite she_881c048f.png"

ARROWS = {"normal": (119, 1655, 310, 1876), "hover": (415, 1655, 608, 1876)}
THUMBS = {"normal": (119, 2119, 608, 2292), "hover": (714, 2119, 1213, 2292),
          "pressed": (1318, 2119, 1833, 2292)}


def dark(c):
    r, g, b = c[:3]
    return max(r, g, b) < 150 and abs(r - g) < 40 and abs(b - g) < 40


def main():
    im = Image.open(SRC).convert("RGB")
    px = im.load()
    for name, (x0, y0, x1, y1) in ARROWS.items():
        pw = x1 - x0 + 1
        ph = y1 - y0 + 1
        print("\n=== arrow-%s  底板 %dx%d  scale 若为 22x27 → %.2f / %.2f" % (
            name, pw, ph, pw / 22.0, ph / 27.0))
        rows = []
        for y in range(y0 + 20, y1 - 20):   # 跳过上下边框
            xs = [x for x in range(x0 + 20, x1 - 20) if dark(px[x, y])]
            if xs:
                rows.append((y, min(xs), max(xs), len(xs)))
        if not rows:
            print("   中部无深色像素")
            continue
        top = rows[0]
        bot = rows[-1]
        # 三角宽度按「连续深色」量
        print("   三角行数 %d，首行 y0+%d、末行 y0+%d" % (
            len(rows), top[0] - y0, bot[0] - y0))
        print("   首行宽 %d、末行宽 %d、最宽 %d" % (
            top[3], bot[3], max(r[3] for r in rows)))
        cx = (x0 + x1) // 2
        print("   三角水平范围 x=%d..%d（应居中于 %d）" % (
            min(r[1] for r in rows), max(r[2] for r in rows), cx))
        for r in rows[:4] + rows[-3:]:
            print("      y0+%-3d x=%d..%d w=%d" % (r[0] - y0, r[1], r[2], r[3]))

    print("\n=== 滑块三态（1x 应为 44x21；相对几何必须一致）")
    for name, (x0, y0, x1, y1) in THUMBS.items():
        pw = x1 - x0 + 1
        ph = y1 - y0 + 1
        print("  %-8s %dx%d  scale %.2f/%.2f  ratio %.2f" % (
            name, pw, ph, pw / 44.0, ph / 21.0, pw / float(ph)))
        # 顶/底/左/右边框厚度（找第一条进入米色面的位置）
        cy = (y0 + y1) // 2
        cx = (x0 + x1) // 2
        def face(c):
            r, g, b = c[:3]
            return r > 195 and g > 190 and 160 < b < 245
        t = next(i for i in range(ph) if face(px[cx, y0 + i]))
        b_ = next(i for i in range(ph) if face(px[cx, y1 - i]))
        l_ = next(i for i in range(pw) if face(px[x0 + i, cy]))
        r_ = next(i for i in range(pw) if face(px[x1 - i, cy]))
        print("     边框厚度 顶 %d 底 %d 左 %d 右 %d（源 px）" % (t, b_, l_, r_))


if __name__ == "__main__":
    main()
