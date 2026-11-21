#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R78 本地采集器快照读取层（**只读、不联网、仅标准库**）。

市场页的行情只认这一层：按当前游戏模式读取 `EFTPriceCollector` 落盘的
最新快照，不再拿构建期 `data/flea-prices.json` 顶替别的模式。

数据目录（与 tools/price_collect.py 完全一致）：
  <root>/collect/snapshots/{mode}/{YYYY-MM-DD}/{HHMMSS}.json.gz   每 30 分钟一份
  <root>/collect/daily/{mode}/{YYYY-MM-DD}.json.gz                当天最后一份（含 lo/hi/b/lv）

  <root> = %LOCALAPPDATA%\\EFTPrice（`EFT_PRICE_ROOT` 可覆盖）

模式键沿用上游：regular = PvP、pve = PvE、pvps = PvPS（赛季服，上游路径 pvp-season）。

返回契约（`snapshot_payload`）：
  {"ok": true, "mode": "pve", "source": "collector", "available": true,
   "snapshotAt": "...", "dataAt": "...", "ageSec": 123, "staleAfterSec": 7200,
   "stale": false, "counts": {...},
   "items": {id: {l, a, u, lo, hi, b, lv}}, "avg7d": {"days": 0, "dates": [], "values": {}},
   "root": "...", "snapshotFile": "...", "error": null}

  · 没有任何快照：available=false, error="no-snapshot"（items 为空对象）
  · 快照损坏读不出来：ok=false, error="unreadable-snapshot"
  · 任何异常都不向外抛；调用方按 error 显示提示，不会 500。

24h 均价 / 7 日均价都从 `daily/` 锚点算：
  · `l` / `a` 直接取最新快照（最新一份，比当天锚点更新）；
  · 7 日均价要求最近 7 个快照日的 `l` 都存在，缺一天即跳过该物品，**不插值**。
