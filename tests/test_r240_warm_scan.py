# -*- coding: utf-8 -*-
"""R240：QQ 式速度（保温窗口 + BMP 冻结帧 + 页面轮询换帧）。

用户反馈（2026-11-11 17:11）：
  「现在按截图键 没有qq截图那样快 而且窗口什么都会动一下」

三个根因：①每次热键都拉起浏览器进程 + 等页面；②整屏 PNG 编码数百毫秒；
③窗口先带标题栏出现→剥样式→挪位置（可见的「动一下」）。
R240：帧改 BMP（免压缩）、窗口保温（隐藏不销毁，唤醒 ≤150ms 换帧）、
冷启动在 -32000 屏幕外完成剥样式/定位/缩放再入场。
"""

import os
import sys

import pytest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TEST_DIR)
TOOLS = os.path.join(ROOT, "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

sys.path.insert(0, TOOLS)
import scan  # noqa: E402

# ---------------------------------------------------------------- 帧格式嗅探 / 元信息端点


@pytest.fixture()
def server(tmp_path):
    sys.path.insert(0, TOOLS)
    import serve

    srv = serve.create_server(port=0, root=str(ROOT), screenshots=None,
                              config_dir=str(tmp_path))
    port = srv.server_address[1]
    th = __import__("threading").Thread(target=srv.serve_forever, daemon=True)
    th.start()
    yield port, srv
    srv.shutdown()


def _raw(port, path, data=None, method=None):
    import urllib.request

    req = urllib.request.Request("http://127.0.0.1:%d%s" % (port, path), data=data,
                                 headers={"Content-Type": "application/octet-stream"},
                                 method=method or ("POST" if data else "GET"))
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with op.open(req, timeout=15) as r:
            return r.status, r.headers.get("Content-Type"), r.read()
    except urllib.error.HTTPError as e:
        return e.code, None, e.read()


def _json(port, path, payload=None):
    import json
    import urllib.request

    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request("http://127.0.0.1:%d%s" % (port, path), data=data,
                                 headers={"Content-Type": "application/json"},
                                 method="POST" if data else "GET")
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with op.open(req, timeout=15) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


def _reset_frame():
    """_OCR_FRAME 是 serve 模块级全局（同进程各测试共享），先清干净。"""
    import serve

    serve._OCR_FRAME.update({"id": None, "bytes": None, "at": 0.0, "fmt": "png"})


def test_frame_bmp_sniff_and_content_type(server):
    import json

    port, _srv = server
    _reset_frame()
    st, _ct, body = _raw(port, "/api/ocr/frame", b"BM-fake-bmp")
    assert st == 200
    fid = json.loads(body.decode())["id"]
    st, ct, body2 = _raw(port, "/api/ocr/frame?id=" + fid)
    assert st == 200 and ct == "image/bmp" and body2 == b"BM-fake-bmp"
    # PNG 魔数仍走 image/png
    st, _ct, body3 = _raw(port, "/api/ocr/frame", b"\x89PNG\r\n\x1a\n-x")
    fid2 = json.loads(body3.decode())["id"]
    st, ct2, _ = _raw(port, "/api/ocr/frame?id=" + fid2)
    assert ct2 == "image/png"


def test_frame_meta_endpoint(server):
    """GET 不带 id → 元信息（页面轮询换帧用）。空/过期 → id=None。"""
    port, _srv = server
    _reset_frame()
    st, d = _json(port, "/api/ocr/frame")
    assert st == 200 and d["ok"] is True and d["id"] is None
    _raw(port, "/api/ocr/frame", b"BM-meta-test")
    st, d = _json(port, "/api/ocr/frame")
    assert st == 200 and d["ok"] is True and d["id"] and d["fmt"] == "bmp"


def test_frame_bad_id_still_404(server):
    port, _srv = server
    _raw(port, "/api/ocr/frame", b"BM-x")
    st, _ct, _body = _raw(port, "/api/ocr/frame?id=nope")
    assert st == 404


def test_overlay_state_has_ts(server):
    """交接态带 ts——宿主用它防「重开窗口读到上一轮完成标题」的竞态。"""
    port, _srv = server
    st, d = _json(port, "/api/ocr/overlay/state",
                  {"region": {"x": 0, "y": 0, "w": 10, "h": 10}, "matches": []})
    assert st == 200
    st, d = _json(port, "/api/ocr/overlay/state")
    assert isinstance(d.get("ts"), float) and d["ts"] > 0


# ---------------------------------------------------------------- 契约

def test_scan_host_warm_contract():
    src = open(os.path.join(TOOLS, "scan.py"), encoding="utf-8").read()
    assert 'img.save(buf, "BMP")' in src                      # 冻结帧免压缩编码
    assert "-32000" in src                                    # 冷启动屏幕外入场
    assert "def show_selection" in src and "def hide_selection" in src
    assert '"phase"' in src and "shown_at" in src             # 保温状态机 + ts 防竞态
    assert "overlay.restore_focus(fg)" in src                 # 隐藏时还焦点给游戏
    # 保留 R238 契约
    assert 'SCAN_TITLE_CLOSED = "EFT截图·关闭"' in src
    assert "post_frame(server, frame)" in src
    assert "ImageGrab.grab()" in src


def test_scan_page_poll_contract():
    html = open(os.path.join(ROOT, "scan.html"), encoding="utf-8").read()
    assert "visibilitychange" in html                         # 唤醒立即拉帧
    assert "document.hidden ? 800 : 150" in html              # 可见快轮询/隐藏节流
    assert "function startNewScan" in html and "resetIdle" in html
    assert '"/api/ocr/frame"' in html                         # 轮询元信息换帧
    assert "window.close" not in html, "R240 起页面绝不自行关闭窗口（宿主隐藏保温）"
    # 保留 R238/R239 契约
    for text in ("EFT截图·关闭", "EFT截图·完成", "/api/ocr/overlay/state",
                 "{ region: ir, matches: matches }", "autotest", "sy:"):
        assert text in html, "scan.html 缺 %s" % text


# ---------------------------------------------------------------- 纯函数回归（防改坏）

def test_fmt_short_and_price_views_still_work():
    assert scan.fmt_short(431400) == "431,400 ₽"
    m = {"price": {"lastLow": 12600}, "gw": 1, "gh": 2, "weight": 0.45}
    main, slot, kg = scan.price_views(m, "last")
    assert main == "12,600 ₽" and slot == "6,300 ₽" and kg == "28,000 ₽"
