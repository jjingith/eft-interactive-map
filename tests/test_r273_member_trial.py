"""R273：新注册赠 3 天会员、会员态展示与配枪属性块精简。

用户要求（2026-11-13 12:56）：
  · 配枪整枪属性里的消音 / 非消音对比、整枪总价 / 无消音器提示、技能后数值全删；
  · 整枪属性与隐藏属性统一成「一行三个」，字体字号底色照隐藏属性；
  · 云账号按钮显示「云账号：免费版 / 会员版」；
  · 二级栏常显会员到期时间；
  · 每个新注册邮箱赠送三天会员时长。
"""

from __future__ import annotations

import datetime
import json
import os
import re
from pathlib import Path

import config

ROOT = Path(__file__).resolve().parent.parent


def _read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def _make_client(tmp_path):
    import cloud

    return cloud.CloudClient(str(tmp_path), str(ROOT / "assets" / "cloud-ca.pem"))


def _stub_verify_register(client, calls):
    def fake(method, path, *, payload=None, token=None, retryable=False):
        calls.append(path)
        assert path.endswith("/auth/verify-email")
        return 200, {
            "session": {
                "access_token": "access-1",
                "refresh_token": "refresh-1",
                "expires_in": 900,
                "refresh_expires_in": 86400,
            },
            "last_login": {"at": "2026-11-13T04:56:00+00:00", "ip": "127.0.0.1"},
        }

    client._request = fake  # type: ignore[method-assign]


# ---------------------------------------------------------------- 本机试用（已停用）

# 2026-11-15 用户要求：「免费时长要和充值的时长一样**增加在账号上**」。
# 注册赠送改由云端写进账号的 member_expires_at（服务端 EFT_REGISTER_FREE_DAYS），
# 客户端不再写 local-trial.json，也不再让本机文件影响会员判定——
# 否则账号显示已到期、本机却能用会员功能，是两本账。
# 下面锁的是「本机文件不再授予会员」这条新契约；旧文件不会被删除。

def test_local_trial_file_no_longer_grants_membership(tmp_path):
    entry = config.grant_local_trial("A@example.com")
    assert entry["email"] == "a@example.com"
    assert entry["days"] == config.TRIAL_DAYS == 3
    # 文件照旧写得出来（保留兼容，不动用户数据）
    payload = json.loads((tmp_path / "local-trial.json").read_text(encoding="utf-8"))
    assert payload["email"] == "a@example.com"
    assert set(payload["accounts"]) == {"a@example.com"}

    # 但它**不再**决定会员态：会员只认服务端快照
    state = config.member_state()
    assert state["member"] is False, "本机试用文件不得再解锁会员功能"
    assert state["member_status"] == "none"
    assert config.is_member() is False


def test_grant_local_trial_is_still_idempotent(tmp_path):
    first = config.grant_local_trial("a@example.com")
    again = config.grant_local_trial("a@example.com")
    assert again["granted_at"] == first["granted_at"], "同一邮箱不叠加、不续期"


def test_verify_register_no_longer_writes_local_trial(tmp_path):
    """注册成功后不再写本机试用——赠送由云端加到账号上。"""
    client = _make_client(tmp_path)
    calls = []
    _stub_verify_register(client, calls)

    result = client.verify_register("new@example.com", "123456")
    assert result["email"] == "new@example.com"
    assert calls and calls[0].endswith("/auth/verify-email")
    assert not (tmp_path / "local-trial.json").exists(), \
        "客户端不该再产生本机试用记录"


def test_server_granted_membership_is_reported_by_status(tmp_path):
    """服务端把赠送时长写进账号后，状态查询必须照实报告（不再靠本机试用）。"""
    client = _make_client(tmp_path)
    _stub_verify_register(client, [])
    client.verify_register("new@example.com", "123456")

    future = (datetime.datetime.now(datetime.timezone.utc)
              + datetime.timedelta(days=3)).isoformat()
    config.set_member_state({
        "member": True, "member_status": "active", "member_plan": "grant",
        "member_expires_at": future,
    })
    status = client.status()
    assert status["logged_in"] is True
    assert status["member"]["member"] is True
    assert status["member"]["member_status"] == "active"
    assert status["member"]["member_expires_at"] == future


# ---------------------------------------------------------------- 过期账号不得被本机试用顶替

