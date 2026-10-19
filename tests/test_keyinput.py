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
