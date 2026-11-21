#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""最后一板连通域检测（DSU 行游程版），输出真实 bbox 与候选匹配。

不落图。用于决定切图参数：每件按实测 bbox 裁切，再按 bbox/1x 比例做盒式降采样。
"""
from __future__ import annotations

import json
import os
import sys

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = r"D:\personal\trae\02-塔科夫\ui图标\xp风格ui\Create ONE single 4K sprite she_881c048f.png"

SPEC = [
    ("current-gun-plate", 288, 32),
    ("version-plate", 136, 22),
    ("brand-plate", 120, 31),
    ("table-frame", 64, 64),
    ("empty-task", 48, 48),
    ("empty-story", 48, 48),
    ("empty-gun", 48, 48),
    ("scroll-v-arrow-down-normal", 22, 27),
    ("scroll-v-arrow-down-hover", 22, 27),
    ("sep-horizontal", 64, 2),
    ("sep-vertical", 2, 22),
    ("icon-map", 16, 16),
    ("icon-tasks", 16, 16),
    ("icon-ammo", 16, 16),
    ("icon-gun", 16, 16),
    ("icon-loadout", 16, 16),
    ("scroll-h-thumb", 44, 21),
    ("scroll-h-thumb-hover", 44, 21),
    ("scroll-h-thumb-pressed", 44, 21),
]


def band_stats(px, w, h, band=20):
    def st(y0, y1, x0, x1):
        n = 0
        s = [0, 0, 0]
        q = [0, 0, 0]
        for y in range(y0, y1):
            for x in range(x0, x1):
                r, g, b = px[x, y][:3]
                s[0] += r
                s[1] += g
                s[2] += b
                q[0] += r * r
                q[1] += g * g
                q[2] += b * b
                n += 1
        out = []
        for c in range(3):
            m = s[c] / n
            out.append((m, max(0.0, q[c] / n - m * m) ** 0.5))
        return out
    return {"top": st(0, band, 0, w), "bottom": st(h - band, h, 0, w),
            "left": st(0, h, 0, band), "right": st(0, h, w - band, w)}


def components(px, w, h, tol, key, ignore_border=6):
    br, bg, bb = key
    runs_prev = []
    parent = []

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    boxes = []  # root -> [x0,y0,x1,y1]
    row_runs_cache = []
    for y in range(h):
        # 横向游程（非键色）
        row = []
        x = 0
        while x < w:
            r, g, b = px[x, y][:3]
            on = max(abs(r - br), abs(g - bg), abs(b - bb)) > tol
            if not on:
                x += 1
                continue
            x0 = x
            while x < w:
                r, g, b = px[x, y][:3]
                if max(abs(r - br), abs(g - bg), abs(b - bb)) <= tol:
                    break
                x += 1
            row.append((x0, x - 1))
        row_runs_cache.append(row)
        cur = []
        for (a, b_) in row:
            idx = len(parent)
            parent.append(idx)
            boxes.append([a, y, b_, y])
            for (pa, pb, pidx) in runs_prev:
                if not (b_ < pa - 1 or a > pb + 1):
                    union(pidx, idx)
            cur.append((a, b_, idx))
        runs_prev = cur

    out = {}
    for i, bx in enumerate(boxes):
        root = find(i)
        o = out.setdefault(root, list(bx))
        o[0] = min(o[0], bx[0])
        o[1] = min(o[1], bx[1])
        o[2] = max(o[2], bx[2])
        o[3] = max(o[3], bx[3])

    res = []
    for root, (x0, y0, x1, y1) in out.items():
        cw = x1 - x0 + 1
        ch = y1 - y0 + 1
        if ignore_border and (x0 <= ignore_border or y0 <= ignore_border
                              or x1 >= w - 1 - ignore_border or y1 >= h - 1 - ignore_border):
            continue
        if cw * ch < 40:
            continue
        res.append({"x0": x0, "y0": y0, "x1": x1, "y1": y1,
                    "w": cw, "h": ch, "area": cw * ch, "ratio": cw / ch})
    res.sort(key=lambda r: (r["y0"] // 64, r["x0"]))
    return res


def main():
    im = Image.open(SRC).convert("RGB")
    w, h = im.size
    px = im.load()
    stats = band_stats(px, w, h)
    means = [[stats[s][c][0] for s in stats] for c in range(3)]
    spread = [max(m) - min(m) for m in means]
    sig = [max(stats[s][c][1] for s in stats) for c in range(3)]
    key = tuple(int(round(sum(m) / len(m))) for m in means)
    report = {"size": [w, h], "key": key, "keyHex": "#%02X%02X%02X" % key,
              "spread": spread, "sigma": sig, "bands": stats}
    print("板 %dx%d  键色 #%02X%02X%02X  四边互差 (%.2f,%.2f,%.2f)  σmax (%.2f,%.2f,%.2f)" % (
        w, h, key[0], key[1], key[2], spread[0], spread[1], spread[2],
        sig[0], sig[1], sig[2]))

    comps = components(px, w, h, 8, key)
    report["components"] = comps
    print("\n连通域 %d：" % len(comps))
    for i, r in enumerate(comps):
        print("  %-3d x=%-5d y=%-5d %4dx%-4d ratio %5.2f" % (
            i, r["x0"], r["y0"], r["w"], r["h"], r["ratio"]))

    # 匹配：对每个期望件找 ratio 最接近且规模合理的 bbox
    print("\n自动匹配（ratio 优先，尺寸按同一 scale 校验）：")
    best_scale = sum(c["w"] / 288.0 for c in comps if abs(c["ratio"] - 9) < 0.6) or 1
    print("  current-gun-plate 候选宽高比 9 的件数：", sum(1 for c in comps if abs(c["ratio"] - 9) < 0.6))

    json.dump(report, open(os.path.join(ROOT, "docs", "xp-ui-final-board-scan.json"), "w",
               encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n已写 docs/xp-ui-final-board-scan.json")


if __name__ == "__main__":
    main()
