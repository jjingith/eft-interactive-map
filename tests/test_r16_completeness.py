# -*- coding: utf-8 -*-
"""R16：枪械兼容性 / Boss 装备池 / 方向性护甲 专项测试

覆盖 R16-A（口径+平台分组）、R16-B（弹药与弹匣兼容）、R16-D（Boss 插板池）、
R16-E（Boss 名单完整性）、R16-F（前后插板方向性）、R16-G（滚动与按钮）。

引擎数值断言在 Python 侧完成：tests/js/combat_sim_r16_test.js 只导出原始结果。
"""
import json
import os
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIM_JS = os.path.join(ROOT, "combat_sim.js")
TEST_JS = os.path.join(ROOT, "tests", "js", "combat_sim_r16_test.js")
APP_JS = os.path.join(ROOT, "app.js")
STYLE = os.path.join(ROOT, "style.css")
INDEX = os.path.join(ROOT, "index.html")
COMPAT = os.path.join(ROOT, "data", "gun-compat.json")
PLATFORMS = os.path.join(ROOT, "data", "gun-platforms.json")
BOSSES = os.path.join(ROOT, "data", "bosses.json")
ITEMS = os.path.join(ROOT, "data", "items.json")
AMMO = os.path.join(ROOT, "data", "ammo.json")
RATES = os.path.join(ROOT, "data", "gun-rates.json")
DOCS = os.path.join(ROOT, "docs", "r16-completeness")

require_node = pytest.mark.skipif(shutil.which("node") is None, reason="node 不可用")


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _json(path):
    return json.loads(_read(path))


@pytest.fixture(scope="module")
def scen():
    out = subprocess.run(["node", TEST_JS, SIM_JS], capture_output=True, text=True, timeout=60, cwd=ROOT)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


@pytest.fixture(scope="module")
def compat():
    return _json(COMPAT)


@pytest.fixture(scope="module")
def items():
    return _json(ITEMS)["items"]


@pytest.fixture(scope="module")
def bosses():
    return _json(BOSSES)


def _names(pellet):
    return [l["name"] for l in pellet["layers"]]


# ———————————————————— F：方向性护甲 ————————————————————

def test_direction_front_uses_only_front_layers(scen):
    """正面：只经过前插板 + 前内衬；后插板/后内衬必须被跳过。"""
    p = scen["front"]
    assert p["dir"] == "front"
    assert [l["side"] for l in p["layers"]] == ["front", "front"]
    assert [l["kind"] for l in p["layers"]] == ["plate", "liner"]
    skipped = [s["name"] for s in p["layersSkipped"]]
    assert "后插板" in skipped and "后内衬" in skipped
    assert all(s["reason"] == "not-on-shot-direction" for s in p["layersSkipped"])


def test_direction_back_uses_only_back_layers(scen):
    """背面：只经过后插板 + 后内衬，前侧层不参与。"""
    p = scen["back"]
    assert p["dir"] == "back"
    assert [l["side"] for l in p["layers"]] == ["back", "back"]
    assert [l["name"] for l in p["layers"]] == ["后插板", "后内衬"]
    assert "前插板" in [s["name"] for s in p["layersSkipped"]]


def test_direction_left_uses_side_plate_only(scen):
    """左侧命中：只碰左侧板，前/后/右侧板都不参与。"""
    p = scen["left"]
    assert p["dir"] == "left"
    assert [l["name"] for l in p["layers"]] == ["左侧板"]
    skipped = [s["name"] for s in p["layersSkipped"]]
    for nm in ("前插板", "后插板", "右侧板"):
        assert nm in skipped


def test_front_without_front_plate_takes_full_damage(scen):
    """正面命中且没装前板：不得因为「有后板」就产生减伤。"""
    p = scen["frontNoFrontPlate"]
    assert p["layers"] == []
    assert p["dmgToPart"] == pytest.approx(50.0, abs=1e-9)
    assert p["stoppedBy"] is None
    assert [s["name"] for s in p["layersSkipped"]] == ["后插板"]


def test_penetrate_then_liner_blocks_and_back_plate_untouched(scen):
    """穿前板 → 被前内衬挡住：只交钝伤；后插板耐久必须没变。"""
    p = scen["penThenLiner"]
    assert [l["kind"] for l in p["layers"]] == ["plate", "liner"]
    assert p["layers"][0]["penetrated"] is True
    assert p["layers"][1]["penetrated"] is False
    assert p["stoppedBy"] == "armor"
    assert p["dmgToPart"] == pytest.approx(p["layers"][1]["blunt"], abs=1e-9)
    assert p["dmgToPart"] < 50.0
    assert "后插板" in [s["name"] for s in p["layersSkipped"]]


