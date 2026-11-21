# -*- coding: utf-8 -*-
"""R19.8e：全量切换 tarkovgunsmith Ballistics.cs 后，真实弹种 × 护甲数值回归。

公式（combat_sim.js R62，0.13.x 客户端反编译原文）：
    穿透概率 = Ballistics.cs PenetrationChance（Desmos m8cmsfokkl）
    减伤 / 穿透伤害 = clamp(P / (FactorA + 12), 0.6, 1) × Damage
    FactorA = (121 − 5000/(45 + 2×耐久%)) × 等级 × 0.1
    未穿透钝伤 = BT% × median(0.2, 1 − 0.03×(FactorA − P), 1) × Damage
    护甲耐久伤害 = P × 甲伤% × 甲伤系数 × 材质毁损系数，最低 1 点；
        甲伤系数默认 decomp = P/(10×AC)（挡下 clamp 0.6–1.1，击穿 clamp 0.5–0.9）
    耐久%分母 = 出厂原始满耐久（站点为当前上限，差异已记录）。

数据来自本地 data/ammo.json 与 data/items.json（离线快照）：
    M80    pen 43 / dmg 80 / ard 67
    M995   pen 53 / dmg 42 / ard 52
    BT     pen 37 / dmg 54 / ard 44
    KITECO 6 级 UHMWPE 45 耐久 bt 0.26
    SAPI   5 级陶瓷 50 耐久 bt 0.30
"""
import json
import math
import os
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIM_JS = os.path.join(ROOT, "combat_sim.js")
TEST_JS = os.path.join(ROOT, "tests", "js", "combat_sim_r19_8_test.js")
AMMO = os.path.join(ROOT, "data", "ammo.json")
ITEMS = os.path.join(ROOT, "data", "items.json")

require_node = pytest.mark.skipif(shutil.which("node") is None, reason="node 不可用")


def _json(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="module")
def scen():
    out = subprocess.run(["node", TEST_JS, SIM_JS, ROOT],
                         capture_output=True, text=True, timeout=60, cwd=ROOT)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def js_round(v):
    """JS Math.round 语义（.5 向上）。"""
    return int(math.floor(v + 0.5))


def layer(case, i=0):
    return case[i]


def test_inputs_match_local_snapshot(scen):
    m = scen["meta"]
    assert (m["M80"]["pen"], m["M80"]["dmg"], m["M80"]["ard"]) == (43, 80, 67)
    assert (m["M995"]["pen"], m["M995"]["dmg"], m["M995"]["ard"]) == (53, 42, 52)
    assert (m["BT"]["pen"], m["BT"]["dmg"], m["BT"]["ard"]) == (37, 54, 44)
    assert (m["KITECO"]["cls"], m["KITECO"]["dur"], m["KITECO"]["mat"]) == (6, 45, "UHMWPE")
    assert m["KITECO"]["bt"] == pytest.approx(0.26)
    assert (m["SAPI"]["cls"], m["SAPI"]["dur"], m["SAPI"]["mat"]) == (5, 50, "Ceramic")
    assert m["SAPI"]["bt"] == pytest.approx(0.3)


def test_m80_vs_kiteco_unpenetrated_matches_hand_calc(scen):
    """decomp 甲伤系数 43/60=0.7167：43 × 0.67 × 0.3375 × 0.7167 ≈ 6.97 → 7。
    钝伤：80 × 0.26 × median(0.2, 1−0.03×(60.355−43), 1) = 80×0.26×0.47935 ≈ 9.97。"""
    L = layer(scen["M80_KITECO_unpen"])
    expect_base = 43 * (67 / 100.0) * 0.3375 * (43 / 60.0)
    assert L["durCoeff"] == pytest.approx(43 / 60.0, abs=1e-4)
    assert L["durMode"] == "decomp"
    assert L["durBase"] == pytest.approx(expect_base, abs=0.005)
    assert L["factorA"] == pytest.approx(60.355)
    assert L["durDmg"] == pytest.approx(expect_base, abs=0.005)   # R65：float 直减，无取整
    assert L["durBefore"] == 45 and L["durAfter"] == pytest.approx(45 - expect_base, abs=1e-9)
    assert L["penetrated"] is False
    assert L["bluntScale"] == pytest.approx(0.47935, abs=1e-4)
    assert L["blunt"] == pytest.approx(80 * 0.26 * 0.47935, abs=0.01)
    assert L["dmgToPart"] == pytest.approx(L["blunt"], abs=1e-9)
    assert L["durConfidence"] == "estimated"


