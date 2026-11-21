# -*- coding: utf-8 -*-
"""R19.26 专项测试：配装插板持久化 / 装备栏紧凑化 / 任务状态联动确认。

数据来源：
  · 代码层断言（静态）——确保实现走的是"稳定身份 + 原子批量 + 确认前零写入"
  · docs/r19.26/browser-accept.json ——真实浏览器验收的逐条结果（由 tools/r1926_gear_accept.py 生成）
  · docs/r19.26/layout-before.json / layout-after.json ——左侧装备栏实测尺寸
"""
from __future__ import annotations

import json
import os
import re

import pytest

from _offline_guard import assert_offline   # R32：外部资源判据（见该模块 docstring）

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "docs", "r19.26")
APP = os.path.join(ROOT, "app.js")
TASKS = os.path.join(ROOT, "tasks.js")
INDEX = os.path.join(ROOT, "index.html")
STYLE = os.path.join(ROOT, "style.css")


def _text(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


@pytest.fixture(scope="module")
def app_js():
    return _text(APP)


@pytest.fixture(scope="module")
def tasks_js():
    return _text(TASKS)


@pytest.fixture(scope="module")
def browser():
    path = os.path.join(DOCS, "browser-accept.json")
    if not os.path.exists(path):
        pytest.skip("先运行 tools/r1926_gear_accept.py 生成真实浏览器验收结果")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(scope="module")
def layout_pair():
    before = os.path.join(DOCS, "layout-before.json")
    after = os.path.join(DOCS, "layout-after.json")
    if not (os.path.exists(before) and os.path.exists(after)):
        pytest.skip("先运行 tools/r1926_side_measure.py --tag before/after")
    return (json.load(open(before, encoding="utf-8")),
            json.load(open(after, encoding="utf-8")))


# ---------------------------------------------------------------- A 配装插板
def test_A_plate_key_carries_armor_identity(app_js):
    assert "function plateStorageKey(slotId, armorId)" in app_js
    assert 'return String(slotId) + "@" + String(armorId || "");' in app_js
    # 板位状态必须按护甲身份读取，不再用裸 `state.loadout[st.slotId]`
    assert "plateGet(st.slotId, armorId)" in app_js
    assert "state.loadout[st.slotId]" not in app_js, "禁止退回不带护甲身份的读法"
    # 安装 / 卸下走统一入口
    assert "nodeSetLoadout(node" in app_js and "plateSet(node.id, ownerArmorId, null)" in app_js


def test_A_prune_keeps_other_armors_plates(app_js):
    # 切换护甲时其它护甲的插板配置不得被 prune 删掉
    assert "if (isPlateStorageKey(key)) {" in app_js
    assert "if (!plateRecordValid(key)) { delete state.loadout[key]; }" in app_js
    # 旧格式迁移：root/zone → root/zone@armorId
    assert "旧格式迁移" in app_js and "plateStorageKey(key, parent.itemId)" in app_js


def test_A_stats_ignore_inactive_plates(app_js):
    # 重量 / 减益 / 护甲等级不得把别的护甲的插板算进来
    assert app_js.count("plateStorageActive(") >= 3, "equippedList / slotLocalPen / maxArmorClassOf 都要过滤"


def test_A_no_parallel_state_system(app_js):
    # 仍在既有 eftmap.loadout 里，不新建 localStorage 键
    assert 'LS_LOADOUT = "eftmap.loadout"' in app_js
    assert "eftmap.plate" not in app_js and "eftmap.armor.config" not in app_js
    assert "window.GWLoadout" in app_js, "测试/验收走同一份 state 的受控接口"


def test_A_browser_plate_persistence(browser):
    names = {c["name"]: c for c in browser["checks"]}
    for key in ("P1 护甲 A 的前插板已写入稳定身份键", "P1b 板位状态显示为已安装",
                "P2 切到护甲 B 后不套用 A 的插板（兼容性不被绕过）",
                "P3 切回护甲 A 后插板配置恢复", "P4 切换页面后插板配置仍在",
                "P5 刷新页面后插板配置恢复（沿用 eftmap.loadout）",
                "P6 统计不把别的护甲的插板算进来", "P7 主动卸下插板立即生效并保存"):
        assert names.get(key, {}).get("ok") is True, key


# ---------------------------------------------------------------- B 装备栏
def test_B_side_layout_compacted(layout_pair):
    before, after = layout_pair
    assert after["sideScrollH"] < before["sideScrollH"], (before["sideScrollH"], after["sideScrollH"])
    assert after["sideScrollH"] <= after["side"]["h"], "改造后不应再溢出滚动"
    assert sum(after["lineGaps"]) < sum(before["lineGaps"]), (before["lineGaps"], after["lineGaps"])
    assert after["lineGaps"] and all(g >= 0 for g in after["lineGaps"]), after["lineGaps"]
    assert not after.get("clippedText"), after.get("clippedText")


def test_B_not_achieved_by_shrinking_font():
    css = _text(STYLE)
    # R299 起布局改为 PSD 512×512 绝对坐标，不再靠压行高 / 缩字号换空间。
    assert "--lw-p: 1px;" in css
    assert "minmax(calc(26 * var(--lw-u)), auto)" not in css
    head = css[css.index(".lw-stats"):css.index(".lw-stats") + 400]
    assert "font-size" not in head, "统计条不允许用缩字号换高度"
    assert "padding: 0;" in head, "统计条按 PSD 原点定位，不再靠内边距压缩"


def test_B_browser_layout_checks(browser):
    names = {c["name"]: c for c in browser["checks"]}
    for key in ("L1 内容高下降且不再溢出滚动", "L2 相邻装备行间距全面收紧", "L3 无文本裁切"):
        assert names.get(key, {}).get("ok") is True, key


# ---------------------------------------------------------------- C 状态联动
def test_C_planner_uses_real_dependency(tasks_js):
    assert "function planPrereqFix(taskId, targetStatus)" in tasks_js
    assert "function planFollowUpReset(taskId)" in tasks_js
    # 必须走现有依赖数据，不另建简化图
    assert "rec.prerequisites" in tasks_js and "rec.followUps" in tasks_js
    assert "wantedOf(p)" in tasks_js and "satisfies(" in tasks_js
    # 失败分支不得被当成解锁边：传播只沿 followUps
    assert "rec.followUps || []" in tasks_js


def test_C_or_semantics(tasks_js):
    # OR（条目内 statuses / logic=or 组）只满足一档；不无差别全完成
    assert "function pickStatus(wants, targetStatus)" in tasks_js
    # R19.27：词面先归一（complete/failed ↔ completed/failed），再选一档
    assert "function wantStatus(w)" in tasks_js and "WANT_TO_STATUS" in tasks_js
    assert "var mapped = (wants || []).map(wantStatus).filter(Boolean);" in tasks_js
    assert 'if (mapped.indexOf("active") >= 0) { return "active"; }' in tasks_js
    # logic=or 的条目按「或组」处理，只规划一条
    assert 'String(p.logic).toLowerCase() === "or"' in tasks_js


def test_C_no_write_before_confirm(tasks_js):
    # 用户入口只弹窗；写入集中在 applyStatusBatch
    assert "function requestStatusChange(id, status)" in tasks_js
    assert "if (planA) { openLinkageDialog(planA); return; }" in tasks_js
    assert "if (planB) { openLinkageDialog(planB); return; }" in tasks_js
    # 执行前复核计划（防覆盖用户刚做的其它修改）
    assert "planSignature(fresh) !== planSignature(plan)" in tasks_js
    # 原子批量：成功路径一次 saveProgress（R19.27 起另有失败回滚分支，同样只调一次 saveProgress）
    body = tasks_js[tasks_js.index("function applyStatusBatch"):tasks_js.index("function toggleObjective(")]
    assert body.count("saveProgress()") == 1, "批量更新只允许一次落盘"
    assert "JSON.parse(snapshot)" in body, "保存失败必须回滚（R19.27）"


def test_C_dialog_uses_project_ui(tasks_js):
    assert "window.GWUI" in tasks_js and "UI.dialog" in tasks_js
    assert "确认并调整前置任务" in tasks_js
    assert "确认并重置后续任务" in tasks_js
    assert "仅重置当前任务" in tasks_js
    # 弹窗里必须列出受影响任务
    assert "tk-plan-list" in tasks_js


def test_C_mode_isolation_preserved(tasks_js):
    # 联动写入仍按当前模式分桶
    assert "state.progress.modes[state.mode]" in tasks_js
    assert "setStatusRaw(taskId, status)" in tasks_js


def test_C_browser_linkage_checks(browser):
    names = {c["name"]: c for c in browser["checks"]}
    for key in ("T1 未满足前置时弹出确认框（含确认按钮）", "T2 弹窗列出了前置任务名称",
                "T3 弹窗打开期间未提前改状态", "T4 取消后当前任务与前置全部不变",
                "T5 确认后前置被调整、当前任务变为已完成",
                "T6 重置后续确认框出现并含「仅重置当前任务」", "T7 弹窗列出直接/间接后续任务",
                "T8 「仅重置当前任务」不动后续任务", "T9 确认后后续任务被重置（真实解锁方向）",
                "T10 三模式进度隔离（同 ID 不互相污染）", "T12 刷新后 PvP 模式仍保留确认后的状态"):
        assert names.get(key, {}).get("ok") is True, key


# ---------------------------------------------------------------- D 版本 / 回归
def test_D_build_stamp_and_assets():
    app = _text(APP)
    m = re.search(r'AM_BUILD = "([^"]+)"', app)
    # R19.27：版本号断言改为跟随 AM_BUILD（不再写死某一轮），并额外要求全局模式脚本被引入
    assert m and re.match(r"^R19\.\d+(\.\d+)?$", m.group(1)), m and m.group(1)
    ver = m.group(1).lower()
    html = _text(INDEX)
    for asset in ("style.css", "app.js", "tasks.js", "tasks.css", "js/ui-components.js",
                  "js/game-mode.js"):
        assert (asset + "?v=" + ver) in html, asset
    assert ('"rev": "%s-"' % m.group(1)) in _text(os.path.join(ROOT, "tools", "serve.py"))


def test_D_no_external_resources():
    """R32 迁移判据：从「不许出现 https://」升级为「不许**加载**外部资源」。

    任务栏的「查看攻略」会给 <a> 设 tarkov.dev 地址（用户点击才跳转，页面自身不加载），
    旧判据把这种正常跳转和「页面偷偷下载外部资源」混为一谈。新判据见
    `tests/_offline_guard.py`：加载型写法一律失败 + 所有外部地址都要过白名单，
    比原来更严。
    """
    for path in (APP, TASKS):
        assert_offline(_text(path), path)


def test_D_previous_round_tests_present():
    tests = os.listdir(os.path.join(ROOT, "tests"))
    for name in ("test_r19_22_round.py", "test_r19_23_round.py", "test_r19_25_round.py",
                 "test_ui_system_round.py", "test_serve.py"):
        assert name in tests, name


def test_D_docs_delivered():
    for name in ("report.md", "layout-before.json", "layout-after.json", "browser-accept.json"):
        assert os.path.exists(os.path.join(DOCS, name)), name


def test_D_browser_offline_and_clean(browser):
    assert browser.get("pass") is True, [c for c in browser["checks"] if not c["ok"]][:3]
    names = {c["name"]: c for c in browser["checks"]}
    assert names.get("G1 所有请求同源（离线可跑）", {}).get("ok") is True
    assert names.get("G2 无 JS 异常 / 控制台错误", {}).get("ok") is True
