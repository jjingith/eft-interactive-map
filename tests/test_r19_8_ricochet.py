# -*- coding: utf-8 -*-
"""R62：护甲/插板跳弹（combat_sim + data/armor-ricochet.json）回归。

依据：
- 0.13.x 客户端反编译原文：ArmorComponent.Deflects 用每件装备自己的 RicochetVals；
  跳弹成立后 ApplyDamage 把 Damage / ArmorDamage / Penetration 全部 ÷2，再走挡下分支，
  仍按 P×AD×clamp(P/Resistance)×Destructibility 扣耐久，并交付半值钝伤。
- 曲线：x = 90° 最大概率，y = 最小角 z 的概率，z→90° 线性插值。
- 视频 8:52：40°/50%/90% 对应 Tac-Kek FAST MT 复刻头盔（0.9/0.5/40）。
"""
import json
import os
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIM_JS = os.path.join(ROOT, "combat_sim.js")
BRIDGE = os.path.join(ROOT, "tests", "js", "combat_sim_r19_8_test.js")
DATA = os.path.join(ROOT, "data", "armor-ricochet.json")
ITEMS = os.path.join(ROOT, "data", "items.json")

require_node = pytest.mark.skipif(shutil.which("node") is None, reason="node 不可用")


@pytest.fixture(scope="module")
def scen():
    out = subprocess.run(["node", BRIDGE, SIM_JS, ROOT], capture_output=True, text=True, timeout=60, cwd=ROOT)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def _json(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def test_ricochet_curve_boundaries(scen):
    m = scen["ricModel"]
    assert m["z40_below"] == 0            # 39° < 最小角 40° → 不跳弹
    assert m["z40_at"] == pytest.approx(0.5)    # 40° → 最小概率 50%
    assert m["z40_65"] == pytest.approx(0.7)    # 线性插值：0.5 → 0.9 的中点
    assert m["z40_90"] == pytest.approx(0.9)    # 90° → 最大概率 90%
    assert m["z50_below"] == 0
    assert m["z50_at"] == pytest.approx(0.4)
    assert m["z50_70"] == pytest.approx(0.65)   # 0.4 + 0.5×20/40
    assert m["z50_90"] == pytest.approx(0.9)
    assert m["zero_x"] == 0                     # 最大概率 0 → 永不跳弹
    assert m["bad"] == 0


def test_helmet_ricochet_engine_result(scen):
    s = scen["ricShots"]["s1"]
    assert s["ricochet"] is True
    assert s["chance"] == pytest.approx(0.7)
    assert s["roll"] < 0.7
    assert s["angle"] == 65
    # R62：÷2 后 P=21.5 / AD=33.5% / D=40，按挡下分支公式扣耐久：
    # 21.5×0.335×clamp(21.5/30)=0.7167×0.375≈1.9357（R65：float 直减，无取整）；半值钝伤 40×0.15×0.7397≈4.44
    assert s["durDmg"] == pytest.approx(1.935671875, abs=1e-6)
    assert s["durBefore"] == 40 and s["durAfter"] == pytest.approx(40 - 1.935671875, abs=1e-6)
    assert s["dmgToPart"] == pytest.approx(4.438, abs=0.01)
    assert s["stoppedBy"] == "ricochet"
    assert s["penetrated"] is False and s["blocked"] is True
    assert s["durConfidence"] == "estimated"
    # 另一个种子未跳弹 → 仍按普通挡下结算（钝伤 > 0）
    s2 = scen["ricShots"]["s2"]
    assert s2["ricochet"] is False
    assert s2["chance"] == pytest.approx(0.7)
    assert s2["dmgToPart"] > 0
    assert s2["stoppedBy"] == "armor"


def test_ricochet_only_above_min_angle_helmets_and_plates(scen):
    assert scen["ricBelow"]["ricochet"] is False       # 39° < 40°
    assert scen["ricBelow"]["chance"] is None
    assert scen["ricZero"]["ricochet"] is False        # 0° 正面
    assert scen["ricZero"]["chance"] is None
    # R62：插板与头盔一样参与跳弹，且按同一套 ÷2 + 甲伤公式结算
    assert scen["ricPlate"]["ricochet"] is True
    assert scen["ricPlate"]["chance"] == pytest.approx(0.7)
    assert scen["ricPlate"]["durDmg"] == pytest.approx(1.935671875, abs=1e-6)
    assert scen["ricPlate"]["dmgToPart"] == pytest.approx(4.438, abs=0.01)
    assert scen["ricPlate"]["stoppedBy"] == "ricochet"
    assert scen["ric90"]["ricochet"] is True
    assert scen["ric90"]["chance"] == pytest.approx(0.9)


def test_ricochet_data_snapshot_complete():
    d = _json(DATA)
    assert d.get("schema") == "eftmap.armor-ricochet/1"
    src = d.get("source") or {}
    assert src.get("site") == "https://tarkovgunsmith.com/"
    assert src.get("fetched_at") == "2026-11-02"
    assert "interpolated linearly" in src.get("rule", "")
    helms = d.get("helmets") or {}
    assert len(helms) == 159
    items = _json(ITEMS)["items"]
    for hid in helms:
        assert hid in items, "跳弹参数引用了本地不存在的物品：%s" % hid
    # 视频 8:52 的 40°/50%/90% 对应 Tac-Kek FAST MT 复刻头盔
    tac = helms["5ea05cf85ad9772e6624305d"]
    assert (tac["x"], tac["y"], tac["z"]) == (0.9, 0.5, 40)
    # 常见 4 级 FAST MT：0.9/0.5/70
    fast = helms["5a154d5cfcdbcb001a3b00da"]
    assert (fast["x"], fast["y"], fast["z"]) == (0.9, 0.5, 70)
    local_helmets = [i for i, r in items.items() if r.get("slot") == "helmet"]
    covered = [i for i in local_helmets if i in helms]
    assert len(covered) >= 70, "本地头盔覆盖率过低：%d/%d" % (len(covered), len(local_helmets))
