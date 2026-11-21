"""R19.28 专项回归：需求一（AK 系照门统一锚点 r2c6）与需求四（右栏候选表属性列）。

这些测试是**加性**的：只校验 R19.28 新增且不与旧测试冲突的行为，绝不改写 / 弱化任何既有用例。
缺 node 时自动跳过（与项目内其它布局不变量测试保持一致）。
"""
import subprocess
import shutil
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
UNIT_TOOL = ROOT / "tools" / "r19_28_unit.js"
AK_PROBE = ROOT / "tools" / "r19_28_ak_probe.js"
HAS_NODE = shutil.which("node") is not None


@pytest.mark.skipif(not HAS_NODE, reason="需要 node 才能跑 R19.28 探针")
def test_req4_columns_unit():
    """需求四：右栏候选表属性列单测 41/41 通过。"""
    proc = subprocess.run(["node", str(UNIT_TOOL)], capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr[-2000:]
    # 断言「N/N 通过」（全部通过，不写死总数，便于后续增补用例）+ 无失败
    assert re.search(r"(\d+)/\1 通过", proc.stdout), proc.stdout[-2000:]
    assert "FAIL" not in proc.stdout, proc.stdout[-2000:]


@pytest.mark.skipif(not HAS_NODE, reason="需要 node 才能跑 R19.28 探针")
def test_req1_ak_rear_sight_anchor():
    """需求一：结构判定的 AK 照门系照门必须落在 r2c6（不看枪名，不碰手动校准）。"""
    proc = subprocess.run(["node", str(AK_PROBE)], capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert "CHECK_REQ1: PASS" in proc.stdout, proc.stdout[-2000:]