def test_exit_model_does_not_change_body_damage(scen):
    """开启出口碰撞只多扣对侧插板耐久；两支场景的人体伤害必须完全一致。"""
    off = scen["exitOff"]["shots"][0]["pellets"][0]
    on = scen["exitOn"]["shots"][0]["pellets"][0]
    assert off["exit"] is None
    assert on["exit"] is not None
    assert on["exit"]["phase"] == "after-body"
    assert on["exit"]["confidence"] == "estimated"
    assert on["exit"]["side"] == "back"
    assert on["exit"]["durAfter"] < on["exit"]["durBefore"]
    assert on["dmgToPart"] == pytest.approx(off["dmgToPart"], abs=1e-9)
    assert on["dmgToArmor"] > off["dmgToArmor"]


def test_engine_rejects_illegal_ammo_and_magazines(scen):
    """非法弹药/弹匣/无弹匣槽的枪：引擎必须抛错，而不是静默按旧状态继续。"""
    assert scen["throwAmmoNotAllowed"] == "ammo not allowed by gun: not-allowed"
    assert scen["throwMagNotAllowed"] == "magazine not allowed by gun: m2"
    assert scen["throwNoMagSlot"] == "gun has no detachable magazine: m1"
    assert scen["okWhenAllowed"]["shotCount"] == 2


def test_direction_reproducible(scen):
    assert scen["reproA"] == scen["reproB"]


def test_legacy_layers_without_side_still_chain(scen):
    """向后兼容：旧数据不带 side 时仍按原顺序串联（R15 场景不回归）。"""
    p = scen["legacyNoSide"]
    assert [l["kind"] for l in p["layers"]] == ["plate", "liner"]
    assert p["layersSkipped"] == []


def test_helmet_applies_from_both_directions(scen):
    """头盔与方向无关：正面/背面命中头部都应经过头盔。"""
    for key in ("helmetFront", "helmetBack"):
        p = scen[key]
        assert [l["kind"] for l in p["layers"]] == ["helmet"]
        assert p["layers"][0]["blocked"] is True


# ———————————————————— A / B：枪械分组与兼容 ————————————————————

def test_gun_compat_covers_all_guns(compat):
    rates = _json(RATES)["guns"]
    guns = compat["guns"]
    assert compat["schema"] == 1
    assert len(guns) == len(rates) == 163
    for gid, g in guns.items():
        assert g.get("cal"), gid
        assert g.get("caln"), gid
        assert isinstance(g.get("ammo"), list) and g["ammo"], gid
        assert isinstance(g.get("mags"), list), gid
    assert compat["counts"]["withAmmo"] == 163


def test_same_caliber_different_platform_magazines(compat):
    """同口径不同枪族：弹药可以相同，但弹匣白名单必须按真实 ID 区分。"""
    guns = compat["guns"]
    m4 = guns["5447a9cd4bdc2dbd208b4567"]
    ak101 = next(g for g in guns.values() if g["n"].startswith("AK-101"))
    assert m4["caln"] == ak101["caln"] == "5.56x45"
    assert m4["platform"] == "ar15" and ak101["platform"] == "ak"
    assert set(m4["ammo"]) == set(ak101["ammo"])          # 同口径弹药一致
    assert set(m4["mags"]) != set(ak101["mags"])          # 弹匣绝不能混用
    assert not (set(m4["mags"]) & set(ak101["mags"]))


def test_ammo_ids_exist_and_mag_ids_are_magazines(compat, items):
    ammo_ids = {a["id"] for a in _json(AMMO)["ammo"]}
    bad_ammo, bad_mag = [], []
    for gid, g in compat["guns"].items():
        for aid in g["ammo"]:
            if aid not in ammo_ids:
                bad_ammo.append((gid, aid))
        for mid in g["mags"]:
            rec = items.get(mid)
            if not rec or rec.get("pt") != "Magazine":
                bad_mag.append((gid, mid))
    assert bad_ammo == []
    assert bad_mag == []


