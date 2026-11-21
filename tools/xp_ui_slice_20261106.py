#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""XP UI 缺件补充板（20261106补充.jpg）切片与匹配管线。

源图实测：4096x4096 RGB JPEG（生成模型未按提示词画布/坐标表）。
做法：
  1. 四边 20px 条带实测键色均值/标准差（JPEG 有损，不能沿用 PNG 板容差 25）
  2. 距离阈值 + 形态学开运算去 JPEG 散点，再对全分辨率做游程连通域标记
  3. 按尺寸/宽高比/全局缩放做贪心匹配，匹配不上的如实报告
  4. 复用 tools/xp_ui_slice.py 的 key_and_clean / resize_premult / normalize 算法
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime

from PIL import Image, ImageChops, ImageFilter, ImageStat

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from xp_ui_slice import (  # noqa: E402
    key_and_clean, resize_premult, estimate_shift, apply_shift,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "..", "ui图标", "xp风格ui", "20261106补充.jpg")
OUT = os.path.join(ROOT, "assets", "xp-ui")
REPORT = os.path.join(ROOT, "docs", "xp-ui-20261106-slice-report.json")

# 44 件清单：name, 预期 1x 宽高（来源 docs/xp-ui-missing-board-prompt.md）
EXPECTED = [
    ("statusbar-bg", 800, 24), ("dialog-box", 720, 480), ("dialog-head", 720, 38),
    ("tbl-head", 600, 32), ("tbl-row", 600, 24), ("tbl-row-alt", 600, 24),
    ("tbl-grid-h", 600, 1), ("menu-panel-bg", 330, 210), ("menu-panel-sep", 330, 1),
    ("app-menu-panel-bg", 210, 140), ("context-menu-bg", 146, 96),
    ("context-menu-sep", 146, 1), ("tbl-grid-v", 1, 24),
    ("scroll-v-track", 22, 171), ("scroll-v-thumb", 23, 51),
    ("scroll-v-thumb-hover", 23, 51), ("scroll-v-thumb-pressed", 23, 51),
    ("scroll-v-arrow-up", 22, 27), ("scroll-v-arrow-up-hover", 22, 27),
    ("scroll-v-arrow-up-pressed", 22, 27), ("scroll-v-arrow-down", 22, 27),
    ("scroll-v-arrow-down-hover", 22, 27), ("scroll-v-arrow-down-pressed", 22, 27),
    ("statusbar-cell", 120, 18), ("statusbar-sep", 2, 18),
    ("scroll-h-track", 71, 21), ("scroll-h-thumb", 44, 21),
    ("scroll-h-thumb-hover", 44, 21), ("scroll-h-thumb-pressed", 44, 21),
    ("scroll-h-arrow-left", 21, 21), ("scroll-h-arrow-right", 21, 21),
    ("select-disabled", 204, 33), ("progress-fill", 200, 17),
    ("progress-fill-100", 200, 17), ("progress-fill-indeterminate", 200, 17),
    ("range-track", 208, 15), ("range-thumb", 19, 33),
    ("range-thumb-hover", 19, 33), ("range-thumb-pressed", 19, 33),
    ("empty-box", 48, 48), ("badge-md", 28, 19), ("badge-sm", 20, 14),
    ("check-disabled", 24, 24), ("radio-disabled", 24, 24),
]


def measure_edges(im):
    w, h = im.size
    names = ("top", "bottom", "left", "right")
    strips = [im.crop((0, 0, w, 20)), im.crop((0, h - 20, w, h)),
              im.crop((0, 0, 20, h)), im.crop((w - 20, 0, w, h))]
    info = []
    for n, s in zip(names, strips):
        st = ImageStat.Stat(s)
        info.append(dict(edge=n, mean=[round(v, 2) for v in st.mean],
                         std=[round(v, 2) for v in st.stddev],
                         min=s.getextrema()))
    # 四边合并均值
    allpx = []
    for s in strips:
        allpx.extend(s.convert("RGB").getdata())
    n = len(allpx)
    mean = [round(sum(p[i] for p in allpx) / n, 2) for i in range(3)]
    var = [sum((p[i] - mean[i]) ** 2 for p in allpx) / n for i in range(3)]
    std = [round(v ** 0.5, 2) for v in var]
    return mean, std, info


