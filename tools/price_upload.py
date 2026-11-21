# -*- coding: utf-8 -*-
"""R79 采集器 → ECS 每小时上传（仅标准库，不依赖本项目其它模块）。

职责：
- 从采集器落盘目录读取三种模式（regular/PvP、pve、pvps）的最新快照与日锚点；
- 精简后 gzip 压缩，`POST /v1/prices/ingest`（采集机专用 Bearer token）；
- 每小时最多一次（与 30 分钟本地采集解耦；失败保留 `pending` 状态，下轮重试）；
- 同一份数据重复上传会被跳过（内容哈希），不会产生重复记录；
- 上传失败只写 `upload-state.json`，**不抛异常、不影响本地采集与落盘**。

凭据文件（不进版本库、不写进代码）：
  <app_root>/upload.json
  {
    "schema": 1,
    "enabled": true,
    "url": "https://47.96.68.209:8443",
    "token": "<采集机专用 token>",
    "caFile": "D:\\\\...\\\\assets\\\\cloud-ca.pem",
    "proxy": "",
    "timeoutSec": 30,
    "maxAttempts": 3,
    "retrySleepSec": 2,
    "minIntervalSec": 1500
  }

状态文件：
  <app_root>/upload-state.json
"""
from __future__ import annotations

import datetime
import gzip
import hashlib
import json
import os
import socket
import ssl
import time
import urllib.error
import urllib.request
from typing import Any

CONFIG_NAME = "upload.json"
STATE_NAME = "upload-state.json"
DATA_DIRNAME = "collect"
INGEST_PATH = "/v1/prices/ingest"
MODES = ("regular", "pve", "pvps")
MODE_LABELS = {"regular": "PvP", "pve": "PvE", "pvps": "PvPS（赛季服）"}
AVG7_DAYS = 7
MAX_PRICE = 100_000_000
MAX_TEXT = 300

DEFAULT_CONFIG = {
    "schema": 1,
    "enabled": False,
    "url": "",
    "token": "",
    "caFile": "",
    "proxy": "",
    "timeoutSec": 30,
    "maxAttempts": 3,
    "retrySleepSec": 2,
    # R221：采集每 30 分钟一轮、上游也是每 30 分钟发一版，上传若仍按 3600 s 节流，
    # 就会「隔一轮才上传」，数据永远滞后 30–60 分钟。改成 1500 s（25 分钟）略小于
    # 采集周期，保证每轮采集都能把刚抓到的数据送上去，同时仍能挡住短时间内的重复上传。
    "minIntervalSec": 1500,
}


def config_path(app_root: str) -> str:
    return os.path.join(app_root, CONFIG_NAME)


def state_path(app_root: str) -> str:
    return os.path.join(app_root, STATE_NAME)


def _collect_root(app_root: str) -> str:
    return os.path.join(app_root, DATA_DIRNAME)


def _now_iso() -> str:
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def _parse_iso(value) -> datetime.datetime | None:
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


def _read_json(path: str) -> dict | None:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            doc = json.load(fh)
        return doc if isinstance(doc, dict) else None
    except (OSError, ValueError):
        return None


