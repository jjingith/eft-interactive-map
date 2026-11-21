#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""头部（头盔/面罩/护颚）防护区域图（R295）——
从用户 20261118 手绘重做的「头部防护图新版」抠出各部位，按 data/items.json
真实 z 自动拼合，替换 R31 时期的 zone-top / zone-back 等旧头部图。

- 部位词：头顶 / 后脑 / 面部 / 下颚 / 眼部 / 耳部 / 喉部 / 后颈。
  `喉部` = NeckFront，`后颈` = NeckBack；**仅在含真正头部区时才使用**，
  护甲（Armor）的 NeckFront/NeckBack 仍归「脖颈」，由躯干图表达（app.js 负责判定）。
- 每张手绘图 = 白底 + 部位色块(189,189,189) + 四角红十字标；本脚本去白底、剔红标，
  保留原坐标（统一 1000x1000 坐标系），因此各层天然对齐。
- 底图 `底图.png`（灰色侧脸轮廓 128,128,128）作为最底层，并按 BASE_ALPHA 淡化，
  让部位色块突出；另外单独产出 `zone-head-base.png`（只有底图、无部位色块）。
- 输出统一 150x150 PNG，文件名 `zone-head-<slug>.png`，与旧 `zone-*.png` 不冲突，
  便于回滚（旧文件不删）。