def make_mask(im, bg, tol, open_radius=1):
    """非背景 mask（255 前景）。距离用通道最大差，避免开方。"""
    r, g, b = im.split()
    br, bgc, bb = bg
    dr = ImageChops.difference(r, Image.new("L", im.size, int(round(br))))
    dg = ImageChops.difference(g, Image.new("L", im.size, int(round(bgc))))
    db = ImageChops.difference(b, Image.new("L", im.size, int(round(bb))))
    d = ImageChops.lighter(ImageChops.lighter(dr, dg), db)
    mask = d.point(lambda v: 255 if v > tol else 0)
    if open_radius > 0:
        # 中值比开运算温和：2px 细线（网格线/分隔线）仍有 6/9 前景，不会被抹掉
        mask = mask.filter(ImageFilter.MedianFilter(open_radius * 2 + 1))
    return mask


def label_runs(mask, min_area=120):
    """整幅游程 + 并查集连通域；返回 [(x0,y0,x1,y1,area)]（右/下开区间）。"""
    w, h = mask.size
    data = mask.tobytes()
    parent = []
    area = []

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

    run_x = []   # 每行 run 的起始 x
    run_y = []
    run_l = []

    prev_lo, prev_hi = 0, 0          # 上一行 run 在数组中的区间
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

        # 只与"上一行"的 run 做重叠合并（两指针，O(run 数)）
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

    # 汇总
    boxes = {}
    for i in range(len(parent)):
        r = find(i)
        x0, y0 = run_x[i], run_y[i]
        x1, y1 = x0 + run_l[i], y0 + 1
        if r not in boxes:
            boxes[r] = [x0, y0, x1, y1, 0]
        b = boxes[r]
        b[0] = min(b[0], x0); b[1] = min(b[1], y0)
        b[2] = max(b[2], x1); b[3] = max(b[3], y1)
        b[4] += run_l[i]
    return [tuple(v) for v in boxes.values() if v[4] >= min_area]


def fill_ratio(b):
    x0, y0, x1, y1, area = b
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0:
        return 0.0
    return area / float(w * h)


def keep_component(b, min_fill=0.93, min_area=200):
    """sprite 是实心矩形块，填充率接近 1；文字标签/噪点是稀疏笔画，填充率低。

    实测：标签 glyph 单个填充率 0.25~0.40，连成词后仍 <0.45；
    带外侧柔影的底板填充率略降，但仍 >0.8。
    """
    x0, y0, x1, y1, area = b
    w, h = x1 - x0, y1 - y0
    if area < min_area:
        return False
    if max(w, h) < 9:
        return False
    return fill_ratio(b) >= min_fill


