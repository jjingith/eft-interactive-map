# -*- coding: utf-8 -*-
"""R19.15 回归：ASH-12 主体行压缩 / 上导轨战术车道 / 全量枪械审计 / 连接线移除 /
合成图隐藏 / XP Luna 设计令牌与按钮橙黄。

证据来源：docs/r19.15-theme-audit/ 下的实跑产物（node 审计 + 浏览器实测 + pytest）。
"""
from __future__ import annotations

import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "app.js")
CSS = os.path.join(ROOT, "style.css")
THEME = os.path.join(ROOT, "theme-windows-xp.css")
HTML = os.path.join(ROOT, "index.html")
AUD = os.path.join(ROOT, "docs", "r19.15-theme-audit")


def _read(p):
    with open(p, "r", encoding="utf-8") as f:
        return f.read()


def _json(name):
    p = os.path.join(AUD, name)
    assert os.path.exists(p), "缺 %s（先跑对应审计脚本）" % name
    return json.load(open(p, encoding="utf-8"))


# ---------------------------------------------------------------- 1. ASH-12
def test_ash12_main_row_compacted_and_tactical_not_on_body_row():
    d = _json("ash12-layout-audit.json")
    assert d["gun"].startswith("ASh-12")
    bases = [c["base"] for c in d["mainRow"]]
    assert bases == ["muzzle", "handguard"], bases
    cols = [c["col"] for c in d["mainRow"]]
    assert cols == [d["body"]["col"] - 2, d["body"]["col"] - 1], cols
    # 根级战术槽全部不在主体行
    for t in d["rootTacticalSlots"]:
        assert t["row"] != d["body"]["row"], t
        assert t["row"] in (2, 6), t
    # 修复前证据保留（曾被塞进 r3c1/r3c3）
    was = d["before"]["mainRowWas"]
    assert any(x["slot"].startswith("mod_tactical") for x in was)


def test_ash12_browser_measured():
    d = _json("browser-check.json")
    a = d["ash12"]
    assert a["mainContiguous"] is True
    assert a["mainAdjacentToBody"] is True
    assert a["tacticalOnBodyRow"] == []
    assert a["phantomCount"] == 0
    assert len(a["rowHeights"]) == 6 and min(a["rowHeights"]) >= 24
    vp = d["viewports"]["1384"]
    assert vp["mainAdjacentToBody"] is True
    assert vp["phantomCount"] == 0


# ------------------------------------------------------- 2. 全量枪械审计
def test_all_guns_scanned_without_anomalies():
    d = _json("all-gun-slot-audit.json")
    assert d["summary"]["scanned"] >= 150
    assert d["summary"]["withAnomalies"] == 0, d["anomalies"][:3]
    assert d["summary"]["clean"] == d["summary"]["scanned"]
    # 每把枪都要有真实槽位规模与落位数量
    for g in d["guns"]:
        assert g["treeSlots"] >= 1
        assert g["placedCells"] >= 1
        assert g["rows"] >= 6


def test_top_row_order_front_tactical_scope_rear():
    d = _json("tactical-slot-lanes.json")
    assert d["summary"]["orderViolations"] == 0
    checked = 0
    for g in d["guns"]:
        o = g["topRowOrder"]
        if not o["tacticalCols"]:
            continue
        checked += 1
        for c in o["tacticalCols"]:
            if o["frontSightCol"] is not None:
                assert c > o["frontSightCol"], (g["gun"], c, o)
            if o["scopeCol"] is not None:
                assert c < o["scopeCol"], (g["gun"], c, o)
    assert checked >= 10


def test_tactical_lane_never_body_row():
    d = _json("tactical-slot-lanes.json")
    assert d["summary"]["rootTacticalGuns"] >= 10
    for g in d["guns"]:
        for s in g["slots"]:
            assert s["lane"] in ("r2 上导轨行", "r6 备用车道"), (g["gun"], s)


# --------------------------------------------------- 3. 连接线 / 合成图
def test_connector_lines_removed():
    js = _read(APP)
    assert "el.gwTree.appendChild(svg)" not in js
    assert "requestAnimationFrame(function () { gwDrawLinks(svg, el.gwTree); })" not in js
    assert "gwBindLinksRedraw();" not in js
    d = _json("connector-lines.json")
    assert d["browserEvidence"]["svgCount"] == 0
    assert d["browserEvidence"]["linkPaths"] == 0
    assert d["codeEvidence"]["keepsFunctionImplementation"] is True


