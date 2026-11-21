# -*- coding: utf-8 -*-
"""R18.2 修改前后对照图（证据生成，不做任何美化）。

三张图：
  1. before-after-icons.png      —— 右侧列表图标：原 webp（深色底） vs 新白底 PNG，
                                    都按浏览器里的实际显示尺寸 30px 贴到白色行底上；
  2. before-after-gun-source.png —— 枪械剪影的**根因**：本体 base-image（裁切，无枪托）
                                    vs 预设 base-image（完整装配）；
  3. before-after-gun-silhouette.png —— 旧剪影（本体图 + R18.1 的 4% 填洞） vs 新剪影。
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "ui-windows-xp", "r18.2")
ICO = os.path.join(ROOT, "assets", "icons-items")
WHITE = os.path.join(ROOT, "assets", "icons-transparent")  # R19.4 更名：白底废止，同一批透明素材
SRC = os.path.join(ROOT, "assets", "ui", "placeholders", "_src")
PH = os.path.join(ROOT, "assets", "ui", "placeholders")

# 五类代表：亮色护甲 / 深色头盔 / 枪 / 背包 / 面部
SAMPLES = [
    ("68948a95d8f2b85fb705e2a6", "护甲 6B45"),
    ("5b40e1525acfc4771e1c6611", "头盔 ULACH"),
    ("5bf3e03b0db834001d2c4a9c", "AK-74"),
    ("59e763f286f7742ee57895da", "背包 Pilgrim"),
    ("572b7f1624597762ae139822", "面部 头套"),
]


def font(size):
    for name in ("msyh.ttc", "simhei.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default()


def icons_sheet():
    """原 webp vs 白底 PNG，均按 30px 显示尺寸贴在白色行底。"""
    DISPLAY = 30
    cell_w, cell_h = 190, 120
    cols = len(SAMPLES)
    sheet = Image.new("RGB", (cell_w * cols, cell_h * 2 + 60), (255, 255, 255))
    dr = ImageDraw.Draw(sheet)
    dr.text((8, 8), "配装右侧列表图标：改前（上） / 改后（下）—— 按浏览器实际显示尺寸 30px",
            fill=(0, 0, 0), font=font(15))
    for i, (iid, label) in enumerate(SAMPLES):
        x = i * cell_w + 12
        # 上排：原 webp（不透明深色底）
        try:
            old = Image.open(os.path.join(ICO, iid + ".webp")).convert("RGB")
            row = Image.new("RGB", (cell_w - 20, 44), (255, 255, 255))
            row.paste(old.resize((DISPLAY, DISPLAY), Image.LANCZOS), (4, 7))
            sheet.paste(row, (x, 40))
        except Exception as exc:
            dr.text((x, 44), "缺图: %s" % exc, fill=(200, 0, 0), font=font(12))
        # 下排：白底 PNG（透明底 + 白行底）
        try:
            new = Image.open(os.path.join(WHITE, iid + ".png")).convert("RGBA")
            row = Image.new("RGB", (cell_w - 20, 44), (255, 255, 255))
            bg = Image.new("RGBA", (DISPLAY, DISPLAY), (255, 255, 255, 255))
            thumb = new.resize((DISPLAY, DISPLAY), Image.LANCZOS)
            bg.alpha_composite(thumb)
            row.paste(bg.convert("RGB"), (4, 7))
            sheet.paste(row, (x, 40 + 60))
        except Exception as exc:
            dr.text((x, 104), "缺图: %s" % exc, fill=(200, 0, 0), font=font(12))
        dr.text((x, 88), label, fill=(60, 60, 60), font=font(12))
    p = os.path.join(OUT, "before-after-icons.png")
    sheet.save(p)
    print("→", os.path.relpath(p, ROOT))


def gun_source():
    """根因对照：本体 base-image（裁切，无枪托） vs 预设 base-image（完整）。"""
    pairs = [
        ("本体图（R18.1 用的素材）", os.path.join(SRC, "5bf3e03b0db834001d2c4a9c.webp")),
        ("预设图（R18.2 改用）", os.path.join(SRC, "5c0c1ce886f77401c119d014.webp")),
    ]
    W, H = 660, 240
    sheet = Image.new("RGB", (W, H * 2 + 40), (245, 245, 245))
    dr = ImageDraw.Draw(sheet)
    dr.text((10, 8), "AK-74 剪影素材对照：本体图不含枪托（枪托是可拆 mod 配件）",
            fill=(0, 0, 0), font=font(15))
    for i, (label, path) in enumerate(pairs):
        y = 34 + i * H
        im = Image.open(path).convert("RGBA")
        im.thumbnail((W - 24, H - 46), Image.LANCZOS)
        board = Image.new("RGB", (W - 24, im.size[1]), (255, 255, 255))
        board.paste(im, (0, 0), im)
        sheet.paste(board, (12, y + 26))
        dr.text((12, y + 4), label, fill=(20, 20, 20), font=font(14))
    p = os.path.join(OUT, "before-after-gun-source.png")
    sheet.save(p)
    print("→", os.path.relpath(p, ROOT))


def gun_silhouette():
    """旧剪影（本体图 + 4% 填洞，复现 R18.1） vs 新剪影。"""
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import build_slot_placeholders as B

    # 复现 R18.1：本体图 + max_ratio=0.04
    mask, w, h, parts, holes = B.mask_from_alpha(os.path.join(SRC, "5bf3e03b0db834001d2c4a9c.webp"))
    old_mask, _ = B.fill_holes(mask, w, h, 0.04)
    old = B.render(old_mask, w, h, 260, 106)
    new = Image.open(os.path.join(PH, "primary.png")).convert("RGB")

    W = 560
    pad = 10
    hh = int(106 * (W - pad) / 260) if False else 106
    scale = (W - 2 * pad) / 260.0
    nh = int(106 * scale)
    sheet = Image.new("RGB", (W, nh * 2 + 80), (235, 235, 235))
    dr = ImageDraw.Draw(sheet)
    dr.text((10, 8), "AK-74 空槽剪影：改前（上，缺枪托） / 改后（下，完整）",
            fill=(0, 0, 0), font=font(15))
    for i, (label, im) in enumerate((("改前 · R18.1（本体裁切图）", old),
                                     ("改后 · R18.2（预设完整图）", new))):
        big = im.resize((W - 2 * pad, nh), Image.LANCZOS)
        y = 34 + i * (nh + 30)
        sheet.paste(big, (pad, y + 22))
        dr.text((pad, y + 4), label, fill=(20, 20, 20), font=font(13))
    p = os.path.join(OUT, "before-after-gun-silhouette.png")
    sheet.save(p)
    print("→", os.path.relpath(p, ROOT))


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    icons_sheet()
    gun_source()
    gun_silhouette()
