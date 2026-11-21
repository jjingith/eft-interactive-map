"""R277：会员激活码充值闭环（先做卡密，不做在线支付）。

档位照 ikuuu 商店 5 档：1天¥1 / 1月¥12 / 3月¥30 / 6月¥60 / 12月¥108。
云端是档位与价格的唯一真源，客户端 BFF / 前端兜底 / 管理工具三处必须一致。
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLOUD = ROOT.parent / "eft-cloud"
DEPLOY = ROOT.parent / "eft-cloud-deploy"

EXPECTED = [("d1", 1, 1), ("m1", 30, 12), ("m3", 90, 30),
            ("m6", 180, 60), ("y1", 365, 108)]


def _read(base: Path, name: str) -> str:
    return (base / name).read_text(encoding="utf-8")


# ---------------------------------------------------------------- 档位一致性

def test_server_tiers_match_ikuuu_prices():
    import sys
    sys.path.insert(0, str(CLOUD))
    from app import redeem  # noqa: PLC0415

    assert [(key, redeem.REDEEM_TIERS[key]["days"], redeem.REDEEM_TIERS[key]["price"])
            for key in redeem.TIER_ORDER] == EXPECTED
    assert [t["price"] for t in redeem.tier_payload()] == [1, 12, 30, 60, 108]
    # 码空间要足够大，且不带易混淆字符
    assert redeem.CODE_LENGTH == 16
    assert not ({"0", "O", "1", "I", "L"} & set(redeem.CODE_ALPHABET))
    code = redeem.generate_code()
    assert re.fullmatch(r"[0-9A-Z]{4}(-[0-9A-Z]{4}){3}", code)
    assert redeem.code_hint(code).startswith(redeem.normalize_code(code)[:4])
    assert "••••" in redeem.code_hint(code)


def test_client_fallback_tiers_match_server():
    js = _read(ROOT, "js/cloud.js")
    fallback = re.search(r"var FALLBACK_TIERS = \[(.*?)\];", js, re.S)
    assert fallback, "前端缺少离线兜底档位"
    rows = re.findall(
        r'tier:\s*"(\w+)",\s*label:\s*"([^"]+)",\s*days:\s*(\d+),\s*price:\s*(\d+)',
        fallback.group(1),
    )
    assert [(r[0], int(r[2]), int(r[3])) for r in rows] == EXPECTED


def test_admin_tool_tiers_match_server():
    py = _read(DEPLOY, "eft-cloud-admin-tool.py")
    rows = re.findall(r'\("([^"]+)\s*¥(\d+)",\s*"(\w+)"\)', py)
    assert len(rows) >= 5
    assert [(key, int(price)) for _label, price, key in rows[:5]] == [
        ("d1", 1), ("m1", 12), ("m3", 30), ("m6", 60), ("y1", 108),
    ]


# ---------------------------------------------------------------- BFF 代理

def test_bff_proxies_redeem_and_tiers():
    serve = _read(ROOT, "tools/serve.py")
    assert '"/api/cloud/redeem": ("redeem", ("code",))' in serve
    assert 'path == "/api/cloud/redeem/tiers"' in serve
    assert "cloud_client.redeem_tiers" in serve

    cloud = _read(ROOT, "tools/cloud.py")
    assert 'CLOUD_BASE + "/redeem/tiers"' in cloud
    assert 'CLOUD_BASE + "/redeem"' in cloud
    assert "def redeem_tiers(" in cloud and "def redeem(" in cloud
    # 兑换必须走登录态，且成功后刷新本机会员缓存
    block = cloud[cloud.find("    def redeem(self, code"):]
    block = block[:block.find("\n    def ")]
    assert "self._authorized(" in block
    assert "config.set_member_state(" in block


def test_cloud_client_redeem_updates_member_cache(tmp_path):
    import config
    from cloud import CloudClient

    client = CloudClient(str(tmp_path), str(ROOT / "assets" / "cloud-ca.pem"))
    client._session = {"access_token": "access-test"}
    calls = []

    def fake_authorized(method, path, *, payload=None, retryable=False):
        calls.append((method, path, payload))
        return 200, {
            "email": "buyer@example.com", "label": "1 个月", "tier": "m1",
            "added_days": 30, "member": True, "member_status": "active",
            "member_plan": "monthly", "member_since": "2026-11-13T07:00:00+00:00",
            "member_expires_at": "2026-12-13T07:00:00+00:00",
        }

    client._authorized = fake_authorized  # type: ignore[method-assign]
    result = client.redeem("AAAA-AAAA-AAAA-AAAA")
    assert result["added_days"] == 30
    assert calls == [("POST", "/v1/redeem", {"code": "AAAA-AAAA-AAAA-AAAA"})]
    state = config.member_state()
    assert state["member"] is True and state["member_status"] == "active"

    tiers_seen = []
    client._request = lambda method, path, **kw: (  # type: ignore[method-assign]
        tiers_seen.append((method, path)) or (200, {"tiers": [{"tier": "m1"}]})
    )
    assert client.redeem_tiers()["tiers"] == [{"tier": "m1"}]
    assert tiers_seen == [("GET", "/v1/redeem/tiers")]


def test_tiers_request_retries_after_keepalive_disconnect(tmp_path):
    """档位接口是幂等 GET：连接被提前关掉时自动重试，不把 502 抛给页面。"""
    import http.client

    from cloud import CloudClient

    client = CloudClient(str(tmp_path), str(ROOT / "assets" / "cloud-ca.pem"))
    source = _read(ROOT, "tools/cloud.py")
    start = source.find("    def _request_once(")
    block = source[start:source.find("\n    def ", start + 1)]
    assert "except AttributeError" in block and "http.client.HTTPException" in block

    calls = []

    def fake_once(method, path, payload, token):
        calls.append(path)
        if len(calls) == 1:
            raise http.client.HTTPException("响应读取时连接已关闭")
        return 200, {"tiers": [{"tier": "d1"}]}, {}

    client._request_once = fake_once  # type: ignore[method-assign]
    client._close = lambda: None  # type: ignore[method-assign]
    status, data = client._request("GET", "/v1/redeem/tiers", retryable=True)
    assert status == 200 and data["tiers"] == [{"tier": "d1"}]
    assert len(calls) == 2


# ---------------------------------------------------------------- 前端面板

def test_cloud_panel_has_tier_cards_and_single_redeem_button():
    js = _read(ROOT, "js/cloud.js")
    for needle in (
        'class="rd-tiers"', 'data-role="rd-code"', 'data-action="redeem"',
        'setAttribute("data-tier", t.tier)',
        "loadRedeemTiers()", "mountRedeem()",
        "submitRedeem()", "redeemErrorMessage", "notifyMemberChanged()",
        "applyMember(result)", '"/api/cloud/redeem/tiers"', '"/api/cloud/redeem"',
        # R277b：爱发电购买入口由云端 shop_url 下发，不写死在 EXE 里
        'data-action="redeem-buy"', "redeemShopUrl", 'window.open(state.redeemShopUrl, "_blank"',
    ):
        assert needle in js, needle
    # shop_url 为空时隐藏购买按钮，绝不能 open 空字符串
    assert 'if (state.redeemShopUrl)' in js
    # 档位卡片是纯展示 div：不设选中态、不可点（兑换以码自带天数为准）
    assert 'var card = document.createElement("div")' in js
    assert 'redeem-tier' not in js
    assert "state.redeemTier:" not in js and "state.redeemTier =" not in js
    assert "不用选档位" in js
    # 两个视图（登录 / 已登录）都要挂兑换区
    assert js.count("mountRedeem();") == 2
    # 档位卡片用 DOM 创建并转义文本，不拼云端字符串进 innerHTML
    assert "price.textContent" in js and "name.textContent" in js
    for code in ("code_not_found", "code_used", "code_disabled",
                 "already_permanent", "too_many_attempts"):
        assert code in js


def test_redeem_styles_are_scoped_and_tier_price_visible():
    css = _read(ROOT, "assets/xp-ui/xp-ui-app.css")
    assert ".rd-tiers" in css and "repeat(3, 1fr)" in css
    assert ".rd-tier-price" in css and ".rd-form .rd-submit" in css
    assert ".rd-tier.is-active" not in css      # 不做选中态
    assert "cursor: default" in css
    assert ".rd-buy" in css and ".rd-buy[hidden]" in css
    # 主题最后加载，全部选择器必须带 html body 前缀压住通用按钮样式
    block = css[css.find("/* R277 会员充值"):]
    selectors = [line.strip() for line in block.splitlines() if "{" in line and "." in line]
    assert selectors
    assert all(line.startswith("html body ") for line in selectors), selectors


# ---------------------------------------------------------------- 管理工具

def test_admin_tool_has_codes_tab_and_never_shows_plaintext_from_list():
    py = _read(DEPLOY, "eft-cloud-admin-tool.py")
    for needle in (
        'self.notebook.add(self.codes_page, text="激活码管理")',
        '"/v1/admin/redeem-codes/generate"',
        '"/v1/admin/redeem-codes/status"',
        '"/v1/admin/redeem-codes/exported"',
        '"/v1/admin/redeem-codes/stats"',
        '"/v1/admin/redeem-codes?"',
        "_auto_save_generated", "copy_generated", "fill_codes",
        'item["code_hint"]', "CODE_STATUS_LABEL",
        "set_code_exported", '"已导出"',
    ):
        assert needle in py, needle
    assert 'self.codes_page = ttk.Frame(self.notebook)' in py
    assert 'ttk.Frame(self.accounts_page' in py
    # 明文只能来自生成响应，列表渲染里不得出现 item["code"]
    assert 'item["code"]' not in py[py.find("    def fill_codes("):py.find("    def on_code_select(")]
