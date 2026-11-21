"""R285：自动截图 / 撞名候选菜单 / 小地图跟随 三项修复的回归契约。

调试插桩由上一轮排查留下，本轮全部清理并补齐回归，避免修复被后续改动冲掉。
菜单与浮窗依赖真实 Win32 窗口，这里用静态源码契约 + 可单测的纯逻辑做覆盖。
"""

from __future__ import annotations

from pathlib import Path

import pytest

import serve
from eftlog import APPLICATION  # noqa: F401  - 仅确认模块可导入，具体见下方 monkeypatch

ROOT = Path(__file__).resolve().parent.parent


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# ---------------------------------------------------------------- 自动截图
def test_best_logs_dir_switches_only_for_much_newer_session(tmp_path, monkeypatch):
    """game_dir/Logs 里 13 天前的旧会话，应让位给别处明显更新的会话。"""
    import os as _os
    import time as _time

    primary = tmp_path / "game" / "Logs"
    alt = tmp_path / "local" / "Logs"
    primary.mkdir(parents=True)
    alt.mkdir(parents=True)
    old = primary / "log_2026.11.02_13-49-07_x"
    new = alt / "log_2026.11.15_20-30-00_x"
    old.mkdir()
    new.mkdir()
    monkeypatch.setattr(serve.eftlog, "latest_session_with_channel",
                        lambda d: str(old) if str(d) == str(primary) else
                        (str(new) if str(d) == str(alt) else None))
    stale = _time.time() - 13 * 86400
    _os.utime(old, (stale, stale))
    assert serve.best_logs_dir(str(primary), [str(alt)]) == str(alt)
    # 差距不到一天时不能切走（避免临时/调试目录干扰，也保住既有测试的环境隔离）
    recent = _time.time() - 3600
    _os.utime(old, (recent, recent))
    assert serve.best_logs_dir(str(primary), [str(alt)]) == str(primary)


def test_best_logs_dir_keeps_primary_without_session(tmp_path, monkeypatch):
    """目录已存在但还没写入会话时保持等待，且没有 game_dir 时必须返回 None。"""
    primary = tmp_path / "Logs"
    primary.mkdir()
    monkeypatch.setattr(serve.eftlog, "latest_session_with_channel", lambda d: None)
    assert serve.best_logs_dir(str(primary), [str(tmp_path / "other")]) == str(primary)
    assert serve.best_logs_dir(None, [str(primary)]) is None


def test_log_dir_getter_scans_all_candidates():
    src = read("tools/serve.py")
    assert "best_logs_dir(primary, alternatives)" in src
    assert 'os.path.join(local, "Temp", "Battlestate Games", "EFT", "Logs")' in src
    assert "time.monotonic()" in src, "轮询很密，必须缓存探测结果"


# ---------------------------------------------------------------- 撞名候选菜单
def test_menu_font_is_decoupled_from_label_font():
    src = read("tools/scan.py")
    assert "fs = max(12, int(round(label_base_font(self.matches) * self.ui_scale)))" not in src
    assert "min(16, int(round(13 * self.ui_scale)))" in src
    assert "sw * 0.55" in src and "sh * 0.65" in src
    assert "fs = max(9, min(48, int(fs)))" in src, "候选很多时允许继续缩字号"


def test_menu_keeps_topmost_after_redraw():
    """_redraw 会把标签窗/控制条重新置顶，必须把菜单窗一并恢复。"""
    src = read("tools/scan.py")
    tail = src[src.index("for hwnd in (self.labels_hwnd, self.ctrl_hwnd):"):]
    segment = tail[: tail.index("\ndef ") if "\ndef " in tail else 600]
    assert "if self.menu_for is not None:" in segment
    assert "_topmost(self.menu_hwnd)" in segment


def test_click_opened_menu_is_pinned():
    src = read("tools/scan.py")
    assert "self.menu_pinned = bool(capture)" in src
    assert "not _ACTIVE.menu_pinned" in src, "钉住时不得安排 200ms 自动收起"
    assert "if not _ACTIVE.menu_pinned:" in src, "定时器触发时不得关闭钉住的菜单"
    assert "self.menu_pinned = False" in src
    assert "if self.menu_for == idx and self.menu_pinned" in src, \
        "悬停已打开时，点击徽章应钉住而不是关闭"
    assert "WM_TIMER = 0x0113" in src, "WM_TIMER 必须定义，否则收起定时器抛 NameError"


# ---------------------------------------------------------------- 小地图跟随
def test_mini_follow_refreshed_when_svg_ready():
    src = read("app.js")
    assert "function refreshMiniFollow()" in src
    assert "state.mapSvgReady = true;" in src
    ready = src.index("state.mapSvgReady = true;")
    assert "refreshMiniFollow();" in src[ready: ready + 200]
    assert "function insideMap(map, pos)" in src


# ---------------------------------------------------------------- 插桩清理
@pytest.mark.parametrize("rel", ["app.js", "tools/serve.py", "tools/scan.py"])
def test_no_debug_instrumentation_left(rel):
    src = read(rel)
    assert "debug-point" not in src
    assert "127.0.0.1:7777" not in src
    assert "_dbg(" not in src
