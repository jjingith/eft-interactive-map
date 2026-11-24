# -*- coding: utf-8 -*-
"""R286 市场大盘聚合。

运行期唯一入口是 `from_snapshots()`：输入云端下发、在本机累积的行情快照
（`cloud-market/history/<mode>/...`），按小时桶聚合涨跌与在售挂单数。
下面的 `overview()` / `baseline()` 是旧的本机采集器 / 内置快照实现，
只保留给构建脚本与历史单测，BFF 不再调用。

严格口径：
  · `o` 是**在售挂单数**，不是成交量。上游无成交笔数字段，绝不伪造。
  · 按小时桶取该小时最后一份快照（同小时多份不重复计数），桶内 0 采样则留空档。
  · 缺字段 / 旧快照没有市场字段 → 该物品该小时记为缺测，不补 0、不插值。
  · 云端还没有市场字段 → 返回 `status: cold_start`，空 series。
"""
from __future__ import annotations

import datetime
import json
import os
import sys
from typing import Any

try:
    import price_history
except ImportError:  # pragma: no cover - 只在本机 BFF / 构建期使用
    price_history = None
try:
    import price_cache
except ImportError:  # pragma: no cover - 只在本机 BFF 使用
    price_cache = None

OUTPUT_NAME = "market-overview.json"
SCHEMA = 1
WINDOW_HOURS_DEFAULT = 24
WINDOW_HOURS_MAX = 72
TOP_N = 10
# 涨跌榜的流动性下限：在售挂单少于这个数的物资不上榜。
# 只有 1 个挂单的冷门物品，挂价随便改一次就是 ±3000%，会把榜单全占满，
# 对「看行情」没有任何参考价值。这是**展示过滤**，不修改原始数据。
MIN_OFFERS_FOR_RANK = 3
# 内置快照基线没有小时序列，单点 48h 涨跌的噪声更大；用更高的流动性门槛，
# 让榜单落在「真的有人买卖」的物资上（采集器有连续快照后仍沿用 3 的门槛）。
BASELINE_MIN_OFFERS = 30

# 与 price_history 一致的模式键
MODES = ("regular", "pve", "pvps")


def _iso(dt: datetime.datetime) -> str:
    return dt.isoformat(timespec="seconds")


def _read_items(path: str) -> dict:
    """读一份快照的 items 字典（gzip，复用 collector_prices 的缓存读取）。"""
    try:
        import collector_prices
    except ImportError:  # pragma: no cover
        return {}
    doc = collector_prices._read_gz_json(path)
    if not isinstance(doc, dict):
        return {}
    items = doc.get("items")
    return items if isinstance(items, dict) else {}


def _market_of(row: Any) -> dict:
    if not isinstance(row, dict):
        return {}
    mk = row.get("mk")
    return mk if isinstance(mk, dict) else {}


