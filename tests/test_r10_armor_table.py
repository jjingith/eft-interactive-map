"""第十轮（防弹衣/弹挂 20 列重构）真实数据审计与静态结构测试。

两层：
1. **真实数据审计**（纯 Python，读 data/items.json）：以 6B43 为固定回归样本核对
   内衬区域映射、耐久汇总（350 / 1867）、硬板位、重量、armorType（H/L 依据）与
   兑换渠道；再对**全部** Armor / ChestRig 物品审计 fx=1 zone 是否都能落进
   app.js 的九个内衬列——映射不到的必须为 0（有就说明内衬列模型缺口）。
2. **静态结构**：app.js / style.css / LW_COL_DEFAULTS 里 20 列装配、角标、
   面部空槽巴拉克拉瓦占位的必备元素；占位图标文件必须真实存在于本地资源目录。

不联网、不引入运行期依赖；数据全部来自仓库内文件。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_JS = ROOT / "app.js"
STYLE_CSS = ROOT / "style.css"
ITEMS_JSON = ROOT / "data" / "items.json"
BALACLAVA_ICON = ROOT / "assets" / "icons-items" / "572b7f1624597762ae139822.webp"

# 6B43 固定回归样本（任务书指定）：id 与任务书给定的各内衬区显示耐久
ID_6B43 = "545cdb794bdc2d3a198b456a"
EXPECT_6B43_LINERS = {
    "soft_armor_front": 85, "soft_armor_back": 85,
    "soft_armor_left": 26, "soft_armor_right": 26,
    "collar": 32, "shoulder_l": 28, "shoulder_r": 28,
    "groin": 40,
}
EXPECT_6B43_TOTAL = 350       # 上述各区显示耐久之和
EXPECT_6B43_EFF = 1867        # 350 ÷ Aramid 毁损系数 0.1875 = 1866.67 → 四舍五入
HARD_PLATE_ZONES = {"front_plate", "back_plate", "left_side_plate", "right_side_plate"}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _liner_zones_from_app_js() -> list[str]:
    """从 app.js 的 LINER_COL_ZONES 定义里提取九个内衬 zone（避免测试里再抄一份映射）。"""
    js = _read(APP_JS)
    i = js.index("var LINER_COL_ZONES = [")
    block = js[i:js.index("];", i)]
    zones = re.findall(r'zone:\s*"([^"]+)"', block)
    assert len(zones) == 9, "内衬列应为 9 个 zone，实际 %d" % len(zones)
    return zones


def _items_data() -> dict:
    data = json.loads(_read(ITEMS_JSON))
    assert isinstance(data, dict) and "items" in data, "items.json 顶层结构变化"
    return data


# ---------------------------------------------------------------- 1. 真实数据审计
def test_r10_6b43_regression_sample():
    """6B43：内衬九区归位、350/1867 汇总、四个硬板位、重量、armorType、兑换渠道。"""
    data = _items_data()
    rec = data["items"].get(ID_6B43)
    assert rec, "data/items.json 里找不到 6B43（%s）" % ID_6B43
    assert "6B43" in (rec.get("n") or ""), "样本物品名称不含 6B43：%s" % rec.get("n")

    # 本体属性：护甲等级 / 重量 / armorType（H/L 角标的可验证依据）
    assert rec.get("cl") == 6, "6B43 护甲等级与回归预期不符：%r" % rec.get("cl")
    assert abs(float(rec.get("w")) - 10.8) < 1e-9, "6B43 重量与回归预期不符：%r" % rec.get("w")
    assert rec.get("at") == "Heavy", "6B43 armorType 应为 Heavy：%r" % rec.get("at")

    # aps 分解：四个硬板位（fx 缺省/0 且带 plates）+ 内衬区
    aps = rec.get("aps") or []
    hard = {str(a.get("zone", "")).lower() for a in aps
            if not a.get("fx") and a.get("plates")}
    assert HARD_PLATE_ZONES <= hard, "6B43 缺硬板位槽位：%s" % sorted(HARD_PLATE_ZONES - hard)

    liner_zones = {z.lower() for z in _liner_zones_from_app_js()}
    got: dict[str, int] = {}
    mats: set[str] = set()
    for a in aps:
        if not a.get("fx"):
            continue
        z = str(a.get("zone", "")).lower()
        assert z in liner_zones, "6B43 内衬区 %s 不在九列映射内" % a.get("zone")
        assert z not in got, "6B43 内衬区重复：%s" % a.get("zone")
        got[z] = int(a["dur"])
        if a.get("mat"):
            mats.add(a["mat"])
    assert got == EXPECT_6B43_LINERS, (
        "6B43 内衬区耐久与回归预期不符：多 %s，少 %s"
        % ({k: v for k, v in got.items() if EXPECT_6B43_LINERS.get(k) != v},
           {k: v for k, v in EXPECT_6B43_LINERS.items() if got.get(k) != v}))
    # 后裆内衬（groin_back）必须**不存在**：任务书预期该格显示「—」，不能造数
    assert "groin_back" not in got, "6B43 出现了预期之外的后裆内衬数据"
    # 汇总：350 = Σ显示耐久；1867 = round(350 ÷ Aramid d)
    assert sum(got.values()) == EXPECT_6B43_TOTAL, (
        "6B43 内衬显示耐久之和应为 %d，实际 %d" % (EXPECT_6B43_TOTAL, sum(got.values())))
    assert mats == {"Aramid"}, "6B43 内衬材质应为 Aramid：%s" % sorted(mats)
    d = (data.get("audit") or {}).get("materials", {}).get("Aramid", {}).get("d")
    assert isinstance(d, (int, float)) and d > 0, "audit.materials.Aramid.d 缺失"
    assert round(EXPECT_6B43_TOTAL / d) == EXPECT_6B43_EFF, (
        "350 ÷ %s 应四舍五入为 %d" % (d, EXPECT_6B43_EFF))

    # 获取方式：本地逐笔 trade 必须有确认兑换（barter）；构建期 src 允许与之矛盾
    trade = rec.get("trade") or []
    assert any(t.get("k") == "barter" for t in trade), "6B43 缺确认兑换渠道（trade）"
    for t in trade:
        if t.get("k") == "barter":
            assert t.get("r"), "兑换配方缺少所需物品清单（r）"
            assert t.get("t"), "兑换缺少商人数（t）"


def test_r10_all_armor_rig_liner_zones_covered():
    """数据集级审计：全部 Armor / ChestRig 的 fx=1 内衬区都必须落进九列映射。"""
    data = _items_data()
    liner_zones = {z.lower() for z in _liner_zones_from_app_js()}
    checked = 0
    unmatched: list[tuple[str, str]] = []
    for iid, rec in (data.get("items") or {}).items():
        if rec.get("pt") not in ("Armor", "ChestRig"):
            continue
        checked += 1
        for a in rec.get("aps") or []:
            if not a.get("fx"):
                continue
            z = str(a.get("zone", "")).lower()
            if z not in liner_zones:
                unmatched.append((iid, a.get("zone", "")))
    assert checked > 0, "数据集里没有 Armor/ChestRig 物品，审计无效"
    assert not unmatched, (
        "%d 件护甲/弹挂中有 fx 内衬区落不进九列映射（不得塞进相近列，需报告）：%s"
        % (len(unmatched), unmatched[:10]))


# ---------------------------------------------------------------- 2. 静态结构
def test_r20_armor_rig_20col_assembly_static():
    """app.js 里 armor / rig 的属性列装配必须对齐参考站 db4（R22.0「按 db4 来」）。

    R22.0 起 armor 与 rig 分开：armor 走参考站 Armor/Armored Rig 口径（插板 + Material +
    Eff + 内衬 + Zone + Cap/SE/Slots），rig 走参考站 Chest Rig 口径（Cap/SE/Slots）。
    本测试断言两条装配链的关键节点存在、顺序合理，且默认列宽覆盖到位。
    """
    js = _read(APP_JS)
    # armor 装配链：名称 → 减益 → 四板位 → Material/Eff → 九内衬 → Zone → Cap/SE/Slots → 重量 → 获取方式 → 价格
    assert "cols = [nameCol, penCol].concat(plateCols)" in js
    assert ".concat([matCol, effDurCol]).concat(linerCols)" in js
    assert ".concat([zoneIcoCol, capCol, seCol, slotsCol, wCol, srcCol]);" in js
    # rig 装配链（无甲胸挂走 Chest Rig 口径，不再套插板/内衬版式）
    assert "cols = [nameCol, penCol, capCol, seCol, slotsCol, wCol, srcCol];" in js
    # R219：获取方式回到末列合并格（图标 + 价格 + 等级），表尾不再有独立价格列；
    # 冲突仍走整行标红
    assert "var srcColPrice" not in js, "不应再有第三套合并列定义（合并逻辑只在 renderSrcCell 里）"
    assert "var p24Col" not in js and "var p7dCol" not in js, "R74 的两列价格应已撤掉"
    assert "cols.splice(1, 0, conflictCol);" not in js
    # 逐类别默认列宽里 rig 带齐 Chest Rig 口径的键（含独立获取方式列）
    i = js.index("    rig: {")
    block = js[i:js.index("},", i)]
    for key in ("n", "pen", "cap", "se", "slots", "w", "srcGroup"):
        assert re.search(r"\b%s:\s*\d+" % re.escape(key), block), \
            "LW_COL_DEFAULTS.rig 缺列宽：%s" % key


def test_r20_zone_column_icon_only_and_src_column_static():
    """防护区域列只渲染图标（无文字标签）；获取方式是末列合并格（图标 + 价格 + 等级）。

    第十一轮问题 A：armor/rig 的 zoneIcoCol 与头盔的 zoneText 列统一走 renderZoneIconCell
    （同一映射 / 同一回退），className 与「—」占位移进该函数；本测试改为断言统一渲染
    机制与两类别的委托接线，语义不变（armor/rig 不显示文字，缺失 →「—」）。
    R219：价格并回获取方式格内（用户要求恢复的原样式）——跳蚤那一枚的价格跟
    「右上角模式 × 价格档」走，商人 / 兑换 / 制作写各自那一条，长文案仍只走悬停。
    """
    js = _read(APP_JS)
    css = _read(STYLE_CSS)
    # 统一渲染函数：命中图标 → 只放 img（armor/rig 用 lw-zone-ico，头盔用 tbl-zone-ico）；
    # allowText=false 时缺失 → 「—」占位（lw-zone-dash）
    assert "function renderZoneIconCell(cell, row, allowText)" in js
    assert 'img.className = allowText ? "tbl-zone-ico" : "lw-zone-ico";' in js
    assert 'className = "lw-zone-dash"' in js and 'textContent = "—"' in js
    # zoneIcoCol（armor/rig）委托统一渲染，false = 不显示文字；头盔 zoneText 列 allowText=true
    i = js.index("var zoneIcoCol = {")
    block = js[i:js.index("var srcCol = {", i)]
    assert "renderZoneIconCell(cell, row, false)" in block
    assert "renderZoneIconCell(cell, row, true)" in js
    # R219：获取方式合并格 —— 单一定义、格内同时有价格与配方摘要
    assert "function renderSrcCell(cell, row) {" in js
    assert "var srcColPrice" not in js
    assert 'className = "lw-src-price"' in js, "价格必须回到获取方式格内"
    assert 'className = "lw-src-req"' in js, "兑换配方摘要必须回到格内（超出省略、明细走悬停）"
    # 跳蚤那一枚读 row.fleaInfo（模式 × 价格档），不是写死的构建期价
    assert "row.fleaInfo" in js and "function fleaPriceInfo(id, rec, mode, basis)" in js
    # 图标 + 罗马等级仍在；无来源数据时用「—」空占位；悬停保留完整文案（含价格行）
    assert 'className = "lw-src"' in js and 'className = "lw-src-lv"' in js
    assert 'dash.className = "lw-dash";' in js and "bindLwTip(dash, srcTip(missing.tip));" in js
    assert "function srcTipNoPrice" not in js, "R219 起不再剥离浮窗里的价格行"
    # 对应 CSS 作用域都在 .loadout-workbench 内
    for sel in (".lw-liner-mat", ".lw-liner-sum", ".lw-liner-cell",
                ".lw-zone-ico", ".lw-zone-dash", ".lw-src", ".lw-src-ico", ".lw-src-lv",
                ".lw-src-price", ".lw-src-req", ".lw-name-plain"):
        assert ".loadout-workbench %s" % sel in css, "缺样式：%s" % sel


def test_r20_badges_and_balaclava_placeholder_static():
    """问题1/问题6 的静态要素：面部空槽占位、armor/rig 角标与样式。

    R18.1 变更：面部空槽不再走「巴拉克拉瓦物品图标 + 灰度半透明」特例，
    改为与其余槽位统一的「白底 + 纯黑剪影」（占位图仍由巴拉克拉瓦头套的真实轮廓
    生成，见 tools/build_slot_placeholders.py）。不变量不变 —— **面部空槽必须有
    一张真实存在于本地资源的占位图形，且选中装备后仍显示真实图标**。
    因此断言迁移为：面部位图存在 + 剪影映射包含 face + 不再有 grayscale 特例。
    """
    js = _read(APP_JS)
    css = _read(STYLE_CSS)
    # 面部空槽：silKey("face") 映射到本地剪影文件，文件必须真实存在
    assert 'face: "face"' in js, "面部槽位缺剪影映射"
    assert (ROOT / "assets" / "ui" / "placeholders" / "face.png").is_file(), \
        "面部空槽剪影缺失：assets/ui/placeholders/face.png"
    assert "assets/ui/placeholders/" in js, "SIL_DIR 未指向剪影目录"
    # 占位图溯源（R30.0：透明底石墨线稿，素材取自上游 -base-image.webp 缓存目录）：
    # face 必须记录来源目录 + 取用 id（可重建，不用无关素材冒充）。
    manifest = json.loads((ROOT / "assets" / "ui" / "placeholders" / "manifest.json")
                          .read_text(encoding="utf-8"))
    face = [i for i in manifest["items"] if i["key"] == "face"]
    assert face, "面部占位图记录缺失"
    src = manifest.get("source", {})
    assert src.get("dir"), "面部占位图缺素材来源目录记录"
    assert "透明" in src.get("kind", ""), \
        "R30.0 起占位图走透明底素材，source.kind 应标注：%s" % src.get("kind")
    ex = manifest.get("extract", {}).get("face", {})
    assert ex.get("itemId"), "面部占位图缺溯源 itemId（无法证明取自真实装备图案）"
    assert ex.get("sourceId"), "面部占位图缺溯源 sourceId（无法重建）"
    # 两个 id 都要能在 items.json 里查到（不是编造的 id）
    items_json = json.loads((ROOT / "data" / "items.json").read_text(encoding="utf-8"))["items"]
    assert ex["itemId"] in items_json, "面部 itemId 不在 items.json：%s" % ex["itemId"]
    assert ex["sourceId"] in items_json, "面部 sourceId 不在 items.json：%s" % ex["sourceId"]
    # 产物本身必须是透明底（抠图真的生效，而不是盖了一层色块）
    from PIL import Image
    face_im = Image.open(ROOT / "assets" / "ui" / "placeholders" / "face.png")
    assert face_im.mode == "RGBA", "面部占位图不是透明底 RGBA：%s" % face_im.mode
    fa = face_im.getchannel("A").load()
    fw, fh = face_im.size
    for (cx, cy) in ((0, 0), (fw - 1, 0), (0, fh - 1), (fw - 1, fh - 1)):
        assert fa[cx, cy] == 0, \
            "面部占位图四角应为全透明，(%d,%d) alpha=%d" % (cx, cy, fa[cx, cy])
        # 旧的灰度半透明特例必须已经移除，否则白底黑剪影会被二次降饱和变成灰块。
        # R30.0 迁移：全站改走「透明底石墨线稿」，躯干线稿**合法使用**
        # `filter: grayscale(1) brightness(2.9)`（把原图降饱和成石墨灰）；
        # 被禁的只是「面部剪影专属的 grayscale 特例规则」——即 .lw-sil-face 这条选择器。
        assert ".lw-sil-face {" not in css, "面部剪影不应再有 grayscale 特例"
    # 角标：最高防弹等级（本体 vs 硬插板取最高，空槽 0 不显示）+ H/L（at 字段）
    assert "function maxArmorClassOf(rootKey)" in js
    assert 'var LW_HARD_PLATE_ZONES = ["front_plate", "back_plate", "left_side_plate", "right_side_plate"];' in js
    i = js.index('if ((key === "armor" || key === "rig" || key === "helmet") && rec)')
    block = js[i:js.index("return btn;", i)]
    assert 'className = "lw-cl-badge"' in block and "maxArmorClassOf(key)" in block
    assert 'rec.at === "Heavy"' in block and 'rec.at === "Light"' in block
    assert 'atb.textContent = rec.at === "Heavy" ? "H" : "L";' in block
    # 样式：左下等级数字 + 右下 H(紫) / L(绿)
    for sel in (".lw-cl-badge", ".lw-at-badge", ".lw-at-badge.lw-at-heavy",
                ".lw-at-badge.lw-at-light"):
        assert ".loadout-workbench %s" % sel in css, "缺角标样式：%s" % sel
    # H/L 颜色按任务书：重甲紫底、轻甲绿底
    heavy = css[css.index(".lw-at-badge.lw-at-heavy"):]
    light = css[css.index(".lw-at-badge.lw-at-light"):]
    assert re.search(r"background:\s*#[0-9a-fA-F]+;", heavy)
    assert re.search(r"background:\s*#[0-9a-fA-F]+;", light)
