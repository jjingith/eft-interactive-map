#!/usr/bin/env python3
"""EFT 互动地图 · 本地服务（运行期，仅 Python 标准库）

职责：
- 用 ThreadingHTTPServer 托管项目根目录（index.html / style.css / app.js / data/ / assets/）；
- `GET /api/health` 供 launcher 自检（数据是否就绪、收录多少张图、实时定位/日志监控是否可用）；
- `GET /api/position` 返回最近一次解析到的玩家位置（截图目录不可用时降级为 available=false）；
- `GET /api/config` 返回启动器里设置的运行期配置（开关 + 目录）；
- `POST /api/prefs` 把页面里的界面偏好（图层开关 / 楼层开关 / 自动居中）写回配置文件；
- `GET /api/logstate` 返回日志跟随状态与已累积的战局 / 任务事件；
- `GET /sounds/<文件>` 提供启动器复制到软件目录的自定义提示音；
- `GET /events` 用 SSE 把变化推给页面：位置（无名帧）+ `config` / `state` / `raid` / `quest` / `shot` / `clean` 命名事件；
- 端口占用时给出明确报错，不静默失败；
- 独立运行时自动打开浏览器，`--no-browser` 可关闭。

不联网、不读游戏进程：位置与战局/任务数据来自两类**只读文件**——截图文件名里的坐标
（见 screenshot.py）与游戏日志（见 eftlog.py）。对文件系统的主动操作只有两项，都默认关闭、
需在启动器里显式开启：**自动截图**（`AutoShotter` / keyinput.py，用 SendInput 模拟按下游戏内截图键）
与**自动删除截图**（`ScreenshotPruner`，读过位置后清掉旧截图，只保留最新一张供定位）。
"""

from __future__ import annotations

import argparse
import errno
import json
import mimetypes
import os
import queue
import sys
import threading
import time
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import config
import eftlog
import keyinput
import screenshot

VERSION = "0.1.0"
APP_ID = "eft-interactive-map"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8787
DEFAULT_POLL = 1.0        # 截图目录轮询间隔（秒）
SSE_HEARTBEAT = 15.0      # SSE 心跳间隔（秒），防止连接被中间层掐掉
MAX_PREFS_BODY = 64 * 1024   # /api/prefs 请求体上限：界面偏好只有几 KB，超了直接拒

# 仓库根目录（tools/ 的上一级）
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Windows 的 WSAEADDRINUSE
_WSAEADDRINUSE = 10048

# 标准库在 Windows 上可能把 .svg/.json 猜错，这里显式纠正
EXTRA_TYPES = {
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".json": "application/json; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".ogg": "audio/ogg",
    ".opus": "audio/ogg",
    ".m4a": "audio/mp4",
    ".aac": "audio/aac",
    ".flac": "audio/flac",
}


class PortInUseError(RuntimeError):
    """端口已被占用（区别于其它 OSError，便于 launcher 给出可操作提示）。"""


def _is_addr_in_use(exc: OSError) -> bool:
    return exc.errno in (errno.EADDRINUSE, _WSAEADDRINUSE) or getattr(exc, "winerror", None) == _WSAEADDRINUSE


def data_status(root: str) -> dict[str, Any]:
    """读取 data/maps.json 汇报数据就绪情况（按 mtime 缓存，避免每次请求都解析）。"""
    path = os.path.join(root, "data", "maps.json")
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return {"ready": False, "maps": 0, "error": "缺少 data/maps.json"}

    cached = getattr(data_status, "_cache", None)
    if cached and cached[0] == path and cached[1] == mtime:
        return cached[2]

    try:
        with open(path, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
        maps = payload.get("maps") or []
        status = {"ready": bool(maps), "maps": len(maps), "error": None if maps else "data/maps.json 里没有任何地图"}
    except (OSError, ValueError) as exc:
        status = {"ready": False, "maps": 0, "error": "data/maps.json 无法解析：%s" % exc}

    data_status._cache = (path, mtime, status)  # type: ignore[attr-defined]
    return status


def default_screenshots_dir() -> str:
    """EFT 截图目录的默认位置：`<我的文档>\\Escape from Tarkov\\Screenshots`。"""
    try:
        import ctypes

        buf = ctypes.create_unicode_buffer(260)
        # CSIDL_PERSONAL = 5（我的文档）
        if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf) == 0 and buf.value:
            docs = buf.value
        else:
            raise OSError("SHGetFolderPathW 未返回路径")
    except (AttributeError, OSError, ValueError):
        docs = os.path.join(os.path.expanduser("~"), "Documents")
    return os.path.join(docs, "Escape from Tarkov", "Screenshots")


