#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""XT（第二张）8 倍合体板切片：竖向滚动条 / 竖向滑轨+滑块 / 窗口三键。

输入：02-塔科夫/ui图标/xp风格ui/Create ONE 4K sprite sheet for_6bd58ee2.png  (3840x2160)
输出：assets/xp-ui/ 下 28 件 PNG，并把条目追加进既有 manifest.json（原有 25 条一字不动）。

与第一张四图管线的差别：
  - 画布是 8 倍绘制（不是 4 倍），因此 SCALE=8，降采样必须用 BOX（面积平均），
    否则 8 倍下的 1px 斜面高光会被 LANCZOS 拉出灰边。
  - 元件坐标按实测包围盒给出（模型没有严格按提示词坐标表摆放，见报告误差表）。
  - 同一物件的三态统一成同一个外部尺寸（按组内最大宽高居中裁切）。

用法：
  python tools/xp_ui_slice_gen.py                # 默认不归一化
  python tools/xp_ui_slice_gen.py --normalize     # 可选：按现有 25 件色板做漂移校正
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xp_ui_slice as base

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(ROOT, "..", "ui图标", "xp风格ui")
OUT_DIR = os.path.join(ROOT, "assets", "xp-ui")
BOARD = "Create ONE 4K sprite sheet for_6bd58ee2.png"
SCALE = 8
ERODE = 2

# box = (x, y, w, h) 实测包围盒（8x 画布像素）
# group = 三态组：组内统一尺寸；sizes 由组内最大宽高算出
ITEMS = [
    # ---------------- 左列：竖向滚动条 ----------------
    dict(name="scroll-v-track", box=(223, 386, 174, 1371), size=(22, 171),
         slice_1x=(18, 3, 18, 3),
         use="竖向滚动条轨道（border-image repeat-y 平铺；端头斜面占 18px，中间 135 行实测行均值极差≤3）"),
    dict(name="scroll-v-thumb", box=(542, 386, 182, 405), group="sv-thumb",
         slice=None, use="竖向滚动条滑块-普通"),
    dict(name="scroll-v-thumb-hover", box=(542, 850, 182, 401), group="sv-thumb",
         slice=None, use="竖向滚动条滑块-悬停"),
    dict(name="scroll-v-thumb-pressed", box=(542, 1311, 182, 406), group="sv-thumb",
         slice=None, use="竖向滚动条滑块-按下"),
    dict(name="scroll-v-arrow-up", box=(872, 386, 227, 211), group="sv-up",
         slice=None, use="竖滚上箭头底板-普通（底板空白，三角由 glyph 叠）"),
    dict(name="scroll-v-arrow-up-hover", box=(872, 742, 227, 214), group="sv-up",
         slice=None, use="竖滚上箭头底板-悬停"),
    dict(name="scroll-v-arrow-up-pressed", box=(872, 1098, 227, 212), group="sv-up",
         slice=None, use="竖滚上箭头底板-按下"),
    dict(name="scroll-v-arrow-down", box=(1234, 386, 222, 211), group="sv-down",
         slice=None, use="竖滚下箭头底板-普通"),
    dict(name="scroll-v-arrow-down-hover", box=(1234, 742, 222, 214), group="sv-down",
         slice=None, use="竖滚下箭头底板-悬停"),
    dict(name="scroll-v-arrow-down-pressed", box=(1234, 1098, 222, 212), group="sv-down",
         slice=None, use="竖滚下箭头底板-按下"),
    dict(name="scroll-v-glyph-up", box=(926, 1432, 160, 86), slice=None,
         use="竖滚上三角（洋红底抠出，叠在箭头上）"),
    dict(name="scroll-v-glyph-down", box=(926, 1627, 161, 90), slice=None,
         use="竖滚下三角"),

    # ---------------- 中列：竖向滑轨 + 滑块 ----------------
    dict(name="slider-v-track", box=(1707, 386, 144, 1102), size=(18, 138),
         slice_1x=(8, 3, 8, 3), use="竖向滑轨轨道（全高行均值极差≤3，可 repeat-y）"),
    dict(name="slider-v-thumb", box=(1995, 386, 440, 224), group="sld-thumb",
         slice=None, use="竖向滑块-普通"),
    dict(name="slider-v-thumb-hover", box=(1995, 758, 440, 227), group="sld-thumb",
         slice=None, use="竖向滑块-悬停"),
    dict(name="slider-v-thumb-pressed", box=(1995, 1131, 440, 234), group="sld-thumb",
         slice=None, use="竖向滑块-按下"),

    # ---------------- 右列：窗口三键 ----------------
    dict(name="win-btn-min", box=(2678, 361, 254, 236), group="win-min",
         slice=None, use="窗口键-最小化-普通底板（空白）"),
    dict(name="win-btn-min-hover", box=(2678, 721, 254, 244), group="win-min",
         slice=None, use="窗口键-最小化-悬停"),
    dict(name="win-btn-min-pressed", box=(2678, 1092, 254, 231), group="win-min",
         slice=None, use="窗口键-最小化-按下"),
    dict(name="win-btn-max", box=(3023, 361, 255, 236), group="win-max",
         slice=None, use="窗口键-最大化-普通底板（空白）"),
    dict(name="win-btn-max-hover", box=(3023, 721, 255, 244), group="win-max",
         slice=None, use="窗口键-最大化-悬停"),
    dict(name="win-btn-max-pressed", box=(3023, 1092, 255, 231), group="win-max",
         slice=None, use="窗口键-最大化-按下"),
    dict(name="win-btn-close", box=(3367, 361, 258, 236), group="win-close",
         slice=None, use="窗口键-关闭-普通底板（实测橄榄黄面 #A5A300，空白；模型未按提示词红色）"),
    dict(name="win-btn-close-hover", box=(3367, 721, 258, 244), group="win-close",
         slice=None, use="窗口键-关闭-悬停（实测橄榄黄面提亮 #DBD900）"),
    dict(name="win-btn-close-pressed", box=(3366, 1092, 259, 231), group="win-close",
         slice=None, use="窗口键-关闭-按下（橄榄黄面）"),
    dict(name="win-glyph-min", box=(2716, 1611, 172, 65), slice=None,
         use="窗口键最小化横杠"),
    dict(name="win-glyph-max", box=(3065, 1557, 161, 157), slice=None,
         use="窗口键最大化方框"),
    dict(name="win-glyph-close", box=(3423, 1557, 159, 172), slice=None,
         use="窗口键关闭叉"),
]


