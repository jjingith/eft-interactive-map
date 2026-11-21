# -*- coding: utf-8 -*-
"""构建期工具（R18.2 建立 / R19.4 升级为全项目统一透明图标管线）：
输出「透明底 + 原色物品」PNG。R19.4 起"白底"方案废止 —— 本目录产物**本来就是
透明底 PNG**（白底从来只由 CSS 容器提供），本轮更名为 icons-transparent 并把
候选集扩展到**本地全部物品图标**（含弹药页 / 逐发模拟引用的弹药），实现全项目统一。

要解决的问题
------------
`assets/icons-items/{id}.webp` 是 tarkov.dev 的 **64×64 带深色底**缩略图（背景固化在像素里，
外圈还有 1px 深色描边）。在 XP 浅色表格里它就是一块深色方块；给容器加 `background:#fff`
完全无效 —— 因为图片本身填满了容器，白底根本露不出来。

为什么不用「抠图」解决
----------------------
试过两条路，都不合格，记录在此避免重做：

  1. 反解前景色（matting）：`F = (C - bg·(1-a)) / a`
     → 深色物品（头盔暗部、黑枪、刀身）与深色背景只差 5–10 个灰阶，alpha 被低估，
       反解把暗部推向白色，物品变成"发光残缺"的轮廓。
  2. 只把「从边界可达且接近背景色」的区域涂白、前景区取原像素
     → 背景被吃掉一部分后，区域生长顺着低对比度断口漏进物品内部，
       物品被大片涂白，只剩碎片。

根本原因：**深色物品 + 深色背景**在这批 64px 素材里没有可靠的逐像素边界。
所以不再猜，改用上游本来就有的**透明底大图**。

做法
----
`https://assets.tarkov.dev/{id}-base-image.webp` 是透明底（RGBA）的原始渲染图，
尺寸 64×64 到 316×379 不等，Alpha 通道就是真实轮廓。抽样 20 件覆盖全部装备类别，
20/20 都有有效 Alpha。

  1. 构建期按需下载到 `build-cache/gear-icons-src/{id}.webp`（增量，已存在跳过；
     该目录已被 .gitignore 排除，不进仓库）；
  2. 用 Alpha 通道裁出主体包围盒，等比缩放到 56×56（画布 64×64，留 4px 边距）；
  3. 输出 **透明底 PNG** 到 `assets/icons-transparent/{id}.png` —— 保留原始颜色与抗锯齿，
     白底由 CSS 容器提供（`background:#fff`），选中行 / 悬停行都不会露出深色块；
  4. 写 manifest 记录每件的来源 URL、原始尺寸、alpha 覆盖率与结果，缺失项单独列出。

运行期零网络请求：前端只引用本地 PNG；PNG 缺失时前端自动回退到原 webp（不会破图）。

用法：
    python tools/build_gear_icons.py            # 增量构建（缺的才下载）
    python tools/build_gear_icons.py --verify   # 只校验已有产物，不联网
    python tools/build_gear_icons.py --debug    # 额外输出联系表
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ITEMS = os.path.join(ROOT, "data", "items.json")
OUT_DIR = os.path.join(ROOT, "assets", "icons-transparent")
SRC_DIR = os.path.join(ROOT, "build-cache", "gear-icons-src")
MANIFEST = os.path.join(OUT_DIR, "manifest.json")
DEBUG_DIR = os.path.join(OUT_DIR, "_debug")

BASE_URL = "https://assets.tarkov.dev/{id}-base-image.webp"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
PROXY = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or "http://127.0.0.1:7896"

CANVAS = 64          # 输出画布边长（与 assets/icons-items 的 64px 保持一致）
CONTENT = 56         # 主体最大边长（四周各留 4px）
ALPHA_CUT = 16       # alpha 低于此值视为全透明（去掉边缘极淡的雾状像素）

# 配装右侧列表可能出现的物品（与 app.js 的候选规则对齐，三种判定**都要**覆盖）：
#   · pt      —— 上游 propertiesType（护甲 / 头盔 / 胸挂 / 背包 / 耳机 / 近战 …）
#   · slot    —— 上游装备槽字段（部分配件用它挂到具体槽位）
#   · cat     —— 本项目构建期归类的槽位（**面部装备只靠这一条**：巴拉克拉瓦头套等
#                的 pt 与 slot 都是 null，此前只按 pt/slot 筛选因此漏了 124 件）
GEAR_PT = {"Armor", "Helmet", "ChestRig", "Backpack", "Glasses", "Headphone",
           "Headwear", "Visor", "ArmorPlate", "ArmorAttachment", "Weapon", "Melee"}
GEAR_CAT = {"face", "rig", "armor", "backpack", "glasses", "helmet", "plate", "headphones"}


def load_gear_ids():
    """R18.2：配装装备（pt/slot/cat 三种判定）。R19.2：加入**枪械 + 枪械改装配件**——
    配枪页的浏览卡片、装配卡、候选表、枪械摘要全都用这两类 id（data/gunslots.json 的
    枪械键 + 每个 slots[].allow 引用的配件），不覆盖它们就会在配枪页继续显示深色方块。"""
    data = json.load(open(ITEMS, encoding="utf-8"))
    items = data["items"]
    out = set()
    for iid, rec in items.items():
        if rec.get("pt") in GEAR_PT or rec.get("slot") or rec.get("cat") in GEAR_CAT:
            out.add(iid)
    slots_path = os.path.join(ROOT, "data", "gunslots.json")
    if os.path.exists(slots_path):
        guns = json.load(open(slots_path, encoding="utf-8")).get("guns") or {}
        out.update(guns.keys())                       # 枪械本体
        for g in guns.values():
            for slot in g.get("slots") or []:
                out.update(slot.get("allow") or [])   # 槽位合法配件（候选表全集）
    # R19.2 补漏：官方预设里引用的配件（如 Glock 准星/照门只出现在预设装配里，
    # 不在任何 slots[].allow 列表中——首版因此漏掉这类件）
    presets_path = os.path.join(ROOT, "data", "gun-presets.json")
    if os.path.exists(presets_path):
        presets = json.load(open(presets_path, encoding="utf-8")).get("presets") or {}
        for pr in presets.values():
            out.update((pr.get("i") or {}).values())
    # R19.4：补齐本地全部物品图标（弹药 / 逐发模拟 / 其他页面可能显示的每一件），
    # 以 assets/icons-items/ 的全集为基准 —— 保证 itemIconUrl 的每个调用点都有透明对应物。
    icons_dir = os.path.join(ROOT, "assets", "icons-items")
    if os.path.isdir(icons_dir):
        for fn in os.listdir(icons_dir):
            if fn.endswith(".webp"):
                out.add(fn[:-5])
    return items, sorted(out)


def fetch(item_id):
    dst = os.path.join(SRC_DIR, "%s.webp" % item_id)
    if os.path.exists(dst) and os.path.getsize(dst) > 0:
        return dst, "cached", None
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({"http": PROXY, "https": PROXY}))
    opener.addheaders = [("User-Agent", UA), ("Referer", "https://tarkov.dev/")]
    try:
        with opener.open(BASE_URL.format(id=item_id), timeout=30) as r:
            data = r.read()
        if not data:
            return None, "empty", None
        os.makedirs(SRC_DIR, exist_ok=True)
        tmp = dst + ".part"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, dst)
        return dst, "downloaded", None
    except Exception as exc:                      # noqa: BLE001 - 单件失败不阻断
        return None, "failed", str(exc)[:160]


def convert(src_path):
    """透明底源图 -> 64×64 透明底 PNG（等比、居中、不裁切主体）。"""
    im = Image.open(src_path).convert("RGBA")
    orig = im.size
    alpha = im.split()[3].point(lambda a: 0 if a < ALPHA_CUT else a)
    bbox = alpha.getbbox()
    if not bbox:
        return None, {"reason": "Alpha 全透明"}
    subject = im.crop(bbox)
    sw, sh = subject.size
    scale = min(CONTENT / float(sw), CONTENT / float(sh))
    nw, nh = max(1, int(round(sw * scale))), max(1, int(round(sh * scale)))
    small = subject.resize((nw, nh), Image.LANCZOS)

    canvas = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    canvas.paste(small, ((CANVAS - nw) // 2, (CANVAS - nh) // 2), small)
    opaque = sum(1 for _, _, _, a in canvas.getdata() if a > 200)
    return canvas, {
        "origSize": [orig[0], orig[1]],
        "bbox": list(bbox),
        "scale": round(scale, 4),
        "opaqueRatio": round(opaque / float(CANVAS * CANVAS), 4),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true", help="只校验已有产物，不下载")
    ap.add_argument("--debug", action="store_true", help="输出联系表")
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()

    items, ids = load_gear_ids()
    print("配装候选物品：%d 件" % len(ids))
    os.makedirs(OUT_DIR, exist_ok=True)

    old = {}
    if os.path.exists(MANIFEST):
        try:
            prev = json.load(open(MANIFEST, encoding="utf-8"))
            old = {i["itemId"]: i for i in prev.get("items", [])}
        except Exception:
            old = {}

    rows, missing = [], []
    if a.verify:
        for iid in ids:
            dst = os.path.join(OUT_DIR, "%s.png" % iid)
            if not os.path.exists(dst):
                missing.append({"itemId": iid, "name": items[iid].get("n"), "reason": "产物缺失"})
        print("校验：缺失 %d / %d" % (len(missing), len(ids)))
    else:
        todo = [i for i in ids if not os.path.exists(os.path.join(SRC_DIR, "%s.webp" % i))]
        if todo:
            print("需下载 %d 张透明底源图（走代理 %s）…" % (len(todo), PROXY))
        done = 0
        with ThreadPoolExecutor(max_workers=a.workers) as pool:
            for iid, (path, how, err) in zip(ids, pool.map(fetch, ids)):
                done += 1
                if done % 100 == 0:
                    print("  下载进度 %d / %d" % (done, len(ids)))
                if path is None:
                    missing.append({"itemId": iid, "name": items[iid].get("n"),
                                    "reason": "下载失败：%s" % (err or how)})

        for iid in ids:
            if any(m["itemId"] == iid for m in missing):
                continue
            src = os.path.join(SRC_DIR, "%s.webp" % iid)
            try:
                img, meta = convert(src)
            except Exception as exc:              # noqa: BLE001
                missing.append({"itemId": iid, "name": items[iid].get("n"),
                                "reason": "转换失败：%s" % str(exc)[:120]})
                continue
            if img is None:
                missing.append({"itemId": iid, "name": items[iid].get("n"),
                                "reason": meta.get("reason", "未知")})
                continue
            img.save(os.path.join(OUT_DIR, "%s.png" % iid), optimize=True)
            rows.append({
                "itemId": iid, "name": items[iid].get("n"), "pt": items[iid].get("pt"),
                "file": "assets/icons-transparent/%s.png" % iid,
                "sourceOrigin": BASE_URL.format(id=iid),
                "canvas": CANVAS,
                **meta,
            })

    if not a.verify:
        manifest = {
            "schema": 1, "round": "R19.4",
            "note": ("配装工作台装备图标：上游透明底 base-image 的 Alpha 轮廓 -> 64×64 透明底 PNG。"
                     "物品颜色/纹理保持原样，白底由 CSS 容器提供。运行期零网络请求。"
                     "原始 assets/icons-items/*.webp 只读未改。"),
            "generator": "tools/build_gear_icons.py",
            "render": {"canvas": CANVAS, "content": CONTENT,
                       "mode": "RGBA（透明底，白底由 CSS 提供）"},
            "counts": {"candidates": len(ids), "generated": len(rows), "missing": len(missing)},
            "items": rows, "missing": missing,
        }
        with open(MANIFEST, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=1)
        print("生成 %d 张，缺失 %d 项 -> %s" % (len(rows), len(missing), OUT_DIR))
        if missing[:6]:
            for m in missing[:6]:
                print("  [缺失] %s %s：%s" % (m["itemId"], m.get("name"), m["reason"]))

    if a.debug and rows:
        os.makedirs(DEBUG_DIR, exist_ok=True)
        cols, cell = 12, 72
        sample = rows[:96]
        r = (len(sample) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * cell, r * cell), (255, 255, 255))
        dr = ImageDraw.Draw(sheet)
        for i, rec in enumerate(sample):
            im = Image.open(os.path.join(ROOT, rec["file"])).convert("RGBA")
            bg = Image.new("RGB", (CANVAS, CANVAS), (255, 255, 255))
            bg.paste(im, (0, 0), im)
            sheet.paste(bg.resize((CANVAS - 8, CANVAS - 8), Image.NEAREST),
                        ((i % cols) * cell + 4, (i // cols) * cell + 4))
        p = os.path.join(DEBUG_DIR, "_contact_sheet.png")
        sheet.save(p)
        print("联系表：%s" % p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
