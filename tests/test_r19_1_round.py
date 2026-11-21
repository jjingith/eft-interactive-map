# -*- coding: utf-8 -*-
"""R19.1 回归测试：按参考截图重构配枪页布局 + 四视图 / 筛选 / FORGE UI / 弹药联动。"""
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "app.js")
HTML = os.path.join(ROOT, "index.html")
CSS = os.path.join(ROOT, "style.css")
GB = os.path.join(ROOT, "gun_builder.js")
STATS = os.path.join(ROOT, "data", "gun-stats.json")


def _read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def test_gun_view_has_four_view_modes():
    """对照参考站 Caliber / Class / Table / Gun 四个视图页签。"""
    html = _read(HTML)
    for mode in ("caliber", "class", "table", "build"):
        assert ('data-gwmode="%s"' % mode) in html, "缺视图页签 %s" % mode
    assert 'id="gw-browsepage"' in html and 'id="gw-tablepage"' in html \
        and 'id="gw-buildpage"' in html


def test_filter_chips_present_with_data_gap_flagged():
    """主武器/手枪 + Auto/Single/Burst 有数据；R264 起 Silent/Loud 已按用户要求移除。"""
    html = _read(HTML)
    for f in ("fullauto", "single", "burst"):
        assert ('data-gwfire="%s"' % f) in html
    for f in ("silent", "loud"):
        assert ('data-gwfire="%s"' % f) not in html, "%s 芯片已移除（R264）" % f


def test_workbench_three_columns_layout():
    """工作台 = 左 FORGE / 中装配 / 右候选（对照参考站 Gun 视图）。"""
    html = _read(HTML)
    assert 'id="gw-forge"' in html
    assert 'id="gw-cand-search"' in html, "候选面板要有自己的搜索框（对照参考站 Type to search）"
    assert 'id="gw-bars"' in html, "属性条（基线括号）容器"
    assert 'id="gw-meta"' in html, "R19.7：画布上方的枪械信息条（基础枪械 / 改装槽位 / 已装配件）"
    assert 'id="gw-ammo"' not in html, "R19.7：画布下方独立的弹药卡已删除，弹药改由子弹格驱动"
    assert 'id="gw-bottom"' in html, "底部 Final Cost + 时间线容器"
    css = _read(CSS)
    m = re.search(r"\.gun-workbench \.gw-buildpage\s*\{[^}]*grid-template-columns:\s*"
                  r"minmax\(216px,\s*246px\)\s+minmax\(0,\s*1fr\)\s+minmax\(292px,\s*32%\)", css)
    assert m, "gw-buildpage 必须是三栏网格（左 FORGE / 中装配 / 右候选）"


def test_candidate_columns_match_reference_order():
    """候选表列序对照参考站：配件 │ 人机(Ergo) │ 尺寸(无数据→子槽) │ 重量(Kg) │ 价格。

    列配置在 R19.28 改为按候选行组装（gunColumns(rows)，缺失属性整列隐藏），
    标签也随界面本地化为中文；这里按当前列常量与 cols 组装顺序校验同一列序契约。
    """
    js = _read(APP)
    m = re.search(r"function gunColumns\(\w*\)\s*\{", js)
    assert m, "找不到 gunColumns"
    start = js.index("{", m.start())
    depth = 0
    end = len(js)
    for i in range(start, len(js)):
        if js[i] == "{":
            depth += 1
        elif js[i] == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    body = js[start:end]
    labels = re.findall(r'label:\s*"([^"]+)"', body)
    assert labels[0] == "配件"
    assert "人机" in labels and "重量" in labels and "子槽" in labels
    seq = body[body.index("var cols = [COL_N]"):]
    assert seq.index("COL_ERGO") < seq.index("COL_W"), \
        "人机（Ergo）应在重量（Kg）之前（对照参考站列序）"
    assert "占格尺寸" in body, "Size 缺数据必须注明，不能编造"


def test_browse_cards_have_version_preset_and_short_name():
    """R19.95：枪卡结构对照截图：版本角标 + 预设数 + 缩写名 + 射速/发射模式 + 空枪重。"""
    js = _read(APP)
    for cls in ("gw-card-ver", "gw-card-presets", "gw-card-short",
                "gw-card-rpm", "gw-card-fire", "gw-card-wt"):
        assert 'className = "%s"' % cls in js, "枪卡缺结构 %s" % cls
    assert "GW_GUN_ADDED" in js, "左上角版本角标数据源"
    assert "gwGunDefaultWeight" in js, "右下角默认预设空枪重"
    assert "gwFireModeIcon" in js, "左下角发射模式图标"
    assert "gwFilteredGuns" in js and "gunClassOf" in js


def test_fire_mode_data_extracted():
    """gun-stats.json 必须带 fireModes（浏览页 Auto/Single/Burst 筛选的数据源）。"""
    data = json.load(open(STATS, encoding="utf-8"))
    guns = data["guns"]
    with_fm = sum(1 for g in guns.values() if g.get("fm"))
    assert with_fm > 80, "fireModes 覆盖过少：%d" % with_fm
    ak = guns["5bf3e03b0db834001d2c4a9c"]
    assert "fullauto" in ak["fm"] and "single" in ak["fm"]


def test_ammo_selection_feeds_velocity():
    """弹药联动：gunCompute 注入 opts.ammo；无弹药时初速 missing 不按 0。"""
    js = _read(APP)
    assert "o.ammo = state.ammo.byId[sel]" in js, "gunCompute 必须把选中的弹药传给 GB.compute"
    gb = _read(GB)
    assert "需要先选中弹药" in gb, "无弹药时初速必须标 missing"


def test_forge_ui_wired_to_engine():
    """FORGE 面板必须真正调用 GB.optimize 并能应用结果，不是空壳按钮。"""
    js = _read(APP)
    assert "window.GB.optimize(ctx, g.gunId" in js
    assert "GENERATE BUILDS" in js
    assert "window.GB.sanitize(ctx, g.gunId, inst)" in js, "应用方案前必须过兼容校验"


def test_bottom_timeline_with_default_marker():
    """底部改装时间线：配件名 + ergo/后坐差值 + default 标记（对照参考站）。"""
    js = _read(APP)
    assert 'gw-tl-default' in js and "default" in js


def test_layout_comparison_evidence_exists():
    """必须有参考/本地对照截图与验收数据。"""
    cmp_dir = os.path.join(ROOT, "docs", "r19-gun-builder", "layout-comparison")
    shots = [f for f in os.listdir(cmp_dir) if f.endswith(".png")]
    assert len(shots) >= 3, "layout-comparison 至少 3 张对照图，现有 %d" % len(shots)
    acc = os.path.join(ROOT, "docs", "r19-gun-builder", "_accept.json")
    data = json.load(open(acc, encoding="utf-8"))
    assert data.get("modeAfterPick") == "build"
    assert data.get("external") == [], "运行期不允许外部请求"
