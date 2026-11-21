# -*- coding: utf-8 -*-
"""R19.12 合并开发 · 自动化测试

覆盖（对应任务书第八节）：
  1 枪匠大师全局兼容性：整树互斥 / 结构 / 声称件 / 无解 / 与安装入口同一口径
  2 固定 6×9 画布：锚点常量 + 全枪不变量（r1912_layout.js）
  3 默认弹药：FMJ 优先 / 中位数兜底 / 数据缺口不虚构
  4 动态外观：真实装配驱动 + 签名缓存 + 资源审计结论
  5 R19.11 回归锚点：容量硬约束 / 个人属性 / 红斜纹 / SPEAR 弹匣
"""
import json
import os
import re
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "app.js")
ENGINE = os.path.join(ROOT, "gun_builder.js")
CSS = os.path.join(ROOT, "style.css")
HTML = os.path.join(ROOT, "index.html")
AUDIT = os.path.join(ROOT, "docs", "r19.12-canvas-audit")   # R19.12 的产物目录（R19.13 另有 layout-audit）
NODE_TOOL = os.path.join(ROOT, "tools", "r1912_engine.js")
LAYOUT_TOOL = os.path.join(ROOT, "tools", "r1912_layout.js")
AMMO_TOOL = os.path.join(ROOT, "tools", "r1912_ammo.js")

M4A1 = "5447a9cd4bdc2dbd208b4567"
AK74 = "5bf3e03b0db834001d2c4a9c"
HERA = "5a33e75ac4a2826c6e06d759"          # Hera Arms CQR AR-15 一体化枪托（握把槽）
UBR = "5947e98b86f774778f1448bc"           # Magpul UBR GEN2 AR-15 枪托（黑色）
GLOCK = "5a7ae0c351dfba0017554310"
GTL = "59d790f486f77403cb06aec6"           # Glock GTL 21 手电


def _read(p):
    with open(p, encoding="utf-8", newline="") as f:
        return f.read()


def _run_node(args, timeout=300):
    return subprocess.run(["node"] + args, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)


# ---------------------------------------------------------------- 1. 优化器兼容性
def test_conflict_rules_are_shared_by_all_entry_points():
    """互斥判定只有一套：conflictPairs 双向比较，validate/checkConstraints/verifyBuild 共用。"""
    js = _read(ENGINE)
    assert "function conflictPairs(ctx, installed)" in js
    assert "function conflictsWith(ctx, idA, idB)" in js
    # 双向：任一方向声明即算
    assert "conflictSet(ctx, idA)[idB]" in js and "conflictSet(ctx, idB)[idA]" in js
    # validate / checkConstraints / verifyBuild 都走同一口径
    assert js.count("conflictPairs(ctx, installed)") >= 2, "校验入口必须真的调用冲突检查"
    assert "kind: \"conflict\"" in js or 'kind: e.kind || "structure"' in js
    assert "function verifyBuild(" in js
    # 声称件核对：sanitize 静默清理后不能当成功
    assert "方案声称已装" in js
    # 优化器候选不许挑与已装件互斥的件
    assert "conflictsWith(ctx, id, ents[ei].id)" in js
    # 试装不许顺手拆掉受保护件
    assert "function evictsProtected(" in js


