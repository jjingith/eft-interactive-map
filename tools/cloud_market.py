# -*- coding: utf-8 -*-
"""云端行情（市场列表 / 市场大盘）的唯一数据源。

产品口径（2026-11-17 定）：
  · 不再使用随安装包发布的离线快照；未登录时市场页只显示登录引导；
  · 登录后由云端 `/v1/prices/market` 下发同一份行情，服务端按账号限次：
      免费 24 次/北京时间自然日、CD 59:59、数据延迟 12 小时；
      会员 不限次、CD 30 秒、最新快照；
  · 列表与大盘共享同一次获取结果，切换子页不再重复扣次；
  · 云端不可达 / 配额用尽时，读本机 `cloud-market/` 里最后一次成功结果，
    明确标 `cached=true`（非实时），不伪造新数据。

文件布局：
  <app_dir>/cloud-market/index.json                 各模式最近一次结果与配额
  <app_dir>/cloud-market/<mode>.json                最后一次成功的完整快照
  <app_dir>/cloud-market/history/<mode>/<day>/<HHMMSS>.json.gz
                                                    历次云端快照（曲线用，按天清理）
"""

from __future__ import annotations

import datetime
import gzip
import json
import os
import threading

try:
    import market_overview
except ImportError:  # pragma: no cover - 只在 BFF / 测试环境使用
    market_overview = None

CACHE_DIRNAME = "cloud-market"
INDEX_NAME = "index.json"
MODES = ("regular", "pve", "pvps")
HISTORY_RETENTION_DAYS = 90
# 免费账号的数据延迟（与云端 price_market 的 FREE_DATA_DELAY_SECONDS 一致）。
FREE_DELAY_SECONDS = 12 * 60 * 60

_lock = threading.RLock()


def _iso(moment: datetime.datetime | None = None) -> str:
    moment = moment or datetime.datetime.now().astimezone()
    return moment.isoformat(timespec="seconds")


def _parse_iso(value) -> datetime.datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        moment = datetime.datetime.fromisoformat(text)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.astimezone()
    return moment


def normalize_mode(raw) -> str:
    mode = str(raw or "").strip().lower()
    if mode not in MODES:
        raise ValueError("mode 必须是 regular/pve/pvps")
    return mode


def cache_dir(app_dir: str) -> str:
    return os.path.join(app_dir, CACHE_DIRNAME)


def latest_path(app_dir: str, mode: str) -> str:
    return os.path.join(cache_dir(app_dir), "%s.json" % mode)


def history_dir(app_dir: str, mode: str) -> str:
    return os.path.join(cache_dir(app_dir), "history", mode)