def test_expired_status_not_masked_by_local_trial(tmp_path):
    """云端已明确 expired 的账号，即使本机存在有效试用，也必须是非会员。

    复现：在另一台机器上重新注册/登录一个已过期的测试账号，verify_register 会
    写入本机试用；此前 member_state() 在云端 member 不为 True 时无条件套用试用，
    把 expired 顶成了 trial，导致过期账号仍能用会员功能。
    """
    config.set_member_state({"member": False, "member_status": "expired"})
    # 同邮箱本机试用仍在有效期内
    config.grant_local_trial("expired@example.com")
    config.set_current_trial_email("expired@example.com")

    state = config.member_state()
    assert state["member"] is False, "expired 账号不能被本机试用顶替成会员"
    assert state["member_status"] == "expired"
    assert config.is_member() is False


def test_member_true_with_past_expiry_is_non_member():
    """member=True 但 member_expires_at 已过 → 强制非会员。"""
    config.set_member_state({
        "member": True,
        "member_status": "active",
        "member_expires_at": "2020-01-01T00:00:00+00:00",
    })
    state = config.member_state()
    assert state["member"] is False
    assert state["member_status"] == "expired"
    assert config.is_member() is False


def test_member_expired_status_forces_non_member():
    """服务端显式 member=True + status=expired → 以 status 为准，非会员。"""
    config.set_member_state({"member": True, "member_status": "expired"})
    assert config.is_member() is False
    assert config.member_state()["member_status"] == "expired"


def test_future_expiry_still_member():
    """member=True 且到期时间在未来 → 仍是会员（反例，确保不误伤）。"""
    future = (datetime.datetime.now(datetime.timezone.utc)
              + datetime.timedelta(days=5)).isoformat()
    config.set_member_state({
        "member": True,
        "member_status": "active",
        "member_expires_at": future,
    })
    assert config.is_member() is True


# ---------------------------------------------------------------- 前端契约（静态）

def test_gunsmith_comparison_and_skill_note_removed():
    app = _read("app.js")
    assert "renderGwSilencerCompare" not in app
    assert "gw-silcompare" not in app
    assert '"技能后数值："' not in app, "渲染用的字符串字面量要删掉（注释不算）"
    assert "gw-bar-skillnote" not in app
    assert "该枪的膛口槽位没有可用的消音器" not in app


def test_stats_and_hidden_use_same_three_column_block():
    css = _read("style.css")
    block = css[css.rindex("R273：整枪属性 / 隐藏属性统一成同一种紧凑块"):]
    assert re.search(r"\.gw-stats,\s*\.gun-workbench \.gw-hidden\s*\{[^}]*"
                     r"grid-template-columns:\s*repeat\(3, 1fr\)", block)
    assert "html body .gun-workbench .gw-stats" in block, "要压过 XP 主题的底色覆盖"
    assert "--lw-panel-2" in block, "底色沿用隐藏属性那套"


def test_cloud_button_and_member_expire_badge():
    html = _read("index.html")
    assert re.search(r'id="am-cloud"[^>]*>云账号：免费版</button>', html)
    assert 'id="vt-member-expire"' in html
    assert html.index('id="vt-market-meta"') < html.index('id="vt-member-expire"')

    js = _read("js/cloud.js")
    assert '"云账号："' in js or "云账号：" in js
    assert "会员版" in js and "免费版" in js
    assert "trial" in js, "试用态要按会员渲染，不能被当成永久会员"
    assert '"/api/member"' in js, "页面加载就要拉会员态，不能等点开面板"
    assert "updateMemberBadges" in js and "vt-member-expire" in js

    xp = _read("assets/xp-ui/xp-ui-app.css")
    assert re.search(r"\.app-cloud-wrap \.app-menu-btn\s*\{[^}]*width:\s*auto", xp)


def test_member_expire_badge_shows_year_and_days_left():
    """到期徽标必须带年份 + 剩余天数。

    用户实测（2026-11-15）：账号实际到 2027-11-14，徽标只写「11-14 13:59」，
    看起来像昨天就到期了，误判成「显示已到期但还能用会员功能」。
    """
    js = _read("js/cloud.js")
    start = js.index("function formatExpire(")
    body = js[start:js.index("\n  function ", start + 10)]
    assert "getFullYear()" in body, "日期必须带年份，否则跨年到期会被读成已过期"
    assert "剩 " in js, "徽标要给出剩余天数"
    assert "function daysLeft(" in js
