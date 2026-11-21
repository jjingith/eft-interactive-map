# -*- coding: utf-8 -*-
"""R20.8：扫描已脱壳的 tarkov-kaedeori-client，定位「地图 / 任务」相关的数据来源。

只读分析，不联网、不修改任何输入文件。输出：
  1. 打包 JS 里的绝对 URL（判断数据是内嵌还是运行时拉取）
  2. API 路径片段（/api/... 之类）
  3. 地图 / 任务相关中文关键词出现的上下文片段（判断有没有内嵌数据）

用法：
    python tools/r208_scan_kaedeori.py
    python tools/r208_scan_kaedeori.py --root <解包目录>
"""
from __future__ import annotations

import argparse
import io
import os
import re

DEFAULT_ROOT = r"D:\personal\trae\02-塔科夫\逆向参考\tarkov.kaedeori\extracted\app\dist"

TARGETS = [
    "render/assets/main-6bc73974.js",
    "render/assets/client-268b225d.js",
    "render/assets/quickSearch-fe180865.js",
    "render/assets/axios-ed4236db.js",
    "render/assets/index-d93ef1b5.js",
    "render/assets/titleBar-ccd10928.js",
    "main/background.js",
    "main/preload.js",
]

KEYWORDS = ["地图", "撤离", "任务", "商人", "刷新点", "钥匙", "Boss", "boss",
            "quest", "task", "trader", "extract", "mapId", "mapData"]

URL_RE = re.compile(r"https?://[a-zA-Z0-9._~:/?#@!$&()*+,;=%-]{6,90}")
API_RE = re.compile(r"[\"'`](/?(?:api|v\d|client|data)/[a-zA-Z0-9._/{}%-]{2,60})[\"'`]")


def scan(root):
    urls, apis = {}, {}
    hits = {}
    for rel in TARGETS:
        p = os.path.join(root, rel.replace("/", os.sep))
        if not os.path.exists(p):
            print("[跳过] 不存在：%s" % rel)
            continue
        text = io.open(p, encoding="utf-8", errors="replace").read()
        print("\n=== %s （%.0f KB）===" % (rel, len(text) / 1024.0))

        found = set()
        for m in URL_RE.findall(text):
            found.add(m.rstrip(".,;)]}'\""))
        for u in sorted(found):
            urls.setdefault(u, []).append(rel)
        print("  绝对 URL %d 个" % len(found))
        for u in sorted(found)[:14]:
            print("     ", u)

        api = set(m for m in API_RE.findall(text))
        for a in api:
            apis.setdefault(a, []).append(rel)
        if api:
            print("  API 路径 %d 个：" % len(api))
            for a in sorted(api)[:20]:
                print("     ", a)

        for kw in KEYWORDS:
            n = text.count(kw)
            if n:
                hits.setdefault(kw, []).append((rel, n))

    print("\n=== 关键词命中汇总 ===")
    for kw in KEYWORDS:
        if kw in hits:
            total = sum(n for _, n in hits[kw])
            detail = ", ".join("%s×%d" % (os.path.basename(r), n) for r, n in hits[kw])
            print("  %-10s 共 %4d 次   %s" % (kw, total, detail))
        else:
            print("  %-10s 0 次" % kw)

    print("\n=== 全部绝对 URL 去重（%d 个）===" % len(urls))
    for u in sorted(urls):
        print("  %-70s %s" % (u, ",".join(os.path.basename(x) for x in urls[u][:2])))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=DEFAULT_ROOT)
    args = ap.parse_args()
    if not os.path.isdir(args.root):
        raise SystemExit("解包目录不存在：%s" % args.root)
    return scan(args.root)


if __name__ == "__main__":
    raise SystemExit(main())
