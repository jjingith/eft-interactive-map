#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R20.5 跳蚤市场价格抓取器 → 本地缓存 `data/flea-prices.json`。

数据源（2026-11-04 纠正 + 复核，详见 docs/r42-live-prices-ledger.md）：
  - 主用：`https://json.tarkov.dev/regular/items`（tarkov.dev 公开 JSON）。
    **路径键 `regular` 就是 PvP（常规模式），不是 PvE**。2026-11-04 实测：
    5498 个 id 在 `/regular` 与 `/pve` 两侧都存在；其中两侧都有 lastLowPrice 的
    3529 个 id 里同值仅 84 个（2.38%），与旧报告「regular=PvE」的标注相反。
    旧版本此处的「PvE / regular 模式」「PvP 上游不可达」标注是错的，已一并纠正。
  - PvE 另有独立端点：`https://json.tarkov.dev/pve/items`（2026-11-04 实测 HTTP 200）。
    本工具默认仍只产出 PvP（regular）一份；PvE 请用
    `python tools/live_prices.py --fetch --mode pve` 单独抓取，两套缓存不混写。
  - `https://json.tarkov.dev/pvp/items` → 404（上游把 PvP 挂在 regular 路径下）。
  - `https://api.tarkov.dev/graphql` 实测返回 GraphQL unavailable，故不作为数据源。
  - 实测：HTTP 200、约 17 MB、带 `ETag` / `Last-Modified`、约 10 分钟一版；
    每条物品**带有 `updated`（ISO 8601 时间）**。旧注释「没有任何逐条 updatedAt」
    是错的；本工具为兼容既有缓存结构仍未写入 `updated`，逐条用本地 `fetchedAt` 代替。
  - `?fields=` 查询参数被上游忽略（载荷恒为 17 MB），故按全量下载。

价格口径（按上游字段名 + 与项目现有 items.json 的对应关系交叉核对，见报告 §4）：
  - lastLowPrice  → 最近一次跳蚤市场最低挂单（"最新低价"）
  - avg24hPrice   → 跳蚤市场 24 小时均价（**历史均价，不是实时价**）
  - low24hPrice / high24hPrice → 24 小时内的最低 / 最高价
  - basePrice     → 基础价（与跳蚤价无关，单独口径）
  上游**不提供** 7 日均价，也不提供"实时挂单列表"；本工具不会用其它字段冒充。

安全约束：
  - 仅标准库；默认走环境代理（http_proxy/https_proxy），localhost 不受影响；
  - 下载 → 全量校验 → 转换 → **原子替换**（tmp + os.replace）；
  - 任何失败（网络/JSON/字段缺失/数量异常/价格越界）**都不写正式缓存**，
    只写 `data/flea-prices.last-error.json` 记录失败原因，旧缓存原样保留；
  - 每天（按**本机本地日期**）最多成功写入一次，`--force` 才可覆盖。

用法：
  python tools/r20_fetch_prices.py                # 当天已更新则跳过
  python tools/r20_fetch_prices.py --force        # 强制刷新
  python tools/r20_fetch_prices.py --dry-run      # 只下载与校验，不写盘
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_OUT = os.path.join(ROOT, "data", "flea-prices.json")
ERROR_OUT = os.path.join(ROOT, "data", "flea-prices.last-error.json")
LOCK_PATH = os.path.join(ROOT, "data", ".flea-prices.lock")
DEFAULT_SOURCE = "https://json.tarkov.dev/regular/items"
DEFAULT_MODE = "regular"
# 模式键 → 真实游戏模式的展示名（regular 是上游路径键，真实含义是 PvP）
MODE_LABELS = {"regular": "PvP（常规）", "pve": "PvE"}
# 项目指定的外网代理（任务书 §六）；环境变量里的 5513 已关闭，故默认走这里。
DEFAULT_PROXY = "http://127.0.0.1:7896"

# R97 市场模块：每次成功抓取都落一份自有快照，供「历史曲线 / 7 日均价」使用。
# 按天保留；每天可有多份（--force 多次抓取时按时间命名，取当天最后一份做日均）。
HISTORY_DIRNAME = "flea-price-history"
HISTORY_KEEP_DAYS = 90
HISTORY_AVG7_DAYS = 7        # 至少 7 个「快照日」才计算，缺一天即不计算（不插值）
HISTORY_FILE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})T(\d{6})\.json$")
ISO_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})"
                    r"(?:\.\d+)?(Z|[+-]\d{2}:\d{2})?$")