def test_m80_vs_kiteco_penetrated_uses_pen_coefficient(scen):
    """击穿甲伤系数仍是 43/60=0.7167（不会因击穿而恒顶 0.9）：
    43 × 0.67 × 0.3375 × 0.7167 ≈ 6.97 → 7；
    减伤 clamp(43/(60.355+12)) = 0.6 下限 → 人体 80×0.6 = 48。"""
    L = layer(scen["M80_KITECO_pen"])
    expect_base = 43 * (67 / 100.0) * 0.3375 * (43 / 60.0)
    assert L["durCoeff"] == pytest.approx(43 / 60.0, abs=1e-4)
    assert L["durBase"] == pytest.approx(expect_base, abs=0.005)
    assert L["durDmg"] == pytest.approx(expect_base, abs=0.005)   # R65：float 直减
    assert L["durAfter"] == pytest.approx(45 - expect_base, abs=1e-9)
    assert L["penetrated"] is True
    assert L["penOut"] == pytest.approx(43 * 0.6, abs=0.01)
    assert L["dmgToPart"] == pytest.approx(80 * 0.6, abs=0.01)


def test_m995_vs_sapi_penetrated_matches_hand_calc(scen):
    """base = 53 × 0.52 × clamp(53/50, 0.5, 0.9)=0.9 × 0.6 ≈ 14.88 → 15；
    减伤 clamp(53/(50.296+12)) = 0.8508 → 人体 42×0.8508 ≈ 35.73。"""
    L = layer(scen["M995_SAPI_pen"])
    expect_base = 53 * (52 / 100.0) * 0.9 * 0.6
    assert L["durCoeff"] == pytest.approx(0.9)
    assert L["durBase"] == pytest.approx(expect_base, abs=0.005)
    assert L["factorA"] == pytest.approx(50.296)
    assert L["durDmg"] == pytest.approx(expect_base, abs=0.005)   # R65：float 直减
    assert L["durBefore"] == 50 and L["durAfter"] == pytest.approx(50 - expect_base, abs=1e-9)
    rf = max(0.6, min(1.0, 53 / (50.296 + 12)))
    assert L["dmgToPart"] == pytest.approx(42 * rf, abs=0.01)
    assert L["blunt"] == 0


def test_bt_vs_sapi_unpenetrated_matches_hand_calc(scen):
    """37/50=0.74：37 × 0.44 × 0.74 × 0.6 ≈ 7.23 → 7；
    钝伤 54 × 0.30 × median(...) = 54×0.3×0.60112 ≈ 9.74。"""
    L = layer(scen["BT_SAPI_unpen"])
    expect_base = 37 * (44 / 100.0) * (37 / 50.0) * 0.6
    assert L["durCoeff"] == pytest.approx(37 / 50.0)
    assert L["durBase"] == pytest.approx(expect_base, abs=0.005)
    assert L["durDmg"] == pytest.approx(expect_base, abs=0.005)   # R65：float 直减
    assert L["durBefore"] == 50 and L["durAfter"] == pytest.approx(50 - expect_base, abs=1e-9)
    assert L["penetrated"] is False
    assert L["bluntScale"] == pytest.approx(0.6011, abs=1e-4)
    assert L["blunt"] == pytest.approx(54 * 0.3 * 0.6011, abs=0.01)


