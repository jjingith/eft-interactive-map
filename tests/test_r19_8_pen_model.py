# -*- coding: utf-8 -*-
"""R19.8b：逐发引擎穿透概率回归（默认 Desmos m8cmsfokkl + 原始满耐久百分比）。

Desmos 状态（2026-11-02 从 https://www.desmos.com/calc-states/production/m8cmsfokkl 读取）：
  d = 耐久%（当前耐久 / 出厂原始满耐久）；c=等级；n=穿透力
  a=(121-5000/(45+2d))*c*10*0.01
  0.4(a-p-15)^2/100  {a-15<p<a}
  (100+p/(0.9a-p))/100 {a<=p}
  p<=a-15 时无输出（本实现取 0）。

备选 "table" 为上一轮 6:07 实测表模型（保留开关）。
"""
import json
import os
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "app.js")
PROBE = os.path.join(ROOT, "tests", "js", "amarmorpen_probe.js")

require_node = pytest.mark.skipif(shutil.which("node") is None, reason="node 不可用")


@pytest.fixture(scope="module")
def probe():
    out = subprocess.run(["node", PROBE, APP], capture_output=True, text=True, timeout=60, cwd=ROOT)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def _by(cases, p, c, dur, durMax, durOrig):
    for x in cases:
        if (x["p"] == p and x["c"] == c and x["dur"] == dur and
                x["durMax"] == durMax and x["durOrig"] == durOrig):
            return x["y"]
    raise AssertionError("case not found: %r" % ((p, c, dur, durMax, durOrig),))


def test_model_is_desmos_and_matches_expression(probe):
    assert probe["extracted"] is True
    assert probe["model"] == "desmos"
    # 4 级满耐久（d=100）
    for p, y in zip([37, 38, 39, 40, 41],
                    [0.5534976426488963, 0.6516037650978759, 0.7577098875468554,
                     0.8718160099958351, 0.9143502728512959]):
        assert _by(probe["cases"], p, 4, 40, 40, 40) == pytest.approx(y, abs=1e-9)
    # 5 级满耐久（d=100）
    for p, y in zip([47, 48, 49, 50, 51],
                    [0.5479421074552266, 0.6455747605164512, 0.7512074135776756,
                     0.8648400666389001, 0.9110517885744794]):
        assert _by(probe["cases"], p, 5, 50, 50, 50) == pytest.approx(y, abs=1e-9)


def test_30_60_equals_30_30_with_original_max_denominator(probe):
    """30/60 与「维修后上限 30、原始满 60」的 30/30：d 都是 50% → 概率完全相同。"""
    a = _by(probe["cases"], 47, 5, 30, 60, 60)
    b = _by(probe["cases"], 47, 5, 30, 30, 60)
    assert a == pytest.approx(0.9417396879675144, abs=1e-9)
    assert b == pytest.approx(a, abs=1e-12)


def test_durability_percentage_monotonic(probe):
    y80 = _by(probe["cases"], 47, 5, 40, 50, 50)
    y40 = _by(probe["cases"], 47, 5, 20, 50, 50)
    assert y80 == pytest.approx(0.7502254610350982, abs=1e-9)
    assert y40 == pytest.approx(0.9554502369668246, abs=1e-9)
    assert y40 > y80


def test_class6_penetration_curve(probe):
    assert _by(probe["cases"], 43, 6, 45, 45, 45) == pytest.approx(0)
    assert _by(probe["cases"], 43, 6, 12, 45, 45) == pytest.approx(0.9159766841094256, abs=1e-9)
    assert _by(probe["cases"], 43, 6, 0, 45, 45) == pytest.approx(0.9885820499203399, abs=1e-9)


def test_model_rejects_bad_input(probe):
    for x in probe["cases"]:
        if isinstance(x["y"], (int, float)):
            assert 0 <= x["y"] <= 0.99
    assert _by(probe["cases"], None, 5, 30, 60, 60) is None
    assert _by(probe["cases"], 47, 5, -1, 50, 50) is None


def test_table_fallback_is_retained(probe):
    """备选表模型仍可切换：4/5 级满耐久与上一轮实测表一致，30/60 == 30/30。"""
    t = probe["table"]
    for p, y in zip([37, 38, 39, 40, 41], [0.27, 0.40, 0.59, 0.80, 0.85]):
        assert _by(t, p, 4, 40, 40, 40) == pytest.approx(y, abs=1e-9)
    for p, y in zip([47, 48, 49, 50, 51], [0.52, 0.62, 0.72, 0.84, 0.88]):
        assert _by(t, p, 5, 50, 50, 50) == pytest.approx(y, abs=1e-9)
    assert _by(t, 47, 5, 30, 60, 60) == _by(t, 47, 5, 30, 30, 60)
