# -*- coding: utf-8 -*-
"""r15：逐发模拟器纠偏专项测试

覆盖 R15 任务书要求：
  A 射速由所选枪械决定（引擎时间间隔 + 数据文件 + UI 只读）
  D Boss 装备池限制（血量/池数据 + UI 过滤与清理接线）
  E 多层护甲逐层状态传递（硬插板 → 软内衬，四种情况 A–D）
  F 障碍物位置与穿透（数据 + 逐层状态 + 顺序 + 终止 + 复现）
  G 离线约束（不引入外部运行期依赖）

数值关系断言在 Python 侧完成，引擎不内置任何示例期望值。
"""
import json
import os
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIM_JS = os.path.join(ROOT, "combat_sim.js")
APP_JS = os.path.join(ROOT, "app.js")
INDEX = os.path.join(ROOT, "index.html")
TEST_JS = os.path.join(ROOT, "tests", "js", "combat_sim_r15_test.js")
BOSSES = os.path.join(ROOT, "data", "bosses.json")
RATES = os.path.join(ROOT, "data", "gun-rates.json")
BARRIERS = os.path.join(ROOT, "data", "barriers.json")
ITEMS = os.path.join(ROOT, "data", "items.json")

require_node = pytest.mark.skipif(shutil.which("node") is None, reason="node 不可用")

AMMO_DMG = 50.0        # tests/js/combat_sim_r15_test.js 中的 TEST 弹药
AMMO_PEN = 40.0


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _json(path):
    return json.loads(_read(path))


@pytest.fixture(scope="module")
def scen():
    out = subprocess.run(["node", TEST_JS, SIM_JS],
                         capture_output=True, text=True, timeout=60, cwd=ROOT)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def _pellet(scen, key, shot=0, pellet=0):
    return scen[key]["shots"][shot]["pellets"][pellet]


# ———————————————————— A：枪械决定射速 ————————————————————

def test_rpm_interval_matches_gun_data(scen):
    """Δt = 60000 / RPM：三把不同射速枪的逐发时刻必须由各自 RPM 决定。"""
    for key, rpm in (("rpm600", 600), ("rpm900", 900), ("rpm150", 150)):
        times = scen[key]
        assert len(times) >= 2
        for i, t in enumerate(times):
            expect = (i + 1) * 60000.0 / rpm
            assert abs(t - expect) <= 1.0, (key, i, t, expect)
    # 不同射速之间确实不同（不能退回固定间隔）
    assert scen["rpm600"][0] != scen["rpm900"][0]
    assert scen["rpm900"][0] < scen["rpm600"][0] < scen["rpm150"][0]


def test_rpm_required_no_silent_fallback(scen):
    """rpm 缺失或 <=0 时引擎必须抛错，不得静默使用兜底数值。"""
    assert scen["throwRpm0"] == "rpm required (>0)"
    assert scen["throwRpmMissing"] == "rpm required (>0)"


def test_gun_rates_dataset_complete():
    """data/gun-rates.json：163 把枪全部有可信 rpm 与射击模式，来源可追溯。"""
    data = _json(RATES)
    assert data.get("schema") == 1
    assert data.get("count") == 163
    assert data.get("missingCount") == 0
    assert data.get("missing") == []
    src = data.get("source") or {}
    assert "properties.fireRate" in src.get("fields", [])
    assert "json.tarkov.dev" in (src.get("url") or "")
    guns = data.get("guns") or {}
    assert len(guns) == data["count"]
    for gid, g in guns.items():
        assert isinstance(g.get("rpm"), (int, float)) and g["rpm"] > 0, gid
        modes = g.get("modes") or []
        assert modes, gid
        for m in modes:
            assert m.get("k") and m.get("n"), gid


