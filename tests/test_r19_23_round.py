# -*- coding: utf-8 -*-
"""R19.23 专项测试：任务系统三模式（PvP / PvE / PvPS 赛季服）。

分组（对应任务书第十一节 A–G）：
  A 模式切换        —— 按钮定义、状态结构、切换不清空进度、浏览器实测
  B 数据完整性      —— 三套独立数据集、引用有效、来源可核、抓取失败不覆盖
  C 模式差异        —— 三对差异报告、集合差与字段差可复核、不按名称合并
  D 进度隔离        —— 三套进度互不影响、导入导出、刷新保留
  E 任务树          —— 节点/边与模式数据一致、AND/OR/失败分支可区分
  F 任务详情与攻略  —— 按模式取数、攻略按模式生成、地图联动用当前模式目标
  G 回归            —— 既有视图/校准器/深链/旧测试仍在

浏览器部分读 tools/r1931_accept.py 的产物 docs/r19.23/browser-accept.json，
不在 pytest 里重复启动 Chrome（避免测试互相抢端口）；若产物缺失则跳过并明确提示。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

TASKS_DIR = os.path.join(ROOT, "data", "tasks")
RAW_DIR = os.path.join(TASKS_DIR, "raw")
DOCS = os.path.join(ROOT, "docs", "r19.23")
TASKS_JS = os.path.join(ROOT, "tasks.js")
TASKS_CSS = os.path.join(ROOT, "tasks.css")
INDEX_HTML = os.path.join(ROOT, "index.html")
APP_JS = os.path.join(ROOT, "app.js")
MODES = ("regular", "pve", "pvps")
UPSTREAM = {"regular": "regular", "pve": "pve", "pvps": "pvp-season"}
CJK = re.compile(r"[\u4e00-\u9fff]")


def _load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _text(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


@pytest.fixture(scope="module")
def packs():
    out = {}
    for mode in MODES:
        out[mode] = {
            "doc": _load(os.path.join(TASKS_DIR, "tasks.%s.json" % mode)),
            "guides": _load(os.path.join(TASKS_DIR, "guides.%s.json" % mode))["guides"],
        }
    return out


@pytest.fixture(scope="module")
def index():
    return _load(os.path.join(TASKS_DIR, "index.json"))


@pytest.fixture(scope="module")
def diff():
    return _load(os.path.join(TASKS_DIR, "diff-report.json"))


@pytest.fixture(scope="module")
def browser():
    path = os.path.join(DOCS, "browser-accept.json")
    if not os.path.exists(path):
        pytest.skip("缺少浏览器验收产物（先跑 tools/r1931_accept.py）")
    return _load(path)


@pytest.fixture(scope="module")
def browser_checks(browser):
    return {c["name"]: c["ok"] for c in browser["checks"]}


# ---------------------------------------------------------------- A 模式切换
def test_A_three_modes_declared_in_frontend():
    js = _text(TASKS_JS)
    keys = re.findall(r'\{\s*key:\s*"(regular|pve|pvps)"', js)
    assert set(keys) == set(MODES), keys
    assert 'label: "PvPS（赛季服）"' in js, "赛季服按钮必须写明「PvPS（赛季服）」"
    assert 'en: "PVP SEASONAL' in js, "赛季服必须有英文原称悬停提示"
    # 模式按钮容器右上角（flex 末尾 + 不参与换行）
    css = _text(TASKS_CSS)
    assert ".tk-modebar" in css and "margin-left: auto" in css
    assert "flex-wrap: nowrap" in css, "标题行不允许换行，避免模式按钮被挤到第二行"


def test_A_mode_switch_is_mode_scoped_not_destructive():
    js = _text(TASKS_JS)
    # 切换模式只换指针 + 恢复该模式状态，不清空任何进度
    setmode = js[js.index("function setMode(mode)"):js.index("function open()")]
    assert "snapshotMode()" in setmode and "restoreMode(mode)" in setmode
    assert "progress" not in setmode, "setMode 不得触碰进度数据"
    # 每个模式独立缓存，切换不重新下载
    assert "state.cache[mode]" in js and "state.pending[mode]" in js
    assert "内存缓存，即时生效" in js


def test_A_progress_structure_has_three_modes():
    js = _text(TASKS_JS)
    norm = re.sub(r"\s+", " ", js)
    assert "modes: { regular: {}, pve: {}, pvps: {} }" in norm
    assert "MODE_KEYS.forEach(function (m) { modes[m] = doc.modes[m] || {}; })" in norm, \
        "读旧进度必须补全三模式（迁移不丢 PvP/PvE 记录）"


def test_A_browser_mode_buttons(browser_checks):
    # R19.27：模式控件升级为全应用（页头右上角），A3 检查名随之升级（断言更强：要求在 menubar 内）
    for name in ("A1 右上角三个模式按钮齐全", "A2 初始选中 PvP（唯一选中态）",
                 "A3 模式按钮固定在全局页头右上角（R19.27）", "A4 按钮文字为 PvP / PvE / PvPS（赛季服）",
                 "A5 按钮带英文悬停提示", "A6 四个内页都保持三模式按钮可见且位置不变"):
        assert browser_checks.get(name) is True, name


# ---------------------------------------------------------------- B 数据完整性
def test_B_three_independent_datasets(packs, index):
    sizes = {}
    for mode in MODES:
        doc = packs[mode]["doc"]
        assert doc["mode"] == mode
        assert doc["upstreamGameMode"] == UPSTREAM[mode], (mode, doc.get("upstreamGameMode"))
        assert doc["counts"]["tasks"] == len(doc["tasks"])
        assert doc["counts"]["tasks"] > 400, (mode, doc["counts"])
        sizes[mode] = doc["counts"]["tasks"]
    assert len(set(sizes.values())) == 3, "三模式任务数完全相同 → 疑似复制数据：%s" % sizes
    assert index["modeOrder"] == list(MODES)
    assert index["modes"]["pvps"]["upstream"] == "pvp-season"


def test_B_pvps_is_not_a_renamed_copy(packs):
    """PvPS 必须是独立端点产物：文件哈希不同、任务集合不同、至少有一处字段差异。"""
    hashes = {}
    for mode in MODES:
        with open(os.path.join(TASKS_DIR, "tasks.%s.json" % mode), "rb") as fh:
            hashes[mode] = hashlib.sha256(fh.read()).hexdigest()
    assert len(set(hashes.values())) == 3, hashes
    pvp_ids = set(packs["regular"]["doc"]["tasks"])
    pvps_ids = set(packs["pvps"]["doc"]["tasks"])
    assert pvp_ids != pvps_ids
    assert pvps_ids - pvp_ids == set(), "当前快照 pvps 不应出现 PvP 未收录的任务（若上游新增需更新本断言）"


def test_B_sources_point_to_real_upstream(index):
    sources = _load(os.path.join(TASKS_DIR, "sources.json"))
    per_mode = {}
    for rec in sources["sources"]:
        if rec["endpoint"] == "tasks":
            per_mode.setdefault(rec["mode"], []).append(rec)
    for mode in MODES:
        assert mode in per_mode, mode
        rec = per_mode[mode][0]
        assert UPSTREAM[mode] in rec["url"], (mode, rec["url"])
        assert len(rec["sha256"]) == 64 and rec["bytes"] > 100_000
        assert rec["fetchedAt"]
    assert "pvp-season" in json.dumps([r["url"] for r in sources["sources"] if r["mode"] == "pvps"])


def test_B_season_metadata_present():
    season = _load(os.path.join(TASKS_DIR, "season.json"))
    assert re.match(r"^[0-9a-f]{24}$", season["id"])
    assert season["startISO"] and season["endISO"]
    assert season["start"] < season["end"]
    assert season["perks"]["common"] or season["perks"]["personal"]
    # 上游只给占位串：中文表有时只有英文原名 → 保留原名并标记缺译名，不得凭空造中文名
    assert season["nameEn"], "赛季英文原名不应为空"
    if season["nameZh"]:
        assert CJK.search(season["nameZh"]), season["nameZh"]
    else:
        assert season["nameZhMissing"] is True, "没有中文译名时必须显式标记，界面才能如实提示"


def test_B_season_only_flags_consistent(packs):
    """seasonOnly 只能出现在 pvps；且必须等于「只出现在 pvps」的真实集合。"""
    ids = {m: set(packs[m]["doc"]["tasks"]) for m in MODES}
    only_pvps = ids["pvps"] - ids["regular"] - ids["pve"]
    flagged = {tid for tid, rec in packs["pvps"]["doc"]["tasks"].items() if rec["seasonOnly"]}
    assert flagged == only_pvps, (len(flagged), len(only_pvps))
    for mode in ("regular", "pve"):
        assert not any(r["seasonOnly"] for r in packs[mode]["doc"]["tasks"].values())
    # onlyInModes 与实际集合一致
    for mode in MODES:
        for tid, rec in packs[mode]["doc"]["tasks"].items():
            expect = sorted(m for m in MODES if tid in ids[m])
            if rec["onlyInModes"]:
                assert sorted(rec["onlyInModes"]) == expect, (mode, tid)


def test_B_validator_runs_clean():
    proc = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "validate_tasks.py"),
                           "--quiet"], capture_output=True, text=True, cwd=ROOT)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_B_fetch_failure_keeps_previous_snapshot(tmp_path, monkeypatch):
    """抓取失败时必须保留旧快照（不写空文件、不删已有数据）。"""
    import fetch_tasks as ft

    raw = tmp_path / "raw"
    raw.mkdir()
    keep = ["tasks.regular.json", "tasks_zh.regular.json", "tasks.pve.json", "tasks_zh.pve.json",
            "tasks.pvps.json", "tasks_zh.pvps.json", "traders.regular.json", "traders_zh.regular.json"]
    for name in keep:
        shutil.copy(os.path.join(ft.RAW_DIR, name), raw / name)
    before = {n: hashlib.sha256((raw / n).read_bytes()).hexdigest() for n in keep}

    monkeypatch.setattr(ft, "RAW_DIR", str(raw))

    def boom(url, timeout=180):
        raise RuntimeError("模拟断网")

    monkeypatch.setattr(ft, "_fetch", boom)
    sources = ft.fetch_raw(offline=False)
    after = {n: hashlib.sha256((raw / n).read_bytes()).hexdigest() for n in keep}
    assert before == after, "抓取失败不得改动已有快照"
    assert all(s.get("error") for s in sources), "失败必须记录 error"
    assert all(s.get("stale") for s in sources), "失败必须标记 stale（正在用旧快照）"


def test_B_missing_snapshot_and_failure_aborts(tmp_path, monkeypatch):
    import fetch_tasks as ft
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setattr(ft, "RAW_DIR", str(empty))

    def boom(url, timeout=180):
        raise RuntimeError("模拟断网")

    monkeypatch.setattr(ft, "_fetch", boom)
    with pytest.raises(SystemExit):
        ft.fetch_raw(offline=False)


def test_B_invalid_json_does_not_overwrite(tmp_path, monkeypatch):
    """上游返回 HTTP 200 但内容是错误页时，也不能覆盖快照。"""
    import fetch_tasks as ft
    raw = tmp_path / "raw"
    raw.mkdir()
    name = "tasks.regular.json"
    good = b'{"data": {"tasks": {}}}'
    # 其它必需快照先放占位，确保本用例只考察「坏响应不覆盖」这一条
    for other in ("tasks_zh.regular.json", "tasks.pve.json", "tasks_zh.pve.json",
                  "tasks.pvps.json", "tasks_zh.pvps.json",
                  "traders.regular.json", "traders_zh.regular.json"):
        (raw / other).write_bytes(b'{"data": {}}')
    (raw / name).write_bytes(good)
    monkeypatch.setattr(ft, "RAW_DIR", str(raw))
    monkeypatch.setattr(ft, "_fetch", lambda url, timeout=180: b"<html>502</html>")
    sources = ft.fetch_raw(offline=False)
    assert (raw / name).read_bytes() == good
    assert any(s.get("stale") for s in sources)


# ---------------------------------------------------------------- C 模式差异
def test_C_diff_report_covers_three_pairs(diff, packs):
    pairs = {"%s|%s" % (p["left"], p["right"]): p for p in diff["pairs"]}
    assert set(pairs) == {"regular|pve", "regular|pvps", "pve|pvps"}
    for key, p in pairs.items():
        left, right = key.split("|")
        assert p["counts"]["tasks"]["left"] == len(packs[left]["doc"]["tasks"])
        assert p["counts"]["tasks"]["right"] == len(packs[right]["doc"]["tasks"])
        assert p["counts"]["onlyLeft"] == len(p["onlyLeftTasks"])
        assert p["counts"]["onlyRight"] == len(p["onlyRightTasks"])


def test_C_only_sets_match_real_set_difference(diff, packs):
    for p in diff["pairs"]:
        left = set(packs[p["left"]]["doc"]["tasks"])
        right = set(packs[p["right"]]["doc"]["tasks"])
        assert {t["id"] for t in p["onlyLeftTasks"]} == left - right
        assert {t["id"] for t in p["onlyRightTasks"]} == right - left


def test_C_field_diffs_are_locatable(diff):
    """每条差异都要能定位：任务 ID + 字段路径 + 两边原值 + 来源。"""
    total = 0
    for p in diff["pairs"]:
        for d in p["fieldDiffs"]:
            assert re.match(r"^[0-9a-f]{24}$", d["taskId"]), d
            assert d["nameZh"], d
            assert d["path"]
            assert "left" in d and "right" in d
            assert d["leftSource"].endswith("tasks.%s.json" % p["left"])
            assert d["rightSource"].endswith("tasks.%s.json" % p["right"])
            total += 1
        # 一个任务可能有多条字段差异，因此条目数 >= 有差异的任务数
        if p["counts"]["sameIdWithDiff"] == 0:
            assert p["fieldDiffs"] == []
        else:
            assert len(p["fieldDiffs"]) >= 1
            assert len({d["taskId"] for d in p["fieldDiffs"]}) == p["counts"]["sameIdWithDiff"]
    assert total > 0, "三种模式之间必须存在可定位的字段差异"


def test_C_no_merging_by_name(packs, diff):
    """同名不同 ID 绝不合并：差异只按 ID 判定，同名任务在两边各自独立计数。"""
    for mode in MODES:
        names = {}
        for tid, rec in packs[mode]["doc"]["tasks"].items():
            names.setdefault(rec["nameZh"], []).append(tid)
        dups = {k: v for k, v in names.items() if len(v) > 1}
        # 同模式内确实存在同名不同 ID（参考数据事实），它们必须各占一个任务位
        for name, ids in dups.items():
            assert len(set(ids)) == len(ids)
            for tid in ids:
                assert packs[mode]["doc"]["tasks"][tid]["id"] == tid
    # 差异报告里不允许出现「用名字对齐」的痕迹：右侧任务集合必须按 ID 计算
    for p in diff["pairs"]:
        for t in p["onlyLeftTasks"]:
            assert t["id"] not in {x["id"] for x in p["onlyRightTasks"]}


def test_C_report_markdown_written():
    md = _text(os.path.join(DOCS, "diff-report.md"))
    for needle in ("数据规模", "配对差异汇总", "同 ID 但字段不同", "无法确认的部分"):
        assert needle in md, needle
    assert "pvp-season" in md


# ---------------------------------------------------------------- D 进度隔离
def test_D_progress_isolated_per_mode():
    js = _text(TASKS_JS)
    assert "function progOf(taskId)" in js
    assert "state.progress.modes[state.mode]" in js, "进度读写必须按当前模式取桶"
    # 三模式进度各自独立：不允许出现「写入时同步到其它模式」
    # R19.26：写入面 = setStatusRaw（内存改）+ toggleObjective，均只写当前模式；
    # setStatus/applyStatusBatch 是它们之上的薄封装，不再重复取桶。
    body = js[js.index("function setStatusRaw(taskId, status)"):js.index("function broadcast()")]
    # 每个写函数各出现两次（取值 + 懒建桶），共两处函数 → 4 次，且不出现任何写死的模式名
    assert body.count("state.progress.modes[state.mode]") == 4, "进度桶必须按 state.mode 取，不能写死模式"
    assert "function setStatus(taskId, status)" in body and "function applyStatusBatch(" in body
    assert "modes.regular" not in body and "modes.pve" not in body and "modes.pvps" not in body


def test_D_export_import_keep_mode_flag():
    js = _text(TASKS_JS)
    assert "activeMode: state.mode" in js
    assert "MODE_KEYS.forEach(function (m) { clean[m] = {}; })" in js
    assert "未知模式" in js
    assert "原进度未改动" in js


def test_D_browser_isolation(browser_checks):
    for name in ("D1 PvP 勾满必需目标后自动完成", "D2 同名任务在 PvE 不会被连带完成",
                 "D3 PvE 自己改状态有效（不与 PvP 混）", "D4 PvPS 两个任务都是独立空白进度",
                 "D5 进度页有三模式对照表且标出当前模式", "D6 刷新后三模式各自状态都保留",
                 "D7 导出进度含三个模式段", "D8 非法导入不破坏已有进度",
                 "D9 合法导入按模式分别落盘"):
        assert browser_checks.get(name) is True, name


def test_D_progress_keyed_by_task_id_only(packs):
    """进度只用任务 ID 关联（不存中文名/序号），重抓数据后仍能对上。"""
    js = _text(TASKS_JS)
    body = js[js.index("function setStatus(taskId, status)"):js.index("function toggleObjective")]
    assert "nameZh" not in body and "indexOf" not in body
    for mode in MODES:
        for tid in list(packs[mode]["doc"]["tasks"])[:200]:
            assert re.match(r"^[0-9a-f]{24}$", tid)


# ---------------------------------------------------------------- E 任务树
def test_E_tree_draws_three_edge_kinds():
    js = _text(TASKS_JS)
    # R19.25：边类型由布局模块给出，渲染层直接透传 e.kind（and/or/fail），
    # 断言改为「三类都要有对应类名与箭头」，比只搜一个三元表达式更完整。
    assert '"data-kind": e.kind' in js
    for cls in ("is-or", "is-fail"):
        assert ('cls += " %s"' % cls) in js, cls
    assert '["tk-arrow", "tk-arrow-head"]' in js and '"tk-arrow-fail"' in js, "三类箭头都要有"
    css = _text(TASKS_CSS)
    assert ".tk-edge.is-or" in css and ".tk-edge.is-fail" in css
    assert ".tk-legend-line.is-fail" in css, "图例必须有失败分支样式（不只靠颜色）"


def test_E_tree_nodes_are_mode_scoped(browser_checks, browser, packs):
    for mode in MODES:
        for kind in ("任务树节点数 = 数据任务数", "关系边数 = 前置边 + 失败分支边",
                     "赛季专属节点标记与数据一致"):
            key = [k for k in browser_checks if k.startswith("B") and kind in k
                   and (" %s " % mode) in k]
            assert key and browser_checks[key[0]] is True, (mode, kind)
    trees = browser["detail"]["trees"]
    assert set(trees) == set(MODES)
    for mode in MODES:
        assert trees[mode]["nodes"] == packs[mode]["doc"]["counts"]["tasks"], mode


def test_E_browser_interactions(browser_checks):
    for name in ("B4 三种模式任务数彼此不同（不是同一份数据改名）", "B5 PvPS 树内搜索命中",
                 "B6 PvPS 树滚轮缩放生效", "B7 PvPS 树拖拽平移生效",
                 "B8 Kappa 筛选在 PvPS 上可用（命中数与数据一致）"):
        assert browser_checks.get(name) is True, name


def test_E_mode_badge_uses_shape_not_only_color():
    js = _text(TASKS_JS)
    # 赛季/仅本模式标记同时用文字 + 形态（节点角标文本「赛季」）
    assert 'sf.textContent = "赛季"' in js, "赛季节点要有文字角标"
    assert '"tk-node-flag is-season"' in js, "角标要有独立样式（形状+颜色双通道）"
    assert 'tipBits.push("赛季专属任务")' in js, "悬停提示要说明赛季专属"
    css = _text(TASKS_CSS)
    assert ".tk-node-flag.is-season" in css


# ---------------------------------------------------------------- F 详情与攻略
def test_F_guides_exist_per_mode(packs):
    for mode in MODES:
        guides = packs[mode]["guides"]
        assert set(guides) == set(packs[mode]["doc"]["tasks"]), mode
        statuses = {g.get("status") for g in guides.values()}
        assert statuses <= {"generated", "curated", "missing"}, statuses
        missing = [k for k, g in guides.items() if g.get("status") == "missing"]
        assert len(missing) <= 5, (mode, missing[:5])


def test_F_detail_is_mode_aware():
    js = _text(TASKS_JS)
    assert '["当前模式", modeLabel()]' in js
    assert '["模式归属", modeScopeShort(rec), "scopeShort", modeScopeText(rec)]' in js
    # R72：模式归属改成短标签 + title 悬浮说明，长解释不再进正文。
    assert "function modeScopeShort(rec)" in js
    # R73：title 在触屏/无 hover 环境读不到 → 改为点击展开的行内短说明（绝对定位不撑高）。
    assert 'h("dd", "tk-fact-scope")' in js
    assert '"tk-scope-toggle"' in js
    assert '"tk-fact-note"' in js
    # 旧实现（title 悬浮）必须已移除，避免两套说明并存
    assert 'dd.title = kv[3]' not in js
    # R32：「详情页 footer 里写着来源 data/tasks/guides.<mode>.json」那句已收进菜单「关于」，
    # 所以改为直接盯**取数处**——断言「按模式取攻略」这件事本身，而不是某句说明文案。
    assert 'data/tasks/guides." + mode + ".json' in js
    assert "赛季结束后请勿把旧赛季的完成状态当作新赛季进度" in js


def test_F_map_linkage_uses_current_mode_task():
    js = _text(TASKS_JS)
    body = js[js.index("function locateZone(zone, rec, obj)"):js.index("// ---------------------------------------------------------------- 渲染总控")]
    assert "window.GWMapFocus" in body
    assert "本图未收录" in body, "本地没有的地图必须明确提示，不能假装定位成功"
    # 定位来源必须是当前模式的 state.tasks
    assert "function locateSelected()" in js and "task(state.selected)" in js


def test_F_browser_detail_and_season(browser_checks):
    for name in ("C2 pve 详情页「当前模式」与本模式一致", "C2 pvps 详情页「当前模式」与本模式一致",
                 "C2 regular 详情页「当前模式」与本模式一致",
                 "E1 PvPS 数据来自上游 pvp-season 端点", "E3 赛季元信息可读（赛季 id + 起止时间）",
                 "E4 赛季专属任务计数与上游一致（当前 0 条，不伪造）",
                 "E5 界面如实说明「PvPS 是 PvP 子集、无赛季专属任务」",
                 "E6 赛季专属筛选项不出现（无数据时不做假筛选）",
                 "F4 详情页保留原始英文名字段（有意的英文展示）",
                 "F5 PvPS 详情可跳转地图并落点（用本模式目标坐标）"):
        assert browser_checks.get(name) is True, name


def test_F_no_fake_filters():
    """没有数据支撑的筛选项一律不做（当前数据里没有 DSPT 字段）。"""
    js = _text(TASKS_JS)
    block = js[js.index('selectEl("tk-special"'):js.index('var lvWrap')]
    assert "DSPT" not in block and "dspt" not in block, \
        "上游无 DSPT 字段时不得照抄参考站的假筛选项"
    assert '"season"' in block, "赛季专属筛选（有数据时才出现）必须在这个下拉里"
    raw = _text(os.path.join(TASKS_DIR, "tasks.regular.json"))
    assert "dspt" not in raw.lower()


# ---------------------------------------------------------------- G 回归
def test_G_browser_regression(browser_checks):
    for name in ("G1 四个既有视图可打开且无脚本错误", "G2 武器槽位校准器仍可用",
                 "G3 校准数据文件仍在且可解析", "G4 #tasks 深链仍可直达任务模块",
                 "C1 pvps 商人列表使用本模式数据（标题+行数）",
                 "C3 pvps 任务树节点/边来自本模式"):
        assert browser_checks.get(name) is True, name


def test_G_build_stamp_and_assets():
    # R19.24 起不再把某轮的版本号写死在测试里（否则每轮都要改测试）：
    # 改为「构建标记必须形如 R19.N，且所有资源版本串都跟着它走」——断言反而覆盖更多资源。
    app = _text(APP_JS)
    m = re.search(r'AM_BUILD = "([^"]+)"', app)
    assert m and re.match(r"^R19\.\d+(\.\d+)?$", m.group(1)), m and m.group(1)
    ver = m.group(1).lower()
    html = _text(INDEX_HTML)
    assert ("?v=" + ver) in html
    for asset in ("tasks.css", "tasks.js", "i18n.js", "app.js", "calibrator.js"):
        assert asset + "?v=" + ver in html, asset


def test_G_previous_round_tests_still_present():
    tests = os.listdir(os.path.join(ROOT, "tests"))
    for name in ("test_r19_16_round.py", "test_r19_17_round.py", "test_r19_18_round.py",
                 "test_r19_19_round.py", "test_r19_20_round.py", "test_r19_21_round.py",
                 "test_r19_22_round.py", "test_r6_gun_workbench.py", "test_serve.py"):
        assert name in tests, name


def test_G_calibration_data_untouched_by_this_round():
    path = os.path.join(ROOT, "data", "gun-layout-calibration.json")
    assert os.path.exists(path), "R19.17 起校准数据必须保留"
    data = _load(path)
    assert data, "校准数据不得被清空"
    # 本轮只读：相关工具脚本不得写入该文件
    for tool in ("fetch_tasks.py", "validate_tasks.py", "diff_tasks.py"):
        body = _text(os.path.join(ROOT, "tools", tool))
        assert "gun-layout-calibration" not in body, tool


def test_G_i18n_zero_gaps():
    proc = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "build_i18n.py")],
                          capture_output=True, text=True, cwd=ROOT)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "未覆盖 0" in proc.stdout, proc.stdout[-400:]
