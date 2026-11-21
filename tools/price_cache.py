# -*- coding: utf-8 -*-
"""R279：云端价格本地缓存（会员登录后整包下载 + 按需增量）。

产品口径（用户 11-14 定）：
1. **登录会员后一次性把云端数据下载到本地**做缓存 —— 之后打开价格页不再
   依赖网络，曲线直接出；
2. **点「获取最新数据」才向服务器请求缺失的部分** —— 带上次 `cursor` 走增量，
   没新数据就什么都不传；
3. **会员过期自动清理缓存** —— 云端 403 / `member=false` 时 `purge()` 掉整份。

为什么缓存按「物品 → 序列」存，而不是照抄 192 份原始快照：
· 原始快照 3 个模式合计 64 MB（每份 ~117 KB × 192 份），读一个物品要扫全量；
· 聚合成 `{itemId: [[ts_ms, price], …]}` 后单模式约 9 MB，取值时用
  `"<id>":[` 在原文里定位再 `raw_decode`（与云端 `/v1/prices/series` 同一套
  手法），单物品 2 ms，整份也不用进内存对象图。

文件布局：`<app_dir>/cloud-cache/<mode>.json`，外加 `index.json` 记录各模式的
cursor / 快照数 / 更新时间，供界面显示「缓存于 …」。
"""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timedelta, timezone

CACHE_DIRNAME = "cloud-cache"
INDEX_NAME = "index.json"
CACHE_VERSION = 1
MODES = ("regular", "pve", "pvps")

_write_lock = threading.RLock()
_text_cache: dict[str, tuple[float, str]] = {}


def cache_dir(app_dir: str) -> str:
    return os.path.join(app_dir, CACHE_DIRNAME)


def cache_path(app_dir: str, mode: str) -> str:
    return os.path.join(cache_dir(app_dir), "%s.json" % mode)


def _read_text(path: str) -> str:
    """读缓存原文；按 mtime 记住一份，重复查询同一模式不重复读盘。"""
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return ""
    hit = _text_cache.get(path)
    if hit and hit[0] == mtime:
        return hit[1]
    try:
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return ""
    _text_cache[path] = (mtime, text)
    return text


def _price_at(text: str, item_id: str) -> list | None:
    """在缓存原文里定位 `"<id>":[[ts,price],…]`，只解析这一个物品。

    与服务端 `_price_at` 同构：`json.loads` 整份 9 MB 会让每次绘图都卡住，
    定位后 `raw_decode` 一个数组就够（实测 2 ms）。
    """
    needle = '"%s":' % item_id
    idx = text.find(needle)
    if idx < 0:
        return None
    decoder = json.JSONDecoder()
    try:
        value, _end = decoder.raw_decode(text, idx + len(needle))
    except ValueError:
        return None
    return value if isinstance(value, list) else None


def _iso(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).isoformat(timespec="seconds")


def _load_index(app_dir: str) -> dict:
    try:
        with open(os.path.join(cache_dir(app_dir), INDEX_NAME), "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_index(app_dir: str, index: dict) -> None:
    directory = cache_dir(app_dir)
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, INDEX_NAME)
    temp = path + ".tmp"
    with open(temp, "w", encoding="utf-8") as fh:
        json.dump(index, fh, ensure_ascii=False, separators=(",", ":"))
    os.replace(temp, path)


def status(app_dir: str) -> dict:
    """各模式缓存概况：给界面显示「已缓存 N 份 / 缓存于 …」。"""
    index = _load_index(app_dir)
    modes = {}
    for mode in MODES:
        path = cache_path(app_dir, mode)
        entry = index.get(mode) if isinstance(index.get(mode), dict) else {}
        exists = os.path.isfile(path)
        modes[mode] = {
            "exists": exists,
            "snapshots": int(entry.get("snapshots") or 0) if exists else 0,
            "points": int(entry.get("points") or 0) if exists else 0,
            "items": int(entry.get("items") or 0) if exists else 0,
            "cursor": entry.get("cursor"),
            "updated_at": entry.get("updated_at"),
            "bytes": os.path.getsize(path) if exists else 0,
        }
    return {"dir": cache_dir(app_dir), "modes": modes}


