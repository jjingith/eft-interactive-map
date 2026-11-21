#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""护甲/胸挂防护区域图（R31.3）——
从用户手绘重做的「20261101防弹衣防护部位图」抠出各部位，按 data/items.json 真实 z 自动拼合。

- 躯干部位词：上胸 / 腹部 / 侧面 / 裆部 / 脖颈 / 肩部。
- **不再绘制「前插板」叠层**（R31.3）：用户明确表示插板图案只是试做、不应出现在防护部位图例里。
  插板区（Plate_*）仍按所覆盖体区计入部位词（前/后插板→上胸，侧插板→侧面），
  因此插板背心的"覆盖面积"不丢，只是不再额外叠一张插板兜图案。
- 每张手绘图 = 白底 + 部位色块 + 四角红十字标；本脚本自动去白底、剔红标、保留部位原坐标，
  因此拼合时各部位天然对齐（都在 2000x2000 同一坐标系）。
- **R31.4：新增「未穿护甲」的人形轮廓底图**（`底图 人物轮廓.png`）作为每张躯干组合图的最底层，
  让防护色块落在身体轮廓上；另外单独产出 `zone-base.png`（只有底图、无任何部位色块），
  供「无防护区域」的护甲/胸挂行显示。
- 仅生成躯干组合（头部沿用既有 zone-*.png，不动）。
依赖：仅 PIL。
"""
import json
import os
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data", "items.json")
ZONES_DIR = os.path.join(ROOT, "assets", "icons", "zones")
HAND = r"D:\personal\trae\02-塔科夫\ui图标\20261101防弹衣防护部位图"

# 躯干部位词顺序（与 app.js ZONE_WORD_ORDER 的躯干段一致；R31.3 去掉「前插板」）
TORSO_ORDER = ["上胸", "腹部", "侧面", "裆部", "脖颈", "肩部"]

ZONE_WORDS = {
    "ParietalHead": "头顶", "BackHead": "后脑", "HeadCommon": "面部", "Jaw": "下颚",
    "Eyes": "眼部", "Ears": "耳部",  # 头部词（仅用于区分 head/torso，不参与躯干拼合）
    "NeckFront": "脖颈", "NeckBack": "脖颈",
    "LeftUpperArm": "肩部", "RightUpperArm": "肩部",
    "RibcageUp": "上胸", "SpineTop": "上胸",          # 上胸 + 上背（正反面统一）
    "RibcageLow": "腹部", "SpineDown": "腹部",        # 下胸/胃部 + 下背
    "LeftSideChestDown": "侧面", "RightSideChestDown": "侧面",
    "Pelvis": "裆部", "PelvisBack": "裆部",
}
HEAD_WORDS = {"头顶", "后脑", "面部", "下颚", "眼部", "耳部"}


def zone_word(z):
    if not z:
        return None
    if z.startswith("Plate_"):
        # R31.3：插板区只按覆盖体区投影成部位词，不再产出「前插板」视觉叠层
        r = z[len("Plate_"):]
        if "side" in r:
            return "侧面"
        if "chest" in r or r.endswith("_back"):
            return "上胸"
        return None
    return ZONE_WORDS.get(z)


def zone_key(zs):
    words = set()
    for z in (zs or []):
        w = zone_word(z)
        if w:
            words.add(w)
    order = TORSO_ORDER + list(HEAD_WORDS)
    return "|".join(w for w in order if w in words) or None


def is_red(c):
    r, g, b = c
    return r > 150 and g < 110 and b < 110


def strip_layer(path):
    """去白底 + 剔红标，保留部位原始像素与坐标（2000x2000）。"""
    im = Image.open(path).convert("RGBA")
    w, h = im.size
    px = im.load()
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    op = out.load()
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a < 20:
                continue
            if r > 238 and g > 238 and b > 238:   # 白底
                continue
            if is_red((r, g, b)):                  # 四角红十字标
                continue
            op[x, y] = (r, g, b, a)
    return out


# 20261101 手绘各部位文件名（内衬 = 软甲层）。R31.3 不再引用「前插板.png」。
# R31.4 新增 base = 未穿护甲的人形轮廓底图（每张躯干图的最底层）。
HAND_LAYERS = {
    "base":     "底图 人物轮廓.png",
    "chest":    "上胸内衬.png",
    "abdomen":  "腹部内衬.png",
    "side":     "侧面内衬.png",
    "shoulder": "肩部内衬.png",
    "neck":     "脖颈内衬.png",
    "groin":    "裆部内衬.png",
}

# 躯干统一取景窗（肩到肩、颈到裆），保证所有组合同框、仅填充块不同
WINDOW = (640, 475, 1375, 1415)  # x0,y0,x1,y1
ICON_H = 150  # 输出高度（CSS 再缩放到 40x40）

# R31.5：底图「淡一点」——只降人形轮廓的不透明度，让防护色块（内衬）更突出。
BASE_ALPHA = 0.4


def build_layer(name):
    im = strip_layer(os.path.join(HAND, HAND_LAYERS[name]))
    if name == "base" and BASE_ALPHA < 1:
        im.putalpha(im.getchannel("A").point(lambda v: int(v * BASE_ALPHA)))
    return im


# 部位词 → ASCII slug（与头部 zone-*.png 命名风格一致）
SLUG = {"上胸": "chest", "腹部": "abdomen", "侧面": "side",
        "裆部": "groin", "脖颈": "neck", "肩部": "shoulder"}
# 部位词 → 图层键（拼合时用）
WORD_TO_LAYER = {"上胸": "chest", "腹部": "abdomen", "侧面": "side",
                 "裆部": "groin", "脖颈": "neck", "肩部": "shoulder"}

# 叠放顺序：底图→颈→肩→胸→腹→侧→裆（后画者覆盖前画者，保证层次自然）
LAYER_ORDER = ("base", "neck", "shoulder", "chest", "abdomen", "side", "groin")


def slug_for(parts):
    ordered = [p for p in TORSO_ORDER if p in parts]
    return "-".join(SLUG[p] for p in ordered)


def main():
    layers = {k: build_layer(k) for k in HAND_LAYERS}
    # 取景窗尺寸
    wx0, wy0, wx1, wy1 = WINDOW
    ww, wh = wx1 - wx0, wy1 - wy0
    scale = ICON_H / float(wh)
    iw, ih = int(ww * scale + 0.5), ICON_H

    data = json.load(open(DATA, encoding="utf-8"))
    items = data["items"]

    # 枚举所有躯干组合键（R31.3：插板不再单独成层，按 parts 归并）
    combos = {}
    for it in items.values():
        z = it.get("z")
        if not isinstance(z, list) or not z:
            continue
        key = zone_key(z)
        if not key:
            continue
        parts = set()
        has_head = False
        for zz in z:
            w = zone_word(zz)
            if w and w in TORSO_ORDER:
                parts.add(w)
            if zz in ("ParietalHead", "BackHead", "HeadCommon", "Jaw", "Eyes", "Ears"):
                has_head = True
        if has_head:
            continue  # 混入头部区（如面罩带护颈）→ 不生成躯干图，走降级
        combos.setdefault(frozenset(parts), key)

    manifest = {}
    for parts, key in combos.items():
        slug = slug_for(parts)
        fname = "zone-%s.png" % slug
        canvas = Image.new("RGBA", (2000, 2000), (0, 0, 0, 0))
        canvas.alpha_composite(layers["base"])          # R31.4：人形轮廓底图（最底层）
        present = {WORD_TO_LAYER[w] for w in parts if w in WORD_TO_LAYER}
        for p in LAYER_ORDER:
            if p != "base" and p in present:
                canvas.alpha_composite(layers[p])
        crop = canvas.crop((wx0, wy0, wx1, wy1))
        crop = crop.resize((iw, ih), Image.LANCZOS)
        out_path = os.path.join(ZONES_DIR, fname)
        crop.save(out_path)
        manifest[key] = "assets/icons/zones/" + fname
        print("  %-16s -> %s  (%d 组合键)" % (slug, fname, 1))

    # R31.4：单独产出「未穿护甲」底图（只有人形轮廓，无任何部位色块）
    base_canvas = Image.new("RGBA", (2000, 2000), (0, 0, 0, 0))
    base_canvas.alpha_composite(layers["base"])
    base_crop = base_canvas.crop((wx0, wy0, wx1, wy1)).resize((iw, ih), Image.LANCZOS)
    base_crop.save(os.path.join(ZONES_DIR, "zone-base.png"))
    print("  %-16s -> %s  (无护甲底图)" % ("base", "zone-base.png"))

    # 写出映射字面量（仅躯干段）供贴入 app.js
    with open(os.path.join(ROOT, "build-cache", "zone-gen", "torso_mapping.txt"), "w", encoding="utf-8") as f:
        f.write("/* 躯干段（R31.4 手绘重做、已去前插板叠层、含人形轮廓底图，由 tools/gen_zone_torso_handraw.py 生成） */\n")
        for key in sorted(manifest, key=lambda k: [TORSO_ORDER.index(x) if x in TORSO_ORDER else 99 for x in k.split("|")]):
            f.write('    "%s": "%s",\n' % (key, manifest[key]))
    print("\n躯干组合 %d 种已生成；映射见 build-cache/zone-gen/torso_mapping.txt" % len(manifest))


if __name__ == "__main__":
    main()
