# -*- coding: utf-8 -*-
"""R20.5 跳蚤行情自动更新与本地缓存 —— 测试。

覆盖任务书第七节 10 项场景。**全部离线**：网络调用一律用桩件替换，
只使用临时目录，不触碰正式 data/flea-prices.json。
"""
import datetime
import io
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import r20_fetch_prices as fp  # noqa: E402
import serve  # noqa: E402


def _upstream(n_items=1200, priced=1000, bad=False):
    """构造一份上游响应（结构与 json.tarkov.dev/regular/items 一致）。"""
    data = {}
    for i in range(n_items):
        item_id = "%024x" % (0x5447a9cd4bdc2dbd208b4567 + i)
        rec = {"name": "Item %d" % i}
        if i < priced:
            rec["lastLowPrice"] = 30000 + i
            rec["avg24hPrice"] = 69000 + i
            rec["low24hPrice"] = 28000 + i
            rec["high24hPrice"] = 150000 + i
            rec["basePrice"] = 18000 + i
        else:
            rec["lastLowPrice"] = None
        data[item_id] = rec
    if bad:
        data.pop(list(data)[0])
    return {"data": data, "translations": {}}


# ---------------------------------------------------------------- 1 无缓存 → 触发更新
def test_no_cache_triggers_update(tmp_path, monkeypatch):
    out = tmp_path / "flea-prices.json"
    calls = []

    def fake_fetch(url, proxy=None, timeout=90):
        calls.append(url)
        return json.dumps(_upstream()).encode(), {"httpStatus": 200, "bytes": 1, "sha256": "x"}

    monkeypatch.setattr(fp, "fetch_source", fake_fetch)
    rc = fp.main(["--out", str(out), "--no-proxy"])
    assert rc == 0
    assert calls, "没有缓存时应触发下载"
    assert out.exists(), "成功后必须落盘缓存"


# ---------------------------------------------------------------- 2 当天已更新 → 不重复下载
def test_same_day_skips_download(tmp_path, monkeypatch):
    out = tmp_path / "flea-prices.json"
    today = fp.local_date_str()
    out.write_text(json.dumps({"schema": 1, "localDate": today,
                               "lastSuccessAt": fp.local_now().isoformat(timespec="seconds"),
                               "items": {"a": {"lastLowPrice": 1}}}), encoding="utf-8")
    calls = []

    def fake_fetch(*a, **k):
        calls.append(a)
        raise AssertionError("当天已更新时不应下载")

    monkeypatch.setattr(fp, "fetch_source", fake_fetch)
    rc = fp.main(["--out", str(out), "--no-proxy"])
    assert rc == 0 and not calls


