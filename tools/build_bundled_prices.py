# -*- coding: utf-8 -*-
"""R79 构建期生成「随安装包内置」的三模式行情快照（只读采集器，不联网）。

数据来源（采集器落盘，见 tools/price_collect.py）：
  <collector>/collect/snapshots/{mode}/{YYYY-MM-DD}/{HHMMSS}.json.gz   最新价锚点
  <collector>/collect/daily/{mode}/{YYYY-MM-DD}.json.gz                日锚点 + 7 日均价

产物（随安装包分发，免费用户的市场数据源）：
  data/flea-prices.json          PvP（regular）
  data/flea-prices-pve.json      PvE
  data/flea-prices-pvps.json     PvPS（赛季服，上游 pvp-season）

字段与 r20_fetch_prices.py 的缓存保持一致（lastLowPrice / avg24hPrice / …），
另外用采集器的 `daily/` 锚点补 `avg7daysPrice`（至少 7 个快照日，缺日不插值）。

构建步骤：
  1. python tools/build_bundled_prices.py                （默认读 %LOCALAPPDATA%\\EFTPrice）
  2. python tools/build_bundled_prices.py --allow-stale  （允许数据超过 --max-age-hours）
  3. 打包：python tools/build_release.py ...             （把 data/ 一起打进安装包）
"""
from __future__ import annotations

import argparse
import datetime
import gzip
import json
import os
import sys
from typing import Any

import price_collect

DEFAULT_OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
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
MODE_NOTES = {
    "regular": "上游路径键 regular = PvP（常规）；内置快照在打包时由采集器日锚点生成。",
    "pve": "PvE 走上游 /pve/items；内置快照在打包时由采集器日锚点生成，与 PvP 不混写。",
    "pvps": "PvPS 走上游 /pvp-season/items（赛季服）；内置快照在打包时由采集器日锚点生成。",
}
HISTORY_AVG7_DAYS = 7
MAX_PRICE = 100_000_000
MAX_FLEA_LEVEL = 60
_SNAP_RE_SUFFIX = ".json.gz"


def _valid_price(value) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not (0 < value < MAX_PRICE):
        return None
    return int(value) if float(value).is_integer() else value


def _read_gz(path: str) -> dict | None:
    try:
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            doc = json.load(fh)
        return doc if isinstance(doc, dict) else None
    except (OSError, ValueError):
        return None


def _day_dirs(path: str) -> list[str]:
    try:
        return sorted(
            name for name in os.listdir(path)
            if os.path.isdir(os.path.join(path, name)) and len(name) == 10
        )
    except OSError:
        return []


def latest_snapshot(data_root: str, mode: str) -> dict | None:
    """最新一份 30 分钟快照（含 l/a/u）。"""
    base = price_collect.snapshot_dir(data_root, mode)
    for day in reversed(_day_dirs(base)):
        try:
            names = sorted(
                n for n in os.listdir(os.path.join(base, day)) if n.endswith(_SNAP_RE_SUFFIX)
            )
        except OSError:
            continue
        if names:
            return _read_gz(os.path.join(base, day, names[-1]))
    return None


def daily_anchors(data_root: str, mode: str) -> list[dict]:
    """按日期升序返回所有日锚点（含 lo/hi/b/lv）。"""
    base = price_collect.daily_dir(data_root, mode)
    try:
        names = sorted(n for n in os.listdir(base) if n.endswith(_SNAP_RE_SUFFIX))
    except OSError:
        return []
    out = []
    for name in names:
        doc = _read_gz(os.path.join(base, name))
        if doc and isinstance(doc.get("items"), dict):
            doc["date"] = name[:-len(_SNAP_RE_SUFFIX)]
            out.append(doc)
    return out


