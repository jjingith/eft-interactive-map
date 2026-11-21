"""`tools/keyinput.py` 的测试：键名归一化、键表查询、不支持的按键、前台窗口判定。

真实发送按键会打到当前前台窗口（可能干扰使用者），所以默认**不**在测试里真发键；
只在 Windows 上做一次「SendInput 调用链路可用」的轻量校验，且目标是一个普通按键。
"""

from __future__ import annotations

import pytest

import keyinput


# --------------------------------------------------------------- 归一化

@pytest.mark.parametrize("raw,expect", [
    ("V", "v"),
    ("v", "v"),
    ("  Left Shift ", "leftshift"),
    ("Left_Shift", "leftshift"),
    ("left-shift", "leftshift"),
    ("Mouse Scroll", "mousescroll"),
    ("", ""),
    (None, ""),
    (42, ""),
])
def test_normalize(raw, expect):
    assert keyinput.normalize(raw) == expect


# --------------------------------------------------------------- 键表

def test_lookup_letters_and_digits():
    v = keyinput.lookup("V")
    assert (v.vk, v.scan, v.extended) == (ord("V"), 0x2F, False)
    one = keyinput.lookup("1")
    assert (one.vk, one.scan) == (0x31, 0x02)


def test_lookup_is_case_and_spacing_insensitive():
    assert keyinput.lookup(" v ") == keyinput.lookup("V")
    assert keyinput.lookup("Page Down") == keyinput.lookup("pagedown")


def test_lookup_named_keys():
    assert keyinput.lookup("Space").scan == 0x39
    assert keyinput.lookup("Escape").vk == 0x1B
    assert keyinput.lookup("F5").vk == 0x74
    # 方向键 / 右 Ctrl 需要扩展标志，否则部分游戏收不到
    assert keyinput.lookup("Up").extended is True
    assert keyinput.lookup("Right Ctrl").extended is True


def test_lookup_printscreen_family_aliases():
    """PrintScreen / SysRq 是同一个物理键；EFT 的控制绑定里写作 `SysReq`，几个名字都要认。"""
    ps = keyinput.lookup("PrintScreen")
    assert (ps.vk, ps.scan, ps.extended) == (0x2C, 0x37, True)
    assert keyinput.lookup("Prtsc") == ps
    assert keyinput.lookup("SysReq") == ps
    assert keyinput.lookup("SysRq") == ps


@pytest.mark.parametrize("name", ["Mouse0", "Mouse Scroll", "鼠标左键", "F13", "", None, "NotAKey"])
def test_lookup_returns_none_for_unknown(name):
    assert keyinput.lookup(name) is None


def test_unsupported_reason_distinguishes_cases():
    assert "鼠标" in keyinput.unsupported_reason("Mouse0")
    assert "未设置" in keyinput.unsupported_reason("")
    assert "不认识" in keyinput.unsupported_reason("Whatever")


# --------------------------------------------------------------- 发送

def test_send_key_refuses_unsupported_without_touching_system():
    ok, reason = keyinput.send_key("Mouse0")
    assert ok is False
    assert "鼠标" in reason


def test_send_key_refuses_empty_name():
    ok, reason = keyinput.send_key("")
    assert ok is False
    assert reason


@pytest.mark.skipif(not keyinput.IS_WINDOWS, reason="SendInput 只在 Windows 上可用")
def test_make_input_uses_scancode_and_flag_bits():
    """按住与抬起两条 INPUT 都要走扫描码（wVk=0），抬起额外带 KEYEVENTF_KEYUP。"""
    key = keyinput.lookup("V")
    down = keyinput._make_input(key, up=False)
    up = keyinput._make_input(key, up=True)
    for item in (down, up):
        assert item.ki.wVk == 0
        assert item.ki.dwFlags & keyinput.KEYEVENTF_SCANCODE
    assert not (down.ki.dwFlags & keyinput.KEYEVENTF_KEYUP)
    assert up.ki.dwFlags & keyinput.KEYEVENTF_KEYUP


def test_send_key_returns_reason_when_not_windows(monkeypatch):
    monkeypatch.setattr(keyinput, "IS_WINDOWS", False)
    ok, reason = keyinput.send_key("V")
    assert ok is False
    assert "Windows" in reason


# -------------------------------------------------------- R32 组合键与注入方式

def test_parse_combo_single_key_has_no_modifiers():
    main, mods = keyinput.parse_combo("PrintScreen")
    assert main == keyinput.lookup("PrintScreen")
    assert mods == []


def test_parse_combo_reads_modifiers_in_written_order():
    main, mods = keyinput.parse_combo("Ctrl+Shift+F10")
    assert main.vk == 0x79                       # F10
    assert [m.vk for m in mods] == [0xA2, 0xA0]  # 左 Ctrl、左 Shift，顺序不能反