def test_skin_hidden():
    js = _read(APP)
    assert "var GW_SKIN_ENABLED = false;" in js
    d = _json("browser-check.json")
    assert d["skin"]["skin"] == 0
    assert d["skin"]["tag"] == 0


# ------------------------------------------------------- 4. 视觉令牌
def test_design_tokens_present_and_used():
    css = _read(THEME)
    for tok in ("--xp-font-family", "--xp-fs-micro", "--xp-fs-compact", "--xp-fs-body",
                "--xp-space-1", "--xp-space-7", "--xp-radius-panel", "--xp-radius-control",
                "--xp-radius-btn", "--xp-divider", "--xp-hover-a", "--xp-hover-c"):
        assert tok in css, "缺设计令牌 " + tok
    d = _json("design-tokens.json")
    assert d["tokens"]["--xp-font-family"].startswith("Tahoma")
    assert d["tokens"]["--xp-hover-a"].lower() == "#ffcc00"
    # 统一层必须实际引用令牌（不是写死一堆散值）
    assert "var(--xp-hover-a)" in css and "var(--xp-radius-panel)" in css


def test_font_family_unified_after():
    d = _json("style-audit-after.json")
    for v in ("map", "loadout", "gun", "ammo"):
        body = d["views"][v]["body"]
        assert body["font"].startswith("Tahoma"), (v, body["font"])
        # 不得出现碎片字号（由 em 继承产生）。
        # 地图 SVG <text> 的字号属于地理图层缩放，不在统一范围内（任务书明确不得改地图层）。
        elems = d["views"][v].get("fractionalSizes") or []
        bad = [x for x in elems if x.get("tag") not in ("text", "tspan", "textPath")]
        assert not bad, bad[:5]


def test_corner_radius_reduced():
    d = _json("corner-radius-audit.json")
    for v in ("map", "gun"):
        assert (d["bigRadiusAfter"][v] or 0) == 0
    comp = d["computed"]["gun"]
    assert comp["panel"]["radius"] in ("0px", "1px", "2px"), comp["panel"]["radius"]
    assert comp["tableCell"]["radius"] == "0px", comp["tableCell"]["radius"]
    assert comp["button"]["radius"] in ("1px", "2px", "3px"), comp["button"]["radius"]


def test_button_orange_hover_and_persistent():
    d = _json("button-states.json")
    m = d["measured"]
    hover = m["genericHoverAfter"] or {}
    assert "255, 204, 0" in (hover.get("img") or ""), hover
    assert "255, 153, 51" in (hover.get("img") or ""), hover
    b = m["browserCheck"]
    assert "255, 204, 0" in (b["hover"]["img"] or "")
    # 点击后离开鼠标仍为橙黄（data-flash 或 aria 选中态，同属橙黄色阶）
    leave_img = b["afterLeave"]["img"] or ""
    assert ("255, 204, 0" in leave_img) or ("255, 224, 138" in leave_img), leave_img
    assert b["afterLeave"]["attr"] == "1" or b["clicked"]["attr"] == "1"
    # 导航选中态为橙黄（不再是蓝色）
    nav = m["navSelectedAfter"]
    assert "255" in (nav.get("img") or "") or "255" in (nav.get("bg") or ""), nav


# ------------------------------------------------------- 5. 版本与瞄具
def test_version_synced_and_nightforce_two_slots():
    js = _read(APP)
    html = _read(HTML)
    m = re.search(r'AM_BUILD = "([^"]+)"', js)
    assert m and m.group(1).startswith("R19.")   # 版本标记跟随 AM_BUILD 动态同步
    assert ("?v=" + m.group(1).lower()) in html
    o = _json("optic-slot-audit.json")
    nf = o["confirmedByGameplay"][0]
    assert nf["directSlots"] == 2
    assert nf["dataCheck"] == ["mod_scope_000", "mod_scope_001"]
    assert o["pendingVerification"]["count"] >= 100