def test_platform_dataset_and_calibers(compat):
    """平台映射逐枪落表；5.56 至少两个平台（AR-15 / AK），AR-15 至少 5 把。"""
    plat = _json(PLATFORMS)
    assert plat["schema"] == 1
    assert set(plat["guns"].keys()) == set(compat["guns"].keys())
    ar15 = [g for g in compat["guns"].values() if g["platform"] == "ar15"]
    assert len(ar15) >= 5
    cals = {}
    for g in compat["guns"].values():
        cals.setdefault(g["caln"], set()).add(g["platformN"] or "其他")
    assert len(cals["5.56x45"]) >= 2
    for cal in ("5.56x45", "5.45x39", "7.62x39"):
        assert cal in cals, cal


# ———————————————————— D / E：Boss 名单与装备池 ————————————————————

REQUIRED_BOSSES = {
    "killa", "reshala", "shturman", "tagilla", "glukhar", "sanitar", "kaban",
    "kollontay", "partisan", "knight", "bigpipe", "birdeye", "zryachiy",
    "shadowoftagilla", "vengefulkilla", "thewedge", "santaclaus",
}
REQUIRED_ELITES = {"cultistpriest", "cultistwarrior", "rogue", "blackdivision"}
TAGILLA_ARMOR = "609e860ebd219504d8507525"
TAGILLA_FRONT = "656fa99800d62bcd2e024088"     # Cult Termite，6 级
TAGILLA_BACK = "656fa0fb498d1b7e3e071d9c"      # Global Armor's Steel，4 级


def test_boss_roster_complete(bosses):
    keys = {b["k"] for b in bosses["bosses"]}
    assert REQUIRED_BOSSES <= keys, REQUIRED_BOSSES - keys
    elites = {e["k"] for e in bosses.get("elites", [])}
    assert REQUIRED_ELITES <= elites, REQUIRED_ELITES - elites
    roster = bosses.get("roster") or {}
    assert set(roster.get("boss", [])) | set(roster.get("goons", [])) \
        | set(roster.get("special", [])) | set(roster.get("event", [])) == keys
    assert bosses.get("revision") == "r16"


def test_boss_health_sums(bosses):
    parts = {"head", "chest", "stomach", "leftArm", "rightArm", "leftLeg", "rightLeg"}
    for b in bosses["bosses"] + bosses.get("elites", []):
        hp = b["health"]
        assert set(hp.keys()) == parts, b["k"]
        assert b["total"] == sum(hp.values()), b["k"]
        assert b["healthConfidence"] in ("verified", "estimated", "missing"), b["k"]


def test_boss_equipment_ids_valid(bosses, items):
    checked = 0
    for b in bosses["bosses"] + bosses.get("elites", []):
        eq = b["equipment"]
        for kind, slots in (("armor", ("armor", "rig")), ("helmets", ("helmet",)),
                            ("faces", ("face",))):
            for iid in eq.get(kind) or []:
                rec = items.get(iid)
                assert rec, (b["k"], kind, iid)
                assert rec.get("slot") in slots, (b["k"], kind, iid, rec.get("slot"))
                checked += 1
        for pid in eq.get("plates") or []:
            assert (items.get(pid) or {}).get("cat") == "plate", (b["k"], pid)
            checked += 1
    assert checked >= 20


def test_tagilla_default_plates(bosses, items):
    """Tagilla：默认护甲 = 专属 AVS，前板 Cult Termite（6 级）/ 后板 Global Steel（4 级）。"""
    tag = next(b for b in bosses["bosses"] if b["k"] == "tagilla")
    dp = tag["equipment"]["defaultPlates"]
    assert tag["equipment"]["defaultArmor"] == TAGILLA_ARMOR
    assert dp["armorId"] == TAGILLA_ARMOR
    assert dp["front"] == TAGILLA_FRONT
    assert dp["back"] == TAGILLA_BACK
    assert dp["front"] != dp["back"]
    front, back = items[dp["front"]], items[dp["back"]]
    assert front["cl"] == 6 and back["cl"] == 4
    assert dp["confidence"] == "estimated"
    assert "Tagilla" in (dp.get("armorTitle") or "")


def test_default_plates_are_armor_compatible(bosses, items):
    """默认插板必须真的是该护甲插板槽的兼容项（兼容 ∩ 生成装备，不是凭空指定）。"""
    for b in bosses["bosses"] + bosses.get("elites", []):
        dp = b["equipment"].get("defaultPlates")
        if not dp:
            continue
        armor = items.get(dp["armorId"])
        assert armor, b["k"]
        sockets = {}
        for a in armor.get("aps") or []:
            if not a.get("fx"):
                sockets[a["zone"].lower()] = set(a.get("plates") or [])
        front = sockets.get("front_plate", set())
        back = sockets.get("back_plate", set())
        if dp.get("front"):
            assert dp["front"] in front, (b["k"], "front")
        if dp.get("back"):
            assert dp["back"] in back, (b["k"], "back")