MAX_FLEA_LEVEL = 100


def parse_iso(ts):
    """解析上游 ISO 时间（Z / ±hh:mm）；失败返回 None。"""
    if not isinstance(ts, str) or not ISO_RE.match(ts):
        return None
    try:
        dt = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:  # noqa: BLE001
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt.astimezone(datetime.timezone.utc)


def iso_utc(dt):
    return dt.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def normalize_updated(ts):
    dt = parse_iso(ts)
    return iso_utc(dt) if dt else None


def history_dir_for(out_path):
    return os.path.join(os.path.dirname(os.path.abspath(out_path)), HISTORY_DIRNAME)

# 上游价格字段 → 缓存字段（一一对应，不做口径转换）
PRICE_FIELDS = [
    ("lastLowPrice", "lastLowPrice"),
    ("avg24hPrice", "avg24hPrice"),
    ("low24hPrice", "low24hPrice"),
    ("high24hPrice", "high24hPrice"),
    ("basePrice", "basePrice"),
]

# R286 市场大盘：上游现成的涨跌 / 在售挂单数 / 最近扫描时间。
# 与价格字段不同，这些值 0 与负数是合法语义（涨跌为 0、跌价为负、无挂单），
# 不能用价格的正数校验过滤，也不参与 MIN_PRICED 判定。
MARKET_FIELDS = [
    ("changeLast48hPercent", "changeLast48hPercent"),
    ("changeLast48h", "changeLast48h"),
    ("velocity", "velocity"),
    ("lastOfferCount", "lastOfferCount"),
    ("lastScan", "lastScan"),
]

# 校验阈值：低于此数量视为「响应不完整」，拒绝写入缓存
MIN_ITEMS = 1000
MIN_PRICED = 500
MAX_PRICE = 100_000_000


def local_now():
    return datetime.datetime.now().astimezone()


def local_date_str(dt=None):
    return (dt or local_now()).strftime("%Y-%m-%d")


def read_cache(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:  # noqa: BLE001
        return None


def cache_is_fresh(cache, today=None):
    """当天是否已成功更新过——按**本机本地日期**比较，不混用 UTC。"""
    if not isinstance(cache, dict):
        return False
    day = cache.get("localDate") or ""
    if not day:
        ts = cache.get("lastSuccessAt") or ""
        if not ts:
            return False
        try:
            day = datetime.datetime.fromisoformat(ts).astimezone().strftime("%Y-%m-%d")
        except Exception:  # noqa: BLE001
            return False
    return day == (today or local_date_str())


def _proxy_opener(proxy):
    if proxy:
        return urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    return urllib.request.build_opener(urllib.request.ProxyHandler())


def fetch_source(url, proxy=None, timeout=90):
    """下载上游 JSON 字节。返回 (raw_bytes, meta)。失败抛异常。"""
    opener = _proxy_opener(proxy)
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36",
        "Accept": "application/json",
    })
    with opener.open(req, timeout=timeout) as resp:
        raw = resp.read()
        return raw, {"httpStatus": getattr(resp, "status", None),
                     "bytes": len(raw),
                     "sha256": hashlib.sha256(raw).hexdigest()}


def extract_items(doc):
    """从上游响应里取出 items 字典。

    实测结构：{"data": {"items": {<id>: {...}, ...}, ...其它块}, "translations": {...}}
    —— 注意 data 顶层只有约 10 个键，物品表在 data.items 里（早期按 data 直接计数会得到 10）。
    异常载荷（上游报错 / 代理错误页）只有 1 个键，必须被后续的数量校验拦下。
    """
    if not isinstance(doc, dict):
        raise ValueError("上游响应不是对象（类型 %s）" % type(doc).__name__)
    data = doc.get("data")
    if isinstance(data, dict) and isinstance(data.get("items"), dict):
        data = data["items"]
    if not isinstance(data, dict):
        raise ValueError("上游响应缺少 data/items 字典")
    return data


