#!/usr/bin/env python3
"""EFT 互动地图 · 置顶小浮窗（游戏内小地图）宿主（运行期，纯标准库）

把 `index.html?mini=1` 放进一个**无边框、常驻置顶、可点击穿透**的浏览器应用窗口里，
就得到一个盖在游戏画面上的小地图。

## 为什么是「宿主窗口 + 网页」而不是自己画地图

参考实现（XiaoMeow `MiniMapWindow`）就是这么做的：它是一个 WebView2 窗口，加载自家
网页的 mini 模式（`…/minimap?size=&opacity=&shape=`），地图渲染、缩放、图标、玩家跟随
全在网页里。本项目本来就是网页，所以这一层几乎是白送的——难点只剩「置顶 + 点击穿透 +
不抢焦点」，而这三件事浏览器做不到，必须改 Win32 扩展样式。

## 关键约束：必须走 http，不能用 file://

页面要 `fetch("api/…")` 拿实时定位、图层偏好、事件流。`file://` 下这些相对请求会被
浏览器的同源策略拦掉，页面会静默地「地图能看、但永远不跟随玩家」。所以默认地址是
本机服务 `http://127.0.0.1:8810/index.html?mini=1…`，并且**先探一次 `/api/health`**，
服务没开就直接说清楚，而不是给你一个不更新的小窗。

## 用法

    python tools/overlay.py                                  # 右下角、260px、方形、90%
    python tools/overlay.py --corner top-left --size 300 --opacity 0.8 --shape circle
    python tools/overlay.py --no-click-through               # 调试：能点得到小窗
    python tools/overlay.py --hotkey off                      # 不注册全局热键
    python tools/overlay.py --dry-run                        # 只打印计划，不启动任何窗口

关闭：关掉那个小窗即可（宿主会跟着退出，不驻留后台、不进托盘）。
全局热键（默认 `Ctrl+Alt+M`）在「小窗 / 大图」之间来回切。

## 与参考实现对齐的细节

1. **四角吸附**：边距固定 16 DIP，再叠加 `--offset-x / --offset-y`（对齐 `ApplyBounds`）；
2. **点击穿透**：`WS_EX_LAYERED | WS_EX_TRANSPARENT`，鼠标事件直接穿到游戏；
3. **不抢焦点、不进 Alt+Tab**：`WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW`；
4. **常驻置顶**：`SetWindowPos(HWND_TOPMOST, …)`；
5. **小窗 / 大图切换**：参考实现是 `window.__xmMiniFull('on'|'off')`，这里用「改窗口尺寸」
   实现同样的效果（页面本身自适应窗口大小），并额外提供页面侧的 `window.__tkMiniFull`。

## 边界

- 只支持 Windows；非 Windows 上一律报「不支持」并退出，不做任何模拟。
- 需要本机装了 Edge（绝大多数 Windows 都有）或 Chrome；找不到就明确报错，不下载浏览器。
- 这个脚本**只改窗口样式**：不注入进程、不读游戏内存、不改游戏文件。
- 圆角/圆形「真正透明」做不到：普通浏览器窗口没有逐像素透明（那是 WebView2 的能力，
  属于新增依赖）。所以方形是默认；圆形时四角由页面按 `--bg` 涂成深色。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request

IS_WINDOWS = sys.platform == "win32"

# 四角吸附的固定边距（像素）—— 与参考实现 ApplyBounds 的 16 DIP 对齐
MARGIN = 16
CORNERS = ("top-left", "top-right", "bottom-left", "bottom-right")
SHAPES = ("circle", "square")

DEFAULT_SIZE = 260
SIZE_MIN, SIZE_MAX = 120, 1200
DEFAULT_OPACITY = 0.9
OPACITY_MIN, OPACITY_MAX = 0.3, 1.0

# 「大图」模式的尺寸（热键切换用）；参考实现里对应 `__xmMiniFull('on')`
FULL_SIZE = (900, 640)

DEFAULT_BASE = "http://127.0.0.1:8787/index.html"
DEFAULT_SERVER = "http://127.0.0.1:8787"

# 小地图页面的窗口标题（app.js 的 applyMiniMode 会把 title 改成它），用来认领窗口
MINI_TITLE = "EFT 小地图"

DEFAULT_HOTKEY = "Ctrl+Alt+M"

# WebView2 无边框宿主（可选组件）：优先用它，失败再回退到 Edge/Chrome 的 --app 窗口。
# 宿主源码与构建脚本在 tools/host/，产物是 bin/MiniHost.exe（csc 编译，不联网）。
HOST_EXE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "host", "bin", "MiniHost.exe")
HOST_MODES = ("auto", "webview2", "browser")

# 游戏日志里的地图 id → data/maps.json 的 key（与 app.js 的 MAP_ID_ALIASES 保持一致）。
# 宿主用 fresh WebView2 profile，拿不到用户浏览器的 localStorage，所以在启动时把当前地图塞进去。
MAP_ID_ALIASES = {
    "bigmap": "customs",
    "customs": "customs",
    "woods": "woods",
    "shoreline": "shoreline",
    "interchange": "interchange",
    "shopping_mall": "interchange",
    "rezervbase": "reserve",
    "reserve": "reserve",
    "lighthouse": "lighthouse",
    "tarkovstreets": "streets-of-tarkov",
    "city": "streets-of-tarkov",
    "factory4_day": "factory",
    "factory4_night": "factory",
    "factory": "factory",
    "sandbox_high": "ground-zero",
    "sandbox": "ground-zero",
    "terminal": "terminal",
}


class HostUnavailable(RuntimeError):
    """WebView2 宿主不可用（缺 Runtime / 缺 exe / 起不来）：调用方据此回退 --app。"""



# ---------------------------------------------------------------- 纯计算（可单测）
def plan_window(work, size, corner="bottom-right", offset_x=0, offset_y=0):
    """把「工作区 + 边长 + 角落」算成一个**正方形**窗口矩形。

    `work` 是 `(left, top, right, bottom)`（Windows 的 RECT 顺序，right/bottom 为开区间）。
    返回 `(x, y, w, h)`；**四角各留 MARGIN，再叠加偏移**，与参考实现一致。

    尺寸会被钳到 [SIZE_MIN, SIZE_MAX]，角落不认识时回落 `bottom-right`
    （宁可跑到右下角，也不要算出一个越界的坐标）。
    """
    left, top, right, bottom = work
    size = max(SIZE_MIN, min(SIZE_MAX, int(size)))
    return plan_rect(work, size, size, corner, offset_x, offset_y)


def plan_rect(work, width, height, corner="bottom-right", offset_x=0, offset_y=0):
    """非正方形窗口（大小图模式）用的四角吸附；规则与 `plan_window` 完全一致。"""
    left, top, right, bottom = work
    width = max(1, int(width))
    height = max(1, int(height))
    if corner not in CORNERS:
        corner = "bottom-right"
    is_left = corner in ("top-left", "bottom-left")
    is_top = corner in ("top-left", "top-right")
    x = (left + MARGIN) if is_left else (right - width - MARGIN)
    y = (top + MARGIN) if is_top else (bottom - height - MARGIN)
    return int(x + offset_x), int(y + offset_y), width, height


def build_url(base=DEFAULT_BASE, size=DEFAULT_SIZE, opacity=DEFAULT_OPACITY, shape="circle",
              labels=0, follow=0, bg=None, host_alpha=False):
    """把页面地址拼成 mini 模式地址（`…?mini=1&size=…&opacity=…&shape=…`）。

    `base` 必须是**服务地址**（`http://127.0.0.1:8810/index.html`）——`file://` 下页面
    拿不到 API，实时定位会失效。参数顺序固定，便于肉眼比对与测试。

    `host_alpha=True` 时带上 `ha=1`：透明度由宿主调**窗口**透明度，
    页面里的地图就别再压暗一次（不然两层叠加会显得过暗）。
    """
    if not base or not isinstance(base, str):
        raise ValueError("页面地址不能为空")
    if not base.startswith(("http://", "https://")):
        raise ValueError("页面地址必须走 http://（file:// 下页面拿不到实时定位）：%s" % base)
    shape = shape if shape in SHAPES else "circle"
    opacity = max(OPACITY_MIN, min(OPACITY_MAX, float(opacity)))
    size = max(SIZE_MIN, min(SIZE_MAX, int(size)))
    query = "mini=1&size=%d&opacity=%s&shape=%s&labels=%d&follow=%d" % (
        size, ("%.2f" % opacity).rstrip("0").rstrip("."), shape, 1 if labels else 0,
        1 if follow else 0)
    if bg:
        query += "&bg=" + urllib.parse.quote(str(bg), safe="")
    if host_alpha:
        query += "&ha=1"
    return "%s?%s" % (base, query)


def parse_hotkey(text):
    """`"Ctrl+Alt+M"` → `(modifiers, vk)`；`"off"` → None；不认识 → None。

    只支持 `Ctrl` / `Alt` / `Shift` / `Win` 修饰键 + 一个主键（字母 / 数字 / F1-F12）。
    """
    if not text or str(text).strip().lower() in ("off", "none", "no"):
        return None
    parts = [p for p in str(text).replace("-", "+").split("+") if p.strip()]
    if not parts:
        return None
    mod = 0
    mods = {"ctrl": 0x0002, "control": 0x0002, "alt": 0x0001, "shift": 0x0004, "win": 0x0008}
    main = None
    for raw in parts:
        name = raw.strip().lower()
        if name in mods:
            mod |= mods[name]
            continue
        main = name
    if main is None:
        return None
    if len(main) == 1 and main.isalpha():
        vk = ord(main.upper())
    elif main.isdigit():
        vk = 0x30 + int(main)
    elif main.startswith("f") and main[1:].isdigit() and 1 <= int(main[1:]) <= 24:
        vk = 0x70 + int(main[1:]) - 1
    else:
        return None
    return mod, vk


def describe(plan, url):
    """人类可读的一行计划（`--dry-run` 用，也方便贴日志）。"""
    x, y, w, h = plan
    return "窗口 %dx%d @ (%d, %d) ← %s" % (w, h, x, y, url)


def server_alive(server=DEFAULT_SERVER, timeout=1.5) -> bool:
    """服务是否在跑（探 `/api/health`）。探不通就**明确告诉用户先启动服务**。"""
    try:
        with urllib.request.urlopen(server.rstrip("/") + "/api/health", timeout=timeout) as res:
            return 200 <= res.status < 300
    except Exception:       # noqa: BLE001 - 探活失败就是「不通」，不是错误
        return False


def resolve_map_key(server=DEFAULT_SERVER, timeout=1.5):
    """从 `/api/logstate` 的当前战局里取地图 key；拿不到返回 None。

    宿主用的是独立 WebView2 profile，读不到用户浏览器的 localStorage，
    所以启动时要把「当前战局地图」显式塞给它，否则小窗会停在默认第一张图上。
    """
    try:
        url = server.rstrip("/") + "/api/logstate"
        with urllib.request.urlopen(url, timeout=timeout) as res:
            data = json.loads(res.read().decode("utf-8"))
    except Exception:       # noqa: BLE001 - 拿不到就交给页面自己的记忆
        return None
    raid = data.get("raid") or {}
    map_id = raid.get("mapId")
    if not map_id:
        return None
    return MAP_ID_ALIASES.get(str(map_id).lower())


def wait_host_window(proc, timeout=20.0, poll=0.2):
    """等宿主自己的窗口出现（标题 = EFT 小地图，且 pid 必须是这次起的进程）。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for hwnd, owner, text in _enum_windows():
            if text == MINI_TITLE and owner == proc.pid:
                return hwnd
        if proc.poll() is not None:
            return None
        time.sleep(poll)
    return None