def test_durability_does_not_change_armor_damage_in_decomp_mode(scen):
    """原文甲伤系数只看穿透力/等级，与耐久无关：满耐久与半耐久都是 0.7167、单发 7。
    （耐久只影响穿透概率与钝伤，不影响 DamageToArmor。）"""
    full = layer(scen["M80_KITECO_unpen"])
    half = layer(scen["M80_KITECO_half"])
    assert half["durCoeff"] == pytest.approx(43 / 60.0, abs=1e-4)
    assert half["durBase"] == pytest.approx(full["durBase"], abs=1e-9)
    assert half["durDmg"] == pytest.approx(full["durDmg"], abs=1e-9)
    assert half["factorA"] == pytest.approx(51.91)
    assert half["durBefore"] == 22.5 and half["durAfter"] == pytest.approx(22.5 - half["durDmg"], abs=1e-9)


def test_durability_damage_never_exceeds_remaining(scen):
    """3 耐久板吃一发公式值 ≈6.97：实际只扣 3，不会被记成 7。"""
    L = layer(scen["M80_KITECO_low"])
    assert L["durDmg"] == 3
    assert L["durBefore"] == 3 and L["durAfter"] == 0


def test_three_shots_keep_armor_damage_constant_but_blunt_rises(scen):
    """连续三发（全未穿）：45→38.03→31.06→24.09，单发甲伤都是 6.9684（与耐久无关）；
    R65 起耐久按浮点直减（不再每发取整），FactorA 60.355→58.583→56.212，
    钝伤 9.9704 → 11.0761 → 12.5558。"""
    shots = scen["M80_KITECO_3shots"]
    assert [s["durDmg"] for s in shots] == pytest.approx([6.96841875] * 3, abs=1e-6)
    assert [s["durAfter"] for s in shots] == pytest.approx([38.03158125, 31.0631625, 24.09474375], abs=1e-6)
    assert [s["factorA"] for s in shots] == pytest.approx([60.355, 58.583, 56.212], abs=0.01)
    assert [s["blunt"] for s in shots] == pytest.approx([9.9704, 11.0761, 12.5558], abs=0.01)


def test_new_formula_constants_and_no_legacy_scale():
    js = _read(SIM_JS)
    assert "CS.ARMOR_DMG_COEFF_MODE = 'decomp';" in js
    assert "CS.armorClassResistance = function" in js
    assert "CS.armorFactorA = function" in js
    assert "CS.armorReductionFactor = function" in js
    assert "CS.armorDamageCoeff = function" in js
    assert "CS.armorBluntScale = function" in js
    assert "CS.SOFT_LINER_PLATE_BLUNT_MUL = 0.6;" in js
    assert "ceramic: 0.6" in js
    # 旧口径仍保留为可选，但默认值必须是 decomp
    assert "mode === 'site'" in js and "mode === 'video'" in js
    assert "EST_PEN_DUR_FACTOR" not in js, "固定 0.7 已废止"
    assert "PEN_ARMOR_DMG_MIN" not in js, "66–75% 随机已废止"
    assert "armorDamageRoll" not in js, "66–75% 随机已废止"
    assert "EST_RESIST_BASE" not in js, "12.5 抵抗系数已废止"
    assert "EST_BLUNT_DUR_SLOPE" not in js, "钝伤耐久斜率 0.5 已废止"
    assert "EST_LAYER_PEN_LOSS" not in js, "固定 -1 穿透已废止"
    assert "EST_SOFT_BACKING_BLUNT" not in js, "软内衬 ×0.8 已废止"
    assert "EST_ARMOR_DMG_PEN_SCALE" not in js, "旧 0.012 标定式不得残留"
    assert "EST_UNPEN_NEAR_MUL" not in js and "EST_UNPEN_FAR_MUL" not in js
    assert "durBase = st.pen * ardPct * coeff * mat" in js
