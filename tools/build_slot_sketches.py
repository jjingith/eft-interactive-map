# -*- coding: utf-8 -*-
"""构建期工具（R30.0）：生成配装工作台「空槽位」的**透明底石墨素描**占位图。

背景
----
R29.3 直接裁了游戏内空槽卡面（深色斜纹底 + 浅灰装备渲染）当占位图。图形是真的，
但**卡面底色也是真的深色** —— 工作台是 XP 风格（面板 #ECE9D8、卡片和表格行都是白色），
一张不透明的近黑卡片放进去就是一块黑色异物，用户反馈「你现在做的这个怎么是纯黑的」。

两条出路：
  A. 给左侧装备栏背面加灰色背景 —— 只是把异物扩大成一整块异物，仍然和右侧
     白色表格行、顶部统计条的浅色 XP 面冲突；
  B. 把占位图案做成透明底     —— 卡片底板交给 CSS 用 XP 凹陷边框 + 斜纹渐变绘制，
     空槽卡片与已装卡片（本来就是透明底物品图）统一成同一套视觉语言。
选 B。

为什么不「从卡面里减背景」
--------------------------
实测卡面背景是**低对比对角波纹**（灰度 16–48），装备渲染只比背景亮 10–30 级，
而且和波纹亮度区间重叠（背景峰值 48 ≈ 装备主体 30–50）。按相位建模的残差方差高达
24–93，二值化必然把波纹碎片误当成装备。所以改用**不经过卡面的干净信号源**：

    build-cache/gear-icons-src/{id}.webp

这是上游 assets.tarkov.dev 的 `-base-image.webp`（**透明底、原色、最高分辨率**），
也就是 R28.0 高清图标用的同一批源图（256px 画布 / 240px 内容）。两个好处：
  1. Alpha 就是真实轮廓，不需要「减背景」，没有误判；
  2. 卡片实际显示只有 47–106 px，源图 240–256 px 是**缩小采样**，边缘锐利 ——
     绕开了 R29.1 / R29.2「先放大插值导致发虚」的老问题。

做法（每件装备一次）
--------------------
  1. 按 Alpha 阈值裁出主体包围盒（丢掉边缘极淡的雾状像素）；
  2. 等比缩放进目标画布（四周留 MARGIN），居中 —— 与 64px 版同一套取景规则；
  3. 在白纸上合成后取灰度，过 S 曲线：暗部压深、亮部提亮，得到铅笔明暗；
  4. 叠**轮廓线**：Alpha 膨胀 − 腐蚀 = 边缘环带，单独加深 → 精细内描边；
  5. 主体只给很淡的填充（BODY_ALPHA），整体以线为主 —— 结构素描的观感；
  6. 输出 RGBA（背景全透明）到 assets/ui/placeholders/{key}.png，并写 manifest。

运行期零网络请求：前端只引用本地 PNG。本工具本身也**不联网**（源图来自已有缓存）。

用法：
    python tools/build_slot_sketches.py              # 生成 / 增量更新
    python tools/build_slot_sketches.py --force      # 忽略已有产物，全部重算
    python tools/build_slot_sketches.py --sheet      # 额外输出联系表（人眼核对）
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from PIL import Image, ImageChops, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "assets", "ui", "placeholders")
CACHE_DIR = os.path.join(ROOT, "build-cache", "gear-icons-src")
HD_DIR = os.path.join(ROOT, "assets", "icons-hd")
TP_DIR = os.path.join(ROOT, "assets", "icons-transparent")
DEBUG_DIR = os.path.join(OUT_DIR, "_debug")
MANIFEST = os.path.join(OUT_DIR, "manifest.json")

# ------------------------------------------------------------------ 渲染参数
OUT_SCALE = 2            # 输出画布 = 卡片尺寸 × 2（HiDPI 2× 屏够用）
SS = 2                   # 工作超采样：内部按 输出×SS 作画再缩回，得到抗锯齿
# 主体相对画布边的最小留白比例。64px 版是 0.06，这里放大到 0.09：
# 第 4 步的轮廓环带是「膨胀 − 腐蚀」，膨胀会把墨迹往外推 EDGE_R 个工作像素
# （= 1 个输出像素），再加上 LANCZOS 的振铃，主体外沿会有约 1px 的半透明羽化。
# 留白仍是 6% 的话，羽化正好压在「外圈 6% 必须全透明」的判定带上，契约被自己吃穿。
MARGIN = 0.09            # 主体相对画布边的最小留白比例（= 6% 判定带 + 描边余量）
ALPHA_CUT = 10           # Alpha 阈值：低于此值当背景（去掉上游图边缘的淡雾）
BODY_ALPHA = 1.0         # 主体按原 Alpha 全不透明（半透明会让图形在白卡片上发飘、看不清体块）
EDGE_R = 2               # 轮廓环带半径（**工作分辨率**下的像素）
EDGE_GAIN = 1.60         # 轮廓环带增强
EDGE_DARK = 0.30         # 轮廓环带处把铅笔压深的比例（只做「内描边」提示，不做黑边）
INK_LO = 38              # 铅笔最深处（原图纯黑处）
INK_HI = 205             # 铅笔最浅处（原图纯白处）
S_CURVE = 0.45           # S 曲线强度：0 = 线性，越大明暗越分明

# key -> (槽位代表装备的物品 id, 装备名, 画布宽, 画布高[, 取图用的物品 id])
#
# 画布尺寸 = style.css 里对应卡片的实际内框（网格轨道 × 行高，扣掉 1px 边框）。
# 主武器 1 / 主武器 2 共用同一张 AK-74 剪影（同一件装备，不出两套图）。
#
# 第 5 列 =「取图用的物品 id」：枪械**本体**的 base-image 是裁掉枪托/握把的侧视图
# （EFT 里这两件是可拆的独立配件），所以改用**预设（Preset）**的 base-image ——
# 预设代表完整装配形态。第 1 列仍是槽位代表的真实装备，两者分开记进 manifest。
SLOTS = [
    ("helmet",     "5b40e1525acfc4771e1c6611", "HighCom Striker ULACH IIIA 头盔（黑色）", 77, 77),
    ("armor",      "68948a95d8f2b85fb705e2a6", "6B45 防弹衣（数码丛林迷彩）",           103, 103),
    ("rig",        "603648ff5a45383c122086ac", 'Azimut SS "Zhuk" 胸挂（黑）',            103, 103),
    ("backpack",   "59e763f286f7742ee57895da", "Pilgrim 旅行包",                          103, 103),
    ("headphones", "66b5f6985891c84aab75ca76", "Peltor ComTac VI 耳机（狼棕色）",          77, 77),
    ("glasses",    "603409c80ca681766b6a0fb2", "NPP KIASS Condor 护目镜",                  77, 34),
    ("face",       "572b7f1624597762ae139822", "巴拉克拉瓦头套",                          39, 39),
    ("armband",    "5b3f16c486f7747c327f55f7", "臂带（白）",                              36, 35),
    ("dogtag",     "59f32bb586f774757e1e8442", "BEAR 狗牌",                                35, 35),
    ("primary",    "5bf3e03b0db834001d2c4a9c", "AK-74 5.45x39 突击步枪",                266, 103,
                   "5c0c1ce886f77401c119d014"),
    ("holster",    "5a7ae0c351dfba0017554310", "Glock 17 9x19 手枪",                     103, 56,
                   "5a88acfb86f77457fd2c0d8f"),
    ("melee",      "54491bb74bdc2d09088b4567", "ER「支点」刺刀",                          103, 56),
]

# 主武器 1 / 主武器 2 共用 primary 一张图
FILE_OF = {
    "helmet": "helmet", "armor": "armor", "rig": "rig", "backpack": "backpack",
    "headphones": "headphones", "glasses": "glasses", "face": "face",
    "armband": "armband", "dogtag": "dogtag",
    "primary1": "primary", "primary2": "primary", "holster": "holster", "melee": "melee",
}


def find_source(item_id):
    """按「分辨率从高到低」找该装备的透明底源图；找不到返回 None。"""
    for d, ext in ((CACHE_DIR, ".webp"), (HD_DIR, ".webp"), (TP_DIR, ".png")):
        p = os.path.join(d, "%s%s" % (item_id, ext))
        if os.path.isfile(p) and os.path.getsize(p) > 0:
            return p
    return None


def build(src_path, tw, th):
    """把一件装备的透明底原图渲染成「透明底石墨素描」。"""
    im = Image.open(src_path).convert("RGBA")

    # 1) 按 Alpha 裁出主体包围盒
    a0 = im.getchannel("A").point(lambda v: 255 if v >= ALPHA_CUT else 0)
    bb = a0.getbbox()
    if bb:
        im = im.crop(bb)

    # 2) 工作分辨率 = 输出 × SS；等比缩放后居中贴进画布
    #    注意**不能用 Image.thumbnail()** —— 它只缩不放，上游原图只有 127~316 px
    #    时会被原样留下，图形只占画布 20~30%，看上去就是一小坨。这里手动算等比
    #    缩放比例，允许放大到房间尺寸（放大只是填满卡片，不会比 64px 版更糊）。
    W, H = tw * OUT_SCALE * SS, th * OUT_SCALE * SS
    room = (int(W * (1 - 2 * MARGIN)), int(H * (1 - 2 * MARGIN)))
    iw, ih = im.size
    scale = min(room[0] / float(iw), room[1] / float(ih))
    im = im.resize((max(1, int(round(iw * scale))), max(1, int(round(ih * scale)))),
              Image.LANCZOS)
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    canvas.paste(im, ((W - im.width) // 2, (H - im.height) // 2), im)

    alpha = canvas.getchannel("A")

    # 3) 在白纸上合成取灰度 —— 透明区域当白纸，避免 RGB 里的 0 被当成黑
    flat = Image.alpha_composite(
        Image.new("RGBA", canvas.size, (255, 255, 255, 255)), canvas).convert("L")

    # 4) S 曲线：以中灰为轴，拉大明暗差（铅笔稿的「精神」来自对比，不是绝对值）
    lut = []
    for v in range(256):
        t = v / 255.0
        s = t + S_CURVE * (t - 0.5) * (1 - abs(2 * t - 1)) * 2.0
        s = 0.0 if s < 0 else (1.0 if s > 1 else s)
        lut.append(int(round((1.0 - s) * (INK_HI - INK_LO) + INK_LO)))
    gray = flat.point(lut)

    # 5) 轮廓环带：膨胀 − 腐蚀（只取形状边缘那一圈），单独加深 → 精细内描边
    dil = alpha.filter(ImageFilter.MaxFilter(EDGE_R * 2 + 1))
    ero = alpha.filter(ImageFilter.MinFilter(EDGE_R * 2 + 1))
    edge = ImageChops.subtract(dil, ero)
    e_gain = [min(255, int(v * EDGE_GAIN)) for v in range(256)]
    edge = edge.point(e_gain)
    # 环带上把铅笔压深（乘性），主体其余部分只留淡填充
    body = alpha.point(lambda v: int(v * BODY_ALPHA))
    out_a = ImageChops.add(body, edge)          # 加法即“边缘更实”，上限 255

    # 轮廓处再压深一档：按 edge 强度在 gray 上做线性压暗
    gray_dark = ImageChops.subtract(gray, edge.point(lambda v: int(v * EDGE_DARK)))

    out = Image.merge("RGBA", (gray_dark, gray_dark, gray_dark, out_a))
    return out.resize((tw * OUT_SCALE, th * OUT_SCALE), Image.LANCZOS)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="忽略已有产物，全部重算")
    ap.add_argument("--sheet", action="store_true", help="额外输出联系表")
    a = ap.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    old = {}
    if os.path.isfile(MANIFEST):
        try:
            old = json.load(open(MANIFEST, encoding="utf-8"))
        except Exception:          # noqa: BLE001 - 旧 manifest 损坏不影响重建
            old = {}
    rows, missing, seen = [], [], {}
    for key, item_id, label, tw, th, *rest in SLOTS:
        src_id = rest[0] if rest else item_id
        src = find_source(src_id)
        if not src:
            src = find_source(item_id)
            src_id = item_id
        if not src:
            missing.append({"key": key, "itemId": item_id, "label": label})
            print("  × %-11s %s（无透明底源图）" % (key, label))
            continue
        out_path = os.path.join(OUT_DIR, "%s.png" % key)
        im = build(src, tw, th)
        im.save(out_path, optimize=True)
        seen[key] = True
        rows.append({
            "key": key,
            "file": ("assets/ui/placeholders/%s.png" % key).replace("\\", "/"),
            "card": [tw, th],
            "canvas": [im.width, im.height],
            "itemId": item_id,
            "sourceId": src_id,
            "label": label,
            "bytes": os.path.getsize(out_path),
        })
        print("  √ %-11s %-34s %dx%d  %.0f KB" %
              (key, label, im.width, im.height, os.path.getsize(out_path) / 1024.0))

    payload = {
        "schema": 1,
        "round": "R30.0",
        "note": ("空槽占位图案：由「该槽位代表装备」的上游 -base-image.webp（透明底、最高分辨率）"
                 "渲染的石墨素描。**背景全透明**，卡片底板交给 CSS 的 XP 凹陷边框 + 斜纹渐变绘制，"
                 "因此不会在 XP 浅色面板上出现黑色方块。源图来自 build-cache/gear-icons-src，"
                 "本工具运行期不联网。"),
        "generator": "tools/build_slot_sketches.py",
        "render": {
            "outScale": OUT_SCALE, "supersample": SS, "margin": MARGIN,
            "alphaCut": ALPHA_CUT, "bodyAlpha": BODY_ALPHA,
            "edgeRadius": EDGE_R, "edgeGain": EDGE_GAIN,
            "inkRange": [INK_LO, INK_HI], "sCurve": S_CURVE,
        },
        "source": {"dir": "build-cache/gear-icons-src", "kind": "上游 -base-image.webp（透明底）"},
        "extract": {
            r["key"]: {"itemId": r["itemId"], "sourceId": r["sourceId"]}
            for r in rows
        },
        "items": rows,
        "missing": missing,
    }
    with open(MANIFEST, "w", encoding="utf-8", newline="\n") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
        f.write("\n")

    print("输出 %d 张，合计 %.1f KB；缺失 %d" %
          (len(rows), sum(r["bytes"] for r in rows) / 1024.0, len(missing)))

    if a.sheet:
        os.makedirs(DEBUG_DIR, exist_ok=True)
        cols, cell = 5, 240
        sheet = Image.new("RGBA", (cols * cell, 2 * cell), (236, 233, 216, 255))
        for i, r in enumerate(rows):
            im = Image.open(os.path.join(ROOT, r["file"]))
            im.thumbnail((cell - 16, cell - 16), Image.LANCZOS)
            cx = (i % cols) * cell + (cell - im.width) // 2
            cy = (i // cols) * cell + (cell - im.height) // 2
            sheet.paste(im, (cx, cy), im)
        p = os.path.join(DEBUG_DIR, "sketch-sheet.png")
        sheet.save(p)
        print("联系表：%s" % p)

    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