def launch_host(url, config_dir, exe=None, click_through=None, map_key=None,
                hotkeys=True, timeout=20.0):
    """启动 WebView2 宿主；失败抛 HostUnavailable（由 main 决定是否回退 --app）。"""
    exe = exe or HOST_EXE
    if not os.path.isfile(exe):
        raise HostUnavailable("找不到 WebView2 宿主：%s（先运行 tools/host/build.ps1）" % exe)
    cmd = [exe, "--url", url]
    if config_dir:
        cmd += ["--config-dir", os.path.abspath(config_dir)]
    if map_key:
        cmd += ["--map-key", map_key]
    if click_through is not None:
        cmd += ["--click-through", "1" if click_through else "0"]
    if not hotkeys:
        cmd += ["--no-hotkey"]
    try:
        proc = subprocess.Popen(                      # noqa: S603 - 参数全部本地拼装
            cmd, cwd=os.path.dirname(exe),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (OSError, ValueError) as exc:
        raise HostUnavailable("拉起 WebView2 宿主失败：%s" % exc)
    hwnd = wait_host_window(proc, timeout=timeout)
    if hwnd is not None:
        return proc, hwnd
    code = proc.poll()
    if code is None:
        proc.terminate()
        raise HostUnavailable("宿主窗口在 %.0f 秒内没有出现" % timeout)
    if code == 3:
        raise HostUnavailable("WebView2 Runtime 不可用（宿主退出码 3）")
    if code == 0:
        return proc, None       # 配置里关掉了小浮窗，正常退出
    raise HostUnavailable("宿主启动失败，退出码 %d" % code)


def watch_host(proc):
    """宿主自己管热键 / 置顶 / 配置；Python 这边只等它退出，并保证不留孤儿进程。"""
    try:
        while proc.poll() is None:
            time.sleep(0.2)
    except KeyboardInterrupt:
        pass
    finally:
        if proc.poll() is None:
            try:
                subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],   # noqa: S603
                               capture_output=True, timeout=10, check=False,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            except (OSError, subprocess.SubprocessError):
                pass



