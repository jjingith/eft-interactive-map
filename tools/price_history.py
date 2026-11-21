# -*- coding: utf-8 -*-
"""R218/R222 历史价格序列（只读、仅标准库、只在本机 BFF 调用）。

数据来源是两个**本机**目录，除此之外不联网、不读云端、不插值、不补点：

1. `data/flea-price-history/`：构建期 `tools/r20_fetch_prices.py` 每次成功抓取
   落的明文快照 + `index.json` 清单（开发机 / 打包随附）；
2. 采集器自己的快照库（R222 起）：`<collector root>/collect/snapshots/<模式>/
   <YYYY-MM-DD>/<HHMMSS>.json.gz`，每 30 分钟一份，保留 90 天。
   `<collector root>` = `%LOCALAPPDATA%\\EFTPrice`，`EFT_PRICE_ROOT` 可覆盖；
   把该变量显式设成空串即关闭这个来源（测试用）。

日常运行时第 2 个来源才是真正在长的那一份：采集器一直在落快照，而
`data/flea-price-history/` 只有构建期抓取时才写。打包后的客户端目录里
通常没有 `data/flea-price-history/`，所以只认第 1 个来源的旧实现会一直显示
「还没有历史快照」——这正是 R222 要修的。

契约（`series`）：
  {"ok": true, "mode": "regular", "days": 7, "requested": ["<itemId>"],
   "windowStart": "2026-11-02T15:00:00+08:00" | null,
   "indexUpdatedAt": "...", "snapshotsTotal": 12, "snapshotsUsed": 9,
   "sources": {"fleaHistory": 1, "collector": 9},   # 窗口内两份来源各用了多少
   "truncated": false,                # 窗口内快照超过上限、只画了最近 COLLECTOR_MAX_FILES 份
   "collectorWindowTotal": 9,         # 窗口内采集器快照总份数（截断前）
   "coverageDays": 7, "firstAt": "...", "lastAt": "...",
   "series": {"<itemId>": {"points": [["<iso>", lastLow, avg24h], ...],
                            "count": 9, "firstAt": "...", "lastAt": "...",
                            "low": 123, "high": 456}},
   "missing": ["<itemId>"],           # 窗口内有快照但该物品没有价格
   "skipped": ["2026-11-07T090000.json"],  # 文件缺失 / 读不动
   "availableModes": {"pve": 76},     # 仅「当前模式一份都没有」时出现
   "error": null | "no-index" | "no-item"}

  · 单个物品在窗口内没有任何快照 → 不出现在 series，也不出现在 missing。
  · points 里的价格可能是 null（该字段缺失），前端自行回退，绝不估。
  · 同一个时间戳在两个来源里都有 → 只算一份（不让重复快照把样本数灌水）。
"""
from __future__ import annotations

import datetime
import gzip
import json
import os
import re
import threading
from typing import Any, Iterable

try:  # 与采集器共用同一套目录约定（模式别名 / %LOCALAPPDATA% / EFT_PRICE_ROOT）
    import collector_prices
except ImportError:  # pragma: no cover - 只在本机 BFF 里用，正常都能导入
    collector_prices = None

HISTORY_DIRNAME = "flea-price-history"
INDEX_NAME = "index.json"
MAX_DAYS = 90
MAX_ITEMS = 60
_CACHE_LIMIT = 8

# 采集器快照库（只读）
COLLECTOR_DATA_DIRNAME = "collect"
COLLECTOR_SNAPSHOT_DIRNAME = "snapshots"
COLLECTOR_MODES = ("regular", "pve", "pvps")
COLLECTOR_MAX_FILES = 2000       # 单次请求最多读多少份 gz，防「全部」区间把服务拖死
SNAPSHOT_NAME_RE = re.compile(r"^(\d{2})(\d{2})(\d{2})\.json\.gz$")
DAY_NAME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_GZ_ROW_CACHE_LIMIT = 512
_GZ_TEXT_CACHE_LIMIT = 24        # 缓存解压后的文本（按文件 mtime/size），避免同一 gz 重复解压

_snapshot_cache: dict[tuple[str, int, int], dict] = {}
_index_cache: dict[tuple[str, int], dict] = {}
_gz_row_cache: dict[tuple[str, int, int, str], Any] = {}
_gz_text_cache: dict[tuple[str, int, int], Any] = {}
_cache_lock = threading.Lock()


def history_dir(root: str) -> str:
    return os.path.join(root, "data", HISTORY_DIRNAME)


