# -*- coding: utf-8 -*-
"""R79 市场行情数据源（只读、只在服务端调用、仅标准库）。

2026-11-17 起**只走云端**（`cloud_market`），免费与会员共用同一入口：

1. 未登录：不请求云端，返回 `loginRequired=true`；
2. 免费账号：云端快照延迟 12 小时、每日 24 次、CD 59:59；
3. 会员：云端最新快照、CD 30 秒、每日不限次；
4. 云端不可达 / 配额用尽：本机最后一次成功结果（`cloud-market/`），
   `cached=true`，绝不冒充实时；不再读取随安装包发布的离线快照。

返回契约（`snapshot_for`）：
  {"ok": true, "mode": "...", "modeLabel": "...", "available": true,
   "source": "cloud", "tier": "free"|"member", "live": bool, "nonLive": bool,
   "cached": bool, "cacheReason": str | null, "dataDelayed": bool,
   "delaySeconds": int, "snapshotAt": "...", "dataAt": "...",
   "items": {id: {l,a,lo,hi,b,u,lv,o,c,d,v}},
   "quota": {daily_limit, used_today, remaining_today, cd_seconds,
             cooldown, next_allowed_at, reset_at, delay_seconds},
   "error": null}

旧的 `_try_cloud` / `_fill_avg24h` / `_backfill_from_bundle` 只保留给历史单测，
运行期不再调用。
"""
from __future__ import annotations

import datetime
import json
import os
import threading
from typing import Any

import collector_prices
import cloud_market

STALE_AFTER_SEC = 2 * 3600        # 与采集器一致：超过 2 小时视为过期
AVG7_MIN_DAYS = 7                 # 与 r20_fetch_prices.HISTORY_AVG7_DAYS 一致
MAX_PRICE = 100_000_000
MODE_ALIASES = collector_prices.MODE_ALIASES

# 内置快照文件名：PvP 沿用历史文件名，PvE / PvPS 各一份。
BUNDLED_FILES = {
    "regular": "flea-prices.json",
    "pve": "flea-prices-pve.json",
    "pvps": "flea-prices-pvps.json",
}
MODE_LABELS = {
    "regular": "PvP",
    "pve": "PvE",
    "pvps": "PvPS（赛季服）",
}
_FULL_TO_SHORT = (
    ("lastLowPrice", "l"),
    ("avg24hPrice", "a"),
    ("low24hPrice", "lo"),
    ("high24hPrice", "hi"),
    ("basePrice", "b"),
    ("updated", "u"),
    ("minLevelForFlea", "lv"),
)
_AVG7_KEYS = ("avg7daysPrice", "avg7dPrice", "avg7d")

_bundle_cache: dict[tuple[str, int], dict] = {}
_cache_lock = threading.Lock()


def normalize_mode(raw) -> str:
    return collector_prices.normalize_mode(raw)


def bundled_path(root: str, mode: str) -> str:
    """内置快照路径；主文件名不存在时再试 `flea-prices-<mode>.json`。"""
    name = BUNDLED_FILES.get(mode)
    if not name:
        raise ValueError("未知模式：%r" % (mode,))
    primary = os.path.join(root, "data", name)
    if os.path.exists(primary) or mode == "regular":
        return primary
    alt = os.path.join(root, "data", "flea-prices-%s.json" % mode)
    return alt if os.path.exists(alt) else primary


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


def _valid_price(value) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not (0 < value < MAX_PRICE):
        return None
    return int(value) if float(value).is_integer() else float(value)


def _compact_row(row: dict) -> dict:
    """把内置快照的完整字段名（lastLowPrice…）归一成市场层用的短键。"""
    if not isinstance(row, dict):
        return {}
    out: dict[str, Any] = {}
    for full, short in _FULL_TO_SHORT:
        value = row.get(full, row.get(short))
        if short in ("u", "lv"):
            if short == "u":
                if value:
                    out["u"] = str(value)
            else:
                if isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= 60:
                    out["lv"] = int(value)
            continue
        price = _valid_price(value)
        if price is not None:
            out[short] = price
    return out


def _age_fields(snapshot_at, now: datetime.datetime) -> dict:
    dt = _parse_time(snapshot_at)
    if not dt:
        return {"ageSec": None, "stale": False}
    age = int((now - dt).total_seconds())
    if age < 0:
        age = 0
    return {"ageSec": age, "stale": age > STALE_AFTER_SEC}


