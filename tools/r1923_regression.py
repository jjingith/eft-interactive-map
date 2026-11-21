# -*- coding: utf-8 -*-
"""汇总 R19.15.3 的回归结果（真实审计文件 → regression-results.json）。

数据来源全部是本轮重新生成的审计物料，不使用旧轮次的手写数字：
  dom-all-after.json            163 把枪真实 DOM 扫描
  browser-check.json            AK 燕尾槽真实浏览器流程
  all-gun-layout-audit.json     布局结构 + 需求符合性
  optic-slot-audit-final.json   Nightforce 两个直接槽位
  r19.12-canvas-audit/*         优化器 / 无解 / 默认弹药（本轮重跑）
  r19.15-theme-audit/style-audit-after.json  XP Luna 计算样式
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "r19.15.3-layout-audit")


def j(rel):
    return json.load(open(os.path.join(ROOT, rel), encoding="utf-8"))


def run_pytest():
    proc = subprocess.run([sys.executable, "-m", "pytest", "tests/", "-q", "--tb=line"],
                          cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=1800)
    tail = [ln for ln in (proc.stdout or "").strip().splitlines() if ln.strip()]
    line = tail[-1] if tail else ""
    import re as _re
    def _num(word):
        m = _re.search(r"(\d+)\s*" + word, line)
        return int(m.group(1)) if m else 0
    passed, skipped, failed = _num("passed"), _num("skipped"), _num("failed")
    return {"command": "C:/Python314/python.exe -m pytest tests/ -q", "summaryLine": line,
            "passed": passed, "skipped": skipped, "failed": failed,
            "returncode": proc.returncode,
            "failures": [ln for ln in tail if ln.startswith("FAILED")][:10]}


def main():
    dom = j("docs/r19.15.3-layout-audit/dom-all-after.json")
    browser = j("docs/r19.15.3-layout-audit/browser-check.json")
    audit = j("docs/r19.15.3-layout-audit/all-gun-layout-audit.json")
    optic = j("docs/r19.15.3-layout-audit/optic-slot-audit-final.json")
    conflicts = j("docs/r19.12-canvas-audit/optimizer-conflicts.json")
    final_val = j("docs/r19.12-canvas-audit/optimizer-final-validation.json")
    no_sol = j("docs/r19.12-canvas-audit/optimizer-no-solution.json")
    ammo = j("docs/r19.12-canvas-audit/default-ammo.json")
    style = j("docs/r19.15-theme-audit/style-audit-after.json")

    hover = (style.get("buttons") or {}).get("hover") or {}
    hover_img = hover.get("img") or ""
    visual = browser.get("visual") or {}

    rep = {
        "generatedFor": "R19.15.3",
        "testSuite": run_pytest(),
        "browserScan": {
            "source": "真实 UI 选枪 + 应用真实默认装配（localStorage），禁缓存",
            "guns": len(dom.get("guns") or {}),
            "failed": len(dom.get("fail") or []),
            "viewport": "1920×919（全量）+ 1384×805（AK-74N 另拍）"
        },
        "layoutAudit": {
            "scanned": audit.get("scanned"),
            "anomalies": len(audit.get("anomalies") or []),
            "summary": audit.get("summary")
        },
        "visual": {
            "buttonHoverOrange": "255, 204, 0" in hover_img and "255, 153, 51" in hover_img,
            "hoverGradient": hover_img,
            "hoverBorder": hover.get("border"),
            "connectorLines": int(visual.get("linkPaths", 0)) + int(visual.get("svgCount", 0)),
            "skinVisible": bool(visual.get("skinCount", 0) or visual.get("skinTag", 0)),
            "fontFamily": visual.get("fontBody"),
            "panelRadius": style.get("cornerRadius", {})
        },
        "features": {
            "optimizerConflictFree": (conflicts.get("scan") or {}).get("buildsWithPairs") == 0,
            "optimizerConflictScan": conflicts.get("scan"),
            "optimizerStructural": final_val.get("structuralOnly"),
            "magCapacity100": all(not b["ok"] for c in no_sol.get("cases") or []
                                  for b in c.get("builds") or []),
            "magCapacityCases": [c.get("case") for c in no_sol.get("cases") or []],
            "nightforceTwoSlots": optic["nightforce"]["declared"] == 2
                                  and optic["nightforce"]["tree"] == 2
                                  and optic["nightforce"]["layout"] == 2,
            "nightforce": optic["nightforce"],
            "defaultAmmo": {"guns": ammo.get("scan", {}).get("guns"), "withAmmo": ammo.get("scan", {}).get("withAmmo")},
            "dovetailAnchors": j("docs/r19.15.3-layout-audit/ak-dovetail-final.json").get("summary"),
            "rearSightBand": j("docs/r19.15.3-layout-audit/ak-dovetail-sight-layout.json").get("summary")
        },
        "browserFlow": {k: {kk: vv for kk, vv in v.items() if kk != "slots"}
                        for k, v in (browser.get("flow") or {}).items() if isinstance(v, dict)}
    }
    path = os.path.join(OUT, "regression-results.json")
    json.dump(rep, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("tests:", rep["testSuite"]["summaryLine"])
    print("hoverOrange:", rep["visual"]["buttonHoverOrange"], "| connector:", rep["visual"]["connectorLines"],
          "| skin:", rep["visual"]["skinVisible"])
    print("optimizer:", rep["features"]["optimizerConflictFree"], rep["features"]["optimizerStructural"] and
          "%s/%s" % (rep["features"]["optimizerStructural"]["ok"], rep["features"]["optimizerStructural"]["total"]))
    print("mag100:", rep["features"]["magCapacity100"], "| nightforce:", rep["features"]["nightforceTwoSlots"])
    print("wrote", path)


if __name__ == "__main__":
    main()
