# -*- coding: utf-8 -*-
"""R19.18 武器槽位 / 配件兼容性 / 校准器编辑能力专项修复。

覆盖任务书第十四节的 A–J 十组：
  A SVDS 燕尾槽   B AK 照门兼容性   C 校准器七行布局   D T-5000 战术槽位
  E SKS SOCOM      F GP-25 榴弹槽位   G VSK-94 环形基座  H AS VAL MOD.4 top cover
  I TKPD            J 校准数据回归

证据来源：docs/r19.18-slot-fix-audit/ 下的实跑产物
（engine-audit.json = node 引擎审计；browser-accept.json = 真实浏览器验收）
+ 每次测试会话实跑 tools/r1926_audit.js（真实槽位树 + 安装行为，不看屏幕卡片数）。
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
ITEMS = os.path.join(ROOT, "data", "items.json")
GUNSLOTS = os.path.join(ROOT, "data", "gunslots.json")
CALIB = os.path.join(ROOT, "data", "gun-layout-calibration.json")
AUDIT = os.path.join(ROOT, "docs", "r19.18-slot-fix-audit")
ENGINE_TOOL = os.path.join(ROOT, "tools", "r1926_audit.js")

need_node = subprocess.run(
    [sys.executable, "-c", "import shutil,sys;sys.exit(0 if shutil.which('node') else 1)"]
).returncode != 0


def _json(name):
    p = os.path.join(AUDIT, name)
    assert os.path.exists(p), "缺 %s（先跑对应审计/验收脚本）" % name
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _items():
    with open(ITEMS, encoding="utf-8") as f:
        return json.load(f)["items"]


def _guns():
    with open(GUNSLOTS, encoding="utf-8") as f:
        return json.load(f)["guns"]


@pytest.fixture(scope="module")
def audit():
    """每次会话实跑引擎审计（真实槽位树 + 安装行为）。"""
    if need_node:
        pytest.skip("需要 node")
    proc = subprocess.run(["node", ENGINE_TOOL], cwd=ROOT, capture_output=True, text=True)
    assert proc.returncode == 0, "r1926_audit.js 失败：\n%s\n%s" % (proc.stdout[-1500:], proc.stderr[-1500:])
    return _json("engine-audit.json")


@pytest.fixture(scope="module")
def browser():
    return _json("browser-accept.json")


# ============================================================ A. SVDS
def test_A_svds_dovetail_slot_exists_and_at_r2c7(audit):
    c = audit["checks"]
    assert c["svds_dovetail_exists"] is True
    assert c["svds_dovetail_at_r2c7"] is True
    assert c["svds_no_duplicate"] is True
    assert c["svds_other_guns_unaffected"] is True, "AK 枪族的燕尾槽仍必须是 r2c8"


def test_A_svds_dovetail_in_real_data():
    items, guns = _items(), _guns()
    gid = "5c46fbd72e2216398b5a8c9c"
    slot = [s for s in guns[gid]["slots"] if s["sid"] == "mod_mount_000"]
    assert len(slot) == 1, "SVDS 的燕尾槽基座在真实数据里必须存在且唯一"
    assert slot[0]["allow"], "燕尾槽基座必须能装东西"
    scopes = [items[a] for a in slot[0]["allow"] if (items.get(a) or {}).get("pt") == "Scope"]
    assert scopes, "燕尾槽基座必须能装光学瞄具（pt=Scope）"


# ============================================================ B. AK 照门兼容性
def test_B_5_45_5_56_ak_has_no_akmp_rs(audit):
    """R19.21 升级（原「5.45/5.56 不得出现 AKMP」被实测推翻）：AKMP 是
    6P1 Sb.2 / 6P20 Sb.2 / 6P44 Sb.1-30 三种照门的子配件——装这三种照门的
    5.45/5.56 AK **有** AKMP 子槽；AKMP 不入枪身照门槽 allow。"""
    assert audit["checks"]["ak_akmp_child_restored_on_leaf_parent"] is True
    assert audit["checks"]["akm_akmp_child_slot_gone"] is True   # AKM 照门上的错误子槽已删


def test_B_akm_family_uses_akmp_rs(audit):
    """R19.21 升级（并列假设被推翻）：AKM 照门 6P1 Sb.2-1 不是 AKMP 的父照门——
    AKM 系枪械无 AKMP 子槽、任何照门槽 allow 不含 AKMP；AKM 系仍不得出现
    AK-74 系列照门。"""
    assert audit["checks"]["akm_akmp_child_slot_gone"] is True
    assert audit["checks"]["akm_no_ak74_rs"] is True
    for gid in ("59d6088586f774275f37482f", "59ff346386f77477562ff5e2"):
        assert audit["checks"]["akm_no_akmp_anywhere_" + gid] is True


def test_B_legal_rear_sight_kept(audit):
    assert audit["checks"]["ak_legal_rear_sight_kept"] is True


def test_B_new_ak_variant_will_not_regress():
    """通用规则（R19.21 升级，实测确认）：AKMP 子槽只随三种标准照门
    （6P1 Sb.2 / 6P20 Sb.2 / 6P44 Sb.1-30）出现；AKM 照门 6P1 Sb.2-1 与其他
    照门不得带；AKMP RS 不得混入任何枪身照门槽 allow。"""
    items = _items()
    leaf = ["5649b0544bdc2d1b2b8b458a", "5ac72e475acfc400180ae6fe", "5ac733a45acfc400192630e2"]
    for iid in leaf:
        slots = (items.get(iid) or {}).get("slots") or []
        subs = [s for s in slots if s.get("sid") == "mod_sight_rear"]
        assert subs and subs[0].get("allow") == ["5a0ed824fcdbcb0176308b0d"], \
            "%s 必须带 AKMP 子槽（R19.21 实测确认的父子关系）" % (items.get(iid) or {}).get("n")
    akm = items.get("59d650cf86f7741b846413a4") or {}
    assert not [s for s in (akm.get("slots") or []) if s.get("sid") == "mod_sight_rear"], \
        "AKM 照门 6P1 Sb.2-1 不得带 AKMP 子槽（并列假设的错误建模已删除）"
    guns = _guns()
    akm_slot = [s for s in guns["59d6088586f774275f37482f"]["slots"] if s.get("sid") == "mod_sight_rear"][0]
    assert "5a0ed824fcdbcb0176308b0d" not in (akm_slot.get("allow") or []), \
        "AKMP RS 不得混入枪身照门槽 allow"


# ============================================================ C. 校准器七行布局
def test_C_g28_and_s12k_have_row7(audit):
    for gid in ("6176aca650224f204c1da3fb", "6981d72ed009ad83920da43a"):
        assert audit["checks"]["rows_%s_7" % gid] is True
        assert audit["checks"]["row7_slots_exist_%s" % gid] is True


def test_C_calibrator_can_edit_row7(browser):
    assert browser["checks"]["g28_rows_7"] is True
    assert browser["checks"]["s12k_rows_7"] is True
    assert browser["checks"]["calibrator_g28_rows_7"] is True
    assert browser["checks"]["calibrator_g28_row7_cards"] is True
    assert browser["checks"]["calibrator_row7_drag_works"] is True
    assert browser["checks"]["calibrator_row7_undo"] is True
    assert browser["checks"]["calibrator_row7_redo"] is True


def test_C_calibrator_grid_is_not_fixed_to_six_rows():
    js = _read_whole(CALIB_JS)
    assert "previewRows" in js and "curRows" in js, "校准器必须按真实行数动态计算可编辑范围"
    assert "repeat(\" + S.rows" not in js or "rowsNow" in js


def _read_whole(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


# ============================================================ D. T-5000
def test_D_t5000_tactical_slots_match_game(audit):
    assert audit["checks"]["t5000_tactical_count_2"] is True, audit["detail"].get("t5000")
    assert audit["checks"]["t5000_rail_count_2"] is True
    assert audit["checks"]["t5000_no_duplicate_rail"] is True


def test_D_t5000_handguard_has_no_duplicate_rails():
    items = _items()
    hg = items.get("5df25d3bfd6b4e6e2276dc9a") or {}
    rails = [s for s in (hg.get("slots") or []) if s.get("sid", "").startswith("mod_mount")]
    assert len(rails) == 2, "T-5000 护木应只有两个导轨安装位"
    allows = [tuple(sorted(s.get("allow") or [])) for s in rails]
    assert len(set(allows)) == len(allows), "两个导轨位的可装清单不应完全相同"


# ============================================================ E. SKS SOCOM
@pytest.mark.parametrize("gid", ["574d967124597745970e7c94", "587e02ff24597743df3deaeb"])
def test_E_sks_socom_slot_and_children(gid, audit):
    assert audit["checks"]["sks_socom_slot_%s" % gid] is True
    assert audit["checks"]["sks_socom_at_r4c3_%s" % gid] is True
    assert audit["checks"]["sks_socom_scope_r2c3_%s" % gid] is True
    assert audit["checks"]["sks_socom_tactical_r5c3_%s" % gid] is True
    assert audit["checks"]["sks_socom_children_gone_%s" % gid] is True


def test_E_sks_socome_install_and_remove(browser):
    for key in ("sks", "opsks"):
        assert browser["checks"]["%s_socom_installable" % key] is True
        assert browser["checks"]["%s_socom_scope_r2c3" % key] is True
        assert browser["checks"]["%s_socom_tactical_r5c3" % key] is True
        assert browser["checks"]["%s_socom_children_removed" % key] is True


# ============================================================ F. GP-25
def test_F_gp25_only_on_compatible_guns(audit):
    assert audit["checks"]["gp25_all_supported_guns_show_slot"] is True
    assert audit["checks"]["gp25_no_slot_on_unsupported"] is True
    assert audit["checks"]["gp25_below_gas_block"] is True
    assert audit["detail"]["gp25"]["guns"] >= 3


def test_F_gp25_browser_installable(browser):
    for key in ("ak74n", "akm", "ak101"):
        assert browser["checks"]["gp25_slot_%s" % key] is True
        assert browser["checks"]["gp25_below_gas_%s" % key] is True
        assert browser["checks"]["gp25_real_item_%s" % key] is True
    assert browser["checks"]["gp25_not_on_ak545"] is True


# ============================================================ G. VSK-94
def test_G_vsk94_has_no_vss_ring_mount(audit):
    assert audit["checks"]["vsk94_no_b3_ring_slot"] is True
    assert audit["checks"]["vss_val_keep_b3_ring"] is True


def test_G_vsk94_browser(browser):
    assert browser["checks"]["vsk94_no_b3_slot"] is True


# ============================================================ H. AS VAL MOD.4
def test_H_top_cover_states(audit):
    assert audit["checks"]["asvalmod4_dovetail_visible_without_cover"] is True
    assert audit["checks"]["asvalmod4_dovetail_hidden_with_cover"] is True
    assert audit["checks"]["asvalmod4_dovetail_restored_after_remove"] is True
    assert audit["checks"]["asvalmod4_cover_children_gone_after_remove"] is True
    assert audit["checks"]["asvalmod4_single_35in_rail"] is True
    assert audit["checks"]["asvalmod4_single_35in_rail_with_cover"] is True
    assert audit["checks"]["asval_unaffected"] is True


def test_H_top_cover_browser(browser):
    assert browser["checks"]["asvalmod4_single_35in_rail"] is True
    assert browser["checks"]["asvalmod4_dovetail_hidden_with_cover"] is True
    assert browser["checks"]["asvalmod4_dovetail_restored"] is True
    assert browser["checks"]["asvalmod4_cover_children_gone"] is True


def test_H_conflict_is_driven_by_installed_item():
    """互斥必须由真实安装状态驱动（按物品 id 判定），不是按画布文字。"""
    js = _read_whole(APP)
    assert "GW_SLOT_CONFLICTS" in js and "gwSlotConflicted" in js
    assert "68712bd4251b8d4c6c04ec19" in js, "top cover 互斥必须按配件物品 id 登记"


# ============================================================ I. TKPD
def test_I_tkpd_slots(audit):
    assert audit["checks"]["tkpd_tactical_count_1"] is True, audit["detail"].get("tkpd")
    assert audit["checks"]["tkpd_two_dovetail_slots"] is True
    assert audit["checks"]["tkpd_dovetail_accepts_real_items"] is True


def test_I_tkpd_browser(browser):
    assert browser["checks"]["tkpd_tactical_1"] is True
    assert browser["checks"]["tkpd_two_dovetail"] is True
    assert browser["checks"]["tkpd_dovetail_installable"] is True


# ============================================================ J. 校准数据回归
def test_J_calibration_records_intact():
    with open(CALIB, encoding="utf-8") as f:
        doc = json.load(f)
    assert doc.get("schemaVersion") == 1
    guns = doc.get("guns") or {}
    assert len(guns) >= 150, "校准枪械数量异常"
    total = sum(len((g or {}).get("slots") or {}) for g in guns.values())
    assert total >= 380, "校准记录数量异常（疑似被清空）"
    for g in guns.values():
        for k in (g.get("slots") or {}):
            assert k.count("|") == 2, k


def test_J_unmatched_records_are_explained(audit):
    """未匹配的记录必须全部是「已解释」的：失效（真实子槽移除）或当前不可用（真实互斥）。"""
    c = audit.get("corpus") or audit["detail"]["calib"]
    assert c["unmatched"] == c.get("stale", 0) + c.get("suppressed", 0)
    assert not [x for x in c.get("staleRecords", []) if x.get("unexpected")], \
        "存在无法解释的未匹配记录：%s" % c.get("staleRecords")


def test_J_stale_records_are_marked_not_deleted():
    """失效记录保留在文件里并写明原因，不删除、不改挂到别的槽位。
    R19.21 升级（断言由「固定条数」升级为「失效必留痕」语义 + 逐代前缀合法）：
    三种标准照门的 10 条子槽记录已复活（注记为 R19.21 重算说明），失效集合随
    真实槽位演进——凡含「不再生效」的记录必须有轮次前缀、有原因、有原坐标。"""
    with open(CALIB, encoding="utf-8") as f:
        doc = json.load(f)
    stale = 0
    for g in (doc.get("guns") or {}).values():
        for rec in (g.get("slots") or {}).values():
            note = rec.get("note") or ""
            if "不再生效" in note:
                stale += 1
                assert note.startswith("R19."), "失效原因必须带轮次前缀：%s" % note[:30]
                assert rec.get("logicalRow") is not None and rec.get("col") is not None, \
                    "失效记录必须保留原坐标"
    assert stale >= 5, "失效记录应当被标记原因（当前 %d 条）" % stale


def test_J_calibration_matches_main_canvas(audit, browser):
    assert audit["checks"]["calib_records_intact"] is True
    assert browser["checks"]["svds_after_reload_r2c7"] is True, "刷新后校准仍生效"


def test_J_version_sync():
    with open(APP, encoding="utf-8") as f:
        js = f.read()
    with open(os.path.join(ROOT, "index.html"), encoding="utf-8") as f:
        html = f.read()
    m = re.search(r'AM_BUILD = "([^"]+)"', js)
    assert m and m.group(1).startswith("R19."), m and m.group(1)   # 版本标记跟随 AM_BUILD 动态同步
    build = m.group(1).lower()
    for name in ("style.css", "theme-windows-xp.css", "calibrator.css",
                 "app.js", "gun_builder.js", "combat_sim.js", "calibrator.js"):
        assert re.search(re.escape(name) + r"\?v=" + re.escape(build), html), "%s 版本串未同步" % name
