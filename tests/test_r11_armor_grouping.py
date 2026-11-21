"""第十一轮（防护区域图标补全 + 基础防弹等级列与分组排序）数据级与静态结构测试。

三层：
1. **映射全覆盖审计**（纯 Python，读 data/items.json + app.js）：从 app.js 提取
   ZONE_ICON_BY_WORDS 真实映射表，验证 Armor / ChestRig(slot=rig) / Headwear(cat=helmet)
   三类中**所有**有 z 数据的装备其部位词组合都能命中映射条目（不得漏）；原始无 z 的装备
   单独列出（不伪造图标）。同时核对交付审计 JSON 与待补图标的登记状态。
2. **基础防弹等级**：三类装备 cl 字段结构一致性（数字或缺失，绝无 0/负数混用），
   6B43=6 / PACA=2 / 普通弹挂无 cl 的语义样本；app.js 中 baseArmorClassOf 只读本体 cl、
   不复用 maxArmorClassOf（含插板）。
3. **列与分组排序静态结构**：armor/rig 21 列装配顺序、helmet 列集（baseCl 替换 cl）、
   createTable 分组主序比较器、baseClGroupRank 组序规则、iconize.py 新增组合任务。

不联网、不引入运行期依赖；数据全部来自仓库内文件。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_JS = ROOT / "app.js"
ICONIZE_PY = ROOT / "tools" / "iconize.py"
ITEMS_JSON = ROOT / "data" / "items.json"
AUDIT_JSON = ROOT / "docs" / "r11-armor-grouping" / "protection-zone-audit.json"
ZONES_DIR = ROOT / "assets" / "icons" / "zones"

ID_6B43 = "545cdb794bdc2d3a198b456a"
ID_PACA = "5648a7494bdc2d9d488b4583"
ID_PLAIN_RIG = "5648a69d4bdc2ded0b8b457b"   # BlackRock 胸挂：普通弹挂，无 cl 无 z
ID_BROKEN_MASK = "5b432b2f5acfc4771e1c6622"  # 破碎面具：头盔，无 z

# 关键组合条目（词集 → 图标文件；R31.3 手绘重做、已去前插板叠层，映射必须就位且文件在盘）
KEY_COMBOS = {
    "上胸": "zone-chest.png",
    "上胸|腹部|侧面": "zone-chest-abdomen-side.png",
    "上胸|侧面": "zone-chest-side.png",
    "上胸|腹部|侧面|裆部|脖颈|肩部": "zone-chest-abdomen-side-groin-neck-shoulder.png",
    # R295：头部换成用户 20261118 手绘新版，颈部在头部语境下拆成喉部/后颈
    "头顶|后脑|面部|下颚|眼部|耳部|喉部|后颈":
        "zone-head-top-back-face-jaw-eyes-ears-throat-nape.png",
    "头顶|后脑|面部|眼部|耳部": "zone-head-top-back-face-eyes-ears.png",
    "头顶|面部|下颚|眼部|耳部": "zone-head-top-face-jaw-eyes-ears.png",
}

ZONE_WORD_ORDER = ["上胸", "腹部", "侧面", "裆部", "脖颈", "肩部",
                   "头顶", "后脑", "面部", "下颚", "眼部", "耳部", "喉部", "后颈"]
# R295：Neck* 的词取决于是否头部装备（含 HEAD_CORE 任一区）。
HEAD_CORE = {"ParietalHead", "BackHead", "HeadCommon", "Jaw", "Eyes", "Ears"}
ZONE_WORDS = {
    "ParietalHead": "头顶", "BackHead": "后脑", "HeadCommon": "面部", "Jaw": "下颚",
    "Eyes": "眼部", "Ears": "耳部",
    "LeftUpperArm": "肩部", "RightUpperArm": "肩部",
    "RibcageUp": "上胸", "SpineTop": "上胸",
    "RibcageLow": "腹部", "SpineDown": "腹部",
    "LeftSideChestDown": "侧面", "RightSideChestDown": "侧面",
    "Pelvis": "裆部", "PelvisBack": "裆部",
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _items_data() -> dict:
    data = json.loads(_read(ITEMS_JSON))
    assert isinstance(data, dict) and "items" in data, "items.json 顶层结构变化"
    return data["items"]


def _zone_table_from_app_js() -> dict[str, str]:
    """从 app.js 提取 ZONE_ICON_BY_WORDS（词集 → 文件），避免测试里再抄一份映射。"""
    js = _read(APP_JS)
    i = js.index("var ZONE_ICON_BY_WORDS = {")
    block = js[i:js.index("\n  };", i)]
    pairs = re.findall(r'"([^"]+)":\s*"assets/icons/zones/([^"]+)"', block)
    assert pairs, "ZONE_ICON_BY_WORDS 提取失败"
    return dict(pairs)


def _zone_key(zs: list[str]) -> str | None:
    """与 app.js zoneIconKey 完全一致（R295）：插板区只按覆盖体区投影成上胸/侧面，
    不追加「前插板」词；头部装备的 NeckFront/NeckBack 投影成喉部/后颈，
    护甲等非头部装备仍合并成脖颈。"""
    head_mode = bool(HEAD_CORE & set(zs))
    words: list[str] = []
    for z in zs:
        if z.startswith("Plate_"):
            r = z[len("Plate_"):]
            # 与 app.js zoneWord 一致：侧插板→侧面，前/后插板→上胸，其他 Plate 类型不投影
            if "side" in r:
                w = "侧面"
            elif "chest" in r or r.endswith("_back"):
                w = "上胸"
            else:
                w = None
        elif z == "NeckFront":
            w = "喉部" if head_mode else "脖颈"
        elif z == "NeckBack":
            w = "后颈" if head_mode else "脖颈"
        else:
            w = ZONE_WORDS.get(z)
        if w and w not in words:
            words.append(w)
    if not words:
        return None
    return "|".join(w for w in ZONE_WORD_ORDER if w in words)


def _cat_items() -> dict[str, list[tuple[str, dict]]]:
    """与 app.js inRootSlot 同口径的三类候选：armor/rig 按 slot，helmet 按 cat。"""
    items = _items_data()
    return {
        "armor": [(i, r) for i, r in items.items() if r.get("slot") == "armor"],
        "rig": [(i, r) for i, r in items.items() if r.get("slot") == "rig"],
        "helmet": [(i, r) for i, r in items.items() if r.get("cat") == "helmet"],
    }


# ------------------------------------------------ 1. 防护区域图标映射全覆盖
def test_r11_zone_mapping_covers_all_valid_zones():
    """三类装备中所有有 z 数据的组合都必须命中映射条目（含关键组合抽查），一件不许漏。"""
    table = _zone_table_from_app_js()
    for combo in KEY_COMBOS:
        assert combo in table, "关键组合未挂进 ZONE_ICON_BY_WORDS：%s" % combo
        assert table[combo] == KEY_COMBOS[combo]
    for cat, pairs in _cat_items().items():
        miss = []
        for iid, rec in pairs:
            zs = rec.get("z") or []
            if not zs:
                continue                      # 原始无 z：不伪造图标，单测单独核对
            key = _zone_key(zs)
            if key not in table:
                miss.append((iid, rec.get("n"), key))
        assert not miss, "%s 类仍有组合未映射：%s" % (cat, miss[:5])


def test_r11_zone_icon_files_state():
    """R79：37 张映射图标（头 24 + 躯干 13，无前插板叠层）全部随仓库打包，
    必须真实存在于磁盘；审计 JSON 的 pending_user_icons 应为空（按数据自动拼合，不再有静默缺图）。"""
    table = _zone_table_from_app_js()
    # 全部映射文件都必须在磁盘上（无运行期缺图回退）
    for combo, fname in table.items():
        f = ZONES_DIR / fname
        assert f.is_file(), "映射表里的图标文件缺失：%s（组合 %s）" % (fname, combo)
    # R31.4：未穿护甲的人形轮廓底图必须随仓库打包，且**不属于任何词组合**（不进映射表）
    assert (ZONES_DIR / "zone-base.png").is_file(), "缺少未穿护甲底图 zone-base.png"
    assert "zone-base.png" not in set(table.values()), "zone-base.png 不应作为词组合条目"
    # 审计 JSON 与映射表一致：全部入库 → 无 pending（R295 头部重做后条目 25+13=38）
    audit = json.loads(_read(AUDIT_JSON))
    assert audit.get("pending_user_icons") == [], "审计 JSON 不应再有待补图标（组合图已按数据自动生成）"
    assert len(table) >= 37, "映射条目数不应少于 37（R295 应为 38），实际 %d" % len(table)
    for cat, rep in audit["categories"].items():
        assert rep["unmapped_combo"] == 0, "%s 类审计仍存在未映射组合" % cat


def test_r11_no_zone_items_are_legit():
    """R79：普通弹挂仍无 z、不得伪造图标；破碎面具已由 game-truth 的 armorColliders 补齐（含眼部）。"""
    items = _items_data()
    plain = items.get(ID_PLAIN_RIG)
    assert plain and not (plain.get("z") or []), "BlackRock 胸挂应有 z 为空（普通弹挂）"
    assert not plain.get("cl"), "普通弹挂不应有本体防弹等级：%r" % plain.get("cl")
    mask = items.get(ID_BROKEN_MASK)
    assert mask and "Eyes" in (mask.get("z") or []), "破碎面具的眼部防护应由 game-truth 补齐"
    rig_no_zone = [i for i, r in items.items()
                   if r.get("slot") == "rig" and not (r.get("z") or [])]
    assert len(rig_no_zone) == 46, "普通弹挂（无 z）件数变化，需复核审计口径：%d" % len(rig_no_zone)


# ------------------------------------------------ 2. 基础防弹等级（本体 cl）
def test_r11_base_class_field_semantics():
    """三类装备 cl 字段结构一致：出现即正整数；固定样本 6B43=6、PACA=2；未知不得伪造为 0。"""
    items = _items_data()
    for cat, pairs in _cat_items().items():
        bad = [(i, r.get("cl")) for i, r in pairs
               if r.get("cl") is not None
               and (not isinstance(r.get("cl"), int) or r["cl"] <= 0)]
        assert not bad, "%s 类 cl 字段出现非正整数（无法区分未知与 0 级）：%s" % (cat, bad[:5])
    assert items[ID_6B43]["cl"] == 6
    assert items[ID_PACA]["cl"] == 2
    assert items[ID_BROKEN_MASK].get("cl") in (None, 0) or isinstance(
        items[ID_BROKEN_MASK].get("cl"), int), "破碎面具 cl 结构异常"


def test_r11_base_armor_class_of_is_body_only():
    """baseArmorClassOf 只读本体 cl 且未知返回 null；不得复用 maxArmorClassOf（含插板）。"""
    js = _read(APP_JS)
    m = re.search(
        r"function baseArmorClassOf\(rec\) \{\s*"
        r"return \(rec && typeof rec\.cl === \"number\" && isFinite\(rec\.cl\) && rec\.cl > 0\)"
        r" \? rec\.cl : null;\s*\}", js)
    assert m, "baseArmorClassOf 实现与约定不符（必须只读本体 rec.cl，未知返回 null）"
    # 右侧列表与分组不得引用 maxArmorClassOf（那是左侧角标"本体+插板"口径）
    for anchor in ("baseClGroupRank", "baseClCol"):
        seg = js[js.index(anchor): js.index(anchor) + 2000]
        assert "maxArmorClassOf" not in seg, "%s 不得依赖 maxArmorClassOf" % anchor


# ------------------------------------------------ 3. 列装配与分组排序静态结构
def test_r11_armor_rig_21_columns():
    """armor/rig 属性列对齐参考站 db4（R22.0）：armor=插板+Material+Eff+内衬+Zone+Cap/SE/Slots；
    rig=参考站 Chest Rig 口径（Cap/SE/Slots，不再套护甲插板/内衬版式）。"""
    js = _read(APP_JS)
    # armor 装配链（参考站 Armor/Armored Rig 口径；获取方式独立列插在价格之前）
    m = re.search(r"cols = \[nameCol, penCol\]\.concat\(plateCols\)\s*"
                  r"\.concat\(\[matCol, effDurCol\]\)\.concat\(linerCols\)\s*"
                  r"\.concat\(\[zoneIcoCol, capCol, seCol, slotsCol, wCol, srcCol\]\);", js)
    assert m, "armor 列装配顺序与参考站不符"
    # rig 装配链（参考站 Chest Rig 口径；获取方式独立列插在价格之前）
    assert "cols = [nameCol, penCol, capCol, seCol, slotsCol, wCol, srcCol];" in js
    # rig 默认列宽 = Chest Rig 口径的键
    block = re.search(r"rig: \{([^}]+)\}", js[js.index("var LW_COL_DEFAULTS"):])
    keys = re.findall(r"([A-Za-z_]\w*): \d+", block.group(1))
    assert set(keys) >= {"n", "pen", "cap", "se", "slots", "w", "srcGroup"}, \
        "rig 默认列宽缺 Chest Rig 口径的键：%s" % keys


def test_r11_helmet_column_set():
    """头盔列集对齐参考站 db4（R22.0）：名称→减益→Material→Eff→防护区域→重量→价格。
    参考站头盔无独立护甲等级/基础防弹等级列（用分组承载），故不再单列 cl/baseCl。"""
    js = _read(APP_JS)
    i = js.index('} else if (rootKey === "helmet") {')
    seg = js[i:js.index("} else {", i)]
    assert "matCol" in seg and "effDurCol" in seg and "helmetZoneCol" in seg, \
        "头盔列集应对齐参考站（Material / Eff / 防护区域）"
    assert "expandCol" in seg and "deafCol" in seg, \
        "头盔列集应含跳弹角（expandCol）与听力衰减（deafCol），对齐参考站 Expand/Deafening"
    assert "clCol" not in seg and "baseClCol" not in seg, \
        "头盔不再单列护甲等级/基础防弹等级（参考站用分组承载）"
    # helmetZoneCol：图标优先（renderZoneIconCell allowText=true），与 zoneIcoCol 同一映射
    mz = re.search(r"var helmetZoneCol = \{[\s\S]*?render: function \(cell, row\) "
                   r"\{ renderZoneIconCell\(cell, row, true\); \}", js)
    assert mz, "helmetZoneCol 必须复用 renderZoneIconCell（true=允许文字降级）"
    mz2 = re.search(r"render: function \(cell, row\) \{ renderZoneIconCell\(cell, row, false\); \}",
                    js[js.index("var zoneIcoCol"): js.index("var zoneIcoCol") + 400])
    assert mz2, "zoneIcoCol 必须复用 renderZoneIconCell（false=不显示文字）"


def test_r11_grouped_sorting_structure():
    """createTable.sorted() 以 groupOf 为固定主序（不受排序方向影响）；仅 armor/rig/helmet 分组。"""
    js = _read(APP_JS)
    s = js.index("function sorted(rows)")
    seg = js[s: js.index("—— DOM 壳 ——")]
    assert "opts.groupOf" in seg, "sorted() 未接入分组比较器"
    gi = seg.index("if (opts.groupOf)")
    # R20.6 引入虚拟排序键后，va 的声明被拆为「var va, vb, numeric;」+ 条件赋值；
    # 这里锚定拆分后的「va = col.sortValue」（位于组序比较块之后），保持意图不变。
    di = seg.index("va = col.sortValue")
    assert gi < di, "组序比较必须先于用户排序列比较（组序为固定主序）"
    assert "(ga < gb) ? -1 : 1" in seg, "组序比较不得乘排序方向"
    # gear 表挂动态 groupOf；组序规则：已知 -cl（6→1），未知 1e9 排最后，其他类别 0
    assert "groupOf: function (row) { return baseClGroupRank(currentNode(), row); }" in js
    m = re.search(r"function baseClGroupRank\(node, row\) \{[\s\S]*?\n  \}", js)
    body = m.group(0)
    assert '"armor" && k !== "rig" && k !== "helmet"' in body.replace("\n", " "), \
        "分组只允许 armor/rig/helmet 三类"
    assert "1e9" in body, "未知等级组必须固定排最后（1e9）"
    assert "return -row.baseCl" in body, "已知等级组序应为 -cl（升序 → 6→1）"


def test_r11_iconize_pending_jobs_registered():
    """躯干组合图仍由 iconize.py 登记复制；R295 头部改由手绘脚本直出 assets。"""
    src = _read(ICONIZE_PY)
    i = src.index("ZONE_JOBS = [")
    block = src[i:src.index("\n]", i)]
    jobs = re.findall(r'\("([^"]+)"\s*,\s*"([^"]+)\.png"\s*,\s*"([^"]+)\.png"\s*,\s*\[([^\]]*)\]\)', block)
    dsts = {j[2] + ".png" for j in jobs}
    for fname in [
        "zone-chest.png", "zone-chest-side.png", "zone-chest-abdomen-side.png",
        "zone-chest-abdomen-side-groin-neck-shoulder.png",
        "zone-neck.png",
    ]:
        assert fname in dsts, "iconize.py 缺少复制任务：%s" % fname
    assert "ZONE_STAGE" in src, "iconize.py 应从组件化生成暂存目录复制"

    # R295：头部手绘图的真正不变量是「映射表指向的文件必须在盘上」
    table = _zone_table_from_app_js()
    heads = {k: v for k, v in table.items() if v.startswith("zone-head-")}
    assert len(heads) >= 25, "头部组合映射不足：%d" % len(heads)
    for key, fname in heads.items():
        assert (ZONES_DIR / fname).is_file(), "头部映射指向的文件不存在：%s → %s" % (key, fname)


def test_r11_other_categories_column_defaults_untouched():
    """非目标类别的默认列宽不受本轮影响（backpack/headphones/glasses/face/plate 抽查键集）。"""
    js = _read(APP_JS)
    defaults = js[js.index("var LW_COL_DEFAULTS"): js.index("gun: {")]
    for cat, must in {
        "backpack": ["n", "conflict", "pen", "size", "cap", "glExcl", "slots", "w", "srcGroup"],
        "glasses": ["n", "cl", "pen", "w", "srcGroup"],   # glasses 保留 cl 列
        "plate": ["cl", "zoneText"],                               # 插板弹窗列集不变
    }.items():
        block = re.search(r"%s: \{([^}]+)\}" % cat, defaults).group(1)
        keys = re.findall(r"([A-Za-z_]\w*): \d+", block)
        for k in must:
            assert k in keys, "%s 类默认列宽缺 %s（不应被本轮改动）" % (cat, k)
