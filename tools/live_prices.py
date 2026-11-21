#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R42 可选在线行情抓取器（**仅 Python 标准库**）。

默认不联网：本工具只在用户显式执行 `--fetch`、且服务端 `livePrices.enabled=true` 时才访问外网。
运行期（网页 / 本地服务）只读本工具写下的缓存文件，不在请求线程里联网。

数据源（2026-11-04 经代理实测，详见 docs/r42-live-prices-ledger.md）：
  - PvP：`https://json.tarkov.dev/regular/items`  —— 上游把「常规 PvP」的路径键叫 `regular`，
    不是 PvE。实测：5498 个 id 在 /regular 与 /pve 两侧都存在；其中两侧都有 lastLowPrice 的
    3529 个 id 里同值仅 84 个（2.38%），确认 regular = PvP。
  - PvE：`https://json.tarkov.dev/pve/items`
  - 两个端点均 HTTP 200、约 17 MB、带 `ETag` 与 `Last-Modified`，约 10 分钟一版；
    用 `If-None-Match` / `If-Modified-Since` 条件请求可拿到 304（已实测）。
  - `https://json.tarkov.dev/pvp/items` 为 404；`api.tarkov.dev/graphql` 当前 422。
  - 每条物品带 `updated`（ISO 时间）、`lastLowPrice`、`avg24hPrice`、`basePrice`、
    `sellToTrader[].priceRUB`（商人收购价，已由上游换算成卢布）。

缓存（只存价格相关字段，不落整包）：
  - 默认目录 `%LOCALAPPDATA%\\EFTMap\\cache\\`，文件 `live-prices-regular.json` / `live-prices-pve.json`
  - 可用环境变量 `EFTMAP_CACHE_DIR` 或 `--cache-dir` 覆盖（测试用）
  - 先用临时文件写、再 `os.replace` 原子替换；失败只写 `.last-attempt.json`，绝不动旧缓存
  - 缓存 TTL 默认 600 秒（与上游约 10 分钟一版对齐），TTL 内 `--fetch` 直接复用缓存；
    `--force` 才发起条件请求

代理（任务书要求，实测可用）：
  - 默认 `http://127.0.0.1:7896`；先做 TCP 可达性检查，再做真实请求验证 HTTP 状态与响应体
  - `--no-proxy` 直连；`--proxy` 可换端口
  - **不关闭 TLS 校验**（显式使用 `ssl.create_default_context()`）
  - 本地地址（127.0.0.1 / localhost）始终直连：本工具只访问 json.tarkov.dev，不请求本地地址

用法：
  python tools/live_prices.py --fetch                 # 抓 PvP + PvE 两套（TTL 内自动跳过）
  python tools/live_prices.py --fetch --mode pve      # 只抓 PvE
  python tools/live_prices.py --fetch --force         # 忽略 TTL，走条件请求
  python tools/live_prices.py --status                # 只看缓存状态（不联网）
  python tools/live_prices.py --status --json         # 机器可读状态

退出码：
  0 成功（含 304 复用、TTL 内跳过）
  1 网络失败（代理不可达 / 连接失败 / HTTP 非 200/304）
  2 上游数据校验失败（物品数异常 / 无价格字段）
  3 缓存写入失败
  4 另一个抓取进程持锁（本轮跳过）
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import http.client
import json
import os
import socket
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR_ENV = "EFTMAP_CACHE_DIR"
DEFAULT_PROXY = "http://127.0.0.1:7896"
DEFAULT_TTL = 600                 # 秒；与上游约 10 分钟一版对齐
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36")

# 模式键沿用上游路径：regular 就是 PvP（不是 PvE）；pve 才是 PvE；
# pvps = PvPS（赛季服），上游路径实际叫 pvp-season（2026-11-09 实测有独立价格）。
MODES = {
    "regular": {
        "mode": "regular",
        "priceMode": "pvp",
        "label": "PvP",
        "source": "https://json.tarkov.dev/regular/items",
    },
    "pve": {
        "mode": "pve",
        "priceMode": "pve",
        "label": "PvE",
        "source": "https://json.tarkov.dev/pve/items",
    },
    "pvps": {
        "mode": "pvps",
        "priceMode": "pvps",
        "label": "PvPS（赛季服）",
        "source": "https://json.tarkov.dev/pvp-season/items",
    },
}
ALIASES = {
    "regular": "regular", "pvp": "regular",
    "pve": "pve",
    "pvps": "pvps", "pvp-season": "pvps", "pvpseason": "pvps", "season": "pvps",
}
MIN_ITEMS = 1000          # 上游实测 5498；低于此视为响应不完整
MIN_PRICED = 500          # 至少这么多条要有 lastLowPrice / avg24hPrice
MAX_PRICE = 100_000_000
LOCK_STALE_SEC = 900
# R275：上游约 17 MB，跨国链路经常在 resp.read() 阶段把响应截断。
FETCH_ATTEMPTS = 3
FETCH_RETRY_SLEEP = 2