def _read_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def load_bundled(root: str, mode: str, now: datetime.datetime | None = None) -> dict:
    """读取随包内置快照并归一化；任何异常都收敛成 error，不向外抛。"""
    now = now or datetime.datetime.now().astimezone()
    path = bundled_path(root, mode)
    rel = os.path.relpath(path, root).replace(os.sep, "/")
    base = {
        "ok": False,
        "mode": mode,
        "modeLabel": MODE_LABELS.get(mode, mode),
        "available": False,
        "source": "bundled",
        "live": False,
        "nonLive": True,
        "offline": False,
        "offlineReason": None,
        "snapshotAt": None,
        "dataAt": None,
        "ageSec": None,
        "staleAfterSec": STALE_AFTER_SEC,
        "stale": False,
        "counts": {},
        "items": {},
        "avg7d": {"days": 0, "dates": [], "values": {}},
        "bundledPath": rel,
        "error": None,
    }
    try:
        stat = os.stat(path)
        cache_key = (path, int(stat.st_mtime))
        with _cache_lock:
            cached = _bundle_cache.get(cache_key)
        if cached:
            hit = dict(cached)
            # R220：缓存里只放归一化后的快照，ageSec / stale 必须按「当前时间 − snapshotAt」现算。
            # 曾把二者一并缓存，进程活得越久报出的年龄越落后（实测落后 27.9 分钟且 4 秒内不推进），
            # 与界面同一行的「数据截止 …（20 小时前）」自相矛盾。
            hit.update(_age_fields(hit.get("snapshotAt"), now))
            return hit
        doc = _read_json(path)
    except FileNotFoundError:
        base["error"] = "no-bundle"
        return base
    except (OSError, ValueError) as exc:
        base["error"] = "unreadable-bundle"
        base["errorDetail"] = str(exc)[:200]
        return base

    if not isinstance(doc, dict) or not isinstance(doc.get("items"), dict):
        base["error"] = "unreadable-bundle"
        return base

    meta = doc.get("meta") if isinstance(doc.get("meta"), dict) else {}
    snapshot_at = (
        meta.get("generatedAt")
        or doc.get("generatedAt")
        or doc.get("lastSuccessAt")
    )
    data_at = meta.get("sourceUpdatedMax")
    if not snapshot_at:
        try:
            snapshot_at = datetime.datetime.fromtimestamp(
                os.path.getmtime(path), tz=datetime.timezone.utc
            ).isoformat(timespec="seconds")
        except OSError:
            snapshot_at = None

    items: dict[str, dict] = {}
    avg_values: dict[str, float] = {}
    for item_id, row in doc["items"].items():
        compact = _compact_row(row)
        if compact:
            items[str(item_id)] = compact
        for key in _AVG7_KEYS:
            value = _valid_price(row.get(key)) if isinstance(row, dict) else None
            if value is not None:
                avg_values[str(item_id)] = value
                break

    days = meta.get("historyDays")
    if not isinstance(days, int) or days < 0:
        days = AVG7_MIN_DAYS if avg_values else 0
    age = _age_fields(snapshot_at, now)
    payload = {
        **base,
        "ok": True,
        "available": bool(items),
        "snapshotAt": snapshot_at,
        "dataAt": data_at,
        "counts": doc.get("counts") if isinstance(doc.get("counts"), dict) else {},
        "items": items,
        "avg7d": {
            "days": days,
            "dates": [],
            "values": avg_values if days >= AVG7_MIN_DAYS else {},
        },
        "error": None if items else "empty-bundle",
        **age,
    }
    with _cache_lock:
        if len(_bundle_cache) > 12:
            _bundle_cache.clear()
        _bundle_cache[cache_key] = dict(payload)
    return payload


def _cloud_doc(raw) -> dict:
    if not isinstance(raw, dict):
        return {}
    for key in ("data", "payload", "result"):
        inner = raw.get(key)
        if isinstance(inner, dict) and isinstance(inner.get("items"), dict):
            merged = dict(raw)
            merged.update(inner)
            return merged
    return raw