依赖：仅 PIL。
"""
import itertools
import json
import os
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data", "items.json")
ZONES_DIR = os.path.join(ROOT, "assets", "icons", "zones")
HAND = r"D:\personal\trae\02-塔科夫\ui图标\20261118头部防护图新版"

# 头部部位词顺序（必须与 app.js HEAD_ZONE_ORDER 完全一致）
HEAD_ORDER = ["头顶", "后脑", "面部", "下颚", "眼部", "耳部", "喉部", "后颈"]

# 手绘图文件名（用户 20261118 新版）
HAND_LAYERS = {
    "base": "底图.png",
    "头顶": "头顶.png",
    "后脑": "后脑勺.png",
    "面部": "面部.png",
    "下颚": "下颚.png",
    "眼部": "眼部.png",
    "耳部": "耳部.png",
    "喉部": "喉部.png",
    "后颈": "后颈.png",
}

# 上游 zone → 头部部位词（NeckFront/NeckBack 只在头部语境下生效）
ZONE_WORDS = {
    "ParietalHead": "头顶", "BackHead": "后脑", "HeadCommon": "面部",
    "Jaw": "下颚", "Eyes": "眼部", "Ears": "耳部",
    "NeckFront": "喉部", "NeckBack": "后颈",
}
# 判定「这是头部装备」的核心区：必须至少含一个，才把 Neck* 当头部部位。
HEAD_CORE = {"ParietalHead", "BackHead", "HeadCommon", "Jaw", "Eyes", "Ears"}

# 部位词 → 文件名 slug
SLUG = {
    "头顶": "top", "后脑": "back", "面部": "face", "下颚": "jaw",
    "眼部": "eyes", "耳部": "ears", "喉部": "throat", "后颈": "nape",
}

# 叠放顺序：底图→后颈→喉部→耳部→后脑→头顶→面部→下颚→眼部（后画的压在上面）
LAYER_ORDER = ("base", "后颈", "喉部", "耳部", "后脑", "头顶", "面部", "下颚", "眼部")

ICON_H = 150          # 输出高度
BASE_ALPHA = 0.38     # 底图淡化，让部位色块突出
OUT_PREFIX = "zone-head-"

# R298：底图与部位原来都是灰（128 vs 189），在深色界面上几乎糊成一片。
# 现在底图压成冷灰、部位染成暖金，明度与色相双拉开；描边保持深色以维持轮廓。
BASE_TINT = (116, 122, 132)
ZONE_TINT = (234, 184, 92)
ZONE_LUMA_FLOOR = 150     # 低于此亮度视为描边/细节，保留原色


def is_red(c):
    r, g, b = c
    return r > 150 and g < 110 and b < 110


def strip_layer(path):
    """去白底 + 剔红标，保留部位原始像素与坐标（1000x1000）。"""
    im = Image.open(path).convert("RGBA")
    w, h = im.size
    px = im.load()
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    op = out.load()
    # 新版手绘图最外圈有 2-3px 的浅灰画布边框（非白非红），会把取景窗撑成整张画布
    edge = 4
    for y in range(h):
        if y < edge or y >= h - edge:
            continue
        for x in range(w):
            if x < edge or x >= w - edge:
                continue
            r, g, b, a = px[x, y]
            if a < 20:
                continue
            if r > 240 and g > 240 and b > 240:   # 白底
                continue
            if is_red((r, g, b)):                  # 四角红十字标
                continue
            op[x, y] = (r, g, b, a)
    return out


def solid_tint(im, color):
    """整层单色化：所有非透明像素换成 color，保留 alpha（底图用）。"""
    px = im.load()
    w, h = im.size
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    op = out.load()
    for y in range(h):
        for x in range(w):
            a = px[x, y][3]
            if a:
                op[x, y] = (color[0], color[1], color[2], a)
    return out


def colorize(im, color):
    """部位染色：主体（亮度 >= ZONE_LUMA_FLOOR）映射到 color 并保留明暗层次，
    描边/深色细节保持原样，避免把轮廓也染成一片金色。"""
    px = im.load()
    w, h = im.size
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    op = out.load()
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if not a:
                continue
            luma = (r + g + b) / 3.0
            if luma >= ZONE_LUMA_FLOOR:
                f = max(0.55, min(1.0, luma / 189.0))
                op[x, y] = (int(color[0] * f), int(color[1] * f), int(color[2] * f), a)
            else:
                k = 0.85
                op[x, y] = (int(r * k), int(g * k), int(b * k), a)
    return out


def head_words(zs):
    """zone 列表 → 头部部位词集合；不含真正头部区时返回空（交给躯干逻辑）。"""
    raw = set(zs or [])
    if not (raw & HEAD_CORE):
        return None
    words = set()
    for z in raw:
        w = ZONE_WORDS.get(z)
        if w:
            words.add(w)
    return words or None


def zone_key(words):
    return "|".join(w for w in HEAD_ORDER if w in words)


def slug_for(words):
    return "-".join(SLUG[w] for w in HEAD_ORDER if w in words)


def main():
    layers = {k: strip_layer(os.path.join(HAND, v)) for k, v in HAND_LAYERS.items()}
    # R298：底图冷灰、部位暖金 —— 原来 128/189 两档灰在深色界面上几乎不可分
    layers["base"] = solid_tint(layers["base"], BASE_TINT)
    for key in list(layers):
        if key != "base":
            layers[key] = colorize(layers[key], ZONE_TINT)
    if BASE_ALPHA < 1:
        base = layers["base"]
        base.putalpha(base.getchannel("A").point(lambda v: int(v * BASE_ALPHA)))

    # 统一取景窗：按底图不透明区域外扩，保证 25 种组合同框
    bbox = layers["base"].getbbox() or (0, 0, 1000, 1000)
    pad = 24
    wx0, wy0 = max(0, bbox[0] - pad), max(0, bbox[1] - pad)
    wx1, wy1 = min(1000, bbox[2] + pad), min(1000, bbox[3] + pad)
    ww, wh = wx1 - wx0, wy1 - wy0
    scale = ICON_H / float(wh)
    iw, ih = int(ww * scale + 0.5), ICON_H
    print("取景窗 %s → 输出 %dx%d" % ((wx0, wy0, wx1, wy1), iw, ih))

    items = json.load(open(DATA, encoding="utf-8"))["items"]

    # 枚举所有真实头部组合（全类别：头盔 / 面罩 / 护颚 / 眼镜）
    combos = {}
    for it in items.values():
        z = it.get("z")
        if not isinstance(z, list) or not z:
            continue
        words = head_words(z)
        if not words:
            continue
        combos.setdefault(frozenset(words), zone_key(words))

    # R298：**本体 + 可装配件**的合并组合。配装界面装上 面罩 / 护颚 / 护颈 后，
    # 左栏装饰图与「当前装备行」会显示合并后的防护区，这些组合也必须预先出图，
    # 否则会退化成「子集图 + 未标注」甚至文字降级。
    # 枚举每个头盔各子槽的「装 / 不装」笛卡尔积，覆盖多配件同时装的情况。
    for it in items.values():
        if (it.get("pt") or "") != "Helmet":
            continue
        own = it.get("z") or []
        if not (set(own) & HEAD_CORE):
            continue
        slots = []
        for s in (it.get("slots") or []):
            opts = [None] + [c for c in (s.get("allow") or []) if c in items]
            slots.append(opts)
        if not slots:
            continue
        for pick in itertools.product(*slots):
            merged = list(own)
            for cid in pick:
                if cid:
                    merged.extend(items[cid].get("z") or [])
            words = head_words(merged)
            if words:
                combos.setdefault(frozenset(words), zone_key(words))

    os.makedirs(os.path.join(ROOT, "build-cache", "zone-gen"), exist_ok=True)
    manifest = {}
    for words, key in combos.items():
        slug = slug_for(words)
        fname = "%s%s.png" % (OUT_PREFIX, slug)
        canvas = Image.new("RGBA", (1000, 1000), (0, 0, 0, 0))
        canvas.alpha_composite(layers["base"])
        for p in LAYER_ORDER:
            if p != "base" and p in words:
                canvas.alpha_composite(layers[p])
        crop = canvas.crop((wx0, wy0, wx1, wy1)).resize((iw, ih), Image.LANCZOS)
        crop.save(os.path.join(ZONES_DIR, fname))
        manifest[key] = "assets/icons/zones/" + fname
        print("  %-46s -> %s" % (key, fname))

    # 无任何部位色块的头像底图（供「头盔但无防护区域」等场景）
    base_canvas = Image.new("RGBA", (1000, 1000), (0, 0, 0, 0))
    base_canvas.alpha_composite(layers["base"])
    base_crop = base_canvas.crop((wx0, wy0, wx1, wy1)).resize((iw, ih), Image.LANCZOS)
    base_crop.save(os.path.join(ZONES_DIR, OUT_PREFIX + "base.png"))
    print("  %-46s -> %sbase.png" % ("(空)", OUT_PREFIX))

    with open(os.path.join(ROOT, "build-cache", "zone-gen", "head_mapping.txt"), "w",
              encoding="utf-8") as f:
        f.write("/* 头部段（R295 手绘重做、含喉部/后颈，由 tools/gen_zone_head_handraw.py 生成） */\n")
        for key in sorted(manifest, key=lambda k: [HEAD_ORDER.index(x) for x in k.split("|")]):
            f.write('    "%s": "%s",\n' % (key, manifest[key]))
    print("\n头部组合 %d 种已生成；映射见 build-cache/zone-gen/head_mapping.txt" % len(manifest))


if __name__ == "__main__":
    main()
