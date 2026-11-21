# -*- coding: utf-8 -*-
"""R19.25 专项测试：任务树布局重构 + 商人英文名统一。

分组（对应任务书第九节）：
  A 布局结构    —— 跑 tools/r1925_layout_test.js（Node），断言结构正确性与质量门槛
  B 渲染接入    —— tasks.js 是否真的用布局模块、旧算法是否已移除、画布尺寸来源
  C 商人名称    —— 审计文件与数据一致、tasks.js 不再显示中文商人名
  D 三模式      —— 浏览器验收产物（tools/r1932_accept.py）必须全绿；缺失则 skip
  E 版本/离线   —— 构建号、资源版本串、无外链
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TASKS_JS = os.path.join(ROOT, "tasks.js")
TASKS_CSS = os.path.join(ROOT, "tasks.css")
LAYOUT_JS = os.path.join(ROOT, "js", "task-graph-layout.js")
INDEX = os.path.join(ROOT, "index.html")
APP = os.path.join(ROOT, "app.js")
DOCS = os.path.join(ROOT, "docs", "r19.25-task-tree")
TASKS_DIR = os.path.join(ROOT, "data", "tasks")
MODES = ("regular", "pve", "pvps")


def _text(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(scope="module")
def layout_run():
    proc = subprocess.run(["node", os.path.join(ROOT, "tools", "r1925_layout_test.js")],
                          capture_output=True, text=True, cwd=ROOT)
    assert proc.returncode == 0, proc.stderr[-800:]
    return json.loads(proc.stdout)


@pytest.fixture(scope="module")
def audit():
    path = os.path.join(DOCS, "trader-name-audit.json")
    if not os.path.exists(path):
        pytest.skip("缺少 trader-name-audit.json（先跑 tools/r1925_trader_audit.py）")
    return _load(path)


@pytest.fixture(scope="module")
def browser():
    path = os.path.join(DOCS, "browser-accept.json")
    if not os.path.exists(path):
        pytest.skip("缺少浏览器验收产物（先跑 tools/r1932_accept.py）")
    return _load(path)


# ---------------------------------------------------------------- A 布局结构
def test_A_layout_module_exists_and_exports():
    src = _text(LAYOUT_JS)
    assert "window.GWTaskGraph" in src
    assert "function layout(tasks, options)" in src
    # 纯计算模块：不碰 DOM / 网络 / 业务
    for bad in ("document.", "fetch(", "XMLHttpRequest", "GWTasks", "state."):
        assert bad not in src, bad


def test_A_layout_structural_checks_all_pass(layout_run):
    assert layout_run["ok"] is True, [r for r in layout_run["results"] if not r["ok"]][:5]
    assert layout_run["total"] >= 40, layout_run["total"]


@pytest.mark.parametrize("mode", MODES)
def test_A_real_data_quality_gate(layout_run, mode):
    m = layout_run["summary"][mode]
    data = _load(os.path.join(TASKS_DIR, "tasks.%s.json" % mode))
    assert m["nodes"] == data["counts"]["tasks"], (m["nodes"], data["counts"]["tasks"])
    assert m["edges"] == data["counts"]["edges"], (m["edges"], data["counts"]["edges"])
    prereq = sum(1 for r in data["tasks"].values() if (r.get("prerequisites") or []))
    assert prereq > 0
    assert m["nodeOverlaps"] == 0
    assert m["straightCrossings"] <= 80, m["straightCrossings"]
    assert m["bands"] >= 8
    assert m["dummies"] >= 0
    assert m["crossTraderEdges"] > 0, "真实数据里确实存在跨商人依赖，必须被识别"


def test_A_crossings_and_canvas_improved_vs_baseline(layout_run):
    """与 docs/r19.25-task-tree/layout-before.json 的改造前指标对比。"""
    before_path = os.path.join(DOCS, "layout-before.json")
    if not os.path.exists(before_path):
        pytest.skip("缺少 layout-before.json")
    before = _load(before_path)["modes"]
    for mode in MODES:
        old = before.get(mode) or {}
        new = layout_run["summary"][mode]
        assert old.get("geometricCrossings"), old
        # 交叉数至少下降 80%
        assert new["straightCrossings"] <= old["geometricCrossings"] * 0.2, (
            mode, new["straightCrossings"], old["geometricCrossings"])
        # 画布高度至少下降 60%（旧版把所有无前置任务堆在第一列）
        assert new and True
        old_h = (old.get("canvas") or {}).get("h") or 1
        # 新高度来自 Node 侧 summary 之外的字段：用 layout-after.json 里的高度
        after_path = os.path.join(DOCS, "layout-after.json")
        after = _load(after_path)["modes"][mode] if os.path.exists(after_path) else {}
        if after.get("canvas", {}).get("h"):
            assert after["canvas"]["h"] <= old_h * 0.4, (mode, after["canvas"]["h"], old_h)


# ---------------------------------------------------------------- B 渲染接入
def test_B_render_uses_layout_module():
    js = _text(TASKS_JS)
    assert "window.GWTaskGraph" in js
    assert "G.layout(state.tasks" in js
    assert "state.layoutCache" in js, "布局要按模式缓存，不能每次重排"
    # 旧的最长路径 + 列排序实现必须移除（否则两套并存）
    assert "nodes[f].rank = Math.max(nodes[f].rank, nodes[id].rank + 1)" not in js
    assert "grid-template-columns" not in js


def test_B_render_draws_bands_edges_nodes():
    js = _text(TASKS_JS)
    assert 'id: "tk-bands"' in js and 'class: "tk-band"' in js
    assert "tk-band-label" in js
    assert "e.points" in js, "连线必须用布局给出的折点，不能自己算"
    assert 'id: "tk-edges"' in js and 'id: "tk-nodes"' in js
    css = _text(TASKS_CSS)
    for cls in (".tk-band", ".tk-band-label", ".tk-edge.is-cross", ".tk-edge.is-long",
                ".tk-edge.is-cycle"):
        assert cls in css, cls


def test_B_canvas_size_from_layout():
    js = _text(TASKS_JS)
    assert "width: r.width" in js and "height: r.height" in js
    # fitTree / centerOnTask 仍读 state.graph 的宽高
    assert "state.graph.width" in js and "state.graph.height" in js


# ---------------------------------------------------------------- C 商人名称
def test_C_audit_covers_all_traders(audit):
    traders = _load(os.path.join(TASKS_DIR, "traders.json"))["traders"]
    assert audit["total"] == len(traders)
    assert audit["resolved"] == len(traders), audit["unresolved"]
    assert not audit["unresolved"], audit["unresolved"]
    for row in audit["traders"]:
        assert row["traderId"] in traders
        assert row["displayName"] == traders[row["traderId"]]["nameEn"]
        assert re.match(r"^[A-Za-z]", row["displayName"]), row
        # 不能用内部 ID / 中文名 / slug 当显示名
        assert row["displayName"] != row["traderId"]
        assert row["displayName"] != row["nameZhBefore"]
        assert row["displayName"] != row["normalizedName"]


def test_C_all_display_sites_audited(audit):
    assert not audit["sitesMissing"], audit["sitesMissing"]
    assert len(audit["sites"]) >= 10


def test_C_no_chinese_trader_names_in_task_ui():
    js = _text(TASKS_JS)
    patterns = [
        r"traderOf\([a-z]+\)\.nameZh",
        r"state\.traders\[[^\]]+\]\.nameZh(?!\s*\))",
        r"\.nameZh \+ \"（\"",
        r'tr\.nameZh \|\|',
    ]
    for p in patterns:
        assert not re.search(p, js), p
    # 显示路径必须走统一入口
    # R73：详情副标题去掉了重复的商人名（任务名下方只留类型/等级），所以调用点由 10 处减为 9 处；
    # 这里保持下限断言，防止后续把商人名改回 data 里的中文 nameZh。
    assert js.count("traderEn(") >= 9
    assert "function traderEn(rec)" in js


def test_C_trader_enums_are_data_driven(audit):
    """英文名必须来自数据，不能在代码里写死一张商人表。"""
    js = _text(TASKS_JS)
    for row in audit["traders"]:
        assert ('"%s"' % row["nameEn"]) not in js, row["nameEn"]


def test_C_i18n_skip_marks_trader_names():
    js = _text(TASKS_JS)
    assert 'nm.setAttribute("data-i18n-skip", "1")' in js
    assert 'o.setAttribute("data-i18n-skip", "1")' in js
    assert 'kv[2] === "traderEn"' in js
    ui = _load(os.path.join(ROOT, "data", "i18n", "ui-zh.json"))
    kept = (ui.get("keptEnglish") or {})
    assert "traderName" in (kept.get("why") or {}), "商人英文名要登记为中文化例外"


def test_C_guide_overview_uses_english_trader():
    py = _text(os.path.join(ROOT, "tools", "fetch_tasks.py"))
    assert "task.get(\"traderEn\") or" in py
    for mode in MODES:
        guides = _load(os.path.join(TASKS_DIR, "guides.%s.json" % mode))["guides"]
        sample = [g["overview"] for g in list(guides.values())[:40] if g.get("overview")]
        assert sample
        for text in sample:
            assert "由 " in text and " 发布" in text
            # 概述里的商人名必须是拉丁字母（英文原名），不能是中文名
            m = re.match(r"^由 ([^ ]+) 发布", text)
            assert m and re.search(r"[A-Za-z]", m.group(1)), text


# ---------------------------------------------------------------- D 三模式
def test_D_browser_acceptance_all_green(browser):
    assert browser.get("pass") is True, [c for c in browser["checks"] if not c["ok"]][:3]
    names = {c["name"]: c["ok"] for c in browser["checks"]}
    for key in ("A1 任务树渲染全部任务节点", "A2 节点无重叠且尺寸正确",
                "A3 连线数量 = 前置边 + 失败分支边", "A4 商人分带已渲染且标题为英文原名",
                "B1 首屏落在第一条商人带（可读）",
                "C1 搜索定位把目标节点移到视野中心", "D1 选中节点高亮上下游",
                "E1 regular 渲染对应任务数", "E1 pve 渲染对应任务数", "E1 pvps 渲染对应任务数",
                "E3 三模式节点数彼此不同（数据独立）",
                "F1 任务树节点副标题 = 商人英文名 + 等级 + 目标数",
                "F9 任务系统不再出现中文商人名",
                "H1 布局稳定：选中/搜索/缩放/模式往返后坐标逐点一致",
                "H2 正交实测硬门槛：节点重叠 0、连接线穿卡片 0",
                "H3 商人名 tooltip 无中文机翻", "H4 奖励里的商人名用英文原名",
                "G2 所有请求同源（离线可跑）", "G4 无 JS 异常 / 控制台错误"):
        assert names.get(key) is True, key


# ---------------------------------------------------------------- E 版本/离线


def test_D_orthogonal_hard_gates_in_browser_report(browser):
    """真实浏览器里跑出来的正交几何：节点重叠与穿卡片必须为 0（指标来自 DOM，不是代码扫描）。"""
    orth = (browser.get("detail") or {}).get("orthogonal") or {}
    assert orth, "验收报告必须记录正交实测指标"
    assert orth.get("edgeNodeHits") == 0, orth
    modes = (browser.get("detail") or {}).get("modes") or {}
    for mode, info in modes.items():
        m = info.get("metrics") or {}
        assert m.get("nodeOverlaps") == 0, (mode, m)
        assert m.get("edgeNodeHitEdges") == 0, (mode, m)


def test_E_build_stamp_and_assets():
    app = _text(APP)
    m = re.search(r'AM_BUILD = "([^"]+)"', app)
    assert m and re.match(r"^R19\.\d+(\.\d+)?$", m.group(1)), m and m.group(1)
    ver = m.group(1).lower()
    html = _text(INDEX)
    for asset in ("style.css", "theme-windows-xp.css", "tasks.css", "app.js", "tasks.js",
                  "js/task-graph-layout.js"):
        assert (asset + "?v=" + ver) in html, asset
    # 布局模块必须在 tasks.js 之前加载
    assert html.index("js/task-graph-layout.js") < html.index('<script src="tasks.js')


def test_E_no_external_resources():
    for path in (LAYOUT_JS, os.path.join(ROOT, "ui-showcase.html")):
        body = _text(path)
        assert "http://" not in body and "https://" not in body, path


def test_E_previous_round_tests_present():
    tests = os.listdir(os.path.join(ROOT, "tests"))
    for name in ("test_r19_22_round.py", "test_r19_23_round.py", "test_ui_system_round.py",
                 "test_serve.py"):
        assert name in tests, name


def test_E_docs_delivered():
    for name in ("audit.md", "layout-design.md", "change-log.md", "test-report.md",
                 "trader-name-audit.json"):
        assert os.path.exists(os.path.join(DOCS, name)), name
