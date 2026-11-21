# -*- coding: utf-8 -*-
"""R63：距离衰减（近似模型对照）、碎片化（固定种子）、重型护甲技能（globals 0.004/级）。

数据依据：
- 飞行段输入：data/ammo.json 的 v0/bc/m/dia（200/200 全覆盖）
- 碎片化概率：data/ammo.json 的 frag（= 官方 FragmentationChance，200/200）
- 重型护甲技能：data/game-truth/globals_ballistic.json → SkillsSettings.HeavyVests
  BluntThroughputDamageHVestsReducePerLevel = 0.004（0–50 级线性推断）

节点脚本：tests/js/combat_sim_r63_flight_frag_skills.js
"""
import importlib.util
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SIM_JS = ROOT / "combat_sim.js"
TEST_JS = ROOT / "tests" / "js" / "combat_sim_r63_flight_frag_skills.js"
APP_JS = ROOT / "app.js"
AMMO_JSON = ROOT / "data" / "ammo.json"

require_node = pytest.mark.skipif(shutil.which("node") is None, reason="node 不可用")


@pytest.fixture(scope="module")
def r63():
    out = subprocess.run(["node", str(TEST_JS), str(SIM_JS)], capture_output=True, text=True,
                         timeout=60, cwd=str(ROOT))
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def _load_r12():
    spec = importlib.util.spec_from_file_location("t12_ammo", str(ROOT / "tests" / "test_r12_ammo.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _ammo_row(aid):
    for row in json.loads(AMMO_JSON.read_text(encoding="utf-8"))["ammo"]:
        if row["id"] == aid:
            return row
    raise AssertionError("弹药 %s 不在 data/ammo.json" % aid)


# ---------------------------------------------------------------- 距离衰减
@require_node
def test_flight_decay_is_monotonic_with_distance():
    """用 app.js 同一套 amSimulate 复算（R12 已验证逐步等价）：
    速度、穿透、伤害必须随距离严格单调下降；0 m 必须等于纸面值。"""
    t12 = _load_r12()
    a = _ammo_row("54527ac44bdc2d36668b4567")   # M855A1
    samples = t12._simulate(float(a["v0"]), float(a["bc"]), float(a["m"]), float(a["dia"]), 500.0)
    by_d = {}
    for s in samples:
        by_d[int(s[0])] = s
    speeds = [by_d[d][2] for d in (0, 100, 200, 300, 400, 500)]
    assert speeds[0] == pytest.approx(a["v0"])
    assert all(speeds[i] > speeds[i + 1] - 1e-9 for i in range(len(speeds) - 1)), speeds

    factors = [0.5 + 0.5 * (v / a["v0"]) for v in speeds]
    pens = [round(a["pen"] * f) for f in factors]
    dmgs = [a["dmg"] * f for f in factors]
    assert all(factors[i] > factors[i + 1] for i in range(len(factors) - 1))
    assert all(pens[i] >= pens[i + 1] for i in range(len(pens) - 1))
    assert all(dmgs[i] > dmgs[i + 1] for i in range(len(dmgs) - 1))
    # 参照点：500 m 时速度仍有意义（不是瞬间归零），且衰减幅度 < 45%
    assert speeds[-1] > a["v0"] * 0.55


@require_node
def test_flight_none_is_flat_and_is_the_explicit_option(r63):
    f = r63["flight"]
    assert f["defaultFlat"] == {"speed": 945, "pen": 44, "dmg": 49}
    assert f["dmgToPart"] == pytest.approx(49)     # 100 m 仍为纸面伤害
    assert f["penIn"] == pytest.approx(44)
    assert f["models"]["flight"] == "none"
    # 默认仍是既有近似模型（不改变 R62 结果），在 UI 里可切换
    src = APP_JS.read_text(encoding="utf-8")
    assert 'flightModel: "approx"' in src
    assert '"flight-model"' in src
    assert '(s.flightModel === "none" && window.CS && window.CS.defaultFlight)' in src


# ---------------------------------------------------------------- 碎片化
@require_node
def test_fragmentation_seeded_is_reproducible(r63):
    f = r63["frag"]
    assert f["off"]["fragCount"] == 0
    assert f["onA"]["fragCount"] > 0
    assert f["onA"]["rolls"] == f["onB"]["rolls"], "同种子必须逐发一致"
    assert f["onA"]["rolls"] != f["onOtherSeed"]["rolls"], "换种子必须产生不同掷点"
    assert f["onA"]["fragCount"] == sum(1 for x in f["onA"]["triggered"] if x)
    # 触发即 +0.5×；M855A1 D49 → 73.5
    assert set(f["onA"]["dmg"]) == {49, 73.5}


@require_node
def test_fragmentation_pen_gate_and_default_off(r63):
    f = r63["frag"]
    assert f["minPen"] == 20 and f["extraMul"] == 0.5
    # 9x19 RIP：P2 < 20 → 概率归零（即使 frag=1 也不触发）
    assert all(c == 0 for c in f["gate"]["chances"])
    assert f["gate"]["fragCount"] == 0
    assert f["off"]["models"]["fragmentation"] is False
    src = APP_JS.read_text(encoding="utf-8")
    assert "fragOn: false" in src
    assert '"frag-on"' in src
    assert "estimated" in SIM_JS.read_text(encoding="utf-8")


# ---------------------------------------------------------------- 重型护甲技能
@require_node
def test_heavy_vests_level_zero_vs_max(r63):
    hv = r63["hv"]
    assert hv["perLevel"] == 0.004 and hv["maxLevel"] == 50
    zero, mx = hv["zeroHeavy"], hv["maxHeavy"]
    assert zero["armorType"] == "Heavy" and mx["hvLevel"] == 50
    assert zero["hvReduce"] == 0 and mx["hvReduce"] == pytest.approx(0.2)
    # 钝伤 BT 0.18 → 0.144；伤害 8.82 → 7.056（恰好 0.8×）
    assert mx["bluntFactor"] == pytest.approx(0.144)
    assert mx["dmgToPart"] == pytest.approx(zero["dmgToPart"] * 0.8, rel=1e-6)


@require_node
def test_heavy_vests_only_affects_heavy_armor(r63):
    hv = r63["hv"]
    light = hv["maxLight"]
    assert light["armorType"] == "Light"
    assert light["hvReduce"] == 0
    assert light["dmgToPart"] == pytest.approx(hv["zeroHeavy"]["dmgToPart"])
    assert light["bluntFactor"] == pytest.approx(hv["zeroHeavy"]["bluntFactor"])


def test_skill_ui_is_optional_and_defaults_to_zero():
    src = APP_JS.read_text(encoding="utf-8")
    assert "hvLevel: 0" in src
    assert '"hv-level"' in src
    assert "heavyVestsLevel: (typeof s.hvLevel" in src
    # 数据来源写进 UI 说明，避免把推断当成官方原文
    assert "BluntThroughputDamageHVestsReducePerLevel" in src


def test_ammo_detail_exposes_new_fields():
    src = APP_JS.read_text(encoding="utf-8")
    for label in ("碎片数量", "穿透偏差 σ", "障碍穿透概率"):
        assert label in src, "弹药详情缺少字段 %s" % label
    assert "fragMin" in src and "fragMax" in src
