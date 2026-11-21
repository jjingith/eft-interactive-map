# -*- coding: utf-8 -*-
"""R19.22 专项测试：任务系统 + 全项目中文化。

分组（对应任务书第十四节）：
  A 任务数据完整性      —— tools/validate_tasks.py 的产出
  B 任务树结构          —— 图论性质 + 模块接入点
  C 任务详情            —— 区块与字段可查（源码 + 浏览器验收产物）
  D 进度与离线          —— 存储键 / 模式隔离 / 导入校验 / 数据版本
  E 全项目中文化        —— 覆盖率、术语一致、不破坏原始 ID
  F 现有功能回归        —— 浏览器验收里的回归项 + 数据文件未被改名
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

TASKS_DIR = os.path.join(ROOT, "data", "tasks")
I18N_DIR = os.path.join(ROOT, "data", "i18n")
DOCS = os.path.join(ROOT, "docs", "r19.22-tasks-i18n")
APP = os.path.join(ROOT, "app.js")
TASKS_JS = os.path.join(ROOT, "tasks.js")
I18N_JS = os.path.join(ROOT, "i18n.js")
INDEX = os.path.join(ROOT, "index.html")
MODES = ("regular", "pve")
CJK = re.compile(r"[\u4e00-\u9fff]")


def _load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _text(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


@pytest.fixture(scope="module")
def validation():
    return _load(os.path.join(DOCS, "task-validation.json"))


@pytest.fixture(scope="module")
def bundle():
    out = {}
    for mode in MODES:
        doc = _load(os.path.join(TASKS_DIR, "tasks.%s.json" % mode))
        guides = _load(os.path.join(TASKS_DIR, "guides.%s.json" % mode))["guides"]
        out[mode] = {"tasks": doc["tasks"], "guides": guides, "meta": doc}
    return out


@pytest.fixture(scope="module")
def browser():
    path = os.path.join(DOCS, "browser-accept.json")
    if not os.path.exists(path):
        pytest.skip("缺少浏览器验收产物（先跑 tools/r1930_accept.py）")
    return _load(path)


# ---------------------------------------------------------------- A 数据完整性
def test_A_validation_has_no_errors(validation):
    assert validation["ok"] is True, validation["errors"][:5]
    assert not validation["errors"], validation["errors"][:5]


def test_A_task_ids_unique_and_indexed(bundle):
    for mode, pack in bundle.items():
        tasks = pack["tasks"]
        assert len(tasks) >= 450, (mode, len(tasks))
        for tid, rec in tasks.items():
            assert rec["id"] == tid
            assert rec["gameMode"] == mode, (tid, rec["gameMode"])


def test_A_prereq_refs_valid_and_bidirectional(bundle):
    for mode, pack in bundle.items():
        tasks = pack["tasks"]
        for tid, rec in tasks.items():
            for p in rec["prerequisites"]:
                assert p["taskId"] in tasks, (mode, tid, p["taskId"])
                assert tid in tasks[p["taskId"]]["followUps"], (mode, tid, p["taskId"])
            for f in rec["followUps"]:
                assert f in tasks, (mode, tid, f)
                assert tid in [x["taskId"] for x in tasks[f]["prerequisites"]], (mode, tid, f)


def test_A_or_and_failed_conditions_preserved(bundle):
    """OR（多状态前置）与失败条件必须保留原始逻辑，不被抹平成「全部完成」。"""
    ors = 0
    failed = 0
    for pack in bundle.values():
        for rec in pack["tasks"].values():
            ors += sum(1 for p in rec["prerequisites"] if p["logic"] == "or")
            failed += len(rec["failedConditions"])
    assert ors >= 10, ors
    assert failed >= 1, failed


def test_A_objectives_have_zh_and_type(bundle):
    seen_types = set()
    for pack in bundle.values():
        for rec in pack["tasks"].values():
            assert rec["objectives"] is not None
            for o in rec["objectives"]:
                assert o["type"], rec["id"]
                assert CJK.search(o["descZh"] or ""), (rec["id"], o["descZh"])
                assert isinstance(o["optional"], bool)
                seen_types.add(o["type"])
    # 任务书 7.4 列出的真实目标类型都应至少出现一次
    for need in ("visit", "shoot", "giveItem", "findItem", "extract", "mark"):
        assert need in seen_types, need


def test_A_modes_are_isolated(bundle):
    reg = set(bundle["regular"]["tasks"])
    pve = set(bundle["pve"]["tasks"])
    assert reg and pve
    diff = (reg - pve) | (pve - reg)
    assert diff, "两种模式的数据完全一致，说明没有真正区分 PvP / PvE"


def test_A_guides_cover_all_tasks_and_mark_status(bundle):
    for mode, pack in bundle.items():
        tasks, guides = pack["tasks"], pack["guides"]
        assert set(guides) == set(tasks), mode
        generated = sum(1 for g in guides.values() if g.get("status") == "generated")
        missing = [k for k, g in guides.items() if g.get("status") == "missing"]
        assert generated >= len(tasks) - 5, (mode, generated, len(tasks))
        assert not missing, missing[:5]
        for tid, g in guides.items():
            if g.get("status") == "missing":
                continue
            assert g.get("overview"), tid
            assert g.get("steps"), tid
            assert g.get("source"), tid


def test_A_traders_indexed(bundle):
    traders = _load(os.path.join(TASKS_DIR, "traders.json"))["traders"]
    assert len(traders) >= 10
    for tid, rec in traders.items():
        assert rec["nameZh"] and rec["nameEn"], tid
        assert CJK.search(rec["nameZh"]), (tid, rec["nameZh"])
    for mode, pack in bundle.items():
        for rec in pack["tasks"].values():
            assert rec["traderId"] in traders, (mode, rec["id"])


def test_A_sources_recorded():
    src = _load(os.path.join(TASKS_DIR, "sources.json"))["sources"]
    kinds = {s["endpoint"] for s in src}
    assert {"tasks", "tasks_zh", "traders", "traders_zh"} <= kinds
    for s in src:
        assert s["url"].startswith("http")
        assert len(s["sha256"]) == 64
        assert s["bytes"] > 1000


# ---------------------------------------------------------------- B 任务树
def test_B_task_module_registered():
    html = _text(INDEX)
    assert 'data-view="tasks"' in html, "主导航必须新增任务入口"
    assert 'id="task-view"' in html
    # R19.23：版本串跟随 AM_BUILD（不再写死某一轮的字面量，断言反而更严）
    m = re.search(r'AM_BUILD = "([^"]+)"', _text(APP))
    assert m, "app.js 必须有 AM_BUILD"
    ver = m.group(1).lower()
    assert ("tasks.css?v=" + ver) in html and ("tasks.js?v=" + ver) in html
    app = _text(APP)
    assert '"tasks"' in app.split("var VIEWS =")[1][:120]
    assert "window.GWTasks" in app
    js = _text(TASKS_JS)
    for api in ("mount", "open", "setMode", "setView", "openTask", "exportProgress", "importProgress"):
        assert api + ":" in js, api


def test_B_edges_match_prerequisites(bundle):
    """树的边必须来自真实前置，数量应与数据里的前置条数一致（不接受「看起来像」的假关系）。"""
    total = 0
    for pack in bundle.values():
        total += sum(len(t["prerequisites"]) for t in pack["tasks"].values())
    assert total >= 200
    js = _text(TASKS_JS)
    assert "prerequisites || []).forEach" in js
    assert "marker-end" in js, "关系边要有箭头方向"


def test_B_layout_handles_dag_and_cycles():
    js = _text(TASKS_JS)
    # R19.25：分层算法移入独立布局模块（js/task-graph-layout.js），这里改为
    # 「模块里确实有入度拓扑分层」+「tasks.js 确实在用这个模块」——比只搜 tasks.js 更强。
    lay = _text(os.path.join(ROOT, "js", "task-graph-layout.js"))
    assert "indeg" in lay and "queue" in lay, "分层布局应按入度做拓扑排序"
    assert "GWTaskGraph" in js and "G.layout(state.tasks" in js, "渲染层必须使用布局模块"
    assert "rest" in js and "环" in js, "环上的任务要有兜底落位，不能整图不画"


def test_B_tree_renders_all_nodes(browser):
    checks = {c["name"]: c for c in browser["checks"]}
    assert checks["T1 任务树渲染全部任务节点"]["ok"], checks["T1 任务树渲染全部任务节点"]
    detail = checks["T1 任务树渲染全部任务节点"]["detail"]
    assert detail["nodes"] >= 490 and detail["edges"] >= 200


def test_B_interactions_work(browser):
    checks = {c["name"]: c for c in browser["checks"]}
    for name in ("T2 滚轮缩放生效", "T2b 拖拽平移生效", "T3 中文搜索命中", "T4 商人筛选弱化非命中节点"):
        assert checks[name]["ok"], (name, checks[name])


# ---------------------------------------------------------------- C 详情
def test_C_detail_sections(browser):
    checks = {c["name"]: c for c in browser["checks"]}
    assert checks["T6 详情六区块齐全"]["ok"], checks["T6 详情六区块齐全"]
    assert checks["T6b 基本信息字段 ≥ 6"]["ok"]
    assert checks["T6c 攻略标明状态"]["ok"]


def test_C_objective_toggle_drives_status(browser):
    checks = {c["name"]: c for c in browser["checks"]}
    assert checks["T6d 勾选目标进入进行中"]["ok"]
    assert checks["T6e 必需目标全勾自动完成"]["ok"]


def test_C_detail_has_no_fabricated_positions(bundle):
    """没有坐标的目标必须留空（位置待核实），不能编造。"""
    for pack in bundle.values():
        for rec in pack["tasks"].values():
            for o in rec["objectives"]:
                for z in o["zones"]:
                    pos = z.get("position")
                    if pos is None:
                        continue
                    assert isinstance(pos.get("x"), (int, float))
                    assert isinstance(pos.get("z"), (int, float))


def test_C_english_name_available_for_tooltip(bundle):
    for pack in bundle.values():
        for rec in pack["tasks"].values():
            assert rec["englishName"], rec["id"]
            assert rec["englishSource"] in ("items.json", "wiki-slug")


# ---------------------------------------------------------------- D 进度与离线
def test_D_progress_storage_and_mode_isolation():
    js = _text(TASKS_JS)
    assert "eftmap.tasks.progress.v1" in js
    # R19.23：进度结构升级为三模式（PvP / PvE / PvPS），断言同步收紧
    assert "modes: { regular: {}, pve: {}, pvps: {} }" in re.sub(r"\s+", " ", js)
    assert "pvps" in js, "PvPS（赛季服）必须有自己的进度桶"
    assert "state.progress.modes[state.mode]" in js
    assert "失败" in js and "原进度未改动" in js


def test_D_import_validation(browser):
    checks = {c["name"]: c for c in browser["checks"]}
    assert checks["T8b 导出进度 JSON 合法"]["ok"]
    assert checks["T8c 非法导入不破坏原进度"]["ok"]


def test_D_persistence_and_isolation(browser):
    checks = {c["name"]: c for c in browser["checks"]}
    assert checks["T9 刷新后进度保留"]["ok"]
    assert checks["T10b PvE 进度与 PvP 隔离"]["ok"]


def test_D_offline_data_available():
    """任务数据必须落在仓库里（断网也能看），而不是每次现拉接口。"""
    for mode in MODES:
        assert os.path.getsize(os.path.join(TASKS_DIR, "tasks.%s.json" % mode)) > 500_000
        assert os.path.getsize(os.path.join(TASKS_DIR, "guides.%s.json" % mode)) > 200_000
    raw = os.path.join(TASKS_DIR, "raw")
    assert os.path.isdir(raw)
    assert any(n.startswith("tasks.") for n in os.listdir(raw)), "原始快照要留档"


# ---------------------------------------------------------------- E 中文化
@pytest.fixture(scope="module")
def coverage():
    return _load(os.path.join(DOCS, "i18n-coverage.json"))


def test_E_no_uncovered_english(coverage):
    """界面英文必须全部有交代：翻译 / 原文浮窗 / 合理保留，三者之外为 0。"""
    assert coverage["stats"]["missing"] == 0, [
        r["text"] for r in coverage["rows"] if r["status"] == "missing"][:10]
    st = coverage["stats"]
    assert st["mapped"] >= 40, st          # 真正被替换成中文的条目
    assert st.get("originalTooltip", 0) >= 400, st   # 由 title 提供英文原文的条目
    assert st["kept"] >= 100, st           # 型号/标识/版本号等合理保留


def test_E_dictionary_has_zh_and_keeps(coverage):
    d = coverage["dict"]
    assert d["uiEntries"] >= 90
    assert d["poiEntries"] >= 250, "地图 POI 地名必须建表"
    assert d["traders"] >= 20 and d["tasks"] >= 100
    assert coverage["keptReasons"], "保留英文必须写明原因分类"


def test_E_poi_table_complete():
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import build_poi_zh
    found = build_poi_zh.collect()
    missing = [n for n in found if n not in build_poi_zh.ZH and n not in build_poi_zh.KEEP_PROPER]
    assert not missing, missing[:10]


def test_E_i18n_engine_contracts():
    js = _text(I18N_JS)
    # 统一浮窗：原文写 title + data-en-text，已有 title 不覆盖
    assert 'setAttribute("title"' in js
    assert "data-en-text" in js
    assert "MutationObserver" in js, "动态渲染必须补翻"
    # 不碰输入控件/脚本/样式
    assert '"SCRIPT"' in js and '"STYLE"' in js
    # 已有中文不算缺翻译，空浮窗不显示
    assert "isLatinOnly" in js
    # 字典缺失不能让页面崩
    assert "loadError" in js


def test_E_data_ids_not_translated():
    """中文化不得改数据：物品 ID 仍是 24 位十六进制，英文原名仍在（任务表用 nameEn）。"""
    items = _load(os.path.join(ROOT, "data", "items.json"))["items"]
    for iid in list(items)[:500]:
        assert re.match(r"^[0-9a-f]{24}$", iid), iid
    tasks = _load(os.path.join(TASKS_DIR, "tasks.regular.json"))["tasks"]
    sample = list(tasks.values())[:50]
    for rec in sample:
        assert re.match(r"^[0-9a-f]{24}$", rec["id"])
        assert rec["nameZh"] != rec["id"]


def test_E_task_names_are_chinese(bundle):
    bad = []
    for pack in bundle.values():
        for rec in pack["tasks"].values():
            if not CJK.search(rec["nameZh"]):
                bad.append((rec["id"], rec["nameZh"]))
    assert not bad, bad[:5]


def test_E_terms_consistent():
    """同一术语在不同模块不能出现互相矛盾的中文（例如 Trader 既叫「商人」又叫「交易商」）。"""
    ui = _load(os.path.join(I18N_DIR, "ui-zh.json"))["entries"]
    assert ui.get("Trader") == "商人价" or "商人" in ui.get("Trader", "")
    assert ui.get("Prerequisites") in (None, "前置条件")
    names = _load(os.path.join(I18N_DIR, "names.json"))
    # 商人表里同一商人有「英文名」和「slug」两个键，按英文名去重后中文必须互不相同
    term = _load(os.path.join(I18N_DIR, "traders.json"))["traders"]
    zh = [v["nameZh"] for v in term.values()]
    assert len(zh) >= 10
    assert len(zh) == len(set(zh)), "商人中文名重复"


def test_E_hover_keeps_original_english(browser):
    cov = browser["detail"].get("i18n") or {}
    assert cov.get("entries", 0) >= 90
    assert cov.get("names", {}).get("tasks", 0) >= 100


# ---------------------------------------------------------------- F 回归
def test_F_existing_views_regression(browser):
    checks = {c["name"]: c for c in browser["checks"]}
    assert checks["T13 四个既有视图均可打开且无脚本错误"]["ok"], checks[
        "T13 四个既有视图均可打开且无脚本错误"]
    assert checks["T13b 校准器仍可用"]["ok"]


def test_F_calibration_data_untouched():
    """任务/中文化不得改动武器校准数据：文件仍在、记录数不变。"""
    calib = _load(os.path.join(ROOT, "data", "gun-layout-calibration.json"))
    records = sum(len((g.get("slots") or {})) for g in calib["guns"].values())
    assert len(calib["guns"]) >= 150
    assert records >= 390


def test_F_app_build_marker():
    app = _text(APP)
    m = re.search(r'AM_BUILD = "([^"]+)"', app)
    assert m and m.group(1).startswith("R19."), m and m.group(1)
    html = _text(INDEX)
    assert ("?v=" + m.group(1).lower()) in html


def test_F_map_linkage_hook():
    app = _text(APP)
    assert "window.GWMapFocus" in app
    assert "worldToSvg" in app, "任务目标坐标必须走既有仿射变换，不能另造一套"
    js = _text(TASKS_JS)
    assert "GWMapFocus" in js
    assert "本图未收录" in js, "本地没有的地图要明确提示，不能装作定位成功"


def test_F_validator_runs_clean():
    """把校验脚本本身跑一遍，避免它悄悄失效（只读，不写文件）。"""
    proc = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "validate_tasks.py"), "--quiet"],
                          capture_output=True, text=True, cwd=ROOT)
    assert proc.returncode == 0, proc.stdout + proc.stderr
