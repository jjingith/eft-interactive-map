# -*- coding: utf-8 -*-
"""R222：历史曲线接上「真正在长的那份数据」——采集器快照库。

背景（事故现场）：
  `js/market.js` 的空态写着「采集脚本每次成功抓取会在 data/flea-price-history/
  落一份快照」，但 `tools/price_collect.py` 从来不写这个目录；它写的是
  `<root>/collect/snapshots/<mode>/<YYYY-MM-DD>/<HHMMSS>.json.gz`。
  而 `price_history.py` 只读前者，于是本机明明躺着 78 份真实快照，界面却一直说
  「还没有历史快照」。

本文件守住四条不变量：
1. 采集器快照库能被读到，且只读该模式的目录（不跨模式）；
2. 两个来源合并后按时间排序、同一时间戳只算一份；
3. 坏文件只记 skipped，不影响同一批里的好文件；缺物品记 missing，不编点；
4. 当前模式一份都没有时，告诉前端「别的模式有」，而不是笼统说「没有快照」。
"""
from __future__ import annotations

import datetime
import gzip
import json
import os

import pytest

import collector_prices
import price_collect
import price_history

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TZ = datetime.timezone(datetime.timedelta(hours=8))
NOW = datetime.datetime(2026, 11, 10, 12, 0, tzinfo=TZ)


def _read(rel: str) -> str:
    with open(os.path.join(ROOT, rel), "r", encoding="utf-8") as fh:
        return fh.read()


@pytest.fixture(autouse=True)
def _fresh_cache():
    price_history.clear_cache()
    yield
    price_history.clear_cache()


def _root(tmp_path) -> str:
    root = str(tmp_path)
    os.makedirs(os.path.join(root, "data"), exist_ok=True)
    return root


def _write_gz(collector_root: str, mode: str, day: str, hhmmss: str, items: dict,
              spaced: bool = False) -> str:
    """按采集器的真实目录约定落一份 gz 快照。"""
    directory = os.path.join(collector_root, "collect", "snapshots", mode, day)
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, hhmmss + ".json.gz")
    doc = {
        "schema": 1,
        "mode": mode,
        "priceMode": "pvp",
        "snapshotAt": "%sT%s:%s:%s+08:00" % (day, hhmmss[:2], hhmmss[2:4], hhmmss[4:]),
        "counts": {"itemsWithPrice": len(items)},
        "items": items,
    }
    raw = json.dumps(doc, ensure_ascii=False,
                     separators=None if spaced else (",", ":")).encode("utf-8")
    with open(path, "wb") as fh:
        fh.write(gzip.compress(raw, 6))
    return path


def _write_archive(root: str, name: str, when: str, items: dict, game_mode: str = "regular"):
    directory = os.path.join(root, "data", "flea-price-history")
    os.makedirs(directory, exist_ok=True)
    with open(os.path.join(directory, name), "w", encoding="utf-8") as fh:
        json.dump({"schema": 1, "date": when[:10], "snapshotAt": when,
                   "gameMode": game_mode, "priceMode": "pvp", "items": items}, fh)
    index_path = os.path.join(directory, "index.json")
    entries = []
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as fh:
            entries = json.load(fh).get("entries") or []
    entries.append({"file": name, "date": when[:10], "snapshotAt": when,
                    "gameMode": game_mode, "priceMode": "pvp"})
    with open(index_path, "w", encoding="utf-8") as fh:
        json.dump({"schema": 1, "updatedAt": when, "keepDays": 90, "entries": entries}, fh)


def test_collector_entries_reads_gz_snapshots_in_time_order(tmp_path, monkeypatch):
    collector = str(tmp_path / "collector")
    monkeypatch.setenv("EFT_PRICE_ROOT", collector)
    _write_gz(collector, "regular", "2026-11-10", "110000", {"a": {"l": 3}})
    _write_gz(collector, "regular", "2026-11-09", "233000", {"a": {"l": 2}})
    _write_gz(collector, "regular", "2026-11-10", "103000", {"a": {"l": 1}})
    # 非快照文件必须被忽略
    with open(os.path.join(collector, "collect", "snapshots", "regular",
                           "2026-11-10", "notes.txt"), "w", encoding="utf-8") as fh:
        fh.write("x")

    picked = price_history.collector_entries("regular", 7, NOW)
    stamps = [when.strftime("%m-%d %H:%M:%S") for when, _ in picked]
    assert stamps == ["11-09 23:30:00", "11-10 10:30:00", "11-10 11:00:00"]


