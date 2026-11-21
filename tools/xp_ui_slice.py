#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""XP 风格 UI 素材切片管线（可重跑，纯标准库 + Pillow）。

输入：02-塔科夫/ui图标/xp风格ui 下的 4 张洋红底素材总图
输出：02-塔科夫/eft-interactive-map/assets/xp-ui/ 下的独立 PNG + manifest.json

管线步骤（每件素材独立处理，稳定可重跑）：
  1. 按源图实测的洋红键色做容差抠图（RGB 欧氏距离，默认阈值 25，可 --tol 覆盖）
  2. alpha 向内腐蚀 2px（MinFilter(5)），消掉外沿 1~2px 的洋红混色过渡
  3. 洋红去污：对半透明像素反解 C = (obs - (1-a)*bg) / a，去掉 R/B 偏色
  4. 预乘 alpha 后 LANCZOS 降采样 1/4，再反预乘，避免缩放把洋红带进画面
  5. 逐件写 PNG，并汇总 manifest.json（尺寸 / 切片保护边 / 用途 / 源图与包围盒）

实测依据（来自对源图的逐像素扫描，不是估计）：
  - 四张图的背景不是数学纯色：均值分别为 #F30DF4 / #FA05F9 / #F805F7 / #F806F7，
    单通道标准差约 1，180x180 区域内最多 304 种颜色，因此必须走容差 + 腐蚀。
  - 外沿存在 1~2px 洋红混色（实测边缘像素如 (226,34,232)、(158,80,160)、(212,34,217)）。
  - 文本输入框内画有文本插入符（黑色竖线，位于源图 x=163~169），若直接 9-slice
    会被拉伸成一条贯穿输入框的黑线，因此必须先擦除（见 erase_caret）。
  - 同一列按钮 5 个状态的高度在源图里分别是 166/169/174/173/177 px，
    相差 11px，会带来状态切换跳变；本管线把 5 态统一缩放到 95x42 @1x。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime

from PIL import Image, ImageChops, ImageFilter, ImageStat

# ----------------------------------------------------------------------------
# 源 / 目标
# ----------------------------------------------------------------------------
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(ROOT, "..", "ui图标", "xp风格ui")
OUT_DIR = os.path.join(ROOT, "assets", "xp-ui")

F_BTN = "XP-Style Button States — Textle_952bcd15.png"
F_FC = "XP-Style Form Controls — Textle_78ca08b3.png"
F_TP = "XP-Style Title Plaques & Status_ebc3e75a.png"
F_WC = "XP-Style Window Chrome — Textle_e8a477c1.png"

SCALE = 4          # 源图按 1/4 降到 1x 使用（圆角硬台阶步进 8~9px，1/4 后最清晰）
ERODE_PX = 2       # alpha 向内腐蚀像素（源图尺度）
DEFAULT_TOL = 25   # RGB 欧氏距离阈值

