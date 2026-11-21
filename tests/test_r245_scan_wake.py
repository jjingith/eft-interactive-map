# -*- coding: utf-8 -*-
"""R245：修「按热键后白屏，点一下鼠标才正常」。

用户反馈（2026-11-11 22:05）：
  「按截图快捷键后会白屏 得鼠标左键单击一下之后才能正常截图」

三个根因（都在保温窗口的生命周期上）：
1. Edge/Chrome 单实例：同 `--user-data-dir` 的新启动会把窗口塞进**旧进程**，
   新加的启动参数不生效；旧进程里攒了 5 个隐藏窗口，隐藏期间合成被挂起，
   唤醒后是白帧，要靠鼠标事件才重绘。
2. 唤醒瞬间页面标题还残留上一轮的「关闭」/「完成」——页面要到 visibilitychange
   才复位标题，比宿主 150ms 轮询晚，宿主读到就直接把刚显示的窗口隐藏（「闪一下白」）。
3. 显示后没有主动触发重绘。

修复：启动/冷启动前清理占用扫描 profile 的旧浏览器进程；浏览器加
`--disable-backgrounding-occluded-windows` / `--disable-renderer-backgrounding` /
`--disable-background-timer-throttling` / 关 `CalculateNativeWinOcclusion`；
显示后 RedrawWindow(RDW_UPDATENOW|ALLCHILDREN) + DwmFlush；页面唤醒时强制一次
合成提交；「关闭」信号要连续两次读到才执行；隐藏时宿主把标题复位。
"""

import os
import sys

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TEST_DIR)
TOOLS = os.path.join(ROOT, "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

sys.path.insert(0, TOOLS)
import scan  # noqa: E402


def _src():
    return open(os.path.join(TOOLS, "scan.py"), encoding="utf-8").read()


def test_browser_flags_disable_occlusion_and_backgrounding():
    src = _src()
    launch = src[src.index("def launch_scan_window"):src.index("def show_selection")]
    for flag in ("--disable-backgrounding-occluded-windows",
                 "--disable-renderer-backgrounding",
                 "--disable-background-timer-throttling"):
        assert flag in launch, "缺少启动参数 %s（隐藏期间合成会被挂起→唤醒白屏）" % flag
    assert "CalculateNativeWinOcclusion" in launch, "需要关闭 Windows 遮挡检测"
    assert "CalculateNativeWinOcclusionOnShow" in launch


def test_show_selection_forces_repaint():
    src = _src()
    body = src[src.index("def show_selection"):src.index("def hide_selection")]
    assert "ShowWindow" in body and "SetWindowPos" in body
    assert "RedrawWindow" in body, "显示后必须强制重绘（RDW_UPDATENOW）"
    assert "0x0100" in body, "RDW_UPDATENOW 标志缺失"
    assert "DwmFlush" in body, "要等 DWM 提交完再返回"


def test_hide_selection_resets_title():
    src = _src()
    body = src[src.index("def hide_selection"):src.index("def watch(")]
    assert "SetWindowTextW" in body and "SCAN_TITLE" in body, \
        "隐藏时要复位标题，避免下一轮唤醒读到残留的「关闭/完成」"


def test_closed_signal_needs_two_polls():
    """「关闭」残留保护：连续两次轮询都读到 CLOSED 才收窗。"""
    src = _src()
    body = src[src.index("if title == SCAN_TITLE_CLOSED"):src.index("elif title == SCAN_TITLE_DONE")]
    assert "closed_stale" in body
    assert "hide_selection" in body
    # 第一次只标记，不立刻隐藏
    first = body.index("closed_stale")
    hide = body.index("hide_selection")
    assert first < hide, "必须先置 closed_stale 再（下一轮）隐藏"
    assert src.count("closed_stale") >= 4, "唤醒/复位/初始化都要维护该标志"


def test_kill_stale_scan_browsers_is_ctypes_only():
    """R246：清理旧浏览器不能再起 PowerShell（pythonw 下会弹黑窗），也要防误杀。"""
    src = _src()
    fn = src[src.index("def kill_stale_scan_browsers"):src.index("def launch_scan_window")]
    body = fn.split('"""')[2]        # 去掉 docstring（里面会解释为什么不用 PowerShell）
    # 纯 ctypes：按窗口标题拿 PID + 上次启动记录的 PID
    assert "_enum_windows" in body
    assert "BROWSER_PID_PATH" in body
    assert "TerminateProcess" in src
    # 二次校验可执行名，防 PID 复用误杀
    assert "_image_name" in body and "msedge.exe" in body and "chrome.exe" in body
    # 绝不启动控制台子进程
    low = body.lower()
    assert "powershell" not in low, "清理路径不能再起 PowerShell（会弹黑窗）"
    assert "subprocess" not in low
    assert "taskkill" not in low


def test_scan_page_forces_compositor_commit_on_wake():
    html = open(os.path.join(ROOT, "scan.html"), encoding="utf-8").read()
    seg = html[html.index('addEventListener("visibilitychange"'):]
    seg = seg[:seg.index("setupPoll();", seg.index("setupPoll();") + 1)]
    assert "opacity" in seg, "唤醒时要强制一次合成提交（极小透明度变化）"
    assert "requestAnimationFrame" in seg
