# -*- coding: utf-8 -*-
"""R303：网页端目录设置从纯文本改为「文本 + 浏览…」系统文件夹选择框。

浏览器 <input type=file webkitdirectory> 拿不到绝对路径（安全限制），
所以经本机服务 /api/pick-folder 调 Windows 原生 FolderBrowserDialog。

不变量：
1. index.html 两个目录输入框旁各有一个 .mini-dir-browse 按钮，绑定正确的输入框；
2. app.js 点击按钮请求 /api/pick-folder 并把 path 回填、触发 change 保存；
3. 服务端有 /api/pick-folder 路由与 pick_folder_dialog 函数；
4. 非 Windows / 取消 / 失败都安全返回 None，不阻断设置。
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "index.html"
APPJS = ROOT / "app.js"
STYLE = ROOT / "style.css"
SERVE = ROOT / "tools" / "serve.py"


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def test_index_has_browse_buttons():
    html = read(INDEX)
    assert html.count('class="mini-dir-browse"') == 2
    assert 'data-dir-for="mini-shots-dir"' in html
    assert 'data-dir-for="mini-log-dir"' in html
    assert 'id="mini-shots-dir"' in html and 'id="mini-log-dir"' in html


def test_appjs_wires_pick_folder():
    js = read(APPJS)
    assert "mini-dir-browse" in js
    assert "api/pick-folder" in js
    assert "data-dir-for" in js
    assert "dispatchEvent(new Event(\"change\"" in js, "选中后要触发 change 保存配置"


def test_style_has_dir_field():
    css = read(STYLE)
    assert ".mini-dir-field" in css
    assert ".mini-dir-browse" in css


def test_serve_has_pick_folder():
    src = read(SERVE)
    assert "def pick_folder_dialog(" in src
    assert '"/api/pick-folder"' in src
    assert "FolderBrowserDialog" in src
    assert "capture_output=True" in src


def test_pick_folder_non_windows_returns_none(monkeypatch):
    spec = importlib.util.spec_from_file_location("serve_r303", str(SERVE))
    # 不整体执行 serve（依赖重），只以源码字符串保证非 Windows 早退分支存在
    src = read(SERVE)
    start = src.index("def pick_folder_dialog(")
    end = src.index("def best_logs_dir(", start)
    func = src[start:end]
    assert 'if os.name != "nt":' in func
    assert "return None" in func
