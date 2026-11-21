# -*- coding: utf-8 -*-
"""R215：右侧面板底部遗留的「物资刷新点」独立区块（标题 + 外框）已撤除。

框去掉，但搜索结果 / 钉选列表两个功能容器仍在，由顶部唯一的共用搜索栏驱动。
"""
from __future__ import annotations

import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(rel: str) -> str:
    with open(os.path.join(ROOT, rel), "r", encoding="utf-8") as f:
        return f.read()


def _panel(html: str) -> str:
    m = re.search(r'(<aside class="panel" id="task-panel".*?</aside>)', html, re.S)
    assert m, "找不到右侧任务面板"
    return m.group(1)


def test_spawn_frame_and_title_are_gone():
    panel = _panel(_read("index.html"))
    assert "task-panel-search" not in panel
    assert "<h2>物资刷新点" not in panel
    assert "物资刷新点</h2>" not in panel
    # 合并搜索栏之后不应再出现第二个输入框
    assert 'id="search"' not in panel
    assert 'id="task-search"' in panel


def test_result_containers_stay_and_belong_to_the_panel():
    panel = _panel(_read("index.html"))
    assert 'id="pinned-list"' in panel
    assert 'id="search-results"' in panel
    assert "<section" not in panel, "结果容器不该再包在独立 section 里"
    # 顺序：任务列表之后紧跟两个结果容器
    assert panel.index('id="task-list"') < panel.index('id="pinned-list"') < panel.index('id="search-results"')
    app = _read("app.js")
    assert 'el.searchResults = $("search-results");' in app
    assert 'el.pinnedList = $("pinned-list");' in app
    assert "el.search = el.taskSearch;" in app


def test_result_containers_are_laid_out_as_panel_children():
    css = _read("style.css")
    assert ".task-panel-search {" not in css
    # [hidden] 由全局 !important 规则保证，容器显示时不能被任务列表挤掉
    assert "[hidden] { display: none !important; }" in css
    for line in css.splitlines():
        if line.startswith(".search-results {") or line.startswith(".pinned-list {"):
            assert "flex: 0 0 auto;" in line
            assert "8px" in line, "左右留白要与 .task-list 对齐"
    assert ".task-list { display: flex;" in css and "flex: 1 1 auto" in css
