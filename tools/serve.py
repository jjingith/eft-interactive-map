#!/usr/bin/env python3
"""EFT 互动地图 · 本地服务（运行期，仅 Python 标准库）

职责：
- 用 ThreadingHTTPServer 托管项目根目录（index.html / style.css / app.js / data/ / assets/）；
- `GET /api/health` 供 launcher 自检（数据是否就绪、收录多少张图、实时定位/日志监控是否可用）；
- `GET /api/position` 返回最近一次解析到的玩家位置（截图目录不可用时降级为 available=false）；
- `GET /api/config` 返回启动器里设置的运行期配置（开关 + 目录）；
- `POST /api/prefs` 把页面里的界面偏好（图层开关 / 楼层开关 / 自动居中）写回配置文件；
- `GET /api/logstate` 返回日志跟随状态与已累积的战局 / 任务事件；
- `GET /sounds/<文件>` 提供启动器复制到软件目录的自定义提示音；
- `GET /events` 用 SSE 把变化推给页面：位置（无名帧）+ `config` / `state` / `raid` / `quest` / `shot` / `clean` 命名事件；
- 端口占用时给出明确报错，不静默失败；
- 独立运行时自动打开浏览器，`--no-browser` 可关闭。

不联网、不读游戏进程：位置与战局/任务数据来自两类**只读文件**——截图文件名里的坐标
（见 screenshot.py）与游戏日志（见 eftlog.py）。对文件系统的主动操作只有两项，都默认关闭、
需在启动器里显式开启：**自动截图**（`AutoShotter` / keyinput.py，用 SendInput 模拟按下游戏内截图键）
与**自动删除截图**（`ScreenshotPruner`，读过位置后清掉旧截图，只保留最新一张供定位）。
"""

from __future__ import annotations

import argparse
import errno
import hashlib
import html
import json
import mimetypes
import os
import datetime
import queue
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import cloud
import cloud_market
import config
import eftlog
import keyinput
import layoutcal
import live_prices
import market_overview
import ocr
import poi_shots
import presets
import price_cache
import price_history
import prices_source
import screenshot


VERSION = "0.2.9.3"
UPDATE_REPO_API = "https://api.github.com/repos/jjingith/eft-interactive-map/releases/latest"
_UPDATE_CACHE: dict[str, Any] = {"at": 0.0, "payload": None}
_UPDATE_CACHE_LOCK = threading.Lock()
_UPDATE_CACHE_TTL = 900.0


