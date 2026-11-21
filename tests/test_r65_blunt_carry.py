# -*- coding: utf-8 -*-
"""R65：前层挡下后，后继层只乘自身 BT（原文 Player.ProceedDamageThroughArmor L27873–27929）。

锚点（用户提供）：伤害 162.3 / 穿透 36.7；5 级 UHMWPE 插板（用户给的 BT 0.093 是 0.12 ×0.6 后的值，
原始 BT 0.155）；3 级芳纶内衬 40/40，BT 兜底 0.18。
原文口径（×0.6 停用）：插板钝伤 ≈14.90 → 内衬只 ×0.18 → ≈2.68。
旧 0.12 口径（×0.6 启用）：插板 ≈8.94 → 内衬 ≈1.61。
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SIM_JS = ROOT / "combat_sim.js"
TEST_JS = ROOT / "tests" / "js" / "combat_sim_r65_anchor.js"

require_node = pytest.mark.skipif(shutil.which("node") is None, reason="node 不可用")


def _run(mode):
    out = subprocess.run(["node", str(TEST_JS), str(SIM_JS), mode],
                         capture_output=True, text=True, timeout=60, cwd=str(ROOT))
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


@pytest.fixture(scope="module")
def off():
    return _run("off")


@pytest.fixture(scope="module")
def on():
    return _run("on")


def test_soft_liner_06_is_disabled_by_default(off):
    assert off["enabled06"] is False
    src = SIM_JS.read_text(encoding="utf-8")
    assert "CS.SOFT_LINER_PLATE_BLUNT_ENABLED = false;" in src
    assert "0.12" in src and "0.13" in src


@require_node
def test_anchor_plate_and_liner_only_multiply_bt(off):
    raw = off["rawBT0155"]
    assert raw["plateBlunt"] == pytest.approx(14.8957, abs=0.002)
    assert raw["plateScale"] == pytest.approx(0.5921, abs=1e-3)
    assert raw["linerIn"] == pytest.approx(raw["plateBlunt"])
    assert raw["linerFactor"] == pytest.approx(0.18)
    assert raw["linerOut"] == pytest.approx(raw["plateBlunt"] * 0.18, abs=1e-9)
    assert raw["dmgToPart"] == pytest.approx(raw["linerOut"])
    # 与用户给的 15.02 / 2.70 一致（差异来自原始 BT 粗略换算）
    assert raw["plateBlunt"] == pytest.approx(15.02, rel=0.01)
    assert raw["linerOut"] == pytest.approx(2.70, rel=0.02)


@require_node
def test_successor_layer_has_no_penetration_chance(off):
    """96.2% 那个穿透概率在原文流程里不存在：后继层不调 ApplyDamage。"""
    raw = off["rawBT0155"]
    assert raw["linerAfterBlock"] is True
    assert raw["linerChance"] is None
    assert raw["linerRoll"] is None
    assert raw["linerDur"] == 0
    assert raw["linerDurAfter"] == 40
    assert raw["stoppedBy"] == "armor"


@require_node
def test_legacy_06_double_deduction(on):
    raw_on = on["rawBT0155"]
    assert on["enabled06"] is True
    assert raw_on["plateBlunt"] == pytest.approx(8.9374, abs=0.002)
    assert raw_on["linerOut"] == pytest.approx(1.6087, abs=0.002)
    # 与原文口径相比正好少乘一次 0.6（双重扣减）
    assert raw_on["plateBlunt"] == pytest.approx(14.8957 * 0.6, abs=1e-3)


@require_node
def test_armor_damage_is_float_not_rounded(off):
    """原文 ApplyDurabilityDamage 是 float 直减；三发甲伤相同且不带整数台阶。"""
    shots = off["rawBT0155"]["threeShotsDur"]
    base = shots[0][0]
    assert base == pytest.approx(4.7275839, abs=1e-6)
    assert base != round(base)
    assert shots[1][0] == pytest.approx(base) and shots[2][0] == pytest.approx(base)
    assert shots[0][1] == pytest.approx(40 - base, abs=1e-9)
    assert shots[1][1] == pytest.approx(40 - 2 * base, abs=1e-9)
    assert shots[2][1] == pytest.approx(40 - 3 * base, abs=1e-9)


@require_node
def test_no_liner_means_plate_blunt_enters_body(off):
    no = off["noLiner"]
    assert no["plateBlunt"] == pytest.approx(14.8957, abs=0.002)
    assert no["dmgToPart"] == pytest.approx(no["plateBlunt"])
    assert no["stoppedBy"] == "armor"
