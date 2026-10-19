#!/usr/bin/env python3
"""EFT 互动地图 · 模拟按键（运行期，纯标准库）

自动截图需要「按下游戏内截图键」，而截图键只能来自**模拟输入**——本模块用 Windows 的
`SendInput` 注入一次「按下 + 抬起」，不注入进程、不挂钩子、不改游戏文件。

## 为什么走 scancode

`SendInput` 有两种填法：填虚拟键码（wVk）或填扫描码（wScan + KEYEVENTF_SCANCODE）。
游戏（尤其 DirectInput / 原生化输入）通常直接读**扫描码**，而送 vk 的按键在部分设备上
会被忽略，所以这里统一走扫描码：`wVk=0`、`wScan=<扫描码>`、必要时加 `KEYEVENTF_EXTENDEDKEY`。

## 调用前提

模拟按键只能打到**前台窗口**。因此调用方（serve.AutoShotter）在发键前必须先确认
前台窗口的进程是 `EscapeFromTarkov.exe`；本模块提供 `foreground_process_name()` /
`foreground_is()` 做这个判断。

## 非 Windows / 不支持的按键

非 Windows 平台、以及鼠标按键（`Mouse0`、`Mouse Scroll` 等本工具不模拟），
一律返回 (False, 原因) 或 None，**绝不误点**。
"""

from __future__ import annotations

import os
import re
import sys
from collections import namedtuple

# 键名 → 实际按键。extended=True 的键需要 KEYEVENTF_EXTENDEDKEY（如方向键、右 Ctrl）。
Key = namedtuple("Key", "vk scan extended")

IS_WINDOWS = sys.platform == "win32"

# ---------------------------------------------------------------- 扫描码表
_LETTER_SCAN = {
    "q": 0x10, "w": 0x11, "e": 0x12, "r": 0x13, "t": 0x14, "y": 0x15, "u": 0x16,
    "i": 0x17, "o": 0x18, "p": 0x19,
    "a": 0x1E, "s": 0x1F, "d": 0x20, "f": 0x21, "g": 0x22, "h": 0x23, "j": 0x24,
    "k": 0x25, "l": 0x26,
    "z": 0x2C, "x": 0x2D, "c": 0x2E, "v": 0x2F, "b": 0x30, "n": 0x31, "m": 0x32,
}

_DIGIT_SCAN = {
    "1": 0x02, "2": 0x03, "3": 0x04, "4": 0x05, "5": 0x06,
    "6": 0x07, "7": 0x08, "8": 0x09, "9": 0x0A, "0": 0x0B,
}

_FKEY_SCAN = {
    1: 0x3B, 2: 0x3C, 3: 0x3D, 4: 0x3E, 5: 0x3F, 6: 0x40,
    7: 0x41, 8: 0x42, 9: 0x43, 10: 0x44, 11: 0x57, 12: 0x58,
}

