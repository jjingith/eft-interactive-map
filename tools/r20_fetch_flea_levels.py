# -*- coding: utf-8 -*-
"""R20.6b：生成「跳蚤市场最低上架等级」sidecar 数据（data/flea-levels.json）。

背景：tarkov.dev 原始响应里每件物品都有 `minLevelForFlea`（上架跳蚤市场所需的解锁等级），
但本项目 `data/items.json` 归一化时没有保留该字段。为了**不改动 items.json 的 sha256 契约**，
这里单独生成一个小 sidecar 文件，运行期只读本地文件、不联网。

数据事实（2026-10-29 抓取 https://json.tarkov.dev/regular/items；2026-11-04 复核）：
  上游路径键 `regular` 对应 **PvP（常规）**，不是 PvE（详见 docs/r42-live-prices-ledger.md）。
  5480 件物品全部带 minLevelForFlea，取值只有 0 / 20 / 25 / 30 / 35 / 40。
  0 = 无限制，可自由上架。PvE 的解锁等级需另抓 `/pve/items`，本文件只代表 PvP。

用法：
  python tools/r20_fetch_flea_levels.py                 # 抓取并原子写入 data/flea-levels.json
  python tools/r20_fetch_flea_levels.py --dry-run       # 只打印统计，不写盘
  python tools/r20_fetch_flea_levels.py --force         # 当天已生成也重新抓
  python tools/r20_fetch_flea_levels.py --proxy http://127.0.0.1:7896
"""
import argparse
import collections
import datetime
import json
import os
import sys
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SOURCE = "https://json.tarkov.dev/regular/items"
DEFAULT_OUT = os.path.join(ROOT, "data", "flea-levels.json")
FIELD = "minLevelForFlea"
MIN_ITEMS = 1000            # 上游实测 5480；低于这个数视为响应不完整


def http_get(url, proxy=None, timeout=90):
    handlers = []
    if proxy:
        handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    else:
        handlers.append(urllib.request.ProxyHandler({}))     # 显式不使用环境代理，避免走错端口
    op = urllib.request.build_opener(*handlers)
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/156.0.0.0 Safari/537.36",
        "Accept": "application/json",
    })
    with op.open(req, timeout=timeout) as r:
        return r.read()


def write_atomic(path, data_bytes):
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data_bytes)
    os.replace(tmp, path)


def extract(doc):
    """从上游响应取 items 字典（实测结构 {"data": {"items": {...}, ...}, "translations": ...}）。"""
    if not isinstance(doc, dict):
        raise ValueError("上游响应不是对象")
    data = doc.get("data")
    if not isinstance(data, dict):
        raise ValueError("上游响应缺少 data")
    items = data.get("items")
    if not isinstance(items, dict):
        raise ValueError("上游响应缺少 data.items")
    return items


def build(levels_by_id, source):
    cnt = collections.Counter(levels_by_id.values())
    return {
        "schema": 1,
        "source": source,
        "sourceType": "tarkov.dev public JSON (items /regular = PvP)",
        "field": FIELD,
        # regular 是上游路径键，真实游戏模式是 PvP；PvE 需单独抓 /pve/items
        "gameMode": "regular",
        "gameModeSemantics": "上游路径键 regular(PvP)；不同游戏模式的跳蚤解锁等级可能不同",
        "priceMode": "pvp",
        "modeLabel": "PvP（常规）",
        "modeNote": ("上游路径键 regular 的真实游戏模式是 PvP（常规），不是 PvE。"
                     "PvE 的跳蚤解锁等级需另抓 https://json.tarkov.dev/pve/items，"
                     "两套数据不混写；本文件只代表 PvP。"),
        "fetchedAt": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "note": ("跳蚤市场上架所需的玩家等级；0 = 无限制。"
                 "该字段来自 tarkov.dev 上游原始响应，本项目的 items.json 未保留它，故单独成文件；"
                 "运行期只读本地，不联网。"),
        "counts": {
            "total": len(levels_by_id),
            "noRestriction": cnt.get(0, 0),
            "restricted": len(levels_by_id) - cnt.get(0, 0),
        },
        "levels": {str(k): v for k, v in sorted(cnt.items())},
        "items": {k: v for k, v in sorted(levels_by_id.items())},
    }


def main():
    ap = argparse.ArgumentParser(description="生成跳蚤上架等级 sidecar 数据")
    ap.add_argument("--source", default=DEFAULT_SOURCE)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--proxy", default=os.environ.get("DB4_PROXY", "http://127.0.0.1:7896"))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    out = os.path.abspath(args.out)
    today = datetime.datetime.now().astimezone().strftime("%Y-%m-%d")

    # 当天已生成过就跳过（与行情缓存同一套「一天一次」纪律）
    if not args.force and os.path.isfile(out):
        try:
            with open(out, "r", encoding="utf-8") as fh:
                old = json.load(fh)
            if str(old.get("fetchedAt", ""))[:10] == today:
                print("[skip] %s 已是今天生成的（%s，%d 件）"
                      % (os.path.basename(out), old.get("fetchedAt"), len(old.get("items") or {})))
                return 0
        except Exception:  # noqa: BLE001
            pass

    try:
        raw = http_get(args.source, proxy=args.proxy or None)
        doc = json.loads(raw.decode("utf-8"))
        items = extract(doc)
    except (urllib.error.URLError, ValueError, OSError) as e:
        print("[error] 抓取或解析失败：%s: %s" % (type(e).__name__, e))
        return 2

    total = len(items)
    if total < MIN_ITEMS:
        keys = list(doc.keys())[:6] if isinstance(doc, dict) else []
        sample = json.dumps(doc, ensure_ascii=False)[:200]
        print("[error] 上游物品数异常（%d < %d）；顶层键=%s；载荷样本=%s"
              % (total, MIN_ITEMS, keys, sample))
        return 2

    levels = {}
    missing = 0
    for iid, rec in items.items():
        if not isinstance(rec, dict):
            missing += 1
            continue
        lv = rec.get(FIELD)
        if not isinstance(lv, int) or lv < 0:
            missing += 1
            continue
        levels[iid] = lv

    if len(levels) < MIN_ITEMS:
        print("[error] 有效等级记录过少（%d），疑似上游字段变更，拒绝写入" % len(levels))
        return 2

    payload = build(levels, args.source)
    if missing:
        payload["counts"]["missingField"] = missing

    cnt = payload["levels"]
    print("[ok] 物品 %d 件；等级分布 %s；无限制 %d 件"
          % (len(levels), cnt, payload["counts"]["noRestriction"]))
    if args.dry_run:
        print("[dry-run] 不写盘")
        return 0

    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    write_atomic(out, body)
    print("[write] %s（%.1f KB）" % (out, len(body) / 1024.0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
