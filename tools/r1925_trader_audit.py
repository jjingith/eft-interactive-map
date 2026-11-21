# -*- coding: utf-8 -*-
"""R19.25 商人名称审计（只读数据 + 静态检查显示位置）。

产出 docs/r19.25-task-tree/trader-name-audit.json：
  · 每个商人的稳定 ID、数据来源、源英文名、当前中文名、最终显示名、映射状态
  · 任务系统里所有显示商人名的地方（用 grep 定位，含文件与代码片段）
  · 无法可靠映射的条目（宁缺毋滥：不猜、不反译、不用 ID 冒充名字）

用法：python tools/r1925_trader_audit.py
"""
from __future__ import annotations

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TASKS_DIR = os.path.join(ROOT, "data", "tasks")
OUT_DIR = os.path.join(ROOT, "docs", "r19.25-task-tree")
TASKS_JS = os.path.join(ROOT, "tasks.js")

# 显示位置清单：文件 + 正则 + 说明（用真实代码定位，不靠记忆）
SITES = [
    ("任务树节点副标题", r'var bits = \[traderEn\(rec\)'),
    ("任务树节点悬停", r'"商人：" \+ traderEn\(rec\)'),
    ("商人分带标题", r'\(t\.nameEn \|\| band\.trader \|\| "未收录商人"\) \+ " · "'),
    ("奖励·声望商人", r'"声望：" \+ traderNameById\(s\.traderId\)'),
    ("奖励·解锁商人", r'"解锁商人：" \+ traderNameById\(t\)'),
    ("商人任务中心卡片", r'var nm = h\("span", "tk-trader-name", tr\.nameEn'),
    ("商人任务中心标题", r'\(state\.traders\[selectedTrader\] \|\| \{\}\)\.nameEn'),
    ("商人筛选下拉", r'\(state\.traders\[tid\]\.nameEn \|\| "未收录商人"\) \+ "（"'),
    ("任务详情副标题", r'sub\.textContent = traderEn\(rec\)'),
    ("任务详情「所属商人」", r'\["所属商人", traderEn\(rec\), "traderEn"\]'),
    ("前置任务摘要", r'\(t \? traderEn\(t\) \+ " · " : ""\)'),
    ("后续任务摘要", r'traderEn\(t\) \+ \(extra\.length'),
    ("进度页条目", r'var meta = \[traderEn\(rec\)'),
    ("攻略概述（数据层生成）", r'由 %s 发布'),
]


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    traders = json.load(open(os.path.join(TASKS_DIR, "traders.json"), encoding="utf-8"))["traders"]
    js = open(TASKS_JS, encoding="utf-8").read()

    rows = []
    unresolved = []
    for tid, t in sorted(traders.items(), key=lambda kv: kv[1].get("nameEn") or ""):
        name_en = (t.get("nameEn") or "").strip()
        name_zh = (t.get("nameZh") or "").strip()
        slug = t.get("normalizedName") or ""
        task_count = 0
        for mode in ("regular", "pve", "pvps"):
            doc = json.load(open(os.path.join(TASKS_DIR, "tasks.%s.json" % mode), encoding="utf-8"))
            task_count = max(task_count, doc["counts"]["tasks"] and
                             sum(1 for r in doc["tasks"].values() if r.get("traderId") == tid))
        status = "ok"
        note = ""
        if not name_en:
            status = "unresolved"
            note = "上游没有给出 nameEn：界面会显示「未收录商人」，不使用 ID 或中文名顶替"
            unresolved.append({"traderId": tid, "reason": note})
        elif not re.match(r"^[A-Za-z][A-Za-z0-9 .'\-]*$", name_en):
            status = "suspect"
            note = "nameEn 含非拉丁字符，需人工确认"
            unresolved.append({"traderId": tid, "reason": note})
        if name_zh and name_zh == name_en:
            note = (note + "；" if note else "") + "中文表与英文名相同（上游未提供译名，不影响本轮显示）"
        rows.append({
            "traderId": tid,
            "source": "data/tasks/traders.json（由 tools/fetch_tasks.py 从上游 traders 端点解析）",
            "upstreamEndpoint": "https://json.tarkov.dev/regular/traders",
            "normalizedName": slug,
            "nameEn": name_en,
            "nameZhBefore": name_zh,
            "displayName": name_en or "未收录商人",
            "taskCountMax": task_count,
            "icon": t.get("localIcon") or "",
            "status": status,
            "note": note or "直接显示英文原名（游戏内名称）",
        })

    sites = []
    for label, pat in SITES:
        hay = js if pat != r'由 %s 发布' else open(os.path.join(ROOT, "tools", "fetch_tasks.py"),
                                                  encoding="utf-8").read()
        m = re.search(pat, hay)
        sites.append({
            "site": label,
            "file": "tasks.js" if pat != r'由 %s 发布' else "tools/fetch_tasks.py（生成进 guides.*.json）",
            "found": bool(m),
            "evidence": (m.group(0)[:80] if m else ""),
        })

    doc = {
        "schema": 1,
        "tool": "tools/r1925_trader_audit.py",
        "rule": "任务系统内的商人名称直接显示游戏内英文原名；其它 UI 文案继续中文。"
                "本条目是中文化规则的显式例外（见 design 决策 docs/r19.25-task-tree/audit.md §5）。",
        "dataSource": "data/tasks/traders.json 的 nameEn（上游 traders 端点的 normalizedName → 英文名）",
        "resolution": "按稳定 traderId 关联；不用显示名匹配、不反向翻译、不用内部 ID 当名字",
        "total": len(rows),
        "resolved": sum(1 for r in rows if r["status"] == "ok"),
        "suspect": [r for r in rows if r["status"] == "suspect"],
        "unresolved": unresolved,
        "sites": sites,
        "sitesMissing": [s["site"] for s in sites if not s["found"]],
        "traders": rows,
    }
    path = os.path.join(OUT_DIR, "trader-name-audit.json")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1)

    print("商人 %d 个：已解析 %d / 可疑 %d / 未解析 %d"
          % (doc["total"], doc["resolved"], len(doc["suspect"]), len(doc["unresolved"])))
    for r in rows:
        print("  %-14s %-10s %-8s %s" % (r["nameEn"], r["nameZhBefore"] or "-",
                                         r["status"], r["note"][:40]))
    print("显示位置：%d 处，缺失 %s" % (len(sites), doc["sitesMissing"] or "无"))
    print("写入", path)
    return 0 if not doc["sitesMissing"] else 1


if __name__ == "__main__":
    sys.exit(main())
