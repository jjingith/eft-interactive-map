# -*- coding: utf-8 -*-
"""R256：截图浮窗的会员态 / 三价格口径 / 切换模式按钮 / 歧义徽章悬停弹窗。

覆盖：
  · BFF 新增 `GET /api/member` 返回权威会员态（宿主独立进程读不到内存会员态）；
  · 价格口径仅三档（最新价格 / 24小时均价 / 7日均价），MODE_FIELDS 映射 w7→avg7d；
  · 控制条三键 [切换模式][价格切换][关闭]，hit_button 区分 gamemode/basis/close；
  · 点击「切换模式」循环 PvP/PvE/PvPS 并回调触发同区域重识别；
  · 歧义物品只画 ? 徽章（不画价格），悬停徽章弹窗列出所有候选口径+价。
"""

from __future__ import annotations

import contextlib
import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

import config
import scan
import serve

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"


# ---------------------------------------------------------------- HTTP 辅助

@contextlib.contextmanager
def _serve(root: Path):
    (root / "index.html").write_text("<!doctype html>", encoding="utf-8")
    httpd = serve.create_server(0, "127.0.0.1", str(root), config_dir=str(root),
                                poll_interval=0.2)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield serve.url_for("127.0.0.1", httpd.server_address[1])
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def _get(url: str):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(url, timeout=20) as res:
            return res.status, json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


# ---------------------------------------------------------------- /api/member

def test_api_member_endpoint(tmp_path):
    with _serve(tmp_path) as base:
        config.set_member_state({"member": True, "member_status": "permanent",
                                 "member_plan": "年付"})
        st, body = _get(base + "/api/member")
        assert st == 200
        assert body["member"] is True
        assert body["member_status"] == "permanent"
        assert body["member_plan"] == "年付"
        config.set_member_state(None)
        st, body = _get(base + "/api/member")
        assert st == 200
        assert body["member"] is False
        assert body["member_status"] == "none"


# ---------------------------------------------------------------- fetch_member_state

class _FakeResp:
    def __init__(self, data: bytes):
        self._d = data

    def read(self):
        return self._d

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _FakeOpener:
    def __init__(self, payload: str):
        self._p = payload.encode("utf-8")

    def open(self, req, timeout=0):
        return _FakeResp(self._p)


def _install_fake_bff(monkeypatch, payload: str):
    monkeypatch.setattr(urllib.request, "build_opener",
                        lambda *a, **k: _FakeOpener(payload))


def test_fetch_member_state_reads_bff(monkeypatch):
    # 永久会员：BFF 返回 member=True → 即使本机 config 没写会员也应为会员
    _install_fake_bff(monkeypatch, json.dumps({"member": True,
                                               "member_status": "permanent"}))
    config.set_member_state(None)
    assert scan.fetch_member_state("http://127.0.0.1:9999", None) is True


def test_fetch_member_state_bff_false(monkeypatch):
    _install_fake_bff(monkeypatch, json.dumps({"member": False}))
    config.set_member_state(None)
    assert scan.fetch_member_state("http://127.0.0.1:9999", None) is False


def test_fetch_member_state_fallback_when_bff_down(monkeypatch):
    # BFF 不可达 → 降级用本机 config；本机是会员则仍按会员处理
    monkeypatch.setattr(
        urllib.request, "build_opener",
        lambda *a, **k: (_ for _ in ()).throw(urllib.error.URLError("connection refused")))
    config.set_member_state(None)
    assert scan.fetch_member_state("http://127.0.0.1:9999", None) is False
    config.set_member_state({"member": True})
    assert scan.fetch_member_state("http://127.0.0.1:9999", None) is True


# ---------------------------------------------------------------- 价格口径 / 游戏模式常量

def test_price_modes_three_bases():
    assert [k for k, _lbl in scan.PRICE_MODES] == ["last", "a24", "w7"]
    assert scan.MODE_FIELDS["last"] == "lastLow"
    assert scan.MODE_FIELDS["a24"] == "avg24h"
    assert scan.MODE_FIELDS["w7"] == "avg7d"        # 7日均价来自快照 avg7d.values


