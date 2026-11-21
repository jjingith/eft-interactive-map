# -*- coding: utf-8 -*-
"""R86 剧情系统专项测试。

覆盖：
  A 数据结构 —— data/stories.json schema / 10 条剧情线 / 步骤与分支
  B 真实字段 —— 门票四结局（survivor/savior/fallen/debtor）、陨落星辰前置
  C 地图联动 —— 剧情点位 id 能归属到剧情线；app.js 支持 #stories 深链
  D 剧情树 UI —— tasks.js 有第 5 个视图、展开/收起、完成标记、搜索筛选
  E 隔离性   —— 剧情进度独立 localStorage、按模式隔离；?mini=1 不加浮窗按钮
  F ES5 约束 —— tasks.js / app.js 不出现 let/const/箭头函数/模板字符串

不启动 Chrome、不访问网络。
"""
from __future__ import annotations

import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORIES = os.path.join(ROOT, "data", "stories.json")
POINTS = os.path.join(ROOT, "data", "task-points.json")
TASKS_JS = os.path.join(ROOT, "tasks.js")
APP_JS = os.path.join(ROOT, "app.js")
TASKS_CSS = os.path.join(ROOT, "tasks.css")

THE_TICKET = "68da33fe00868edcb6025ac4"
FALLING_SKIES = "68cbcdc4c964ab83cc0c928e"
HEX24 = re.compile(r"^[0-9a-f]{24}$")


def _doc():
    with open(STORIES, encoding="utf-8") as f:
        return json.load(f)


