# -*- coding: utf-8 -*-
"""UI 现状审计（只读，不改任何文件）。

把「样式到底乱在哪」变成可复核的数字，而不是凭印象：
  · 每个样式表的体积、规则数、`!important`、硬编码颜色 / 字号 / 圆角 / 间距数量
  · 令牌（--xp-*）采用率：用了 var() 的声明占比
  · 组件实现分布：按钮 / 输入 / 弹窗 / 菜单 / 提示 / 表格 / 标签页 的类名与出现次数
  · 近似色聚类：把「肉眼几乎一样」的十六进制色归组，暴露复制粘贴出来的多套近似色
  · JS 内联样式：`style.width = …` 这类写法有多少处（这类最不受设计系统约束）

输出：
    docs/ui-system/audit-data.json   机读数据（audit.md 的数字来源）

用法：
    python tools/ui_audit.py
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "ui-system")

CSS_FILES = ["style.css", "theme-windows-xp.css", "tasks.css", "calibrator.css"]
JS_FILES = ["app.js", "tasks.js", "calibrator.js", "gun_builder.js", "combat_sim.js", "i18n.js"]

HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")
VAR = re.compile(r"var\(\s*--([a-z0-9-]+)")
FONT_SIZE = re.compile(r"font-size:\s*([^;}]+)")
RADIUS = re.compile(r"border-radius:\s*([^;}]+)")
PADDING = re.compile(r"padding(?:-[a-z]+)?:\s*([^;}]+)")
SELECTOR = re.compile(r"(^|})\s*([^{}@]+)\{", re.M)
DECL = re.compile(r"([a-z-]+)\s*:\s*([^;}]+)")

# 组件识别的关键词（类名 / id / data 属性）
COMPONENT_HINTS = {
    "Button": re.compile(r"\b(btn|button)\b", re.I),
    "Input": re.compile(r"\b(input|field|search)\b", re.I),
    "Select": re.compile(r"\b(select|dropdown|combo)\b", re.I),
    "Checkbox/Radio": re.compile(r"\b(check|radio|toggle)\b", re.I),
    "Tabs": re.compile(r"\b(tab|tabs|segmented)\b", re.I),
    "Menu": re.compile(r"\b(menu|popup|context)\b", re.I),
    "Dialog/Modal": re.compile(r"\b(modal|dialog|overlay|mask|backdrop)\b", re.I),
    "Tooltip": re.compile(r"\b(tooltip|tip|hint|popover)\b", re.I),
    "Table": re.compile(r"\b(table|thead|tbody|tr|td|th|row|grid-row)\b", re.I),
    "Badge/Status": re.compile(r"\b(badge|chip|tag|status|pill|flag)\b", re.I),
    "Panel/Group": re.compile(r"\b(panel|group|card|section|box|groupbox|fieldset)\b", re.I),
    "Toolbar": re.compile(r"\b(toolbar|topbar|menubar|statusbar|actionbar)\b", re.I),
}


def read(path):
    with open(os.path.join(ROOT, path), encoding="utf-8") as fh:
        return fh.read()


def norm_color(h: str) -> str:
    """统一成 #rrggbb（兼容 #abc / #abcd / #rrggbbaa，任何长度都不会抛异常）。"""
    h = h.lower().lstrip("#")
    if len(h) in (3, 4):       # #abc / #abcd → 展开成 6 位
        h = "".join(c * 2 for c in h[:3])
    h = (h + "000000")[:6]
    return "#" + h


def color_groups(counter: Counter) -> list[dict]:
    """把 RGB 距离 <= 6 的颜色归为「近似色同族」，暴露重复造色。"""
    items = list(counter.items())
    def rgb(h):
        h = h.lstrip("#")
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    used = [False] * len(items)
    groups = []
    for i, (c1, n1) in enumerate(items):
        if used[i]:
            continue
        used[i] = True
        r1 = rgb(c1)
        members = [(c1, n1)]
        for j in range(i + 1, len(items)):
            if used[j]:
                continue
            c2, n2 = items[j]
            r2 = rgb(c2)
            if max(abs(a - b) for a, b in zip(r1, r2)) <= 6:
                used[j] = True
                members.append((c2, n2))
        if len(members) > 1:
            groups.append({"colors": [m[0] for m in members],
                           "total": sum(m[1] for m in members)})
    groups.sort(key=lambda g: (-len(g["colors"]), -g["total"]))
    return groups[:14]


def audit_css(name: str) -> dict:
    css = read(name)
    hexes = [norm_color(h) for h in HEX.findall(css)]
    counter = Counter(hexes)
    rules = len(SELECTOR.findall(css))
    decls = DECL.findall(css)
    total_decl = len(decls)
    var_decls = sum(1 for k, v in decls if "var(--" in v)
    colors = [(k, v) for k, v in decls if k.startswith("color") or k in
              ("background", "border", "border-top", "border-bottom", "border-left", "border-right",
               "outline", "box-shadow", "fill", "stroke")]
    color_var = sum(1 for _k, v in colors if "var(--" in v)
    sizes = Counter(s.strip() for s in FONT_SIZE.findall(css))
    radii = Counter(s.strip() for s in RADIUS.findall(css))
    pads = Counter(s.strip() for s in PADDING.findall(css))
    return {
        "file": name,
        "bytes": len(css.encode("utf-8")),
        "rules": rules,
        "declarations": total_decl,
        "important": css.count("!important"),
        "hexOccurrences": len(hexes),
        "hexDistinct": len(counter),
        "topColors": counter.most_common(12),
        "nearDuplicateColorGroups": color_groups(counter),
        "varDecls": var_decls,
        "varAdoption": round(var_decls / max(total_decl, 1) * 100, 1),
        "colorDecls": len(colors),
        "colorVarAdoption": round(color_var / max(len(colors), 1) * 100, 1),
        "fontSizes": sizes.most_common(14),
        "fontSizeDistinct": len(sizes),
        "radii": radii.most_common(8),
        "radiusDistinct": len(radii),
        "paddingDistinct": len(pads),
    }