def _error_text(exc) -> str:
    detail = getattr(exc, "to_dict", None)
    if callable(detail):
        try:
            info = detail()
            code = info.get("code") or ""
            # R220：CloudError.to_dict() 的键是 error / code，不是 message / detail；
            # 旧写法读不到服务端的真实说明，只能退回 str(exc)
            msg = info.get("message") or info.get("detail") or info.get("error") or ""
            if code or msg:
                return ("%s（%s）" % (msg or "云端请求失败", code or "error")).strip()
        except Exception:
            pass
    code = getattr(exc, "code", None)
    msg = str(exc) or exc.__class__.__name__
    if code:
        return "%s（%s）" % (msg, code)
    return msg[:200]


def _cloud_items(doc: dict) -> dict[str, dict]:
    out: dict[str, dict] = {}
    raw = doc.get("items")
    if isinstance(raw, dict):
        for item_id, row in raw.items():
            compact = _compact_row(row) if isinstance(row, dict) else {}
            if compact:
                out[str(item_id)] = compact
    # 服务端 `/v1/prices` 契约是「物品 → 单个价格」，按当前最低价（l）展示。
    prices = doc.get("prices")
    if isinstance(prices, dict):
        for item_id, value in prices.items():
            price = _valid_price(value)
            if price is not None:
                out[str(item_id)] = {"l": price}
    return out


def _cloud_avg_values(doc: dict) -> dict[str, float]:
    """兼容 `/v1/prices/history` 可能的几种返回形状。"""
    if not isinstance(doc, dict):
        return {}
    container = None
    for key in ("items", "averages", "values"):
        if isinstance(doc.get(key), dict):
            container = doc.get(key)
            break
    if not isinstance(container, dict):
        return {}
    out: dict[str, float] = {}
    for item_id, value in container.items():
        if isinstance(value, dict):
            value = value.get("avg", value.get("average", value.get("value", value.get("l"))))
        price = _valid_price(value)
        if price is not None:
            out[str(item_id)] = price
    return out


def _fill_avg24h(client, mode: str, items: dict[str, dict]) -> int:
    """给云端行情补上 24h 均价（`a`）。

    `GET /v1/prices` 的契约是「物品 → 单个价格」（只给最近低价的 `l`），没有 24h 均价；
    配装表的「最新 / 24h 均价」切换需要它，所以这里再取一次
    `GET /v1/prices/history?mode=...&basis=24h`：

      · 只补 `a` **缺失**的行，云端已经给了值的绝不覆盖；
      · 形状不认识 / 请求失败时静默跳过（返回 0），
        **绝不拿 7d 均价或 last 冒充 24h**，界面会照实显示「—」。
    """
    if not items:
        return 0
    try:
        doc = _cloud_doc(client.prices_history(mode, "24h"))
    except Exception:          # 边界：网络 / 鉴权 / 旧服务端不支持 24h 都按「没有」处理
        return 0
    values = _cloud_avg_values(doc)
    filled = 0
    for item_id, price in values.items():
        row = items.get(str(item_id))
        if not isinstance(row, dict):
            continue
        if _valid_price(row.get("a")) is not None:
            continue
        row["a"] = price
        filled += 1
    return filled


def _backfill_from_bundle(root: str, mode: str, payload: dict, now) -> int:
    """云端只给了最近低价时，用**同模式**的内置快照补 24h 均价。

    为什么允许这么做：内置快照是同一个采集器、同一个模式的输出（只差时间），
    `avg24hPrice` 本身就是一个 24 小时窗口的均值，用同模式稍早的均值补「云端没给」
    远比显示「—」更可用，也比拿 last / 7d 冒充更诚实。
    边界：只补 `a` 缺失的条目，只读同模式文件（PvE 绝不会拿 PvP 的均价），
    补了多少写进 `avg24hFromBundled`，界面照这个数字在悬停里说明来源。
    """
    items = payload.get("items") or {}
    if not items:
        return 0
    missing = [k for k, v in items.items()
               if isinstance(v, dict) and _valid_price(v.get("a")) is None]
    if not missing:
        return 0
    bundled = load_bundled(root, mode, now)
    src = (bundled.get("items") or {}) if bundled.get("available") else {}
    filled = 0
    for item_id in missing:
        row = src.get(item_id)
        if not isinstance(row, dict):
            continue
        price = _valid_price(row.get("a"))
        if price is None:
            continue
        items[item_id]["a"] = price
        filled += 1
    if filled:
        payload["avg24hFromBundled"] = filled
    return filled


