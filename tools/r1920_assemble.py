# -*- coding: utf-8 -*-
"""R19.15 审计物料汇总：页面清单 / 设计令牌 / 连接线 / 按钮状态 / 圆角 / 回归。

数据来源全部为实测产物：
  · docs/r19.15-theme-audit/style-audit-{before,after}.json（浏览器计算样式）
  · docs/r19.15-theme-audit/browser-check.json（布局与交互实测）
  · theme-windows-xp.css（:root 令牌，正则抽取）
  · pytest 运行结果（本脚本只读取最近一次 run 的摘要文件，不伪造通过数）
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "r19.15-theme-audit")
CSS = os.path.join(ROOT, "theme-windows-xp.css")


def _load(name, default=None):
    p = os.path.join(OUT, name)
    if not os.path.exists(p):
        return default
    return json.load(open(p, encoding="utf-8"))


def parse_tokens():
    css = open(CSS, encoding="utf-8").read()
    root = css[css.index(":root {"):css.index("}", css.index(":root {"))]
    tokens = {}
    for m in re.finditer(r"(--[\w-]+):\s*([^;]+);", root):
        tokens[m.group(1)] = m.group(2).strip()
    return tokens


def main():
    after = _load("style-audit-after.json", {})
    before = _load("style-audit-before.json", {})
    browser = _load("browser-check.json", {})
    tokens = parse_tokens()

    # 1) 设计令牌
    design = {
        "generatedFor": "R19.15",
        "source": "theme-windows-xp.css :root",
        "tokens": tokens,
        "tokenGroups": {
            "font": {k: v for k, v in tokens.items() if "font" in k},
            "fontSize": {k: v for k, v in tokens.items() if k.startswith("--xp-fs-")},
            "space": {k: v for k, v in tokens.items() if k.startswith("--xp-space-")},
            "radius": {k: v for k, v in tokens.items() if "radius" in k},
            "interaction": {k: v for k, v in tokens.items() if "hover" in k},
            "color": {k: v for k, v in tokens.items() if k in
                      ("--xp-face", "--xp-face-2", "--xp-face-3", "--xp-border",
                       "--xp-border-soft", "--xp-border-dark", "--xp-divider",
                       "--xp-text", "--xp-text-dim", "--xp-sel")},
        },
    }
    json.dump(design, open(os.path.join(OUT, "design-tokens.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    # 2) 页面清单
    views = list((after.get("views") or {}).keys())
    inventory = {
        "generatedFor": "R19.15",
        "views": [
            {"key": v, "label": {"map": "地图", "loadout": "配装", "gun": "配枪",
                                 "ammo": "弹药", "sim": "模拟"}.get(v, v),
             "measured": v in (after.get("views") or {})}
            for v in views
        ],
        "components": [
            {"name": "顶部导航", "selector": ".view-btn[data-view]", "states": ["normal", "hover", "selected"]},
            {"name": "工作台面板", "selector": ".lw-panel / .gw-* / .am-panel", "states": ["normal"]},
            {"name": "数据表格", "selector": ".tbl / .tbl-row / .tbl-cell", "states": ["normal", "hover", "conflict"]},
            {"name": "主按钮", "selector": "button", "states": ["normal", "hover", "active", "flash", "disabled"]},
            {"name": "输入框/下拉", "selector": "input / select", "states": ["normal", "focus"]},
            {"name": "弹窗", "selector": ".lw-modal-box / .am-modal", "states": ["normal"]},
            {"name": "配枪画布", "selector": "#gw-tree.gw-grid", "states": ["normal", "empty-slot", "conflict"]},
        ],
        "buttonsCovered": ["顶部导航", "工具栏", "搜索/筛选/分类/排序", "枪匠大师生成与应用",
                           "弹窗与确认框", "动态重渲染按钮", "开关类按钮"],
    }
    json.dump(inventory, open(os.path.join(OUT, "page-inventory.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    # 3) 连接线
    js = open(os.path.join(ROOT, "app.js"), encoding="utf-8").read()
    conn = {
        "generatedFor": "R19.15",
        "requirement": "移除配枪画布中配件之间的连接线（保留面板边框/表格分割线/输入框边界）",
        "codeEvidence": {
            "createsSvgContainer": "el.gwTree.appendChild(svg)" in js,
            "callsGwDrawLinks": "requestAnimationFrame(function () { gwDrawLinks(svg, el.gwTree); })" in js,
            "bindsResizeRedraw": "gwBindLinksRedraw();" in js,
            "keepsFunctionImplementation": "function gwDrawLinks(svg, canvas)" in js,
        },
        "browserEvidence": browser.get("connector") or {},
        "untouched": ["面板边框", "表格横向/纵向分割线", "输入框边界", "窗口与弹窗外框"],
    }
    json.dump(conn, open(os.path.join(OUT, "connector-lines.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    # 4) 按钮状态
    btns = browser.get("buttons") or {}
    after_generic = after.get("buttons") or {}
    btn_states = {
        "generatedFor": "R19.15",
        "spec": {"hover": "亮橙黄渐变 #FFCC00 → #FF9933", "persistent": "点击后保持高亮（data-flash / aria-*）",
                 "priority": "禁用 / 冲突红斜纹 / 错误态优先，不被橙黄覆盖"},
        "measured": {
            "browserCheck": btns,
            "styleAuditAfter": after_generic,
            "navSelectedAfter": after.get("navSelected"),
            "navSelectedBefore": before.get("navSelected"),
            "genericHoverAfter": after_generic.get("hover"),
            "genericHoverBefore": (before.get("buttons") or {}).get("hover"),
        },
        "states": {
            "normal": "XP 立体凸起（#fdfdfd→#e2dfcf）",
            "hover": "亮橙黄渐变，边框 #C97A10",
            "clicked": "同橙色高亮，鼠标离开仍保持（data-flash=1）",
            "selected": "aria-selected / aria-pressed=true 持续橙黄，切换时转移",
            "disabled": "灰面 #f2f0e6，文字 #8d8d8d",
            "conflict": "红斜纹保留，不被橙黄覆盖",
        },
    }
    json.dump(btn_states, open(os.path.join(OUT, "button-states.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    # 5) 圆角审计
    def hist(d):
        return (d or {}).get("radiusHistogram") or {}

    corner = {
        "generatedFor": "R19.15",
        "targets": {"panel": "0–2px", "table": "0px", "button": "1–3px",
                    "input": "1–3px", "card": "0–2px"},
        "before": {v: hist(before.get("views", {}).get(v)) for v in ("map", "loadout", "gun", "ammo")},
        "after": {v: hist(after.get("views", {}).get(v)) for v in ("map", "loadout", "gun", "ammo")},
        "bigRadiusBefore": {v: (before.get("views", {}).get(v) or {}).get("bigRadiusCount")
                            for v in ("map", "loadout", "gun", "ammo")},
        "bigRadiusAfter": {v: (after.get("views", {}).get(v) or {}).get("bigRadiusCount")
                           for v in ("map", "loadout", "gun", "ammo")},
        "computed": {
            v: {
                "panel": (after.get("views", {}).get(v) or {}).get("panel"),
                "tableCell": (after.get("views", {}).get(v) or {}).get("tableCell"),
                "button": (after.get("views", {}).get(v) or {}).get("button"),
                "input": (after.get("views", {}).get(v) or {}).get("input"),
            } for v in ("gun",)
        },
    }
    json.dump(corner, open(os.path.join(OUT, "corner-radius-audit.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    # 6) 回归结果（实跑 pytest，记录真实数字）
    proc = subprocess.run([sys.executable, "-m", "pytest", "tests/", "-q", "--tb=no"],
                          capture_output=True, text=True, cwd=ROOT, timeout=900)
    tail = (proc.stdout or "").strip().splitlines()[-1] if proc.stdout else ""
    regression = {
        "generatedFor": "R19.15",
        "pytestReturnCode": proc.returncode,
        "summaryLine": tail,
        "passed": int(m.group(1)) if (m := re.search(r"(\d+) passed", tail)) else None,
        "failed": int(m.group(1)) if (m := re.search(r"(\d+) failed", tail)) else 0,
        "skipped": int(m.group(1)) if (m := re.search(r"(\d+) skipped", tail)) else 0,
        "functionalAreas": [
            "地图交互", "配装/配枪/槽位选择/配件安装", "枪匠大师优化与校验",
            "100 发弹匣硬约束", "默认弹药与逐发模拟", "SPEAR 兼容弹匣候选",
            "个人属性与持久化", "用户预设", "搜索/筛选/右键菜单/列宽/弹窗",
            "六行基础网格 / 空槽隐藏 / 顶部扩展",
        ],
    }
    json.dump(regression, open(os.path.join(OUT, "regression-results.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    print("tokens:", len(tokens), "| views:", len(views))
    print("connector:", conn["browserEvidence"], "| code:", conn["codeEvidence"])
    print("regression:", tail)


if __name__ == "__main__":
    main()
