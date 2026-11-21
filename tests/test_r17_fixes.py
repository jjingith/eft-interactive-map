# -*- coding: utf-8 -*-
"""R17：护甲损毁公式 / 全口径弹药筛选 / Top-Loop-Bottom 预设压弹 / 肉体伤害专项测试

引擎数值断言在 Python 侧完成：tests/js/combat_sim_r17_test.js 只导出原始结果。
用户提供的异常案例（5.56 HP 打 5 级陶瓷每发掉 7 点）作为固定回归用例保留。
"""
import json
import os
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIM_JS = os.path.join(ROOT, "combat_sim.js")
TEST_JS = os.path.join(ROOT, "tests", "js", "combat_sim_r17_test.js")
APP_JS = os.path.join(ROOT, "app.js")
STYLE = os.path.join(ROOT, "style.css")
COMPAT = os.path.join(ROOT, "data", "gun-compat.json")
AMMO = os.path.join(ROOT, "data", "ammo.json")
DOCS = os.path.join(ROOT, "docs", "r17-fixes")


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _json(path):
    return json.loads(_read(path))


require_node = pytest.mark.skipif(shutil.which("node") is None, reason="node 不可用")


@pytest.fixture(scope="module")
def scen():
    out = subprocess.run(["node", TEST_JS, SIM_JS], capture_output=True, text=True, timeout=60, cwd=ROOT)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


# ———————————————————— A：护甲耐久损毁 ————————————————————

def test_user_case_hp_vs_class5_ceramic(scen):
    """用户案例回归：5.56 HP（甲伤22 穿7）打 5 级陶瓷（50 耐久）——R62 起按
    反编译原文：base = 7 × 0.22 × clamp(7/50, 0.6, 1.1) × 0.6 = 0.5544，
    未穿仍取最低 1 点，每发掉 1。"""
    uc = scen["userCase"]
    assert uc["perShot"] == [1] * 8
    assert uc["durAfter"] == 42          # 50 − 8×1
    assert uc["durBase"] == pytest.approx(7 * 0.22 * 0.6 * 0.6, abs=0.005)
    assert uc["durCoeff"] == pytest.approx(0.6)
    assert uc["durMode"] == "decomp"
    assert uc["conf"] == "estimated"


def test_durability_formula_dimensions(scen):
    """量纲断言（R62）：decomp 模式甲伤系数 clamp(P/(10×AC), 0.6, 1.1)，
    durBase == 穿深 × 甲伤% × 材质毁损系数 × 0.8；最低 1 点；Ceramic=0.6
    （来自 globals ArmorMaterials，不再是站点旧表 0.55）。"""
    c = scen["consts"]
    assert c["MODE"] == "decomp"
    assert c["LINER_MUL"] == 0.6
    assert c["MAT"]["ceramic"] == pytest.approx(0.6)
    for m, v in c["MAT"].items():
        assert 0 < v < 1, m                     # 材质毁损系数是 0–1 的比例
    mats = scen["materials"]
    for m, rec in mats.items():
        # 场景：穿深 40 / 甲伤 30 / 5 级板满耐久 / 未穿透（40/50=0.8 未触 clamp）
        expect_base = 40 * (30 / 100.0) * c["MAT"][m] * 0.8
        assert rec["durBase"] == pytest.approx(expect_base, abs=0.01), m
        assert rec["durDmg"] >= 1, m
    # 材质排序按毁损系数：陶瓷 > 装甲钢 > 钛 > 芳纶
    assert (mats["ceramic"]["durBase"] > mats["armorSteel"]["durBase"] >
            mats["titan"]["durBase"] > mats["aramid"]["durBase"])


def test_pen_penetrates_less_than_unpen(scen):
    """R62：穿透用击穿系数 clamp(...,0.5,0.9)，未穿用挡下系数 clamp(...,0.6,1.1)。
    52/50=1.04：击穿侧截断到 0.9，挡下侧保持 1.04，因此未穿损甲更高。"""
    pv = scen["penVsUnpen"]
    assert pv["pen"]["coeff"] == pytest.approx(0.9)
    assert pv["unpen"]["coeff"] == pytest.approx(1.04)
    assert pv["unpen"]["durDmg"] > pv["pen"]["durDmg"]
    assert pv["pen"]["durBase"] / pv["unpen"]["durBase"] == pytest.approx(0.9 / 1.04, abs=1e-4)


