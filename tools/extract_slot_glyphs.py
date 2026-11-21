# -*- coding: utf-8 -*-
"""构建期工具：从用户指定的布局参考图里抠出装备剪影，供配装工作台左侧槽位卡片直接复用。

背景：用户指定的设计基准是 `02-塔科夫/ui图标/配装参考布局.png`。该图里的装备剪影是
用户认可的正式视觉素材，但不是一个可直接放进网页的独立图片。本工具把它按槽位切成
9 张透明底 PNG（统一剪影灰），产物落在 `assets/slot-glyphs/`，前端用
`<img class="lw-sil">` 直接引用。

做法：
  1. 按实测的卡片内框裁剪（见 RECTS，坐标实测自参考图，已按扫描线核对过四条边框；
     裁剪框取边框线内侧，因此天然不含卡片边框）；
  2. 取裁剪框内出现次数最多的亮度作为「该卡底色」（参考图里是 39，躯干装饰则为页面底 23）；
  3. 掩膜 = 比底色亮 >=14 的像素（剪影灰 94、压在剪影上的白字 255）或比底色暗 >=12 的
     像素（少数卡片里的深色剪影/深色字）。这样亮剪影与深剪影都能抠出来；
  4. 把「不与裁剪框边界连通的非掩膜连通域」补进掩膜 —— 把白字抠掉后留下的洞补回实心，
     得到参考图里那种实心剪影；
  5. 按最终掩膜求紧包围盒，输出透明底 + 纯剪影灰的 PNG。

实测（参考图 504×448，整幅即左侧工作区；边框线坐标，含边框 1px 亮线）：
    helmet     x214..293 y 54..133      armor      x200..307 y152..259
    glasses    x 46..110 y152..184      rig        x367..474 y152..259
    face       x130..162 y152..184      gun        x 46..308 y285..393
    headphones x 46..110 y195..259      backpack   x367..474 y285..393
    torso(无边框装饰) x128..163 y197..241

依赖 Pillow（只在本机构建期跑，运行期不联网、不依赖任何第三方库）。
"""
import os
import sys
from collections import deque

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REF_IMG = os.path.join(os.path.dirname(ROOT), "ui图标", "配装参考布局.png")
OUT_DIR = os.path.join(ROOT, "assets", "slot-glyphs")

FILL = (0x5e, 0x5e, 0x5e)
SOL_LO, SOL_HI = 60, 150   # 有边框卡片：卡片底 39 / 边框 45~109 / 剪影 94 / 白字 >=200
FLAT_LO = 30               # 无边框装饰剪影：页面底 23 / 图形 40

# key -> 裁剪框 (x0, y0, x1, y1)，开区间；card=有边框卡片，flat=无边框装饰
RECTS = {
    "helmet":     ((215,  55, 293, 133), "card"),
    "glasses":    (( 47, 153, 110, 183), "card"),
    "face":       ((131, 153, 162, 182), "card"),
    "headphones": (( 47, 196, 110, 259), "card"),
    "torso":      ((128, 197, 164, 242), "flat"),
    "armor":      ((201, 153, 307, 259), "card"),
    "rig":        ((368, 153, 474, 259), "card"),
    "gun":        (( 48, 287, 308, 393), "card"),
    "backpack":   ((368, 287, 474, 393), "card"),
}

# 参考图里没有「近战武器」卡片（本轮按用户决策新增该槽位），故这一张不来自参考图：
# 直接取本地已有的近战物品图标（A-2607 大马士革钢匕首），按同一套剪影灰 flatten 成
# 同风格的透明底剪影 —— 复用本地资产，不另画一套风格不同的新图标。
MELEE_ICON = os.path.join(ROOT, "assets", "icons-items", "57e26ea924597715ca604a09.webp")
MELEE_CANVAS = (145, 108)   # 近战卡片内框比例（本轮新增槽位，宽按参考图枪械行左段给）


def lum_at(px, x, y):
    r, g, b = px[x, y]
    return (r * 299 + g * 587 + b * 114) // 1000


def components(mask, w, h, want):
    """把 mask 里值为 want 的像素按 4 邻域分连通域，返回 [(像素表, 是否贴边), ...]。"""
    seen = [[False] * w for _ in range(h)]
    out = []
    for sy in range(h):
        for sx in range(w):
            if mask[sy][sx] != want or seen[sy][sx]:
                continue
            comp, touches = [], False
            q = deque([(sx, sy)])
            seen[sy][sx] = True
            while q:
                x, y = q.popleft()
                comp.append((x, y))
                if x == 0 or y == 0 or x == w - 1 or y == h - 1:
                    touches = True
                for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                    if 0 <= nx < w and 0 <= ny < h and mask[ny][nx] == want and not seen[ny][nx]:
                        seen[ny][nx] = True
                        q.append((nx, ny))
            out.append((comp, touches))
    return out