def has_data(app_dir: str, mode: str) -> bool:
    path = cache_path(app_dir, mode)
    return os.path.isfile(path) and os.path.getsize(path) > 64


def series(app_dir: str, mode: str, item_ids, days: int | None = None) -> dict:
    """从本地缓存取若干物品的曲线（不联网）。

    返回结构与服务端 `/v1/prices/series` 对齐：`points[item] = [[iso, price], …]`，
    时间窗口锚**缓存里的最新点**（不是「现在」），采集机停更时右端不会多出空白。
    """
    ids = [str(x).strip() for x in (item_ids or []) if str(x).strip()]
    result = {
        "status": "no_data",
        "mode": mode,
        "days": days,
        "snapshots": 0,
        "window_end": None,
        "points": {item: [] for item in ids},
        "counts": {item: 0 for item in ids},
    }
    text = _read_text(cache_path(app_dir, mode))
    if not text or not ids:
        return result
    entry = _load_index(app_dir).get(mode) or {}
    result["snapshots"] = int(entry.get("snapshots") or 0)

    latest_ms = 0
    raw: dict[str, list] = {}
    for item in ids:
        rows = _price_at(text, item)
        if not rows:
            continue
        raw[item] = rows
        if rows and isinstance(rows[-1], list):
            latest_ms = max(latest_ms, int(rows[-1][0]))
    if not raw:
        return result

    window_start = None
    if days:
        try:
            window_start = latest_ms - int(days) * 86400 * 1000
        except (TypeError, ValueError):
            window_start = None
    for item, rows in raw.items():
        points = []
        for row in rows:
            if not isinstance(row, list) or len(row) < 2:
                continue
            ts, price = row[0], row[1]
            if not isinstance(ts, (int, float)) or not isinstance(price, (int, float)):
                continue
            if window_start is not None and ts < window_start:
                continue
            points.append([_iso(int(ts)), price])
        result["points"][item] = points
        result["counts"][item] = len(points)
    result["window_end"] = _iso(latest_ms) if latest_ms else None
    result["status"] = "ok" if any(result["counts"].values()) else "no_data"
    return result


def _merge(app_dir: str, mode: str, payload: dict) -> dict:
    """把一次下载结果并入本地缓存文件（整包覆盖 / 增量拼接）。"""
    incoming = payload.get("series") if isinstance(payload.get("series"), dict) else {}
    path = cache_path(app_dir, mode)
    existing_text = _read_text(path)
    merged: dict[str, list] = {}
    base_snapshots = 0
    cursor = payload.get("cursor")
    if existing_text:
        try:
            current = json.loads(existing_text)
        except ValueError:
            current = None
        if isinstance(current, dict):
            base = current.get("series")
            if isinstance(base, dict):
                merged = {k: v for k, v in base.items() if isinstance(v, list)}
            base_snapshots = int(current.get("snapshots") or 0)
            if not cursor:
                cursor = current.get("cursor")
    snapshots = base_snapshots + int(payload.get("snapshots") or 0)

    added = 0
    for item, rows in incoming.items():
        if not isinstance(item, str) or not isinstance(rows, list):
            continue
        bucket = merged.setdefault(item, [])
        seen = {row[0] for row in bucket if isinstance(row, list) and row}
        for row in rows:
            if not isinstance(row, list) or len(row) < 2:
                continue
            ts, price = row[0], row[1]
            if not isinstance(ts, (int, float)) or not isinstance(price, (int, float)):
                continue
            if ts in seen:
                continue
            bucket.append([int(ts), price])
            seen.add(ts)
            added += 1
        bucket.sort(key=lambda r: r[0])

    if not merged:
        return {"mode": mode, "added": 0, "snapshots": snapshots, "items": 0, "points": 0}

    points = sum(len(v) for v in merged.values())
    doc = {
        "version": CACHE_VERSION,
        "mode": mode,
        "cursor": cursor,
        "snapshots": snapshots,
        "items": len(merged),
        "points": points,
        "updated_at": int(time.time()),
        "series": merged,
    }
    os.makedirs(cache_dir(app_dir), exist_ok=True)
    temp = path + ".tmp"
    with open(temp, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, separators=(",", ":"))
    os.replace(temp, path)
    _text_cache.pop(path, None)

    index = _load_index(app_dir)
    index[mode] = {
        "cursor": cursor,
        "snapshots": snapshots,
        "items": len(merged),
        "points": points,
        "updated_at": doc["updated_at"],
    }
    _save_index(app_dir, index)
    return {
        "mode": mode,
        "added": added,
        "snapshots": snapshots,
        "items": len(merged),
        "points": points,
        "cursor": cursor,
        "updated_at": doc["updated_at"],
    }