def test_low_pen_does_not_shred_high_class(scen):
    """低穿弹（穿7/5 级=0.14）夹到下限 0.6，只能打 1；高穿弹（穿50/50=1.0）12 点。"""
    lv = scen["lowVsHigh"]
    assert lv["low"]["durDmg"] == 1
    assert lv["high"]["durDmg"] > 10
    assert lv["high"]["durDmg"] > lv["low"]["durDmg"] * 8
    assert lv["low"]["coeff"] == pytest.approx(0.6)
    assert lv["low"]["durBase"] == pytest.approx(7 * 0.22 * 0.6 * 0.6, abs=0.005)


def test_zero_durability_behavior_is_marked_estimated(scen):
    """耐久归零后的下一发：degraded + 显式 estimated 标注；内衬仍按自己的机制结算（只吃钝伤）。"""
    zd = scen["zeroDur"]
    assert zd["shot1"]["durAfter"] == 0 and zd["shot1"]["degraded"] is False
    assert zd["shot2"]["degraded"] is True
    assert zd["shot2"]["zeroConf"] == "estimated"
    assert zd["shot2"]["linerBlocked"] is True
    assert zd["shot2"]["stoppedBy"] == "armor"
    assert 0 < zd["shot2"]["blunt"] < 60


def test_multilayer_no_double_counting(scen):
    """一发穿过板+内衬：每层各自扣耐久，总甲伤 = 各层之和（不重复计算）。"""
    ml = scen["multiLayer"]
    assert ml["dmgToArmor"] == ml["sum"]
    assert ml["plateDmg"] > 0 and ml["linerDmg"] > 0


def test_shotgun_pellet_min_one_each(scen):
    """霰弹 4 弹丸零穿透：单发总甲伤 ≥ 4（每颗最低 1 点，wiki 口径）。"""
    sg = scen["shotgun"]
    assert sg["shotPellets"] == 4
    assert sg["dmgToArmor"] >= 4


# ———————————————————— B：全口径弹药筛选（数据不变量） ————————————————————

# 上游 allowedAmmo 里唯一有据可查的跨口径情况：9x18PMM 枪可以吃 9x18 PM 弹
CROSS_CALIBER_OK = {("9x18PMM", "9x18")}


def test_ammo_lists_match_gun_caliber():
    """163 把枪的白名单逐条核对：弹药口径必须与枪口径一致（PP-9 的 9x18 是有据例外）。"""
    compat = _json(COMPAT)["guns"]
    ammo = {a["id"]: a for a in _json(AMMO)["ammo"]}
    bad = []
    for gid, g in compat.items():
        for aid in g["ammo"]:
            pair = (g["caln"], ammo[aid]["caln"])
            if pair not in CROSS_CALIBER_OK and g["caln"] != ammo[aid]["caln"]:
                bad.append((g["n"], pair))
    assert bad == []


def test_representative_calibers_present_and_correct():
    """六个代表口径：弹药白名单非空且口径全部正确。"""
    compat = _json(COMPAT)["guns"]
    ammo = {a["id"]: a for a in _json(AMMO)["ammo"]}
    expect = {
        "柯尔特 M4A1": "5.56x45",
        "AKS-74N": "5.45x39",
        "AKM": "7.62x39",
        "MP5": "9x19",
        "MP-133": "12g",
        "SR-25": "7.62x51",
    }
    found = {}
    for g in compat.values():
        for key, caln in expect.items():
            if key in g["n"]:
                cals = {ammo[aid]["caln"] for aid in g["ammo"]}
                assert cals == {caln}, (g["n"], cals, caln)
                found[key] = True
    assert len(found) == len(expect), found


def test_gun_compat_has_no_shared_list():
    """163 把枪的白名单不能是同一份列表（旧症状「永远 5.56」的数据面表现）。"""
    import hashlib
    compat = _json(COMPAT)["guns"]
    sigs = {hashlib.md5(json.dumps(sorted(g["ammo"]), sort_keys=True).encode()).hexdigest()
            for g in compat.values()}
    assert len(sigs) >= 25


# ———————————————————— C：Top / Loop / Bottom 预设压弹 ————————————————————

