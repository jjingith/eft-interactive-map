# -*- coding: utf-8 -*-
"""r14 阶段C：combat_sim.js 逐发引擎场景测试（node 子进程执行，pytest 断言）"""
import json
import os
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIM_JS = os.path.join(ROOT, "combat_sim.js")
APP_JS = os.path.join(ROOT, "app.js")
TEST_JS = os.path.join(ROOT, "tests", "js", "combat_sim_test.js")

require_node = pytest.mark.skipif(shutil.which("node") is None, reason="node 不可用")


@pytest.fixture(scope="module")
def sim():
    out = subprocess.run(["node", TEST_JS, SIM_JS, APP_JS],
                         capture_output=True, text=True, timeout=60, cwd=ROOT)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def _shot(sim, key, i=0):
    return sim[key]["shots"][i]


def test_direct_fire_three_shot_kill(sim):
    """无护甲 dmg42 vs 胸 85：3 发死亡，第 3 发触发；弹匣 5 发死亡后停射剩 2 发。"""
    r = sim["direct"]
    assert r["dead"] is True
    assert r["killedAt"] == 3
    assert r["shotCount"] == 3
    assert r["roundsLeft"] == 2


def test_full_penetration_through_plate(sim):
    """满穿透桩：4 级板 clamp(53/52.5)=1 → 单发入体 42（R19.8 起删除额外 ×0.9 层损耗）；板掉耐久。"""
    r = sim["pen1"]
    assert r["dead"] is True
    s0 = _shot(sim, "pen1")
    assert s0["pellets"][0]["penetrated"] is True
    assert s0["dmgToPart"] == pytest.approx(42, abs=1e-9)
    assert r["armorFinal"][0]["dur"] < r["armorFinal"][0]["durMax"]


def test_zero_penetration_blunt_and_degradation(sim):
    """零穿透桩：只有钝伤入体；护甲每发掉耐久且 ≥1；耐久逐发递减。"""
    r = sim["pen0"]
    assert r["dead"] is False
    shots = r["shots"]
    assert len(shots) >= 2
    for s in shots:
        for p in s["pellets"]:
            assert p["penetrated"] is False
            assert p["blunt"] is True
            assert p["dmgToArmor"] >= 1
    durs = [s["pellets"][0]["layers"][0]["durAfter"] for s in shots]
    assert durs == sorted(durs, reverse=True)   # 单调不增


def test_mixed_magazine_order(sim):
    """混压弹匣按数组顺序逐发消耗，耗尽即停。"""
    r = sim["mixed"]
    assert [s["ammoId"] for s in r["shots"]] == ["a", "b", "a"]
    assert r["roundsLeft"] == 0
    # B 弹（dmg50 pen60）对无甲胸部 100：20+50+20=90 < 100 → 不死；验证伤害按序累计
    assert r["dead"] is False


def test_seed_reproducibility(sim):
    """同种子结果逐字节一致；不同种子结果不同（真实概率模型）。"""
    a = json.dumps(sim["reproA"], sort_keys=True)
    a2 = json.dumps(sim["reproA2"], sort_keys=True)
    b = json.dumps(sim["reproB"], sort_keys=True)
    assert a == a2
    assert a != b


def test_headshot_rules(sim):
    """头部：满穿透一枪摧毁 35 血头部立即死亡；零穿透只钝伤不掉超过上限。"""
    r = sim["headKill"]
    assert r["dead"] is True
    assert r["killedAt"] == 1
    b = sim["headBlunt"]
    assert b["dead"] is False
    assert 0 < b["targetFinal"]["parts"]["head"]["hp"] < 35


def test_destroyed_limb_overflow(sim):
    """手臂 100 伤一发：扣完 60，击杀发剩余 40 全额均摊到其余 6 个存活部位
    （0.49× 比例仅作用于对已摧毁部位的后续命中，见 combat_sim.js overflow）。"""
    r = sim["overflow"]
    p0 = _shot(sim, "overflow")["pellets"][0]
    ov = p0.get("overflow")
    assert ov is not None
    assert ov["from"] == "leftArm"
    assert ov["dmg"] == pytest.approx(40.0, abs=1e-9)
    assert ov["each"] == pytest.approx(40.0 / 6, abs=1e-9)
    assert len(ov["to"]) == 6
    assert sim["overflow"]["targetFinal"]["parts"]["leftArm"]["hp"] == 0


def test_multipellet_min_durability(sim):
    """霰弹 8 弹丸零穿透：单发护甲耐久损伤 ≥ 8（每颗最低 1 点）。"""
    r = sim["pellets"]
    assert len(r["shots"]) == 1
    s = r["shots"][0]
    assert len(s["pellets"]) == 8
    assert s["dmgToArmor"] >= 8


def test_fire_rate_timing_and_empty_stop(sim):
    """600rpm → 每发 100ms；弹匣 3 发耗尽即停。"""
    r = sim["timing"]
    assert [s["timeMs"] for s in r["shots"]] == [100, 200, 300]
    assert r["roundsLeft"] == 0


def test_durability_monotonic_pen_chance(sim):
    """真实概率模型：同弹药同等级，耐久越低穿透概率单调不降。"""
    assert sim["durMonotonic"] is True


def test_dist_mode_raw_weights_normalized(sim):
    """加权命中分布：UI 传入原始百分比权重（总和≠1）须归一化后按比例抽部位，
    不得恒中首键（修复前 r∈[0,1) 与未归一化累加值比较 → 永远命中第一个部位）。"""
    low = sim["rawDistHead5"]
    high = sim["rawDistHead95"]
    norm = sim["rawDistNormalized"]
    assert sum(low.values()) == 200
    assert low["head"] <= 30          # ≈5%，修复前恒为 200
    assert low["chest"] >= 100
    assert high["head"] >= 120        # ≈95%
    assert high.get("chest", 0) <= 30
    assert 60 <= norm["head"] <= 140  # 已归一化 50/50 权重同样有效
    assert norm["head"] + norm["chest"] == 200


def test_real_model_reproducible_kill_recorded(sim):
    """真实模型 + 种子：产生完整可复现对局记录（供阶段D 案例展示）。"""
    r = sim["reproA"]
    assert r["dead"] is True
    assert r["killedAt"] >= 1
    assert r["shots"][0]["ammoId"] == "x"
    for s in r["shots"]:
        assert "timeMs" in s and "part" in s
