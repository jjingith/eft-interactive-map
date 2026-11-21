# -*- coding: utf-8 -*-
"""R20.7e：把护甲/头盔「防护区域」图标的深色底抠掉，改成透明底 + 提亮的剪影。

参考站 db4tarkov 的 Zone 列是**白色护甲剪影 + 透明底**（放大看是纯白剪影、四周透出表格底色）；
本地这批图是从上游 assets 抠下来的 **深底不透明 PNG**（角像素 23,23,23,255），
在表格里表现为「一个黑底小方块里有个浅色剪影」——正是用户说的「太小、还要扣掉黑底」。

处理规则（按亮度分档）：
  · 暗部（亮度 < KEEP_AT 阈值）→ alpha = 0（底色去掉）
  · 亮部（剪影）→ 保留并按 GAIN 提亮，逼近参考站的白色剪影
  · 边缘中间调 → alpha 按亮度线性过渡，避免锯齿

原图先备份到 assets/icons/zones-orig/，脚本可重复执行（已处理过的会跳过，除非 --force）。

用法：
    python tools/r20_7_strip_zone_bg.py            # 处理
    python tools/r20_7_strip_zone_bg.py --force    # 强制重做
"""
from __future__ import annotations

import argparse
import os
import shutil

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "assets", "icons", "zones")
BAK = os.path.join(ROOT, "assets", "icons", "zones-orig")

# 低于这个亮度算「底色」，直接抠掉
DROP_BELOW = 96
# 高于这个亮度算「剪影实心」，完全保留
KEEP_AT = 150
# 剪影提亮倍数（参考站是白色剪影）
GAIN = 1.35


def process(path: str) -> None:
    im = Image.open(path).convert("RGBA")
    px = im.load()
    w, h = im.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            lum = (r * 299 + g * 587 + b * 114) // 1000
            if lum < DROP_BELOW:
                px[x, y] = (0, 0, 0, 0)
                continue
            if lum >= KEEP_AT:
                k = min(255, int(lum * GAIN))
                px[x, y] = (k, k, k, 255)
            else:
                # 中间调：alpha 线性过渡，避免边缘出现硬锯齿
                t = (lum - DROP_BELOW) / float(KEEP_AT - DROP_BELOW)
                k = min(255, int(lum * GAIN))
                px[x, y] = (k, k, k, max(0, min(255, int(a * t))))
    im.save(path)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="已处理过也重做")
    args = ap.parse_args()

    if not os.path.isdir(SRC):
        print("找不到目录:", SRC)
        return 1
    os.makedirs(BAK, exist_ok=True)
    marker = os.path.join(BAK, ".processed")
    done_before = os.path.exists(marker)
    n = 0
    for f in sorted(os.listdir(SRC)):
        if not f.lower().endswith(".png"):
            continue
        src = os.path.join(SRC, f)
        bak = os.path.join(BAK, f)
        if not os.path.exists(bak):
            shutil.copy2(src, bak)
        if done_before and not args.force:
            continue          # 已经处理过一轮，除非 --force
        process(src)
        n += 1
    with open(marker, "w", encoding="utf-8") as fh:
        fh.write("r20.7e zone background stripped\n")
    print("处理完成：%d 个文件；原图备份在 %s" % (n, os.path.relpath(BAK, ROOT).replace("\\", "/")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