def build_cache(doc, source_url, mode, now=None):
    """校验上游数据并转换为缓存结构；任何异常都抛异常（调用方负责不写盘）。"""
    items = extract_items(doc)
    total = len(items)
    if total < MIN_ITEMS:
        # 带上可诊断信息：上游顶层键 + 载荷样本（截断），便于判断是限流/错误页还是响应不完整
        keys = list(doc.keys())[:6] if isinstance(doc, dict) else []
        sample = json.dumps(doc, ensure_ascii=False)[:200] if isinstance(doc, dict) else str(doc)[:200]
        raise ValueError("上游物品数异常（%d < %d）；顶层键=%s；载荷样本=%s"
                         % (total, MIN_ITEMS, keys, sample))
    now = now or local_now()
    ts = now.isoformat(timespec="seconds")
    out = {}
    priced = 0
    with_updated = 0
    with_level = 0
    updated_max = None
    for item_id, rec in items.items():
        if not isinstance(rec, dict):
            continue
        row = {}
        for src, dst in PRICE_FIELDS:
            v = rec.get(src)
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                continue
            if not (0 < v < MAX_PRICE):
                continue          # 越界值直接丢弃（不按 0 计入，也不写进缓存）
            row[dst] = int(v) if float(v).is_integer() else float(v)
        if not row:
            continue
        # R286：市场指标原值透传（0 / 负数合法，单独校验，不参与价格门槛）
        for src, dst in MARKET_FIELDS:
            value = rec.get(src)
            if isinstance(value, bool) or value is None:
                continue
            if isinstance(value, (int, float, str)) and value != "":
                row[dst] = value
        row["fetchedAt"] = ts
        # 上游逐条 updated（实测 100% 覆盖）：原样归一化成 UTC ISO，供界面显示「更新于」。
        upd = normalize_updated(rec.get("updated"))
        if upd:
            row["updated"] = upd
            with_updated += 1
            dt = parse_iso(upd)
            if dt and (updated_max is None or dt > updated_max):
                updated_max = dt
        # 跳蚤上架等级（db4 的 Lv 列来源）：只接受合法数值，不猜、不补。
        lv = rec.get("minLevelForFlea")
        if isinstance(lv, (int, float)) and not isinstance(lv, bool) \
                and 0 <= lv <= MAX_FLEA_LEVEL:
            row["minLevelForFlea"] = int(lv)
            with_level += 1
        out[str(item_id)] = row
        if "lastLowPrice" in row:
            priced += 1
    if priced < MIN_PRICED:
        raise ValueError("有最近低价的物品过少（%d < %d），疑似字段缺失" % (priced, MIN_PRICED))
    return {
        "schema": 1,
        "source": source_url,
        "sourceType": "tarkov.dev public JSON (items /regular = PvP)",
        # 上游路径键（regular|pve）与其对应的真实游戏模式是两个概念，必须分开写：
        "gameMode": mode,
        "priceMode": "pvp" if mode == "regular" else "pve",
        "modeLabel": MODE_LABELS.get(mode, mode),
        "modeNote": ("上游路径键 regular = PvP（常规），不是 PvE；"
                     "PvE 走 /pve/items，需用 tools/live_prices.py --mode pve 单独抓取，"
                     "两套缓存不混写。"),
        "lastSuccessAt": ts,
        "localDate": local_date_str(now),
        # R97 市场：数据截止（上游逐条 updated 的最大值）与本地生成时刻。
        # generatedAt 用 UTC（与上游 updated 同一坐标系）；lastSuccessAt 保留本地时间兼容旧界面。
        "meta": {
            "generatedAt": iso_utc(now),
            "generatedAtLocal": ts,
            "sourceUpdatedMax": iso_utc(updated_max) if updated_max else None,
            "sourceUpdatedCount": with_updated,
            "minLevelCount": with_level,
            "historyDays": 0,
            "avg7daysPriceReady": False,
            "avg7daysPriceMethod": ("本地每日快照的 lastLowPrice 均值；需至少 %d 个快照日，"
                                    "缺日不计算、不插值、不估算" % HISTORY_AVG7_DAYS),
        },
        "fieldSemantics": {
            "lastLowPrice": "跳蚤市场最近一次最低挂单（最新低价）",
            "avg24hPrice": "跳蚤市场 24 小时均价（历史均价，非实时）",
            "low24hPrice": "24 小时内最低价",
            "high24hPrice": "24 小时内最高价",
            "basePrice": "基础价（与跳蚤价无关）",
            "updated": "上游逐条更新时间（UTC，原样归一化）",
            "minLevelForFlea": "跳蚤市场上架所需最低等级（db4 的 Lv 列同源）",
            "avg7daysPrice": ("仅当本地快照累积 ≥%d 个快照日后，由自有历史均值计算；"
                              "上游本身不提供该字段" % HISTORY_AVG7_DAYS),
            "fetchedAt": "本地抓取时刻（逐物品 updated 已单独写入）",
        },
        "notAvailable": ["avg7daysPrice（上游无该字段；本地快照 ≥%d 个快照日后由历史计算，不估算/不插值）"
                         % HISTORY_AVG7_DAYS,
                         "实时挂单列表（上游该接口不返回挂单明细）",
                         "PvE 模式价格（本快照是 PvP；PvE 需用 tools/live_prices.py 单独抓取）"],
        "counts": {"itemsUpstream": total, "itemsWithPrice": len(out), "withLastLowPrice": priced,
                   "withUpdated": with_updated, "withMinLevel": with_level},
        "items": out,
    }


