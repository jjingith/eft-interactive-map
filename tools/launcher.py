#!/usr/bin/env python3
"""EFT 互动地图 · 启动器（运行期入口 → EFTMap.exe）

双击 exe 后：显示一个 Windows XP（Luna）简约风的启动框 → 依次执行
「检查数据 → 启动本地服务 → 载入资源（自检）→ 打开浏览器」四步，
每步在框内显示进度与状态文字；跑完后自动打开浏览器进入 Web UI。

设计上刻意把「编排」与「界面」分离：
- `Startup` 是纯逻辑编排，依赖（起服务/自检/开浏览器）全部可注入 → 可单测，不需要弹窗；
- `LaunchWindow` 只用 tkinter 做呈现，不搞业务判断。

与 serve.py 的关系：launcher 是入口与界面壳，serve.py 是可被调用的服务模块
（同时也保留独立 CLI 便于调试）。全程不联网、不读游戏进程。
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import sys
import threading
import time
import urllib.request
import webbrowser
from typing import Any, Callable

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


class StartupError(RuntimeError):
    """某一步失败。带 step（哪一步）与 hint（用户接下来该做什么）。"""

    def __init__(self, step: str, message: str, hint: str = ""):
        super().__init__(message)
        self.step = step
        self.message = message
        self.hint = hint


def app_root() -> str:
    """站点根目录：打包后取 PyInstaller 的资源目录，直接运行时取仓库根目录。"""
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.executable)))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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
        screenshots: str | None = None,   # M2 接入截图目录监听时交给 serve
        create_server: Callable[..., Any] = serve.create_server,
        open_browser: Callable[[str], Any] = webbrowser.open,
        health: Callable[[str], dict] = check_health,
        on_step: Callable[[str, str, str], None] | None = None,
    ):
        self.root = os.path.abspath(root or app_root())
        self.port = port
        self.host = host
        self.screenshots = screenshots
        self.create_server = create_server
        self.open_browser = open_browser
        self.health = health
        self.on_step = on_step

        self.server = None
        self.thread: threading.Thread | None = None
        self.url = ""
        self.health_payload: dict[str, Any] | None = None
        self.screenshots_resolved: str | None = None

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
        # 未显式指定截图目录时自动探测默认位置；目录不存在就不启动监听（不报错）
        screenshots = self.screenshots
        if screenshots is None:
            default = serve.default_screenshots_dir()
            screenshots = default if os.path.isdir(default) else None
        self.screenshots_resolved = screenshots
        try:
            self.server = self.create_server(self.port, self.host, self.root, screenshots=screenshots)
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
        # health 的 position 表示「监听是否已开启」，positionAvailable 表示「已解析到位置」
        if not self.health_payload.get("position"):
            position = "实时定位未开启（未找到截图目录）"
        elif self.health_payload.get("positionAvailable"):
            position = "实时定位已开启"
        else:
            position = "实时定位已开启，等待首张截图"
        self._emit(STEP_SELFCHECK, "done", "版本 %s · %s" % (self.health_payload.get("version", VERSION), position))

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


# ---------------------------------------------------------------- XP(Luna) 风启动框
FACE = "#ECE9D8"        # XP 对话框底色
TITLE_A = (0x00, 0x5A, 0xE6)
TITLE_B = (0x3D, 0x9C, 0xF5)
GREEN = "#06B025"       # XP 进度条绿
SUNKEN_DARK = "#808080"
SUNKEN_LIGHT = "#FFFFFF"


class LaunchWindow:
    """tkinter 壳：把 Startup 的进度画出来，并提供「打开界面/最小化/退出」。"""

    W, H = 460, 306

    def __init__(self, startup: Startup):
        import tkinter as tk

        self.tk = tk
        self.startup = startup
        self.events: queue.Queue = queue.Queue()
        self.step_widgets: dict[str, tuple[Any, Any]] = {}
        self.states: dict[str, str] = {step: "pending" for step, _ in STEPS}
        self.progress = 0.0
        self.failed = False

        self.root = tk.Tk()
        self.root.title("EFT 互动地图")
        self.root.resizable(False, False)
        self.root.configure(bg=FACE)
        self.root.protocol("WM_DELETE_WINDOW", self.quit)

        self._center()
        self._build_header()
        self._build_body()
        self._build_buttons()

        self.startup.on_step = lambda step, state, detail: self.events.put((step, state, detail))
        self.root.after(60, self._pump)

    # ------------------------------------------------------------ 布局
    def _center(self):
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = max(0, (sw - self.W) // 2)
        y = max(0, (sh - self.H) // 3)
        self.root.geometry("%dx%d+%d+%d" % (self.W, self.H, x, y))

    def _build_header(self):
        tk = self.tk
        canvas = tk.Canvas(self.root, width=self.W, height=30, highlightthickness=0, bd=0)
        canvas.pack(fill="x")
        for i in range(30):
            t = i / 29.0
            color = "#%02x%02x%02x" % tuple(round(a + (b - a) * t) for a, b in zip(TITLE_A, TITLE_B))
            canvas.create_line(0, i, self.W, i, fill=color)
        self.title_text = canvas.create_text(
            9, 15, anchor="w", text="EFT 互动地图 · 正在启动", fill="white", font=("Tahoma", 9, "bold")
        )
        # XP 风格关闭按钮（红底白叉）
        canvas.create_rectangle(self.W - 27, 6, self.W - 7, 24, fill="#D25A2E", outline="#B34A22")
        canvas.create_line(self.W - 22, 11, self.W - 12, 20, fill="white", width=2)
        canvas.create_line(self.W - 12, 11, self.W - 22, 20, fill="white", width=2)
        canvas.tag_bind(canvas.create_rectangle(self.W - 27, 4, self.W - 5, 26, fill="", outline=""),
                        "<Button-1>", lambda _ev: self.quit())
        self.header = canvas

    def _build_body(self):
        tk = self.tk
        body = tk.Frame(self.root, bg=FACE)
        body.pack(fill="both", expand=True, padx=14, pady=(12, 0))

        tk.Label(body, text="本地服务准备中，请稍候…", bg=FACE, font=("Tahoma", 9, "bold")).pack(anchor="w")
        tk.Label(body, text="全程离线运行，与游戏进程零交互。", bg=FACE, fg="#4A4A4A",
                 font=("Tahoma", 8)).pack(anchor="w", pady=(1, 8))

        steps = tk.Frame(body, bg=FACE)
        steps.pack(fill="x")
        for step, label in STEPS:
            row = tk.Frame(steps, bg=FACE)
            row.pack(fill="x", pady=1)
            icon = tk.Label(row, text=STATE_ICON["pending"], width=2, bg=FACE,
                            fg=STATE_COLOR["pending"], font=("Tahoma", 10, "bold"))
            icon.pack(side="left")
            tk.Label(row, text=label, width=12, anchor="w", bg=FACE,
                     font=("Tahoma", 9)).pack(side="left")
            detail = tk.Label(row, text="", anchor="w", bg=FACE, fg="#4A4A4A", font=("Tahoma", 8))
            detail.pack(side="left", fill="x", expand=True)
            self.step_widgets[step] = (icon, detail)

        self.bar = tk.Canvas(body, width=self.W - 28, height=20, highlightthickness=0, bd=0, bg=FACE)
        self.bar.pack(pady=(12, 2))
        self.status = tk.Label(body, text="", bg=FACE, fg="#4A4A4A", font=("Tahoma", 8), anchor="w")
        self.status.pack(fill="x")

        self.message = tk.Message(body, text="", width=self.W - 32, bg=FACE, fg="#C00000",
                                  font=("Tahoma", 8), justify="left")
        self.message.pack(fill="x", pady=(4, 0))
        self._draw_bar()

    def _build_buttons(self):
        tk = self.tk
        row = tk.Frame(self.root, bg=FACE)
        row.pack(fill="x", padx=14, pady=(6, 12))

        def mk(text, command, state="normal"):
            btn = tk.Button(row, text=text, command=command, state=state, font=("Tahoma", 9),
                            bg=FACE, activebackground=FACE, relief="raised", bd=2, padx=12, pady=2)
            btn.pack(side="right", padx=(6, 0))
            return btn

        self.btn_exit = mk("退出", self.quit)
        self.btn_min = mk("最小化", self.root.iconify, state="disabled")
        self.btn_open = mk("打开界面", self.open_ui, state="disabled")
        self.btn_retry = mk("重试", self.retry, state="disabled")
        self.btn_retry.pack_forget()   # 默认隐藏，失败时才换出来

    # ------------------------------------------------------------ 绘制
    def _draw_bar(self):
        c, w, h = self.bar, self.W - 28, 20
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
        """把工作线程投递的进度事件画到界面上（tkinter 只能在主线程动控件）。"""
        try:
            while True:
                step, state, detail = self.events.get_nowait()
                self._apply(step, state, detail)
        except queue.Empty:
            pass
        if not self.failed:
            self.root.after(60, self._pump)

    def _apply(self, step, state, detail):
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
            self.status.configure(text="启动失败")
            self.message.configure(text=detail)
            self.btn_open.configure(state="disabled")
            self.btn_retry.pack(side="right", padx=(6, 0))
            self.btn_retry.configure(state="normal")
            self.header.itemconfigure(self.title_text, text="EFT 互动地图 · 启动失败")

    def _worker(self):
        try:
            self.startup.run()
        except StartupError as exc:
            text = exc.message + ("\n建议：" + exc.hint if exc.hint else "")
            self.events.put((exc.step, "failed", text))
        except Exception as exc:  # 兜底：未预期异常也要落在界面上，不静默
            self.events.put((STEPS[-1][0], "failed", "未预期的错误：%s" % exc))

    def start(self):
        threading.Thread(target=self._worker, daemon=True).start()

    def open_ui(self):
        if self.startup.url:
            webbrowser.open(self.startup.url)

    def retry(self):
        self.failed = False
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
        self.root.after(60, self._pump)
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
        self.status.configure(text="服务已就绪：" + self.startup.url)
        self.header.itemconfigure(self.title_text, text="EFT 互动地图 · 已就绪")
        self.btn_open.configure(state="normal")
        self.btn_min.configure(state="normal")
        self.btn_retry.pack_forget()

    def quit(self):
        try:
            self.startup.stop()
        finally:
            self.root.destroy()

    def run(self) -> int:
        self.start()

        def watch():
            """四步全 done 就把窗口切到「已就绪」（进度事件只负责画步骤行）。"""
            if self.failed or self.states.get("__ready__"):
                return
            if all(self.states[step] == "done" for step, _ in STEPS):
                self.states["__ready__"] = "done"
                self.on_ready()
                return
            self.root.after(80, watch)

        self.root.after(80, watch)
        self.root.mainloop()
        return 0


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="EFT 互动地图启动器")
    parser.add_argument("--host", default=DEFAULT_HOST, help="监听地址，默认 %s" % DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="监听端口，默认 %d" % DEFAULT_PORT)
    parser.add_argument("--screenshots", default=None, help="EFT 截图目录（M2 实时定位用）")
    parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器（调试/自动化）")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    startup = Startup(port=args.port, host=args.host, screenshots=args.screenshots)
    if args.no_browser:
        startup.open_browser = lambda _url: None
    try:
        window = LaunchWindow(startup)
    except Exception as exc:  # 没有图形环境时退化为纯控制台启动，避免完全不可用
        _say("无法创建启动窗口（%s），改为无界面启动。" % exc)
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


def _say(text: str):
    """windowed 打包后 sys.stdout 可能为 None，打印前先确认。"""
    if sys.stdout is not None:
        print(text)


if __name__ == "__main__":
    raise SystemExit(main())
