# -*- coding: utf-8 -*-
"""R20.8：Electron `app.asar` 只读解包（脱壳取证用，不修改原归档）。

asar 是 Chromium Pickle 打包的归档，布局：

  [0:4]    uint32 = 4              sizeBuf 的 payload 长度（固定）
  [4:8]    uint32 = headerBuf 总长度
  [8:12]   uint32 = headerBuf 的 payload 长度
  [12:16]  uint32 = 8              headerBuf 的 pickle 头长度
  [16 …]   headerBuf payload = [uint32 json 长度][json bytes][padding]
  [数据区]  各文件按 header 里的 offset（相对数据区起点 = 8 + headerBuf 总长度）存放

用法：
    python tools/r208_unpack_asar.py                 # 解到默认输出目录
    python tools/r208_unpack_asar.py --out <dir>     # 指定输出目录
    python tools/r208_unpack_asar.py --list          # 只列顶层结构，不落盘
"""
from __future__ import annotations

import argparse
import json
import os
import struct
import sys

CLIENT = r"D:\personal\trae\02-塔科夫\逆向参考\tarkov.kaedeori\tarkov-kaedeori-client"
DEFAULT_SRC = os.path.join(CLIENT, "resources", "app.asar")
DEFAULT_OUT = r"D:\personal\trae\02-塔科夫\逆向参考\tarkov.kaedeori\extracted\app"

# 与地图 / 任务相关的关键词（只用于 --scan 统计，不做任何改写）
MAP_KEYS = ("map", "maps", "extract", "extracts", "transit", "spawn", "boss",
            "loot", "container", "世界", "地图", "撤离", "刷新", "boss", "钥匙")
QUEST_KEYS = ("quest", "quests", "task", "tasks", "trader", "traders",
              "objective", "reward", "任务", "商人", "奖励", "目标")


def read_header(f):
    head = f.read(16)
    if len(head) < 16:
        raise SystemExit("文件太小，不是 asar 归档")
    magic, buf_len, payload_len, pickle_hdr = struct.unpack("<IIII", head)
    if magic != 4:
        raise SystemExit("asar 头 magic 不是 4（实际 %d），格式可能不同" % magic)
    f.seek(16)
    payload = f.read(payload_len)
    # 实测：JSON 从 payload 起始处直接开始，不是「4 字节长度前缀 + 字符串」——
    # pickle 的 writeString 在这里落的是原始字节；尾部是 4/8 字节对齐 padding，
    # 所以必须 raw_decode 只取第一个完整 JSON 值，不能用 json.loads 整段。
    header, _ = json.JSONDecoder().raw_decode(payload.decode("utf-8", "replace"))
    data_base = 8 + buf_len
    return header, data_base


def walk(node, prefix, out, f, data_base, stat):
    for name, ent in (node.get("files") or {}).items():
        # Windows 非法文件名兜底，避免整包解包因一个坏名中断
        safe = "".join(c for c in name if c not in '<>:"|?*\\/') or "_"
        p = os.path.join(prefix, safe)
        try:
            if ent.get("files"):
                os.makedirs(p, exist_ok=True)
                walk(ent, p, out, f, data_base, stat)
                stat["dirs"] += 1
            elif ent.get("link"):
                stat["links"] += 1          # 符号链接：不落盘（Windows 上无意义）
            else:
                os.makedirs(os.path.dirname(p), exist_ok=True)
                off, size = ent.get("offset"), int(ent.get("size", 0) or 0)
                if off is None or size <= 0:
                    open(p, "wb").close()
                else:
                    f.seek(data_base + int(off))
                    open(p, "wb").write(f.read(size))
                stat["files"] += 1
                stat["bytes"] += size
                low = (p + "|" + safe).lower()
                if any(k in low for k in MAP_KEYS):
                    stat["mapHits"].append(os.path.relpath(p, out))
                if any(k in low for k in QUEST_KEYS):
                    stat["questHits"].append(os.path.relpath(p, out))
        except Exception as exc:  # noqa: BLE001 - 单文件失败不中断整包
            stat["errors"].append("%s: %s" % (safe, exc))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=DEFAULT_SRC)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--list", action="store_true", help="只列顶层结构，不落盘")
    args = ap.parse_args()

    if not os.path.exists(args.src):
        raise SystemExit("找不到归档：%s" % args.src)

    with open(args.src, "rb") as f:
        header, data_base = read_header(f)
        print("归档：%s" % args.src)
        print("数据区起点：%d" % data_base)
        top = header.get("files") or {}
        print("顶层条目 %d 个：" % len(top))
        for k, v in list(top.items())[:25]:
            kind = "DIR" if v.get("files") else ("%d B" % v.get("size", 0))
            print("   %-28s %s" % (k, kind))

        if args.list:
            return 0

        if os.path.exists(args.out):
            print("输出目录已存在，跳过重复解包：%s" % args.out)
            return 0
        os.makedirs(args.out, exist_ok=True)

        stat = {"dirs": 0, "files": 0, "links": 0, "bytes": 0,
                "errors": [], "mapHits": [], "questHits": []}
        walk(header, args.out, args.out, f, data_base, stat)

    print("解包完成 → %s" % args.out)
    print("目录 %d / 文件 %d / 符号链接 %d / 共 %.1f MB"
          % (stat["dirs"], stat["files"], stat["links"], stat["bytes"] / 1048576.0))
    if stat["errors"]:
        print("失败 %d 项（前 10）：" % len(stat["errors"]))
        for e in stat["errors"][:10]:
            print("   ", e)
    if stat["mapHits"]:
        print("\n疑似地图相关 %d 个（前 25）：" % len(stat["mapHits"]))
        for p in stat["mapHits"][:25]:
            print("   ", p)
    if stat["questHits"]:
        print("\n疑似任务相关 %d 个（前 25）：" % len(stat["questHits"]))
        for p in stat["questHits"][:25]:
            print("   ", p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