def update_check_payload() -> dict[str, Any]:
    """Fetch the latest stable GitHub release once per local server run."""
    now = time.monotonic()
    with _UPDATE_CACHE_LOCK:
        cached = _UPDATE_CACHE.get("payload")
        if cached is not None and now - float(_UPDATE_CACHE.get("at") or 0) < _UPDATE_CACHE_TTL:
            return dict(cached)
    payload: dict[str, Any] = {"ok": True, "available": False, "current_version": VERSION}
    try:
        request = urllib.request.Request(
            UPDATE_REPO_API,
            headers={"Accept": "application/vnd.github+json", "User-Agent": "EFTMap-Updater"},
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            release = json.loads(response.read(1024 * 1024).decode("utf-8"))
        tag = str(release.get("tag_name") or "").strip()
        version = tag[1:] if tag[:1].lower() == "v" else tag

        def parts(value: str) -> tuple[int, ...]:
            values = value.split(".")
            if not values or any(not piece.isdigit() for piece in values):
                return ()
            return tuple(int(piece) for piece in values)

        latest_parts, current_parts = parts(version), parts(VERSION)
        if latest_parts and current_parts:
            latest_parts += (0,) * max(0, len(current_parts) - len(latest_parts))
            current_parts += (0,) * max(0, len(latest_parts) - len(current_parts))
            payload.update({
                "available": latest_parts > current_parts,
                "latest_version": version,
                "tag": tag,
                "release_name": str(release.get("name") or tag),
                "release_url": str(release.get("html_url") or ""),
                "published_at": str(release.get("published_at") or ""),
                "notes": str(release.get("body") or "").strip(),
                "assets": [
                    {"name": str(asset.get("name") or "下载文件"),
                     "url": str(asset.get("browser_download_url") or ""),
                     "size": int(asset.get("size") or 0)}
                    for asset in (release.get("assets") or [])
                    if isinstance(asset, dict)
                    and str(asset.get("name") or "").lower().endswith((".zip", ".exe"))
                    and str(asset.get("browser_download_url") or "").startswith(
                        "https://github.com/jjingith/eft-interactive-map/releases/download/"
                    )
                ],
            })
    except Exception as exc:  # 更新检查失败不能影响离线主功能
        payload["error"] = str(exc)[:160]
    with _UPDATE_CACHE_LOCK:
        _UPDATE_CACHE.update({"at": now, "payload": payload})
    return dict(payload)


# ---------------------------------------------------------------- 游戏更新（官方补丁说明）
# 数据源为什么是 Steam 官方公告：EFT 上架 Steam 后，BSG 的补丁说明会同步发在
# Steam 公告里，而 Steam 有一个稳定的 JSON 接口（ISteamNews）。官网是 Cloudflare +
# HTML，解析脆弱且随时会变；这里只需要一个「能长期不坏」的源。
# 公告正文是 Steam BBCode（[h3]标题[/h3]、[list][*][p]…[/p][/*][/list]），
# 下面的 parse_steam_bbcode 把它拆成「分区 + 条目」，供页面按 改动/修复 分组显示。
GAME_NEWS_APPID = "3932890"
GAME_NEWS_URL = ("https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/"
                 "?appid=%s&count=60&maxlength=0&format=json" % GAME_NEWS_APPID)
GAME_NEWS_PAGE = "https://store.steampowered.com/news/app/%s/view/%%s" % GAME_NEWS_APPID
GAME_NEWS_HOME = "https://store.steampowered.com/news/app/%s" % GAME_NEWS_APPID
GAME_CHANGES_BUNDLED = os.path.join("data", "game-changes.json")
GAME_CHANGES_CACHE_DIR = "game-changes"
GAME_CHANGES_CACHE_NAME = "news.json"
GAME_CHANGES_TTL = 6 * 3600.0             # 超过 6 小时没刷新就在界面上提示「可能不是最新」
# R308：云端发布的补丁快照（GitHub 仓库里的 data/game-changes.json，由
# .github/workflows/update-game-changes.yml 每 6 小时自动更新并提交）。
# 老版本客户端不用重新打包，只要本机服务能访问 GitHub 就能拿到最新补丁说明；
# Steam 直连失败（被墙 / 抽风）时也走这里兜底。
GAME_CHANGES_REMOTE_URL = (
    "https://api.github.com/repos/jjingith/eft-interactive-map/contents/"
    "data/game-changes.json?ref=main")
_GAME_NEWS_REFRESH_LOCK = threading.Lock()

_PATCH_TITLE_RE = re.compile(r"^\s*patch\s+([0-9][0-9A-Za-z.\-]*)\s*$", re.I)
_BB_HEADER_RE = re.compile(r"\[h([1-6])\](.*?)\[/h\1\]", re.S | re.I)
_BB_INLINE_RE = re.compile(
    r"\[/?(?:b|i|u|s|code|quote|center|left|right"
    r"|dynamiclink[^\]]*|previewyoutube[^\]]*|video[^\]]*|sticker[^\]]*"
    r"|url(?:=[^\]]*)?|img[^\]]*)\]", re.I)


def _bb_text(value: str) -> str:
    """去掉行内 BBCode / HTML 实体，压掉多余空白。"""
    text = _BB_INLINE_RE.sub("", value or "")
    text = text.replace("[/*]", "").replace("[/p]", " ")
    text = html.unescape(text)
    return re.sub(r"[ \t\u00a0]+", " ", text).strip()


def parse_steam_bbcode(body: str) -> list[dict]:
    """Steam 公告 BBCode → `[{title, blocks:[{type,text}]}]`。

    type 只有两种：`bullet`（列表项，页面上加 ·）与 `para`（普通段落）。
    `[h1]~[h6]` 开新分区；没有标题的内容归到一个 title 为空的分区里。
    """
    text = str(body or "")
    # 图片与分隔线先整体丢掉：它们对「这版改了什么」没有信息量
    text = re.sub(r"\[img[^\]]*\].*?\[/img\]", " ", text, flags=re.S | re.I)
    text = re.sub(r"\[hr\]\s*\[/hr\]", "\n", text, flags=re.I)
    text = _BB_HEADER_RE.sub(lambda m: "\n\x01" + _bb_text(m.group(2)) + "\n", text)
    text = re.sub(r"\[\*\]", "\n\x02", text)
    text = re.sub(r"\[/?list\]", "\n", text, flags=re.I)
    text = re.sub(r"\[p\]", "", text, flags=re.I)
    text = re.sub(r"\[/p\]", "\n", text, flags=re.I)
    text = _BB_INLINE_RE.sub("", text).replace("[/*]", "")

    sections: list[dict] = []
    current: dict | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("\x01"):
            title = _bb_text(line[1:])
            current = {"title": title, "blocks": []}
            sections.append(current)
            continue
        kind = "bullet" if line.startswith("\x02") else "para"
        clean = _bb_text(line[1:] if kind == "bullet" else line)
        if not clean:
            continue
        if current is None:
            current = {"title": "", "blocks": []}
            sections.append(current)
        current["blocks"].append({"type": kind, "text": clean})
    return [section for section in sections if section["blocks"]]


def _version_kind(version: str) -> str:
    """版本号类型：x.y.0.0 大版本 / x.y.z.0 小版本 / 第 4 位非 0 是热修。"""
    parts = []
    for piece in str(version or "").split("."):
        parts.append(int(piece) if piece.isdigit() else 0)
    if len(parts) >= 4 and parts[3] > 0:
        return "热修"
    if len(parts) >= 3 and parts[2] > 0:
        return "小版本"
    return "大版本"


def _patch_entry(item: dict) -> dict | None:
    """一条 Steam 公告 → 一个版本条目；不是 `Patch x.y.z` 的公告返回 None。"""
    title = html.unescape(str(item.get("title") or "")).strip()
    match = _PATCH_TITLE_RE.match(title)
    if not match:
        return None
    version = match.group(1).rstrip(".")
    sections = parse_steam_bbcode(str(item.get("contents") or ""))
    if not sections:
        return None
    try:
        stamp = int(item.get("date") or 0)
    except (TypeError, ValueError):
        stamp = 0
    gid = str(item.get("gid") or "").strip()
    bullets = sum(1 for s in sections for b in s["blocks"] if b["type"] == "bullet")
    return {
        "id": "steam-" + (gid or version),
        "version": version,
        "kind": _version_kind(version),
        "title": title,
        "date": time.strftime("%Y-%m-%d", time.localtime(stamp)) if stamp else "",
        "timestamp": stamp,
        "url": (GAME_NEWS_PAGE % gid) if gid else GAME_NEWS_HOME,
        "sections": sections,
        "bullets": bullets,
    }


def fetch_game_changes(timeout: float = 12.0) -> list[dict]:
    """拉 Steam 官方公告并只保留补丁条目（按时间倒序）。"""
    request = urllib.request.Request(
        GAME_NEWS_URL, headers={"User-Agent": "EFTMap-GameChanges"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = json.loads(response.read(4 * 1024 * 1024).decode("utf-8"))
    items = ((data.get("appnews") or {}).get("newsitems") or [])
    entries: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        # 只认 BSG 自己在 Steam 发的公告；媒体转载（PlayGround.ru 等）不算官方补丁说明
        if str(item.get("feedname") or "") != "steam_community_announcements":
            continue
        entry = _patch_entry(item)
        if entry:
            entries.append(entry)
    entries.sort(key=lambda entry: entry["timestamp"], reverse=True)
    return entries


def game_changes_cache_path(config_dir: str) -> str:
    return os.path.join(config_dir, GAME_CHANGES_CACHE_DIR, GAME_CHANGES_CACHE_NAME)


def fetch_game_changes_remote(timeout: float = 8.0) -> list[dict]:
    """从 GitHub 仓库读取云端补丁快照（自动同步产物，免重新打包客户端）。

    走 GitHub contents API 的 raw 媒体类型，只拉一个 100KB 左右的 JSON；
    未登录限流 60 次/小时，而本机最多每 6 小时拉一次，余量充足。
    """
    request = urllib.request.Request(
        GAME_CHANGES_REMOTE_URL,
        headers={"Accept": "application/vnd.github.raw",
                 "User-Agent": "EFTMap-GameChanges"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = json.loads(response.read(4 * 1024 * 1024).decode("utf-8"))
    entries = data.get("entries") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        raise ValueError("云端快照格式不正确")
    cleaned = [
        entry for entry in entries
        if isinstance(entry, dict) and entry.get("version")
        and isinstance(entry.get("sections"), list) and entry["sections"]
    ]
    if not cleaned:
        raise ValueError("云端快照里没有补丁条目")
    return cleaned


def _read_game_changes_file(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _merge_game_changes(*groups: list[dict]) -> list[dict]:
    """按 id 合并多份数据（先出现的优先），再按时间倒序。"""
    merged: dict[str, dict] = {}
    for group in groups:
        for entry in group or []:
            if not isinstance(entry, dict):
                continue
            key = str(entry.get("id") or entry.get("version") or "")
            if not key or key in merged:
                continue
            if not isinstance(entry.get("sections"), list) or not entry["sections"]:
                continue
            merged[key] = entry
    return sorted(merged.values(), key=lambda e: int(e.get("timestamp") or 0), reverse=True)


def game_changes_payload(root: str, config_dir: str | None = None) -> dict:
    """页面读取用：内置快照 + 本地缓存合并，**不打网络**（离线可用、秒开）。"""
    bundled_path = os.path.join(root, GAME_CHANGES_BUNDLED)
    bundled = _read_game_changes_file(bundled_path)
    cache_path = game_changes_cache_path(config_dir) if config_dir else ""
    cached = _read_game_changes_file(cache_path) if cache_path else {}
    entries = _merge_game_changes(cached.get("entries") or [], bundled.get("entries") or [])
    age = None
    if cache_path:
        try:
            age = time.time() - os.path.getmtime(cache_path)
        except OSError:
            age = None
    return {
        "ok": True,
        "entries": entries,
        "count": len(entries),
        "source": {"name": "Steam 官方公告", "url": GAME_NEWS_HOME,
                   "note": "补丁说明为官方英文原文，分区标题已中文化"},
        "bundledAt": str(bundled.get("generated_at") or ""),
        "fetchedAt": str(cached.get("fetched_at") or ""),
        "from": "cache" if cached.get("entries") else "bundled",
        "stale": bool(age is not None and age > GAME_CHANGES_TTL),
    }


def refresh_game_changes(root: str, config_dir: str | None = None) -> dict:
    """抓最新补丁说明：先 Steam 官方公告，失败再读 GitHub 云端快照，最后原子写缓存。"""
    payload = game_changes_payload(root, config_dir)
    before = int(payload.get("count") or 0)
    if not _GAME_NEWS_REFRESH_LOCK.acquire(blocking=False):
        payload.update({"ok": False, "busy": True, "error": "正在获取中，请稍候"})
        return payload
    try:
        errors: list[str] = []
        entries: list[dict] = []
        origin = "network"
        try:
            entries = fetch_game_changes()
        except Exception as exc:  # noqa: BLE001 - 网络失败不能影响已内置的内容
            errors.append("官方公告：%s" % str(exc)[:120])
        if not entries:
            # R308：Steam 不通（被墙/抽风）或暂时抓不到条目时，读仓库里自动同步的
            # 云端快照——老客户端无需重新打包也能看到新版本补丁说明。
            try:
                entries = fetch_game_changes_remote()
                origin = "cloud"
            except Exception as exc:  # noqa: BLE001
                errors.append("云端快照：%s" % str(exc)[:120])
        if not entries:
            payload.update({"ok": False,
                            "error": "无法获取补丁说明（%s）" % "；".join(errors)})
            return payload
        if config_dir:
            path = game_changes_cache_path(config_dir)
            try:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                temp = path + ".tmp"
                with open(temp, "w", encoding="utf-8") as handle:
                    json.dump({"fetched_at": time.strftime("%Y-%m-%d %H:%M"),
                               "source": origin, "entries": entries},
                              handle, ensure_ascii=False)
                os.replace(temp, path)
            except OSError as exc:  # 缓存写不进去也要把本次结果返回给页面
                payload["warning"] = "缓存写入失败：%s" % exc
        merged = _merge_game_changes(entries, payload.get("entries") or [])
        payload.update({
            "ok": True,
            "entries": merged,
            "count": len(merged),
            "added": max(0, len(merged) - before),
            "fetchedAt": time.strftime("%Y-%m-%d %H:%M"),
            "from": origin,
            "stale": False,
        })
        return payload
    finally:
        _GAME_NEWS_REFRESH_LOCK.release()


APP_ID = "eft-interactive-map"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8787
DEFAULT_POLL = 1.0        # 截图目录轮询间隔（秒）
SSE_HEARTBEAT = 15.0      # SSE 心跳间隔（秒），防止连接被中间层掐掉
MAX_PREFS_BODY = 64 * 1024   # /api/prefs 请求体上限：界面偏好只有几 KB，超了直接拒
# 云同步每次最多 3 个键，单键服务端上限 256 KB；这里再留一点 JSON 壳的余量。
MAX_CLOUD_BODY = 3 * 256 * 1024 + 128 * 1024
# R238 截图识别：1080p PNG base64 约 8-12 MB，留足余量但设硬上限防滥用。
MAX_OCR_BODY = 24 * 1024 * 1024
# R238 冻结帧（QQ 式框选）：整屏 PNG 原始字节，4K 约 10-20 MB，上限 48 MB。
MAX_OCR_FRAME_BODY = 48 * 1024 * 1024
# 内存里只留**最近一帧**（宿主每次热键都重抓覆盖），10 分钟没人用就丢弃。
# R240：帧格式跟随宿主上报（BMP 免压缩编码，热键→可框选 <0.5s；PNG 兼容旧路径）。
_OCR_FRAME: dict[str, Any] = {"id": None, "bytes": None, "at": 0.0, "fmt": "png"}
_OCR_FRAME_TTL = 600.0

# R239 截图识别交接态：scan.html 识别完成后把框选区域与匹配结果 POST 上来，
# 宿主（tools/scan.py）轮询标题看到「完成」后 GET 走，改开原生透明浮窗。
# 单槽覆盖（只保留最近一次交接），无 TTL——宿主消费完就不再读。
_OCR_OVERLAY: dict[str, Any] = {"ts": 0.0, "region": None, "matches": []}

# 物品目录 / 匹配器缓存（items.json 按 mtime 失效；匹配器随目录重建）
_OCR_CATALOG: dict[str, Any] = {"mtime": None, "names": None,
                                "name_to_ids": None, "items": None}
_OCR_MATCHER: dict[str, Any] = {"key": None, "matcher": None}


# R237：OCR 短名表缓存（data/ocr-item-names.json，tools/build_ocr_names.py 生成）
_OCR_SHORTNAMES: dict[str, Any] = {"mtime": None, "shorts": None}


def _ocr_shortnames(root_dir: str) -> dict[str, str]:
    """id → 中文短名（游戏内显示名）。占位符 "<id> ShortName" 已在生成时过滤。"""
    path = os.path.join(root_dir, "data", "ocr-item-names.json")
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        mtime = None
    cache = _OCR_SHORTNAMES
    if cache["shorts"] is not None and cache["mtime"] == mtime:
        return cache["shorts"]
    shorts: dict[str, str] = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            doc = json.load(f)
        for iid, v in (doc.get("names") or {}).items():
            zh = v.get("zh") if isinstance(v, dict) else None
            if isinstance(zh, str) and zh.strip():
                shorts[iid] = zh.strip()
    except (OSError, ValueError):
        shorts = {}
    cache.update({"mtime": mtime, "shorts": shorts})
    return shorts


# R242：OCR 匹配的档位层级（去重时保留更高层级的匹配）
_OCR_TIER_RANK = {"精确": 4, "去空格": 3, "整串模糊": 1}


def _ocr_match_rank(m: dict) -> int:
    tier = str(m.get("tier") or "")
    for pre, r in _OCR_TIER_RANK.items():
        if tier.startswith(pre):
            return r
    return 2  # 模糊(n)


def _ocr_close(a: dict, b: dict) -> bool:
    """两个 OCR 行框近到视为同一物品。

    R243 修正：水平/垂直分开取阈值——同一物品名的多个片段是**同一行**被切碎
    （dx 可到 3×行高、dy≈0），而**相邻行**的间距也是约 3×行高，垂直用 3h 会把
    上下格的不同物品误合并（演示帧 80px 行距实测被误并）。垂直收到 1.2h。"""
    h = max(a.get("h") or 10, b.get("h") or 10)
    return (abs(a.get("x", 0) - b.get("x", 0)) < 3 * h
            and abs(a.get("y", 0) - b.get("y", 0)) < 1.2 * h)


def dedup_ocr_matches(matches: list) -> list:
    """同位置只留一个匹配（R242，实测驱动）：
    · 同 id 近距 = 同一物品名的多个 OCR 片段（'肾上'+'腺素'→肾上腺素×2）→ 留优；
    · 不同 id 近距 = 正确匹配与擦线误配共存（EXFIL 精确 vs EXPIE 整串模糊、
      LBCR vs SDSK）→ 按档位层级+分数留优；
    · 远距的同 id 物品（两块夹板）各自保留。"""
    out: list = []
    for m in sorted(matches, key=lambda x: (-x.get("ocrScore", 0), -_ocr_match_rank(x))):
        slot = None
        for j, other in enumerate(out):
            if _ocr_close(m, other):
                slot = j
                break
        if slot is None:
            out.append(m)
        elif ((_ocr_match_rank(m), m.get("ocrScore", 0))
              > (_ocr_match_rank(out[slot]), out[slot].get("ocrScore", 0))):
            out[slot] = m
    return sorted(out, key=lambda x: (x.get("y", 0), x.get("x", 0)))


def _ocr_catalog(root_dir: str):
    """items.json + ocr-item-names.json → (names, name_to_ids, items)。

    索引名单 = 全名（items.json n）+ 中文短名（游戏内显示名）；name_to_ids
    两种名字都能反查到 id。缓存键含两个数据源的变化标记，任一更新即重建。
    """
    path = os.path.join(root_dir, "data", "items.json")
    shorts = _ocr_shortnames(root_dir)
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        mtime = None
    cache = _OCR_CATALOG
    cache_key = (mtime, len(shorts))
    if cache["names"] is not None and cache["mtime"] == cache_key:
        return cache["names"], cache["name_to_ids"], cache["items"]
    items: dict[str, Any] = {}
    name_to_ids: dict[str, list[str]] = {}
    names: list[str] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            doc = json.load(f)
        for iid, rec in (doc.get("items") or {}).items():
            name = rec.get("n")
            if not name:
                continue
            name_to_ids.setdefault(name, []).append(iid)
            names.append(name)
        items = doc.get("items") or {}
    except (OSError, ValueError):
        items = {}
    # 中文短名（游戏内显示名）也进索引与反查表——OCR 读到的就是它们
    known = set(names)
    for iid, short in shorts.items():
        if not short:
            continue
        name_to_ids.setdefault(short, []).append(iid)
        if short not in known:
            known.add(short)
            names.append(short)
    cache.update({"mtime": cache_key, "names": names,
                  "name_to_ids": name_to_ids, "items": items})
    return names, name_to_ids, items


def _trader_sell_price(rec: dict):
    """R249：商人收购价（玩家把物品卖给商人拿到手的钱）。

    数据源与市场页「Sell to 卖给谁」**完全相同**：items.json 的 `sl` =
    `[[traderId, priceRUB], …]`，价格已由采集脚本换算成卢布，按降序排好，
    所以取第一条就是最高收购价（市场页也是默认只显示最高值）。
    没有 `sl` 时退回 `p.b`（基础价）并标 `approx=True`；两者都没有返回 None。

    返回 (价格 or None, 商人 id or None, 是否为基础价兜底)。
    """
    best = None
    for row in rec.get("sl") or []:
        if isinstance(row, (list, tuple)) and len(row) > 1:
            p = row[1]
            if isinstance(p, (int, float)) and not isinstance(p, bool) and p > 0:
                if best is None or p > best[0]:
                    best = (int(p), row[0])
    if best:
        return best[0], best[1], False
    p = (rec.get("p") or {}).get("b")
    if isinstance(p, (int, float)) and not isinstance(p, bool) and p > 0:
        return int(p), None, True
    return None, None, False


def _ocr_no_flea(rec: dict) -> bool:
    """是否被禁止在跳蚤市场挂单（与市场页 ts.noFlea 同一判据）。"""
    return ("noFlea" in (rec.get("ts") or [])
            or "flea" not in (rec.get("src") or []))


def _ocr_flea_price(rec: dict, snap_row: dict):
    """跳蚤价：实时快照优先（lastLowPrice / avg24hPrice），缺失回退目录 p.l / p.a
    （这些是目录里的跳蚤基线价，采集时写入）。返回 (base, last_low, avg24, fallback?)。"""
    row = snap_row or {}
    last_low = row.get("lastLowPrice") or row.get("l")
    avg24 = row.get("avg24hPrice") or row.get("a")
    base = last_low or avg24
    if base:
        return base, last_low, avg24, False
    p = (rec or {}).get("p") or {}
    fb = p.get("l") or p.get("a")
    if fb:
        # 目录基线价没有分口径，lastLow/avg24h 都填它，避免前端误判缺失
        return fb, fb, fb, True
    return None, None, None, False


def _trader_sell_offer(rec: dict):
    """商人售卖价（玩家从商人处购买的价，R258）：trade 列表里 k='buy' 的 RUB 报价，
    取最低（最便宜的买入渠道）。返回 (价, 商人id, 等级) 或 (None, None, None)。"""
    best = None
    for opt in (rec or {}).get("trade") or []:
        if not isinstance(opt, dict) or opt.get("k") != "buy":
            continue
        c = opt.get("c")
        if c and c != "RUB":
            continue
        pr = opt.get("p")
        if isinstance(pr, (int, float)) and not isinstance(pr, bool) and pr > 0:
            if best is None or pr < best[0]:
                best = (int(pr), opt.get("t"), opt.get("l"))
    return best or (None, None, None)


def _ocr_resolve_price(rec: dict, snap_row: dict, hist_row: dict, avg7_val):
    """R258：按三档优先级解析单件物品的展示价（见上方调用处注释）。返回 price dict。

    优先级：
      1) 跳蚤有售卖（src 含 flea 且非 noFlea）→ 跳蚤价（lastLow/avg24h/avg7d 分口径）；
      2) 跳蚤不卖但商人会卖（trade 含 k='buy'）→ 商人售卖价（玩家从商人处购买）；
      3) 都不卖 → 商人收购价（sl，玩家卖给商人，红购物车警示）。
    商人价没有历史行情窗口，w72/w30d 一律置空，绝不拿跳蚤均价冒充商人价。"""
    gw, gh = rec.get("gw"), rec.get("gh")
    slots = (gw * gh) if (isinstance(gw, int) and isinstance(gh, int)
                         and gw > 0 and gh > 0) else 1
    no_flea = _ocr_no_flea(rec)
    flea_base, last_low, avg24, flea_fallback = _ocr_flea_price(rec, snap_row)
    if (not no_flea) and flea_base:
        per_slot = flea_base / slots
        return {
            "lastLow": last_low, "avg24h": avg24, "avg7d": avg7_val,
            "w72": (hist_row or {}).get("w72"),
            "w30d": (hist_row or {}).get("w30d"),
            "base": flea_base, "perSlot": per_slot,
            "priceSource": "flea", "noFlea": no_flea,
            "fleaFallback": flea_fallback,
            "updated": (snap_row or {}).get("updated"),
        }
    # 跳蚤不卖 → 看商人是否售卖
    tsell, tsell_id, tsell_lvl = _trader_sell_offer(rec)
    if tsell:
        return {
            "lastLow": None, "avg24h": None, "avg7d": None,
            "w72": None, "w30d": None,
            "base": tsell, "perSlot": tsell / slots,
            "priceSource": "traderSell",
            "traderSell": tsell, "traderSellId": tsell_id,
            "traderSellLvl": tsell_lvl, "noFlea": True,
        }
    # 都不卖 → 商人收购价（玩家卖给商人）
    tbuy, tbuy_id, approx = _trader_sell_price(rec)
    return {
        "lastLow": None, "avg24h": None, "avg7d": None,
        "w72": None, "w30d": None,
        "base": tbuy, "perSlot": (tbuy / slots) if tbuy else None,
        "priceSource": "trader", "trader": tbuy, "traderId": tbuy_id,
        "noFlea": True, "traderApprox": approx,
    }


_OCR_PRICE_FIELDS = ("lastLow", "avg24h", "avg7d", "w72", "w30d",
                     "base", "perSlot", "trader", "traderSell", "unitPrice",
                     "manual")


def _ocr_scrub_prices(matches: list) -> None:
    """R19.81：未登录时抹掉所有价格。

    价格只能来自云端行情；未登录既不发云端请求，也不拿 items.json 里构建期
    写入的跳蚤基线（p.l / p.a）冒充行情，否则「截图识别」照常报价。
    物品名 / 档位 / 歧义徽记保留，前端价格列显示「—」。
    """
    for m in matches or []:
        price = m.get("price")
        if isinstance(price, dict):
            for field in _OCR_PRICE_FIELDS:
                if field in price:
                    price[field] = None
            price["priceSource"] = "flea"
            price["noFlea"] = bool(price.get("noFlea"))
            price["fleaFallback"] = False
            for cand in price.get("candidates") or []:
                cand["price"] = None
        for cand in m.get("candidates") or []:
            cand["price"] = None
            cand["perSlot"] = None


# R260：同名多 id 的「颜色/版本变体」识别（如弹匣 GEN M3 的黑/ FDE / 香蕉黄 / BB弹）。
# 游戏内显示名（ShortName）对同家族所有变体完全相同（都是「GEN M3」），OCR 无法区分；
# 而异色版在跳蚤上常贵好几倍，按「每格价最高」挑会误选成异色版（用户实反馈：普通版
# PvE ~4 万，却显示成 FDE 版 10 万）。变体名的共同特征：带括号后缀「(FDE)」「（香蕉黄）」。
_VARIANT_BRACKET_RE = re.compile(r"[\(（\[【][^\)）\]】]*[\)）\]】]")


def _ocr_name_is_variant(name) -> bool:
    """物品名是否带括号后缀（颜色/特殊版本标记）。"""
    return bool(_VARIANT_BRACKET_RE.search(str(name or "")))


def _ocr_prefer_base_variant(ids: list, catalog: dict) -> list:
    """同名多 id：若存在不带括号后缀的「普通版本」，优先只在普通版本里挑，
    避免异色/特殊版把价格拉高。全是变体（或单条）时原样返回。"""
    if len(ids) <= 1:
        return ids
    plain = [i for i in ids if not _ocr_name_is_variant((catalog.get(i) or {}).get("n"))]
    return plain if plain else ids


def _ocr_variant_rank(name: str, disp: str, price: dict, per_slot) -> tuple:
    """同名多 id 的挑选顺序：全名以显示名结尾 > 有真实行情 > 每格价高。

    R309（用户实测「文件包」）：两个同名物品里，一个跳蚤有真价（99,999），另一个
    跳蚤不卖、只剩 `p.b` 基础价兜底（167,469，traderApprox）。旧逻辑只比每格价，
    基础价更高就盖过真实跳蚤价，浮窗显示错的数、也拉不到历史曲线。基础价是估算，
    永远排在真实行情之后。
    """
    suffix = 1 if str(name).endswith(disp) else 0
    approx = bool((price or {}).get("traderApprox"))
    return (suffix, 0 if approx else 1, per_slot if per_slot is not None else -1)


def _ocr_name_collision(ids: list, catalog: dict, snap_items: dict,
                        hist: dict, snap: dict) -> list:
    """同一个游戏内显示名对应多个**不同物品**时的候选清单。

    背景（用户实测）：实验室白卡、蓝色记号钥匙卡、钥匙卡收纳盒的短名都是「钥匙卡」，
    截图只看得到「钥匙卡」三个字，OCR 无法区分；旧逻辑按「每格价最高」直接挑一个，
    于是白卡被显示成收纳盒的价格。这里把候选**按全名折叠**后返回，长度 ≥2 即
    说明该显示名确实歧义，调用方据此打「?」徽记并把候选价目写进 tooltip。

    同一件物品重复录入（全名完全相同）折叠成一条，取每格价最高的那条作代表。
    """
    by_name: dict[str, dict] = {}
    for iid in ids:
        rec = catalog.get(iid) or {}
        name = rec.get("n") or iid
        avg7 = (snap.get("avg7d") or {}).get("values", {}).get(iid)
        price = _ocr_resolve_price(rec, snap_items.get(iid) or {},
                                   hist.get(iid) or {}, avg7)
        per_slot = price.get("perSlot")
        # 菜单里显示「整件价」；排序仍用每格价（同格数比才公平）
        main = price.get("lastLow")
        for field in ("traderSell", "trader", "base"):
            if main is None:
                main = price.get(field)
        # R303：候选补齐可切换所需的字段（前端点「?」后可改选这一项）。
        # detail 是完整价格对象，切换后直接顶替 match.price，三档价格/商人标记都不会错。
        cand = {"id": iid, "name": name,
                "price": main if main is not None else per_slot,
                "perSlot": per_slot, "kind": price.get("priceSource"),
                "short": ocr.short_name_of(name), "gw": rec.get("gw"), "gh": rec.get("gh"),
                "weight": rec.get("w"), "noFlea": bool(price.get("noFlea")),
                "detail": price}
        cur = by_name.get(name)
        if cur is None or (cand["perSlot"] or -1) > (cur["perSlot"] or -1):
            by_name[name] = cand
    return sorted(by_name.values(),
                  key=lambda c: -(c["perSlot"] if c["perSlot"] is not None else -1))


# ---------------------------------------------------------------- R250 弹药
#
# 游戏里「散装子弹」不能上跳蚤（只有弹药包能挂单），但 OCR 读到的短名（BS / BT /
# BP / M856A1 …）在索引里同时指向散装子弹和弹药包，旧逻辑按「每格价最高」挑，
# 于是散装子弹常被错配成弹药包的跳蚤价（80 发 BS 显示成 30 发装弹药包的价格）。
#
# 判据（用户提供 + 4K 游戏截图实测）：两种物品的数量都印在**同一格右下角**、
# 与右上角的名字右沿对齐、纵向相距约 0.76 个格子（4K：名字 y=42 / 数量 y=138）：
#   · 弹药包 → "25/25" "30/30" "120/120"（带斜杠）
#   · 散装弹 → "80" "21" "24"（不带斜杠）
# 有斜杠 → 按弹药包价；无斜杠 → 单发商人收购价 × 堆叠数量。

_AMMO_PACK_RE = re.compile(r"^(\d{1,4})\s*/\s*(\d{1,4})$")
_AMMO_STACK_RE = re.compile(r"^(\d{1,4})$")
_AMMO_PACK_SIZE_RE = re.compile(r"(\d+)\s*发\s*装")
# 口径：公制 "5.45x39"（别把 mm 吞进去，弹药包名带 mm、散装名带「毫米」）；
# 英制 ".338" ".300" ".45" ".357"（.338 AP 与 .300 AP 的短名都是 AP，游戏内
# 显示名完全相同，只能靠这个把候选口径分开）。「12/70」霰弹口径不带 x 也不带
# 前导点，匹配不到 → 返回空串，这类组（Poleva 12/70 vs 20/70）按歧义处理。
_AMMO_CALIBER_RE = re.compile(r"^\s*(\d+(?:\.\d+)?x\d+|\.\d+)", re.I)
_AMMO_COUNT_TR = str.maketrans({"O": "0", "o": "0", "l": "1", "I": "1",
                                "|": "1", "S": "5", "B": "8", "，": "", ",": ""})


def _ocr_ammo_kind(rec: dict) -> str | None:
    """弹药形态：'ammoBox' → 弹药包；仅 'ammo' → 散装子弹；其余 → None。

    items.json 里少数弹药包 ts 同时含 ammo 和 ammoBox，所以必须先判 ammoBox。"""
    ts = rec.get("ts") or []
    if "ammoBox" in ts:
        return "pack"
    if "ammo" in ts:
        return "loose"
    return None


def _ocr_caliber(name) -> str:
    m = _AMMO_CALIBER_RE.match(str(name or ""))
    return m.group(1).lower() if m else ""


def _ocr_pack_size(name) -> int | None:
    m = _AMMO_PACK_SIZE_RE.search(str(name or ""))
    return int(m.group(1)) if m else None


def _ocr_count_lines(lines) -> list:
    """从 OCR 原始行里挑数量行（带斜杠=弹药包 / 纯数字=散装堆叠）。

    只做 OCR 常见字形归一（O→0、l→1 …），且要求原文含数字或斜杠，避免把
    'BS' 这类纯字母物品名误判成数量。"""
    out = []
    for ln in lines or []:
        raw = str(ln.get("text") or "").strip()
        if not raw or not re.search(r"\d|/", raw):
            continue
        text = raw.replace(" ", "").translate(_AMMO_COUNT_TR)
        mp = _AMMO_PACK_RE.match(text)
        ms = None if mp else _AMMO_STACK_RE.match(text)
        if not (mp or ms):
            continue
        g = mp or ms
        qty = int(g.group(1))
        if not (0 < qty <= 999):
            continue
        pts = ln.get("points") or []
        if len(pts) < 3:
            continue
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        out.append({"y": min(ys), "right": max(xs), "left": min(xs),
                    "cx": (min(xs) + max(xs)) / 2.0,
                    "pack": bool(mp), "qty": qty, "text": raw})
    return out


def _ocr_ammo_count(match: dict, counts: list):
    """找装备名所在格子底部的数量行：右沿对齐、纵向不超过约一格半。

    R261：改为**先比水平对齐（同格右沿 dx）、再比纵向距离 dy**。原来只按 dy 最近
    挑，遇到同格附近有别的数字行（价格/耐久/邻格）时可能挑错或挑空；按 (dx, dy)
    排序后，只有「右沿几乎对齐本格」的数量行才会被认领，不会抢邻格的数字。"""
    right = (match.get("x") or 0) + (match.get("w") or 0)
    top = match.get("y") or 0
    h = max(8, match.get("h") or 16)
    best = None
    for c in counts:
        dy = c["y"] - top
        # R261：纵向窗口放宽到 14h——格子高、名字字框矮时 dy/h 会偏大，10h 会把
        # 同格的数量行挡在外面（实测散装弹 80 明明检出却没对上）。仍按 (dx,dy) 取最近，
        # 自己那行 dy 最小，不会去抢下一行。
        if not (1.0 * h <= dy <= 14.0 * h):
            continue
        dx = abs(c["right"] - right)
        if dx > 4.0 * h:
            continue
        key = (dx, dy)
        if best is None or key < best[0]:
            best = (key, c)
    return best[1] if best else None


def _ocr_prefer_pack(packs: list, catalog: dict, qty: int) -> list:
    """'30/30' → 优先 30 发装弹药包，'120/120' → 120 发装。"""
    sized = [i for i in packs
             if _ocr_pack_size((catalog.get(i) or {}).get("n")) == qty]
    return sized or packs


def _ocr_ambiguous(ids: list, catalog: dict) -> bool:
    """候选里是否仍含 >1 个口径 → 截图上根本无法区分，必须如实标注。"""
    return len({_ocr_caliber((catalog.get(i) or {}).get("n")) or "?"
                for i in ids}) > 1


def _ocr_ambig_candidates(ids: list, catalog: dict, snap_items: dict) -> list:
    """歧义候选价目表（市场页 / 浮窗选单用）：每个口径显示什么价一目了然。

    R258：与主浮窗同一套三档优先级解析（跳蚤价 → 商人售卖价 → 商人收购价），
    保证候选价与识别价一致。
    R309：不再截断到 6 条——FMJ 有 11 个口径，旧实现把 6.8x51 等后半段直接丢掉，
    表现为「选单里少了口径」。菜单自身会按屏幕缩小字号，11 条不会刷屏。
    """
    out = []
    for iid in ids:
        rec = catalog.get(iid) or {}
        row = snap_items.get(iid) or {}
        price = _ocr_resolve_price(rec, row, {}, None)
        src = price.get("priceSource")
        label = "flea" if src == "flea" else "trader"
        # R303：补 id / 短名 / 格数 / 完整价格，前端可点选切换口径。
        # R309：再补 unit（散装弹单发商人价）——宿主选中候选后要用它恢复「整堆价」。
        kind = _ocr_ammo_kind(rec) or ""
        unit = _trader_sell_price(rec)[0] if kind == "loose" else None
        out.append({"id": iid, "name": rec.get("n") or iid,
                    "short": ocr.short_name_of(rec.get("n") or ""),
                    "caliber": _ocr_caliber(rec.get("n")),
                    "kind": kind, "source": label,
                    "price": price.get("base"), "perSlot": price.get("perSlot"),
                    "gw": rec.get("gw"), "gh": rec.get("gh"),
                    "weight": rec.get("w"), "noFlea": bool(price.get("noFlea")),
                    "unit": unit, "detail": price})
    return out


def _ocr_ammo_decision(match: dict, lines: list, ids: list, catalog: dict,
                       counts: list | None = None):
    """→ (kind, qty, narrowed_ids, count_found, ambiguous)

    kind: "pack"（显示弹药包价）/ "loose"（单价×堆叠）/ None（非弹药，不干预）
    narrowed_ids 为空表示数据里没有该形态，调用方应退回原逻辑。
    `counts` 可由调用方预先算好（整张图只扫一次），省略时内部现算。
    ambiguous: 候选里仍有多个口径（.338 AP vs .300 AP、散装 BP 的三种口径…）。
    截图上只有短名 + 数量，这种歧义没法消除，只能全部列进选单让玩家核对。
    散装弹**不再按同短名弹药包的口径分布去猜**（R309 用户口径：宁可全部列出来）。
    """
    packs = [i for i in ids if _ocr_ammo_kind(catalog.get(i) or {}) == "pack"]
    loose = [i for i in ids if _ocr_ammo_kind(catalog.get(i) or {}) == "loose"]
    if not packs and not loose:
        return None, 0, [], False, False
    cnt = _ocr_ammo_count(match, counts if counts is not None else _ocr_count_lines(lines))
    if cnt and cnt["pack"] and packs:
        narrowed = _ocr_prefer_pack(packs, catalog, cnt["qty"])
        return ("pack", cnt["qty"], narrowed, True,
                _ocr_ambiguous(narrowed, catalog))
    if loose:
        qty = cnt["qty"] if (cnt and not cnt["pack"]) else 1
        return ("loose", qty, loose, bool(cnt and not cnt["pack"]),
                _ocr_ambiguous(loose, catalog))
    # 只有弹药包数据、又没读到 xx/xx：仍按弹药包显示，不臆造散装单价
    return "pack", 0, packs, False, _ocr_ambiguous(packs, catalog)


def _ocr_apply_ammo_stack(cand: dict, catalog: dict, qty: int, found: bool) -> bool:
    """散装弹：整体价 = 单发商人收购价 × 堆叠数量（写进 price，供浮窗/表格共用）。"""
    rec = catalog.get(cand.get("id")) or {}
    unit, trader_id, approx = _trader_sell_price(rec)
    if not unit:
        return False
    qty = max(1, int(qty or 1))
    total = unit * qty
    gw, gh = rec.get("gw"), rec.get("gh")
    slots = gw * gh if (isinstance(gw, int) and isinstance(gh, int)
                        and gw > 0 and gh > 0) else 1
    (cand["price"] or {}).update({
        "lastLow": None, "avg24h": None, "w72": None, "w30d": None,
        "base": total, "perSlot": total / slots,
        "priceSource": "trader", "trader": total,
        "traderId": trader_id, "traderApprox": approx,
        "noFlea": True, "ammoStack": True, "ammoPack": False,
        "unitPrice": unit, "qty": qty, "qtyFound": bool(found),
    })
    cand["ammoKind"] = "loose"
    cand["qty"] = qty
    return True


def _ocr_matcher(names):
    """ItemMatcher 进程级缓存（构建 0.2 s，不能每个请求重建）。"""
    key = (len(names), names[0] if names else "", names[-1] if names else "")
    cache = _OCR_MATCHER
    if cache["matcher"] is None or cache["key"] != key:
        cache["matcher"] = ocr.ItemMatcher(names)
        cache["key"] = key
    return cache["matcher"]
MAX_PRESET_BODY = 1024 * 1024   # /api/presets：单个方案很小，1MB 足够容纳导入整包
MAX_CALIB_BODY = 4 * 1024 * 1024   # /api/layout-calibration：整包导入，400 枪 × 400 槽位也够
# 页面顶部「构建标记」与启动器自检共用的资源清单（路径相对仓库根）
BUILD_ASSETS = ("index.html", "app.js", "style.css")
# 版本前缀只在这里写一次；/api/health 与 /api/build 共用（每轮升级只改这一行 + 前端）
# 注意：多处测试会用字面量 '"rev": "R19.xx-"' 检查同步，下面的 payload 必须保留字面量写法。


def build_digest(root: str) -> str:
    """站点指纹：三个入口文件的 size+mtime 摘要，换版本即变，用于本地缓存失效排查。"""
    h = hashlib.sha256()
    for rel in ("index.html", "app.js", "style.css"):
        try:
            st = os.stat(os.path.join(root, rel))
        except OSError:
            continue
        h.update(("%s:%d:%d" % (rel, st.st_size, int(st.st_mtime))).encode("utf-8"))
    return h.hexdigest()[:8]


def build_payload(root: str) -> dict:
    """`/api/build`：页面构建标记 + 启动器「端口是否本仓库」自检。

    返回 `root` 是刚需：启动器会把 `os.path.abspath(root)` 与自身目录比对，
    不一致就提示「端口被别的程序占用」。`assets` 给出入口文件的体积 / 修改时间 /
    内容摘要，便于排查「明明换了版本页面还是旧的」。
    """
    assets = []
    for rel in BUILD_ASSETS:
        path = os.path.join(root, rel)
        try:
            st = os.stat(path)
            with open(path, "rb") as fh:
                digest = hashlib.sha256(fh.read()).hexdigest()
        except OSError:
            continue
        assets.append({
            "file": rel,
            "size": st.st_size,
            "mtime": int(st.st_mtime),
            "sha256": digest,
        })
    return {
        "ok": True,
        "rev": "R19.97-" + build_digest(root),
        "root": os.path.abspath(root),
        "assets": assets,
    }

# 仓库根目录（tools/ 的上一级）
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Windows 的 WSAEADDRINUSE
_WSAEADDRINUSE = 10048

# 标准库在 Windows 上可能把 .svg/.json 猜错，这里显式纠正
EXTRA_TYPES = {
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".json": "application/json; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".ogg": "audio/ogg",
    ".opus": "audio/ogg",
    ".m4a": "audio/mp4",
    ".aac": "audio/aac",
    ".flac": "audio/flac",
}


class PortInUseError(RuntimeError):
    """端口已被占用（区别于其它 OSError，便于 launcher 给出可操作提示）。"""


def _is_addr_in_use(exc: OSError) -> bool:
    return exc.errno in (errno.EADDRINUSE, _WSAEADDRINUSE) or getattr(exc, "winerror", None) == _WSAEADDRINUSE


def data_status(root: str) -> dict[str, Any]:
    """读取 data/maps.json 汇报数据就绪情况（按 mtime 缓存，避免每次请求都解析）。"""
    path = os.path.join(root, "data", "maps.json")
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return {"ready": False, "maps": 0, "error": "缺少 data/maps.json"}

    cached = getattr(data_status, "_cache", None)
    if cached and cached[0] == path and cached[1] == mtime:
        return cached[2]

    try:
        with open(path, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
        maps = payload.get("maps") or []
        status = {"ready": bool(maps), "maps": len(maps), "error": None if maps else "data/maps.json 里没有任何地图"}
    except (OSError, ValueError) as exc:
        status = {"ready": False, "maps": 0, "error": "data/maps.json 无法解析：%s" % exc}

    data_status._cache = (path, mtime, status)  # type: ignore[attr-defined]
    return status


def default_screenshots_dir() -> str:
    """EFT 截图目录的默认位置：`<我的文档>\\Escape from Tarkov\\Screenshots`。"""
    try:
        import ctypes

        buf = ctypes.create_unicode_buffer(260)
        # CSIDL_PERSONAL = 5（我的文档）
        if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf) == 0 and buf.value:
            docs = buf.value
        else:
            raise OSError("SHGetFolderPathW 未返回路径")
    except (AttributeError, OSError, ValueError):
        docs = os.path.join(os.path.expanduser("~"), "Documents")
    return os.path.join(docs, "Escape from Tarkov", "Screenshots")


def _documents_dirs() -> list[str]:
    """可能的「我的文档」目录（R107 自动探测用）。

    OneDrive 接管文档 / 中文系统 / 多用户环境都可能让真实路径不在 `%USERPROFILE%\\Documents`，
    这里把系统 API 与常见替代位置都收进来，按优先级去重返回。
    """
    dirs: list[str] = []
    try:
        import ctypes

        buf = ctypes.create_unicode_buffer(260)
        # CSIDL_PERSONAL = 5（我的文档）
        if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf) == 0 and buf.value:
            dirs.append(buf.value)
    except (AttributeError, OSError, ValueError):
        pass

    home = os.path.expanduser("~")
    dirs.extend([
        os.path.join(home, "Documents"),
        os.path.join(home, "OneDrive", "Documents"),
        os.path.join(home, "OneDrive", "文档"),
        os.path.join(home, "文档"),
    ])
    seen: set[str] = set()
    out: list[str] = []
    for path in dirs:
        key = os.path.normcase(os.path.abspath(path))
        if key not in seen:
            seen.add(key)
            out.append(path)
    return out


def screenshot_dir_candidates(game_dir: str | None = None) -> list[str]:
    """可能存放 EFT 截图的目录，按优先级排列。

    游戏目录附近的 Screenshots → 我的文档（含 OneDrive 改道）→ 图片目录。
    只做浅层枚举，绝不递归遍历磁盘。
    """
    candidates: list[str] = []
    if game_dir:
        candidates.append(os.path.join(game_dir, "Screenshots"))
        parent = os.path.dirname(os.path.abspath(game_dir))
        if parent:
            candidates.append(os.path.join(parent, "Escape from Tarkov", "Screenshots"))
    candidates.append(default_screenshots_dir())
    for docs in _documents_dirs():
        candidates.append(os.path.join(docs, "Escape from Tarkov", "Screenshots"))
    home = os.path.expanduser("~")
    candidates.append(os.path.join(home, "Pictures", "Escape from Tarkov", "Screenshots"))

    seen: set[str] = set()
    out: list[str] = []
    for path in candidates:
        key = os.path.normcase(os.path.abspath(path))
        if key not in seen:
            seen.add(key)
            out.append(path)
    return out


def detect_screenshots_dir(game_dir: str | None = None) -> tuple[str | None, str | None]:
    """在候选目录里挑「最新截图最晚」的那个，返回 (目录, 说明)。

    没有任何可解析截图时，退回第一个存在的候选目录：刚装好的游戏可能还没拍过图，
    但目录本身有效，实时定位应当先开着等第一张截图。
    """
    best: str | None = None
    best_mtime: float | None = None
    fallback: str | None = None
    for path in screenshot_dir_candidates(game_dir):
        if not os.path.isdir(path):
            continue
        if fallback is None:
            fallback = path
        newest = screenshot.newest_mtime(path)
        if newest is None:
            continue
        if best is None or best_mtime is None or newest > best_mtime:
            best, best_mtime = path, newest
    if best is None:
        if fallback is not None:
            return fallback, "自动探测到截图目录：%s（还没有截图）" % fallback
        return None, "未找到可用的 EFT 截图目录（可在启动器里手动指定）"
    return best, "自动探测到截图目录：%s" % best


def pick_folder_dialog(current: str | None = None, title: str = "选择目录") -> str | None:
    """弹出系统文件夹选择框，返回用户选中的绝对路径；取消 / 失败返回 None。

    网页端 <input type=file webkitdirectory> 拿不到绝对路径（浏览器安全限制），
    所以目录类设置经由本机服务调用 Windows 原生对话框。服务端是用户自己启动的
    桌面程序，运行在交互会话里，能正常弹窗。
    R306：加 CREATE_NO_WINDOW——powershell 是控制台子系统程序，不加就会在
    点「浏览…」时闪一个控制台窗口。对话框本身是该进程里的 GUI 窗口，
    与控制台无关，实测加了这个标志对话框照常弹出（R306 有探针验证）。
    非 Windows / 无 GUI 环境直接返回 None，前端保留文本输入兜底。
    """
    if os.name != "nt":
        return None
    ps = (
        "Add-Type -AssemblyName System.Windows.Forms; "
        "$d = New-Object System.Windows.Forms.FolderBrowserDialog; "
        "$d.Description = $args[0]; "
        "$d.ShowNewFolderButton = $true; "
    )
    if current and os.path.isdir(current):
        # 用单引号字面量，路径里的单引号翻倍（PowerShell 转义）
        ps += "$d.SelectedPath = '%s'; " % current.replace("'", "''")
    ps += (
        "if ($d.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) "
        "{ Write-Output $d.SelectedPath }"
    )
    kwargs: dict = {"capture_output": True, "text": True, "timeout": 180}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps, title],
            **kwargs,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    out = (proc.stdout or "").strip()
    if out and os.path.isdir(out):
        return os.path.abspath(out)
    return None


def best_logs_dir(primary, alternatives) -> str | None:
    """返回当前应跟随的 Logs 目录。

    ``primary``（game_dir/Logs）优先，保持 LogFollower「目录存在就等日志出现」的
    原语义：目录还在但还没有会话时不该切走。仅当 ``alternatives`` 里存在明显
    更新（>1 天）的有效会话才切换——EFT 常把应用日志写在
    ``%LOCALAPPDATA%\\Temp\\Battlestate Games\\EFT\\Logs``，只认 primary 会一直
    跟随数周前的旧会话，战局阶段永远停在 end，自动截图因此永不触发（R285）。
    用会话目录 mtime 而非会话名比较，避免临时目录 / 调试产物干扰。
    """
    if not primary or not os.path.isdir(primary):
        return None
    try:
        base = eftlog.latest_session_with_channel(primary)
    except OSError:
        return primary
    if not base:
        return primary
    best, best_mtime = primary, os.path.getmtime(base)
    seen = {os.path.normcase(os.path.abspath(primary))}
    for logs in alternatives:
        key = os.path.normcase(os.path.abspath(logs))
        if key in seen:
            continue
        seen.add(key)
        try:
            session = eftlog.latest_session_with_channel(logs)
            if not session:
                continue
            mtime = os.path.getmtime(session)
        except OSError:
            continue
        if mtime > best_mtime + 86400.0:
            best, best_mtime = logs, mtime
    return best


def detect_logs_dir(game_dir: str | None = None) -> tuple[str | None, str | None]:
    """在候选位置里找「真的含 application 日志」的最新会话，返回 (Logs 目录, 说明)。"""
    candidates: list[str] = []
    if game_dir:
        candidates.append(os.path.join(game_dir, "Logs"))
    for docs in _documents_dirs():
        candidates.append(os.path.join(docs, "Escape from Tarkov", "Logs"))
    local = os.environ.get("LOCALAPPDATA")
    if local:
        candidates.append(os.path.join(local, "Temp", "Battlestate Games", "EFT", "Logs"))
    home = os.path.expanduser("~")
    candidates.append(os.path.join(home, "AppData", "Local", "Temp", "Battlestate Games", "EFT", "Logs"))

    seen: set[str] = set()
    for logs in candidates:
        key = os.path.normcase(os.path.abspath(logs))
        if key in seen:
            continue
        seen.add(key)
        session = eftlog.latest_session_with_channel(logs)
        if session:
            return logs, "自动探测到日志目录：%s（会话 %s）" % (logs, os.path.basename(session))
    return None, "未找到包含 application 日志的游戏会话目录（可在启动器里手动指定）"


# 游戏目录常见命名（用户实测目录为 `E:\EFT`，这里把裸名字与常见安装路径都覆盖）
GAME_DIR_NAMES = ("EFT", "Escape from Tarkov", "EscapeFromTarkov")
_GAME_EXES = ("EscapeFromTarkov.exe", "EscapeFromTarkov_BE.exe")


def _looks_like_game_dir(path: str) -> bool:
    """判定一个目录是不是 EFT 安装根：有 `Logs` 子目录，或装着游戏主程序。"""
    if not os.path.isdir(path):
        return False
    if os.path.isdir(os.path.join(path, "Logs")):
        return True
    return any(os.path.isfile(os.path.join(path, exe)) for exe in _GAME_EXES)


def is_network_path(path) -> bool:
    """是不是 UNC 网络路径（`\\\\server\\share`）。

    游戏装在另一台电脑上时，模拟按键物理上只能打到**本机**前台窗口，硬发键会把内容
    打进本机正在用的程序里，所以调用方必须先识别出来并停下。
    """
    if not isinstance(path, str) or not path:
        return False
    return path.replace("/", "\\").startswith("\\\\")


_NET_USE_RE = re.compile(r"\\\\([^\\\s]+)\\")


def parse_net_use(text) -> list[str]:
    """从 `net use` 输出里抽出网络主机根（`\\\\HOST`），按出现顺序去重。

    输出里既有带盘符的映射（`Z:  \\\\JJPC\\eft`），也有无盘符的「记住的共享」，
    两种都认；`None` / 空串返回空列表。
    """
    if not text:
        return []
    roots: list[str] = []
    for host in _NET_USE_RE.findall(text):
        root = "\\\\" + host
        if root not in roots:
            roots.append(root)
    return roots


def _network_roots() -> list[str]:
    """跑一次 `net use` 取已连接 / 记住的网络主机；命令不存在或无输出都返回空列表。"""
    try:
        proc = subprocess.run(["net", "use"], capture_output=True, text=True,
                              timeout=5, errors="ignore")
    except (OSError, ValueError, subprocess.SubprocessError):
        return []
    return parse_net_use(proc.stdout or "")


def default_game_dir() -> str | None:
    """自动定位 EFT 游戏目录（找不到返回 None，由用户在启动器里手填）。

    依次尝试：环境变量 `EFT_GAME_DIR` → 常见盘符下的裸目录名 → 常见安装路径 →
    `net use` 里记录的网络共享。只做**浅层**存在性判断，不递归遍历整盘，避免启动卡顿。
    """
    env = os.environ.get("EFT_GAME_DIR")
    if env and _looks_like_game_dir(env):
        return env

    candidates: list[str] = []
    for drive in "CDEFGHIJK":
        root = "%s:\\" % drive
        if not os.path.isdir(root):
            continue
        for name in GAME_DIR_NAMES:
            candidates.append(os.path.join(root, name))
        candidates.extend([
            os.path.join(root, "Battlestate Games", "EFT"),
            os.path.join(root, "Battlestate Games", "Escape from Tarkov"),
            os.path.join(root, "Games", "EFT"),
            os.path.join(root, "Program Files", "Battlestate Games", "EFT"),
            os.path.join(root, "Program Files (x86)", "Steam", "steamapps", "common", "Escape from Tarkov"),
        ])
    for path in candidates:
        if _looks_like_game_dir(path):
            return path

    for root in _network_roots():
        for name in GAME_DIR_NAMES:
            path = os.path.join(root, name)
            if _looks_like_game_dir(path):
                return path
    return None


class PathResolver:
    """截图 / 日志目录的「手动优先、自动兜底」解析器。

    手动值来自配置文件（页面或启动器写入），只有目录真实存在才采信；否则走自动探测。
    探测结果不回写配置——自动值只是本次运行的兜底，用户确认过才落盘。
    """

    def __init__(self, app_dir: str, game_dir: str | None = None):
        self.app_dir = app_dir
        self.game_dir = game_dir

    def _manual(self, key: str) -> str | None:
        value = (config.load(self.app_dir) or {}).get(key)
        if isinstance(value, str) and value and os.path.isdir(value):
            return value
        return None

    def screenshots_dir(self) -> str | None:
        manual = self._manual("screenshots_dir")
        if manual:
            return manual
        found, _note = detect_screenshots_dir(self.game_dir)
        return found

    def logs_dir(self) -> str | None:
        manual = self._manual("log_dir")
        if manual:
            return manual
        found, _note = detect_logs_dir(self.game_dir)
        return found

    def snapshot(self) -> dict[str, Any]:
        """当前解析结果 + 两个「是否手动值」标记（启动器界面据此展示来源）。"""
        manual_shots = self._manual("screenshots_dir")
        manual_logs = self._manual("log_dir")
        return {
            "screenshots": manual_shots or self.screenshots_dir(),
            "logs": manual_logs or self.logs_dir(),
            "screenshotsManual": manual_shots is not None,
            "logManual": manual_logs is not None,
        }


class Broadcaster:
    """SSE 订阅者注册表：把新位置与命名事件推给所有在线页面。

    队列里放的要么是位置帧（裸 dict），要么是 `(事件名, 负载)` 元组；
    每个订阅者一个 Queue，避免在请求线程里做网络写；广播失败/客户端断开只影响自己。
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._subs: set[queue.Queue] = set()

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=64)
        with self._lock:
            self._subs.add(q)
        return q

    def unsubscribe(self, q: queue.Queue):
        with self._lock:
            self._subs.discard(q)

    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subs)

    def publish(self, payload: dict):
        self._put(payload)

    def publish_event(self, name: str, payload: dict):
        """推一个 SSE 命名事件（`event: <name>`），前端用 addEventListener 各自订阅。"""
        self._put((name, payload))

    def _put(self, item):
        with self._lock:
            subs = list(self._subs)
        for q in subs:
            try:
                q.put_nowait(item)
            except queue.Full:      # 页面跟不上就先丢掉这一帧，不阻塞监听线程
                pass


class PositionTracker:
    """后台线程轮询截图目录；只有拿到的位置**真的变了**才广播。

    降级行为：目录不存在 / 读不了 / 一张都解析不出来 → available=false 并给出原因，
    地图其余功能不受影响（不抛异常、不停服务）。

    R108 会员门控：非会员两次位置刷新至少间隔 `SHOT_INTERVAL_LOCKED_MS`（10 秒），
    锁定期内直接不扫描、不广播；会员（或 `force=True`，用于进战局时丢掉上一局坐标）
    不受这个限制。会员态通过可调用对象读取，配置变化后无需重建 tracker。
    """

    LOCK_SECONDS = config.SHOT_INTERVAL_LOCKED_MS / 1000.0

    def __init__(self, directory: str | None, poll_interval: float = DEFAULT_POLL,
                 broadcaster: Broadcaster | None = None, member=None,
                 clock=time.monotonic):
        self.directory = directory
        self.poll_interval = poll_interval
        self.broadcaster = broadcaster or Broadcaster()
        if member is None:
            self.member = lambda: True
        elif callable(member):
            self.member = member
        else:
            self.member = lambda: bool(member)
        self.clock = clock
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._latest: dict[str, Any] | None = None
        self._reason: str | None = None
        self._last_accept: float | None = None

    # ------------------------------------------------------------ 状态
    def enabled(self) -> bool:
        return bool(self.directory)

    def snapshot(self) -> dict[str, Any]:
        """当前定位状态（`/api/position` 用；也是 SSE 每帧的内容）。"""
        with self._lock:
            latest, reason = self._latest, self._reason
        if not self.enabled():
            return {"available": False, "reason": "未配置截图目录（启动器加 --screenshots 可开启实时定位）",
                    "position": None}
        if latest is None:
            return {"available": False, "reason": reason or "截图目录里还没有可解析的截图", "position": None}
        pos = {k: latest[k] for k in ("x", "y", "z", "yaw")}
        pos["name"] = latest["name"]
        pos["mtime"] = latest["mtime"]
        return {"available": True, "reason": None, "position": pos, "directory": self.directory}

    # ------------------------------------------------------------ 轮询
    def poll_once(self, force: bool = False) -> bool:
        """扫一次目录；位置有变化返回 True（并广播）。

        非会员在锁定期内直接返回 False——既不扫描也不广播，避免「攒了几张一起补发」。
        """
        if not self.enabled():
            return False
        now = self.clock()
        if not force and not self.member():
            with self._lock:
                last = self._last_accept
            if last is not None and now - last < self.LOCK_SECONDS:
                return False
        with self._lock:
            self._last_accept = now

        if not os.path.isdir(self.directory):
            with self._lock:
                changed = self._latest is not None
                self._latest = None
                self._reason = "截图目录不存在：%s" % self.directory
            if changed:
                self.broadcaster.publish(self.snapshot())
            return changed

        found = screenshot.latest_position(self.directory)
        prev = None
        with self._lock:
            if found is None:
                self._reason = "截图目录里还没有可解析的截图"
                changed = self._latest is not None
                self._latest = None
            else:
                self._reason = None
                prev = self._latest
                changed = prev is None or prev["name"] != found["name"] or prev["mtime"] != found["mtime"]
                self._latest = found
        if changed:
            self.broadcaster.publish(self.snapshot())
        return changed

    def start(self):
        if not self.enabled() or self._thread is not None:
            return
        self.poll_once()                       # 先给一帧，页面首屏就有位置
        self._thread = threading.Thread(target=self._loop, daemon=True, name="eft-position-watch")
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3)
            self._thread = None

    def _loop(self):
        while not self._stop.wait(self.poll_interval):
            try:
                self.poll_once()
            except Exception:       # 任何意外都不该让监听线程死掉
                continue


class ConfigWatcher:
    """盯着 `eftmap.config.json` 的 mtime：文件一变就把新配置推给页面。

    这样启动器里改开关（自动缩放 / 自动居中 / 声音提示）后，已经开着的页面会立刻生效，
    不需要重启服务或刷新浏览器。
    """

    def __init__(self, app_dir: str, poll_interval: float = DEFAULT_POLL,
                 broadcaster: Broadcaster | None = None):
        self.app_dir = app_dir
        self.poll_interval = poll_interval
        self.broadcaster = broadcaster or Broadcaster()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._mtime: float | None = None
        self._initialized = False

    def snapshot(self) -> dict[str, Any]:
        return config_payload(self.app_dir)

    def poll_once(self) -> bool:
        """配置 mtime 有变化就广播一次，返回是否变化。首次只记基线，不广播。"""
        path = config.config_path(self.app_dir)
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            mtime = None
        if not self._initialized:
            self._initialized = True
            self._mtime = mtime
            return False
        if mtime == self._mtime:
            return False
        self._mtime = mtime
        self.broadcaster.publish_event("config", self.snapshot())
        return True

    def start(self):
        if self._thread is not None:
            return
        self.poll_once()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="eft-config-watch")
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3)
            self._thread = None

    def _loop(self):
        while not self._stop.wait(self.poll_interval):
            try:
                self.poll_once()
            except Exception:
                continue


# 自动截图只对游戏主程序在前台时发送（模拟按键只能打到前台窗口）
GAME_PROCESS = "escapefromtarkov.exe"
# 通过 BattlEye 启动时前台窗口可能属于 `EscapeFromTarkov_BE.exe`（防作弊引导进程），
# 它和主程序是同一个游戏窗口。只认主程序名会让「自动截图」在 BE 启动下永远不触发。
GAME_PROCESS_ALSO = ("escapefromtarkov_be.exe",)


def is_game_process(name) -> bool:
    """前台进程名是否属于 EFT（主程序或 BattlEye 引导进程）。"""
    base = os.path.basename(str(name or "")).lower()
    return base == GAME_PROCESS or base in GAME_PROCESS_ALSO


class ShotManifest:
    """自动截图的清理清单：只记录「本工具发键后新出现」的文件。

    「手动截图永不自动删除」是硬承诺，所以清单必须是**加法记录**而不是按目录乱删：
    `AutoShotter` 只有确认某张图是本次发键后新出现的，才调用 `add()`；
    `RaidEndCleaner` 战局结束时只删清单里的文件。清单落盘在软件目录，重启后仍然有效。
    """

    FILENAME = "auto-screenshot-manifest.json"

    def __init__(self, app_dir: str):
        self.app_dir = app_dir
        self._lock = threading.Lock()
        self._paths = self._load()

    def _path(self) -> str:
        return os.path.join(self.app_dir, self.FILENAME)

    def _load(self) -> list[str]:
        try:
            with open(self._path(), "r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except (OSError, ValueError):
            return []
        if not isinstance(raw, list):
            return []
        return [os.path.abspath(str(p)) for p in raw if isinstance(p, str) and p]

    def _save(self):
        os.makedirs(self.app_dir, exist_ok=True)
        path = self._path()
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self._paths, fh, ensure_ascii=False, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)

    def add(self, path: str):
        """登记一张自动截图（绝对路径，重复登记幂等）。"""
        target = os.path.abspath(str(path))
        with self._lock:
            if target in self._paths:
                return
            self._paths.append(target)
            self._save()

    def discard(self, paths) -> None:
        """把已删除 / 已失效的路径移出清单。"""
        drop = {os.path.abspath(str(p)) for p in paths or []}
        with self._lock:
            remain = [p for p in self._paths if p not in drop]
            if len(remain) == len(self._paths):
                return
            self._paths = remain
            self._save()

    def list(self) -> list[str]:
        with self._lock:
            return list(self._paths)


class RaidEndCleaner:
    """战局结束清理：只删 `ShotManifest` 里登记过的自动截图。

    默认关闭（`auto_screenshot.cleanup_on_raid_end`），开启后才在 `phase == "end"` 时执行。
    清单里的文件已经不存在就不算删除，顺手从清单里摘掉；落单的手动截图永远不碰。
    """

    def __init__(self, app_dir: str, manifest: ShotManifest, directory: str | None = None):
        self.app_dir = app_dir
        self.manifest = manifest
        self.directory = directory

    def cleanup(self) -> dict[str, Any]:
        shot = (config.load(self.app_dir) or {}).get("auto_screenshot") or {}
        if not shot.get("cleanup_on_raid_end"):
            return {"deleted": 0, "reason": "未开启战局结束清理"}

        base = os.path.abspath(self.directory) if self.directory else None
        deleted: list[str] = []
        stale: list[str] = []
        for path in self.manifest.list():
            absolute = os.path.abspath(path)
            # 只处理截图目录里的文件：清单被手改 / 目录换了也不会误删别处的东西
            if base is not None and os.path.dirname(absolute) != base:
                continue
            if not os.path.exists(absolute):
                stale.append(absolute)
                continue
            try:
                os.remove(absolute)
            except OSError:
                continue
            deleted.append(absolute)
        self.manifest.discard(deleted + stale)
        return {"deleted": len(deleted), "files": [os.path.basename(p) for p in deleted]}

    def on_event(self, event: dict) -> None:
        """挂到 `LogFollower.on_event`：战局结束（end）时清理，其它事件忽略。"""
        if event.get("type") == "raid" and event.get("phase") == "end":
            self.cleanup()


class AutoShotter:
    """自动截图：在战局中按固定间隔向游戏窗口发送截图键（模拟按键）。

    四个门条件（**都**满足才发键）：

    1. 启动器里开了「自动截图」（读 `eftmap.config.json`）；
    2. 游戏目录不是 UNC 网络路径（跨机模拟按键物理上打不到对方窗口）；
    3. 日志显示当前在战局中（`phase == "start"`，来自 `LogFollower`）；
    4. 前台窗口的进程是 `EscapeFromTarkov.exe`（模拟按键只能打到前台窗口）。

    截图键优先用配置里填/同步到的 `auto_screenshot.key`，为空时回落到日志同步到的键
    （`LogFollower.screenshot_key()`，即游戏内 `MakeScreenshot` 绑定）。

    发键后会在 `GRACE` 秒窗口内校验截图目录是否真的多了文件：到货才算成功；
    连续两次没到货就自动改用虚拟键码注入。窗口内出现多张新图时整批放弃归属，
    因为无法区分哪张是用户手动拍的——宁可漏删，也不删手动截图。

    `sender` / `foreground` 可注入，便于单测时不必真的发按键。
    """

    TICK = 0.1     # 内部轮询步长（秒）：比最短间隔 200ms 更细，保证不丢拍
    GRACE = 1.2    # 发键后允许截图落盘的归属窗口（秒），与发送间隔无关

    def __init__(self, app_dir: str, follower: "eftlog.LogFollower | None" = None,
                 broadcaster: Broadcaster | None = None, sender=None, foreground=None,
                 tick: float = TICK, directory: str | None = None,
                 game_dir: str | None = None, clock=time.monotonic,
                 manifest: ShotManifest | None = None):
        self.app_dir = app_dir
        self.follower = follower
        self.broadcaster = broadcaster or Broadcaster()
        self.directory = directory
        self.game_dir = game_dir
        self.clock = clock
        self.manifest = manifest
        self.sender = sender or self._default_send
        self.foreground = foreground or keyinput.foreground_process_name
        self.tick = tick
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._sent = 0
        self._last_at = 0.0
        self._reason = "自动截图未开启"
        self._mode = keyinput.MODE_SCAN
        self._arrived: bool | None = None
        self._misses = 0
        self._pending: dict[str, Any] | None = None

    # ------------------------------------------------------------ 状态
    def settings(self) -> tuple[bool, int, str | None]:
        """读配置 → (是否开启, 间隔毫秒, 截图键)。键为空时回落到日志同步到的键。"""
        shot = (config.load(self.app_dir) or {}).get("auto_screenshot") or {}
        enabled = bool(shot.get("enabled"))
        interval = config.clamp_interval(shot.get("interval_ms"), config.is_member(self.app_dir))
        key = shot.get("key") or (self.follower.screenshot_key() if self.follower else None)
        return enabled, interval, key

    def phase(self) -> str | None:
        if self.follower is None:
            return None
        return (self.follower.snapshot().get("raid") or {}).get("phase")

    def snapshot(self) -> dict[str, Any]:
        enabled, interval, key = self.settings()
        with self._lock:
            sent, last, reason = self._sent, self._last_at, self._reason
            mode, arrived, misses = self._mode, self._arrived, self._misses
        return {
            "enabled": enabled,
            "intervalMs": interval,
            "key": key,
            "sent": sent,
            "lastSentAt": last or None,
            "available": bool(enabled and key),
            "reason": reason,
            "mode": mode,
            "arrived": arrived,
            "misses": misses,
        }

    def _set_reason(self, text: str | None):
        with self._lock:
            self._reason = text

    def _block(self, text: str):
        """记下被门条件拦住的原因；原因没变就不重复推（轮询很密，重复推会刷爆页面）。"""
        with self._lock:
            changed = self._reason != text
            self._reason = text
        if changed:
            self.broadcaster.publish_event("shot", self.snapshot())

    def _game_dir(self) -> str | None:
        """实际生效的游戏目录：注入值（命令行/自动探测）优先于配置文件。"""
        if self.game_dir is not None:
            return self.game_dir
        return (config.load(self.app_dir) or {}).get("game_dir")

    def _network_reason(self) -> str | None:
        path = self._game_dir()
        if is_network_path(path):
            return ("游戏目录在另一台电脑（%s）上，模拟按键无法跨机发送；"
                    "请在本机运行游戏，或改用本地截图目录" % path)
        return None

    def _default_send(self, key: str) -> tuple[bool, str]:
        """默认注入：按当前模式（scan / vk）调用 keyinput，模式可随到货校验自动切换。"""
        return keyinput.send_key(key, self._mode)

    def _file_snapshot(self) -> set[str] | None:
        """目录里当前所有图片的文件名；没有可用目录返回 None（不校验）。"""
        if not self.directory or not os.path.isdir(self.directory):
            return None
        names: set[str] = set()
        try:
            entries = os.scandir(self.directory)
        except OSError:
            return None
        try:
            for entry in entries:
                if entry.is_file() and os.path.splitext(entry.name)[1].lower() in screenshot.IMAGE_EXTS:
                    names.add(entry.name)
        except OSError:
            pass
        finally:
            entries.close()
        return names

    # ------------------------------------------------------------ 到货校验
    def _check_arrival(self, now: float) -> bool:
        """判定上一次发键是否真的产生了截图；返回状态是否变化。"""
        with self._lock:
            pending = self._pending
        if pending is None:
            return False
        if not self.directory or not os.path.isdir(self.directory):
            # 不知道 / 用不了截图目录时不下结论，绝不冤枉游戏
            with self._lock:
                self._pending = None
            return False

        current = self._file_snapshot() or set()
        new = sorted(n for n in current if n not in pending["baseline"])
        elapsed = now - pending["sentAt"]

        if not new:
            if elapsed < self.GRACE:
                return False
            with self._lock:
                self._pending = None
                self._arrived = False
                self._misses += 1
                if self._misses >= 2:
                    self._mode = keyinput.MODE_VK
                    self._reason = ("连续 %d 次没到货：已切换为虚拟键码注入"
                                    "（发送截图键后没有出现新截图）" % self._misses)
                else:
                    self._reason = "发送截图键后没有出现新截图（已等待 %.1f 秒）" % elapsed
            return True

        if elapsed > self.GRACE:
            # 超出归属窗口：可能是用户手动拍的，宁可漏删也不能记进清理清单
            with self._lock:
                self._pending = None
                self._arrived = False
                self._reason = ("发键后新截图超出 %.1f 秒归属窗口，放弃归属（不会写入清理清单）"
                                % self.GRACE)
            print("[auto-shot] 发键后新截图超出归属窗口（%.1f 秒），放弃归属：%s"
                  % (self.GRACE, "、".join(new)), file=sys.stderr)
            return True

        if len(new) != 1:
            with self._lock:
                self._pending = None
                self._arrived = False
                self._reason = ("发键后出现 %d 张新截图，无法区分来源，全部放弃（不会写入清理清单）"
                                % len(new))
            print("[auto-shot] 窗口内出现 %d 张新截图，无法区分来源，放弃归属：%s"
                  % (len(new), "、".join(new)), file=sys.stderr)
            return True

        path = os.path.join(self.directory, new[0])
        with self._lock:
            self._pending = None
            self._arrived = True
            self._misses = 0
            self._reason = None
        if self.manifest is not None:
            self.manifest.add(path)
        return True

    # ------------------------------------------------------------ 轮询
    def poll_once(self, now: float | None = None) -> bool:
        """跑一轮门检查；真的发了按键返回 True（并发 `shot` 事件）。"""
        now = self.clock() if now is None else now
        enabled, interval_ms, key = self.settings()
        if not enabled:
            self._block("自动截图未开启")
            return False
        if not key:
            self._block("未取得截图按键：请在启动器里从日志同步或手动填写")
            return False
        network = self._network_reason()
        if network:
            self._block(network)
            return False
        phase = self.phase()
        if phase != "start":
            reason = "不在战局中（当前阶段：%s）" % (phase or "无日志")
            # 区分「在菜单里没进战局」与「日志压根没读到」：后者才是自动截图永不触发的真因，
            # 直接把 follower 的原因摆到界面上，省得用户在截图设置里反复折腾。
            snap = self.follower.snapshot() if self.follower is not None else {}
            if not snap.get("available"):
                reason = "游戏日志未就绪，无法判断战局阶段：%s" % (
                    snap.get("reason") or "未找到日志目录或会话文件夹")
            self._block(reason)
            return False
        process = self.foreground()
        if not process:
            self._block("无法确认游戏窗口是否在前台")
            return False
        if not is_game_process(process):
            self._block("游戏窗口不在前台（当前前台：%s）" % os.path.basename(str(process)))
            return False

        if self._check_arrival(now):
            self.broadcaster.publish_event("shot", self.snapshot())

        with self._lock:
            last = self._last_at
        if now - last < interval_ms / 1000.0:
            return False
        return self._shoot(key, now)

    def shoot_once(self) -> dict[str, Any]:
        """「试拍一张」：不受自动截图开关、战局阶段、前台与间隔限制，只保留跨机拦截。"""
        network = self._network_reason()
        if network:
            self._block(network)
            return {"ok": False, "reason": network}
        _enabled, _interval, key = self.settings()
        if not key:
            reason = "未取得截图按键：请在启动器里从日志同步或手动填写"
            self._block(reason)
            return {"ok": False, "reason": reason}
        ok = self._shoot(key, self.clock())
        if not ok:
            return {"ok": False, "reason": self.snapshot()["reason"], "key": key}
        return {"ok": True, "key": key, "verifying": self._pending is not None}

    def _shoot(self, key: str, now: float) -> bool:
        baseline = self._file_snapshot()
        ok, error = self._send(key)
        with self._lock:
            self._last_at = now
            if ok:
                self._sent += 1
            else:
                self._reason = error or "发送按键失败"
        if not ok:
            self.broadcaster.publish_event("shot", self.snapshot())
            return False

        with self._lock:
            # 「没到货」的提示不能被下一拍的成功发送立刻清掉，否则用户根本看不到
            if self._arrived is not False:
                self._reason = None
        # 基线为 None（没目录 / 目录不存在）时不校验，arrived 保持 None
        self._pending = {"sentAt": now, "baseline": baseline} if baseline is not None else None
        self.broadcaster.publish_event("shot", self.snapshot())
        return True

    def _send(self, key: str) -> tuple[bool, str]:
        try:
            result = self.sender(key)
        except Exception as exc:       # 注入实现抛异常也不能让线程死掉
            return False, "发送按键出错：%s" % exc
        if isinstance(result, tuple):
            return bool(result[0]), (result[1] if len(result) > 1 else "")
        return bool(result), ""

    # ------------------------------------------------------------ 线程
    def start(self):
        if self._thread is not None:
            return
        self.poll_once()               # 先跑一轮，页面首屏就有状态
        self._thread = threading.Thread(target=self._loop, daemon=True, name="eft-auto-shot")
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3)
            self._thread = None

    def _loop(self):
        while not self._stop.wait(self.tick):
            try:
                self.poll_once()
            except Exception:
                continue


class ScreenshotPruner:
    """自动删除截图：**位置读到手之后**，把多余的旧截图删掉，给截图目录止血。

    与「自动截图」配套使用效果最好（一个负责拍、一个负责清），但**彼此独立**：
    单独打开也能用（手动拍的截图，读过位置后同样会被清掉）。

    安全性三条：

    1. **只留最新 1 张**（`KEEP_NEWEST`）——实时定位就靠它，删了会没位置；
    2. **只删开关打开之后产生的**（配置里的 `auto_delete.since` 作时间闸），
       历史截图、以及开关关闭期间攒下的截图一律不动；
    3. **只删能解析出位置的截图**（见 `screenshot.select_deletable`），
       读不到位置的杂图不碰；删不掉（被占用等）就跳过，不抛异常。

    `since` 为空时会**先「布防」再删**：把 `since` 写成当前时刻并落盘，这一轮不删任何东西，
    避免手改配置或首次开启时一把清空整个目录。`prune` 可注入，便于单测不真删文件。
    """

    KEEP_NEWEST = 1

    def __init__(self, directory: str | None, app_dir: str,
                 broadcaster: Broadcaster | None = None, poll_interval: float = DEFAULT_POLL,
                 prune=None, clock=time.time):
        self.directory = directory
        self.app_dir = app_dir
        self.broadcaster = broadcaster or Broadcaster()
        self.poll_interval = poll_interval
        self.prune = prune or screenshot.prune
        self.clock = clock
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._deleted = 0
        self._last_at = 0.0
        self._reason = "自动删除未开启"

    # ------------------------------------------------------------ 状态
    def settings(self) -> tuple[bool, float | None]:
        """读配置 → (是否开启, 布防时刻)。"""
        delete = (config.load(self.app_dir) or {}).get("auto_delete") or {}
        return bool(delete.get("enabled")), delete.get("since")

    def snapshot(self) -> dict[str, Any]:
        enabled, since = self.settings()
        with self._lock:
            deleted, last, reason = self._deleted, self._last_at, self._reason
        return {
            "enabled": enabled,
            "since": since,
            "keepNewest": self.KEEP_NEWEST,
            "deleted": deleted,
            "lastDeletedAt": last or None,
            "available": bool(enabled and since and self.directory),
            "reason": reason,
        }

    def _set_reason(self, text: str):
        with self._lock:
            self._reason = text

    def _arm(self, now: float):
        """布防：把开启时刻落盘，作为「只删之后产生的截图」的时间闸。"""
        cfg = config.load(self.app_dir)
        cfg["auto_delete"]["enabled"] = True
        cfg["auto_delete"]["since"] = now
        config.save(cfg, self.app_dir)
        self._set_reason("已就绪：从现在起产生的截图才会被清理")

    # ------------------------------------------------------------ 轮询
    def poll_once(self, now: float | None = None) -> list[str]:
        """跑一轮；返回本轮删掉的文件名（空列表 = 这轮没删）。"""
        enabled, since = self.settings()
        if not enabled:
            self._set_reason("自动删除未开启")
            return []
        if not self.directory:
            self._set_reason("未配置截图目录（自动删除需要知道从哪儿清）")
            return []
        if since is None:
            self._arm(self.clock() if now is None else now)
            return []
        if not os.path.isdir(self.directory):
            self._set_reason("截图目录不存在：%s" % self.directory)
            return []

        deleted = self.prune(self.directory, since, self.KEEP_NEWEST)
        with self._lock:
            if deleted:
                self._deleted += len(deleted)
                self._last_at = time.time() if now is None else now
                self._reason = "已清理 %d 张（保留最新 %d 张供定位）" % (len(deleted), self.KEEP_NEWEST)
            else:
                self._reason = "暂无可清理的截图"
        if deleted:
            self.broadcaster.publish_event("clean", self.snapshot())
        return deleted

    # ------------------------------------------------------------ 线程
    def start(self):
        if self._thread is not None:
            return
        self.poll_once()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="eft-shot-prune")
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3)
            self._thread = None

    def _loop(self):
        while not self._stop.wait(self.poll_interval):
            try:
                self.poll_once()
            except Exception:
                continue


def _resolved_shot_key(cfg: dict) -> tuple[str, str]:
    """截图键：手动填写的值优先；没填时读游戏 Control.ini 的 MakeScreenshot 绑定。

    返回 (键名, 来源)。来源用于页面显示（manual / control.ini），读不到时返回空串。
    """
    shot = (cfg or {}).get("auto_screenshot") or {}
    manual = str(shot.get("key") or "").strip()
    if manual:
        return manual, "manual"
    try:
        detected = eftlog.read_screenshot_key_from_control_ini()
    except Exception:  # noqa: BLE001 - 读不到配置不能影响界面
        detected = None
    return (detected or "", "control.ini" if detected else "")


def config_payload(app_dir: str) -> dict[str, Any]:
    """`/api/config` 与 SSE `config` 事件共用的一份负载。"""
    cfg = config.load(app_dir)
    shot_key, shot_key_source = _resolved_shot_key(cfg)
    return {
        "config": cfg,
        "resolved": {
            "appDir": app_dir,
            "soundsDir": config.sounds_dir(app_dir),
            # R308：截图键没有启动器了，页面要知道当前生效的键与来源；
            # 手动值写 auto_screenshot.key，留空时由 Control.ini / 日志绑定兜底。
            "shotKey": shot_key,
            "shotKeySource": shot_key_source,
        },
    }


def _cloud_ca_path() -> str:
    """云证书路径：源码在仓库 assets/，PyInstaller onedir 在 _internal/assets/。

    打包后 `__file__` 是 `<exe目录>/_internal/serve.py`，ROOT 会算成 exe 目录，
    而 --add-data 的资源实际落在 `_internal`，所以这里按候选逐个找，
    避免冻结版直接抛 FileNotFoundError 让云端功能全废。
    """
    candidates = [os.path.join(ROOT, "assets", "cloud-ca.pem")]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(os.path.join(meipass, "assets", "cloud-ca.pem"))
    candidates.append(
        os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "_internal", "assets", "cloud-ca.pem")
    )
    for path in candidates:
        if os.path.isfile(path):
            return path
    return candidates[0]


def make_cloud_client(app_dir: str) -> "cloud.CloudClient":
    """云账号客户端：CA 随仓库发布（assets/cloud-ca.pem），证书固定只认这一份。"""
    return cloud.CloudClient(app_dir, _cloud_ca_path())


def _cloud_logged_in(cloud_client) -> bool:
    """是否已有可用的登录会话（token 过期由 CloudClient 自动刷新）。"""
    if cloud_client is None:
        return False
    try:
        return bool((cloud_client.session or {}).get("access_token"))
    except Exception:  # noqa: BLE001
        return False


def _free_price_cutoff(member: bool):
    """免费账号可见的数据上限（现在 − 12 小时）；会员返回 None。"""
    if member:
        return None
    return datetime.datetime.now().astimezone() - datetime.timedelta(
        seconds=cloud_market.FREE_DELAY_SECONDS
    )


# ---------------------------------------------------------------- 云端历史曲线（R278）
# 本机快照是「这个用户自己的采集器」，新装的机器一份都没有；云端那份是采集机
# 每 30 分钟上传的同一批数据。这里给 /api/price-history 补一个云端来源：
# 会员 → 直接问云端；非会员 / 离线 / 出错 → 一律静默回退本机，不弹错、不阻塞。
_CLOUD_SERIES_TTL = 300.0          # 5 分钟内同一个 (模式, 物品, 天数) 只问一次云端
_CLOUD_SERIES_MAX_ITEMS = 12       # 与云端 /v1/prices/series 的上限保持一致
_cloud_series_cache: dict[tuple, tuple[float, dict | None, str]] = {}
_cloud_series_lock = threading.Lock()


def _cloud_series(cloud_client, mode: str, ids: list[str], days: int) -> tuple[dict | None, str]:
    """带 TTL 缓存的云端曲线查询；任何失败都收敛成 (None, status)。"""
    if cloud_client is None or not ids:
        return None, "disabled"
    ids = ids[:_CLOUD_SERIES_MAX_ITEMS]
    key = (mode, tuple(ids), int(days))
    now = time.monotonic()
    with _cloud_series_lock:
        hit = _cloud_series_cache.get(key)
    if hit and now - hit[0] < _CLOUD_SERIES_TTL:
        return hit[1], hit[2]
    try:
        payload = cloud_client.prices_series(mode, ids, days)
        status = str(payload.get("status") or "ok")
    except cloud.CloudError as exc:
        if exc.status == 403 and exc.code == "membership_required":
            payload, status = None, "member_required"
        elif exc.status == 0:
            payload, status = None, "offline"
        elif exc.status == 404:
            payload, status = None, "no_data"
        else:
            payload, status = None, "error"
    except Exception:  # noqa: BLE001 - 云端异常不能影响本机曲线
        payload, status = None, "error"
    with _cloud_series_lock:
        if len(_cloud_series_cache) > 64:
            _cloud_series_cache.clear()
        _cloud_series_cache[key] = (time.monotonic(), payload, status)
    return payload, status


def _cloud_series_cached(app_dir: str, cloud_client, mode: str, ids: list[str],
                         days: int) -> tuple[dict | None, str]:
    """先读本地缓存，没有再用云端实时接口兜底。

    R279：登录会员后整包下载的缓存就躺在 `<app_dir>/cloud-cache/` 里，
    读它是本地文件操作（单物品 ~2 ms），比每次开图都打云端快一个数量级，
    也让「会员但暂时断网」照样能看曲线。缓存为空（刚登录还没同步完 /
    清过缓存）才回落到 `/v1/prices/series`。
    """
    try:
        cached = price_cache.series(app_dir, mode, ids, days)
    except Exception:  # noqa: BLE001 - 缓存坏了不能连累本机曲线
        cached = None
    if isinstance(cached, dict) and cached.get("status") == "ok":
        return cached, "cache"
    return _cloud_series(cloud_client, mode, ids, days)


# ---------------------------------------------------------------- 行情缓存（R20.5 / R42）

def _local_date() -> str:
    """本机本地日期（`YYYY-MM-DD`），用来判断 flea-prices.json 是不是今天的。"""
    return time.strftime("%Y-%m-%d")


def _read_json_file(path: str):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def flea_price_status(root: str) -> dict[str, Any]:
    """构建期跳蚤快照的状态：missing / stale / fresh，并带上上次抓取失败原因。

    只读本地文件，不联网；供 `/api/prices` 与页面状态行轮询使用。
    """
    data_dir = os.path.join(root, "data")
    path = os.path.join(data_dir, "flea-prices.json")
    payload = _read_json_file(path)
    out: dict[str, Any] = {
        "ok": True,
        "state": "missing",
        "items": 0,
        "path": path,
        "localDate": None,
        "lastSuccessAt": None,
        "source": None,
        "gameMode": None,
        "counts": None,
        "lastError": None,
    }
    error = _read_json_file(os.path.join(data_dir, "flea-prices.last-error.json"))
    if isinstance(error, dict):
        out["lastError"] = error.get("error")
    if isinstance(payload, dict) and isinstance(payload.get("items"), dict):
        out["items"] = len(payload["items"])
        out["localDate"] = payload.get("localDate")
        out["lastSuccessAt"] = payload.get("lastSuccessAt")
        out["source"] = payload.get("source")
        out["gameMode"] = payload.get("gameMode")
        out["counts"] = payload.get("counts")
        out["state"] = "fresh" if payload.get("localDate") == _local_date() else "stale"
    return out


_FLEA_REFRESH_LOCK = threading.Lock()
_FLEA_REFRESHING = False


def spawn_flea_refresh(root: str, force: bool = True) -> tuple[bool, str]:
    """后台跑一次 `tools/r20_fetch_prices.py`；返回 (是否已启动, 说明)。

    抓取器不存在 / 已在运行时不抛异常、也不起线程，只把原因交给调用方。
    """
    global _FLEA_REFRESHING

    root = os.path.abspath(root or ROOT)
    fetcher = os.path.join(root, "tools", "r20_fetch_prices.py")
    if not os.path.isfile(fetcher):
        return False, "抓取器不存在：%s" % fetcher
    with _FLEA_REFRESH_LOCK:
        if _FLEA_REFRESHING:
            return False, "已有行情抓取进行中"
        _FLEA_REFRESHING = True

    def run():
        global _FLEA_REFRESHING
        try:
            argv = [sys.executable, fetcher,
                    "--out", os.path.join(root, "data", "flea-prices.json"), "--no-proxy"]
            if force:
                argv.append("--force")
            subprocess.run(argv, cwd=root, timeout=300,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (OSError, subprocess.SubprocessError):
            pass
        finally:
            with _FLEA_REFRESH_LOCK:
                _FLEA_REFRESHING = False

    threading.Thread(target=run, daemon=True, name="eft-flea-refresh").start()
    return True, "已开始更新跳蚤行情"


_LIVE_FETCH_LOCK = threading.Lock()
_LIVE_FETCHING: set[str] = set()


def spawn_live_fetch(root: str, app_dir: str, mode: str, settings: dict | None = None) -> tuple[bool, str]:
    """后台抓取一个模式（regular=PvP / pve）的在线行情；返回 (是否已启动, 说明)。

    同一模式已有抓取在跑时直接跳过（去重），全部异常都收在后台线程里，
    旧缓存由 live_prices.fetch_mode 自己保证不被破坏。
    """
    try:
        mode = live_prices.normalize_mode(mode)
    except ValueError as exc:
        return False, str(exc)
    settings = settings or config.live_prices(app_dir)
    ttl = int(settings.get("ttlSec") or live_prices.DEFAULT_TTL)
    source = settings.get("source")

    with _LIVE_FETCH_LOCK:
        if mode in _LIVE_FETCHING:
            return False, "该模式已有抓取进行中（%s）" % mode
        _LIVE_FETCHING.add(mode)

    def run():
        try:
            proxy = live_prices.DEFAULT_PROXY
            reachable, _why = live_prices.proxy_reachable(proxy)
            live_prices.fetch_mode(mode, proxy=proxy if reachable else None,
                                   ttl_sec=ttl, force=True, source=source)
        except Exception:       # 后台抓取失败只写 attempt 记录，绝不影响服务
            pass
        finally:
            with _LIVE_FETCH_LOCK:
                _LIVE_FETCHING.discard(mode)

    threading.Thread(target=run, daemon=True, name="eft-live-prices-%s" % mode).start()
    return True, "已开始抓取 %s 行情" % mode


def build_handler(root: str, tracker: PositionTracker, follower: eftlog.LogFollower | None = None,
                  app_dir: str | None = None, shotter: AutoShotter | None = None,
                  pruner: ScreenshotPruner | None = None, cloud_client: "cloud.CloudClient | None" = None,
                  shutdown_token: str | None = None, shutdown_callback=None):
    """构造静态文件 Handler，并把 /api/ 前缀留给 JSON 接口、/sounds/ 留给自定义提示音。

    `shutdown_token` 是桌面壳写进 runtime JSON 的随机令牌：只有带对 `X-EFTMap-Token`
    才能调 `/api/shutdown`、`/api/live-prices/refresh`；网页刷新另走同源校验。
    """
    app_dir = app_dir or config.app_dir()
    cloud_client = cloud_client or make_cloud_client(app_dir)

    class Handler(SimpleHTTPRequestHandler):
        server_version = "EFTMap/%s" % VERSION
        protocol_version = "HTTP/1.1"
        extensions_map = dict(SimpleHTTPRequestHandler.extensions_map, **EXTRA_TYPES)

        def __init__(self, *args, **kwargs):
            self._cache_header_set = False     # 见 end_headers()
            super().__init__(*args, directory=root, **kwargs)

        # 本地单机服务，逐请求一行日志只是噪音
        def log_message(self, fmt, *args):  # noqa: A003 - 覆盖标准库签名
            pass

        def end_headers(self):  # noqa: N802 - 覆盖标准库签名
            """给静态文件也加上禁缓存头。

            标准库的 SimpleHTTPRequestHandler 不发 Cache-Control，浏览器于是按启发式
            规则缓存 app.js / data/maps.json，换了新版本仍旧拿旧文件——表现为「打包了
            新版却还是昨天的界面」。本地服务一律不缓存，改完刷新即生效。
            """
            if not self._cache_header_set:
                self.send_header("Cache-Control", "no-store, must-revalidate")
                self.send_header("Pragma", "no-cache")
                self._cache_header_set = True
            super().end_headers()

        def _send_cache_header(self):
            """接口自行声明过缓存策略时打个招呼，免得 end_headers() 再叠一层。"""
            self._cache_header_set = True

        def do_OPTIONS(self):  # noqa: N802 - 覆盖标准库签名
            """预检：只声明允许的方法，**不发**任何 Access-Control-Allow-* 头。

            本服务只给同源页面用；跨站网页即使拿到预检响应，浏览器也不会放行带
            自定义头的 POST。这是抵御跨站刷新行情 / 关闭服务的第一道门。
            """
            self.send_response(204)
            self.send_header("Allow", "GET, POST, OPTIONS")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_GET(self):  # noqa: N802 - 覆盖标准库签名
            raw_path, _, query = self.path.partition("?")
            path = raw_path.split("#", 1)[0]
            if path in ("/ui-showcase", "/ui-showcase/"):
                self.path = "/ui-showcase.html"
                return SimpleHTTPRequestHandler.do_GET(self)
            if path == "/api/health":
                return self._send_json(200, health_payload(root, tracker, follower, shotter, pruner))
            if path == "/api/update-check":
                return self._send_json(200, update_check_payload())
            if path == "/api/game-changes":
                # 只读本地（内置快照 + 缓存），不打网络：离线也能秒开
                return self._send_json(200, game_changes_payload(root, app_dir))
            if path == "/api/pick-folder":
                # 网页端「浏览…」：弹系统文件夹选择框拿绝对路径（浏览器自身做不到）。
                from urllib.parse import parse_qs
                qs = parse_qs(query)
                current = (qs.get("current") or [""])[0]
                title = (qs.get("title") or ["选择目录"])[0]
                picked = pick_folder_dialog(current or None, title)
                return self._send_json(200, {"ok": True, "path": picked})
            if path == "/api/presets":
                return self._handle_presets_get(query)
            if path == "/api/live-prices":
                return self._handle_live_prices_get(query)
            if path == "/api/live-prices/status":
                return self._handle_live_prices_status()
            if path == "/api/price-snapshot":
                return self._handle_price_snapshot(query)
            if path == "/api/price-history":
                return self._handle_price_history(query)
            if path == "/api/market-overview":
                return self._handle_market_overview(query)
            if path == "/api/market-offers":
                # R291 热卖榜：本机累积快照里的在售挂单数 / 24h 峰值（不联网、不扣配额）
                from urllib.parse import parse_qs
                qs = parse_qs(query)
                mode = (qs.get("mode") or ["regular"])[0]
                ids: list[str] = []
                for chunk in qs.get("itemIds") or []:
                    for part in str(chunk).split(","):
                        part = part.strip()
                        if part and part not in ids:
                            ids.append(part)
                if not ids:
                    return self._send_json(400, {"ok": False, "error": "no-itemIds"})
                try:
                    hours = max(1, min(24 * 90, int((qs.get("hours") or ["24"])[0])))
                except (TypeError, ValueError):
                    hours = 24
                return self._send_json(200, cloud_market.offers_history(app_dir, mode, ids[:64], hours))
            if path == "/api/market-history":
                return self._handle_market_history(query)
            if path == "/api/poi-shot":
                return self._handle_poi_shot_get(query)
            if path == "/api/poi-shots":
                return self._send_json(200, {"ok": True, "items": poi_shots.list_keys(app_dir),
                                             "maxBytes": poi_shots.MAX_BYTES})
            if path == "/api/ocr/frame":
                return self._handle_ocr_frame_get(query)
            if path == "/api/ocr/overlay/state":
                return self._handle_ocr_overlay_get()
            if path == "/api/prices":
                return self._send_json(200, flea_price_status(root))
            if path == "/api/position":
                return self._send_json(200, tracker.snapshot())
            if path == "/api/config":
                return self._send_json(200, config_payload(app_dir))
            if path == "/api/build":
                return self._send_json(200, build_payload(root))
            if path == "/api/layout-calibration":
                return self._handle_calibration_get()
            if path == "/api/cloud/status":
                return self._cloud_call(cloud_client.status)
            if path == "/api/cloud/login-preferences":
                return self._cloud_call(cloud_client.login_preferences)
            if path == "/api/cloud/me":
                return self._cloud_call(cloud_client.me)
            if path == "/api/cloud/redeem/tiers":
                return self._cloud_call(cloud_client.redeem_tiers)
            if path == "/api/member":
                # R256：截图宿主是独立进程，读不到 BFF 进程的会员快照。
                # 提供一个只读接口，宿主启动时/每次开浮窗前拉一次当前会员态。
                st = config.member_state()
                return self._send_json(200, {
                    "member": config.is_member(app_dir),
                    "member_status": st.get("member_status"),
                    "member_plan": st.get("member_plan"),
                    "member_since": st.get("member_since"),
                    "member_expires_at": st.get("member_expires_at"),
                })
            if path == "/api/cloud/devices":
                return self._cloud_call(cloud_client.devices)
            if path == "/api/cloud/prices/series":
                # R290：市场列表「历史 72h」缩略图。云端 /v1/prices/series 是会员接口，
                # 从采集机上传的 30 分钟快照抽真实序列；未登录 / 非会员由云客户端报错，
                # _cloud_call 原样回 401 / 403，前端据此显示「会员功能」而不是假曲线。
                from urllib.parse import parse_qs
                qs = parse_qs(query)
                mode = (qs.get("mode") or ["regular"])[0]
                ids: list[str] = []
                for chunk in qs.get("itemIds") or []:
                    for part in str(chunk).split(","):
                        part = part.strip()
                        if part and part not in ids:
                            ids.append(part)
                days = 3
                try:
                    days = max(1, min(90, int((qs.get("days") or ["3"])[0])))
                except (TypeError, ValueError):
                    pass
                if not ids:
                    return self._send_json(400, {"ok": False, "error": "no-itemIds"})
                return self._cloud_call(cloud_client.prices_series, mode, ids[:12], days)
            if path == "/api/price-cache/status":
                # R279：本地云端价格缓存概况（各模式快照数 / 更新时间 / 体积）。
                # 会员过期时顺手清掉——「过期自动清理缓存」是产品口径。
                try:
                    member = config.is_member(app_dir)
                except Exception:  # noqa: BLE001
                    member = False
                if not member:
                    price_cache.purge(app_dir, reason="not-member")
                    live_prices.purge_cache()
                data = price_cache.status(app_dir)
                data["ok"] = True
                data["member"] = member
                return self._send_json(200, data)
            if path == "/api/logstate":
                snap = follower.snapshot() if follower is not None else {"available": False}
                if shotter is not None:
                    snap = dict(snap, shot=shotter.snapshot())
                if pruner is not None:
                    snap = dict(snap, clean=pruner.snapshot())
                return self._send_json(200, snap)
            if path == "/events":
                return self._serve_events()
            if path == "/sounds":
                return self._send_json(200, {"files": list_sounds(app_dir)})
            if path.startswith("/sounds/"):
                return self._serve_sound(path[len("/sounds/"):])
            if path.startswith("/api/"):
                return self._send_json(404, {"ok": False, "error": "未知接口：%s" % path})
            return super().do_GET()

        def do_POST(self):  # noqa: N802 - 覆盖标准库签名
            """写接口：界面偏好 + 云账号 + 行情刷新 + 关闭服务。

            `/api/prefs` 只写本机配置（无鉴权，限制在 MAX_PREFS_BODY）；
            `/api/cloud/*` 只是把页面请求转给 CloudClient，真正的鉴权与证书固定都在 Python 侧，
            页面永远拿不到 token。云同步的请求体上限单独用 MAX_CLOUD_BODY（3 个 256KB 键）。
            """
            path = self.path.split("?", 1)[0].split("#", 1)[0]
            if path.startswith("/api/cloud/"):
                return self._handle_cloud_post(path)
            if path == "/api/presets":
                return self._handle_presets_post()
            if path == "/api/ocr/frame":
                return self._handle_ocr_frame_post()
            if path == "/api/ocr/recognize":
                return self._handle_ocr_recognize()
            if path == "/api/ocr/overlay/state":
                return self._handle_ocr_overlay_post()
            if path == "/api/price-cache/sync":
                return self._handle_price_cache_sync()
            if path == "/api/live-prices/refresh":
                return self._handle_live_prices_refresh()
            if path == "/api/game-changes/refresh":
                return self._handle_game_changes_refresh()
            if path == "/api/prices/refresh":
                return self._handle_flea_refresh()
            if path == "/api/shutdown":
                return self._handle_shutdown()
            if path == "/api/overlay":
                return self._handle_overlay_toggle()
            if path == "/api/active-map":
                return self._handle_active_map()
            if path == "/api/layout-calibration":
                return self._handle_calibration_post()
            if path == "/api/poi-shot":
                return self._handle_poi_shot_post()
            if path != "/api/prefs":
                # 该路径没有请求体读取逻辑；关闭连接，避免残留字节污染下一条请求。
                return self._send_json(404, {"ok": False, "error": "未知接口：%s" % path}, close=True)
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except (TypeError, ValueError):
                length = 0
            if not 0 < length <= MAX_PREFS_BODY:
                return self._send_json(400, {"ok": False, "error": "请求体缺失或过大"})
            try:
                prefs = json.loads(self.rfile.read(length).decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                return self._send_json(400, {"ok": False, "error": "请求体不是合法 JSON"})
            try:
                cfg = config.save(config.merge_ui(config.load(app_dir), prefs), app_dir)
            except OSError as exc:
                return self._send_json(500, {"ok": False, "error": "保存配置失败：%s" % exc})
            tracker.broadcaster.publish_event("config", config_payload(app_dir))
            return self._send_json(200, {"ok": True, "config": cfg})

        # ---- 小浮窗显隐（R104：设置面板与左侧栏开关共用） ----
        def _handle_overlay_toggle(self):
            """`POST /api/overlay {enabled: bool}`：写 overlay.enabled 并广播 config。

            桌面壳每 500ms 读一次配置决定小浮窗窗口是否出现；这里的 POST 只是让
            页面在写完偏好后立刻拿到一次确认（前端失败时会提示手动启动 overlay.py）。
            """
            body = self._read_body(MAX_PREFS_BODY, "too_large")
            if body is None:
                return
            enabled = body.get("enabled") if isinstance(body, dict) else None
            if not isinstance(enabled, bool):
                return self._send_json(400, {"ok": False, "error": "需要 enabled 布尔值"})
            try:
                cfg = config.load(app_dir)
                overlay = dict(cfg.get("overlay") or {})
                overlay["enabled"] = enabled
                cfg["overlay"] = overlay
                config.save(cfg, app_dir)
            except OSError as exc:
                return self._send_json(500, {"ok": False, "error": "保存配置失败：%s" % exc})
            tracker.broadcaster.publish_event("config", config_payload(app_dir))
            return self._send_json(200, {"ok": True, "enabled": enabled})

        # ---- 当前主窗口地图（R-fix：小地图窗口据此实时跟随主界面选中的地图） ----
        def _handle_active_map(self):
            """`POST /api/active-map {map: key}`：记录当前主地图并广播 `map` 事件。

            主窗口每次切换地图都上报一次；两个 WebView2 窗口各自独立连 SSE，
            后端把当前地图广播给所有订阅者，小地图窗口收到后切换自己的底图，
            从而实现「主界面切图 → 小地图跟着切」的实时联动。
            """
            body = self._read_body(MAX_PREFS_BODY, "too_large")
            if body is None:
                return
            key = body.get("map") if isinstance(body, dict) else None
            if not isinstance(key, str) or not key:
                return self._send_json(400, {"ok": False, "error": "需要 map 字段（地图 key）"})
            self.server.active_map = key
            tracker.broadcaster.publish_event("map", {"map": key})
            return self._send_json(200, {"ok": True, "map": key})

        # ---- 武器布局校准（校准器页面唯一写入口，见 tools/layoutcal.py） ----
        @staticmethod
        def _calibration_payload(doc: dict) -> dict:
            return {
                "ok": True,
                "path": "data/%s" % layoutcal.FILENAME,
                "data": doc,
                "summary": layoutcal.summary(doc),
            }

        def _calibration_error(self, exc: "layoutcal.CalibrationError"):
            return self._send_json(409 if exc.corrupt else 400, {
                "ok": False,
                "code": exc.code,
                "corrupt": exc.corrupt,
                "error": str(exc),
            })

        def _handle_calibration_get(self):
            try:
                doc = layoutcal.load(root)
            except layoutcal.CalibrationError as exc:
                return self._calibration_error(exc)
            return self._send_json(200, self._calibration_payload(doc))

        def _handle_calibration_post(self):
            body = self._read_body(MAX_CALIB_BODY, "too_large")
            if body is None:
                return
            if not isinstance(body, dict):
                return self._send_json(400, {"ok": False, "error": "请求体必须是 JSON 对象"})
            action = body.get("action")
            try:
                doc = layoutcal.load(root)
                if action == "save":
                    gun_id, gun = body.get("gunId"), body.get("gun")
                    if not isinstance(gun_id, str) or not gun_id or not isinstance(gun, dict):
                        raise layoutcal.CalibrationError("save 需要 gunId（字符串）与 gun（对象）")
                    doc = layoutcal.merge_gun(doc, gun_id, layoutcal.validate_gun(gun, gun_id))
                elif action == "save-all":
                    guns = body.get("guns")
                    if not isinstance(guns, dict):
                        raise layoutcal.CalibrationError("save-all 需要 guns 对象")
                    for gun_id, gun in guns.items():
                        if not isinstance(gun_id, str) or not gun_id:
                            raise layoutcal.CalibrationError("save-all 的 gunId 必须是非空字符串")
                        doc = layoutcal.merge_gun(doc, gun_id, layoutcal.validate_gun(gun, gun_id))
                elif action == "clear":
                    gun_id = body.get("gunId")
                    if not isinstance(gun_id, str) or not gun_id:
                        raise layoutcal.CalibrationError("clear 需要 gunId（字符串）")
                    doc = layoutcal.drop_gun(doc, gun_id)
                elif action == "import":
                    # 整包替换语义：先整包校验，非法直接拒，磁盘上的旧数据保持不变
                    doc = layoutcal.validate_doc(body.get("data"))
                else:
                    raise layoutcal.CalibrationError("未知 action：%r" % (action,), code="action")
                doc = layoutcal.save(doc, root)
            except layoutcal.CalibrationError as exc:
                return self._calibration_error(exc)
            except OSError as exc:
                return self._send_json(500, {"ok": False, "error": "写入校准文件失败：%s" % exc})
            return self._send_json(200, self._calibration_payload(doc))

        # ---- 行情（云端唯一数据源；免费 / 会员共用，按账号限次） ----
        def _handle_market_overview(self, query: str):
            """`GET /api/market-overview?mode=&hours=` —— 市场大盘（只读）。

            数据来自云端行情快照（与本机「市场列表」同一次取数结果）；
            免费账号由服务端延迟 12 小时。没有可用缓存时才向云端取一次，
            列表已经取过就直接复用，不重复扣次。
            """
            from urllib.parse import parse_qs

            qs = parse_qs(query)
            raw_mode = (qs.get("mode") or ["regular"])[0]
            try:
                mode = prices_source.normalize_mode(raw_mode)
            except ValueError:
                return self._send_json(400, {"ok": False, "error": "bad-mode",
                                             "allowed": list(prices_source.MODE_ALIASES)})
            try:
                hours = int((qs.get("hours") or [market_overview.WINDOW_HOURS_DEFAULT])[0])
            except (TypeError, ValueError):
                return self._send_json(400, {"ok": False, "error": "bad-hours"})
            ids = []
            for key in ("ids", "itemIds", "itemId"):
                for chunk in qs.get(key) or []:
                    for part in str(chunk).split(","):
                        part = part.strip()
                        if part and part not in ids:
                            ids.append(part)
            ids = ids[:24]
            sector = (qs.get("sector") or [""])[0].strip()
            if not _cloud_logged_in(cloud_client):
                return self._send_json(200, {
                    "ok": False, "mode": mode, "source": "cloud",
                    "loginRequired": True, "error": "login_required",
                    "message": "市场行情需要登录账号后从云端获取",
                    "buckets": [], "gainers": [], "losers": [], "hot": [],
                    "sectors": [], "items": {},
                })
            try:
                member = config.is_member(app_dir)
            except Exception:  # noqa: BLE001
                member = False
            # 大盘的 24h / 48h / 七天均价用云端价格缓存（会员全量序列）；
            # 每次打开大盘做一次增量同步，失败不阻塞（继续用已有缓存 / 快照）。
            if member and cloud_client is not None:
                try:
                    price_cache.sync(app_dir, cloud_client, mode)
                except Exception:  # noqa: BLE001
                    pass
            cutoff = _free_price_cutoff(member)
            if cloud_market.load_latest(app_dir, mode) is None:
                try:
                    cloud_market.fetch(app_dir, mode, cloud_client, max_generated_at=cutoff)
                except Exception as exc:  # noqa: BLE001 - 大盘失败不能影响主服务
                    code = getattr(exc, "code", "") or "unavailable"
                    return self._send_json(200, {
                        "ok": False, "mode": mode, "source": "cloud",
                        "error": code, "message": str(exc) or "云端行情不可用",
                        "loginRequired": getattr(exc, "status", None) in (401, 403),
                        "quota": (getattr(exc, "details", {}) or {}).get("quota"),
                    })
            try:
                payload = cloud_market.overview(app_dir, mode, hours, ids=ids,
                                                sector=sector or None,
                                                max_generated_at=cutoff)
            except Exception as exc:  # noqa: BLE001
                return self._send_json(200, {"ok": False, "error": "overview-failed",
                                             "hint": str(exc)})
            return self._send_json(200, payload)

        def _handle_market_history(self, query: str):
            """`GET /api/market-history?mode=&itemIds=&days=` —— 大盘专用曲线。

            只读本机历次云端取数累积的快照，不再额外向云端请求、不重复扣配额。
            免费账号拿到的快照本身已由服务端延迟 12 小时，曲线口径与列表一致。
            """
            from urllib.parse import parse_qs

            qs = parse_qs(query)
            raw_mode = (qs.get("mode") or ["regular"])[0]
            try:
                mode = prices_source.normalize_mode(raw_mode)
            except ValueError:
                return self._send_json(400, {"ok": False, "error": "bad-mode",
                                             "allowed": list(prices_source.MODE_ALIASES)})
            ids = []
            for key in ("itemId", "itemIds"):
                for chunk in qs.get(key) or []:
                    for part in str(chunk).split(","):
                        part = part.strip()
                        if part and part not in ids:
                            ids.append(part)
            if not ids:
                return self._send_json(400, {"ok": False, "error": "no-item"})
            ids = ids[:24]
            try:
                days = int((qs.get("days") or ["1"])[0])
            except (TypeError, ValueError):
                days = 1
            days = max(1, min(90, days))
            if not _cloud_logged_in(cloud_client):
                return self._send_json(200, {
                    "ok": False, "mode": mode, "source": "cloud",
                    "loginRequired": True, "error": "login_required",
                    "series": {}, "status": "login_required",
                })
            try:
                member = config.is_member(app_dir)
            except Exception:  # noqa: BLE001
                member = False
            try:
                payload = cloud_market.history(app_dir, mode, ids, days,
                                               max_generated_at=_free_price_cutoff(member))
            except Exception as exc:  # noqa: BLE001 - 大盘曲线失败不能影响主服务
                return self._send_json(200, {"ok": False, "error": "history-failed",
                                             "hint": str(exc)})
            # 会员登录时可能已经整包下载过云端历史：补进曲线，免去「等本机攒样本」。
            # 免费账号不合并（会员缓存里可能是 12 小时内的新数据）。
            if member and price_cache.has_data(app_dir, mode):
                try:
                    cached = price_cache.series(app_dir, mode, ids, days)
                    payload = price_history.merge_cloud(
                        payload, cached, status=str(cached.get("status") or "ok")
                    )
                except Exception:  # noqa: BLE001 - 缓存损坏不能影响已有曲线
                    pass
            return self._send_json(200, payload)

        # ---------------------------------------------------------- 点位参考图
        def _read_raw(self, limit: int, code: str):
            """读原始二进制请求体（图片上传）。超限也要读尽剩余字节，否则连接错位。"""
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except (TypeError, ValueError):
                length = 0
            if length <= 0:
                self._send_json(400, {"ok": False, "code": code, "error": "请求体为空"})
                return None
            if length > limit:
                remaining = length
                while remaining > 0:
                    chunk = self.rfile.read(min(65536, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                self._send_json(413, {"ok": False, "code": code,
                                      "error": "图片超过上限（%d MB）"
                                               % (poi_shots.MAX_BYTES // 1024 // 1024)})
                return None
            data = self.rfile.read(length)
            if len(data) != length:
                self._send_json(400, {"ok": False, "code": code, "error": "请求体读取不完整"})
                return None
            return data

        def _handle_poi_shot_get(self, query: str):
            """`GET /api/poi-shot?key=` → 参考图原始字节（没有就 404，不回占位图）。"""
            from urllib.parse import parse_qs

            key = (parse_qs(query).get("key") or [""])[0]
            found = poi_shots.load(app_dir, key) if key else None
            if found is None:
                return self._send_json(404, {"ok": False, "error": "该点位还没有参考图"})
            data, ctype = found
            self._send_cache_header()
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def _handle_poi_shot_post(self):
            """`POST /api/poi-shot?key=[&action=delete]`，非 delete 时请求体就是图片字节。

            类型按**魔数**判定而不是 Content-Type：前端可以随便写 header，
            但写不出 JPEG 的 FFD8FF。
            """
            from urllib.parse import parse_qs, urlparse

            qs = parse_qs(urlparse(self.path).query)
            key = (qs.get("key") or [""])[0]
            action = (qs.get("action") or ["save"])[0].strip().lower()
            if action == "delete":
                try:
                    removed = poi_shots.delete(app_dir, key)
                except poi_shots.ShotError as exc:
                    return self._send_json(400, {"ok": False, "error": str(exc)})
                return self._send_json(200, {"ok": True, "removed": removed})
            data = self._read_raw(poi_shots.MAX_BYTES, "poi_shot")
            if data is None:
                return
            try:
                info = poi_shots.save(app_dir, key, data, self.headers.get("Content-Type") or "")
            except poi_shots.ShotError as exc:
                return self._send_json(400, {"ok": False, "error": str(exc)})
            payload = {"ok": True, "hash": poi_shots.hash_of(key)}
            payload.update(info)
            return self._send_json(200, payload)

        def _handle_price_history(self, query: str):
            """`GET /api/price-history?mode=&itemId=&days=`。

            只读 `data/flea-price-history/` 里由采集脚本落下的真实快照，
            没有数据就说没有：不插值、不补点、不拿别的模式顶替。
            支持 `itemIds=a,b,c`（表格首屏批量取迷你曲线，最多 60 个）。
            """
            from urllib.parse import parse_qs

            qs = parse_qs(query)
            raw_mode = (qs.get("mode") or ["regular"])[0]
            try:
                mode = prices_source.normalize_mode(raw_mode)
            except ValueError:
                return self._send_json(400, {"ok": False, "error": "bad-mode",
                                             "allowed": list(prices_source.MODE_ALIASES)})
            ids = []
            for key in ("itemId", "itemIds"):
                for chunk in qs.get(key) or []:
                    for part in str(chunk).split(","):
                        part = part.strip()
                        if part and part not in ids:
                            ids.append(part)
            if not ids:
                return self._send_json(400, {"ok": False, "error": "no-item"})
            try:
                member = config.is_member(app_dir)
            except Exception:  # noqa: BLE001
                member = False
            if not member:
                price_cache.purge(app_dir, reason="not-member")
                live_prices.purge_cache()
                return self._send_json(403, {
                    "ok": False, "error": "member_required",
                    "hint": "价格历史是会员功能；免费档仅提供随安装包发布的离线快照。",
                })
            try:
                days = int((qs.get("days") or ["7"])[0])
            except (TypeError, ValueError):
                days = 7
            payload = price_history.series(root, mode, ids, days)
            # R278/R279：本机快照之外再并一份云端历史。
            # 优先级：本地缓存（登录时整包下载，秒回、不联网）→ 云端实时接口（缓存还没建好时兜底）。
            # 会员才有云端价格权限；非会员直接跳过，接口行为与旧版一致。
            if cloud_client is not None and len(ids) <= _CLOUD_SERIES_MAX_ITEMS:
                try:
                    member = config.is_member(app_dir)
                except Exception:  # noqa: BLE001 - 会员态读不到按非会员处理
                    member = False
                if member:
                    cloud_payload, cloud_status = _cloud_series_cached(
                        app_dir, cloud_client, mode, ids, days
                    )
                else:
                    cloud_payload, cloud_status = None, "member_required"
                    # 会员过期 / 退出登录：缓存不再可用，直接清掉（用户要求）。
                    if price_cache.has_data(app_dir, mode):
                        price_cache.purge(app_dir, reason="not-member")
                    live_prices.purge_cache()
                payload = price_history.merge_cloud(
                    payload, cloud_payload, status=cloud_status
                )
            return self._send_json(200, payload)

        def _handle_price_cache_sync(self):
            """`POST /api/price-cache/sync`：整包 / 增量同步云端价格缓存。

            请求体 `{"mode": "regular"}`（可选，缺省用当前数据模式）。
            · 本地还没有缓存 → 整包下载（首次登录，约 2–4 MB / 一个模式）；
            · 已有 cursor → 只取新快照（通常 0–2 条）；
            · 非会员 → 403 `member_required`，顺手清掉本地缓存；
            · 云端不可达 → 502，本地缓存照旧可用（不清）。
            """
            body = self._read_cloud_body()
            raw_mode = body.get("mode") if isinstance(body, dict) else None
            if not raw_mode:
                try:
                    raw_mode = (config.load(app_dir) or {}).get("dataScope", {}).get("mode")
                except (OSError, ValueError):
                    raw_mode = None
            try:
                mode = prices_source.normalize_mode(raw_mode or "regular")
            except ValueError:
                return self._send_json(400, {"ok": False, "error": "bad-mode",
                                             "allowed": list(prices_source.MODE_ALIASES)})
            try:
                member = config.is_member(app_dir)
            except Exception:  # noqa: BLE001
                member = False
            if not member:
                price_cache.purge(app_dir, reason="not-member")
                live_prices.purge_cache()
                return self._send_json(403, {
                    "ok": False,
                    "error": "member_required",
                    "hint": "云端价格缓存是会员数据；开通会员后登录即自动下载。",
                })
            if cloud_client is None:
                return self._send_json(503, {"ok": False, "error": "cloud-disabled",
                                             "hint": "云端客户端不可用"})
            try:
                summary = price_cache.sync(app_dir, cloud_client, mode)
            except cloud.CloudError as exc:
                if exc.status == 403 and exc.code == "membership_required":
                    # 服务端说已经不是会员了：本地缓存立刻清，界面按非会员重画。
                    price_cache.purge(app_dir, reason="membership-required")
                    live_prices.purge_cache()
                    config.set_member_state({"member": False, "member_status": "none"})
                    return self._send_json(403, {
                        "ok": False, "error": "member_required",
                        "hint": "会员已过期，本地云端缓存已清理；重新开通后再点一次。",
                    })
                if exc.status == 0:
                    return self._send_json(502, {"ok": False, "error": "offline",
                                                 "hint": "云端暂时连不上，本地缓存仍然可用。"})
                return self._send_json(exc.status or 502, {"ok": False, "error": exc.code,
                                                           "hint": str(exc)})
            except OSError as exc:
                return self._send_json(500, {"ok": False, "error": "io", "hint": str(exc)})
            summary["ok"] = True
            summary["member"] = True
            summary["status"] = price_cache.status(app_dir)
            return self._send_json(200, summary)

        def _handle_price_snapshot(self, query: str):
            """`GET /api/price-snapshot?mode=regular|pve|pvps[&force=1]`。

            数据只来自云端（免费与会员同一入口）：
              · 未登录 → `loginRequired=true`，不发任何云端请求；
              · 免费 → 服务端 12 小时延迟、每日 24 次、CD 59:59；
              · 会员 → 最新快照、CD 30 秒；
              · 云端不可达 / 配额用尽 → 本机最后一次成功结果，标 `cached=true`。
            不再读取随安装包发布的离线快照。
            """
            from urllib.parse import parse_qs

            qs = parse_qs(query)
            raw_mode = (qs.get("mode") or ["regular"])[0]
            try:
                mode = prices_source.normalize_mode(raw_mode)
            except ValueError:
                return self._send_json(400, {"ok": False, "error": "bad-mode",
                                             "allowed": list(prices_source.MODE_ALIASES)})
            if not _cloud_logged_in(cloud_client):
                return self._send_json(200, {
                    "ok": False,
                    "mode": mode,
                    "available": False,
                    "source": "cloud",
                    "loginRequired": True,
                    "items": {},
                    "error": "login_required",
                    "message": "市场行情需要登录账号后从云端获取",
                })
            try:
                member = config.is_member(app_dir)
            except Exception:  # noqa: BLE001
                member = False
            if not member:
                # 会员到期的本地会员缓存（旧版整包 history）不再可用；新行情缓存
                # 仍允许免费账号读取自己最后一次云端结果。
                price_cache.purge(app_dir, reason="not-member")
                live_prices.purge_cache()
            force = (qs.get("force") or ["0"])[0] == "1"
            payload = prices_source.snapshot_for(
                root, mode, cloud_client=cloud_client, member=member,
                force=force, app_dir=app_dir,
                max_generated_at=_free_price_cutoff(member),
            )
            return self._send_json(200, payload)

        def _handle_ocr_frame_post(self):
            """`POST /api/ocr/frame`（R238/R240）：宿主把热键抓的整屏冻结帧交上来。

            原始图像字节（octet-stream）；R240 起宿主发 **BMP**（免压缩编码，
            热键→可框选 <0.5s），按魔数嗅探格式（BM→bmp / PNG→png）。
            内存里只留最近一帧（下一次热键覆盖），10 分钟无人使用即失效。
            """
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except (TypeError, ValueError):
                return self._send_json(400, {"ok": False, "error": "冻结帧 Content-Length 非法"}, close=True)
            if not 0 < length <= MAX_OCR_FRAME_BODY:
                return self._send_json(400, {"ok": False,
                                             "error": "冻结帧缺失或超过上限（%d MB）"
                                                      % (MAX_OCR_FRAME_BODY // (1024 * 1024))}, close=True)
            data = self.rfile.read(length)
            fmt = "bmp" if data[:2] == b"BM" else "png"
            frame_id = "%d" % int(time.time() * 1000)
            _OCR_FRAME.update({"id": frame_id, "bytes": data, "at": time.time(), "fmt": fmt})
            return self._send_json(200, {"ok": True, "id": frame_id, "bytes": length})

        def _handle_ocr_frame_get(self, query: str):
            """`GET /api/ocr/frame`（R238/R240）：scan.html 取冻结帧。

            带 `?id=`：返回图像原始字节（Content-Type 跟随上报格式，BMP/PNG）；
            不带 id：返回元信息 `{"ok", "id", "fmt"}`——R240 页面轮询它发现新帧
            （保温窗口不重载页面，热键后 ≤150ms 内换帧）。
            """
            from urllib.parse import parse_qs

            qs = parse_qs(query)
            if not qs.get("id"):
                st = _OCR_FRAME
                fresh = bool(st["id"]) and time.time() - st["at"] <= _OCR_FRAME_TTL
                return self._send_json(200, {"ok": True,
                                             "id": st["id"] if fresh else None,
                                             "fmt": st["fmt"] if fresh else None})
            fid = (qs.get("id") or [""])[0]
            frame = _OCR_FRAME
            if (not fid or frame["id"] != fid or not frame["bytes"]
                    or time.time() - frame["at"] > _OCR_FRAME_TTL):
                return self._send_json(404, {"ok": False, "error": "冻结帧不存在或已过期"})
            body = frame["bytes"]
            self._send_cache_header()
            self.send_response(200)
            self.send_header("Content-Type", "image/bmp" if frame.get("fmt") == "bmp"
                             else "image/png")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _handle_ocr_overlay_get(self):
            """`GET /api/ocr/overlay/state`（R239）：宿主读框选交接状态。

            scan.html 识别成功后 POST 上来（region + matches），宿主轮询到
            「EFT截图·完成」标题后取走并切换原生透明浮窗。
            """
            st = _OCR_OVERLAY
            return self._send_json(200, {
                "ok": True,
                "active": bool(st.get("region")),
                "region": st.get("region"),
                "matches": st.get("matches") or [],
                "ageMs": int((time.time() - st.get("ts", 0.0)) * 1000) if st.get("ts") else None,
                "ts": st.get("ts"),
            })

        def _handle_ocr_overlay_post(self):
            """`POST /api/ocr/overlay/state`（R239）：scan.html 交接框选区域与匹配结果。

            matches 做白名单瘦身（宿主只渲染标签用不到的字段不收），单槽覆盖。
            """
            body = self._read_body(4 * 1024 * 1024, "overlay_too_large")
            if body is None:
                return
            region = body.get("region")
            if not isinstance(region, dict):
                return self._send_json(400, {"ok": False, "error": "缺少 region"})
            try:
                rx, ry = int(region["x"]), int(region["y"])
                rw, rh = int(region["w"]), int(region["h"])
            except (KeyError, TypeError, ValueError):
                return self._send_json(400, {"ok": False, "error": "region 需要 x/y/w/h 整数"})
            if rw <= 0 or rh <= 0:
                return self._send_json(400, {"ok": False, "error": "region 尺寸非法"})
            raw_matches = body.get("matches")
            if not isinstance(raw_matches, list):
                raw_matches = []
            keep = ("id", "name", "short", "text", "tier", "ocrScore",
                    "x", "y", "w", "h", "gw", "gh", "weight", "noFlea",
                    "ammoKind", "qty", "price")
            matches = []
            for m in raw_matches[:200]:
                if not isinstance(m, dict):
                    continue
                matches.append({k: m.get(k) for k in keep if m.get(k) is not None})
            _OCR_OVERLAY.update({"ts": time.time(),
                                 "region": {"x": rx, "y": ry, "w": rw, "h": rh},
                                 "matches": matches})
            return self._send_json(200, {"ok": True, "count": len(matches)})

        def _handle_ocr_recognize(self):
            """`POST /api/ocr/recognize`（R234）：截图 → OCR → 物品匹配 → 价格。

            请求体：`{"image": "<base64 或 dataURL>", "mode": "regular|pve|pvps"(可选),
            "annotate": true(可选)}`。价格复用市场页同一数据源
            `prices_source.snapshot_for`（云端行情；免费延迟 12 小时）。
            OCR 引擎/模型缺失回 503 `ocr-unavailable`，不影响其它功能。
            """
            import base64

            body = self._read_body(MAX_OCR_BODY, "ocr_too_large")
            if body is None:
                return
            raw = body.get("image") or ""
            if isinstance(raw, str) and raw.startswith("data:"):
                _, _, raw = raw.partition(",")
            if not raw or not isinstance(raw, str):
                return self._send_json(400, {"ok": False, "error": "缺少 image 字段（base64）"})
            try:
                img_bytes = base64.b64decode(raw)
            except (ValueError, TypeError):
                return self._send_json(400, {"ok": False, "error": "image 不是合法 base64"})
            try:
                img = ocr.decode_image_bgr(img_bytes)
            except ocr.OcrUnavailable as exc:
                return self._send_json(503, {"ok": False, "error": "ocr-unavailable",
                                             "hint": str(exc)})
            if img is None:
                return self._send_json(400, {"ok": False, "error": "图片解码失败（支持 PNG/JPEG）"})

            raw_mode = body.get("mode")
            mode = None
            if raw_mode:
                try:
                    mode = prices_source.normalize_mode(raw_mode)
                except ValueError:
                    return self._send_json(400, {"ok": False, "error": "bad-mode",
                                                 "allowed": list(prices_source.MODE_ALIASES)})
            else:
                mode = "regular"
                try:
                    scope = (config.load(app_dir) or {}).get("dataScope") or {}
                    mode = prices_source.normalize_mode(scope.get("mode") or "regular")
                except (ValueError, OSError):
                    mode = "regular"

            try:
                engine = ocr.get_engine()
            except ocr.OcrUnavailable as exc:
                return self._send_json(503, {"ok": False, "error": "ocr-unavailable",
                                             "hint": str(exc)})
            want_annotate = body.get("annotate")
            want_annotate = True if want_annotate is None else bool(want_annotate)
            lines, annotated_png, took_ms = engine.recognize(img, annotate=want_annotate)

            names, name_to_ids, catalog = _ocr_catalog(root)
            matcher = _ocr_matcher(names)
            matches = matcher.match_lines(
                [{"text": ln["text"], "score": ln["score"], "box": ln["points"]} for ln in lines])

            # R19.81：未登录不请求云端，也不拿目录里的构建期基线价冒充行情。
            # 截图识别只做物品名识别，价格列留空（前端显示「—」）。
            logged_in = _cloud_logged_in(cloud_client)
            if logged_in:
                try:
                    member = config.is_member(app_dir)
                except Exception:
                    member = False
                snap = prices_source.snapshot_for(root, mode, cloud_client=cloud_client,
                                                  member=member, app_dir=app_dir,
                                                  max_generated_at=_free_price_cutoff(member))
                snap_items = (snap.get("items") or {}) if snap.get("available") else {}
            else:
                snap = {"available": False, "loginRequired": True, "source": "cloud",
                        "items": {}, "avg7d": {"values": {}}}
                snap_items = {}
            # R238：72h / 30d 均价（price_history 本地快照，72h=3 天窗口）。
            # 快照序列 points = [[iso, lastLow, avg24h], …]；取 lastLow 非空值求均值，
            # 一个窗口没有任何快照就没有该字段（绝不估算/插值）。
            hist: dict[str, dict[str, int]] = {}
            match_ids = []
            for m in matches:
                for iid in name_to_ids.get(matcher.names_for(m["key"])[0]) or []:
                    if iid not in match_ids:
                        match_ids.append(iid)
            if match_ids and logged_in:
                # R248：只扫一次 30 天序列，按时间戳本地切 72h 窗口。
                # 原来 3 天 / 30 天各调一次 series → 全部 gz 解压两遍。
                try:
                    s = price_history.series(root, mode, match_ids, days=30)
                except Exception:
                    s = {}
                cutoff3 = (datetime.datetime.now().astimezone()
                           - datetime.timedelta(days=3)).isoformat(timespec="seconds")
                for iid, row in (s.get("series") or {}).items():
                    pts = [p for p in (row.get("points") or [])
                           if isinstance(p, (list, tuple)) and len(p) > 1 and p[1]]
                    vals30 = [p[1] for p in pts]
                    vals3 = [p[1] for p in pts if str(p[0]) >= cutoff3]
                    if vals3:
                        hist.setdefault(iid, {})["w72"] = int(sum(vals3) / len(vals3))
                    if vals30:
                        hist.setdefault(iid, {})["w30d"] = int(sum(vals30) / len(vals30))
            out_matches = []
            count_lines = _ocr_count_lines(lines)   # R250：整张图只扫一次数量行
            for m in matches:
                ids = name_to_ids.get(matcher.names_for(m["key"])[0]) or []
                # R250：短名同时指向散装子弹与弹药包时，按格子右下角的数量形态
                # 决定用哪一类候选（xx/xx=弹药包 / 纯数字=散装堆叠）。
                # R251：ammo_ambig = 候选里仍有多个口径（.338 AP vs .300 AP…），
                # 截图上无法区分，只标注不瞎猜；R309 起散装不再按包装分布收窄。
                ammo_kind, ammo_qty, ammo_ids, ammo_found, ammo_ambig = \
                    _ocr_ammo_decision(m, lines, ids, catalog, count_lines)
                if ammo_kind and ammo_ids:
                    ids = ammo_ids
                else:
                    ammo_kind = None          # 数据里没这个形态 → 不干预原逻辑
                # 同名多 id：挑价格可用且每格价最高的（对应规格 PickBest PerSlot↓Price↓）
                # R260：先排除异色/特殊版（带括号后缀）——避免 FDE/香蕉黄/BB弹 等
                # 高价变体盖过普通版（弹匣 GEN M3 这类一字多版本的重灾区）。
                disp = matcher.names_for(m["key"])[0]
                best = None
                best_rank = None
                for iid in _ocr_prefer_base_variant(ids, catalog):
                    rec = catalog.get(iid) or {}
                    row = snap_items.get(iid) or {}
                    hist_row = hist.get(iid) or {}
                    avg7 = (snap.get("avg7d") or {}).get("values", {}).get(iid)
                    # R258：三档价格优先级（用户提供）
                    #   1) 跳蚤有售卖 → 跳蚤价（实时快照优先，缺失回退目录跳蚤基线）
                    #   2) 跳蚤不卖但商人会卖 → 商人售卖价（玩家从商人处购买）
                    #   3) 都不卖 → 商人收购价（玩家卖给商人，红购物车警示）
                    price = _ocr_resolve_price(rec, row, hist_row, avg7)
                    no_flea = bool(price.get("noFlea"))
                    per_slot = price.get("perSlot")
                    cand = {"id": iid, "name": rec.get("n") or iid,
                            "short": ocr.short_name_of(rec.get("n") or ""),
                            "gw": rec.get("gw"), "gh": rec.get("gh"),
                            "weight": rec.get("w"),
                            "noFlea": no_flea, "price": price}
                    # 撞名时的排序：**全名以该显示名结尾**的优先。游戏内短名几乎都是全名
                    # 的末段（「TerraGroup实验室访问钥匙卡」），而容器/打包品不是
                    # （「钥匙卡收纳盒」）。R309：同名多 id 时真实行情优先于基础价兜底，
                    # 同档再比每格价（见 _ocr_variant_rank）。
                    rank = _ocr_variant_rank(cand["name"], disp, price, per_slot)
                    if best is None or rank > best_rank:
                        best, best_rank = cand, rank
                if best is None:
                    continue
                if ocr.item_name_excluded(best["name"]):
                    continue  # R242：臂带/臂章/狗牌类物品不识别（用户点名）
                # 撞名徽记：一个显示名对应多个**不同物品**时（钥匙卡 / 海报 / FMJ…），
                # 截图上无法区分，只标「?」并把候选价目给前端，绝不假装确定。
                # 弹药有自己的通道（口径歧义 / 弹药包形态），这里不掺和，避免双重标注。
                if not ammo_kind:
                    collided = _ocr_name_collision(ids, catalog, snap_items, hist, snap)
                    if len(collided) > 1:
                        best["ambiguous"] = True
                        best["candidates"] = collided
                        # 候选价差：浮窗据此决定「只画徽章不报价」还是「报价 + 徽章」。
                        # 差价很小的同名组（同款不同色）不该被剥掉价格。
                        vals = [c["perSlot"] for c in collided
                                if isinstance(c["perSlot"], (int, float)) and c["perSlot"] > 0]
                        if len(vals) >= 2:
                            best["priceSpread"] = round(max(vals) / min(vals), 2)
                if ammo_kind == "loose" and not _ocr_apply_ammo_stack(
                        best, catalog, ammo_qty, ammo_found):
                    ammo_kind = None       # 没取到商人收购价，保留原结果
                elif ammo_kind == "pack":
                    best["ammoKind"] = "pack"
                    best["qty"] = ammo_qty
                    best["price"]["ammoPack"] = True
                    best["price"]["ammoStack"] = False
                if ammo_kind and ammo_ambig:
                    # R251：同短名多口径无法从截图区分（显示名都是 AP/FMJ）。
                    # 浮窗只画 ? 徽章（不报价），候选价目表给前端选单自己核对。
                    best["price"]["ambiguous"] = True
                    best["price"]["candidates"] = _ocr_ambig_candidates(
                        ammo_ids, catalog, snap_items)
                best.update({"text": m["text"], "tier": m["path"],
                             "ocrScore": m["score"], "x": m["x"], "y": m["y"],
                             "w": m["w"], "h": m["h"]})
                out_matches.append(best)
            out_matches = dedup_ocr_matches(out_matches)
            # R261 诊断：散装弹没对上数量行时记一行（含检测到的数量行 qty + 该件兜底价），
            # 便于用户偶发「两堆 80 只显示单价」时定位是没检出还是没对齐。
            try:
                unfound = [m for m in out_matches
                           if (m.get("price") or {}).get("ammoStack")
                           and (m.get("price") or {}).get("qtyFound") is False]
                if unfound:
                    print("[ocr] 散装弹药未对齐数量 %d 件；数量行 qty=%s；件=%s"
                          % (len(unfound), [c["qty"] for c in count_lines],
                             "、".join("%s@%s" % ((m.get("price") or {}).get("unitPrice"),
                                                  (m.get("name") or "")[:16])
                                       for m in unfound)),
                          file=sys.stderr)
            except Exception:
                pass
            if not logged_in:
                _ocr_scrub_prices(out_matches)
            annotated = None
            if annotated_png:
                annotated = "data:image/png;base64," + base64.b64encode(annotated_png).decode("ascii")
            return self._send_json(200, {
                "ok": True,
                "tookMs": round(took_ms),
                "mode": mode,
                "loginRequired": not logged_in,
                "source": snap.get("sourceType") or snap.get("source") or "",
                "nonLive": bool(snap.get("nonLive")),
                "offline": bool(snap.get("offline")),
                "counts": {"lines": len(lines), "matched": len(out_matches)},
                "lines": [{"text": ln["text"], "score": ln["score"],
                           "points": ln["points"]} for ln in lines],
                "matches": out_matches,
                "annotated": annotated,
            })

        def _handle_live_prices_get(self, query: str):
            """`GET /api/live-prices?mode=regular|pve`：返回缓存里的价格（只读本地）。"""
            from urllib.parse import parse_qs

            try:
                member = config.is_member(app_dir)
            except Exception:
                member = False
            if not member:
                price_cache.purge(app_dir, reason="not-member")
                live_prices.purge_cache()
                return self._send_json(200, {
                    "ok": True, "enabled": False, "available": False,
                    "source": "bundled", "prices": {}, "count": 0,
                    "stale": True, "error": "member-required",
                    "message": "在线行情仅对有效会员开放", "mode": "regular",
                })
            settings = config.live_prices(app_dir)
            raw_mode = (parse_qs(query).get("mode") or [settings["mode"]])[0]
            try:
                mode = live_prices.normalize_mode(raw_mode)
            except ValueError:
                return self._send_json(400, {"ok": False, "error": "bad-mode",
                                             "allowed": list(live_prices.MODES)})
            info = live_prices.MODES[mode]
            source = settings.get("source") or info["source"]
            if not settings["enabled"]:
                return self._send_json(200, {
                    "ok": True,
                    "enabled": False,
                    "available": False,
                    "source": "snapshot",
                    "snapshot": "data/flea-prices.json",
                    "prices": {},
                    "count": 0,
                    "stale": True,
                    "mode": mode,
                    "priceMode": info["priceMode"],
                })
            status = live_prices.cache_status(mode, settings["ttlSec"])
            cache = live_prices.load_cache(mode)
            if cache is None:
                return self._send_json(200, {
                    "ok": False,
                    "enabled": True,
                    "available": False,
                    "error": status.get("error") or "no-cache",
                    "prices": {},
                    "count": 0,
                    "stale": True,
                    "mode": mode,
                    "priceMode": info["priceMode"],
                    "source": source,
                })
            prices: dict[str, dict[str, Any]] = {}
            for item_id, row in cache["items"].items():
                if not isinstance(row, dict):
                    continue
                quote = {key: row[key] for key in ("l", "a", "u") if key in row}
                if quote:
                    prices[str(item_id)] = quote
            return self._send_json(200, {
                "ok": True,
                "enabled": True,
                "available": True,
                "prices": prices,
                "count": len(cache["items"]),
                "stale": bool(status.get("stale")),
                "mode": mode,
                "priceMode": info["priceMode"],
                "source": source,
                "fetchedAt": cache.get("fetchedAt"),
                "checkedAt": cache.get("checkedAt"),
                "updatedOldest": status.get("updatedOldest"),
                "updatedNewest": status.get("updatedNewest"),
                "ttlSec": status.get("ttlSec"),
                "ageSec": status.get("ageSec"),
            })

        def _handle_live_prices_status(self):
            """`GET /api/live-prices/status`：开关 + 两个模式各自的缓存状态。"""
            settings = config.live_prices(app_dir)
            modes = {mode: live_prices.cache_status(mode, settings["ttlSec"])
                     for mode in live_prices.MODES}
            return self._send_json(200, {"ok": True, "enabled": settings["enabled"],
                                         "mode": settings["mode"], "ttlSec": settings["ttlSec"],
                                         "modes": modes})

        def _is_loopback_client(self) -> bool:
            host = (getattr(self, "client_address", None) or ("", 0))[0]
            return host in ("::1", "localhost") or str(host).startswith("127.")

        def _same_origin_ok(self) -> bool:
            """Origin / Referer 的 netloc 必须与请求 Host 一致（同源页面）。"""
            from urllib.parse import urlparse

            origin = self.headers.get("Origin") or self.headers.get("Referer")
            if not origin:
                return False
            host = (self.headers.get("Host") or "").strip().lower()
            try:
                netloc = urlparse(origin).netloc.lower()
            except ValueError:
                return False
            return bool(netloc) and netloc == host

        def _read_refresh_body(self):
            """读刷新接口的 JSON 体；超限 / 非法 Content-Length 会直接回错误并关连接。

            提前返回 409/403 之前也必须先把 body 读尽，否则残留字节会被当下一请求行。
            """
            raw = self.headers.get("Content-Length")
            if raw in (None, ""):
                return {}
            try:
                length = int(raw)
            except (TypeError, ValueError):
                self._send_json(400, {"ok": False, "error": "Content-Length 非法"}, close=True)
                return None
            if length < 0:
                self._send_json(400, {"ok": False, "error": "Content-Length 非法"}, close=True)
                return None
            if length == 0:
                return {}
            if length > MAX_PREFS_BODY:
                remaining = length
                while remaining > 0:
                    chunk = self.rfile.read(min(65536, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                self._send_json(413, {"ok": False, "error": "请求体过大",
                                      "limit": MAX_PREFS_BODY}, close=True)
                return None
            data = self.rfile.read(length)
            try:
                body = json.loads(data.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                self._send_json(400, {"ok": False, "error": "请求体不是合法 JSON"})
                return None
            return body if isinstance(body, dict) else {}

        def _handle_game_changes_refresh(self):
            """`POST /api/game-changes/refresh`：本机 / 同源页面触发一次官方公告拉取。

            只读的对外抓取（取官方补丁说明），没有破坏性副作用；仍然限制来源，
            避免任意网页借用户的本机服务当免费代理。
            """
            if not self._is_loopback_client():
                return self._send_json(403, {"ok": False, "error": "只允许本机刷新"})
            origin = self.headers.get("Origin") or self.headers.get("Referer")
            if origin and not self._same_origin_ok():
                return self._send_json(403, {"ok": False, "error": "跨站请求被拒绝"})
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except (TypeError, ValueError):
                length = 0
            if 0 < length <= 65536:      # 读尽请求体，保持 keep-alive 连接干净
                self.rfile.read(length)
            return self._send_json(200, refresh_game_changes(root, app_dir))

        def _handle_live_prices_refresh(self):
            """`POST /api/live-prices/refresh`：桌面壳凭 token、网页凭同源会话触发抓取。

            判定顺序固定为：本机限制 → 读尽请求体 → 开关 → 凭据。
            这样开关关闭时先回 409（而不是 403），且 keep-alive 连接不会残留 body。
            """
            if not self._is_loopback_client():
                return self._send_json(403, {"ok": False, "error": "刷新行情只允许本机操作"})
            body = self._read_refresh_body()
            if body is None:
                return
            try:
                member = config.is_member(app_dir)
            except Exception:
                member = False
            if not member:
                price_cache.purge(app_dir, reason="not-member")
                live_prices.purge_cache()
                return self._send_json(403, {"ok": False, "error": "member-required",
                                             "message": "在线行情仅对有效会员开放"})
            settings = config.live_prices(app_dir)
            if not settings["enabled"]:
                return self._send_json(409, {"ok": False, "enabled": False,
                                             "error": "disabled",
                                             "message": "在线行情未开启（设置里打开 livePrices 后再试）"})
            raw_mode = body.get("mode") or settings["mode"]
            try:
                mode = live_prices.normalize_mode(raw_mode)
            except ValueError:
                return self._send_json(400, {"ok": False, "error": "bad-mode",
                                             "allowed": list(live_prices.MODES)})

            token = (self.headers.get("X-EFTMap-Token") or "").strip()
            client = (self.headers.get("X-EFTMap-Client") or "").strip().lower()
            via = None
            if shutdown_token and token and token == shutdown_token:
                via = "token"
            elif client == "web":
                if not (self.headers.get("Origin") or self.headers.get("Referer")):
                    return self._send_json(403, {"ok": False,
                                                 "error": "网页刷新需要同源 Origin/Referer"})
                if not self._same_origin_ok():
                    return self._send_json(403, {"ok": False, "error": "跨站请求被拒绝"})
                via = "web"
            if via is None:
                return self._send_json(403, {"ok": False,
                                             "error": "缺少有效的 token（X-EFTMap-Token 不匹配）"})

            started, reason = spawn_live_fetch(root, app_dir, mode, settings=settings)
            if not started:
                return self._send_json(409, {"ok": False, "started": False, "mode": mode,
                                             "via": via, "error": "busy", "message": reason})
            return self._send_json(202, {"ok": True, "started": True, "mode": mode,
                                         "via": via, "message": reason})

        def _handle_flea_refresh(self):
            """`POST /api/prices/refresh`：页面手动刷新构建期跳蚤快照（本机 + 并发保护）。"""
            if not self._is_loopback_client():
                return self._send_json(403, {"ok": False, "error": "刷新行情只允许本机操作"})
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except (TypeError, ValueError):
                return self._send_json(400, {"ok": False, "error": "Content-Length 非法"}, close=True)
            if length < 0 or length > MAX_PREFS_BODY:
                return self._send_json(400, {"ok": False, "error": "请求体长度非法或过大"}, close=True)
            if length > 0:
                self.rfile.read(length)
            started, reason = spawn_flea_refresh(root, force=True)
            return self._send_json(202, {"ok": True, "started": started,
                                         "state": flea_price_status(root)["state"],
                                         "message": reason})

        def _handle_shutdown(self):
            """`POST /api/shutdown`：桌面壳带 token 关闭后端；缺 token 一律 403。"""
            token = (self.headers.get("X-EFTMap-Token") or "").strip()
            if not shutdown_token or token != shutdown_token:
                return self._send_json(403, {"ok": False, "error": "token 校验失败"})
            self._send_json(200, {"ok": True})
            if shutdown_callback is not None:
                try:
                    shutdown_callback()
                except Exception:
                    pass
            server = getattr(self, "server", None)
            if server is not None:
                threading.Thread(target=server.shutdown, daemon=True).start()

        # ---- 云账号（页面 <-> BFF）：错误一律回 {"ok": false, "code": ...} ----
        _CLOUD_POST_ROUTES = {
            "/api/cloud/login-preferences": ("set_login_preferences", ("remember_password", "auto_login", "email", "password")),
            "/api/cloud/login": ("login", ("email", "password")),
            "/api/cloud/login/verify": ("verify_login", ("email", "code", "challenge")),
            "/api/cloud/register": ("register", ("email", "password")),
            "/api/cloud/register/verify": ("verify_register", ("email", "code")),
            "/api/cloud/resend-verification": ("resend_verification", ("email",)),
            "/api/cloud/password/reset-request": ("request_password_reset", ("email",)),
            "/api/cloud/password/reset": ("reset_password", ("email", "code", "password")),
            "/api/cloud/password/change-request": ("request_password_change", ()),
            "/api/cloud/password/change": ("change_password", ("code", "password")),
            "/api/cloud/devices/remove": ("revoke_device", ("device_id",)),
            "/api/cloud/logout": ("logout", ()),
            "/api/cloud/redeem": ("redeem", ("code",)),
        }

        def _cloud_call(self, fn, *args, **kwargs):
            try:
                result = fn(*args, **kwargs)
            except cloud.CloudError as exc:
                code = exc.status if exc.status and 400 <= exc.status <= 599 else 502
                return self._send_json(code, exc.to_dict())
            except OSError as exc:
                return self._send_json(500, {"ok": False, "code": "io", "error": str(exc)})
            payload = dict(result) if isinstance(result, dict) else {"value": result}
            payload.setdefault("ok", True)
            return self._send_json(200, payload)

        def _read_cloud_body(self):
            """读 JSON 请求体；超过 MAX_CLOUD_BODY 直接 413（并把剩余字节读掉，避免连接错位）。"""
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except (TypeError, ValueError):
                length = 0
            if length <= 0:
                return {}
            if length > MAX_CLOUD_BODY:
                remaining = length
                while remaining > 0:
                    chunk = self.rfile.read(min(65536, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                self._send_json(413, {"ok": False, "code": "payload_too_large",
                                      "error": "请求体超过上限（%d 字节）" % MAX_CLOUD_BODY})
                return None
            try:
                data = json.loads(self.rfile.read(length).decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                self._send_json(400, {"ok": False, "code": "invalid_json", "error": "请求体不是合法 JSON"})
                return None
            return data if isinstance(data, dict) else {}

        def _handle_cloud_post(self, path):
            if path == "/api/cloud/sync":
                body = self._read_cloud_body()
                if body is None:
                    return
                values = body.get("values")
                if not isinstance(values, dict):
                    return self._send_json(400, {"ok": False, "code": "invalid_request",
                                                 "error": "values 必须是对象"})
                return self._cloud_call(cloud_client.sync, values, force=bool(body.get("force")))
            route = self._CLOUD_POST_ROUTES.get(path)
            if route is None:
                # 未知云接口不会解析请求体，不能在 keep-alive 上留下未读字节。
                return self._send_json(404, {"ok": False, "error": "未知接口：%s" % path}, close=True)
            name, keys = route
            body = self._read_cloud_body()
            if body is None:
                return
            return self._cloud_call(getattr(cloud_client, name), *[body.get(k) for k in keys])

        # ---- 预设（配装 / 配枪）：读写 tools/presets.py 的本地 JSON ----
        @staticmethod
        def _preset_error(exc) -> dict[str, Any]:
            payload: dict[str, Any] = {"ok": False, "code": exc.code, "error": str(exc)}
            if getattr(exc, "corrupt", False):
                payload["corrupt"] = True
            return payload

        def _handle_presets_get(self, query: str):
            from urllib.parse import parse_qs

            kind = (parse_qs(query).get("kind") or ["loadout"])[0]
            try:
                store = presets.load(kind, app_dir)
                path = presets.store_path(kind, app_dir)
            except presets.PresetError as exc:
                return self._send_json(409 if exc.corrupt else 400, self._preset_error(exc))
            return self._send_json(200, {"ok": True, "kind": kind, "path": path,
                                         "count": len(store["presets"]),
                                         "presets": store["presets"]})

        def _handle_presets_post(self):
            body = self._read_body(MAX_PRESET_BODY, "preset_payload_too_large")
            if body is None:
                return
            kind = body.get("kind")
            action = body.get("action") or "save"
            repair = bool(body.get("repair"))
            try:
                store = presets.empty_store(kind) if repair else presets.load(kind, app_dir)
            except presets.PresetError as exc:
                return self._send_json(409 if exc.corrupt else 400, self._preset_error(exc))
            items = list(store["presets"])
            rec = None
            try:
                if action == "save":
                    rec = presets.normalize_preset(kind, body.get("preset"))
                    for i, cur in enumerate(items):
                        if cur.get("id") == rec.get("id"):
                            items[i] = rec
                            break
                    else:
                        items.insert(0, rec)
                elif action == "delete":
                    pid = body.get("id")
                    remain = [p for p in items if p.get("id") != pid]
                    if len(remain) == len(items):
                        return self._send_json(400, {"ok": False, "code": "missing",
                                                     "error": "没有这个预设"})
                    items = remain
                elif action == "import":
                    rec = presets.normalize_preset(kind, body.get("data"))
                    if any(p.get("id") == rec.get("id") for p in items):
                        rec["id"] = presets.new_id(kind)
                    items.insert(0, rec)
                elif action == "replace":
                    # R233：会员云同步下发的预设整包。只接受数组，交给下面统一的
                    # presets.save 走逐条归一化校验 + 原子写回；本地文件仍是第一事实源，
                    # 磁盘文件损坏时 save 会拒绝覆盖（不静默冲掉数据）。
                    incoming = body.get("presets")
                    if not isinstance(incoming, list):
                        raise presets.PresetError("replace 需要 presets 数组", code="invalid")
                    items = list(incoming)
                else:
                    return self._send_json(400, {"ok": False, "code": "action",
                                                 "error": "未知操作：%s" % action})
                saved = presets.save(kind, dict(store, presets=items), app_dir, repair=repair)
            except presets.PresetError as exc:
                return self._send_json(400, self._preset_error(exc))
            except OSError as exc:
                return self._send_json(500, {"ok": False, "code": "io", "error": str(exc)})
            payload: dict[str, Any] = {"ok": True, "kind": kind, "action": action,
                                       "count": len(saved["presets"]),
                                       "path": presets.store_path(kind, app_dir),
                                       "presets": saved["presets"]}
            if rec is not None:
                payload["preset"] = rec
            return self._send_json(200, payload)

        def _read_body(self, limit: int, code: str):
            """读 JSON 请求体；超过 limit 回 413（读掉剩余字节，避免连接错位）。"""
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except (TypeError, ValueError):
                length = 0
            if length <= 0:
                return {}
            if length > limit:
                remaining = length
                while remaining > 0:
                    chunk = self.rfile.read(min(65536, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                self._send_json(413, {"ok": False, "code": code,
                                      "error": "请求体超过上限（%d 字节）" % limit})
                return None
            try:
                data = json.loads(self.rfile.read(length).decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                self._send_json(400, {"ok": False, "code": "invalid_json", "error": "请求体不是合法 JSON"})
                return None
            return data if isinstance(data, dict) else {}

        def _send_json(self, code: int, payload: dict, close: bool = False):
            body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
            self._send_cache_header()
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            if close:
                # 无法安全判断请求体长度（超限 / Content-Length 非法）时才关连接
                self.close_connection = True
                self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)

        def _serve_sound(self, rel: str):
            """提供软件目录 `sounds/` 下的自定义提示音；拒绝越权路径与目录请求。"""
            base = os.path.realpath(config.sounds_dir(app_dir))
            target = os.path.realpath(os.path.join(base, rel))
            if not target.startswith(base + os.sep) or not os.path.isfile(target):
                return self._send_json(404, {"ok": False, "error": "音频文件不存在：%s" % rel})
            ctype = EXTRA_TYPES.get(os.path.splitext(target)[1].lower()) \
                or mimetypes.guess_type(target)[0] or "application/octet-stream"
            with open(target, "rb") as fh:
                body = fh.read()
            self._send_cache_header()
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _serve_events(self):
            """SSE：连上先推当前状态，之后有变化就推，另加心跳注释保持连接。

            帧有两种：位置是**无名帧**（前端 onmessage 收），其余是命名事件
            `config` / `state` / `raid` / `quest`（前端 addEventListener 各自订阅）。
            无 Content-Length，因此按 HTTP/1.1 规范用 `Connection: close` 把「流到连接关闭为止」
            表达清楚（不能用 chunked，标准库的分块编码会把每帧再包一层长度前缀）。
            """
            self._send_cache_header()
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()

            q = tracker.broadcaster.subscribe()
            try:
                self._write_frame(tracker.snapshot())
                self._write_event("config", config_payload(app_dir))
                if follower is not None:
                    self._write_event("state", follower.snapshot())
                if shotter is not None:
                    self._write_event("shot", shotter.snapshot())
                if pruner is not None:
                    self._write_event("clean", pruner.snapshot())
                # R-fix：把当前主窗口选中的地图也推给刚连上的小地图窗口，
                # 这样即使它错过之前的 `map` 广播，也能立刻对齐到主界面当前地图。
                active = getattr(self.server, "active_map", None)
                if active:
                    self._write_event("map", {"map": active})
                last_beat = time.monotonic()
                while True:
                    try:
                        item = q.get(timeout=1.0)
                    except queue.Empty:
                        item = None
                    if isinstance(item, tuple):
                        self._write_event(item[0], item[1])
                    elif item is not None:
                        self._write_frame(item)
                    if time.monotonic() - last_beat >= SSE_HEARTBEAT:
                        last_beat = time.monotonic()
                        self.wfile.write(b": ping\n\n")
                        self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                pass          # 页面关了就正常收摊
            finally:
                tracker.broadcaster.unsubscribe(q)

        def _write_frame(self, payload: dict):
            data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            self.wfile.write(b"data: " + data + b"\n\n")
            self.wfile.flush()

        def _write_event(self, name: str, payload: dict):
            data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            self.wfile.write(b"event: " + name.encode("ascii") + b"\ndata: " + data + b"\n\n")
            self.wfile.flush()

    return Handler


def list_sounds(app_dir: str) -> list[str]:
    """软件目录 `sounds/` 里已有的音频文件名（启动器与页面共用）。"""
    directory = config.sounds_dir(app_dir)
    try:
        names = os.listdir(directory)
    except OSError:
        return []
    return sorted(n for n in names if n.lower().endswith(config.AUDIO_EXTS))


def health_payload(root: str, tracker: PositionTracker | None = None,
                   follower: eftlog.LogFollower | None = None,
                   shotter: AutoShotter | None = None,
                   pruner: ScreenshotPruner | None = None) -> dict[str, Any]:
    status = data_status(root)
    ocr_ok, ocr_hint = ocr.check_available()
    payload = {
        "ok": bool(status["ready"]),
        "app": APP_ID,
        "version": VERSION,
        "rev": "R19.97-" + build_digest(root),
        "root": root,
        "data": status,
        "position": bool(tracker and tracker.enabled()),
        "logs": bool(follower and follower.enabled()),
        "ocr": {"available": bool(ocr_ok), "hint": ocr_hint},
    }
    if tracker is not None:
        snap = tracker.snapshot()
        payload["positionAvailable"] = snap["available"]
        payload["screenshots"] = tracker.directory
    if follower is not None:
        payload["gameDir"] = follower.game_dir
        payload["logDir"] = follower.logs_dir
        payload["logSession"] = follower.snapshot()["session"]
    if shotter is not None:
        payload["shot"] = shotter.snapshot()
    if pruner is not None:
        payload["clean"] = pruner.snapshot()
    return payload


class _Server(ThreadingHTTPServer):
    """禁用地址复用：Windows 下 SO_REUSEADDR 会让端口占用检测失效。"""

    daemon_threads = True
    allow_reuse_address = False

    def server_close(self):
        # 关闭服务时一并停掉截图 / 日志 / 配置 / 自动截图 / 自动删除监听线程，避免残留轮询
        for name in ("tracker", "follower", "watcher", "shotter", "pruner"):
            watcher_obj = getattr(self, name, None)
            if watcher_obj is not None:
                watcher_obj.stop()
        super().server_close()


def create_server(port: int = DEFAULT_PORT, host: str = DEFAULT_HOST, root: str | None = None,
                  screenshots: str | None = None, poll_interval: float = DEFAULT_POLL,
                  config_dir: str | None = None, game_dir: str | None = None,
                  detect_paths: bool = False, shutdown_token: str | None = None,
                  shutdown_callback=None, shell_mode: bool = False) -> ThreadingHTTPServer:
    """创建（已 listen 的）HTTP 服务对象。

    port=0 表示由系统分配空闲端口，便于测试。
    `screenshots=None` 表示**不开启**实时定位，`game_dir=None` 表示**不开启**日志监控
    （测试与无对应目录的场景走这两条路），传入目录才启动监听线程。
    `config_dir` 是配置与 `sounds/` 的落盘位置，默认软件目录。
    `detect_paths=True` 时（启动器路径）截图目录没给就自动探测候选目录；
    游戏目录不做二次探测，避免把用户清空的目录又顶回来。
    `shutdown_token` / `shutdown_callback` 供桌面壳 Secure 关闭后端。
    """
    root = os.path.abspath(root or ROOT)
    if not os.path.isfile(os.path.join(root, "index.html")):
        raise FileNotFoundError("根目录里找不到 index.html：%s\n请用 --root 指向仓库根目录。" % root)

    if detect_paths and screenshots is None:
        screenshots, _note = detect_screenshots_dir(game_dir)

    app_dir = os.path.abspath(config_dir) if config_dir else os.path.abspath(config.default_storage_dir())
    if not config_dir:
        config.migrate_legacy(app_dir, config.app_dir())   # 旧软件目录里的配置首次搬到用户目录
    broadcaster = Broadcaster()
    manifest = ShotManifest(app_dir)
    cleaner = RaidEndCleaner(app_dir, manifest, directory=screenshots)
    # 会员门控读实时配置：页面里切换会员/账号后，无需重启服务
    tracker = PositionTracker(screenshots, poll_interval, broadcaster,
                              member=lambda: config.is_member(app_dir))
    # R-fix：动态解析日志目录。配置（启动器写入的 game_dir）或默认自动探测任一就绪即启用
    # 跟随，避免「启动时目录还没就位 / 启动器后写配置 / 游戏后安装」导致监控彻底不开。
    _logs_probe = {"at": 0.0, "dir": None}

    def _log_dir_getter():
        """每轮返回当前应跟随的 Logs 目录：在全部候选里挑「会话名最新」的一个。

        旧实现只认 ``game_dir/Logs``，但 EFT 常把真正的应用日志写到
        ``%LOCALAPPDATA%\\Temp\\Battlestate Games\\EFT\\Logs``。硬取前者会一直跟随
        数周前的旧会话，LogFollower 的战局阶段永远停在 ``end``，自动截图因此永不
        触发（实测：game_dir/Logs 停在 11/02，实际会话在 11/15）。
        轮询很密，扫描结果缓存 3 秒；新会话出现后最多 3 秒即切换。
        """
        now = time.monotonic()
        if now - _logs_probe["at"] < 3.0:
            return _logs_probe["dir"]
        g = game_dir
        if not g:
            try:
                g = (config.load(app_dir) or {}).get("game_dir")
            except Exception:
                g = None
        if not g:
            g = default_game_dir()
        primary = os.path.join(g, "Logs") if g else None
        alternatives: list[str] = []
        for docs in _documents_dirs():
            alternatives.append(os.path.join(docs, "Escape from Tarkov", "Logs"))
        local = os.environ.get("LOCALAPPDATA")
        if local:
            alternatives.append(os.path.join(local, "Temp", "Battlestate Games", "EFT", "Logs"))
        _logs_probe.update(at=now, dir=best_logs_dir(primary, alternatives))
        return _logs_probe["dir"]
    follower = eftlog.LogFollower(game_dir, poll_interval, broadcaster,
                                  on_event=cleaner.on_event, log_dir_getter=_log_dir_getter)
    watcher = ConfigWatcher(app_dir, poll_interval, broadcaster)
    shotter = AutoShotter(app_dir, follower, broadcaster, directory=screenshots,
                          game_dir=game_dir, manifest=manifest)
    pruner = ScreenshotPruner(screenshots, app_dir, broadcaster, poll_interval)
    handler = build_handler(root, tracker, follower, app_dir, shotter, pruner,
                            shutdown_token=shutdown_token,
                            shutdown_callback=shutdown_callback)
    try:
        httpd = _Server((host, port), handler)
    except OSError as exc:
        if _is_addr_in_use(exc):
            raise PortInUseError(
                "端口 %d 已被占用。请关闭占用该端口的程序，或用 --port 换一个端口（如 --port 8788）。" % port
            ) from exc
        raise
    httpd.tracker = tracker       # type: ignore[attr-defined]
    httpd.follower = follower     # type: ignore[attr-defined]
    httpd.watcher = watcher       # type: ignore[attr-defined]
    httpd.shotter = shotter       # type: ignore[attr-defined]
    httpd.pruner = pruner         # type: ignore[attr-defined]
    httpd.app_dir = app_dir       # type: ignore[attr-defined]
    httpd.shell_mode = bool(shell_mode)  # type: ignore[attr-defined]
    httpd.active_map = None       # type: ignore[attr-defined]
    tracker.start()
    follower.start()
    watcher.start()
    shotter.start()
    pruner.start()
    return httpd


def url_for(host: str, port: int) -> str:
    shown = "127.0.0.1" if host in ("", "0.0.0.0") else host
    return "http://%s:%d/" % (shown, port)


def lan_address() -> str | None:
    """取本机局域网 IPv4（取不到返回 None）。

    只做本机名字解析，不发任何网络包；解析结果里的回环 / 链路本地地址一律跳过。
    """
    try:
        infos = socket.gethostbyname_ex(socket.gethostname())[2]
    except (OSError, UnicodeError, ValueError):
        return None
    for ip in infos:
        if not ip or ip.count(".") != 3:
            continue
        if ip.startswith("127.") or ip.startswith("169.254."):
            continue
        return ip
    return None


def url_for_lan(port: int) -> str | None:
    """监听 `0.0.0.0` 时给用户的局域网访问地址；探测不到就返回 None。"""
    ip = lan_address()
    if not ip:
        return None
    return "http://%s:%d/" % (ip, port)


def lan_hint(host: str, port: int) -> str | None:
    """根据监听地址生成「怎么让手机/平板访问」的提示；仅本机监听时返回 None。"""
    if host not in ("0.0.0.0", "::", ""):
        return None
    lan = url_for_lan(port)
    if not lan:
        return "已监听所有网卡，但未探测到局域网地址；手机/平板暂时无法访问。"
    return "局域网访问：%s（若打不开，请在 Windows 防火墙里允许本程序）" % lan


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="EFT 互动地图本地服务（静态站点 + 健康检查 + 实时定位 + 日志监控）")
    parser.add_argument("--host", default=DEFAULT_HOST, help="监听地址，默认 %s（仅本机可访问）" % DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="监听端口，默认 %d；0 表示自动分配" % DEFAULT_PORT)
    parser.add_argument("--root", default=None, help="站点根目录，默认仓库根目录")
    parser.add_argument("--screenshots", default=None,
                        help="EFT 截图目录；不给则用默认位置 %s" % default_screenshots_dir())
    parser.add_argument("--no-position", action="store_true", help="关闭实时定位（不监听截图目录）")
    parser.add_argument("--game-dir", default=None,
                        help="EFT 游戏目录（含 Logs）；不给则用配置或自动定位")
    parser.add_argument("--config-dir", default=None, help="配置文件与 sounds/ 的落盘目录，默认软件目录")
    parser.add_argument("--no-logs", action="store_true", help="关闭游戏日志监控（不自动切图/统计任务）")
    parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    return parser.parse_args(argv)


def resolve_screenshots(args) -> str | None:
    """CLI 参数 → 实际要监听的目录：--no-position 关掉，否则用给定值或默认位置。"""
    if args.no_position:
        return None
    if args.screenshots:
        return args.screenshots
    default = default_screenshots_dir()
    return default if os.path.isdir(default) else None


def resolve_settings(args) -> dict[str, Any]:
    """CLI 参数 + 配置文件 → 运行期实际使用的目录与配置。

    优先级：命令行显式给出 > 配置文件 > 自动定位（仅当配置文件里也没写时）。
    自动定位的结果**不会**回写配置文件——只有用户在启动器里确认过才落盘。
    """
    app_dir = os.path.abspath(args.config_dir) if args.config_dir else os.path.abspath(config.default_storage_dir())
    if not args.config_dir:
        config.migrate_legacy(app_dir, config.app_dir())
    cfg = config.load(app_dir)

    game_dir = args.game_dir or cfg.get("game_dir")
    if args.no_logs:
        game_dir = None
    elif not game_dir:
        game_dir = default_game_dir()
    if game_dir and not os.path.isdir(game_dir):
        game_dir = None

    screenshots = args.screenshots or cfg.get("screenshots_dir")
    if args.no_position:
        screenshots = None
    elif not screenshots:
        screenshots = default_screenshots_dir()
    if screenshots and not os.path.isdir(screenshots):
        screenshots = None

    return {"app_dir": app_dir, "config": cfg, "game_dir": game_dir, "screenshots": screenshots}


def start_ocr_host(url: str, config_dir: str | None = None):
    """R309：源码模式（`启动项目.bat` → serve.py）也要拉起截图识别宿主。

    R308 之后双击 bat 只启动 serve.py，而宿主（tools/scan.py，负责全局热键
    → 框选 → 透明浮窗）原来只由 launcher.py 拉起——源码模式下按热键
    自然毫无反应。这里在服务 listen 之后补上 spawn：宿主会先探 /api/health，
    且自带命名互斥量，已有宿主时新起的这个会自行退出。
    `EFT_OCR_HOST=0` 可整体关掉（排查 / 自动化测试用）。
    """
    if (os.environ.get("EFT_OCR_HOST") or "").strip().lower() in {"0", "off", "false", "no"}:
        return None
    script = os.path.join(ROOT, "tools", "scan.py")
    if not os.path.isfile(script):
        return None
    kwargs: dict[str, Any] = {"cwd": ROOT}
    if getattr(sys, "frozen", False):
        # 冻结产物里 sys.executable 是 EFTMap.exe；宿主由 --run-tool 在同一套依赖里跑
        cmd = [sys.executable, "--run-tool", script, "--server", url]
        kwargs.update({"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
                       "stdin": subprocess.DEVNULL})
        if os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    else:
        # 源码模式共享 bat 的控制台：宿主异常时 traceback 能直接看到
        cmd = [sys.executable, script, "--server", url]
    if config_dir:
        cmd += ["--config-dir", config_dir]   # 热键等偏好要与当前服务读同一份配置
    try:
        return subprocess.Popen(cmd, **kwargs)
    except OSError:
        return None


def main(argv=None) -> int:
    args = parse_args(argv)
    settings = resolve_settings(args)
    try:
        httpd = create_server(args.port, args.host, args.root, screenshots=settings["screenshots"],
                              config_dir=settings["app_dir"], game_dir=settings["game_dir"])
    except PortInUseError as exc:
        print("[错误] %s" % exc, file=sys.stderr)
        return 2
    except FileNotFoundError as exc:
        print("[错误] %s" % exc, file=sys.stderr)
        return 3

    url = url_for(args.host, httpd.server_address[1])
    print("EFT 互动地图已启动：%s" % url)
    if settings["screenshots"]:
        print("实时定位：监听截图目录 %s" % settings["screenshots"])
    else:
        print("实时定位：未开启（截图目录不可用或已用 --no-position 关闭）")
    if settings["game_dir"]:
        print("日志监控：跟随游戏目录 %s\\Logs（自动切图 + 任务事件）" % settings["game_dir"])
    else:
        print("日志监控：未开启（游戏目录不可用或已用 --no-logs 关闭）")
    print("自动截图：%s（在启动器里开关与设置间隔 / 按键）" % ("已开启" if httpd.shotter.snapshot()["enabled"] else "未开启"))
    print("自动删除截图：%s（在启动器里开关；只删开启后产生、且已读过位置的旧截图）"
          % ("已开启" if httpd.pruner.snapshot()["enabled"] else "未开启"))
    print("配置文件：%s" % config.config_path(settings["app_dir"]))
    ocr_host = start_ocr_host(url, settings["app_dir"])
    if ocr_host is not None:
        print("截图识别：已在后台启动（热键见「小工具 → 价格识别」）")
    print("按 Ctrl+C 停止服务。")
    if not args.no_browser:
        webbrowser.open(url)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
    finally:
        httpd.server_close()
        if ocr_host is not None and ocr_host.poll() is None:
            ocr_host.terminate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