def test_known_incompatible_combo_is_rejected():
    """真实案例：Hera 一体化枪托 + Magpul UBR 独立枪托必须判为装配冲突。"""
    src = r'''
    const fs=require('fs');const GB=require('./gun_builder.js');
    const items=JSON.parse(fs.readFileSync('data/items.json','utf8')).items;
    const stats=JSON.parse(fs.readFileSync('data/gun-stats.json','utf8'));
    const presets=JSON.parse(fs.readFileSync('data/gun-presets.json','utf8')).presets;
    const ctx=GB.context(items,stats);
    const gid="%s";
    const p=Object.values(presets).filter(x=>x.g===gid)[0];
    const base=GB.sanitize(ctx,gid,p.i||{}).installed;
    const legacy={};
    Object.keys(base).forEach(k=>{ if(base[k] && !/^mod_stock(\/|$)/.test(k)) legacy[k]=base[k]; });
    legacy["mod_stock"]="%s";
    legacy["mod_pistol_grip"]="%s";
    const pairs=GB.conflictPairs(ctx,legacy);
    const v=GB.verifyBuild(ctx,gid,legacy,null,{ids:["%s","%s"]});
    const san=GB.sanitize(ctx,gid,legacy);
    console.log(JSON.stringify({
      pairs:pairs.map(p=>({a:p.a,b:p.b,dirAtoB:p.dirAtoB,dirBtoA:p.dirBtoA})),
      verifyOk:v.ok,
      kinds:v.problems.map(p=>p.kind),
      whys:v.problems.map(p=>p.why),
      sanitizedHasBoth: !!(san.installed["mod_stock"] && san.installed["mod_pistol_grip"])
    }));
    ''' % (M4A1, UBR, HERA, UBR, HERA)
    proc = _run_node(["-e", src], timeout=120)
    assert proc.returncode == 0, proc.stderr[:800]
    d = json.loads(proc.stdout)
    assert d["pairs"], "Hera 与 UBR 必须被识别为互斥"
    assert d["pairs"][0]["dirAtoB"] or d["pairs"][0]["dirBtoA"]
    assert d["verifyOk"] is False
    assert "conflict" in d["kinds"], "verifyBuild 必须给出 conflict 违规：%s" % d["kinds"]
    assert any("互斥" in w for w in d["whys"])
    assert d["sanitizedHasBoth"] is False, "sanitize 只清掉冲突的一方，不允许两件共存"


def test_optimizer_outputs_are_structurally_valid():
    """优化器输出的每个方案都要过整树校验：结构 + 双向互斥 + 声称件在位。"""
    proc = _run_node([NODE_TOOL, "final"], timeout=600)
    assert proc.returncode == 0, proc.stderr[:800]
    with open(os.path.join(AUDIT, "optimizer-final-validation.json"), encoding="utf-8") as f:
        d = json.load(f)
    pure = d["structuralOnly"]
    assert pure["total"] > 200
    assert pure["ok"] == pure["total"], "存在结构/互斥不合法的方案：%s" % pure["badSamples"][:2]
    # 带约束一轮：notOk 的原因必须是用户约束未满足（例如装不上瞄具），不能是结构问题
    kinds = d["withConstraints"]["problemKinds"]
    assert set(kinds) <= {"scope", "required", "excluded", "caps", "scopeId", "deviceId",
                          "feature", "missing"}, kinds
    assert "conflict" not in kinds and "structure" not in kinds


def test_no_solution_is_explicit_and_stays_invalid():
    """无解案例：必须全部判无效 + 可读原因；不能退回 30 发 / 换型号。"""
    proc = _run_node([NODE_TOOL, "nosolution"], timeout=300)
    assert proc.returncode == 0, proc.stderr[:800]
    with open(os.path.join(AUDIT, "optimizer-no-solution.json"), encoding="utf-8") as f:
        d = json.load(f)
    cases = {c["case"]: c for c in d["cases"]}
    ak = cases["容量约束无解"]
    assert ak["allInvalid"] and ak["builds"]
    assert "没有满足 100 发容量约束" in ak["firstReason"]
    assert all(b["ok"] is False for b in ak["builds"])
    dev = cases["必装型号不兼容"]
    assert dev["allInvalid"]
    assert any("未装入方案" in (b["why"] or "") for b in dev["builds"])
    pistol = cases["手枪无 100 发弹匣"]
    assert pistol["allInvalid"]


def test_apply_entry_uses_same_verification():
    """方案应用入口必须先整树终检，且被兼容链改动过的方案不得静默应用。"""
    js = _read(APP)
    assert "window.GB.verifyBuild(ctx, g.gunId, res.installed, cons" in js
    assert "方案终检未通过" in js
    assert "方案无法原样应用" in js
    # 应用只在验证通过后才写装配（顺序：verify → dropped 检查 → g.installed）
    i_verify = js.index("window.GB.verifyBuild(ctx, g.gunId, res.installed, cons")
    i_assign = js.index("g.installed = res.installed;", i_verify)
    assert i_verify < i_assign