def _js(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


# ------------------------------------------------------------------ A 数据结构
def test_stories_schema_and_counts():
    doc = _doc()
    assert doc["schema"] == 1
    stories = doc["stories"]
    assert len(stories) == 10
    assert doc["counts"]["stories"] == 10
    assert doc["counts"]["steps"] >= 100
    ids = [s["id"] for s in stories]
    assert len(set(ids)) == len(ids)
    for s in stories:
        assert HEX24.match(s["id"]), s["id"]
        assert s["slug"]
        assert s["nameZh"]
        assert isinstance(s["steps"], list) and s["steps"]
        for st in s["steps"]:
            assert st["id"] and st["name"] is not None
            assert isinstance(st["order"], int)


def test_story_steps_have_stable_order():
    doc = _doc()
    for s in doc["stories"]:
        orders = [st["order"] for st in s["steps"]]
        assert orders == sorted(orders), s["id"]


# ------------------------------------------------------------------ B 真实字段
def test_ticket_has_four_real_endings():
    doc = _doc()
    ticket = next(s for s in doc["stories"] if s["id"] == THE_TICKET)
    endings = [c for c in ticket["choices"] if c["role"] == "ending"]
    assert len(endings) == 1
    ch = endings[0]
    assert ch["variableId"] == "story_the_ticket_ending"
    values = sorted(o["value"] for o in ch["options"])
    assert values == ["debtor", "fallen", "savior", "survivor"]
    # 站点的原始 value 保留，便于回溯（与中文标签顺序不一致是站点给定的）
    assert all(o.get("rawValue") for o in ch["options"])


def test_ticket_requires_falling_skies_choice():
    doc = _doc()
    ticket = next(s for s in doc["stories"] if s["id"] == THE_TICKET)
    pre_ids = [p["storyId"] for p in ticket["prerequisites"]]
    assert FALLING_SKIES in pre_ids
    pre = next(p for p in ticket["prerequisites"] if p["storyId"] == FALLING_SKIES)
    assert pre["choiceKey"]
    assert pre["options"]


def test_story_keys_match_db4tarkov_evidence():
    doc = _doc()
    by_id = {s["id"]: s for s in doc["stories"]}
    assert by_id[THE_TICKET]["storyKey"] == "story_the_ticket"
    assert by_id[FALLING_SKIES]["storyKey"] == "story_falling_skies"
    assert by_id["68da36cf7cff54fc6109874a"]["storyKey"] == "story_batya"


# ------------------------------------------------------------------ C 地图联动
def test_story_points_belong_to_known_storylines():
    with open(POINTS, encoding="utf-8") as f:
        points = json.load(f)
    known = {s["id"] for s in _doc()["stories"]}
    seen = set()
    for _map, mv in points["maps"].items():
        for g in mv.get("stories", []):
            gid = g.get("id", "")
            if not gid.startswith("story-"):
                continue
            sid = gid[6:30]
            if HEX24.match(sid):
                seen.add(sid)
    assert seen
    assert seen <= known, seen - known


def test_app_routes_story_deeplinks():
    js = _js(APP_JS)
    assert "#stories:" in js
    assert "storyRouteFromGroupId" in js
    assert "storyRouteFromHash" in js
    assert "GWTasks.openStory" in js
    # 深链必须参与首屏视图恢复与 hashchange 消费
    assert re.search(r"#stories", js)
    assert "/^#(tasks|stories)/" in js or "/^#stories:" in js


def test_marker_popup_jump_is_mini_guarded():
    js = _js(APP_JS)
    assert "markerGroupFor" in js
    assert "marker-pop-jump" in js
    seg = js[js.index("marker-pop-jump") - 500:js.index("marker-pop-jump") + 200]
    assert "state.mini" in seg, "浮窗跳转按钮必须带 !state.mini 守卫（小地图零影响）"


def test_cold_load_story_deeplink_is_consumed():
    """首屏直接打开 #stories:<id> 也要落到剧情详情（与 #tasks:<id> 同等待遇）。"""
    js = _js(APP_JS)
    assert "var deepStory = state.mini ? null : storyRouteFromHash();" in js, "小地图不消费剧情深链"
    assert "window.GWTasks.openStory(deepStory.storyId" in js
    # 与任务深链的消费位置相邻，说明走的是同一条首屏路径
    i_task = js.index("var deepTaskId = taskIdFromHash();")
    i_story = js.index("var deepStory = state.mini ? null : storyRouteFromHash();")
    assert 0 < i_story - i_task < 600
    # hashchange 路径同样要挡住小地图
    seg = js[js.index("function applyTaskHashRoute()"):js.index("function applyTaskHashRoute()") + 220]
    assert "if (state.mini) { return false; }" in seg


def test_story_map_chips_use_chinese_labels():
    """stories.json 的 maps 是 maps.json 的 key；chip 必须显示中文名而不是原始 key。"""
    js = _js(TASKS_JS)
    assert "STORY_MAP_LABELS" in js and "storyMapLabel" in js
    assert '"streets-of-tarkov": "塔科夫街区"' in js
    with open(os.path.join(ROOT, "data", "maps.json"), encoding="utf-8") as f:
        maps = json.load(f)["maps"]
    keys = {m["key"] for m in maps}
    labels = set(re.findall(r'"([a-z\-]+)": "[^"]+"', js[js.index("STORY_MAP_LABELS"):js.index("function storyMapLabel")]))
    assert keys <= labels, keys - labels


# ------------------------------------------------------------------ D 剧情树 UI
def test_tasks_js_has_story_view_and_tree_features():
    js = _js(TASKS_JS)
    assert '["story", "剧情"]' in js
    assert 'state.view === "story"' in js
    for token in ("data-story-id", "data-story-step-toggle", "data-story-choice",
                  "data-story-expand", "data-story-filter", "data-story-node"):
        assert token in js, token
    # 展开/收起阈值与搜索/筛选
    assert "STORY_STEP_LIMIT" in js
    assert "storyMatches" in js
    # 空态 / 缺数据提示
    assert "tk-story-empty" in js
    assert "dataGaps" in js
    assert "tk-story-gaps" in js


def test_tasks_js_story_progress_isolation():
    js = _js(TASKS_JS)
    assert 'eftmap.stories.progress.v1' in js
    assert 'eftmap.stories.ui.v1' in js
    # 与任务进度键不同
    assert 'eftmap.tasks.progress.v1' in js
    assert "storyProgress" in js
    # 三模式各自一份
    assert "modes: { regular: {}, pve: {}, pvps: {} }" in js


def test_tasks_css_has_story_styles():
    css = _js(TASKS_CSS)
    for cls in (".tk-story-wrap", ".tk-story-side", ".tk-story-main",
                ".tk-story-tree", ".tk-story-node", ".tk-story-opt",
                ".tk-story-gaps", ".marker-pop-jump"):
        assert cls in css, cls
    assert "@media (max-width: 860px)" in css


# ------------------------------------------------------------------ E 数据缺口
def test_data_gaps_are_reported_not_hidden():
    doc = _doc()
    gaps = doc.get("dataGaps")
    assert isinstance(gaps, list) and gaps
    kinds = {g["type"] for g in gaps}
    assert "orphan-points" in kinds or "step-without-map" in kinds
    for g in gaps:
        assert g.get("message")


# ------------------------------------------------------------------ F ES5 约束
def test_es5_only():
    """tasks.js 全文件；app.js 只查 R86 新增段（既有注释里允许出现反引号）。"""
    js = _js(TASKS_JS)
    for pat, name in [
        (re.compile(r"\blet\s"), "let"),
        (re.compile(r"\bconst\s"), "const"),
        (re.compile(r"=>"), "arrow function"),
        (re.compile(r"`"), "template literal"),
    ]:
        assert not pat.search(js), "tasks.js 含 %s" % name

    app = _js(APP_JS)
    start = app.index("function storyRouteFromGroupId")
    end = app.index("function initTaskPanel")
    seg = app[start:end]
    for pat, name in [
        (re.compile(r"\blet\s"), "let"),
        (re.compile(r"\bconst\s"), "const"),
        (re.compile(r"=>"), "arrow function"),
        (re.compile(r"`"), "template literal"),
    ]:
        assert not pat.search(seg), "app.js R86 段含 %s" % name
