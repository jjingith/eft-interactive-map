"""R19.29 专项回归：任务A（光学配件子槽定位）、任务B（战术槽冲突动态避让）、
任务C（R+E/3 符号语义）、任务D（静态审计产物与实时布局一致）。

这些测试是**加性**的：只校验 R19.29 新增行为与任务书明确要求的不变量，
不改写 / 弱化任何既有用例。缺 node 时自动跳过（与项目内其它布局测试一致）。

判定口径（任务书第十节要求区分）：
  · 代码检查 = node --check / 源码断言
  · 自动化测试 = 本文件（node 探针 + pytest 断言）
  · 真实浏览器操作 = 不在本文件内声明（见 docs/r19.29/report.md 的浏览器验收章节）
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TASKA_TOOL = ROOT / "tools" / "r19_29_taska.js"
TASKB_TOOL = ROOT / "tools" / "r19_29_taskb.js"
UNIT_TOOL = ROOT / "tools" / "r19_28_unit.js"
AUDIT_JSON = ROOT / "docs" / "r19.15.3-layout-audit" / "ak-dovetail-sight-layout.json"
TASKA_JSON = ROOT / "docs" / "r19.29" / "task-a.json"
TASKB_JSON = ROOT / "docs" / "r19.29" / "task-b.json"
HAS_NODE = shutil.which("node") is not None


def _run(tool):
    return subprocess.run(["node", str(tool)], capture_output=True, text=True, timeout=300)


def _json(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


# ----------------------------------------------------------------------------
# 任务A：光学配件（scope）子槽必须位于父件上方同一列
# ----------------------------------------------------------------------------
@pytest.mark.skipif(not HAS_NODE, reason="需要 node 才能跑 R19.29 任务A 探针")
def test_taska_scope_kind_stays_above_parent():
    """scope 母槽 → scope 子槽：落在父件同排或下方 = 硬违规，必须为 0。"""
    proc = _run(TASKA_TOOL)
    assert proc.returncode == 0, proc.stdout[-3000:] + proc.stderr[-2000:]
    assert "CHECK_TASKA: PASS" in proc.stdout, proc.stdout[-3000:]
    d = _json(TASKA_JSON)
    s = d["summary"]
    assert s["hardViolation"] == 0, s
    assert d["unexplained"] == [], d.get("unexplained")
    assert s["okDefault"] >= 3, "紧邻正上方同列的默认场景样本不足（至少 3 组）"


@pytest.mark.skipif(not HAS_NODE, reason="需要 node 才能跑 R19.29 任务A 探针")
def test_taska_covers_three_structures():
    """至少三种不同挂载结构通过（机匣直挂 / 燕尾槽 / 顶部锚点 …），不看枪名。"""
    if not TASKA_JSON.exists():
        pytest.skip("先跑 tools/r19_29_taska.js")
    d = _json(TASKA_JSON)
    structs = d["structsCompliantDefault"]
    assert len(structs) >= 3, structs
    # 结构来自父件链路判定，必须是引擎给出的结构签名而不是枪名字符串
    for s in structs:
        assert s in ("top-anchor", "receiver-direct", "dovetail-mount",
                     "rail-mount", "handguard-mount-chain"), s


@pytest.mark.skipif(not HAS_NODE, reason="需要 node 才能跑 R19.29 任务A 探针")
def test_taska_hard_violation_exemption_is_justified():
    """硬违规豁免必须写明原因：人工校准（约束⑦）或与既有不变量冲突（R19.13 第 6 行）。"""
    d = _json(TASKA_JSON)
    assert d["knownHard"], "豁免名单不该为空，否则应直接修掉"
    for k in d["knownHard"]:
        assert ("校准" in k["why"]) or ("R19.13" in k["why"]), k


# ----------------------------------------------------------------------------
# 任务B：战术槽冲突动态避让
# ----------------------------------------------------------------------------
@pytest.mark.skipif(not HAS_NODE, reason="需要 node 才能跑 R19.29 任务B 探针")
def test_taskb_reflow_rules():
    """B1–B5 全部通过：子槽落右邻格 / 让位右移 / 两槽不同格 / 移除恢复 / 幂等不漂移。"""
    proc = _run(TASKB_TOOL)
    assert proc.returncode == 0, proc.stdout[-4000:] + proc.stderr[-2000:]
    assert "CHECK_TASKB: PASS" in proc.stdout, proc.stdout[-4000:]
    d = _json(TASKB_JSON)
    s = d["summary"]
    assert s["scenarios"] >= 30, s
    assert s["sameRowConflict"] == 0 and s["dup"] == 0, s
    assert s["restoreClean"] == s["scenarios"], s
    assert s["idempotent"] == s["scenarios"], s
    assert s["fallbackDirty"] == 0, "避让不得污染 info.fallback（人工校准统计必须保持干净）"
    assert s["synthPass"] == s["synthTotal"], d["synthChecks"]
    assert s["calibUntouched"] is True, "避让不得写入 data/gun-layout-calibration.json"


@pytest.mark.skipif(not HAS_NODE, reason="需要 node 才能跑 R19.29 任务B 探针")
def test_taskb_avoidance_actually_shifts_blocker():
    """确实存在「独立槽位临时代父件右邻格让位并右移」的真实场景（不是空跑）。"""
    d = _json(TASKB_JSON)
    shifted = [c for c in d["cases"] if c["shiftedCount"] > 0]
    assert len(shifted) >= 3, "未观察到任何让位右移，规则可能没生效"
    for c in shifted:
        for s in c["shifted"]:
            assert "->" in s and s.split("->")[0].split()[-1] != s.split("->")[1].strip(), s


@pytest.mark.skipif(not HAS_NODE, reason="需要 node 才能跑 R19.29 任务B 探针")
def test_taskb_calibration_records_untouched():
    """校准记录数必须与 R19.28 交付时一致（397 条），证明避让是纯显示层。"""
    calib = _json(ROOT / "data" / "gun-layout-calibration.json")
    total = 0
    for g in calib.get("guns", {}).values():
        total += len(g.get("slots", {}) or {})
    assert total == 397, total


# ----------------------------------------------------------------------------
# 任务C：R+E/3 公式符号（不取绝对值）
# ----------------------------------------------------------------------------
@pytest.mark.skipif(not HAS_NODE, reason="需要 node 才能跑 R19.28/R19.29 单元测试")
def test_taskc_re3_sign_semantics():
    """任务书六个示例值必须逐个成立；符号只反转一次；缺失与真实 0 区分。"""
    proc = _run(UNIT_TOOL)
    assert proc.returncode == 0, proc.stderr[-2000:]
    out = proc.stdout
    assert "FAIL" not in out, out[-3000:]
    assert re.search(r"(\d+)/\1 通过", out), out[-2000:]
    # 源码层面：不得再出现对后坐力取绝对值的写法
    src = (ROOT / "app.js").read_text(encoding="utf-8")
    m = re.search(r"function gunRE3\([^)]*\)\s*\{(.+?)\n  \}", src, re.S)
    assert m, "未找到 gunRE3 实现"
    body = m.group(1)
    assert "Math.abs" not in body, body
    assert "(-r)" in body.replace(" ", "") or "-r)" in body.replace(" ", ""), body


# ----------------------------------------------------------------------------
# 任务D：静态审计产物与实时布局一致
# ----------------------------------------------------------------------------
def test_taskd_audit_json_rear_sight_matches_live_rule():
    """静态产物里 AK 照门系必须记 r2c6、非 AK 非燕尾槽必须记 r2c8（与实时规则一致）。"""
    d = _json(AUDIT_JSON)
    sample = d["nonDovetailSample"]
    assert len(sample) >= 3, sample
    non_ak = 0
    for g in sample:
        rs = g.get("rearSight")
        if not rs:
            continue
        assert rs["row"] == 2, g
        if g.get("akRearFamily"):
            assert rs["col"] == 6, g
        else:
            assert rs["col"] == 8, g
            non_ak += 1
    assert non_ak >= 3, "非 AK 非燕尾槽样本不足，无法验证 r2c8 不变量"
    assert d["summary"]["violations"] == [], d["summary"]
