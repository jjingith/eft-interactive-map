# -*- coding: utf-8 -*-
"""R18.1：空槽剪影占位图 / 三处文字对比度 / 护甲与插板下拉分组。

三层：
1. **产物像素审计**（Pillow 直读 PNG）：每个空槽剪影必须是「纯白底 + 纯黑图形」，
   画布尺寸与卡片内框一致，且确实有足量墨迹（不是一张空白图或一张全黑方块）。
2. **接线审计**（纯文本）：app.js 的槽位→文件映射、CSS 的三处对比度修正必须存在，
   且旧的 grayscale 面部特例已移除。
3. **分组规则审计**（纯 Python 复刻 JS 规则）：用 data/items.json 真实字段推出期望分组，
   断言「等级降序 → 材质固定序 → 无内衬最后」与「不虚构数据里不存在的组合」。

不联网、不引入运行期依赖。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
APP_JS = ROOT / "app.js"
THEME_CSS = ROOT / "theme-windows-xp.css"
STYLE_CSS = ROOT / "style.css"
ITEMS = ROOT / "data" / "items.json"
PH_DIR = ROOT / "assets" / "ui" / "placeholders"
MANIFEST = PH_DIR / "manifest.json"

ROMAN = {1: "I", 2: "II", 3: "III", 4: "IV", 5: "V", 6: "VI"}
MAT_ZH = {"Aramid": "芳纶", "UHMWPE": "聚乙烯", "Combined": "复合材料",
          "Titan": "钛合金", "Aluminium": "铝合金", "ArmoredSteel": "装甲钢",
          "Ceramic": "陶瓷", "Glass": "防弹玻璃"}
# 与 app.js 的 AM_SIM_MAT_ORDER 一致：硬质到软质，未知材质排在最后
MAT_ORDER = ["Ceramic", "Titan", "ArmoredSteel", "UHMWPE",
             "Combined", "Aluminium", "Aramid", "Glass"]

EXPECT_SLOTS = ["helmet", "armor", "rig", "backpack", "headphones",
                "glasses", "face", "armband", "dogtag",
                "primary", "holster", "melee"]


def _items():
    return json.loads(ITEMS.read_text(encoding="utf-8"))["items"]


def _manifest():
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


# --------------------------------------------------------------- 1. 产物像素
def test_placeholder_pngs_are_graphite_on_transparent():
    """空槽占位图的当前规格（R30.0）：**透明底石墨素描**。

    历史沿革（断言随规格迁移，不删测试）：
      R18.1 白底纯黑剪影 → R21.0 灰白填充 + 灰内描边 → R28.0 灰色细线轮廓
      → R29.1/2 素描滤镜 → R29.3 直接采用游戏内截图裁切
      → R30.0 透明底石墨素描（用户：「现在 ui 是 xp 风格，你现在做的这个怎么是纯黑的」——
        不透明深色游戏卡在 XP 浅色面板上就是一块黑异物；故卡片底板改由 CSS 的
        XP 凹陷边框 + 斜纹渐变绘制，图片本身只保留灰色图形）。

    判据：
      · **背景必须透明**（外圈像素 alpha ≈ 0）—— 本轮核心；
      · 画布 = 卡片 ×2（HiDPI）；
      · 必须有成规模的可见图形像素（不能是空白图）；
      · 图形是灰阶（三通道接近），且不是大面积纯黑 / 纯白。
    """
    from PIL import Image

    man = _manifest()
    assert re.match(r"R\d+\.\d+$", man["round"]), man["round"]
    items = {i["key"]: i for i in man["items"]}
    assert set(items) == set(EXPECT_SLOTS), "剪影清单与槽位清单不一致"
    assert man["missing"] == [], "存在缺失项：%s" % man["missing"]

    for key in EXPECT_SLOTS:
        rec = items[key]
        path = ROOT / rec["file"]
        assert path.is_file(), "占位图文件缺失：%s" % rec["file"]
        im = Image.open(path)
        cw, ch = rec["card"]
        ow, oh = rec["canvas"]
        assert im.size == (ow, oh), "%s 画布尺寸与记录不符：记录 %s 实际 %s" % (
            key, (ow, oh), im.size)
        assert (ow, oh) == (cw * 2, ch * 2), \
            "%s 画布应为卡片 %dx%d 的 2 倍，实际 %dx%d" % (key, cw, ch, ow, oh)
        assert im.mode == "RGBA", "%s 必须是带 Alpha 的 PNG" % key

        rgba = im.convert("RGBA")
        w, h = rgba.size
        px = rgba.load()
        # 1) 外圈（四周 6% 边框带）必须全透明 —— 底板交给 CSS，图片不能再带实底。
        #    取景留白由 manifest 的 render.margin 给出（0.09），比判定带宽 3 个点，
        #    给轮廓描边的向外膨胀和 LANCZOS 振铃留余量。
        m = max(2, int(min(w, h) * 0.06))
        edge = []
        for y in range(h):
            for x in range(w):
                if x < m or y < m or x >= w - m or y >= h - m:
                    edge.append(px[x, y][3])
        if edge:
            assert max(edge) <= 8, \
                "%s 外圈仍有不透明像素（max alpha %d），底板没抠干净" % (key, max(edge))

        # 2) 必须有成规模的图形像素（不是空白图）
        vis = [px[x, y] for y in range(h) for x in range(w) if px[x, y][3] > 64]
        if vis:
            frac = len(vis) / float(w * h)
            assert frac > 0.004, \
                "%s 可见图形像素仅 %.2f%%，疑似空白图" % (key, 100 * frac)
            # 3) 图形必须是**灰阶**（石墨），不能带饱和色
            for r, g, b, a in vis[:2000]:
                assert abs(r - g) <= 12 and abs(g - b) <= 12, \
                    "%s 图形含彩色像素 rgb(%d,%d,%d)，不是石墨灰阶" % (key, r, g, b)
            # 4) 不能是大面积纯黑（黑块）
            lums = [0.299 * r + 0.587 * g + 0.114 * b for r, g, b, a in vis]
            mmean = sum(lums) / len(lums)
            assert 28.0 <= mmean <= 215.0, \
                "%s 图形平均亮度 %.1f 越界（应是可辨识的中灰）" % (key, mmean)


def test_placeholder_sources_are_the_requested_items():
    """R30.0：占位图由「该槽位代表装备」的上游透明底原图渲染，溯源必须可重建。

    历史沿革：R18~R29.2 记 `itemId`/`sourceFile`；R29.3 记 `source.file` +
    `extract[key].box`（游戏截图裁切）；R30.0 起改回**按装备 id 取图**
    （源 = `build-cache/gear-icons-src/{id}.webp`），`extract[key]`
    记 `itemId`（槽位代表装备）与 `sourceId`（实际取图的物品 / 预设 id）。
    三条路径都要求可重建、不得用无关素材冒充 —— 只是溯源字段不同。
    """
    man = _manifest()
    src = man.get("source", {})
    assert src.get("dir"), "必须记录源图目录"
    assert src.get("kind"), "必须记录源图类型"
    ex = man.get("extract", {})
    assert set(ex) == set(EXPECT_SLOTS), "溯源清单与槽位清单不一致"
    for key in EXPECT_SLOTS:
        e = ex[key]
        assert e.get("itemId"), "%s 缺槽位代表装备 id" % key
        assert e.get("sourceId"), "%s 缺取图用的物品 id" % key

# --------------------------------------------------------------- 2. 接线审计
def test_app_js_maps_every_slot_to_its_own_placeholder():
    js = APP_JS.read_text(encoding="utf-8")
    assert 'var SIL_DIR = "assets/ui/placeholders/";' in js
    for key in ("helmet", "armor", "rig", "backpack", "headphones", "glasses",
                "face", "armband", "dogtag", "melee", "primary1", "primary2", "holster"):
        assert re.search(r'\b%s:\s*"[a-z]+"' % key, js), "槽位 %s 缺剪影映射" % key
    # 主武器 1/2 复用同一张 AK-74；手枪必须独立，不能再共用步枪图形
    assert re.search(r'primary1:\s*"primary"', js)
    assert re.search(r'primary2:\s*"primary"', js)
    assert re.search(r'holster:\s*"holster"', js)
    assert "function silSrc(" in js and "function silImg(" in js
    # 面部不再走「物品图标 + 灰度」特例
    assert "BALACLAVA_ITEM_ID" not in js


def test_theme_fixes_three_contrast_spots():
    css = THEME_CSS.read_text(encoding="utf-8")
    # 1) 配装悬停提示：标题行必须是近黑色
    assert re.search(r"\.lw-tip \.lw-tip-head\s*\{\s*color:\s*#0{3}", css), \
        "缺悬停提示标题行的颜色修正"
    # 2) BALLISTICS graph：悬停提示里的弹药名/行文字
    assert re.search(r"\.am-graph-tip \.am-graph-tip-row\s*\{\s*color:\s*#232323", css)
    assert re.search(r"\.am-graph-tip \.am-graph-tip-name\s*\{[^}]*color:\s*#0{3}", css)
    # 3) 弹药详情标题栏：口径/类型/分类与标题同为白色
    assert "html .am-modal-head .am-detail-meta" in css
    assert re.search(r"html \.am-modal-head \.am-detail-meta\s*\{[^}]*color:\s*#ffffff", css)
    # R299 修订：槽位名改为贴右上角的浮字，透明底、无边框（不再压白底标签）
    style_css = STYLE_CSS.read_text(encoding="utf-8")
    label = style_css[style_css.index(".loadout-workbench .lw-cell-label {"):]
    label = label[:label.index("}")]
    assert "position: absolute;" in label
    assert "right: calc(1 * var(--lw-p));" in label
    assert "background: transparent;" in label


def test_style_css_no_longer_has_grayscale_face_silhouette():
    """面部空槽不再有「灰度物品图标」特例（R18.1 起与其它槽位统一走剪影）。

    R30.0 注：本文件后来为**躯干占位图**引入了 `filter: grayscale(1) brightness(2.9)`
    （用途是把深色旧剪影提亮成中灰轮廓，与「面部灰度特例」无关），
    所以断言从「全文不含 grayscale(1)」收窄为「不存在 .lw-sil-face 特例规则」。
    """
    css = STYLE_CSS.read_text(encoding="utf-8")
    # 只认「选择器 + {」的规则，注释里提到旧类名不算
    assert not re.search(r"\.lw-sil-face\s*\{", css), "面部灰度特例规则又回来了"


# --------------------------------------------------------------- 3. 分组规则
def _is_armor(rec):
    return rec.get("pt") == "Armor" or (rec.get("slot") == "rig" and (rec.get("cl") or 0) > 0)


def _liner(rec):
    """护甲真正参与计算的内衬：aps[] 中 fx=1、等级最高的那条（与引擎取数同源）。"""
    best = None
    for a in rec.get("aps") or []:
        if not a or not a.get("fx"):
            continue
        if best is None or (a.get("cl") or 0) > (best.get("cl") or 0):
            best = a
    return best


def _armor_group(rec):
    liner = _liner(rec)
    if liner is None:
        return ("无内衬", 1, -1, "")
    cls = liner.get("cl") if isinstance(liner.get("cl"), int) and liner.get("cl") > 0 else None
    mat = liner.get("mat") or rec.get("mat")
    if cls is None or not mat:
        return ("内衬数据未知", 2, -1, "")
    return ("%s · %s · 内衬" % (ROMAN.get(cls, "?"), MAT_ZH.get(mat, mat)), 0, cls, mat)


def _plate_group(rec):
    cls = rec.get("cl") if isinstance(rec.get("cl"), int) and rec.get("cl") > 0 else None
    mat = rec.get("mat")
    if cls is None or not mat:
        return ("等级或材质缺失", 2, -1, "")
    return ("%s · %s" % (ROMAN.get(cls, "?"), MAT_ZH.get(mat, mat)), 0, cls, mat)


def test_armor_groups_follow_liner_level_then_material():
    items = _items()
    groups = {}
    for rec in items.values():
        if not _is_armor(rec):
            continue
        label, kind, cls, mat = _armor_group(rec)
        groups[label] = (kind, cls, mat)

    # 任务书点名的三类实际存在的内衬组必须出现
    for must in ("III · 芳纶 · 内衬", "II · 芳纶 · 内衬"):
        assert must in groups, "缺护甲分组：%s" % must
    assert "无内衬" in groups, "纯插板护甲应归入「无内衬」"
    # 数据里没有 I 级内衬，就不允许凭空出现这一组
    assert not any(g.startswith("I · ") for g in groups), "出现了数据中不存在的 I 级内衬组"

    order = sorted(groups.items(), key=lambda kv: (kv[1][0], -kv[1][1],
                                                   MAT_ORDER.index(kv[1][2])
                                                   if kv[1][2] in MAT_ORDER else 99,
                                                   kv[0]))
    kinds = [v[1][0] for v in order]
    assert kinds == sorted(kinds), "「无内衬 / 未知」必须排在正常组之后"
    normal = [v for v in order if v[1][0] == 0]
    levels = [v[1][1] for v in normal]
    assert levels == sorted(levels, reverse=True), "内衬等级未按降序排列"
    # 同等级内材质顺序固定
    for lv in set(levels):
        mats = [v[1][2] for v in normal if v[1][1] == lv]
        idx = [MAT_ORDER.index(m) if m in MAT_ORDER else 99 for m in mats]
        assert idx == sorted(idx), "%s 级内衬的材质顺序不稳定" % ROMAN.get(lv, lv)


def test_armor_group_uses_liner_not_body_class():
    """内衬等级必须取自 aps[].fx 条目，不能用护甲本体 cl 顶替（两者确实不同）。"""
    items = _items()
    diff = 0
    for rec in items.values():
        if not _is_armor(rec):
            continue
        liner = _liner(rec)
        if liner and liner.get("cl") and rec.get("cl") and liner["cl"] != rec["cl"]:
            diff += 1
    assert diff >= 5, "没有出现「内衬等级 != 本体等级」的样本，分组口径可能取错了字段"


def test_plate_groups_exist_for_every_real_combination():
    items = _items()
    plate_ids = set()
    for rec in items.values():
        for a in rec.get("aps") or []:
            for pid in a.get("plates") or []:
                plate_ids.add(pid)
    assert len(plate_ids) > 20, "插板候选数量异常：%d" % len(plate_ids)

    groups = {}
    unknown = []
    for pid in plate_ids:
        rec = items.get(pid)
        if not rec:
            continue
        label, kind, cls, mat = _plate_group(rec)
        if kind == 2:
            unknown.append(pid)
            continue
        groups.setdefault(label, 0)
        groups[label] += 1

    for must in ("VI · 陶瓷", "VI · 钛合金", "VI · 聚乙烯", "V · 陶瓷"):
        assert must in groups, "缺插板分组：%s" % must

    # 每个组的标签都必须能由某个真实物品反推出来（不虚构组合）
    rebuilt = set()
    for pid in plate_ids:
        rec = items.get(pid)
        if rec and _plate_group(rec)[1] == 0:
            rebuilt.add(_plate_group(rec)[0])
    assert set(groups) == rebuilt
    # 等级分布必须真实：至少覆盖 VI..III 中的四级
    levels = {g.split(" · ")[0] for g in groups}
    assert len(levels & {"VI", "V", "IV", "III", "II", "I"}) >= 4, \
        "插板等级覆盖不足：%s" % sorted(levels)


def test_grouping_helpers_wire_filtering_before_grouping():
    """分组只能改变展示：候选必须先经过装备池/兼容过滤，再交给分组函数。"""
    js = APP_JS.read_text(encoding="utf-8")
    for fn in ("amSimLinerEntry", "amSimArmorGroup", "amSimPlateGroup", "amSimFillGrouped"):
        assert "function %s(" % fn in js, "缺函数 %s" % fn
    # 护甲候选：allowed 过滤在 amSimGearCatalog 内，分组在其后
    i_cat = js.index("var armorIds = amSimGearCatalog(\"armor\", allowedA);")
    i_fill = js.index("amSimFillGrouped(sel, arows);")
    assert i_cat < i_fill
    # 插板候选：Boss 白名单过滤必须在分组之前
    i_pol = js.index("plateIds = plateIds.filter(function (pid) { return sideAllowed.indexOf(pid) >= 0; });")
    i_pfill = js.index("amSimFillGrouped(psel, prow);")
    assert i_pol < i_pfill, "插板白名单过滤必须发生在分组渲染之前"
    # 不得为了分组而放宽兼容性判断
    assert "socket.plates" in js


@pytest.mark.parametrize("label", ["III · 芳纶 · 内衬", "II · 芳纶 · 内衬"])
def test_named_armor_groups_have_members(label):
    items = _items()
    members = [rec.get("n") for rec in items.values()
               if _is_armor(rec) and _armor_group(rec)[0] == label]
    assert members, "分组 %s 没有成员" % label
