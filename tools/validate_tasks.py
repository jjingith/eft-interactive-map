# -*- coding: utf-8 -*-
"""任务数据校验（R19.23：三模式）。

只读检查 `data/tasks/` 产出的标准化数据，覆盖：
  · 三种模式各自：任务 ID 唯一、必需字段齐全、任务数非空
  · 前置 / 后续引用有效，且反向索引与正向一致（有向图自洽）
  · 目标条目结构合法（type / descZh / 可选标记）
  · AND / OR / 失败分支语义保留（logic=or、failedConditions）
  · 攻略覆盖率、缺失攻略标记
  · 模式隔离（PvP / PvE / PvPS 任务集合不混用），并输出三对集合差异
  · 模式专属标记自洽（seasonOnly 只可能出现在 pvps；onlyInModes 与实际集合一致）
  · 数据来源有效（sources.json 有 url/sha256/fetchedAt；PvPS 必须来自 pvp-season 端点）
  · 差异报告存在且与当前数据一致（数量、配对齐全）
  · 商人、地图引用可解析

用法：
    python tools/validate_tasks.py            # 校验并写报告
    python tools/validate_tasks.py --quiet    # 只返回退出码
"""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TASKS_DIR = os.path.join(ROOT, "data", "tasks")
OUT_DIR = os.path.join(ROOT, "docs", "r19.23")
MODES = ("regular", "pve", "pvps")
UPSTREAM = {"regular": "regular", "pve": "pve", "pvps": "pvp-season"}

REQUIRED = ("id", "nameZh", "nameEn", "traderId", "gameMode", "objectives", "prerequisites")
OBJECTIVE_TYPES = {
    "visit", "mark", "shoot", "findItem", "findQuestItem", "giveItem", "giveQuestItem",
    "plantItem", "plantQuestItem", "extract", "buildWeapon", "useItem", "sellItem",
    "traderLevel", "traderStanding", "taskStatus", "skill", "experience", "globalVariable",
    "dialogue",
    "sellItem", "buildWeapon",
}


