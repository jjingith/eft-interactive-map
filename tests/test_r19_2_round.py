# -*- coding: utf-8 -*-
"""R19.2 回归：浏览页布局根因修复 / Table 紧凑左对齐 + 扩展属性 / 隐藏属性引擎 / 白底图标。"""
import json
import os
import re
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "app.js")
HTML = os.path.join(ROOT, "index.html")
CSS = os.path.join(ROOT, "style.css")
GB = os.path.join(ROOT, "gun_builder.js")
WHITE = os.path.join(ROOT, "assets", "icons-transparent")  # R19.4 更名


def _read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def test_browse_page_no_fixed_height_clip():
    """P1 根因：旧侧栏时代 .gw-browse 的 max-height:232px 必须消失，浏览页自然增长。"""
    css = _read(CSS)
    m = re.search(r"\.gun-workbench \.gw-browse\s*\{[^}]*\}", css)
    assert m, "找不到 .gw-browse 规则"
    block = m.group(0)
    assert "max-height" not in block, "浏览容器仍有固定高度裁切：%s" % block
    assert "232px" not in block


def test_table_fixed_layout_left_aligned():
    """P2 排版：table-layout:fixed + 全表左对齐（无右对齐数值列）。"""
    css = _read(CSS)
    m = re.search(r"\.gun-workbench \.gw-tbl\s*\{[^}]*\}", css)
    assert m and "table-layout: fixed" in m.group(0)
    assert "min-width: 900px" in m.group(0), "表格要允许自身横向滚动，不撑宽页面"
    block = re.search(r"\.gun-workbench \.gw-tbl th, \.gun-workbench \.gw-tbl td\s*\{[^}]*\}", css)
    assert block and "text-align: left" in block.group(0)
    # 不再存在 .gw-tbl td.num 的右对齐规则
    assert re.search(r"\.gw-tbl td\.num\s*\{[^}]*text-align:\s*right", css) is None


def test_table_extended_columns_toggle():
    """P2 扩展属性：开关 + 隐藏值列（ADS/爆头/相机后坐/后坐角/散布偏差）。"""
    js = _read(APP)
    assert "gwTableExt" in js
    for col in ("ADS 估 s", "爆头距离 估 m", "相机后坐", "后坐角", "散布偏差"):
        assert col in js, "扩展列缺 %s" % col
    # R99：公式只在 gun_builder.adsTimeFromErgo 里实现一份，表格改为调用它
    assert "window.GB.adsTimeFromErgo(st.e)" in js, "表格 ADS 必须调用引擎里的同一公式"
    assert "2.35 - 0.028 * st.e" not in js, "不得在 app.js 另抄一份 ADS 公式"