def _write_json(path: str, obj: dict) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(obj, fh, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _read_gz(path: str) -> dict | None:
    try:
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            doc = json.load(fh)
        return doc if isinstance(doc, dict) else None
    except (OSError, ValueError):
        return None


def load_config(app_root: str) -> dict | None:
    cfg = _read_json(config_path(app_root))
    if not isinstance(cfg, dict):
        return None
    merged = dict(DEFAULT_CONFIG)
    merged.update(cfg)
    return merged


def init_config(app_root: str, force: bool = False) -> dict:
    """写一份**默认关闭**的凭据模板；已存在时默认不覆盖。"""
    path = config_path(app_root)
    if os.path.exists(path) and not force:
        return {"ok": True, "created": False, "path": path}
    _write_json(path, dict(DEFAULT_CONFIG))
    return {"ok": True, "created": True, "path": path}


def load_state(app_root: str) -> dict:
    doc = _read_json(state_path(app_root))
    if not isinstance(doc, dict) or not isinstance(doc.get("modes"), dict):
        doc = {"schema": 1, "modes": {}}
    return doc


def _mode_state(state: dict, mode: str) -> dict:
    modes = state.setdefault("modes", {})
    entry = modes.get(mode)
    if not isinstance(entry, dict):
        entry = {}
        modes[mode] = entry
    return entry


def _valid_price(value) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not (0 < value < MAX_PRICE):
        return None
    return int(value) if float(value).is_integer() else value


def _day_dirs(path: str) -> list[str]:
    try:
        return sorted(
            name for name in os.listdir(path)
            if os.path.isdir(os.path.join(path, name)) and len(name) == 10
        )
    except OSError:
        return []


def _latest_snapshot(collect_root: str, mode: str) -> dict | None:
    base = os.path.join(collect_root, "snapshots", mode)
    for day in reversed(_day_dirs(base)):
        try:
            names = sorted(n for n in os.listdir(os.path.join(base, day)) if n.endswith(".json.gz"))
        except OSError:
            continue
        if names:
            doc = _read_gz(os.path.join(base, day, names[-1]))
            if doc:
                doc["snapshotAt"] = doc.get("snapshotAt") or "%sT%s" % (
                    day, names[-1][:2] + ":" + names[-1][2:4] + ":" + names[-1][4:6]
                )
                return doc
    return None


def _daily_anchors(collect_root: str, mode: str) -> list[dict]:
    base = os.path.join(collect_root, "daily", mode)
    try:
        names = sorted(n for n in os.listdir(base) if n.endswith(".json.gz"))
    except OSError:
        return []
    out = []
    for name in names:
        doc = _read_gz(os.path.join(base, name))
        if doc and isinstance(doc.get("items"), dict):
            doc["date"] = name[:-len(".json.gz")]
            out.append(doc)
    return out


def _compact(row: dict) -> dict:
    if not isinstance(row, dict):
        return {}
    out = {}
    for key in ("l", "a", "lo", "hi", "b"):
        value = _valid_price(row.get(key))
        if value is not None:
            out[key] = value
    if row.get("u"):
        out["u"] = str(row["u"])
    lv = row.get("lv")
    if isinstance(lv, int) and not isinstance(lv, bool) and 0 <= lv <= 60:
        out["lv"] = lv
    return out


def _market_row(row: dict) -> dict:
    """市场字段：价格口径 + 在售挂单 / 48h 涨跌（采集器 `mk` 块）。

    只上传快照里真实存在的字段；缺测不补 0。`o` 是在售挂单数，不是成交量。
    """
    if not isinstance(row, dict):
        return {}
    out = _compact(row)
    mk = row.get("mk") if isinstance(row.get("mk"), dict) else {}
    for key in ("o", "c", "d", "v"):
        value = mk.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        if value != value or value in (float("inf"), float("-inf")):
            continue
        if key == "o" and value < 0:
            continue
        out[key] = int(value) if float(value).is_integer() else value
    stamp = mk.get("s") or row.get("lastScan")
    if isinstance(stamp, str) and stamp.strip():
        out["s"] = stamp.strip()[:MAX_TEXT]
    return out


def build_mode_payload(app_root: str, mode: str) -> tuple[dict | None, str | None]:
    """精简后的上传载荷：prices + 日锚点 + 市场字段（在售挂单 / 48h 涨跌）。"""
    collect_root = _collect_root(app_root)
    snap = _latest_snapshot(collect_root, mode)
    anchors = _daily_anchors(collect_root, mode)
    if not snap and not anchors:
        return None, "no-data（采集器还没有 %s 的落盘数据）" % mode

    latest_anchor = anchors[-1] if anchors else {}
    items: dict[str, dict] = {}
    for item_id, row in (latest_anchor.get("items") or {}).items():
        compact = _compact(row)
        if compact:
            items[str(item_id)] = compact
    for item_id, row in ((snap or {}).get("items") or {}).items():
        compact = _compact(row)
        if not compact:
            continue
        tgt = items.setdefault(str(item_id), {})
        for key in ("l", "a", "u"):
            if key in compact:
                tgt[key] = compact[key]

    generated_at = (
        (snap or {}).get("snapshotAt")
        or latest_anchor.get("snapshotAt")
        or _now_iso()
    )

    # 服务端契约：prices 是「物品 → 单个价格」，daily 是「日期 → 当日均价」。
    prices: dict[str, object] = {}
    for item_id, compact in items.items():
        price = compact.get("l")
        if price is None:
            price = compact.get("a")
        if isinstance(price, (int, float)) and not isinstance(price, bool) and price > 0:
            prices[item_id] = int(price) if float(price).is_integer() else price
    if not prices:
        return None, "no-prices（%s 的最新快照与日锚点都没有可用价格）" % mode

    daily: dict[str, object] = {}
    for doc in anchors[-AVG7_DAYS:]:
        day = str(doc.get("date") or "").strip()
        if not day:
            continue
        values = []
        for row in (doc.get("items") or {}).values():
            compact = _compact(row)
            price = compact.get("l") if "l" in compact else compact.get("a")
            if isinstance(price, (int, float)) and not isinstance(price, bool) and price > 0:
                values.append(float(price))
        if values:
            daily[day] = round(sum(values) / len(values), 2)

    # 市场字段只取最新快照（日锚点没有 mk 块）。缺字段的物品就是没有数据，
    # 服务端按「无市场字段」处理，绝不补 0。
    market: dict[str, object] = {}
    for item_id, row in ((snap or {}).get("items") or {}).items():
        rec = _market_row(row)
        if rec:
            market[str(item_id)] = rec

    payload = {
        "schema": 1,
        "mode": mode,
        "generatedAt": generated_at,
        "prices": prices,
        "daily": daily,
        "market": market,
    }
    canonical = json.dumps(
        {"mode": mode, "generatedAt": generated_at, "prices": prices,
         "daily": daily, "market": market},
        ensure_ascii=False, separators=(",", ":"), sort_keys=True,
    )
    payload["contentHash"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return payload, None


def endpoint_of(cfg: dict) -> str | None:
    endpoint = str(cfg.get("endpoint") or "").strip()
    if endpoint:
        return endpoint
    url = str(cfg.get("url") or "").strip()
    if not url:
        return None
    base = url.rstrip("/")
    if base.endswith("/prices/ingest"):
        return base
    if base.endswith("/v1"):
        return base + "/prices/ingest"
    return base + INGEST_PATH


def _opener(cfg: dict, endpoint: str):
    proxy = str(cfg.get("proxy") or "").strip()
    if proxy:
        handlers = [urllib.request.ProxyHandler({"http": proxy, "https": proxy})]
    else:
        # 采集机直连 ECS；显式清空代理，避免系统代理把内网/直连请求拐走。
        handlers = [urllib.request.ProxyHandler({})]
    if endpoint.startswith("https://"):
        cafile = str(cfg.get("caFile") or "").strip()
        context = ssl.create_default_context(cafile=cafile if cafile and os.path.exists(cafile) else None)
        handlers.append(urllib.request.HTTPSHandler(context=context))
    return urllib.request.build_opener(*handlers)


def _response_text(raw: bytes) -> str:
    try:
        text = raw.decode("utf-8", "replace")
    except Exception:
        return ""
    try:
        doc = json.loads(text)
        if isinstance(doc, dict):
            error = doc.get("error")
            if isinstance(error, dict):
                return str(error.get("message") or error.get("code") or "")[:MAX_TEXT]
            return str(doc.get("message") or doc.get("detail") or "")[:MAX_TEXT]
    except ValueError:
        pass
    return text[:MAX_TEXT]


def _post_once(endpoint: str, token: str, blob: bytes, cfg: dict) -> tuple[bool, str, int | None]:
    body = gzip.compress(blob, compresslevel=6)
    req = urllib.request.Request(
        endpoint,
        data=body,
        method="POST",
        headers={
            # 服务端只认采集机专用头，不复用用户 Bearer。
            "X-Ingest-Token": token,
            "Content-Type": "application/json; charset=utf-8",
            "Content-Encoding": "gzip",
            "Accept": "application/json",
            "User-Agent": "EFTPriceCollector/upload",
        },
    )
    timeout = float(cfg.get("timeoutSec") or 30)
    try:
        with _opener(cfg, endpoint).open(req, timeout=timeout) as res:
            raw = res.read()
            status = int(getattr(res, "status", 200) or 200)
    except urllib.error.HTTPError as exc:
        raw = exc.read() if hasattr(exc, "read") else b""
        status = int(exc.code or 0)
        message = _response_text(raw)
        if status == 409:
            return True, "服务端已存在同一份数据（幂等跳过）", status
        return False, "HTTP %d：%s" % (status, message or "请求被拒绝"), status
    except (urllib.error.URLError, OSError, socket.timeout, ssl.SSLError) as exc:
        return False, "网络错误：%s" % str(exc)[:MAX_TEXT], None
    message = _response_text(raw)
    return True, message or "OK", status


def _upload_mode(app_root: str, mode: str, cfg: dict, state: dict, endpoint: str) -> dict:
    entry = _mode_state(state, mode)
    now = _now_iso()
    payload, error = build_mode_payload(app_root, mode)
    if payload is None:
        entry.update({
            "lastAttemptAt": now,
            "lastStatus": "no-data",
            "lastError": error,
            "pending": True,
        })
        _write_json(state_path(app_root), state)
        return {"mode": mode, "ok": False, "status": "no-data", "error": error}

    content_hash = payload["contentHash"]
    if entry.get("lastContentHash") == content_hash and entry.get("lastSuccessAt") and not entry.get("pending"):
        entry.update({"lastAttemptAt": now, "lastStatus": "identical"})
        _write_json(state_path(app_root), state)
        return {
            "mode": mode, "ok": True, "status": "identical",
            "generatedAt": payload["generatedAt"], "items": len(payload["prices"]),
        }

    token = str(cfg.get("token") or "")
    max_attempts = max(1, int(cfg.get("maxAttempts") or 1))
    sleep_base = max(0.0, float(cfg.get("retrySleepSec") or 0))
    blob = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    last_error = ""
    last_status = None
    for attempt in range(max_attempts):
        ok, message, status = _post_once(endpoint, token, blob, cfg)
        last_error, last_status = message, status
        if ok:
            entry.update({
                "lastAttemptAt": now,
                "lastSuccessAt": now,
                "lastContentHash": content_hash,
                "lastGeneratedAt": payload["generatedAt"],
                "lastStatus": "uploaded",
                "lastHttpStatus": status,
                "lastError": None,
                "pending": False,
                "items": len(payload["prices"]),
                "historyDays": len(payload["daily"]),
            })
            _write_json(state_path(app_root), state)
            return {
                "mode": mode, "ok": True, "status": "uploaded", "httpStatus": status,
                "generatedAt": payload["generatedAt"], "items": len(payload["prices"]),
                "message": message,
            }
        if attempt + 1 < max_attempts and sleep_base > 0:
            time.sleep(sleep_base * (attempt + 1))

    entry.update({
        "lastAttemptAt": now,
        "lastStatus": "failed",
        "lastHttpStatus": last_status,
        "lastError": last_error,
        "pending": True,
    })
    _write_json(state_path(app_root), state)
    return {"mode": mode, "ok": False, "status": "failed", "error": last_error, "httpStatus": last_status}


def _pending_modes(state: dict, modes: tuple[str, ...]) -> list[str]:
    return [mode for mode in modes if (_mode_state(state, mode) or {}).get("pending")]


def next_upload_at(app_root: str) -> str | None:
    state = load_state(app_root)
    cfg = load_config(app_root) or DEFAULT_CONFIG
    interval = float(cfg.get("minIntervalSec") or 0)
    times = []
    for mode in MODES:
        dt = _parse_iso((state.get("modes", {}).get(mode) or {}).get("lastSuccessAt"))
        if dt:
            times.append(dt)
    if not times or interval <= 0:
        return None
    return (max(times) + datetime.timedelta(seconds=interval)).isoformat(timespec="seconds")


def upload_all(
    app_root: str,
    modes: list[str] | tuple[str, ...] | None = None,
    *,
    force: bool = False,
    cfg: dict | None = None,
) -> dict:
    """上传指定模式。force 只绕过 minIntervalSec 节流；内容相同仍会跳过。"""
    modes = tuple(modes or MODES)
    cfg = cfg if isinstance(cfg, dict) else load_config(app_root)
    if not cfg or not cfg.get("enabled"):
        return {"ok": False, "skipped": True, "reason": "disabled", "configPath": config_path(app_root)}
    endpoint = endpoint_of(cfg)
    if not endpoint or not str(cfg.get("token") or "").strip():
        return {"ok": False, "skipped": True, "reason": "not-configured", "configPath": config_path(app_root)}

    state = load_state(app_root)
    pending = _pending_modes(state, modes)
    if not force and not pending:
        interval = float(cfg.get("minIntervalSec") or 0)
        success_times = [
            _parse_iso((state.get("modes", {}).get(mode) or {}).get("lastSuccessAt"))
            for mode in modes
        ]
        if interval > 0 and all(dt for dt in success_times):
            latest = max(success_times)
            age = (datetime.datetime.now().astimezone() - latest).total_seconds()
            if age < interval:
                return {
                    "ok": True, "skipped": True, "reason": "interval",
                    "nextUploadAt": (latest + datetime.timedelta(seconds=interval)).isoformat(timespec="seconds"),
                    "pending": pending,
                }

    results = []
    for mode in modes:
        results.append(_upload_mode(app_root, mode, cfg, state, endpoint))
    failed = [item for item in results if not item.get("ok")]
    return {
        "ok": not failed,
        "skipped": False,
        "endpoint": endpoint,
        "modes": {item["mode"]: item for item in results},
        "failed": [item["mode"] for item in failed],
        "pending": _pending_modes(state, modes),
        "statePath": state_path(app_root),
    }


def tick(app_root: str, *, force: bool = False) -> dict:
    """采集器每轮结束时调用：默认 25 分钟节流（略小于 30 分钟采集周期，保证每轮都传），
    failures 只记状态不抛异常。"""
    try:
        return upload_all(app_root, force=force)
    except Exception as exc:      # 上传失败绝不能影响本地采集与落盘
        return {"ok": False, "skipped": False, "exception": str(exc)[:MAX_TEXT]}


def status(app_root: str) -> dict:
    cfg = load_config(app_root) or {}
    state = load_state(app_root)
    endpoint = endpoint_of(cfg) if cfg else None
    pending = _pending_modes(state, MODES)
    return {
        "configPath": config_path(app_root),
        "configured": bool(endpoint and str(cfg.get("token") or "").strip()),
        "enabled": bool(cfg.get("enabled")),
        "endpoint": endpoint,
        "caFile": str(cfg.get("caFile") or "") or None,
        "pending": pending,
        "lastSuccessAt": max(
            [str((state.get("modes", {}).get(m) or {}).get("lastSuccessAt") or "")
             for m in MODES] or [""]
        ) or None,
        "nextUploadAt": next_upload_at(app_root),
        "modes": {
            mode: {
                "lastAttemptAt": (state.get("modes", {}).get(mode) or {}).get("lastAttemptAt"),
                "lastSuccessAt": (state.get("modes", {}).get(mode) or {}).get("lastSuccessAt"),
                "lastStatus": (state.get("modes", {}).get(mode) or {}).get("lastStatus"),
                "lastError": (state.get("modes", {}).get(mode) or {}).get("lastError"),
                "pending": bool((state.get("modes", {}).get(mode) or {}).get("pending")),
                "items": (state.get("modes", {}).get(mode) or {}).get("items"),
                "generatedAt": (state.get("modes", {}).get(mode) or {}).get("lastGeneratedAt"),
            }
            for mode in MODES
        },
        "statePath": state_path(app_root),
    }
