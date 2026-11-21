# -*- coding: utf-8 -*-
"""R212：右侧任务 / 剧情栏改成「标点图层」勾选。

静态断言锁定界面结构（标题与旧控件撤除、两个分组 × 完成状态、独立可并行推进），
再用 Node 直接跑 app.js 里抽出来的判定函数，验证勾选真的同时约束地图标点与任务列表。
"""
from __future__ import annotations

import json
import os
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
XP_CSS = os.path.join("assets", "xp-ui", "xp-ui-app.css")


def _read(rel: str) -> str:
    with open(os.path.join(ROOT, rel), "r", encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------- 静态结构

def test_title_and_legacy_filters_are_gone():
    html = _read("index.html")
    assert "<h2>任务 / 剧情目标" not in html
    assert 'id="task-count"' not in html
    for legacy in (
        'id="task-show-all"', 'id="task-show-names"', 'id="task-filter-note"',
        'name="task-point-filter"', "task-filter-opt", "task-name-toggle",
        "task-master-toggle",
    ):
        assert legacy not in html, "旧控件仍在页面上：%s" % legacy
    # 收起按钮必须保留：右侧栏仍要能折叠
    assert 'id="task-panel-collapse"' in html


def test_two_groups_with_completion_subtoggles_and_parallel():
    html = _read("index.html")
    assert 'id="task-layer-toggles"' in html
    for group in ("普通任务", "剧情任务"):
        assert "<span class=\"legend-group-title\">%s</span>" % group in html
    for kind in ("tasks", "stories"):
        for st in ("done", "todo"):
            assert 'data-task-layer-row="%s:%s"' % (kind, st) in html
            assert 'data-task-layer="%s" data-task-state="%s"' % (kind, st) in html
            assert 'id="task-layer-count-%s-%s"' % (kind, st) in html
        assert 'data-task-layer-fold="%s"' % kind in html
        assert 'id="task-layer-body-%s"' % kind in html
        assert 'id="task-group-count-%s"' % kind in html
    # 图标与左侧图例同款 PNG（不是 XP 皮肤下的方形色点）
    assert html.count("map-task-point.png") == 2
    assert html.count("map-story-point.png") == 2
    # 独立的「可并行推进」：在两个分组之外，默认不勾
    assert 'id="task-parallel-only"' in html
    assert "checked" not in html.split('id="task-parallel-only"')[1][:80]
    assert html.index('id="task-parallel-only"') > html.index('data-task-layer-fold="stories"')
    assert html.index('id="task-list"') > html.index('id="task-parallel-only"')


def test_quest_layer_group_moved_out_of_left_sidebar():
    app = _read("app.js")
    # LAYER_SPEC 仍保留 quests 组：地图绘制 / 计数 / 配置合并都依赖它
    assert '{ id: "quests", group: "任务 / 剧情"' in app
    assert 'if (group.id === "quests") { return; }' in app
    # 旧四档筛选、总闸、名字开关的绑定与状态全部撤除
    for dead in (
        "TASK_FILTERS", "LS_TASK_POINTS_MASTER", "LS_TASK_POINT_FILTER",
        "taskPointsMaster", "taskPointFilter", "taskFilterPass",
        "el.taskShowAll", "el.taskShowNames", "el.taskFilterNote",
        "el.taskCount", "taskFilterInputs",
    ):
        assert dead not in app, "旧筛选逻辑仍在：%s" % dead


def test_layer_checks_drive_both_list_and_map():
    app = _read("app.js")
    # 列表与地图共用同一套准入函数，避免两边各算一套
    assert "if (!taskListPass(g.kind, g.id)) { return false; }" in app
    assert "if (!taskListPass(kind, id)) { return false; }" in app
    assert "return taskLayerOn(kind, id) && taskParallelPass(kind, id);" in app
    assert "syncTaskLayerMaster(merged);" in app          # 服务端回声不能改回去
    assert "renderTaskPanel();          // 下面的列表跟着勾选变" in app
    # 整组从全关恢复时该层节点当初没建出来，必须重建覆盖层而不是只切显隐
    assert "var layerChanged = TASK_LAYER_KINDS.some(function (k) {" in app
    assert "if (layerChanged) { renderOverlay(); } else { applyTaskPointDisplay(); }" in app
    # 默认：四个勾选全开，可并行推进关
    assert "taskLayerFilters: { tasks: { done: true, todo: true }, stories: { done: true, todo: true } }" in app
    assert 'state.taskParallelOnly = parallel === "1";' in app


def test_styles_reuse_left_legend_skin():
    css = _read("style.css")
    xp = _read(XP_CSS)
    for dead in (".task-filter {", ".task-filter-opt {", ".task-filter-note {",
                 ".task-master-toggle {", ".task-name-toggle {"):
        assert dead not in css, "旧控件样式仍在：%s" % dead
    assert ".task-layer-toggles {" in css
    assert ".task-parallel-toggle {" in css
    # 右侧图例行 / 折叠头与左侧共用同一条 XP 皮肤规则
    assert "html body #task-layer-toggles .legend-item," in xp
    assert "html body #task-layer-toggles .legend-group-toggle {" in xp


# ---------------------------------------------------------------- JS 行为

JS_HARNESS = r"""
const fs = require('fs');
const src = fs.readFileSync('app.js', 'utf8');

/* 按名字抠出函数声明（花括号配平；跳过字符串与注释）。 */
function extractFn(name) {
  const i = src.indexOf('function ' + name + '(');
  if (i < 0) throw new Error('missing function ' + name);
  let depth = 0, started = false, quote = null;
  for (let k = i; k < src.length; k++) {
    const c = src[k];
    if (quote) { if (c === '\\') { k++; continue; } if (c === quote) quote = null; continue; }
    if (c === '"' || c === "'" || c === '`') { quote = c; continue; }
    if (c === '/' && src[k + 1] === '/') { while (k < src.length && src[k] !== '\n') k++; continue; }
    if (c === '/' && src[k + 1] === '*') { k = src.indexOf('*/', k + 2) + 1; continue; }
    if (c === '{') { depth++; started = true; }
    else if (c === '}') { depth--; if (started && depth === 0) return src.slice(i, k + 1); }
  }
  throw new Error('unbalanced function ' + name);
}

const names = ['taskPointStorageKey', 'taskStatusOf', 'taskPrereqSatisfied',
  'taskGroupDone', 'taskStateKey', 'taskLayerOn', 'taskParallelPass',
  'taskListPass', 'taskPointSwitchOn', 'taskGroupVisible', 'syncTaskLayerMaster'];
const bundle = names.map(extractFn).join('\n');

const TASK_LAYER_KINDS = ['tasks', 'stories'];
const TASK_LAYER_STATES = ['done', 'todo'];
let storyDone = {};
function storyStatusOfGroup(id) { return storyDone[id] ? 'done' : 'none'; }

const state = {
  dataScope: { mode: 'pvp' },
  taskProgressSnap: {},
  taskPointSwitches: {},
  taskMetaByMode: { pvp: { hasPrereq: true, prereq: {} } },
  taskLayerFilters: { tasks: { done: true, todo: true }, stories: { done: true, todo: true } },
  taskParallelOnly: false,
  taskFocus: null,
  layers: { tasks: true, stories: true }
};

eval(bundle);

/* 夹具：普通任务的完成 / 进行中 / 失败 / 未开始，剧情点的完成 / 未完成，
   以及一条前置未满足的任务。 */
state.taskProgressSnap = {
  qDone: { status: 'completed' },
  qActive: { status: 'active' },
  qFailed: { status: 'failed' },
  qBlocked: { status: 'none' }
};
state.taskProgressSnap.qPre = { status: 'completed' };
state.taskMetaByMode.pvp.prereq = {
  qActive: [{ taskId: 'qPre', logic: 'and' }],          // 前置已完成 → 可并行
  qBlocked: [{ taskId: 'qNeverDone', logic: 'and' }]    // 前置未完成 → 不可并行
};
storyDone = { 'story-aaaaaaaaaaaaaaaaaaaaaaaa-step1': true };

const G = [
  { kind: 'tasks', id: 'qDone' }, { kind: 'tasks', id: 'qActive' },
  { kind: 'tasks', id: 'qFailed' }, { kind: 'tasks', id: 'qBlocked' },
  { kind: 'tasks', id: 'qFresh' },
  { kind: 'stories', id: 'story-aaaaaaaaaaaaaaaaaaaaaaaa-step1' },
  { kind: 'stories', id: 'story-bbbbbbbbbbbbbbbbbbbbbbbb-step2' }
];

const results = [];
function check(name, cond) { results.push({ name: name, pass: !!cond }); }

function listed() { return G.filter(g => taskListPass(g.kind, g.id)).map(g => g.id); }
function drawn() { return G.filter(g => taskGroupVisible(g.kind, g.id)).map(g => g.id); }
function reset() {
  state.taskLayerFilters = { tasks: { done: true, todo: true }, stories: { done: true, todo: true } };
  state.taskParallelOnly = false;
  state.taskFocus = null;
  state.taskPointSwitches = {};
  syncTaskLayerMaster();
}

reset();
check('默认四勾全开：列表 7 条', listed().length === 7);
check('默认四勾全开：地图 7 条', drawn().length === 7);
check('默认两层开关都是开', state.layers.tasks === true && state.layers.stories === true);
check('完成状态归类正确', taskStateKey('tasks', 'qDone') === 'done'
  && taskStateKey('tasks', 'qFailed') === 'todo'
  && taskStateKey('stories', 'story-aaaaaaaaaaaaaaaaaaaaaaaa-step1') === 'done');

reset();
state.taskLayerFilters.tasks.done = false;
syncTaskLayerMaster();
check('关「普通任务-已完成」：已完成项从列表消失', listed().indexOf('qDone') === -1);
check('关「普通任务-已完成」：未完成普通任务仍在', listed().indexOf('qActive') >= 0);
check('关「普通任务-已完成」：已完成项不画', drawn().indexOf('qDone') === -1);
check('只关一项时该图层仍画', state.layers.tasks === true);
check('剧情分组不受影响', listed().indexOf('story-bbbbbbbbbbbbbbbbbbbbbbbb-step2') >= 0);

reset();
state.taskLayerFilters.tasks.done = false;
state.taskLayerFilters.tasks.todo = false;
syncTaskLayerMaster();
check('普通任务整组关掉：列表只剩剧情 2 条', listed().length === 2);
check('普通任务整组关掉：tasks 图层关闭', state.layers.tasks === false);
check('stories 图层仍开', state.layers.stories === true);

reset();
state.taskParallelOnly = true;
const par = listed();
check('可并行推进：已完成被排除', par.indexOf('qDone') === -1
  && par.indexOf('story-aaaaaaaaaaaaaaaaaaaaaaaa-step1') === -1);
check('可并行推进：已失败被排除', par.indexOf('qFailed') === -1);
check('可并行推进：前置未满足被排除', par.indexOf('qBlocked') === -1);
check('可并行推进：前置满足的未完成保留', par.indexOf('qActive') >= 0);
check('可并行推进：无前置的未开始保留', par.indexOf('qFresh') >= 0);
check('可并行推进：地图口径与列表一致', JSON.stringify(par) === JSON.stringify(drawn()));

reset();
state.taskParallelOnly = true;
state.taskLayerFilters.tasks.done = true;   // 即便「已完成」勾着，parallel 也优先
check('可并行推进独立于分组勾选：已完成仍不显示', listed().indexOf('qDone') === -1);

reset();
state.taskPointSwitches.pvp = { 'tasks:qFresh': false };
check('单条开关关闭只影响地图', listed().indexOf('qFresh') >= 0 && drawn().indexOf('qFresh') === -1);

reset();
state.taskFocus = { kind: 'tasks', id: 'qActive' };
check('聚焦某条时列表不变、地图只画这一条', listed().length === 7 && drawn().length === 1);

console.log(JSON.stringify(results));
if (results.some(r => !r.pass)) process.exit(2);
"""


def test_js_filter_logic_under_node():
    proc = subprocess.run(
        ["node", "-e", JS_HARNESS],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=60,
    )
    assert proc.returncode == 0, "Node 判定失败：\n%s\n%s" % (proc.stdout, proc.stderr)
    rows = json.loads(proc.stdout.strip().splitlines()[-1])
    failed = [r["name"] for r in rows if not r["pass"]]
    assert not failed, "未通过的判定：%s" % failed
    assert len(rows) >= 20