def _read_json(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            doc = json.load(fh)
        return doc if isinstance(doc, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_json(path: str, doc: dict) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    temp = path + ".tmp"
    with open(temp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(doc, fh, ensure_ascii=False, separators=(",", ":"))
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(temp, path)


def _read_index(app_dir: str) -> dict:
    doc = _read_json(os.path.join(cache_dir(app_dir), INDEX_NAME))
    modes = doc.get("modes")
    return modes if isinstance(modes, dict) else {}


def _write_index(app_dir: str, index: dict) -> None:
    _write_json(os.path.join(cache_dir(app_dir), INDEX_NAME), {"modes": index})


def _mark_cache_error(app_dir: str, mode: str, reason: str) -> None:
    """记下「这次云端取数失败」，供大盘/状态条如实标注缓存。"""
    index = _read_index(app_dir)
    entry = index.get(mode) if isinstance(index.get(mode), dict) else {}
    entry["lastError"] = reason or "offline"
    entry["lastErrorAt"] = _iso()
    index[mode] = entry
    _write_index(app_dir, index)


def status(app_dir: str) -> dict:
    """给界面显示的缓存 / 配额概况（不联网）。"""
    index = _read_index(app_dir)
    modes = {}
    for mode in MODES:
        entry = index.get(mode) if isinstance(index.get(mode), dict) else {}
        modes[mode] = dict(entry)
        modes[mode]["exists"] = os.path.isfile(latest_path(app_dir, mode))
    return {"dir": cache_dir(app_dir), "modes": modes}


def load_latest(app_dir: str, mode: str) -> dict | None:
    mode = normalize_mode(mode)
    doc = _read_json(latest_path(app_dir, mode))
    if not doc.get("generated_at"):
        return None
    if not isinstance(doc.get("prices"), dict) and not isinstance(doc.get("market"), dict):
        return None
    return doc


def _history_file(app_dir: str, mode: str, generated_at: str) -> str | None:
    moment = _parse_iso(generated_at)
    if moment is None:
        return None
    day = moment.astimezone().date().isoformat()
    stamp = moment.astimezone().strftime("%H%M%S")
    return os.path.join(history_dir(app_dir, mode), day, stamp + ".json.gz")


def _save_snapshot(app_dir: str, mode: str, doc: dict) -> None:
    """落一份完整快照：最新文件 + 历史曲线文件（同一 generated_at 只写一次）。"""
    generated_at = str(doc.get("generated_at") or "")
    prices = doc.get("prices") if isinstance(doc.get("prices"), dict) else {}
    market = doc.get("market") if isinstance(doc.get("market"), dict) else {}
    if not generated_at or not (prices or market):
        return
    snapshot = {"generated_at": generated_at, "prices": prices, "market": market}
    path = _history_file(app_dir, mode, generated_at)
    if path:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        temp = path + ".tmp"
        with gzip.open(temp, "wt", encoding="utf-8") as fh:
            json.dump(snapshot, fh, ensure_ascii=False, separators=(",", ":"))
        os.replace(temp, path)


def _prune_history(app_dir: str, mode: str, *, now: datetime.datetime | None = None) -> None:
    now = now or datetime.datetime.now().astimezone()
    cutoff = (now - datetime.timedelta(days=HISTORY_RETENTION_DAYS)).date().isoformat()
    base = history_dir(app_dir, mode)
    try:
        days = sorted(name for name in os.listdir(base) if len(name) == 10)
    except OSError:
        return
    for day in days:
        if day >= cutoff:
            break
        path = os.path.join(base, day)
        try:
            for name in os.listdir(path):
                os.remove(os.path.join(path, name))
            os.rmdir(path)
        except OSError:
            continue


def _history_snapshots(app_dir: str, mode: str, days: int | None = None,
                       *, now: datetime.datetime | None = None) -> list[dict]:
    """按时间顺序读历史快照；days 给定时只读窗口内的文件。"""
    base = history_dir(app_dir, mode)
    try:
        day_dirs = sorted(name for name in os.listdir(base) if len(name) == 10)
    except OSError:
        return []
    now = now or datetime.datetime.now().astimezone()
    if days:
        cutoff = (now - datetime.timedelta(days=days)).astimezone().date().isoformat()
        day_dirs = [name for name in day_dirs if name >= cutoff]
    out = []
    for day in day_dirs:
        folder = os.path.join(base, day)
        try:
            names = sorted(name for name in os.listdir(folder) if name.endswith(".json.gz"))
        except OSError:
            continue
        for name in names:
            try:
                with gzip.open(os.path.join(folder, name), "rt", encoding="utf-8") as fh:
                    doc = json.load(fh)
            except (OSError, ValueError):
                continue
            if isinstance(doc, dict) and doc.get("generated_at"):
                out.append(doc)
    return out


def _items_of(doc: dict) -> dict[str, dict]:
    prices = doc.get("prices") if isinstance(doc.get("prices"), dict) else {}
    market = doc.get("market") if isinstance(doc.get("market"), dict) else {}
    items: dict[str, dict] = {}
    for item_id, rec in market.items():
        if not isinstance(rec, dict):
            continue
        row = {}
        price = rec.get("l")
        if not isinstance(price, (int, float)) or isinstance(price, bool):
            price = prices.get(item_id)
        if isinstance(price, (int, float)) and not isinstance(price, bool):
            row["l"] = price
        for key in ("a", "lo", "hi", "b", "o", "c", "d", "v"):
            value = rec.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                row[key] = value
        stamp = rec.get("s") or rec.get("u")
        if isinstance(stamp, str) and stamp:
            row["u"] = stamp
        if row:
            items[str(item_id)] = row
    for item_id, price in prices.items():
        key = str(item_id)
        if key in items:
            continue
        if isinstance(price, (int, float)) and not isinstance(price, bool):
            items[key] = {"l": price}
    return items


def _moment_of(doc: dict) -> datetime.datetime | None:
    return _parse_iso((doc or {}).get("generated_at") or (doc or {}).get("generatedAt"))


def _allowed(doc: dict, max_generated_at: datetime.datetime | None) -> bool:
    if max_generated_at is None:
        return True
    moment = _moment_of(doc)
    return moment is not None and moment <= max_generated_at


def _newest_allowed_history(app_dir: str, mode: str,
                            max_generated_at: datetime.datetime) -> dict | None:
    """本机历史里找一份不晚于 max_generated_at 的快照（免费账号降级时用）。"""
    snapshots = _history_snapshots(app_dir, mode, days=HISTORY_RETENTION_DAYS)
    allowed = [doc for doc in snapshots if _allowed(doc, max_generated_at)]
    if not allowed:
        return None
    allowed.sort(key=lambda doc: str(doc.get("generated_at") or ""))
    return allowed[-1]


def _normalize(doc: dict, mode: str, *, cached: bool, cache_reason: str = "",
               quota: dict | None = None,
               max_generated_at: datetime.datetime | None = None) -> dict:
    quota = quota if isinstance(quota, dict) and quota else (
        doc.get("quota") if isinstance(doc.get("quota"), dict) else {})
    tier = str(doc.get("tier") or quota.get("tier") or "free")
    delay = doc.get("delay_seconds")
    if not isinstance(delay, int):
        delay = int(quota.get("delay_seconds") or 0)
    if max_generated_at is not None:
        # 免费账号：即使本机缓存是会员时期留下的新快照，也只能按免费口径展示。
        tier, delay = "free", FREE_DELAY_SECONDS
    generated_at = doc.get("generated_at")
    return {
        "ok": True,
        "mode": mode,
        "modeLabel": {"regular": "PvP", "pve": "PvE", "pvps": "PvPS"}.get(mode, mode),
        "available": True,
        "source": "cloud",
        "live": (not cached) and tier == "member",
        "nonLive": bool(cached) or tier != "member",
        "cached": bool(cached),
        "cacheReason": cache_reason or None,
        "offline": bool(cached) and cache_reason in ("offline", "network", "pinning"),
        "tier": tier,
        "member": tier == "member",
        "delaySeconds": delay,
        "dataDelayed": delay > 0,
        "snapshotAt": generated_at,
        "dataAt": generated_at,
        "fetchedAt": doc.get("fetched_at"),
        "items": _items_of(doc),
        "quota": quota,
        "status": "cached" if cached else str(doc.get("status") or "ok"),
        "error": None,
    }


def cached_payload(app_dir: str, mode: str, *, cache_reason: str = "cached",
                   quota: dict | None = None) -> dict | None:
    doc = load_latest(app_dir, mode)
    if doc is None:
        return None
    return _normalize(doc, mode, cached=True, cache_reason=cache_reason, quota=quota)


def fetch(app_dir: str, mode: str, cloud_client=None, *, force: bool = False,
          now: datetime.datetime | None = None,
          max_generated_at: datetime.datetime | None = None) -> dict:
    """取一份行情：优先云端，失败 / 配额用尽时回退本机最后一次成功结果。

    `force=True`（用户点「获取最新数据」）一定打云端，由服务端决定是扣次、
    CD 回放还是 429；`force=False`（打开页面 / 切子页）只要本机有结果就直接复用，
    不消耗免费额度；只有第一次没有任何缓存时才自动取一次。

    `max_generated_at` 是免费账号的可见上限（当前时间 − 12 小时）：本机缓存
    里更新的快照也不能下发，必要时退到历史里更早的一份。
    """
    mode = normalize_mode(mode)
    now = now or datetime.datetime.now().astimezone()

    latest = load_latest(app_dir, mode)
    if latest is not None and not _allowed(latest, max_generated_at):
        latest = _newest_allowed_history(app_dir, mode, max_generated_at)
    if latest is not None and not force:
        entry = _read_index(app_dir).get(mode) or {}
        reason = str(entry.get("lastError") or "")
        return _normalize(latest, mode, cached=bool(reason), cache_reason=reason,
                          max_generated_at=max_generated_at)

    if cloud_client is None:
        if latest is not None:
            return _normalize(latest, mode, cached=True, cache_reason="offline",
                              max_generated_at=max_generated_at)
        raise RuntimeError("云服务不可用")

    with _lock:
        # 等锁期间另一个请求可能已经取回来了：非 force 直接复用，不重复扣次。
        latest = load_latest(app_dir, mode)
        if latest is not None and not _allowed(latest, max_generated_at):
            latest = _newest_allowed_history(app_dir, mode, max_generated_at)
        if latest is not None and not force:
            entry = _read_index(app_dir).get(mode) or {}
            reason = str(entry.get("lastError") or "")
            return _normalize(latest, mode, cached=bool(reason), cache_reason=reason,
                              max_generated_at=max_generated_at)
        try:
            data = cloud_client.prices_market(mode)
        except Exception as exc:
            reason = getattr(exc, "code", "") or "offline"
            quota = None
            details = getattr(exc, "details", None)
            if isinstance(details, dict):
                quota = details.get("quota") if isinstance(details.get("quota"), dict) else None
            if latest is not None:
                _mark_cache_error(app_dir, mode, reason)
                return _normalize(latest, mode, cached=True, cache_reason=reason, quota=quota,
                                  max_generated_at=max_generated_at)
            raise

        doc = {
            "generated_at": data.get("generated_at"),
            "stored_at": data.get("stored_at"),
            "tier": data.get("tier"),
            "delay_seconds": data.get("delay_seconds"),
            "quota": data.get("quota") if isinstance(data.get("quota"), dict) else {},
            "prices": data.get("prices") if isinstance(data.get("prices"), dict) else {},
            "market": data.get("market") if isinstance(data.get("market"), dict) else {},
            "fetched_at": _iso(now),
            "status": data.get("status") or "ok",
        }
        _save_snapshot(app_dir, mode, doc)
        _write_json(latest_path(app_dir, mode), doc)
        index = _read_index(app_dir)
        index[mode] = {
            "generatedAt": doc["generated_at"],
            "storedAt": doc.get("stored_at"),
            "fetchedAt": doc["fetched_at"],
            "tier": doc.get("tier"),
            "delaySeconds": doc.get("delay_seconds"),
            "quota": doc.get("quota"),
            "itemCount": len(doc["prices"]) or len(doc["market"]),
            "marketCount": len(doc["market"]),
            "lastError": None,
            "lastErrorAt": None,
        }
        _write_index(app_dir, index)
        _prune_history(app_dir, mode, now=now)
        if not _allowed(doc, max_generated_at):
            # 服务端本应已经延迟；真出现更新数据时不向免费账号下发。
            if latest is not None:
                return _normalize(latest, mode, cached=True, cache_reason="delayed",
                                  quota=doc.get("quota"),
                                  max_generated_at=max_generated_at)
            raise RuntimeError("该数据尚未到免费账号的可见时间")
        return _normalize(doc, mode, cached=False, max_generated_at=max_generated_at)


def overview(app_dir: str, mode: str, hours: int = 24, *, ids: list[str] | None = None,
             sector: str | None = None, now: datetime.datetime | None = None,
             max_generated_at: datetime.datetime | None = None) -> dict:
    """市场大盘：最新快照 + 本机累积的历史快照，口径与原先一致。

    `max_generated_at` 对免费账号生效：更新的本机缓存也不参与大盘统计。
    """
    mode = normalize_mode(mode)
    if market_overview is None:  # pragma: no cover
        return {"ok": False, "error": "overview-unavailable", "mode": mode}
    now = now or datetime.datetime.now().astimezone()
    snapshots = _history_snapshots(app_dir, mode, days=max(7, (int(hours) + 23) // 24 + 1), now=now)
    snapshots = [doc for doc in snapshots if _allowed(doc, max_generated_at)]
    latest = load_latest(app_dir, mode)
    if latest is not None and _allowed(latest, max_generated_at):
        generated = latest.get("generated_at")
        if not any(snapshot.get("generated_at") == generated for snapshot in snapshots):
            snapshots.append({
                "generated_at": generated,
                "prices": latest.get("prices") or {},
                "market": latest.get("market") or {},
            })
    payload = market_overview.from_snapshots(mode, snapshots, hours, now=now, ids=ids,
                                             sector=sector, app_dir=app_dir)
    entry = _read_index(app_dir).get(mode) or {}
    if max_generated_at is not None:
        payload["tier"] = "free"
        payload["delaySeconds"] = FREE_DELAY_SECONDS
        payload["dataDelayed"] = True
    else:
        payload["tier"] = entry.get("tier") or (latest or {}).get("tier") or "free"
        payload["delaySeconds"] = entry.get("delaySeconds") if isinstance(entry.get("delaySeconds"), int) else (
            (latest or {}).get("delay_seconds") or 0)
        payload["dataDelayed"] = (payload["delaySeconds"] or 0) > 0
    payload["quota"] = entry.get("quota") if isinstance(entry.get("quota"), dict) else {}
    payload["fetchedAt"] = entry.get("fetchedAt")
    payload["cached"] = bool(entry.get("lastError"))
    payload["cacheReason"] = entry.get("lastError")
    return payload


def _num_offers(value):
    """只收真数值（bool 不是），供热卖榜用；不放宽成字符串以免把脏值当挂单数。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def offers_history(app_dir: str, mode: str, item_ids, hours: int = 24,
                   *, now: datetime.datetime | None = None) -> dict:
    """R291 热卖榜：本机历史快照里的在售挂单数当前值 + 窗口峰值。

    只读本机已落盘的云端快照，不额外请求云端、不扣配额。
    冷启动（还没有历史快照）时 peak=None，前端显示「—」，绝不补 0。
    `o` 是**在售挂单数**，不是成交量。
    """
    mode = normalize_mode(mode)
    ids = []
    for value in (item_ids or []):
        value = str(value).strip()
        if value and value not in ids:
            ids.append(value)
    hours = max(1, min(24 * 90, int(hours or 24)))
    now = now or datetime.datetime.now().astimezone()
    snapshots = _history_snapshots(app_dir, mode, days=max(1, (hours + 23) // 24))
    cutoff = (now - datetime.timedelta(hours=hours)).astimezone()
    points: dict[str, list] = {item: [] for item in ids}
    for doc in snapshots:
        try:
            stamp = str(doc.get("generated_at") or "")
            when = datetime.datetime.fromisoformat(stamp)
        except (TypeError, ValueError):
            continue
        if when.astimezone() < cutoff:
            continue
        market = doc.get("market") if isinstance(doc.get("market"), dict) else {}
        for item in ids:
            row = market.get(item)
            offer = _num_offers((row or {}).get("o")) if isinstance(row, dict) else None
            if offer is not None:
                points[item].append([stamp, offer])

    latest = load_latest(app_dir, mode) or {}
    latest_market = latest.get("market") if isinstance(latest.get("market"), dict) else {}
    items: dict[str, dict] = {}
    for item in ids:
        row = latest_market.get(item)
        current = _num_offers((row or {}).get("o")) if isinstance(row, dict) else None
        vals = [value for _stamp, value in points[item]]
        items[item] = {
            "current": current,
            "peak": max(vals) if vals else None,
            "samples": len(vals),
            # 24h 在售数量序列（热卖榜曲线用）：[[iso, offers], ...]，缺测不补点
            "points": points[item],
        }
    return {
        "ok": True, "mode": mode, "hours": hours, "items": items,
        "status": "ok" if any(v["samples"] for v in items.values()) else "cold_start",
        "note": "在售挂单数，非成交量；冷启动无历史时峰值留空，不补 0",
    }


def history(app_dir: str, mode: str, item_ids, days: int = 7,
            *, now: datetime.datetime | None = None,
            max_generated_at: datetime.datetime | None = None) -> dict:
    """单物品曲线：只读本机累积的云端快照，不额外消耗配额。"""
    mode = normalize_mode(mode)
    ids = [str(item).strip() for item in (item_ids or []) if str(item).strip()]
    now = now or datetime.datetime.now().astimezone()
    days = max(1, min(90, int(days or 7)))
    snapshots = _history_snapshots(app_dir, mode, days=days, now=now)
    latest = load_latest(app_dir, mode)
    if latest is not None and _allowed(latest, max_generated_at):
        generated = latest.get("generated_at")
        if not any(snapshot.get("generated_at") == generated for snapshot in snapshots):
            snapshots.append({
                "generated_at": generated,
                "prices": latest.get("prices") or {},
                "market": latest.get("market") or {},
            })
    snapshots = [doc for doc in snapshots if _allowed(doc, max_generated_at)]
    snapshots.sort(key=lambda doc: str(doc.get("generated_at") or ""))
    points = {item: [] for item in ids}
    for snapshot in snapshots:
        rows = _items_of(snapshot)
        stamp = snapshot.get("generated_at")
        for item in ids:
            price = (rows.get(item) or {}).get("l")
            if isinstance(price, (int, float)) and not isinstance(price, bool):
                points[item].append([stamp, price])
    series = {}
    for item in ids:
        rows = points[item]
        if not rows:
            continue
        series[item] = {
            "points": rows,
            "count": len(rows),
            "firstAt": rows[0][0],
            "lastAt": rows[-1][0],
        }
    return {
        "ok": True,
        "status": "ok" if series else "no_data",
        "mode": mode,
        "days": days,
        "source": "cloud",
        "series": series,
        "snapshots": len(snapshots),
        "window_end": snapshots[-1].get("generated_at") if snapshots else None,
        "note": "曲线来自本机历次云端取数；不插值、不补点",
    }