def test_ui_rpm_is_readonly_and_tied_to_gun():
    """UI 不得存在手填 RPM 入口；射速只读来自枪械记录，缺失即阻止模拟。"""
    js = _read(APP_JS)
    for needle in ("data-sim='rpm'", 'data-sim="rpm"', "AM_SIM_RPM"):
        assert needle not in js
    assert "function simGunRate" in js
    # 只读展示：射速与 Δt 都取自枪械记录
    assert "60000 / rec.rpm" in js
    assert "射速 \" + rec.rpm" in js
    # 状态由枪械记录推导，缺失为 null
    assert "s.rpm = (rate && rate.rpm > 0) ? rate.rpm : null;" in js
    # 缺失射速明确阻止，不静默兜底
    assert "没有可信射速，已阻止模拟" in js
    # 射击模式只在数据存在时提供
    assert "data-sim\", \"gun-mode\"" in js
    assert "modes.length > 1" in js


# ———————————————————— D：Boss 装备池 ————————————————————

def test_bosses_dataset_health_and_pools():
    data = _json(BOSSES)
    assert data.get("schema") == 1
    bosses = data.get("bosses") or []
    keys = [b["k"] for b in bosses]
    assert len(bosses) >= 4
    assert len(set(keys)) == len(keys)
    parts = ["head", "chest", "stomach", "leftArm", "rightArm", "leftLeg", "rightLeg"]
    for b in bosses:
        hp = b.get("health")
        assert hp and set(hp.keys()) == set(parts), b["k"]
        assert b.get("total") == sum(hp.values()), b["k"]
        assert b.get("healthConfidence") in ("verified", "estimated", "missing")
        assert b.get("healthSource"), b["k"]
        eq = b.get("equipment") or {}
        assert eq.get("confidence") in ("verified", "estimated", "missing")
        assert isinstance(eq.get("armor"), list) and isinstance(eq.get("helmets"), list)
        fol = b.get("follower") or {}
        assert fol.get("k"), b["k"]
        # Boss 与护卫血量不得混用
        if fol.get("health"):
            assert fol["health"] != hp, b["k"]
            assert fol.get("total") == sum(fol["health"].values())


def test_bosses_pool_ids_exist_in_items():
    """装备池中的每个 id 必须存在于本地物品库，且为护甲/头盔根槽装备。"""
    data = _json(BOSSES)
    items = _json(ITEMS)["items"]
    checked = 0
    for b in data["bosses"]:
        eq = b.get("equipment") or {}
        for pid in (eq.get("armor") or []) + (eq.get("helmets") or []) + (eq.get("faces") or []):
            assert pid in items, (b["k"], pid)
            rec = items[pid]
            ok_slot = rec.get("slot") in ("armor", "helmet", "face", "rig")
            assert ok_slot, (b["k"], pid, rec.get("slot"))
            checked += 1
        fol = b.get("follower") or {}
        feq = fol.get("equipment") or {}
        for pid in (feq.get("armor") or []) + (feq.get("helmets") or []):
            assert pid in items, (fol.get("k"), pid)
            checked += 1
    assert checked >= 20


def test_generic_pools_are_not_enforced():
    """PMC/Scav 无公开固定池，示例集合必须显式标 enforced=false（不得伪造限制）。"""
    data = _json(BOSSES)
    gp = data.get("genericPools") or {}
    for kind in ("pmc", "scav"):
        eq = (gp.get(kind) or {}).get("equipment") or {}
        assert eq.get("enforced") is False, kind
        assert eq.get("confidence") in ("estimated", "verified"), kind


def test_ui_pool_filter_and_cleanup_wiring():
    js = _read(APP_JS)
    assert "function amSimTargetPool" in js
    assert "preset.pool.enforced === false" in js
    # 护甲与头盔候选都必须经过池白名单过滤
    assert "amSimGearCatalog(\"armor\", allowedA)" in js
    assert "amSimGearCatalog(\"helmet\", allowedH)" in js
    # 切换目标后清理不属于新池的旧选择
    assert "if (s.armorId && !kept)" in js
    assert "if (s.helmetId && !kept)" in js
    # Boss 来自 bosses.json，护卫来自 follower 分支
    assert "boss:<k>" in js or "\"boss:\"" in js
    assert "follower:" in js
    # 装甲胸挂（slot=rig 且有护甲）可进入护甲候选
    assert 'rec.slot === "rig" && rec.cl > 0' in js


# ———————————————————— E：多层护甲 ————————————————————