# ----------------------------------------------------------------------------
# 素材清单
#   box  = 源图包围盒 (x0, y0, x1, y1)，右/下开区间
#   size = 输出 1x 尺寸；None 表示按 box 除以 SCALE 自动取整
#   slice= 保护边（源图 px，(上, 右, 下, 左)）；None 表示整件使用、不 9-slice
# ----------------------------------------------------------------------------
ITEMS = [
    # ---- 按钮五态：统一成 95x42，消除状态间 166~177px 的高低差 ----
    dict(name="btn-normal", src=F_BTN, box=(219, 258, 599, 424), size=(95, 42),
         slice=(20, 20, 20, 20), use="按钮-普通态，border-image 九宫格"),
    dict(name="btn-hover", src=F_BTN, box=(219, 632, 599, 801), size=(95, 42),
         slice=(20, 20, 20, 20), use="按钮-悬停态"),
    dict(name="btn-pressed", src=F_BTN, box=(219, 1032, 599, 1206), size=(95, 42),
         slice=(20, 20, 20, 20), use="按钮-按下态（斜角明暗反转）"),
    dict(name="btn-focus", src=F_BTN, box=(219, 1422, 599, 1595), size=(95, 42),
         slice=(20, 20, 20, 20), use="按钮-焦点态（内含黑点虚线框）"),
    dict(name="btn-disabled", src=F_BTN, box=(219, 1812, 599, 1989), size=(95, 42),
         slice=(20, 20, 20, 20), use="按钮-禁用态（无高光）"),

    # ---- 表单控件 ----
    dict(name="input", src=F_FC, box=(130, 140, 1207, 271), size=(269, 33),
         slice=(20, 20, 20, 20), use="文本输入框框体", erase_caret=True),
    dict(name="select", src=F_FC, box=(1284, 140, 2100, 271), size=(204, 33),
         slice=(20, 20, 20, 20), use="下拉框输入区"),
    dict(name="select-arrow", src=F_FC, box=(2094, 141, 2233, 271), size=(35, 32),
         slice=None, use="下拉框箭头按钮（三角已画入，整件使用）"),
    dict(name="check-off", src=F_FC, box=(130, 404, 224, 500), size=(24, 24),
         slice=None, use="复选框-未选"),
    dict(name="check-on", src=F_FC, box=(343, 404, 437, 500), size=(24, 24),
         slice=None, use="复选框-选中（勾已画入）"),
    dict(name="check-indeterminate", src=F_FC, box=(556, 404, 651, 500), size=(24, 24),
         slice=None, use="复选框-半选（横杠已画入）"),
    dict(name="radio-off", src=F_FC, box=(823, 404, 921, 500), size=(25, 24),
         slice=None, use="单选-未选"),
    dict(name="radio-on", src=F_FC, box=(1013, 404, 1110, 500), size=(24, 24),
         slice=None, use="单选-选中"),
    dict(name="track", src=F_FC, box=(130, 695, 1039, 755), size=(208, 15),
         slice=(24, 32, 24, 32),
         use="滑轨（左段 130~386 + 右段 465~1038 拼接，中间滑块覆盖区已跳过）",
         stitch=[(130, 695, 387, 755), (465, 695, 1039, 755)]),
    dict(name="thumb", src=F_FC, box=(1106, 648, 1181, 779), size=(19, 33),
         slice=None, use="滑块（整件使用，固定尺寸）"),
    dict(name="scroll-h-track", src=F_FC, box=(1368, 687, 1650, 768), size=(71, 21),
         slice=(16, 0, 16, 16), use="横向滚动条轨道（左端圆头，右端齐平）"),
    dict(name="scroll-h-thumb", src=F_FC, box=(1657, 687, 1832, 768), size=(44, 21),
         slice=None, use="横向滚动条滑块"),
    dict(name="progress-frame", src=F_FC, box=(130, 914, 1038, 999), size=(227, 21),
         slice=(20, 20, 20, 20), use="进度条框体（蓝色填充已替换为轨道色，蓝条由 CSS 另画）",
         strip_blue=True),
    dict(name="groupbox", src=F_FC, box=(1119, 915, 2239, 1531), size=(280, 154),
         slice=(20, 20, 20, 20), use="分组框框体（已抹掉叠在上边框的凸起标题标签）",
         strip_tab=True),

    # ---- 标题牌 / 状态 ----
    dict(name="plaque-1", src=F_TP, box=(185, 518, 1501, 674), size=(329, 39),
         slice=(20, 20, 20, 56),
         use="宽标题牌；左 56px 保护边用于保留左侧内凹槽"),
    dict(name="plaque-2", src=F_TP, box=(1577, 518, 2538, 674), size=(240, 39),
         slice=(20, 20, 20, 56), use="中标题牌"),
    dict(name="plaque-3", src=F_TP, box=(2609, 518, 3341, 674), size=(183, 39),
         slice=(20, 20, 20, 56), use="窄标题牌"),

    # ---- 窗口框架 ----
    dict(name="titlebar", src=F_WC, box=(110, 582, 2986, 726), size=(719, 36),
         slice=(20, 20, 20, 20),
         use="标题栏长条（已裁掉右侧三键，三键由 CSS 重建）"),
    dict(name="tab-active", src=F_WC, box=(116, 1429, 560, 1571), size=(111, 36),
         slice=(20, 20, 0, 20), use="激活标签页（底部不设保护边，与内容区衔接）"),
    dict(name="tab-inactive", src=F_WC, box=(570, 1450, 922, 1571), size=(88, 30),
         slice=(20, 20, 0, 20), use="非激活标签页"),
]