def avg7_values(anchors: list[dict]) -> tuple[int, dict[str, int]]:
    """最近 7 个日锚点的 l 均值；缺日/缺价不插值，直接跳过该物品。"""
    tail = anchors[-HISTORY_AVG7_DAYS:]
    if len(tail) < HISTORY_AVG7_DAYS:
        return 0, {}
    values: dict[str, int] = {}
    common = set((tail[0].get("items") or {}).keys())
    for doc in tail[1:]:
        common &= set((doc.get("items") or {}).keys())
    for item_id in common:
        prices = []
        for doc in tail:
            value = _valid_price((doc["items"].get(item_id) or {}).get("l"))
            if value is None:
                prices = []
                break
            prices.append(value)
        if prices:
            values[item_id] = int(round(sum(prices) / len(prices)))
    return HISTORY_AVG7_DAYS, values


def _full_row(short: dict, fetched_at: str) -> dict:
    row: dict[str, Any] = {}
    mapping = (
        ("l", "lastLowPrice"), ("a", "avg24hPrice"), ("lo", "low24hPrice"),
        ("hi", "high24hPrice"), ("b", "basePrice"),
    )
    for src, dst in mapping:
        value = _valid_price(short.get(src))
        if value is not None:
            row[dst] = value
    if short.get("u"):
        row["updated"] = str(short["u"])
    lv = short.get("lv")
    if isinstance(lv, int) and not isinstance(lv, bool) and 0 <= lv <= MAX_FLEA_LEVEL:
        row["minLevelForFlea"] = lv
    # R286：市场大盘字段（在售挂单数 / 48h 涨跌 / 动能）随内置快照一起发布，
    # 否则没有采集器的机器打开大盘只能看到冷启动空态。这些是上游原值，不计算。
    market = short.get("mk") if isinstance(short.get("mk"), dict) else {}
    for src, dst in (("o", "lastOfferCount"), ("c", "changeLast48hPercent"),
                     ("d", "changeLast48h"), ("v", "velocity"), ("s", "lastScan")):
        value = market.get(src)
        if value is None or isinstance(value, bool) or value == "":
            continue
        row[dst] = value
    row["fetchedAt"] = fetched_at
    return row