def collector_root() -> str:
    """采集器根目录；`EFT_PRICE_ROOT=""` 表示显式关闭这个来源（返回空串）。"""
    if "EFT_PRICE_ROOT" in os.environ:
        raw = os.environ.get("EFT_PRICE_ROOT") or ""
        raw = raw.strip()
        if not raw:
            return ""
        return os.path.abspath(raw)
    if collector_prices is not None:
        try:
            return collector_prices.root_dir()
        except Exception:  # noqa: BLE001 - 环境异常时按「没有采集器」处理
            return ""
    return ""


def collector_snapshot_dir(mode: str, root: str | None = None) -> str:
    base = collector_root() if root is None else root
    if not base:
        return ""
    return os.path.join(base, COLLECTOR_DATA_DIRNAME, COLLECTOR_SNAPSHOT_DIRNAME, mode)



def _parse_time(value) -> datetime.datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt


def _price(value) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not (0 < value < 100_000_000):
        return None
    return int(value) if float(value).is_integer() else value


def load_index(root: str) -> dict:
    """读 `index.json`（按 mtime 缓存）。任何异常都收敛成空清单。"""
    path = os.path.join(history_dir(root), INDEX_NAME)
    try:
        stat = os.stat(path)
    except OSError:
        return {"entries": [], "updatedAt": None, "keepDays": None, "error": "no-index"}
    key = (path, int(stat.st_mtime))
    with _cache_lock:
        cached = _index_cache.get(key)
    if cached is not None:
        return cached
    try:
        with open(path, "r", encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError):
        doc = {}
    entries = doc.get("entries") if isinstance(doc, dict) else None
    out = {
        "entries": [e for e in entries if isinstance(e, dict)] if isinstance(entries, list) else [],
        "updatedAt": doc.get("updatedAt") if isinstance(doc, dict) else None,
        "keepDays": doc.get("keepDays") if isinstance(doc, dict) else None,
        "error": None,
    }
    with _cache_lock:
        if len(_index_cache) > 4:
            _index_cache.clear()
        _index_cache[key] = out
    return out


def _load_snapshot(path: str) -> dict:
    """读单份历史快照（按 mtime + size 缓存，最多 8 份）。失败返回 {}。"""
    try:
        stat = os.stat(path)
    except OSError:
        return {}
    key = (path, int(stat.st_mtime), int(stat.st_size))
    with _cache_lock:
        cached = _snapshot_cache.get(key)
    if cached is not None:
        return cached
    try:
        with open(path, "r", encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError):
        doc = {}
    items = doc.get("items") if isinstance(doc, dict) else None
    out = items if isinstance(items, dict) else {}
    with _cache_lock:
        if len(_snapshot_cache) >= _CACHE_LIMIT:
            _snapshot_cache.pop(next(iter(_snapshot_cache)))
        _snapshot_cache[key] = out
    return out


def _entry_time(entry: dict) -> datetime.datetime | None:
    return _parse_time(entry.get("snapshotAt") or entry.get("generatedAt") or entry.get("date"))


def _collector_when(day: str, name: str, tzinfo) -> datetime.datetime | None:
    m = SNAPSHOT_NAME_RE.match(name)
    if not m or not DAY_NAME_RE.match(day):
        return None
    try:
        date = datetime.date.fromisoformat(day)
        return datetime.datetime(date.year, date.month, date.day,
                                 int(m.group(1)), int(m.group(2)), int(m.group(3)),
                                 tzinfo=tzinfo)
    except ValueError:
        return None


def collector_entries(mode: str, days: int, now: datetime.datetime,
                      limit: int | None = COLLECTOR_MAX_FILES):
    """采集器快照库里落在窗口内的 (时间, 路径)，按时间升序。

    目录约定与 `tools/price_collect.py` 完全一致：
    `<root>/collect/snapshots/<mode>/<YYYY-MM-DD>/<HHMMSS>.json.gz`。
    文件名就是本地时间戳，不解析文件内容就能定时间——省掉一次 gzip 解压。
    没有采集器 / 目录读不动 → 空列表，绝不抛。
    """
    base = collector_snapshot_dir(mode)
    if not base:
        return []
    try:
        day_names = os.listdir(base)
    except OSError:
        return []
    cutoff = now - datetime.timedelta(days=days) if days else None
    picked = []
    for day in day_names:
        if not DAY_NAME_RE.match(day):
            continue
        day_dir = os.path.join(base, day)
        if cutoff is not None:
            try:
                d = datetime.date.fromisoformat(day)
                day_end = datetime.datetime(d.year, d.month, d.day, 23, 59, 59,
                                            tzinfo=now.tzinfo)
            except ValueError:
                continue
            if day_end < cutoff:
                continue
        try:
            names = os.listdir(day_dir)
        except OSError:
            continue
        for name in names:
            when = _collector_when(day, name, now.tzinfo)
            if when is None:
                continue
            if cutoff is not None and when < cutoff:
                continue
            picked.append((when, os.path.join(day_dir, name)))
    picked.sort(key=lambda pair: pair[0])
    if limit is not None and len(picked) > limit:
        picked = picked[-limit:]
    return picked