def test_low_class_plate_cannot_enter_boss_pool(bosses, items):
    """Boss 池里不能出现「护甲能装但 Boss 不会带」的板（例如 1 级板）。"""
    tag = next(b for b in bosses["bosses"] if b["k"] == "tagilla")
    allowed = {tag["equipment"]["defaultPlates"][k] for k in ("front", "back", "left", "right")
               if tag["equipment"]["defaultPlates"].get(k)}
    armor = items[TAGILLA_ARMOR]
    compat_plates = set()
    for a in armor.get("aps") or []:
        if not a.get("fx"):
            compat_plates |= set(a.get("plates") or [])
    assert compat_plates - allowed, "样例护甲应存在兼容但不在 Boss 池内的插板，才能验证收窄"
    low = [pid for pid in compat_plates if (items.get(pid) or {}).get("cl") in (1, 2)]
    for pid in low:
        assert pid not in allowed
    one_class = [pid for pid, rec in items.items() if rec.get("cat") == "plate" and rec.get("cl") == 1]
    assert one_class, "物品库应存在 1 级插板"
    for pid in one_class:
        assert pid not in allowed


def test_boss_followers_not_mixed(bosses):
    """护卫血量不得与本体混用（同值视为页面复用，标记 missing 而非当作护卫数据）。"""
    for b in bosses["bosses"]:
        for f in b.get("followers") or []:
            if not f.get("health"):
                continue
            assert f["health"] != b["health"], b["k"]
            assert f["total"] == sum(f["health"].values()), b["k"]


def test_docs_and_screenshots_present():
    for name in ("baseline.md", "weapon-compatibility.md", "ammo-window-review.md",
                 "boss-roster.md", "boss-loadouts.json", "armor-direction-research.md",
                 "known-gaps.md", "test-report.md"):
        assert os.path.exists(os.path.join(DOCS, name)), name
    assert os.path.isdir(os.path.join(DOCS, "screenshots"))


# ———————————————————— UI 接线 / 布局 / 离线 ————————————————————

def test_ui_gun_grouping_wiring():
    js = _read(APP_JS)
    assert "AM_SIM_COMPAT_URL = \"data/gun-compat.json\"" in js
    assert "AM_SIM_PLATFORMS_URL = \"data/gun-platforms.json\"" in js
    assert 'data-sim", "cal-filter"' in js
    assert "function rebuildSimGunOptions" in js
    assert "og.label = cal + \" · \" + pfs[pi]" in js


def test_ui_ammo_and_mag_filter_wiring():
    js = _read(APP_JS)
    assert "function simAllowedAmmo" in js
    assert "function simAllowedMags" in js
    assert "function amSimOnGunChanged" in js
    assert 'data-sim", "mag-pick"' in js
    # R17S：旧独立填弹按钮删除后，白名单硬校验移到弹窗写入路径（等价防线，不是弱化）
    assert "allowNow.indexOf(ca) < 0" in js
    assert "simDefaultMagId" in js


def test_ui_direction_and_plate_policy_wiring():
    js = _read(APP_JS)
    assert 'data-sim", "dir"' in js
    assert 'data-sim", "exit-model"' in js
    assert "function amSimPlatePolicy" in js
    assert "bySide" in js
    assert "function amSimApplyBossDefaults" in js
    assert "amSimSideFromZone" in js


def test_ui_scroll_and_sticky_run_button():
    css = _read(STYLE)
    js = _read(APP_JS)
    assert ".am-sim-runbar" in css and "position: sticky" in css
    assert "max-height: calc(100vh - 168px)" in css
    assert "overflow-y: auto" in css
    assert "am-sim-runbar" in js
    # 执行按钮在顶部操作条里（不再只在表单末尾）
    assert 'var runBar = elTag("div", "am-sim-runbar")' in js


def test_runtime_offline_no_external_dependency():
    html = _read(INDEX)
    for line in html.splitlines():
        low = line.strip().lower()
        if low.startswith("<script") or low.startswith("<link"):
            assert "http://" not in low and "https://" not in low, line
    js = _read(APP_JS)
    assert "fetch(\"http" not in js and "fetch('http" not in js
    for path in (COMPAT, PLATFORMS, BOSSES):
        assert os.path.exists(path), path