def test_preset_top_loop_bottom_order(scen):
    """Top 3×A → Loop B/C 循环 7 发 → Bottom 2×D；末轮不满按序截断。"""
    p = scen["preset"]["mixed"]
    assert p["ok"] is True
    assert p["sequence"] == ["A", "A", "A", "B", "C", "B", "C", "B", "C", "B", "D", "D"]
    assert len(p["sequence"]) == 12
    assert p["warnings"], "末轮 7 发不是整轮（B,C 共 2 发/轮），必须有截断提示"


def test_preset_loop_only_fills_capacity(scen):
    p = scen["preset"]["loopOnly"]
    assert p["sequence"] == ["B", "C", "B", "C", "B", "C"]


def test_preset_single_ammo_fills_mag(scen):
    p = scen["preset"]["single"]
    assert p["sequence"] == ["A"] * 10


def test_preset_top_bottom_over_capacity_rejected(scen):
    p = scen["preset"]["over"]
    assert p["ok"] is False
    assert "超过弹匣容量" in p["error"]


def test_preset_empty_loop_rows_skipped(scen):
    p = scen["preset"]["emptyLoopRow"]
    assert p["sequence"] == ["B", "C", "B", "C", "B"]


def test_preset_bottom_only_warns_unfilled(scen):
    """只有末发、循环区全空：只装末发的 2 发，并提示剩余 3 发未装填。"""
    p = scen["preset"]["bottomOnly"]
    assert p["sequence"] == ["D", "D"]
    assert any("剩余 3 发未装填" in w for w in p["warnings"])


def test_preset_unknown_capacity_rejected(scen):
    assert scen["preset"]["noCapacity"]["ok"] is False
    assert "容量未知" in scen["preset"]["noCapacity"]["error"]


def test_preset_empty_rejected(scen):
    assert scen["preset"]["empty"]["ok"] is False


def test_preset_loop_weights(scen):
    """循环行的数量 = 每轮发数：B×2 + C×1 为一轮。"""
    p = scen["preset"]["weights"]
    assert p["sequence"] == ["A", "B", "B", "C", "B", "B", "E"]


# ———————————————————— 补充：肉体伤害 / 黑化分散 / 续命中 ————————————————————

def test_normal_chest_hit_no_limb_multiplier(scen):
    b = scen["body"]["chest"]
    assert b["dmgToPart"] == 40.0
    assert b["chest"] == 45.0               # 85 − 40，原样结算
    assert b["overflow"] is None


def test_normal_arm_leg_stomach_hits_full_damage(scen):
    """正常命中手臂/腿/胃：按剩余有效伤害原样结算，不套用任何分散倍率。"""
    assert scen["body"]["leftArm"]["dmgToPart"] == 40.0
    assert scen["body"]["leftArm"]["leftArm"] == 20.0
    assert scen["body"]["leftLeg"]["dmgToPart"] == 40.0
    assert scen["body"]["leftLeg"]["leftLeg"] == 25.0
    assert scen["body"]["stomach"]["dmgToPart"] == 40.0
    assert scen["body"]["stomach"]["stomach"] == 30.0


def test_blacked_arm_spreads_at_049(scen):
    ov = scen["body"]["blackedArm"]["overflow"]
    assert ov["dmg"] == pytest.approx(40 * 0.49, abs=1e-9)
    assert scen["body"]["blackedArm"]["aliveParts"] == 6
    assert ov["each"] == pytest.approx(40 * 0.49 / 6, abs=1e-9)


def test_blacked_leg_spreads_at_07(scen):
    """r17 修正回归：腿的黑化分散是 0.7×（wiki verified），不是旧代码的手臂 0.49×。"""
    ov = scen["body"]["blackedLeg"]["overflow"]
    assert ov["dmg"] == pytest.approx(40 * 0.7, abs=1e-9)
    assert ov["each"] == pytest.approx(40 * 0.7 / 6, abs=1e-9)


def test_blacked_stomach_spreads_at_105(scen):
    ov = scen["body"]["blackedStomach"]["overflow"]
    assert ov["dmg"] == pytest.approx(40 * 1.05, abs=1e-9)
    assert ov["each"] == pytest.approx(40 * 1.05 / 6, abs=1e-9)