def _try_cloud(client, mode: str, now: datetime.datetime):
    """返回 (payload, error_text)。任何云端异常都收敛成 error 文本。"""
    try:
        latest = _cloud_doc(client.prices(mode))
    except Exception as exc:      # 边界：网络/鉴权/解析异常都必须能降级
        return None, _error_text(exc)
    items = _cloud_items(latest)
    if not items:
        return None, "云端没有该模式的最新行情"
    avg24_filled = _fill_avg24h(client, mode, items)

    history = {}
    try:
        history = _cloud_doc(client.prices_history(mode, "7d"))
    except Exception:
        history = {}
    values = _cloud_avg_values(history)
    if not values:
        # 最新文档自己带 7 日均价时直接使用（服务端两种写法都兼容）
        for item_id, row in (latest.get("items") or {}).items():
            if not isinstance(row, dict):
                continue
            for key in _AVG7_KEYS:
                price = _valid_price(row.get(key))
                if price is not None:
                    values[str(item_id)] = price
                    break
    days = history.get("days") if isinstance(history.get("days"), int) else 0
    points = history.get("points")
    if not days and isinstance(points, list) and points:
        # 服务端 history 返回的是逐日全局均价（points），没有逐物品均价值。
        days = len(points)
    if not days and values:
        days = AVG7_MIN_DAYS
    if days < AVG7_MIN_DAYS:
        values = {}

    snapshot_at = (
        latest.get("generatedAt")
        or latest.get("generated_at")
        or latest.get("snapshotAt")
        or latest.get("updatedAt")
    )
    age = _age_fields(snapshot_at, now)
    return {
        "ok": True,
        "mode": mode,
        "modeLabel": MODE_LABELS.get(mode, mode),
        "available": True,
        "source": "cloud",
        "live": True,
        "nonLive": False,
        "offline": False,
        "offlineReason": None,
        "snapshotAt": snapshot_at,
        "dataAt": latest.get("sourceUpdatedMax") or latest.get("dataAt"),
        "counts": latest.get("counts") if isinstance(latest.get("counts"), dict) else {},
        "items": items,
        "avg7d": {"days": days, "dates": [], "values": values},
        # R219：从 `/v1/prices/history?basis=24h` 补进 `a` 的条数（0 = 服务端还没这个口径，
        # 界面照实显示「—」，不拿别的口径顶替）
        "avg24hFilled": avg24_filled,
        "bundledPath": None,
        "error": None,
        "staleAfterSec": STALE_AFTER_SEC,
        **age,
    }, None


# R268：云端采集机每小时 **:01 / :31** 各采集上传一次，所以「按按钮能不能拿到更新的数据」
# 取决于**缓存快照是否已覆盖最近一个采集时刻**，而不是固定 20 分钟窗口。
#   · 已覆盖 → 云端不可能有更新的东西，直接回缓存（force 时标 throttled/up-to-date，
#     前端显示「已是最新，下次采集 HH:MM」）；
#   · 未覆盖 → 允许打云端，但同一个采集时刻内 2 分钟内只试一次，防连点把云端打爆。
COLLECT_MINUTES = (1, 31)
CLOUD_FETCH_MIN_INTERVAL = datetime.timedelta(minutes=2)
_cloud_fetch_at: dict[str, datetime.datetime] = {}
_cloud_last: dict[str, dict] = {}
_cloud_lock = threading.Lock()


def latest_collect_slot(now: datetime.datetime) -> datetime.datetime:
    """最近一个**已经到达**的云端采集时刻（:01 / :31）。"""
    for minute in sorted(COLLECT_MINUTES, reverse=True):
        if now.minute >= minute:
            return now.replace(minute=minute, second=0, microsecond=0)
    previous = now - datetime.timedelta(hours=1)
    return previous.replace(minute=max(COLLECT_MINUTES), second=0, microsecond=0)


def next_collect_slot(now: datetime.datetime) -> datetime.datetime:
    """下一个云端采集时刻（:01 / :31）。"""
    for minute in sorted(COLLECT_MINUTES):
        if now.minute < minute:
            return now.replace(minute=minute, second=0, microsecond=0)
    following = now + datetime.timedelta(hours=1)
    return following.replace(minute=min(COLLECT_MINUTES), second=0, microsecond=0)


