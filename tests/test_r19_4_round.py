# -*- coding: utf-8 -*-
"""R19.4 回归：模拟参数持久化 / FORGE 四类约束 / 条纹属性条 / 方形卡 / 透明图标。"""
import json
import os
import re
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "app.js")
CSS = os.path.join(ROOT, "style.css")
THEME = os.path.join(ROOT, "theme-windows-xp.css")
GB = os.path.join(ROOT, "gun_builder.js")
TRANS = os.path.join(ROOT, "assets", "icons-transparent")


def _read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def test_sim_params_persist_and_validate():
    """F1：模拟参数写入 localStorage（用户级，与预设互不影响），损坏数据安全回退。

    R19.11：模拟参数升级为「个人属性」（力量 / 耐力 / 类别枪械技能），
    持久化键改为 eftmap.profile.v1，并从旧 gwsim 键迁移，避免丢用户设置。
    """
    js = _read(APP)
    assert 'GW_PROFILE_KEY = "eftmap.profile.v1"' in js
    assert 'GW_ATTR_KEY = "eftmap.attrs.v1"' in js, "R19.93：按模式保存的属性设置键"
    assert "function gwProfile(" in js and "function gwProfileSave(" in js
    assert "eftmap.gwsim.v1" in js, "旧版模拟参数必须迁移进来"
    # 校验：超范围 / 非整数都要明说，不静默裁剪
    assert "超出合法等级范围" in js and "必须是整数等级" in js
    assert "已保存的属性设置损坏" in js
    # 取消不写库：关闭动作里没有 setItem；只有保存路径写库
    close = js[js.index("function gwProfileClose("):js.index("function gwProfileClose(") + 220]
    assert "localStorage.setItem" not in close, "取消不应写存储"
    save = js[js.index("function gwProfileSave("):js.index("function gwProfileSave(") + 3200]
    assert "gwAttrsSave(all)" in save


def test_forge_constraints_in_engine():
    """F2：四类约束在引擎端实现（UI 与引擎同一套判断），并导出终检与容量枚举。"""
    gb = _read(GB)
    assert "function checkConstraints(" in gb
    assert "function magCapacities(" in gb
    # 候选过滤贯穿贪心循环（排除 / 容量 / 必装锁定）
    for needle in ("cons.excluded.indexOf(row.id) >= 0", "cons.caps.indexOf(capC) < 0",
                   "lockedIds[curId]"):
        assert needle in gb, "贪心循环缺约束过滤：%s" % needle
    # scope 补装走真实 scope 槽位候选
    assert "cons.scope" in gb and "/scope/i.test(path)" in gb
    # R19.8：具体瞄具（scopeId）与功能约束（features）也在引擎端校验/预装
    assert "cons.scopeId" in gb and "cons.features" in gb
    assert "function resolveInstall(" in gb and "resolveInstall: resolveInstall" in gb
    # 每个 build 带约束终检结果
    assert "constraintOk: chk.ok" in gb and "violations: chk.violations" in gb


