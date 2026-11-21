# -*- coding: utf-8 -*-
"""R268 的采集时刻判定已在 2026-11-17 被云端账号级 CD 取代。

保留：
  · 云端采集节奏常量（:01 / :31）仍用于界面提示；
  · 不同模式各自缓存，互不串数据；
  · 「获取最新数据」带 force=1，由服务端决定扣次 / CD 回放 / 配额用尽。
"""

import datetime
import json
import os
import sys

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TEST_DIR)
TOOLS = os.path.join(ROOT, "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import pytest  # noqa: E402

import prices_source  # noqa: E402

TZ = datetime.timezone(datetime.timedelta(hours=8))


def _at(hour, minute, second=0):
    return datetime.datetime(2026, 11, 12, hour, minute, second, tzinfo=TZ)


def _doc(mode, status="ok"):
    return {
        "status": status,
        "mode": mode,
        "tier": "free",
        "member": False,
        "generated_at": "2026-11-12T15:31:00+08:00",
        "delay_seconds": 12 * 3600,
        "prices": {"x": 1},
        "market": {"x": {"l": 1, "o": 10, "c": 1.0}},
        "quota": {"tier": "free", "daily_limit": 24, "used_today": 1,
                  "remaining_today": 23, "cd_seconds": 3599,
                  "cooldown": status == "cd", "next_allowed_at": "2026-11-12T15:32:00+08:00"},
    }


class _Client:
    def __init__(self):
        self.calls = []

    def prices_market(self, mode):
        self.calls.append(mode)
        return _doc(mode)


def test_collect_minutes_are_01_and_31():
    assert prices_source.COLLECT_MINUTES == (1, 31)


def test_payload_moment_parses_iso_variants():
    z = prices_source._payload_moment({"snapshotAt": "2026-11-12T15:31:00Z"})
    assert z is not None and z.utcoffset() == datetime.timedelta(0)
    off = prices_source._payload_moment({"snapshotAt": "2026-11-12T15:31:00+08:00"})
    assert off is not None and off.hour == 15
    naive = prices_source._payload_moment({"snapshotAt": "2026-11-12T15:31:00"})
    assert naive is not None and naive.tzinfo is not None, "无时区按本地解释而不是丢弃"
    assert prices_source._payload_moment({"snapshotAt": "t1"}) is None
    assert prices_source._payload_moment({}) is None


def test_different_modes_use_separate_cache(tmp_path):
    client = _Client()
    app_dir = str(tmp_path / "app")
    prices_source.snapshot_for(str(tmp_path), "pve", cloud_client=client,
                               now=_at(15, 35), app_dir=app_dir)
    prices_source.snapshot_for(str(tmp_path), "regular", cloud_client=client,
                               now=_at(15, 35), app_dir=app_dir)
    assert client.calls == ["pve", "regular"]
    # 再读一次 pve 走本地结果，不再扣次
    prices_source.snapshot_for(str(tmp_path), "pve", cloud_client=client,
                               now=_at(15, 36), app_dir=app_dir)
    assert client.calls == ["pve", "regular"]


def test_cd_payload_is_json_serializable(tmp_path):
    client = _Client()
    client.prices_market = lambda mode: dict(_doc(mode, status="cd"))
    payload = prices_source.snapshot_for(
        str(tmp_path), "regular", cloud_client=client, now=_at(15, 40),
        force=True, app_dir=str(tmp_path / "app"),
    )
    assert payload["status"] == "cd"
    assert payload["quota"]["cooldown"] is True
    json.dumps(payload)   # 不能抛 TypeError


def test_market_ui_uses_cloud_status_states():
    js = open(os.path.join(ROOT, "js", "market.js"), encoding="utf-8").read()
    css = open(os.path.join(ROOT, "market.css"), encoding="utf-8").read()
    assert "is-info" in js and ".mk-cutoff-warn.is-info" in css
    assert "CD 59:59" in js
    assert "payload.status === \"cd\"" in js
    assert "quota_exhausted" in js
    assert "内置离线快照" not in js


def test_free_user_uses_cloud_not_bundle(tmp_path):
    client = _Client()
    payload = prices_source.snapshot_for(
        str(tmp_path), "regular", cloud_client=client, member=False,
        now=_at(15, 5), force=True, app_dir=str(tmp_path / "app"),
    )
    assert payload.get("available") is True
    assert payload.get("source") == "cloud"
    assert payload.get("nonLive") is True
    assert "throttled" not in payload
    assert client.calls == ["regular"]


def test_serve_forwards_force_flag():
    src = open(os.path.join(TOOLS, "serve.py"), encoding="utf-8").read()
    assert 'qs.get("force")' in src
    assert "force=force" in src
