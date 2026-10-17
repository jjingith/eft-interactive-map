#!/usr/bin/env python3
"""EFT 互动地图 · 本地服务（运行期，仅 Python 标准库）

M1 职责：
- 用 ThreadingHTTPServer 托管项目根目录（index.html / style.css / app.js / data/ / assets/）；
- `GET /api/health` 供 launcher 自检（数据是否就绪、收录多少张图）；
- 端口占用时给出明确报错，不静默失败；
- 独立运行时自动打开浏览器，`--no-browser` 可关闭。

M2（T12）将在此之上追加 `/api/position` 与 `/events`(SSE) 以及截图目录监听线程；
本文件的静态托管与 API 分发结构已按“可扩展”写，届时只需扩充 Handler 与 start()。

不用 UC 头、不联网、不读游戏进程：服务只服务本仓库内已有的文件。
"""

from __future__ import annotations

import argparse
import errno
import json
import os
import sys
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

VERSION = "0.1.0"
APP_ID = "eft-interactive-map"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8787

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


def build_handler(root: str):
    """构造静态文件 Handler，并把 /api/ 前缀留给 JSON 接口。"""

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
                return self._send_json(200, health_payload(root))
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

    return Handler


def health_payload(root: str) -> dict[str, Any]:
    status = data_status(root)
    return {
        "ok": bool(status["ready"]),
        "app": APP_ID,
        "version": VERSION,
        "root": root,
        "data": status,
        "position": False,   # M2 接入实时定位后置 True
    }


class _Server(ThreadingHTTPServer):
    """禁用地址复用：Windows 下 SO_REUSEADDR 会让端口占用检测失效。"""

    daemon_threads = True
    allow_reuse_address = False


def create_server(port: int = DEFAULT_PORT, host: str = DEFAULT_HOST, root: str | None = None) -> ThreadingHTTPServer:
    """创建（已 listen 的）HTTP 服务对象。port=0 表示由系统分配空闲端口，便于测试。"""
    root = os.path.abspath(root or ROOT)
    if not os.path.isfile(os.path.join(root, "index.html")):
        raise FileNotFoundError("根目录里找不到 index.html：%s\n请用 --root 指向仓库根目录。" % root)

    handler = build_handler(root)
    try:
        httpd = _Server((host, port), handler)
    except OSError as exc:
        if _is_addr_in_use(exc):
            raise PortInUseError(
                "端口 %d 已被占用。请关闭占用该端口的程序，或用 --port 换一个端口（如 --port 8788）。" % port
            ) from exc
        raise
    return httpd


def url_for(host: str, port: int) -> str:
    shown = "127.0.0.1" if host in ("", "0.0.0.0") else host
    return "http://%s:%d/" % (shown, port)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="EFT 互动地图本地服务（静态站点 + 健康检查）")
    parser.add_argument("--host", default=DEFAULT_HOST, help="监听地址，默认 %s（仅本机可访问）" % DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="监听端口，默认 %d；0 表示自动分配" % DEFAULT_PORT)
    parser.add_argument("--root", default=None, help="站点根目录，默认仓库根目录")
    parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        httpd = create_server(args.port, args.host, args.root)
    except PortInUseError as exc:
        print("[错误] %s" % exc, file=sys.stderr)
        return 2
    except FileNotFoundError as exc:
        print("[错误] %s" % exc, file=sys.stderr)
        return 3

    url = url_for(args.host, httpd.server_address[1])
    print("EFT 互动地图已启动：%s" % url)
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