# 游戏目录常见命名（用户实测目录为 `E:\EFT`，这里把裸名字与常见安装路径都覆盖）
GAME_DIR_NAMES = ("EFT", "Escape from Tarkov", "EscapeFromTarkov")
_GAME_EXES = ("EscapeFromTarkov.exe", "EscapeFromTarkov_BE.exe")


def _looks_like_game_dir(path: str) -> bool:
    """判定一个目录是不是 EFT 安装根：有 `Logs` 子目录，或装着游戏主程序。"""
    if not os.path.isdir(path):
        return False
    if os.path.isdir(os.path.join(path, "Logs")):
        return True
    return any(os.path.isfile(os.path.join(path, exe)) for exe in _GAME_EXES)


def default_game_dir() -> str | None:
    """自动定位 EFT 游戏目录（找不到返回 None，由用户在启动器里手填）。

    依次尝试：环境变量 `EFT_GAME_DIR` → 常见盘符下的裸目录名 → 常见安装路径。
    只做**浅层**存在性判断，不递归遍历整盘，避免启动卡顿。
    """
    env = os.environ.get("EFT_GAME_DIR")
    if env and _looks_like_game_dir(env):
        return env

    candidates: list[str] = []
    for drive in "CDEFGHIJK":
        root = "%s:\\" % drive
        if not os.path.isdir(root):
            continue
        for name in GAME_DIR_NAMES:
            candidates.append(os.path.join(root, name))
        candidates.extend([
            os.path.join(root, "Battlestate Games", "EFT"),
            os.path.join(root, "Battlestate Games", "Escape from Tarkov"),
            os.path.join(root, "Games", "EFT"),
            os.path.join(root, "Program Files", "Battlestate Games", "EFT"),
            os.path.join(root, "Program Files (x86)", "Steam", "steamapps", "common", "Escape from Tarkov"),
        ])
    for path in candidates:
        if _looks_like_game_dir(path):
            return path
    return None