def audit_js(name: str) -> dict:
    js = read(name)
    return {
        "file": name,
        "bytes": len(js.encode("utf-8")),
        "lines": js.count("\n") + 1,
        "inlineStyleAssign": len(re.findall(r"\.style\.[a-zA-Z]+\s*=", js)),
        "setAttributeStyle": len(re.findall(r"setAttribute\(\s*[\"']style[\"']", js)),
        "cssText": js.count("cssText"),
        "createElement": len(re.findall(r"document\.createElement\(", js)),
        "innerHTML": js.count("innerHTML"),
        "classList": len(re.findall(r"classList\.(add|toggle|remove)", js)),
        "windowConfirm": js.count("window.confirm"),
        "windowAlert": js.count("window.alert"),
        "hexColorLiterals": len(set(norm_color(h) for h in HEX.findall(js))),
    }


def component_inventory() -> dict:
    """按关键词统计「谁在定义/使用哪类控件」，说明重复实现范围。"""
    sources = {f: read(f) for f in CSS_FILES + JS_FILES}
    out = {}
    for comp, pat in COMPONENT_HINTS.items():
        hits = {}
        for f, text in sources.items():
            n = len(pat.findall(text))
            if n:
                hits[f] = n
        if hits:
            out[comp] = dict(sorted(hits.items(), key=lambda kv: -kv[1]))
    return out


def dialog_inventory() -> list[dict]:
    """列出所有弹窗/遮罩类的真实实现（类名 + 文件 + 是否独立一套）。"""
    pats = {
        "modal": re.compile(r"\.([a-z0-9-]*modal[a-z0-9-]*)", re.I),
        "overlay/mask": re.compile(r"\.([a-z0-9-]*(overlay|mask|backdrop)[a-z0-9-]*)", re.I),
        "menu/popup": re.compile(r"\.([a-z0-9-]*(menu|popup)[a-z0-9-]*)", re.I),
        "tooltip/tip": re.compile(r"\.([a-z0-9-]*(tooltip|tip)[a-z0-9-]*)", re.I),
    }
    found = defaultdict(set)
    for f in CSS_FILES:
        css = read(f)
        for kind, pat in pats.items():
            for m in pat.findall(css):
                found[kind].add("%s:%s" % (f, m))
    return [{"kind": k, "selectors": sorted(v)} for k, v in found.items()]


def main():
    os.makedirs(OUT, exist_ok=True)
    data = {
        "schema": 1,
        "tool": "tools/ui_audit.py",
        "css": [audit_css(f) for f in CSS_FILES if os.path.exists(os.path.join(ROOT, f))],
        "js": [audit_js(f) for f in JS_FILES if os.path.exists(os.path.join(ROOT, f))],
        "components": component_inventory(),
        "dialogs": dialog_inventory(),
    }
    total_hex = sum(c["hexOccurrences"] for c in data["css"])
    all_colors = Counter()
    for c in data["css"]:
        for col, n in c["topColors"]:
            pass
    data["summary"] = {
        "cssBytes": sum(c["bytes"] for c in data["css"]),
        "cssFiles": len(data["css"]),
        "rules": sum(c["rules"] for c in data["css"]),
        "important": sum(c["important"] for c in data["css"]),
        "hexOccurrences": total_hex,
        "hexDistinctMax": max(c["hexDistinct"] for c in data["css"]),
        "varAdoptionAvg": round(sum(c["varAdoption"] for c in data["css"]) / len(data["css"]), 1),
        "colorVarAdoptionAvg": round(
            sum(c["colorVarAdoption"] for c in data["css"]) / len(data["css"]), 1),
        "inlineStyleAssign": sum(j["inlineStyleAssign"] for j in data["js"]),
        "windowConfirm": sum(j["windowConfirm"] for j in data["js"]),
        "distinctFontSizes": sorted({s for c in data["css"] for s, _ in c["fontSizes"]}),
        "distinctRadii": sorted({s for c in data["css"] for s, _ in c["radii"]}),
    }
    path = os.path.join(OUT, "audit-data.json")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)

    s = data["summary"]
    print("CSS %d 个文件 %.1f KB / %d 条规则 / !important %d 处"
          % (s["cssFiles"], s["cssBytes"] / 1024, s["rules"], s["important"]))
    print("颜色：硬编码 %d 次，单文件最多 %d 种；var() 声明占比 %.1f%%，颜色声明里 %.1f%%"
          % (s["hexOccurrences"], s["hexDistinctMax"], s["varAdoptionAvg"], s["colorVarAdoptionAvg"]))
    print("字体号：%d 种 → %s" % (len(s["distinctFontSizes"]), s["distinctFontSizes"]))
    print("圆角：%d 种 → %s" % (len(s["distinctRadii"]), s["distinctRadii"]))
    print("JS 内联样式赋值 %d 处；window.confirm %d 处" % (s["inlineStyleAssign"], s["windowConfirm"]))
    for c in data["css"]:
        print("  %-22s %6.1fKB rules=%-4d hex=%-4d(%-3d种) var=%.1f%% 色var=%.1f%%"
              % (c["file"], c["bytes"] / 1024, c["rules"], c["hexOccurrences"],
                 c["hexDistinct"], c["varAdoption"], c["colorVarAdoption"]))
    print("写入", path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