FIELD_SEMANTICS = {
    "l": "lastLowPrice：跳蚤市场最近一次最低挂单（上游字段原值）",
    "a": "avg24hPrice：跳蚤市场 24 小时均价（历史均价，不是实时挂单）",
    "u": "updated：上游每条价格的更新时间（ISO 8601，UTC）",
    "b": "basePrice：物品基础价（与跳蚤价无关）",
    "tb": "bestTraderBuy：商人收购价的最大值（上游 sellToTrader[].priceRUB，已换算卢布）",
    "tn": "bestTraderBuy 对应的商人 id（上游 sellToTrader[].trader）",
}


# ---------------------------------------------------------------- 路径与模式

def cache_dir(directory: str | None = None) -> str:
    """缓存目录：显式参数 > 环境变量 EFTMAP_CACHE_DIR > %LOCALAPPDATA%\\EFTMap\\cache。"""
    if directory:
        return os.path.abspath(directory)
    override = os.environ.get(CACHE_DIR_ENV)
    if override:
        return os.path.abspath(override)
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        base = os.path.join(os.path.expanduser("~"), ".eftmap")
    return os.path.join(base, "EFTMap", "cache")


def cache_path(mode: str, directory: str | None = None) -> str:
    return os.path.join(cache_dir(directory), "live-prices-%s.json" % normalize_mode(mode))


def attempt_path(mode: str, directory: str | None = None) -> str:
    return os.path.join(cache_dir(directory), "live-prices-%s.last-attempt.json" % normalize_mode(mode))


def normalize_mode(raw) -> str:
    """`regular`/`pvp`/`pve`/`pvps` → 上游路径键；非法值抛 ValueError。"""
    key = str(raw or "").strip().lower()
    mode = ALIASES.get(key)
    if not mode:
        raise ValueError("未知模式：%s（可用 regular(PvP) / pve / pvps）" % raw)
    return mode


def mode_info(mode) -> dict:
    return dict(MODES[normalize_mode(mode)])


# ---------------------------------------------------------------- 时间与文件

def local_now() -> datetime.datetime:
    return datetime.datetime.now().astimezone()