def _gz_row(text: str, item_id: str):
    """从解压后的快照文本里只抠出目标物品那一行（不整体 json.loads）。"""
    needle = '"%s":' % item_id
    pos = text.find(needle)
    if pos < 0:
        return None
    pos += len(needle)
    while pos < len(text) and text[pos] in " \t\r\n":
        pos += 1
    try:
        row, _ = json.JSONDecoder().raw_decode(text, pos)
    except ValueError:
        return None
    return row if isinstance(row, dict) else None


def _gz_rows(path: str, item_id: str):
    """读一份采集器 gz 快照里某个物品的行；按 (路径, mtime, size, 物品) 缓存。

    返回 `(status, row)`：`status` 是 `ok`（文件读得动，行可能不存在 → row=None）
    或 `error`（文件读不动）。两者必须分开，否则「物品没挂单」会被误记成坏文件。
    """
    try:
        stat = os.stat(path)
    except OSError:
        return "error", None
    key = (path, int(stat.st_mtime), int(stat.st_size), item_id)
    with _cache_lock:
        cached = _gz_row_cache.get(key)
    if cached is not None:
        return cached
    try:
        with gzip.open(path, "rb") as fh:
            text = fh.read().decode("utf-8")
        out = ("ok", _gz_row(text, item_id))
    except (OSError, EOFError, ValueError):
        out = ("error", None)
    with _cache_lock:
        if len(_gz_row_cache) >= _GZ_ROW_CACHE_LIMIT:
            _gz_row_cache.pop(next(iter(_gz_row_cache)))
        _gz_row_cache[key] = out
    return out


def _gz_rows_batch(path: str, wanted):
    """R248：一次解压、批量取出所有目标物品的行。

    旧 `series()` 对每个 (快照文件, 物品) 组合调用 `_gz_rows` —— 同一个 gz 会被
    解压 `len(wanted)` 遍。实测 60 物品 × 142 份快照 ≈ 8500 次解压 ≈ 24 秒，
    OCR 本身只要 0.5~4 秒。批处理把复杂度从「文件数 × 物品数」降为「文件数」。

    返回 `(status, {item_id: row|None})`；status=error 表示文件读不动。
    """
    try:
        stat = os.stat(path)
    except OSError:
        return "error", {}
    key = (path, int(stat.st_mtime), int(stat.st_size))
    with _cache_lock:
        cached = _gz_text_cache.get(key)
    if cached is None:
        try:
            with gzip.open(path, "rb") as fh:
                text = fh.read().decode("utf-8")
            cached = ("ok", text)
        except (OSError, EOFError, ValueError):
            cached = ("error", "")
        with _cache_lock:
            if len(_gz_text_cache) >= _GZ_TEXT_CACHE_LIMIT:
                _gz_text_cache.pop(next(iter(_gz_text_cache)))
            _gz_text_cache[key] = cached
    status, text = cached
    if status == "error":
        return "error", {}
    return "ok", {item_id: _gz_row(text, item_id) for item_id in wanted}


def modes_with_snapshots(now: datetime.datetime, days: int, skip: str | None = None) -> dict:
    """其它模式各有多少份采集器快照——只用于「该模式还没有」时给出可行动的信息。"""
    out = {}
    for mode in COLLECTOR_MODES:
        if mode == skip:
            continue
        count = len(collector_entries(mode, days, now, limit=None))
        if count:
            out[mode] = count
    return out


def _mode_entries(root: str, mode: str, days: int, now: datetime.datetime):
    index = load_index(root)
    cutoff = None
    if days and days > 0:
        cutoff = now - datetime.timedelta(days=days)
    picked = []
    skipped = []
    for entry in index["entries"]:
        game_mode = str(entry.get("gameMode") or "").strip()
        if game_mode and game_mode != mode:
            continue
        when = _entry_time(entry)
        if when is None:
            skipped.append(str(entry.get("file") or "?"))
            continue
        if cutoff is not None and when < cutoff:
            continue
        name = str(entry.get("file") or "").strip()
        if not name or os.path.basename(name) != name:
            skipped.append(name or "?")
            continue
        picked.append((when, name))
    picked.sort(key=lambda pair: pair[0])
    total = sum(1 for e in index["entries"]
                if (not str(e.get("gameMode") or "").strip()
                    or str(e.get("gameMode") or "").strip() == mode))
    return picked, skipped, total, index


