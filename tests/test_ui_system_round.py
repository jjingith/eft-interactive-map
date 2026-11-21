# -*- coding: utf-8 -*-
"""R19.24 专项测试：项目级 UI 设计系统（Windows XP Luna 方向）。

分组（对应任务书第十节与第十四节）：
  A 设计令牌      —— 是否加载、是否语义化、颜色是否桥接既有 --xp-*、字号/圆角是否受控
  B 通用组件      —— API 是否完整、状态是否齐、是否与业务解耦、是否重复注册
  C 展示页        —— 结构、可交互、长中文、无外链
  D 试点应用      —— 任务商人页是否真的用上组件、旧结构钩子是否保留
  E 浏览器验收    —— tools/ui_accept.py 的产物必须全绿（缺失则 skip 并说明）
  F 回归          —— 版本、加载顺序、旧测试、校准数据、i18n
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOKENS = os.path.join(ROOT, "styles", "design-tokens.css")
COMP_CSS = os.path.join(ROOT, "styles", "ui-components.css")
COMP_JS = os.path.join(ROOT, "js", "ui-components.js")
SHOW_HTML = os.path.join(ROOT, "ui-showcase.html")
SHOW_JS = os.path.join(ROOT, "ui-showcase.js")
SHOW_CSS = os.path.join(ROOT, "ui-showcase.css")
TASKS_JS = os.path.join(ROOT, "tasks.js")
TASKS_CSS = os.path.join(ROOT, "tasks.css")
INDEX_HTML = os.path.join(ROOT, "index.html")
APP_JS = os.path.join(ROOT, "app.js")
DOCS = os.path.join(ROOT, "docs", "ui-system")

HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")
CJK = re.compile(r"[\u4e00-\u9fff]")


def _text(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(scope="module")
def tokens():
    return _text(TOKENS)


@pytest.fixture(scope="module")
def comp_css():
    return _text(COMP_CSS)


@pytest.fixture(scope="module")
def comp_js():
    return _text(COMP_JS)


@pytest.fixture(scope="module")
def browser():
    path = os.path.join(DOCS, "browser-accept.json")
    if not os.path.exists(path):
        pytest.skip("缺少浏览器验收产物（先跑 tools/ui_accept.py）")
    return _load(path)


# ---------------------------------------------------------------- A 设计令牌
def test_A_files_exist():
    for p in (TOKENS, COMP_CSS, COMP_JS, SHOW_HTML, SHOW_JS, SHOW_CSS,
              os.path.join(DOCS, "audit.md"), os.path.join(DOCS, "design-spec.md")):
        assert os.path.exists(p), p


def test_A_required_tokens_present(tokens):
    need = [
        "--ui-color-primary", "--ui-color-surface", "--ui-color-surface-alt",
        "--ui-color-surface-raised", "--ui-color-text", "--ui-color-text-muted",
        "--ui-color-text-disabled", "--ui-color-border", "--ui-color-border-light",
        "--ui-color-border-dark", "--ui-color-hover", "--ui-color-selected",
        "--ui-color-focus", "--ui-color-success", "--ui-color-warning",
        "--ui-color-danger", "--ui-color-info", "--ui-color-conflict",
        "--ui-font", "--ui-fs-micro", "--ui-fs-compact", "--ui-fs-body",
        "--ui-fs-strong", "--ui-fs-panel", "--ui-fs-title",
        "--ui-space-1", "--ui-space-7", "--ui-control-h-md", "--ui-icon-md",
        "--ui-radius-control", "--ui-radius-btn", "--ui-shadow-raised",
        "--ui-z-dropdown", "--ui-z-dialog", "--ui-z-tooltip",
        "--ui-dur-fast",
    ]
    missing = [n for n in need if (n + ":") not in tokens]
    assert not missing, missing


def test_A_colors_bridge_existing_palette(tokens):
    """颜色令牌必须引用既有 --xp-*，避免出现第二套近似色（§2.1）。"""
    # 这些必须桥接（值来自 theme-windows-xp.css 的 Luna 调色板）
    bridged = ["--ui-color-primary", "--ui-color-surface", "--ui-color-surface-alt",
               "--ui-color-surface-raised", "--ui-color-selected", "--ui-color-text",
               "--ui-color-text-muted", "--ui-color-border", "--ui-color-border-dark",
               "--ui-color-link", "--ui-color-success", "--ui-color-warning",
               "--ui-color-danger", "--ui-color-info"]
    for name in bridged:
        m = re.search(re.escape(name) + r":\s*([^;]+);", tokens)
        assert m, name
        assert "var(--xp-" in m.group(1), (name, m.group(1))
    # 新增令牌只允许这 5 个（其余一律桥接）
    literals = [n for n in re.findall(r"(--ui-color-[a-z-]+):\s*([^;]+);", tokens)
                if "var(--xp-" not in n[1]]
    # --xp-* 里没有、必须新增的语义色（浅底/白字/遮罩/冲突/提示）
    allowed = {"--ui-color-surface-inset", "--ui-color-conflict", "--ui-color-scrim",
               "--ui-color-tip-bg", "--ui-color-tip-border", "--ui-color-border-light",
               "--ui-color-text-inverse", "--ui-color-success-bg", "--ui-color-warning-bg",
               "--ui-color-danger-bg", "--ui-color-info-bg"}
    extra = {n for n, _ in literals} - allowed
    assert not extra, extra


def test_A_type_and_radius_are_enumerated(tokens, comp_css):
    # 字号只有 6 档，且全部桥接 --xp-fs-*
    sizes = re.findall(r"(--ui-fs-[a-z]+):\s*([^;]+);", tokens)
    assert len(sizes) == 6, sizes
    for name, val in sizes:
        assert "var(--xp-fs-" in val, (name, val)
    # 组件层不得出现裸字号 / 裸圆角 / 裸颜色 / 裸 z-index
    assert not HEX.findall(comp_css), HEX.findall(comp_css)[:6]
    assert not re.search(r"font-size:\s*\d", comp_css), "组件层禁止裸字号"
    assert not re.search(r"border-radius:\s*\d", comp_css), "组件层禁止裸圆角"
    assert not re.search(r"z-index:\s*\d", comp_css), "组件层禁止裸 z-index"
    assert "!important" not in comp_css


def test_A_radius_and_z_scale_limited(tokens):
    radii = re.findall(r"--ui-radius-[a-z]+:\s*([^;]+);", tokens)
    assert len(radii) == 5, radii          # panel / control / btn / pill / circle
    zs = re.findall(r"--ui-z-[a-z]+:\s*(\d+);", tokens)
    assert len(zs) == 8, zs                # raised/sticky/dropdown/overlay/dialog/menu/tooltip/toast
    assert len(set(zs)) == 8, zs
    assert [int(x) for x in zs] == sorted(int(x) for x in zs), "层级必须单调递增"


# ---------------------------------------------------------------- B 组件
def test_B_api_surface(comp_js):
    for name in ("btn", "input", "select", "check", "field", "tabs", "panel",
                 "toolbar", "table", "badge", "dialog", "menu", "toast"):
        assert re.search(r"\b%s:\s*%s\b" % (name, name), comp_js) or \
               re.search(r"\b%s:\s*function" % name, comp_js), name
    assert re.search(r"tooltip:\s*\{", comp_js), "tooltip 必须是 {attach,show,hide}"
    assert "window.GWUI" in comp_js
    assert "version" in comp_js


def test_B_component_decoupled_from_business(comp_js):
    """通用组件不得知道任务/枪械/弹药/地图这些业务概念。"""
    for bad in ("GWTasks", "state.tasks", "gun_builder", "combat_sim", "taskId", "traderId"):
        assert bad not in comp_js, bad


def test_B_states_defined(comp_css):
    for sel in (":hover", ":active", ":focus-visible", "[disabled]", "[aria-disabled=\"true\"]",
                "[aria-selected=\"true\"]", "[aria-pressed=\"true\"]", "[aria-invalid=\"true\"]",
                "[aria-busy=\"true\"]", ".is-conflict", ".is-selected", ".is-disabled"):
        assert sel in comp_css, sel


def test_B_singleton_and_cleanup(comp_js):
    """浮层必须单例、可关闭、不重复插入（§4.8/§4.9/§4.10）。"""
    assert "if (openDialog) { openDialog.close(); }" in comp_js
    assert "var liveMenu = null" in comp_js
    assert "document.removeEventListener(\"mousedown\", m._down, true)" in comp_js
    assert "removeChild" in comp_js
    assert "ui-scroll-lock" in comp_js
    # 关闭后恢复焦点
    assert "prevFocus" in comp_js


def test_B_no_outer_resources(comp_js, comp_css, tokens):
    for name, body in (("ui-components.js", comp_js), ("ui-components.css", comp_css),
                       ("design-tokens.css", tokens)):
        assert "http://" not in body and "https://" not in body, name
        assert "@import" not in body, name


# ---------------------------------------------------------------- C 展示页
def test_C_showcase_links_local_assets():
    html = _text(SHOW_HTML)
    assert "styles/design-tokens.css" in html
    assert "styles/ui-components.css" in html
    assert "js/ui-components.js" in html
    assert "ui-showcase.js" in html
    for m in re.findall(r'(?:src|href)="([^"]+)"', html):
        assert not m.startswith("http"), m


def test_C_showcase_sections_cover_required_items():
    html = _text(SHOW_HTML)
    ids = re.findall(r'id="sec-([a-z]+)"', html)
    assert set(ids) >= {"panel", "button", "form", "tabs", "overlay", "dialog",
                        "badge", "table", "type", "contrast"}, ids
    js = _text(SHOW_JS)
    # 10 类演示都必须真的调用组件
    for fn in ("UI.panel(", "UI.btn(", "UI.input(", "UI.select(", "UI.check(",
               "UI.tabs(", "UI.toolbar(", "UI.table(", "UI.badge(",
               "UI.dialog(", "UI.menu(", "UI.tooltip.attach("):
        assert fn in js, fn


def test_C_long_chinese_text_and_no_fake_data():
    js = _text(SHOW_JS)
    assert "这是一段较长的说明文字" in js or "长中文段落" in js
    assert "长中文段落" in js, "必须有长中文文本用于检查换行/溢出"
    # 展示页的数据必须是示例，不能冒充真实业务数据
    assert "示例任务" in js
    assert "不对应任何真实游戏数据" in _text(SHOW_HTML)


# ---------------------------------------------------------------- D 试点
def test_D_pilot_uses_components():
    js = _text(TASKS_JS)
    for fn in ("UI.table(", "UI.toolbar(", "UI.badge(", "UI.dialog(", "UI.tooltip.attach(",
               "UI.select(", "UI.btn(", "UI.check(", "UI.input("):
        assert fn in js, fn
    assert "function openDataNote" in js, "试点必须有一个真实的弹窗"


def test_D_pilot_keeps_legacy_hooks():
    """试点不破坏既有结构与测试钩子（tk-table / tk-tr / tk-td / 各 id）。"""
    js = _text(TASKS_JS)
    for hook in ('className: "tk-table"', "tk-tr", "tk-td-name", "tk-td-mode",
                 '"tk-search"', '"tk-trader"', '"tk-sort"', '"tk-special"'):
        assert hook in js, hook
    css = _text(TASKS_CSS)
    # 旧表格的视觉规则必须已删除（视觉归组件），只留结构注释
    assert "grid-template-columns: minmax(140px" not in css, "旧列宽网格必须移除"
    assert ".tk-td-status.is-done" not in css
    assert "border: 1px solid var(--xp-border, #aca899); background: #fff; }" not in css


def test_D_load_order_is_tokens_then_components():
    html = _text(INDEX_HTML)
    i_theme = html.index("theme-windows-xp.css")
    i_tokens = html.index("styles/design-tokens.css")
    i_comp = html.index("styles/ui-components.css")
    i_tasks = html.index("tasks.css")
    assert i_theme < i_tokens < i_comp, "令牌必须在主题之后、组件在令牌之后"
    assert i_tasks < i_comp, "组件样式必须加载在模块样式之后才能压过它"


# ---------------------------------------------------------------- E 浏览器
def test_E_browser_acceptance_all_green(browser):
    assert browser.get("pass") is True, [c for c in browser["checks"] if not c["ok"]][:3]
    names = {c["name"]: c["ok"] for c in browser["checks"]}
    assert len(names) >= 30, len(names)
    for key in ("A3 设计令牌已加载且可解析（颜色/字号/间距/尺寸/层级）",
                "A4 桥接令牌与既有 --xp-* 解析为同一颜色（没有第二套近似色）",
                "A6 十类基础组件都渲染出来了",
                "A10 弹窗可打开且带 role=dialog/aria-modal、锁滚动",
                "A11 Esc 关闭弹窗、解除滚动锁并把焦点还给触发按钮",
                "A12 危险弹窗：确认按钮为 danger 变体，默认焦点在「取消」",
                "A13 菜单可打开、在视口内、焦点进入菜单",
                "A15 自定义提示可显示、不被视口裁切、限宽 320px",
                "A16 表格：行可选中（aria-selected+蓝底）、冲突行虚线、禁用行灰面",
                "A18 1680px 下无横向溢出（整页与长文段落）",
                "B2 商人任务表改由 ui-table 渲染（保留 tk-* 结构钩子）",
                "B7「数据说明」弹窗内容来自真实数据（模式名 + 任务数）",
                "C1 所有请求都是本地同源资源（无 CDN / 在线字体 / 在线图标）"):
        assert names.get(key) is True, key


def test_E_offline_requests_are_local(browser):
    req = (browser.get("detail") or {}).get("requests") or {}
    assert req.get("total", 0) > 0
    assert not req.get("external"), req.get("external")


# ---------------------------------------------------------------- F 回归
def test_F_build_and_assets():
    app = _text(APP_JS)
    m = re.search(r'AM_BUILD = "([^"]+)"', app)
    assert m and re.match(r"^R19\.\d+(\.\d+)?$", m.group(1)), m and m.group(1)
    ver = m.group(1).lower()
    html = _text(INDEX_HTML)
    for name in ("style.css", "theme-windows-xp.css", "tasks.css", "app.js", "tasks.js",
                 "styles/design-tokens.css", "styles/ui-components.css", "js/ui-components.js"):
        assert (name + "?v=" + ver) in html, name
    assert ('"rev": "%s-"' % m.group(1)) in _text(os.path.join(ROOT, "tools", "serve.py"))


def test_F_old_tests_still_present():
    tests = os.listdir(os.path.join(ROOT, "tests"))
    for name in ("test_r19_22_round.py", "test_r19_23_round.py", "test_r9_round.py"
                 if "test_r9_round.py" in tests else "test_r6_gun_workbench.py",
                 "test_serve.py", "test_config.py"):
        assert name in tests, name


def test_F_showcase_route_in_server():
    serve = _text(os.path.join(ROOT, "tools", "serve.py"))
    assert '"/ui-showcase"' in serve
    assert "ui-showcase.html" in serve


def test_F_calibration_untouched():
    path = os.path.join(ROOT, "data", "gun-layout-calibration.json")
    assert os.path.exists(path) and _load(path)
    for tool in ("ui_audit.py", "ui_accept.py"):
        assert "gun-layout-calibration" not in _text(os.path.join(ROOT, "tools", tool))


def test_F_i18n_still_zero_gaps():
    proc = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "build_i18n.py")],
                          capture_output=True, text=True, cwd=ROOT)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "未覆盖 0" in proc.stdout, proc.stdout[-300:]
