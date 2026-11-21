# -*- coding: utf-8 -*-
"""R18.2：配装图标透明底统一 / 完整枪械剪影。
（R19.4 修订：「白底」方案废止——本目录产物本来就是透明底 PNG，白底只是当年由
CSS 容器提供；本轮把容器白底一并移除，目录更名为 assets/icons-transparent/，
候选集扩展到本地全部物品图标。下列断言全部按透明方案等价强迁移。）

三层：
1. **产物审计**（Pillow 直读 PNG）：`assets/icons-transparent/*.png` 必须是透明底、
   主体保留原始颜色（不是被涂白/涂黑的方块）、尺寸统一 64×64。
2. **枪械剪影完整性**：`primary.png` / `holster.png` 的主体必须横向铺满画布两端，
   证明枪口与枪托都未被裁切；并从 manifest 校验素材改用「预设（完整装配）」而非本体裁切图。
   R19.4：剪影重建为 **透明底**（黑剪影 + Alpha），断言改用 Alpha 通道判定墨迹。
3. **接线审计**：app.js 的 `setGearIcon` / `gearIconUrl` 与三处 `tbl-icon` 调用、
   图标容器**不再绘制白底**（透出主题底色）。

不联网；数据全部来自仓库内文件。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
APP_JS = ROOT / "app.js"
STYLE_CSS = ROOT / "style.css"
ITEMS = ROOT / "data" / "items.json"
TRANS_DIR = ROOT / "assets" / "icons-transparent"
TRANS_MANIFEST = TRANS_DIR / "manifest.json"
PH_DIR = ROOT / "assets" / "ui" / "placeholders"
PH_MANIFEST = PH_DIR / "manifest.json"


def _white():
    """透明图标 manifest（历史函数名保留，避免调用点漂移）。"""
    return json.loads(TRANS_MANIFEST.read_text(encoding="utf-8"))


def _ph():
    return json.loads(PH_MANIFEST.read_text(encoding="utf-8"))


def _ink_mask(img):
    """剪影墨迹掩膜：透明底 PNG 按「非透明像素」取（兼容旧 RGB 按暗像素）。"""
    from PIL import Image
    if img.mode == "RGBA":
        a = img.split()[3]
        return a.point(lambda v: 255 if v > 128 else 0)
    return img.convert("L").point(lambda v: 255 if v < 128 else 0)


# ------------------------------------------------------- 1. 透明图标产物
def test_white_icon_manifest_is_complete():
    m = _white()
    assert re.match(r"R1[89]\.\d$", m["round"]) or m["round"] in ("R18.2", "R19.4"), m["round"]
    assert m["render"]["canvas"] == 64
    assert m["counts"]["candidates"] > 2700, "全量候选物品数量异常"
    gen = m["counts"]["generated"]
    assert gen > 2700, "生成数量过少：%d" % gen
    # 允许少量上游缺图（base-image 404 的新物品），但必须逐条记录原因
    assert m["counts"]["missing"] == len(m["missing"])
    for miss in m["missing"]:
        assert miss.get("reason"), "缺失项没有记录原因：%s" % miss
    # 每个生成项都要能对上真实文件与来源
    for rec in m["items"][:50]:
        assert (ROOT / rec["file"]).is_file(), rec["file"]
        assert rec["sourceOrigin"].startswith("https://assets.tarkov.dev/")
        assert rec["origSize"][0] > 0 and rec["origSize"][1] > 0


def test_white_icons_are_transparent_with_original_colour():
    """抽样：透明底 + 主体保留原色，不能是「整块深色方块」或「被涂白的残影」。"""
    from PIL import Image
    m = _white()
    items = m["items"]
    assert len(items) >= 700
    # 抽 24 件，覆盖头尾与中间
    step = max(1, len(items) // 24)
    sample = items[::step][:24]
    for rec in sample:
        im = Image.open(ROOT / rec["file"])
        assert im.mode == "RGBA", "%s 不是 RGBA（透明底）" % rec["itemId"]
        assert im.size == (64, 64), "%s 尺寸不是 64×64" % rec["itemId"]
        px = im.load()
        # 四角必须是全透明：证明背景真的被去掉了，而不是白底盖在上面
        for (cx, cy) in ((0, 0), (63, 0), (0, 63), (63, 63)):
            assert px[cx, cy][3] == 0, "%s 角落不透明（背景没去掉）" % rec["itemId"]
        opaque = 0
        colours = set()
        for y in range(64):
            for x in range(64):
                a = px[x, y][3]
                if a > 200:
                    opaque += 1
                    colours.add((px[x, y][0] // 32, px[x, y][1] // 32, px[x, y][2] // 32))
        ratio = opaque / 4096.0
        # 小件（贴纸 / 小配件）主体可能只占 2%，下限放到 1% 仍能挡住空白图
        assert 0.01 < ratio < 0.92, "%s 主体占比异常 %.1f%%" % (rec["itemId"], 100 * ratio)
        # 主体内部颜色要有层次（真实贴图），不能是单色方块
        assert len(colours) >= 3, "%s 主体颜色过少（%d 种），可能是涂色块" % (rec["itemId"], len(colours))
        # manifest 记录的不透明占比要与实测一致（防止清单与产物脱节）
        assert abs(rec["opaqueRatio"] - ratio) < 0.06, \
            "%s 清单记录 %.3f 与实测 %.3f 不符" % (rec["itemId"], rec["opaqueRatio"], ratio)


def test_white_icon_keeps_source_colour_not_painted():
    """把新 PNG 叠到白底上，与原始 64px 图标的主体颜色分布对比（应高度接近）。"""
    from PIL import Image
    m = _white()
    items_json = json.loads(ITEMS.read_text(encoding="utf-8"))["items"]
    # 挑几类典型：亮色（护甲）、暗色（枪）、彩色（背包）
    picked = []
    for rec in m["items"]:
        pt = items_json.get(rec["itemId"], {}).get("pt")
        if pt in ("Armor", "Weapon", "Backpack") and len([p for p in picked if p[1] == pt]) < 2:
            picked.append((rec, pt))
    assert len(picked) >= 5, "样本不足"
    for rec, pt in picked:
        new = Image.open(ROOT / rec["file"]).convert("RGBA")
        old = Image.open(ROOT / "assets" / "icons-items" / ("%s.webp" % rec["itemId"])).convert("RGB")
        # 取新图不透明像素的中位亮度，和旧图对应区域比较：不应整体被推白
        vals = []
        for y in range(64):
            for x in range(64):
                a = new.getpixel((x, y))[3]
                if a > 200:
                    r, g, b = new.getpixel((x, y))[:3]
                    vals.append((r + g + b) / 3.0)
        assert vals, "%s 没有不透明像素" % rec["itemId"]
        vals.sort()
        med_new = vals[len(vals) // 2]
        # 旧图整幅（含背景）中位亮度
        old_vals = sorted((sum(old.getpixel((x, y))) / 3.0) for y in range(64) for x in range(64))
        med_old = old_vals[len(old_vals) // 2]
        # 新图主体中位亮度不能明显高于旧图整体（否则说明被"漂白"了）
        assert med_new <= med_old + 60, \
            "%s（%s）主体亮度 %.0f 远高于原图中位 %.0f，疑似被涂白" % (rec["itemId"], pt, med_new, med_old)


# ------------------------------------------------------- 2. 枪械剪影完整性
def test_gun_silhouettes_span_whole_canvas():
    """完整枪械必须横跨画布两端：左端（枪口）与右端（枪托/套筒尾）都要有墨迹。

    R30.0 迁移：占位图从「满幅裁切」改回「等比缩放 + 四周留白」的线稿，
    主体不可能再占满画布 —— 取景规则是 `scale = min(room_w/iw, room_h/ih)`，
    即**受限的那一维**恰好撑到 `1 - 2×margin`，另一维会留出更多空白（取决于
    装备本身的宽高比）。所以「未被裁切」的判据改为：
      · 至少有一维撑到留白边界（说明是按比例完整装入，不是被裁掉一头）；
      · 两端 8% 窗口内都有墨迹（枪口 / 枪托都在画布里）。
    阈值从 manifest 的 `render.margin` 推导，改留白参数时断言自动跟随。
    """
    from PIL import Image
    margin = float(_ph()["render"]["margin"])
    full = 1.0 - 2 * margin          # 受限维度应达到的占比
    for key in ("primary", "holster"):
        im = Image.open(PH_DIR / ("%s.png" % key))
        w, h = im.size
        mask = _ink_mask(im)
        px = mask.load()
        cols = [x for x in range(w) if any(px[x, y] for y in range(h))]
        rows = [y for y in range(h) if any(px[x, y] for x in range(w))]
        assert cols and rows, "%s 没有墨迹" % key
        x0, x1 = cols[0], cols[-1]
        spanx = (x1 - x0 + 1) / float(w)
        spany = (rows[-1] - rows[0] + 1) / float(h)
        assert max(spanx, spany) >= full - 0.02, \
            "%s 横向只占 %.0f%%、纵向 %.0f%%，都够不到留白边界 %.0f%%，疑似被裁切" % (
                key, 100 * spanx, 100 * spany, 100 * full)
        # 两端各留 8% 的窗口里必须有墨迹 —— 枪口制退器 / 枪托尾端都在画布里
        edge = max(2, int(w * 0.08))
        left_ink = sum(1 for x in range(x0, min(x0 + edge, w)) for y in range(h) if px[x, y])
        right_ink = sum(1 for x in range(max(x1 - edge, 0), x1 + 1) for y in range(h) if px[x, y])
        assert left_ink > 0, "%s 左端（枪口侧）没有墨迹，可能被裁掉" % key
        assert right_ink > 0, "%s 右端（枪托侧）没有墨迹，可能被裁掉" % key


def test_gun_silhouette_uses_preset_source():
    """枪械占位图的溯源契约（R30.0）：素材必须可重建，且枪械走「预设（完整装配）」图。

    历史沿革：R18~R29.2 走「生成」路线，manifest 记 `assetItemId`（必须是预设装配图，
    否则缺枪托/握把）；R29.3 改为「裁自游戏内截图」，溯源字段换成
    `source.file` + `extract[key].box`；R30.0 因 XP 主题下深色卡面与白底表格冲突，
    改回**透明底石墨线稿**，素材取自上游 `-base-image.webp`（本身就带 Alpha 通道），
    溯源字段换成 `source.dir` + `extract[key].{itemId,sourceId}`。

    三轮的共同底线（本测真正守的不变量）：
      · **可重建** —— manifest 必须写明素材来源与取用 id，不能凭空生成；
      · **枪械必须用预设图** —— `sourceId != itemId`。枪械「本体」图是枪身裁切，
        没有枪托/握把/弹匣，用它做占位会缺部件（R18.2 最初踩过的坑）。
    """
    m = _ph()
    by = {i["key"]: i for i in m["items"]}
    ex = m.get("extract", {})
    src = m.get("source", {})
    assert src.get("dir"), "必须记录素材来源目录（可重建的前提）"
    assert "透明" in src.get("kind", ""), \
        "R30.0 起占位图走透明底素材，source.kind 应标注：%s" % src.get("kind")
    for key in ("primary", "holster"):
        assert key in ex, "%s 缺溯源记录（无法重建）" % key
        item_id = ex[key].get("itemId")
        source_id = ex[key].get("sourceId")
        assert item_id and source_id, "%s 溯源字段不全：%s" % (key, ex[key])
        # 枪械：sourceId 必须 ≠ itemId —— 用预设（完整装配）图，而不是缺部件的本体裁切图
        assert source_id != item_id, \
            "%s 用了本体图（%s）而非预设完整装配图，会缺枪托/握把/弹匣" % (key, item_id)
        # 两个 id 都要能在 items.json 里查到（不是编造的 id）
        items_json = json.loads(ITEMS.read_text(encoding="utf-8"))["items"]
        assert item_id in items_json, "%s 的 itemId 不在 items.json：%s" % (key, item_id)
        assert source_id in items_json, "%s 的 sourceId 不在 items.json：%s" % (key, source_id)
        rec = by[key]
        assert rec.get("canvas") and rec.get("card"), "%s 缺画布/卡片尺寸记录" % key
        assert rec.get("itemId") == item_id, "%s 清单与溯源 itemId 不一致" % key
        # 线稿是「原图 → 描边 + 灰度化」，不能有「填洞」这类破坏内部镂空的后处理
        assert "fillHoles" not in rec and "fill_holes" not in str(rec), \
            "%s 出现填洞后处理记录，内部镂空（扳机护圈等）会被填平" % key


def _inner_holes(ink, w, h):
    """统计「被主体包围的透明区域」像素数：从画布边界泛洪掉外部透明，剩下的就是内孔。
    R19.4：剪影为透明底，内孔判定改用「非墨迹（alpha 低）区域」。"""
    from collections import deque
    white = [[ink[y][x] == 0 for x in range(w)] for y in range(h)]
    ext = [[False] * w for _ in range(h)]
    q = deque()
    for x in range(w):
        for y in (0, h - 1):
            if white[y][x] and not ext[y][x]:
                ext[y][x] = True
                q.append((x, y))
    for y in range(h):
        for x in (0, w - 1):
            if white[y][x] and not ext[y][x]:
                ext[y][x] = True
                q.append((x, y))
    while q:
        x, y = q.popleft()
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= nx < w and 0 <= ny < h and white[ny][nx] and not ext[ny][nx]:
                ext[ny][nx] = True
                q.append((nx, ny))
    return sum(1 for y in range(h) for x in range(w) if white[y][x] and not ext[y][x])


def _enclosed_regions(mask, w, h):
    """返回「被主体完全包围的空白连通域」面积列表（画布边界泛洪掉外部）。"""
    from collections import deque
    white = [[not mask[y][x] for x in range(w)] for y in range(h)]
    ext = [[False] * w for _ in range(h)]
    seen = [[False] * w for _ in range(h)]
    q = deque()
    for x in range(w):
        for y in (0, h - 1):
            if white[y][x] and not ext[y][x]:
                ext[y][x] = True
                q.append((x, y))
    for y in range(h):
        for x in (0, w - 1):
            if white[y][x] and not ext[y][x]:
                ext[y][x] = True
                q.append((x, y))
    while q:
        x, y = q.popleft()
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= nx < w and 0 <= ny < h and white[ny][nx] and not ext[ny][nx]:
                ext[ny][nx] = True
                q.append((nx, ny))
    areas = []
    for sy in range(h):
        for sx in range(w):
            if white[sy][sx] and not ext[sy][sx] and not seen[sy][sx]:
                n = 0
                q2 = deque([(sx, sy)])
                seen[sy][sx] = True
                while q2:
                    x, y = q2.popleft()
                    n += 1
                    for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                        if 0 <= nx < w and 0 <= ny < h and white[ny][nx] and not seen[ny][nx]:
                            seen[ny][nx] = True
                            q2.append((nx, ny))
                areas.append(n)
    return areas


@pytest.mark.parametrize("key,min_hole", [("primary", 20), ("holster", 60)])
def test_trigger_guard_hole_preserved(key, min_hole):
    """枪械图案必须保留内部镂空结构（扳机护圈/挂环这类孔洞），不能是实心块。

    历史沿革：R18~R29.2 走生成路线，这条测的是 `fill_holes` 的契约——
    「只填小孔（<1.5% 主体），大镂空必须保留」。R29.3 改为**直接裁切游戏内卡面**，
    没有填洞后处理；R30.0 改为**透明底石墨线稿**（Alpha 承载墨迹）。
    不变的是同一条底线：**成品枪械图案必须保留内部镂空，不能是一块实心**。
    判据随载体迁移为「Alpha 墨迹内部存在被包围的透明连通域」。
    """
    from PIL import Image
    im = Image.open(PH_DIR / ("%s.png" % key))
    assert im.mode == "RGBA", "%s 线稿必须是透明底 RGBA，当前 %s" % (key, im.mode)
    w, h = im.size
    a = im.getchannel("A").load()
    mask = [[a[x, y] > 128 for x in range(w)] for y in range(h)]
    ink = sum(1 for y in range(h) for x in range(w) if mask[y][x])
    assert ink > 0, "%s 没有任何墨迹" % key
    # 墨迹要成规模（实测 primary 18.9% / holster 38.1%），过小说明渲染丢了
    assert ink / float(w * h) > 0.05, \
        "%s 墨迹仅占 %.1f%%，枪械线稿缺失" % (key, 100 * ink / float(w * h))
    # 内部镂空：从画布边界泛洪掉外部透明后，剩下的透明像素就是被主体包围的孔
    holes = _inner_holes(mask, w, h)
    assert holes >= min_hole, \
        "%s 内部镂空仅 %d 像素，像实心块（扳机护圈/握把间隙丢失）" % (key, holes)
    # 可重建：必须记录溯源 id（大镂空不被偷偷填平的前提）
    ex = _ph().get("extract", {})
    assert key in ex and ex[key].get("itemId") and ex[key].get("sourceId"), \
        "%s 缺溯源记录，无法证明未经破坏性后处理" % key


@pytest.mark.parametrize("key,min_span", [("primary", 0.18), ("holster", 0.30)])
def test_right_side_has_bulky_part(key, min_span):
    """画布右端 25% 必须有「有体积的部件」—— AK 的枪托、Glock 的握把。

    旧素材（枪械本体裁切图）右端只剩细枪管 / 套筒尾，这个占比会明显偏低。

    R28.0：占位图从「实心剪影」改为「灰色轮廓线稿」，**墨迹密度判据不再适用**
    （线稿内部是透明的，枪托只留一圈线，密度天然只有几个点）。改判「竖向展开幅度」：
    枪托/握把会在右端撑开一段明显的高度，而光秃的枪管只占中间很薄的一条。
    """
    from PIL import Image
    im = Image.open(PH_DIR / ("%s.png" % key))
    w, h = im.size
    mask = _ink_mask(im).load()
    x0 = int(w * 0.75)
    ys = [y for y in range(h) for x in range(x0, w) if mask[x, y]]
    assert ys, "%s 右端完全没有墨迹，疑似缺枪托/握把" % key
    span = (max(ys) - min(ys) + 1) / float(h)
    assert span >= min_span, \
        "%s 右端竖向只展开 %.0f%%，疑似缺枪托/握把" % (key, 100 * span)


# ------------------------------------------------------- 3. 接线审计
def test_frontend_uses_white_icons_only_in_loadout():
    js = APP_JS.read_text(encoding="utf-8")
    assert 'var GEAR_ICON_DIR = "assets/icons-transparent/";' in js
    assert "function gearIconUrl(" in js and "function setGearIcon(" in js
    # 三处配装列表图标都必须走 setGearIcon
    assert js.count("setGearIcon(img,") >= 3, "配装列表图标未全部切到透明版"
    # 两级回退：透明 PNG 缺失 -> 原 webp -> 原图也缺失则隐藏（不留浏览器破损占位）
    assert "this.onerror = function () { this.style.visibility = \"hidden\"; };" in js, \
        "缺二级回退：原 webp 也 404 时应隐藏 <img>"
    assert "this.src = itemIconUrl(id);" in js, "缺一级回退：应回到原 webp"
    # R19.4：弹药等页面的通用 itemIconUrl 也有了透明版 setItemImg（带同样回退）
    assert "function setItemImg(" in js
    assert '"assets/icons-transparent/"' in js


def test_css_gives_icon_area_pure_white_background():
    """R19.4 迁移：图标容器**不再绘制白底**（白底废止）——
    断言 .tbl-icon 块没有 background，且剪影不再使用 multiply 混合。"""
    css = STYLE_CSS.read_text(encoding="utf-8")
    block = css[css.index(".loadout-workbench .tbl-icon {"):]
    block = block[:block.index("}")]
    assert not re.search(r"background:\s*#fff", block), \
        "白底已废止：图标容器不得再绘制白底（%s）" % block.strip()
    theme = (ROOT / "theme-windows-xp.css").read_text(encoding="utf-8")
    assert "mix-blend-mode: normal;" in theme, "剪影 multiply 混合必须废止"


@pytest.mark.parametrize("key", ["primary", "holster"])
def test_gun_png_still_black_on_white(key):
    """R30.0 起枪械占位图是**透明底石墨线稿**（灰度墨迹 + Alpha）。

    历史沿革（断言随规格迁移，不删测试）：
      · R18.2：白底纯黑剪影 —— 判「四角纯白 + 主体纯黑」；
      · R19.4：透明底剪影 —— 判「四角全透明 + 主体黑」；
      · R28.0：灰色轮廓线稿 —— 判「墨迹非纯黑」；
      · R29.3：游戏内实拍卡面 —— 判「alpha 最小值 ≥ 250（不透明）+ 整体偏暗」；
      · R30.0：XP 主题下深色卡面与白底表格/白色行冲突（用户反馈「纯黑」），
        改回透明底石墨线稿。判据迁移为：
          · **透明底** —— alpha 最小值必须为 0（背景真的被去掉，不是白/黑方块）；
          · **墨迹不过曝** —— alpha 最大值 ≥ 250（主体是实打实的笔画）；
          · **石墨灰阶** —— 可见像素必须是灰度（|r−g|、|g−b| ≤ 12），
            且均值落在中灰区（28~215），既不糊成黑块也不被漂白；
          · **有明暗层次** —— 可见像素亮度标准差 > 5（枪管/机匣/枪托起伏）。
    """
    from PIL import Image
    im = Image.open(PH_DIR / ("%s.png" % key))
    assert im.mode == "RGBA", "%s 应为透明底 RGBA，当前 %s" % (key, im.mode)
    w, h = im.size
    lo, hi = im.getchannel("A").getextrema()
    assert lo == 0, "%s 背景不透明（alpha 最小值 %d），透明抠图失败" % (key, lo)
    assert hi >= 250, "%s 主体墨迹太淡（alpha 最大值 %d）" % (key, hi)

    px = im.load()
    vals = []
    for y in range(h):
        for x in range(w):
            r, g, b, a4 = px[x, y]
            if a4 <= 128:
                continue
            assert abs(r - g) <= 12 and abs(g - b) <= 12, \
                "%s 存在彩色像素 (%d,%d,%d)，不是石墨灰阶" % (key, r, g, b)
            vals.append((r + g + b) / 3.0)
    assert vals, "%s 没有任何可见墨迹" % key
    n = float(len(vals))
    mean = sum(vals) / n
    std = (sum((v - mean) ** 2 for v in vals) / n) ** 0.5
    # 中灰区：R29.3 的深色卡底（mean<55）不再适用，透明线稿是中灰石墨
    assert 28 < mean < 215, "%s 可见像素平均亮度 %.1f，不在石墨中灰区" % (key, mean)
    assert std > 5.0, "%s 亮度标准差仅 %.2f，像纯色块" % (key, std)
    black = sum(1 for v in vals if v <= 6)
    assert black / n < 0.60, "%s 纯黑像素占 %.1f%%，像被二值化过" % (key, 100 * black / n)
