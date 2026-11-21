#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""审计「游戏内显示名撞名」：同一个短名指向多个**不同**物品。

背景（用户实测）：实验室白卡、蓝色记号钥匙卡、钥匙卡收纳盒的短名都是「钥匙卡」，
截图只看得到这三个字，OCR 无法区分。运行期已经按「标 ? 徽记 + 只画徽章不报价」处理，
但这个命令把**全部**撞名组列出来，并按「选错代价」排序，便于判断要不要人工补别名。

数据源（都是仓库内只读文件）：
  · data/items.json        → 全名 n / 每格价 / 尺寸
  · data/ocr-item-names.json → 游戏内中文短名（zh）

用法：
    python tools/audit_ocr_collisions.py                    # 打印摘要 + 前 40 组
    python tools/audit_ocr_collisions.py --all              # 打印全部组
    python tools/audit_ocr_collisions.py --md docs/x.md     # 写成 Markdown 清单
    python tools/audit_ocr_collisions.py --min-ratio 3      # 只列价差 ≥3 倍的高危组
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ITEMS = os.path.join(ROOT, "data", "items.json")
SHORTS = os.path.join(ROOT, "data", "ocr-item-names.json")


def per_slot(rec: dict) -> int | None:
    """每格价（与运行期 PickBest 同口径）：p.b / (gw × gh)。"""
    price = (rec.get("p") or {}).get("b")
    gw, gh = rec.get("gw"), rec.get("gh")
    if not isinstance(price, (int, float)) or price <= 0:
        return None
    slots = (gw * gh) if isinstance(gw, int) and isinstance(gh, int) and gw > 0 and gh > 0 else 1
    return int(price / slots)


def load_groups() -> list[dict]:
    items = json.load(open(ITEMS, encoding="utf-8"))["items"]
    shorts = json.load(open(SHORTS, encoding="utf-8"))["names"]

    by_short: dict[str, list[str]] = collections.defaultdict(list)
    for iid, v in shorts.items():
        zh = (v or {}).get("zh")
        if isinstance(zh, str) and zh.strip():
            by_short[zh.strip()].append(iid)

    groups = []
    for short, ids in by_short.items():
        # 按全名折叠：同一件物品重复录入不算撞名
        seen: dict[str, dict] = {}
        for iid in ids:
            rec = items.get(iid) or {}
            name = rec.get("n") or iid
            ps = per_slot(rec)
            cur = seen.get(name)
            if cur is None or (ps or -1) > (cur["perSlot"] or -1):
                seen[name] = {"id": iid, "name": name, "perSlot": ps,
                              "w": rec.get("w"), "pt": rec.get("pt")}
        if len(seen) < 2:
            continue
        rows = sorted(seen.values(), key=lambda r: -(r["perSlot"] or -1))
        prices = [r["perSlot"] for r in rows if r["perSlot"]]
        ratio = (max(prices) / min(prices)) if len(prices) >= 2 and min(prices) > 0 else None
        groups.append({"short": short, "rows": rows, "ratio": ratio})
    # 选错代价大的排前面：价差倍数优先，其次组内物品数
    groups.sort(key=lambda g: (-(g["ratio"] or 0), -len(g["rows"]), g["short"]))
    return groups


def fmt(n) -> str:
    return "—" if not isinstance(n, (int, float)) or n <= 0 else format(int(n), ",")


def print_summary(groups: list[dict], limit: int | None):
    total_items = sum(len(g["rows"]) for g in groups)
    risky = [g for g in groups if (g["ratio"] or 0) >= 3]
    print("撞名组：%d 组，涉及 %d 件不同物品；其中价差 ≥3 倍的高危组 %d 组"
          % (len(groups), total_items, len(risky)))
    print()
    shown = groups if limit is None else groups[:limit]
    for g in shown:
        ratio = ("价差 %.1f×" % g["ratio"]) if g["ratio"] else "价格缺失"
        print("「%s」→ %d 件（%s）" % (g["short"], len(g["rows"]), ratio))
        for r in g["rows"]:
            print("    %-10s %-34s %s ₽/格" % (r["id"][:10], r["name"][:34], fmt(r["perSlot"])))
        print()
    if limit is not None and len(groups) > limit:
        print("…… 还有 %d 组未显示（--all 看全部）" % (len(groups) - limit))


def write_md(groups: list[dict], path: str):
    total_items = sum(len(g["rows"]) for g in groups)
    risky = [g for g in groups if (g["ratio"] or 0) >= 3]
    lines = [
        "# OCR 短名撞名清单（游戏内显示名重复）",
        "",
        "由 `tools/audit_ocr_collisions.py` 生成，数据源 `data/items.json` +",
        "`data/ocr-item-names.json`。运行期遇到这些短名不再猜价格：浮窗只画 **?** 徽章，",
        "点开列出全部候选；市场页识别结果同样标 **?** 并给候选价目。",
        "",
        "- 撞名组：**%d** 组，涉及 **%d** 件不同物品" % (len(groups), total_items),
        "- 其中价差 ≥3 倍的**高危组**：**%d** 组（选错物品会给出严重误导读数）" % len(risky),
        "",
        "| 短名 | 物品数 | 价差 | 候选（全名 · 每格价） |",
        "| --- | --- | --- | --- |",
    ]
    for g in groups:
        ratio = ("%.1f×" % g["ratio"]) if g["ratio"] else "—"
        cands = "<br>".join("%s · %s ₽" % (r["name"], fmt(r["perSlot"])) for r in g["rows"])
        lines.append("| %s | %d | %s | %s |" % (g["short"], len(g["rows"]), ratio, cands))
    lines.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("已写入 %s（%d 组）" % (path, len(groups)))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="打印全部组")
    ap.add_argument("--md", default=None, help="同时写 Markdown 清单到该路径")
    ap.add_argument("--min-ratio", type=float, default=None,
                    help="只保留价差 ≥ 该倍数的组")
    ap.add_argument("--limit", type=int, default=40, help="终端显示前 N 组（默认 40）")
    a = ap.parse_args()

    groups = load_groups()
    if a.min_ratio is not None:
        groups = [g for g in groups if (g["ratio"] or 0) >= a.min_ratio]
    if a.md:
        write_md(groups, a.md)
    print_summary(groups, None if a.all else a.limit)
    return 0


if __name__ == "__main__":
    sys.exit(main())
