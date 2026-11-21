#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R237：构建 OCR 物品短名表（data/ocr-item-names.json）。

背景（用户实测，2026-11-11）：游戏内物品显示的是**短名**（ComTac VI / EXFIL /
OTV / Specter / 布洛芬 / 止血剂…），而 items.json 的 `sn` 在构建期上游全部退化成
"<id> ShortName" 占位符，OCR 匹配索引只有全名 → 短名对不上就模糊串到别的物品
（实测 Specter→Aspect 钥匙、T30→丰和基座）。

本脚本从 tarkov.dev 拉两份数据补齐（一次性，运行期不联网）：
  · https://json.tarkov.dev/regular/items   → item.shortName（EN 短名）
  · https://json.tarkov.dev/regular/items_zh → `<id> ShortName`（中文本地化短名）
输出 data/ocr-item-names.json：
  {"schema": 1, "fetchedAt": iso, "count": n,
   "names": {item_id: {"en": str|null, "zh": str|null}}}

tools/ocr.py 的 ItemMatcher 会把这两类短名一并索引进键表；
serve.py 按 mtime 缓存，文件更新即生效。

用法：
    python tools/build_ocr_names.py            # 走系统网络（可用代理环境变量）
    python tools/build_ocr_names.py --proxy http://127.0.0.1:7896
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

OUT_PATH = os.path.join(ROOT, "data", "ocr-item-names.json")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--proxy", default=None, help="如 http://127.0.0.1:7896（fetch 走环境变量时可不传）")
    ap.add_argument("--force", action="store_true", help="忽略 build-cache 强制重下")
    ap.add_argument("--timeout", type=int, default=300)
    a = ap.parse_args()

    if a.proxy:
        os.environ["http_proxy"] = a.proxy
        os.environ["https_proxy"] = a.proxy

    # 复用 fetch_data 的抓取器（UA 变体 + curl 回退 + build-cache），Cloudflare 稳过
    import fetch_data as fd

    print("加载 EN items（约 17 MB，build-cache 可复用）…")
    items_doc, _raw = fd.load_json_cached(
        fd.ITEMS_URL.format(mode="regular"), "items-regular.json",
        force=a.force, timeout=a.timeout)
    items = items_doc["data"]["items"] if isinstance(items_doc, dict) else items_doc
    if isinstance(items, dict):          # 上游 items 是 {id: item} 字典
        items = list(items.values())
    print("  %d 条" % len(items))

    print("加载中文本地化 items_zh …")
    zh_doc, _raw = fd.load_json_cached(
        fd.ITEMS_ZH_URL.format(mode="regular"), "items-zh-regular.json",
        force=a.force, timeout=a.timeout)
    zh = zh_doc.get("data") if isinstance(zh_doc, dict) else zh_doc
    if not isinstance(zh, dict):
        zh = {}
    print("  %d 条键" % len(zh))

    names: dict[str, dict] = {}
    for item in items:
        iid = item.get("id")
        if not iid:
            continue
        en = item.get("shortName")
        # 上游 EN 数据的 shortName 字段被 "<id> ShortName" 占位符污染，视为无效；
        # 真实短名来自 items_zh 翻译表的 `<id> ShortName`（游戏中文界面显示的正是它）。
        if isinstance(en, str) and en.strip() and not en.strip().endswith(" ShortName"):
            entry_en = en.strip()
        else:
            entry_en = None
        zh_short = zh.get("%s ShortName" % iid)
        zh_val = zh_short.strip() if isinstance(zh_short, str) and zh_short.strip() else None
        if zh_val and zh_val.endswith(" ShortName"):
            zh_val = None
        entry = {"en": entry_en, "zh": zh_val}
        if entry["en"] or entry["zh"]:
            names[iid] = entry

    doc = {
        "schema": 1,
        "fetchedAt": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "source": "tarkov.dev items + items_zh（R237 OCR 短名表）",
        "count": len(names),
        "names": names,
    }
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    tmp = OUT_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False)
    os.replace(tmp, OUT_PATH)
    both = sum(1 for v in names.values() if v["en"] and v["zh"])
    en_only = sum(1 for v in names.values() if v["en"] and not v["zh"])
    zh_only = sum(1 for v in names.values() if v["zh"] and not v["en"])
    print("写出 %s：%d 条（en+zh %d / 仅 en %d / 仅 zh %d）"
          % (OUT_PATH, len(names), both, en_only, zh_only))
    return 0


if __name__ == "__main__":
    sys.exit(main())