# 具名键（键名统一做「去空白/下划线/连字符 + 小写」归一化后再查）
_NAMED = {
    "space": Key(0x20, 0x39, False),
    "escape": Key(0x1B, 0x01, False), "esc": Key(0x1B, 0x01, False),
    "tab": Key(0x09, 0x0F, False),
    "enter": Key(0x0D, 0x1C, False), "return": Key(0x0D, 0x1C, False),
    "backspace": Key(0x08, 0x0E, False), "back": Key(0x08, 0x0E, False),
    "capslock": Key(0x14, 0x3A, False), "caps": Key(0x14, 0x3A, False),
    "shift": Key(0xA0, 0x2A, False), "leftshift": Key(0xA0, 0x2A, False), "lshift": Key(0xA0, 0x2A, False),
    "rightshift": Key(0xA1, 0x36, False), "rshift": Key(0xA1, 0x36, False),
    "ctrl": Key(0xA2, 0x1D, False), "control": Key(0xA2, 0x1D, False),
    "leftctrl": Key(0xA2, 0x1D, False), "leftcontrol": Key(0xA2, 0x1D, False), "lctrl": Key(0xA2, 0x1D, False),
    "rightctrl": Key(0xA3, 0x1D, True), "rightcontrol": Key(0xA3, 0x1D, True), "rctrl": Key(0xA3, 0x1D, True),
    "alt": Key(0xA4, 0x38, False), "leftalt": Key(0xA4, 0x38, False), "lalt": Key(0xA4, 0x38, False),
    "rightalt": Key(0xA5, 0x38, True), "ralt": Key(0xA5, 0x38, True), "altgr": Key(0xA5, 0x38, True),
    "win": Key(0x5B, 0x5B, True), "leftwin": Key(0x5B, 0x5B, True), "lwin": Key(0x5B, 0x5B, True),
    "rightwin": Key(0x5C, 0x5C, True), "rwin": Key(0x5C, 0x5C, True),
    "minus": Key(0xBD, 0x0C, False),
    "equals": Key(0xBB, 0x0D, False), "plus": Key(0xBB, 0x0D, False),
    "leftbracket": Key(0xDB, 0x1A, False), "lbracket": Key(0xDB, 0x1A, False),
    "rightbracket": Key(0xDD, 0x1B, False), "rbracket": Key(0xDD, 0x1B, False),
    "backslash": Key(0xDC, 0x2B, False),
    "semicolon": Key(0xBA, 0x27, False),
    "quote": Key(0xDE, 0x28, False),
    "comma": Key(0xBC, 0x33, False),
    "period": Key(0xBE, 0x34, False), "dot": Key(0xBE, 0x34, False),
    "slash": Key(0xBF, 0x35, False),
    "backquote": Key(0xC0, 0x29, False), "grave": Key(0xC0, 0x29, False), "tilde": Key(0xC0, 0x29, False),
    "up": Key(0x26, 0x48, True), "down": Key(0x28, 0x50, True),
    "left": Key(0x25, 0x4B, True), "right": Key(0x27, 0x4D, True),
    "home": Key(0x24, 0x47, True), "end": Key(0x23, 0x4F, True),
    "pageup": Key(0x21, 0x49, True), "pgup": Key(0x21, 0x49, True),
    "pagedown": Key(0x22, 0x51, True), "pgdn": Key(0x22, 0x51, True),
    "insert": Key(0x2D, 0x52, True), "ins": Key(0x2D, 0x52, True),
    "delete": Key(0x2E, 0x53, True), "del": Key(0x2E, 0x53, True),
    "numlock": Key(0x90, 0x45, False),
    "scrolllock": Key(0x91, 0x46, False),
    "printscreen": Key(0x2C, 0x37, True), "prtsc": Key(0x2C, 0x37, True),
    "numpad0": Key(0x60, 0x52, False), "numpad1": Key(0x61, 0x4F, False),
    "numpad2": Key(0x62, 0x50, False), "numpad3": Key(0x63, 0x51, False),
    "numpad4": Key(0x64, 0x4B, False), "numpad5": Key(0x65, 0x4C, False),
    "numpad6": Key(0x66, 0x4D, False), "numpad7": Key(0x67, 0x47, False),
    "numpad8": Key(0x68, 0x48, False), "numpad9": Key(0x69, 0x49, False),
    "numpadmultiply": Key(0x6A, 0x37, False), "numpadmul": Key(0x6A, 0x37, False),
    "numpadadd": Key(0x6B, 0x4E, False), "numpadplus": Key(0x6B, 0x4E, False),
    "numpadsubtract": Key(0x6D, 0x4A, False), "numpadminus": Key(0x6D, 0x4A, False),
    "numpaddecimal": Key(0x6E, 0x53, False), "numpaddot": Key(0x6E, 0x53, False),
    "numpaddivide": Key(0x6F, 0x35, True), "numpadslash": Key(0x6F, 0x35, True),
    "numpadenter": Key(0x0D, 0x1C, True),
}

_FKEY_RE = re.compile(r"^f(\d{1,2})$")


def normalize(name) -> str:
    """键名归一化：去掉空白/下划线/连字符并转小写（`Left Shift` → `leftshift`）。"""
    if not isinstance(name, str):
        return ""
    return re.sub(r"[\s_\-]+", "", name).lower()


def lookup(name) -> Key | None:
    """键名 → Key(vk, scan, extended)；不认识（含鼠标、组合键）返回 None。"""
    norm = normalize(name)
    if not norm:
        return None
    if norm in _NAMED:
        return _NAMED[norm]
    if len(norm) == 1:
        if norm in _LETTER_SCAN:
            return Key(ord(norm.upper()), _LETTER_SCAN[norm], False)
        if norm in _DIGIT_SCAN:
            return Key(0x30 + int(norm), _DIGIT_SCAN[norm], False)
    m = _FKEY_RE.match(norm)
    if m:
        number = int(m.group(1))
        if 1 <= number <= 12:
            return Key(0x6F + number, _FKEY_SCAN[number], False)
    return None


