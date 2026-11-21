# -*- coding: utf-8 -*-
"""R100 剧情步骤联动测试（完成时级联补齐前置 / 撤销时重置后续）。

覆盖：
  A 交互复用 —— 剧情联动复用 GWUI.dialog 与 tk-plan* 结构，取消不写状态
  B 依赖同源 —— 三态与联动计划都走 storyMissingPrereqs，不另建判断
  C 级联写入 —— 确认后一次批量写入；存储键仍是 eftmap.stories.progress.v1
  D 防御     —— 重复 id / 超长链有防护并记日志；结局分支不参与级联
  E 数据     —— 步骤 id 不与结局/分支选项 id 重叠（结构上不会误把结局当步骤）
  F ES5 约束 —— tasks.js 不出现 let/const/箭头函数/模板字符串

不启动 Chrome、不访问网络。
"""
from __future__ import annotations

import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORIES = os.path.join(ROOT, "data", "stories.json")
TASKS_JS = os.path.join(ROOT, "tasks.js")
INDEX_HTML = os.path.join(ROOT, "index.html")

BATYA = "68da36cf7cff54fc6109874a"
LS_KEY = "eftmap.stories.progress.v1"
SCRIPT_VERSION = "r19.97"


def _js():
    with open(TASKS_JS, encoding="utf-8") as f:
        return f.read()


def _doc():
    with open(STORIES, encoding="utf-8") as f:
        return json.load(f)


def _between(src, start, end):
    i = src.index(start)
    j = src.index(end, i)
    return src[i:j]


def test_story_linkage_reuses_task_dialog():
    js = _js()
    block = _between(js, "function openStoryLinkageDialog", "function requestStoryStepToggle")
    assert "window.GWUI" in block and "UI.dialog(" in block, "必须复用通用弹窗组件"
    assert '"前置步骤尚未完成"' in block
    assert '"确认并完成前置步骤"' in block
    assert '"取消"' in block

    body = _between(js, "function storyPlanBody", "function storyPlanSignature")
    for cls in (
        "tk-plan",
        "tk-plan-head",
        "tk-plan-list",
        "tk-plan-group",
        "tk-plan-item",
        "tk-plan-name",
        "tk-plan-note",
    ):
        assert cls in body, cls
    assert "tk-story-plan" not in js, "不得新增未被样式表覆盖的类名"


def test_cancel_button_has_no_side_effect():
    js = _js()
    block = _between(js, "function openStoryLinkageDialog", "function requestStoryStepToggle")
    cancel = re.search(r'\{\s*label:\s*"取消",\s*variant:\s*""\s*\}', block)
    assert cancel, "取消按钮必须是纯关闭按钮（无 onClick）"

    entry = _between(js, "function requestStoryStepToggle", "function chooseStoryOption")
    assert "saveStoryProgress" not in entry, "取消路径不得写 storage"


def test_prereq_plan_shares_status_dependency():
    js = _js()
    assert "function storyMissingPrereqs" in js
    status = _between(js, "function storyStepStatus", "function renderStoryMain")
    assert "storyMissingPrereqs(story, idx)" in status, "三态必须与联动共用同一份前置判定"
    plan = _between(js, "function planStoryPrereqFix", "function planStoryFollowUpReset")
    assert "storyMissingPrereqs(story, idx)" in plan, "联动计划也必须复用同一份判定"


def test_batch_write_is_atomic_and_isolated():
    js = _js()
    batch = _between(js, "function applyStoryStepBatch", "function executeStoryPlan")
    assert batch.count("saveStoryProgress()") == 1, "确认后应只保存一次"
    assert "JSON.stringify(state.storyProgress)" in batch, "写入前要有快照"
    assert "JSON.parse(snapshot)" in batch, "失败要回滚"
    assert "renderStory()" in batch, "写入后立即重绘三态 / 勾选 / 进度"
    assert LS_KEY in js
    assert "eftmap.tasks.progress.v1" not in batch
    assert '"regular"' in js or "'regular'" in js


def test_confirm_marks_target_and_all_prereqs():
    js = _js()
    ex = _between(js, "function executeStoryPlan", "function openStoryLinkageDialog")
    assert "plan.changes.map" in ex
    assert "ids.push(plan.stepId)" in ex, "当前步骤本身也要写入"
    assert "applyStoryStepBatch(plan.storyId, ids, true)" in ex
    assert "storyPlanSignature(fresh) !== storyPlanSignature(plan)" in ex, "确认前要复核计划"


def test_cycle_and_duplicate_id_guards_log():
    js = _js()
    assert "seen[st.id]" in js, "重复 id 只处理一次"
    assert "storyPlanLog(" in js and "console.warn" in js, "异常必须如实记日志"
    assert "1000" in js, "超长链有安全上限"