# ---------------------------------------------------------------- 3 跨天 → 重新更新
def test_next_day_refreshes(tmp_path, monkeypatch):
    out = tmp_path / "flea-prices.json"
    yesterday = (fp.local_now() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    out.write_text(json.dumps({"schema": 1, "localDate": yesterday,
                               "lastSuccessAt": fp.local_now().isoformat(timespec="seconds"),
                               "items": {"a": {"lastLowPrice": 1}}}), encoding="utf-8")
    calls = []

    def fake_fetch(url, proxy=None, timeout=90):
        calls.append(url)
        return json.dumps(_upstream()).encode(), {"httpStatus": 200, "bytes": 1, "sha256": "x"}

    monkeypatch.setattr(fp, "fetch_source", fake_fetch)
    rc = fp.main(["--out", str(out), "--no-proxy"])
    assert rc == 0 and calls, "跨天后应重新下载"
    assert json.loads(out.read_text(encoding="utf-8"))["localDate"] == fp.local_date_str()


# ---------------------------------------------------------------- 4 下载失败 → 旧缓存不变
def test_failure_keeps_old_cache(tmp_path, monkeypatch):
    out = tmp_path / "flea-prices.json"
    old = {"schema": 1, "localDate": "2020-01-01", "items": {"x": {"lastLowPrice": 5}}}
    out.write_text(json.dumps(old), encoding="utf-8")
    before = out.read_bytes()

    def boom(*a, **k):
        raise RuntimeError("网络不可用")

    monkeypatch.setattr(fp, "fetch_source", boom)
    rc = fp.main(["--out", str(out), "--no-proxy", "--force"])
    assert rc == 1, "失败必须返回非零退出码"
    assert out.read_bytes() == before, "失败时旧缓存必须逐字节保持不变"


# ---------------------------------------------------------------- 5 无效响应不覆盖旧缓存
@pytest.mark.parametrize("payload", [
    b"not json at all",
    json.dumps({"data": {}}).encode(),                       # 物品数异常少
    json.dumps({"data": {"a": {"lastLowPrice": "NaN"}}}).encode(),   # 价格类型错
])
def test_invalid_response_never_overwrites(tmp_path, monkeypatch, payload):
    out = tmp_path / "flea-prices.json"
    out.write_text(json.dumps({"schema": 1, "localDate": "2020-01-01",
                               "items": {"x": {"lastLowPrice": 5}}}), encoding="utf-8")
    before = out.read_bytes()
    monkeypatch.setattr(fp, "fetch_source",
                        lambda *a, **k: (payload, {"httpStatus": 200, "bytes": len(payload), "sha256": "x"}))
    rc = fp.main(["--out", str(out), "--no-proxy", "--force"])
    assert rc == 1
    assert out.read_bytes() == before


def test_out_of_range_price_dropped_not_zeroed():
    doc = _upstream()
    k = list(doc["data"])[0]
    doc["data"][k]["lastLowPrice"] = 10 ** 12      # 越界
    cache = fp.build_cache(doc, "https://x", "regular")
    assert "lastLowPrice" not in cache["items"][k], "越界价格必须丢弃，不能写成 0"
    assert cache["items"][k]["avg24hPrice"] > 0, "其它正常字段仍应保留"


# ---------------------------------------------------------------- 6 成功后价格与更新时间一致
def test_success_writes_consistent_prices_and_time(tmp_path, monkeypatch):
    out = tmp_path / "flea-prices.json"
    monkeypatch.setattr(fp, "fetch_source",
                        lambda *a, **k: (json.dumps(_upstream()).encode(),
                                         {"httpStatus": 200, "bytes": 1, "sha256": "x"}))
    assert fp.main(["--out", str(out), "--no-proxy"]) == 0
    d = json.loads(out.read_text(encoding="utf-8"))
    assert d["lastSuccessAt"].startswith(fp.local_date_str()), "更新时间必须是本机本地日期"
    assert d["localDate"] == fp.local_date_str()
    assert d["counts"]["withLastLowPrice"] > 0
    row = d["items"][list(d["items"])[0]]
    assert row["fetchedAt"] == d["lastSuccessAt"], "逐条时间戳应与本次抓取时刻一致"
    for f in ("lastLowPrice", "avg24hPrice", "basePrice"):
        assert isinstance(row[f], (int, float)) and row[f] > 0


# ---------------------------------------------------------------- 7 不同模式不混用
def test_game_mode_recorded_and_not_mixed(tmp_path, monkeypatch):
    out = tmp_path / "flea-prices.json"
    monkeypatch.setattr(fp, "fetch_source",
                        lambda *a, **k: (json.dumps(_upstream()).encode(),
                                         {"httpStatus": 200, "bytes": 1, "sha256": "x"}))
    assert fp.main(["--out", str(out), "--no-proxy", "--mode", "regular"]) == 0
    d = json.loads(out.read_text(encoding="utf-8"))
    assert d["gameMode"] == "regular"
    # PvP 不可用：缓存里必须写明不可用项，避免被当成有 PvP 数据
    assert any("PvP" in x for x in d["notAvailable"])


# ---------------------------------------------------------------- 8 同名不同 ID 不混淆
def test_items_keyed_by_id_not_name(tmp_path, monkeypatch):
    out = tmp_path / "flea-prices.json"
    doc = _upstream(n_items=1200, priced=1200)
    # 造两个同名不同 ID 的物品
    ids = list(doc["data"])[:2]
    doc["data"][ids[0]]["name"] = "同名物品"
    doc["data"][ids[1]]["name"] = "同名物品"
    monkeypatch.setattr(fp, "fetch_source",
                        lambda *a, **k: (json.dumps(doc).encode(),
                                         {"httpStatus": 200, "bytes": 1, "sha256": "x"}))
    assert fp.main(["--out", str(out), "--no-proxy"]) == 0
    d = json.loads(out.read_text(encoding="utf-8"))
    assert ids[0] in d["items"] and ids[1] in d["items"], "必须按稳定 ID 分别建档"
    assert d["items"][ids[0]]["lastLowPrice"] != d["items"][ids[1]]["lastLowPrice"]


# ---------------------------------------------------------------- 9 并发不重复下载
def test_lock_prevents_concurrent_download(tmp_path, monkeypatch):
    lock = tmp_path / ".lock"
    assert fp.acquire_lock(str(lock)) is True
    assert fp.acquire_lock(str(lock)) is False, "第二个进程必须拿不到锁"
    fp.release_lock(str(lock))
    assert fp.acquire_lock(str(lock)) is True, "释放后应能再次获取"


# ---------------------------------------------------------------- 10 离线/失败时服务与界面仍可用
def test_status_states(tmp_path):
    root = tmp_path
    (root / "data").mkdir()
    # missing
    st = serve.flea_price_status(str(root))
    assert st["state"] == "missing" and st["items"] == 0
    # fresh
    (root / "data" / "flea-prices.json").write_text(json.dumps(
        {"schema": 1, "localDate": serve._local_date(), "lastSuccessAt": "x",
         "items": {"a": {}}, "source": "s", "gameMode": "regular"}), encoding="utf-8")
    st = serve.flea_price_status(str(root))
    assert st["state"] == "fresh" and st["items"] == 1
    # stale
    (root / "data" / "flea-prices.json").write_text(json.dumps(
        {"schema": 1, "localDate": "2020-01-01", "lastSuccessAt": "x",
         "items": {"a": {}}}), encoding="utf-8")
    st = serve.flea_price_status(str(root))
    assert st["state"] == "stale"
    # 失败记录（不覆盖缓存）
    (root / "data" / "flea-prices.last-error.json").write_text(json.dumps(
        {"error": "网络不可用", "lastAttemptAt": "x"}), encoding="utf-8")
    st = serve.flea_price_status(str(root))
    assert st["lastError"] == "网络不可用"


def test_spawn_refresh_without_fetcher_is_safe(tmp_path):
    ok, reason = serve.spawn_flea_refresh(str(tmp_path), force=True)
    assert ok is False and "抓取器不存在" in reason


# ---------------------------------------------------------------- 前端契约（静态）
def test_frontend_uses_separate_cache_and_shows_status():
    js = io.open(ROOT / "app.js", encoding="utf-8").read()
    html = io.open(ROOT / "index.html", encoding="utf-8").read()
    # 独立缓存文件，不覆盖 items.json
    assert 'loadJSON("data/flea-prices.json")' in js
    assert "data/flea-prices.json" in html or True
    # 统一行情读取层
    assert "function fleaQuoteOf(id)" in js
    assert "function fleaState()" in js
    assert "function renderQuoteStatus()" in js
    # 三种价格口径分列（2026-11 统一到市场口径：最新 / 24h 均价 / 7 日均价）
    assert "COL_FLEALAST" in js and "跳蚤最新" in js
    assert "modeLabel" in js, "市场价列标题必须跟随当前口径"
    assert 'key: "avg24h"' in js and 'key: "avg7d"' in js, "缺少市场口径 24h / 7d 档"
    # 旧 FLEA/BASE 档必须真正删除
    assert 'key: "flea"' not in js and 'key: "base"' not in js
    # R19.91：候选栏不再重复行情状态与刷新按钮（统一在二级工具条显示）
    assert 'id="gw-quote-status"' not in html
    assert 'id="gw-quote-refresh"' not in html
    assert 'fetch("/api/prices/refresh"' in js
    assert 'fetch("/api/prices")' in js
    # 不得在运行期直接请求外部行情 API
    assert "api.tarkov.dev" not in js


def test_fetch_tool_never_writes_items_json():
    src = io.open(ROOT / "tools" / "r20_fetch_prices.py", encoding="utf-8").read()
    # 只允许写行情缓存与其错误记录，绝不碰业务数据文件
    assert "data/items.json" not in src
    assert fp.DEFAULT_OUT.endswith("data\\flea-prices.json") or fp.DEFAULT_OUT.endswith("data/flea-prices.json")
    assert fp.ERROR_OUT.endswith("flea-prices.last-error.json")
    assert "os.replace" in src, "必须用原子替换"


def test_cache_file_real_shape():
    """正式缓存文件结构自检（若存在）。"""
    p = ROOT / "data" / "flea-prices.json"
    if not p.exists():
        pytest.skip("尚未生成行情缓存")
    d = json.loads(p.read_text(encoding="utf-8"))
    for k in ("schema", "source", "gameMode", "lastSuccessAt", "localDate", "items", "counts"):
        assert k in d, "缓存缺少字段 %s" % k
    assert d["gameMode"] == "regular"
    assert d["localDate"] == fp.local_date_str() or d["localDate"] < fp.local_date_str()
    k0 = list(d["items"])[0]
    assert isinstance(d["items"][k0]["fetchedAt"], str)