def test_game_modes_three():
    assert [k for k, _lbl in scan.GAME_MODES] == ["regular", "pve", "pvps"]
    assert scan.game_mode_label("regular") == "PvP"
    assert scan.game_mode_label("pve") == "PvE"
    assert scan.game_mode_label("pvps") == "PvPS"
    assert scan.game_mode_index("pvps") == 2
    assert scan.game_mode_index("unknown") == 0


# ---------------------------------------------------------------- 控制条三键 + hit_button

def test_render_control_returns_three_buttons():
    img, rgm, rb, rc = scan.render_control("PvP", "最新价格", 1.0)
    assert rgm[2] < rb[0] < rc[0], "三键必须有透明间隔"
    assert rc[2] == img.width and rc[3] == img.height


@pytest.fixture
def fake_overlay(monkeypatch):
    """用桩替换所有真正的 Win32 调用，让 OverlaySession 可在无桌面环境下实例化。"""
    monkeypatch.setattr(scan, "create_overlay_window", lambda role: 100 + role)
    monkeypatch.setattr(scan, "screen_size", lambda: (1920, 1080))
    monkeypatch.setattr(scan, "set_layered_bitmap", lambda *a, **k: None)
    monkeypatch.setattr(scan, "_topmost", lambda *a, **k: None)
    monkeypatch.setattr(scan, "control_position", lambda *a, **k: (0, 0))
    monkeypatch.setattr(scan, "_user32",
                        type("_U32", (), {"ShowWindow": staticmethod(lambda *a, **k: 1),
                                          "ReleaseCapture": staticmethod(lambda *a, **k: 1)})())
    yield


def test_overlay_hit_button_keys(fake_overlay):
    sess = scan.OverlaySession({"x": 0, "y": 0, "w": 10, "h": 10}, [], None,
                               server=None, game_idx=1)
    sess.btn_gamemode = (0, 0, 30, 24)
    sess.btn_basis = (34, 0, 80, 24)
    sess.btn_close = (84, 0, 108, 24)
    assert sess.hit_button(10, 10) == "gamemode"
    assert sess.hit_button(50, 10) == "basis"
    assert sess.hit_button(95, 10) == "close"
    assert sess.hit_button(200, 10) is None
    assert sess.game_mode_label == "PvE"


def test_overlay_cycle_game_mode_invokes_callback(fake_overlay):
    calls = []
    sess = scan.OverlaySession({"x": 0, "y": 0, "w": 10, "h": 10}, [], None,
                               server=None, game_idx=0, on_gamemode=calls.append)
    assert sess.game_mode_code == "regular"
    sess.cycle_game_mode()
    assert sess.game_mode_code == "pve" and calls == ["pve"]
    sess.cycle_game_mode()
    assert sess.game_mode_code == "pvps" and calls == ["pve", "pvps"]
    sess.cycle_game_mode()                      # 回到 PvP
    assert sess.game_mode_code == "regular" and calls == ["pve", "pvps", "regular"]


# ---------------------------------------------------------------- 歧义徽章只画徽章

def _ink(img):
    return sum(1 for p in img.getdata() if p[3] > 0)


def test_render_labels_ambiguous_hides_price_text():
    base = {"x": 0, "y": 0, "w": 200, "h": 30, "gw": 1, "gh": 1,
            "price": {"lastLow": 400000}}
    normal = dict(base)
    amb = dict(base)
    amb["price"] = dict(base["price"], ambiguous=True,
                       candidates=[{"name": ".338 AP", "price": 400000},
                                   {"name": ".300 AP", "price": 300000}])
    tiers = config.OCR_SCAN_TIERS_DEFAULT
    img_normal = scan.render_labels(900, 400, [normal], "last", tiers)
    badges = []
    img_amb = scan.render_labels(900, 400, [amb], "last", tiers, badges_out=badges)
    # 歧义只画 ? 徽章、不画价格 → 墨量明显少于正常价
    assert _ink(img_amb) < _ink(img_normal)
    # 且必须收集到 ? 徽章命中矩形，供悬停弹窗使用
    assert len(badges) == 1
    x0, y0, x1, y1 = badges[0][1]
    assert x1 > x0 and y1 > y0
