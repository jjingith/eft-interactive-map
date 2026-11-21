# -*- coding: utf-8 -*-
"""R62 golden：用真实 ammo/items 数据验证四条验收锚点。

(a) 甲伤比值不再恒顶上限：P44 打 2/3 级仍被 1.1 夹住，5 级降到 0.88、6 级 0.733；
    旧 site 口径在 2–6 级全部恒为 1.1（对照列保留）。
(b) 跳弹 ÷2 且扣耐久：见 test_r19_8_ricochet.py（头盔与插板都断言）。
(c) 正态浮动可复现：见 test_r19_8b_rules.py::test_penetration_jitter_is_normal_and_seeded。
(d) 三个实弹锚点：
    - 用户视频 8→1 那组：.308 ME LOKT + Altyn 5 级面罩 10% 耐久 + 2 级面罩（H1 口径）
    - 5.56 M855A1 打 4 级 6B23-2 钢插板满耐久
    - 5.56 M995 打 5 级 SAPI 陶瓷插板满耐久

所有输入来自 data/ammo.json / data/items.json 离线快照；节点脚本见
tests/js/combat_sim_r62_golden.js。
"""
import json
import os
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIM_JS = os.path.join(ROOT, "combat_sim.js")
TEST_JS = os.path.join(ROOT, "tests", "js", "combat_sim_r62_golden.js")

require_node = pytest.mark.skipif(shutil.which("node") is None, reason="node 不可用")


@pytest.fixture(scope="module")
def golden():
    out = subprocess.run(["node", TEST_JS, SIM_JS], capture_output=True, text=True,
                         timeout=60, cwd=ROOT)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def _layer(rec):
    return rec["layers"][0]


@require_node
def test_a_armor_ratio_no_longer_plateaus(golden):
    rows = {r["cls"]: r for r in golden["ratio"]}
    assert rows[2]["decomp"] == pytest.approx(1.1)
    assert rows[5]["decomp"] == pytest.approx(0.88)
    assert rows[6]["decomp"] == pytest.approx(0.7333, abs=1e-4)
    assert rows[5]["decomp"] < rows[4]["decomp"]           # 5 级开始离开上限
    # 旧 site 口径对照：2–6 级全部恒顶 1.1（这正是 R62 要修的“恒顶上限”）
    assert [r["site"] for r in golden["ratio"]] == [pytest.approx(1.1)] * 5


@require_node
def test_d1_m855a1_vs_class4_6b23_2(golden):
    """P44/40=1.1 → 击穿侧夹到 0.9；钢 0.525：
    甲伤 = 44×0.47×0.9×0.525 = 9.7713（R65 float 直减；界面显示 10）；40→30.2287。
    减伤 clamp(44/(40.237+12)) = 0.8423；人体 49×0.8423 = 41.27。"""
    rec = golden["m855a1_class4"]
    L = _layer(rec)
    assert golden["meta"]["M855A1"]["pen"] == 44
    assert L["cls"] == 4 and L["durBefore"] == 40
    assert L["durCoeff"] == pytest.approx(0.9)
    assert L["durBase"] == pytest.approx(9.77, abs=0.01)
    assert L["durDmg"] == pytest.approx(9.7713, abs=1e-3)
    assert L["durAfter"] == pytest.approx(30.2287, abs=1e-3)
    assert L["reduceFactor"] == pytest.approx(0.8423, abs=1e-4)
    assert rec["dmgToPart"] == pytest.approx(41.27, abs=0.02)
    assert rec["penetrated"] is True


@require_node
def test_d2_m995_vs_class5_sapi(golden):
    """P53/50=1.06 → 击穿侧 0.9；陶瓷 0.6：
    甲伤 = 53×0.52×0.9×0.6 = 14.8824（R65 float 直减；显示 15）；50→35.1176。
    减伤 clamp(53/(50.296+12)) = 0.8508；人体 42×0.8508 = 35.73。"""
    rec = golden["m995_class5"]
    L = _layer(rec)
    assert golden["meta"]["M995"]["pen"] == 53
    assert L["cls"] == 5 and L["durBefore"] == 50
    assert L["durCoeff"] == pytest.approx(0.9)
    assert L["durBase"] == pytest.approx(14.88, abs=0.01)
    assert L["durDmg"] == pytest.approx(14.8824, abs=1e-3)
    assert L["durAfter"] == pytest.approx(35.1176, abs=1e-3)
    assert L["reduceFactor"] == pytest.approx(0.8508, abs=1e-4)
    assert rec["dmgToPart"] == pytest.approx(35.73, abs=0.02)
    assert rec["penetrated"] is True


@require_node
def test_d3_video_anchor_8_to_1_keeps_h1(golden):
    """用户视频锚点：第一层钝伤 7.6032（界面显示 8），
    第二层 H1 = 7.6032 × 9.9% × scale1 = 0.7527（界面显示 1）。
    若换成站点 H4 会得到 6.0586（显示 6），与本工具默认口径不一致，已在「关于」注明。"""
    rec = golden["video8to1"]
    first, second = rec["layers"]
    assert golden["meta"]["ME308"]["pen"] == 24
    assert first["blunt"] == pytest.approx(7.6032, abs=1e-4)
    assert round(first["blunt"]) == 8
    assert second["blunt"] == pytest.approx(0.7527, abs=1e-4)
    assert round(second["blunt"]) == 1
    assert rec["dmgToPart"] == pytest.approx(0.7527, abs=1e-4)
    # R62 甲伤公式同时生效：第一层 24×0.55×0.6×0.375=2.97（R65 float 直减；显示 3），5→2.03
    assert first["durDmg"] == pytest.approx(2.97, abs=1e-6)
    assert first["durCoeff"] == pytest.approx(0.6)