def test_through_body_hit_degrades_and_hits_chest_normally(scen):
    """穿过手臂后命中胸腔：弹体按估算系数衰减，胸腔按正常命中结算（不套用黑化倍率）。"""
    off = scen["body"]["throughOff"]
    on = scen["body"]["throughOn"]
    assert off["has"] is False and off["chest"] == 85.0        # 默认关闭
    assert on["tb"]["confidence"] == "estimated"
    assert on["tb"]["from"] == "leftArm" and on["tb"]["to"] == "chest"
    assert on["tb"]["dmg"] == pytest.approx(40 * 0.6, abs=1e-9)
    assert on["chest"] == pytest.approx(85 - 24, abs=1e-9)
    assert on["arm"] == 20.0


def test_boss_and_pmc_use_own_hp_pools(scen):
    bv = scen["body"]["bossVsPmc"]
    assert bv["pmcChest"] == 45.0                              # 85 − 40
    assert bv["bossChest"] == 170.0                            # 210 − 40（Killa 胸腔）


def test_body_damage_reproducible(scen):
    assert scen["body"]["reproA"] == scen["body"]["reproB"]


# ———————————————————— UI 接线 / 构建标记 ————————————————————

def test_ui_preset_loader_wiring():
    """R17S：预设行改为点击方框 + 弹窗选弹；旧式独立填弹 UI 必须移除。"""
    js = _read(APP_JS)
    assert 'data-sim", "preset-rows"' in js
    assert 'data-sim", "preset-count"' in js
    assert 'data-act", "sim-preset-pick"' in js          # 可点击方框
    assert 'data-act", "sim-preset-choose"' in js        # 弹窗写入
    assert 'data-act", "sim-dialog-close"' in js
    assert 'data-sim", "preset-ammo"' not in js          # 旧下拉已删
    assert '"ammo-pick"' not in js                       # 旧独立填弹下拉已删
    assert '"mag-count"' not in js                       # 旧数量输入已删
    assert 'data-act", "sim-load"' not in js             # 旧装填按钮已删
    assert "sim-preset-load" in js
    assert "sim-preset-toloop" not in js                 # 换区按钮已删：全部行可拖拽换区
    assert "buildMagazineFromPreset" in js               # 序列生成器保留
    assert "amSimPresetDrop" in js and "amSimPresetZoneCount" in js
    assert "sim-preset-add" in js and "AM_SIM_ZONE_MAX" in js   # R17S4：可变条目 + 分区上限
    assert "am-sim-zsec" in js and "am-sim-zhead" in js  # 三个分区有独立标题/分隔
    # 小叉叉清空 = 弹药 + 数量一起清
    assert "s.magPreset[sc].ammoId = null" in js and "s.magPreset[sc].count = 0" in js
    # 逐发预览列表已删除（不是隐藏）：不再产生队列 chip/箭头 DOM
    assert "am-sim-magchip" not in js and '"sim-mag-up"' not in js and '"sim-mag-del"' not in js
    assert "amSimQueueBlocks" not in js and "amSimMoveQueueBlock" not in js
    # R17S3：弹窗挂 document.body（fixed 浮层）+ Esc + uid 拖放 + 前/后插入提示
    assert '"am-sim-ammo-dlg"' in js
    assert 'document.addEventListener("mousedown"' in js
    assert '"Escape"' in js
    assert "amSimIdxByUid" in js and "dataset.uid" in js
    assert "am-sim-dropbefore" in js and "am-sim-dropafter" in js
    assert '(pos === "after") ? t0 + 1 : t0' in js   # 同区按目标行前/后插入（真排序）
    assert '(pos === "after") ? t + 1 : t' in js      # 跨区插入也按目标行前/后
    # R17S3：旧队列 UI 的 DOM/渲染/绑定彻底删除（不是隐藏）
    assert '"sim-clear-mag"' not in js
    assert '"am-sim-magicon"' not in js
    assert "renderSimMagList" not in js
    assert "capTagRefresh" not in js
    assert "amSimQueueBlocks" not in js
    assert '"ammo-dialog"' not in js          # inline 弹窗容器已移除（弹窗在 body 根）
    # 型号缩写：同一映射用于行徽标与弹窗选项
    assert "amSimAmmoShort" in js
    # 弹窗点击外部自动关闭
    assert 'document.addEventListener("mousedown"' in js
    assert 'addEventListener("dragstart"' in js and 'addEventListener("drop"' in js
    # 弹窗列表：穿透力数值升序（不是字符串排序）
    assert "(ra.pen || 0) - (rb.pen || 0)" in js


