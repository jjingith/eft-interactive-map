# -*- coding: utf-8 -*-
"""R17S5：空行可拖 —— 预设行拖放模型专项测试。

模型结果来自 tests/js/preset_drag_model_test.js，它在运行时**从 app.js 抽取真实实现**
（amSimPresetDrop / amSimIdxByUid / 分区计数），不是另写一份逻辑。
"""
import json
import os
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_JS = os.path.join(ROOT, "app.js")
TEST_JS = os.path.join(ROOT, "tests", "js", "preset_drag_model_test.js")

require_node = pytest.mark.skipif(shutil.which("node") is None, reason="node 不可用")


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="module")
def model():
    out = subprocess.run(["node", TEST_JS], capture_output=True, text=True, timeout=60, cwd=ROOT)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_empty_top_row_drags_into_loop_first(model):
    """空首发行拖入循环第一位：循环出现空行 + A,B,C 全部保留，首发不再有该行。"""
    r = model["emptyTopToLoopFirst"]
    assert r["moved"] is True
    assert r["top"] == []
    assert r["loop"] == ["(空)", "A", "B", "C"]
    assert r["uidCount"] == 4 and r["uidUnique"] == 4      # 无副本、无重复 ID


def test_empty_bottom_row_drags_into_loop_second(model):
    r = model["emptyBottomToLoopSecond"]
    assert r["moved"] is True
    assert r["loop"] == ["A", "B", "(空)", "C"]
    assert r["bottom"] == []
    assert r["uidCount"] == 4


def test_empty_loop_row_drags_into_top(model):
    r = model["emptyLoopToTop"]
    assert r["moved"] is True
    assert r["top"] == ["D", "(空)"]
    assert r["loop"] == ["A", "C"]                          # 已选弹药完整保留


def test_empty_row_reorders_inside_loop(model):
    r = model["emptyReorderInsideLoop"]
    assert r["moved"] is True
    assert r["loop"] == ["(空)", "A", "C"]
    assert r["ord"] == 0


def test_empty_row_allowed_into_full_loop(model):
    """循环区已有 5 种弹药时，空行仍可迁入（空行不占弹药名额），只受行数上限约束。"""
    r = model["emptyIntoFullLoop"]
    assert r["moved"] is True
    assert r["ammoCount"] == 5
    assert r["loop"][-1] == "(空)"
    assert r["top"] == []
    assert "空" in r["msg"]


def test_ammo_row_rejected_when_loop_full(model):
    """带弹药条目拖入已满 5 种的循环区：拒绝且配置零变化（不能借空行绕过上限）。"""
    r = model["ammoIntoFullLoop"]
    assert r["moved"] is False
    assert r["unchanged"] is True
    assert r["top"] == ["D"]
    assert r["loop"] == ["A", "B", "C", "E1", "E2"]
    assert "最多 5 种" in r["msg"]


def test_empty_row_does_not_overwrite_target(model):
    r = model["emptyDoesNotOverwrite"]
    assert r["moved"] is True
    assert r["loop"] == ["(空)", "A", "B"]                  # 目标行 A 被保留并顺延
    assert r["bottom"] == []


def test_repeated_drags_keep_stable_uids(model):
    r = model["repeatedDrags"]
    assert r["uidStable"] is True
    assert r["rows"] == 4
    assert r["emptySame"] is True                           # 空行数量守恒，无重复/丢失


def test_row_cap_guard_keeps_config(model):
    r = model["rowCapGuard"]
    assert r["moved"] is False
    assert r["unchanged"] is True
    assert r["rowCount"] == 8


def test_no_empty_row_drag_block_in_source():
    """源码级断言：不再有「必须先选弹药才能拖」的拦截，且拖拽行为入口无条件。"""
    js = _read(APP_JS)
    assert "这一行还没有弹药" not in js                     # 提示已删除
    assert "if (!src.ammoId) { return { moved: false" not in js   # 拦截逻辑一并删除
    assert "amSimPresetZoneAmmoCount" in js                  # 上限只按「已配置弹药」计
    assert "AM_SIM_ZONE_ROWS_MAX" in js                      # 空行只受行数上限
    # 行渲染：draggable 与是否已选弹药无关
    seg = js[js.index("function amSimPresetRow"):]
    seg = seg[:seg.index("var prbox")]
    assert "row.draggable = true" in seg
    assert "draggable = !!" not in seg and "draggable = slot.ammoId" not in seg


def test_build_marker_current():
    """构建标记跟随当前轮次（R18 起为 R18）；只断言「标记存在且与资源版本一致」，
    不把某一轮的字符串写死成功能判据。"""
    js = _read(APP_JS)
    html = _read(os.path.join(ROOT, "index.html"))
    import re as _re
    m = _re.search(r'AM_BUILD = "([^"]+)"', js)
    assert m, "缺 AM_BUILD 构建标记"
    # 资源版本与构建标记同步（大小写无关：R18 / r18）
    assert ("?v=" + m.group(1).lower()) in html, "index.html 资源版本未与 AM_BUILD 同步"
    assert "?v=r17s4" not in html