# 每组按钮的源图包围盒（用于 manifest 审计与高度一致性说明）
BTN_STATE_BOXES = {
    "btn-normal": (380, 166),
    "btn-hover": (380, 169),
    "btn-pressed": (380, 174),
    "btn-focus": (380, 173),
    "btn-disabled": (380, 177),
}


# ----------------------------------------------------------------------------
# 基础工具
# ----------------------------------------------------------------------------
def measure_bg(im: Image.Image):
    """用四周 20px 边条均值实测洋红键色（四张图各不相同）。"""
    w, h = im.size
    strips = [
        im.crop((0, 0, w, 20)),
        im.crop((0, h - 20, w, h)),
        im.crop((0, 0, 20, h)),
        im.crop((w - 20, 0, w, h)),
    ]
    means = [ImageStat.Stat(s).mean for s in strips]
    rgb = tuple(int(round(sum(m[i] for m in means) / len(means))) for i in range(3))
    std = max(round(ImageStat.Stat(s).stddev[0], 1) for s in strips)
    return rgb, std


def erase_caret(crop: Image.Image, box):
    """擦除文本输入框内画入的文本插入符。

    依据：源图 x=163~169 有一段黑色竖线（实测该列存在 sum(RGB)<300 的连续像素），
    换算到本件裁剪坐标约 32~40px，落在 9-slice 的中间拉伸区，会被横向拉成一条黑线。
    做法：用左邻列 x=161 的像素覆盖 162~170 整列，保留原有纵向明暗。
    """
    x0, _, _, _ = box
    px = crop.load()
    w, h = crop.size
    fill_x = 161 - x0
    for dx in range(162 - x0, 170 - x0 + 1):
        if not (0 <= dx < w):
            continue
        for y in range(h):
            px[dx, y] = px[fill_x, y]


def strip_blue(crop: Image.Image, box, track_rgb):
    """把进度条内部的蓝色填充替换成轨道色，让框体可安全 9-slice。

    蓝色实测 (52,116,210)，轨道实测 (221,217,201)；判据 B-R>30 只命中蓝色。
    """
    px = crop.load()
    w, h = crop.size
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            if b - r > 30:
                px[x, y] = (track_rgb[0], track_rgb[1], track_rgb[2])


def strip_tab(crop: Image.Image, box, span, rows, ref_col_src):
    """抹掉叠在分组框上边框上的凸起标题标签。

    依据：实测该标签占据源图 x=1183~1488、y=903~940（行扫描：该区间内像素与
    参考列 x=1600 的差异 >25），其两侧投影阴影还向下延续到 y≈965。
    标签压在上边框之上，而上边框在同一行内是水平均匀的，因此直接用参考列
    在该行的像素回填标签覆盖区，既恢复边框条纹又不破坏左侧圆角。
    """
    x0, y0, _, _ = box
    px = crop.load()
    lx, rx = span[0] - x0, span[1] - x0
    refx = ref_col_src - x0
    for y in rows:
        ry = y - y0
        if not (0 <= ry < crop.height):
            continue
        col = px[refx, ry]
        for x in range(lx, rx + 1):
            px[x, ry] = col


