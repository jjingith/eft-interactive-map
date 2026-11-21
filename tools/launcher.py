#!/usr/bin/env python3
"""EFT 互动地图 · 启动器（运行期入口 → EFTMap.exe）

R71：**双击 EFTMap.exe（无参数）默认启动无边框桌面壳 `EFTMapDesktop.exe`**，
不再静默拉起浏览器。浏览器只在两种情况下出现：
- 显式传 `--browser`（高级用户）；
- 桌面壳缺失 / 启动失败时，先弹中文提示，用户选「是」才改用浏览器。

`EFTMap.exe --server-only` 仍是无窗口后端，供桌面壳内部调用。
Tk 启动窗口保留给 `--settings-only`（壳托盘）与 `--browser` 调试路径。

Tk 启动窗口（`--settings-only` / `--browser`）形态：

    ┌ 游戏目录 / 截图目录   ← 自动定位 + 手填 + 浏览
    ├ 地图显示开关         ← 定位自动缩放 / 点位自动居中
    ├ 声音提示开关 + 3 个子开关（战局开始 / 开始加载战局 / 开始匹配）+「选取音频…」+「试听」
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
import runpy
import secrets
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from typing import Any, Callable

import config
import eftlog
import keyinput
import screenshot
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
    shots = screenshots or cfg.get("screenshots_dir")
    if shots and not os.path.isdir(shots):
        shots = None
    if not shots:
        # R107：配置与默认位置都没有时，按候选目录自动探测（含用户改到 OneDrive/图片目录的情况）
        shots, _note = serve.detect_screenshots_dir(game)
    return game or "", shots or ""


def build_config(game_dir: str = "", screenshots_dir: str = "", auto_zoom: bool = False,
                 auto_center: bool = True, auto_start: bool = False, sound_enabled: bool = False,
                 sound_on: dict | None = None, sound_files: dict | None = None,
                 auto_screenshot: bool = False, shot_interval_ms: int = config.SHOT_INTERVAL_DEFAULT,
                 shot_key: str | None = None, auto_delete: bool = False,
                 cleanup_on_raid_end: bool = False,
                 delete_since: float | None = None, host: str = config.HOST_DEFAULT) -> dict:
    """把界面上的表单值收敛成一份完整配置（交给 config.save 落盘）。

    音频只存**文件名**（已复制进软件目录 `sounds/`），所以换机器/清缓存都不会失效。
    自动截图的按键只存键名（如 `V`），间隔钳到合理区间（见 config.clamp_interval）。
    `delete_since` 是「自动删除」开关的开启时刻：只删它之后产生的截图，历史截图不动。
    `host` 是监听地址（`127.0.0.1` 仅本机 / `0.0.0.0` 允许局域网），见 config.clamp_host。
    """
    sound_on = sound_on or {}
    sound_files = sound_files or {}
    sound = {"enabled": bool(sound_enabled)}
    for key in config.SOUND_KEYS:
        sound[key] = {"on": bool(sound_on.get(key, True)), "file": sound_files.get(key) or None}
    return {
        "version": 1,
        "host": config.clamp_host(host),
        "game_dir": (game_dir or "").strip() or None,
        "screenshots_dir": (screenshots_dir or "").strip() or None,
        "log_dir": None,          # R107：页面里的「日志目录」手动覆盖，启动器不覆盖它（见 _save）
        "auto_zoom": bool(auto_zoom),
        "auto_center": bool(auto_center),
        "auto_start": bool(auto_start),
        "auto_screenshot": {
            "enabled": bool(auto_screenshot),
            "interval_ms": config.clamp_interval(shot_interval_ms),
            "key": (shot_key or "").strip() or None,
            "cleanup_on_raid_end": bool(cleanup_on_raid_end),
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
        shell_mode: bool = False,
        shutdown_token: str | None = None,
        shutdown_callback: Callable[[], None] | None = None,
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
        self.shell_mode = shell_mode
        self.shutdown_token = shutdown_token
        self.shutdown_callback = shutdown_callback

        self.server = None
        self.thread: threading.Thread | None = None
        self.url = ""
        self.health_payload: dict[str, Any] | None = None
        self.screenshots_resolved: str | None = None
        self.game_dir_resolved: str | None = None
        self.ocr_host: subprocess.Popen | None = None

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
        # R107：没显式给截图目录时按候选目录自动探测（不只默认那一处）；
        # 探测不到就不启动对应监听（不报错），服务端仍会继续按配置变化重试。
        screenshots = self.screenshots
        if screenshots is None:
            screenshots, _note = serve.detect_screenshots_dir(self.game_dir)
        self.screenshots_resolved = screenshots
        # 游戏目录不做二次探测：界面/命令行已经填过自动定位的结果。
        # 日志目录由服务端独立探测（Game\Logs / %LOCALAPPDATA% / 文档目录），不再强依赖 game_dir。
        self.game_dir_resolved = self.game_dir

        kwargs: dict[str, Any] = {"screenshots": screenshots, "detect_paths": True}
        if self.game_dir:
            kwargs["game_dir"] = self.game_dir
        if self.config_dir:
            kwargs["config_dir"] = self.config_dir
        if self.shell_mode:
            kwargs["shell_mode"] = True
        if self.shutdown_token:
            kwargs["shutdown_token"] = self.shutdown_token
        if self.shutdown_callback:
            kwargs["shutdown_callback"] = self.shutdown_callback
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

    # ------------------------------------------------------------ 截图识别宿主
    def start_ocr_host(self):
        """拉起截图识别宿主（全局热键 → 框选 → 透明浮窗）。

        R278 之前宿主只存在于开发机的登录自启任务里，装好的客户端根本没有这个
        进程，用户按 Ctrl+Alt+P 自然「没反应」。现在随主程序起，退出时一起收。

        · 宿主自己会先探 /api/health，服务没起就立刻退出，不会留僵尸进程；
        · 宿主带命名互斥量，用户机器上若真有旧的登录自启，晚到的那个自动退出；
        · `EFT_OCR_HOST=0` 可整体关掉（排查 / 自动化测试用）。
        """
        if (os.environ.get("EFT_OCR_HOST") or "").strip().lower() in {"0", "off", "false", "no"}:
            return
        if self.ocr_host is not None and self.ocr_host.poll() is None:
            return
        script = os.path.join(self.root, "tools", "scan.py")
        if not os.path.isfile(script):
            return
        if getattr(sys, "frozen", False):
            # onedir 产物里 sys.executable 是 EFTMap.exe；宿主由 --run-tool 在
            # 同一套冻结依赖里跑，不要求用户机器上装 Python。
            cmd = [sys.executable, "--run-tool", script, "--server", self.url]
        else:
            cmd = [sys.executable, script, "--server", self.url]
        kwargs: dict[str, Any] = {"cwd": self.root,
                                  "stdout": subprocess.DEVNULL,
                                  "stderr": subprocess.DEVNULL,
                                  "stdin": subprocess.DEVNULL}
        if os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            self.ocr_host = subprocess.Popen(cmd, **kwargs)
        except OSError:
            # 宿主起不来不影响主界面：热键失效时用户仍能用「截图识别」面板粘贴图片。
            # 这里不往四步进度里塞状态，避免「打开浏览器」一步被重复上报。
            self.ocr_host = None

    def stop_ocr_host(self):
        host = self.ocr_host
        self.ocr_host = None
        if host is None:
            return
        try:
            if host.poll() is None:
                host.terminate()
                try:
                    host.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    host.kill()
        except OSError:
            pass

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
        self.start_ocr_host()    # 宿主失败不影响主流程：它自己会退出

    def stop(self):
        """关闭服务并等待服务线程退出。可重复调用。"""
        self.stop_ocr_host()
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


# ---------------------------------------------------------------- 提示音试听
# 自定义音频直接播用户选的文件；**没选音频时游戏里响的是「内置提示音」——那是页面用 Web Audio
# 现场合成的**（见 app.js 的 DEFAULT_TONES），所以这里把同一组频率 / 时长在本地合成成 WAV 再播，
# 让「试听听到的」和「游戏里听到的」是同一个音。两边的数值改动要同步（下表与 app.js 一一对应）。
DEFAULT_TONES = {
    "raid_start": ((523.0, 0.00, 0.13), (784.0, 0.14, 0.22)),
    "location_loading": ((430.0, 0.00, 0.16), (430.0, 0.19, 0.16)),
    "matching": ((620.0, 0.00, 0.11), (830.0, 0.12, 0.11)),
}
PREVIEW_RATE = 22050      # 试听用采样率（比 CD 低一档，够听清且文件更小）
PREVIEW_GAIN = 0.22       # 峰值音量，与页面里 gain 的目标值一致


def render_tone_wav(path: str, key: str) -> str:
    """把某个内置提示音合成成 16 位单声道 WAV（三角波 + 快起软收的包络，照页面那套写）。"""
    import math
    import wave

    tones = DEFAULT_TONES.get(key) or ()
    total = max([at + dur for _, at, dur in tones] + [0.0]) + 0.05
    frames = bytearray()
    for index in range(int(total * PREVIEW_RATE)):
        now = index / float(PREVIEW_RATE)
        sample = 0.0
        for freq, at, dur in tones:
            if now < at or now > at + dur:
                continue
            local = now - at
            if local < 0.015:            # 起音：15ms 内线性升到峰值（避免爆音）
                amp = PREVIEW_GAIN * local / 0.015
            else:                        # 收尾：按指数衰减到几乎听不见（同页面里的 ramp）
                amp = PREVIEW_GAIN * math.exp(
                    math.log(0.0001 / PREVIEW_GAIN) * (local - 0.015) / max(dur - 0.015, 1e-6))
            phase = (local * freq) % 1.0                 # 三角波
            sample += amp * (4.0 * abs(phase - 0.5) - 1.0)
        value = max(-1.0, min(1.0, sample))
        frames += int(value * 32000).to_bytes(2, "little", signed=True)
    with wave.open(path, "wb") as fh:
        fh.setnchannels(1)
        fh.setsampwidth(2)
        fh.setframerate(PREVIEW_RATE)
        fh.writeframes(bytes(frames))
    return path


def preview_wav(key: str) -> str:
    """内置提示音的试听 WAV 落在临时目录里（同一 key 只合成一次）。"""
    import tempfile

    path = os.path.join(tempfile.gettempdir(), "eftmap-preview-%s.wav" % key)
    if not os.path.isfile(path):
        render_tone_wav(path, key)
    return path


def play_audio(path: str) -> bool:
    """尽量把音频放出来：WAV 走 winsound（异步、不挡窗口），其它格式交给系统默认播放器。

    试听是辅助功能，播不出来也不算错误（返回 False），调用方据此提示用户。
    """
    try:
        import winsound
    except ImportError:              # 非 Windows：没有 winsound
        winsound = None
    if winsound is not None and path.lower().endswith(".wav"):
        winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
        return True
    try:
        if hasattr(os, "startfile"):
            os.startfile(path)       # noqa: S606 - 播的是用户自己选 / 本项目生成的音频
            return True
    except OSError:
        return False
    return False


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
        self._refresh_lan_label()
        self._refresh_remote_warning()

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
        # 允许局域网访问：配置文件里的 host 或命令行 --host 只要有一个是 0.0.0.0 就默认勾上
        self.lan_var = tk.BooleanVar(
            value=self.cfg.get("host") == "0.0.0.0" or startup.host == "0.0.0.0")
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

        # ------------------------------- 局域网访问
        net = self._group(body, "局域网访问（在别的电脑 / 手机上打开本工具）")
        self._check(net, "允许局域网访问（监听 0.0.0.0，仅同一局域网内可访问）",
                    self.lan_var, command=self._on_lan_toggle)
        self.lan_label = tk.Label(net, text="", bg=FACE, fg=MUTED, font=("Tahoma", 8), anchor="w",
                                  justify="left", wraplength=self.W - 60)
        self.lan_label.pack(fill="x", padx=(16, 0))
        tk.Label(net, text="首次开启时 Windows 可能弹出防火墙提示，请选「允许访问」（专用 / 家庭网络）。"
                           "本工具本身不联网；局域网访问只是让同一路由器下的设备能打开这个页面。",
                 bg=FACE, fg=MUTED, font=("Tahoma", 8), anchor="w", justify="left",
                 wraplength=self.W - 60).pack(fill="x", padx=(16, 0), pady=(2, 0))

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
        # R32：一键分辨「按键没送到」/「送到了但游戏没截图」/「截图目录配错了」——
        # 这三种情况以前都只表现为「已发送 N 张」，谁也说不清卡在哪。
        tk.Button(row, text="试拍一张", font=("Tahoma", 8), bd=1, padx=6, pady=1,
                  command=self._try_shot).pack(side="left", padx=(4, 0))
        self.shot_sync_label = tk.Label(shot, text="", bg=FACE, fg=MUTED, font=("Tahoma", 8), anchor="w")
        self.shot_sync_label.pack(fill="x", padx=(16, 0))
        tk.Label(shot, text="原理：按游戏内截图键（默认 V，可从日志同步）。注意：EFT 有 BattlEye 反作弊，"
                            "模拟输入可能被判定为异常；截图会按间隔写入截图目录并持续增长，请自行取舍。",
                 bg=FACE, fg="#8A5A00", font=("Tahoma", 8), anchor="w", justify="left",
                 wraplength=self.W - 60).pack(fill="x", padx=(16, 0), pady=(2, 0))
        # 游戏目录在网络位置时（游戏跑在另一台电脑）模拟按键物理上打不到，这里给一条醒目提示
        self.shot_remote_label = tk.Label(shot, text="", bg=FACE, fg="#C00000", font=("Tahoma", 8, "bold"),
                                          anchor="w", justify="left", wraplength=self.W - 60)
        self.shot_remote_label.pack(fill="x", padx=(16, 0), pady=(2, 0))
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
        btn.pack(side="left", padx=(6, 2))
        pv = tk.Button(row, text="试听", font=("Tahoma", 8), bd=1, padx=6, pady=1,
                       command=lambda k=key: self._preview_sound(k))
        pv.pack(side="left", padx=(2, 4))
        label = tk.Label(row, text="（默认提示音）", bg=FACE, fg=MUTED, font=("Tahoma", 8), anchor="w")
        label.pack(side="left", fill="x", expand=True)
        self.sound_vars[key] = var
        self.sound_labels[key] = label
        self.sound_children.extend([cb, btn, pv])

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
            host=("0.0.0.0" if self.lan_var.get() else config.HOST_DEFAULT),
        )

    def _save(self) -> bool:
        """把界面上的表单落盘。

        页面里的界面偏好（`ui` 块：图层开关 / 楼层开关）由 WebUI 自己维护，
        启动器只管自己的那几项；这里把磁盘上的 `ui` 原样带上，
        否则每次表单失焦落盘都会把用户刚在页面上保存的勾选清掉。
        """
        payload = self.current_config()
        disk = config.load(self.app_dir)
        payload["ui"] = disk.get("ui") or {}
        # R107：这两项由页面维护，启动器表单里没有对应控件，落盘时原样保留，
        # 否则「保存配置」会把页面上刚填的日志目录 / 战局结束清理开关清掉。
        payload["log_dir"] = disk.get("log_dir")
        payload["auto_screenshot"]["cleanup_on_raid_end"] = bool(
            (disk.get("auto_screenshot") or {}).get("cleanup_on_raid_end"))
        if hasattr(self, "shot_remote_label"):     # 游戏目录可能是刚手填的，顺手刷新跨机提示
            self._refresh_remote_warning()
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

    def _preview_sound(self, key):
        """试听：选了自定义音频就播它，没选就播**现场合成**的内置提示音（与游戏里响的是同一个音）。"""
        name = self.sound_files.get(key) or ""
        path = config.resolve_sound(name, self.app_dir) if name else None
        if name and not path:
            self._error("试听提示音", "音频文件已丢失：\n%s\n请重新点「选取音频…」导入。" % name)
            return
        if not path:
            try:
                path = preview_wav(key)
            except (OSError, ValueError) as exc:
                self._error("试听提示音", "内置提示音合成失败：%s" % exc)
                return
        if not play_audio(path):
            self._error("试听提示音", "无法播放这段音频：\n%s\n（可先确认该文件本身能用系统播放器打开）" % path)

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

    # ------------------------------------------------------------ 试拍一张
    # 判据只有一个：**发完之后截图目录里有没有出现新文件**。
    #   扫描码成功 → 完事；扫描码没反应 → 自动换虚拟键码再试一次（参考实现走的就是 vk）；
    #   两种都没反应 → 明确告诉用户去查「游戏内截图键绑定」和「截图目录」。
    SHOT_PROBE_WAIT = 1200      # 发键后等多久再查目录（毫秒）

    def _shot_dir(self) -> str | None:
        """当前生效的截图目录：配置里填的优先，否则用游戏默认位置（存在才算）。"""
        configured = (self.cfg.get("screenshots_dir") or "").strip()
        if configured and os.path.isdir(configured):
            return configured
        fallback = serve.default_screenshots_dir()
        return fallback if fallback and os.path.isdir(fallback) else None

    def _try_shot(self):
        """「试拍一张」：真发一次按键，然后盯目录，把结论直接写在这行小字上。"""
        key = (self.shot_key_var.get() or "").strip()
        if not key:
            self._shot_note("先填截图键，或点「从日志同步」——空键发不出去", "#C00000")
            return
        if keyinput.parse_combo(key) is None:
            self._shot_note("这个键名不认识：%s（%s）" % (key, keyinput.unsupported_reason(key)), "#C00000")
            return
        directory = self._shot_dir()
        if not directory:
            self._shot_note("找不到截图目录：先在下面把「截图目录」设对，否则无法判断有没有拍到", "#C00000")
            return
        base = screenshot.newest_mtime(directory)
        self._shot_note("正在试拍：%s（等 %d ms 看目录）…" % (key, self.SHOT_PROBE_WAIT))
        self._shot_probe(key, directory, base, keyinput.MODE_SCAN)

    def _shot_probe(self, key: str, directory: str, base, mode: str):
        """发一次键并安排「稍后查目录」；失败时换成另一种注入方式再试一次。"""
        try:
            ok, error = keyinput.send_key(key, mode)
        except Exception as exc:                      # 注入实现出问题也不能让界面崩
            ok, error = False, "模拟按键出错：%s" % exc
        if not ok:
            self._shot_note("发不出去：%s" % (error or "未知原因"), "#C00000")
            return
        self.after(self.SHOT_PROBE_WAIT, lambda: self._shot_verdict(key, directory, base, mode))

    def _shot_verdict(self, key: str, directory: str, base, mode: str):
        try:
            newest = screenshot.newest_mtime(directory)
        except Exception:
            newest = None
        if newest is not None and (base is None or newest > base):
            how = "虚拟键码" if mode == keyinput.MODE_VK else "扫描码"
            self._shot_note("试拍成功：截图已出现（%s注入可用），定位马上就会跟上" % how, "#1B7F3B")
            return
        if mode != keyinput.MODE_VK:
            self._shot_note("扫描码没触发截图，自动改用虚拟键码再试一次…")
            self._shot_probe(key, directory, base, keyinput.MODE_VK)
            return
        self._shot_note("两种注入方式都没让游戏出图：请确认①游戏内「截图」键就是 %s"
                        "（设置 → 控制 → 界面）；②截图目录确实是 %s；③游戏窗口在前台且已进战局"
                        % (key, directory), "#C00000")

    # ------------------------------------------------------------ 局域网访问
    def _refresh_lan_label(self):
        """按勾选状态显示「本机地址 / 局域网地址」提示。"""
        port = self.startup.port or DEFAULT_PORT
        if self.lan_var.get():
            url = serve.url_for_lan(port)
            text = ("同一网络访问地址：%s（本机仍可用 http://127.0.0.1:%d/）" % (url, port)) if url \
                else "已开启监听所有网卡，但未探测到本机局域网地址（请检查网络连接）。"
        else:
            text = "当前仅本机可访问：http://127.0.0.1:%d/" % port
        self.lan_label.configure(text=text)

    def _on_lan_toggle(self):
        self._refresh_lan_label()
        self._save()

    def _refresh_remote_warning(self):
        """游戏目录在网络位置时提示「跨机器模拟按键无效」——这正是自动截图无效的根因。"""
        if not hasattr(self, "shot_remote_label"):
            return
        game = self.game_var.get().strip()
        if serve.is_network_path(game):
            self.shot_remote_label.configure(
                text="检测到游戏目录在网络位置（%s）：说明游戏跑在另一台电脑上。模拟按键只能打进"
                     "本机前台窗口，跨机器打不到——自动截图会一直无效。请把本工具放到游戏所在的那台"
                     "电脑上运行（可在本机勾选「允许局域网访问」，再在别的设备上打开看地图）。" % game)
        else:
            self.shot_remote_label.configure(text="")

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
        self.startup.host = "0.0.0.0" if self.lan_var.get() else config.HOST_DEFAULT
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
        self.startup.host = "0.0.0.0" if self.lan_var.get() else config.HOST_DEFAULT
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
        text = "服务已就绪：" + self.startup.url
        if self.lan_var.get():
            server = getattr(self.startup, "server", None)
            port = server.server_address[1] if server is not None else self.startup.port
            lan = serve.url_for_lan(port)
            if lan:
                text += "   · 局域网：" + lan
        self.status.configure(text=text)
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
    parser = argparse.ArgumentParser(
        description="EFT 互动地图启动器（默认打开无边框独立窗口；--help 可见全部开关）",
        epilog="默认路径：EFTMap.exe → EFTMapDesktop.exe（独立窗口）。"
               "EFTMap.exe --server-only 仅作为桌面壳的后端启动器。")
    parser.add_argument("--host", default=DEFAULT_HOST, help="监听地址，默认 %s" % DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="监听端口，默认 %d" % DEFAULT_PORT)
    parser.add_argument("--screenshots", default=None, help="EFT 截图目录（实时定位用）")
    parser.add_argument("--game-dir", default=None, help="EFT 游戏目录（含 Logs，日志监控用）")
    parser.add_argument("--config-dir", default=None, help="配置与 sounds/ 的落盘目录，默认软件目录")
    parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器（调试/自动化）")
    parser.add_argument("--browser", action="store_true",
                        help="显式使用浏览器打开（高级用户；默认打开独立窗口）")
    parser.add_argument("--app-window", action="store_true",
                        help="浏览器 --app 模式（仅在 --browser 下生效）")
    parser.add_argument("--server-only", action="store_true",
                        help="桌面壳模式：只启动本地服务，不创建窗口、不打开浏览器（壳内部调用）")
    parser.add_argument("--shell-mode", action="store_true",
                        help="桌面壳模式：/api/overlay 不再拉起 overlay.py，由壳管理小浮窗")
    parser.add_argument("--runtime-file", default=None,
                        help="--server-only 就绪后写出的 runtime JSON 路径")
    parser.add_argument("--log-file", default=None,
                        help="--server-only 的后端日志路径")
    parser.add_argument("--parent-pid", type=int, default=None,
                        help="--server-only 监视的父进程 PID；父进程退出后自动收摊")
    parser.add_argument("--settings-only", action="store_true",
                        help="只打开 tkinter 高级设置窗口，不自动启动服务（供桌面壳托盘调用）")
    return parser.parse_args(argv)


def _say(text: str):
    """windowed 打包后 sys.stdout 可能为 None，打印前先确认。"""
    if sys.stdout is not None:
        print(text)


def harden_stdio() -> None:
    """把 stdout/stderr 统一成 UTF-8 + errors="replace"，启动最开始就做。

    windowed 产物没有控制台时这两个流可能是 None，argparse 的 `--help` 会直接
    往 stdout 写，None 就 AttributeError → PyInstaller 弹窗口版 traceback 对话框
    并挂住进程。这里先用 os.devnull 兜底（重定向输出时仍是真实的管道流），
    再统一编码；任何调整失败都不影响主流程。
    """
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        if stream is None:
            try:
                setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))
            except OSError:
                continue
            stream = getattr(sys, name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


def _log_tool_failure(script: str, detail: str) -> None:
    """把 `--run-tool` 的异常写进 %LOCALAPPDATA%\\EFTMap\\logs\\run-tool.log。

    windowed 产物没有控制台，`_say` 的输出直接进 devnull——截图识别宿主这类
    「随包脚本」一旦启动失败，用户只会看到「按热键没反应」，排查时没有任何线索。
    """
    base = os.environ.get("LOCALAPPDATA") or config.default_storage_dir()
    path = os.path.join(base, "EFTMap", "logs", "run-tool.log")
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write("[%s] %s\n%s\n\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), script, detail))
    except OSError:
        pass


def run_tool(argv) -> int:
    """打包产物内部隐藏入口：用当前（冻结的）解释器执行随包脚本。

    `sys.executable` 在 onedir 产物里是 EFTMap.exe，不能被当成 python 使用；
    serve.py 的后台抓取（live_prices.py / r20_fetch_prices.py）因此走
    `EFTMap.exe --run-tool <脚本> <原参数...>`，由这里 runpy 执行，退出码原样返回。
    不对用户暴露：不带 --run-tool 时行为与之前完全一致。
    """
    if not argv:
        return 2
    script, rest = argv[0], list(argv[1:])
    if not os.path.isfile(script):
        _say("找不到脚本：%s" % script)
        return 2
    # 抓取器会打印中文；windowed 产物里 stdout 可能继承到 cp1252 的控制台编码，
    # 直接 print 会抛 UnicodeEncodeError。这里统一成 UTF-8/replace，且不让
    # 异常冒泡到 PyInstaller 的“窗口版 traceback 对话框”（那会挂住子进程）。
    for stream in (sys.stdout, sys.stderr):
        try:
            if stream is not None and hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001 - 编码调整失败不影响抓取
            pass
    sys.argv = [script] + rest
    try:
        runpy.run_path(script, run_name="__main__")
    except SystemExit as exc:
        code = exc.code
        if code is None:
            return 0
        if isinstance(code, int):
            if code != 0:
                _log_tool_failure(script, "SystemExit(%d)" % code)
            return code
        _say(str(code))
        _log_tool_failure(script, "SystemExit: %s" % code)
        return 1
    except BaseException as exc:  # noqa: BLE001 - 后台子进程不能弹窗
        _say("%s: %s" % (type(exc).__name__, exc))
        import traceback
        _log_tool_failure(script, traceback.format_exc())
        return 1
    return 0


# ---------------------------------------------------------------- 桌面壳后端模式
def default_runtime_file() -> str:
    """桌面壳握手文件：优先 LOCALAPPDATA，避免写进漫游配置目录。"""
    local = os.environ.get("LOCALAPPDATA")
    base = os.path.join(local, "EFTMap") if local else config.default_storage_dir()
    return os.path.join(base, "run", "server-%d.json" % os.getpid())


def default_log_file() -> str:
    local = os.environ.get("LOCALAPPDATA")
    base = os.path.join(local, "EFTMap") if local else config.default_storage_dir()
    return os.path.join(base, "logs", "backend-%d.log" % os.getpid())


def _append_log(path: str | None, text: str) -> None:
    if not path:
        return
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write("%s  %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), text))
    except OSError:
        pass


def _atomic_write_json(path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def _safe_remove(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def _parent_alive(pid: int | None) -> bool:
    """父进程是否还活着。Job Object 是主保险；这个是壳被强杀时的第二道保险。"""
    if not pid:
        return True
    if os.name != "nt":
        try:
            os.kill(int(pid), 0)
            return True
        except OSError:
            return False
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x1000, False, int(pid))  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        code = ctypes.c_ulong()
        ok = kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
        kernel32.CloseHandle(handle)
        return bool(ok) and code.value == 259  # STILL_ACTIVE
    except Exception:  # noqa: BLE001 - 探测失败时宁可继续运行，不误杀后端
        return True


def run_server_only(args) -> int:
    """`--server-only`：无 Tk、无浏览器；写 runtime JSON，等壳调 shutdown 或父进程退出。"""
    runtime_path = os.path.abspath(args.runtime_file or default_runtime_file())
    log_path = os.path.abspath(args.log_file or default_log_file())
    token = secrets.token_urlsafe(24)
    stop_event = threading.Event()

    def log(text: str):
        _append_log(log_path, text)

    def on_step(step: str, state: str, detail: str = ""):
        log("[%s] %s %s" % (step, state, detail))

    cfg_dir = os.path.abspath(args.config_dir or config.default_storage_dir())
    if not args.config_dir:
        config.migrate_legacy(cfg_dir, config.app_dir())
    cfg = config.load(cfg_dir)
    game, shots = resolve_dirs(cfg, args.game_dir, args.screenshots)

    startup = Startup(
        port=args.port, host=args.host,
        screenshots=shots or None, game_dir=game or None,
        config_dir=cfg_dir,
        open_browser=lambda _url: None,
        on_step=on_step,
        shell_mode=bool(args.shell_mode),
        shutdown_token=token,
        shutdown_callback=stop_event.set,
    )
    log("server-only start pid=%d runtime=%s" % (os.getpid(), runtime_path))
    try:
        startup.run()
    except StartupError as exc:
        log("startup failed: %s %s" % (exc.message, exc.hint))
        _safe_remove(runtime_path)
        return 1
    except Exception as exc:  # noqa: BLE001 - 任何启动异常都必须落到日志里
        log("startup exception: %s: %s" % (type(exc).__name__, exc))
        _safe_remove(runtime_path)
        return 1

    port = startup.server.server_address[1]
    payload = {
        "app": serve.APP_ID,
        "version": serve.VERSION,
        "pid": os.getpid(),
        "port": port,
        "url": startup.url,
        "token": token,
        "shellMode": bool(args.shell_mode),
        "configDir": cfg_dir,
        "logFile": log_path,
        "startedAt": time.time(),
        "startedAtIso": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    try:
        _atomic_write_json(runtime_path, payload)
    except OSError as exc:
        log("写 runtime JSON 失败：%s" % exc)
        startup.stop()
        return 1
    log("ready url=%s pid=%d" % (startup.url, os.getpid()))

    try:
        while not stop_event.wait(0.5):
            if args.parent_pid and not _parent_alive(args.parent_pid):
                log("父进程 %s 已退出，后端收摊" % args.parent_pid)
                break
            if startup.thread is not None and not startup.thread.is_alive():
                log("服务线程已退出，后端收摊")
                break
    finally:
        startup.stop()
        _safe_remove(runtime_path)
        log("server-only exit pid=%d" % os.getpid())
    return 0


# ---------------------------------------------------------------- 卸载器双击入口
UNINSTALLER_EXE = "Uninstall.exe"
# 措辞按 `uninstall()` 的真实行为：整个安装目录被 rd /s /q 删除（默认安装目录里的
# 缓存也随目录一起没）；个人设置单独放在 %APPDATA%\EFTMap，不在删除范围内。
_UNINSTALL_QUESTION = (
    "确定要卸载《逃离塔科夫》互动地图吗？\n\n"
    "卸载将删除安装目录里的全部程序文件（含默认位置 %LOCALAPPDATA%\\EFTMap 的缓存）、"
    "开始菜单与桌面快捷方式，并移除「程序和功能」中的卸载项。\n"
    "个人设置保存在 %APPDATA%\\EFTMap，卸载后会保留。"
)
_UNINSTALL_SCRIPT_REL = (os.path.join("_internal", "tools", "installer.py"),
                         os.path.join("tools", "installer.py"))


def launched_as_uninstaller() -> bool:
    """双击 `Uninstall.exe` 等价调用：它是 EFTMap.exe 的副本，且没有任何参数。"""
    try:
        return os.path.basename(sys.executable).lower() == UNINSTALLER_EXE.lower()
    except (AttributeError, TypeError, ValueError):
        return False


def _message_box(text: str, title: str, flags: int) -> int:
    """原生消息框；windowed 产物没有控制台也能弹（纯 ctypes，无第三方依赖）。"""
    import ctypes
    try:
        return int(ctypes.windll.user32.MessageBoxW(None, text, title, flags))
    except (AttributeError, OSError):
        return 0


def uninstall_after_confirm() -> int:
    """双击 Uninstall.exe：先确认，选“是”才走与 `--uninstall --dir ...` 相同的卸载流程。

    选“否”（或弹框失败）静默返回 0：不打开启动器、不建任何 WebView 窗口。
    """
    install_dir = os.path.dirname(os.path.abspath(sys.executable))
    # MB_YESNO | MB_ICONQUESTION | MB_SETFOREGROUND：确认框置前，别被启动窗口盖住。
    reply = _message_box(_UNINSTALL_QUESTION, "EFT 互动地图 · 卸载", 0x4 | 0x20 | 0x10000)
    if reply != 6:  # IDYES=6；IDNO / 关闭 / 无法弹框一律按“取消”处理
        return 0
    script = ""
    for rel in _UNINSTALL_SCRIPT_REL:
        candidate = os.path.join(install_dir, rel)
        if os.path.isfile(candidate):
            script = candidate
            break
    if not script:
        _message_box("找不到卸载脚本，程序文件未删除。\n" + install_dir,
                     "EFT 互动地图 · 卸载失败", 0x10)
        return 1
    # 与「程序和功能」的 UninstallString 同一条路径：
    # EFTMap.exe --run-tool _internal/tools/installer.py --uninstall --dir <安装目录>
    return run_tool([script, "--uninstall", "--dir", install_dir])


# ---------------------------------------------------------------- 桌面壳优先入口（R71）
_DESKTOP_SHELL_EXE = "EFTMapDesktop.exe"


def desktop_shell_path() -> str:
    """按「安装目录 → 资源目录 → 开发目录」的顺序找桌面壳。"""
    exe_dir = os.path.dirname(os.path.abspath(sys.executable))
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidates = (
        os.path.join(exe_dir, _DESKTOP_SHELL_EXE),
        os.path.join(exe_dir, "_internal", _DESKTOP_SHELL_EXE),
        os.path.join(repo, "tools", "host", "bin", _DESKTOP_SHELL_EXE),
    )
    for path in candidates:
        if os.path.isfile(path):
            return path
    return ""


def launch_desktop_shell(args) -> int:
    """无参数 / 普通参数双击：交给桌面壳，浏览器不参与。

    壳已在跑时由壳自己的单实例 Mutex 激活旧窗口并退出，不会起第二份后端。
    """
    shell = desktop_shell_path()
    reason = ""
    if shell:
        cmd = [shell]
        if args.port is not None:
            cmd += ["--port", str(args.port)]
        if args.config_dir:
            cmd += ["--config-dir", os.path.abspath(args.config_dir)]
        try:
            # R75：壳是 winexe，正常不会建控制台；仍显式加 CREATE_NO_WINDOW，
            # 防止从 cmd / bat 里启动时把控制台句柄传给壳（那会多一个 cmd 窗口）。
            kwargs = {"cwd": os.path.dirname(shell), "close_fds": True}
            if os.name == "nt":
                kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            subprocess.Popen(cmd, **kwargs)
            _say("已启动独立窗口：%s" % shell)
            return 0
        except OSError as exc:
            reason = "独立窗口组件启动失败：%s" % exc
    else:
        reason = ("缺少独立窗口组件 %s。\n\n"
                  "它应与 EFTMap.exe 位于同一目录；安装不完整或被杀毒软件隔离时会缺失。\n"
                  "修复方法：重新运行安装包覆盖安装，或重新解压 Portable 包。") % _DESKTOP_SHELL_EXE
    _say(reason)
    # 壳不可用：先弹中文提示，用户明确选「是」才允许浏览器回退（绝不静默拉起浏览器）。
    # 0x4=是/否，0x20=问号图标，0x100=默认选「否」，0x10000=置顶。
    reply = _message_box(reason + "\n\n是否改用浏览器打开界面？",
                         "EFT 互动地图 · 独立窗口不可用", 0x4 | 0x20 | 0x100 | 0x10000)
    if reply == 6:  # IDYES
        return run_legacy_ui(args)
    return 1


def run_legacy_ui(args) -> int:
    """Tk 启动窗口路径：仅 `--settings-only` / `--browser` / 壳不可用回退时使用。"""
    startup = Startup(port=args.port, host=args.host, screenshots=args.screenshots,
                      game_dir=args.game_dir, config_dir=args.config_dir,
                      shell_mode=bool(args.shell_mode))
    if args.no_browser:
        startup.open_browser = lambda _url: None
    elif args.browser:
        if args.app_window or app_mode_enabled():
            startup.open_browser = open_app_window
        _say("显式 --browser：使用浏览器打开界面。")
    elif args.app_window or app_mode_enabled():
        startup.open_browser = open_app_window
    try:
        window = LaunchWindow(startup)
        if args.settings_only:
            window.auto_start_var.set(False)
            window.status.configure(text="高级设置模式：修改后关闭即可，不会自动启动服务。")
        elif args.browser:
            # 显式要浏览器：跳过手动点「启动 WebUI」，直接起服务并打开浏览器。
            window.auto_start_var.set(True)
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


def main(argv=None) -> int:
    harden_stdio()
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv and launched_as_uninstaller():
        return uninstall_after_confirm()
    if argv and argv[0] == "--run-tool":
        return run_tool(argv[1:])
    args = parse_args(argv)
    if args.server_only:
        return run_server_only(args)
    # 默认路径：独立窗口。只有显式开关或壳不可用（回退前会弹提示）才走 Tk/浏览器。
    if args.settings_only or args.browser or args.no_browser or args.app_window:
        return run_legacy_ui(args)
    return launch_desktop_shell(args)


if __name__ == "__main__":
    raise SystemExit(main())