def _num(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


_ITEM_CACHE: dict = {"at": None, "size": -1, "map": {}}

# 板块口径：按游戏内 Handbook 的十个分类聚合（不再按 tpl 父类型拆成二十多个碎片）。
# 前端「板块行情」点击后按这里的 key 过滤榜单，因此 key 必须与游戏分类一一对应。
SECTOR_ORDER = ["Barter", "Info", "Container", "Key", "Gear",
                "Weapon", "Mod", "Ammo", "Medical", "Food"]
SECTOR_LABELS = {
    "Barter": "交换物品",
    "Info": "情报物品",
    "Container": "容器",
    "Key": "钥匙",
    "Gear": "装备",
    "Weapon": "武器",
    "Mod": "配件",
    "Ammo": "弹药",
    "Medical": "医疗",
    "Food": "饮食",
    "Other": "交换物品",
}
# items.json 的 `pt`（tpl 父类型）→ 游戏分类
PT_SECTORS = {
    "Weapon": "Weapon", "Melee": "Weapon", "Grenade": "Weapon", "Preset": "Weapon",
    "WeaponMod": "Mod", "Scope": "Mod", "Magazine": "Mod", "Barrel": "Mod",
    "Ammo": "Ammo",
    "Armor": "Gear", "Helmet": "Gear", "ChestRig": "Gear", "Backpack": "Gear",
    "Headwear": "Gear", "Glasses": "Gear", "Headphone": "Gear",
    "ArmorAttachment": "Gear", "NightVision": "Gear",
    "Key": "Key", "Container": "Container",
    "FoodDrink": "Food",
    "MedicalItem": "Medical", "MedKit": "Medical", "Stim": "Medical",
    "Painkiller": "Medical", "SurgicalKit": "Medical", "Injectors": "Medical",
    "InfoContent": "Info",
    "Resource": "Barter", "BarterItem": "Barter", "Other": "Barter",
}
# 没有 `pt` 时回退到 `ts`（types）里的可识别词
TYPE_SECTORS = {
    "gun": "Weapon", "melee": "Weapon", "grenade": "Weapon",
    "mods": "Mod", "suppressor": "Mod", "pistolGrip": "Mod",
    "ammo": "Ammo", "ammoBox": "Ammo",
    "armor": "Gear", "helmet": "Gear", "rig": "Gear", "backpack": "Gear",
    "glasses": "Gear", "headphones": "Gear", "armorPlate": "Gear", "wearable": "Gear",
    "keys": "Key", "container": "Container",
    "provisions": "Food",
    "meds": "Medical", "injectors": "Medical", "medkit": "Medical",
    "surgicalKit": "Medical",
    "barter": "Barter", "resource": "Barter",
    "info": "Info", "infoContent": "Info",
}


def _project_root() -> str:
    """返回包含 `data/` 的目录（源码树根，或打包后的 _internal）。

    PyInstaller 冻结后 `__file__` 落在 `<exe>/_internal/tools/market_overview.py`，
    上两级虽然是 `<exe>/_internal`，但 __file__ 在 onefile 模式下并不可靠，
    所以优先用 _MEIPASS / exe 旁的 _internal 兜底，确保 items.json 能被读到。
    否则这里会返回错目录 → items.json 读空 → 名称全部回退成物品 ID（安装版才会出现）。
    """
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass and os.path.isdir(os.path.join(meipass, "data")):
            return meipass
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        internal = os.path.join(exe_dir, "_internal")
        if os.path.isdir(os.path.join(internal, "data")):
            return internal
        return exe_dir
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _trimmed_mean(values):
    """中位数 ×5 剔除天价孤挂后求平均（大盘七天榜与列表 7 日均价同一口径）。"""
    if not values:
        return None
    ordered_vals = sorted(values)
    median = ordered_vals[len(ordered_vals) // 2]
    kept = [value for value in values if value <= median * 5]
    use = kept or values
    return sum(use) / len(use)


def _sector_key(row: dict) -> str:
    parent = row.get("pt") or row.get("parentType")
    if isinstance(parent, str) and parent:
        mapped = PT_SECTORS.get(parent)
        if mapped:
            return mapped
    for kind in (row.get("ts") or row.get("types") or []):
        mapped = TYPE_SECTORS.get(kind)
        if mapped:
            return mapped
    return "Barter"


def _sector_label(key: str) -> str:
    return SECTOR_LABELS.get(key or "Other", key or "其他")


_SECTOR_MAP_CACHE: dict = {"at": None, "size": -1, "map": {}, "totals": {}}
_CLOUD_SERIES_CACHE: dict = {"path": None, "mtime": None, "map": {}}
_AVG7_CACHE: dict = {"path": None, "mtime": None, "values": {}}


def _cloud_price_series(app_dir: str | None, mode: str) -> dict:
    """读取云端价格缓存（`cloud-cache/<mode>.json`）里的全量序列。

    这份缓存是会员登录后从云端 `/v1/prices/cache` 下载的 30 分钟采样序列，
    大盘的 24h / 48h / 七天均价都以它为准（不再依赖本机自己攒的少量快照）。
    """
    if not app_dir or price_cache is None:
        return {}
    path = price_cache.cache_path(app_dir, mode)
    try:
        stat = os.stat(path)
    except OSError:
        return {}
    if _CLOUD_SERIES_CACHE["path"] == path and _CLOUD_SERIES_CACHE["mtime"] == stat.st_mtime:
        return _CLOUD_SERIES_CACHE["map"]
    out: dict[str, list] = {}
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
        raw = doc.get("series") if isinstance(doc, dict) else None
        for item_id, rows in (raw or {}).items():
            points = []
            for row in rows or []:
                if not isinstance(row, list) or len(row) < 2:
                    continue
                ts, price = row[0], row[1]
                if not isinstance(ts, (int, float)) or not isinstance(price, (int, float)):
                    continue
                if price <= 0:
                    continue
                points.append((datetime.datetime.fromtimestamp(ts / 1000.0, tz=datetime.timezone.utc),
                               float(price)))
            if points:
                out[str(item_id)] = points
    except (OSError, ValueError):
        out = {}
    _CLOUD_SERIES_CACHE.update(path=path, mtime=stat.st_mtime, map=out)
    return out


def seven_day_averages(app_dir: str | None, mode: str) -> dict[str, int]:
    """云端价格缓存 → 物品 id → 过去 7 天均价（中位数 ×5 剔除天价后平均）。

    市场列表的「7 日均价」列与大盘七天价格榜共用这一套口径。窗口锚**缓存里
    最新的采样点**（不是「现在」），采集机停更时右端不会凭空少一天；缓存跨度
    不足 7 天时返回空表，界面照实显示「积累中」，绝不拿更短的窗口冒充 7 天。
    """
    if not app_dir or price_cache is None:
        return {}
    series = _cloud_price_series(app_dir, mode)
    if not series:
        return {}
    path = price_cache.cache_path(app_dir, mode)
    try:
        mtime = os.stat(path).st_mtime
    except OSError:
        return {}
    cache = _AVG7_CACHE
    if cache["path"] == path and cache["mtime"] == mtime:
        return cache["values"]
    # 缓存跨度（所有物品里最早 / 最晚的采样点）
    first = min((points[0][0] for points in series.values() if points), default=None)
    last = max((points[-1][0] for points in series.values() if points), default=None)
    if first is None or last is None or (last - first) < datetime.timedelta(days=7):
        _AVG7_CACHE.update(path=path, mtime=mtime, values={})
        return {}
    cutoff = last - datetime.timedelta(days=7)
    values: dict[str, int] = {}
    for item_id, points in series.items():
        samples = [price for moment, price in points if moment >= cutoff]
        avg = _trimmed_mean(samples)
        if avg is not None and avg > 0:
            values[str(item_id)] = int(round(avg))
    _AVG7_CACHE.update(path=path, mtime=mtime, values=values)
    return values


def _sector_map() -> tuple[dict, dict]:
    """读取 `data/item-sectors.json`（tarkov.dev handbookCategories 的派生表）。

    返回 (id -> [分类 key], 分类 key -> 物品总数)。文件不存在时返回空表，
    调用方回退到 items.json 的 pt/ts 口径（仅测试环境会走到）。
    """
    path = os.path.join(_project_root(), "data", "item-sectors.json")
    try:
        st = os.stat(path)
    except OSError:
        return {}, {}
    if _SECTOR_MAP_CACHE["at"] == st.st_mtime and _SECTOR_MAP_CACHE["size"] == st.st_size:
        return _SECTOR_MAP_CACHE["map"], _SECTOR_MAP_CACHE["totals"]
    mapping: dict[str, list[str]] = {}
    totals: dict[str, int] = {}
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
        raw = doc.get("items") if isinstance(doc, dict) else None
        for item_id, sectors in (raw or {}).items():
            if isinstance(sectors, str):
                sectors = [sectors]
            keys = [str(key) for key in (sectors or []) if str(key) in SECTOR_LABELS
                    and str(key) != "Other"]
            if not keys:
                continue
            mapping[str(item_id)] = keys
            for key in keys:
                totals[key] = totals.get(key, 0) + 1
    except (OSError, ValueError):
        mapping, totals = {}, {}
    _SECTOR_MAP_CACHE.update(at=st.st_mtime, size=st.st_size, map=mapping, totals=totals)
    return mapping, totals


def _item_index() -> dict:
    """id -> {"name", "sector", "sectors"}（取 `data/items.json`；采集快照只存 id，不带名称）。

    板块归属优先用 tarkov.dev handbookCategories 的派生表；派生表缺失时回退到
    items.json 的 pt/ts。快照每行都塞名称会把体积放大数倍（每天 48 份），
    所以名称在读取侧统一解析。文件不存在（纯测试环境）时返回空表，调用方回退到 id。
    """
    path = os.path.join(_project_root(), "data", "items.json")
    try:
        st = os.stat(path)
    except OSError:
        return {}
    if _ITEM_CACHE["at"] == st.st_mtime and _ITEM_CACHE["size"] == st.st_size:
        return _ITEM_CACHE["map"]
    smap, _totals = _sector_map()
    has_map = bool(smap)
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
        items = doc.get("items") if isinstance(doc, dict) else None
        index = {}
        for item_id, row in (items or {}).items():
            if isinstance(row, dict):
                name = row.get("n") or row.get("name")
                sectors = smap.get(str(item_id), []) if has_map else [_sector_key(row)]
                index[str(item_id)] = {
                    "name": str(name) if name else str(item_id),
                    "sector": sectors[0] if sectors else "Other",
                    "sectors": sectors,
                }
    except (OSError, ValueError):
        index = {}
    _ITEM_CACHE.update(at=st.st_mtime, size=st.st_size, map=index)
    return index


def _load_json(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
        return doc if isinstance(doc, dict) else {}
    except (OSError, ValueError):
        return {}


def _short_num(value) -> float | int | None:
    """上游数值统一成 int/float；bool 与空串不算数值。"""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _row_sectors(row: dict) -> list[str]:
    sectors = row.get("sectors")
    if isinstance(sectors, list) and sectors:
        return [str(key) for key in sectors]
    key = row.get("sector")
    return [str(key)] if key else []


def _sector_summary(rows: list[dict]) -> list[dict]:
    """把逐物品行聚合成板块行情。

    `items` 用 tarkov.dev handbookCategories 的全量分类计数（与游戏内 Handbook、
    参考站的分类数量一致）；涨跌 / 挂单只统计有行情的物资。派生表缺失时
    （纯测试环境）退回按行计数。
    """
    _mapping, totals = _sector_map()
    groups: dict[str, dict] = {}

    def group_of(key: str, items: int = 0) -> dict:
        group = groups.get(key)
        if group is None:
            group = {
                "key": key, "label": _sector_label(key), "items": items,
                "up": 0, "down": 0, "flat": 0, "offers": 0,
                "changeSum": 0.0, "changeCount": 0,
            }
            groups[key] = group
        return group

    if totals:
        for key in SECTOR_ORDER:
            count = int(totals.get(key) or 0)
            if count:
                group_of(key, count)
    for row in rows:
        change = _short_num(row.get("change"))
        if change is None:
            continue
        for key in _row_sectors(row):
            if totals and key not in groups:
                continue          # 任务物品 / 地图等不在游戏十类里的条目
            group = group_of(key)
            if not totals:
                group["items"] += 1
            group["changeSum"] += float(change)
            group["changeCount"] += 1
            if change > 0:
                group["up"] += 1
            elif change < 0:
                group["down"] += 1
            else:
                group["flat"] += 1
            offers = _short_num(row.get("offers"))
            if offers is not None and offers > 0:
                group["offers"] += int(offers)
    out = []
    for group in groups.values():
        count = group.pop("changeCount")
        total = group.pop("changeSum")
        group["avgChange"] = round(total / count, 2) if count else None
        out.append(group)
    order = {key: index for index, key in enumerate(SECTOR_ORDER)}
    out.sort(key=lambda g: (order.get(g["key"], len(SECTOR_ORDER)), -g["items"]))
    return out


def overview(mode: str, hours: int = WINDOW_HOURS_DEFAULT,
             *, now: datetime.datetime | None = None,
             ids: list[str] | None = None,
             sector: str | None = None) -> dict:
    """按小时聚合市场指标，返回可直接给前端的结构。

    {"ok": true, "status": "ok"|"cold_start", "mode": ..., "hours": ...,
     "generatedAt": ..., "buckets": [ {"hour": iso, "items": n, "offers": n,
        "avgChange": float|null, "up": n, "down": n, "flat": n} ],
     "gainers": [{"id","name","change","offers","price"}],
     "losers": [...], "hot": [{"id","name","offers","prev","delta","rate","price"}],
     "coverage": {"items": n, "withOffers": n, "withChange": n},
     "note": "在售挂单数，非成交量"}
    """
    mode = str(mode or "regular").strip().lower()
    if mode not in MODES:
        return {"ok": False, "error": "bad-mode", "allowed": list(MODES)}
    hours = max(1, min(WINDOW_HOURS_MAX, int(hours or WINDOW_HOURS_DEFAULT)))
    now = now or datetime.datetime.now().astimezone()

    if price_history is None:
        return {"ok": False, "error": "no-price-history"}

    files = price_history.collector_entries(mode, days=max(1, (hours + 23) // 24 + 1), now=now)
    # 按本地小时桶取最后一份；桶内多份不重复计
    by_hour: dict[str, tuple] = {}
    for when, path in files:
        key = when.strftime("%Y-%m-%dT%H:00")
        prev = by_hour.get(key)
        if prev is None or when > prev[0]:
            by_hour[key] = (when, path)
    ordered = [by_hour[k] for k in sorted(by_hour)]
    ordered = ordered[-hours:]

    buckets: list[dict] = []
    offers_by_bucket: list[dict[str, int]] = []   # 只收有市场字段的桶，供热度榜比上一小时
    last_offers: dict[str, int] = {}
    last_price: dict[str, int | float] = {}
    latest_rows: dict[str, dict] = {}
    any_market = False
    for when, path in ordered:
        rows = _read_items(path)
        offers_total = 0
        with_offers = 0
        changes: list[float] = []
        up = down = flat = 0
        cur_offers: dict[str, int] = {}
        market_rows = 0
        for item_id, row in rows.items():
            mk = _market_of(row)
            if not mk:
                continue
            market_rows += 1
            any_market = True
            latest_rows[str(item_id)] = row
            change = _num(mk.get("c"))
            if change is not None:
                changes.append(float(change))
                if change > 0:
                    up += 1
                elif change < 0:
                    down += 1
                else:
                    flat += 1
            offer = _num(mk.get("o"))
            if offer is not None and float(offer).is_integer():
                cur_offers[str(item_id)] = int(offer)
                offers_total += int(offer)
                with_offers += 1
            price = _num(row.get("l") if isinstance(row, dict) else None)
            if price is not None:
                last_price[str(item_id)] = price
        # 没有 mk 的旧快照（采集器升级前落的）整桶记缺测：offers/avgChange 留 None，
        # 绝不写 0——否则图上会出现一段「在售 0 件」的假断崖。
        has_market = market_rows > 0
        buckets.append({
            "hour": _iso(when.replace(minute=0, second=0, microsecond=0)),
            "items": len(rows),
            "marketRows": market_rows,
            "offers": offers_total if has_market else None,
            "withOffers": with_offers,
            "avgChange": round(sum(changes) / len(changes), 2) if changes else None,
            "up": up if has_market else None,
            "down": down if has_market else None,
            "flat": flat if has_market else None,
        })
        if has_market:
            offers_by_bucket.append(cur_offers)
            if cur_offers:
                last_offers = cur_offers

    if not any_market:
        return {
            "ok": True, "status": "cold_start", "mode": mode, "hours": hours,
            "generatedAt": _iso(now), "buckets": [],
            "gainers": [], "losers": [], "hot": [],
            "coverage": {"items": 0, "withOffers": 0, "withChange": 0},
            "note": "在售挂单数，非成交量；采集器尚未写入市场字段，历史不能回溯",
        }

    # 涨跌榜 / 热度榜用最新一份快照的字段（48h 涨跌是上游现成口径）
    meta = _item_index()

    def _meta_of(item_id: str) -> dict:
        info = meta.get(str(item_id)) or {}
        row = latest_rows.get(item_id) or {}
        return {
            "name": str(row.get("n") or row.get("name") or info.get("name") or item_id),
            "sector": info.get("sector") or "Other",
        }

    def _name_of(item_id: str) -> str:
        return _meta_of(item_id)["name"]

    def _sort_rank(key, reverse, top=TOP_N):
        picked = []
        for item_id, row in latest_rows.items():
            mk = _market_of(row)
            value = _num(mk.get(key))
            if value is None:
                continue
            offers = _num(mk.get("o"))
            # 流动性下限：避免「1 个挂单 +3900%」这类噪声占满榜单。
            # 没有挂单数的物资同样不上榜（无法判断流动性）。
            if offers is None or offers < MIN_OFFERS_FOR_RANK:
                continue
            info = _meta_of(item_id)
            if sector and info["sector"] != sector:
                continue
            picked.append({
                "id": item_id, "name": info["name"], "sector": info["sector"],
                "sectorLabel": _sector_label(info["sector"]),
                "change": _num(mk.get("c")), "changeAmount": _num(mk.get("d")),
                "offers": offers, "price": _num(row.get("l")), "value": value,
            })
        picked.sort(key=lambda r: r["value"], reverse=reverse)
        return [{k: v for k, v in r.items() if k != "value"} for r in picked[:top]]

    gainers = _sort_rank("c", True)
    losers = _sort_rank("c", False)

    # 热度 = 在售挂单数相对**上一个有市场数据的桶**的变化率；没有可比桶则 rate=None，不补 0。
    # 不能直接拿 ordered[-2] 的文件：那可能是采集器升级前落下的无 mk 快照。
    prev_offers: dict[str, int] = {}
    if len(offers_by_bucket) >= 2:
        prev_offers = offers_by_bucket[-2]
    hot = []
    for item_id, current in last_offers.items():
        prev = prev_offers.get(item_id)
        rate = None
        if prev is not None and prev > 0:
            rate = round((current - prev) / prev * 100.0, 2)
        info = _meta_of(item_id)
        hot.append({
            "id": item_id, "name": info["name"], "sector": info["sector"],
            "sectorLabel": _sector_label(info["sector"]),
            "offers": current, "prev": prev, "rate": rate,
            "price": last_price.get(item_id),
        })
    hot.sort(key=lambda r: (abs(r["rate"]) if r["rate"] is not None else -1), reverse=True)

    with_change = sum(1 for row in latest_rows.values() if _num(_market_of(row).get("c")) is not None)
    # 板块聚合要覆盖所有有 48h 涨跌的物品，不能只用 TOP_N 榜单。
    all_rows = []
    for item_id, row in latest_rows.items():
        mk = _market_of(row)
        info = _meta_of(item_id)
        all_rows.append({
            "id": item_id, "name": info["name"], "sector": info["sector"],
            "change": _num(mk.get("c")), "changeAmount": _num(mk.get("d")),
            "offers": _num(mk.get("o")), "price": _num(row.get("l")),
        })
    item_details = {}
    if ids:
        wanted = {str(value) for value in ids}
        item_details = {row["id"]: row for row in all_rows if row["id"] in wanted}
    last_market = None
    for bucket in reversed(buckets):
        if bucket.get("up") is not None:
            last_market = bucket
            break
    summary = {
        "up": (last_market or {}).get("up") or 0,
        "down": (last_market or {}).get("down") or 0,
        "flat": (last_market or {}).get("flat") or 0,
        "avgChange": (last_market or {}).get("avgChange"),
        "offers": (last_market or {}).get("offers"),
        "items": len(latest_rows),
        "priced": len(last_price),
    }
    return {
        "ok": True, "status": "ok", "mode": mode, "hours": hours,
        "source": "collector", "dataAt": (last_market or {}).get("hour") or _iso(now),
        "generatedAt": _iso(now),
        "buckets": buckets,
        "gainers": gainers, "losers": losers, "hot": hot[:TOP_N],
        "items": item_details,
        "minOffers": MIN_OFFERS_FOR_RANK,
        "summary": summary,
        "sectors": _sector_summary(all_rows),
        "coverage": {
            "items": len(latest_rows),
            "withOffers": len(last_offers),
            "withChange": with_change,
        },
        "note": "在售挂单数，非成交量；涨跌榜仅统计在售挂单 ≥%d 的物资；缺测不补 0、不插值"
                % MIN_OFFERS_FOR_RANK,
    }


def baseline(mode: str, *, root: str | None = None,
             now: datetime.datetime | None = None,
             ids: list[str] | None = None,
             sector: str | None = None) -> dict:
    """内置快照基线：没有采集器快照时，也能给出真实的涨跌榜与板块行情。

    regular 用 `data/items.json` 的 `mk` 块（构建期已写入 lastOfferCount /
    changeLast48h）；pve / pvps 用 `data/flea-prices-<mode>.json` 的同名字段。
    名称与板块仍从 items.json 的 `pt / ts` 取，避免三套数据各写一份。
    没有历史桶，`buckets` 恒为空；涨跌是**上游 48h 口径**，不是自算的小时涨跌。
    """
    mode = str(mode or "regular").strip().lower()
    if mode not in MODES:
        return {"ok": False, "error": "bad-mode", "allowed": list(MODES)}
    now = now or datetime.datetime.now().astimezone()
    root = root or _project_root()
    data_dir = os.path.join(root, "data")
    if mode == "regular":
        doc = _load_json(os.path.join(data_dir, "items.json"))
        source = "bundled-items"
    else:
        doc = _load_json(os.path.join(data_dir, "flea-prices-%s.json" % mode))
        source = "bundled-prices"
    items = doc.get("items") if isinstance(doc, dict) else None
    if not isinstance(items, dict) or not items:
        return {
            "ok": True, "status": "cold_start", "mode": mode, "hours": 0,
            "source": source, "dataAt": None, "generatedAt": _iso(now),
            "buckets": [], "gainers": [], "losers": [], "hot": [], "sectors": [],
            "summary": {"up": 0, "down": 0, "flat": 0, "avgChange": None,
                        "offers": 0, "items": 0, "priced": 0},
            "coverage": {"items": 0, "withOffers": 0, "withChange": 0, "withPrice": 0},
            "note": "没有可用的内置行情快照",
        }

    meta = _item_index()
    rows = []
    changes = []
    offers_total = 0
    with_offers = with_change = with_price = 0
    data_at = ""
    for item_id, rec in items.items():
        if not isinstance(rec, dict):
            continue
        info = meta.get(str(item_id)) or {}
        if mode == "regular":
            mk = rec.get("mk") if isinstance(rec.get("mk"), dict) else {}
            price_block = rec.get("p") if isinstance(rec.get("p"), dict) else {}
            price = _num(price_block.get("l"))
            avg24h = _num(price_block.get("a"))
            low = _num(price_block.get("lo"))
            high = _num(price_block.get("hi"))
            offers = _num(mk.get("o"))
            change = _num(mk.get("c"))
            change_amount = _num(mk.get("d"))
            last_scan = mk.get("s") or rec.get("lastScan")
        else:
            price = _num(rec.get("lastLowPrice"))
            avg24h = _num(rec.get("avg24hPrice"))
            low = _num(rec.get("low24hPrice"))
            high = _num(rec.get("high24hPrice"))
            offers = _num(rec.get("lastOfferCount"))
            change = _num(rec.get("changeLast48hPercent"))
            change_amount = _num(rec.get("changeLast48h"))
            last_scan = rec.get("lastScan")
        if price is None and change is None and offers is None:
            continue
        name = info.get("name") or rec.get("n") or rec.get("name") or str(item_id)
        # 注意：这里不能用 `sector` 作循环变量，否则会覆盖函数参数 sector，
        # 让后面的榜单筛选变成「只留最后一条物品的板块」。
        row_sector = info.get("sector") or _sector_key(rec)
        row = {
            "id": str(item_id), "name": str(name), "sector": row_sector,
            "sectorLabel": _sector_label(row_sector),
            "price": price, "avg24h": avg24h, "low24h": low, "high24h": high,
            "change": change, "changeAmount": change_amount, "offers": offers,
            "lastScan": str(last_scan) if last_scan else None,
        }
        rows.append(row)
        if price is not None:
            with_price += 1
        if change is not None:
            with_change += 1
            changes.append(float(change))
        if offers is not None and offers > 0:
            with_offers += 1
            offers_total += int(offers)
        stamp = row["lastScan"] or rec.get("fetchedAt") or rec.get("updated")
        if isinstance(stamp, str) and stamp > data_at:
            data_at = stamp

    if not rows:
        return {
            "ok": True, "status": "cold_start", "mode": mode, "hours": 0,
            "source": source, "dataAt": None, "generatedAt": _iso(now),
            "buckets": [], "gainers": [], "losers": [], "hot": [], "sectors": [],
            "summary": {"up": 0, "down": 0, "flat": 0, "avgChange": None,
                        "offers": 0, "items": 0, "priced": 0},
            "coverage": {"items": 0, "withOffers": 0, "withChange": 0, "withPrice": 0},
            "note": "内置快照没有可用的价格 / 市场字段",
        }

    ranked = [row for row in rows if row["change"] is not None
              and row["offers"] is not None and row["offers"] >= BASELINE_MIN_OFFERS
              and (not sector or row["sector"] == sector)]
    gainers = sorted(ranked, key=lambda r: r["change"], reverse=True)[:TOP_N]
    losers = sorted(ranked, key=lambda r: r["change"])[:TOP_N]
    up = sum(1 for value in changes if value > 0)
    down = sum(1 for value in changes if value < 0)
    flat = len(changes) - up - down
    summary = {
        "up": up, "down": down, "flat": flat,
        "avgChange": round(sum(changes) / len(changes), 2) if changes else None,
        "offers": offers_total, "items": len(rows), "priced": with_price,
    }
    item_details = {}
    if ids:
        wanted = {str(value) for value in ids}
        item_details = {row["id"]: row for row in rows if row["id"] in wanted}
    return {
        "ok": True, "status": "baseline", "mode": mode, "hours": 0,
        "source": source, "dataAt": data_at or None, "generatedAt": _iso(now),
        "buckets": [], "gainers": gainers, "losers": losers, "hot": [],
        "items": item_details,
        "minOffers": BASELINE_MIN_OFFERS,
        "ranked": len(ranked),
        "summary": summary,
        "sectors": _sector_summary(rows),
        "coverage": {
            "items": len(rows), "withOffers": with_offers,
            "withChange": with_change, "withPrice": with_price,
        },
        "note": "内置快照（非实时）；涨跌为上游 48h 口径；在售挂单数，非成交量；"
                "历史曲线需本机采集器或云端 history 累积",
    }


def _parse_moment(value) -> datetime.datetime | None:
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


def _snapshot_rows(snapshot: dict) -> dict[str, dict]:
    """把一份云端快照整理成 `物品 -> 市场字段`；没有 market 时退回 prices。"""
    prices = snapshot.get("prices") if isinstance(snapshot.get("prices"), dict) else {}
    market = snapshot.get("market") if isinstance(snapshot.get("market"), dict) else {}
    rows: dict[str, dict] = {}
    for item_id, rec in market.items():
        if isinstance(rec, dict):
            rows[str(item_id)] = dict(rec)
    for item_id, price in prices.items():
        key = str(item_id)
        price = _num(price)
        if price is None:
            continue
        row = rows.get(key)
        if row is None:
            rows[key] = {"l": price}
        elif _num(row.get("l")) is None:
            row["l"] = price
    return rows


def from_snapshots(mode: str, snapshots: list[dict], hours: int = WINDOW_HOURS_DEFAULT,
                   *, now: datetime.datetime | None = None,
                   ids: list[str] | None = None,
                   sector: str | None = None,
                   app_dir: str | None = None) -> dict:
    """用云端快照（最新一份 + 本机累积的历史）生成大盘，口径与 `overview` 一致。

    数据只来自云端：`market` 字段缺失就是没有涨跌 / 挂单，不拿别的模式或
    内置快照顶替。`hours` 只影响小时桶和曲线窗口，榜单始终用最新一份快照。
    """
    mode = str(mode or "regular").strip().lower()
    if mode not in MODES:
        return {"ok": False, "error": "bad-mode", "allowed": list(MODES)}
    hours = max(1, min(WINDOW_HOURS_MAX, int(hours or WINDOW_HOURS_DEFAULT)))
    now = now or datetime.datetime.now().astimezone()

    ordered = []
    for snapshot in snapshots or []:
        if not isinstance(snapshot, dict):
            continue
        moment = _parse_moment(snapshot.get("generated_at") or snapshot.get("generatedAt"))
        rows = _snapshot_rows(snapshot)
        if moment is None or not rows:
            continue
        ordered.append((moment, rows, snapshot))
    ordered.sort(key=lambda entry: entry[0])
    if not ordered:
        return {
            "ok": True, "status": "cold_start", "mode": mode, "hours": hours,
            "source": "cloud", "dataAt": None, "generatedAt": _iso(now),
            "buckets": [], "gainers": [], "losers": [], "hot": [], "trend": [],
            "items": {}, "sectors": [],
            "summary": {"up": 0, "down": 0, "flat": 0, "avgChange": None,
                        "offers": None, "items": 0, "priced": 0},
            "coverage": {"items": 0, "withOffers": 0, "withChange": 0, "withPrice": 0},
            "note": "云端还没有可用于大盘的行情快照",
        }

    latest_moment = ordered[-1][0]
    cutoff = latest_moment - datetime.timedelta(hours=hours)
    window = [entry for entry in ordered if entry[0] >= cutoff]

    buckets: list[dict] = []
    offers_by_bucket: list[dict[str, int]] = []
    last_offers: dict[str, int] = {}
    last_price: dict[str, float] = {}
    for moment, rows, _snapshot in window:
        market_rows = 0
        offers_total = 0
        with_offers = 0
        changes: list[float] = []
        up = down = flat = 0
        current_offers: dict[str, int] = {}
        for item_id, row in rows.items():
            offer = _num(row.get("o"))
            change = _num(row.get("c"))
            if offer is None and change is None:
                continue
            market_rows += 1
            if change is not None:
                changes.append(float(change))
                if change > 0:
                    up += 1
                elif change < 0:
                    down += 1
                else:
                    flat += 1
            if offer is not None and float(offer).is_integer() and offer >= 0:
                current_offers[item_id] = int(offer)
                offers_total += int(offer)
                with_offers += 1
            price = _num(row.get("l"))
            if price is not None:
                last_price[item_id] = price
        has_market = market_rows > 0
        buckets.append({
            "hour": _iso(moment.replace(minute=0, second=0, microsecond=0)),
            "items": len(rows),
            "marketRows": market_rows,
            "offers": offers_total if has_market else None,
            "withOffers": with_offers,
            "avgChange": round(sum(changes) / len(changes), 2) if changes else None,
            "up": up if has_market else None,
            "down": down if has_market else None,
            "flat": flat if has_market else None,
        })
        if has_market:
            offers_by_bucket.append(current_offers)
            if current_offers:
                last_offers = current_offers

    latest_rows = ordered[-1][1]
    meta = _item_index()

    def _meta_of(item_id: str) -> dict:
        info = meta.get(str(item_id))
        if not info:
            return {"name": str(item_id), "sector": "Other", "sectors": []}
        sectors = info.get("sectors")
        if sectors is None:
            sectors = [info.get("sector") or "Other"]
        return {
            "name": info.get("name") or str(item_id),
            "sector": sectors[0] if sectors else "Other",
            "sectors": sectors,
        }

    def _rank(reverse: bool) -> list[dict]:
        picked = []
        for item_id, row in latest_rows.items():
            change = _num(row.get("c"))
            offers = _num(row.get("o"))
            if change is None:
                continue
            info = _meta_of(item_id)
            if sector and sector not in info["sectors"]:
                continue
            picked.append({
                "id": item_id, "name": info["name"], "sector": info["sector"],
                "sectorLabel": _sector_label(info["sector"]),
                "change": change, "changeAmount": _num(row.get("d")),
                "offers": offers, "price": _num(row.get("l")), "value": change,
            })
        picked.sort(key=lambda item: item["value"], reverse=reverse)
        return [{key: value for key, value in item.items() if key != "value"}
                for item in picked[:TOP_N]]

    all_rows = []
    for item_id, row in latest_rows.items():
        info = _meta_of(item_id)
        all_rows.append({
            "id": item_id, "name": info["name"], "sector": info["sector"],
            "sectors": info["sectors"],
            "change": _num(row.get("c")), "changeAmount": _num(row.get("d")),
            "offers": _num(row.get("o")), "price": _num(row.get("l")),
            "lastScan": row.get("s") or row.get("u"),
        })

    prev_offers = offers_by_bucket[-2] if len(offers_by_bucket) >= 2 else {}
    hot = []
    for item_id, current in last_offers.items():
        info = _meta_of(item_id)
        # R19.69：热卖榜同样要跟随板块筛选，否则点「装备」后榜单里混进别的分类
        if sector and sector not in info["sectors"]:
            continue
        prev = prev_offers.get(item_id)
        rate = round((current - prev) / prev * 100.0, 2) if prev else None
        hot.append({
            "id": item_id, "name": info["name"], "sector": info["sector"],
            "sectorLabel": _sector_label(info["sector"]),
            "offers": current, "prev": prev, "rate": rate,
            "price": last_price.get(item_id),
        })
    # 热卖榜按**当前在售挂单数**降序（榜单标题就是「在售挂单数」）；
    # 同数时再看 24h 变化率。之前按 rate 排序，会把挂单少的暴涨物品排到第一。
    hot.sort(key=lambda item: (
        item["offers"],
        abs(item["rate"]) if item["rate"] is not None else -1,
    ), reverse=True)

    last_bucket = next((bucket for bucket in reversed(buckets) if bucket.get("up") is not None), {})
    with_change = sum(1 for row in latest_rows.values() if _num(row.get("c")) is not None)
    with_offers = sum(1 for row in latest_rows.values() if _num(row.get("o")) is not None)
    item_details = {}
    if ids:
        wanted = {str(value) for value in ids}
        item_details = {row["id"]: row for row in all_rows if row["id"] in wanted}

    # —— 全市场排行（24h / 48h / 七天）——
    # 所有榜单都从**全部有价格的物品**里选，板块筛选时从该板块的全量物品里选；
    # 不再只从涨跌/热卖候选里二次排序。
    sample_cutoff = latest_moment - datetime.timedelta(days=7)

    price_samples: dict[str, list] = {}
    for moment, rows, _snapshot in ordered:
        if moment < sample_cutoff:
            continue
        for item_id, row in rows.items():
            price = _num(row.get("l"))
            if price is not None and price > 0:
                price_samples.setdefault(item_id, []).append((moment, float(price)))
    # 云端价格缓存（会员下载的 30 分钟全量序列）优先；没有时才用本机快照采样
    cloud_series = _cloud_price_series(app_dir, mode)

    trend = []
    rank_rows = []
    for item_id, latest in latest_rows.items():
        info = _meta_of(item_id)
        if sector and sector not in info["sectors"]:
            continue
        samples = cloud_series.get(item_id) or price_samples.get(item_id) or []
        price = _num(latest.get("l"))
        if price is None and samples:
            price = samples[-1][1]
        if price is None:
            continue
        offers = _num(latest.get("o"))

        # 24h / 48h 均价优先用云端序列计算（与本项目其它曲线同一口径）；
        # 云端缓存还没覆盖到的物品才退回上游字段 / 本机快照采样。
        avg24 = None
        if samples:
            cutoff24 = latest_moment - datetime.timedelta(hours=24)
            avg24 = _trimmed_mean([value for moment, value in samples if moment >= cutoff24])
        if avg24 is None:
            avg24 = _num(latest.get("a"))
        avg48 = None
        if samples:
            cutoff48 = latest_moment - datetime.timedelta(hours=48)
            avg48 = _trimmed_mean([value for moment, value in samples if moment >= cutoff48])
        if avg48 is None:
            change48_up = _num(latest.get("c"))
            if change48_up is not None and (100 + change48_up) > 0:
                avg48 = price / (1 + change48_up / 100.0)

        def _pack(avg):
            if avg is None or avg <= 0:
                return None
            change = (price / avg - 1) * 100
            if abs(change) > 1000:      # 与前端 MAX_PLAUSIBLE_PCT 一致，剔除脏值
                return None
            return {"avg": round(avg), "amount": round(price - avg), "change": round(change, 2)}

        p24 = _pack(avg24)
        p48 = _pack(avg48)
        row = {
            "id": item_id, "name": info["name"], "sector": info["sector"],
            "sectorLabel": _sector_label(info["sector"]),
            "price": price, "offers": offers,
        }
        if p24:
            row.update({"avg24": p24["avg"], "amount24": p24["amount"], "change24": p24["change"]})
        if p48:
            row.update({"avg48": p48["avg"], "amount48": p48["amount"], "change48": p48["change"]})
        rank_rows.append(row)

        avg7 = _trimmed_mean([value for _moment, value in samples])
        if avg7 is not None:
            trend.append({
                "id": item_id, "name": info["name"], "sector": info["sector"],
                "sectorLabel": _sector_label(info["sector"]),
                "price": price, "offers": offers,
                "avg7": round(avg7), "samples": len(samples),
            })

    def _top(field: str, reverse: bool) -> list[dict]:
        picked = [row for row in rank_rows if field in row]
        picked.sort(key=lambda row: row[field], reverse=reverse)
        return picked[:TOP_N]

    trend.sort(key=lambda row: row["avg7"], reverse=True)

    return {
        "ok": True, "status": "ok", "mode": mode, "hours": hours,
        "source": "cloud", "dataAt": _iso(latest_moment), "generatedAt": _iso(now),
        "buckets": buckets,
        "gainers": _rank(True), "losers": _rank(False), "hot": hot[:TOP_N],
        "gainers24": _top("change24", True), "losers24": _top("change24", False),
        "gainers48": _top("change48", True), "losers48": _top("change48", False),
        "trend": trend[:TOP_N],
        "items": item_details,
        "minOffers": 0,
        "summary": {
            "up": last_bucket.get("up") or 0,
            "down": last_bucket.get("down") or 0,
            "flat": last_bucket.get("flat") or 0,
            "avgChange": last_bucket.get("avgChange"),
            "offers": last_bucket.get("offers"),
            "items": len(latest_rows),
            "priced": len(last_price),
        },
        "sectors": _sector_summary(all_rows),
        "coverage": {
            "items": len(latest_rows),
            "withOffers": with_offers,
            "withChange": with_change,
            "withPrice": len(last_price),
        },
        "note": "在售挂单数，非成交量；榜单不设在售数量门槛；缺测不补 0、不插值",
    }


def build(root: str, *, now: datetime.datetime | None = None) -> str:
    """构建期把三种模式的大盘快照写到 `<root>/data/market-overview.json`。"""
    doc = {
        "schema": SCHEMA,
        "generatedAt": _iso(now or datetime.datetime.now().astimezone()),
        "modes": {mode: overview(mode, now=now) for mode in MODES},
    }
    target = os.path.join(root, "data", OUTPUT_NAME)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, separators=(",", ":"))
    return target
