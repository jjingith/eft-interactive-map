# -*- coding: utf-8 -*-
"""R239：透明价格浮窗（用户纠偏：浮窗要像小地图——透明背景、只显示价格文字、
价格直接叠在对应装备上、不影响游戏操作；不再用浏览器交互面板）。

架构：scan.html 交接 → BFF /api/ocr/overlay/state → 宿主开原生分层窗口：
  · 标签窗 UpdateLayeredWindow 逐像素透明 + WS_EX_TRANSPARENT 全穿透；
  · 控制条窗独立小窗，仅 ✕/口径按钮可点（WM_NCHITTEST 按钮外穿透）。
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
import scan  # noqa: E402  纯函数部分无 Win32 依赖

# ---------------------------------------------------------------- BFF 交接态端点

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


def _req_json(port, path, payload=None):
    import json
    import urllib.request

    if payload is None:
        req = urllib.request.Request("http://127.0.0.1:%d%s" % (port, path))
    else:
        req = urllib.request.Request("http://127.0.0.1:%d%s" % (port, path),
                                     data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"},
                                     method="POST")
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with op.open(req, timeout=15) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


_MATCH = {"id": "abc", "name": "工厂紧急出口钥匙", "text": "工厂紧急出口钥匙",
          "tier": "精确", "ocrScore": 0.98, "x": 40, "y": 40, "w": 180, "h": 30,
          "gw": 1, "gh": 1, "weight": 0.01, "price": {"lastLow": 431400},
          "junk": {"should": "be dropped"}}


def _reset_overlay():
    """_OCR_OVERLAY 是 serve 模块级全局（同进程各测试文件共享），先清干净。"""
    import serve

    serve._OCR_OVERLAY.update({"ts": 0.0, "region": None, "matches": []})


def test_overlay_state_roundtrip(server):
    port, _srv = server
    _reset_overlay()
    st, d = _req_json(port, "/api/ocr/overlay/state")
    assert st == 200 and d["active"] is False and d["matches"] == []

    st, d = _req_json(port, "/api/ocr/overlay/state",
                      {"region": {"x": 10, "y": 20, "w": 300, "h": 200},
                       "matches": [_MATCH]})
    assert st == 200 and d["ok"] and d["count"] == 1

    st, d = _req_json(port, "/api/ocr/overlay/state")
    assert st == 200 and d["active"] is True
    assert d["region"] == {"x": 10, "y": 20, "w": 300, "h": 200}
    m = d["matches"][0]
    assert m["name"] == "工厂紧急出口钥匙" and m["price"]["lastLow"] == 431400
    assert "junk" not in m, "白名单外字段必须被丢弃"


def test_overlay_state_sanitize_and_cap(server):
    port, _srv = server
    junk = dict(_MATCH, junk2=1)
    matches = [dict(junk, x=i) for i in range(260)]
    st, d = _req_json(port, "/api/ocr/overlay/state",
                      {"region": {"x": 0, "y": 0, "w": 800, "h": 600}, "matches": matches})
    assert st == 200 and d["count"] == 200, "超过 200 条要截断"


def test_overlay_state_bad_region_400(server):
    port, _srv = server
    st, d = _req_json(port, "/api/ocr/overlay/state", {"matches": []})
    assert st == 400 and d["error"]
    st, d = _req_json(port, "/api/ocr/overlay/state",
                      {"region": {"x": 0, "y": 0, "w": 0, "h": 10}, "matches": []})
    assert st == 400


# ---------------------------------------------------------------- 纯函数

def test_fmt_short():
    # R243：精确卢布（用户要求：不要万/亿简写，精确到个位数）
    assert scan.fmt_short(431400) == "431,400 ₽"
    assert scan.fmt_short(90000) == "90,000 ₽"
    assert scan.fmt_short(12600) == "12,600 ₽"
    assert scan.fmt_short(9999) == "9,999 ₽"
    assert scan.fmt_short(123456789) == "123,456,789 ₽"
    assert scan.fmt_short(43140000) == "43,140,000 ₽"
    assert scan.fmt_short(None) == "—"
    assert scan.fmt_short(0) == "—"
    assert scan.fmt_short(-5) == "—"


def test_price_views_three_views():
    m = {"price": {"lastLow": 431400, "avg24h": 400000, "avg7d": None},
         "gw": 2, "gh": 2, "weight": 4.0}
    main, slot, kg = scan.price_views(m, "last")
    assert main == "431,400 ₽" and slot == "107,850 ₽" and kg == "107,850 ₽"
    main24, slot24, kg24 = scan.price_views(m, "a24")
    assert main24 == "400,000 ₽" and slot24 == "100,000 ₽" and kg24 == "100,000 ₽"
    # 7日均价无数据 → 如实显示 —，不估算
    main7, _, _ = scan.price_views(m, "w7")
    assert main7 == "—"
    # 无重量 → kg 为 —
    m2 = {"price": {"lastLow": 12600}, "gw": 1, "gh": 1}
    assert scan.price_views(m2, "last")[2] == "—"


def test_price_modes_order():
    # R256：价格口径仅三档——最新价格 / 24小时均价 / 7日均价
    assert [k for k, _lbl in scan.PRICE_MODES] == ["last", "a24", "w7"]
    assert scan.MODE_FIELDS["last"] == "lastLow" and scan.MODE_FIELDS["w7"] == "avg7d"
    # 游戏模式三档（切换模式按钮循环）
    assert [k for k, _lbl in scan.GAME_MODES] == ["regular", "pve", "pvps"]
    assert scan.game_mode_index("pvps") == 2 and scan.game_mode_label("pve") == "PvE"


# ---------------------------------------------------------------- 宿主契约（R239）

def test_scan_host_overlay_contract():
    src = open(os.path.join(TOOLS, "scan.py"), encoding="utf-8").read()
    assert 'SCAN_TITLE_DONE = "EFT截图·完成"' in src
    assert "UpdateLayeredWindow" in src and "WS_EX_TRANSPARENT" in src
    assert "HTTRANSPARENT" in src                  # 控制条按钮外穿透
    assert "DispatchMessageW" in src               # 原生浮窗 WndProc 需要消息派发
    assert "fetch_state(server)" in src            # 「完成」标题后取交接态
    assert "WS_EX_NOACTIVATE" in src               # 点击不抢游戏焦点
    assert "WM_NCHITTEST" in src and "WM_LBUTTONDOWN" in src
    assert 'PRICE_MODES = [("last", "最新价格")' in src
    assert '("a24", "24小时均价")' in src
    assert '("w7", "7日均价")' in src
    assert 'GAME_MODES = [("regular", "PvP")' in src


def test_serve_overlay_endpoint_contract():
    src = open(os.path.join(TOOLS, "serve.py"), encoding="utf-8").read()
    assert '"/api/ocr/overlay/state"' in src
    assert "_handle_ocr_overlay_get" in src and "_handle_ocr_overlay_post" in src
    assert "_OCR_OVERLAY" in src


def test_scan_page_handoff_contract():
    html = open(os.path.join(ROOT, "scan.html"), encoding="utf-8").read()
    assert "/api/ocr/overlay/state" in html and "{ region: ir, matches: matches }" in html
    assert "EFT截图·完成" in html