def test_ui_preset_compatible_cleanup_wiring():
    js = _read(APP_JS)
    assert "presetCleared" in js
    assert "已切换枪械：清空了" in js


def test_ui_hit_mode_mutex_and_seed_wiring():
    """R17S：命中模式两个互斥复选框；随机种子默认不固定、用 crypto 生成。"""
    js = _read(APP_JS)
    assert 'data-sim", "hit-fixed"' in js and 'data-sim", "hit-dist"' in js
    assert 'data-sim", "hit-mode"' not in js             # 旧下拉已删
    assert "renderSimHitMode" in js
    assert 'data-sim", "seed-fixed"' in js
    assert "getRandomValues" in js
    assert "math.random（crypto 不可用时的 fallback）" in js
    # 不再默认写死 12345：cfgFromUI 里旧兜底表达式必须消失
    assert "s.seed = isFinite(seed) ? seed : 12345" not in js
    assert "seedSource" in js
    assert "__seedSource" in js                          # 结果摘要记录实际使用的基种子


def test_index_html_versioned_assets():
    """R17S 缓存加固：脚本/样式带版本参数，改动后旧会话不会再吃 memory cache。"""
    html = _read(os.path.join(ROOT, "index.html"))
    assert 'src="app.js?v=' in html
    assert 'src="combat_sim.js?v=' in html
    assert 'href="style.css?v=' in html


def test_ui_ammo_list_reload_hooks():
    """R17-B 加固：弹药数据晚到时补渲染；面板带可见构建标记（版本随 ?v= 同步升级）。

    R18.1 起断言改为「构建标记存在，且与 index.html 的资源版本参数一致」——
    原断言把轮次号写死成 "R18"，每轮升级都要改测试，反而弱化了真正的不变量
    （标记与资源版本必须同步，否则浏览器会继续吃旧脚本）。断言强度不变。
    """
    import re
    js = _read(APP_JS)
    assert "ensureAmmo().then" in js
    m = re.search(r'AM_BUILD = "([^"]+)"', js)
    assert m, "app.js 缺少可见构建标记 AM_BUILD"
    build = m.group(1)
    html = _read(os.path.join(ROOT, "index.html"))
    assert "v=" + build.lower() in html, "index.html 的资源版本参数未与 AM_BUILD(%s) 同步" % build


def test_docs_present():
    for name in ("baseline.md", "armor-durability-research.md", "caliber-filter-investigation.md",
                 "magazine-preset-design.md", "body-damage-research.md", "change-log.md",
                 "test-report.md"):
        assert os.path.exists(os.path.join(DOCS, name)), name
    assert os.path.isdir(os.path.join(DOCS, "screenshots"))


# ———————————————————— R17S2：严格序列长度 / 多弹药固定区 ————————————————————

def test_preset_exact30_no_missing_rounds(scen):
    """用户报告的算术矛盾回归：30 发弹匣 Top3 + Loop(B1,C1) + Bottom2，
    序列必须恰好 30 发 —— loop 25 发占第 4–28 发，bottom 占第 29–30 发，无跳号。"""
    p = scen["preset"]["exact30"]
    assert p["ok"] is True
    seq = p["sequence"]
    assert len(seq) == 30
    assert seq[0:3] == ["A", "A", "A"]
    assert seq[3:28] == ["B", "C"] * 12 + ["B"]          # 25 发，循环截断
    assert seq[28:30] == ["D", "D"]
    # 逐位核对：位置 28（第 28 发）必须是 B，不允许被遗漏
    assert seq[27] == "B" and seq[28] == "D"


def test_preset_multi_entry_fixed_zones(scen):
    """首发/末尾都允许多个条目：按配置顺序输出，不参与循环。"""
    p = scen["preset"]["multiFixed"]
    assert p["ok"] is True
    seq = p["sequence"]
    assert len(seq) == 30
    assert seq[0:3] == ["A", "A", "B"]                    # 首发两段按序（2+1 发）
    assert seq[3:28] == ["C"] * 25                        # 循环单弹填满中段 25 发
    assert seq[28:30] == ["D", "E"]                       # 末尾两段按序


