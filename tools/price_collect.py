#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R19.49 跳蚤价格定时采集：独立可执行程序（本机，仅标准库）。

定位：**不依赖 EFTMap 客户端、不依赖目标机 Python** 的独立采集器。
由 Windows 计划任务每 30 分钟触发一次（`--once`），单次下载 -> 复用
`live_prices.py` 的条件请求 / 锁 / 质量校验 -> 落三类产物：

  <root>/collect/raw/{mode}/{YYYY-MM-DDTHHMMSS}.json.gz
      上游原始载荷（约 17 MB -> gzip 约 2~3 MB），按模式滚动保留 48 份。
  <root>/collect/snapshots/{mode}/{YYYY-MM-DD}/{HHMMSS}.json.gz
      精简价格快照（只有 l/a/u），每 30 分钟一份，按日期保留 90 天。
  <root>/collect/daily/{mode}/{YYYY-MM-DD}.json.gz
      按天锚点：当天最后一份，保留完整价格字段（l/a/lo/hi/b/u），保留 90 天。
      供后续计算 24 小时均价 / 7 天均价（缺日不算、不插值）。

  <root> = %LOCALAPPDATA%\\EFTPrice（`--root` 或 `EFT_PRICE_ROOT` 可覆盖）
  <root>/cache/live-prices-{mode}.json 为运行期缓存，独立程序只读写自己这一份。

首轮运行若发现旧客户端目录 `%LOCALAPPDATA%\\EFTMap\\price-collect` 有数据，
会整体搬进 `<root>\\collect` 并写 `MIGRATION.json`（只搬一次，不会两套同时写）。
若客户端缓存目录 `%LOCALAPPDATA%\\EFTMap\\cache` 已存在，写完运行期缓存后会
best-effort 镜像一份，让客户端市场页仍能读到新鲜数据（`--no-mirror` 关闭）；
镜像失败只告警，采集器本身不读取客户端目录。

不写 `data/flea-prices.json`（构建期快照），不改任何页面 / 服务代码。
抓取失败或数据异常时只写错误记录，**已有快照与状态原样保留**。

用法：
  EFTPriceCollector.exe                       # 双击：显示人话状态
  EFTPriceCollector.exe --once                # 被计划任务调用
  EFTPriceCollector.exe --once --mode pve     # 只抓 PvE
  EFTPriceCollector.exe --once --mode pvps    # 只抓 PvPS（赛季服）
  EFTPriceCollector.exe --status [--json]     # 只读状态（不联网）
  EFTPriceCollector.exe --upload              # 立即上传三模式到 ECS（手动触发）
  EFTPriceCollector.exe --upload-init         # 生成上传凭据模板 <root>\\upload.json
  EFTPriceCollector.exe --upload-status       # 只看云端上传状态
  EFTPriceCollector.exe --install             # 注册计划任务（每 30 分钟）
  EFTPriceCollector.exe --uninstall [--purge] # 删除任务与自启项
  EFTPriceCollector.exe --task-status         # 只看计划任务
  EFTPriceCollector.exe --daemon              # 常驻，每 30 分钟一轮

退出码：
  0 成功（含 304 未变更 / 距上次成功过近跳过）
  1 网络失败
  2 上游数据校验失败
  3 写盘失败
  4 另一个采集进程持锁
  5 计划任务安装 / 卸载失败
"""
from __future__ import annotations

import argparse
import datetime
import gzip
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import live_prices
import price_upload
import r20_fetch_prices as r20

ROOT_ENV = "EFT_PRICE_ROOT"
LEGACY_ROOT_ENV = "EFTMAP_PRICE_ROOT"
APP_NAME = "EFTPrice"
APP_VERSION = "1.2.0"
DATA_DIRNAME = "collect"
CACHE_DIRNAME = "cache"
TASK_NAME = "EFTPriceCollector"
LEGACY_TASKS = ("EFTMap-PriceCollector",)
RUN_REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUES = ("EFTPriceCollector", "EFTMap-PriceCollector")
DEFAULT_INTERVAL_MIN = 30
DEFAULT_RAW_KEEP = 48
DEFAULT_KEEP_DAYS = 90
DEFAULT_MIN_INTERVAL = 20 * 60      # 两次成功抓取的最小间隔（秒），避免重复劳动
DEFAULT_TASK_TIMEOUT_MIN = 30       # 计划任务执行时限
TIMEOUT = 120
LOCK_NAME = ".price-collect.lock"
STATE_NAME = "state.json"
INDEX_NAME = "index.json"
ERROR_NAME = "last-error.json"
HEARTBEAT_NAME = "heartbeat.json"
MIGRATION_NAME = "MIGRATION.json"
FATAL_NAME = "fatal.log"


# ---------------------------------------------------------------- 路径

def _local_appdata() -> str:
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        base = os.path.join(os.path.expanduser("~"), ".local", "share")
    return base


def root_dir(explicit: str | None = None) -> str:
    """程序根目录（collect / cache / 日志都在它下面）。"""
    if explicit:
        return os.path.abspath(explicit)
    override = os.environ.get(ROOT_ENV) or os.environ.get(LEGACY_ROOT_ENV)
    if override:
        return os.path.abspath(override)
    return os.path.join(_local_appdata(), APP_NAME)


def data_dir(app_root: str) -> str:
    """采集产物目录（原 price-collect 的内容整体搬到这里）。"""
    return os.path.join(app_root, DATA_DIRNAME)


def cache_dir(app_root: str) -> str:
    """独立程序的运行期缓存目录（live-prices-*.json）。"""
    return os.path.join(app_root, CACHE_DIRNAME)


def legacy_data_dir() -> str:
    return os.path.join(_local_appdata(), "EFTMap", "price-collect")


def legacy_cache_dir() -> str:
    return os.path.join(_local_appdata(), "EFTMap", "cache")


def _p(root: str, *parts: str) -> str:
    return os.path.join(root, *parts)


# ---------------------------------------------------------------- 旧数据迁移

def _dir_entries(path: str) -> list:
    try:
        return list(os.scandir(path))
    except OSError:
        return []


def _dir_bytes(path: str) -> int:
    total = 0
    for dp, _dn, fn in os.walk(path):
        for name in fn:
            try:
                total += os.path.getsize(os.path.join(dp, name))
            except OSError:
                pass
    return total


def _has_data(directory: str) -> bool:
    if not os.path.isdir(directory):
        return False
    for name in ("raw", "snapshots", "daily", STATE_NAME, HEARTBEAT_NAME):
        if os.path.exists(os.path.join(directory, name)):
            return True
    return False


def migrate_legacy(app_root: str) -> dict | None:
    """把旧 `%LOCALAPPDATA%\\EFTMap\\price-collect` 整体搬进新目录。

    只在「新目录无数据、旧目录有数据」时搬；新旧都有数据时不动，只返回 skipped。
    迁移完成后写 `<root>/MIGRATION.json`，并尝试删掉空的旧目录。
    """
    legacy = legacy_data_dir()
    target = data_dir(app_root)
    if not _has_data(legacy):
        return None
    if os.path.abspath(legacy) == os.path.abspath(target):
        return None
    if _has_data(target):
        return {"status": "skipped", "legacy": legacy, "target": target,
                "reason": "新目录已有数据，未自动迁移（避免两套数据混在一起）"}

    os.makedirs(target, exist_ok=True)
    total_bytes = _dir_bytes(legacy)
    moved = 0
    failed = []
    for entry in _dir_entries(legacy):
        src = entry.path
        dst = os.path.join(target, entry.name)
        try:
            if os.path.exists(dst):
                failed.append(entry.name)
                continue
            shutil.move(src, dst)
            moved += 1
        except OSError as exc:
            failed.append("%s (%s)" % (entry.name, exc))

    record = {
        "schema": 1,
        "at": _iso(local_now()),
        "status": "moved",
        "legacy": legacy,
        "target": target,
        "movedEntries": moved,
        "bytes": total_bytes,
        "failed": failed,
    }
    try:
        write_json_atomic(os.path.join(app_root, MIGRATION_NAME), record)
    except OSError:
        pass
    # 旧目录只有空了才删；缓存目录与客户端其它文件不在迁移范围
    try:
        os.rmdir(legacy)
    except OSError:
        pass
    return record


def raw_dir(root: str, mode: str) -> str:
    return _p(root, "raw", mode)


def snapshot_dir(root: str, mode: str) -> str:
    return _p(root, "snapshots", mode)


def daily_dir(root: str, mode: str) -> str:
    return _p(root, "daily", mode)


def error_path(root: str) -> str:
    return _p(root, ERROR_NAME)


# ---------------------------------------------------------------- 原子写

def _write_atomic_bytes(path: str, blob: bytes) -> None:
    """临时文件 + fsync + os.replace；与 live_prices.write_atomic 同策略。"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(blob)
        fh.flush()
        os.fsync(fh.fileno())
    for attempt in range(5):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.05)