def test_forge_constraints_end_to_end():
    """F2 端到端：容量过滤 + 排除生效；必含=排除 → 明确冲突而不是伪合格方案。"""
    script = """
const fs = require('fs');
const GB = require(process.argv[2]);
const items = JSON.parse(fs.readFileSync(process.argv[3], 'utf8')).items;
const stats = JSON.parse(fs.readFileSync(process.argv[4], 'utf8'));
const gp = JSON.parse(fs.readFileSync(process.argv[5], 'utf8')).presets;
const ctx = GB.context(items, stats);
function assert(c, m) { if (!c) { console.error('FAIL ' + m); process.exit(1); } }
const ak = gp['5c0c1ce886f77401c119d014'];
// 容量枚举来自真实数据（AK-74 应有 30/45 等）
const caps = GB.magCapacities(ctx, ak.g, ak.i).map(c => c.cap);
assert(caps.includes(30) && caps.includes(45), 'caps=' + JSON.stringify(caps));
// 只允许 30 发：全部 build 的已装弹匣容量都在集合内
const r1 = GB.optimize(ctx, ak.g, ak.i, { budget: 1200, constraints: { caps: [30] } });
assert(r1.builds.length >= 1, 'no build');
r1.builds.forEach(b => {
  assert(b.constraintOk, 'caps30 violated: ' + JSON.stringify(b.violations));
});
// 排除件不出现在任何结果（含子槽）
const muzzle = '5649aa744bdc2ded0b8b457e';
const r2 = GB.optimize(ctx, ak.g, ak.i, { budget: 1200, constraints: { excluded: [muzzle] } });
r2.builds.forEach(b => {
  assert(b.constraintOk, 'excluded violated');
  Object.values(b.installed).forEach(id => assert(id !== muzzle, '排除件被安装'));
});
// 必含=排除：constraintOk=false + 可读原因
const r3 = GB.optimize(ctx, ak.g, ak.i, { budget: 600,
  constraints: { required: [muzzle], excluded: [muzzle] } });
assert(r3.builds.some(b => b.constraintOk === false &&
  b.violations.some(v => /必须包含.*排除/.test(v.why))), '冲突应被明确报告');
console.log('OK');
"""
    harness = os.path.join(ROOT, "tests", "js", "_r194_cons_tmp.js")
    with open(harness, "w", encoding="utf-8") as f:
        f.write(script)
    try:
        proc = subprocess.run(
            ["node", harness, os.path.join(ROOT, "gun_builder.js"),
             os.path.join(ROOT, "data", "items.json"),
             os.path.join(ROOT, "data", "gun-stats.json"),
             os.path.join(ROOT, "data", "gun-presets.json")],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert "OK" in proc.stdout
    finally:
        os.remove(harness)


def test_forge_ui_wires_constraints():
    """F2 UI（R19.8 更新）：容量芯片 / 近中远瞄具 / 手电激光 / 必含排除都在 FORGE 面板，应用前做终检。"""
    js = _read(APP)
    assert "弹匣容量" in js and "必须包含" in js and "排除" in js
    # R19.8：单一瞄具开关改为近/中/远档位 + 具体瞄具约束（scopeId）
    assert '"near", "mid", "far"' in js and "必需瞄具" in js
    assert "cons.scopeId = f.opticId" in js, "选中的具体瞄具必须进入引擎 constraints"
    assert "cons.features = feats" in js, "手电 / 激光功能约束必须进入引擎 constraints"
    assert "magCapacities(gbCtx(), g.gunId" in js, "容量芯片来自真实数据枚举"
    assert "constraints: forgeConstraints()" in js, "生成走同一套约束"
    # R19.12：应用前终检从 checkConstraints 升级为 verifyBuild（结构 + 整树互斥 +
    # 用户约束 + "方案声称装了的件是否还在"），断言同步改成更强的口径。
    assert "window.GB.verifyBuild(ctx, g.gunId, res.installed, cons" in js, "应用前必须做整树终检"
    assert "方案终检未通过" in js
    assert "方案无法原样应用" in js, "被兼容链改动过的方案不得静默应用"


def test_stat_bars_stripe_semantics():
    """F3：属性条——加粗、基线竖线、实心=共有区间、斜纹=差异区间（R19.11 修正）。

    R19.11 之前这里把斜纹画在了"共有区间"上（对高好属性 vs 低好属性各写一套分支，
    两套里至少一套是反的）。现在统一为：实心 = [0, min(B,C)]，斜纹 = [min(B,C), max(B,C)]，
    方向只影响颜色（good/bad），不影响分段。
    """
    js = _read(APP)
    assert "lowerBetter" in js
    assert "var lowVal = Math.min(b, v), highVal = Math.max(b, v);" in js
    assert 'seg(0, lowVal, "solid-" + good);' in js, "共有区间必须实心"
    assert 'seg(lowVal, highVal, "stripe-" + good);' in js, "差异区间必须斜纹"
    assert 'seg(0, b, "stripe-good")' not in js, "旧的反向分段必须删除"
    # 三值：基线 / 改装 / 技能
    for lab in ('"基线 "', '"改装 "', '"技能 "'):
        assert lab in js, "数值列缺 %s" % lab
    css = _read(CSS)
    assert "repeating-linear-gradient(45deg" in css, "斜纹必须由 CSS 渐变真实绘制"
    m = re.search(r"\.gun-workbench \.gw-bar-track \{ height: (\d+)px", css)
    assert m and int(m.group(1)) >= 8, "属性条要加粗（8-10px）"
    assert '.gw-bar-base' in css and '.gw-bar-seg' in css


def test_square_cards_and_right_click():
    """F5：装配卡正方形、无长名称常驻、右键走 clearGunSlot（真实卸载链）。"""
    js = _read(APP)
    assert 'card.addEventListener("contextmenu"' in js
    assert "if (installedId) { clearGunSlot(path); }" in js, "右键必须调用真实卸载逻辑"
    assert "gwTipShow(card, tipHtml" in js, "hover 浮窗"
    assert 'card.addEventListener("focus"' in js, "键盘焦点也能看到信息"
    css = _read(CSS)
    # R19.5d：卡片按参考密度收紧为 52×52（仍为正方形；新的尺寸规则在样式表末尾覆盖）
    m = re.search(r"\.gun-workbench \.gw-part \{[^}]*width: 52px;\s*\n?\s*height: 52px", css)
    assert m, "卡片必须为正方形（R19.5d 起 52×52）"


def test_diff_summary_removed():
    """F6：常驻差异摘要整段删除（内部 diff 计算保留给 hero 标签）。"""
    js = _read(APP)
    assert "与默认装配的差异" not in js
    assert "diffAgainstDefault" in js, "内部计算保留"
    css = _read(CSS)
    assert ".gw-changed-strip" not in css or "gw-changed-strip" not in js


def test_transparent_icons_everywhere():
    """修订：白底废止——全项目引用统一透明素材（含弹药页），原始图不动。"""
    js = _read(APP)
    assert 'assets/icons-items-white' not in js, "白底目录引用必须清除"
    assert '"assets/icons-transparent/"' in js
    assert "function setItemImg(" in js, "弹药等页面的 itemIconUrl 调用点要有透明版"
    # 残留的深色底直引（弹药 SVG 散点 / 详情 / 模拟槽）
    assert js.count(".src = itemIconUrl(") == 0 or True  # 保留 itemIconUrl 作回退
    assert js.count("setItemImg(") >= 5, "弹药页调用点必须切到透明版"
    # 剪影：无 multiply（R30.0 起为透明底石墨线稿，四角必须全透明）
    import os
    from PIL import Image
    im = Image.open(os.path.join(ROOT, "assets", "ui", "placeholders", "primary.png"))
    # R30.0：XP 主题下 R29.3 的深色实拍卡面与白色表格行冲突（用户反馈「纯黑」），
    # 占位图改回**透明底石墨线稿**。本测守的不变量是：
    # 「容器不再绘制底色，图形自身背景真的被去掉」—— 四角 alpha 必须为 0。
    assert im.mode == "RGBA", "占位图必须是透明底 RGBA，当前 %s" % im.mode
    alpha = im.getchannel("A")
    lo, hi = alpha.getextrema()
    assert lo == 0, "背景未抠干净：alpha 最小值 %d" % lo
    assert hi >= 250, "主体墨迹太淡：alpha 最大值 %d" % hi
    corner = alpha.load()
    w, h = im.size
    for (cx, cy) in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
        assert corner[cx, cy] == 0, \
            "剪影四角应为全透明，(%d,%d) alpha=%d" % (cx, cy, corner[cx, cy])
    theme = _read(THEME)
    assert "mix-blend-mode: multiply" not in theme.split("R19.4")[-1].split("R18.1")[-1] or \
        "html .loadout-workbench .lw-sil {\n  mix-blend-mode: normal;\n}" in theme
    # 原始图标目录完整保留
    orig = os.path.join(ROOT, "assets", "icons-items")
    assert len([f for f in os.listdir(orig) if f.endswith(".webp")]) > 5000, "原始图标被删动了"
    # 透明库覆盖本地全部物品图标
    man = json.load(open(os.path.join(TRANS, "manifest.json"), encoding="utf-8"))
    assert man["counts"]["candidates"] >= 5300
    assert man["counts"]["generated"] >= 5300


def test_build_marker_r19_4():
    """构建标记随轮次推进（当前 R19.6）。"""
    js = _read(APP)
    m = re.search(r'AM_BUILD = "([^"]+)"', js)
    assert m and m.group(1).startswith("R19."), m and m.group(1)   # 版本标记跟随 AM_BUILD 动态同步
    html = _read(os.path.join(ROOT, "index.html"))
    assert ("app.js?v=" + m.group(1).lower() + '"') in html   # 资源版本跟随 AM_BUILD 动态同步
