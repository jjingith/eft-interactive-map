# -*- coding: utf-8 -*-
"""R62：按 0.13.x 反编译原文重写后的回归。

覆盖：穿透概率/原始满耐久、正态穿透浮动 N(P, σ)（旧 ±1 仅显式调试）、
减伤 clamp(P/(FactorA+12))、多层 P/D 同比衰减、钝伤 median 公式、
插板+内衬 ×0.6、内衬耐久×插板击穿概率、decomp 甲伤系数（旧 site/video 仍可选）、
材质 Ceramic=0.6（globals 真值）。
"""
import json
import os
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIM_JS = os.path.join(ROOT, "combat_sim.js")
BRIDGE = os.path.join(ROOT, "tests", "js", "combat_sim_r19_8b_test.js")

require_node = pytest.mark.skipif(shutil.which("node") is None, reason="node 不可用")


@pytest.fixture(scope="module")
def out():
    r = subprocess.run(["node", BRIDGE, SIM_JS], capture_output=True, text=True, timeout=60, cwd=ROOT)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_new_formula_constants(out):
    c = out["consts"]
    assert c["mode"] == "decomp"                     # 默认按反编译原文
    assert c["matCeramic"] == pytest.approx(0.6)     # globals ArmorMaterials 真值
    assert c["matGlass"] == pytest.approx(0.6)
    assert c["linerMul"] == pytest.approx(0.6)
    assert c["throughMin"] == pytest.approx(0.6)
    assert c["videoCap"] == pytest.approx(1.2)       # 仅旧 video 模式使用
    assert c["res0"] == pytest.approx(1)             # 0 级 Resistance=1
    assert c["res5"] == pytest.approx(50)            # 5 级 Resistance=50


def test_armor_damage_coefficient_decomp_and_legacy(out):
    """decomp=P/(10×AC)：20/4 → 0.5；击穿侧 0.5，挡下侧夹到 0.6；
    2/6 → 0.333 → 挡下夹到 0.6；100/4=2.5 → 挡下夹到 1.1（不会 1.2）。
    旧 site=(P/AC)*10 恒顶格；video=P/(AC*10) 保留 1.2 上限（仅供对照）。"""
    c = out["coeffCases"]
    assert c["decompBlock20_4"] == pytest.approx(0.6)
    assert c["decompPen20_4"] == pytest.approx(0.5)
    assert c["decompLowBlock2_6"] == pytest.approx(0.6)
    assert c["decompHighBlock100_4"] == pytest.approx(1.1)
    assert c["siteBlock"] == pytest.approx(1.1)
    assert c["sitePen"] == pytest.approx(0.9)
    assert c["siteLowBlock"] == pytest.approx(1.1)      # 低穿也会被顶到 1.1
    assert c["videoBlock"] == pytest.approx(0.6)
    assert c["videoPen"] == pytest.approx(0.5)
    assert c["videoHighBlock"] == pytest.approx(1.2)


def test_desmos_original_max_30_60_equals_30_30(out):
    a = out["penEqual"]["a"]
    b = out["penEqual"]["b"]
    assert a["penBase"] == 47
    assert a["layers"][0]["chance"] == pytest.approx(0.9417396879675144)
    assert b["layers"][0]["chance"] == pytest.approx(a["layers"][0]["chance"])
    assert a["layers"][0]["factorA"] == pytest.approx(43.259)
    assert a["layers"][0]["durDmg"] == b["layers"][0]["durDmg"]
    assert a["layers"][0]["penOut"] == pytest.approx(b["layers"][0]["penOut"])


def test_damage_reduction_scales_with_durability(out):
    """clamp(P/(FactorA+12), 0.6, 1)：满耐久 4 级 FactorA=40.237 → 0.7657；
    半耐久 FactorA=34.607 → 0.8582。P、D 同乘该系数。"""
    f = out["reduceFull"]["layers"][0]
    h = out["reduceHalf"]["layers"][0]
    assert f["factorA"] == pytest.approx(40.237)
    assert f["reduceFactor"] == pytest.approx(0.7657, abs=1e-4)
    assert h["factorA"] == pytest.approx(34.607)
    assert h["reduceFactor"] == pytest.approx(0.8582, abs=1e-4)
    assert out["reduceFull"]["dmgToPart"] == pytest.approx(50 * 0.7657, abs=0.01)
    assert out["reduceHalf"]["dmgToPart"] == pytest.approx(50 * 0.8582, abs=0.01)
    assert f["penOut"] == pytest.approx(40 * 0.7657, abs=0.01)
    assert h["penOut"] == pytest.approx(40 * 0.8582, abs=0.01)