def write_atomic(path, payload):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(payload, fh, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)


def record_error(message, source, mode, path=ERROR_OUT):
    """记录失败原因；**不触碰正式缓存**。"""
    try:
        write_atomic(path, {"schema": 1, "lastAttemptAt": local_now().isoformat(timespec="seconds"),
                            "source": source, "gameMode": mode, "error": str(message)[:500]})
    except Exception:  # noqa: BLE001
        pass


def acquire_lock(path=LOCK_PATH, stale_seconds=900):
    """跨进程互斥：同一时间只允许一个抓取进程在跑。返回 True=拿到锁。"""
    now = local_now().timestamp()
    try:
        if os.path.exists(path):
            age = now - os.path.getmtime(path)
            if age < stale_seconds:
                return False
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(now).encode())
        os.close(fd)
        return True
    except FileExistsError:
        return False
    except OSError:
        return True      # 锁文件不可用时不阻塞抓取（写盘本身仍是原子的）


def release_lock(path=LOCK_PATH):
    try:
        os.remove(path)
    except OSError:
        pass


def compact_history_items(payload):
    """历史归档只保留价格子集（压缩键），避免每天多份大文件。"""
    out = {}
    for item_id, row in (payload.get("items") or {}).items():
        if not isinstance(row, dict):
            continue
        c = {}
        for src, dst in (("lastLowPrice", "l"), ("avg24hPrice", "a"),
                         ("low24hPrice", "lo"), ("high24hPrice", "hi")):
            v = row.get(src)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                c[dst] = v
        upd = row.get("updated")
        if upd:
            c["u"] = upd
        if c:
            out[str(item_id)] = c
    return out


def history_cutoff_date(now, keep_days):
    day = now.date() if isinstance(now, datetime.datetime) else now
    return day - datetime.timedelta(days=max(1, int(keep_days)) - 1)


def prune_history(directory, keep_days=HISTORY_KEEP_DAYS, now=None):
    """按文件名里的日期清理过期快照；只删本工具命名的文件。"""
    now = now or local_now()
    cutoff = history_cutoff_date(now, keep_days)
    removed = 0
    try:
        names = os.listdir(directory)
    except OSError:
        return 0
    for name in names:
        m = HISTORY_FILE_RE.match(name)
        if not m:
            continue
        try:
            day = datetime.date.fromisoformat(m.group(1))
        except ValueError:
            continue
        if day < cutoff:
            try:
                os.remove(os.path.join(directory, name))
                removed += 1
            except OSError:
                pass
    return removed


def update_history_index(directory, entry, keep_days=HISTORY_KEEP_DAYS, now=None):
    """维护 index.json：前端无法列目录，只能读这个清单。"""
    now = now or local_now()
    cutoff = history_cutoff_date(now, keep_days)
    path = os.path.join(directory, "index.json")
    doc = read_cache(path)
    entries = []
    if isinstance(doc, dict) and isinstance(doc.get("entries"), list):
        entries = [e for e in doc["entries"] if isinstance(e, dict)]
    entries = [e for e in entries
               if e.get("file") != entry.get("file")
               and str(e.get("date") or "") >= cutoff.isoformat()]
    entries.append(entry)
    entries.sort(key=lambda e: (str(e.get("date") or ""), str(e.get("file") or "")))
    write_atomic(path, {"schema": 1, "updatedAt": now.isoformat(timespec="seconds"),
                        "keepDays": keep_days, "entries": entries})