def build_mask(crop, kind):
    """裁剪块 -> (布尔掩膜, 底色, 直方图)。"""
    w, h = crop.size
    px = crop.load()
    hist = {}
    for y in range(h):
        for x in range(w):
            v = lum_at(px, x, y)
            hist[v] = hist.get(v, 0) + 1

    # 1) 原始掩膜：剪影主体（参考图剪影灰 94）+ 略宽的窗口；白字（>=200）不算墨迹，
    #    它压出的缺口靠后面的补洞步骤还原，溢出到剪影外面的笔画自然被丢弃。
    mask = [[False] * w for _ in range(h)]
    lo = FLAT_LO if kind == "flat" else SOL_LO
    for y in range(h):
        for x in range(w):
            v = lum_at(px, x, y)
            if lo <= v <= SOL_HI:
                mask[y][x] = True

    # 2) 丢掉碎渣：只保留面积 >= 最大连通域 15% 的连通域（眼镜左右镜片、背包肩带等
    #    都远大于这个比例，白字抗锯齿拉出的细线、孤立噪点会被清掉）
    comps = components(mask, w, h, True)
    if comps:
        biggest = max(len(c[0]) for c in comps)
        keep = set()
        for comp, _ in comps:
            if len(comp) >= max(30, 0.15 * biggest):
                keep.update(comp)
        mask = [[False] * w for _ in range(h)]
        for x, y in keep:
            mask[y][x] = True

    # 3) 补洞：不与裁剪框边界连通的非掩膜区 = 压在剪影里的白字，补回实心
    for comp, touches in components(mask, w, h, False):
        if not touches:
            for x, y in comp:
                mask[y][x] = True

    base = max(hist.items(), key=lambda kv: kv[1])[0]
    return mask, base, hist


def build_melee():
    """近战剪影：本地近战物品图标 -> 同款剪影灰透明底 PNG（参考图里没有近战卡片）。"""
    if not os.path.exists(MELEE_ICON):
        print("找不到近战图标：%s" % MELEE_ICON)
        return None
    src = Image.open(MELEE_ICON).convert("RGBA")
    alpha = src.split()[3].point(lambda a: 255 if a > 60 else 0)
    bbox = alpha.getbbox()
    if not bbox:
        print("近战图标 alpha 全透明")
        return None
    crop = src.crop(bbox)
    cw, ch = crop.size
    CW, CH = MELEE_CANVAS
    scale = min(CW * 0.92 / cw, CH * 0.86 / ch)
    nw, nh = max(1, int(cw * scale)), max(1, int(ch * scale))
    small = crop.resize((nw, nh), Image.LANCZOS)
    out = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
    op = out.load()
    sp = small.load()
    ox, oy = (CW - nw) // 2, (CH - nh) // 2
    ink = 0
    for y in range(nh):
        for x in range(nw):
            if sp[x, y][3] > 60:
                op[ox + x, oy + y] = (FILL[0], FILL[1], FILL[2], 255)
                ink += 1
    out.save(os.path.join(OUT_DIR, "melee.png"))
    print("[%-10s] %s -> 画布 %dx%d 墨迹%d" % ("melee", "本地图标", CW, CH, ink))
    return out


def main():
    debug = "--debug" in sys.argv
    if not os.path.exists(REF_IMG):
        print("找不到参考图：%s" % REF_IMG)
        return 1
    ref = Image.open(REF_IMG).convert("RGB")
    print("参考图 %dx%d" % ref.size)
    os.makedirs(OUT_DIR, exist_ok=True)
    dbg_dir = os.path.join(OUT_DIR, "_debug")
    if debug:
        os.makedirs(dbg_dir, exist_ok=True)

    results = {}
    for key, (box, kind) in RECTS.items():
        crop = ref.crop(box)
        mask, base, hist = build_mask(crop, kind)
        w, h = crop.size
        x0, y0, x1, y1 = w, h, -1, -1
        for y in range(h):
            for x in range(w):
                if mask[y][x]:
                    x0 = min(x0, x); x1 = max(x1, x); y0 = min(y0, y); y1 = max(y1, y)
        if x1 < 0:
            print("[%s] 掩膜为空" % key)
            continue
        # 输出按卡片内框整幅尺寸（不做紧裁剪）：这样剪影在卡片里的相对位置与参考图完全一致，
        # 前端把图片拉满卡片内框即可原样还原「剪影位置」。
        out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        op = out.load()
        src = crop.load()
        ink = 0
        for y in range(h):
            for x in range(w):
                if mask[y][x]:
                    if kind == "flat":
                        # 无边框装饰（躯干）不涂统一剪影灰：参考图/参考站实测这一块灰度是 40，
                        # 强行涂成卡片剪影灰 94 会比原图亮一倍多。保留原像素灰度即可原样还原。
                        v = lum_at(src, x, y)
                        op[x, y] = (v, v, v, 255)
                    else:
                        op[x, y] = (FILL[0], FILL[1], FILL[2], 255)
                    ink += 1
        out.save(os.path.join(OUT_DIR, "%s.png" % key))
        results[key] = out
        print("[%-10s] %s 裁剪 %s -> 画布 %dx%d 底色%d 墨迹%d；剪影紧包围盒 %d,%d..%d,%d"
              % (key, kind, box, w, h, base, ink, x0, y0, x1, y1))

    melee = build_melee()
    if melee is not None:
        results["melee"] = melee

    if debug and results:
        scale = 3
        cell = 360
        cols = 3
        rows = (len(results) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * cell, rows * cell), (0x17, 0x17, 0x17))
        dr = ImageDraw.Draw(sheet)
        for i, (k, im) in enumerate(results.items()):
            cx, cy = (i % cols) * cell, (i // cols) * cell
            big = im.resize((im.size[0] * scale, im.size[1] * scale), Image.NEAREST)
            sheet.paste(big, (cx + 8, cy + 26), big)
            dr.text((cx + 8, cy + 8), "%s %dx%d" % (k, im.size[0], im.size[1]), fill=(235, 235, 235))
        sheet.save(os.path.join(dbg_dir, "_contact_sheet.png"))
        print("联系表：%s" % os.path.join(dbg_dir, "_contact_sheet.png"))
    print("共输出 %d 张到 %s" % (len(results), OUT_DIR))
    return 0


if __name__ == "__main__":
    sys.exit(main())