def parse_time(text) -> datetime.datetime | None:
    """解析上游/缓存里的 ISO 时间；无时区按 UTC；解析失败返回 None。"""
    if not isinstance(text, str) or not text:
        return None
    raw = text.strip()
    if raw.endswith("Z") or raw.endswith("z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt


def _iso(dt: datetime.datetime) -> str:
    return dt.isoformat(timespec="seconds")


def read_json(path: str):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def write_atomic(path: str, payload: dict) -> None:
    """临时文件 + replace；目录不存在则创建。

    Windows 上服务端可能正在读旧缓存（读句柄未带 delete share），replace 会短暂
    PermissionError，故做几次短重试，避免一次读竞争就把抓取判成失败。
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(payload, fh, ensure_ascii=False, separators=(",", ":"))
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


def record_attempt(mode: str, ok: bool, detail: dict, directory: str | None = None) -> None:
    """记录「上次尝试结果」（成功/失败都写），供 `/api/live-prices/status` 读取。"""
    body = {
        "schema": 1,
        "mode": normalize_mode(mode),
        "at": local_now().isoformat(timespec="seconds"),
        "ok": bool(ok),
    }
    body.update(detail)
    try:
        write_atomic(attempt_path(mode, directory), body)
    except OSError:
        pass


# ---------------------------------------------------------------- 读取缓存

def load_cache(mode: str, directory: str | None = None) -> dict | None:
    data = read_json(cache_path(mode, directory))
    if not isinstance(data, dict) or not isinstance(data.get("items"), dict):
        return None
    return data


def purge_cache(directory: str | None = None) -> int:
    """删除在线行情本地缓存；会员失效后只保留随包内置快照。"""
    removed = 0
    for mode in MODES:
        for path in (cache_path(mode, directory), attempt_path(mode, directory)):
            try:
                os.remove(path)
                removed += 1
            except OSError:
                pass
    return removed


def cache_status(mode: str, ttl_sec: int = DEFAULT_TTL, directory: str | None = None,
                 now: datetime.datetime | None = None) -> dict:
    """缓存状态（只读本地，不联网）。`stale` 依据 checkedAt 与 TTL。"""
    mode = normalize_mode(mode)
    info = MODES[mode]
    path = cache_path(mode, directory)
    out = {
        "mode": mode,
        "priceMode": info["priceMode"],
        "label": info["label"],
        "source": info["source"],
        "cachePath": path,
        "cacheDir": cache_dir(directory),
        "exists": False,
        "readable": False,
        "fetchedAt": None,
        "checkedAt": None,
        "fileMtime": None,
        "fileMtimeIso": None,
        "ageSec": None,
        "ttlSec": int(ttl_sec),
        "inTtl": False,
        "stale": True,
        "count": 0,
        "updatedOldest": None,
        "updatedNewest": None,
        "dataAgeSec": None,
        "error": None,
    }
    now = now or local_now()
    try:
        out["fileMtime"] = os.path.getmtime(path)
        out["fileMtimeIso"] = _iso(datetime.datetime.fromtimestamp(out["fileMtime"]).astimezone())
    except OSError:
        out["error"] = "no-cache"
        out["lastAttempt"] = read_json(attempt_path(mode, directory))
        return out
    out["exists"] = True
    cache = load_cache(mode, directory)
    if cache is None:
        out["error"] = "unreadable"
        out["lastAttempt"] = read_json(attempt_path(mode, directory))
        return out
    out["readable"] = True
    out["fetchedAt"] = cache.get("fetchedAt")
    out["checkedAt"] = cache.get("checkedAt") or cache.get("fetchedAt")
    out["count"] = len(cache["items"])
    anchor = parse_time(out["checkedAt"]) or datetime.datetime.fromtimestamp(
        out["fileMtime"], tz=datetime.timezone.utc)
    age = (now - anchor).total_seconds()
    out["ageSec"] = int(age) if age >= 0 else 0
    out["inTtl"] = out["ageSec"] <= out["ttlSec"]
    out["stale"] = not out["inTtl"]
    oldest = None
    newest = None
    for row in cache["items"].values():
        if not isinstance(row, dict):
            continue
        dt = parse_time(row.get("u"))
        if dt is None:
            continue
        if oldest is None or dt < oldest:
            oldest = dt
        if newest is None or dt > newest:
            newest = dt
    if oldest is not None:
        out["updatedOldest"] = _iso(oldest.astimezone())
        out["dataAgeSec"] = max(0, int((now - newest).total_seconds()))
    if newest is not None:
        out["updatedNewest"] = _iso(newest.astimezone())
    out["lastAttempt"] = read_json(attempt_path(mode, directory))
    return out


# ---------------------------------------------------------------- 上游抓取

def proxy_reachable(proxy: str, timeout: float = 2.0) -> tuple[bool, str]:
    """代理 TCP 可达性检查（等价 Test-NetConnection）。返回 (ok, 说明)。"""
    try:
        parsed = urllib.parse.urlparse(proxy)
    except Exception:  # noqa: BLE001
        return False, "代理地址无法解析：%s" % proxy
    host, port = parsed.hostname, parsed.port or 8080
    if not host:
        return False, "代理地址缺少主机名：%s" % proxy
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, "代理 %s:%d 可连接" % (host, port)
    except OSError as exc:
        return False, "代理 %s:%d 不可达：%s" % (host, port, exc)


def build_opener(proxy: str | None):
    """HTTPS 一直用默认证书校验；这里的 context 只是显式声明，不关闭校验。"""
    context = ssl.create_default_context()
    handlers = [urllib.request.HTTPSHandler(context=context)]
    if proxy:
        handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    else:
        handlers.append(urllib.request.ProxyHandler({}))
    return urllib.request.build_opener(*handlers)


def _headers(cache: dict | None) -> dict:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if isinstance(cache, dict):
        http = cache.get("http") or {}
        if isinstance(http.get("etag"), str) and http["etag"]:
            headers["If-None-Match"] = http["etag"]
        if isinstance(http.get("lastModified"), str) and http["lastModified"]:
            headers["If-Modified-Since"] = http["lastModified"]
    return headers


class FetchResult:
    """一次下载的结果：304 时 body/etag 为 None，沿用旧缓存。"""

    def __init__(self, status: int, headers: dict, body: bytes | None, url: str):
        self.status = status
        self.headers = headers
        self.body = body
        self.url = url

    @property
    def not_modified(self) -> bool:
        return self.status == 304


def fetch_url(url: str, proxy: str | None = None, timeout: int = 120,
              cache: dict | None = None, opener=None) -> FetchResult:
    """发一次（可选条件）GET。HTTP 非 200/304 抛 RuntimeError，连接失败抛 OSError。

    R275：``http.client.IncompleteRead`` 既不是 RuntimeError 也不是 OSError，
    原来会一路冒到 main() 把采集进程打崩（fatal.log 从 11-09 起反复出现）。
    这里做有限重试，最终仍失败时统一转成 OSError，交给 fetch_mode 记成结构化
    失败：其他模式继续跑，轮末的云端上传也照常执行。
    """
    op = opener or build_opener(proxy)
    req = urllib.request.Request(url, headers=_headers(cache))
    for attempt in range(1, FETCH_ATTEMPTS + 1):
        try:
            with op.open(req, timeout=timeout) as resp:
                body = resp.read()
            return FetchResult(getattr(resp, "status", 200), dict(resp.headers), body, url)
        except urllib.error.HTTPError as exc:
            if exc.code == 304:
                return FetchResult(304, dict(exc.headers), None, url)
            raise RuntimeError("上游 HTTP %s %s（%s）" % (exc.code, exc.reason, url)) from exc
        except (http.client.IncompleteRead, http.client.RemoteDisconnected,
                socket.timeout, ConnectionResetError) as exc:
            if attempt >= FETCH_ATTEMPTS:
                raise OSError("上游下载中断（重试 %d 次仍失败）：%s: %s"
                              % (FETCH_ATTEMPTS, type(exc).__name__, exc)) from exc
            time.sleep(FETCH_RETRY_SLEEP * attempt)
    raise OSError("上游下载失败：重试次数耗尽")


def extract_items(doc) -> dict:
    """取 `data.items` 字典（实测结构 {"data": {"items": {...}, ...}, "translations": ...}）。"""
    if not isinstance(doc, dict):
        raise ValueError("上游响应不是对象（类型 %s）" % type(doc).__name__)
    data = doc.get("data")
    if isinstance(data, dict) and isinstance(data.get("items"), dict):
        return data["items"]
    raise ValueError("上游响应缺少 data.items 字典")


def _price(value) -> int | float | None:
    """价格收敛：正数且不越界才保留；布尔/字符串/None/0/负值一律丢弃（不按 0 计入）。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not (0 < value < MAX_PRICE):
        return None
    return int(value) if float(value).is_integer() else float(value)


def _best_trader_buy(item: dict) -> tuple[int | None, str | None]:
    """商人收购价：`sellToTrader` 里 priceRUB 最大的一条（上游已按货币换算成卢布）。"""
    offers = item.get("sellToTrader")
    if not isinstance(offers, list):
        return None, None
    best_price = None
    best_trader = None
    for offer in offers:
        if not isinstance(offer, dict):
            continue
        price = _price(offer.get("priceRUB"))
        trader = offer.get("trader")
        if price is None or not isinstance(trader, str) or not trader:
            continue
        if best_price is None or price > best_price:
            best_price = price
            best_trader = trader
    return best_price, best_trader


def build_cache(doc, mode: str, source: str, now: datetime.datetime | None = None,
                ttl_sec: int = DEFAULT_TTL, http: dict | None = None) -> dict:
    """上游整包 → 规范化价格缓存；任何异常都抛异常（调用方不写盘）。"""
    mode = normalize_mode(mode)
    items = extract_items(doc)
    total = len(items)
    if total < MIN_ITEMS:
        keys = list(doc.keys())[:6] if isinstance(doc, dict) else []
        sample = json.dumps(doc, ensure_ascii=False)[:200] if isinstance(doc, dict) else str(doc)[:200]
        raise ValueError("上游物品数异常（%d < %d）；顶层键=%s；载荷样本=%s"
                         % (total, MIN_ITEMS, keys, sample))
    now = now or local_now()
    ts = _iso(now)
    out = {}
    priced = 0
    with_updated = 0
    for item_id, rec in items.items():
        if not isinstance(rec, dict):
            continue
        row = {}
        low = _price(rec.get("lastLowPrice"))
        avg = _price(rec.get("avg24hPrice"))
        if low is not None:
            row["l"] = low
        if avg is not None:
            row["a"] = avg
        base = _price(rec.get("basePrice"))
        if base is not None:
            row["b"] = base
        updated = rec.get("updated")
        if isinstance(updated, str) and parse_time(updated) is not None:
            row["u"] = updated
            with_updated += 1
        buy, trader = _best_trader_buy(rec)
        if buy is not None:
            row["tb"] = buy
            if trader:
                row["tn"] = trader
        if "l" not in row and "a" not in row:
            continue
        out[str(item_id)] = row
        if "l" in row:
            priced += 1
    if priced < MIN_PRICED:
        raise ValueError("有最近低价的物品过少（%d < %d），疑似字段缺失或上游改版"
                         % (priced, MIN_PRICED))
    info = MODES[mode]
    return {
        "schema": 2,
        "mode": mode,
        "priceMode": info["priceMode"],
        "modeLabel": info["label"],
        "gameModeNote": "上游路径键 regular = PvP（常规）；pve = PvE。两者不混用。",
        "source": source,
        "sourceType": "tarkov.dev public JSON (items)",
        "fetchedAt": ts,
        "fetchedAtUnix": int(now.timestamp()),
        "checkedAt": ts,
        "checkedAtUnix": int(now.timestamp()),
        "ttlSec": int(ttl_sec),
        "http": http or {"status": 200, "notModified": False},
        "fieldSemantics": dict(FIELD_SEMANTICS),
        "counts": {
            "itemsUpstream": total,
            "itemsWithPrice": len(out),
            "withLastLowPrice": priced,
            "withUpdated": with_updated,
        },
        "items": out,
    }


def reuse_cache(cache: dict, http: dict, ttl_sec: int, now: datetime.datetime | None = None) -> dict:
    """304 或 TTL 跳过：保留价格，只刷新 checkedAt / http / ttl。"""
    now = now or local_now()
    updated = dict(cache)
    updated["checkedAt"] = _iso(now)
    updated["checkedAtUnix"] = int(now.timestamp())
    updated["ttlSec"] = int(ttl_sec)
    updated["http"] = dict(http or {})
    updated["http"].setdefault("notModified", True)
    return updated


# ---------------------------------------------------------------- 锁

def acquire_lock(path: str, stale_seconds: int = LOCK_STALE_SEC) -> bool:
    now = local_now().timestamp()
    try:
        try:
            st = os.stat(path)
        except FileNotFoundError:
            st = None
        if st is not None:
            if now - st.st_mtime < stale_seconds:
                return False
            # R275：陈旧锁必须先删掉，否则 O_EXCL 会因文件已存在永远失败，
            # 采集器会一直报「另一个进程持锁」彻底停摆。只删 mtime 没变过的
            # 那把锁，避免误删期间刚被别的进程重建的新锁；真正的并发由 O_EXCL 裁决。
            try:
                if os.stat(path).st_mtime_ns == st.st_mtime_ns:
                    os.unlink(path)
            except (FileNotFoundError, OSError):
                pass
    except OSError:
        return True          # 锁文件不可用时沿用旧语义：不阻塞抓取
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(now).encode())
        os.close(fd)
        return True
    except FileExistsError:
        return False
    except OSError:
        return True


