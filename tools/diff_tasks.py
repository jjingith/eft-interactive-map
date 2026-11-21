# -*- coding: utf-8 -*-
"""R19.23 三模式任务数据差异审计（只读，不修改任何任务数据）。

读取 data/tasks/tasks.{regular,pve,pvps}.json（tools/fetch_tasks.py 的标准化产物），
对三组配对做**逐字段**比较，输出：

    data/tasks/diff-report.json      机读报告（供测试与前端「数据说明」使用）
    docs/r19.23/diff-report.md       人读报告（交付文档用）

比较口径
--------
1. 任务集合：按上游任务 ID 求差集。**不按中文名/英文名合并**——同名不同 ID 视为两个任务。
2. 同 ID 字段：名称、商人、等级、阵营、Kappa/灯塔标记、经验、目标（逐条）、
   前置关系（含 AND/OR 与状态语义）、非任务前置条件、奖励、失败分支。
3. 每条差异都带 taskId / nameZh / nameEn / 字段路径 / 两边原值 / 数据来源文件。

用法
----
    python tools/diff_tasks.py            # 生成报告
    python tools/diff_tasks.py --check    # 只打印汇总，不写文件（供测试用）
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TASKS_DIR = os.path.join(ROOT, "data", "tasks")
DOCS_DIR = os.path.join(ROOT, "docs", "r19.23")
MODES = ("regular", "pve", "pvps")
LABEL = {"regular": "PvP（常规）", "pve": "PvE", "pvps": "PvPS（赛季服）"}

# 单条对比的字段上限：报告体积可控，但计数一定完整
DETAIL_CAP = 260


def load(mode: str) -> dict:
    path = os.path.join(TASKS_DIR, "tasks.%s.json" % mode)
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _obj_sig(o: dict) -> dict:
    """目标的可比签名（只取有语义的字段，随机 id 不参与）。"""
    return {
        "type": o.get("type"),
        "descZh": o.get("descZh"),
        "count": o.get("count"),
        "optional": bool(o.get("optional")),
        "maps": list(o.get("maps") or []),
        "zones": len(o.get("zones") or []),
        "constraints": list(o.get("constraints") or []),
    }


def _rew_sig(r: dict) -> dict:
    r = r or {}
    return {
        "items": sorted("%s×%s" % (it.get("id"), it.get("count")) for it in (r.get("items") or [])),
        "standing": sorted("%s:%s" % (s.get("traderId"), s.get("standing"))
                           for s in (r.get("traderStanding") or [])),
        "offerUnlock": len(r.get("offerUnlock") or []),
        "traderUnlock": sorted(r.get("traderUnlock") or []),
        "achievement": len(r.get("achievement") or []),
    }


def _pre_sig(rec: dict) -> list:
    return sorted(
        "%s|%s|%s" % (p.get("taskId"), ",".join(p.get("statuses") or ["complete"]), p.get("logic") or "all")
        for p in (rec.get("prerequisites") or [])
    )


def compare(a_mode: str, b_mode: str, a: dict, b: dict) -> dict:
    ta = a.get("tasks") or {}
    tb = b.get("tasks") or {}
    only_a = sorted(set(ta) - set(tb))
    only_b = sorted(set(tb) - set(ta))
    common = sorted(set(ta) & set(tb))

    details = []
    counts = {
        "tasks": {"left": len(ta), "right": len(tb), "common": len(common)},
        "onlyLeft": len(only_a), "onlyRight": len(only_b),
        "sameIdWithDiff": 0, "nameDiff": 0, "objectiveDiff": 0, "prereqDiff": 0,
        "conditionDiff": 0, "rewardDiff": 0, "traderDiff": 0, "levelDiff": 0,
        "flagDiff": 0, "failBranchDiff": 0, "edges": {"left": 0, "right": 0},
    }
    for rec in ta.values():
        counts["edges"]["left"] += len(rec.get("prerequisites") or [])
    for rec in tb.values():
        counts["edges"]["right"] += len(rec.get("prerequisites") or [])

    def add(task_id, path, left, right, kind):
        if len(details) >= DETAIL_CAP:
            return
        rec = ta.get(task_id) or tb.get(task_id) or {}
        details.append({"taskId": task_id, "nameZh": rec.get("nameZh"), "nameEn": rec.get("nameEn"),
                        "englishName": rec.get("englishName"), "kind": kind, "path": path,
                        "left": left, "right": right,
                        "leftSource": "data/tasks/tasks.%s.json" % a_mode,
                        "rightSource": "data/tasks/tasks.%s.json" % b_mode})

    for tid in common:
        ra, rb = ta[tid], tb[tid]
        touched = False
        scalar = [("nameZh", "name"), ("nameEn", "name"), ("traderId", "trader"),
                  ("minLevel", "level"), ("faction", "flag"),
                  ("kappaRequired", "flag"), ("lightkeeperRequired", "flag"),
                  ("restartable", "flag"), ("experience", "reward")]
        for field, kind in scalar:
            if ra.get(field) != rb.get(field):
                add(tid, field, ra.get(field), rb.get(field), kind)
                touched = True
                key = {"name": "nameDiff", "trader": "traderDiff", "level": "levelDiff",
                       "flag": "flagDiff", "reward": "rewardDiff"}[kind]
                counts[key] += 1

        oa = [_obj_sig(o) for o in (ra.get("objectives") or [])]
        ob = [_obj_sig(o) for o in (rb.get("objectives") or [])]
        if oa != ob:
            counts["objectiveDiff"] += 1
            touched = True
            diffs = []
            for i in range(max(len(oa), len(ob))):
                x = oa[i] if i < len(oa) else None
                y = ob[i] if i < len(ob) else None
                if x != y:
                    diffs.append({"index": i, "left": x, "right": y})
            add(tid, "objectives[%d]" % len(diffs), {"count": len(oa), "diff": diffs[:4]},
                {"count": len(ob)}, "objective")

        pa, pb = _pre_sig(ra), _pre_sig(rb)
        if pa != pb:
            counts["prereqDiff"] += 1
            touched = True
            add(tid, "prerequisites", pa, pb, "prereq")

        ca = [c.get("text") for c in (ra.get("conditions") or [])]
        cb = [c.get("text") for c in (rb.get("conditions") or [])]
        if ca != cb:
            counts["conditionDiff"] += 1
            touched = True
            add(tid, "conditions", ca, cb, "condition")

        wa, wb = _rew_sig(ra.get("rewards")), _rew_sig(rb.get("rewards"))
        if wa != wb:
            counts["rewardDiff"] += 1
            touched = True
            add(tid, "rewards", wa, wb, "reward")

        fa = [f.get("taskId") for f in (ra.get("failedConditions") or [])]
        fb = [f.get("taskId") for f in (rb.get("failedConditions") or [])]
        if fa != fb:
            counts["failBranchDiff"] += 1
            touched = True
            add(tid, "failedConditions", fa, fb, "fail")

        if touched:
            counts["sameIdWithDiff"] += 1

    return {
        "left": a_mode, "right": b_mode,
        "leftLabel": LABEL[a_mode], "rightLabel": LABEL[b_mode],
        "counts": counts,
        "onlyLeftTasks": [{"id": t, "nameZh": ta[t].get("nameZh"), "nameEn": ta[t].get("nameEn"),
                           "englishName": ta[t].get("englishName"),
                           "traderZh": ta[t].get("traderZh"), "minLevel": ta[t].get("minLevel")}
                          for t in only_a],
        "onlyRightTasks": [{"id": t, "nameZh": tb[t].get("nameZh"), "nameEn": tb[t].get("nameEn"),
                            "englishName": tb[t].get("englishName"),
                            "traderZh": tb[t].get("traderZh"), "minLevel": tb[t].get("minLevel")}
                           for t in only_b],
        "fieldDiffs": details,
        "fieldDiffTruncated": counts["sameIdWithDiff"] and len(details) >= DETAIL_CAP,
    }


def md_report(report: dict, index: dict, season: dict | None) -> str:
    L = []
    L.append("# R19.23 三模式任务数据差异报告（自动生成）")
    L.append("")
    L.append("> 生成工具 `tools/diff_tasks.py`；数据 `data/tasks/tasks.{regular,pve,pvps}.json`；"
             "生成时间 %s。" % report["generatedAt"])
    L.append("> 口径：按**上游任务 ID** 求差集，绝不按名称合并；同 ID 逐字段比较。")
    L.append("")
    L.append("## 一、数据规模")
    L.append("")
    L.append("| 项目 | PvP（常规） | PvE | PvPS（赛季服） |")
    L.append("|---|---:|---:|---:|")
    m = index.get("modes") or {}
    rows = [("实际收录任务数", "tasks"), ("任务目标总数", "objectives"),
            ("前置关系（边）", "edges"), ("有前置的任务", "withPrereq"),
            ("赛季专属任务", "seasonOnly"), ("Kappa 必需", "kappa"), ("阵营限定", "faction")]
    for title, key in rows:
        L.append("| %s | %s | %s | %s |" % (
            title, m.get("regular", {}).get(key, "-"), m.get("pve", {}).get(key, "-"),
            m.get("pvps", {}).get(key, "-")))
    L.append("| 上游端点 | `/regular/tasks` | `/pve/tasks` | `/pvp-season/tasks` |")
    if season:
        L.append("| 数据时间 | 见 sources.json | 见 sources.json | 赛季 %s → %s |" % (
            season.get("startISO"), season.get("endISO")))
    L.append("")
    L.append("## 二、配对差异汇总")
    L.append("")
    L.append("| 检查项 | PvP vs PvE | PvP vs PvPS | PvE vs PvPS |")
    L.append("|---|---:|---:|---:|")
    pairs = {("%s|%s" % (p["left"], p["right"])): p for p in report["pairs"]}
    order = [("regular", "pve"), ("regular", "pvps"), ("pve", "pvps")]
    keys = [("任务数量（左/右）", lambda c: "%d / %d" % (c["tasks"]["left"], c["tasks"]["right"])),
            ("仅在左侧模式存在", lambda c: c["onlyLeft"]),
            ("仅在右侧模式存在", lambda c: c["onlyRight"]),
            ("同 ID 有差异的任务", lambda c: c["sameIdWithDiff"]),
            ("名称差异", lambda c: c["nameDiff"]),
            ("任务目标差异", lambda c: c["objectiveDiff"]),
            ("前置关系差异", lambda c: c["prereqDiff"]),
            ("前置条件差异", lambda c: c["conditionDiff"]),
            ("奖励与解锁差异", lambda c: c["rewardDiff"]),
            ("商人归属差异", lambda c: c["traderDiff"]),
            ("等级差异", lambda c: c["levelDiff"]),
            ("标记差异（Kappa/阵营等）", lambda c: c["flagDiff"]),
            ("失败分支差异", lambda c: c["failBranchDiff"]),
            ("关系边（左/右）", lambda c: "%d / %d" % (c["edges"]["left"], c["edges"]["right"]))]
    for title, fn in keys:
        cells = []
        for a, b in order:
            p = pairs.get("%s|%s" % (a, b))
            cells.append(fn(p["counts"]) if p else "-")
        L.append("| %s | %s | %s | %s |" % (title, cells[0], cells[1], cells[2]))
    L.append("")
    for a, b in order:
        p = pairs.get("%s|%s" % (a, b))
        if not p:
            continue
        L.append("## 三、%s ↔ %s 明细" % (p["leftLabel"], p["rightLabel"]))
        L.append("")
        L.append("### 只在 %s 存在的任务（%d）" % (p["leftLabel"], len(p["onlyLeftTasks"])))
        L.append("")
        if p["onlyLeftTasks"]:
            L.append("| 任务 ID | 中文名 | 英文名 | 商人 | 等级 |")
            L.append("|---|---|---|---|---:|")
            for t in p["onlyLeftTasks"][:40]:
                L.append("| `%s` | %s | %s | %s | %s |" % (
                    t["id"], t["nameZh"], t.get("englishName") or t.get("nameEn") or "",
                    t.get("traderZh") or "", t.get("minLevel")))
            if len(p["onlyLeftTasks"]) > 40:
                L.append("| … | 其余 %d 条见 diff-report.json | | | |" % (len(p["onlyLeftTasks"]) - 40))
        else:
            L.append("无。")
        L.append("")
        L.append("### 只在 %s 存在的任务（%d）" % (p["rightLabel"], len(p["onlyRightTasks"])))
        L.append("")
        if p["onlyRightTasks"]:
            L.append("| 任务 ID | 中文名 | 英文名 | 商人 | 等级 |")
            L.append("|---|---|---|---|---:|")
            for t in p["onlyRightTasks"][:40]:
                L.append("| `%s` | %s | %s | %s | %s |" % (
                    t["id"], t["nameZh"], t.get("englishName") or t.get("nameEn") or "",
                    t.get("traderZh") or "", t.get("minLevel")))
            if len(p["onlyRightTasks"]) > 40:
                L.append("| … | 其余 %d 条见 diff-report.json | | | |" % (len(p["onlyRightTasks"]) - 40))
        else:
            L.append("无。")
        L.append("")
        L.append("### 同 ID 但字段不同的任务（前 30 条）")
        L.append("")
        if p["fieldDiffs"]:
            L.append("| 任务 | 字段 | 左值 | 右值 |")
            L.append("|---|---|---|---|")
            for d in p["fieldDiffs"][:30]:
                def cut(v):
                    s = json.dumps(v, ensure_ascii=False)
                    return (s[:90] + "…") if len(s) > 90 else s
                L.append("| %s `%s` | `%s` | %s | %s |" % (
                    d["nameZh"], d["taskId"][:8], d["path"], cut(d["left"]).replace("|", "\\|"),
                    cut(d["right"]).replace("|", "\\|")))
            L.append("")
            L.append("> 完整 %d 条记录见 `data/tasks/diff-report.json` 的 `fieldDiffs`。" %
                     len(p["fieldDiffs"]))
        else:
            L.append("无：两模式同 ID 任务的名称 / 目标 / 前置 / 条件 / 奖励完全一致。")
        L.append("")
    L.append("## 四、无法确认的部分")
    L.append("")
    if (m.get("pvps", {}) or {}).get("seasonOnly", 0) == 0:
        L.append("- 当前上游快照 **没有** 只属于 pvp-season 的任务：PvPS 任务集是 PvP 的真子集，"
                 "因此「赛季专属任务」计数为 0。本项目不构造虚构赛季任务。")
    p_rp = pairs.get("regular|pvps")
    if p_rp and p_rp["counts"]["onlyLeft"]:
        L.append("- PvPS 缺少的 %d 个任务是上游 pvp-season 端点本身没有下发的，"
                 "本项目按「该模式不存在」处理，不用 PvP 数据补齐。" % p_rp["counts"]["onlyLeft"])
    L.append("- 赛季元信息（赛季名 / 赛季技能名）上游只给占位串与中文描述，界面不显示虚构赛季名。")
    L.append("")
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只打印汇总，不写文件")
    args = ap.parse_args(argv)

    packs = {}
    for mode in MODES:
        path = os.path.join(TASKS_DIR, "tasks.%s.json" % mode)
        if not os.path.exists(path):
            print("缺少数据：%s（先跑 tools/fetch_tasks.py）" % path)
            return 2
        packs[mode] = load(mode)

    index = {}
    ipath = os.path.join(TASKS_DIR, "index.json")
    if os.path.exists(ipath):
        with open(ipath, encoding="utf-8") as fh:
            index = json.load(fh)
    season = None
    spath = os.path.join(TASKS_DIR, "season.json")
    if os.path.exists(spath):
        with open(spath, encoding="utf-8") as fh:
            season = json.load(fh)

    pairs = [compare("regular", "pve", packs["regular"], packs["pve"]),
             compare("regular", "pvps", packs["regular"], packs["pvps"]),
             compare("pve", "pvps", packs["pve"], packs["pvps"])]
    report = {
        "schema": 1,
        "tool": "tools/diff_tasks.py",
        "generatedAt": index.get("generatedAt") or "",
        "modeOrder": list(MODES),
        "inputs": {m: {"path": "data/tasks/tasks.%s.json" % m,
                       "sha256": hashlib.sha256(
                           open(os.path.join(TASKS_DIR, "tasks.%s.json" % m), "rb").read()).hexdigest(),
                       "tasks": len(packs[m]["tasks"])} for m in MODES},
        "pairs": pairs,
    }
    for p in pairs:
        c = p["counts"]
        print("%-8s vs %-8s tasks %d/%d only %d/%d sameIdDiff %d obj %d pre %d rew %d trader %d" % (
            p["left"], p["right"], c["tasks"]["left"], c["tasks"]["right"], c["onlyLeft"],
            c["onlyRight"], c["sameIdWithDiff"], c["objectiveDiff"], c["prereqDiff"],
            c["rewardDiff"], c["traderDiff"]))
    if args.check:
        return 0

    os.makedirs(DOCS_DIR, exist_ok=True)
    with open(os.path.join(TASKS_DIR, "diff-report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)
    md = md_report(report, index, season)
    with open(os.path.join(DOCS_DIR, "diff-report.md"), "w", encoding="utf-8") as fh:
        fh.write(md)
    print("wrote data/tasks/diff-report.json + docs/r19.23/diff-report.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
