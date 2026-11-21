# -*- coding: utf-8 -*-
"""构建期工具（R28.0）：为配装工作台左侧「装备槽卡片」生成**高清透明底图标**。

要解决的问题
------------
`assets/icons-transparent/{id}.png` 是 64×64 画布、内容只有 56px。左栏卡片实际显示
65–106 px（HiDPI 屏还要 ×2），浏览器把 56px 内容放大到 106px → 边缘发虚、细节糊成一片，
用户反馈「装备的图怎么都这么糊」。

为什么用 `-base-image.webp`
--------------------------
上游有四种尺寸：
  `-icon.webp` / `-grid-image.webp` / `-base-image.webp`   —— 透明底（Alpha 就是真实轮廓），
      但 `base-image` 通常给到 127–316 px；
  `-image.webp` 512×350 —— **RGB、纯黑底**（实测角落像素 (0,0,0)），
      深色装备与黑底只差几个灰阶，抠图必然失败（见 build_gear_icons.py 开头记录的两条失败路径）。
所以高清源只能用 `-base-image.webp`：它是**同一套渲染的透明底版本**，只是尺寸小一档。
253→240 只需轻微缩放，接着浏览器把 240 缩到 106 显示 = 缩小采样，边缘自然锐利。

做法
----
  1. 直接读 `build-cache/gear-icons-src/{id}.webp`（build_gear_icons.py 早已下好的透明底
     原图，60 MB / 5355 张），**本工具不联网**；缓存缺失时才回退下载（--fetch）。
  2. Alpha 通道裁出主体包围盒（阈值 ALPHA_CUT 去掉边缘极淡雾状像素）。
  3. 等比缩放主体到 CONTENT×CONTENT 以内，居中贴进 CANVAS×CANVAS 透明画布
     —— 与 64px 版**同一套取景规则**（主体居中、四周留边），换图不会跳动。
  4. 输出 WebP（保留 Alpha）到 `assets/icons-hd/{id}.webp`，并写 manifest。
  5. 只处理「实际会按大尺寸显示」的集合（配装根槽位装备 + 插板 + 枪械），
     其余物品仍走 64px PNG，避免无意义地翻倍体积。

运行期零网络请求：前端只引用本地 `.webp`；缺失时自动回落 64px PNG，再退中性占位。

用法：
    python tools/build_gear_icons_hd.py              # 只用本地缓存生成（推荐）
    python tools/build_gear_icons_hd.py --fetch      # 缓存缺源图时允许联网补齐
    python tools/build_gear_icons_hd.py --verify     # 只校验产物，不写文件
    python tools/build_gear_icons_hd.py --debug      # 输出联系表与尺寸分布
"""
from __future__ import annotations

import argparse
import json
import os
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ITEMS = os.path.join(ROOT, "data", "items.json")
SRC_DIR = os.path.join(ROOT, "build-cache", "gear-icons-src")
OUT_DIR = os.path.join(ROOT, "assets", "icons-hd")
MANIFEST = os.path.join(OUT_DIR, "manifest.json")
DEBUG_DIR = os.path.join(OUT_DIR, "_debug")

BASE_URL = "https://assets.tarkov.dev/{id}-base-image.webp"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
PROXY = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or "http://127.0.0.1:7896"

CANVAS = 256        # 输出画布边长（显示最大 106px，2× 屏 212px，256 足够）
CONTENT = 240       # 主体最大边长（四周各留 8px，与 64px 版 56/64 的比例一致）
ALPHA_CUT = 16      # alpha 低于此值视为全透明
QUALITY = 90        # WebP 质量：保留抗锯齿边缘，体积可控
METHOD = 4          # WebP 编码方法（6 更慢但收益很小，批量生成取 4）