def release_lock(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


# ---------------------------------------------------------------- 抓一个模式

def fetch_mode(mode: str, proxy: str | None = DEFAULT_PROXY, ttl_sec: int = DEFAULT_TTL,
               force: bool = False, timeout: int = 120, directory: str | None = None,
               source: str | None = None, opener=None) -> dict:
    """抓取单个模式。返回 {"mode", "ok", "exitCode", "skipped", "notModified", "status", "message"}。

    不抛异常；失败只写 attempt 记录，旧缓存原样保留。
    """
    mode = normalize_mode(mode)
    info = MODES[mode]
    url = source or info["source"]
    path = cache_path(mode, directory)
    cache = load_cache(mode, directory)
    if cache and not force and cache_status(mode, ttl_sec, directory)["inTtl"]:
        return {"mode": mode, "ok": True, "exitCode": 0, "skipped": True, "notModified": True,
                "status": None, "message": "缓存仍在 TTL（%d 秒）内，跳过下载" % ttl_sec}

    lock = cache_dir(directory) + os.sep + ".live-prices-%s.lock" % mode
    if not acquire_lock(lock):
        return {"mode": mode, "ok": True, "exitCode": 4, "skipped": True, "notModified": False,
                "status": None, "message": "另一个抓取进程持锁，本轮跳过"}
    try:
        if proxy:
            ok, why = proxy_reachable(proxy)
            if not ok:
                record_attempt(mode, False, {"stage": "proxy", "error": why}, directory)
                return {"mode": mode, "ok": False, "exitCode": 1, "skipped": False,
                        "notModified": False, "status": None, "message": why}
        try:
            result = fetch_url(url, proxy=proxy, timeout=timeout,
                               cache=cache, opener=opener)
        except RuntimeError as exc:
            record_attempt(mode, False, {"stage": "http", "error": str(exc)}, directory)
            return {"mode": mode, "ok": False, "exitCode": 1, "skipped": False,
                    "notModified": False, "status": None, "message": str(exc)}
        except OSError as exc:
            msg = "下载失败：%s: %s" % (type(exc).__name__, exc)
            record_attempt(mode, False, {"stage": "network", "error": msg}, directory)
            return {"mode": mode, "ok": False, "exitCode": 1, "skipped": False,
                    "notModified": False, "status": None, "message": msg}

        http = {
            "status": result.status,
            "notModified": result.not_modified,
            "etag": result.headers.get("ETag"),
            "lastModified": result.headers.get("Last-Modified"),
            "bytes": 0 if result.body is None else len(result.body),
            "sha256": None if result.body is None else hashlib.sha256(result.body).hexdigest(),
        }
        if result.not_modified:
            if cache is None:
                msg = "上游返回 304 但本地没有可用缓存：请用 --force 重新下载"
                record_attempt(mode, False, {"stage": "304-without-cache", "error": msg}, directory)
                return {"mode": mode, "ok": False, "exitCode": 2, "skipped": False,
                        "notModified": True, "status": 304, "message": msg}
            payload = reuse_cache(cache, http, ttl_sec)
            try:
                write_atomic(path, payload)
            except OSError as exc:
                msg = "缓存写入失败：%s" % exc
                record_attempt(mode, False, {"stage": "write", "error": msg}, directory)
                return {"mode": mode, "ok": False, "exitCode": 3, "skipped": False,
                        "notModified": True, "status": 304, "message": msg}
            record_attempt(mode, True, {"stage": "fetch", "status": 304, "notModified": True}, directory)
            return {"mode": mode, "ok": True, "exitCode": 0, "skipped": False,
                    "notModified": True, "status": 304, "message": "304 未变更，沿用缓存并刷新 checkedAt"}

        try:
            doc = json.loads(result.body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            msg = "JSON 解析失败：%s" % exc
            record_attempt(mode, False, {"stage": "parse", "error": msg}, directory)
            return {"mode": mode, "ok": False, "exitCode": 2, "skipped": False,
                    "notModified": False, "status": result.status, "message": msg}
        try:
            payload = build_cache(doc, mode, url, ttl_sec=ttl_sec, http=http)
        except ValueError as exc:
            record_attempt(mode, False, {"stage": "validate", "error": str(exc)}, directory)
            return {"mode": mode, "ok": False, "exitCode": 2, "skipped": False,
                    "notModified": False, "status": result.status, "message": str(exc)}
        try:
            write_atomic(path, payload)
        except OSError as exc:
            msg = "缓存写入失败：%s" % exc
            record_attempt(mode, False, {"stage": "write", "error": msg}, directory)
            return {"mode": mode, "ok": False, "exitCode": 3, "skipped": False,
                    "notModified": False, "status": result.status, "message": msg}
        record_attempt(mode, True, {"stage": "fetch", "status": result.status,
                                    "notModified": False, "bytes": http["bytes"],
                                    "sha256": http["sha256"], "count": len(payload["items"])},
                       directory)
        return {"mode": mode, "ok": True, "exitCode": 0, "skipped": False,
                "notModified": False, "status": result.status,
                "message": "已写入 %d 条（上游 %d 件）" % (len(payload["items"]),
                                                    payload["counts"]["itemsUpstream"])}
    finally:
        release_lock(lock)


# ---------------------------------------------------------------- 命令行

def _status_payload(modes: list[str], ttl_sec: int, directory: str | None) -> dict:
    return {
        "ok": True,
        "cacheDir": cache_dir(directory),
        "ttlSec": int(ttl_sec),
        "modes": {m: cache_status(m, ttl_sec, directory) for m in modes},
    }


def main(argv=None) -> int:
    # 本地地址永远直连：即使外部环境设置了全局代理，也不让 localhost 走代理
    for key in ("NO_PROXY", "no_proxy"):
        os.environ.setdefault(key, "localhost,127.0.0.1,::1")
    ap = argparse.ArgumentParser(
        description="R42 可选在线行情（默认离线；只在 --fetch 时访问 tarkov.dev）")
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--fetch", action="store_true", help="联网抓取并写缓存")
    group.add_argument("--status", action="store_true", help="只读缓存状态（不联网）")
    ap.add_argument("--mode", default="all", help="regular(PvP) / pve / all（默认 all）")
    ap.add_argument("--force", action="store_true", help="忽略 TTL，发起条件请求")
    ap.add_argument("--ttl", type=int, default=DEFAULT_TTL, help="缓存 TTL 秒（默认 %d）" % DEFAULT_TTL)
    ap.add_argument("--proxy", default=DEFAULT_PROXY, help="HTTP(S) 代理（默认 %s）" % DEFAULT_PROXY)
    ap.add_argument("--no-proxy", action="store_true", help="直连（不走代理）")
    ap.add_argument("--timeout", type=int, default=120, help="单次请求超时秒（默认 120）")
    ap.add_argument("--cache-dir", default=None,
                    help="缓存目录（默认 %%LOCALAPPDATA%%\\EFTMap\\cache）")
    ap.add_argument("--source", default=None,
                    help="只抓单个模式时覆盖上游地址（--mode all 下不可用）")
    ap.add_argument("--json", action="store_true", help="--status 输出 JSON")
    args = ap.parse_args(argv)

    try:
        modes = list(MODES) if str(args.mode).lower() == "all" else [normalize_mode(args.mode)]
    except ValueError as exc:
        print("[错误] %s" % exc, file=sys.stderr)
        return 2
    if args.source and len(modes) != 1:
        print("[错误] --source 只能配合单个 --mode 使用", file=sys.stderr)
        return 2
    ttl = max(30, int(args.ttl))
    proxy = None if args.no_proxy else (args.proxy or DEFAULT_PROXY)

    if args.status:
        payload = _status_payload(modes, ttl, args.cache_dir)
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print("缓存目录：%s（TTL %d 秒）" % (payload["cacheDir"], ttl))
            for mode, st in payload["modes"].items():
                state = "无缓存" if not st["exists"] else ("OK" if st["inTtl"] else "已过 TTL")
                print("[%s] %s → %s：%s；%d 条；文件 %s；数据更新时间 %s ~ %s"
                      % (mode, st["priceMode"], state, "可读" if st["readable"] else st["error"],
                         st["count"], st["fileMtimeIso"], st["updatedOldest"], st["updatedNewest"]))
                if not st["lastAttempt"]:
                    continue
                last = st["lastAttempt"]
                print("    上次尝试：%s ok=%s %s" % (last.get("at"), last.get("ok"),
                                                  last.get("error") or last.get("message") or ""))
        return 0

    exit_code = 0
    for mode in modes:
        res = fetch_mode(mode, proxy=proxy, ttl_sec=ttl, force=args.force,
                         timeout=args.timeout, directory=args.cache_dir, source=args.source)
        tag = {"regular": "PvP", "pve": "PvE", "pvps": "PvPS"}[mode]
        stream = sys.stdout if res["ok"] else sys.stderr
        print("[%s] %s %s" % (tag, "OK" if res["ok"] else "FAIL", res["message"]), file=stream)
        if not res["ok"]:
            exit_code = res["exitCode"] if exit_code == 0 else exit_code
        elif res["exitCode"] == 4 and exit_code == 0:
            exit_code = 0
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