def rounded_size(w, h):
    return (max(1, int(round(w / SCALE))), max(1, int(round(h / SCALE))))


def main():
    ap = base.argparse.ArgumentParser()
    ap.add_argument("--tol", type=float, default=base.DEFAULT_TOL)
    ap.add_argument("--normalize", action="store_true",
                    help="按现有 25 件色板做平移归一化（默认关闭）")
    args = ap.parse_args()

    path = os.path.join(SRC_DIR, BOARD)
    if not os.path.exists(path):
        print("缺少合体板:", path, file=sys.stderr)
        return 2
    im = Image.open(path).convert("RGB")
    bg, std = base.measure_bg(im)
    print("合体板 %s  bg=#%02X%02X%02X std=%.1f" % (im.size, bg[0], bg[1], bg[2], std))

    # 组内统一尺寸
    groups = {}
    for it in ITEMS:
        g = it.get("group")
        if not g:
            continue
        w, h = it["box"][2], it["box"][3]
        gw, gh = groups.get(g, (0, 0))
        groups[g] = (max(gw, w), max(gh, h))
    for it in ITEMS:
        g = it.get("group")
        if g:
            gw, gh = groups[g]
            x, y, w, h = it["box"]
            # 以自身包围盒中心为准，扩到组内统一尺寸后裁切
            nx = x - (gw - w) // 2
            ny = y - (gh - h) // 2
            it["crop_box"] = (nx, ny, nx + gw, ny + gh)
            it["size"] = rounded_size(gw, gh)
        else:
            x, y, w, h = it["box"]
            it["crop_box"] = (x, y, x + w, y + h)
            if not it.get("size"):
                it["size"] = rounded_size(w, h)

    built = []
    for it in ITEMS:
        crop = im.crop(it["crop_box"])
        rgba = base.key_and_clean(crop, bg, tol=args.tol, erode=ERODE)
        out = base.resize_premult(rgba, it["size"], resample=Image.BOX)
        built.append(dict(it=it, img=out, crop=crop))

    norm = None
    if args.normalize:
        offsets, info = base.estimate_shift([b["img"] for b in built])
        norm = dict(offsets=[round(v, 2) for v in offsets], **{k: v for k, v in info.items()})
        print("归一化 offsets=%s bands=%s" % ([round(v, 2) for v in offsets], info.get("band_hex")))
        for b in built:
            b["img"] = base.apply_shift(b["img"], offsets)

    manifest_path = os.path.join(OUT_DIR, "manifest.json")
    manifest = {}
    if os.path.exists(manifest_path):
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)
    assets = [a for a in manifest.get("assets", []) if a.get("file") not in
              {it["name"] + ".png" for it in ITEMS}]

    new_entries = []
    for b in built:
        it, out = b["it"], b["img"]
        out.save(os.path.join(OUT_DIR, it["name"] + ".png"), optimize=True)
        # source_box 与既有 25 条保持同一口径：8x 画布上的 (x0, y0, x1, y1) 裁切框
        bx, by, bxx, byy = it["crop_box"]
        sl1 = it.get("slice_1x")
        e = dict(
            file=it["name"] + ".png",
            size=[out.width, out.height],
            source_file=BOARD,
            source_box=[bx, by, bxx, byy],
            source_size=[bxx - bx, byy - by],
            bg_rgb=list(bg),
            slice_source=[v * SCALE for v in sl1] if sl1 else None,
            slice_1x=list(sl1) if sl1 else None,
            border_width_css=(" ".join("%spx" % v for v in sl1)) if sl1 else None,
            purpose=it["use"],
        )
        new_entries.append(e)
        print("  输出 %-28s %-9s" % (it["name"] + ".png", str(out.size)))

    assets.extend(new_entries)
    manifest["assets"] = assets
    manifest["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cfg = manifest.setdefault("config", {})
    cfg["generated_board"] = dict(
        file=BOARD, size=list(im.size), bg_rgb=list(bg),
        bg_hex="#%02X%02X%02X" % bg, bg_std=std, scale=SCALE,
        downsample="box", normalize=bool(args.normalize),
        normalize_info=norm,
        note="第二张合体板（模型生成）：竖向滚动条 / 竖向滑轨+滑块 / 窗口三键，共 28 件",
    )
    manifest["generated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print("\n追加 %d 条，manifest 现有 %d 条" % (len(new_entries), len(assets)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