def build_mode_payload(app_root: str, mode: str, now: datetime.datetime) -> tuple[dict | None, list[str]]:
    data_root = price_collect.data_dir(app_root)
    warnings: list[str] = []
    snap = latest_snapshot(data_root, mode)
    anchors = daily_anchors(data_root, mode)
    if not snap and not anchors:
        return None, ["%s：没有任何采集快照，无法生成内置快照" % mode]

    latest_anchor = anchors[-1] if anchors else {}
    # 最新快照的 l/a/u 比日锚点更新；lo/hi/b/lv 只有日锚点有。
    merged: dict[str, dict] = {}
    for item_id, row in (latest_anchor.get("items") or {}).items():
        if isinstance(row, dict):
            merged[str(item_id)] = dict(row)
    for item_id, row in ((snap or {}).get("items") or {}).items():
        if not isinstance(row, dict):
            continue
        tgt = merged.setdefault(str(item_id), {})
        for key in ("l", "a", "u"):
            if _valid_price(row.get(key)) is not None or (key == "u" and row.get(key)):
                tgt[key] = row[key]
        # 最新快照的 mk 比日锚点新；只在快照确实带了市场字段时覆盖，
        # 旧快照没有 mk 时保留锚点里的值（不把已有字段清空）。
        if isinstance(row.get("mk"), dict) and row["mk"]:
            tgt["mk"] = row["mk"]

    snapshot_at = (snap or {}).get("snapshotAt") or latest_anchor.get("snapshotAt") or now.isoformat(timespec="seconds")
    source_max = (snap or {}).get("sourceUpdatedMax") or latest_anchor.get("sourceUpdatedMax")
    counts = (snap or {}).get("counts") or latest_anchor.get("counts") or {}

    days, avg_values = avg7_values(anchors)
    if latest_anchor and not snap:
        warnings.append("%s：只有日锚点，没有最新快照；l/a/u 可能最多滞后一轮" % mode)
    if days < HISTORY_AVG7_DAYS:
        warnings.append("%s：日锚点 %d 天 < %d 天，avg7daysPrice 暂不生成（不插值）"
                        % (mode, len(anchors), HISTORY_AVG7_DAYS))

    items: dict[str, dict] = {}
    with_low = with_updated = with_level = 0
    for item_id, short in merged.items():
        row = _full_row(short, str(latest_anchor.get("snapshotAt") or snapshot_at))
        if not row:
            continue
        if "lastLowPrice" in row:
            with_low += 1
        if "updated" in row:
            with_updated += 1
        if "minLevelForFlea" in row:
            with_level += 1
        value = avg_values.get(item_id)
        if value is not None:
            row["avg7daysPrice"] = value
        items[str(item_id)] = row

    payload = {
        "schema": 1,
        "source": "EFTPriceCollector 本地采集（构建期日锚点）",
        "sourceType": "bundled-snapshot (daily anchor + latest snapshot)",
        "gameMode": mode,
        "priceMode": mode,
        "modeLabel": MODE_LABELS.get(mode, mode),
        "modeNote": MODE_NOTES.get(mode, ""),
        "lastSuccessAt": str((snap or latest_anchor).get("snapshotAt") or now.isoformat(timespec="seconds")),
        "localDate": now.strftime("%Y-%m-%d"),
        "meta": {
            "generatedAt": snapshot_at,
            "generatedAtLocal": snapshot_at,
            "sourceUpdatedMax": source_max,
            "sourceUpdatedCount": with_updated,
            "minLevelCount": with_level,
            "historyDays": len(anchors),
            "avg7daysPriceReady": bool(avg_values),
            "avg7daysPriceMethod": (
                "本地每日快照的 lastLowPrice 均值；需至少 %d 个快照日，"
                "缺日不计算、不插值、不估算" % HISTORY_AVG7_DAYS
            ),
            "bundledAt": now.isoformat(timespec="seconds"),
            "bundledFrom": "tools/build_bundled_prices.py",
        },
        "fieldSemantics": {
            "lastLowPrice": "跳蚤市场最近一次最低挂单（最新低价）",
            "avg24hPrice": "跳蚤市场 24 小时均价（历史均价，非实时）",
            "low24hPrice": "24 小时内最低价",
            "high24hPrice": "24 小时内最高价",
            "basePrice": "基础价（与跳蚤价无关）",
            "updated": "上游逐条更新时间（UTC，原样归一化）",
            "minLevelForFlea": "跳蚤市场上架所需最低等级（db4 的 Lv 列同源）",
            "avg7daysPrice": (
                "仅当本地快照累积 ≥%d 个快照日后，由自有历史均值计算；上游本身不提供该字段"
                % HISTORY_AVG7_DAYS
            ),
            "fetchedAt": "本地采集时刻",
        },
        "notAvailable": [
            "avg7daysPrice（上游无该字段；本地快照 ≥%d 个快照日后由历史计算，不估算/不插值）"
            % HISTORY_AVG7_DAYS,
            "实时挂单列表（上游该接口不返回挂单明细）",
        ],
        "counts": {
            "itemsUpstream": len(merged),
            "itemsWithPrice": len(items),
            "withLastLowPrice": with_low,
            "withUpdated": with_updated,
            "withMinLevel": with_level,
            "historyDays": len(anchors),
        },
        "items": items,
    }
    return payload, warnings