def _payload_moment(payload) -> datetime.datetime | None:
    """把快照里的 snapshotAt 解析成带时区的 datetime；解不出返回 None。

    采集机给的 generatedAt 可能带 Z / +00:00，也可能是无时区的本地时间（按本地解释），
    解析失败时调用方退回「短时间重试保护」，不会因为格式怪就疯狂打云端。
    """
    raw = (payload or {}).get("snapshotAt")
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        moment = datetime.datetime.fromisoformat(text)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.astimezone()
    return moment


def reset_cloud_throttle() -> None:
    """清空云端节流状态（进程内缓存的「上次拉取时间」与「上次结果」）。

    节流状态按设计应跨请求保留，它只在两个场景需要清空：
      · 测试之间隔离（避免前面的用例污染后面用例的 member 云端拉取判断）；
      · 进程长时间运行、运维想强制下一次请求真的打云端。
    生产环境正常运行不需要调用。
    """
    with _cloud_lock:
        _cloud_fetch_at.clear()
        _cloud_last.clear()


def snapshot_for(
    root: str,
    mode: str,
    cloud_client=None,
    member: bool = False,
    now: datetime.datetime | None = None,
    force: bool = False,
    app_dir: str | None = None,
    max_generated_at: datetime.datetime | None = None,
) -> dict:
    """当前模式行情：**只走云端**（免费 / 会员同一份数据源）。

    · 免费账号由服务端延迟 12 小时、每日 24 次、CD 59:59；会员 30 秒 CD；
    · 未登录不请求云端，返回 `loginRequired=true` 的结构化结果；
    · 云端不可达 / 配额用尽时由 `cloud_market` 回退本机最后一次成功结果，
      并标 `cached=true`；没有缓存就如实返回错误，不再使用内置离线快照。
    · `max_generated_at` 用于免费账号：本机缓存里更新的快照也不能看。
    """
    now = now or datetime.datetime.now().astimezone()
    mode = normalize_mode(mode)
    try:
        payload = cloud_market.fetch(
            app_dir or root, mode, cloud_client, force=force, now=now,
            max_generated_at=max_generated_at,
        )
    except Exception as exc:  # noqa: BLE001 - BFF 需要结构化错误，不能抛 500
        status = getattr(exc, "status", None)
        code = getattr(exc, "code", "") or "unavailable"
        message = str(exc) or "云端行情不可用"
        login_required = status in (401, 403) or code in {
            "unauthorized", "membership_required", "login_required"
        }
        quota = getattr(exc, "details", {}).get("quota") if isinstance(
            getattr(exc, "details", None), dict) else None
        return {
            "ok": False,
            "mode": mode,
            "modeLabel": MODE_LABELS.get(mode, mode),
            "available": False,
            "source": "cloud",
            "live": False,
            "nonLive": True,
            "offline": True,
            "cached": False,
            "loginRequired": bool(login_required),
            "quota": quota if isinstance(quota, dict) else {},
            "snapshotAt": None,
            "dataAt": None,
            "items": {},
            "avg7d": {"days": 0, "dates": [], "values": {}},
            "bundledPath": None,
            "error": code,
            "message": message,
            "staleAfterSec": STALE_AFTER_SEC,
        }

    payload.setdefault("counts", {
        "items": len(payload.get("items") or {}),
        "withPrice": len(payload.get("items") or {}),
    })
    payload.setdefault("avg7d", {"days": 0, "dates": [], "values": {}})
    # R19.82：7 日均价按**云端价格缓存**逐物品计算（`/v1/prices/history?basis=7d`
    # 只给全市场逐日均值，没有逐物品价，直接用它会让列表整列显示「积累中」）。
    if payload.get("available") and app_dir:
        try:
            import market_overview  # 局部导入：避免 BFF 之外的调用路径强依赖
            values = market_overview.seven_day_averages(app_dir, mode)
        except Exception:  # noqa: BLE001 - 均价缺失不能影响行情主流程
            values = {}
        if values:
            payload["avg7d"] = {"days": 7, "dates": [], "values": values}
    payload.setdefault("bundledPath", None)
    payload.setdefault("staleAfterSec", STALE_AFTER_SEC)
    payload["requestedMember"] = bool(member)
    return payload


def clear_cache() -> None:
    with _cache_lock:
        _bundle_cache.clear()