class Broadcaster:
    """SSE 订阅者注册表：把新位置与命名事件推给所有在线页面。

    队列里放的要么是位置帧（裸 dict），要么是 `(事件名, 负载)` 元组；
    每个订阅者一个 Queue，避免在请求线程里做网络写；广播失败/客户端断开只影响自己。
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._subs: set[queue.Queue] = set()

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=64)
        with self._lock:
            self._subs.add(q)
        return q

    def unsubscribe(self, q: queue.Queue):
        with self._lock:
            self._subs.discard(q)

    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subs)

    def publish(self, payload: dict):
        self._put(payload)

    def publish_event(self, name: str, payload: dict):
        """推一个 SSE 命名事件（`event: <name>`），前端用 addEventListener 各自订阅。"""
        self._put((name, payload))

    def _put(self, item):
        with self._lock:
            subs = list(self._subs)
        for q in subs:
            try:
                q.put_nowait(item)
            except queue.Full:      # 页面跟不上就先丢掉这一帧，不阻塞监听线程
                pass


class PositionTracker:
    """后台线程轮询截图目录；只有拿到的位置**真的变了**才广播。

    降级行为：目录不存在 / 读不了 / 一张都解析不出来 → available=false 并给出原因，
    地图其余功能不受影响（不抛异常、不停服务）。
    """

    def __init__(self, directory: str | None, poll_interval: float = DEFAULT_POLL,
                 broadcaster: Broadcaster | None = None):
        self.directory = directory
        self.poll_interval = poll_interval
        self.broadcaster = broadcaster or Broadcaster()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._latest: dict[str, Any] | None = None
        self._reason: str | None = None

    # ------------------------------------------------------------ 状态
    def enabled(self) -> bool:
        return bool(self.directory)

    def snapshot(self) -> dict[str, Any]:
        """当前定位状态（`/api/position` 用；也是 SSE 每帧的内容）。"""
        with self._lock:
            latest, reason = self._latest, self._reason
        if not self.enabled():
            return {"available": False, "reason": "未配置截图目录（启动器加 --screenshots 可开启实时定位）",
                    "position": None}
        if latest is None:
            return {"available": False, "reason": reason or "截图目录里还没有可解析的截图", "position": None}
        pos = {k: latest[k] for k in ("x", "y", "z", "yaw")}
        pos["name"] = latest["name"]
        pos["mtime"] = latest["mtime"]
        return {"available": True, "reason": None, "position": pos, "directory": self.directory}

    # ------------------------------------------------------------ 轮询
    def poll_once(self) -> bool:
        """扫一次目录；位置有变化返回 True（并广播）。"""
        if not self.enabled():
            return False
        if not os.path.isdir(self.directory):
            with self._lock:
                changed = self._latest is not None
                self._latest = None
                self._reason = "截图目录不存在：%s" % self.directory
            if changed:
                self.broadcaster.publish(self.snapshot())
            return changed

        found = screenshot.latest_position(self.directory)
        with self._lock:
            if found is None:
                self._reason = "截图目录里还没有可解析的截图"
                changed = self._latest is not None
                self._latest = None
            else:
                self._reason = None
                prev = self._latest
                changed = prev is None or prev["name"] != found["name"] or prev["mtime"] != found["mtime"]
                self._latest = found
        if changed:
            self.broadcaster.publish(self.snapshot())
        return changed

    def start(self):
        if not self.enabled() or self._thread is not None:
            return
        self.poll_once()                       # 先给一帧，页面首屏就有位置
        self._thread = threading.Thread(target=self._loop, daemon=True, name="eft-position-watch")
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3)
            self._thread = None

    def _loop(self):
        while not self._stop.wait(self.poll_interval):
            try:
                self.poll_once()
            except Exception:       # 任何意外都不该让监听线程死掉
                continue


class ConfigWatcher:
    """盯着 `eftmap.config.json` 的 mtime：文件一变就把新配置推给页面。

    这样启动器里改开关（自动缩放 / 自动居中 / 声音提示）后，已经开着的页面会立刻生效，
    不需要重启服务或刷新浏览器。
    """

    def __init__(self, app_dir: str, poll_interval: float = DEFAULT_POLL,
                 broadcaster: Broadcaster | None = None):
        self.app_dir = app_dir
        self.poll_interval = poll_interval
        self.broadcaster = broadcaster or Broadcaster()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._mtime: float | None = None
        self._initialized = False

    def snapshot(self) -> dict[str, Any]:
        return config_payload(self.app_dir)

    def poll_once(self) -> bool:
        """配置 mtime 有变化就广播一次，返回是否变化。首次只记基线，不广播。"""
        path = config.config_path(self.app_dir)
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            mtime = None
        if not self._initialized:
            self._initialized = True
            self._mtime = mtime
            return False
        if mtime == self._mtime:
            return False
        self._mtime = mtime
        self.broadcaster.publish_event("config", self.snapshot())
        return True

    def start(self):
        if self._thread is not None:
            return
        self.poll_once()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="eft-config-watch")
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3)
            self._thread = None

    def _loop(self):
        while not self._stop.wait(self.poll_interval):
            try:
                self.poll_once()
            except Exception:
                continue


# 自动截图只对游戏主程序在前台时发送（模拟按键只能打到前台窗口）
GAME_PROCESS = "escapefromtarkov.exe"


class AutoShotter:
    """自动截图：在战局中按固定间隔向游戏窗口发送截图键（模拟按键）。

    三个门条件（**都**满足才发键）：

    1. 启动器里开了「自动截图」（读 `eftmap.config.json`）；
    2. 日志显示当前在战局中（`phase == "start"`，来自 `LogFollower`）；
    3. 前台窗口的进程是 `EscapeFromTarkov.exe`（模拟按键只能打到前台窗口）。

    截图键优先用配置里填/同步到的 `auto_screenshot.key`，为空时回落到日志同步到的键
    （`LogFollower.screenshot_key()`，即游戏内 `MakeScreenshot` 绑定）。

    `sender` / `foreground` 可注入，便于单测时不必真的发按键。
    """

    TICK = 0.1     # 内部轮询步长（秒）：比最短间隔 200ms 更细，保证不丢拍

    def __init__(self, app_dir: str, follower: "eftlog.LogFollower | None" = None,
                 broadcaster: Broadcaster | None = None, sender=None, foreground=None,
                 tick: float = TICK):
        self.app_dir = app_dir
        self.follower = follower
        self.broadcaster = broadcaster or Broadcaster()
        self.sender = sender or keyinput.send_key
        self.foreground = foreground or keyinput.foreground_process_name
        self.tick = tick
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._sent = 0
        self._last_at = 0.0
        self._reason = "自动截图未开启"

    # ------------------------------------------------------------ 状态
    def settings(self) -> tuple[bool, int, str | None]:
        """读配置 → (是否开启, 间隔毫秒, 截图键)。键为空时回落到日志同步到的键。"""
        shot = (config.load(self.app_dir) or {}).get("auto_screenshot") or {}
        enabled = bool(shot.get("enabled"))
        interval = config.clamp_interval(shot.get("interval_ms"))
        key = shot.get("key") or (self.follower.screenshot_key() if self.follower else None)
        return enabled, interval, key

    def phase(self) -> str | None:
        if self.follower is None:
            return None
        return (self.follower.snapshot().get("raid") or {}).get("phase")

    def snapshot(self) -> dict[str, Any]:
        enabled, interval, key = self.settings()
        with self._lock:
            sent, last, reason = self._sent, self._last_at, self._reason
        return {
            "enabled": enabled,
            "intervalMs": interval,
            "key": key,
            "sent": sent,
            "lastSentAt": last or None,
            "available": bool(enabled and key),
            "reason": reason,
        }

    def _set_reason(self, text: str | None):
        with self._lock:
            self._reason = text

    # ------------------------------------------------------------ 轮询
    def poll_once(self, now: float | None = None) -> bool:
        """跑一轮门检查；真的发了按键返回 True（并发 `shot` 事件）。"""
        now = time.monotonic() if now is None else now
        enabled, interval_ms, key = self.settings()
        if not enabled:
            self._set_reason("自动截图未开启")
            return False
        if not key:
            self._set_reason("未取得截图按键：请在启动器里从日志同步或手动填写")
            return False
        phase = self.phase()
        if phase != "start":
            self._set_reason("不在战局中（当前阶段：%s）" % (phase or "无日志"))
            return False
        process = self.foreground()
        if not process:
            self._set_reason("无法确认游戏窗口是否在前台")
            return False
        if os.path.basename(str(process)).lower() != GAME_PROCESS:
            self._set_reason("游戏窗口不在前台（当前前台：%s）" % os.path.basename(str(process)))
            return False
        with self._lock:
            last = self._last_at
        if now - last < interval_ms / 1000.0:
            return False
        ok, error = self._send(key)
        with self._lock:
            self._last_at = now
            if ok:
                self._sent += 1
                self._reason = None
            else:
                self._reason = error or "发送按键失败"
        if ok:
            self.broadcaster.publish_event("shot", self.snapshot())
        return ok

    def _send(self, key: str) -> tuple[bool, str]:
        try:
            result = self.sender(key)
        except Exception as exc:       # 注入实现抛异常也不能让线程死掉
            return False, "发送按键出错：%s" % exc
        if isinstance(result, tuple):
            return bool(result[0]), (result[1] if len(result) > 1 else "")
        return bool(result), ""

    # ------------------------------------------------------------ 线程
    def start(self):
        if self._thread is not None:
            return
        self.poll_once()               # 先跑一轮，页面首屏就有状态
        self._thread = threading.Thread(target=self._loop, daemon=True, name="eft-auto-shot")
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3)
            self._thread = None

    def _loop(self):
        while not self._stop.wait(self.tick):
            try:
                self.poll_once()
            except Exception:
                continue


class ScreenshotPruner:
    """自动删除截图：**位置读到手之后**，把多余的旧截图删掉，给截图目录止血。

    与「自动截图」配套使用效果最好（一个负责拍、一个负责清），但**彼此独立**：
    单独打开也能用（手动拍的截图，读过位置后同样会被清掉）。

    安全性三条：

    1. **只留最新 1 张**（`KEEP_NEWEST`）——实时定位就靠它，删了会没位置；
    2. **只删开关打开之后产生的**（配置里的 `auto_delete.since` 作时间闸），
       历史截图、以及开关关闭期间攒下的截图一律不动；
    3. **只删能解析出位置的截图**（见 `screenshot.select_deletable`），
       读不到位置的杂图不碰；删不掉（被占用等）就跳过，不抛异常。

    `since` 为空时会**先「布防」再删**：把 `since` 写成当前时刻并落盘，这一轮不删任何东西，
    避免手改配置或首次开启时一把清空整个目录。`prune` 可注入，便于单测不真删文件。
    """

    KEEP_NEWEST = 1

    def __init__(self, directory: str | None, app_dir: str,
                 broadcaster: Broadcaster | None = None, poll_interval: float = DEFAULT_POLL,
                 prune=None, clock=time.time):
        self.directory = directory
        self.app_dir = app_dir
        self.broadcaster = broadcaster or Broadcaster()
        self.poll_interval = poll_interval
        self.prune = prune or screenshot.prune
        self.clock = clock
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._deleted = 0
        self._last_at = 0.0
        self._reason = "自动删除未开启"

    # ------------------------------------------------------------ 状态
    def settings(self) -> tuple[bool, float | None]:
        """读配置 → (是否开启, 布防时刻)。"""
        delete = (config.load(self.app_dir) or {}).get("auto_delete") or {}
        return bool(delete.get("enabled")), delete.get("since")

    def snapshot(self) -> dict[str, Any]:
        enabled, since = self.settings()
        with self._lock:
            deleted, last, reason = self._deleted, self._last_at, self._reason
        return {
            "enabled": enabled,
            "since": since,
            "keepNewest": self.KEEP_NEWEST,
            "deleted": deleted,
            "lastDeletedAt": last or None,
            "available": bool(enabled and since and self.directory),
            "reason": reason,
        }

    def _set_reason(self, text: str):
        with self._lock:
            self._reason = text

    def _arm(self, now: float):
        """布防：把开启时刻落盘，作为「只删之后产生的截图」的时间闸。"""
        cfg = config.load(self.app_dir)
        cfg["auto_delete"]["enabled"] = True
        cfg["auto_delete"]["since"] = now
        config.save(cfg, self.app_dir)
        self._set_reason("已就绪：从现在起产生的截图才会被清理")

    # ------------------------------------------------------------ 轮询
    def poll_once(self, now: float | None = None) -> list[str]:
        """跑一轮；返回本轮删掉的文件名（空列表 = 这轮没删）。"""
        enabled, since = self.settings()
        if not enabled:
            self._set_reason("自动删除未开启")
            return []
        if not self.directory:
            self._set_reason("未配置截图目录（自动删除需要知道从哪儿清）")
            return []
        if since is None:
            self._arm(self.clock() if now is None else now)
            return []
        if not os.path.isdir(self.directory):
            self._set_reason("截图目录不存在：%s" % self.directory)
            return []

        deleted = self.prune(self.directory, since, self.KEEP_NEWEST)
        with self._lock:
            if deleted:
                self._deleted += len(deleted)
                self._last_at = time.time() if now is None else now
                self._reason = "已清理 %d 张（保留最新 %d 张供定位）" % (len(deleted), self.KEEP_NEWEST)
            else:
                self._reason = "暂无可清理的截图"
        if deleted:
            self.broadcaster.publish_event("clean", self.snapshot())
        return deleted

    # ------------------------------------------------------------ 线程
    def start(self):
        if self._thread is not None:
            return
        self.poll_once()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="eft-shot-prune")
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3)
            self._thread = None

    def _loop(self):
        while not self._stop.wait(self.poll_interval):
            try:
                self.poll_once()
            except Exception:
                continue


def config_payload(app_dir: str) -> dict[str, Any]:
    """`/api/config` 与 SSE `config` 事件共用的一份负载。"""
    cfg = config.load(app_dir)
    return {
        "config": cfg,
        "resolved": {
            "appDir": app_dir,
            "soundsDir": config.sounds_dir(app_dir),
        },
    }


def build_handler(root: str, tracker: PositionTracker, follower: eftlog.LogFollower | None = None,
                  app_dir: str | None = None, shotter: AutoShotter | None = None,
                  pruner: ScreenshotPruner | None = None):
    """构造静态文件 Handler，并把 /api/ 前缀留给 JSON 接口、/sounds/ 留给自定义提示音。"""
    app_dir = app_dir or config.app_dir()

    class Handler(SimpleHTTPRequestHandler):
        server_version = "EFTMap/%s" % VERSION
        protocol_version = "HTTP/1.1"
        extensions_map = dict(SimpleHTTPRequestHandler.extensions_map, **EXTRA_TYPES)

        def __init__(self, *args, **kwargs):
            self._cache_header_set = False     # 见 end_headers()
            super().__init__(*args, directory=root, **kwargs)

        # 本地单机服务，逐请求一行日志只是噪音
        def log_message(self, fmt, *args):  # noqa: A003 - 覆盖标准库签名
            pass

        def end_headers(self):  # noqa: N802 - 覆盖标准库签名
            """给静态文件也加上禁缓存头。

            标准库的 SimpleHTTPRequestHandler 不发 Cache-Control，浏览器于是按启发式
            规则缓存 app.js / data/maps.json，换了新版本仍旧拿旧文件——表现为「打包了
            新版却还是昨天的界面」。本地服务一律不缓存，改完刷新即生效。
            """
            if not self._cache_header_set:
                self.send_header("Cache-Control", "no-store, must-revalidate")
                self.send_header("Pragma", "no-cache")
                self._cache_header_set = True
            super().end_headers()

        def _send_cache_header(self):
            """接口自行声明过缓存策略时打个招呼，免得 end_headers() 再叠一层。"""
            self._cache_header_set = True

        def do_GET(self):  # noqa: N802 - 覆盖标准库签名
            path = self.path.split("?", 1)[0].split("#", 1)[0]
            if path == "/api/health":
                return self._send_json(200, health_payload(root, tracker, follower, shotter, pruner))
            if path == "/api/position":
                return self._send_json(200, tracker.snapshot())
            if path == "/api/config":
                return self._send_json(200, config_payload(app_dir))
            if path == "/api/logstate":
                snap = follower.snapshot() if follower is not None else {"available": False}
                if shotter is not None:
                    snap = dict(snap, shot=shotter.snapshot())
                if pruner is not None:
                    snap = dict(snap, clean=pruner.snapshot())
                return self._send_json(200, snap)
            if path == "/events":
                return self._serve_events()
            if path == "/sounds":
                return self._send_json(200, {"files": list_sounds(app_dir)})
            if path.startswith("/sounds/"):
                return self._serve_sound(path[len("/sounds/"):])
            if path.startswith("/api/"):
                return self._send_json(404, {"ok": False, "error": "未知接口：%s" % path})
            return super().do_GET()

        def do_POST(self):  # noqa: N802 - 覆盖标准库签名
            """页面把界面偏好（图层开关 / 楼层开关 / 自动居中）写回 `eftmap.config.json`。

            这是唯一的 POST 接口，本地单机服务不做鉴权；请求体限制在 MAX_PREFS_BODY 内。
            写盘后顺手广播一次 `config`，让其它已打开的页面立刻跟上。
            """
            path = self.path.split("?", 1)[0].split("#", 1)[0]
            if path != "/api/prefs":
                return self._send_json(404, {"ok": False, "error": "未知接口：%s" % path})
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except (TypeError, ValueError):
                length = 0
            if not 0 < length <= MAX_PREFS_BODY:
                return self._send_json(400, {"ok": False, "error": "请求体缺失或过大"})
            try:
                prefs = json.loads(self.rfile.read(length).decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                return self._send_json(400, {"ok": False, "error": "请求体不是合法 JSON"})
            try:
                cfg = config.save(config.merge_ui(config.load(app_dir), prefs), app_dir)
            except OSError as exc:
                return self._send_json(500, {"ok": False, "error": "保存配置失败：%s" % exc})
            tracker.broadcaster.publish_event("config", config_payload(app_dir))
            return self._send_json(200, {"ok": True, "config": cfg})

        def _send_json(self, code: int, payload: dict):
            body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
            self._send_cache_header()
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _serve_sound(self, rel: str):
            """提供软件目录 `sounds/` 下的自定义提示音；拒绝越权路径与目录请求。"""
            base = os.path.realpath(config.sounds_dir(app_dir))
            target = os.path.realpath(os.path.join(base, rel))
            if not target.startswith(base + os.sep) or not os.path.isfile(target):
                return self._send_json(404, {"ok": False, "error": "音频文件不存在：%s" % rel})
            ctype = EXTRA_TYPES.get(os.path.splitext(target)[1].lower()) \
                or mimetypes.guess_type(target)[0] or "application/octet-stream"
            with open(target, "rb") as fh:
                body = fh.read()
            self._send_cache_header()
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _serve_events(self):
            """SSE：连上先推当前状态，之后有变化就推，另加心跳注释保持连接。

            帧有两种：位置是**无名帧**（前端 onmessage 收），其余是命名事件
            `config` / `state` / `raid` / `quest`（前端 addEventListener 各自订阅）。
            无 Content-Length，因此按 HTTP/1.1 规范用 `Connection: close` 把「流到连接关闭为止」
            表达清楚（不能用 chunked，标准库的分块编码会把每帧再包一层长度前缀）。
            """
            self._send_cache_header()
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()

            q = tracker.broadcaster.subscribe()
            try:
                self._write_frame(tracker.snapshot())
                self._write_event("config", config_payload(app_dir))
                if follower is not None:
                    self._write_event("state", follower.snapshot())
                if shotter is not None:
                    self._write_event("shot", shotter.snapshot())
                if pruner is not None:
                    self._write_event("clean", pruner.snapshot())
                last_beat = time.monotonic()
                while True:
                    try:
                        item = q.get(timeout=1.0)
                    except queue.Empty:
                        item = None
                    if isinstance(item, tuple):
                        self._write_event(item[0], item[1])
                    elif item is not None:
                        self._write_frame(item)
                    if time.monotonic() - last_beat >= SSE_HEARTBEAT:
                        last_beat = time.monotonic()
                        self.wfile.write(b": ping\n\n")
                        self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                pass          # 页面关了就正常收摊
            finally:
                tracker.broadcaster.unsubscribe(q)

        def _write_frame(self, payload: dict):
            data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            self.wfile.write(b"data: " + data + b"\n\n")
            self.wfile.flush()

        def _write_event(self, name: str, payload: dict):
            data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            self.wfile.write(b"event: " + name.encode("ascii") + b"\ndata: " + data + b"\n\n")
            self.wfile.flush()

    return Handler


def list_sounds(app_dir: str) -> list[str]:
    """软件目录 `sounds/` 里已有的音频文件名（启动器与页面共用）。"""
    directory = config.sounds_dir(app_dir)
    try:
        names = os.listdir(directory)
    except OSError:
        return []
    return sorted(n for n in names if n.lower().endswith(config.AUDIO_EXTS))


def health_payload(root: str, tracker: PositionTracker | None = None,
                   follower: eftlog.LogFollower | None = None,
                   shotter: AutoShotter | None = None,
                   pruner: ScreenshotPruner | None = None) -> dict[str, Any]:
    status = data_status(root)
    payload = {
        "ok": bool(status["ready"]),
        "app": APP_ID,
        "version": VERSION,
        "root": root,
        "data": status,
        "position": bool(tracker and tracker.enabled()),
        "logs": bool(follower and follower.enabled()),
    }
    if tracker is not None:
        snap = tracker.snapshot()
        payload["positionAvailable"] = snap["available"]
        payload["screenshots"] = tracker.directory
    if follower is not None:
        payload["gameDir"] = follower.game_dir
        payload["logDir"] = follower.logs_dir
        payload["logSession"] = follower.snapshot()["session"]
    if shotter is not None:
        payload["shot"] = shotter.snapshot()
    if pruner is not None:
        payload["clean"] = pruner.snapshot()
    return payload


class _Server(ThreadingHTTPServer):
    """禁用地址复用：Windows 下 SO_REUSEADDR 会让端口占用检测失效。"""

    daemon_threads = True
    allow_reuse_address = False

    def server_close(self):
        # 关闭服务时一并停掉截图 / 日志 / 配置 / 自动截图 / 自动删除监听线程，避免残留轮询
        for name in ("tracker", "follower", "watcher", "shotter", "pruner"):
            watcher_obj = getattr(self, name, None)
            if watcher_obj is not None:
                watcher_obj.stop()
        super().server_close()


def create_server(port: int = DEFAULT_PORT, host: str = DEFAULT_HOST, root: str | None = None,
                  screenshots: str | None = None, poll_interval: float = DEFAULT_POLL,
                  config_dir: str | None = None, game_dir: str | None = None) -> ThreadingHTTPServer:
    """创建（已 listen 的）HTTP 服务对象。

    port=0 表示由系统分配空闲端口，便于测试。
    `screenshots=None` 表示**不开启**实时定位，`game_dir=None` 表示**不开启**日志监控
    （测试与无对应目录的场景走这两条路），传入目录才启动监听线程。
    `config_dir` 是配置与 `sounds/` 的落盘位置，默认软件目录。
    """
    root = os.path.abspath(root or ROOT)
    if not os.path.isfile(os.path.join(root, "index.html")):
        raise FileNotFoundError("根目录里找不到 index.html：%s\n请用 --root 指向仓库根目录。" % root)

    app_dir = os.path.abspath(config_dir) if config_dir else os.path.abspath(config.default_storage_dir())
    if not config_dir:
        config.migrate_legacy(app_dir, config.app_dir())   # 旧软件目录里的配置首次搬到用户目录
    broadcaster = Broadcaster()
    tracker = PositionTracker(screenshots, poll_interval, broadcaster)
    follower = eftlog.LogFollower(game_dir, poll_interval, broadcaster)
    watcher = ConfigWatcher(app_dir, poll_interval, broadcaster)
    shotter = AutoShotter(app_dir, follower, broadcaster)
    pruner = ScreenshotPruner(screenshots, app_dir, broadcaster, poll_interval)
    handler = build_handler(root, tracker, follower, app_dir, shotter, pruner)
    try:
        httpd = _Server((host, port), handler)
    except OSError as exc:
        if _is_addr_in_use(exc):
            raise PortInUseError(
                "端口 %d 已被占用。请关闭占用该端口的程序，或用 --port 换一个端口（如 --port 8788）。" % port
            ) from exc
        raise
    httpd.tracker = tracker       # type: ignore[attr-defined]
    httpd.follower = follower     # type: ignore[attr-defined]
    httpd.watcher = watcher       # type: ignore[attr-defined]
    httpd.shotter = shotter       # type: ignore[attr-defined]
    httpd.pruner = pruner         # type: ignore[attr-defined]
    httpd.app_dir = app_dir       # type: ignore[attr-defined]
    tracker.start()
    follower.start()
    watcher.start()
    shotter.start()
    pruner.start()
    return httpd


def url_for(host: str, port: int) -> str:
    shown = "127.0.0.1" if host in ("", "0.0.0.0") else host
    return "http://%s:%d/" % (shown, port)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="EFT 互动地图本地服务（静态站点 + 健康检查 + 实时定位 + 日志监控）")
    parser.add_argument("--host", default=DEFAULT_HOST, help="监听地址，默认 %s（仅本机可访问）" % DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="监听端口，默认 %d；0 表示自动分配" % DEFAULT_PORT)
    parser.add_argument("--root", default=None, help="站点根目录，默认仓库根目录")
    parser.add_argument("--screenshots", default=None,
                        help="EFT 截图目录；不给则用默认位置 %s" % default_screenshots_dir())
    parser.add_argument("--no-position", action="store_true", help="关闭实时定位（不监听截图目录）")
    parser.add_argument("--game-dir", default=None,
                        help="EFT 游戏目录（含 Logs）；不给则用配置或自动定位")
    parser.add_argument("--config-dir", default=None, help="配置文件与 sounds/ 的落盘目录，默认软件目录")
    parser.add_argument("--no-logs", action="store_true", help="关闭游戏日志监控（不自动切图/统计任务）")
    parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    return parser.parse_args(argv)


def resolve_screenshots(args) -> str | None:
    """CLI 参数 → 实际要监听的目录：--no-position 关掉，否则用给定值或默认位置。"""
    if args.no_position:
        return None
    if args.screenshots:
        return args.screenshots
    default = default_screenshots_dir()
    return default if os.path.isdir(default) else None


def resolve_settings(args) -> dict[str, Any]:
    """CLI 参数 + 配置文件 → 运行期实际使用的目录与配置。

    优先级：命令行显式给出 > 配置文件 > 自动定位（仅当配置文件里也没写时）。
    自动定位的结果**不会**回写配置文件——只有用户在启动器里确认过才落盘。
    """
    app_dir = os.path.abspath(args.config_dir) if args.config_dir else os.path.abspath(config.default_storage_dir())
    if not args.config_dir:
        config.migrate_legacy(app_dir, config.app_dir())
    cfg = config.load(app_dir)

    game_dir = args.game_dir or cfg.get("game_dir")
    if args.no_logs:
        game_dir = None
    elif not game_dir:
        game_dir = default_game_dir()
    if game_dir and not os.path.isdir(game_dir):
        game_dir = None

    screenshots = args.screenshots or cfg.get("screenshots_dir")
    if args.no_position:
        screenshots = None
    elif not screenshots:
        screenshots = default_screenshots_dir()
    if screenshots and not os.path.isdir(screenshots):
        screenshots = None

    return {"app_dir": app_dir, "config": cfg, "game_dir": game_dir, "screenshots": screenshots}


def main(argv=None) -> int:
    args = parse_args(argv)
    settings = resolve_settings(args)
    try:
        httpd = create_server(args.port, args.host, args.root, screenshots=settings["screenshots"],
                              config_dir=settings["app_dir"], game_dir=settings["game_dir"])
    except PortInUseError as exc:
        print("[错误] %s" % exc, file=sys.stderr)
        return 2
    except FileNotFoundError as exc:
        print("[错误] %s" % exc, file=sys.stderr)
        return 3

    url = url_for(args.host, httpd.server_address[1])
    print("EFT 互动地图已启动：%s" % url)
    if settings["screenshots"]:
        print("实时定位：监听截图目录 %s" % settings["screenshots"])
    else:
        print("实时定位：未开启（截图目录不可用或已用 --no-position 关闭）")
    if settings["game_dir"]:
        print("日志监控：跟随游戏目录 %s\\Logs（自动切图 + 任务事件）" % settings["game_dir"])
    else:
        print("日志监控：未开启（游戏目录不可用或已用 --no-logs 关闭）")
    print("自动截图：%s（在启动器里开关与设置间隔 / 按键）" % ("已开启" if httpd.shotter.snapshot()["enabled"] else "未开启"))
    print("自动删除截图：%s（在启动器里开关；只删开启后产生、且已读过位置的旧截图）"
          % ("已开启" if httpd.pruner.snapshot()["enabled"] else "未开启"))
    print("配置文件：%s" % config.config_path(settings["app_dir"]))
    print("按 Ctrl+C 停止服务。")
    if not args.no_browser:
        webbrowser.open(url)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
