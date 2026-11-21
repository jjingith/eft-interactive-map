# -*- coding: utf-8 -*-
"""R54 / R54b：护甲钝伤系数（BT%）落库与取证校验。

R54：gunsmith 反解 4 件（三档自洽）。
R54b：tarkov.dev 上游 armorSlots.bluntThroughput 覆盖剩余 5 件，并交叉校验反解结果。

只校验落库结果与取证文件，不联网；复算脚本见 tools/r54_armor_bt_invert.py
与 tools/r54b_upstream_bt.py。
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_JSON = os.path.join(ROOT, "data", "armor-bt.json")
EVIDENCE_JSON = os.path.join(ROOT, "docs", "r54-armor-bt-inversion-evidence.json")
UPSTREAM_JSON = os.path.join(ROOT, "docs", "r54b-upstream-bt-evidence.json")

INVERTED = {
    "5fd4c474dd870108a754b241": 0.26,
    "609e8540d5c319764c2bc2e9": 0.33,
    "60a283193cb70855c43a381d": 0.36,
    "68a89146212dbbeead0d5636": 0.33,
}
UPSTREAM = {
    "69cbfe44897389c1870b2337": 0.1314,
    "6a567ae55cbe811cbe0136a8": 0.1314,
    "6a568dda1d89fcfb35010389": 0.1548,
    "6a576f2105af50743903b74c": 0.33,
    "6a670ae11ab6ac490a0b9a99": 0.1548,
}
# R54 的 gunsmith 覆盖度差集（历史事实，不随 R54b 改变）
GUNSMITH_MISSING = list(UPSTREAM)


def load():
    with open(DATA_JSON, encoding="utf-8") as f:
        db = json.load(f)
    with open(EVIDENCE_JSON, encoding="utf-8") as f:
        ev = json.load(f)
    with open(UPSTREAM_JSON, encoding="utf-8") as f:
        up = json.load(f)
    return db["items"], ev, up


def test_inverted_entries_have_self_consistent_evidence():
    items, _, _ = load()
    for iid, bt in INVERTED.items():
        ent = items[iid]
        assert ent["btSource"] == "gunsmith-inverted"
        assert ent["bt"] == bt
        proof = ent["btEvidence"]
        assert proof["inverted"] == bt
        assert proof["selfConsistent"] is True
        assert proof["spread"] <= 5e-5
        assert len(proof["samples"]) == 3
        assert proof["ammoId"] == "56dff3afd2720bba668b4567"
        assert all(s["durability"] >= 1 and s["maxDurability"] >= 1 for s in proof["samples"])


def test_gunsmith_coverage_still_records_five_missing():
    _, ev, _ = load()
    assert set(ev["coverage"]["covered_ids"]) == set(INVERTED)
    assert set(ev["coverage"]["missing_ids"]) == set(GUNSMITH_MISSING)


def test_missing_entries_now_use_upstream_armor_slots():
    items, _, up = load()
    assert set(up["targets"]) == set(UPSTREAM)
    for iid, bt in UPSTREAM.items():
        ent = items[iid]
        assert ent["bt"] == bt
        assert ent["btSource"] == "tarkov.dev:armorSlots.bluntThroughput"
        # 兜底值保留但不再命中
        assert ent["btFallback"] == 0.18
        assert ent["btFallbackSource"] == "material-fallback"
        proof = ent["btEvidence"]
        assert proof["field"] == "properties.armorSlots[].bluntThroughput"
        assert proof["rootBluntThroughput"] == 0          # 根字段不可用，必须为 0
        assert proof["inverted"] == bt
        assert proof["slots"] and all(s["bluntThroughput"] == bt for s in proof["slots"])
        # 证据来源必须是本次实际抓到的上游快照
        assert up["targets"][iid]["effectiveBt"] == bt
        assert up["targets"][iid]["normalizedName"]
        assert up["targets"][iid]["localItemsJson"]["slotBts"] == [bt]


def test_no_entry_remains_material_fallback():
    items, _, _ = load()
    assert not [i for i, e in items.items() if e.get("btSource") == "material-fallback"]
    assert len(items) == 168


def test_upstream_crosscheck_of_inverted_values():
    items, _, up = load()
    ck = up["crossCheck"]
    assert set(ck) == set(INVERTED)
    for iid in ("609e8540d5c319764c2bc2e9", "60a283193cb70855c43a381d", "68a89146212dbbeead0d5636"):
        rec = ck[iid]
        assert rec["verdict"] == "match"
        assert rec["effectiveBt"] == INVERTED[iid]
        assert abs(rec["delta"]) < 0.01
    # Hexgrid 是纯插板背心，上游没有软甲槽 BT，无法用同一字段交叉校验
    hexgrid = ck["5fd4c474dd870108a754b241"]
    assert hexgrid["verdict"] == "no-upstream-slot-bt"
    assert hexgrid["effectiveBt"] is None
    assert [s["nameId"] for s in hexgrid["armorSlots"]] == []
