# -*- coding: utf-8 -*-
"""R221：上传节流必须与采集周期对齐（云端数据不再滞后 30–60 分钟）。

背景：采集器每 30 分钟跑一轮（`price_collect.DEFAULT_INTERVAL_MIN = 30`），
但上传曾硬性按 `minIntervalSec = 3600` 节流，于是「隔一轮才上传一次」——
云端 `generated_at` 永远落后 30–60 分钟，市场页长期显示
「数据截止 10:31（57 分钟前）」。

根因不是采集频率：上游 json.tarkov.dev 本身每 30 分钟才发一版
（实测 Last-Modified 11:30:29 / 11:30:51 / 11:31:16），本地 23 个快照
23 个不同哈希，说明抓取端完全跟得上。唯一卡点就是上传节流值。

不变量：`minIntervalSec` 必须**严格小于**采集周期，否则每两轮才有一次更新。
"""

from __future__ import annotations

import datetime
import json
import re
import socket
from pathlib import Path

import pytest

import price_upload


ROOT = Path(__file__).resolve().parent.parent
COLLECT_SRC = (ROOT / "tools" / "price_collect.py").read_text(encoding="utf-8")
UPLOAD_SRC = (ROOT / "tools" / "price_upload.py").read_text(encoding="utf-8")


def _dead_port() -> int:
    """拿一个一定没人监听的本地端口，让上传必然失败（不产生任何外部请求）。"""
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _write_cfg(app_root: Path, **over) -> dict:
    cfg = {
        "schema": 1,
        "enabled": True,
        "url": "http://127.0.0.1:%d" % _dead_port(),
        "token": "collector-secret",
        "caFile": "",
        "proxy": "",
        "timeoutSec": 2,
        "maxAttempts": 1,
        "retrySleepSec": 0,
        "minIntervalSec": price_upload.DEFAULT_CONFIG["minIntervalSec"],
    }
    cfg.update(over)
    (app_root / "upload.json").write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    return cfg


def _write_state(app_root: Path, age_sec: float) -> str:
    """把三模式的 lastSuccessAt 设成「age_sec 秒之前」，返回那个时间戳。"""
    at = (datetime.datetime.now().astimezone()
          - datetime.timedelta(seconds=age_sec)).isoformat(timespec="seconds")
    doc = {
        "schema": 1,
        "modes": {
            mode: {
                "lastSuccessAt": at,
                "lastAttemptAt": at,
                "lastStatus": "uploaded",
                "pending": False,
            }
            for mode in price_upload.MODES
        },
    }
    (app_root / "upload-state.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return at


def _skipped_by_interval(result: dict) -> bool:
    return bool(result.get("skipped")) and result.get("reason") == "interval"


# ---------------------------------------------------------------- 静态不变量

def test_upload_interval_is_strictly_less_than_collect_interval():
    """R221 核心：节流值必须小于采集周期，否则每两轮才上传一次。"""
    m = re.search(r"^DEFAULT_INTERVAL_MIN\s*=\s*(\d+)", COLLECT_SRC, re.M)
    assert m, "price_collect.py 里找不到 DEFAULT_INTERVAL_MIN"
    collect_sec = int(m.group(1)) * 60

    interval = price_upload.DEFAULT_CONFIG["minIntervalSec"]
    assert interval == 1500, "默认上传节流应为 1500 s（25 分钟），实际 %r" % (interval,)
    assert interval < collect_sec, (
        "上传节流 %d s 不小于采集周期 %d s：每两轮才上传一次，云端会滞后 30–60 分钟"
        % (interval, collect_sec))


def test_no_hourly_throttle_left_behind():
    """旧的「按小时节流」既不能留在默认配置里，也不能留在文案里。"""
    assert '"minIntervalSec": 3600' not in UPLOAD_SRC
    assert "按小时节流" not in COLLECT_SRC
    assert "按小时节流" not in UPLOAD_SRC


def test_plan_task_help_matches_new_cadence():
    """`--no-upload` 的帮助文案不该再宣称按小时节流。"""
    assert "25 分钟节流" in COLLECT_SRC


# ---------------------------------------------------------------- 行为断言

def test_round_after_one_collect_cycle_is_not_throttled(tmp_path):
    """采集过了一轮（31 分钟）后必须真的上传，而不是因 interval 跳过。"""
    _write_cfg(tmp_path)
    _write_state(tmp_path, age_sec=31 * 60)

    result = price_upload.tick(str(tmp_path))

    assert not _skipped_by_interval(result), (
        "31 分钟前刚成功过就被节流跳过了：这正是「数据截止 10:31（57 分钟前）」的成因")


def test_round_within_interval_is_still_throttled(tmp_path):
    """同一轮窗口内的重复调用仍要挡住，避免手动连点把服务端打爆。"""
    _write_cfg(tmp_path)
    _write_state(tmp_path, age_sec=5 * 60)

    result = price_upload.tick(str(tmp_path))

    assert _skipped_by_interval(result)


def test_force_bypasses_interval(tmp_path):
    """`--upload` 手动触发必须无视节流（force=True）。"""
    _write_cfg(tmp_path)
    _write_state(tmp_path, age_sec=10)

    result = price_upload.upload_all(str(tmp_path), force=True)

    assert not _skipped_by_interval(result)


def test_next_upload_at_uses_configured_interval(tmp_path):
    """nextUploadAt 必须按配置值推算，而不是写死的 3600。"""
    _write_cfg(tmp_path, minIntervalSec=1500)
    at = _write_state(tmp_path, age_sec=5 * 60)

    got = price_upload.next_upload_at(str(tmp_path))
    assert got is not None

    base = datetime.datetime.fromisoformat(at)
    expect = (base + datetime.timedelta(seconds=1500)).isoformat(timespec="seconds")
    assert got == expect


def test_disabled_upload_short_circuits_before_interval(tmp_path):
    """关掉上传时理由必须是 disabled，不能误报成 interval（排查时容易带偏）。"""
    _write_cfg(tmp_path, enabled=False)
    _write_state(tmp_path, age_sec=5 * 60)

    result = price_upload.tick(str(tmp_path))

    assert result.get("skipped") is True
    assert result.get("reason") == "disabled"