def generate(
    app_root: str | None = None,
    out_dir: str | None = None,
    modes: list[str] | None = None,
    now: datetime.datetime | None = None,
    max_age_hours: float = 12.0,
    allow_stale: bool = False,
) -> dict:
    """生成三模式内置快照，返回可打印的报告（不抛异常，失败写进 report）。"""
    app_root = price_collect.root_dir(app_root)
    out_dir = os.path.abspath(out_dir or DEFAULT_OUT)
    modes = modes or list(BUNDLED_FILES.keys())
    now = now or price_collect.local_now()

    payloads: dict[str, dict] = {}
    warnings: list[str] = []
    errors: list[str] = []
    ages: dict[str, float] = {}
    for mode in modes:
        payload, mode_warnings = build_mode_payload(app_root, mode, now)
        warnings.extend(mode_warnings)
        if not payload:
            errors.append("%s：无采集数据" % mode)
            continue
        try:
            dt = datetime.datetime.fromisoformat(str(payload["meta"]["generatedAt"]).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=now.tzinfo)
            ages[mode] = max(0.0, (now - dt).total_seconds() / 3600.0)
        except ValueError:
            ages[mode] = 0.0
        payloads[mode] = payload

    stale_modes = [mode for mode, age in ages.items() if max_age_hours > 0 and age > max_age_hours]
    if stale_modes and not allow_stale:
        errors.append("以下模式的数据超过 %.1f 小时，拒绝打包：%s（可用 --allow-stale 强制）"
                      % (max_age_hours, ", ".join(stale_modes)))

    written = {}
    if not errors:
        os.makedirs(out_dir, exist_ok=True)
        for mode, payload in payloads.items():
            path = os.path.join(out_dir, BUNDLED_FILES[mode])
            price_collect.write_json_atomic(path, payload)
            written[mode] = {
                "file": os.path.relpath(path, os.path.dirname(out_dir)).replace(os.sep, "/"),
                "items": len(payload["items"]),
                "generatedAt": payload["meta"]["generatedAt"],
                "ageHours": round(ages.get(mode, 0.0), 2),
                "historyDays": payload["meta"]["historyDays"],
                "avg7daysPriceReady": payload["meta"]["avg7daysPriceReady"],
                "bytes": os.path.getsize(path),
            }
    return {
        "ok": not errors,
        "appRoot": app_root,
        "outDir": out_dir,
        "modes": modes,
        "written": written,
        "warnings": warnings,
        "errors": errors,
        "agesHours": {mode: round(value, 2) for mode, value in ages.items()},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="从采集器数据生成随包内置的三模式行情快照")
    parser.add_argument("--root", help="采集器程序根目录（默认 %%LOCALAPPDATA%%\\EFTPrice）")
    parser.add_argument("--out-dir", default=DEFAULT_OUT, help="输出目录（默认仓库 data/）")
    parser.add_argument("--modes", default="regular,pve,pvps",
                        help="逗号分隔模式，默认三模式全量")
    parser.add_argument("--max-age-hours", type=float, default=12.0,
                        help="数据超过这么多小时拒绝打包（0 = 不检查），默认 12")
    parser.add_argument("--allow-stale", action="store_true", help="允许使用过期数据强制打包")
    args = parser.parse_args(argv)

    modes = [m.strip().lower() for m in args.modes.split(",") if m.strip()]
    try:
        modes = [price_collect_mode(m) for m in modes]
    except ValueError as exc:
        print("[fail] %s" % exc, file=sys.stderr)
        return 2

    report = generate(
        app_root=args.root, out_dir=args.out_dir, modes=modes,
        max_age_hours=args.max_age_hours, allow_stale=args.allow_stale,
    )
    print("采集器根目录：%s" % report["appRoot"])
    print("输出目录：%s" % report["outDir"])
    for mode, info in report["written"].items():
        print("  [%s] %s  items=%d  generatedAt=%s  age=%.2fh  historyDays=%d  avg7d=%s  %d KB"
              % (mode, info["file"], info["items"], info["generatedAt"], info["ageHours"],
                 info["historyDays"], "是" if info["avg7daysPriceReady"] else "否",
                 max(1, info["bytes"] // 1024)))
    for warning in report["warnings"]:
        print("[warn] %s" % warning, file=sys.stderr)
    for error in report["errors"]:
        print("[fail] %s" % error, file=sys.stderr)
    return 0 if report["ok"] else 1


def price_collect_mode(raw: str) -> str:
    if raw in BUNDLED_FILES:
        return raw
    if raw in ("pvp", "regular"):
        return "regular"
    if raw in ("pvp-season", "pvpseason", "season", "pvps"):
        return "pvps"
    if raw == "pve":
        return "pve"
    raise ValueError("未知模式：%r（可用 regular/pve/pvps）" % (raw,))


if __name__ == "__main__":
    raise SystemExit(main())
