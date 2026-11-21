# -*- coding: utf-8 -*-
"""R216：任务模块子栏页签恒为 XP 风格，db4 皮肤不再串台到其它子页。

根因：ensureListUI() 曾把 db4 类加到整个 .tk-shell 且从不移除；
tasks.css 的 .tk-shell.db4 .tk-tab（特异性 0,3,0）压过 xp-ui 的
html body .tk-tab（0,1,2），把 XP 位图按钮换成了 db4 渐变。
"""
from __future__ import annotations

import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(rel: str) -> str:
    with open(os.path.join(ROOT, rel), "r", encoding="utf-8") as f:
        return f.read()


def test_db4_scope_is_switched_per_subview():
    js = _read("tasks.js")
    assert 'state.el.root.classList.toggle("db4", state.view === "list");' in js
    assert 'shell.classList.add("db4")' not in js, "整壳 db4 不能再由列表页一次性加上"
    assert "R216：db4 只留在任务板容器上" in js
    assert "host.classList.add(\"db4\");" in js, "任务板自身的 db4 仍要保留"


def test_tab_keeps_the_xp_bitmap_skin():
    css = _read("tasks.css")
    for selector in (
        ".tk-shell.db4 .tk-tab {",
        ".tk-shell.db4 .tk-tab:hover {",
        ".tk-shell.db4 .tk-tab[aria-selected=\"true\"] {",
    ):
        assert selector not in css, "db4 不该再覆盖页签：%s" % selector
    xp = _read(os.path.join("assets", "xp-ui", "xp-ui-app.css"))
    assert "html body .tk-tab," in xp
    assert 'border-image: url("btn-normal.png")' in xp
    assert 'border-image-source: url("btn-pressed.png");' in xp


def test_subview_is_restored_from_local_prefs():
    """「点进去默认停在某个子页」是 loadUi() 按模式恢复的，不是写死的首页。"""
    js = _read("tasks.js")
    assert 'if (cur.view && ["tree", "list", "detail", "progress", "story"].indexOf(cur.view) >= 0) {' in js
    assert "state.view = cur.view;" in js
    assert 'view: "list",' in js  # 首次使用的初始值
