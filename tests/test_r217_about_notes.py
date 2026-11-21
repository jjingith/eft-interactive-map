# -*- coding: utf-8 -*-
"""R217：三处说明文字统一搬进顶部菜单「关于」。

用户要求（原话）：
  · 任务详情最下面的「赛季服说明：…」；
  · 我的进度里的「进度只保存在本机浏览器（localStorage）…」；
  · 剧情任务下面的「数据来源：eftarkov 剧情页」。

三处都是「每打开一次就要念一遍」的元信息，放在正文里只会把人推离内容。现在只保留在
「关于」面板；本文件既验「关于里确实有」，也验「原位置确实没了」，防止只改一半或日后回潮。
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(ROOT, "index.html")
TASKS = os.path.join(ROOT, "tasks.js")
STYLE = os.path.join(ROOT, "style.css")
TASKS_CSS = os.path.join(ROOT, "tasks.css")
SEASON = os.path.join(ROOT, "data", "tasks", "season.json")


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _about_panel() -> str:
    html = _read(INDEX)
    start = html.index('id="about-block"')
    return html[start:html.index("<!-- R19.11", start)]


# --------------------------------------------------------------- 关于里确实有

def test_about_panel_carries_the_season_notice():
    panel = _about_panel()
    assert 'id="about-season-note"' in panel
    for must in ("赛季服说明", "上游 pvp-season 端点",
                 "旧赛季的完成状态当作新赛季进度"):
        assert must in panel, "关于面板缺少：%s" % must


def test_about_panel_carries_the_progress_storage_note():
    panel = _about_panel()
    for must in ("进度只保存在本机浏览器（localStorage）", "按模式隔离",
                 "导入/导出为 JSON", "格式不合法时不会覆盖原数据"):
        assert must in panel, "关于面板缺少：%s" % must


def test_about_panel_carries_the_story_source_link():
    panel = _about_panel()
    assert "数据来源：" in panel
    assert "eftarkov 剧情页" in panel
    assert 'href="https://www.eftarkov.com/storyline"' in panel
    assert 'target="_blank"' in panel and 'rel="noopener"' in panel


def test_notes_live_inside_the_about_panel_before_the_meta_line():
    """三块说明必须在关于面板内、数据版本行之前，别跑到面板外面去。"""
    panel = _about_panel()
    assert panel.index("about-notes") < panel.index('id="about-meta-line"')


# --------------------------------------------------------------- 原位置确实没了

@pytest.mark.parametrize("needle", [
    "进度只保存在本机浏览器",
    "eftarkov 剧情页",
    "tk-detail-foot",
    "tk-detail-warn",
    "tk-story-src",
])
def test_task_ui_no_longer_renders_them(needle):
    src = _read(TASKS)
    for line in src.splitlines():
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("*") or stripped.startswith("/*"):
            continue
        assert needle not in line, "任务界面里仍在渲染：%s（%s）" % (needle, stripped[:80])


def test_season_notice_only_lives_in_the_about_filler():
    """赛季文案还留在 tasks.js 里是应该的 —— 但只能出现在给「关于」填字的那一个函数里。"""
    src = _read(TASKS)
    assert src.count("赛季服说明") == 1
    detail = src[src.index("function renderDetail()"):src.index("function condLabel")]
    assert "赛季服说明" not in detail
    filler = src[src.index("function syncAboutSeasonNote"):]
    filler = filler[:filler.index("\n  }\n") + 4]
    assert "赛季服说明" in filler


def test_dead_styles_are_removed():
    css = _read(TASKS_CSS)
    for selector in (".tk-detail-foot", ".tk-detail-warn", ".tk-story-src"):
        assert selector not in css, "样式已无引用，仍留在 tasks.css：%s" % selector


# --------------------------------------------------------------- 版式不能被截断

def test_about_notes_wrap_instead_of_ellipsis():
    """署名行单行省略号是对的；这三条长说明必须整句换行读完。"""
    css = _read(STYLE)
    start = css.index(".about-panel .about-note-row dd {")
    rule = css[start:css.index("}", start) + 1]
    assert "white-space: normal" in rule
    assert "text-overflow" not in rule
    assert "overflow: hidden" not in rule


# --------------------------------------------------------------- 赛季周期跟数据走

def test_season_note_is_filled_from_season_json():
    """周期不写死：把 season.json 的真实日期喂给函数，输出必须带上同一周期。"""
    node = shutil.which("node")
    if not node:
        pytest.skip("未安装 Node.js，跳过行为断言")

    season = json.loads(_read(SEASON))
    src = _read(TASKS)
    fn = src[src.index("function syncAboutSeasonNote"):]
    fn = fn[:fn.index("\n  }\n") + 4]

    harness = """
var out = {};
var node = { textContent: "" };
var document = { getElementById: function (id) { return id === "about-season-note" ? node : null; } };
var state = { season: null };
%s
syncAboutSeasonNote();
out.missing = node.textContent;
state.season = %s;
syncAboutSeasonNote();
out.filled = node.textContent;
console.log(JSON.stringify(out));
""" % (fn, json.dumps({"startISO": season["startISO"], "endISO": season["endISO"]}))

    proc = subprocess.run([node, "-e", harness], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)

    assert "赛季元信息暂缺" in out["missing"], "数据缺失时退回「暂缺」，不能编日期"
    filled = out["filled"]
    assert ("对应当前赛季周期 %s → %s。" % (season["startISO"], season["endISO"])) in filled
    assert filled.startswith("赛季服说明：以上内容来自上游 pvp-season 端点，")
    assert filled.endswith("赛季结束后请勿把旧赛季的完成状态当作新赛季进度。")
    assert not re.search(r"20\d\d-\d\d-\d\d", fn), "函数里不得写死日期"