# 会按「大尺寸」显示的集合：
#   · 配装根槽位装备（头盔/护甲/胸挂/背包/耳机/眼镜/护面）—— 卡片 65–106px
#   · 插板（pt=ArmorAttachment）—— 插板格剪影 52px，放大后也不该发虚
#   · 枪械本体（cat=primary/holster）—— 主武器卡 106×106
BOARD_SLOTS = {"helmet", "glasses", "face", "headphones", "armor", "rig", "backpack"}
BOARD_CATS = {"primary", "holster", "melee"}
# 枪械 / 近战在上游的 `cat` 一律为 null（只靠 pt 判别），只按 cat 筛会整类漏掉
BOARD_PT = {"ArmorAttachment", "ArmorPlate", "Weapon", "Melee"}


def load_targets():
    data = json.load(open(ITEMS, encoding="utf-8"))
    items = data["items"]
    out = []
    for iid, rec in items.items():
        if (rec.get("slot") in BOARD_SLOTS
                or rec.get("cat") in BOARD_CATS
                or rec.get("pt") in BOARD_PT):
            out.append(iid)
    return items, sorted(out)


def ensure_src(item_id, allow_fetch):
    dst = os.path.join(SRC_DIR, "%s.webp" % item_id)
    if os.path.exists(dst) and os.path.getsize(dst) > 0:
        return dst, "cached"
    if not allow_fetch:
        return None, "missing"
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({"http": PROXY, "https": PROXY}))
    opener.addheaders = [("User-Agent", UA), ("Referer", "https://tarkov.dev/")]
    try:
        with opener.open(BASE_URL.format(id=item_id), timeout=30) as r:
            raw = r.read()
        if not raw:
            return None, "empty"
        os.makedirs(SRC_DIR, exist_ok=True)
        tmp = dst + ".part"
        with open(tmp, "wb") as f:
            f.write(raw)
        os.replace(tmp, dst)
        return dst, "downloaded"
    except Exception as exc:                      # noqa: BLE001 - 单件失败不阻断
        return None, "failed: %s" % str(exc)[:120]


def alpha_bbox(im):
    """用 Alpha 通道求主体包围盒；全透明返回 None。"""
    a = im.getchannel("A")
    mask = a.point(lambda v: 255 if v > ALPHA_CUT else 0)
    return mask.getbbox()