def _dump_json(obj) -> bytes:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _header(headers: dict, name: str):
    """响应头大小写不敏感取值（上游/代理实现不一致时仍能读到 ETag）。"""
    if not headers:
        return None
    lower = name.lower()
    for key, value in headers.items():
        if str(key).lower() == lower:
            return value
    return None


def write_raw_atomic(path: str, body: bytes) -> tuple[int, str]:
    """原始载荷原样 gzip 落盘（不改写、不重新序列化）。"""
    blob = gzip.compress(body, 6)
    _write_atomic_bytes(path, blob)
    return len(blob), hashlib.sha256(body).hexdigest()


def write_gzip_atomic(path: str, obj) -> tuple[int, str]:
    """写入 gzip JSON，返回 (压缩后字节数, 原文 sha256)。"""
    raw = _dump_json(obj)
    blob = gzip.compress(raw, 6)
    _write_atomic_bytes(path, blob)
    return len(blob), hashlib.sha256(raw).hexdigest()


def write_json_atomic(path: str, obj) -> None:
    _write_atomic_bytes(path, _dump_json(obj))


def read_json(path: str):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


# ---------------------------------------------------------------- 时间

def local_now() -> datetime.datetime:
    return datetime.datetime.now().astimezone()


def _iso(dt: datetime.datetime) -> str:
    return dt.isoformat(timespec="seconds")