def key_and_clean(crop: Image.Image, bg, tol=DEFAULT_TOL, erode=ERODE_PX):
    """容差抠图 + 去污 + 腐蚀，返回 RGBA。

    alpha 不用"到背景色的距离"估计：洋红与深色描边的 50% 混色，
    到背景的距离已经接近满值，会被判成不透明，紫色描边就会留下来。
    改用"通道污染比例"估计：洋红的 R-G / B-G 均约 230，混色像素按比例下降，
    因此 alpha = 1 - max(R-G, B-G) / (BG 的 R-G)。
    再用 obs = a*C + (1-a)*bg 反解出真实色 C，最后才腐蚀 alpha——
    顺序必须是"先按原始 alpha 去污，再腐蚀"，否则腐蚀改写了 alpha，
    反解就会把颜色算错，留下 (120,88,120) 这类紫边。
    """
    rgb = crop.convert("RGB")
    px = rgb.load()
    w, h = rgb.size
    br, bgc, bb = bg
    spill_ref = float(max(br - bgc, bb - bgc)) or 1.0

    alpha = Image.new("L", (w, h), 0)
    apx = alpha.load()
    out = rgb.convert("RGBA")
    o = out.load()

    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            dr, dg, db = r - br, g - bgc, b - bb
            if (dr * dr + dg * dg + db * db) ** 0.5 <= tol:
                apx[x, y] = 0
                continue
            spill = max(r - g, b - g)
            a = 1.0 - min(1.0, max(0.0, spill) / spill_ref)
            if a <= 0.06:
                apx[x, y] = 0
                continue
            av = int(round(a * 255))
            apx[x, y] = av
            if a >= 0.98:
                o[x, y] = (r, g, b, 255)
            else:
                o[x, y] = (clamp((r - (1 - a) * br) / a),
                           clamp((g - (1 - a) * bgc) / a),
                           clamp((b - (1 - a) * bb) / a),
                           av)

    if erode > 0:
        alpha = alpha.filter(ImageFilter.MinFilter(erode * 2 + 1))
    out.putalpha(alpha)
    return out


def clamp(v):
    return max(0, min(255, int(round(v))))


def resize_premult(img: Image.Image, size, resample=Image.LANCZOS) -> Image.Image:
    """预乘 alpha 缩放，再反预乘，避免透明区的洋红被插值带进边缘。

    resample 默认 LANCZOS（源图 4 倍降到 1x）；8 倍绘制的新板应传 Image.BOX
    （面积平均），保证 8 倍缩放是整数下采样、斜面 1px 高光不被拉成灰边。
    """
    img = img.convert("RGBA")
    r, g, b, a = img.split()
    pr = ImageChops.multiply(r, a)
    pg = ImageChops.multiply(g, a)
    pb = ImageChops.multiply(b, a)
    pre = Image.merge("RGB", (pr, pg, pb)).resize(size, resample)
    al = a.resize(size, resample)
    ap = al.load()
    out = Image.new("RGBA", size, (0, 0, 0, 0))
    op = out.load()
    pp = pre.load()
    w, h = size
    for y in range(h):
        for x in range(w):
            av = ap[x, y]
            if av == 0:
                continue
            f = av / 255.0
            op[x, y] = (clamp(pp[x, y][0] / f), clamp(pp[x, y][1] / f), clamp(pp[x, y][2] / f), av)
    return out


