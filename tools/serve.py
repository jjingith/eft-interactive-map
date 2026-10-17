#!/usr/bin/env python3
"""EFT 互动地图 · 本地服务（运行期，仅 Python 标准库）

职责：
- 用 ThreadingHTTPServer 托管项目根目录（index.html / style.css / app.js / data/ / assets/）；
- `GET /api/health` 供 launcher 自检（数据是否就绪、收录多少张图、实时定位是否可用）；
- `GET /api/position` 返回最近一次解析到的玩家位置（截图目录不可用时降级为 available=false）；
- `GET /events` 用 SSE 把位置变更实时推给页面（目录监听线程只在**位置真的变了**才广播）；
- 端口占用时给出明确报错，不静默失败；
- 独立运行时自动打开浏览器，`--no-browser` 可关闭。

不联网、不读游戏进程：定位来源是**截图文件名里的坐标**（见 screenshot.py），
只读文件名与文件时间戳。
"""

from __future__ import annotations

import argparse
import errno
import json
import os
import queue
import sys
import threading
import time
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import screenshot

VERSION = "0.1.0"
APP_ID = "eft-interactive-map"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8787
DEFAULT_POLL = 1.0        # 截图目录轮询间隔（秒）
SSE_HEARTBEAT = 15.0      # SSE 心跳间隔（秒），防止连接被中间层掐掉

# 仓库根目录（tools/ 的上一级）
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Windows 的 WSAEADDRINUSE
_WSAEADDRINUSE = 10048

# 标准库在 Windows 上可能把 .svg/.json 猜错，这里显式纠正
EXTRA_TYPES = {
    ".svg": "image/svg+xml",
    ".json": "application/json; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".html": "text/html; charset=utf-8",
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


class Broadcaster:
    """SSE 订阅者注册表：把新位置推给所有在线页面。

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
        with self._lock:
            subs = list(self._subs)
        for q in subs:
            try:
                q.put_nowait(payload)
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


def build_handler(root: str, tracker: PositionTracker):
    """构造静态文件 Handler，并把 /api/ 前缀留给 JSON 接口与 SSE。"""

    class Handler(SimpleHTTPRequestHandler):
        server_version = "EFTMap/%s" % VERSION
        protocol_version = "HTTP/1.1"
        extensions_map = dict(SimpleHTTPRequestHandler.extensions_map, **EXTRA_TYPES)

        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=root, **kwargs)

        # 本地单机服务，逐请求一行日志只是噪音
        def log_message(self, fmt, *args):  # noqa: A003 - 覆盖标准库签名
            pass

        def do_GET(self):  # noqa: N802 - 覆盖标准库签名
            path = self.path.split("?", 1)[0].split("#", 1)[0]
            if path == "/api/health":
                return self._send_json(200, health_payload(root, tracker))
            if path == "/api/position":
                return self._send_json(200, tracker.snapshot())
            if path == "/events":
                return self._serve_events()
            if path.startswith("/api/"):
                return self._send_json(404, {"ok": False, "error": "未知接口：%s" % path})
            return super().do_GET()

        def _send_json(self, code: int, payload: dict):
            body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _serve_events(self):
            """SSE：连上先推当前状态，之后位置一变就推，另加心跳注释保持连接。

            无 Content-Length，因此按 HTTP/1.1 规范用 `Connection: close` 把「流到连接关闭为止」
            表达清楚（不能用 chunked，标准库的分块编码会把每帧再包一层长度前缀）。
            """
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()

            q = tracker.broadcaster.subscribe()
            try:
                self._write_frame(tracker.snapshot())
                last_beat = time.monotonic()
                while True:
                    try:
                        payload = q.get(timeout=1.0)
                        self._write_frame(payload)
                    except queue.Empty:
                        pass
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

    return Handler


def health_payload(root: str, tracker: PositionTracker | None = None) -> dict[str, Any]:
    status = data_status(root)
    payload = {
        "ok": bool(status["ready"]),
        "app": APP_ID,
        "version": VERSION,
        "root": root,
        "data": status,
        "position": bool(tracker and tracker.enabled()),
    }
    if tracker is not None:
        snap = tracker.snapshot()
        payload["positionAvailable"] = snap["available"]
        payload["screenshots"] = tracker.directory
    return payload


class _Server(ThreadingHTTPServer):
    """禁用地址复用：Windows 下 SO_REUSEADDR 会让端口占用检测失效。"""

    daemon_threads = True
    allow_reuse_address = False

    def server_close(self):
        # 关闭服务时一并停掉截图目录监听线程，避免残留轮询
        tracker = getattr(self, "tracker", None)
        if tracker is not None:
            tracker.stop()
        super().server_close()


def create_server(port: int = DEFAULT_PORT, host: str = DEFAULT_HOST, root: str | None = None,
                  screenshots: str | None = None, poll_interval: float = DEFAULT_POLL) -> ThreadingHTTPServer:
    """创建（已 listen 的）HTTP 服务对象。

    port=0 表示由系统分配空闲端口，便于测试。
    `screenshots=None` 表示**不开启**实时定位（测试与无定位场景走这条路）；
    传入目录才启动监听线程。
    """
    root = os.path.abspath(root or ROOT)
    if not os.path.isfile(os.path.join(root, "index.html")):
        raise FileNotFoundError("根目录里找不到 index.html：%s\n请用 --root 指向仓库根目录。" % root)

    tracker = PositionTracker(screenshots, poll_interval)
    handler = build_handler(root, tracker)
    try:
        httpd = _Server((host, port), handler)
    except OSError as exc:
        if _is_addr_in_use(exc):
            raise PortInUseError(
                "端口 %d 已被占用。请关闭占用该端口的程序，或用 --port 换一个端口（如 --port 8788）。" % port
            ) from exc
        raise
    httpd.tracker = tracker     # type: ignore[attr-defined]
    tracker.start()
    return httpd


def url_for(host: str, port: int) -> str:
    shown = "127.0.0.1" if host in ("", "0.0.0.0") else host
    return "http://%s:%d/" % (shown, port)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="EFT 互动地图本地服务（静态站点 + 健康检查 + 实时定位）")
    parser.add_argument("--host", default=DEFAULT_HOST, help="监听地址，默认 %s（仅本机可访问）" % DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="监听端口，默认 %d；0 表示自动分配" % DEFAULT_PORT)
    parser.add_argument("--root", default=None, help="站点根目录，默认仓库根目录")
    parser.add_argument("--screenshots", default=None,
                        help="EFT 截图目录；不给则用默认位置 %s" % default_screenshots_dir())
    parser.add_argument("--no-position", action="store_true", help="关闭实时定位（不监听截图目录）")
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


def main(argv=None) -> int:
    args = parse_args(argv)
    screenshots = resolve_screenshots(args)
    try:
        httpd = create_server(args.port, args.host, args.root, screenshots=screenshots)
    except PortInUseError as exc:
        print("[错误] %s" % exc, file=sys.stderr)
        return 2
    except FileNotFoundError as exc:
        print("[错误] %s" % exc, file=sys.stderr)
        return 3

    url = url_for(args.host, httpd.server_address[1])
    print("EFT 互动地图已启动：%s" % url)
    if screenshots:
        print("实时定位：监听截图目录 %s" % screenshots)
    else:
        print("实时定位：未开启（截图目录不可用或已用 --no-position 关闭）")
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