def _stamp(dt: datetime.datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H%M%S")


# ---------------------------------------------------------------- 状态

def load_state(root: str) -> dict:
    doc = read_json(_p(root, STATE_NAME))
    if not isinstance(doc, dict) or not isinstance(doc.get("modes"), dict):
        return {"schema": 1, "modes": {}}
    return doc


def save_state(root: str, state: dict) -> None:
    state["schema"] = 1
    state["updatedAt"] = _iso(local_now())
    write_json_atomic(_p(root, STATE_NAME), state)


def record_error(root: str, mode: str, stage: str, message: str, status=None) -> None:
    try:
        write_json_atomic(error_path(root), {
            "schema": 1,
            "at": _iso(local_now()),
            "mode": mode,
            "stage": stage,
            "httpStatus": status,
            "error": str(message)[:800],
        })
    except OSError:
        pass


def clear_error(root: str) -> None:
    try:
        os.remove(error_path(root))
    except OSError:
        pass


# ---------------------------------------------------------------- 落盘

def _market_row(full: dict) -> dict:
    """R286 市场大盘的紧凑字段：o 在售挂单数 / c 48h 涨跌率 / d 48h 涨跌额 / v 动能。

    `o` 是**在售挂单数**（lastOfferCount），不是成交笔数——上游无成交量字段，
    UI 必须照实标注。0 / 负数是合法值，不能用价格的正数门槛过滤。
    旧快照缺这些字段时返回空 dict，读取端一律按「无数据」处理，不补 0、不插值。
    """
    c = {}
    for src, dst in (("lastOfferCount", "o"), ("changeLast48hPercent", "c"),
                     ("changeLast48h", "d"), ("velocity", "v")):
        v = full.get(src)
        if isinstance(v, bool) or v is None:
            continue
        if isinstance(v, (int, float, str)) and v != "":
            c[dst] = v
    return c


def _compact_row(full: dict) -> dict:
    c = {}
    for src, dst in (("lastLowPrice", "l"), ("avg24hPrice", "a")):
        v = full.get(src)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and 0 < v < r20.MAX_PRICE:
            c[dst] = v
    upd = full.get("updated")
    if isinstance(upd, str) and upd:
        c["u"] = upd
    market = _market_row(full)
    if market:
        c["mk"] = market
    return c


def _anchor_row(full: dict) -> dict:
    c = {}
    for src, dst in (("lastLowPrice", "l"), ("avg24hPrice", "a"),
                     ("low24hPrice", "lo"), ("high24hPrice", "hi"),
                     ("basePrice", "b")):
        v = full.get(src)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and 0 < v < r20.MAX_PRICE:
            c[dst] = v
    upd = full.get("updated")
    if isinstance(upd, str) and upd:
        c["u"] = upd
    lv = full.get("minLevelForFlea")
    if isinstance(lv, int) and not isinstance(lv, bool):
        c["lv"] = lv
    market = _market_row(full)
    if market:
        c["mk"] = market
    return c


def _items_of(row_fn, payload: dict) -> dict:
    out = {}
    for item_id, full in (payload.get("items") or {}).items():
        if not isinstance(full, dict):
            continue
        row = row_fn(full)
        if row:
            out[str(item_id)] = row
    return out


def write_outputs(root: str, mode: str, payload: dict, body: bytes, now: datetime.datetime,
                  keep_days: int, raw_keep: int) -> dict:
    """写 raw / snapshot / daily，并清理过期文件。任何异常向上抛，由调用方判失败。"""
    stamp = _stamp(now)
    day = now.strftime("%Y-%m-%d")

    raw_file = os.path.join(raw_dir(root, mode), stamp + ".json.gz")
    raw_bytes, raw_sha = write_raw_atomic(raw_file, body)

    snap_file = os.path.join(snapshot_dir(root, mode), day, stamp[11:] + ".json.gz")
    snap = {
        "schema": 1,
        "mode": mode,
        "priceMode": payload.get("priceMode"),
        "snapshotAt": _iso(now),
        "sourceUpdatedMax": (payload.get("meta") or {}).get("sourceUpdatedMax"),
        "counts": payload.get("counts") or {},
        "items": _items_of(_compact_row, payload),
    }
    snap_bytes, _ = write_gzip_atomic(snap_file, snap)

    anchor_file = os.path.join(daily_dir(root, mode), day + ".json.gz")
    anchor = {
        "schema": 1,
        "mode": mode,
        "priceMode": payload.get("priceMode"),
        "date": day,
        "snapshotAt": _iso(now),
        "sourceUpdatedMax": (payload.get("meta") or {}).get("sourceUpdatedMax"),
        "counts": payload.get("counts") or {},
        "items": _items_of(_anchor_row, payload),
    }
    anchor_bytes, _ = write_gzip_atomic(anchor_file, anchor)

    pruned = {
        "raw": prune_raw(raw_dir(root, mode), raw_keep),
        "snapshots": prune_snapshots(snapshot_dir(root, mode), keep_days, now),
        "daily": prune_daily(daily_dir(root, mode), keep_days, now),
    }
    return {
        "rawFile": raw_file, "rawBytes": raw_bytes, "rawSha256": raw_sha,
        "snapshotFile": snap_file, "snapshotBytes": snap_bytes,
        "dailyFile": anchor_file, "dailyBytes": anchor_bytes,
        "pruned": pruned,
    }


def prune_raw(directory: str, keep: int) -> int:
    try:
        names = sorted(n for n in os.listdir(directory) if n.endswith(".json.gz"))
    except OSError:
        return 0
    removed = 0
    for name in names[:max(0, len(names) - max(1, keep))]:
        try:
            os.remove(os.path.join(directory, name))
            removed += 1
        except OSError:
            pass
    return removed


def _cutoff(now: datetime.datetime, keep_days: int) -> datetime.date:
    return now.date() - datetime.timedelta(days=max(1, int(keep_days)) - 1)


def prune_snapshots(directory: str, keep_days: int, now: datetime.datetime) -> int:
    cutoff = _cutoff(now, keep_days)
    removed = 0
    try:
        entries = list(os.scandir(directory))
    except OSError:
        return 0
    for entry in entries:
        if not entry.is_dir():
            continue
        try:
            day = datetime.date.fromisoformat(entry.name)
        except ValueError:
            continue
        if day >= cutoff:
            continue
        try:
            for f in os.scandir(entry.path):
                try:
                    os.remove(f.path)
                    removed += 1
                except OSError:
                    pass
            os.rmdir(entry.path)
        except OSError:
            pass
    return removed


def prune_daily(directory: str, keep_days: int, now: datetime.datetime) -> int:
    cutoff = _cutoff(now, keep_days)
    removed = 0
    try:
        names = list(os.listdir(directory))
    except OSError:
        return 0
    for name in names:
        if not name.endswith(".json.gz"):
            continue
        try:
            day = datetime.date.fromisoformat(name[:-len(".json.gz")])
        except ValueError:
            continue
        if day >= cutoff:
            continue
        try:
            os.remove(os.path.join(directory, name))
            removed += 1
        except OSError:
            pass
    return removed


# ---------------------------------------------------------------- 统计

def _count_files(directory: str, suffix: str = ".json.gz") -> int:
    try:
        return sum(1 for n in os.listdir(directory) if n.endswith(suffix))
    except OSError:
        return 0


def _snapshot_days(directory: str) -> list[str]:
    try:
        days = [e.name for e in os.scandir(directory)
                if e.is_dir() and len(e.name) == 10]
    except OSError:
        return []
    out = []
    for day in days:
        try:
            datetime.date.fromisoformat(day)
        except ValueError:
            continue
        out.append(day)
    return sorted(out)


def _bytes_under(directory: str) -> int:
    total = 0
    for dp, _dn, fn in os.walk(directory):
        for name in fn:
            try:
                total += os.path.getsize(os.path.join(dp, name))
            except OSError:
                pass
    return total


def mode_stats(root: str, mode: str) -> dict:
    snaps = _snapshot_days(snapshot_dir(root, mode))
    daily = [n[:-len(".json.gz")] for n in
             (os.listdir(daily_dir(root, mode)) if os.path.isdir(daily_dir(root, mode)) else [])
             if n.endswith(".json.gz")]
    daily = sorted(d for d in daily if len(d) == 10)
    return {
        "rawCount": _count_files(raw_dir(root, mode)),
        "snapshotDays": len(snaps),
        "snapshotFirstDay": snaps[0] if snaps else None,
        "snapshotLastDay": snaps[-1] if snaps else None,
        "snapshotFiles": sum(_count_files(os.path.join(snapshot_dir(root, mode), d)) for d in snaps),
        "dailyDays": len(daily),
        "dailyFirstDay": daily[0] if daily else None,
        "dailyLastDay": daily[-1] if daily else None,
        "avg7Ready": len(daily) >= r20.HISTORY_AVG7_DAYS,
        "bytes": _bytes_under(_p(root, "raw", mode)) + _bytes_under(_p(root, "snapshots", mode))
                 + _bytes_under(daily_dir(root, mode)),
    }


def update_index(root: str, state: dict) -> dict:
    modes = {}
    for mode in live_prices.MODES:
        entry = state["modes"].get(mode) or {}
        stats = mode_stats(root, mode)
        stats.update({
            "lastSuccessAt": entry.get("lastSuccessAt"),
            "lastCheckedAt": entry.get("lastCheckedAt"),
            "lastStatus": entry.get("lastStatus"),
            "counts": entry.get("counts"),
        })
        modes[mode] = stats
    index = {
        "schema": 1,
        "updatedAt": _iso(local_now()),
        "root": root,
        "keepDays": state.get("keepDays"),
        "rawKeep": state.get("rawKeep"),
        "modes": modes,
    }
    write_json_atomic(_p(root, INDEX_NAME), index)
    return index


# ---------------------------------------------------------------- 抓取

def _conditional_cache(state: dict, mode: str) -> dict | None:
    entry = state["modes"].get(mode) or {}
    etag = entry.get("etag")
    last_modified = entry.get("lastModified")
    if not etag and not last_modified:
        return None
    return {"http": {"etag": etag, "lastModified": last_modified}}


def _has_local_copy(root: str, mode: str) -> bool:
    return _count_files(raw_dir(root, mode)) > 0 and len(_snapshot_days(snapshot_dir(root, mode))) > 0


def collect_mode(root: str, mode: str, state: dict, args,
                 live_cache_dir: str | None = None,
                 mirror_cache_dir: str | None = None) -> dict:
    """抓一个模式。返回 {mode, ok, exitCode, skipped, notModified, message}。"""
    mode = live_prices.normalize_mode(mode)
    url = args.source or live_prices.MODES[mode]["source"]
    entry = dict(state["modes"].get(mode) or {})
    now = local_now()

    last_ok = live_prices.parse_time(entry.get("lastSuccessAt"))
    if last_ok and not args.force:
        age = (now - last_ok).total_seconds()
        if 0 <= age < max(60, args.min_interval):
            return {"mode": mode, "ok": True, "exitCode": 0, "skipped": True,
                    "notModified": False, "status": None,
                    "message": "距上次成功 %d 秒（< %d），本轮跳过" % (age, args.min_interval)}

    cache = _conditional_cache(state, mode)
    if cache and not _has_local_copy(root, mode):
        # 状态说有 ETag，但本地产物已被清理：不能发条件请求，否则 304 会让我们无数据可用
        cache = None

    try:
        result = live_prices.fetch_url(url, proxy=args.proxy, timeout=args.timeout, cache=cache)
    except RuntimeError as exc:
        record_error(root, mode, "http", str(exc))
        return {"mode": mode, "ok": False, "exitCode": 1, "skipped": False,
                "notModified": False, "status": None, "message": str(exc)}
    except OSError as exc:
        msg = "下载失败：%s: %s" % (type(exc).__name__, exc)
        record_error(root, mode, "network", msg)
        return {"mode": mode, "ok": False, "exitCode": 1, "skipped": False,
                "notModified": False, "status": None, "message": msg}

    http = {
        "status": result.status,
        "notModified": result.not_modified,
        "etag": _header(result.headers, "ETag"),
        "lastModified": _header(result.headers, "Last-Modified"),
        "bytes": 0 if result.body is None else len(result.body),
        "sha256": None if result.body is None else hashlib.sha256(result.body).hexdigest(),
    }

    if result.not_modified:
        entry.update({
            "lastCheckedAt": _iso(now),
            "lastStatus": 304,
            "etag": http["etag"] or entry.get("etag"),
            "lastModified": http["lastModified"] or entry.get("lastModified"),
        })
        state["modes"][mode] = entry
        return {"mode": mode, "ok": True, "exitCode": 0, "skipped": False,
                "notModified": True, "status": 304,
                "message": "304 未变更，沿用已有快照（不重复落盘）"}

    try:
        doc = json.loads(result.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        msg = "JSON 解析失败：%s" % exc
        record_error(root, mode, "parse", msg, result.status)
        return {"mode": mode, "ok": False, "exitCode": 2, "skipped": False,
                "notModified": False, "status": result.status, "message": msg}

    try:
        payload = r20.build_cache(doc, url, mode)
    except ValueError as exc:
        record_error(root, mode, "validate", str(exc), result.status)
        return {"mode": mode, "ok": False, "exitCode": 2, "skipped": False,
                "notModified": False, "status": result.status, "message": str(exc)}

    if args.dry_run:
        return {"mode": mode, "ok": True, "exitCode": 0, "skipped": True,
                "notModified": False, "status": result.status,
                "message": "dry-run：校验通过（上游 %d 条，含最近低价 %d 条），不写盘"
                           % (payload["counts"]["itemsUpstream"],
                              payload["counts"]["withLastLowPrice"])}

    try:
        written = write_outputs(root, mode, payload, result.body, now, args.keep_days, args.raw_keep)
    except OSError as exc:
        msg = "写盘失败：%s" % exc
        record_error(root, mode, "write", msg, result.status)
        return {"mode": mode, "ok": False, "exitCode": 3, "skipped": False,
                "notModified": False, "status": result.status, "message": msg}

    # 同步刷新本程序自己的运行期缓存（独立目录，不依赖客户端）。
    # 失败只记为告警，不影响已经落盘的采集产物。
    live_warning = None
    try:
        live_payload = live_prices.build_cache(doc, mode, url, ttl_sec=live_prices.DEFAULT_TTL, http=http)
        live_prices.write_atomic(live_prices.cache_path(mode, live_cache_dir), live_payload)
        live_prices.record_attempt(mode, True, {
            "stage": "scheduled", "status": result.status,
            "notModified": False, "bytes": http["bytes"],
            "sha256": http["sha256"], "count": len(live_payload["items"]),
        }, directory=live_cache_dir)
        # 客户端已安装时 best-effort 镜像一份，保证市场页仍能读到新鲜数据；
        # 只是额外写一份，采集器不读取客户端目录，失败也不影响本轮结果。
        if mirror_cache_dir:
            try:
                live_prices.write_atomic(live_prices.cache_path(mode, mirror_cache_dir), live_payload)
                live_prices.record_attempt(mode, True, {
                    "stage": "mirror", "status": result.status,
                    "notModified": False, "bytes": http["bytes"],
                    "sha256": http["sha256"], "count": len(live_payload["items"]),
                }, directory=mirror_cache_dir)
            except Exception as exc:  # noqa: BLE001
                live_warning = "客户端缓存镜像失败（不影响采集）：%s: %s" % (type(exc).__name__, exc)
    except Exception as exc:  # noqa: BLE001
        live_warning = "运行期缓存刷新失败（不影响采集产物）：%s: %s" % (type(exc).__name__, exc)

    entry.update({
        "lastCheckedAt": _iso(now),
        "lastSuccessAt": payload.get("lastSuccessAt") or _iso(now),
        "lastStatus": result.status,
        "etag": http["etag"],
        "lastModified": http["lastModified"],
        "sha256": http["sha256"],
        "bytes": http["bytes"],
        "counts": payload.get("counts"),
        "rawFile": os.path.basename(written["rawFile"]),
        "snapshotFile": os.path.relpath(written["snapshotFile"], root),
        "dailyFile": os.path.relpath(written["dailyFile"], root),
    })
    state["modes"][mode] = entry

    message = ("已落盘：上游 %d 条 → 精简 %d 条（最近低价 %d）；raw %.1f MB / snapshot %.0f KB / daily %.0f KB"
               % (payload["counts"]["itemsUpstream"], payload["counts"]["itemsWithPrice"],
                  payload["counts"]["withLastLowPrice"],
                  written["rawBytes"] / 1048576, written["snapshotBytes"] / 1024,
                  written["dailyBytes"] / 1024))
    if live_warning:
        message += "；" + live_warning
    return {"mode": mode, "ok": True, "exitCode": 0, "skipped": False,
            "notModified": False, "status": result.status, "message": message,
            "written": written}


def collect_once(args) -> int:
    app_root = root_dir(args.root)
    os.makedirs(app_root, exist_ok=True)

    try:
        migrated = migrate_legacy(app_root)
    except OSError as exc:
        print("[warn] 旧数据迁移失败：%s" % exc, file=sys.stderr)
        migrated = None
    if migrated and migrated.get("status") == "moved":
        print("[migrate] 旧目录 %s -> %s：迁移 %d 个条目 / %.1f MB%s"
              % (migrated["legacy"], migrated["target"], migrated["movedEntries"],
                 migrated.get("bytes", 0) / 1048576,
                 ("；未迁移：%s" % ", ".join(migrated["failed"])) if migrated["failed"] else ""))
    elif migrated and migrated.get("status") == "skipped":
        print("[migrate] %s" % migrated["reason"], file=sys.stderr)

    root = data_dir(app_root)
    os.makedirs(root, exist_ok=True)
    live_cache = cache_dir(app_root)
    os.makedirs(live_cache, exist_ok=True)
    mirror = None
    if not args.no_mirror:
        legacy_cache = legacy_cache_dir()
        if os.path.isdir(legacy_cache) and os.path.abspath(legacy_cache) != os.path.abspath(live_cache):
            mirror = legacy_cache

    lock = _p(root, LOCK_NAME)
    if not live_prices.acquire_lock(lock):
        print("[skip] 另一个采集进程持锁，本轮跳过", file=sys.stderr)
        return 4

    started = time.time()
    state = load_state(root)
    state["keepDays"] = args.keep_days
    state["rawKeep"] = args.raw_keep
    results = []
    try:
        if args.proxy:
            ok, why = live_prices.proxy_reachable(args.proxy)
            if not ok:
                record_error(root, "all", "proxy", why)
                print("[fail] %s" % why, file=sys.stderr)
                return 1
        modes = list(live_prices.MODES) if str(args.mode).lower() == "all" \
            else [live_prices.normalize_mode(args.mode)]
        for mode in modes:
            res = collect_mode(root, mode, state, args, live_cache, mirror)
            results.append(res)
            tag = live_prices.MODES[mode]["label"]
            stream = sys.stdout if res["ok"] else sys.stderr
            print("[%s] %s %s" % (tag, "OK" if res["ok"] else "FAIL", res["message"]), file=stream)
    finally:
        try:
            if any(r.get("status") == 200 and r.get("ok") for r in results):
                save_state(root, state)
                update_index(root, state)
                clear_error(root)
            else:
                save_state(root, state)
                update_index(root, state)
        except OSError as exc:
            print("[warn] 状态写入失败：%s" % exc, file=sys.stderr)
        _write_heartbeat(root, results, time.time() - started)
        live_prices.release_lock(lock)
        # R275：上传放进 finally —— 某一模式抓取抛异常时，异常会跳过函数末尾的
        # _auto_upload，云端就一直停在上一轮；已落盘的快照仍应尽力送上去。
        # R79：上传与采集解耦，上传成败不影响采集退出码。
        # R221：节流 1500 s（略小于 30 分钟采集周期），保证每轮都能上传。
        _auto_upload(app_root, args)

    if any(not r["ok"] for r in results):
        return max((r["exitCode"] for r in results if not r["ok"]), default=1)
    return 0


def _auto_upload(app_root: str, args) -> None:
    """本轮采集结束后尝试云端上传；任何异常都只告警，绝不影响采集退出码。"""
    if getattr(args, "no_upload", False):
        return
    try:
        result = price_upload.tick(app_root)
    except Exception as exc:  # noqa: BLE001 —— 上传不能拖垮采集
        print("[upload][warn] %s: %s" % (type(exc).__name__, exc), file=sys.stderr)
        return
    if result.get("skipped"):
        return
    for mode, item in (result.get("modes") or {}).items():
        label = live_prices.MODES.get(mode, {}).get("label", mode)
        if item.get("status") == "uploaded":
            print("[upload] %s OK（%d 条，generatedAt %s）"
                  % (label, item.get("items", 0), item.get("generatedAt")))
        elif item.get("status") == "identical":
            print("[upload] %s 与上次已上传数据相同，跳过（幂等）" % label)
        elif item.get("ok"):
            continue
        else:
            print("[upload][fail] %s：%s（已保留待上传状态，下轮重试）"
                  % (label, item.get("error") or item.get("status")), file=sys.stderr)


def print_upload_status(args) -> int:
    app_root = root_dir(args.root)
    info = price_upload.status(app_root)
    print("云端上传凭据：%s" % info["configPath"])
    print("  状态：%s / %s" % ("已启用" if info["enabled"] else "未启用",
                              "已配置" if info["configured"] else "未配置 URL 或 token"))
    print("  接口：%s" % (info["endpoint"] or "—"))
    print("  下次上传：%s" % (info["nextUploadAt"] or "下一轮采集结束后"))
    print("  待上传：%s" % (", ".join(info["pending"]) if info["pending"] else "无"))
    for mode in ("regular", "pve", "pvps"):
        entry = info["modes"].get(mode) or {}
        label = live_prices.MODES.get(mode, {}).get("label", mode)
        print("  [%s] 上次尝试 %s · 上次成功 %s · %s%s"
              % (label, entry.get("lastAttemptAt") or "—", entry.get("lastSuccessAt") or "—",
                 entry.get("lastStatus") or "—",
                 ("（%s）" % entry["lastError"]) if entry.get("lastError") else ""))
    return 0


def _mode_list(args) -> list:
    if str(args.mode).lower() == "all":
        return list(live_prices.MODES)
    return [live_prices.normalize_mode(args.mode)]


def upload_now(args) -> int:
    app_root = root_dir(args.root)
    try:
        modes = _mode_list(args)
    except ValueError as exc:
        print("[错误] %s" % exc, file=sys.stderr)
        return 2
    result = price_upload.upload_all(app_root, modes, force=True)
    if result.get("skipped"):
        reason = result.get("reason")
        if reason == "disabled":
            print("[错误] 上传未启用：请先运行 --upload-init，再在 %s 里填写 "
                  "enabled=true、url、token" % price_upload.config_path(app_root), file=sys.stderr)
        elif reason == "not-configured":
            print("[错误] 上传未配置：请在 %s 里填写 url 与 token"
                  % price_upload.config_path(app_root), file=sys.stderr)
        else:
            print("[跳过] %s" % reason)
        return 1
    for mode, item in (result.get("modes") or {}).items():
        label = live_prices.MODES.get(mode, {}).get("label", mode)
        if item.get("status") == "uploaded":
            print("[%s] 上传成功：%d 条，generatedAt %s"
                  % (label, item.get("items", 0), item.get("generatedAt")))
        elif item.get("status") == "identical":
            print("[%s] 与上次已上传数据相同，跳过（幂等）" % label)
        else:
            print("[%s] 上传失败：%s" % (label, item.get("error") or item.get("status")), file=sys.stderr)
    return 0 if result.get("ok") else 1


def init_upload_config(args) -> int:
    app_root = root_dir(args.root)
    result = price_upload.init_config(app_root)
    if result["created"]:
        print("已生成上传凭据模板：%s" % result["path"])
    else:
        print("上传凭据已存在（未覆盖）：%s" % result["path"])
    print("请填写 enabled=true、url（ECS 基地址）、token（采集机专用 token）；"
          "如使用自签 CA，再填 caFile。该文件不会进版本库。")
    return 0


def _write_heartbeat(root: str, results: list, duration: float) -> None:
    try:
        write_json_atomic(_p(root, HEARTBEAT_NAME), {
            "schema": 1,
            "at": _iso(local_now()),
            "pid": os.getpid(),
            "durationSec": round(duration, 2),
            "modes": {r["mode"]: {"ok": r["ok"], "status": r.get("status"),
                                  "notModified": r.get("notModified"),
                                  "skipped": r.get("skipped")} for r in results},
        })
    except OSError:
        pass


# ---------------------------------------------------------------- 计划任务

def _run(cmd, timeout: int = 25) -> tuple:
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, "", str(exc)

    def _decode(blob: bytes) -> str:
        if not blob:
            return ""
        # schtasks 的输出编码随控制台代码页变化（chcp 65001 时是 UTF-8，
        # 默认中文控制台是 GBK）；先按 UTF-8 严格解，失败再退回本地编码。
        for enc in ("utf-8", "mbcs", "gbk"):
            try:
                return blob.decode(enc)
            except (UnicodeDecodeError, LookupError):
                continue
        return blob.decode("utf-8", "replace")

    return proc.returncode, _decode(proc.stdout), _decode(proc.stderr)


_TASK_LABELS = (
    ("nextRun", ("Next Run Time", "下次运行时间")),
    ("lastRun", ("Last Run Time", "上次运行时间")),
    ("lastResult", ("Last Result", "上次结果")),
    ("taskToRun", ("Task To Run", "要运行的任务")),
    ("state", ("Status", "状态")),
)


def _parse_task_list(text: str) -> dict:
    """从 `schtasks /Query /FO LIST /V` 的本地化输出里取关键字段。"""
    out = {}
    for line in text.splitlines():
        for key, labels in _TASK_LABELS:
            if key in out:
                continue
            for label in labels:
                if line.startswith(label):
                    rest = line[len(label):].lstrip(" :：")
                    if rest:
                        out[key] = rest.strip()
                    break
    return out


def task_info(name: str = TASK_NAME) -> dict:
    code, out, err = _run(["schtasks", "/Query", "/TN", name, "/FO", "LIST", "/V"])
    info = {"name": name, "installed": code == 0}
    if code != 0:
        info["error"] = (err or out).strip() or "任务不存在"
        return info
    info.update(_parse_task_list(out))
    return info


def task_command() -> tuple:
    """计划任务要执行的 (命令, 参数)。打包后必须指向 exe 本身。"""
    if getattr(sys, "frozen", False):
        return os.path.abspath(sys.executable), "--once --mode all"
    script = os.path.abspath(__file__)
    exe = sys.executable
    pyw = os.path.join(os.path.dirname(exe), "pythonw.exe")
    if os.path.isfile(pyw):
        exe = pyw
    return exe, '"%s" --once --mode all' % script


def _xml_escape(text) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def _task_xml(command: str, arguments: str, workdir: str,
              interval_min: int, timeout_min: int) -> str:
    start = local_now().replace(second=0, microsecond=0) + datetime.timedelta(minutes=1)
    return """<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>EFT 跳蚤价格采集（独立程序，每 {interval} 分钟抓取一次）</Description>
    <URI>\\{name}</URI>
  </RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>{start}</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByDay>
        <DaysInterval>1</DaysInterval>
      </ScheduleByDay>
      <Repetition>
        <Interval>PT{interval}M</Interval>
        <Duration>P1D</Duration>
        <StopAtDurationEnd>false</StopAtDurationEnd>
      </Repetition>
    </CalendarTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>{user}</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT{timeout}M</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{command}</Command>
      <Arguments>{arguments}</Arguments>
      <WorkingDirectory>{workdir}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
""".format(
        interval=max(5, int(interval_min)),
        timeout=max(5, int(timeout_min)),
        name=_xml_escape(TASK_NAME),
        start=start.strftime("%Y-%m-%dT%H:%M:%S"),
        user=_xml_escape(os.environ.get("USERNAME") or ""),
        command=_xml_escape(command),
        arguments=_xml_escape(arguments),
        workdir=_xml_escape(workdir),
    )


def _task_exists(name: str) -> bool:
    code, _out, _err = _run(["schtasks", "/Query", "/TN", name], timeout=15)
    return code == 0


def _remove_run_values() -> list:
    """删除 HKCU\\...\\Run 下与本程序相关的自启项（历史遗留）。"""
    removed = []
    try:
        import winreg
    except ImportError:
        return removed
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_REG_PATH, 0,
                             winreg.KEY_READ | winreg.KEY_SET_VALUE)
    except OSError:
        return removed
    try:
        with key:
            for value in RUN_VALUES:
                try:
                    winreg.QueryValueEx(key, value)
                except FileNotFoundError:
                    continue
                try:
                    winreg.DeleteValue(key, value)
                    removed.append(value)
                except OSError:
                    pass
    except OSError:
        pass
    return removed


def install_task(args) -> int:
    app_root = root_dir(args.root)
    os.makedirs(data_dir(app_root), exist_ok=True)
    os.makedirs(cache_dir(app_root), exist_ok=True)
    try:
        record = migrate_legacy(app_root)
        if record and record.get("status") == "moved":
            print("[migrate] 旧数据已迁到 %s（%d 个条目 / %.1f MB）"
                  % (record["target"], record["movedEntries"], record.get("bytes", 0) / 1048576))
    except OSError as exc:
        print("[warn] 旧数据迁移失败：%s" % exc, file=sys.stderr)

    command, arguments = task_command()
    interval = max(5, int(args.interval))
    timeout_min = max(interval, int(args.task_timeout))
    xml = _task_xml(command, arguments, os.path.dirname(command), interval, timeout_min)

    code, out, err = 1, "", ""
    fd, tmp = tempfile.mkstemp(prefix="eftprice-task-", suffix=".xml")
    os.close(fd)
    try:
        with open(tmp, "w", encoding="utf-16", newline="\r\n") as fh:
            fh.write(xml)
        code, out, err = _run(["schtasks", "/Create", "/TN", TASK_NAME, "/XML", tmp, "/F"], timeout=40)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    if code != 0:
        print("[fail] 计划任务创建失败（退出码 %d）：%s"
              % (code, (err or out).strip()), file=sys.stderr)
        return 5

    # 旧版 pythonw 任务必须清掉，否则新旧两套会同时抓
    for legacy in LEGACY_TASKS:
        if _task_exists(legacy):
            c2, _o2, _e2 = _run(["schtasks", "/Delete", "/TN", legacy, "/F"], timeout=15)
            print("[clean] 旧任务 %s %s" % (legacy, "已删除" if c2 == 0 else "删除失败"))
    removed = _remove_run_values()
    if removed:
        print("[clean] 已删除自启项：%s" % ", ".join(removed))

    info = task_info()
    print("[ok] 已注册计划任务：%s" % TASK_NAME)
    print("     执行：%s" % (info.get("taskToRun") or "%s %s" % (command, arguments)))
    print("     状态：%s；上次运行 %s；下次运行 %s"
          % (info.get("state", "?"), info.get("lastRun", "无"), info.get("nextRun", "?")))
    print("     间隔：每 %d 分钟；执行时限 %d 分钟；错过补跑；多实例忽略" % (interval, timeout_min))
    print("     数据目录：%s" % data_dir(app_root))
    print("     运行缓存：%s" % cache_dir(app_root))
    return 0


def uninstall_task(args) -> int:
    removed = []
    failed = []
    for name in (TASK_NAME,) + LEGACY_TASKS:
        if not _task_exists(name):
            continue
        code, out, err = _run(["schtasks", "/Delete", "/TN", name, "/F"], timeout=15)
        if code == 0:
            removed.append(name)
        else:
            failed.append("%s（%s）" % (name, (err or out).strip()))
    values = _remove_run_values()

    print("[ok] 已删除计划任务：%s" % (", ".join(removed) or "无"))
    print("[ok] 已删除自启项：%s" % (", ".join(values) or "无"))

    app_root = root_dir(args.root)
    if args.purge:
        shutil.rmtree(app_root, ignore_errors=True)
        print("[ok] 已删除数据目录：%s" % app_root)
    else:
        print("[keep] 数据目录保留：%s（要一并删除请加 --purge）" % app_root)
    if failed:
        print("[fail] %s" % "；".join(failed), file=sys.stderr)
        return 5
    return 0


def print_task_status() -> int:
    info = task_info()
    print("计划任务：%s" % TASK_NAME)
    if not info.get("installed"):
        print("  未安装（%s）" % info.get("error", "任务不存在"))
        return 1
    command, arguments = task_command()
    print("  执行：%s" % (info.get("taskToRun") or "%s %s" % (command, arguments)))
    print("  上次运行：%s（结果 %s）" % (info.get("lastRun", "无"), info.get("lastResult", "?")))
    print("  下次运行：%s" % info.get("nextRun", "?"))
    print("  状态：%s" % info.get("state", "?"))
    return 0


# ---------------------------------------------------------------- 状态

def status_payload(args) -> dict:
    app_root = root_dir(args.root)
    root = data_dir(app_root)
    state = load_state(root)
    modes = {}
    for mode in live_prices.MODES:
        entry = state["modes"].get(mode) or {}
        st = mode_stats(root, mode)
        st.update({
            "label": live_prices.MODES[mode]["label"],
            "priceMode": live_prices.MODES[mode]["priceMode"],
            "source": live_prices.MODES[mode]["source"],
            "lastSuccessAt": entry.get("lastSuccessAt"),
            "lastCheckedAt": entry.get("lastCheckedAt"),
            "lastStatus": entry.get("lastStatus"),
            "counts": entry.get("counts"),
            "etag": entry.get("etag"),
        })
        modes[mode] = st
    legacy_cache = legacy_cache_dir()
    return {
        "ok": True,
        "app": {
            "name": APP_NAME,
            "version": APP_VERSION,
            "frozen": bool(getattr(sys, "frozen", False)),
            "executable": os.path.abspath(sys.executable),
        },
        "appRoot": app_root,
        "root": root,
        "cacheDir": cache_dir(app_root),
        "mirrorDir": (legacy_cache if os.path.isdir(legacy_cache)
                      and not getattr(args, "no_mirror", False) else None),
        "legacyDataDir": legacy_data_dir(),
        "legacyDataExists": os.path.isdir(legacy_data_dir()),
        "migration": read_json(os.path.join(app_root, MIGRATION_NAME)),
        "task": task_info(),
        "keepDays": state.get("keepDays", DEFAULT_KEEP_DAYS),
        "rawKeep": state.get("rawKeep", DEFAULT_RAW_KEEP),
        "lastError": read_json(error_path(root)),
        "heartbeat": read_json(_p(root, HEARTBEAT_NAME)),
        "upload": price_upload.status(app_root),
        "modes": modes,
    }


def _verdict(last_status) -> str:
    if last_status == 304:
        return "HTTP 304 未变更（沿用已有快照）"
    if last_status == 200:
        return "HTTP 200 新数据已落盘"
    if last_status:
        return "HTTP %s" % last_status
    return "尚无记录"


def print_status(args) -> int:
    payload = status_payload(args)
    if getattr(args, "json", False):
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    app = payload["app"]
    print("EFT 跳蚤价格采集器 v%s（%s）"
          % (app["version"], "独立 exe，无需 Python / 无需客户端" if app["frozen"] else "源码运行"))
    print("程序：%s" % app["executable"])
    print("数据目录：%s（快照保留 %d 天 / raw 保留 %d 份）"
          % (payload["root"], payload["keepDays"], payload["rawKeep"]))
    print("运行缓存：%s" % payload["cacheDir"])
    if payload.get("mirrorDir"):
        print("客户端镜像：%s（只额外写一份，程序不读取客户端目录）" % payload["mirrorDir"])

    task = payload["task"]
    print("")
    print("计划任务：%s" % TASK_NAME)
    if task.get("installed"):
        print("  执行：%s" % (task.get("taskToRun") or "未知"))
        print("  上次运行：%s（结果 %s）" % (task.get("lastRun") or "无", task.get("lastResult") or "?"))
        print("  下次运行：%s" % (task.get("nextRun") or "未知"))
        print("  状态：%s" % (task.get("state") or "?"))
    else:
        print("  未安装（双击 install.bat 或运行 --install 注册每 30 分钟采集）")

    heartbeat = payload.get("heartbeat")
    print("")
    if heartbeat:
        print("最近一次采集：%s（耗时 %.2f 秒）"
              % (heartbeat.get("at"), heartbeat.get("durationSec") or 0))
    else:
        print("最近一次采集：无记录")

    for st in payload["modes"].values():
        counts = st.get("counts") or {}
        if counts:
            counts_text = ("上游 %s 条 / 精简 %s 条 / 最近低价 %s 条"
                           % (counts.get("itemsUpstream"), counts.get("itemsWithPrice"),
                              counts.get("withLastLowPrice")))
        else:
            counts_text = "条数未知（尚未成功抓取过）"
        print("[%s] %s；%s" % (st["label"], _verdict(st.get("lastStatus")), counts_text))
        print("    上次成功 %s；raw %d 份；快照 %d 天 / %d 份；锚点 %d 天；7 日均价%s；占用 %.1f MB"
              % (st.get("lastSuccessAt") or "无", st["rawCount"], st["snapshotDays"],
                 st["snapshotFiles"], st["dailyDays"],
                 "就绪" if st["avg7Ready"] else "待累积", st["bytes"] / 1048576))

    err = payload.get("lastError")
    print("")
    if err:
        print("最近一次错误：%s [%s / HTTP %s] %s"
              % (err.get("at"), err.get("stage"), err.get("httpStatus"), err.get("error")))
    else:
        print("最近一次错误：无")

    upload = payload.get("upload") or {}
    print("")
    print("云端上传（每小时一次，失败保留待上传）：")
    print("  凭据：%s（%s）" % (upload.get("configPath") or "—",
                              "已配置" if upload.get("configured") else "未配置"))
    print("  状态：%s；接口：%s" % ("已启用" if upload.get("enabled") else "未启用",
                                  upload.get("endpoint") or "—"))
    print("  上次成功：%s；下次约：%s；待上传：%s"
          % (upload.get("lastSuccessAt") or "无", upload.get("nextUploadAt") or "下一轮采集后",
             ", ".join(upload.get("pending") or []) or "无"))

    migration = payload.get("migration")
    if migration and migration.get("status") == "moved":
        print("迁移记录：%s 已从 %s 迁入 %d 个条目（详见 MIGRATION.json）"
              % (migration.get("at"), migration.get("legacy"), migration.get("movedEntries")))
    elif payload.get("legacyDataExists"):
        print("提示：旧目录 %s 仍有数据，可用 --install 迁移或手动删除" % payload["legacyDataDir"])
    return 0


def pause_if_interactive() -> None:
    if os.environ.get("EFT_PRICE_NO_PAUSE"):
        return
    try:
        if not sys.stdin or not sys.stdin.isatty():
            return
        input("\n按回车键退出...")
    except (EOFError, KeyboardInterrupt):
        pass


# ---------------------------------------------------------------- 常驻

def run_daemon(args) -> int:
    interval = max(5, int(args.interval)) * 60
    print("[daemon] 启动，每 %d 分钟一轮；目录 %s"
          % (interval // 60, data_dir(root_dir(args.root))))
    while True:
        try:
            collect_once(args)
        except KeyboardInterrupt:
            print("[daemon] 收到中断，退出")
            return 0
        except Exception as exc:  # noqa: BLE001
            print("[daemon] 本轮异常：%s: %s" % (type(exc).__name__, exc), file=sys.stderr)
        # 对齐到下一个整 30 分钟边界；休眠/唤醒后 sleep 会晚返回，循环顶部立即补跑一次
        now = local_now().timestamp()
        nxt = (int(now // interval) + 1) * interval
        wait = max(5.0, nxt - now)
        print("[daemon] 下一轮 %s（%.0f 秒后）"
              % (datetime.datetime.fromtimestamp(nxt).astimezone().strftime("%H:%M:%S"), wait))
        time.sleep(wait)


# ---------------------------------------------------------------- 命令行

def main(argv=None) -> int:
    for key in ("NO_PROXY", "no_proxy"):
        os.environ.setdefault(key, "localhost,127.0.0.1,::1")
    # R221：必须在 argparse 之前把输出流切到 UTF-8。`--help` 是在 parse_args 内部就打印的，
    # 晚一步设置就会走 Windows 默认 cp1252，中文帮助文案直接 UnicodeEncodeError 崩溃
    # （打包成 exe 后同样如此，`EFTPriceCollector.exe --help` 实测必崩）。
    for stream in (sys.stdout, sys.stderr):
        try:
            # 控制台（双击）交给 Windows 的 Unicode 控制台；被重定向时统一 UTF-8，
            # 避免打包后默认编码不是 GBK 而把中文替换成问号。
            if stream is None:
                continue
            if stream.isatty():
                stream.reconfigure(errors="replace")
            else:
                stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass

    ap = argparse.ArgumentParser(description="跳蚤价格定时采集（独立程序；无参数时显示状态）")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true", help="跑一轮（计划任务使用）")
    mode.add_argument("--daemon", action="store_true", help="常驻，按 --interval 循环")
    mode.add_argument("--status", action="store_true", help="只读状态（不联网，默认行为）")
    mode.add_argument("--install", action="store_true", help="注册计划任务（每 30 分钟）")
    mode.add_argument("--uninstall", action="store_true", help="删除计划任务与自启项")
    mode.add_argument("--task-status", action="store_true", help="只看计划任务")
    mode.add_argument("--upload", action="store_true", help="立即上传三种模式到 ECS（不抓取）")
    mode.add_argument("--upload-status", action="store_true", help="只看云端上传状态")
    mode.add_argument("--upload-init", action="store_true", help="生成上传凭据模板（默认关闭）")
    ap.add_argument("--purge", action="store_true", help="配合 --uninstall 一并删除数据目录")
    ap.add_argument("--mode", default="all", help="regular(PvP) / pve / pvps / all（默认 all，覆盖三种模式）")
    ap.add_argument("--root", default=None,
                    help="程序根目录（默认 %%LOCALAPPDATA%%\\EFTPrice）")
    ap.add_argument("--interval", type=int, default=DEFAULT_INTERVAL_MIN,
                    help="采集间隔分钟（常驻 / 计划任务，默认 30）")
    ap.add_argument("--task-timeout", type=int, default=DEFAULT_TASK_TIMEOUT_MIN,
                    help="计划任务执行时限分钟（默认 30）")
    ap.add_argument("--min-interval", type=int, default=DEFAULT_MIN_INTERVAL,
                    help="两次成功抓取的最小间隔秒（默认 1200）")
    ap.add_argument("--raw-keep", type=int, default=DEFAULT_RAW_KEEP, help="原始快照保留份数（默认 48）")
    ap.add_argument("--keep-days", type=int, default=DEFAULT_KEEP_DAYS, help="快照/锚点保留天数（默认 90）")
    ap.add_argument("--proxy", default=live_prices.DEFAULT_PROXY,
                    help="HTTP(S) 代理（默认 %s）" % live_prices.DEFAULT_PROXY)
    ap.add_argument("--no-proxy", action="store_true", help="直连")
    ap.add_argument("--no-mirror", action="store_true", help="不向客户端缓存目录镜像运行期缓存")
    ap.add_argument("--no-upload", action="store_true",
                    help="本轮不尝试云端上传（默认 25 分钟节流，30 分钟采集每轮都会上传）")
    ap.add_argument("--timeout", type=int, default=TIMEOUT, help="单次请求超时秒（默认 120）")
    ap.add_argument("--source", default=None, help="覆盖上游地址（只能配合单一 --mode）")
    ap.add_argument("--force", action="store_true", help="忽略最小间隔，强制本轮抓取")
    ap.add_argument("--dry-run", action="store_true", help="下载 + 校验，不写盘")
    ap.add_argument("--json", action="store_true", help="--status 输出 JSON")
    args = ap.parse_args(argv)

    if args.source and str(args.mode).lower() == "all":
        print("[错误] --source 只能配合单个 --mode 使用", file=sys.stderr)
        return 2
    args.proxy = None if args.no_proxy else (args.proxy or None)

    if args.uninstall:
        return uninstall_task(args)
    if args.install:
        return install_task(args)
    if args.task_status:
        return print_task_status()
    if args.upload_init:
        return init_upload_config(args)
    if args.upload_status:
        return print_upload_status(args)
    if args.upload:
        return upload_now(args)
    if args.status:
        return print_status(args)
    if args.daemon:
        return run_daemon(args)
    if args.once:
        return collect_once(args)
    # 无参数（双击）：显示人话状态，不联网
    rc = print_status(args)
    pause_if_interactive()
    return rc


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException:  # noqa: BLE001 —— 无控制台场景下至少留下痕迹
        import traceback
        try:
            _root = root_dir(None)
            os.makedirs(_root, exist_ok=True)
            with open(os.path.join(_root, FATAL_NAME), "a", encoding="utf-8") as _fh:
                _fh.write("[%s] %s\n" % (_iso(local_now()), traceback.format_exc()[-4000:]))
        except OSError:
            pass
        # R275：崩溃前最后一次兜底，把已落盘的最新快照送上去，
        # 不让一次异常造成云端行情断更几小时。tick 自带节流与幂等，重复调用无害。
        try:
            price_upload.tick(root_dir(None))
        except Exception:
            pass
        raise