# ----------------------------------------------------------------------------
# 漂移色归一化（--normalize，默认关闭）
#
# 目标色板 = 现有 1x 件的实测色阶（逐行取样，见报告里的色板表）：
#   #3B412F 图标深色 / #626355 1px 外框 / #757861 凹槽顶线 / #A5A396 内底暗边
#   #DDD9CA 凹陷内体 / #EAE7D8 按钮下段 / #EDEAD9 按钮体 / #F4F2E8 内顶次高光
#   #F5F5EB 顶面高光 / #FFFFFF 最亮高光
#
# 做法（第二版，按"整体平移"而非"端点回归"）：
#   1) 只在同一张画布的成品像素池里估计一次漂移，而不是逐件估计——小件（16x16 的
#      勾选框）像素少、没有按钮体，逐件估计必然被黑色描边/白色内腔带偏。
#   2) 锚点取"米色带"（亮度 0.50~1.00、通道跨度 <= 40）里出现次数最多的色簇，
#      它的中心就是按钮体，直接对到 #EDEAD9，得到每通道偏移量。
#      不做"暗端→#626355"的回归：暗端在不同件里可能是纯黑描边，强行抬到 #626355
#      会同时毁掉 1px 外框和图标（上一版就是这么坏的）。
#   3) 应用时只做平移（单调），因此 1px 外框仍最暗、内高光仍最亮，层次不被压平；
#      平移量对饱和像素取三通道均值，保住红/绿/蓝的色相。
#   4) 两端饱和保护：max(RGB)<=3 的纯黑描边与 min(RGB)>=250 的纯白高光不参与平移。
#      前者是 1px 外框/图标，后者是被漂移打爆到 255 的高光（信息已丢，抬回来只会变灰）。
#   5) alpha<8 的像素与 alpha 本身一律不动。
# ----------------------------------------------------------------------------
RAMP_DARK = (0x62, 0x63, 0x55)     # 1px 外框
RAMP_BRIGHT = (0xFF, 0xFF, 0xFF)   # 最亮高光
RAMP_MEDIAN = (0xED, 0xEA, 0xD9)   # 按钮体（主色）
RAMP = [
    (0x3B412F, "图标深色"), (0x626355, "1px 外框"), (0x757861, "凹槽顶线"),
    (0xA5A396, "内底暗边"), (0xDDD9CA, "凹陷内体"), (0xEAE7D8, "按钮下段"),
    (0xEDEAD9, "按钮体"), (0xF4F2E8, "内顶次高光"), (0xF5F5EB, "顶面高光"),
    (0xFFFFFF, "最亮高光"),
]


def luma(c):
    return (0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]) / 255.0


NORM_ALPHA_FLOOR = 8
NORM_BAND_EDGES = (0.30, 0.50, 0.70, 0.90)
# 现有 25 件在这三个亮度带里的实测平均色（xp_ui_slice 量出，见报告色板表）。
# 选中间三段而非全分位：米色在 0.30~0.90 区间近乎平坦，分位归属漂移对均值影响最小，
# 因此"漂移池带均值 → 参考带均值"的差就是纯平移量，与画面里哪种元件占多大面积无关。
REF_BANDS = ((0xE9, 0xE6, 0xD5), (0xEC, 0xE9, 0xD8), (0xEE, 0xEB, 0xDB))
NORM_MIN_ANCHOR = 48
NORM_SAT_HI = 250              # min(RGB) >= 250：被漂移打爆的纯白，平移不动
NORM_SAT_LO = 3                # max(RGB) <= 3：纯黑描边，平移不动
NORM_SCALAR_SPREAD = 60        # 明显彩色只做标量平移，保住色相


def _band_means(images):
    """按亮度分位取各带的平均色；只统计 alpha>=floor 的精灵像素。"""
    pts = []
    for img in images:
        img = img.convert("RGBA")
        px = img.load()
        for y in range(img.height):
            for x in range(img.width):
                r, g, b, a = px[x, y]
                if a < NORM_ALPHA_FLOOR:
                    continue
                pts.append((luma((r, g, b)), r, g, b))
    if not pts:
        return [], 0
    pts.sort(key=lambda t: t[0])
    n = len(pts)
    out = []
    edges = NORM_BAND_EDGES
    for lo, hi in zip(edges[:-1], edges[1:]):
        a, b = int(n * lo), max(int(n * lo) + 1, int(n * hi))
        seg = pts[a:min(n, b)]
        if not seg:
            out.append(None)
            continue
        m = [sum(p[i] for p in seg) / len(seg) for i in (1, 2, 3)]
        out.append(m)
    return out, n