def test_plate_penetrated_then_liner_blocks(scen):
    """情况 B：高穿弹穿透硬插板，但被后方软内衬挡住 → 人体只吃钝伤。"""
    p = _pellet(scen, "ePlatePenLinerBlock")
    assert len(p["layers"]) == 2
    plate, liner = p["layers"]
    assert plate["kind"] == "plate" and plate["penetrated"] is True
    assert liner["kind"] == "liner" and liner["penetrated"] is False
    assert liner["blocked"] is True
    assert p["stoppedBy"] == "armor"
    # 状态逐层传递：内衬的输入 = 插板的输出
    assert liner["penIn"] == plate["penOut"]
    assert liner["dmgIn"] == pytest.approx(plate["dmgOut"], abs=1e-9)
    assert plate["penOut"] < plate["penIn"]
    assert plate["dmgOut"] < plate["dmgIn"]
    # 人体只收到钝伤，不吃穿透后的完整伤害
    assert p["dmgToPart"] == pytest.approx(liner["blunt"], abs=1e-9)
    assert 0 < p["dmgToPart"] < AMMO_DMG


def test_no_liner_control_full_pen_body_damage(scen):
    """对照：同样的穿透结果没有软内衬时，人体承受完整的穿透后伤害。"""
    p = _pellet(scen, "ePlatePenNoLiner")
    assert p["layers"][0]["penetrated"] is True
    assert p["stoppedBy"] is None
    assert p["dmgToPart"] == pytest.approx(p["layers"][0]["dmgOut"], abs=1e-9)
    assert p["dmgToPart"] > _pellet(scen, "ePlatePenLinerBlock")["dmgToPart"]


def test_blunt_reduced_by_soft_backing(scen):
    """情况 A：硬插板未穿透 → 插板钝伤；R65 起 0.13 原文不再乘 ×0.6（0.12 常量默认停用），
    后继软内衬只按自身 BT 衰减一次，最终人体只吃内衬输出。"""
    with_liner = _pellet(scen, "eBluntWithLiner")
    without = _pellet(scen, "eBluntNoLiner")
    plate_w = with_liner["layers"][0]
    plate_n = without["layers"][0]
    liner = with_liner["layers"][1]
    assert plate_w["blocked"] is True and plate_n["blocked"] is True
    assert plate_w.get("softBacking") is not True          # R65：×0.6 默认停用
    assert plate_n.get("softBacking") is False
    assert plate_w["bluntOut"] == pytest.approx(plate_n["bluntOut"], rel=1e-9)
    assert liner["bluntIn"] == pytest.approx(plate_w["bluntOut"], abs=1e-9)
    assert liner["bluntFactor"] == pytest.approx(0.3, abs=1e-9)   # 内衬 BT 0.30
    assert with_liner["dmgToPart"] == pytest.approx(liner["bluntOut"], abs=1e-9)
    assert with_liner["dmgToPart"] < plate_w["bluntOut"]


def test_through_both_layers_state_chain(scen):
    """情况 C：依次穿透硬插板与软内衬，只把剩余伤害交给人体。"""
    p = _pellet(scen, "eThroughBoth")
    plate, liner = p["layers"]
    assert plate["penetrated"] is True and liner["penetrated"] is True
    assert liner["penIn"] == plate["penOut"]
    assert liner["dmgIn"] == pytest.approx(plate["dmgOut"], abs=1e-9)
    assert liner["dmgOut"] < liner["dmgIn"]
    assert p["dmgToPart"] == pytest.approx(liner["dmgOut"], abs=1e-9)
    assert p["dmgToPart"] < AMMO_DMG


def test_durability_feeds_next_shot(scen):
    """情况 D：插板掉耐久后，下一发以新耐久判定并穿透（不得复用上一发状态）。"""
    shots = scen["eDurDrop"]["shots"]
    assert len(shots) == 2
    a = shots[0]["pellets"][0]["layers"][0]
    b = shots[1]["pellets"][0]["layers"][0]
    assert a["blocked"] is True and a["penetrated"] is False
    assert b["penetrated"] is True
    assert b["durBefore"] == a["durAfter"]          # 第二发用第一发后的耐久
    assert a["durAfter"] < a["durMax"]
    assert b["durAfter"] < b["durBefore"]