# ---------------------------------------------------------------- 2. 固定 6×9 画布
def test_fixed_grid_constants_and_anchor_map():
    js = _read(APP)
    eng = js[js.index("var GW_GRID_ROWS = 6"):js.index("function renderGunTree() {")]
    assert "GW_GRID_ROWS = 6" in eng and "GW_GRID_COLS = 9" in eng
    for frag in ('body:      { row: 3, col: 6, span: 3 }',
                 'stock:     { row: 3, col: 9 }',
                 'mag:       { row: 4, col: 7 }',
                 'grip:      { row: 4, col: 8 }',
                 'ammo:      { row: 5, col: 7 }',
                 'charge:    { row: 2, col: 9 }'):
        assert frag in eng, frag
    assert 'if (hasBarrel) { return { muzzle: 1, gas_block: 2, barrel: 3, handguard: 4, receiver: 5 }; }' in eng
    assert 'return { muzzle: 2, gas_block: 3, barrel: 0, handguard: 4, receiver: 5 };' in eng
    css = _read(CSS)
    # R19.14：6 行固定，且空行有非零最小高度（禁止 minmax(0, auto) 塌缩）
    assert "repeat(var(--gw-rows, 6), minmax(var(--gw-row-min" in css
    assert "minmax(0, auto))" not in css.split(".gun-workbench .gw-canvas.gw-grid")[1].split("}")[0]
    assert "repeat(var(--gw-cols, 9), minmax(0, 1fr))" in css


@pytest.mark.skipif(shutil.which("node") is None, reason="需要 node")
def test_fixed_grid_invariants_on_all_guns():
    proc = _run_node([LAYOUT_TOOL], timeout=600)
    assert proc.returncode == 0, proc.stderr[:800]
    d = json.loads(proc.stdout)
    assert d["summary"]["guns"] >= 150
    assert not d["summary"]["problems"], d["summary"]["problems"][:3]
    assert d["summary"]["overflow"] == 0
    fg = d["summary"]["foregrip"]
    assert fg["guns"] >= 50 and fg["direct"] >= 30 and fg["viaRail"] >= 5
    assert not fg["offParent"]


@pytest.mark.skipif(shutil.which("node") is None, reason="需要 node")
def test_layout_cases_file_matches_fixed_grid():
    p = os.path.join(AUDIT, "layout-cases.json")
    if not os.path.exists(p):
        pytest.skip("layout-cases.json 尚未生成（先跑 tools/r1912_accept.py）")
    with open(p, encoding="utf-8") as f:
        d = json.load(f)
    assert len(d["cases"]) >= 6
    for key, c in d["cases"].items():
        assert c["invariants"]["colsIs9"], key
        assert c["invariants"]["rowsIs6"], key
        assert c["invariants"]["noOverflow"], key
    # 无独立枪管槽的枪必须真的存在，且主体链整体左移
    integral = [c for c in d["cases"].values() if c["desc"] and "无独立枪管槽" in c["desc"]]
    assert integral and integral[0]["hasBarrel"] is False


# ---------------------------------------------------------------- 3. 默认弹药
def test_default_ammo_rule_prefers_fmj_then_median():
    src = r'''
    const fs=require('fs');
    const ammo=JSON.parse(fs.readFileSync('data/ammo.json','utf8')).ammo;
    const src=fs.readFileSync('app.js','utf8');
    const block=src.slice(src.indexOf('function gwDefaultAmmoRule('), src.indexOf('function defaultAmmoForGun('));
    const rule=new Function('list', block+'\nreturn gwDefaultAmmoRule(list);');
    const byCal={};
    ammo.forEach(a=>{(byCal[a.cal]=byCal[a.cal]||[]).push(a);});
    const m4=rule(byCal['Caliber556x45NATO']);
    const noFmj=rule([{id:'a',n:'普通弹 A',t:'bullet',pen:10,cal:'X'},
                      {id:'b',n:'普通弹 B',t:'bullet',pen:20,cal:'X'},
                      {id:'c',n:'普通弹 C',t:'bullet',pen:30,cal:'X'}]);
    const empty=rule([{id:'z',n:'信号弹',t:'bullet',pen:0,cal:'Y'}]);
    const notBullet=rule([{id:'g',n:'榴弹',t:'grenade',pen:40,cal:'Z'}]);
    console.log(JSON.stringify({m4, noFmj, empty, notBullet}));
    '''
    proc = _run_node(["-e", src], timeout=120)
    assert proc.returncode == 0, proc.stderr[:800]
    d = json.loads(proc.stdout)
    assert d["m4"]["mode"] == "fmj" and "FMJ" in d["m4"]["n"]
    assert d["m4"]["pen"] < d["m4"]["median"] + 5, "默认弹必须贴近中位数，不得默认最高穿深"
    assert d["noFmj"]["mode"] == "median" and d["noFmj"]["id"] == "b", "取穿深最接近中位数的普通弹"
    assert d["empty"]["id"] is None and "数据缺口" in d["empty"]["reason"]
    assert d["notBullet"]["id"] is None, "非弹头不得当默认弹"