def test_parse_combo_is_spacing_insensitive():
    """`Ctrl + Shift + F10` 与 `ctrl+shift+f10` 是同一个组合（归一化先去掉空白）。"""
    assert keyinput.parse_combo("Ctrl + Shift + F10") == keyinput.parse_combo("ctrl+shift+f10")


def test_parse_combo_accepts_alias_and_side_specific_modifiers():
    assert [m.vk for m in keyinput.parse_combo("Control+Alt+V")[1]] == [0xA2, 0xA4]
    assert [m.vk for m in keyinput.parse_combo("RCtrl+RShift+RAlt+V")[1]] == [0xA3, 0xA1, 0xA5]


@pytest.mark.parametrize("name", ["Ctrl+Mouse0", "Ctrl+Whatever", "Ctrl+", "Meta+V"])
def test_parse_combo_rejects_what_it_cannot_press(name):
    assert keyinput.parse_combo(name) is None


def test_parse_combo_collapses_repeated_modifiers():
    """`Ctrl+Ctrl+V` 只按一次 Ctrl —— 重复按下同一个修饰键没有意义，还会让计数对不上。"""
    main, mods = keyinput.parse_combo("Ctrl+Ctrl+V")
    assert len(mods) == 1 and main == keyinput.lookup("V")


def test_unsupported_reason_explains_combo_problems():
    assert "Ctrl / Shift / Alt" in keyinput.unsupported_reason("Ctrl+Meta+V")
    assert "主键" in keyinput.unsupported_reason("Ctrl+Whatever")
    assert "鼠标" in keyinput.unsupported_reason("Ctrl+Mouse0")


@pytest.mark.skipif(not keyinput.IS_WINDOWS, reason="SendInput 只在 Windows 上可用")
def test_build_inputs_wraps_main_key_with_modifiers():
    """顺序必须是「修饰按下 → 主键按下 → 主键抬起 → 修饰逆序抬起」，且**一次**投递。"""
    combo = keyinput.parse_combo("Ctrl+Shift+F10")
    items = keyinput.build_inputs(combo, keyinput.MODE_SCAN)
    assert len(items) == 6                       # 2 个修饰 ×2（按下+抬起）+ 主键 ×2
    wvks = [it.ki.wVk for it in items]
    up = [bool(it.ki.dwFlags & keyinput.KEYEVENTF_KEYUP) for it in items]
    assert wvks == [0, 0, 0, 0, 0, 0]            # scan 模式一律不填 wVk
    assert up == [False, False, False, True, True, True]
    scans = [it.ki.wScan for it in items]
    assert scans == [0x1D, 0x2A, 0x44, 0x44, 0x2A, 0x1D]   # 左Ctrl、左Shift、F10，抬起逆序


@pytest.mark.skipif(not keyinput.IS_WINDOWS, reason="SendInput 只在 Windows 上可用")
def test_build_inputs_vk_mode_fills_virtual_key_not_scancode():
    """`mode="vk"` 对齐参考实现：wVk=<虚拟键码>、wScan=0、不带 SCANCODE 标志。"""
    items = keyinput.build_inputs(keyinput.parse_combo("V"), keyinput.MODE_VK)
    assert len(items) == 2
    for item in items:
        assert item.ki.wVk == ord("V")
        assert item.ki.wScan == 0
        assert not (item.ki.dwFlags & keyinput.KEYEVENTF_SCANCODE)
    assert items[0].ki.dwFlags == 0
    assert items[1].ki.dwFlags == keyinput.KEYEVENTF_KEYUP


def test_send_key_rejects_unknown_mode():
    ok, reason = keyinput.send_key("V", "telepathy")
    assert ok is False
    assert "注入方式" in reason


def test_send_key_refuses_unsupported_combo_without_touching_system():
    ok, reason = keyinput.send_key("Ctrl+Mouse0")
    assert ok is False
    assert "鼠标" in reason


# --------------------------------------------------------------- 前台窗口

def test_foreground_process_name_none_when_not_windows(monkeypatch):
    monkeypatch.setattr(keyinput, "IS_WINDOWS", False)
    assert keyinput.foreground_process_name() is None
    assert keyinput.foreground_is("EscapeFromTarkov.exe") is False


def test_foreground_is_compares_basename_case_insensitively(monkeypatch):
    monkeypatch.setattr(keyinput, "foreground_process_name",
                        lambda: r"C:\Games\EFT\EscapeFromTarkov.EXE")
    assert keyinput.foreground_is("escapefromtarkov.exe") is True
    assert keyinput.foreground_is("EscapeFromTarkov.exe") is True
    assert keyinput.foreground_is("chrome.exe") is False


def test_foreground_is_false_when_process_unknown(monkeypatch):
    monkeypatch.setattr(keyinput, "foreground_process_name", lambda: None)
    assert keyinput.foreground_is("EscapeFromTarkov.exe") is False