def test_penetration_jitter_is_normal_and_seeded(out):
    """R62：默认正态 N(P, σ)。测试弹未带 penDev → 降级 σ=1（来源标注）。
    固定种子完全可复现；不同种子结果不同。旧 ±1 均匀只能在 'uniform' 下显式复现。"""
    a = out["jitterA"]
    a2 = out["jitterA2"]
    b = out["jitterB"]
    assert a["penBase"] == 43
    assert a["penJitterMode"] == "normal"
    assert a["penDev"] == pytest.approx(1.0)
    assert a["penDevSource"] == "fallback-sigma1"   # 无官方 σ 的降级路径
    assert a["penUsed"] == pytest.approx(a2["penUsed"])     # 固定种子可复现
    assert a["penRoll"] == pytest.approx(a2["penRoll"])
    assert abs(a["penUsed"] - b["penUsed"]) > 0.1           # 不同种子不同浮动

    dev = out["jitterDev"]
    assert dev["penDev"] == pytest.approx(1.375)            # M855A1 官方 σ
    assert dev["penDevSource"] == "game-truth"
    assert dev["penUsed"] == pytest.approx(43 + dev["penRoll"], abs=1e-3)

    uni = out["jitterUniform"]
    assert uni["penJitterMode"] == "uniform"
    assert uni["penDevSource"] == "legacy-uniform"
    assert -1 <= uni["penRoll"] <= 1


def test_multilayer_blunt_chains_8_to_1_44(out):
    """R19.8f：第一层挡下的 8 点继续送入二级面罩，按二级面罩 BT 0.18×缩放 1
    再衰减一次 → 1.44；最终人体只吃最后输出（用户实测约 1–1.5）。"""
    s = out["bluntMulti"]
    L1, L2 = s["layers"][0], s["layers"][1]
    assert L1["bluntOut"] == pytest.approx(8)
    assert L1["bluntFactor"] == pytest.approx(0.08)
    assert L2["bluntIn"] == pytest.approx(8)
    assert L2["bluntFactor"] == pytest.approx(0.18)
    assert L2["bluntOut"] == pytest.approx(1.44)
    assert L2["blunt"] == pytest.approx(1.44)
    assert s["dmgToPart"] == pytest.approx(1.44)
    assert 1.0 <= s["dmgToPart"] <= 1.5


def test_low_pen_blunt_hits_median_floor_then_chains(out):
    """单层缩放项下限 0.2：8 → 1.6；后继面罩（R65）只按自身 BT 0.18 衰减，
    不再套自己的 0.2 下限/缩放项 → 1.6×0.18 = 0.288。"""
    hi = out["bluntMulti"]["layers"][0]
    lo = out["bluntMultiLow"]["layers"][0]
    lo2 = out["bluntMultiLow"]["layers"][1]
    assert lo["bluntScale"] == pytest.approx(0.2)
    assert lo["bluntBase"] == pytest.approx(8 * 0.2)
    assert lo["blunt"] == pytest.approx(1.6)
    assert lo["blunt"] < hi["blunt"]
    assert lo2["bluntIn"] == pytest.approx(1.6)
    assert "bluntScale" not in lo2                 # R65：后继层不判穿透、不套缩放项
    assert lo2["bluntFactor"] == pytest.approx(0.18)
    assert lo2["bluntOut"] == pytest.approx(1.6 * 0.18, abs=1e-6)
    assert out["bluntMultiLow"]["dmgToPart"] == pytest.approx(lo2["bluntOut"])


def test_three_layers_blunt_chains(out):
    """三层连续衰减：8 → 1.44 → 0.2592，每层都用自身 BT × 缩放项。"""
    s = out["bluntThree"]
    L1, L2, L3 = s["layers"]
    assert L1["bluntOut"] == pytest.approx(8)
    assert L2["bluntIn"] == pytest.approx(8)
    assert L2["bluntOut"] == pytest.approx(1.44)
    assert L3["bluntIn"] == pytest.approx(1.44)
    assert L3["bluntOut"] == pytest.approx(0.2592, abs=1e-6)
    assert s["dmgToPart"] == pytest.approx(0.2592, abs=1e-6)


def test_penetrated_second_layer_does_not_terminate_chain(out):
    """R65 原文：层 1 挡下后，层 2 不再判穿透（原文 flag 短路），只做 Damage ×= 自身 BT；
    无 chance/roll、不算甲伤、不扣耐久。现场景层 2 的 penChanceFn 恒 1，也必须被短路。"""
    s = out["bluntSecondPen"]
    L1, L2 = s["layers"]
    assert L1["penetrated"] is False and L1["bluntOut"] == pytest.approx(19.8935, abs=1e-3)
    assert L2["afterBlock"] is True
    assert L2["penetrated"] is False and L2["blocked"] is True
    assert L2["chance"] is None and L2["roll"] is None
    assert L2["durDmg"] == 0 and L2["durAfter"] == L2["durBefore"]
    assert L2["bluntFactor"] == pytest.approx(0.18)
    assert L2["bluntIn"] == pytest.approx(L1["bluntOut"])
    assert L2["bluntOut"] == pytest.approx(L1["bluntOut"] * 0.18, abs=1e-6)
    assert s["dmgToPart"] == pytest.approx(L2["bluntOut"])
    assert s["stoppedBy"] == "armor" and s["penetrated"] is False


