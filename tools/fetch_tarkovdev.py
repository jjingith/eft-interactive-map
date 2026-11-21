#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tarkov.dev 全量数据抓取（构建期工具，零依赖，运行期不联网）

背景
----
tarkov.dev 是开源社区项目（https://github.com/the-hideout/tarkov-dev），其预构建的
静态 JSON 数据发布在 `https://json.tarkov.dev/{mode}/{name}`。本项目原有管线
`tools/fetch_data.py` 只按需取其中几类（items / traders / barters / tasks / maps）。

本工具把 json.tarkov.dev **当前公开的全部数据集**一次性抓到本地 `build-cache/tarkovdev/`，
并落一份可复核的 manifest（url / 字节数 / sha256 / 顶层键 / 记录数）。用途：

  · 想看上游到底有哪些字段/数据集时，不用一次又一次临时联网
  · 未来接新功能（crafts 制作表、hideout 藏身处、任务链等）时直接用本地快照
  · 审计「本地缺哪类数据」时有明确基线

边界（重要）
------------
1. **只写 build-cache/**（该目录已进 .gitignore），不改 `data/*.json` 任何契约数据。
2. **只在构建期手动运行**：运行期页面依然零联网，唯一联网点仍是构建期。
3. 只抓 JSON 数据，**不抓图片素材**：许可复核确认上游图片（尤其游戏角色美术）
   没有明确再分发许可，详见 `assets/icons-traders/manifest.json` 的 licenseReview。

用法
----
    python tools/fetch_tarkovdev.py --list                 # 看有哪些数据集
    python tools/fetch_tarkovdev.py                        # 抓 regular 全部
    python tools/fetch_tarkovdev.py --mode pve             # 抓 pve 全部
    python tools/fetch_tarkovdev.py --mode all             # 两种模式都抓
    python tools/fetch_tarkovdev.py --only items,traders   # 只抓指定数据集
    python tools/fetch_tarkovdev.py --force                # 忽略已存在，强制重抓
    python tools/fetch_tarkovdev.py --summary              # 抓完打印各数据集记录数
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "build-cache" / "tarkovdev"
MANIFEST = "manifest.json"

BASE = "https://json.tarkov.dev/{mode}/{name}"
MODES = ("regular", "pve")

# json.tarkov.dev 当前公开的数据集（2026-10 实测全部 200）。
# 顺序即抓取顺序；`-zh` 结尾的是中文翻译表。
DATASETS = [
    "items", "items_zh",
    "traders", "traders_zh",
    "barters",
    "tasks", "tasks_zh",
    "maps", "maps_zh",
    "crafts",
    "hideout",
]

BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36")
TIMEOUT = 180  # items / maps 单份十几 MB，给足时间


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def fetch(url: str) -> bytes:
    """抓一份数据。带浏览器 UA（上游会对无 UA 的请求返回 403），失败抛异常。"""
    req = urllib.request.Request(url, headers={
        "User-Agent": BROWSER_UA,
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.read()


def _shape(payload):
    """返回 (顶层键, 估计记录数)，用于 manifest 里快速概览。"""
    keys = []
    count = None
    if isinstance(payload, dict):
        keys = sorted(payload.keys())[:12]
        data = payload.get("data")
        if isinstance(data, list):
            count = len(data)
        elif isinstance(data, dict):
            count = len(data)
    elif isinstance(payload, list):
        count = len(payload)
    return keys, count


def write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)


def load_manifest() -> dict:
    p = OUT_DIR / MANIFEST
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - manifest 损坏就重建
            pass
    return {}


def run(mode_arg: str, only, force: bool, summary: bool) -> int:
    modes = MODES if mode_arg == "all" else (mode_arg,)
    wanted = DATASETS
    if only:
        want = [s.strip() for s in only.split(",") if s.strip()]
        unknown = [s for s in want if s not in DATASETS]
        if unknown:
            print("未知数据集：%s（可用：%s）" % (", ".join(unknown), ", ".join(DATASETS)))
            return 2
        wanted = [s for s in DATASETS if s in want]

    manifest = load_manifest()
    manifest.setdefault("note", "tarkov.dev 全量数据快照（构建期抓取，运行期不联网）")
    manifest.setdefault("source", "https://json.tarkov.dev/{mode}/{name}")
    manifest.setdefault("repository", "https://github.com/the-hideout/tarkov-dev")
    manifest.setdefault("modes", {})
    manifest["updatedAt"] = now_iso()

    total_bytes = 0
    total_files = 0
    failures = []

    for mode in modes:
        bucket = manifest["modes"].setdefault(mode, {})
        for name in wanted:
            url = BASE.format(mode=mode, name=name)
            dest = OUT_DIR / mode / ("%s.json" % name)
            if dest.exists() and not force:
                raw = dest.read_bytes()
                status = "已存在"
            else:
                try:
                    raw = fetch(url)
                except urllib.error.HTTPError as err:
                    print("  %-12s %-8s HTTP %s" % (name, mode, err.code))
                    failures.append("%s/%s:%s" % (mode, name, err.code))
                    continue
                except Exception as err:  # noqa: BLE001 - 单个数据集失败不影响其余
                    print("  %-12s %-8s 失败 %s" % (name, mode, err))
                    failures.append("%s/%s:%s" % (mode, name, err))
                    continue
                write_atomic(dest, raw)
                status = "下载"

            total_files += 1
            total_bytes += len(raw)
            try:
                payload = json.loads(raw.decode("utf-8", "replace"))
                keys, count = _shape(payload)
            except Exception:  # noqa: BLE001
                keys, count = [], None

            prev = bucket.get(name) or {}
            bucket[name] = {
                "url": url,
                "file": str(dest.relative_to(ROOT)).replace("\\", "/"),
                "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "topKeys": keys,
                "records": count,
                "fetchedAt": prev.get("fetchedAt") if status == "已存在" else now_iso(),
                "checkedAt": now_iso(),
            }
            print("  %-12s %-8s %-6s %10d bytes  records=%s"
                  % (name, mode, status, len(raw), count))

    write_atomic(OUT_DIR / MANIFEST,
                 json.dumps(manifest, ensure_ascii=False, indent=1).encode("utf-8"))

    print("\n输出目录：%s" % OUT_DIR.relative_to(ROOT).as_posix())
    print("本次处理 %d 份，共 %.1f MB" % (total_files, total_bytes / 1024 / 1024))
    if failures:
        print("失败 %d 项：%s" % (len(failures), ", ".join(failures)))
    print("manifest：%s" % (OUT_DIR / MANIFEST).relative_to(ROOT).as_posix())

    if summary:
        print("\n各数据集概览：")
        for mode in modes:
            for name in wanted:
                rec = (manifest["modes"].get(mode) or {}).get(name)
                if not rec:
                    continue
                print("  %-8s %-12s records=%-8s keys=%s"
                      % (mode, name, rec.get("records"), ",".join(rec.get("topKeys") or [])[:70]))

    return 1 if failures else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="抓取 json.tarkov.dev 的全部公开数据集到 build-cache/tarkovdev/（构建期工具）")
    ap.add_argument("--mode", default="regular",
                    choices=["regular", "pve", "all"], help="游戏模式（默认 regular）")
    ap.add_argument("--only", default="", help="只抓指定数据集，逗号分隔（见 --list）")
    ap.add_argument("--force", action="store_true", help="忽略已有文件，强制重抓")
    ap.add_argument("--summary", action="store_true", help="抓完打印各数据集记录数")
    ap.add_argument("--list", action="store_true", help="列出可用数据集后退出")
    args = ap.parse_args(argv)

    if args.list:
        print("可用数据集（json.tarkov.dev/{mode}/{name}）：")
        for name in DATASETS:
            print("  " + name)
        print("\n模式：%s" % " / ".join(MODES))
        return 0

    return run(args.mode, args.only, args.force, args.summary)


if __name__ == "__main__":
    sys.exit(main())
