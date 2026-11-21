# -*- coding: utf-8 -*-
"""R96 素材加工：滚动条滑块三层切图（A） + 四件几何件（C）。

A：从现有 scroll-v-thumb / scroll-h-thumb 三态图里**按像素切出**顶帽 / 1px 中段 / 底帽，
   不重绘、不缩放，供 CSS 三层背景使用。
C：用 Pillow 逐像素画下箭头两态与两条分隔线，三角严格 15x10、水平居中、距板顶 9px。

用法：python tools/xp_ui_r96_pieces.py
"""
import os
import sys
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "assets", "xp-ui")

# --- A：竖滑块的帽高 / 中段取样行（实测 23x51：y0 顶影、y1 顶白边、y2 面高光、
#     y3..46 均匀面、y47 下过渡、y48..49 底暗边、y50 底影） ---------------------
V_TOP_CAP = (0, 0, 23, 3)      # y0..2
V_MID_ROW = 25                 # 均匀中段取样行
V_BOTTOM_CAP = (0, 47, 23, 51)  # y47..50

# 横滑块 44x21：x0 影、x1 亮边、x2 内高光、x3..40 均匀面、x41 过渡、x42..43 底暗边
H_LEFT_CAP = (0, 0, 3, 21)     # x0..2
H_MID_COL = 22                 # 均匀中段取样列
H_RIGHT_CAP = (41, 0, 44, 21)  # x41..43

STATES = ["", "-hover", "-pressed"]


def slice_thumbs():
    made = []
    for suffix in STATES:
        src = Image.open(os.path.join(ASSETS, "scroll-v-thumb%s.png" % suffix)).convert("RGBA")
        w, h = src.size
        assert (w, h) == (23, 51), "竖滑块尺寸变动: %s %s" % (suffix, src.size)
        caps = {
            "scroll-v-thumb-cap-top%s.png" % suffix: src.crop(V_TOP_CAP),
            "scroll-v-thumb-mid%s.png" % suffix: src.crop((0, V_MID_ROW, w, V_MID_ROW + 1)),
            "scroll-v-thumb-cap-bottom%s.png" % suffix: src.crop(V_BOTTOM_CAP),
        }
        for name, im in caps.items():
            im.save(os.path.join(ASSETS, name))
            made.append((name, im.size))

        src = Image.open(os.path.join(ASSETS, "scroll-h-thumb%s.png" % suffix)).convert("RGBA")
        w, h = src.size
        assert (w, h) == (44, 21), "横滑块尺寸变动: %s %s" % (suffix, src.size)
        caps = {
            "scroll-h-thumb-cap-left%s.png" % suffix: src.crop(H_LEFT_CAP),
            "scroll-h-thumb-mid%s.png" % suffix: src.crop((H_MID_COL, 0, H_MID_COL + 1, h)),
            "scroll-h-thumb-cap-right%s.png" % suffix: src.crop(H_RIGHT_CAP),
        }
        for name, im in caps.items():
            im.save(os.path.join(ASSETS, name))
            made.append((name, im.size))
    return made


# --- C：几何件 ---------------------------------------------------------------
ARROW_INK = (59, 65, 47, 255)      # #3B412F
HOVER_FACE = (247, 245, 238, 255)  # #F7F5EE
# 10 行，15 宽收到 1 宽；每行左右各内收 0 或 1px，整体关于 x=11 对称
TRI_WIDTHS = [15, 13, 11, 11, 9, 7, 5, 5, 3, 1]
TRI_TOP = 9
TRI_LEFT = 4


def luma(p):
    return 0.299 * p[0] + 0.587 * p[1] + 0.114 * p[2]


def clean_plate(im):
    """抹掉旧素材里烘焙的三角：面区内 luma<200 的像素用同行面色填平。"""
    px = im.load()
    w, h = im.size
    for y in range(7, 20):
        left = px[3, y]
        right = px[18, y]
        face = (
            (left[0] + right[0]) // 2,
            (left[1] + right[1]) // 2,
            (left[2] + right[2]) // 2,
            255,
        )
        # 旧三角 + 它头顶那条 1px 高光带（y7）一起抹平，避免新三角上方留亮条
        for x in range(5, 18):
            px[x, y] = face
    return im