def test_preset_three_loop_ammo_alternates(scen):
    p = scen["preset"]["threeLoop"]
    assert p["sequence"] == ["A", "B", "C", "A", "B", "C", "A", "B", "C", "A"]
    assert len(p["sequence"]) == 10


def test_preset_top_multi_only_and_capacity_truncation(scen):
    p1 = scen["preset"]["topMultiOnly"]
    assert p1["sequence"] == ["A", "A", "B", "B", "B"]
    p2 = scen["preset"]["capTruncTop"]
    assert p2["sequence"] == ["A", "A", "A", "A", "A"]    # 首发超过容量：截断到容量
    assert p2["ok"] is True


def test_ui_zone_sections_and_drag_model():
    """R17S4：分区标题、全行可拖、跨区为「插入」语义（不替换、不覆盖、不留副本）。"""
    js = _read(APP_JS)
    assert "amSimPresetDrop" in js
    assert "插入" in js and "不再保留副本" in js
    assert "已阻止本次移动，原配置保持不变" in js      # 循环满 5 时拒绝且不丢配置
    # 分区标题与视觉分隔
    for token in ("首发区 · 最先射出", "循环区 · 按行序反复填满中段", "末尾区 · 最后射出"):
        assert token in js
    css = _read(STYLE)
    assert ".am-sim-zsec" in css and ".am-sim-zhead" in css


# ———————————————————— R17S3：顺序语义 / 型号缩写 ————————————————————

def test_preset_zone_internal_order_drives_sequence(scen):
    """循环区 C,A,B → 弹序必须按 C,A,B 循环（不是 A,B,C）。"""
    p = scen["preset"]["loopCAB"]
    assert p["ok"] is True
    assert p["sequence"] == ["C", "A", "B"] * 3
    assert len(p["sequence"]) == 9


def test_preset_top_bottom_internal_order(scen):
    """首发 A,B,B / 末尾 F,G：区内顺序 = 射出顺序。"""
    p = scen["preset"]["topOrder"]
    assert p["ok"] is True
    assert p["sequence"] == ["A", "B", "B", "F", "G"]


def test_ammo_short_names_distinguish_models():
    """型号缩写 = 剥掉口径前缀后的真实型号（M995/M855A1…），非口径数字；
    与 app.js 的 amSimAmmoShort 同一算法（口径前缀 + 毫米/空格）。"""
    ammo = _json(AMMO)["ammo"]
    rows = {a["id"]: a for a in ammo}

    def short(rec):
        n, caln = str(rec["n"]), str(rec["caln"])
        sh = n
        if caln and n.startswith(caln):
            import re as _re
            sh = _re.sub(r"^(毫米|mm|×|X| )+", "", n[len(caln):])
        return sh or n

    m4 = _json(COMPAT)["guns"]["5447a9cd4bdc2dbd208b4567"]
    shorts = [short(rows[i]) for i in m4["ammo"]]
    assert len(set(shorts)) == len(shorts), "同口径弹药的型号缩写必须互不相同"
    for sh in shorts:
        assert "5.56" not in sh or "5.56" in sh[:2], sh  # 缩写不等于口径数字
    assert "M995" in shorts and "M855A1" in shorts


# ———————————————————— R17S4：命中率 / 循环上限 / 五类口径 ————————————————————

def test_hit_rate_100_equals_disabled(scen):
    """100% 命中必须与「关闭命中率」逐发日志完全一致（不额外消耗随机数）。"""
    h = scen["hitRate"]
    assert h["off"]["hits"] == h["off"]["shotCount"]
    assert json.dumps(h["off"]["shots"], sort_keys=True) == json.dumps(h["h100"]["shots"], sort_keys=True)
    assert h["h100"]["hits"] == h["h100"]["shotCount"]


def test_hit_rate_zero_no_damage_no_wear(scen):
    """0%：不发命中伤害 → 护甲耐久与部位 HP 完全不变，但弹药照常消耗。"""
    h = scen["hitRate"]["h0"]
    assert h["hits"] == 0 and h["misses"] == h["shotCount"] == 4
    assert h["armorFinal"][0]["dur"] == h["armorFinal"][0]["durMax"] == 40
    assert h["targetFinal"]["total"] == 755
    assert h["dead"] is False
    assert h["roundsLeft"] == 0                      # 4 发全部消耗
    for s in h["shots"]:
        assert s["hit"] is False and s["miss"] is True
        assert s["part"] is None
        assert s["dmgToPart"] == 0 and s["dmgToArmor"] == 0


