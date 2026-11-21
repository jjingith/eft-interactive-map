# -*- coding: utf-8 -*-
"""R298：防护区域图配色拉开对比 + 装上配件后合并显示。

问题 1：底图(128 灰)与部位(189 灰)在深色界面上几乎分不清。
处理：底图染冷灰并压到 38% 透明，部位染暖金 (234,184,92)，两者亮度差 > 60。

问题 2：头盔装面罩/护颚/护颈后，防护区域图不变。
处理：`loadoutZones(slotKey)` 合并「本体 z + 已装子配件 z」，
左栏装饰图与「当前装备行」都用它；并预生成所有本体+配件组合图。
"""
from __future__ import annotations

import itertools
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_JS = ROOT / "app.js"
GEN = ROOT / "tools" / "gen_zone_head_handraw.py"
ITEMS = ROOT / "data" / "items.json"
ZONES = ROOT / "assets" / "icons" / "zones"

HEAD_ORDER = ["头顶", "后脑", "面部", "下颚", "眼部", "耳部", "喉部", "后颈"]
HEAD_CORE = {"ParietalHead", "BackHead", "HeadCommon", "Jaw", "Eyes", "Ears"}
HEAD_WORDS = {"ParietalHead": "头顶", "BackHead": "后脑", "HeadCommon": "面部",
              "Jaw": "下颚", "Eyes": "眼部", "Ears": "耳部"}
NECK_WORDS = {"NeckFront": "喉部", "NeckBack": "后颈"}


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def mapping() -> dict[str, str]:
    js = read(APP_JS)
    i = js.index("var ZONE_ICON_BY_WORDS = {")
    block = js[i:js.index("\n  };", i)]
    return dict(re.findall(r'"([^"]+)":\s*"assets/icons/zones/([^"]+)"', block))


def head_key(zs) -> str | None:
    raw = set(zs or [])
    if not (raw & HEAD_CORE):
        return None
    words = []
    for z in raw:
        w = HEAD_WORDS.get(z) or NECK_WORDS.get(z)
        if w and w not in words:
            words.append(w)
    return "|".join(w for w in HEAD_ORDER if w in words) if words else None


# ---------------------------------------------------------------- 配色
def test_tint_contrast_is_enough():
    src = read(GEN)
    assert "ZONE_TINT = (234, 184, 92)" in src, "部位应为暖金色"
    assert "BASE_TINT = (116, 122, 132)" in src, "底图应为冷灰"
    assert "BASE_ALPHA = 0.38" in src
    assert "def colorize(" in src and "def solid_tint(" in src

    def luma(c):
        return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]
    zone = luma((234, 184, 92))
    base = luma((116, 122, 132))
    assert zone - base >= 50, "部位与底图亮度差不足：%.1f" % (zone - base)


# ---------------------------------------------------------------- 合并逻辑
def test_loadout_zones_merges_attachments():
    js = read(APP_JS)
    assert "function loadoutZones(slotKey)" in js
    # 子槽 key 规则必须与 buildSlotTree 一致
    assert 'var kid = slotKey + "/" + (s.id || s.sid || s.label || "slot");' in js
    assert 'var rec = itemRec(state.loadout[slotKey] || "");' in js
    # 左栏装饰图用合并结果
    assert "var zones = loadoutZones(slotKey);" in js
    assert "var exact = zoneIconFile(zones);" in js
    # 表格「当前装备行」用合并结果，其它候选行仍用本体
    assert "var mergedZones = loadoutZones(rootKey);" in js
    assert "zoneIcon: zoneIconFile(rowZones)" in js
    assert "zoneHasAttach: rowZones !== rec.z" in js


def test_current_helmet_row_marks_attachment_in_tooltip():
    js = read(APP_JS)
    assert 'row.zoneHasAttach ? "含已装配件 · " : ""' in js


# ---------------------------------------------------------------- 数据覆盖
def test_every_helmet_attachment_combo_has_icon():
    items = json.loads(read(ITEMS))["items"]
    table = mapping()
    missing = []
    checked = 0
    for iid, it in items.items():
        if (it.get("pt") or "") != "Helmet":
            continue
        own = it.get("z") or []
        if not (set(own) & HEAD_CORE):
            continue
        slots = []
        for s in (it.get("slots") or []):
            slots.append([None] + [c for c in (s.get("allow") or []) if c in items])
        if not slots:
            continue
        for pick in itertools.product(*slots):
            merged = list(own)
            for cid in pick:
                if cid:
                    merged.extend(items[cid].get("z") or [])
            key = head_key(merged)
            if not key:
                continue
            checked += 1
            if key not in table:
                missing.append((it.get("n"), key))
    assert checked > 0, "没有扫描到任何头盔-配件组合"
    assert not missing, "以下「本体+配件」组合没有图：%s" % missing[:5]


def test_all_mapped_head_icons_exist():
    table = mapping()
    heads = {k: v for k, v in table.items() if v.startswith("zone-head-")}
    assert len(heads) >= 36, "头部组合应至少 36 种（25 本体 + 11 配件合并），实际 %d" % len(heads)
    for key, fname in heads.items():
        assert (ZONES / fname).is_file(), "映射指向的文件不存在：%s → %s" % (key, fname)
