# -*- coding: utf-8 -*-
"""R238：QQ 式截图识别工作流（热键宿主 / 冻结帧 / 原位浮窗）。

用户原话（2026-11-11 16:00）：
  「能否做成和qq截图一样 按用户设置的快捷键 然后框选要识别的地方 然后再进行识别
    还会然后识别的结果和小地图一样 以浮窗结果显示 就显示在框选的位置
    显示整体价格和每格价格以及每公斤价格 然后在浮窗右上角有关闭键 和切换价格的键
    点击后在最新价格 24小时均价 72小时均价 30天均价直接切换」
"""

import os
import sys

import pytest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TEST_DIR)
TOOLS = os.path.join(ROOT, "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

# ---------------------------------------------------------------- 冻结帧端点（HTTP 级）

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


def _post_frame(port, data: bytes):
    import urllib.request

    req = urllib.request.Request("http://127.0.0.1:%d/api/ocr/frame" % port, data=data,
                                 headers={"Content-Type": "application/octet-stream"},
                                 method="POST")
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=15) as r:
        import json

        return json.loads(r.read().decode("utf-8"))


def _get_frame(port, fid: str):
    import urllib.request

    url = "http://127.0.0.1:%d/api/ocr/frame?id=%s" % (port, fid)
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(url, timeout=15) as r:
        return r.read()


def test_frame_roundtrip(server):
    port, _srv = server
    doc = _post_frame(port, b"\x89PNG\r\n\x1a\n-fake-frame")
    assert doc["ok"] and doc["id"]
    assert _get_frame(port, doc["id"]) == b"\x89PNG\r\n\x1a\n-fake-frame"


def test_frame_bad_id_404(server):
    import urllib.error
    import urllib.request

    port, _srv = server
    _post_frame(port, b"x")
    with pytest.raises(urllib.error.HTTPError) as ei:
        urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
            "http://127.0.0.1:%d/api/ocr/frame?id=nope" % port, timeout=15)
    assert ei.value.code == 404


def test_frame_single_slot_and_ttl(server):
    """内存里只留最近一帧（新帧覆盖旧 id），过期取不到。"""
    import time

    import serve

    port, _srv = server
    d1 = _post_frame(port, b"frame-1")
    d2 = _post_frame(port, b"frame-2")
    assert d1["id"] != d2["id"]
    with pytest.raises(Exception):
        _get_frame(port, d1["id"])  # 旧帧被覆盖
    assert _get_frame(port, d2["id"]) == b"frame-2"
    # TTL 过期
    serve._OCR_FRAME["at"] = time.time() - serve._OCR_FRAME_TTL - 1
    with pytest.raises(Exception):
        _get_frame(port, d2["id"])


# ---------------------------------------------------------------- recognize 多窗口价格（静态契约）

def test_recognize_has_price_windows_and_weight():
    src = open(os.path.join(TOOLS, "serve.py"), encoding="utf-8").read()
    assert "MAX_OCR_FRAME_BODY" in src and "48 * 1024 * 1024" in src
    # R248：3 天 / 30 天合并成一次 30 天序列 + 本地按时间戳切 72h（gz 只解压一遍）
    assert "price_history.series(root, mode, match_ids, days=30)" in src
    assert 'cutoff3 = ' in src and '"w72"' in src and '"w30d"' in src
    # R258：历史窗口在 _ocr_resolve_price 里按 hist_row 读取
    assert '"w72": (hist_row or {}).get("w72")' in src
    assert '"weight": rec.get("w")' in src


def test_price_history_series_supports_windows():
    """72h=3 天 / 30d=30 天：price_history.series 的 days 参数语义。"""
    sys.path.insert(0, TOOLS)
    import price_history

    assert hasattr(price_history, "series")
    src = open(os.path.join(TOOLS, "price_history.py"), encoding="utf-8").read()
    assert "days: int = 7" in src


# ---------------------------------------------------------------- scan.py / scan.html 契约

def test_scan_host_contract():
    src = open(os.path.join(TOOLS, "scan.py"), encoding="utf-8").read()
    assert "DEFAULT_HOTKEY = \"ctrl+alt+p\"" in src
    assert "ImageGrab.grab()" in src
    assert 'SCAN_TITLE_CLOSED = "EFT截图·关闭"' in src
    assert "ocrScan" in src and '"hotkey"' in src        # 配置可覆盖热键
    assert "RegisterHotKey" in src and "WM_HOTKEY" in src
    assert "post_frame(server, frame)" in src             # 冻结帧先上传再开窗


def test_scan_page_contract():
    html = open(os.path.join(ROOT, "scan.html"), encoding="utf-8").read()
    # R239：页内不再渲染结果面板——识别成功后交接宿主开透明浮窗
    for text in ("autotest", "scaleFactors", "EFT截图·关闭", "EFT截图·完成",
                 "/api/ocr/overlay/state", "matches"):
        assert text in html, "scan.html 缺 %s" % text
    assert "id=\"panel\"" not in html, "R239 起结果面板已移除（改为透明浮窗交接）"
    # 裁剪按 X/Y 各自比例（窗口与帧尺寸不一致时不错位）
    assert "sy:" in html


def test_hotkey_parsing_matches_overlay():
    """scan.py 复用 overlay.parse_hotkey；'ctrl+alt+p' 必须解析成功。"""
    sys.path.insert(0, TOOLS)
    import overlay

    hk = overlay.parse_hotkey("ctrl+alt+p")
    assert hk is not None and len(hk) == 2