"""
from __future__ import annotations

import datetime
import gzip
import json
import os
import re
import threading

MODE_ALIASES = {
    "regular": "regular", "pvp": "regular",
    "pve": "pve",
    "pvps": "pvps", "pvp-season": "pvps", "pvpseason": "pvps", "season": "pvps",
}
STALE_AFTER_SEC = 2 * 3600        # 采集器每 30 分钟一轮；超过 2 小时即视为过期
AVG7_MIN_DAYS = 7                 # 与 r20_fetch_prices.HISTORY_AVG7_DAYS 一致
SNAPSHOT_FILE_RE = re.compile(r"^(\d{2})(\d{2})(\d{2})\.json\.gz$")
DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MAX_PRICE = 100_000_000
_CACHE_MAX = 8

_cache = {}
_cache_lock = threading.Lock()


def normalize_mode(raw) -> str:
    """`regular`/`pvp`/`pve`/`pvps`/`pvp-season` → 内部键；非法值抛 ValueError。"""
    key = str(raw or "").strip().lower()
    if key in MODE_ALIASES:
        return MODE_ALIASES[key]
    raise ValueError("未知模式：%r（可用 regular(PvP) / pve / pvps）" % (raw,))


def root_dir(explicit: str | None = None) -> str:
    """采集器程序根目录（collect / cache 都在它下面）。"""
    if explicit:
        return os.path.abspath(explicit)
    override = os.environ.get("EFT_PRICE_ROOT")
    if override:
        return os.path.abspath(override)
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        base = os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, "EFTPrice")


def data_root(explicit: str | None = None) -> str:
    return os.path.join(root_dir(explicit), "collect")


# ---------------------------------------------------------------- 读文件（带小缓存）

def _read_gz_json(path: str):
    """读 gzip JSON；按 (路径, 大小, mtime) 缓存，避免每次请求都解压。读不出来返回 None。"""
    try:
        st = os.stat(path)
    except OSError:
        return None
    key = (path, st.st_size, int(st.st_mtime_ns))
    with _cache_lock:
        hit = _cache.get(key)
    if hit is not None:
        return hit
    try:
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError, EOFError):
        return None
    if not isinstance(doc, dict):
        return None
    with _cache_lock:
        if len(_cache) >= _CACHE_MAX:
            _cache.pop(next(iter(_cache)), None)
        _cache[key] = doc
    return doc


def _latest_snapshot_path(root: str, mode: str):
    """最新快照文件：先取最新日期目录，再取该目录里最大的 HHMMSS。"""
    base = os.path.join(root, "snapshots", mode)
    try:
        days = sorted((n for n in os.listdir(base) if DAY_RE.match(n)), reverse=True)
    except OSError:
        return None
    for day in days:
        directory = os.path.join(base, day)
        try:
            names = sorted(n for n in os.listdir(directory) if SNAPSHOT_FILE_RE.match(n))
        except OSError:
            continue
        if names:
            return os.path.join(directory, names[-1])
    return None


def daily_files(root: str, mode: str) -> list:
    """按日期升序返回 daily 锚点文件名（只认 YYYY-MM-DD.json.gz）。"""
    base = os.path.join(root, "daily", mode)
    try:
        names = sorted(n[:-len(".json.gz")] for n in os.listdir(base)
                       if n.endswith(".json.gz") and DAY_RE.match(n[:-len(".json.gz")]))
    except OSError:
        return []
    return names


def _parse_iso(text):
    if not isinstance(text, str) or not text:
        return None
    value = text.strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        dt = datetime.datetime.fromisoformat(value)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt


def _iso_local(dt: datetime.datetime) -> str:
    return dt.astimezone().isoformat(timespec="seconds")


def _valid_price(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not (0 < value < MAX_PRICE):
        return None
    return value


def _avg7(root: str, mode: str) -> dict:
    """最近 7 个快照日的 lastLowPrice 均值；缺日不插值（与 r20_fetch_prices 同规则）。"""
    names = daily_files(root, mode)
    out = {"days": len(names), "dates": [], "values": {}}
    if len(names) < AVG7_MIN_DAYS:
        return out
    picked = names[-AVG7_MIN_DAYS:]
    out["dates"] = picked
    maps = []
    for day in picked:
        doc = _read_gz_json(os.path.join(root, "daily", mode, day + ".json.gz"))
        if not doc or not isinstance(doc.get("items"), dict):
            return out
        maps.append({iid: _valid_price(row.get("l"))
                     for iid, row in doc["items"].items() if isinstance(row, dict)})
    for iid in maps[-1]:
        vals = []
        for row_map in maps:
            value = row_map.get(iid)
            if value is None:
                vals = []
                break
            vals.append(float(value))
        if vals:
            out["values"][iid] = int(round(sum(vals) / len(vals)))
    return out


def snapshot_payload(mode, explicit_root: str | None = None, now: datetime.datetime | None = None) -> dict:
    """读取某模式的最新本地采集快照；任何异常都转成结构化结果，不向外抛。"""
    key = normalize_mode(mode)
    root = data_root(explicit_root)
    payload = {
        "ok": True,
        "mode": key,
        "source": "collector",
        "available": False,
        "snapshotAt": None,
        "dataAt": None,
        "ageSec": None,
        "staleAfterSec": STALE_AFTER_SEC,
        "stale": False,
        "counts": {},
        "items": {},
        "avg7d": {"days": len(daily_files(root, key)), "dates": [], "values": {}},
        "root": root,
        "snapshotFile": None,
        "error": None,
    }
    path = _latest_snapshot_path(root, key)
    if not path:
        payload["error"] = "no-snapshot"
        return payload
    doc = _read_gz_json(path)
    if not doc or not isinstance(doc.get("items"), dict):
        payload["ok"] = False
        payload["error"] = "unreadable-snapshot"
        payload["snapshotFile"] = path
        return payload

    now = now or datetime.datetime.now().astimezone()
    items = {}
    for iid, row in doc["items"].items():
        if not isinstance(row, dict):
            continue
        compact = {}
        for src, dst in (("l", "l"), ("a", "a"), ("u", "u")):
            value = row.get(src)
            if src == "u":
                if isinstance(value, str) and value:
                    compact[dst] = value
            elif _valid_price(value) is not None:
                compact[dst] = value
        if compact:
            items[str(iid)] = compact

    # daily 锚点补齐 24h 低/高、基础价与跳蚤等级（最新快照里只有 l/a/u）
    days = daily_files(root, key)
    if days:
        anchor = _read_gz_json(os.path.join(root, "daily", key, days[-1] + ".json.gz"))
        if anchor and isinstance(anchor.get("items"), dict):
            for iid, row in anchor["items"].items():
                target = items.get(str(iid))
                if target is None or not isinstance(row, dict):
                    continue
                for field in ("lo", "hi", "b"):
                    value = _valid_price(row.get(field))
                    if value is not None and field not in target:
                        target[field] = value
                lv = row.get("lv")
                if isinstance(lv, int) and not isinstance(lv, bool) and "lv" not in target:
                    target["lv"] = lv

    snapshot_at = doc.get("snapshotAt")
    parsed = _parse_iso(snapshot_at)
    if parsed is None:
        try:
            parsed = datetime.datetime.fromtimestamp(os.path.getmtime(path)).astimezone()
        except OSError:
            parsed = None
        snapshot_at = _iso_local(parsed) if parsed else None
    age = None
    if parsed is not None:
        age = max(0, int(round((now - parsed).total_seconds())))

    payload.update({
        "available": bool(items),
        "snapshotAt": snapshot_at,
        "dataAt": doc.get("sourceUpdatedMax") or snapshot_at,
        "ageSec": age,
        "stale": bool(age is not None and age > STALE_AFTER_SEC),
        "counts": doc.get("counts") or {},
        "items": items,
        "snapshotFile": path,
    })
    if not items:
        payload["error"] = "empty-snapshot"
    payload["avg7d"] = _avg7(root, key)
    return payload
