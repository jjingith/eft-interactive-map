# -*- coding: utf-8 -*-
"""r14 阶段B/C 测试：Desmos 穿透概率纯函数 + 逐发模拟引擎 combat_sim.js"""
import json
import math
import os
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_JS = os.path.join(ROOT, "app.js")
PROBE_JS = os.path.join(ROOT, "tests", "js", "amdesmos_probe.js")

require_node = pytest.mark.skipif(shutil.which("node") is None, reason="node 不可用")


def _desmos_ref(p, c, d):
    """独立转录的 Desmos m8cmsfokkl 参考实现（仅测试用，与 app.js 转录相互印证）。
    a = (121 - 5000/(45+2d))·c/10；
    p ≤ a-15 → 0；a-15 < p < a → 0.4·(a-p-15)²/100；p ≥ a → (100+p/(0.9a-p))/100
    """
    a = (121 - 5000.0 / (45 + 2.0 * d)) * c / 10.0
    if p <= a - 15:
        return 0.0
    if p < a:
        t = a - p - 15
        return max(0.0, min(1.0, 0.4 * t * t / 100.0))
    den = 0.9 * a - p
    if den >= -1e-9:
        den = -1e-9
    y = (100.0 + p / den) / 100.0
    return min(1.0, y) if y >= 0 else 0.0


def _run_probe():
    out = subprocess.run(["node", PROBE_JS, APP_JS],
                         capture_output=True, text=True, timeout=60, cwd=ROOT)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


@require_node
def test_am_desmos_chance_extracted_from_app():
    data = _run_probe()
    assert data["extracted"] is True


@require_node
def test_am_desmos_chance_matches_reference_transcription():
    """JS 实现与测试侧独立转录在固定向量上逐点一致（1e-12）。"""
    data = _run_probe()
    for case in data["cases"]:
        expect = _desmos_ref(case["p"], case["c"], case["d"])
        assert case["y"] == pytest.approx(expect, abs=1e-12), (
            "mismatch at p=%r c=%r d=%r: js=%r ref=%r" % (case["p"], case["c"], case["d"], case["y"], expect)
        )


@require_node
def test_am_desmos_chance_properties():
    """独立性质锚点：零段 / p=a 处连续且为 0.9 / 渐近上限 <1 / 异常输入返回 null。"""
    props = _run_probe()["props"]
    assert props["zeroBand_isZero"] is True
    assert props["continuity_at_a"] is True
    assert props["asymptote_below_1"] is True
    assert props["monotonic_high_pen"] is True
    assert props["null_on_bad_input"] is True
    assert props["zero_dur_valid"] is True


@require_node
def test_am_desmos_chance_sweep_in_unit_range():
    sweep = _run_probe()["sweep"]
    assert sweep["nullCount"] == 0
    assert sweep["min"] >= 0.0
    assert sweep["max"] <= 1.0
    assert sweep["max"] < 1.0          # 模型永远达不到 100%
    assert sweep["count"] == 6 * 21 * 161   # c 1..6 × d 0..100 步5 × p 0..80 步0.5