def load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def validate(quiet=False) -> dict:
    report = {"schema": 2, "build": "R19.23", "modes": {}, "errors": [], "warnings": []}
    traders = load(os.path.join(TASKS_DIR, "traders.json"))["traders"]
    index = load(os.path.join(TASKS_DIR, "index.json"))
    sources = load(os.path.join(TASKS_DIR, "sources.json"))
    ids = {}

    for mode in MODES:
        path = os.path.join(TASKS_DIR, "tasks.%s.json" % mode)
        gpath = os.path.join(TASKS_DIR, "guides.%s.json" % mode)
        if not os.path.exists(path):
            report["errors"].append("缺少 %s" % path)
            continue
        doc = load(path)
        tasks = doc["tasks"]
        ids[mode] = set(tasks)
        guides = load(gpath)["guides"] if os.path.exists(gpath) else {}

        stats = {
            "tasks": len(tasks),
            "objectives": 0,
            "edges": 0,
            "orEdges": 0,
            "failedEdges": 0,
            "withPrereq": 0,
            "withFollowUp": 0,
            "guideGenerated": 0,
            "guideCurated": 0,
            "guideMissing": 0,
            "unknownTrader": 0,
            "seasonOnly": 0,
            "dupNames": [],
            "missingFields": [],
        }
        if not tasks:
            report["errors"].append("%s 任务数为 0（拒绝空数据覆盖）" % mode)
        if doc.get("mode") != mode:
            report["errors"].append("%s 文档 mode 字段=%r 与文件名不符" % (mode, doc.get("mode")))
        if (doc.get("upstreamGameMode") or "") != UPSTREAM[mode]:
            report["errors"].append("%s upstreamGameMode=%r 与预期 %r 不符"
                                    % (mode, doc.get("upstreamGameMode"), UPSTREAM[mode]))

        # 1) 必需字段 / ID 唯一
        for tid, rec in tasks.items():
            if rec.get("id") != tid:
                report["errors"].append("%s/%s id 字段与键不一致" % (mode, tid))
            for field in REQUIRED:
                if field not in rec:
                    stats["missingFields"].append("%s/%s 缺 %s" % (mode, tid, field))
            if rec.get("gameMode") != mode:
                report["errors"].append("%s/%s gameMode=%r 与所属模式不符" % (mode, tid, rec.get("gameMode")))
            if rec.get("seasonOnly"):
                stats["seasonOnly"] += 1
                if mode != "pvps":
                    report["errors"].append("%s/%s 标记 seasonOnly 但不在 pvps 模式" % (mode, tid))
            if rec.get("traderId") not in traders:
                stats["unknownTrader"] += 1
                report["warnings"].append("%s/%s 商人 %s 不在 traders.json" % (mode, tid, rec.get("traderId")))
            if not rec.get("nameZh") or rec["nameZh"].endswith("（未翻译）"):
                report["warnings"].append("%s/%s 缺少中文名：%s" % (mode, tid, rec.get("nameEn")))

        # 2) 目标结构
        for tid, rec in tasks.items():
            for o in rec.get("objectives") or []:
                stats["objectives"] += 1
                if o.get("type") not in OBJECTIVE_TYPES:
                    report["warnings"].append("%s/%s 目标类型未知：%s" % (mode, tid, o.get("type")))
                if not o.get("descZh"):
                    report["errors"].append("%s/%s 目标缺少中文描述" % (mode, tid))
                if o.get("optional") is None:
                    report["errors"].append("%s/%s 目标缺少 optional 标记" % (mode, tid))

        # 3) 图自洽：前置 / 后续互为反查
        for tid, rec in tasks.items():
            prereq = rec.get("prerequisites") or []
            if prereq:
                stats["withPrereq"] += 1
            for p in prereq:
                stats["edges"] += 1
                pid = p.get("taskId")
                if pid not in tasks:
                    report["errors"].append("%s/%s 前置任务不存在：%s" % (mode, tid, pid))
                    continue
                if p.get("logic") == "or":
                    stats["orEdges"] += 1
                if tid not in (tasks[pid].get("followUps") or []):
                    report["errors"].append("%s/%s 的反向索引缺失（前置 %s 未列出后续）" % (mode, tid, pid))
            for f in rec.get("followUps") or []:
                if f not in tasks:
                    report["errors"].append("%s/%s 后续任务不存在：%s" % (mode, tid, f))
                    continue
                if f not in rec.get("followUps"):
                    continue
                stats["withFollowUp"] += 1 if rec.get("followUps") else 0
                backs = {p.get("taskId") for p in (tasks[f].get("prerequisites") or [])}
                if tid not in backs:
                    report["errors"].append("%s/%s 的后续 %s 未把其列为前置" % (mode, tid, f))
            stats["failedEdges"] += len(rec.get("failedConditions") or [])

        # 4) 攻略覆盖
        for tid in tasks:
            g = guides.get(tid) or {}
            status = g.get("status")
            if status == "curated":
                stats["guideCurated"] += 1
            elif status == "generated":
                stats["guideGenerated"] += 1
            else:
                stats["guideMissing"] += 1
                report["warnings"].append("%s/%s 攻略缺失（status=%s）" % (mode, tid, status))
            if status in ("generated", "curated") and not (g.get("steps") or []):
                report["warnings"].append("%s/%s 攻略无步骤" % (mode, tid))

        # 5) 重名（同模式内不同 ID 同名 → 需人工确认不是数据串位）
        names = {}
        for tid, rec in tasks.items():
            names.setdefault(rec.get("nameZh"), []).append(tid)
        stats["dupNames"] = [{"name": k, "ids": v} for k, v in names.items() if len(v) > 1]

        stats["indexCounts"] = index.get("modes", {}).get(mode, {})
        if stats["indexCounts"].get("tasks") not in (None, len(tasks)):
            report["errors"].append("%s index.json 记录任务数 %s 与文件 %d 不符"
                                    % (mode, stats["indexCounts"].get("tasks"), len(tasks)))
        report["modes"][mode] = stats

    # 6) 模式隔离：三对集合差异
    if len(ids) == 3:
        pairs = {}
        for a, b in (("regular", "pve"), ("regular", "pvps"), ("pve", "pvps")):
            pairs["%s|%s" % (a, b)] = {
                "leftOnly": sorted(ids[a] - ids[b]),
                "rightOnly": sorted(ids[b] - ids[a]),
                "shared": len(ids[a] & ids[b]),
            }
        report["modeDiff"] = pairs
        for key, val in pairs.items():
            if not val["leftOnly"] and not val["rightOnly"] and not val["shared"]:
                report["warnings"].append("%s 两侧任务集合都为空" % key)
        # 三种模式若任务集合完全一致 → 说明没有真正区分（PvPS 复制 PvP 的典型症状）
        if ids["regular"] == ids["pvps"]:
            report["errors"].append("PvP 与 PvPS 任务集合完全一致：PvPS 疑似直接复制 PvP 数据")
        # onlyInModes 必须与实际集合一致
        for mode in MODES:
            doc = load(os.path.join(TASKS_DIR, "tasks.%s.json" % mode))
            for tid, rec in doc["tasks"].items():
                expect = sorted(m for m in MODES if tid in ids[m])
                only = rec.get("onlyInModes") or []
                if only and sorted(only) != expect:
                    report["errors"].append("%s/%s onlyInModes=%s 与实际 %s 不符"
                                            % (mode, tid, only, expect))
                if (rec.get("modeScope") == "all") != (len(expect) == len(MODES)):
                    report["errors"].append("%s/%s modeScope=%r 与实际 %s 不符"
                                            % (mode, tid, rec.get("modeScope"), expect))

    # 7) 数据来源有效
    src_list = sources.get("sources") or []
    for mode in MODES:
        mine = [s for s in src_list if s.get("mode") == mode and s.get("endpoint") == "tasks"]
        if not mine:
            report["errors"].append("sources.json 缺少 %s 的 tasks 来源记录" % mode)
            continue
        s = mine[0]
        for field in ("url", "sha256", "fetchedAt", "bytes"):
            if not s.get(field):
                report["errors"].append("sources.json %s 来源缺字段 %s" % (mode, field))
        if UPSTREAM[mode] not in (s.get("url") or ""):
            report["errors"].append("%s 来源 URL=%s 未指向上游端点 %s"
                                    % (mode, s.get("url"), UPSTREAM[mode]))
        if s.get("stale"):
            report["warnings"].append("%s 本次抓取失败，正在使用上一次有效快照：%s"
                                      % (mode, s.get("error")))
    if sources.get("failures"):
        report["warnings"].append("抓取失败端点 %d 个（已回退旧快照）" % len(sources["failures"]))

    # 8) 赛季元信息
    spath = os.path.join(TASKS_DIR, "season.json")
    if os.path.exists(spath):
        season = load(spath)
        report["season"] = {"id": season.get("id"), "nameEn": season.get("nameEn"),
                            "nameZh": season.get("nameZh"),
                            "startISO": season.get("startISO"),
                            "endISO": season.get("endISO"),
                            "perks": len((season.get("perks") or {}).get("common") or []) +
                                     len((season.get("perks") or {}).get("personal") or [])}
        if not season.get("id") or not season.get("startISO"):
            report["warnings"].append("season.json 缺 id / 起止时间")
        if season.get("nameZhMissing"):
            report["notes"] = (report.get("notes") or []) + [
                "赛季名上游只提供英文「%s」，中文表无译名：界面按原样显示并标注，不自动翻译"
                % season.get("nameEn")]
    else:
        report["warnings"].append("缺少 season.json（赛季元信息不可用，界面会显示「数据待补充」）")

    # 9) 差异报告存在且覆盖三对
    dpath = os.path.join(TASKS_DIR, "diff-report.json")
    if os.path.exists(dpath):
        diff = load(dpath)
        pairs = {"%s|%s" % (p["left"], p["right"]) for p in (diff.get("pairs") or [])}
        need = {"regular|pve", "regular|pvps", "pve|pvps"}
        missing = need - pairs
        if missing:
            report["errors"].append("diff-report.json 缺少配对：%s" % sorted(missing))
        for p in diff.get("pairs") or []:
            left_n = (p.get("counts") or {}).get("tasks", {}).get("left")
            if left_n != len(ids.get(p.get("left"), ())):
                report["warnings"].append("diff-report %s|%s 左侧任务数与当前数据不一致（报告过期？可重跑 diff_tasks.py）"
                                          % (p.get("left"), p.get("right")))
        report["diffPairs"] = sorted(pairs)
    else:
        report["warnings"].append("缺少 diff-report.json（跑 tools/diff_tasks.py 生成）")

    report["ok"] = not report["errors"]
    if not quiet:
        os.makedirs(OUT_DIR, exist_ok=True)
        with open(os.path.join(OUT_DIR, "task-validation.json"), "w", encoding="utf-8", newline="\n") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=1)
        for mode, st in report["modes"].items():
            print("%-8s tasks=%-4d objectives=%-5d edges=%-4d or=%-2d fail=%-2d seasonOnly=%-2d guides=%d/%d"
                  % (mode, st["tasks"], st["objectives"], st["edges"], st["orEdges"],
                     st["failedEdges"], st["seasonOnly"],
                     st["guideGenerated"] + st["guideCurated"], st["tasks"]))
            if st["dupNames"]:
                print("   重名 %d 组（同名不同 ID，需人工确认）：%s"
                      % (len(st["dupNames"]), [x["name"] for x in st["dupNames"]][:5]))
        for key, val in (report.get("modeDiff") or {}).items():
            print("   diff %-16s leftOnly=%-3d rightOnly=%-3d shared=%d"
                  % (key, len(val["leftOnly"]), len(val["rightOnly"]), val["shared"]))
        print("errors=%d warnings=%d -> %s" % (len(report["errors"]), len(report["warnings"]),
                                               "OK" if report["ok"] else "FAIL"))
        for e in report["errors"][:10]:
            print("  E:", e)
    return report


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)
    rep = validate(quiet=args.quiet)
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
