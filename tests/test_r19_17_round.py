# -*- coding: utf-8 -*-
"""R19.17 校准接入主程序专项。

覆盖：引擎全量应用（397 条对照 + 合成身份隔离/回退/交换/挤位/topPad/AMMO 躲让）、
浏览器验收 A–E 证据、校准器预览与主画布一致性、数据安全、版本同步、主引擎只读校准数据。
证据来源：docs/r19.17-calibration-integration/（engine-apply-audit.json / browser-accept.json）
+ node 实跑 tools/r1925_engine.js（全量对照每次重算）。
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "app.js")
CALIB_JS = os.path.join(ROOT, "calibrator.js")
HTML = os.path.join(ROOT, "index.html")
CALIB = os.path.join(ROOT, "data", "gun-layout-calibration.json")
ENGINE_TOOL = os.path.join(ROOT, "tools", "r1925_engine.js")
AUD = os.path.join(ROOT, "docs", "r19.17-calibration-integration")

need_node = subprocess.run(
    [sys.executable, "-c", "import shutil,sys;sys.exit(0 if shutil.which('node') else 1)"]
).returncode != 0


def _read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def _json(name):
    p = os.path.join(AUD, name)
    assert os.path.exists(p), "缺 %s（先跑对应验收脚本）" % name
    with open(p, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def engine_audit():
    """每次测试会话实跑一次引擎审计（全量校准记录对照 + 合成用例）。"""
    if need_node:
        pytest.skip("需要 node")
    proc = subprocess.run(["node", ENGINE_TOOL], cwd=ROOT, capture_output=True, text=True)
    assert proc.returncode == 0, "r1925_engine.js 失败：\n%s\n%s" % (proc.stdout[-2000:], proc.stderr[-2000:])
    return _json("engine-apply-audit.json")


@pytest.fixture(scope="module")
def browser():
    return _json("browser-accept.json")


# ---------------------------------------------------------------- 引擎全量应用
def test_corpus_every_record_applied_exactly(engine_audit):
    """R19.18 升级：真实条件子槽被修正移除后，旧记录变成「失效记录」（保留不生效）；
    口径 = 已应用 + 失效 + 当前不可用（真实互斥）= 全部记录，且没有任何静默丢失。"""
    c = engine_audit["corpus"]
    assert c["totalRecords"] >= 1
    stale = c.get("stale", 0)
    suppressed = c.get("suppressed", 0)
    assert c["applied"] + stale + suppressed == c["totalRecords"], c
    assert c["unmatched"] == stale + suppressed, "存在既匹配不上、又没被解释的记录"
    assert c["fallback"] == 0
    assert c["exactCoords"] + stale + suppressed == c["totalRecords"], \
        "存在落点与保存坐标不一致的记录"


def test_synthetic_identity_and_fallback(engine_audit):
    k = engine_audit["checks"]
    for name in ("autoBaseline", "akApplied", "ownerIsolation", "unmatchedFallback",
                 "invalidCoordsFallback", "bodyReject", "cellConflict",
                 "ownerChangeNoCross", "noRecordsNoChange"):
        assert k.get(name) is True, "%s 未通过" % name


def test_synthetic_move_semantics(engine_audit):
    k = engine_audit["checks"]
    for name in ("swapApplied", "displaceKeepsAll", "topPadRecomputed", "ammoDodged",
                 "roleOverride", "noCalibBaseline", "engineAutoReadsCalib"):
        assert k.get(name) is True, "%s 未通过" % name


# ---------------------------------------------------------------- 浏览器验收 A–F
def test_browser_A_calibrated_guns_applied(browser):
    assert browser.get("ok") is True, browser.get("failures")
    a = browser["A"]
    assert len(a) >= 3
    for key, per in a.items():
        assert per["calib"] == "1", key
        assert per["records"] >= 1 and per["match"] == per["records"], (key, per.get("mismatch"))
        assert per["fallback"] == "0", key


def test_browser_B_uncalibrated_falls_back_to_auto(browser):
    b = browser["B"]
    assert b["ok"] is True and b["calib"] == "0" and b["recordsInFile"] == 0
    assert b["cards"] >= 6 and b["rows"] >= 6, "未校准枪械自动布局必须正常渲染"


def test_browser_C_install_replace_remove_keeps_calibrated_coords(browser):
    c = browser["C"]
    assert c["afterInstall"]["installed"] is True
    assert c["afterInstall"]["mountKept"] is True
    assert c["afterReplace"]["changed"] is True
    assert c["afterReplace"]["mountKept"] is True
    assert c["afterRemove"]["emptied"] is True
    assert c["afterRemove"]["mountKept"] is True
    assert len(c["afterRemove"]["childSlots"]) == 0
    assert c["afterRemove"]["cards"] == c["before"]["cards"], "卸件后槽位卡必须复原"


def test_browser_D_persists_through_reload(browser):
    d = browser["D"]
    assert d["savedRecords"], "D：未产生保存记录"
    reloaded = d["afterReload"]
    assert reloaded["calib"] == "1" and reloaded["applied"] != "0"
    assert reloaded["slots"] and all(s["ok"] for s in reloaded["slots"]), reloaded["slots"]


def test_browser_E_calibration_content_untouched(browser):
    e = browser["E"]
    assert e["contentUnchanged"] is True, e.get("diffGuns")
    assert e["recordsBefore"] == e["recordsAfter"] and e["recordsBefore"] >= 1
    assert e["gunsBefore"] == e["gunsAfter"]


def test_browser_F_calibrator_matches_main_canvas(browser):
    f = browser["F"]
    assert f["compared"] >= 6 and f["allSame"] is True, f.get("diffs")


# ---------------------------------------------------------------- 源码契约与数据安全
def test_calibrator_preview_shares_application_rule():
    js = _read(CALIB_JS)
    assert "previewView" in js
    assert "GWCalib.applyCalibration" in js, "校准预览必须走主程序同一条规则"
    assert "curRows" in js and "previewTopPad" in js, "顶部扩展必须按最终坐标动态重算"
    assert "layoutCalibrator=1" in js, "校准器入口约束不得破坏"


def test_engine_source_contract():
    js = _read(APP)
    assert "function ensureLayoutCalib" in js
    assert "function gwApplyCalibToLayout" in js and "function gwCalibKey" in js
    assert "gwCalibRecordsFor" in js
    assert "noCalib" in js
    assert "GW_CALIB_STATE" in js
    assert 'data-calib-applied' in js, "浏览器验收钩子缺失"
    assert 'fetch("/api/layout-calibration", { cache: "no-cache" })' in js, "校准数据必须走 GET 读取"
    seg = js[js.index("function ensureLayoutCalib"):]
    seg = seg[:seg.index("\n  function ")]
    assert "POST" not in seg, "app.js 校准读取必须只读"
    html = _read(HTML)
    m = re.search(r'AM_BUILD = "([^"]+)"', js)
    assert m and m.group(1).startswith("R19."), m and m.group(1)
    build = m.group(1).lower()
    for name in ("style.css", "theme-windows-xp.css", "calibrator.css",
                 "app.js", "gun_builder.js", "combat_sim.js", "calibrator.js"):
        assert re.search(re.escape(name) + r"\?v=" + re.escape(build), html), "%s 版本串未同步" % name


def test_calibration_file_intact():
    d = json.loads(_read(CALIB))
    assert d.get("schemaVersion") == 1
    guns = d.get("guns") or {}
    assert guns, "校准数据被清空"
    total = sum(len((g or {}).get("slots") or {}) for g in guns.values())
    assert total >= 1
    # 身份键必须遵循 slotPath|slotId|ownerItemId
    for g in guns.values():
        for k in (g.get("slots") or {}):
            assert k.count("|") == 2, k
