# -*- coding: utf-8 -*-
"""R19.16 武器槽位布局校准器专项。

覆盖：数据校验（身份 / 坐标 / 冲突）、原子保存与备份恢复、导入拒绝、
工具入口、浏览器证据（拖动 / 撤销 / 重做 / 交换 / 本体保护 / 条件槽位 / 保存重载 / 普通页无调试元素）。
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import layoutcal  # noqa: E402

AUDIT = os.path.join(ROOT, "docs", "r19.16-calibrator-audit")
CALIB_JS = os.path.join(ROOT, "calibrator.js")
CALIB_CSS = os.path.join(ROOT, "calibrator.css")
APP = os.path.join(ROOT, "app.js")
HTML = os.path.join(ROOT, "index.html")


def _json(name):
    return json.load(open(os.path.join(AUDIT, name), encoding="utf-8"))


def _entry(path="mod_mount_000", sid="mod_mount_000", owner="", row=2, col=8):
    return {"slotId": sid, "slotPath": path, "ownerItemId": owner,
            "logicalRow": row, "col": col, "topPad": 0, "displayRow": row,
            "role": "dovetailMount", "source": "manual", "note": "",
            "autoRow": 2, "autoCol": 8}


# ---------------------------------------------------------------- 数据身份与校验
def test_slot_identity_includes_owner_item():
    a = layoutcal.validate_slot_entry(_entry(path="mod_mount/mod_scope", sid="mod_scope", owner="591ee00d86f774592f7b841e"))
    b = layoutcal.validate_slot_entry(_entry(path="mod_mount/mod_scope", sid="mod_scope", owner="5aa66c72e5b5b00016327c93"))
    assert a["slotPath"] == b["slotPath"] and a["slotId"] == b["slotId"]
    assert layoutcal.slot_key(a) != layoutcal.slot_key(b), "同一路径同名槽位在不同父件下必须是不同身份"


def test_validate_rejects_bad_coordinates():
    with pytest.raises(layoutcal.CalibrationError):
        layoutcal.validate_slot_entry(_entry(row=99, col=3))
    with pytest.raises(layoutcal.CalibrationError):
        layoutcal.validate_slot_entry(_entry(row=3, col=12))
    with pytest.raises(layoutcal.CalibrationError):
        layoutcal.validate_slot_entry(_entry(row="3", col=3))


def test_validate_rejects_unknown_gun_and_collision():
    known = {"gun1"}
    with pytest.raises(layoutcal.CalibrationError):
        layoutcal.validate_gun({"slots": {}}, "gunX", known)
    e1, e2 = _entry(path="mod_mount_000"), _entry(path="mod_charge", sid="mod_charge")
    key1, key2 = layoutcal.slot_key(e1), layoutcal.slot_key(e2)
    with pytest.raises(layoutcal.CalibrationError) as exc:
        layoutcal.validate_gun({"name": "x", "slots": {key1: e1, key2: e2}}, "gun1", known)
    assert "同一格" in str(exc.value)


def test_slot_path_must_be_real_slot():
    with pytest.raises(layoutcal.CalibrationError):
        layoutcal.validate_slot_entry(_entry(path="fakepath"))
    ok = layoutcal.validate_slot_entry(_entry(path="mod_reciever/mod_mount/mod_scope"))
    assert ok["slotPath"].startswith("mod_")


# ---------------------------------------------------------------- 保存 / 备份 / 恢复
def test_save_backup_restore_roundtrip():
    tmp = tempfile.mkdtemp(prefix="calib_")
    try:
        e = _entry(row=2, col=8)
        key = layoutcal.slot_key(e)
        doc1 = layoutcal.empty_doc()
        doc1 = layoutcal.merge_gun(doc1, "gun1", {"name": "测试枪", "slots": {key: e}}, known_guns={"gun1"})
        layoutcal.save(doc1, tmp, known_guns={"gun1"})
        assert os.path.exists(layoutcal.path_for(tmp))
        assert not os.path.exists(layoutcal.backup_path_for(tmp)), "首次保存不应产生备份"

        e2 = dict(e, logicalRow=5, col=2)
        doc2 = layoutcal.merge_gun(doc1, "gun1", {"name": "测试枪", "slots": {key: e2}}, known_guns={"gun1"})
        layoutcal.save(doc2, tmp, known_guns={"gun1"})
        assert os.path.exists(layoutcal.backup_path_for(tmp)), "第二次保存必须备份上一版"

        cur = layoutcal.load(tmp, known_guns={"gun1"})
        assert cur["guns"]["gun1"]["slots"][key]["logicalRow"] == 5
        restored = layoutcal.restore_backup(tmp, known_guns={"gun1"})
        assert restored["guns"]["gun1"]["slots"][key]["logicalRow"] == 2
        assert layoutcal.load(tmp, known_guns={"gun1"})["guns"]["gun1"]["slots"][key]["logicalRow"] == 2
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_import_invalid_schema_rejected(tmp_path=None):
    tmp = tempfile.mkdtemp(prefix="calib_")
    try:
        e = _entry()
        key = layoutcal.slot_key(e)
        good = layoutcal.merge_gun(layoutcal.empty_doc(), "gun1", {"slots": {key: e}}, known_guns={"gun1"})
        layoutcal.save(good, tmp, known_guns={"gun1"})
        with pytest.raises(layoutcal.CalibrationError):
            layoutcal.save({"schemaVersion": 99, "guns": {}}, tmp, known_guns={"gun1"})
        # 已有数据不被覆盖
        assert layoutcal.load(tmp, known_guns={"gun1"})["guns"]["gun1"]["slots"][key]["logicalRow"] == 2
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_logical_row_authority_and_top_pad_fields():
    e = _entry(row=3, col=8)
    norm = layoutcal.validate_slot_entry(dict(e, topPad=1, displayRow=4))
    assert norm["logicalRow"] == 3 and norm["col"] == 8
    assert norm["topPad"] == 1 and norm["displayRow"] == 4, "逻辑行为权威值，显示行仅作还原参考"


# ---------------------------------------------------------------- 工具入口与实现
def test_calibrator_entry_and_files():
    js = open(CALIB_JS, encoding="utf-8").read()
    css = open(CALIB_CSS, encoding="utf-8").read()
    html = open(HTML, encoding="utf-8").read()
    assert "layoutCalibrator=1" in js, "工具必须只在 ?layoutCalibrator=1 时激活"
    assert 'if (!/[?&]layoutCalibrator=1/.test(location.search)) { return; }' in js, \
        "普通模式必须在脚本入口直接 return，零副作用"
    appjs = open(APP, encoding="utf-8").read()
    mb = re.search(r'AM_BUILD = "([^"]+)"', appjs)
    build = mb.group(1).lower() if mb else ""
    assert build and ("calibrator.js?v=" + build) in html and ("calibrator.css?v=" + build) in html, \
        "calibrator 资源版本必须与 AM_BUILD(%s) 同步" % (mb and mb.group(1))
    assert ".cal-overlay" in css and ".cal-grid" in css


def test_calibrator_uses_project_file_not_localstorage():
    js = open(CALIB_JS, encoding="utf-8").read()
    assert "/api/layout-calibration" in js
    assert "localStorage.setItem" not in js, "校准数据不得用 localStorage 冒充项目文件持久化"
    assert "action: \"save\"" in js.replace("'", '"') or 'action: "save"' in js or "action: 'save'" in js or '"save"' in js


def test_gwcalib_exposes_shared_engine():
    js = open(APP, encoding="utf-8").read()
    assert "window.GWCalib" in js
    assert "ensureItems()" in js, "校准器必须等待 items 加载（同一套物品数据）"
    assert "gwBuildLayout(" in js, "校准器复用同一个布局引擎"
    assert "window.GB" in js, "复用同一个 gun_builder"


def test_engine_reads_saved_calibration_readonly():
    """R19.17 升级（原「禁止批量应用」由 R19.17 任务书明确作废，升级为更强断言）：
    主布局引擎必须读取**已保存**的校准文件（data/gun-layout-calibration.json /
    /api/layout-calibration），且只读不写、坐标不得写死在 app.js，无记录时回退自动布局。"""
    js = open(APP, encoding="utf-8").read()
    assert "gun-layout-calibration" in js, "主引擎必须读取已保存的校准文件"
    assert "/api/layout-calibration" in js, "优先走现有校准数据接口"
    assert "gwApplyCalibToLayout" in js and "gwCalibKey" in js, "必须按槽位身份套用坐标"
    assert "noCalib" in js, "校准器基线（自动布局）必须可绕过校准应用"
    assert 'fetch("/api/layout-calibration", { cache: "no-cache" })' in js, "校准数据必须走 GET 读取"
    seg = js[js.index("function ensureLayoutCalib"):]
    seg = seg[:seg.index("\n  function ")]
    assert "POST" not in seg, \
        "app.js 只读校准数据，不得写文件（写入只允许校准器经 /api/layout-calibration）"


# ---------------------------------------------------------------- 浏览器证据
@pytest.fixture(scope="module")
def browser():
    return _json("browser-check.json")


def test_browser_drag_undo_redo(browser):
    f = browser["flow"]
    assert f["dragSource"]["row"] == 2 and f["dragSource"]["col"] == 8
    assert f["afterDrag"]["row"] == 5 and f["afterDrag"]["col"] == 1
    assert f["afterDrag"]["dirty"] is True
    assert f["afterUndo"]["row"] == 2 and f["afterUndo"]["col"] == 8
    assert f["afterRedo"]["row"] == 5 and f["afterRedo"]["col"] == 1


def test_browser_body_protected_and_swap_keeps_slots(browser):
    f = browser["flow"]
    assert f["bodyReject"]["rejected"] is True
    assert f["swap"]["allSlotsKept"] is True
    assert f["swap"]["mount"]["col"] == 9 and f["swap"]["charge"]["col"] == 8


def test_browser_save_reload_persistence(browser):
    f = browser["flow"]
    saved = f["fileAfterSave"]["ak"]["mod_mount_000|mod_mount_000|"]
    assert saved["logicalRow"] == 5 and saved["col"] == 2
    assert saved["slotPath"] == "mod_mount_000"
    assert f["afterReload"]["row"] == 5 and f["afterReload"]["col"] == 2
    assert f["afterReload"]["movedTag"] is True


def test_browser_conditional_slots_and_import_reject(browser):
    f = browser["flow"]
    assert f["conditional"]["changed"] is True, "切换预设必须反映真实条件子槽位差异"
    assert f["conditional"]["slotsBefore"] != f["conditional"]["slotsAfter"]
    assert f["importReject"]["ok"] is False


def test_browser_guns_cover_required_cases(browser):
    need = {"ash12", "axmc", "m10", "marlin", "ak74n", "m4a1", "sa58", "sv98"}
    assert need <= set(browser["guns"].keys())
    for k in need:
        assert browser["guns"][k]["slotCount"] > 0, k


def test_browser_normal_page_clean(browser):
    n = browser["normalPage"]
    assert n["overlay"] is False
    assert n["calGrid"] == 0 and n["gridlines"] == 0
    assert n["ghost"] == 0 and n["connectors"] == 0
    assert n["gunCanvas"] is True


# ---------------------------------------------------------------- 审计物料
def test_audit_tool_inventory():
    d = _json("tool-inventory.json")
    assert d["entry"].startswith("http") and "layoutCalibrator=1" in d["entry"]
    for pane in ("left", "center", "right"):
        assert d["panes"][pane]
    assert "save" in d["operations"] and "undo" in d["operations"]


def test_audit_slot_identity_schema():
    d = _json("slot-identity-schema.json")
    fields = set(d["entryFields"].keys())
    for f in ("slotId", "slotPath", "ownerItemId", "logicalRow", "col", "topPad", "displayRow"):
        assert f in fields
    assert d["keyFormula"].count("+") >= 2


def test_audit_calibration_save_load():
    d = _json("calibration-save-load.json")
    assert d["savePath"] == "data/gun-layout-calibration.json"
    assert d["persistence"]["serverRestart"] is True
    assert d["persistence"]["pageReload"] is True
    assert d["import"]["invalidRejected"] is True
    assert d["backup"]["exists"] is True


def test_audit_drag_drop_tests():
    d = _json("drag-drop-tests.json")
    assert d["drag"]["moved"] is True
    assert d["undo"]["reverted"] is True and d["redo"]["reapplied"] is True
    assert d["bodyProtection"]["rejected"] is True
    assert d["swap"]["noSlotLost"] is True


def test_audit_conditional_slots():
    d = _json("conditional-slots.json")
    assert d["presetSwitch"]["slotsChanged"] is True
    assert d["identity"]["boundToSlotPathAndOwner"] is True


def test_audit_layout_preview():
    d = _json("layout-preview.json")
    assert d["views"] == ["auto", "manual"]
    assert d["manualAppliedToMainEngine"] is False


def test_audit_regression_results():
    d = _json("regression-results.json")
    assert d["testSuite"]["failed"] == 0
    assert d["mainApp"]["overlayLeak"] is False
    assert d["mainApp"]["engineUntouched"] is True
