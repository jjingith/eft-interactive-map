#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""手绘防护区域图 —— 预处理管道（R31.3）。

处理用户重画的「内衬」部位图，输出到 build-cache/zone-gen/handraw/ 待接入。

用户交付格式约定：
  ui图标/20261031 防护区域重画/
      人物轮廓.png            ← 参考底（线稿，不参与合成）
      内衬/上胸.png 下胸.png 侧面.png 脖颈.png 腹股沟.png ...

图源特征：2000x2000、RGB、白底（255）、同一坐标系、区域块为米白/浅褐色，
          另含一层青绿色参考标记（需剔除）。

处理步骤：去白底 → 剔绿 · → 连通域清理（剔除碎片抗锯齿） → 输出透明 RGBA。
所有图共用同一坐标系，region 之间直接按坐标叠放即可，无需人为对齐。

**本脚本不写 assets/icons/zones/、不改 app.js**，只产出干净图层与预览；
确认无误后再由交接流程正式入库。仅依赖 PIL；运行期不联网。
"""
import hashlib
import os
import sys
from collections import deque

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = r"D:\personal\trae\02-塔科夫\ui图标\20261031 防护区域重画"
SRC_INNER = os.path.join(SRC, "内衬")
OUT = os.path.join(ROOT, "build-cache", "zone-gen", "handraw")
PARTS = os.path.join(OUT, "parts")

WHITE_THR = 246      # 亮度 >= 此值视为白底
MIN_BLOB = 400       # 连通域像素下限，滤掉碎片
CANVAS = None        # 原坐标系尺寸，读图后确定


def lum(c):
    return (c[0] * 299 + c[1] * 587 + c[2] * 114) // 1000


def is_green(c):
    """青绿色参考层（PS 标记 / 辅助十字）。"""
    r, g, b = c
    return g > 120 and g > r + 40 and g > b + 20


def mask_of(im):
    """非白、非绿 的像素集合。"""
    w, h = im.size
    px = im.load()
    m = set()
    for y in range(h):
        for x in range(w):
            c = px[x, y]
            if is_green(c) or lum(c) >= WHITE_THR:
                continue
            m.add((x, y))
    return m, px


def components(m):
    seen, res = set(), []
    for p in m:
        if p in seen:
            continue
        q, cur = deque([p]), []
        seen.add(p)
        while q:
            cx, cy = q.popleft()
            cur.append((cx, cy))
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1),
                           (1, 1), (-1, -1), (1, -1), (-1, 1)):
                n = (cx + dx, cy + dy)
                if n in m and n not in seen:
                    seen.add(n)
                    q.append(n)
        res.append(cur)
    return res


def keep_big(m):
    """保留大块主体，滤掉抗锯齿碎片。"""
    out = set()
    for c in components(m):
        if len(c) >= MIN_BLOB:
            out.update(c)
    return out


def strip(path):
    """读一张手绘图 → 干净的透明底 RGBA（保持原坐标系）。"""
    im = Image.open(path).convert("RGB")
    w, h = im.size
    m, px = mask_of(im)
    m = keep_big(m)
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    op = out.load()
    for x, y in m:
        c = px[x, y]
        op[x, y] = (c[0], c[1], c[2], 255)
    return out


def md5(path):
    with open(path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def load_parts():
    """读全部内衬部位，返回 {中文名: RGBA图层}，并打印体检信息。"""
    if not os.path.isdir(SRC_INNER):
        sys.exit("没找到手绘目录：%s" % SRC_INNER)
    layers, seen_md5 = {}, {}
    for fn in sorted(os.listdir(SRC_INNER)):
        if not fn.lower().endswith(".png"):
            continue
        name = os.path.splitext(fn)[0]
        path = os.path.join(SRC_INNER, fn)
        layers[name] = strip(path)
        h = md5(path)
        bb = layers[name].getbbox()
        dup = seen_md5.get(h)
        seen_md5[h] = name
        print("  %-8s bbox=%-26s %s" % (name, str(bb),
                                        "!! 与「%s」逐像素相同" % dup if dup else ""))
    return layers


def compose(layers, names):
    """按原坐标系叠放若干部位，裁到内容框。"""
    base = Image.new("RGBA", layers[next(iter(layers))].size, (0, 0, 0, 0))
    for n in names:
        if n in layers:
            base.alpha_composite(layers[n])
    bb = base.getbbox()
    return base.crop(bb) if bb else base


def preview(im, path, scale=0.5):
    """合成到深色背景上便于目检。"""
    bg = Image.new("RGBA", im.size, (40, 44, 52, 255))
    out = Image.alpha_composite(bg, im).convert("RGB")
    if scale != 1.0:
        out = out.resize((max(1, int(im.size[0] * scale)),
                          max(1, int(im.size[1] * scale))), Image.LANCZOS)
    out.save(path)


def main():
    os.makedirs(PARTS, exist_ok=True)
    print("== 手绘躯干部位体检 ==")
    layers = load_parts()

    print("\n== 输出干净图层 ==")
    for name, im in layers.items():
        im.save(os.path.join(PARTS, name + ".png"))
        print("  parts/%s.png  %s" % (name, im.getbbox()))

    print("\n== 典型组合预览 ==")
    combos = [
        ("PLATEminus类_上胸侧面", ["上胸", "侧面"]),
        ("PACA类_上下胸侧面", ["上胸", "下胸", "侧面"]),
        ("全躯干_含腹股沟", ["上胸", "下胸", "侧面", "腹股沟"]),
    ]
    for fn, names in combos:
        avail = [n for n in names if n in layers]
        if not avail:
            continue
        c = compose(layers, avail)
        preview(c, os.path.join(OUT, "预览_" + fn + ".png"))
        print("  预览_%s.png  %s  缺部件=%s"
              % (fn, c.size, [n for n in names if n not in layers] or "无"))

    missing = [n for n in ("上胸", "下胸", "侧面", "脖颈", "腹股沟", "肩部")
               if n not in layers]
    if missing:
        print("\n!! 尚缺部位：%s" % "、".join(missing))
    print("\n产物目录：%s" % OUT)


if __name__ == "__main__":
    main()