def test_hit_rate_partial_deterministic(scen):
    """50%：命中/未命中混合，同种子完全复现。"""
    a = scen["hitRate"]["h50a"]
    b = scen["hitRate"]["h50b"]
    assert a["hits"] + a["misses"] == 4
    assert 0 < a["hits"] < 4
    assert json.dumps(a["shots"], sort_keys=True) == json.dumps(b["shots"], sort_keys=True)


def test_hit_rate_miss_keeps_barrier_resolution(scen):
    """未命中不跳过障碍物逻辑：掩体仍按实际路径逐层结算，但无人体伤害。"""
    m = scen["hitRate"]["missBarrier"]
    shot = m["shots"][0]
    assert shot["miss"] is True
    assert len(shot["pellets"][0]["barriers"]) == 1
    assert shot["dmgToPart"] == 0
    assert m["armorFinal"][0]["dur"] == 40


def test_preset_loop_cap_five(scen):
    """循环区第 6 种弹药被引擎拒绝（UI 也阻止）；5 种可正常装填。"""
    p6 = scen["preset"]["loop6"]
    assert p6["ok"] is False
    assert "最多 5 种" in p6["error"]
    p5 = scen["preset"]["threeLoop"]
    assert p5["ok"] is True


def test_caliber_groups_cover_all_gun_calibers():
    """data/caliber-groups.json 必须覆盖枪械表里的全部口径，且类别合法、弹径为正。"""
    groups = _json(os.path.join(ROOT, "data", "caliber-groups.json"))
    cats = [c["id"] for c in groups["categories"]]
    assert cats == ["pistol_smg", "rifle", "shotgun", "pdw", "grenade"]   # 固定顺序
    compat = _json(COMPAT)["guns"]
    used = {v["cal"] for v in compat.values()}
    mapped = set(groups["calibers"].keys())
    missing = used - mapped
    assert not missing, "未归类口径：%s" % missing
    for cal, rec in groups["calibers"].items():
        assert rec["cat"] in cats, (cal, rec["cat"])
        assert rec["dia"] > 0, cal


def test_caliber_group_order_examples():
    """组内弹径降序：手枪组 12.7 > 11.43 > 9，步枪组 12.7 > 9.55 > 9 > 5.45，
    霰弹 23 > 12g(18.5) > 20g(15.6)，PDW/榴弹按真实口径。"""
    g = _json(os.path.join(ROOT, "data", "caliber-groups.json"))["calibers"]
    def dia(cal):
        return g[cal]["dia"]
    def cat(cal):
        return g[cal]["cat"]
    assert cat("Caliber9x19PARA") == "pistol_smg" and cat("Caliber1143x23ACP") == "pistol_smg"
    assert dia("Caliber127x33") > dia("Caliber1143x23ACP") > dia("Caliber9x19PARA")
    assert cat("Caliber762x39") == "rifle" and dia("Caliber762x39") > dia("Caliber545x39")
    assert dia("Caliber366TKM") > dia("Caliber9x39") > dia("Caliber545x39")
    assert cat("Caliber12g") == "shotgun" and cat("Caliber20g") == "shotgun"
    assert dia("Caliber23x75") > dia("Caliber12g") > dia("Caliber20g")
    assert cat("Caliber46x30") == "pdw" and dia("Caliber57x28") > dia("Caliber46x30")
    assert cat("Caliber40x46") == "grenade" and dia("Caliber40x46") == 40


def test_ui_hit_rate_and_caliber_wiring():
    """UI 接线：命中率复选框/输入框、五类口径分组、口径元数据加载。"""
    js = _read(APP_JS)
    for token in ('data-sim", "hit-rate-on"', 'data-sim", "hit-rate"', "renderSimHitRate",
                  "AM_SIM_CALGROUP_URL", "ensureSimCalGroups", "amSimCalMeta",
                  "未识别口径"):
        assert token in js, token
    assert "hitChance: s.hitRateOn ? (s.hitRate / 100) : undefined" in js
    # 命中率未勾选时输入框隐藏（display none），不是可编辑
    assert 'hrInp.style.display = s.hitRateOn ? "" : "none"' in js