def series(root: str, mode: str, item_ids: Iterable[str], days: int = 7,
           now: datetime.datetime | None = None) -> dict:
    """返回若干物品在窗口内的真实快照序列；没有就明确说没有。"""
    now = now or datetime.datetime.now().astimezone()
    try:
        days = int(days)
    except (TypeError, ValueError):
        days = 7
    if days < 0:
        days = 0
    days = min(days, MAX_DAYS)

    requested = []
    for raw in item_ids:
        text = str(raw or "").strip()
        if text and text not in requested:
            requested.append(text)
        if len(requested) >= MAX_ITEMS:
            break

    index_entries, skipped, index_total, index = _mode_entries(root, mode, days, now)
    collected_all = collector_entries(mode, days, now, limit=None)
    collected = collected_all
    truncated = False
    if len(collected_all) > COLLECTOR_MAX_FILES:
        # 只取最近 N 份，但绝不说成「全都画了」——truncated 交给前端明示。
        collected = collected_all[-COLLECTOR_MAX_FILES:]
        truncated = True

    merged = [(when, "index", name) for when, name in index_entries]
    merged += [(when, "collector", path) for when, path in collected]
    merged.sort(key=lambda row: (row[0], row[1]))

    base = {
        "ok": True,
        "mode": mode,
        "days": days,
        "requested": requested,
        "windowStart": (now - datetime.timedelta(days=days)).isoformat(timespec="seconds")
        if days else None,
        "indexUpdatedAt": index.get("updatedAt"),
        "snapshotsTotal": index_total + len(collector_entries(mode, 0, now, limit=None)),
        "snapshotsUsed": 0,
        "sources": {"fleaHistory": len(index_entries), "collector": len(collected)},
        "truncated": truncated,
        "collectorWindowTotal": len(collected_all),
        "coverageDays": 0,
        "firstAt": None,
        "lastAt": None,
        "series": {},
        "missing": [],
        "skipped": skipped,
        "error": None,
    }
    if not merged:
        # 真正的一份都没有：把「别的模式有」这件事说清楚，前端才给得出可行动的话。
        other = modes_with_snapshots(now, days, skip=mode)
        if other:
            base["availableModes"] = other
        elif index.get("error") == "no-index":
            base["error"] = "no-index"
        return base
    if not requested:
        base["error"] = "no-item"
        return base

    wanted = set(requested)
    buckets: dict[str, list] = {item_id: [] for item_id in requested}
    seen_ts: dict[str, set] = {item_id: set() for item_id in requested}
    used_stamps: set = set()
    days_seen = set()
    first_at = None
    last_at = None

    for when, kind, ref in merged:
        stamp = when.isoformat(timespec="seconds")
        if stamp in used_stamps:
            continue
        if kind == "index":
            items = _load_snapshot(os.path.join(history_dir(root), ref))
            if not items:
                base["skipped"].append(ref)
                continue
            rows = {item_id: items.get(item_id) for item_id in wanted}
        else:
            # R248：整份 gz 只解压一次，批量取所有目标行（原来每个 id 解压一遍）
            status, rows = _gz_rows_batch(ref, wanted)
            if status == "error":
                base["skipped"].append(os.path.basename(ref))
                continue
        used_stamps.add(stamp)
        if first_at is None or stamp < first_at:
            first_at = stamp
        if last_at is None or stamp > last_at:
            last_at = stamp
        days_seen.add(when.date().isoformat())
        for item_id in wanted:
            row = rows.get(item_id)
            if not isinstance(row, dict):
                continue
            price_l = _price(row.get("l", row.get("lastLowPrice")))
            price_a = _price(row.get("a", row.get("avg24hPrice")))
            if price_l is None and price_a is None:
                continue
            if stamp in seen_ts[item_id]:
                continue
            seen_ts[item_id].add(stamp)
            buckets[item_id].append([stamp, price_l, price_a])

    for item_id in requested:
        points = buckets[item_id]
        if not points:
            # 窗口内有快照，但这个物品在每一份快照里都没有可用价格。
            base["missing"].append(item_id)
            continue
        lows = [p[1] for p in points if isinstance(p[1], (int, float))]
        base["series"][item_id] = {
            "points": points,
            "count": len(points),
            "firstAt": points[0][0],
            "lastAt": points[-1][0],
            "low": min(lows) if lows else None,
            "high": max(lows) if lows else None,
        }
    base["coverageDays"] = len(days_seen)
    base["firstAt"] = first_at
    base["lastAt"] = last_at
    base["snapshotsUsed"] = len(used_stamps)
    return base


