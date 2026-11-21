"""把用户提供的任务图标（灰底）处理成透明 PNG，并加一层 Windows XP 风格图标底。

源图：`D:/personal/trae/02-塔科夫/ui图标/任务图标/` 下的三张 88×88 PNG
（剧情任务标 / 支线任务标 / 行动任务标，白字形 + 灰蓝底）。

处理：
  1. 按亮度阈值抠掉灰底（保留抗锯齿边缘），字形统一成白色；
  2. 画一层 XP Luna 风格的圆角底板：立体渐变 + 内外描边 + 顶部高光 + 投影；
  3. 字形居中叠在底板上，带一点深色投影保证浅色区域也清楚。

产物（96×96 PNG）：
  assets/icons/task-way.png    支线任务标（蓝底）
  assets/icons/task-story.png  剧情任务标（青绿底）
  assets/icons/task-action.png 行动任务标（琥珀底）

用法：python tools/build_task_icons.py [--src 目录]
"""

import argparse
import os

from PIL import Image, ImageDraw, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "assets", "icons")
DEFAULT_SRC = r"D:\personal\trae\02-塔科夫\ui图标\任务图标"

SOURCE = [
    ("支线任务标.png", "task-way.png", "blue"),
    ("剧情任务标.png", "task-story.png", "green"),
    ("行动任务标.png", "task-action.png", "amber"),
]

# XP Luna 三套底色：上亮、下深的立体渐变（颜色停靠点用 0~1 的相对高度）
PALETTES = {
    "blue": [(0.0, (250, 253, 255)), (0.18, (225, 240, 255)), (0.5, (126, 178, 236)),
             (0.82, (44, 106, 198)), (1.0, (25, 70, 145))],
    "green": [(0.0, (245, 255, 251)), (0.18, (214, 250, 238)), (0.5, (96, 208, 176)),
              (0.82, (18, 145, 108)), (1.0, (7, 95, 72))],
    "amber": [(0.0, (255, 253, 244)), (0.18, (255, 243, 210)), (0.5, (246, 196, 96)),
              (0.82, (206, 132, 24)), (1.0, (150, 88, 9))]
}
EDGE = {
    "blue": (18, 45, 88),
    "green": (8, 62, 48),
    "amber": (104, 60, 8)
}

SIZE = 96          # 画布
BASE = (8, 8, 88, 88)   # 圆角底板范围（80×80）
RADIUS = 13


def remove_background(path):
    """把灰蓝底抠成透明：亮度 150 以下全透明，230 以上全不透明，中间线性过渡。"""
    im = Image.open(path).convert("RGBA")
    src = im.load()
    out = Image.new("RGBA", im.size, (0, 0, 0, 0))
    dst = out.load()
    for y in range(im.height):
        for x in range(im.width):
            r, g, b, _a = src[x, y]
            lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
            if lum <= 150:
                a = 0
            elif lum >= 230:
                a = 255
            else:
                a = int(round((lum - 150) * 255 / 80))
            dst[x, y] = (255, 255, 255, a)
    return out.crop(out.getbbox())


def gradient_base(palette):
    """按行画竖直渐变，再裁成圆角。"""
    base = Image.new("RGBA", (BASE[2] - BASE[0], BASE[3] - BASE[1]), (0, 0, 0, 0))
    draw = ImageDraw.Draw(base)
    w, h = base.size
    stops = palette
    for y in range(h):
        t = y / float(h - 1)
        for i in range(len(stops) - 1):
            t0, c0 = stops[i]
            t1, c1 = stops[i + 1]
            if t0 <= t <= t1:
                k = (t - t0) / (t1 - t0) if t1 > t0 else 0
                color = tuple(int(round(c0[j] + (c1[j] - c0[j]) * k)) for j in range(3))
                break
        else:
            color = stops[-1][1]
        draw.line([(0, y), (w, y)], fill=color + (255,))
    mask = Image.new("L", base.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], radius=RADIUS, fill=255)
    base.putalpha(mask)
    return base


def build(src_glyph, palette_name):
    edge = EDGE[palette_name]
    canvas = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))

    # 投影：底板形状的暗色圆角矩形，模糊后压在下面
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle(
        [BASE[0] + 1, BASE[1] + 3, BASE[2] + 1, BASE[3] + 3], radius=RADIUS, fill=(8, 16, 30, 110))
    shadow = shadow.filter(ImageFilter.GaussianBlur(4))
    canvas.alpha_composite(shadow)

    base = gradient_base(PALETTES[palette_name])
    canvas.alpha_composite(base, (BASE[0], BASE[1]))

    # XP 立体描边：外侧深色 2px + 内侧左上白色高光 1px + 右下暗部 1px
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    d.rounded_rectangle([BASE[0], BASE[1], BASE[2] - 1, BASE[3] - 1], radius=RADIUS,
                        outline=edge + (220,), width=2)
    d.arc([BASE[0] + 2, BASE[1] + 2, BASE[2] - 3, BASE[3] - 3], 180, 270,
          fill=(255, 255, 255, 200), width=1)
    canvas.alpha_composite(overlay)

    # 顶部玻璃高光：从顶边向中间渐隐
    gloss = Image.new("RGBA", (BASE[2] - BASE[0], (BASE[3] - BASE[1]) // 2), (255, 255, 255, 0))
    gd = ImageDraw.Draw(gloss)
    gh = gloss.height
    for y in range(gh):
        a = int(120 * (1 - y / float(gh)) ** 1.6)
        gd.line([(0, y), (gloss.width, y)], fill=(255, 255, 255, a))
    gmask = Image.new("L", gloss.size, 0)
    ImageDraw.Draw(gmask).rounded_rectangle([0, 0, gloss.width - 1, gloss.height + RADIUS],
                                            radius=RADIUS, fill=255)
    gloss.putalpha(Image.composite(gloss.getchannel("A"), Image.new("L", gloss.size, 0), gmask))
    canvas.alpha_composite(gloss, (BASE[0], BASE[1] + 1))

    # 字形：缩放到 44px 内，带深色投影，居中略偏上
    glyph = src_glyph.copy()
    max_side = 44
    k = min(max_side / float(glyph.width), max_side / float(glyph.height))
    glyph = glyph.resize((max(1, int(round(glyph.width * k))), max(1, int(round(glyph.height * k))),
                          ), Image.LANCZOS)
    gx = (SIZE - glyph.width) // 2
    gy = (SIZE - glyph.height) // 2 - 1
    gshadow = Image.new("RGBA", glyph.size, (0, 0, 0, 0))
    gshadow.putalpha(glyph.getchannel("A"))
    gshadow = Image.composite(Image.new("RGBA", glyph.size, (6, 14, 26, 150)),
                              Image.new("RGBA", glyph.size, (0, 0, 0, 0)), glyph.getchannel("A"))
    gshadow = gshadow.filter(ImageFilter.GaussianBlur(1.6))
    canvas.alpha_composite(gshadow, (gx, gy + 2))
    canvas.alpha_composite(glyph, (gx, gy))
    return canvas


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=DEFAULT_SRC)
    args = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    for name, out_name, palette in SOURCE:
        src = os.path.join(args.src, name)
        if not os.path.exists(src):
            raise SystemExit("缺少源图：%s" % src)
        glyph = remove_background(src)
        icon = build(glyph, palette)
        path = os.path.join(OUT, out_name)
        icon.save(path, "PNG")
        print("%-40s -> %s (%d×%d)" % (name, os.path.relpath(path, ROOT), icon.width, icon.height))


if __name__ == "__main__":
    main()