# --------------------------------------------------------------- 窗口消息注入（MODE_POST）
# 存在的理由：Windows 11 默认「按 Print Screen 打开截屏工具」，PrtSc 会被系统在到达游戏
# 之前吃掉。`SendInput` 返回成功、游戏收不到；`PostMessage` 直接写进窗口消息队列，
# 绕过全局钩子。实测（2026-11-02）本机游戏截图键就是 SysReq，只有换成 F10 才通。

def test_post_lparam_encodes_scan_and_flags():
    key = keyinput.lookup("F10")                 # vk 0x79 / scan 0x44 / 非扩展键
    down = keyinput._post_lparam(key, up=False)
    up = keyinput._post_lparam(key, up=True)
    assert down == 1 | (0x44 << 16)              # 重复次数 = 1，扫描码在 16-23 位
    assert up & (1 << 30) and up & (1 << 31)     # 30 / 31 位是「抬起 + 上一状态」
    assert (up & ~(1 << 30) & ~(1 << 31)) == down


def test_post_lparam_marks_extended_keys():
    key = keyinput.lookup("NumPadEnter")         # extended = True
    assert keyinput._post_lparam(key, up=False) & (1 << 24)


def test_post_key_refuses_on_non_windows(monkeypatch):
    monkeypatch.setattr(keyinput, "IS_WINDOWS", False)
    ok, reason = keyinput.post_key("F10")
    assert ok is False
    assert "Windows" in reason


def test_post_key_without_target_window_reports_it(monkeypatch):
    """没有前台窗口时不能假装成功 —— 否则又是「已发送 N 张」的假象。"""
    monkeypatch.setattr(keyinput, "foreground_hwnd", lambda: None)
    ok, reason = keyinput.post_key("F10")
    assert ok is False
    assert "目标窗口" in reason


def test_post_key_posts_down_then_up_for_plain_key(monkeypatch):
    posted = []
    # 直接替换 PostMessageW：用假的 user32 顶替真实调用
    class FakeUser32:
        @staticmethod
        def PostMessageW(hwnd, msg, wparam, lparam):
            posted.append((hwnd, msg, wparam, lparam))
            return 1
    import ctypes
    monkeypatch.setattr(ctypes.windll, "user32", FakeUser32, raising=False)
    ok, reason = keyinput.post_key("F10", hwnd=0x1234)
    assert ok is True, reason
    assert [m for _, m, _, _ in posted] == [keyinput.WM_KEYDOWN, keyinput.WM_KEYUP]
    assert [w for _, _, w, _ in posted] == [0x79, 0x79]
    assert all(h == 0x1234 for h, _, _, _ in posted)


def test_post_key_wraps_modifiers_in_order(monkeypatch):
    posted = []
    class FakeUser32:
        @staticmethod
        def PostMessageW(hwnd, msg, wparam, lparam):
            posted.append((msg, wparam))
            return 1
    import ctypes
    monkeypatch.setattr(ctypes.windll, "user32", FakeUser32, raising=False)
    ok, _ = keyinput.post_key("Ctrl+F10", hwnd=7)
    assert ok is True
    vks = [w for _, w in posted]
    # Ctrl 按下 → F10 按下 → F10 抬起 → Ctrl 抬起
    ctrl_vk = keyinput.lookup("ctrl").vk          # 左 Ctrl（工程里 ctrl 就是左边那个）
    assert vks == [ctrl_vk, 0x79, 0x79, ctrl_vk]
    assert [m for m, _ in posted] == [keyinput.WM_KEYDOWN, keyinput.WM_KEYDOWN,
                                      keyinput.WM_KEYUP, keyinput.WM_KEYUP]


def test_post_key_uses_syskey_message_for_alt(monkeypatch):
    posted = []
    class FakeUser32:
        @staticmethod
        def PostMessageW(hwnd, msg, wparam, lparam):
            posted.append(msg)
            return 1
    import ctypes
    monkeypatch.setattr(ctypes.windll, "user32", FakeUser32, raising=False)
    keyinput.post_key("Alt+F10", hwnd=7)
    assert keyinput.WM_SYSKEYDOWN in posted and keyinput.WM_SYSKEYUP in posted


def test_send_key_dispatches_post_mode(monkeypatch):
    """`MODE_POST` 必须走 post_key，不能落回 SendInput。"""
    called = {}
    monkeypatch.setattr(keyinput, "post_key",
                        lambda name: (called.setdefault("name", name), (True, ""))[1])
    ok, _ = keyinput.send_key("F10", keyinput.MODE_POST)
    assert ok is True
    assert called["name"] == "F10"


def test_post_mode_is_declared():
    assert keyinput.MODE_POST in keyinput.MODES