def make_sheet(im, comps, path, cell=(210, 170), cols=9):
    from PIL import ImageDraw
    comps = sorted(comps, key=lambda c: ((c[0] // 700), c[1], c[0]))
    rows = (len(comps) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell[0], rows * cell[1]), (24, 24, 24))
    dr = ImageDraw.Draw(sheet)
    for i, (x0, y0, x1, y1, area) in enumerate(comps):
        cw, chh = x1 - x0, y1 - y0
        box = im.crop((x0, y0, x1, y1))
        k = min((cell[0] - 20) / float(cw), (cell[1] - 34) / float(chh))
        nw, nh = max(1, int(cw * k)), max(1, int(chh * k))
        box = box.resize((nw, nh), Image.BOX)
        cx, cy = (i % cols) * cell[0], (i // cols) * cell[1]
        sheet.paste(box, (cx + 10 + (cell[0] - 20 - nw) // 2,
                          cy + 22 + (cell[1] - 34 - nh) // 2))
        dr.rectangle([cx, cy, cx + cell[0] - 1, cy + cell[1] - 1], outline=(70, 70, 70))
        dr.text((cx + 5, cy + 4), "#%d (%d,%d) %dx%d f%.2f" %
                (i, x0, y0, cw, chh, fill_ratio((x0, y0, x1, y1, area))),
                fill=(255, 255, 0))
    sheet.save(path, optimize=True)
    return path


def make_overlay(im, comps, path, size=1500):
    """全图缩略 + 候选框编号，用于一次性核对"哪个框是哪个件"。"""
    from PIL import ImageDraw
    k = size / float(max(im.size))
    base = im.resize((int(im.width * k), int(im.height * k)), Image.BOX).convert("RGB")
    dr = ImageDraw.Draw(base)
    for i, (x0, y0, x1, y1, area) in enumerate(comps):
        r = [int(x0 * k), int(y0 * k), int(x1 * k), int(y1 * k)]
        dr.rectangle(r, outline=(0, 255, 0))
        dr.text((r[0] + 2, r[1] + 2), "#%d" % i, fill=(0, 0, 0))
        dr.text((r[0] + 1, r[1] + 1), "#%d" % i, fill=(255, 255, 0))
    base.save(path, optimize=True)
    return path


def row_profile(crop):
    """逐行平均值（打印用），用于找行带边界。"""
    from PIL import ImageStat
    w, h = crop.size
    out = []
    for y in range(h):
        st = ImageStat.Stat(crop.crop((0, y, w, y + 1)))
        out.append([int(round(v)) for v in st.mean])
    return out


def make_contact(paths, out_path, cell=(260, 150), cols=7):
    """把输出 PNG 放在棋盘底上排成一张对照表，检查紫边/透明度/裁切。"""
    from PIL import ImageDraw
    rows = (len(paths) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell[0], rows * cell[1]), (40, 40, 40))
    dr = ImageDraw.Draw(sheet)
    for i, p in enumerate(paths):
        img = Image.open(p).convert("RGBA")
        cx, cy = (i % cols) * cell[0], (i // cols) * cell[1]
        # 棋盘底
        for yy in range(cy + 18, cy + cell[1], 10):
            for xx in range(cx, cx + cell[0], 10):
                c = (120, 120, 120) if ((xx // 10) + (yy // 10)) % 2 else (150, 150, 150)
                dr.rectangle([xx, yy, min(xx + 9, cx + cell[0]), min(yy + 9, cy + cell[1])], fill=c)
        k = min((cell[0] - 16) / float(img.width), (cell[1] - 30) / float(img.height), 3.0)
        if k > 1.0:
            k = int(k)
        elif k < 1.0:
            k = k
        else:
            k = 1
        nw, nh = max(1, int(img.width * k)), max(1, int(img.height * k))
        big = img.resize((nw, nh), Image.NEAREST if k >= 1 else Image.LANCZOS)
        sheet.paste(big, (cx + 8 + (cell[0] - 16 - nw) // 2,
                          cy + 22 + (cell[1] - 30 - nh) // 2), big)
        dr.text((cx + 4, cy + 4), os.path.basename(p), fill=(255, 255, 0))
    sheet.save(out_path, optimize=True)
    return out_path


def ink_map(im, bg, tol, cells=64):
    """把非键色像素密度降到 cells×cells 的 ASCII 图，用于人工核对版式。"""
    mask = make_mask(im, bg, tol, open_radius=0)
    w, h = mask.size
    px = mask.load()
    cw, ch = w / cells, h / cells
    rows = []
    for cy in range(cells):
        y0, y1 = int(cy * ch), int((cy + 1) * ch)
        line = []
        for cx in range(cells):
            x0, x1 = int(cx * cw), int((cx + 1) * cw)
            cnt = tot = 0
            for y in range(y0, y1, 4):
                for x in range(x0, x1, 4):
                    tot += 1
                    if px[x, y]:
                        cnt += 1
            f = cnt / float(tot) if tot else 0.0
            line.append(" " if f < 0.015 else "." if f < 0.06 else
                        "o" if f < 0.25 else "+" if f < 0.55 else "#")
        rows.append(line)
    head = "     " + "".join(str((int(cx * cw) // 1000) % 10) for cx in range(cells))
    print(head)
    for cy, line in enumerate(rows):
        print("%4d %s" % (int(cy * ch), "".join(line)))


# -------------------------------------------------------------------------
# 44 件提取表：box 是源图像素绝对包围盒（由连通域自动检测后逐件人工核对）
#   kind=panel : 整块按 0.5 均匀降采样（保留 2px 源斜角 → 1px 1x 斜角），供 9-slice
#   kind=icon  : 按预期 1x 尺寸缩放（图标/滑块/箭头/小控件）
# -------------------------------------------------------------------------
def _b(x0, y0, x1, y1):
    return (x0, y0, x1, y1)


ITEMS = [
    # 面板 / 底板（9-slice）
    dict(name="statusbar-bg", box=_b(204, 203, 1465, 403), kind="panel", expect=(800, 24)),
    dict(name="dialog-box", box=_b(204, 534, 1465, 1472), kind="panel", expect=(720, 480)),
    dict(name="dialog-head", box=_b(204, 1651, 1465, 1798), kind="panel", expect=(720, 38)),
    dict(name="tbl-head", box=_b(204, 1925, 1465, 2299), kind="panel", expect=(600, 32)),
    # 表格行：从合并的大表格体里取列分隔线之间的干净横带
    dict(name="tbl-row", box=_b(230, 2526, 332, 2706), kind="icon", expect=(600, 24)),
    dict(name="tbl-row-alt", box=_b(230, 2736, 332, 2796), kind="icon", expect=(600, 24)),
    dict(name="tbl-grid-h", box=_b(230, 2513, 332, 2519), kind="icon", expect=(600, 1)),
    dict(name="menu-panel-bg", box=_b(1633, 203, 2502, 859), kind="panel", expect=(330, 210)),
    dict(name="menu-panel-sep", box=_b(1634, 1000, 2502, 1006), kind="icon", expect=(330, 1)),
    dict(name="app-menu-panel-bg", box=_b(1633, 1146, 2324, 1671), kind="panel", expect=(210, 140)),
    dict(name="context-menu-bg", box=_b(1633, 1861, 2106, 2214), kind="panel", expect=(146, 96)),
    dict(name="context-menu-sep", box=_b(1635, 2349, 2109, 2355), kind="icon", expect=(146, 1)),
    dict(name="tbl-grid-v", box=_b(1752, 2650, 1756, 2870), kind="icon", expect=(1, 24)),
    # 竖向滚动条（重点补齐项）
    dict(name="scroll-v-track", box=_b(2654, 204, 2764, 1190), kind="icon", expect=(22, 171)),
    dict(name="scroll-v-thumb", box=_b(2867, 204, 3000, 523), kind="icon", expect=(23, 51)),
    dict(name="scroll-v-thumb-hover", box=_b(2867, 641, 3000, 963), kind="icon", expect=(23, 51)),
    dict(name="scroll-v-thumb-pressed", box=_b(2867, 1080, 3000, 1401), kind="icon", expect=(23, 51)),
    dict(name="scroll-v-arrow-up", box=_b(2703, 1533, 2863, 1690), kind="icon", expect=(22, 27)),
    dict(name="scroll-v-arrow-up-hover", box=_b(2703, 1804, 2863, 1960), kind="icon", expect=(22, 27)),
    dict(name="scroll-v-arrow-up-pressed", box=_b(2703, 2075, 2863, 2224), kind="icon", expect=(22, 27)),
    dict(name="scroll-v-arrow-down", box=_b(2703, 2228, 2863, 2378), kind="icon", expect=(22, 27)),
    dict(name="scroll-v-arrow-down-hover", box=None, kind="icon", expect=(22, 27)),
    dict(name="scroll-v-arrow-down-pressed", box=_b(2703, 2494, 2863, 2648), kind="icon", expect=(22, 27)),
    # 状态栏格 / 分隔 / 横向滚动条
    dict(name="statusbar-cell", box=_b(2043, 2865, 2599, 3022), kind="icon", expect=(120, 18)),
    dict(name="statusbar-sep", box=_b(2703, 2867, 2730, 3024), kind="icon", expect=(2, 18)),
    dict(name="scroll-h-track", box=_b(2043, 3147, 2599, 3295), kind="icon", expect=(71, 21)),
    dict(name="scroll-h-thumb", box=None, kind="icon", expect=(44, 21)),
    dict(name="scroll-h-thumb-hover", box=_b(2043, 3416, 2558, 3565), kind="icon", expect=(44, 21)),
    dict(name="scroll-h-thumb-pressed", box=_b(2043, 3685, 2558, 3833), kind="icon", expect=(44, 21)),
    dict(name="scroll-h-arrow-left", box=_b(2704, 3148, 2863, 3305), kind="icon", expect=(21, 21)),
    dict(name="scroll-h-arrow-right", box=_b(2704, 3423, 2864, 3578), kind="icon", expect=(21, 21)),
    # 表单 / 进度 / range
    dict(name="select-disabled", box=_b(3195, 203, 3893, 390), kind="panel", expect=(204, 33)),
    dict(name="progress-fill", box=_b(3201, 527, 3628, 631), kind="icon", expect=(200, 17)),
    dict(name="progress-fill-100", box=_b(3195, 769, 3893, 889), kind="icon", expect=(200, 17)),
    dict(name="progress-fill-indeterminate", box=_b(3195, 1019, 3893, 1137), kind="icon", expect=(200, 17)),
    dict(name="range-track", box=_b(3235, 1267, 3495, 1385), kind="icon", expect=(208, 15)),
    dict(name="range-thumb", box=_b(3272, 1513, 3404, 1703), kind="icon", expect=(19, 33)),
    dict(name="range-thumb-hover", box=_b(3272, 1818, 3404, 2006), kind="icon", expect=(19, 33)),
    dict(name="range-thumb-pressed", box=_b(3272, 2122, 3404, 2310), kind="icon", expect=(19, 33)),
    # 空态 / 徽标 / 禁用控件
    dict(name="empty-box", box=_b(3273, 2429, 3653, 2849), kind="icon", expect=(48, 48)),
    dict(name="badge-md", box=_b(3272, 2968, 3556, 3134), kind="icon", expect=(28, 19), baked_text=True),
    dict(name="badge-sm", box=_b(3272, 3254, 3448, 3353), kind="icon", expect=(20, 14), baked_text=True),
    dict(name="check-disabled", box=_b(3273, 3471, 3407, 3606), kind="icon", expect=(24, 24), baked_glyph=True),
    dict(name="radio-disabled", box=_b(3273, 3727, 3407, 3860), kind="icon", expect=(24, 24)),
]


def clamp(v):
    return max(0, min(255, int(round(v))))


def key_magenta(crop, bg, hard=45, erode=2):
    """洋红键色抠图（本板专用）。

    与 tools/xp_ui_slice.py 的 key_and_clean 的差别：
      旧版用 spill = max(r-g, b-g) 估 alpha，蓝色像素（r-g 为负、b-g 很大）会被
      误判成半透明，标题栏 / 进度条会被"漂白"成青色（实测 dialog-head 被改成青色）。
      本版改 spill = min(r-g, b-g)：只有 R 和 B 都明显高于 G 才是洋红污染；
      蓝色 min 为负 → alpha=1 原样保留，奶油色同理。
    另外：键色判定用切比雪夫距离（每通道差 ≤hard），比欧氏距离更适合逐通道噪声。
    JPEG 噪点靠 hard=45 + 中值 3 去块，边缘靠 alpha 腐蚀 2px 兜底。
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
                t = min(r - g, b - g)      # 洋红溢出量，同时削减 R/B 保亮度
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


def near_key_count(crop, bg, tol=12):
    px = crop.convert("RGB").load()
    w, h = crop.size
    n = 0
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            dr = abs(r - int(round(bg[0])))
            dg = abs(g - int(round(bg[1])))
            db = abs(b - int(round(bg[2])))
            if max(dr, dg, db) <= tol:
                n += 1
    return n


def fringe_count(img):
    """输出图里仍偏洋红（色相 270~330、饱和>0.25）的像素数，用于判断紫边。"""
    px = img.convert("RGBA").load()
    w, h = img.size
    n = 0
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a < 24:
                continue
            mx, mn = max(r, g, b), min(r, g, b)
            if mx == 0:
                continue
            s = (mx - mn) / float(mx)
            if s <= 0.25:
                continue
            # 色相
            if mx == r:
                hue = 60 * (((g - b) / float(mx - mn)) % 6)
            elif mx == g:
                hue = 60 * (((b - r) / float(mx - mn)) + 2)
            else:
                hue = 60 * (((r - g) / float(mx - mn)) + 4)
            if 265 <= hue <= 335:
                n += 1
    return n


def run_slice(im, bg, tol):
    """按 ITEMS 逐件裁切 → 抠图 → 缩放 → 落盘，返回报告条目列表。"""
    entries = []
    for it in ITEMS:
        box = it["box"]
        name = it["name"]
        ew, eh = it["expect"]
        if box is None:
            entries.append(dict(name=name, expect_1x=[ew, eh], usable=False,
                                verdict="源图未绘制该件（连通域中不存在）"))
            print("[MISS] %-28s 预期 %dx%d" % (name, ew, eh))
            continue
        crop = im.crop(box)
        sw, sh = crop.size
        near = near_key_count(crop, bg)
        # 中度去块噪：MedianFilter(3) 只压 JPEG 8x8 块噪，2px 斜角仍保留
        crop = crop.filter(ImageFilter.MedianFilter(3))
        keyed = key_magenta(crop, bg, hard=tol, erode=2)
        if it["kind"] == "panel":
            tw, th = max(1, int(round(sw * 0.5))), max(1, int(round(sh * 0.5)))
            out = resize_premult(keyed, (tw, th), Image.LANCZOS)
        else:
            out = resize_premult(keyed, (ew, eh), Image.LANCZOS)
        fringe = fringe_count(out)
        path = os.path.join(OUT, name + ".png")
        out.save(path, optimize=True)
        dw = (out.width - ew) / float(ew)
        dh = (out.height - eh) / float(eh)
        if it.get("baked_text"):
            verdict = "图内烘焙了 EMPTY 文字，与提示词要求（中心留空）不符，不可用作徽标底"
            usable = False
        elif it.get("baked_glyph"):
            verdict = "图内已画入勾号；只能当「禁用+已选」使用，不能当「禁用未选」"
            usable = True
        elif fringe > out.width * out.height * 0.004:
            verdict = "紫边像素 %.2f%%，偏高" % (100.0 * fringe / (out.width * out.height))
            usable = False
        else:
            verdict = "可用"
            usable = True
        entries.append(dict(
            name=name, crop_px=list(box), crop_size=[sw, sh], out_size=[out.width, out.height],
            expect_1x=[ew, eh], dev_w=round(dw, 3), dev_h=round(dh, 3),
            near_key_px=near, fringe_px=fringe, usable=usable, verdict=verdict,
        ))
        print("[%-3s] %-28s %dx%d -> %dx%d  预期 %dx%d  偏差 %+.0f%%/%+.0f%%  近键色 %d 紫边 %d  %s"
              % ("OK" if usable else "NG", name, sw, sh, out.width, out.height, ew, eh,
                 100 * dw, 100 * dh, near, fringe, verdict))
    return entries


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--preview", default="")
    ap.add_argument("--detect", action="store_true")
    ap.add_argument("--profile", action="store_true")
    ap.add_argument("--sheet", default="")
    ap.add_argument("--overlay", default="")
    ap.add_argument("--dump", default="")
    ap.add_argument("--dumpbox", default="")
    ap.add_argument("--rows", default="")
    ap.add_argument("--slice", action="store_true")
    ap.add_argument("--report", default="docs/xp-ui-20261106-slice-report.json")
    ap.add_argument("--contact", default="")
    ap.add_argument("--tol", type=float, default=45.0)
    args = ap.parse_args()

    im = Image.open(SRC).convert("RGB")
    mean, std, edges = measure_edges(im)
    print("源图", im.size, "键色均值", mean, "std", std)
    for e in edges:
        print(" ", e)
    if args.slice:
        entries = run_slice(im, mean, args.tol)
        os.makedirs(os.path.dirname(os.path.abspath(args.report)), exist_ok=True)
        with open(args.report, "w", encoding="utf-8") as f:
            json.dump(dict(
                source=SRC, source_size=list(im.size), key_color=[round(v, 2) for v in mean],
                key_color_hex="#%02X%02X%02X" % tuple(int(round(v)) for v in mean),
                key_std=[round(v, 2) for v in std], edges=edges, tol=args.tol,
                erode=2, median=3, items=entries,
            ), f, ensure_ascii=False, indent=1)
        print("report ->", args.report)
    if args.contact:
        paths = [os.path.join(OUT, it["name"] + ".png") for it in ITEMS
                 if it["box"] and os.path.exists(os.path.join(OUT, it["name"] + ".png"))]
        print("contact:", make_contact(paths, args.contact), len(paths))
    if args.preview:
        im.resize((1024, 1024), Image.BOX).save(args.preview, optimize=True)
        print("preview ->", args.preview)
    if args.profile:
        ink_map(im, mean, args.tol)
    if args.sheet:
        mask = make_mask(im, mean, args.tol)
        comps = [c for c in label_runs(mask, min_area=200) if keep_component(c)]
        comps = sorted(comps, key=lambda c: ((c[0] // 700), c[1], c[0]))
        for i, (x0, y0, x1, y1, area) in enumerate(comps):
            print("sheet#%2d  (%4d,%4d)  %4dx%-4d  fill=%.2f"
                  % (i, x0, y0, x1 - x0, y1 - y0, fill_ratio((x0, y0, x1, y1, area))))
        print("sheet:", make_sheet(im, comps, args.sheet), len(comps), "comps")
    if args.rows:
        mask = make_mask(im, mean, args.tol)
        comps = [c for c in label_runs(mask, min_area=200) if keep_component(c)]
        comps = sorted(comps, key=lambda c: ((c[0] // 700), c[1], c[0]))
        for tok in args.rows.split(","):
            i = int(tok)
            x0, y0, x1, y1, _ = comps[i]
            crop = im.crop((x0, y0, x1, y1))
            prof = row_profile(crop)
            print("rows of #%d  (%d,%d) %dx%d" % (i, x0, y0, x1 - x0, y1 - y0))
            prev = None
            for y, rgb in enumerate(prof):
                key = (rgb[0] // 6, rgb[1] // 6, rgb[2] // 6)
                if key != prev:
                    print("   y=%4d  rgb=%s" % (y, rgb))
                    prev = key
    if args.dumpbox:
        x0, y0, x1, y1 = [int(v) for v in args.dumpbox.split(",")]
        p = "D:\\Temp\\2\\dumpbox.png"
        im.crop((x0, y0, x1, y1)).save(p)
        print("dumpbox->", p, (x1 - x0, y1 - y0))
    if args.dump:
        mask = make_mask(im, mean, args.tol)
        comps = [c for c in label_runs(mask, min_area=200) if keep_component(c)]
        comps = sorted(comps, key=lambda c: ((c[0] // 700), c[1], c[0]))
        for tok in args.dump.split(","):
            i = int(tok)
            x0, y0, x1, y1, _ = comps[i]
            p = os.path.join("D:\\Temp\\2", "crop_%02d.png" % i)
            im.crop((x0, y0, x1, y1)).save(p)
            print("dump->", p, x0, y0, x1 - x0, y1 - y0)
    if args.overlay:
        mask = make_mask(im, mean, args.tol)
        comps = [c for c in label_runs(mask, min_area=200) if keep_component(c)]
        comps = sorted(comps, key=lambda c: ((c[0] // 700), c[1], c[0]))
        print("overlay:", make_overlay(im, comps, args.overlay))
    if args.detect:
        mask = make_mask(im, mean, args.tol)
        comps = label_runs(mask, min_area=200)
        kept = [c for c in comps if keep_component(c)]
        print("连通域 %d 个，保留 %d 个（tol=%.0f）" % (len(comps), len(kept), args.tol))
        big = [c for c in comps if not keep_component(c) and c[4] >= 1500]
        print("被丢弃的大块（area>=1500）%d 个" % len(big))
        for c in sorted(big, key=lambda t: -t[4])[:20]:
            x0, y0, x1, y1, area = c
            print("  drop x=%4d y=%4d w=%4d h=%4d area=%6d fill=%.2f"
                  % (x0, y0, x1 - x0, y1 - y0, area, fill_ratio(c)))
        for i, (x0, y0, x1, y1, area) in enumerate(sorted(kept, key=lambda t: (t[1], t[0]))):
            w, h = x1 - x0, y1 - y0
            print("%3d  x=%4d y=%4d w=%4d h=%4d area=%7d fill=%.2f"
                  % (i, x0, y0, w, h, area, fill_ratio((x0, y0, x1, y1, area))))


if __name__ == "__main__":
    main()