def render(src_path):
    """透明底原图 → CANVAS 方形画布、主体等比填充。返回 (Image, 源尺寸)。"""
    im = Image.open(src_path)
    im.load()
    im = im.convert("RGBA")
    src_size = im.size
    box = alpha_bbox(im)
    if not box:
        return None, src_size
    body = im.crop(box)
    bw, bh = body.size
    scale = min(CONTENT / float(bw), CONTENT / float(bh))
    nw, nh = max(1, int(round(bw * scale))), max(1, int(round(bh * scale)))
    # 缩小用 LANCZOS（保细节），放大用 BICUBIC（避免 LANCZOS 放大产生的振铃）
    resample = Image.LANCZOS if scale < 1 else Image.BICUBIC
    body = body.resize((nw, nh), resample)
    canvas = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    canvas.paste(body, ((CANVAS - nw) // 2, (CANVAS - nh) // 2), body)
    return canvas, src_size


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true", help="缓存缺源图时允许联网补齐")
    ap.add_argument("--verify", action="store_true", help="只校验产物")
    ap.add_argument("--debug", action="store_true", help="输出联系表")
    ap.add_argument("--force", action="store_true", help="忽略已有产物，全部重算")
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()

    items, targets = load_targets()
    print("目标集合：%d 件（配装槽位 / 插板 / 枪械 / 近战）" % len(targets))
    os.makedirs(OUT_DIR, exist_ok=True)

    def one(iid):
        """单件：源图 -> 256 画布 -> WebP。返回 (row|None, missing|None, upscaled)。"""
        rec = items.get(iid) or {}
        out_path = os.path.join(OUT_DIR, "%s.webp" % iid)
        src, how = ensure_src(iid, a.fetch)
        if src is None:
            return None, {"itemId": iid, "name": rec.get("n"), "reason": how}, 0
        canvas, src_size = render(src)
        if canvas is None:
            return None, {"itemId": iid, "name": rec.get("n"), "reason": "源图全透明"}, 0
        canvas.save(out_path, "WEBP", quality=QUALITY, method=METHOD)
        return ({"itemId": iid, "name": rec.get("n"),
                 "src": list(src_size), "out": [CANVAS, CANVAS],
                 "bytes": os.path.getsize(out_path)},
                None, 1 if max(src_size) < CONTENT else 0)

    rows, missing, upscaled = [], [], 0
    if a.verify:
        for iid in targets:
            if not os.path.exists(os.path.join(OUT_DIR, "%s.webp" % iid)):
                missing.append({"itemId": iid, "name": (items.get(iid) or {}).get("n")})
    else:
        todo = [i for i in targets
                if a.force or not os.path.exists(os.path.join(OUT_DIR, "%s.webp" % i))]
        print("需生成 %d 张（已有 %d 张跳过）" % (len(todo), len(targets) - len(todo)))
        with ThreadPoolExecutor(max_workers=a.workers) as pool:
            for n, (row, miss, up) in enumerate(pool.map(one, todo), 1):
                if row:
                    rows.append(row)
                if miss:
                    missing.append(miss)
                upscaled += up
                if n % 50 == 0:
                    print("  进度 %d / %d" % (n, len(todo)))
        # 增量运行时把磁盘上已有的也算进清单，manifest 才是全量快照
        have = {r["itemId"] for r in rows}
        for iid in targets:
            if iid in have:
                continue
            p_out = os.path.join(OUT_DIR, "%s.webp" % iid)
            if os.path.exists(p_out):
                rows.append({"itemId": iid, "name": (items.get(iid) or {}).get("n"),
                             "src": None, "out": [CANVAS, CANVAS],
                             "bytes": os.path.getsize(p_out)})

    if a.verify:
        total = len(targets)
        print("校验：缺失 %d / %d" % (len(missing), total))
        return

    total_bytes = sum(r["bytes"] for r in rows)
    payload = {
        "schema": 1,
        "round": "R28.0",
        "note": ("配装左栏高清装备图：源为上游 -base-image.webp（透明底），"
                 "Alpha 裁边后等比填充 240/256，输出 WebP。运行期零网络请求；"
                 "前端缺失时回落 assets/icons-transparent 的 64px 版本。"),
        "generator": "tools/build_gear_icons_hd.py",
        "render": {"canvas": CANVAS, "content": CONTENT, "quality": QUALITY,
                   "alphaCut": ALPHA_CUT},
        "count": len(rows),
        "totalBytes": total_bytes,
        "upscaledFromSmallSource": upscaled,
        "items": rows,
        "missing": missing,
    }
    with open(MANIFEST, "w", encoding="utf-8", newline="\n") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print("输出 %d 张，合计 %.1f MB（平均 %.1f KB）；源图偏小需放大 %d 张；缺失 %d"
          % (len(rows), total_bytes / 1024.0 / 1024.0,
             total_bytes / 1024.0 / max(1, len(rows)), upscaled, len(missing)))

    if a.debug and rows:
        os.makedirs(DEBUG_DIR, exist_ok=True)
        cols, cell = 12, 128
        pick = rows[:120]
        sheet = Image.new("RGBA", (cols * cell, ((len(pick) + cols - 1) // cols) * cell),
                          (245, 245, 245, 255))
        for i, r in enumerate(pick):
            im = Image.open(os.path.join(OUT_DIR, "%s.webp" % r["itemId"])).resize((120, 120),
                                                                                  Image.LANCZOS)
            sheet.paste(im, ((i % cols) * cell + 4, (i // cols) * cell + 4), im)
        sheet_path = os.path.join(DEBUG_DIR, "contact-sheet.png")
        sheet.save(sheet_path)
        print("联系表：%s" % sheet_path)


if __name__ == "__main__":
    main()