def test_liner_durability_independent(scen):
    """情况 D：插板与内衬耐久各自独立递减，不因一层变化而同步清零另一层。"""
    shots = scen["eLinerIndependent"]["shots"]
    assert len(shots) == 2
    p0 = shots[0]["pellets"][0]
    p1 = shots[1]["pellets"][0]
    plate0, liner0 = p0["layers"]
    plate1, liner1 = p1["layers"]
    assert plate1["durBefore"] == plate0["durAfter"]
    assert liner1["durBefore"] == liner0["durAfter"]
    assert plate0["durAfter"] > 0 and liner0["durAfter"] > 0
    assert plate1["durAfter"] > 0 and liner1["durAfter"] > 0
    # 两者耐久损失量不同（不同材质/等级，不是同一个数值）
    assert (plate0["durMax"] - plate0["durAfter"]) != (liner0["durMax"] - liner0["durAfter"])


def test_material_affects_durability_loss(scen):
    """换材质必须改变耐久损失：陶瓷(0.6) 损失 > 芳纶(0.1875)。"""
    ceramic = _pellet(scen, "eMatCeramic")["layers"][0]
    aramid = _pellet(scen, "eMatAramid")["layers"][0]
    loss_c = ceramic["durBefore"] - ceramic["durAfter"]
    loss_a = aramid["durBefore"] - aramid["durAfter"]
    assert loss_c > loss_a > 0


def test_class_affects_penetration_result(scen):
    """换护甲等级必须改变穿透结果（同一发弹同一随机流）。"""
    p3 = _pellet(scen, "eClass3")
    p5 = _pellet(scen, "eClass5")
    assert p3["layers"][0]["penetrated"] is True
    assert p5["layers"][0]["penetrated"] is False
    assert p3["dmgToPart"] > 0
    assert p5["dmgToPart"] > 0 and p5["dmgToPart"] < p3["dmgToPart"]


def test_armor_scenarios_reproducible(scen):
    assert scen["eReproA"] == scen["eReproA2"]
    assert json.loads(scen["eReproA"])["shotCount"] >= 1


# ———————————————————— F：障碍物 ————————————————————

def test_barriers_dataset_structured():
    data = _json(BARRIERS)
    assert data.get("schema") == 1
    rows = data.get("barriers") or []
    assert len(rows) >= 8
    ids = [r["id"] for r in rows]
    assert len(set(ids)) == len(ids)
    for r in rows:
        assert r.get("n") and r.get("material")
        assert isinstance(r.get("penChanceMul"), (int, float))
        assert isinstance(r.get("dmgKeep"), (int, float))
        assert isinstance(r.get("penKeep"), (int, float))
        assert isinstance(r.get("ricochetMul"), (int, float))
        assert 0 <= r["penChanceMul"] <= 1 and 0 < r["dmgKeep"] <= 1 and 0 < r["penKeep"] <= 1
        assert r.get("confidence") == "estimated"
        assert "thickness" in r
    # 明确声明不是游戏原始数据
    note = (data.get("source") or {}).get("note", "")
    assert "不是游戏原始数据" in note
    assert "missing" in ((data.get("fields") or {}).get("thickness") or "")


def test_barrier_baseline_single_and_multi(scen):
    """无障碍 → 一层 → 两层：伤害必须逐层递减，且层间状态链一致。"""
    base = _pellet(scen, "fBase")
    one = _pellet(scen, "fOne")
    two = _pellet(scen, "fTwo")
    assert base["barriers"] == []
    assert base["dmgToPart"] == pytest.approx(AMMO_DMG, abs=1e-9)
    assert one["dmgToPart"] < base["dmgToPart"]
    assert two["dmgToPart"] < one["dmgToPart"]
    # 层间传递：后一层的输入 = 前一层的输出
    b0, b1 = two["barriers"]
    assert b0["passed"] is True and b1["passed"] is True
    assert b1["penIn"] == pytest.approx(b0["penOut"], abs=1e-9)
    assert b1["dmgIn"] == pytest.approx(b0["dmgOut"], abs=1e-9)
    # 每层都有可审计字段
    for b in two["barriers"]:
        for k in ("baseChance", "chance", "roll", "passed", "penIn", "penOut", "dmgIn", "dmgOut"):
            assert k in b


