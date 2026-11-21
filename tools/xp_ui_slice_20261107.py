#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""XP UI 缺件补充板（20261107补充.png）切片管线（R93）。

源图：2880x2880 RGB PNG，实测键色 #E815EF（四边 20px 条带互差 ≤1.3/通道，背景干净）。
坐标表（用户给出）与实际绘制不一致：本脚本先按键色 + 游程连通域检测真实 bbox，
再按「尺寸 / 宽高比 / 相对位置 / 件名」逐件对照；匹配不上的如实标注，不强派。

复用 tools/xp_ui_slice.py 的 key_and_clean / resize_premult。
"""
from __future__ import annotations

import json
import os
import sys

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageStat

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from xp_ui_slice import resize_premult  # noqa: E402


def clamp(v):
    return max(0, min(255, int(round(v))))


def key_magenta(crop, bg, hard=12, erode=1):
    """洋红键色抠图（沿用 20261106 板修正版）。

    key_and_clean 用 spill=max(r-g, b-g) 估 alpha，蓝色像素 r-g 为负、b-g 很大，
    会被误判成半透明 → 蓝件"漂白"成青色（本板 switch-track-on 实测变青）。
    这里改 spill=min(r-g, b-g)：只有 R/B 同时明显高于 G 才算洋红污染，
    蓝色 min 为负 → alpha=1 原样保留。
    键色判定用切比雪夫距离（逐通道），PNG 无 JPEG 块噪，hard 取实测 tol。
    """
    rgb = crop.convert("RGB")
    px = rgb.load()
    w, h = rgb.size
    br, bgc, bb = int(round(bg[0])), int(round(bg[1])), int(round(bg[2]))
    m_ref = float(min(br - bgc, bb - bgc)) or 1.0
    alpha = Image.new("L", (w, h), 0)
    ap = alpha.load()
    out = rgb.copy()
    o = out.load()
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            if max(abs(r - br), abs(g - bgc), abs(b - bb)) <= hard:
                ap[x, y] = 0
                continue
            a = 1.0 - max(0.0, min(1.0, min(r - g, b - g) / m_ref))
            if a <= 0.06:
                ap[x, y] = 0
                continue
            av = int(round(a * 255))
            ap[x, y] = av
            if a >= 0.985:
                t = min(r - g, b - g)
                if t > 0:
                    r -= t
                    b -= t
                o[x, y] = (max(0, r), g, max(0, b))
            else:
                o[x, y] = (clamp((r - (1 - a) * br) / a),
                           clamp((g - (1 - a) * bgc) / a),
                           clamp((b - (1 - a) * bb) / a))
    if erode > 0:
        alpha = alpha.filter(ImageFilter.MinFilter(erode * 2 + 1))
    out.putalpha(alpha)
    return out

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "..", "ui图标", "xp风格ui", "20261107补充.png")
OUT = os.path.join(ROOT, "assets", "xp-ui")
REPORT = os.path.join(ROOT, "docs", "xp-ui-20261107-slice-report.json")
PREVIEW = r"D:\Temp\3\slice_preview.png"


def measure_edges(im):
    w, h = im.size
    names = ("top", "bottom", "left", "right")
    strips = [im.crop((0, 0, w, 20)), im.crop((0, h - 20, w, h)),
              im.crop((0, 0, 20, h)), im.crop((w - 20, 0, w, h))]
    info = []
    for n, s in zip(names, strips):
        st = ImageStat.Stat(s)
        info.append(dict(edge=n, mean=[round(v, 2) for v in st.mean],
                         std=[round(v, 2) for v in st.stddev]))
    means = [i["mean"] for i in info]
    bg = [round(sum(m[c] for m in means) / 4.0, 2) for c in range(3)]
    spread = [round(max(m[c] for m in means) - min(m[c] for m in means), 2) for c in range(3)]
    worst_std = max(max(i["std"]) for i in info)
    return bg, spread, worst_std, info


def make_mask(im, bg, tol):
    dr = ImageChops.difference(im.getchannel(0), Image.new("L", im.size, int(round(bg[0]))))
    dg = ImageChops.difference(im.getchannel(1), Image.new("L", im.size, int(round(bg[1]))))
    db = ImageChops.difference(im.getchannel(2), Image.new("L", im.size, int(round(bg[2]))))
    d = ImageChops.lighter(ImageChops.lighter(dr, dg), db)
    mask = d.point(lambda v: 255 if v > tol else 0)
    return mask.filter(ImageFilter.MedianFilter(3))


def label_runs(mask, min_area=800):
    w, h = mask.size
    data = mask.tobytes()
    parent, area = [], []

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra
            area[ra] += area[rb]

    run_x, run_y, run_l = [], [], []
    prev_lo, prev_hi = 0, 0
    for y in range(h):
        row = data[y * w:(y + 1) * w]
        cur_lo = len(run_x)
        x = 0
        while True:
            s = row.find(255, x)
            if s < 0:
                break
            e = row.find(0, s)
            if e < 0:
                e = w
            rid = len(parent)
            parent.append(rid)
            area.append(e - s)
            run_x.append(s)
            run_y.append(y)
            run_l.append(e - s)
            x = e if e > s else s + 1
        j = prev_lo
        for i in range(cur_lo, len(run_x)):
            s, e = run_x[i], run_x[i] + run_l[i]
            while j < prev_hi and run_x[j] + run_l[j] <= s:
                j += 1
            k = j
            while k < prev_hi and run_x[k] < e:
                union(i, k)
                k += 1
        prev_lo, prev_hi = cur_lo, len(run_x)

    boxes = {}
    for i in range(len(parent)):
        r = find(i)
        x0, y0 = run_x[i], run_y[i]
        x1, y1 = x0 + run_l[i], y0 + 1
        b = boxes.setdefault(r, [x0, y0, x1, y1, 0])
        b[0] = min(b[0], x0); b[1] = min(b[1], y0)
        b[2] = max(b[2], x1); b[3] = max(b[3], y1)
        b[4] += run_l[i]
    return [tuple(v) for v in boxes.values() if v[4] >= min_area]


# 实测 bbox（连通域编号见 docs 报告；y 序与提示词件序完全一致）
# name, box(x0,y0,x1,y1), 输出 1x 尺寸, 是否接入主界面, 备注
ITEMS = [
    ("scroll-v-arrow-down-hover", (1834, 321, 2031, 512), (22, 27), True,
     "竖条按钮实际是 22x27，按控件尺寸输出，运行时不再缩放"),
    ("range-track-compact", (254, 343, 1550, 466), (200, 16), True, ""),
    ("tip-plate", (254, 682, 1550, 984), (120, 40), True, ""),
    ("scroll-h-thumb", (1834, 713, 2401, 897), (44, 21), False,
     "横向滑块常态已有 scroll-h-thumb.png 且三态齐全，新件更厚、边框更重，未采用"),
    ("badge-md", (1834, 1133, 2012, 1277), (17, 17), True, ""),
    ("badge-md-hover", (2127, 1119, 2308, 1277), (17, 17), True, "蓝调色版"),
    ("badge-md-warn", (2426, 1132, 2610, 1277), (17, 17), True, "棕调色版"),
    ("tab-active-26", (254, 1154, 1550, 1300), (120, 26), True, ""),
    ("tab-inactive-26", (254, 1484, 1550, 1651), (120, 26), True, ""),
    ("tab-hover-26", (254, 1825, 1550, 1982), (120, 26), True, ""),
    ("badge-sm", (1834, 1442, 2153, 1528), (26, 11), True, ""),
    ("badge-micro", (1834, 1654, 1965, 1802), (13, 16), True, ""),
    ("switch-track-off", (1834, 1917, 2178, 2044), (28, 14), True, ""),
    ("switch-track-on", (2306, 1918, 2660, 2044), (28, 14), True, ""),
    ("switch-knob-off", (1834, 2173, 1972, 2311), (10, 10), True, ""),
    ("switch-knob-on", (2105, 2173, 2242, 2311), (10, 10), True, ""),
    ("switch-knob-hover", (2375, 2171, 2512, 2311), (10, 10), True, ""),
    ("range-thumb-compact", (1833, 2441, 1965, 2621), (10, 16), True, ""),
]


def trim_weak_edges(img, max_alpha=191):
    """裁掉最外侧"几乎是键色"的过渡行/列。

    连通域把「边缘与键色的混合行」也算进 bbox（差 > 阈值），这一行在缩小后
    会把整条边的 alpha 拉低（实测 badge-md 底边 alpha 从 255 掉到 210，
    看起来像缺了一条边）。按「该行最大 alpha < max_alpha」判定并裁掉。
    """
    a = img.getchannel("A")
    w, h = img.size
    px = a.load()
    x0, y0, x1, y1 = 0, 0, w, h
    while y0 < y1 - 1 and max(px[x, y0] for x in range(w)) < max_alpha:
        y0 += 1
    while y1 > y0 + 1 and max(px[x, y1 - 1] for x in range(w)) < max_alpha:
        y1 -= 1
    while x0 < x1 - 1 and max(px[x0, y] for y in range(y0, y1)) < max_alpha:
        x0 += 1
    while x1 > x0 + 1 and max(px[x1 - 1, y] for y in range(y0, y1)) < max_alpha:
        x1 -= 1
    return img.crop((x0, y0, x1, y1))


def fringe_count(img):
    """洋红紫边：R 与 B 同时显著高于 G（蓝件的 b-g 大但 r-g 负，不算）。"""
    px = img.load()
    n = 0
    for y in range(img.height):
        for x in range(img.width):
            r, g, b, a = px[x, y]
            if a > 20 and min(r - g, b - g) > 40:
                n += 1
    return n


def main():
    im = Image.open(SRC).convert("RGB")
    bg, spread, worst_std, edges = measure_edges(im)
    bgi = [int(round(v)) for v in bg]
    print("源图 %dx%d  键色均值 RGB%s (#%02X%02X%02X)" %
          (im.width, im.height, bgi, bgi[0], bgi[1], bgi[2]))
    print("四边均值互差: %s   最大单边 std=%.2f" % (spread, worst_std))
    if max(spread) > 4:
        print("!! 背景不干净（互差 > ±4/通道），请人工复核")
    tol = max(8, int(round(worst_std * 6)))
    print("抠图容差 tol =", tol)

    comps = label_runs(make_mask(im, bg, tol))
    comps = [c for c in comps if (c[2] - c[0]) >= 60 and (c[3] - c[1]) >= 60]
    comps.sort(key=lambda c: (c[1], c[0]))
    print("连通域 %d 个" % len(comps))

    entries = []
    for name, box, (ew, eh), adopt, note in ITEMS:
        x0, y0, x1, y1 = box
        # 与检测结果比对（±8px）
        hit = None
        for c in comps:
            if abs(c[0] - x0) <= 8 and abs(c[1] - y0) <= 8 and abs(c[2] - x1) <= 8 and abs(c[3] - y1) <= 8:
                hit = c
                break
        crop = im.crop((x0, y0, x1, y1))
        sw, sh = crop.size
        keyed = trim_weak_edges(key_magenta(crop, bg, hard=tol, erode=1))
        out = resize_premult(keyed, (ew, eh), Image.LANCZOS)
        path = os.path.join(OUT if adopt else r"D:\Temp\3\rejected", name + ".png")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        out.save(path, optimize=True)
        fr = fringe_count(out)
        entries.append(dict(
            name=name, crop_px=[x0, y0, x1, y1], crop_size=[sw, sh],
            out_size=[out.width, out.height], detected=(list(hit) if hit else None),
            adopt=adopt, fringe_px=fr, note=note,
            aspect_src=round(sw / float(sh), 3), aspect_out=round(ew / float(eh), 3),
        ))
        print("[%-3s] %-26s 源 %4d,%4d %4dx%-4d (ar %.2f) -> %dx%d (ar %.2f) 紫边 %d %s"
              % ("IN " if adopt else "SKIP", name, x0, y0, sw, sh, sw / float(sh),
                 ew, eh, ew / float(eh), fr, note))

    # 预览：棋盘底，1x 原尺寸 4x 放大
    cols, cw, chh = 6, 320, 200
    rows = (len(entries) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cw, rows * chh), (45, 45, 45))
    dr = ImageDraw.Draw(sheet)
    for i, e in enumerate(entries):
        cx, cy = (i % cols) * cw, (i // cols) * chh
        for yy in range(cy, cy + chh, 10):
            for xx in range(cx, cx + cw, 10):
                if ((xx // 10) + (yy // 10)) % 2:
                    dr.rectangle([xx, yy, xx + 9, yy + 9], fill=(110, 110, 110))
                else:
                    dr.rectangle([xx, yy, xx + 9, yy + 9], fill=(140, 140, 140))
        img = Image.open(os.path.join(OUT if e["adopt"] else r"D:\Temp\3\rejected",
                                      e["name"] + ".png")).convert("RGBA")
        k = min(4, (cw - 12) / img.width, (chh - 34) / img.height)
        big = img.resize((max(1, int(img.width * k)), max(1, int(img.height * k)),
                         ), Image.NEAREST)
        sheet.paste(big, (cx + (cw - big.width) // 2,
                          cy + 20 + (chh - 20 - big.height) // 2), big)
        dr.text((cx + 4, cy + 4), "%s %dx%d" % (e["name"], e["out_size"][0],
                                                e["out_size"][1]),
                fill=(255, 255, 0))
    sheet.save(PREVIEW, optimize=True)
    print("预览:", PREVIEW)

    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w", encoding="utf-8") as f:
        json.dump(dict(src=SRC, size=[im.width, im.height], bg=bg, spread=spread,
                       worst_std=worst_std, tol=tol, edges=edges,
                       comps=[dict(box=list(c), w=c[2] - c[0], h=c[3] - c[1]) for c in comps],
                       items=entries), f, ensure_ascii=False, indent=1)
    print("报告:", REPORT)


if __name__ == "__main__":
    main()
