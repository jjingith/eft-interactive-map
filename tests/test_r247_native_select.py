# -*- coding: utf-8 -*-
"""R247 · ShareX 式原生选区：热键零抓屏 / 零 HTTP / 零浏览器。

用户反馈（2026-11-12 11:38）：
  「按截图键反应非常慢啊  https://github.com/ShareX/ShareX 你看下sharex
    他的截图就不会有这种反应 很丝滑 能否直接拿来用」

结论：ShareX 是 GPLv3 的 C#/Avalonia 项目，整体拿来用不现实（技术栈、许可证、
且没有我们的 OCR 价格逻辑）；但把**做法**复刻到项目已有的原生分层窗口引擎里，
正好能根治慢：
  · `RegionCaptureTransparentWindow`：透明命中层只画选区，不画冻结帧；
    窗口关闭后才抓屏（"caller captures the screen after the window closes"）；
  · `RegionCaptureIntegration.WarmUp()`：启动时就把窗口建好，首次按键不付初始化；
  · 常量 alpha=1 保持整窗可点（colorkey 的透明像素会穿透鼠标）。

旧链路：热键 → 整屏 BMP → POST /api/ocr/frame → 唤醒/冷启动 Edge → 页面 150ms
轮询 → GET 6MB 帧 → 解码 → 框选 → 再 POST 识别。冷启动 2~3s，保温 300~500ms。
新链路：热键 → ShowWindow（预热过，7~20ms）→ 框选 → 关窗 → 只抓选区 → 直接
POST /api/ocr/recognize → 本地开透明价格浮窗。
"""

import os
import sys

import pytest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TEST_DIR)
TOOLS = os.path.join(ROOT, "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

sys.path.insert(0, TOOLS)
import scan  # noqa: E402


@pytest.fixture()
def require_interactive_desktop():
    """无交互桌面（会话锁定 / CI）时跳过真实窗口测试。"""
    if not getattr(scan, "IS_WINDOWS", False):
        pytest.skip("仅 Windows")
    pytest.importorskip("numpy", reason="原生窗口测试需要 numpy（服务端 Python 才有）")
    import ctypes

    if not ctypes.windll.user32.GetForegroundWindow():
        pytest.skip("当前会话无交互桌面")


def _src():
    return open(os.path.join(TOOLS, "scan.py"), encoding="utf-8").read()


def test_native_selection_uses_prewarmed_layered_windows():
    src = _src()
    assert "class NativeSelection" in src
    assert "create_overlay_window(3" in src      # 命中层
    assert "create_overlay_window(4" in src      # 选区边框层
    assert "create_overlay_window(5" in src      # 提示条层
    assert "LWA_ALPHA" in src and "SetLayeredWindowAttributes" in src
    # 预热：构造时就做第一次 ULW（否则首次热键付 GDI 初始化 ~130ms）
    body = src[src.index("class NativeSelection"):src.index("class OverlaySession")]
    init = body[body.index("def __init__"):body.index("def show")]
    assert "set_layered_bitmap(self.hint" in init, "提示条位图要在预热阶段画好"


def test_hotkey_path_never_grabs_fullscreen_or_launches_browser():
    """热键分支里不得再出现整屏抓帧 / 帧上传 / 浏览器启动。"""
    src = _src()
    body = src[src.index("def watch_native"):src.index("# 演示模式")]
    hotkey = body[body.index("if msg.message == 0x0312"):body.index("user32.DispatchMessageW")]
    for banned in ("grab_frame(", "post_frame(", "launch_scan_window(", "warm["):
        assert banned not in hotkey, "热键路径不该有 %s" % banned


def test_recognize_region_captures_only_selection_after_window_closed():
    src = _src()
    body = src[src.index("def recognize_region"):src.index("def watch_native")]
    assert "ImageGrab.grab(bbox=" in body, "只抓选区，不抓整屏"
    assert "/api/ocr/recognize" in body
    assert "DwmFlush" in body, "关窗后等合成结束，避免把边框截进去"
    assert "annotate\": False" in body


def test_wndproc_handles_mouse_and_escape_for_hit_layer():
    src = _src()
    body = src[src.index("def _ov_wndproc"):src.index("def overlay_role")]
    for name in ("WM_LBUTTONDOWN", "WM_MOUSEMOVE", "WM_LBUTTONUP",
                 "WM_RBUTTONDOWN", "WM_KEYDOWN", "WM_SETCURSOR"):
        assert name in body, "命中层必须处理 %s" % name


def test_default_is_native_with_legacy_fallback():
    src = _src()
    main = src[src.index("def main("):]
    assert "--legacy-select" in main
    assert "watch_native(a.server, hotkey, a.config_dir)" in main
    assert "watch(a.server, hotkey, a.config_dir)" in main


def test_prewarmed_show_is_fast(require_interactive_desktop):
    """预热后热键路径应 < 50ms（本机有交互桌面时才跑）。"""
    import ctypes
    import time

    from ctypes import wintypes

    u = ctypes.windll.user32
    t0 = time.monotonic()
    sel = scan.NativeSelection()
    build_ms = (time.monotonic() - t0) * 1000

    def pump(sec=0.02):
        msg = wintypes.MSG()
        end = time.monotonic() + sec
        while time.monotonic() < end:
            while u.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                u.DispatchMessageW(ctypes.byref(msg))
            time.sleep(0.002)

    times = []
    try:
        for _ in range(4):
            t0 = time.monotonic()
            sel.show()
            times.append((time.monotonic() - t0) * 1000)
            pump(0.02)
            sel.hide()
            pump(0.02)
        assert build_ms < 1000, "预热不应超过 1s，实际 %.0f ms" % build_ms
        assert max(times) < 50, "预热后 show() 应 <50ms，实际 %s" % [
            round(x, 1) for x in times]
    finally:
        sel.hide()