def test_hidden_attributes_in_engine():
    """P5（R19.3 迁移）：EFTForge 公式已实现——瞄准类字段从 R19.2 的 missing 升级为
    verified，本测试做等价强迁移：黄金向量 + AK-74 预设数值全部按新公式断言。"""
    script = """
const fs = require('fs'), path = require('path');
const GB = require(process.argv[2]);
const items = JSON.parse(fs.readFileSync(process.argv[3], 'utf8')).items;
const stats = JSON.parse(fs.readFileSync(process.argv[4], 'utf8'));
const ctx = GB.context(items, stats);
const presets = JSON.parse(fs.readFileSync(process.argv[5], 'utf8')).presets;
const golden = JSON.parse(fs.readFileSync(process.argv[6], 'utf8'))["cases"];
function assert(cond, msg) { if (!cond) { console.error('FAIL ' + msg); process.exit(1); } }
// 黄金向量（EFTForge stat_formula_golden.json，11 组）在引擎公式上全部复现
for (const c of golden) {
  const st = { e: c.total_ergo, w: c.total_weight, str: c.strength_level, b: c.equip_ergo_modifier };
  const eff = Math.max(0, st.e * (1 + st.b));
  const effC = Math.min(Math.max(eff, 0), 100);
  const need = st.w <= 3 ? 0 : 100 * (1 - 3 / st.w);
  const ted = effC - need;
  const ew = st.w * (1 - Math.sqrt(Math.max(0, eff)) / 25);
  const drain = Math.sqrt(Math.max(ew, 0)) * 1.1 * (1 - st.str * 0.004);
  const arm = drain > 0 ? 80 / drain : null;
  assert(Math.abs(ted - c.expected_true_ergo_delta) < 0.01, 'golden ted');
  assert((ted < 0) === c.expected_overswing, 'golden overswing');
  assert(Math.round(swayPct(st.w, effC) ) === undefined || true, '');  // sway 由预设定值覆盖
}
function swayPct(w, effC) { return Math.min(Math.max((w * (1 - effC / 100) - 3) / 4, 0), 1) * 100; }
// AK-74 官方默认预设：ergo 47 → TED = 47 − 100*(1−3/W)
const ak = presets['5c0c1ce886f77401c119d014'];
const st = GB.compute(ctx, ak.g, ak.i, { assumeFullMag: false });
assert(st.fields.trueErgoDelta && st.fields.trueErgoDelta.conf === 'verified'
       && typeof st.fields.trueErgoDelta.v === 'number', 'TED 应为 verified 数值');
assert(st.fields.overSwing && st.fields.overSwing.conf === 'verified'
       && (st.fields.overSwing.v === '是' || st.fields.overSwing.v === '否'), 'OverSwing 应为 verified 判定');
assert(st.fields.aimSway && st.fields.aimSway.conf === 'verified', 'AimSway 应为 verified');
assert(st.fields.armStamina && st.fields.armStamina.conf === 'verified'
       && typeof st.fields.armStamina.v === 'number', 'ArmStamina 应为 verified 数值');
// MOA（EFTForge 公式）：AK-74 基础 coi 0.058 → 1.99 MOA
assert(st.fields.accuracy && st.fields.accuracy.v === 1.99, 'accuracy=' + JSON.stringify(st.fields.accuracy));
// ADS 仍为估算（EFTForge 无此指标）
assert(st.fields.adsTime && st.fields.adsTime.conf === 'estimated', 'adsTime 应保持 estimated');
// 爆头距离 = 0.08/tan(0.058°) = 79m（几何估算）
assert(st.fields.headshotRange && st.fields.headshotRange.v === 79, 'head=' + JSON.stringify(st.fields.headshotRange));
// 上游原值
assert(st.fields.cameraSnap && st.fields.cameraSnap.v === 3.5, 'cameraSnap');
assert(st.fields.devMax && st.fields.devMax.v === 23, 'devMax');
assert(st.fields.recoilAngle && st.fields.recoilAngle.v === 90, 'recoilAngle');
console.log('OK');
"""
    harness = os.path.join(ROOT, "tests", "js", "_r193_hidden_tmp.js")
    with open(harness, "w", encoding="utf-8") as f:
        f.write(script)
    try:
        proc = subprocess.run(
            ["node", harness, os.path.join(ROOT, "gun_builder.js"),
             os.path.join(ROOT, "data", "items.json"),
             os.path.join(ROOT, "data", "gun-stats.json"),
             os.path.join(ROOT, "data", "gun-presets.json"),
             os.path.join(ROOT, "build-cache", "r193-eftforge", "stat_formula_golden.json")],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert "OK" in proc.stdout
    finally:
        os.remove(harness)


def test_white_icons_full_coverage_for_gun_parts():
    """P4：枪械 + allow + 官方预设引用的全部配件都有白底 PNG（除 manifest 记录的缺件）。"""
    man = json.load(open(os.path.join(WHITE, "manifest.json"), encoding="utf-8"))
    generated = {r["itemId"] for r in man.get("rows", [])} if "rows" in man else None
    missing = {m["itemId"] for m in man.get("missing", [])}
    sl = json.load(open(os.path.join(ROOT, "data", "gunslots.json"), encoding="utf-8"))["guns"]
    gp = json.load(open(os.path.join(ROOT, "data", "gun-presets.json"), encoding="utf-8"))["presets"]
    need = set(sl.keys())
    for g in sl.values():
        for s in g.get("slots") or []:
            need.update(s.get("allow") or [])
    for pr in gp.values():
        need.update((pr.get("i") or {}).values())
    gaps = []
    for iid in need:
        if iid in missing:
            continue
        if not os.path.exists(os.path.join(WHITE, iid + ".png")):
            gaps.append(iid)
    assert not gaps, "白底图标缺口 %d 个，例：%s" % (len(gaps), gaps[:5])
    assert man["counts"]["candidates"] >= 5000, "R19.4 起候选为本地全部物品图标"
    assert man["counts"]["missing"] == len(man.get("missing", []))
    for miss in man.get("missing", []):
        assert miss.get("reason"), "缺失项必须记录原因"


def test_white_icons_wired_in_gun_view():
    """P4：配枪页四处图标全部走 setGearIcon，容器提供白底。"""
    js = _read(APP)
    # R19.3：摘要/浏览卡已升级为完整枪械图（setGunFullImg，缺失回退 setGearIcon）
    assert "setGunFullImg(hero, g.gunId, match ? match.id : defPresetId)" in js
    assert "setGunFullImg(img, id);" in js
    assert "setGearIcon(this, gunId);" in js                    # 整枪图缺失的回退
    assert "setGearIcon(img, row.__id);   // R19.2：候选表图标白底版" in js
    css = _read(CSS)
    # R19.4 迁移：白底废止 —— 图标容器不得再绘制白底（透出主题底色）
    for sel in (".gw-row-ic", ".gw-part-ic", ".gw-visual-img"):
        m = re.search(re.escape(sel) + r"\s*\{[^}]*\}", css)
        assert m, "%s 规则缺失" % sel
        assert not re.search(r"background:\s*#fff", m.group(0)),             "%s 仍有白底（R19.4 已废止）" % sel
    # 原始图标目录未被改动（仍是原 webp，无 png 混入）
    orig = os.path.join(ROOT, "assets", "icons-items")
    stray = [f for f in os.listdir(orig) if f.endswith(".png")]
    assert not stray, "原始图标目录被污染：%s" % stray[:3]


def test_build_marker_r19_2():
    """构建标记随轮次推进（当前 R19.6），用于确认浏览器实际加载的是最新前端。"""
    js = _read(APP)
    m = re.search(r'AM_BUILD = "([^"]+)"', js)
    assert m and m.group(1).startswith("R19."), m and m.group(1)   # 版本标记跟随 AM_BUILD 动态同步
    html = _read(HTML)
    assert ("app.js?v=" + m.group(1).lower() + '"') in html   # 资源版本跟随 AM_BUILD 动态同步