@pytest.mark.skipif(shutil.which("node") is None, reason="需要 node")
def test_default_ammo_audit_covers_playable_guns():
    proc = _run_node([AMMO_TOOL], timeout=300)
    assert proc.returncode == 0, proc.stderr[:800]
    d = json.loads(proc.stdout)
    s = d["summary"]
    assert s["guns"] >= 150
    assert s["withAmmo"] >= 150, "绝大多数有弹药数据的枪都要有默认弹"
    assert s["fmjMode"] > 50
    # 五把指定枪必须有默认弹且真实兼容
    for name in ("柯尔特 M4A1", "SIG MCX SPEAR", "AK-74", "Glock 17"):
        recs = [g for g in d["guns"].values() if (g["name"] or "").startswith(name)]
        assert recs, name
        r = recs[0]
        assert r["defaultAmmoId"], name
        assert r["compatible"] is True, name
        assert r["mode"] in ("fmj", "median")
    # 无数据的枪必须写明缺口，不虚构
    assert all(x["gun"] for x in s["noData"])


# ---------------------------------------------------------------- 4. 动态外观
def test_appearance_is_driven_by_installed_and_cached():
    js = _read(APP)
    assert "function renderGunSkin(host)" in js
    assert "gwSkinSignature()" in js, "外观必须由真实装配签名驱动"
    assert "GW_SKIN_CACHE.sig === sig" in js
    assert 'host.querySelector(".gw-skin")' in js, "DOM 重建后必须重绘"
    assert "GW_SKIN_ANCHOR" in js
    # 只读装配，不改状态
    body = js[js.index("function renderGunSkin(host)"):js.index("function nodeLabelOf(")]
    assert not re.search(r"g\.installed\[[^\]]+\]\s*=", body), "外观渲染不得写装配状态"
    assert "setGearIcon(img, L.id)" in body
    css = _read(CSS)
    assert ".gw-skin" in css and "pointer-events: none" in css


def test_appearance_audit_and_runtime_states():
    assets = os.path.join(AUDIT, "appearance-assets.json")
    if not os.path.exists(assets):
        pytest.skip("appearance-assets.json 尚未生成")
    with open(assets, encoding="utf-8") as f:
        a = json.load(f)
    assert a["三维资源"]["modelCount"] == 0, "本地确实没有 3D 模型，报告不得虚报 3D"
    assert a["整枪渲染"]["guns-full"]["count"] >= 100
    assert a["配件图层资源"]["icons-transparent"]["count"] >= 1000
    p = os.path.join(AUDIT, "appearance-tests.json")
    if not os.path.exists(p):
        pytest.skip("appearance-tests.json 尚未生成")
    with open(p, encoding="utf-8") as f:
        t = json.load(f)
    s = t["states"]
    assert s["default"]["count"] >= 8
    assert s["removedMuzzle"]["count"] == s["default"]["count"] - 1, "卸件后图层必须减少"
    dt = [x["title"] for x in s["default"]["layers"] if x["base"] == "muzzle"]
    ct = [x["title"] for x in s["changedMuzzle"]["layers"] if x["base"] == "muzzle"]
    assert dt and ct and dt != ct, "换件后枪口图层必须换掉"


# ---------------------------------------------------------------- 5. R19.11 回归锚点
def test_r1911_anchors_still_present():
    js = _read(APP)
    # 100 发硬约束
    assert "function enforceMagCapacity(" in open(ENGINE, encoding="utf-8").read()
    eng_js = open(ENGINE, encoding="utf-8").read()
    assert "capsOk" in eng_js and "没有满足当前约束的可行方案" in js
    # 个人属性
    assert "function gwProfileSave(" in js and "eftmap.profile.v1" in js
    assert 'id="btn-profile"' in _read(HTML)
    # 属性条三值
    for lab in ('"基线 "', '"改装 "', '"技能 "'):
        assert lab in js
    assert "solid-" in js and "stripe-" in js
    # 右栏红斜纹 + 隐藏不兼容
    assert "gw-hidebad" in _read(HTML)
    css = _read(CSS)
    assert "repeating-linear-gradient(45deg" in css
    assert ".tbl-row.tbl-conflict::after" in css
    # SPEAR 模拟器弹匣同源
    assert "function gunMagIds(" in js
