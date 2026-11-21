# -*- coding: utf-8 -*-
"""R260：三件事。

用户反馈（2026-11-12）：
  ①「截图识别的价格模式默认跟随互动地图应用的模式，应用右上角选了 pve，
     截图识别就也是 pve」
  ②「有些不是物资名称的也会被误识别到，特别是弹匣和弹药包，或者药下面的
     xx/xx 非常容易被识别」
  ③「弹匣有些存在不同颜色的版本，异色的在跳蚤上特别贵（GEN M3 普通版 PvE
     ~4 万，却识别成 FDE 版 10 万）」
"""

import os
import sys
import tempfile

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TEST_DIR)
TOOLS = os.path.join(ROOT, "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import config  # noqa: E402
import ocr  # noqa: E402
import scan  # noqa: E402
import serve  # noqa: E402


# ============================================================ ① 模式跟随

def test_merge_ui_data_scope_persists():
    cfg = config.default_config()
    m = config.merge_ui(cfg, {"dataScope": {"mode": "pve"}})
    assert m["dataScope"]["mode"] == "pve"
    assert config.normalize(m)["dataScope"]["mode"] == "pve"


def test_data_scope_invalid_falls_back_regular():
    assert config.normalize({"dataScope": {"mode": "banana"}})["dataScope"]["mode"] == "regular"
    assert config.default_config()["dataScope"]["mode"] == "regular"


def test_current_mode_reads_config_data_scope():
    d = tempfile.mkdtemp()
    cfg = config.default_config()
    cfg["dataScope"] = {"mode": "pvps"}
    config.save(cfg, d)
    assert scan.current_mode(d) == "pvps"


def test_scan_resyncs_mode_each_hotkey():
    src = open(os.path.join(TOOLS, "scan.py"), encoding="utf-8").read()
    # 每次热键识别前重新读应用模式（默认跟随）
    assert "game_idx = game_mode_index(current_mode(config_dir))" in src


def test_game_mode_js_pushes_mode_to_server():
    js = open(os.path.join(ROOT, "js", "game-mode.js"), encoding="utf-8").read()
    assert "function pushMode" in js
    assert "api/prefs" in js and "dataScope" in js
    # set() 与启动各同步一次
    assert js.count("pushMode(") >= 3


# ============================================================ ② 误识别（计数/价格）

def test_looks_like_count_or_number_blocks_counts():
    for t in ("3/3", "30/30", "45.5/60", "53548", "53.548", "53,548",
              "3|3", "3l3", "3O/3O", "30 / 30"):
        assert ocr.looks_like_count_or_number(t), "应判为计数/价格：%r" % t


def test_looks_like_count_or_number_allows_item_names():
    for t in ("AKM", "9x19", "GEN M3", "布洛芬", "M855", "5.56x45", "", None):
        assert not ocr.looks_like_count_or_number(t), "不应误伤物品名：%r" % t


def test_resolve_key_rejects_counts_with_ocr_noise():
    m = ocr.ItemMatcher(["AKM 突击步枪", "GEN M3", "布洛芬"])
    for bad in ("3/3", "30/30", "45.5/60", "3l3", "3O/3O"):
        key, _path = m.resolve_key(bad)
        assert key is None, "计数被当物品名：%r → %s" % (bad, key)


def test_resolve_key_keeps_real_names():
    m = ocr.ItemMatcher(["AKM 突击步枪", "GEN M3", "布洛芬"])
    assert m.resolve_key("GEN M3")[0] is not None
    assert m.resolve_key("布洛芬")[0] is not None


# ============================================================ ③ 异色变体

def _cat(**kw):
    return kw


def test_prefer_base_variant_drops_bracketed():
    catalog = {
        "a": {"n": "Magpul PMAG 30 GEN M3 5.56x45 STANAG 30发弹匣"},
        "b": {"n": "Magpul PMAG 30 GEN M3 5.56x45 STANAG 30发弹匣 (FDE)"},
        "c": {"n": "Magpul PMAG 30 GEN M3 7.62x39 30 发 AK 弹匣（香蕉黄）"},
        "d": {"n": "Magpul PMAG 30 GEN M3 STANAG 30 发 BB 弹弹匣 (FDE)"},
    }
    kept = serve._ocr_prefer_base_variant(["a", "b", "c", "d"], catalog)
    assert kept == ["a"], "应只保留不带括号后缀的普通版本"


def test_prefer_base_variant_keeps_all_when_all_variants():
    catalog = {"b": {"n": "X (FDE)"}, "c": {"n": "Y（香蕉黄）"}}
    kept = serve._ocr_prefer_base_variant(["b", "c"], catalog)
    assert kept == ["b", "c"], "全是变体时原样返回"


def test_prefer_base_variant_single_id():
    assert serve._ocr_prefer_base_variant(["a"], {"a": {"n": "foo (FDE)"}}) == ["a"]


def test_variant_name_detection():
    assert serve._ocr_name_is_variant("PMAG (FDE)")
    assert serve._ocr_name_is_variant("弹匣（香蕉黄）")
    assert serve._ocr_name_is_variant("弹匣 [OD]")
    assert not serve._ocr_name_is_variant("Magpul PMAG 30 GEN M3 5.56x45 STANAG 30发弹匣")


def test_real_gen_m3_selection_excludes_variants():
    """真实数据：GEN M3 同名多版本，新版必须挑到不带括号的普通版（不再选 FDE/BB）。"""
    _names, n2i, catalog = serve._ocr_catalog(ROOT)
    ids = n2i.get("GEN M3") or []
    assert len(ids) > 3
    kept = serve._ocr_prefer_base_variant(ids, catalog)
    # 至少排除了几条带括号的异色/特殊版
    assert len(kept) < len(ids)
    for iid in kept:
        assert not serve._ocr_name_is_variant((catalog.get(iid) or {}).get("n"))