def test_collector_entries_respects_days_window(tmp_path, monkeypatch):
    collector = str(tmp_path / "collector")
    monkeypatch.setenv("EFT_PRICE_ROOT", collector)
    _write_gz(collector, "regular", "2026-11-08", "120000", {"a": {"l": 1}})
    _write_gz(collector, "regular", "2026-11-10", "110000", {"a": {"l": 2}})
    one_day = price_history.collector_entries("regular", 1, NOW)
    assert len(one_day) == 1, "24h 窗口不能把 11-08 的快照算进来"
    assert len(price_history.collector_entries("regular", 7, NOW)) == 2


def test_collector_source_can_be_disabled_with_empty_env(tmp_path, monkeypatch):
    collector = str(tmp_path / "collector")
    _write_gz(collector, "regular", "2026-11-10", "110000", {"a": {"l": 2}})
    monkeypatch.setenv("EFT_PRICE_ROOT", "")
    assert price_history.collector_root() == ""
    assert price_history.collector_entries("regular", 7, NOW) == []


def test_series_merges_archive_and_collector_points(tmp_path, monkeypatch):
    root = _root(tmp_path)
    collector = str(tmp_path / "collector")
    monkeypatch.setenv("EFT_PRICE_ROOT", collector)
    _write_archive(root, "2026-11-08T144256.json", "2026-11-08T14:42:56+08:00",
                   {"item-a": {"l": 1000, "a": 1200}})
    _write_gz(collector, "regular", "2026-11-10", "110000", {"item-a": {"l": 1300}})
    _write_gz(collector, "regular", "2026-11-10", "113000", {"item-a": {"l": 1400}})

    out = price_history.series(root, "regular", ["item-a"], 7, now=NOW)
    series = out["series"]["item-a"]
    assert series["count"] == 3
    assert [p[1] for p in series["points"]] == [1000, 1300, 1400]
    assert out["sources"] == {"fleaHistory": 1, "collector": 2}
    assert out["snapshotsUsed"] == 3
    assert out["error"] is None


def test_series_does_not_double_count_same_timestamp(tmp_path, monkeypatch):
    root = _root(tmp_path)
    collector = str(tmp_path / "collector")
    monkeypatch.setenv("EFT_PRICE_ROOT", collector)
    _write_archive(root, "2026-11-10T110000.json", "2026-11-10T11:00:00+08:00",
                   {"item-a": {"l": 999}})
    _write_gz(collector, "regular", "2026-11-10", "110000", {"item-a": {"l": 1300}})

    out = price_history.series(root, "regular", ["item-a"], 7, now=NOW)
    series = out["series"]["item-a"]
    assert series["count"] == 1, "同一时间戳只能算一份，否则样本数会灌水"
    assert series["points"][0][1] == 1300, "同一时间戳优先用采集器那份（更新更全）"
    assert out["snapshotsUsed"] == 1


def test_series_never_mixes_modes(tmp_path, monkeypatch):
    root = _root(tmp_path)
    collector = str(tmp_path / "collector")
    monkeypatch.setenv("EFT_PRICE_ROOT", collector)
    _write_gz(collector, "regular", "2026-11-10", "110000", {"item-a": {"l": 1300}})
    _write_gz(collector, "pve", "2026-11-10", "110000", {"item-a": {"l": 77}})

    regular = price_history.series(root, "regular", ["item-a"], 7, now=NOW)
    pve = price_history.series(root, "pve", ["item-a"], 7, now=NOW)
    assert [p[1] for p in regular["series"]["item-a"]["points"]] == [1300]
    assert [p[1] for p in pve["series"]["item-a"]["points"]] == [77]


def test_series_survives_broken_gz_and_missing_items(tmp_path, monkeypatch):
    root = _root(tmp_path)
    collector = str(tmp_path / "collector")
    monkeypatch.setenv("EFT_PRICE_ROOT", collector)
    good = _write_gz(collector, "regular", "2026-11-10", "110000", {"item-a": {"l": 1300}})
    _write_gz(collector, "regular", "2026-11-10", "113000", {"other": {"l": 5}})
    broken = os.path.join(os.path.dirname(good), "120000.json.gz")
    with open(broken, "wb") as fh:
        fh.write(b"not a gzip stream")

    out = price_history.series(root, "regular", ["item-a"], 7, now=NOW)
    assert [p[1] for p in out["series"]["item-a"]["points"]] == [1300]
    assert "120000.json.gz" in out["skipped"]

    missing = price_history.series(root, "regular", ["nope"], 7, now=NOW)
    assert missing["missing"] == ["nope"]
    assert missing["series"] == {}