def _stamp_key(stamp: str):
    """时间戳去重键：能解析成时间就用 epoch 秒，否则退回原字符串。

    本机快照的时间戳是**本地时区**（`2026-11-14T11:51:01+08:00`），云端存的是
    UTC（`2026-11-14T03:51:01+00:00`）——同一个瞬间、两种写法。按字符串比会
    把同一份采样算成两个点（图上叠一个竖线、count 灌水），所以统一换算成
    epoch 秒再比。
    """
    parsed = _parse_time(stamp)
    return int(parsed.timestamp()) if parsed is not None else stamp


def merge_cloud(payload: dict, cloud: dict | None, *, status: str = "ok") -> dict:
    """把云端单物品曲线并进本机结果（就地修改并返回 payload）。

    云端数据来自采集机每 30 分钟上传的快照，和本机采集器是同一批源数据；
    所以按**时间戳去重**合并——本机那份优先（它就在用户机器上，粒度最全），
    云端补齐本机没有的历史。这样「昨天才装的客户端」也能看到完整曲线。

    `status` 只用于让前端知道云端的处境：
      ok / no_data / member_required / offline / disabled / error
    绝不因为云端失败就把本机已有数据抹掉，也绝不拿云端数据冒充本机采样。
    """
    info = {"status": status, "points": 0, "snapshots": 0, "window_end": None}
    if isinstance(cloud, dict):
        try:
            info["snapshots"] = int(cloud.get("snapshots") or 0)
        except (TypeError, ValueError):
            info["snapshots"] = 0
        info["window_end"] = cloud.get("window_end") or cloud.get("latest_generated_at")
    payload.setdefault("sources", {})
    payload["sources"]["cloud"] = 0
    payload["cloud"] = info
    if not isinstance(cloud, dict):
        return payload

    points_by_item = cloud.get("points")
    if not isinstance(points_by_item, dict) or not points_by_item:
        return payload

    added = 0
    for item_id, rows in points_by_item.items():
        if not isinstance(rows, list) or not rows:
            continue
        merged: dict = {}
        for row in rows:
            if not isinstance(row, (list, tuple)) or len(row) < 2:
                continue
            stamp = str(row[0] or "")
            price = row[1]
            if not stamp or not isinstance(price, (int, float)) or isinstance(price, bool):
                continue
            merged[_stamp_key(stamp)] = [stamp, price, None]
        if not merged:
            continue
        local = payload.get("series", {}).get(item_id)
        if isinstance(local, dict):
            for row in local.get("points") or []:
                if isinstance(row, (list, tuple)) and row:
                    merged[_stamp_key(str(row[0]))] = list(row)
                # 本机点覆盖同时间戳的云端点：粒度/口径以本机为准
        points = [merged[key] for key in sorted(merged, key=lambda k: (isinstance(k, str), k))]
        lows = [p[1] for p in points if isinstance(p[1], (int, float))]
        payload.setdefault("series", {})[item_id] = {
            "points": points,
            "count": len(points),
            "firstAt": points[0][0],
            "lastAt": points[-1][0],
            "low": min(lows) if lows else None,
            "high": max(lows) if lows else None,
        }
        added += len(rows)
        try:
            payload["missing"] = [x for x in (payload.get("missing") or []) if x != item_id]
        except AttributeError:
            pass

    info["points"] = added
    payload["sources"]["cloud"] = added
    if payload.get("series"):
        payload["error"] = None
        payload["snapshotsUsed"] = sum(
            len((s or {}).get("points") or []) for s in payload["series"].values()
        )
        payload["snapshotsTotal"] = int(payload.get("snapshotsTotal") or 0) + info["snapshots"]
        stamps = [s.get("firstAt") for s in payload["series"].values() if s.get("firstAt")]
        tails = [s.get("lastAt") for s in payload["series"].values() if s.get("lastAt")]
        if stamps:
            payload["firstAt"] = min(stamps)
            payload["lastAt"] = max(tails) if tails else payload.get("lastAt")
    return payload


def clear_cache() -> None:
    with _cache_lock:
        _snapshot_cache.clear()
        _index_cache.clear()
        _gz_row_cache.clear()
        _gz_text_cache.clear()
        _gz_row_cache.clear()