# ---------------------------------------------------------------- Win32（只有真跑时才碰）
GWL_STYLE = -16
GWL_EXSTYLE = -20

WS_CAPTION = 0x00C00000
WS_THICKFRAME = 0x00040000
WS_SYSMENU = 0x00080000
WS_MINIMIZEBOX = 0x00020000
WS_MAXIMIZEBOX = 0x00010000
WS_BORDER = 0x00800000
WS_DLGFRAME = 0x00400000

WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080

HWND_TOPMOST = -1
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020
SWP_SHOWWINDOW = 0x0040
SPI_GETWORKAREA = 0x0030

WM_HOTKEY = 0x0312
LWA_ALPHA = 0x2

_BROWSER_CANDIDATES = (
    ("edge", r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    ("edge", r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    ("chrome", r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    ("chrome", r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
)


def find_browser(prefer="auto") -> tuple[str, str] | None:
    """找可用的浏览器 → `(名字, 路径)`；找不到返回 None（**绝不下载浏览器**）。

    R279：除 Program Files 的两个标准位置外，再补「按用户安装」的路径
    （`%LOCALAPPDATA%`）与 PATH 里的 msedge/chrome——干净系统上 Edge 一般
    在标准位置，但精简版 / 换过安装位置的机器上只在用户目录，漏了就会表现成
    「按了热键没反应」。
    """
    order = list(_BROWSER_CANDIDATES)
    local = os.environ.get("LOCALAPPDATA") or ""
    if local:
        order.extend((
            ("edge", os.path.join(local, "Microsoft", "Edge", "Application", "msedge.exe")),
            ("chrome", os.path.join(local, "Google", "Chrome", "Application", "chrome.exe")),
        ))
    if prefer in ("edge", "chrome"):
        order.sort(key=lambda item: 0 if item[0] == prefer else 1)
    for name, path in order:
        if os.path.isfile(path):
            return name, path
    for env in ("EDGE_PATH", "CHROME_PATH"):
        path = os.environ.get(env)
        if path and os.path.isfile(path):
            return ("edge" if "edge" in path.lower() else "chrome"), path
    for exe, name in (("msedge.exe", "edge"), ("chrome.exe", "chrome")):
        found = shutil.which(exe) if shutil is not None else None
        if found:
            return name, found
    return None


def dpi_aware() -> None:
    """让本进程拿到**物理像素**（不感知 DPI 的话，屏幕尺寸会被系统缩放，改窗口大小会偏）。"""
    if not IS_WINDOWS:
        return
    import ctypes

    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # PER_MONITOR_AWARE_V2
    except (AttributeError, OSError, ValueError):
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except (AttributeError, OSError, ValueError):
            pass


def work_area():
    """主屏工作区（不含任务栏）→ `(left, top, right, bottom)`；拿不到返回 None。"""
    if not IS_WINDOWS:
        return None
    import ctypes
    from ctypes import wintypes

    class RECT(ctypes.Structure):
        _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                    ("right", wintypes.LONG), ("bottom", wintypes.LONG)]

    rect = RECT()
    if not ctypes.windll.user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(rect), 0):
        return None
    return rect.left, rect.top, rect.right, rect.bottom


def foreground_hwnd() -> int | None:
    """当前前台窗口句柄（用来在起完小窗后把焦点还给游戏）。"""
    if not IS_WINDOWS:
        return None
    import ctypes

    try:
        return int(ctypes.windll.user32.GetForegroundWindow() or 0) or None
    except (AttributeError, OSError, ValueError):
        return None


def restore_focus(hwnd: int | None) -> bool:
    """把焦点还给原来的窗口（起浏览器一定会抢焦点，必须还回去）。"""
    if not hwnd or not IS_WINDOWS:
        return False
    import ctypes

    try:
        return bool(ctypes.windll.user32.SetForegroundWindow(ctypes.c_void_p(hwnd)))
    except (AttributeError, OSError, ValueError):
        return False


def _enum_windows() -> list[tuple[int, int, str]]:
    """枚举所有顶层窗口 → `[(hwnd, pid, title)]`。"""
    if not IS_WINDOWS:
        return []
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    out: list[tuple[int, int, str]] = []
    proto = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def callback(hwnd, _lparam):
        length = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        pid = wintypes.DWORD(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        out.append((int(hwnd), int(pid.value), buf.value))
        return True

    user32.EnumWindows(proto(callback), 0)
    return out


def wait_window(pid: int, timeout: float = 15.0, poll: float = 0.2, title: str | None = None) -> int | None:
    """等小地图窗口出现，返回 hwnd；超时返回 None。

    - `title` 给了：等标题**等于**它（页面加载完才会变成「EFT 小地图」）；
    - `title` 为 None：只要该进程名下有一个可见窗口就返回（窗口刚创建时标题还是 URL）。

    拿不到就老实等超时，不猜、不误改别人的窗口。
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        windows = _enum_windows()
        if title:
            for hwnd, _owner, text in windows:
                if text == title:
                    return hwnd
        else:
            for hwnd, owner, text in windows:
                if owner == pid and text:
                    return hwnd
        time.sleep(poll)
    return None


def window_class(hwnd: int) -> str:
    """窗口类名（`Chrome_WidgetWin_1` 之类）。"""
    import ctypes

    try:
        buf = ctypes.create_unicode_buffer(256)
        ctypes.windll.user32.GetClassNameW(ctypes.c_void_p(hwnd), buf, 256)
        return buf.value
    except (AttributeError, OSError, ValueError):
        return ""


def window_pid(hwnd: int) -> int | None:
    """窗口所属进程号。"""
    import ctypes
    from ctypes import wintypes

    try:
        pid = wintypes.DWORD(0)
        ctypes.windll.user32.GetWindowThreadProcessId(ctypes.c_void_p(hwnd), ctypes.byref(pid))
        return int(pid.value) or None
    except (AttributeError, OSError, ValueError):
        return None


def wait_new_window(before, timeout: float = 15.0, poll: float = 0.05, class_hint="Chrome_WidgetWin"):
    """等「启动之后新出现」的浏览器窗口出现，返回 hwnd。

    **不能靠进程号认领窗口**：Edge 的 `--app` 会另起一个浏览器进程，父进程很快就退出了，
    按 pid 找常常永远找不到（实测踩过）。所以用「启动前的窗口快照」做差集，
    再用类名（`Chrome_WidgetWin_*`）过滤掉那些看不见的辅助窗口。
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for hwnd, _pid, title in _enum_windows():
            if hwnd in before or not title:
                continue
            if class_hint and class_hint not in window_class(hwnd):
                continue
            return hwnd
        time.sleep(poll)
    return None


def _get_style(hwnd: int, index: int) -> int:
    import ctypes
    user32 = ctypes.windll.user32
    getter = getattr(user32, "GetWindowLongPtrW", None) or user32.GetWindowLongW
    getter.restype = ctypes.c_ssize_t
    getter.argtypes = [ctypes.c_void_p, ctypes.c_int]
    return int(getter(ctypes.c_void_p(hwnd), index))


def _set_style(hwnd: int, index: int, value: int) -> None:
    import ctypes
    user32 = ctypes.windll.user32
    setter = getattr(user32, "SetWindowLongPtrW", None) or user32.SetWindowLongW
    setter.restype = ctypes.c_ssize_t
    setter.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
    setter(ctypes.c_void_p(hwnd), index, ctypes.c_ssize_t(value))


def style_overlay(hwnd: int, click_through: bool = True) -> None:
    """把一个普通窗口改造成「无边框 + 置顶 + 不抢焦点（+ 点击穿透）」的小地图。

    分三步，任何一步失败都会原样抛出（不吞异常，免得界面看着没变化却查不出原因）：

    1. 去掉标题栏 / 可调边框 / 系统菜单 / 最小化最大化按钮 —— 浏览器 `--app=` 仍会留一圈框；
    2. 扩展样式加 NOACTIVATE + TOOLWINDOW，需要穿透时再加 LAYERED + TRANSPARENT；
    3. `SetWindowPos(HWND_TOPMOST, SWP_NOMOVE|SWP_NOSIZE|SWP_NOACTIVATE|SWP_SHOWWINDOW)` 钉在最上层。
    """
    import ctypes

    style = _get_style(hwnd, GWL_STYLE)
    style &= ~(WS_CAPTION | WS_THICKFRAME | WS_SYSMENU | WS_MINIMIZEBOX | WS_MAXIMIZEBOX
               | WS_BORDER | WS_DLGFRAME)
    _set_style(hwnd, GWL_STYLE, style)

    ex = _get_style(hwnd, GWL_EXSTYLE)
    ex |= WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW
    if click_through:
        ex |= WS_EX_LAYERED | WS_EX_TRANSPARENT
    else:
        ex &= ~(WS_EX_LAYERED | WS_EX_TRANSPARENT)
    _set_style(hwnd, GWL_EXSTYLE, ex)

    ctypes.windll.user32.SetWindowPos(
        ctypes.c_void_p(hwnd), ctypes.c_void_p(HWND_TOPMOST), 0, 0, 0, 0,
        SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_FRAMECHANGED | SWP_SHOWWINDOW)


def client_size(hwnd: int):
    """客户区尺寸（不含窗口边框与标题栏）。"""
    import ctypes
    from ctypes import wintypes

    try:
        rect = wintypes.RECT()
        ctypes.windll.user32.GetClientRect(ctypes.c_void_p(hwnd), ctypes.byref(rect))
        return rect.right - rect.left, rect.bottom - rect.top
    except (AttributeError, OSError, ValueError):
        return 0, 0


def window_size(hwnd: int):
    """窗口整体尺寸（含边框 / 标题栏）。"""
    import ctypes
    from ctypes import wintypes

    try:
        rect = wintypes.RECT()
        ctypes.windll.user32.GetWindowRect(ctypes.c_void_p(hwnd), ctypes.byref(rect))
        return rect.right - rect.left, rect.bottom - rect.top
    except (AttributeError, OSError, ValueError):
        return 0, 0


def fit_client(hwnd: int, rect, corner: str = "bottom-right", rounds: int = 3):
    """调整窗口，让**客户区**正好是 `rect` 里想要的尺寸，并贴回指定角落。

    Chromium 的 app 窗口会自己画一条标题栏（普通浏览器窗口去不掉，那要 WebView2 才没有），
    这条标题栏吃掉了一截高度。做法是「量一次边框增量 → 目标尺寸 + 增量」，
    一两轮就收敛。

    注意**不能**用 `w + (w - cw)` 那种写法：那是在拿「目标值」当「当前窗口值」，
    会在两个尺寸之间来回振荡（实测第一版就是这样，窗口卡在 237×340）。
    """
    x, y, w, h = rect
    fx, fy, fw, fh = x, y, w, h
    for _ in range(max(1, rounds)):
        cw, ch = client_size(hwnd)
        ww, wh = window_size(hwnd)
        if not cw or not ch or not ww or not wh:
            break
        target_w, target_h = w + (ww - cw), h + (wh - ch)   # 边框 / 标题栏吃掉的部分补回来
        if (target_w, target_h) == (ww, wh):
            break
        fw, fh = target_w, target_h
        fx = x - (fw - w) if corner in ("top-right", "bottom-right") else x
        fy = y - (fh - h) if corner in ("bottom-left", "bottom-right") else y
        move_window(hwnd, (fx, fy, fw, fh))
        time.sleep(0.25)
    return fx, fy, fw, fh


def move_window(hwnd: int, rect) -> None:
    """把窗口放到指定位置与大小（物理像素）并保持置顶。"""
    import ctypes

    x, y, w, h = rect
    ctypes.windll.user32.SetWindowPos(
        ctypes.c_void_p(hwnd), ctypes.c_void_p(HWND_TOPMOST), int(x), int(y), int(w), int(h),
        SWP_NOACTIVATE | SWP_SHOWWINDOW)


def is_alive(hwnd: int) -> bool:
    import ctypes

    try:
        return bool(ctypes.windll.user32.IsWindow(ctypes.c_void_p(hwnd)))
    except (AttributeError, OSError, ValueError):
        return False


def close_overlay(hwnd: int) -> None:
    """关掉小地图窗口，并把它所属的浏览器进程一起收掉。

    浏览器进程是**这个窗口自己的**（我们用独立的 `--user-data-dir` 启动的），
    所以可以放心按 pid 结束；结束不掉也无所谓——用户手动关窗同样会走到这里。
    """
    import ctypes

    try:
        ctypes.windll.user32.PostMessageW(ctypes.c_void_p(hwnd), 0x0010, 0, 0)   # WM_CLOSE
    except (AttributeError, OSError, ValueError):
        pass
    pid = window_pid(hwnd)
    if not pid:
        return
    try:
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],       # noqa: S603
                       capture_output=True, timeout=10, check=False,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        pass


# ---------------------------------------------------------------- 主流程
def launch(url: str, plan, browser=None, profile_dir: str | None = None,
           click_through: bool = True, timeout: float = 15.0, corner: str = "bottom-right"):
    """起一个浏览器应用窗口并把它改造成小地图。

    返回 `(进程, hwnd, 浏览器名)`；失败抛异常（原因写在异常里，命令行工具直接打给用户看）。
    """
    found = browser or find_browser()
    if not found:
        raise RuntimeError("没找到 Edge 或 Chrome（可用环境变量 EDGE_PATH 指定 msedge.exe）")
    name, exe = found
    x, y, w, h = plan
    profile = profile_dir or os.path.join(
        os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "EFTMap", "overlay-profile")
    os.makedirs(profile, exist_ok=True)
    cmd = [
        exe,
        "--app=%s" % url,
        "--window-size=%d,%d" % (w, h),
        "--window-position=%d,%d" % (x, y),
        "--user-data-dir=%s" % profile,      # 独立配置，不污染用户日常浏览器
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-extensions",
        "--autoplay-policy=no-user-gesture-required",
        "--disable-features=Translate,MediaRouter",
    ]
    before = {h for h, _p, _t in _enum_windows()}
    proc = subprocess.Popen(cmd)          # noqa: S603 - 参数全部来自本脚本，无外部输入
    # 关键一：**窗口一出现就去标题栏**，不能等页面加载完再去。
    # Chromium 在创建窗口时就决定要不要自绘那条标题栏（它是浏览器自己画的，不是系统边框，
    # 所以 SetWindowLong 改样式也去不掉）；等页面加载完再改，Chromium 已经按「有标题栏」排好版了。
    #
    # 关键二：**不能靠 pid 认领窗口** —— Edge 的 `--app` 会另起浏览器进程，父进程秒退。
    hwnd = wait_new_window(before, timeout=timeout)
    if hwnd is None:
        proc.terminate()
        raise RuntimeError("浏览器窗口没在超时时间内出现（%.0f 秒）" % timeout)
    style_overlay(hwnd, click_through=click_through)
    # 再确认页面真的加载出来了（标题变成「EFT 小地图」），否则小窗会是白板
    if wait_window(0, timeout=timeout, title=MINI_TITLE) is None:
        raise RuntimeError("小地图页面没加载出来（标题没变成「%s」）" % MINI_TITLE)
    # 页面加载完再定位：Chromium 会在加载过程中自己调窗口大小，这时定尺寸才不会被它改回去
    time.sleep(0.8)
    move_window(hwnd, (x, y, w, h))
    time.sleep(0.4)
    # 客户区补偿：Chromium 自绘的标题栏吃掉了一截高度，补回来，小地图本体就是请求的尺寸
    fit_client(hwnd, (x, y, w, h), corner=corner)
    return proc, hwnd, name


def set_opacity(hwnd: int, opacity: float) -> bool:
    """窗口整体不透明度（0.3~1）—— 实测对 Chromium 窗口有效，可以透过小窗看到游戏。"""
    import ctypes

    try:
        user32 = ctypes.windll.user32
        user32.SetLayeredWindowAttributes.argtypes = [ctypes.c_void_p, ctypes.c_uint,
                                                      ctypes.c_byte, ctypes.c_uint]
        user32.SetLayeredWindowAttributes.restype = ctypes.c_bool
        alpha = max(0, min(255, int(round(float(opacity) * 255))))
        return bool(user32.SetLayeredWindowAttributes(ctypes.c_void_p(hwnd), 0, alpha, LWA_ALPHA))
    except (AttributeError, OSError, ValueError):
        return False


def settings_from(config_dir: str | None = None, overrides=None) -> dict:
    """把配置文件里的 `overlay` 段读出来，命令行显式给的值再覆盖上去。

    **配置是唯一真源**（设置面板改的就是它），所以命令行参数全部默认 `None`，
    只有用户真的写了才覆盖——否则设置面板里的值永远生效不了。
    """
    import config

    base = dict(config.OVERLAY_DEFAULTS)
    try:
        base.update(config.load(config_dir).get("overlay") or {})
    except Exception:       # noqa: BLE001 - 读不到配置就用默认，不要连小窗都起不来
        pass
    for key, value in (overrides or {}).items():
        if value is not None:
            base[key] = value
    import config as _config
    return _config._normalize_overlay(base)


def _watch_loop(hwnd: int, settings: dict, config_dir: str | None, hotkey, work):
    """常驻循环：热键切大小图 + 每 0.5 秒读一次配置并实时应用（位置 / 大小 / 透明度）。

    小窗被关掉、或设置里关掉「小浮窗」就退出。**每轮都重新钉一次置顶**：
    游戏（尤其独占全屏）会把窗口挤下去，这是实测里「小地图不显示在游戏之上」的原因。
    """
    import ctypes
    from ctypes import wintypes

    import config

    mod_vk = hotkey
    registered = False
    user32 = ctypes.windll.user32
    if mod_vk:
        mod, vk = mod_vk
        if user32.RegisterHotKey(None, 1, mod, vk):
            registered = True
        else:
            print("[warn] 热键注册失败（可能已被占用），小窗仍可用，只是不能快捷切换")

    big = False
    applied = None
    last_read = 0.0
    try:
        msg = wintypes.MSG()
        user32.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND,
                                         wintypes.UINT, wintypes.UINT, wintypes.UINT]
        user32.PeekMessageW.restype = wintypes.BOOL
        while is_alive(hwnd):
            while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0):
                if msg.message == WM_HOTKEY and big is not None:
                    big = not big
                    print("[hotkey] 切到%s" % ("大图" if big else "小窗"))
            now = time.monotonic()
            if now - last_read >= 0.5:
                last_read = now
                try:
                    fresh = config.load(config_dir).get("overlay") or {}
                except Exception:       # noqa: BLE001 - 读不到就沿用上一次的设置
                    fresh = {}
                if fresh and not fresh.get("enabled", True):
                    print("设置里关掉了小浮窗，退出。")
                    return
                if fresh:
                    settings.update(fresh)
                    settings = config._normalize_overlay(settings)
                if big:
                    rect = plan_rect(work, FULL_SIZE[0], FULL_SIZE[1],
                                     settings["corner"], settings["offset_x"], settings["offset_y"])
                else:
                    rect = plan_window(work, settings["size"], settings["corner"],
                                       settings["offset_x"], settings["offset_y"])
                signature = (rect, round(float(settings["opacity"]), 3),
                             bool(settings["click_through"]))
                if signature != applied:
                    fit_client(hwnd, rect, corner=settings["corner"])
                    set_opacity(hwnd, settings["opacity"])
                    style_overlay(hwnd, click_through=bool(settings["click_through"]))
                    applied = signature
                else:
                    # 便宜的「再钉一次置顶」：独占全屏的游戏会把普通置顶窗挤下去
                    ctypes.windll.user32.SetWindowPos(
                        ctypes.c_void_p(hwnd), ctypes.c_void_p(HWND_TOPMOST), 0, 0, 0, 0,
                        SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW)
            time.sleep(0.05)
    finally:
        if registered:
            user32.UnregisterHotKey(None, 1)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="把互动地图的 mini 模式放进一个置顶穿透的小窗口（游戏内小地图）")
    parser.add_argument("--config-dir", default=None,
                        help="配置文件目录（默认 %%APPDATA%%\\EFTMap；与服务端同一份配置）")
    parser.add_argument("--base", default=DEFAULT_BASE,
                        help="页面地址（默认 %s；必须是 http://，file:// 下拿不到实时定位）" % DEFAULT_BASE)
    parser.add_argument("--server", default=DEFAULT_SERVER,
                        help="服务地址，用于探活（默认 %s）" % DEFAULT_SERVER)
    # 以下参数**默认 None**：不写就用设置面板里的值（配置文件），写了才覆盖
    parser.add_argument("--size", type=int, default=None, help="边长 px（覆盖设置面板）")
    parser.add_argument("--corner", default=None, choices=CORNERS, help="吸附角落（覆盖设置面板）")
    parser.add_argument("--offset-x", type=int, default=None, help="角落基础上再偏移 X 像素")
    parser.add_argument("--offset-y", type=int, default=None, help="角落基础上再偏移 Y 像素")
    parser.add_argument("--opacity", type=float, default=None, help="窗口不透明度 0.3~1")
    parser.add_argument("--shape", default=None, choices=SHAPES, help="小窗形状")
    parser.add_argument("--labels", dest="labels", action="store_true", default=None,
                        help="显示地图标签")
    parser.add_argument("--no-follow", dest="follow", action="store_false", default=None,
                        help="不跟随玩家")
    parser.add_argument("--bg", default=None,
                        help="小窗背景色（圆形时给四角上色，默认 #0d1117）")
    parser.add_argument("--no-click-through", dest="click_through", action="store_false",
                        default=None, help="不穿透鼠标（调试用）")
    parser.add_argument("--hotkey", default=DEFAULT_HOTKEY,
                        help="小窗/大图切换热键（默认 %s；写 off 表示不注册）" % DEFAULT_HOTKEY)
    parser.add_argument("--browser", default="auto", choices=("auto", "edge", "chrome"),
                        help="用哪个浏览器渲染")
    parser.add_argument("--host", default="auto", choices=HOST_MODES,
                        help="宿主模式：auto=优先 WebView2、失败回退 --app；browser=只用 --app")
    parser.add_argument("--host-exe", default=None,
                        help="WebView2 宿主路径（默认 tools/host/bin/MiniHost.exe）")
    parser.add_argument("--dry-run", action="store_true", help="只打印计划，不启动任何窗口")
    args = parser.parse_args(argv)

    settings = settings_from(args.config_dir, {
        "size": args.size, "corner": args.corner,
        "offset_x": args.offset_x, "offset_y": args.offset_y,
        "opacity": args.opacity, "shape": args.shape,
        "labels": args.labels, "follow": args.follow,
        "click_through": args.click_through,
    })

    try:
        bg = args.bg
        if bg is None and settings["shape"] == "circle":
            # 普通浏览器窗口没有逐像素透明：圆形小窗的四角得自己涂色，否则是一块白
            bg = "#0d1117"
        # 透明度由**宿主**统一控制（SetLayeredWindowAttributes），页面里就别再压一次
        url = build_url(args.base, settings["size"], 1, settings["shape"],
                        labels=1 if settings["labels"] else 0,
                        follow=1 if settings["follow"] else 0,
                        bg=bg, host_alpha=True)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if not IS_WINDOWS:
        print("置顶小窗只在 Windows 上可用（当前平台不支持）", file=sys.stderr)
        return 3

    work = work_area()
    if work is None:
        print("拿不到屏幕工作区，无法定位小窗", file=sys.stderr)
        return 4

    hotkey = parse_hotkey(args.hotkey)
    if args.hotkey and not hotkey and str(args.hotkey).lower() not in ("off", "none", "no"):
        print("看不懂这个热键：%s（用 Ctrl/Alt/Shift/Win + 字母/数字/F1-F12，或写 off）" % args.hotkey,
              file=sys.stderr)
        return 2

    mini_rect = plan_window(work, settings["size"], settings["corner"],
                            settings["offset_x"], settings["offset_y"])
    full_rect = plan_rect(work, FULL_SIZE[0], FULL_SIZE[1], settings["corner"],
                          settings["offset_x"], settings["offset_y"])

    if args.dry_run:
        print("[dry-run] 工作区 %s" % (work,))
        print("[dry-run] %s" % describe(mini_rect, url))
        print("[dry-run] 大图 %s" % (describe(full_rect, url),))
        found = find_browser(args.browser)
        print("[dry-run] 浏览器 = %s" % (("%s（%s）" % found) if found else "（未找到）"))
        print("[dry-run] WebView2 宿主 = %s" % ("有（%s）" % (args.host_exe or HOST_EXE)
                                                  if os.path.isfile(args.host_exe or HOST_EXE)
                                                  else "（未构建，将回退 --app）"))
        print("[dry-run] 热键 = %s" % (args.hotkey,))
        print("[dry-run] 设置 = %s" % (settings,))
        return 0

    if not server_alive(args.server):
        print("本机服务没在跑（%s/api/health 不通）。\n"
              "小地图页面要靠服务拿实时定位，请先启动：\n"
              "    python tools/serve.py --port 8787" % args.server, file=sys.stderr)
        return 5

    dpi_aware()
    previous = foreground_hwnd()

    # 优先 WebView2 宿主：它没有浏览器窗口框架，是真正「无边框」的那条路。
    # Runtime 缺失 / exe 没构建 / 启动失败时回退到原来的 Edge/Chrome --app，保证小地图不会整体不可用。
    if args.host != "browser":
        exe = args.host_exe or HOST_EXE
        if not os.path.isfile(exe):
            print("[host] 找不到 WebView2 宿主（%s），回退 Edge/Chrome --app 模式。\n"
                  "       构建：powershell -ExecutionPolicy Bypass -File tools/host/build.ps1" % exe)
        else:
            map_key = resolve_map_key(args.server)
            try:
                proc, hwnd = launch_host(
                    url, args.config_dir, exe=exe,
                    click_through=bool(settings["click_through"]),
                    map_key=map_key, hotkeys=bool(hotkey))
            except HostUnavailable as exc:
                print("[host] %s；回退 Edge/Chrome --app 模式。" % exc)
            else:
                if hwnd is None:
                    print("设置里关掉了小浮窗，宿主已退出。")
                    return 0
                restore_focus(previous)
                print("小地图已就位（WebView2 宿主，pid %d，%dx%d @ %s，不透明度 %d%%）。"
                      "设置面板里改大小/位置/透明度会实时生效。"
                      % (proc.pid, settings["size"], settings["size"], settings["corner"],
                         int(settings["opacity"] * 100)))
                if map_key:
                    print("[host] 当前战局地图 = %s" % map_key)
                print("[host] 热键：Ctrl+Shift+M 显隐、Ctrl+Shift+F 全图、全图时 Esc 收回。")
                watch_host(proc)
                return 0

    try:
        proc, hwnd, browser_name = launch(
            url, mini_rect, browser=find_browser(args.browser),
            click_through=bool(settings["click_through"]), corner=settings["corner"])
    except Exception as exc:  # noqa: BLE001 - 命令行工具：把原因讲清楚比抛栈更有用
        print("启动失败：%s" % exc, file=sys.stderr)
        return 1

    restore_focus(previous)          # 浏览器一定会抢焦点，必须还给游戏
    set_opacity(hwnd, settings["opacity"])
    print("小地图已就位（%s，pid %d，%dx%d @ %s，不透明度 %d%%）。设置面板里改大小/位置/透明度会实时生效。"
          % (browser_name, proc.pid, settings["size"], settings["size"], settings["corner"],
             int(settings["opacity"] * 100)))
    if hotkey:
        print("热键 %s 可在小窗 / 大图之间切换。" % args.hotkey)
    try:
        _watch_loop(hwnd, dict(settings), args.config_dir, hotkey, work)
    except KeyboardInterrupt:
        pass
    finally:
        close_overlay(hwnd)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