def sync(app_dir: str, client, mode: str) -> dict:
    """整包（无缓存时）或增量（有 cursor 时）同步一个模式。

    返回 `{"mode","kind":"full|incremental","added","snapshots","cursor",…}`；
    云端 403 由调用方处理（这里只负责把异常抛上去）。
    """
    mode = str(mode or "").strip().lower() or "regular"
    with _write_lock:
        entry = _load_index(app_dir).get(mode) or {}
        cursor = entry.get("cursor")
        kind = "incremental" if cursor and has_data(app_dir, mode) else "full"
        payload = client.prices_cache(mode, None if kind == "full" else cursor)
        if payload.get("status") == "up_to_date" and not payload.get("series"):
            return {
                "mode": mode,
                "kind": kind,
                "added": 0,
                "snapshots": int(entry.get("snapshots") or 0),
                "cursor": payload.get("cursor") or cursor,
                "up_to_date": True,
            }
        summary = _merge(app_dir, mode, payload)
        summary["kind"] = kind
        summary["up_to_date"] = summary.get("added", 0) == 0
        return summary


def purge(app_dir: str, reason: str = "") -> int:
    """清掉整份缓存（会员过期 / 注销登录）。返回删掉的文件数。"""
    directory = cache_dir(app_dir)
    removed = 0
    with _write_lock:
        _text_cache.clear()
        if not os.path.isdir(directory):
            return 0
        for name in os.listdir(directory):
            path = os.path.join(directory, name)
            try:
                if os.path.isfile(path):
                    os.remove(path)
                    removed += 1
            except OSError:
                continue
        try:
            os.rmdir(directory)
        except OSError:
            pass
    return removed


def window_hint(app_dir: str, mode: str) -> dict:
    """给前端的缓存口径说明：覆盖到哪一刻、有多少份快照。"""
    text = _read_text(cache_path(app_dir, mode))
    if not text:
        return {"exists": False}
    entry = _load_index(app_dir).get(mode) or {}
    latest = 0
    try:
        decoder = json.JSONDecoder()
        idx = text.rfind("]]")
        if idx > 0:
            start = text.rfind("[[", 0, idx)
            rows, _ = decoder.raw_decode(text, start)
            if rows:
                latest = int(rows[-1][0])
    except (ValueError, IndexError, TypeError):
        latest = 0
    return {
        "exists": True,
        "snapshots": int(entry.get("snapshots") or 0),
        "updated_at": entry.get("updated_at"),
        "latest": _iso(latest) if latest else None,
        "bytes": os.path.getsize(cache_path(app_dir, mode)),
    }


def cleanup_older_than(app_dir: str, days: int = 0) -> int:
    """占位：缓存只在会员有效期内存在，过期即整体清理，不做按天裁剪。"""
    del app_dir, days
    return 0


__all__ = [
    "CACHE_DIRNAME",
    "MODES",
    "cache_dir",
    "cache_path",
    "has_data",
    "purge",
    "series",
    "status",
    "sync",
    "window_hint",
]
