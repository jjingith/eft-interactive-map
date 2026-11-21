# -*- coding: utf-8 -*-
"""R19.3 回归：整枪图 / 选中黄色 / 文字对比度 / EFTForge 公式接入。"""
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "app.js")
CSS = os.path.join(ROOT, "style.css")
THEME = os.path.join(ROOT, "theme-windows-xp.css")
GB = os.path.join(ROOT, "gun_builder.js")
GUNIMG = os.path.join(ROOT, "assets", "guns-full")


def _read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def test_full_gun_images_manifest_coverage():
    """P1：163 把枪里 161 把有整枪渲染；缺失的只有已知的 2 件上游 404。"""
    man = json.load(open(os.path.join(GUNIMG, "manifest.json"), encoding="utf-8"))
    sl = json.load(open(os.path.join(ROOT, "data", "gunslots.json"), encoding="utf-8"))["guns"]
    have = {r["gunId"] for r in man["items"]}
    missing = sorted(set(sl.keys()) - have)
    known_404 = {"6a15ae2ae5267ba21c07f98f", "6a78b7f8c2016eb33e0027cd"}
    assert set(missing) <= known_404, "整枪图缺口超出已知 404：%s" % missing
    assert man["counts"]["withDefaultPreset"] == 163
    # manifest 记录 gun→preset 映射与来源（可审计）
    r0 = man["items"][0]
    for key in ("gunId", "presetId", "source", "size"):
        assert key in r0


def test_browse_cards_use_full_gun_images():
    """P1：浏览卡走 setGunFullImg（预设整枪渲染，缺失回退白底图标）。"""
    js = _read(APP)
    assert 'img.src = presetId' in js and "assets/presets-full/" in js
    assert "assets/guns-full/" in js
    assert "setGunFullImg(img, id);" in js, "浏览卡未接整枪图"
    # 原始物品图目录未被污染
    stray = [f for f in os.listdir(os.path.join(ROOT, "assets", "icons-items"))
             if f.endswith(".png")]
    assert not stray


def test_selected_card_stays_yellow():
    """P2：选中卡是黄色底 + 深色字，且 .gw-card 已从 XP 按钮皮肤排除。"""
    theme = _read(THEME)
    assert "html .gun-workbench .gw-card[aria-current=\"true\"]," in theme
    assert "background: #ffe9a8;" in theme, "选中卡必须黄色（非深色回退）"
    # 结构性修复：三段按钮皮肤都排除了 .gw-card
    assert theme.count("button:not(.gw-hit):not(.gw-card)") == 3, \
        "卡片必须从 XP 按钮皮肤排除（否则悬停/选中被渐变接管）"
    assert "html .gun-workbench .gw-card:hover" in theme
    assert "html .gun-workbench .gw-card:focus-visible" in theme


def test_workbench_text_contrast_rules():
    """P3：审计发现的 6 处低对比全部有主题级深色修复（限 gun-workbench 作用域）。"""
    theme = _read(THEME)
    for sel in (".gw-visual-name", ".gw-current", ".gw-chip b", ".lw-focus-title"):
        assert re.search(r"html \.gun-workbench %s\s*\{[^}]*color:\s*#000000" %
                         re.escape(sel), theme), "%s 缺深色修复" % sel
    assert "html .gun-workbench .gw-finalcost" in theme


def test_forge_formulas_wired():
    """P5：EFTForge 公式在引擎里（常量与结构），模拟参数显式传入。"""
    gb = _read(GB)
    assert "100 / 2.9089" in gb, "MOA 换算常量"
    assert "100 * (1 - 3 / wNow)" in gb, "过摆阈值 ergoNeeded"
    assert "1.1 * (1 - STR * 0.004)" in gb, "ArmStamina 耐力系数"
    assert gb.count('conf: CONF.E') >= 2 and '官方客户端公式不可得' in gb, \
        'ADS 必须保持 estimated 标注（检索结论写进 why）'
    js = _read(APP)
    assert "strengthLevel" in js and "equipErgoModifier" in js, "模拟参数必须显式"
    assert "gwSimParams" in js


def test_center_hero_reflects_assembly():
    """P4：主图两态（官方预设精确匹配 / 基准+改动标签）。
    R19.4：常驻差异摘要条已按任务删除，内部 diff 计算保留（hero 标签仍用）。"""
    js = _read(APP)
    assert "matchingOfficialPreset" in js
    assert "diffAgainstDefault" in js            # 内部计算保留
    assert "与默认装配的差异" not in js           # 常驻摘要已删除


def test_build_marker_r19_3():
    """构建标记随轮次推进（当前 R19.6）。"""
    js = _read(APP)
    m = re.search(r'AM_BUILD = "([^"]+)"', js)
    assert m and m.group(1).startswith("R19."), m and m.group(1)   # 版本标记跟随 AM_BUILD 动态同步
    html = _read(os.path.join(ROOT, "index.html"))
    assert ("app.js?v=" + m.group(1).lower() + '"') in html   # 资源版本跟随 AM_BUILD 动态同步
