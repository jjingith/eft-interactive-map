# -*- coding: utf-8 -*-
"""R275：采集机抗故障能力。

事故现场（2026-11-13）：上游 17 MB 响应反复被截断，采集进程被打崩，
残留的 .price-collect.lock 又永远清不掉，导致连续多轮「另一个进程持锁」，
云端行情断更 2 小时 19 分，前端弹出「云端行情已过期」。

守住四条不变量：
1. 新鲜锁仍然互斥，陈旧锁必须能被回收；
2. IncompleteRead 会重试，重试成功就正常返回；
3. 重试耗尽后转成 OSError，fetch_mode 记成结构化失败而不是打崩进程；
4. 采集过程中抛异常时，轮末仍会尝试上传已落盘的快照，且锁会被释放。
"""
from __future__ import annotations

import argparse
import http.client
import os
import time
from pathlib import Path

import pytest

import live_prices
import price_collect

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def fast_retry(monkeypatch):
    monkeypatch.setattr(live_prices, "FETCH_RETRY_SLEEP", 0)


class _TruncatedResponse:
    status = 200
    headers = {}

    def __init__(self, fail_times: int):
        self.fail_times = fail_times
        self.reads = 0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        self.reads += 1
        if self.reads <= self.fail_times:
            raise http.client.IncompleteRead(b"abc", 17_000_000)
        return b'{"data":{"items":{}}}'


class _Opener:
    def __init__(self, fail_times: int):
        self.response = _TruncatedResponse(fail_times)
        self.requests = 0

    def open(self, req, timeout=None):
        self.requests += 1
        return self.response


# ---------------------------------------------------------------- 锁

def test_fresh_lock_blocks_second_acquirer(tmp_path):
    path = tmp_path / "collect.lock"
    assert live_prices.acquire_lock(str(path)) is True
    assert live_prices.acquire_lock(str(path)) is False
    live_prices.release_lock(str(path))
    assert live_prices.acquire_lock(str(path)) is True


def test_stale_lock_is_reclaimed(tmp_path):
    path = tmp_path / "collect.lock"
    assert live_prices.acquire_lock(str(path)) is True
    old = time.time() - 2000
    os.utime(path, (old, old))
    # 旧实现在这里会因为 O_EXCL 撞上残留文件而永远返回 False
    assert live_prices.acquire_lock(str(path), stale_seconds=900) is True
    assert live_prices.acquire_lock(str(path), stale_seconds=900) is False
    live_prices.release_lock(str(path))


# ---------------------------------------------------------------- 截断重试

def test_incomplete_read_retries_then_becomes_oserror(fast_retry, monkeypatch):
    opener = _Opener(fail_times=99)
    monkeypatch.setattr(live_prices, "build_opener", lambda proxy=None: opener)
    with pytest.raises(OSError) as caught:
        live_prices.fetch_url("https://example.test/items")
    assert opener.requests == live_prices.FETCH_ATTEMPTS
    assert "IncompleteRead" in str(caught.value)


def test_incomplete_read_recovers_on_second_attempt(fast_retry, monkeypatch):
    opener = _Opener(fail_times=1)
    monkeypatch.setattr(live_prices, "build_opener", lambda proxy=None: opener)
    result = live_prices.fetch_url("https://example.test/items")
    assert opener.requests == 2
    assert result.body == b'{"data":{"items":{}}}'


def test_fetch_mode_records_truncated_download_without_crashing(tmp_path, fast_retry, monkeypatch):
    monkeypatch.setenv(live_prices.CACHE_DIR_ENV, str(tmp_path / "cache"))
    opener = _Opener(fail_times=99)
    monkeypatch.setattr(live_prices, "build_opener", lambda proxy=None: opener)
    result = live_prices.fetch_mode("regular", proxy=None, force=True)
    assert isinstance(result, dict)
    assert result["ok"] is False
    assert result["exitCode"] == 1
    assert "上游下载中断" in result["message"]


# ---------------------------------------------------------------- 崩溃兜底上传

def test_collect_once_uploads_even_when_a_mode_crashes(tmp_path, monkeypatch):
    uploads: list[tuple[str, object]] = []
    monkeypatch.setattr(price_collect, "migrate_legacy", lambda root: None)
    monkeypatch.setattr(price_collect, "load_state", lambda root: {"modes": {}})
    for name in ("save_state", "update_index", "clear_error", "_write_heartbeat"):
        monkeypatch.setattr(price_collect, name, lambda *a, **k: None)

    def boom(*_a, **_k):
        raise RuntimeError("上游炸了")

    monkeypatch.setattr(price_collect, "collect_mode", boom)
    monkeypatch.setattr(price_collect, "_auto_upload",
                        lambda root, args: uploads.append((root, args)))

    args = argparse.Namespace(
        root=str(tmp_path / "collector"), no_mirror=True, keep_days=90, raw_keep=48,
        proxy=None, mode="regular", no_upload=False,
    )
    with pytest.raises(RuntimeError, match="上游炸了"):
        price_collect.collect_once(args)

    assert len(uploads) == 1
    lock = os.path.join(
        price_collect.data_dir(price_collect.root_dir(args.root)), price_collect.LOCK_NAME
    )
    assert not os.path.exists(lock), "崩溃后不能残留采集锁"


def test_top_level_crash_handler_still_tries_upload():
    src = (ROOT / "tools" / "price_collect.py").read_text(encoding="utf-8")
    assert "price_upload.tick(root_dir(None))" in src
    body = src.split("def collect_once(", 1)[1].split("\ndef _auto_upload(", 1)[0]
    assert body.count("_auto_upload(app_root, args)") == 1