def test_blunt_scale_formula_bounds(out):
    """5 级满耐久 FactorA=50.296：P 0/5/20 都触底 0.2；P 50 → 0.9911；P 60 → 1。
    5 级板 bt 0.30 / dmg 100 / 无内衬 → 钝伤 6 / 6 / 6 / 29.73 / 30。"""
    cases = out["bluntF"]
    assert [c["layers"][0]["bluntScale"] for c in cases] == pytest.approx(
        [0.2, 0.2, 0.2, 0.9911, 1], abs=1e-4)
    assert [c["layers"][0]["blunt"] for c in cases] == pytest.approx(
        [6, 6, 6, 29.73, 30], abs=0.01)
    assert cases[0]["layers"][0]["blunt"] == pytest.approx(6)   # 下限不是 0
    assert cases[4]["layers"][0]["bluntScale"] == pytest.approx(1)


def test_soft_liner_reduces_plate_blunt_then_chains(out):
    """R65：0.12 的插板 ×0.6 默认停用（0.13 由后继层自身 BT 承担）；
    插板钝伤 30 原样进入内衬，内衬只乘自身 BT 0.18 → 5.4，不再有二次扣减。"""
    s = out["bluntSoft"]
    plate, liner = s["layers"][0], s["layers"][1]
    solo = out["bluntPlateOnly"]["layers"][0]
    assert plate["bluntScale"] == pytest.approx(1)
    assert plate["bluntBase"] == pytest.approx(30)          # 100 dmg × 0.30 陶瓷板
    assert plate["bluntOut"] == pytest.approx(30)
    assert plate.get("softBacking") is not True             # 默认停用
    assert plate["bluntLayers"] == []
    assert liner["bluntIn"] == pytest.approx(30)
    assert liner["bluntFactor"] == pytest.approx(0.18)
    assert liner["bluntOut"] == pytest.approx(5.4)
    assert s["dmgToPart"] == pytest.approx(5.4)
    assert solo["blunt"] == pytest.approx(30)
    assert plate["bluntOut"] == pytest.approx(solo["blunt"])


def test_multilayer_penetration_scales_pen_and_damage(out):
    """板穿透后 P=20→12、D=100→60（都乘 0.6）；内衬被挡：钝伤 8.17、
    内衬耐久伤害 = 公式值 1 点 × 板的击穿概率 0.8 = 0.8。
    板甲伤：20×0.5×clamp(20/40)=0.5×0.525≈2.63 → 3；
    内衬：12×0.5×clamp(12/20)=0.6×0.1875≈0.675 → 1。"""
    s = out["multiPen"]
    plate, liner = s["layers"][0], s["layers"][1]
    assert plate["penIn"] == 20 and plate["dmgIn"] == 100
    assert plate["reduceFactor"] == pytest.approx(0.6)
    assert plate["penOut"] == pytest.approx(12)
    assert plate["dmgOut"] == pytest.approx(60)
    assert plate["durCoeff"] == pytest.approx(0.5)
    assert plate["durDmg"] == pytest.approx(2.625, abs=1e-6)   # R65：float 直减，展示层才取整
    assert liner["penIn"] == pytest.approx(12) and liner["dmgIn"] == pytest.approx(60)
    assert liner["bluntScale"] == pytest.approx(0.7564, abs=1e-4)
    assert liner["blunt"] == pytest.approx(8.17, abs=0.01)
    assert liner["linerDurScale"] == pytest.approx(0.8)
    assert liner["durCoeff"] == pytest.approx(0.6)
    assert liner["durDmg"] == pytest.approx(0.8, abs=1e-9)   # max(1, 0.675)×0.8，浮点保留
    assert s["dmgToPart"] == pytest.approx(8.17, abs=0.01)


def test_legacy_video_mode_same_at_low_pen_and_differs_at_high(out):
    """20/4 时 decomp 与 video 都是 0.5，旧 site 才会被顶到 1.1；
    只有超高穿（100/4）时 video 的 1.2 上限才与原文 decomp 的 1.1 分开。"""
    site = out["multiPen"]["layers"]
    video = out["multiPenVideo"]["layers"]
    assert site[0]["penOut"] == pytest.approx(video[0]["penOut"])
    assert site[0]["dmgOut"] == pytest.approx(video[0]["dmgOut"])
    assert site[0]["durCoeff"] == pytest.approx(video[0]["durCoeff"]) == pytest.approx(0.5)
    assert site[1]["blunt"] == pytest.approx(video[1]["blunt"])
    assert site[1]["durCoeff"] == pytest.approx(video[1]["durCoeff"]) == pytest.approx(0.6)
    c = out["coeffCases"]
    assert c["decompHighBlock100_4"] == pytest.approx(1.1)
    assert c["videoHighBlock"] == pytest.approx(1.2)         # 旧口径才有的 1.2 上限
