# -*- coding: utf-8 -*-
"""R19.27 专项测试：递归任务依赖联动 / 全局游戏模式 / 任务进度持久化。

约定（与项目既有测试一致）：
  · 只断言真实存在的文件与行为，不猜 API；
  · 旧测试不删不弱化，冲突断言在原文件里升级；
  · 纯逻辑场景用 Node 从 tasks.js 抽真函数跑，不复制实现。
"""
import json
import os
import re
import subprocess

import pytest

from _offline_guard import assert_offline   # R32：外部资源判据（见该模块 docstring）

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TASKS = os.path.join(ROOT, "tasks.js")
APP = os.path.join(ROOT, "app.js")
INDEX = os.path.join(ROOT, "index.html")
GAME_MODE = os.path.join(ROOT, "js", "game-mode.js")
UI_CSS = os.path.join(ROOT, "style.css")
SERVE = os.path.join(ROOT, "tools", "serve.py")

NODE = "node"


def _text(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _run_node(script):
    r = subprocess.run([NODE, "-e", script], capture_output=True, text=True,
                       cwd=ROOT, timeout=60)
    if r.returncode != 0:
        raise AssertionError("node failed: " + (r.stderr or r.stdout)[-800:])
    return r.stdout


# ---------------------------------------------------------------- A 递归前置
_PLAN_PROBE = r"""
const fs=require('fs');
const src=fs.readFileSync('tasks.js','utf8');
function grab(name){
  const i=src.indexOf('function '+name);
  if(i<0) throw new Error('missing '+name);
  let d=0,j=src.indexOf('{',i);
  for(let k=j;k<src.length;k++){ if(src[k]==='{')d++; else if(src[k]==='}'){d--; if(!d) return src.slice(i,k+1);} }
}
global.window={};
const tasks=%TASKS%;
const progress={modes:{regular:{}}};
const STATUS_ZH={none:'未开始',active:'进行中',completed:'已完成',failed:'已失败'};
const WANT_TO_STATUS={complete:'completed',completed:'completed',active:'active',fail:'failed',failed:'failed'};
function task(id){return tasks[id];}
function statusOf(id){const r=progress.modes.regular[id];return r&&r.status?r.status:'none';}
eval([grab('wantStatus'),grab('wantedOf'),grab('satisfies'),grab('wantZh'),
      grab('pickStatus'),grab('planPrereqFix'),grab('planFollowUpReset')].join('\n'));
%BODY%
"""


def _probe(body, tasks_json):
    script = _PLAN_PROBE.replace("%TASKS%", tasks_json).replace("%BODY%", body)
    return _run_node(script)


CHAIN = json.dumps({
    "A": {"id": "A", "nameZh": "任务A", "prerequisites": [], "conditions": [], "followUps": ["B"]},
    "B": {"id": "B", "nameZh": "任务B", "prerequisites": [{"taskId": "A", "statuses": ["complete"], "logic": "all"}],
          "conditions": [], "followUps": ["C"]},
    "C": {"id": "C", "nameZh": "任务C", "prerequisites": [{"taskId": "B", "statuses": ["complete"], "logic": "all"}],
          "conditions": [], "followUps": ["D"]},
    "D": {"id": "D", "nameZh": "任务D", "prerequisites": [{"taskId": "C", "statuses": ["complete"], "logic": "all"}],
          "conditions": [], "followUps": ["E"]},
    "E": {"id": "E", "nameZh": "任务E", "prerequisites": [{"taskId": "D", "statuses": ["complete"], "logic": "all"}],
          "conditions": [], "followUps": []},
})


def test_A_recursive_full_chain_not_just_direct():
    """场景 A/B：三层与五层直线依赖，必须递归到链顶，不能只动直接前置。"""
    out = _probe("""
    var p3 = planPrereqFix('C','completed');
    var p5 = planPrereqFix('E','completed');
    console.log(JSON.stringify({
      c: p3.changes.map(function(x){return x.id+'@'+x.depth;}),
      e: p5.changes.map(function(x){return x.id+'@'+x.depth;}),
      maxC: p3.maxDepth, maxE: p5.maxDepth
    }));
    """, CHAIN)
    d = json.loads(out.strip().splitlines()[-1])
    assert d["c"] == ["B@0", "A@1"], d
    assert d["maxC"] == 1
    # 五层链 E←D←C←B←A：四个前置都要进计划（R19.26 只会做 D 一个）
    assert len(d["e"]) == 4 and d["e"][0] == "D@0" and "A@3" in d["e"], d
    assert d["maxE"] == 3


def test_A_satisfied_untouched():
    """已满足的前置不得被无谓修改。"""
    out = _probe("""
    progress.modes.regular['A'] = {status:'completed', objectives:{}};
    var p = planPrereqFix('C','completed');
    console.log(JSON.stringify(p.changes.map(function(x){return x.id;})));
    """, CHAIN)
    ids = json.loads(out.strip().splitlines()[-1])
    assert ids == ["B"], ids


def test_A_or_group_picks_single_branch():
    """场景 D：OR 组只选一条改动最少的分支，不把全部分支标完成。"""
    tasks = json.dumps({
        "O1": {"id": "O1", "nameZh": "或分支1", "prerequisites": [], "conditions": []},
        "O2": {"id": "O2", "nameZh": "或分支2",
               "prerequisites": [{"taskId": "O1", "statuses": ["complete"], "logic": "all"}], "conditions": []},
        "T": {"id": "T", "nameZh": "目标",
              "prerequisites": [{"taskId": "O1", "statuses": ["complete"], "logic": "or"},
                                {"taskId": "O2", "statuses": ["complete"], "logic": "or"}],
              "conditions": []},
    })
    out = _probe("""
    var p = planPrereqFix('T','completed');
    console.log(JSON.stringify({
      changes: p.changes.map(function(x){return x.id;}),
      orNote: p.notes.filter(function(n){return String(n).indexOf('或条件')===0;}).length
    }));
    """, tasks)
    d = json.loads(out.strip().splitlines()[-1])
    assert d["changes"] == ["O1"], d        # 只动一条，O2 不碰
    assert d["orNote"] == 1


def test_A_or_already_satisfied_skips():
    """OR 组已有一条满足 → 整组不动。"""
    tasks = json.dumps({
        "O1": {"id": "O1", "nameZh": "或1", "prerequisites": [], "conditions": []},
        "O2": {"id": "O2", "nameZh": "或2", "prerequisites": [], "conditions": []},
        "T": {"id": "T", "nameZh": "目标",
              "prerequisites": [{"taskId": "O1", "statuses": ["complete"], "logic": "or"},
                                {"taskId": "O2", "statuses": ["complete"], "logic": "or"}],
              "conditions": []},
    })
    out = _probe("""
    progress.modes.regular['O2'] = {status:'completed', objectives:{}};
    var p = planPrereqFix('T','completed');
    console.log(JSON.stringify(p));
    """, tasks)
    assert json.loads(out.strip().splitlines()[-1]) is None    # 无需调整 → 不弹窗


def test_A_status_wording_active_and_failed():
    """场景 E：需要进行中/需要失败的前置，不得一律标成已完成。"""
    tasks = json.dumps({
        "F1": {"id": "F1", "nameZh": "要失败的", "prerequisites": [], "conditions": []},
        "G": {"id": "G", "nameZh": "目标", "prerequisites": [{"taskId": "F1", "statuses": ["failed"], "logic": "all"}],
              "conditions": []},
        "P": {"id": "P", "nameZh": "要进行中", "prerequisites": [{"taskId": "F1", "statuses": ["active"], "logic": "all"}],
              "conditions": []},
    })
    out = _probe("""
    var a = planPrereqFix('G','completed');
    var b = planPrereqFix('P','completed');
    console.log(JSON.stringify({g:a.changes.map(function(x){return x.to;}), p:b.changes.map(function(x){return x.to;})}));
    """, tasks)
    d = json.loads(out.strip().splitlines()[-1])
    assert d["g"] == ["failed"], d          # 数据词面是 failed，不能映射丢档
    assert d["p"] == ["active"], d


def test_A_cycle_and_missing_safe():
    """场景 F：环 / 指向不存在任务 —— 不挂死、不静默删边、不产生部分修改。"""
    tasks = json.dumps({
        "X": {"id": "X", "nameZh": "环1", "prerequisites": [{"taskId": "Y", "statuses": ["complete"], "logic": "all"}],
              "conditions": []},
        "Y": {"id": "Y", "nameZh": "环2", "prerequisites": [{"taskId": "X", "statuses": ["complete"], "logic": "all"}],
              "conditions": []},
        "M": {"id": "M", "nameZh": "缺前置", "prerequisites": [{"taskId": "NOPE", "statuses": ["complete"], "logic": "all"}],
              "conditions": []},
    })
    out = _probe("""
    var a = planPrereqFix('Y','completed');
    var b = planPrereqFix('M','completed');
    console.log(JSON.stringify({
      cycChanges: a.changes.length, cycUnfix: a.unfixable.map(function(u){return u.need;}),
      missUnfix: b.unfixable.map(function(u){return u.need;}),
      missChanges: b.changes.length
    }));
    """, tasks)
    d = json.loads(out.strip().splitlines()[-1])
    assert any("循环" in x for x in d["cycUnfix"]), d
    assert any("不存在" in x for x in d["missUnfix"]), d
    assert d["missChanges"] == 0          # 异常链不写任何东西（缺失任务不进改动清单）


def test_A_non_task_conditions_not_forged():
    """非任务型条件只提示，不伪造完成。"""
    tasks = json.dumps({
        "N": {"id": "N", "nameZh": "带条件", "prerequisites": [],
              "conditions": [{"kind": "traderLevel", "text": "商人等级 3"}]},
    })
    out = _probe("""
    var p = planPrereqFix('N','completed');
    // 无任务型前置可调 → 计划为 null（不弹无意义窗口）；有改动时 notes 才带出非任务条件
    console.log(JSON.stringify({plan: p === null ? 'null' : 'set',
                                notes: p ? p.notes : [],
                                changes: p ? p.changes.length : 0}));
    """, tasks)
    d = json.loads(out.strip().splitlines()[-1])
    assert d["plan"] == "null" and d["changes"] == 0, d
    # 有任务型前置时，非任务条件必须以 notes 提示而不是伪造
    out2 = _probe("""
    tasks['N2'] = {id:'N2', nameZh:'N2', conditions:[],
                   prerequisites:[{taskId:'M2', statuses:['complete'], logic:'all'}]};
    tasks['M2'] = {id:'M2', nameZh:'M2', prerequisites:[], conditions:[]};
    tasks['N'].conditions = [{kind:'traderLevel', text:'商人等级 3'}];
    var p2 = planPrereqFix('N2','completed');
    tasks['N'].prerequisites = [{taskId:'M2', statuses:['complete'], logic:'all'}];
    var p3 = planPrereqFix('N','completed');
    console.log(JSON.stringify({n3notes: p3 ? p3.notes : [], n3changes: p3 ? p3.changes.map(function(c){return c.to;}) : []}));
    """, tasks)
    d2 = json.loads(out2.strip().splitlines()[-1])
    assert d2["n3changes"] == ["completed"]
    assert any("商人等级" in str(x) for x in d2["n3notes"]), d2


# ---------------------------------------------------------------- B 后续重置不退化
def test_B_followup_reset_still_recursive_or_aware():
    """场景：后续重置保持 R19.26 行为（递归下游 + OR 有其它路径不重置）。"""
    tasks = json.dumps({
        "A": {"id": "A", "nameZh": "A", "prerequisites": [], "conditions": [],
              "followUps": ["B", "C"]},
        "B": {"id": "B", "nameZh": "B", "prerequisites": [{"taskId": "A", "statuses": ["complete"], "logic": "all"}],
              "conditions": [], "followUps": ["D"]},
        "C": {"id": "C", "nameZh": "C", "prerequisites": [{"taskId": "A", "statuses": ["complete"], "logic": "all"}],
              "conditions": [], "followUps": ["D"]},
        "D": {"id": "D", "nameZh": "D", "prerequisites": [{"taskId": "B", "statuses": ["complete"], "logic": "all"},
                                                          {"taskId": "C", "statuses": ["complete"], "logic": "all"}],
              "conditions": [], "followUps": []},
    })
    out = _probe("""
    progress.modes.regular['A']={status:'completed',objectives:{}};
    progress.modes.regular['B']={status:'completed',objectives:{}};
    progress.modes.regular['C']={status:'completed',objectives:{}};
    progress.modes.regular['D']={status:'completed',objectives:{}};
    var p = planFollowUpReset('A');
    console.log(JSON.stringify(p.plan.map(function(x){return x.id+'@'+x.depth;})));
    """, tasks)
    ids = json.loads(out.strip().splitlines()[-1])
    # A→B/C→D：B、C 失去 A 后都要重置，D 失去 AND 也要重置
    assert set(ids) == {"B@1", "C@1", "D@2"}, ids


# ---------------------------------------------------------------- C 全局模式
def test_C_global_mode_module_exists_and_single_owner():
    gm = _text(GAME_MODE)
    assert "window.GWGameMode" in gm
    assert 'eftmap.gameMode' in gm          # 唯一持久化键
    # 合法性校验 + 默认回退
    assert "valid(" in gm and "readStored" in gm
    assert 'MODES' in gm and '"pvps"' in gm
    # 不存页面局部状态（搜索/筛选不进本模块）
    assert "perMode" not in gm and "filters" not in gm


def test_C_tasks_reads_global_mode_not_own_storage():
    js = _text(TASKS)
    assert "window.GWGameMode" in js
    assert "globalMode()" in js
    # 不再把 mode 写进 LS_UI（模式唯一持久化在 eftmap.gameMode）
    save = js[js.index("function saveUi()"):js.index("function progOf(")]
    assert "perMode: state.perMode" in save and "mode: state.mode" not in save, save[:400]
    # 页内不再放重复的模式按钮
    assert 'modes.id = "tk-modes"' not in js
    assert "tk-mode-hint" in js            # 只留文字提示


def test_C_mode_bar_in_header_not_per_page():
    html = _text(INDEX)
    assert 'id="game-mode-bar"' in html
    # 挂点在全局 menubar 内（不在某个 view-pane 里）
    menubar = html[html.index('id="menubar"'):html.index('class="workspace"')]
    assert "game-mode-bar" in menubar
    assert "js/game-mode.js" in html


def test_C_mode_persist_key_and_validation():
    gm = _text(GAME_MODE)
    assert "localStorage.setItem(LS_KEY" in gm or "localStorage.setItem(LS_KEY," in gm
    # 只接受合法 key
    assert "KEYS.indexOf(key) >= 0" in gm or "valid(key)" in gm


# ---------------------------------------------------------------- D 持久化
def test_D_all_progress_writes_share_one_pipeline():
    """所有进度写入口都走 setStatusRaw/toggleObjective + saveProgress，不各写各的。"""
    js = _text(TASKS)
    body = js[js.index("function setStatusRaw("):js.index("function broadcast()")]
    assert body.count("state.progress.modes[state.mode]") == 4
    # 批量 + 单条 + 目标勾选都最终调 saveProgress
    assert "function setStatus(taskId, status)" in body
    assert "function applyStatusBatch(" in body
    assert body.count("saveProgress()") >= 3


def test_D_batch_atomic_with_rollback():
    js = _text(TASKS)
    body = js[js.index("function applyStatusBatch("):js.index("function toggleObjective(")]
    assert "snapshot" in body and "JSON.parse(snapshot)" in body, "保存失败必须回滚"
    assert "saveProgress()" in body
    assert body.count("return false") >= 1   # 失败路径要可感知


def test_D_progress_scoped_per_mode_unchanged():
    js = _text(TASKS)
    # 三模式桶仍在同一个 LS_PROGRESS 结构里
    assert 'LS_PROGRESS = "eftmap.tasks.progress.v1"' in js
    assert "MODE_KEYS.forEach" in js
    body = js[js.index("function setStatusRaw("):js.index("function broadcast()")]
    assert "modes.regular" not in body and "modes.pve" not in body and "modes.pvps" not in body


def test_D_import_export_still_cover_batch():
    js = _text(TASKS)
    assert "function exportProgress()" in js and "function importProgress(" in js
    # 导出内容仍是三模式结构
    exp = js[js.index("function exportProgress()"):js.index("function importFromFile(")]
    assert "modes" in exp and "eftmap-task-progress" in exp


# ---------------------------------------------------------------- E 版本 / 资源
def test_E_build_stamp_and_assets():
    app = _text(APP)
    m = re.search(r'AM_BUILD = "([^"]+)"', app)
    assert m and re.match(r"^R19\.\d+(\.\d+)?$", m.group(1)), m and m.group(1)
    ver = m.group(1).lower()
    html = _text(INDEX)
    for asset in ("style.css", "app.js", "tasks.js", "tasks.css",
                  "js/game-mode.js", "js/task-graph-layout.js", "js/ui-components.js"):
        assert (asset + "?v=" + ver) in html, asset
    assert ('"rev": "%s-"' % m.group(1)) in _text(SERVE)


def test_E_offline_no_external():
    """R32 迁移判据：从「不许出现 https://」升级为「不许**加载**外部资源」。

    同 test_r19_26 的 test_D_no_external_resources：任务栏「查看攻略」的跳转型外链
    不算运行期联网。判定细则见 `tests/_offline_guard.py`。
    """
    for path in (TASKS, GAME_MODE, APP):
        assert_offline(_text(path), path)


def test_E_previous_rounds_present():
    tests = os.listdir(os.path.join(ROOT, "tests"))
    for name in ("test_r19_23_round.py", "test_r19_25_round.py", "test_r19_26_round.py",
                 "test_loadout_workbench.py", "test_ui_system_round.py"):
        assert name in tests, name