def test_series_tells_frontend_which_modes_have_snapshots(tmp_path, monkeypatch):
    root = _root(tmp_path)
    collector = str(tmp_path / "collector")
    monkeypatch.setenv("EFT_PRICE_ROOT", collector)
    _write_gz(collector, "pve", "2026-11-10", "110000", {"item-a": {"l": 1}})
    _write_gz(collector, "pve", "2026-11-10", "113000", {"item-a": {"l": 2}})

    out = price_history.series(root, "regular", ["item-a"], 7, now=NOW)
    assert out["snapshotsUsed"] == 0
    assert out["availableModes"] == {"pve": 2}
    assert out["error"] is None, "有别的模式的数据时不能说 no-index"


def test_series_still_says_no_index_when_nothing_anywhere(tmp_path, monkeypatch):
    root = _root(tmp_path)
    monkeypatch.setenv("EFT_PRICE_ROOT", str(tmp_path / "empty-collector"))
    out = price_history.series(root, "regular", ["item-a"], 7, now=NOW)
    assert out["error"] == "no-index"
    assert out["snapshotsUsed"] == 0
    assert "availableModes" not in out


def test_series_marks_truncation_instead_of_silently_dropping(tmp_path, monkeypatch):
    root = _root(tmp_path)
    collector = str(tmp_path / "collector")
    monkeypatch.setenv("EFT_PRICE_ROOT", collector)
    monkeypatch.setattr(price_history, "COLLECTOR_MAX_FILES", 2)
    for hh in ("100000", "110000", "113000"):
        _write_gz(collector, "regular", "2026-11-10", hh, {"item-a": {"l": 1}})

    out = price_history.series(root, "regular", ["item-a"], 7, now=NOW)
    assert out["truncated"] is True
    assert out["collectorWindowTotal"] == 3
    assert out["sources"]["collector"] == 2
    assert out["series"]["item-a"]["count"] == 2


def test_gz_extraction_is_robust_to_spaced_json(tmp_path, monkeypatch):
    root = _root(tmp_path)
    collector = str(tmp_path / "collector")
    monkeypatch.setenv("EFT_PRICE_ROOT", collector)
    # json.dump 默认格式（冒号后有空格）也要能抠出来
    _write_gz(collector, "regular", "2026-11-10", "110000",
              {"item-a": {"l": 1300, "a": 1500}}, spaced=True)
    out = price_history.series(root, "regular", ["item-a"], 7, now=NOW)
    assert out["series"]["item-a"]["points"][0] == ["2026-11-10T11:00:00+08:00", 1300, 1500]


def test_collector_contract_matches_collector_module():
    """目录约定必须和采集器一致：写的那头改了，读的这头要一起改。"""
    assert price_history.COLLECTOR_DATA_DIRNAME == price_collect.DATA_DIRNAME
    assert price_collect.APP_NAME == "EFTPrice"
    assert collector_prices.root_dir().endswith("EFTPrice")


def test_frontend_copy_is_truthful_about_where_snapshots_land():
    js = _read("js/market.js")
    # 旧文案把「采集脚本会写 data/flea-price-history/」当事实，实际从来不写
    assert "采集脚本每次成功抓取会在 data/flea-price-history/ 落一份快照" not in js
    assert "EFТPrice" not in js  # 防西里尔字母同形异码
    # R278：曲线改成「本机快照 + 云端历史」双来源后，文案必须说清两条来源，
    # 而不是继续教用户去 %LOCALAPPDATA% 里数文件。
    assert "采集机上传到云端" in js
    assert "云端历史是会员数据" in js
    # 三种空态必须分开说
    assert "当前模式还没有历史快照" in js
    assert "所选区间没有历史快照" in js
    assert "还没有历史快照" in js
    assert "availableModes" in js
    # 仍然不跨模式、不补点
    assert "不拿其他模式的价格顶替" in js
    assert "不插值" in js