def unsupported_reason(name) -> str:
    """给一个「为什么这个键没被支持」的说法，让界面能讲清楚。（不是组合键，只是字符串描述。）"""
    if not name or not isinstance(name, str) or not name.strip():
        return "未设置按键"
    if normalize(name).startswith("mouse"):
        return "鼠标按键不在支持范围内，请改用键盘按键"
    return "不认识这个按键：%s" % name.strip()


# ---------------------------------------------------------------- Windows 注入
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
INPUT_KEYBOARD = 1


if IS_WINDOWS:                                   # pragma: no cover - 仅在 Windows 上定义结构
    import ctypes
    from ctypes import wintypes

    ULONG_PTR = ctypes.c_ulong if ctypes.sizeof(ctypes.c_void_p) == 4 else ctypes.c_ulonglong

    class _KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ULONG_PTR),
        ]

    class _MOUSEINPUT(ctypes.Structure):
        _fields_ = [
            ("dx", wintypes.LONG),
            ("dy", wintypes.LONG),
            ("mouseData", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ULONG_PTR),
        ]

    class _HARDWAREINPUT(ctypes.Structure):
        _fields_ = [
            ("uMsg", wintypes.DWORD),
            ("wParamL", wintypes.WORD),
            ("wParamH", wintypes.WORD),
        ]

    class _INPUTUNION(ctypes.Union):
        _fields_ = [("ki", _KEYBDINPUT), ("mi", _MOUSEINPUT), ("hi", _HARDWAREINPUT)]

    class _INPUT(ctypes.Structure):
        _anonymous_ = ("union",)
        _fields_ = [("type", wintypes.DWORD), ("union", _INPUTUNION)]


def _make_input(key: "Key", up: bool):
    """构造一条键盘 INPUT（按扫描码注入）。"""
    import ctypes

    flags = KEYEVENTF_SCANCODE
    if key.extended:
        flags |= KEYEVENTF_EXTENDEDKEY
    if up:
        flags |= KEYEVENTF_KEYUP
    item = _INPUT()
    item.type = INPUT_KEYBOARD
    item.ki.wVk = 0
    item.ki.wScan = key.scan
    item.ki.dwFlags = flags
    item.ki.time = 0
    item.ki.dwExtraInfo = 0
    return item


def send_key(name) -> tuple[bool, str]:
    """模拟「按下 + 抬起」一次；返回 (是否成功, 失败原因)。不支持的键不发送。"""
    key = lookup(name)
    if key is None:
        return False, unsupported_reason(name)
    if not IS_WINDOWS:
        return False, "模拟按键仅在 Windows 上可用"
    import ctypes

    try:
        down = _make_input(key, up=False)
        up = _make_input(key, up=True)
        array = (_INPUT * 2)(down, up)
        sent = ctypes.windll.user32.SendInput(2, array, ctypes.sizeof(_INPUT))
    except (AttributeError, OSError, ValueError) as exc:
        return False, "模拟按键失败：%s" % exc
    if sent != 2:
        return False, "按键未送达（可能被系统或安全软件拦截）"
    return True, ""


# ---------------------------------------------------------------- 前台窗口
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def foreground_process_name() -> str | None:
    """前台窗口所属进程的可执行文件全路径；取不到（非 Windows / 无权限）返回 None。"""
    if not IS_WINDOWS:
        return None
    import ctypes

    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None
        pid = ctypes.c_ulong(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value:
            return None
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
        if not handle:
            return None
        try:
            buf = ctypes.create_unicode_buffer(1024)
            size = ctypes.c_ulong(len(buf))
            if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
                return buf.value or None
            return None
        finally:
            kernel32.CloseHandle(handle)
    except (AttributeError, OSError, ValueError):
        return None


def foreground_is(name) -> bool:
    """前台窗口的进程名是否等于 `name`（比较文件名，忽略大小写与路径）。"""
    proc = foreground_process_name()
    if not proc:
        return False
    return os.path.basename(proc).lower() == str(name).lower()