def test_ending_nodes_never_auto_completed():
    js = _js()
    plan = _between(js, "function planStoryPrereqFix", "function planStoryFollowUpReset")
    assert 'roles[st.id] === "ending"' in plan
    assert "结局分支不参与自动完成" in plan


def test_story_steps_never_reference_choice_ids():
    doc = _doc()
    batya = next(s for s in doc["stories"] if s["id"] == BATYA)
    assert len(batya["steps"]) == 38

    step_ids = [st["id"] for st in batya["steps"]]
    assert len(set(step_ids)) == len(step_ids), "步骤 id 不重复"

    for s in doc["stories"]:
        choice_keys = {c.get("key") or c.get("id") for c in s.get("choices") or []}
        for c in s.get("choices") or []:
            if c.get("role") == "ending":
                for o in c.get("options") or []:
                    choice_keys.add(o.get("value"))
                    choice_keys.add(o.get("endingKey"))
        choice_keys.discard(None)
        overlap = choice_keys & {st["id"] for st in s["steps"]}
        assert not overlap, "步骤不能与分支/结局共用 id：%s" % overlap


def test_ending_role_map_uses_real_fields():
    """choices 用 key 而不是 id；结局选项在 options[].value / endingKey 上。"""
    js = _js()
    block = _between(js, "function storyChoiceRoleMap", "function storyPlanLog")
    assert "c.key || c.id" in block
    assert "o.value" in block and "o.endingKey" in block

    doc = _doc()
    ticket = next(s for s in doc["stories"] if s["id"] == "68da33fe00868edcb6025ac4")
    ending = next(c for c in ticket["choices"] if c.get("role") == "ending")
    assert ending["key"] == "case_choice2"
    assert {o["value"] for o in ending["options"]} >= {"savior", "survivor"}


def test_tasks_js_stays_es5():
    js = _js()
    for pat in (r"\bconst\s", r"\blet\s", "=>", "`"):
        assert not re.search(pat, js), "tasks.js 必须保持 ES5：%s" % pat


def test_all_script_versions_are_bumped_together():
    """改了 tasks.js 必须同步换版本号，否则浏览器会继续用缓存里的旧实现。"""
    with open(INDEX_HTML, encoding="utf-8") as f:
        html = f.read()
    versions = re.findall(r'(?:src|href)="[^"]+\.(?:js|css)\?v=([^"]+)"', html)
    assert versions, "index.html 的脚本 / 样式必须带 ?v= 版本号"
    assert set(versions) == {SCRIPT_VERSION}, versions
    assert "tasks.js?v=%s" % SCRIPT_VERSION in html
    assert (
        "?v=r19.35" not in html and "?v=r19.36" not in html and "?v=r19.37" not in html
    ), "旧版本号必须全部替换"

    with open(os.path.join(ROOT, "app.js"), encoding="utf-8") as f:
        app = f.read()
    assert 'var AM_BUILD = "%s"' % SCRIPT_VERSION.upper() in app

    with open(os.path.join(ROOT, "tools", "serve.py"), encoding="utf-8") as f:
        serve = f.read()
    assert '"rev": "%s-"' % SCRIPT_VERSION.upper() in serve


def test_whole_step_row_counts_as_toggle():
    """按钮只有几十像素宽，点在步骤行（圆点 / 名称）上也要走同一套勾选逻辑。"""
    js = _js()
    block = _between(
        js, 'var storyStep = t.closest("[data-story-step-toggle]")', "var storyChoice"
    )
    assert 't.closest("[data-story-node]")' in block, "步骤行要参与点击委托"
    assert "requestStoryStepToggle(storyNode.dataset.storyNode)" in block


def test_story_step_marker_reuses_task_list_tick():
    """步骤前的状态标记必须是任务列表同款 db4-tick，三态映射 ✓ / ◐ / 空。"""
    js = _js()
    block = _between(js, "function renderStoryStep", "function renderStoryChoice")
    assert 'h("button", "db4-tick")' in block
    assert 'h("span", "db4-tick-mark"' in block
    assert "tk-story-dot" not in block, "步骤行不得再用旧圆点"
    assert '"✓"' in block and '"◐"' in block
    assert "tick.dataset.storyStepToggle = st.id" in block, "点标记本身也要能勾选"


def test_story_tick_css_reuses_task_style_and_drops_dead_dot_rules():
    css = os.path.join(ROOT, "tasks.css")
    with open(css, encoding="utf-8") as f:
        text = f.read()
    assert ".tk-story-node > .db4-tick" in text
    assert ".tk-story-node.is-done > .db4-tick" in text
    assert ".tk-story-node.is-done .tk-story-dot" not in text
    assert ".tk-story-node.is-avail .tk-story-dot" not in text
    assert ".tk-story-dot {" in text
    assert ".tk-story-node.is-choice .tk-story-dot" in text
    assert ".tk-story-node.is-ending .tk-story-dot" in text
