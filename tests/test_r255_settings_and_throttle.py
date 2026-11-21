# -*- coding: utf-8 -*-
"""R255：设置面板精简 + 会员门禁弹窗 + 全屏识别 + 数据获取节流。

用户反馈（2026-11-12 16:00）：
  · 档位 UI 精简成「档位N: + [颜色方框][上限价格]」，字体/描边/字号全删；
  · 面板注释精简；点档位区域弹「会员功能」提示，免费版固定灰白；
  · 浮窗口径切换按钮免费版灰色不可切（免费版没有服务器数据）；
  · 热键上方加「全屏识别」勾选框（勾上不框选直接识别整屏）+ 热键恢复默认按钮；
  · F5 不再自动打云端：截止徽标左边加「获取最新数据」按钮。

R268 更正：该按钮的判定不再是「每 20 分钟一次」，而是「缓存快照是否已覆盖最近
一个云端采集时刻（每小时 :01 / :31）」——见本文件下方的采集时刻用例。
"""

import os
import sys
import datetime
from types import SimpleNamespace

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TEST_DIR)
TOOLS = os.path.join(ROOT, "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import pytest  # noqa: E402

import config  # noqa: E402
import prices_source  # noqa: E402
import scan  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_cloud_throttle():
    prices_source._cloud_fetch_at.clear()
    prices_source._cloud_last.clear()
    yield
    prices_source._cloud_fetch_at.clear()
    prices_source._cloud_last.clear()


# ------------------------------------------------- 云端取数（免费 / 会员同一入口）
# 2026-11-17 起不再按「采集时刻」在客户端预判：F5 / 打开页面复用本地结果，
# 用户点「获取最新数据」一定打云端，由服务端执行账号级 CD / 每日配额。

TZ = datetime.timezone(datetime.timedelta(hours=8))


def _doc(tier="free", status="ok", item_price=1, generated_at="2026-11-12T15:31:00+08:00"):
    member = tier == "member"
    return {
        "status": status,
        "mode": "regular",
        "tier": tier,
        "member": member,
        "generated_at": generated_at,
        "stored_at": generated_at,
        "delay_seconds": 0 if member else 12 * 3600,
        "prices": {"x": item_price},
        "market": {"x": {"l": item_price, "o": 10, "c": 1.0}},
        "quota": {
            "tier": tier,
            "daily_limit": None if member else 24,
            "used_today": 1,
            "remaining_today": None if member else 23,
            "cd_seconds": 30 if member else 3599,
            "cooldown": status == "cd",
            "next_allowed_at": "2026-11-12T15:32:00+08:00",
        },
    }


class _FakeCloud:
    def __init__(self, doc=None, error=None):
        self.calls = 0
        self.doc = doc or _doc()
        self.error = error

    def prices_market(self, mode):
        self.calls += 1
        if self.error:
            raise self.error
        return dict(self.doc, mode=mode)


def _at(hour, minute, second=0):
    return datetime.datetime(2026, 11, 12, hour, minute, second, tzinfo=TZ)


def test_slot_helpers_use_01_and_31():
    assert prices_source.latest_collect_slot(_at(15, 30)).strftime("%H:%M") == "15:01"
    assert prices_source.latest_collect_slot(_at(15, 31)).strftime("%H:%M") == "15:31"
    assert prices_source.latest_collect_slot(_at(15, 0)).strftime("%H:%M") == "14:31"
    assert prices_source.next_collect_slot(_at(15, 30)).strftime("%H:%M") == "15:31"
    assert prices_source.next_collect_slot(_at(15, 40)).strftime("%H:%M") == "16:01"
    assert prices_source.next_collect_slot(_at(15, 0)).strftime("%H:%M") == "15:01"


def test_force_always_calls_cloud_and_non_force_reuses_local_result(tmp_path):
    client = _FakeCloud(_doc("member"))
    app_dir = str(tmp_path / "app")
    first = prices_source.snapshot_for(
        str(tmp_path), "regular", cloud_client=client, member=True,
        now=_at(15, 31), app_dir=app_dir,
    )
    assert first["available"] is True and client.calls == 1

    # 打开页面 / 切子页：复用刚取回来的结果，不重复扣次。
    again = prices_source.snapshot_for(
        str(tmp_path), "regular", cloud_client=client, member=True,
        now=_at(15, 32), app_dir=app_dir,
    )
    assert again["available"] is True and client.calls == 1

    # 用户点「获取最新数据」：一定打云端，CD 由服务端决定。
    forced = prices_source.snapshot_for(
        str(tmp_path), "regular", cloud_client=client, member=True,
        now=_at(15, 33), force=True, app_dir=app_dir,
    )
    assert forced["available"] is True and client.calls == 2


def test_cd_payload_is_passed_through_without_charging(tmp_path):
    client = _FakeCloud(_doc("free", status="cd"))
    payload = prices_source.snapshot_for(
        str(tmp_path), "regular", cloud_client=client, member=False,
        now=_at(15, 35), force=True, app_dir=str(tmp_path / "app"),
    )
    assert payload["status"] == "cd"
    assert payload["cached"] is False
    assert payload["quota"]["cooldown"] is True
    assert payload["quota"]["used_today"] == 1
    assert payload["items"]["x"]["l"] == 1


def test_free_user_also_uses_cloud_with_delay(tmp_path):
    client = _FakeCloud(_doc("free"))
    payload = prices_source.snapshot_for(
        str(tmp_path), "regular", cloud_client=client, member=False,
        now=_at(15, 31), app_dir=str(tmp_path / "app"),
    )
    assert client.calls == 1
    assert payload["source"] == "cloud"
    assert payload["tier"] == "free"
    assert payload["nonLive"] is True
    assert payload["dataDelayed"] is True
    assert payload["quota"]["remaining_today"] == 23


def test_serve_passes_force_query():
    src = open(os.path.join(TOOLS, "serve.py"), encoding="utf-8").read()
    assert 'qs.get("force")' in src
    assert "force=force" in src


def test_market_manual_fetch_contract():
    js = open(os.path.join(ROOT, "js", "market.js"), encoding="utf-8").read()
    assert 'payload.status === "cd"' in js
    assert "今日剩余" in js
    assert "quota_exhausted" in js
    assert "内置离线快照" not in js


# ------------------------------------------------- 非会员灰白 + 口径禁用

def test_load_label_tiers_grey_for_non_member(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "is_member", lambda d=None: False)
    tiers = scan.load_label_tiers(str(tmp_path))
    assert tiers == scan._OCR_MEMBER_GREY_TIERS
    assert all(t["color"] in ("#b9c0c9",) for t in tiers), "非会员固定灰白"


def test_load_label_tiers_member_uses_config(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "is_member", lambda d=None: True)
    custom = [{"max": 10000, "color": "#ff0000", "sizeScale": 1.0,
               "font": "msyhbd", "outer": True, "outerColor": "#000",
               "inner": False, "innerColor": "#000"}]
    monkeypatch.setattr(config, "load",
                        lambda d=None: {"ocrScan": {"labelStyle": {"tiers": custom}}})
    assert scan.load_label_tiers(str(tmp_path)) == custom


def test_render_control_member_toggle():
    img_m, _, _, _ = scan.render_control("PvP", "最新价格", 1.0, member=True)
    img_f, _, _, _ = scan.render_control("PvP", "最新价格", 1.0, member=False)
    assert img_m.size == img_f.size
    src = open(os.path.join(TOOLS, "scan.py"), encoding="utf-8").read()
    assert "member=self.member" in src
    body = src[src.index("def _ov_wndproc"):]
    assert "if _ACTIVE.member:" in body, "非会员点击功能按钮必须被忽略"
    # R256：宿主进程读不到 BFF 进程内存里的会员态，必须改从 BFF 的 /api/member 拉取
    assert "fetch_member_state(" in src, "会员态必须从 BFF 拉取（宿主独立进程）"
    assert '"/api/member"' in open(os.path.join(ROOT, "tools", "serve.py"),
                                   encoding="utf-8").read(), "BFF 必须提供 /api/member 接口"


# ------------------------------------------------- 全屏识别

def test_full_screen_reads_config(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "load",
                        lambda d=None: {"ocrScan": {"fullScreen": True}})
    assert scan.full_screen(None) is True
    monkeypatch.setattr(config, "load", lambda d=None: {"ocrScan": {}})
    assert scan.full_screen(None) is False


def test_full_screen_worker_appends_results(monkeypatch):
    calls = {}

    def fake_recognize(server, rect, mode, config_dir):
        calls["rect"] = rect
        return [{"x": 1}], (0, 0, rect[2], rect[3])

    monkeypatch.setattr(scan, "recognize_region", fake_recognize)
    results, recognizing = [], {"flag": True}
    scan._full_screen_worker("http://x", "regular", None, results, recognizing)
    assert results and results[0][2] is None and results[0][0] == [{"x": 1}]
    assert calls["rect"][2] == scan.screen_size()[0], "全屏 = 整个屏幕尺寸"
    assert calls["rect"][3] == scan.screen_size()[1]


def test_watch_hotkey_branch_has_fullscreen_shortcut():
    src = open(os.path.join(TOOLS, "scan.py"), encoding="utf-8").read()
    body = src[src.index("def watch_native"):]
    assert "full_screen(config_dir)" in body and "target=_full_screen_worker" in body


def test_config_normalizes_fullscreen():
    cfg = config._normalize_ocr_scan({"fullScreen": True, "hotkey": "ctrl+alt+p"})
    assert cfg["fullScreen"] is True
    cfg2 = config._normalize_ocr_scan({"fullScreen": "yes"})
    assert cfg2["fullScreen"] is False, "非布尔一律 False"


# ------------------------------------------------- 前端契约

def test_page_panel_contract():
    html = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
    assert 'id="ocr-fullscreen"' in html, "全屏识别勾选框"
    assert 'id="ocr-hotkey-reset"' in html, "恢复默认热键按钮"
    assert "按价格分档上色" in html, "档位说明已精简"
    assert "按热键框选装备，价格直接叠在装备上。" in html, "面板说明已精简"
    assert "价格档位样式" not in html, "旧标题已改名"


def test_app_tier_ui_simplified():
    js = open(os.path.join(ROOT, "app.js"), encoding="utf-8").read()
    body = js[js.index("function ocrTierRow"):js.index("function renderOcrTierRows")]
    assert "档位" in body and '+ (idx + 1) + ":"' in body, "档位N: 标题"
    assert "ocr-t-size" not in body and "ocr-t-font" not in body \
        and "ocr-t-outer" not in body and "ocr-t-inner" not in body, \
        "字号/字体/内外描边控件必须移除"
    collect = js[js.index("function collectOcrTiers"):js.index("function applyOcrSettings")]
    assert 'sizeScale: 1,' in collect and 'font: "msyhbd",' in collect, \
        "保存时写固定兼容字段，宿主渲染契约不变"


def test_app_member_prompt_and_fullscreen_binding():
    js = open(os.path.join(ROOT, "app.js"), encoding="utf-8").read()
    assert "function showMemberPrompt" in js
    assert "价格档位自定义是会员功能" in js
    assert 'queuePrefs({ ocrScan: { fullScreen: !!el.ocrFullscreen.checked } })' in js
    assert 'queuePrefs({ ocrScan: { hotkey: "ctrl+alt+p" } })' in js, "恢复默认热键"


def test_styles_for_new_controls():
    css = open(os.path.join(ROOT, "style.css"), encoding="utf-8").read()
    for marker in (".ocr-fullrow", ".ocr-hotkey-reset", ".ocr-tier-head",
                   ".ocr-tier-line", ".ocr-style-box.is-member-locked",
                   ".ocr-member-tip"):
        assert marker in css, "style.css 缺 %s" % marker
    mcss = open(os.path.join(ROOT, "market.css"), encoding="utf-8").read()
    for marker in (".mk-cutoff-fetch", ".mk-cutoff-warn"):
        assert marker in mcss, "market.css 缺 %s" % marker
    # R6 护栏：@keyframes 不得出现在配枪工作台段之后
    gun = css[css.index(".gun-workbench {"):]
    assert "@keyframes" not in gun
