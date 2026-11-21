#!/usr/bin/env python3
"""EFT 互动地图 · 模拟按键（运行期，纯标准库）

自动截图需要「按下游戏内截图键」，而截图键只能来自**模拟输入**——本模块用 Windows 的
`SendInput` 注入一次「按下 + 抬起」，不注入进程、不挂钩子、不改游戏文件。

## 为什么走 scancode

`SendInput` 有两种填法：填虚拟键码（wVk）或填扫描码（wScan + KEYEVENTF_SCANCODE）。
游戏（尤其 DirectInput / 原生化输入）通常直接读**扫描码**，而送 vk 的按键在部分设备上
会被忽略，所以这里统一走扫描码：`wVk=0`、`wScan=<扫描码>`、必要时加 `KEYEVENTF_EXTENDEDKEY`。

## 两种注入方式

| `mode` | `wVk` | `wScan` / 标志 | 说明 |
| --- | --- | --- | --- |
| `scan` | 0 | `<扫描码>` + `KEYEVENTF_SCANCODE` | 默认，历史行为 |
| `vk` | `<虚拟键码>` | 0 | 对齐参考实现（XiaoMeow `InputSender`） |
| `post` | — | — | 不走 `SendInput`，直接 `PostMessage(WM_KEYDOWN)` 进目标窗口 |

两种 `SendInput` 都有人用、也都有游戏认。**默认仍是 `scan`**（不改变既有行为），由调用方
（`serve.AutoShotter`）在「发了但截图没出现」时自动切到 `vk` 再试。

`post` 是兜底：`SendInput` 投递的是系统级输入，要先过全局键盘钩子和热键注册。Windows 11
默认开着「按 Print Screen 打开截屏工具」，这个键在到达游戏之前就被系统吃掉了 ——
`SendInput` 返回成功、游戏一无所获。`post` 直接把按键写进窗口消息队列，绕开那条链路。

## 组合键

`"Ctrl+Shift+F10"` 这种写法现在能认了：所有修饰键与主键**在一次 `SendInput` 里**
按「修饰按下 → 主键按下 → 主键抬起 → 修饰逆序抬起」整体投递。参考实现就是这么做的，
分开投递会在部分游戏里被当成两段输入。

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
    # SysRq 与 PrintScreen 是同一个物理键，EFT 的控制绑定里写作 `SysReq`，两个名字都要认
    "printscreen": Key(0x2C, 0x37, True), "prtsc": Key(0x2C, 0x37, True),
    "sysreq": Key(0x2C, 0x37, True), "sysrq": Key(0x2C, 0x37, True),
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

# 注入方式：
#   scan = 扫描码（默认，历史行为）
#   vk   = 虚拟键码（对齐参考实现）
#   post = 直接把 WM_KEYDOWN/WM_KEYUP 投递进目标窗口的消息队列
MODE_SCAN = "scan"
MODE_VK = "vk"
MODE_POST = "post"
MODES = (MODE_SCAN, MODE_VK, MODE_POST)

# 组合键里可以出现在「主键之前」的修饰键（归一化名 → _NAMED 里的键）
_MODIFIER_ALIASES = {
    "ctrl": "ctrl", "control": "control",
    "leftctrl": "leftctrl", "lctrl": "lctrl",
    "rightctrl": "rightctrl", "rctrl": "rctrl",
    "shift": "shift", "leftshift": "leftshift", "lshift": "lshift",
    "rightshift": "rightshift", "rshift": "rshift",
    "alt": "alt", "leftalt": "leftalt", "lalt": "lalt",
    "rightalt": "rightalt", "ralt": "ralt", "altgr": "altgr",
}


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
    norm = normalize(name)
    if any(part.startswith("mouse") for part in norm.split("+")):
        return "鼠标按键不在支持范围内，请改用键盘按键"
    parts = norm.split("+")
    if len(parts) > 1:
        for part in parts[:-1]:
            if part not in _MODIFIER_ALIASES:
                return "组合键里只支持 Ctrl / Shift / Alt，不认识：%s" % part
        if lookup(parts[-1]) is None:
            return "组合键的最后一段必须是主键，不认识：%s" % parts[-1]
    return "不认识这个按键：%s" % name.strip()


def parse_combo(name):
    """`"Ctrl+Shift+F10"` → `(主键 Key, [修饰 Key, ...])`；解析不了返回 None。

    单键（`"V"`、`"PrintScreen"`）也会正常返回 `(Key, [])`，所以调用方可以只用这一个入口：
    先归一化（去空白/下划线/连字符、转小写），再按 `+` 切；**最后一段是主键**，
    前面每段都必须是 Ctrl / Shift / Alt 家族，否则整个键名判为不支持（绝不猜）。
    """
    norm = normalize(name)
    if not norm:
        return None
    parts = norm.split("+")
    main = lookup(parts[-1])
    if main is None:
        return None
    mods = []
    seen = set()
    for part in parts[:-1]:
        alias = _MODIFIER_ALIASES.get(part)
        if alias is None:
            return None
        key = _NAMED.get(alias)
        if key is None:            # 理论上不会发生：别名表与 _NAMED 同源
            return None
        if key.vk in seen:         # `Ctrl+Ctrl+V` 这种重复写法只按一次算，别真按两下
            continue
        seen.add(key.vk)
        mods.append(key)
    return main, mods


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


def _make_input(key: "Key", up: bool, mode: str = MODE_SCAN):
    """构造一条键盘 INPUT。

    `mode="scan"`（默认）填 `wScan` + `KEYEVENTF_SCANCODE`，`wVk=0`；
    `mode="vk"` 反过来填 `wVk`，`wScan=0`、不带 SCANCODE 标志。
    """
    import ctypes

    flags = 0
    if mode == MODE_VK:
        vk, scan = key.vk, 0
    else:
        vk, scan = 0, key.scan
        flags |= KEYEVENTF_SCANCODE
        if key.extended:
            flags |= KEYEVENTF_EXTENDEDKEY
    if up:
        flags |= KEYEVENTF_KEYUP
    item = _INPUT()
    item.type = INPUT_KEYBOARD
    item.ki.wVk = vk
    item.ki.wScan = scan
    item.ki.dwFlags = flags
    item.ki.time = 0
    item.ki.dwExtraInfo = 0
    return item


def build_inputs(combo, mode: str = MODE_SCAN) -> list:
    """`(主键, [修饰...])` → 一次投递用的 INPUT 列表。

    顺序固定为「修饰按下（按书写顺序）→ 主键按下 → 主键抬起 → 修饰抬起（逆序）」，
    这样主键的按下/抬起一定夹在修饰键按住的时间窗里（游戏读的是「按下时的修饰状态」）。
    """
    main, mods = combo
    items = [_make_input(m, up=False, mode=mode) for m in mods]
    items.append(_make_input(main, up=False, mode=mode))
    items.append(_make_input(main, up=True, mode=mode))
    items.extend(_make_input(m, up=True, mode=mode) for m in reversed(mods))
    return items


def send_key(name, mode: str = MODE_SCAN) -> tuple[bool, str]:
    """模拟「按下 + 抬起」一次（支持 `Ctrl+Shift+F10` 这种组合）；返回 (是否成功, 失败原因)。

    不支持的键一律不发送。所有事件（含修饰键）在**同一次** `SendInput` 里投递。
    """
    if mode not in MODES:
        return False, "未知的注入方式：%s" % mode
    combo = parse_combo(name)
    if combo is None:
        return False, unsupported_reason(name)
    if not IS_WINDOWS:
        return False, "模拟按键仅在 Windows 上可用"
    if mode == MODE_POST:
        return post_key(name)
    import ctypes

    try:
        items = build_inputs(combo, mode)
        array = (_INPUT * len(items))(*items)
        sent = ctypes.windll.user32.SendInput(len(items), array, ctypes.sizeof(_INPUT))
    except (AttributeError, OSError, ValueError) as exc:
        return False, "模拟按键失败：%s" % exc
    if sent != len(items):
        return False, "按键未送达（可能被系统或安全软件拦截）"
    return True, ""


# ---------------------------------------------------------------- 窗口消息注入
# 为什么还需要第三种方式：`SendInput` 投递的是**系统级**输入，会先过一遍全局键盘钩子
# 与热键注册。Windows 11 默认开着「按 Print Screen 打开截屏工具」，这个键在到达游戏
# 之前就被系统吃掉了 —— `SendInput` 返回成功，游戏一无所获，现象和「注入被反作弊拦」一模一样。
# `PostMessage(WM_KEYDOWN)` 直接写进目标窗口的消息队列，不经过那条链路，因此能绕开它。
# 代价是只对「按窗口消息读键盘」的程序有效（多数 Unity 游戏可以），所以它是兜底而非默认。
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
_VK_ALT = 0x12
# 左/右 Alt 的具体键码：`Alt` 走的是左边那个，只判 0x12 会让组合键退化成普通 WM_KEYDOWN
_VK_ALT_SIDED = frozenset({0x12, 0xA4, 0xA5})
_VK_LWIN = 0x5B
_VK_RWIN = 0x5C


def foreground_hwnd() -> int | None:
    """前台窗口句柄；取不到返回 None。"""
    if not IS_WINDOWS:
        return None
    import ctypes

    try:
        return int(ctypes.windll.user32.GetForegroundWindow() or 0) or None
    except (AttributeError, OSError, ValueError):
        return None


def _post_lparam(key, up: bool) -> int:
    """WM_KEYDOWN/UP 的 lParam：低 16 位重复次数，16-23 扫描码，24 扩展位，30/31 抬起标志。"""
    value = 1 | (int(key.scan) << 16)
    if key.extended:
        value |= 1 << 24
    if up:
        value |= (1 << 30) | (1 << 31)
    return value


def post_key(name, hwnd: int | None = None) -> tuple[bool, str]:
    """把一次「按下 + 抬起」（含修饰键）以窗口消息的形式投递给 `hwnd`（默认前台窗口）。

    只在 `MODE_POST` 下由 `send_key` 调用；也可直接调用来探测某个窗口收不收消息。
    """
    combo = parse_combo(name)
    if combo is None:
        return False, unsupported_reason(name)
    if not IS_WINDOWS:
        return False, "模拟按键仅在 Windows 上可用"
    import ctypes
    from ctypes import wintypes

    target = hwnd or foreground_hwnd()
    if not target:
        return False, "没有可投递的目标窗口"
    main, mods = combo
    steps = [(m, False) for m in mods] + [(main, False)]
    steps += [(main, True)] + [(m, True) for m in reversed(mods)]
    try:
        user32 = ctypes.windll.user32
        # 不声明 argtypes 时 64 位句柄会按 c_int 截断，PostMessage 会静默失败
        user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT,
                                        wintypes.WPARAM, wintypes.LPARAM]
        user32.PostMessageW.restype = wintypes.BOOL
    except (AttributeError, OSError, ValueError) as exc:
        return False, "准备窗口消息失败：%s" % exc
    failed = 0
    for key, is_up in steps:
        alt = key.vk in _VK_ALT_SIDED or key.vk in (_VK_LWIN, _VK_RWIN)
        if is_up:
            msg = WM_SYSKEYUP if alt else WM_KEYUP
        else:
            msg = WM_SYSKEYDOWN if alt else WM_KEYDOWN
        try:
            if not user32.PostMessageW(target, msg, key.vk, _post_lparam(key, is_up)):
                failed += 1
        except (AttributeError, OSError, ValueError):
            failed += 1
    if failed:
        return False, "窗口消息投递失败 %d/%d（窗口可能已关闭或无权限）" % (failed, len(steps))
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


def foreground_pid() -> int | None:
    """前台窗口所属进程的 PID；取不到（非 Windows / 无前台窗口）返回 None。"""
    if not IS_WINDOWS:
        return None
    import ctypes
    from ctypes import wintypes

    try:
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        if not hwnd:
            return None
        pid = wintypes.DWORD(0)
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return int(pid.value) or None
    except (AttributeError, OSError, ValueError):
        return None


# ---------------------------------------------------------------- 权限对等
# Windows 的 UIPI（用户界面特权隔离）会**静默丢弃**低完整性进程发往高完整性窗口的
# `SendInput`：返回值照样是「成功」，但键根本没送进去。这是「模拟按键毫无反应、
# 代码却报成功」最经典的原因——游戏以管理员运行时，普通权限的工具必然中招。
TOKEN_QUERY = 0x0008
_TOKEN_ELEVATION = 20
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def _token_is_elevated(token_handle) -> bool | None:
    import ctypes
    from ctypes import wintypes

    class TOKEN_ELEVATION(ctypes.Structure):
        _fields_ = [("TokenIsElevated", wintypes.DWORD)]

    advapi32 = ctypes.windll.advapi32
    advapi32.GetTokenInformation.argtypes = [
        ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32,
        ctypes.POINTER(ctypes.c_uint32)]
    advapi32.GetTokenInformation.restype = ctypes.c_int

    info = TOKEN_ELEVATION()
    size = wintypes.DWORD(0)
    ok = advapi32.GetTokenInformation(
        token_handle, _TOKEN_ELEVATION, ctypes.byref(info),
        ctypes.sizeof(info), ctypes.byref(size))
    if not ok:
        return None
    return bool(info.TokenIsElevated)


def _handle_elevation(raw_handle) -> bool | None:
    """给一个进程句柄，问它「这个进程提权了吗」。

    句柄在 64 位下是 8 字节指针：必须显式声明 `c_void_p` 的 argtypes，
    否则 ctypes 会当成 int 转换，传 `-1`（伪句柄）时直接 OverflowError。
    """
    import ctypes

    advapi32 = ctypes.windll.advapi32
    kernel32 = ctypes.windll.kernel32
    advapi32.OpenProcessToken.argtypes = [
        ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p)]
    advapi32.OpenProcessToken.restype = ctypes.c_int
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.restype = ctypes.c_int

    token = ctypes.c_void_p()
    if not advapi32.OpenProcessToken(
            ctypes.c_void_p(raw_handle), TOKEN_QUERY, ctypes.byref(token)):
        return None
    try:
        return _token_is_elevated(token)
    finally:
        kernel32.CloseHandle(token)


def is_elevated() -> bool | None:
    """**本进程**是否以管理员身份运行；查不到返回 None。"""
    if not IS_WINDOWS:
        return None
    import ctypes

    try:
        kernel32 = ctypes.windll.kernel32
        kernel32.GetCurrentProcess.argtypes = []
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        return _handle_elevation(kernel32.GetCurrentProcess())
    except (AttributeError, OSError, ValueError):
        return None


def process_elevated(pid: int | None) -> bool | None:
    """指定进程是否以管理员身份运行；打不开进程（权限不足 / 已退出）返回 None。"""
    if not IS_WINDOWS or not pid:
        return None
    import ctypes

    try:
        kernel32 = ctypes.windll.kernel32
        kernel32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
        kernel32.OpenProcess.restype = ctypes.c_void_p
        handle = kernel32.OpenProcess(
            _PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not handle:
            return None
        try:
            return _handle_elevation(handle)
        finally:
            kernel32.CloseHandle(ctypes.c_void_p(handle))
    except (AttributeError, OSError, ValueError):
        return None


def injection_blocked(pid: int | None = None) -> str | None:
    """判断「往这个进程发模拟输入会不会被 UIPI 静默丢弃」；会被拦就返回一句人话。

    规则只有一条：**目标进程提权了、本进程没有** → 一定被拦。
    反过来（本进程提权、目标没有）不受影响，允许注入。
    查不出来时返回 None（不冤枉系统，也不假装没问题——交给到货校验兜底）。
    """
    target = process_elevated(pid if pid is not None else foreground_pid())
    if target is None:
        return None
    if target and not is_elevated():
        return ("目标进程以管理员身份运行，而本工具不是：Windows 会静默丢弃这样的模拟输入"
                "（返回值仍显示成功，但游戏收不到）。请右键「以管理员身份运行」再试。")
    return None


# ---------------------------------------------------------------- 注入方式选择
# 走扫描码会失效 / 行为不一致的键：一律改用虚拟键码。
#   VK_SNAPSHOT（PrintScreen / SysRq，scan 0x37 + 扩展位）是最典型的一个：
#   用 SCANCODE 注入时，系统按「截屏到剪贴板」处理，游戏侧根本收不到这个按键。
#   参考实现（XiaoMeow InputSender）全部走虚拟键码，不受这个问题影响。
_VK_ONLY_VKS = frozenset({0x2C})


def preferred_mode(name, fallback: str = MODE_SCAN) -> str:
    """这个键该用哪种注入方式。

    PrintScreen / SysRq 家族**强制虚拟键码**（扫描码对它们无效），其余沿用 `fallback`
    （默认扫描码，即项目历史行为）。
    """
    combo = parse_combo(name)
    if combo is not None and combo[0].vk in _VK_ONLY_VKS:
        return MODE_VK
    return fallback