def test_barrier_block_terminates_shot(scen):
    """无法穿透障碍：子弹终止，不得继续对人体结算任何伤害。"""
    p = _pellet(scen, "fBlocked")
    assert p["barriers"][0]["passed"] is False
    assert p["stoppedBy"] == "barrier"
    assert p["dmgToPart"] == 0
    assert p["layers"] == []
    assert scen["fBlocked"]["targetFinal"]["total"] == pytest.approx(
        sum(scen["fBlocked"]["targetFinal"]["parts"][k]["max"]
            for k in scen["fBlocked"]["targetFinal"]["parts"]))


def test_barrier_order_changes_result(scen):
    """同一随机种子，仅改变障碍顺序就必须改变结果（金属在前挡住 / 木板在前通过）。"""
    ab = _pellet(scen, "fOrderAB")
    ba = _pellet(scen, "fOrderBA")
    assert ab["stoppedBy"] == "barrier" and ab["dmgToPart"] == 0
    assert ba["stoppedBy"] is None and ba["dmgToPart"] > 0
    assert [b["name"] for b in ab["barriers"]] != [b["name"] for b in ba["barriers"]]


def test_barrier_then_armor_uses_reduced_state(scen):
    """穿过障碍后命中插板与内衬：护甲层必须吃障碍后的剩余弹体状态。"""
    p = _pellet(scen, "fThenArmor")
    assert len(p["barriers"]) == 1 and p["barriers"][0]["passed"] is True
    plate, liner = p["layers"]
    assert plate["penIn"] == pytest.approx(p["barriers"][0]["penOut"], abs=1e-9)
    assert plate["dmgIn"] == pytest.approx(p["barriers"][0]["dmgOut"], abs=1e-9)
    assert plate["penIn"] < AMMO_PEN
    assert plate["dmgIn"] < AMMO_DMG
    assert liner["penIn"] == pytest.approx(plate["penOut"], abs=1e-9)
    assert p["dmgToPart"] == pytest.approx(liner["dmgOut"], abs=1e-9)


def test_barrier_scenarios_reproducible(scen):
    assert scen["fReproA"] == scen["fReproA2"]


# ———————————————————— 布局 / 离线 ————————————————————

def test_ui_order_gun_barrier_target_armor():
    """阅读顺序：枪械 → 障碍物 → 目标类型 → 目标护甲 → 命中分布 → 执行。"""
    js = _read(APP_JS)
    idx = {}
    for key in ("var boxGun", "var box1", "var boxB", "var box3", "var box4", "var box5", "var box6"):
        pos = js.find(key)
        assert pos >= 0, key
        idx[key] = pos
    assert idx["var boxGun"] < idx["var boxB"] < idx["var box3"] < idx["var box4"] < idx["var box5"] < idx["var box6"]
    assert idx["var box1"] < idx["var boxB"]
    # 障碍物栏不是折叠面板
    assert "am-sim-barrierbox" in js
    assert "data-sim\", \"barrier-add\"" in js or "data-sim='barrier-add'" in js


def test_runtime_offline_no_external_dependency():
    """运行期离线：HTML 不加载外部脚本/样式，模拟器数据均为本地相对路径。"""
    html = _read(INDEX)
    for line in html.splitlines():
        low = line.strip().lower()
        if low.startswith("<script") or low.startswith("<link"):
            assert "http://" not in low and "https://" not in low, line
    js = _read(APP_JS)
    assert "AM_SIM_BOSSES_URL = \"data/bosses.json\"" in js
    assert "AM_SIM_BARRIERS_URL = \"data/barriers.json\"" in js
    assert "AM_SIM_RATES_URL = \"data/gun-rates.json\"" in js
    assert "fetch(\"http" not in js and "fetch('http" not in js
    for path in (BOSSES, RATES, BARRIERS):
        assert os.path.exists(path), path