def write_history(payload, out_path, keep_days=HISTORY_KEEP_DAYS, now=None):
    """每次成功抓取落一份快照（文件名带本地时间），并更新 index.json。"""
    now = now or local_now()
    snap = parse_iso(payload.get("lastSuccessAt")) or now.astimezone()
    snap_local = snap.astimezone()
    name = snap_local.strftime("%Y-%m-%dT%H%M%S") + ".json"
    directory = history_dir_for(out_path)
    os.makedirs(directory, exist_ok=True)
    archive = {
        "schema": 1,
        "date": snap_local.strftime("%Y-%m-%d"),
        "snapshotAt": snap_local.isoformat(timespec="seconds"),
        "generatedAt": (payload.get("meta") or {}).get("generatedAt"),
        "sourceUpdatedMax": (payload.get("meta") or {}).get("sourceUpdatedMax"),
        "source": payload.get("source"),
        "gameMode": payload.get("gameMode"),
        "priceMode": payload.get("priceMode"),
        "counts": payload.get("counts") or {},
        "items": compact_history_items(payload),
    }
    write_atomic(os.path.join(directory, name), archive)
    prune_history(directory, keep_days, now)
    update_history_index(directory, {
        "file": name,
        "date": archive["date"],
        "snapshotAt": archive["snapshotAt"],
        "generatedAt": archive["generatedAt"],
        "sourceUpdatedMax": archive["sourceUpdatedMax"],
        "gameMode": archive["gameMode"],
        "priceMode": archive["priceMode"],
        "counts": archive["counts"],
    }, keep_days, now)
    return os.path.join(directory, name)


def list_history_dates(directory):
    """只从文件名汇总快照日（不读文件内容）。"""
    dates = set()
    try:
        names = os.listdir(directory)
    except OSError:
        return dates
    for name in names:
        m = HISTORY_FILE_RE.match(name)
        if m:
            dates.add(m.group(1))
    return dates


def load_daily_snapshots(directory, exclude_date=None, max_dates=HISTORY_AVG7_DAYS):
    """取最近 N 个快照日（每天取最后一份），返回按日期升序的 [(date, payload)]。"""
    try:
        names = sorted((n for n in os.listdir(directory) if HISTORY_FILE_RE.match(n)), reverse=True)
    except OSError:
        return []
    picked = {}
    for name in names:
        m = HISTORY_FILE_RE.match(name)
        day = m.group(1)
        if exclude_date and day == exclude_date:
            continue
        if day in picked:
            continue
        payload = read_cache(os.path.join(directory, name))
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), dict):
            continue
        picked[day] = payload
        if len(picked) >= max_dates:
            break
    return [(d, picked[d]) for d in sorted(picked)]


def compute_avg7(payload, snapshots, today_date, min_days=HISTORY_AVG7_DAYS):
    """用自有快照算 7 日均价：要求每个取用日都有该物品的 lastLowPrice，缺一天即跳过。

    这里只做「已有真实快照的算术平均」，不做任何插值、估算或跨字段冒充。
    """
    maps = {}
    for day, snap in snapshots:
        maps[day] = {iid: row.get("l") for iid, row in (snap.get("items") or {}).items()
                     if isinstance(row, dict)}
    maps[today_date] = {iid: row.get("lastLowPrice") for iid, row in (payload.get("items") or {}).items()
                        if isinstance(row, dict)}
    days = sorted(maps)
    if len(days) < min_days:
        return {}
    use_days = days[-min_days:]
    avg = {}
    for item_id, first in maps[use_days[0]].items():
        vals = []
        for day in use_days:
            v = maps[day].get(item_id)
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not (0 < v < MAX_PRICE):
                vals = []
                break
            vals.append(float(v))
        if vals:
            avg[item_id] = int(round(sum(vals) / len(vals)))
    return avg


