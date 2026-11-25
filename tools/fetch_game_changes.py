"""把官方补丁公告抓成随包快照：`data/game-changes.json`。

页面本身会优先读 `%APPDATA%\\EFTMap\\game-changes\\news.json`（用户点「检查更新」后
产生的缓存），没有缓存时才用这份内置快照。所以**每次发版前跑一次**，让新装用户
在完全离线的情况下也能看到最近的补丁说明。

用法：
    python tools/fetch_game_changes.py                 # 直接抓 Steam 官方公告
    python tools/fetch_game_changes.py --from FILE     # 用已保存的 ISteamNews JSON
    python tools/fetch_game_changes.py --check         # 只报告差异，不写文件
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import serve  # noqa: E402


def _entries_from_file(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    items = ((data.get("appnews") or {}).get("newsitems") or [])
    entries = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if str(item.get("feedname") or "") != "steam_community_announcements":
            continue
        entry = serve._patch_entry(item)
        if entry:
            entries.append(entry)
    entries.sort(key=lambda e: e["timestamp"], reverse=True)
    return entries


def main(argv=None) -> int:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_path = os.path.join(root, "data", "game-changes.json")

    parser = argparse.ArgumentParser(description="生成随包的游戏更新快照")
    parser.add_argument("--from", dest="source", default=None,
                        help="本地 ISteamNews JSON（不给则直连 Steam）")
    parser.add_argument("--check", action="store_true", help="只比较，不写文件")
    parser.add_argument("--if-changed", action="store_true",
                        help="条目没有变化时不写文件（定时任务用，避免只改 generated_at 也产生提交）")
    args = parser.parse_args(argv)

    entries = _entries_from_file(args.source) if args.source else serve.fetch_game_changes()
    if not entries:
        print("没有解析到任何补丁条目")
        return 1

    old = {}
    old_entries = []
    if os.path.isfile(out_path):
        try:
            with open(out_path, encoding="utf-8") as handle:
                old_entries = json.load(handle).get("entries") or []
                old = {e["id"]: e for e in old_entries}
        except (OSError, ValueError):
            old = {}
            old_entries = []
    if args.if_changed:
        canon = lambda rows: json.dumps(rows, ensure_ascii=False, sort_keys=True)
        if canon(old_entries) == canon(entries):
            print("补丁条目没有变化，不写文件")
            return 0
    added = [e for e in entries if e["id"] not in old]
    print("解析到 %d 个版本，其中 %d 个是新增：" % (len(entries), len(added)))
    for entry in entries[:12]:
        mark = "NEW " if entry["id"] not in old else "    "
        print("  %s%-10s %s  %2d 条" % (mark, entry["version"], entry["date"], entry["bullets"]))
    if args.check:
        return 0

    payload = {
        "generated_at": serve.time.strftime("%Y-%m-%d %H:%M"),
        "source": "steam-official-announcements",
        "source_url": serve.GAME_NEWS_HOME,
        "entries": entries,
    }
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    temp = out_path + ".tmp"
    with open(temp, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=1)
        handle.write("\n")
    os.replace(temp, out_path)
    print("已写入 %s（%.1f KB）" % (out_path, os.path.getsize(out_path) / 1024))
    return 0


if __name__ == "__main__":
    sys.exit(main())