def draw_triangle(im):
    px = im.load()
    for i, width in enumerate(TRI_WIDTHS):
        y = TRI_TOP + i
        left = TRI_LEFT + (15 - width) // 2
        for x in range(left, left + width):
            px[x, y] = ARROW_INK
    return im


def make_arrow_pair():
    base = Image.open(os.path.join(ASSETS, "scroll-v-arrow-down.png")).convert("RGBA")
    assert base.size == (22, 27), "下箭头底板尺寸变动: %s" % (base.size,)
    base = clean_plate(base)

    normal = draw_triangle(base.copy())
    normal.save(os.path.join(ASSETS, "scroll-v-arrow-down-normal.png"))

    # hover：几何与常态逐像素相同，只把面改成 #F7F5EE、上/左高光提亮
    hover_src = base.copy()
    hpx = hover_src.load()
    for y in range(3, 23):
        for x in range(3, 18):
            if luma(hpx[x, y]) >= 195:
                hpx[x, y] = HOVER_FACE
    for y in (1, 2):
        for x in range(1, 20):
            r, g, b, a = hpx[x, y]
            hpx[x, y] = (min(255, r + 12), min(255, g + 12), min(255, b + 12), a)
    for x in (1, 2):
        for y in range(1, 23):
            r, g, b, a = hpx[x, y]
            hpx[x, y] = (min(255, r + 10), min(255, g + 10), min(255, b + 10), a)
    hover = draw_triangle(hover_src)
    hover.save(os.path.join(ASSETS, "scroll-v-arrow-down-hover.png"))
    return normal, hover


def make_separators():
    sep = Image.new("RGBA", (64, 2))
    sp = sep.load()
    for x in range(64):
        sp[x, 0] = (172, 168, 153, 255)  # #ACA899
        sp[x, 1] = (255, 255, 255, 255)
    sep.save(os.path.join(ASSETS, "sep-horizontal.png"))

    sepv = Image.new("RGBA", (2, 22))
    vp = sepv.load()
    for y in range(22):
        vp[0, y] = (172, 168, 153, 255)
        vp[1, y] = (255, 255, 255, 255)
    sepv.save(os.path.join(ASSETS, "sep-vertical.png"))
    return sep, sepv


def check_arrow(im):
    px = im.load()
    xs, ys = [], []
    for y in range(im.size[1]):
        for x in range(im.size[0]):
            if px[x, y] == ARROW_INK:
                xs.append(x)
                ys.append(y)
    return (min(xs), min(ys), max(xs), max(ys), max(xs) - min(xs) + 1, max(ys) - min(ys) + 1)


def main():
    made = slice_thumbs()
    print("== A 切图 ==")
    for name, size in made:
        print("  %-38s %s" % (name, size))

    normal, hover = make_arrow_pair()
    print("== C 箭头 ==")
    for name, im in (("scroll-v-arrow-down-normal.png", normal),
                     ("scroll-v-arrow-down-hover.png", hover)):
        x0, y0, x1, y1, w, h = check_arrow(im)
        print("  %-34s %s  三角 bbox=(%d,%d)-(%d,%d) %dx%d 距顶=%d" %
              (name, im.size, x0, y0, x1, y1, w, h, y0))
        assert (w, h) == (15, 10) and y0 == 9 and x0 == 4, "三角几何不达标"

    sep, sepv = make_separators()
    print("== C 分隔线 ==")
    print("  sep-horizontal.png %s row0=%s row1=%s" % (sep.size, sep.getpixel((0, 0)), sep.getpixel((0, 1))))
    print("  sep-vertical.png   %s col0=%s col1=%s" % (sepv.size, sepv.getpixel((0, 0)), sepv.getpixel((1, 0))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