def _median3(vals):
    s = sorted(vals)
    return s[len(s) // 2]


def estimate_shift(images):
    """估计漂移偏移（每通道），返回 (offsets, info)。

    做法：把成品像素按亮度分位切三段，各自取平均色；与参考 25 件的同段平均色作差，
    每通道取三个差值的中位数。纯平移漂移下三段差值相同，取中位数即去噪；
    画面组成不同（长轨道占大面积）也不会把锚点带偏，因为比的是"同一亮度段"。
    """
    means, n = _band_means(images)
    if not means or any(m is None for m in means):
        return (0.0, 0.0, 0.0), dict(ok=False, reason="像素不足，无法分带")
    if n < NORM_MIN_ANCHOR * 3:
        return (0.0, 0.0, 0.0), dict(ok=False, reason="像素不足（%d）" % n)
    deltas = [[REF_BANDS[i][c] - means[i][c] for i in range(len(means))] for c in range(3)]
    offsets = tuple(_median3(deltas[c]) for c in range(3))
    return offsets, dict(ok=True, pixels=n,
                         band_means=[[round(v, 1) for v in m] for m in means],
                         band_hex=["#%02X%02X%02X" % tuple(int(round(v)) for v in m) for m in means],
                         band_deltas=[[round(v, 2) for v in d] for d in deltas],
                         offsets=[round(v, 2) for v in offsets])


def apply_shift(img, offsets, strength=1.0, alpha_floor=NORM_ALPHA_FLOOR):
    """按每通道偏移做整体平移；只动 alpha>=floor 的像素，不改 alpha。"""
    img = img.convert("RGBA")
    ox, oy, oz = (v * strength for v in offsets)
    if max(abs(ox), abs(oy), abs(oz)) < 0.5:
        return img
    scalar = (ox + oy + oz) / 3.0
    px = img.load()
    for y in range(img.height):
        for x in range(img.width):
            r, g, b, a = px[x, y]
            if a < alpha_floor:
                continue
            mx, mn = max(r, g, b), min(r, g, b)
            if mx <= NORM_SAT_LO or mn >= NORM_SAT_HI:
                continue
            if mx - mn >= NORM_SCALAR_SPREAD:
                nr, ng, nb = r + scalar, g + scalar, b + scalar
            else:
                nr, ng, nb = r + ox, g + oy, b + oz
            px[x, y] = (clamp(nr), clamp(ng), clamp(nb), a)
    return img


def normalize_palette(img, strength=1.0):
    """单件入口（自测/离线用）：先估计再平移。整板处理请用 estimate_shift+apply_shift。"""
    offsets, _ = estimate_shift([img])
    return apply_shift(img, offsets, strength)


# ----------------------------------------------------------------------------
# 主流程
# ----------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tol", type=float, default=DEFAULT_TOL, help="RGB 欧氏距离阈值")
    ap.add_argument("--src", default=SRC_DIR)
    ap.add_argument("--out", default=OUT_DIR)
    ap.add_argument("--normalize", action="store_true",
                    help="对成品按目标色板做漂移归一化（默认关闭；开启才写入 manifest）")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)

    sheets = {}
    sources = []
    for fn in (F_BTN, F_FC, F_TP, F_WC):
        path = os.path.join(args.src, fn)
        if not os.path.exists(path):
            print("缺少源图:", path, file=sys.stderr)
            return 2
        im = Image.open(path).convert("RGB")
        bg, std = measure_bg(im)
        sheets[fn] = (im, bg)
        sources.append(dict(file=fn, size=list(im.size), bg_rgb=list(bg),
                            bg_hex="#%02X%02X%02X" % bg, bg_std=std))
        print("源图 %-52s %s  bg=%s #%02X%02X%02X  std=%.1f"
              % (fn, im.size, bg, bg[0], bg[1], bg[2], std))

    built = []
    for it in ITEMS:
        im, bg = sheets[it["src"]]
        box = it["box"]
        if it.get("stitch"):
            parts = [im.crop(b) for b in it["stitch"]]
            crop = Image.new("RGB", (sum(p.width for p in parts), parts[0].height))
            x = 0
            for p in parts:
                crop.paste(p, (x, 0))
                x += p.width
        else:
            crop = im.crop(box)

        if it.get("erase_caret"):
            erase_caret(crop, box)
        if it.get("strip_blue"):
            strip_blue(crop, box, (221, 217, 201))
        if it.get("strip_tab"):
            strip_tab(crop, box, (1183, 1488), range(915, 995), 1600)

        rgba = key_and_clean(crop, bg, tol=args.tol, erode=ERODE_PX)
        size = it["size"] or (max(1, round(crop.width / SCALE)), max(1, round(crop.height / SCALE)))
        out_img = resize_premult(rgba, size)
        built.append(dict(it=it, img=out_img, crop=crop, box=box, bg=bg))

    norm_info = None
    if args.normalize:
        # 逐画布估计：同一源图（= 模型一次生成的同一张板）共用一组偏移，
        # 小件因此不会被自己的黑描边带偏。
        norm_info = {}
        pool = {}
        for b in built:
            pool.setdefault(b["it"]["src"], []).append(b["img"])
        for fn, imgs in pool.items():
            offsets, info = estimate_shift(imgs)
            norm_info[fn] = dict(offsets=[round(v, 2) for v in offsets],
                                 info_ok=info.get("ok", False),
                                 body_hex=info.get("body_hex"),
                                 body_observed=info.get("body_observed"),
                                 anchor_px=info.get("anchor_px"),
                                 beige_px=info.get("beige_px"),
                                 reason=info.get("reason"))
            print("归一化 %-52s body=%s offsets=%s"
                  % (fn, info.get("body_hex"), [round(v, 2) for v in offsets]))
        for b in built:
            b["img"] = apply_shift(b["img"], tuple(norm_info[b["it"]["src"]]["offsets"]))

    manifest_assets = []
    for b in built:
        it, out_img, crop, bg = b["it"], b["img"], b["crop"], b["bg"]
        dst = os.path.join(args.out, it["name"] + ".png")
        out_img.save(dst, optimize=True)

        sl = it["slice"]
        manifest_assets.append(dict(
            file=it["name"] + ".png",
            size=[out_img.width, out_img.height],
            source_file=it["src"],
            source_box=list(b["box"]),
            source_size=[crop.width, crop.height],
            bg_rgb=list(bg),
            slice_source=list(sl) if sl else None,
            slice_1x=[round(v / SCALE, 2) for v in sl] if sl else None,
            border_width_css=(" ".join("%spx" % round(v / SCALE, 2) for v in sl)) if sl else None,
            purpose=it["use"],
        ))
        print("  输出 %-22s %-9s slice=%s" % (it["name"] + ".png", str(out_img.size), sl))

    manifest = dict(
        generator="tools/xp_ui_slice.py",
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        config=dict(key_tolerance=args.tol, erode_px=ERODE_PX, scale=SCALE,
                    normalize=bool(args.normalize),
                    normalize_ramp=[[("#%02X%02X%02X" % c), n] for c, n in RAMP] if args.normalize else None,
                    normalize_per_sheet=norm_info,
                    background_rule="按每张源图四周边条均值实测，容差抠图后腐蚀 2px 再去污"),
        sources=sources,
        button_source_sizes=BTN_STATE_BOXES,
        button_normalized=dict(note="5 个按钮状态源图高度 166/169/174/173/177px，已统一缩放为 95x42 @1x",
                               size=[95, 42]),
        assets=manifest_assets,
    )
    with open(os.path.join(args.out, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print("\n共输出 %d 件，manifest -> %s" % (len(manifest_assets), os.path.join(args.out, "manifest.json")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
