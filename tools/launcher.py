#!/usr/bin/env python3
"""EFT 互动地图 · 启动器（运行期入口 → EFTMap.exe）

双击 exe 后显示一个 Windows XP（Luna）风的小窗口：

    ┌ 游戏目录 / 截图目录   ← 自动定位 + 手填 + 浏览
    ├ 地图显示开关         ← 定位自动缩放 / 点位自动居中
    ├ 声音提示开关 + 3 个子开关（战局开始 / 开始加载战局 / 开始匹配）+「选取音频…」
    ├ 自动截图开关 + 间隔(ms) / 按键 +「从日志同步」（默认关闭，见下方反作弊提醒）
    └ 状态                ← 四步进度（检查数据 → 启动本地服务 → 载入资源 → 打开浏览器）
    [启动 WebUI]  ☑ 自动启动 WebUI   [保存配置] [退出]

**服务不再随窗口自动启动**，而是由「启动 WebUI」按钮（或「自动启动 WebUI」勾选）触发。
**配置落在用户级目录**（`%APPDATA%\\EFTMap\\eftmap.config.json`，见 config.default_storage_dir）：
打包会整个重建 dist，配置留在 exe 目录就会被清掉；表单失焦 / 勾选 / 点「保存配置」都会落盘。

设计上刻意把「编排」与「界面」分离：
- `Startup` 是纯逻辑编排，依赖（起服务/自检/开浏览器）全部可注入 → 可单测，不需要弹窗；
- `build_config` / `resolve_dirs` 是纯函数，把「表单值 ↔ 配置文件 ↔ 自动定位」的换算摊开，
  同样可单测；
- `LaunchWindow` 只用 tkinter 做呈现，不搞业务判断。

与 serve.py 的关系：launcher 是入口与界面壳，serve.py 是可被调用的服务模块
（同时也保留独立 CLI 便于调试）。全程不联网、不读游戏进程，只读日志与截图文件名。
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from typing import Any, Callable

import config
import eftlog
import serve

VERSION = serve.VERSION
DEFAULT_PORT = serve.DEFAULT_PORT
DEFAULT_HOST = serve.DEFAULT_HOST

# 启动四步的 id 与显示名（UI 与编排共用同一份定义，避免两边写散）
STEP_CHECK = "check-data"
STEP_SERVER = "start-server"
STEP_SELFCHECK = "load-assets"
STEP_BROWSER = "open-browser"
STEPS: list[tuple[str, str]] = [
    (STEP_CHECK, "检查数据"),
    (STEP_SERVER, "启动本地服务"),
    (STEP_SELFCHECK, "载入资源"),
    (STEP_BROWSER, "打开浏览器"),
]

# 每步状态 → UI 图标（只用 Tahoma 稳能渲染的字符，避免出豆腐块）
STATE_ICON = {"pending": "·", "running": "»", "done": "√", "failed": "×"}
STATE_COLOR = {"pending": "#808080", "running": "#0A4FA8", "done": "#0A8A0A", "failed": "#C00000"}

AUDIO_FILETYPES = [("音频文件", "*.mp3 *.wav *.ogg *.m4a *.aac *.flac *.opus"), ("所有文件", "*.*")]


class StartupError(RuntimeError):
    """某一步失败。带 step（哪一步）与 hint（用户接下来该做什么）。"""

    def __init__(self, step: str, message: str, hint: str = ""):
        super().__init__(message)
        self.step = step
        self.message = message
        self.hint = hint


# ---------------------------------------------------------------- 纯函数：目录与配置
def app_root() -> str:
    """站点根目录：打包后取 PyInstaller 的资源目录，直接运行时取仓库根目录。"""
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.executable)))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


APP_MODE_FLAG = "appmode.flag"      # 资源目录里放了这个文件 → 「独立应用窗口」模式（加壳版）
_APP_WINDOW_BROWSERS = (
    r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe",
    r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe",
    r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
    r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
    r"%LocalAppData%\Google\Chrome\Application\chrome.exe",
)


def app_mode_enabled() -> bool:
    """加壳版判定：资源目录里放了 appmode.flag 就在独立应用窗口里打开界面。"""
    return os.path.isfile(os.path.join(app_root(), APP_MODE_FLAG))


def find_app_browser() -> str | None:
    """找一个能用 `--app` 模式开无地址栏窗口的内核（Edge 优先，其次 Chrome）；找不到返回 None。"""
    for pattern in _APP_WINDOW_BROWSERS:
        path = os.path.expandvars(pattern)
        if os.path.isfile(path):
            return path
    return None


def open_app_window(url: str):
    """用 Edge/Chrome 的 `--app` 模式开一个无地址栏 / 无标签页的独立窗口。

    找不到可用内核时退回系统默认浏览器（行为与普通版一致），保证不会打不开。
    """
    exe = find_app_browser()
    if exe:
        try:
            subprocess.Popen([exe, "--app=%s" % url],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except OSError:
            pass
    return webbrowser.open(url)


def resolve_dirs(cfg: dict | None = None, game_dir: str | None = None,
                 screenshots: str | None = None) -> tuple[str, str]:
    """配置文件 + 命令行 + 自动定位 → (游戏目录, 截图目录)。

    优先级：显式给出 > 配置里记住的 > 自动定位。只有**确实存在**的目录才会返回，
    免得界面上显示一个用不了的路径；取不到就是空串（由用户手填）。
    """
    cfg = cfg or {}
    game = game_dir or cfg.get("game_dir") or serve.default_game_dir()
    if game and not os.path.isdir(game):
        game = None
    shots = screenshots or cfg.get("screenshots_dir") or serve.default_screenshots_dir()
    if shots and not os.path.isdir(shots):
        shots = None
    return game or "", shots or ""


def build_config(game_dir: str = "", screenshots_dir: str = "", auto_zoom: bool = False,
                 auto_center: bool = True, auto_start: bool = False, sound_enabled: bool = False,
                 sound_on: dict | None = None, sound_files: dict | None = None,
                 auto_screenshot: bool = False, shot_interval_ms: int = config.SHOT_INTERVAL_DEFAULT,
                 shot_key: str | None = None, auto_delete: bool = False,
                 delete_since: float | None = None) -> dict:
    """把界面上的表单值收敛成一份完整配置（交给 config.save 落盘）。

    音频只存**文件名**（已复制进软件目录 `sounds/`），所以换机器/清缓存都不会失效。
    自动截图的按键只存键名（如 `V`），间隔钳到合理区间（见 config.clamp_interval）。
    `delete_since` 是「自动删除」开关的开启时刻：只删它之后产生的截图，历史截图不动。
    """
    sound_on = sound_on or {}
    sound_files = sound_files or {}
    sound = {"enabled": bool(sound_enabled)}
    for key in config.SOUND_KEYS:
        sound[key] = {"on": bool(sound_on.get(key, True)), "file": sound_files.get(key) or None}
    return {
        "version": 1,
        "game_dir": (game_dir or "").strip() or None,
        "screenshots_dir": (screenshots_dir or "").strip() or None,
        "auto_zoom": bool(auto_zoom),
        "auto_center": bool(auto_center),
        "auto_start": bool(auto_start),
        "auto_screenshot": {
            "enabled": bool(auto_screenshot),
            "interval_ms": config.clamp_interval(shot_interval_ms),
            "key": (shot_key or "").strip() or None,
        },
        "auto_delete": {
            "enabled": bool(auto_delete),
            "since": float(delete_since) if (auto_delete and delete_since) else None,
        },
        "sound": sound,
    }


# ---------------------------------------------------------------- 启动编排
def _no_proxy_opener():
    """本机自检必须绕过系统代理，否则 127.0.0.1 会被送去代理。"""
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def check_health(url: str, timeout: float = 12.0, interval: float = 0.25) -> dict[str, Any]:
    """轮询 /api/health 直到服务就绪；超时抛 TimeoutError（附最后一次失败原因）。"""
    opener = _no_proxy_opener()
    deadline = time.monotonic() + timeout
    last = ""
    while time.monotonic() < deadline:
        try:
            with opener.open(url + "api/health", timeout=3) as res:
                payload = json.loads(res.read().decode("utf-8"))
            if payload.get("ok"):
                return payload
            last = (payload.get("data") or {}).get("error") or "服务未就绪"
        except Exception as exc:  # 端口刚起时连接被拒很正常，继续轮询
            last = str(exc)
        time.sleep(interval)
    raise TimeoutError(last or "自检超时")


class Startup:
    """四步启动编排。所有外部动作都可注入，便于单测。"""

    def __init__(
        self,
        root: str | None = None,
        port: int = DEFAULT_PORT,
        host: str = DEFAULT_HOST,
        screenshots: str | None = None,
        game_dir: str | None = None,       # 游戏目录（含 Logs）→ serve 用它做日志监控
        config_dir: str | None = None,     # 配置与 sounds/ 的落盘目录，默认软件目录
        create_server: Callable[..., Any] = serve.create_server,
        open_browser: Callable[[str], Any] = webbrowser.open,
        health: Callable[[str], dict] = check_health,
        on_step: Callable[[str, str, str], None] | None = None,
    ):
        self.root = os.path.abspath(root or app_root())
        self.port = port
        self.host = host
        self.screenshots = screenshots
        self.game_dir = game_dir
        self.config_dir = config_dir
        self.create_server = create_server
        self.open_browser = open_browser
        self.health = health
        self.on_step = on_step

        self.server = None
        self.thread: threading.Thread | None = None
        self.url = ""
        self.health_payload: dict[str, Any] | None = None
        self.screenshots_resolved: str | None = None
        self.game_dir_resolved: str | None = None

    # ------------------------------------------------------------ 内部
    def _emit(self, step: str, state: str, detail: str = ""):
        if self.on_step:
            self.on_step(step, state, detail)

    # ------------------------------------------------------------ 步骤
    def step_check_data(self):
        self._emit(STEP_CHECK, "running")
        status = serve.data_status(self.root)
        if not status["ready"]:
            detail = status.get("error") or "数据未就绪"
            self._emit(STEP_CHECK, "failed", detail)
            raise StartupError(
                STEP_CHECK,
                detail,
                "首次使用需要联网拉取一次数据：在项目目录运行 python tools/fetch_data.py"
                "（本工具运行期不联网，数据是提前拉好的）。",
            )
        self._emit(STEP_CHECK, "done", "已收录 %d 张地图" % status["maps"])

    def step_start_server(self):
        self._emit(STEP_SERVER, "running")
        # 未显式指定截图目录时自动探测默认位置；目录不存在就不启动对应监听（不报错）
        screenshots = self.screenshots
        if screenshots is None:
            default = serve.default_screenshots_dir()
            screenshots = default if os.path.isdir(default) else None
        self.screenshots_resolved = screenshots
        # 游戏目录不做二次探测：界面/命令行已经填过自动定位的结果，
        # 这里再猜一次会让用户「清空目录以关闭日志监控」的意图失效。
        self.game_dir_resolved = self.game_dir

        kwargs: dict[str, Any] = {"screenshots": screenshots}
        if self.game_dir:
            kwargs["game_dir"] = self.game_dir
        if self.config_dir:
            kwargs["config_dir"] = self.config_dir
        try:
            self.server = self.create_server(self.port, self.host, self.root, **kwargs)
        except serve.PortInUseError as exc:
            self._emit(STEP_SERVER, "failed", str(exc))
            raise StartupError(STEP_SERVER, str(exc), "换个端口重启，例如 --port 8788。") from exc
        except FileNotFoundError as exc:
            self._emit(STEP_SERVER, "failed", str(exc))
            raise StartupError(STEP_SERVER, str(exc), "请确认站点文件完整（index.html、data/、assets/）。") from exc

        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = serve.url_for(self.host, self.server.server_address[1])
        self._emit(STEP_SERVER, "done", self.url)

    def step_self_check(self):
        self._emit(STEP_SELFCHECK, "running")
        try:
            self.health_payload = self.health(self.url)
        except Exception as exc:
            self._emit(STEP_SELFCHECK, "failed", str(exc))
            raise StartupError(STEP_SELFCHECK, "服务自检未通过：%s" % exc, "请查看是否有安全软件拦截本机端口。") from exc
        # health 的 position/logs 表示「监听是否已开启」，positionAvailable 表示「已解析到位置」
        if not self.health_payload.get("position"):
            position = "实时定位未开启（未找到截图目录）"
        elif self.health_payload.get("positionAvailable"):
            position = "实时定位已开启"
        else:
            position = "实时定位已开启，等待首张截图"
        if self.health_payload.get("logs"):
            logs = "日志监控已开启（自动切图 / 任务事件）"
        else:
            logs = "日志监控未开启（未找到游戏目录）"
        self._emit(STEP_SELFCHECK, "done",
                   "版本 %s · %s · %s" % (self.health_payload.get("version", VERSION), position, logs))

    def step_open_browser(self):
        self._emit(STEP_BROWSER, "running")
        try:
            opened = self.open_browser(self.url)
        except Exception as exc:  # 浏览器打不开不该把已经就绪的服务关掉
            self._emit(STEP_BROWSER, "done", "未能自动打开，请手动访问 %s（%s）" % (self.url, exc))
            return
        if opened is False:
            self._emit(STEP_BROWSER, "done", "未能自动打开，请手动访问 %s" % self.url)
        else:
            self._emit(STEP_BROWSER, "done", self.url)

    def run(self):
        """依次跑完四步；失败即抛 StartupError，不留下半启动状态。"""
        self.step_check_data()
        self.step_start_server()
        try:
            self.step_self_check()
        except StartupError:
            self.stop()          # 自检不过就别留着一个半活的端口
            raise
        self.step_open_browser()

    def stop(self):
        """关闭服务并等待服务线程退出。可重复调用。"""
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
            self.server = None
        if self.thread is not None:
            self.thread.join(timeout=5)
            self.thread = None

    def retry(self):
        """退出清理后重跑一遍（UI 的「重试」按钮用）。"""
        self.stop()
        for step, _ in STEPS:
            self._emit(step, "pending")
        self.run()


# ---------------------------------------------------------------- XP(Luna) 风窗口
FACE = "#ECE9D8"        # XP 对话框底色
GROUP_FG = "#204070"    # 分组框标题
TITLE_A = (0x00, 0x5A, 0xE6)
TITLE_B = (0x3D, 0x9C, 0xF5)
GREEN = "#06B025"       # XP 进度条绿
SUNKEN_DARK = "#808080"
SUNKEN_LIGHT = "#FFFFFF"
MUTED = "#4A4A4A"


class LaunchWindow:
    """tkinter 壳：设置表单 + 启动按钮 + 四步进度。"""

    W, H = 560, 600

    def __init__(self, startup: Startup):
        import tkinter as tk

        self.tk = tk
        self.startup = startup
        # 默认落在用户级持久化目录（%APPDATA%\EFTMap）：打包会整个重建 dist，
        # 配置若留在 exe 目录就每次都被清掉。旧的软件目录里有配置/提示音时首次自动迁移。
        if startup.config_dir:
            self.app_dir = os.path.abspath(startup.config_dir)
            self.migrated: list[str] = []
        else:
            self.app_dir = os.path.abspath(config.default_storage_dir())
            self.migrated = config.migrate_legacy(self.app_dir, config.app_dir())
        self.cfg = config.load(self.app_dir)

        self.events: queue.Queue = queue.Queue()
        self.step_widgets: dict[str, tuple[Any, Any]] = {}
        self.states: dict[str, str] = {step: "pending" for step, _ in STEPS}
        self.progress = 0.0
        self.failed = False
        self.running = False
        self._closing = False
        self._ready = False

        self.root = tk.Tk()
        self.root.title("EFT 互动地图 · 设置与启动")
        self.root.resizable(False, False)
        self.root.configure(bg=FACE)
        self.root.protocol("WM_DELETE_WINDOW", self.quit)

        self._build_header()
        self._build_body()
        self._build_buttons()
        self._sync_sound_enabled()
        self._refresh_sound_labels()
        self._sync_shot_enabled()
        self._prefill_shot_key()

        self.startup.on_step = lambda step, state, detail: self.events.put((step, state, detail))
        self._fit()
        self.root.after(60, self._pump)

    # ------------------------------------------------------------ 布局
    def _fit(self):
        """按实际内容算窗口大小（表单行数固定，但字体度量随系统 DPI 变）。"""
        self.root.update_idletasks()
        w = max(self.W, self.root.winfo_reqwidth())
        h = max(self.H, self.root.winfo_reqheight())
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 3)
        self.root.geometry("%dx%d+%d+%d" % (w, h, x, y))

    def _group(self, parent, title):
        box = self.tk.LabelFrame(parent, text=" " + title + " ", bg=FACE, fg=GROUP_FG,
                                 font=("Tahoma", 9, "bold"), bd=1, relief="groove",
                                 labelanchor="nw", padx=8, pady=5)
        box.pack(fill="x", pady=(0, 6))
        return box

    def _build_header(self):
        tk = self.tk
        self.header_w = self.W
        canvas = tk.Canvas(self.root, width=self.header_w, height=30, highlightthickness=0, bd=0)
        canvas.pack(fill="x")
        for i in range(30):
            t = i / 29.0
            color = "#%02x%02x%02x" % tuple(round(a + (b - a) * t) for a, b in zip(TITLE_A, TITLE_B))
            canvas.create_line(0, i, self.header_w, i, fill=color)
        self.title_text = canvas.create_text(
            9, 15, anchor="w", text="EFT 互动地图 · 设置与启动", fill="white", font=("Tahoma", 9, "bold")
        )
        # XP 风格关闭按钮（红底白叉）
        canvas.create_rectangle(self.header_w - 27, 6, self.header_w - 7, 24, fill="#D25A2E", outline="#B34A22")
        canvas.create_line(self.header_w - 22, 11, self.header_w - 12, 20, fill="white", width=2)
        canvas.create_line(self.header_w - 12, 11, self.header_w - 22, 20, fill="white", width=2)
        canvas.tag_bind(canvas.create_rectangle(self.header_w - 27, 4, self.header_w - 5, 26, fill="", outline=""),
                        "<Button-1>", lambda _ev: self.quit())
        self.header = canvas

    def _build_body(self):
        tk = self.tk
        body = tk.Frame(self.root, bg=FACE)
        body.pack(fill="both", expand=True, padx=12, pady=(10, 0))

        game, shots = resolve_dirs(self.cfg)
        self.game_var = tk.StringVar(value=game)
        self.shots_var = tk.StringVar(value=shots)
        self.auto_zoom_var = tk.BooleanVar(value=bool(self.cfg.get("auto_zoom")))
        self.auto_center_var = tk.BooleanVar(value=bool(self.cfg.get("auto_center")))
        self.auto_start_var = tk.BooleanVar(value=bool(self.cfg.get("auto_start")))
        self.sound_enabled_var = tk.BooleanVar(value=bool(self.cfg["sound"]["enabled"]))
        self.sound_on: dict[str, bool] = {k: bool(self.cfg["sound"][k]["on"]) for k in config.SOUND_KEYS}
        self.sound_vars: dict[str, Any] = {}
        self.sound_files: dict[str, str] = {k: (self.cfg["sound"][k]["file"] or "") for k in config.SOUND_KEYS}
        self.sound_labels: dict[str, Any] = {}
        self.sound_children: list[Any] = []
        self.shot_enabled_var = tk.BooleanVar(value=bool(self.cfg["auto_screenshot"]["enabled"]))
        self.shot_interval_var = tk.StringVar(value=str(self.cfg["auto_screenshot"]["interval_ms"]))
        self.shot_key_var = tk.StringVar(value=self.cfg["auto_screenshot"]["key"] or "")
        self.shot_children: list[Any] = []
        # 自动删除：开关状态沿用配置；开启时刻在「关→开」那一刻记下（关掉即清空，下次重开重新计时）
        self.delete_var = tk.BooleanVar(value=bool(self.cfg["auto_delete"]["enabled"]))
        self.delete_since: float | None = self.cfg["auto_delete"]["since"]

        # ------------------------------- 目录
        dirs = self._group(body, "目录（留空则自动定位；定不到可手填或浏览）")
        self._dir_row(dirs, "game", self.game_var, "游戏目录", self._auto_game)
        self._dir_row(dirs, "shots", self.shots_var, "截图目录", self._auto_shots)
        tk.Label(dirs, text="游戏目录用于监控 Logs（进图自动切图 + 任务事件）；截图目录用于实时定位。",
                 bg=FACE, fg=MUTED, font=("Tahoma", 8), anchor="w").pack(fill="x", pady=(1, 0))

        # ------------------------------- 地图显示
        maps = self._group(body, "地图显示")
        self._check(maps, "定位自动缩放（沿用最近一次手动缩放比例，首次 4×）", self.auto_zoom_var)
        self._check(maps, "点位自动居中（跟随实时位置平移地图）", self.auto_center_var)

        # ------------------------------- 声音
        sound = self._group(body, "声音提示")
        self._check(sound, "启用声音提示", self.sound_enabled_var, command=self._on_sound_master)
        for key in config.SOUND_KEYS:
            self._sound_row(sound, key)

        # ------------------------------- 自动截图
        shot = self._group(body, "自动截图（模拟按键，游戏窗口需在前台）")
        self._check(shot, "启用自动截图（仅在战局中且游戏窗口在前台时发送）",
                    self.shot_enabled_var, command=self._on_shot_master)
        row = tk.Frame(shot, bg=FACE)
        row.pack(fill="x", pady=1, padx=(16, 0))
        tk.Label(row, text="间隔", bg=FACE, font=("Tahoma", 9)).pack(side="left")
        self.shot_interval_entry = tk.Entry(row, textvariable=self.shot_interval_var, width=7,
                                            font=("Tahoma", 9), bd=1, relief="sunken", justify="right")
        self.shot_interval_entry.pack(side="left", padx=(4, 2))
        tk.Label(row, text="ms", bg=FACE, font=("Tahoma", 9)).pack(side="left")
        tk.Label(row, text="按键", bg=FACE, font=("Tahoma", 9)).pack(side="left", padx=(10, 0))
        self.shot_key_entry = tk.Entry(row, textvariable=self.shot_key_var, width=10,
                                       font=("Tahoma", 9), bd=1, relief="sunken")
        self.shot_key_entry.pack(side="left", padx=(4, 2))
        tk.Button(row, text="从日志同步", font=("Tahoma", 8), bd=1, padx=6, pady=1,
                  command=self._sync_shot_key).pack(side="left", padx=(4, 0))
        self.shot_sync_label = tk.Label(shot, text="", bg=FACE, fg=MUTED, font=("Tahoma", 8), anchor="w")
        self.shot_sync_label.pack(fill="x", padx=(16, 0))
        tk.Label(shot, text="原理：按游戏内截图键（默认 V，可从日志同步）。注意：EFT 有 BattlEye 反作弊，"
                            "模拟输入可能被判定为异常；截图会按间隔写入截图目录并持续增长，请自行取舍。",
                 bg=FACE, fg="#8A5A00", font=("Tahoma", 8), anchor="w", justify="left",
                 wraplength=self.W - 60).pack(fill="x", padx=(16, 0), pady=(2, 0))
        self.shot_children.extend([self.shot_interval_entry, self.shot_key_entry])
        for entry in (self.shot_interval_entry, self.shot_key_entry):
            entry.bind("<FocusOut>", lambda _ev: self._save())

        # 自动删除与自动截图同组：一个负责拍、一个负责清，但各自独立开关
        self._check(shot, "读取位置后自动删除旧截图（只保留最新 1 张供定位）",
                    self.delete_var, command=self._on_delete_master)
        tk.Label(shot, text="注意：开启后，开启期间产生的截图会在读出位置后被删除（含你手动按截图键拍的）；"
                            "开关关闭前的历史截图不会动。删除不可恢复，请确认后再开。",
                 bg=FACE, fg="#8A5A00", font=("Tahoma", 8), anchor="w", justify="left",
                 wraplength=self.W - 60).pack(fill="x", padx=(16, 0), pady=(2, 0))

        # ------------------------------- 状态
        status = self._group(body, "状态")
        for step, label in STEPS:
            row = tk.Frame(status, bg=FACE)
            row.pack(fill="x", pady=1)
            icon = tk.Label(row, text=STATE_ICON["pending"], width=2, bg=FACE,
                            fg=STATE_COLOR["pending"], font=("Tahoma", 10, "bold"))
            icon.pack(side="left")
            tk.Label(row, text=label, width=12, anchor="w", bg=FACE,
                     font=("Tahoma", 9)).pack(side="left")
            detail = tk.Label(row, text="", anchor="w", bg=FACE, fg=MUTED, font=("Tahoma", 8))
            detail.pack(side="left", fill="x", expand=True)
            self.step_widgets[step] = (icon, detail)

        self.bar = tk.Canvas(status, width=self.W - 56, height=20, highlightthickness=0, bd=0, bg=FACE)
        self.bar.pack(pady=(8, 2))
        self.status = tk.Label(status, text="尚未启动。点「启动 WebUI」开始。", bg=FACE, fg=MUTED,
                               font=("Tahoma", 8), anchor="w")
        self.status.pack(fill="x")

        self.message = tk.Message(body, text="", width=self.W - 40, bg=FACE, fg="#C00000",
                                  font=("Tahoma", 8), justify="left")
        self.message.pack(fill="x", pady=(2, 0))
        self._draw_bar()

    def _dir_row(self, parent, key, var, label, on_auto):
        tk = self.tk
        row = tk.Frame(parent, bg=FACE)
        row.pack(fill="x", pady=2)
        tk.Label(row, text=label, width=8, anchor="w", bg=FACE, font=("Tahoma", 9)).pack(side="left")
        entry = tk.Entry(row, textvariable=var, font=("Tahoma", 9), bd=1, relief="sunken")
        entry.pack(side="left", fill="x", expand=True, padx=(2, 4))
        # 失焦即落盘，这样「手填一个路径」不必再点别处确认
        entry.bind("<FocusOut>", lambda _ev: self._save())
        tk.Button(row, text="自动定位", font=("Tahoma", 8), command=on_auto, bd=1,
                  padx=6, pady=1).pack(side="left")
        tk.Button(row, text="浏览…", font=("Tahoma", 8), command=lambda k=key: self._browse(k), bd=1,
                  padx=6, pady=1).pack(side="left", padx=(4, 0))

    def _check(self, parent, text, var, command=None):
        cb = self.tk.Checkbutton(parent, text=text, variable=var, bg=FACE, activebackground=FACE,
                                 font=("Tahoma", 9), anchor="w", highlightthickness=0,
                                 command=command or self._save)
        cb.pack(fill="x")
        return cb

    def _sound_row(self, parent, key):
        tk = self.tk
        row = tk.Frame(parent, bg=FACE)
        row.pack(fill="x", pady=1, padx=(16, 0))
        var = tk.BooleanVar(value=self.sound_on[key])
        cb = tk.Checkbutton(row, text=config.SOUND_LABELS[key], variable=var, bg=FACE,
                            activebackground=FACE, font=("Tahoma", 9), width=11, anchor="w",
                            highlightthickness=0, command=self._save)
        cb.pack(side="left")
        btn = tk.Button(row, text="选取音频…", font=("Tahoma", 8), bd=1, padx=6, pady=1,
                        command=lambda k=key: self._pick_sound(k))
        btn.pack(side="left", padx=(6, 4))
        label = tk.Label(row, text="（默认提示音）", bg=FACE, fg=MUTED, font=("Tahoma", 8), anchor="w")
        label.pack(side="left", fill="x", expand=True)
        self.sound_vars[key] = var
        self.sound_labels[key] = label
        self.sound_children.extend([cb, btn])

    def _build_buttons(self):
        tk = self.tk
        row = tk.Frame(self.root, bg=FACE)
        row.pack(fill="x", padx=12, pady=(8, 2))

        def mk(text, command, state="normal", side="right"):
            btn = tk.Button(row, text=text, command=command, state=state, font=("Tahoma", 9),
                            bg=FACE, activebackground=FACE, relief="raised", bd=2, padx=12, pady=2)
            btn.pack(side=side, padx=(6, 0))
            return btn

        self.btn_exit = mk("退出", self.quit)
        self.btn_min = mk("最小化", self.root.iconify, state="disabled")
        self.btn_open = mk("打开界面", self.open_ui, state="disabled")
        self.btn_save = mk("保存配置", self.save_config)
        self.btn_retry = mk("重试", self.retry, state="disabled")
        self.btn_retry.pack_forget()   # 默认隐藏，失败时才换出来

        self.btn_start = mk("启动 WebUI", self.start_webui, side="left")
        self.chk_auto = tk.Checkbutton(row, text="自动启动 WebUI", variable=self.auto_start_var,
                                       bg=FACE, activebackground=FACE, font=("Tahoma", 9),
                                       highlightthickness=0, command=self._save)
        self.chk_auto.pack(side="left", padx=(10, 0))

        # 保存位置 / 保存结果反馈（表单本来就会自动保存，这行让用户看得见「保存在哪」）
        self.save_note = tk.Label(self.root, text=self._config_note_text(), bg=FACE, fg=MUTED,
                                  font=("Tahoma", 8), anchor="w")
        self.save_note.pack(fill="x", padx=12, pady=(0, 10))

    # ------------------------------------------------------------ 表单动作
    def current_config(self) -> dict:
        """界面上的表单值 → 完整配置。"""
        return build_config(
            game_dir=self.game_var.get(),
            screenshots_dir=self.shots_var.get(),
            auto_zoom=self.auto_zoom_var.get(),
            auto_center=self.auto_center_var.get(),
            auto_start=self.auto_start_var.get(),
            sound_enabled=self.sound_enabled_var.get(),
            sound_on={k: self.sound_vars[k].get() for k in config.SOUND_KEYS},
            sound_files=self.sound_files,
            auto_screenshot=self.shot_enabled_var.get(),
            shot_interval_ms=self._shot_interval(),
            shot_key=self.shot_key_var.get(),
            auto_delete=self.delete_var.get(),
            delete_since=self.delete_since,
        )

    def _save(self) -> bool:
        """把界面上的表单落盘。

        页面里的界面偏好（`ui` 块：图层开关 / 楼层开关）由 WebUI 自己维护，
        启动器只管自己的那几项；这里把磁盘上的 `ui` 原样带上，
        否则每次表单失焦落盘都会把用户刚在页面上保存的勾选清掉。
        """
        payload = self.current_config()
        payload["ui"] = config.load(self.app_dir).get("ui") or {}
        try:
            config.save(payload, self.app_dir)
        except OSError as exc:
            self.message.configure(text="设置保存失败：%s（不影响本次启动）" % exc)
            return False
        return True

    def _config_note_text(self) -> str:
        """保存位置提示（迁移过就把迁移项数带上）。"""
        note = "配置保存在：" + config.config_path(self.app_dir)
        if self.migrated:
            note = "已从软件目录迁移 %d 项配置 · %s" % (len(self.migrated), note)
        return note

    def save_config(self):
        """「保存配置」按钮：把当前表单落盘并就地给出反馈。

        表单本来在失焦 / 勾选 / 启动时就自动保存，这个按钮只是让「保存」这件事看得见，
        用户不必先点一下别处再启动。
        """
        if self._save():
            self.save_note.configure(text="已保存 ✓  " + config.config_path(self.app_dir),
                                     fg="#0A8A0A")
            self.root.after(4000, self._reset_save_note)
        else:
            self.save_note.configure(text="保存失败：" + config.config_path(self.app_dir),
                                     fg="#C00000")

    def _reset_save_note(self):
        if self._closing:
            return
        self.save_note.configure(text=self._config_note_text(), fg=MUTED)

    def _info(self, title, text):
        from tkinter import messagebox

        messagebox.showinfo(title, text, parent=self.root)

    def _error(self, title, text):
        from tkinter import messagebox

        messagebox.showerror(title, text, parent=self.root)

    def _browse(self, key):
        from tkinter import filedialog

        var = self.game_var if key == "game" else self.shots_var
        current = var.get().strip()
        chosen = filedialog.askdirectory(
            title="选择%s" % ("游戏目录（含 Logs）" if key == "game" else "截图目录"),
            initialdir=current if os.path.isdir(current) else None, parent=self.root)
        if chosen:
            var.set(os.path.normpath(chosen))
            self._save()

    def _auto_game(self):
        found = serve.default_game_dir()
        if not found:
            self._info("自动定位",
                       "没有找到 EFT 游戏目录。\n请点「浏览…」手动选择（目录里应有 Logs 子文件夹）。")
            return
        self.game_var.set(found)
        self.message.configure(text="")
        self._save()

    def _auto_shots(self):
        found = serve.default_screenshots_dir()
        if not os.path.isdir(found):
            self._info("自动定位", "没有找到截图目录：\n%s\n请点「浏览…」手动选择。" % found)
            return
        self.shots_var.set(os.path.normpath(found))
        self.message.configure(text="")
        self._save()

    def _pick_sound(self, key):
        """选音频 → 复制进软件目录（持久化）→ 记下文件名。"""
        from tkinter import filedialog

        chosen = filedialog.askopenfilename(title="选择「%s」提示音" % config.SOUND_LABELS[key],
                                            filetypes=AUDIO_FILETYPES, parent=self.root)
        if not chosen:
            return
        try:
            name = config.import_sound(chosen, self.app_dir)
        except (OSError, ValueError) as exc:
            self._error("选取音频", "导入失败：%s" % exc)
            return
        self.sound_files[key] = name
        self.sound_enabled_var.set(True)
        self._sync_sound_enabled()
        self._refresh_sound_labels()
        self._save()

    def _refresh_sound_labels(self):
        for key in config.SOUND_KEYS:
            name = self.sound_files.get(key) or ""
            label = self.sound_labels[key]
            if not name:
                label.configure(text="（默认提示音）", fg=MUTED)
            elif config.resolve_sound(name, self.app_dir):
                label.configure(text=name, fg="#0A8A0A")
            else:
                label.configure(text="%s（文件已丢失）" % name, fg="#C00000")

    def _sync_sound_enabled(self):
        state = "normal" if self.sound_enabled_var.get() else "disabled"
        for widget in self.sound_children:
            widget.configure(state=state)

    def _on_sound_master(self):
        self._sync_sound_enabled()
        self._save()

    # ------------------------------------------------------------ 自动截图
    def _shot_interval(self) -> int:
        """间隔输入框 → 合法毫秒数（脏值由 config.clamp_interval 兜底）。"""
        return config.clamp_interval(self.shot_interval_var.get())

    def _sync_shot_enabled(self):
        state = "normal" if self.shot_enabled_var.get() else "disabled"
        for widget in self.shot_children:
            widget.configure(state=state)

    def _on_shot_master(self):
        self._sync_shot_enabled()
        self._save()

    def _on_delete_master(self):
        """自动删除开关：由关变开时记下此刻（时间闸），由开变关时清掉，下次重开重新计时。"""
        if self.delete_var.get():
            if not self.delete_since:
                self.delete_since = time.time()
        else:
            self.delete_since = None
        self._save()

    def _shot_note(self, text: str, color: str = MUTED):
        self.shot_sync_label.configure(text=text, fg=color)

    def _sync_shot_key(self):
        """从最新会话的日志里同步游戏内截图键（控制绑定写在日志开头）。"""
        game = self.game_var.get().strip()
        if not game or not os.path.isdir(game):
            self._shot_note("请先填写可用的游戏目录（含 Logs）", "#C00000")
            return
        try:
            key = eftlog.read_screenshot_key(game)
        except OSError as exc:
            self._shot_note("读取日志失败：%s" % exc, "#C00000")
            return
        if not key:
            self._shot_note("日志里没找到截图键（游戏需先启动过一次）", "#C00000")
            return
        self.shot_key_var.set(key)
        self._shot_note("已从日志同步截图键：%s" % key, "#0A8A0A")
        self._save()

    def _prefill_shot_key(self):
        """开窗时若按键为空，就静默地同步一次（失败不打扰用户）。"""
        if self.shot_key_var.get().strip():
            return
        game = self.game_var.get().strip()
        if not game or not os.path.isdir(game):
            return
        try:
            key = eftlog.read_screenshot_key(game)
        except OSError:
            return
        if key:
            self.shot_key_var.set(key)
            self._shot_note("已从日志同步截图键：%s" % key, "#0A8A0A")
            self._save()

    # ------------------------------------------------------------ 绘制
    def _draw_bar(self):
        c, w, h = self.bar, self.W - 56, 20
        c.delete("all")
        c.create_rectangle(0, 0, w - 1, h - 1, outline=SUNKEN_DARK, fill=SUNKEN_DARK)
        c.create_line(w - 1, 1, w - 1, h - 1, fill=SUNKEN_LIGHT)
        c.create_line(1, h - 1, w - 1, h - 1, fill=SUNKEN_LIGHT)
        c.create_rectangle(2, 2, w - 2, h - 2, outline="#FFFFFF", fill="#FFFFFF")
        inner_w = w - 5
        filled = int(inner_w * max(0.0, min(1.0, self.progress)))
        block = 9
        x = 3
        while x + block - 2 <= 3 + filled:
            c.create_rectangle(x, 4, x + block - 2, h - 5, fill=GREEN, outline=GREEN)
            x += block

    # ------------------------------------------------------------ 事件
    def _pump(self):
        """把工作线程投递的进度事件画到界面上（tkinter 只能在主线程动控件）。

        常驻自循环（60ms 一次，开销可忽略）：事件可能在任何时刻到达，
        包括窗口刚建好还没点启动的时候，所以不做「只在启动期间轮询」的条件判断。
        """
        try:
            while True:
                step, state, detail = self.events.get_nowait()
                self._apply(step, state, detail)
        except queue.Empty:
            pass
        if not self._closing:
            self.root.after(60, self._pump)

    def _apply(self, step, state, detail):
        if step not in self.step_widgets:
            return
        self.states[step] = state
        icon, label = self.step_widgets[step]
        icon.configure(text=STATE_ICON[state], fg=STATE_COLOR[state])
        label.configure(text=detail or "")
        done = sum(1 for s in STEPS if self.states[s[0]] == "done")
        self.progress = done / len(STEPS)
        if self.failed:
            self.progress = min(self.progress, (len(STEPS) - 1) / len(STEPS))
        self._draw_bar()

        if state == "failed":
            self.failed = True
            self.running = False
            self.status.configure(text="启动失败，改正后点「重试」。")
            self.message.configure(text=detail)
            self.btn_open.configure(state="disabled")
            self.btn_start.configure(state="disabled", text="启动 WebUI")
            self.btn_retry.pack(side="right", padx=(6, 0))
            self.btn_retry.configure(state="normal")
            self.header.itemconfigure(self.title_text, text="EFT 互动地图 · 启动失败")
            return

        if not self.failed and not self._ready and all(self.states[s[0]] == "done" for s in STEPS):
            self.on_ready()

    def _worker(self):
        try:
            self.startup.run()
        except StartupError as exc:
            text = exc.message + ("\n建议：" + exc.hint if exc.hint else "")
            self.events.put((exc.step, "failed", text))
        except Exception as exc:  # 兜底：未预期异常也要落在界面上，不静默
            self.events.put((STEPS[-1][0], "failed", "未预期的错误：%s" % exc))

    # ------------------------------------------------------------ 启动 / 重试
    def _reset_steps(self):
        self.failed = False
        self._ready = False
        self.progress = 0.0
        self.states = {step: "pending" for step, _ in STEPS}
        for step, _ in STEPS:
            icon, detail = self.step_widgets[step]
            icon.configure(text=STATE_ICON["pending"], fg=STATE_COLOR["pending"])
            detail.configure(text="")
        self.message.configure(text="")
        self.status.configure(text="")
        self.header.itemconfigure(self.title_text, text="EFT 互动地图 · 正在启动")
        self.btn_retry.pack_forget()
        self.btn_open.configure(state="disabled")
        self.btn_min.configure(state="disabled")
        self._draw_bar()

    def start_webui(self):
        """把表单里的设置落盘，然后起服务（工作线程里跑，界面不卡）。"""
        if self.running:
            return
        self._save()          # 写不进去也照样启动，只是先在界面上提示了
        self.startup.game_dir = self.game_var.get().strip() or None
        self.startup.screenshots = self.shots_var.get().strip() or None
        self.startup.config_dir = self.app_dir
        self.running = True
        self._reset_steps()
        self.btn_start.configure(state="disabled", text="正在启动…")
        threading.Thread(target=self._worker, daemon=True).start()

    def open_ui(self):
        if self.startup.url:
            self.startup.open_browser(self.startup.url)

    def retry(self):
        self.startup.game_dir = self.game_var.get().strip() or None
        self.startup.screenshots = self.shots_var.get().strip() or None
        self.startup.config_dir = self.app_dir
        self.running = True
        self._reset_steps()
        self.btn_start.configure(state="disabled", text="正在启动…")
        threading.Thread(target=self._worker_retry, daemon=True).start()

    def _worker_retry(self):
        try:
            self.startup.retry()
        except StartupError as exc:
            text = exc.message + ("\n建议：" + exc.hint if exc.hint else "")
            self.events.put((exc.step, "failed", text))
        except Exception as exc:
            self.events.put((STEPS[-1][0], "failed", "未预期的错误：%s" % exc))

    def on_ready(self):
        self._ready = True
        self.running = True
        self.status.configure(text="服务已就绪：" + self.startup.url)
        self.header.itemconfigure(self.title_text, text="EFT 互动地图 · 已就绪")
        self.btn_open.configure(state="normal")
        self.btn_min.configure(state="normal")
        self.btn_retry.pack_forget()
        self.btn_start.configure(state="disabled", text="已启动")

    def quit(self):
        self._closing = True
        self._save()
        try:
            self.startup.stop()
        finally:
            self.root.destroy()

    def run(self) -> int:
        if self.auto_start_var.get():
            self.root.after(400, self.start_webui)
        self.root.mainloop()
        return 0


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="EFT 互动地图启动器")
    parser.add_argument("--host", default=DEFAULT_HOST, help="监听地址，默认 %s" % DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="监听端口，默认 %d" % DEFAULT_PORT)
    parser.add_argument("--screenshots", default=None, help="EFT 截图目录（实时定位用）")
    parser.add_argument("--game-dir", default=None, help="EFT 游戏目录（含 Logs，日志监控用）")
    parser.add_argument("--config-dir", default=None, help="配置与 sounds/ 的落盘目录，默认软件目录")
    parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器（调试/自动化）")
    parser.add_argument("--app-window", action="store_true",
                        help="在独立的无地址栏应用窗口里打开界面（加壳版行为，见 appmode.flag）")
    return parser.parse_args(argv)


def _say(text: str):
    """windowed 打包后 sys.stdout 可能为 None，打印前先确认。"""
    if sys.stdout is not None:
        print(text)


def main(argv=None) -> int:
    args = parse_args(argv)
    startup = Startup(port=args.port, host=args.host, screenshots=args.screenshots,
                      game_dir=args.game_dir, config_dir=args.config_dir)
    if args.no_browser:
        startup.open_browser = lambda _url: None
    elif args.app_window or app_mode_enabled():
        startup.open_browser = open_app_window
    try:
        window = LaunchWindow(startup)
    except Exception as exc:  # 没有图形环境时退化为纯控制台启动，避免完全不可用
        _say("无法创建启动窗口（%s），改为无界面启动。" % exc)
        cfg_dir = os.path.abspath(startup.config_dir or config.default_storage_dir())
        if not startup.config_dir:
            config.migrate_legacy(cfg_dir, config.app_dir())
        cfg = config.load(cfg_dir)
        game, shots = resolve_dirs(cfg, startup.game_dir, startup.screenshots)
        startup.game_dir = game or None
        startup.screenshots = shots or None
        try:
            startup.run()
        except StartupError as err:
            _say("启动失败：%s %s" % (err.message, err.hint))
            return 1
        _say("服务已就绪：%s  按 Ctrl+C 退出。" % startup.url)
        try:
            while True:
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
        finally:
            startup.stop()
        return 0
    return window.run()


if __name__ == "__main__":
    raise SystemExit(main())