def main(argv=None):
    ap = argparse.ArgumentParser(description="R20.5 跳蚤行情抓取器（只写本地缓存，失败不动旧缓存）")
    ap.add_argument("--source", default=DEFAULT_SOURCE, help="上游 JSON 地址（默认 tarkov.dev regular）")
    ap.add_argument("--mode", default=DEFAULT_MODE,
                    help="上游路径键（regular=PvP / pve=PvE）；默认 regular(=PvP)")
    ap.add_argument("--out", default=DEFAULT_OUT, help="缓存文件路径")
    ap.add_argument("--proxy", default=None,
                    help="代理地址（默认用项目指定的 127.0.0.1:7896；--no-proxy 走直连）")
    ap.add_argument("--no-proxy", action="store_true", help="忽略代理，直连下载")
    ap.add_argument("--timeout", type=int, default=90)
    ap.add_argument("--force", action="store_true", help="忽略「当天已更新」直接刷新")
    ap.add_argument("--dry-run", action="store_true", help="只下载与校验，不写盘")
    args = ap.parse_args(argv)

    out_path = args.out
    if not os.path.isabs(out_path):
        out_path = os.path.join(ROOT, out_path)
    # 代理优先级：--proxy > 项目指定代理(7896) > 环境变量。
    # 说明：环境变量里的 127.0.0.1:5513 已实测关闭，而任务书指定的外网代理是 7896，
    # 因此默认走 7896；--no-proxy 可强制直连。localhost 始终直连，不受影响。
    if args.no_proxy:
        proxy = None
    else:
        proxy = args.proxy or DEFAULT_PROXY or os.environ.get("https_proxy") \
            or os.environ.get("http_proxy")

    cache = read_cache(out_path)
    if not args.force and not args.dry_run and cache_is_fresh(cache):
        print("[skip] 当天（%s）已成功更新过：%s" % (local_date_str(), cache.get("lastSuccessAt")))
        return 0

    lock_path = out_path + ".lock"      # 每个缓存文件一把锁，互不阻塞
    if not acquire_lock(lock_path):
        print("[skip] 另一个抓取进程正在运行（锁文件存在），本次不重复下载")
        return 0
    try:
        print("[fetch] %s (proxy=%s)" % (args.source, proxy or "直连"))
        try:
            raw, meta = fetch_source(args.source, proxy=proxy, timeout=args.timeout)
        except urllib.error.HTTPError as e:
            raise RuntimeError("HTTP %s %s" % (e.code, e.reason))
        except Exception as e:  # noqa: BLE001
            raise RuntimeError("下载失败：%s: %s" % (type(e).__name__, e))
        print("[fetch] 收到 %d 字节，sha256=%s" % (meta["bytes"], meta["sha256"][:16]))
        try:
            doc = json.loads(raw.decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            raise RuntimeError("JSON 解析失败：%s" % e)
        payload = build_cache(doc, args.source, args.mode)
        history_dir = history_dir_for(out_path)
        history_dates = list_history_dates(history_dir)
        history_dates.add(payload["localDate"])
        hist = load_daily_snapshots(history_dir, exclude_date=payload["localDate"],
                                    max_dates=HISTORY_AVG7_DAYS)
        avg7 = compute_avg7(payload, hist, payload["localDate"])
        if avg7:
            for item_id, value in avg7.items():
                row = payload["items"].get(item_id)
                if isinstance(row, dict) and "avg7daysPrice" not in row:
                    row["avg7daysPrice"] = value
        payload["meta"]["historyDays"] = len(history_dates)
        payload["meta"]["avg7daysPriceReady"] = bool(avg7)
        payload["meta"]["avg7daysPriceItems"] = len(avg7)
        print("[ok] 校验通过：上游 %d 条 → 缓存 %d 条（含最近低价 %d 条；updated %d、Lv %d）"
              % (payload["counts"]["itemsUpstream"], payload["counts"]["itemsWithPrice"],
                 payload["counts"]["withLastLowPrice"], payload["counts"]["withUpdated"],
                 payload["counts"]["withMinLevel"]))
        print("[history] 快照日 %d 个；7 日均价%s（%d 条）"
              % (payload["meta"]["historyDays"],
                 "已就绪" if avg7 else "累积中（不足 %d 个快照日）" % HISTORY_AVG7_DAYS,
                 len(avg7)))
        if args.dry_run:
            print("[dry-run] 不写盘")
            return 0
        # 先落历史快照，再写正式缓存：归档失败会中止本次成功路径（宁可失败也不悄悄不积累）
        hist_path = write_history(payload, out_path)
        write_atomic(out_path, payload)
        # 成功即清掉上一轮的失败记录（否则界面会一直显示已过期的错误）
        try:
            os.remove(ERROR_OUT)
        except OSError:
            pass
        print("[write] 已原子写入 %s" % out_path)
        print("[write] 历史快照 %s" % hist_path)
        return 0
    except Exception as e:  # noqa: BLE001
        record_error(e, args.source, args.mode)
        print("[fail] %s" % e, file=sys.stderr)
        print("[fail] 旧缓存保持不变", file=sys.stderr)
        return 1
    finally:
        release_lock(lock_path)


if __name__ == "__main__":
    sys.exit(main())
