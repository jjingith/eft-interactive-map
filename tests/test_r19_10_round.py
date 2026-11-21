# -*- coding: utf-8 -*-
"""R19.10 回归：FORGE 选择器三态 / 已选黄色高亮 / 具体型号约束 / 前握把父子布局。

对应任务书：
1. 瞄具：点档位展开 → 选型号收起只剩一款 → 再点档位重新展开 → 换型号 → 清除；
2. 手电 / 激光：统一「手电 | 激光 | 清除」三个按钮，选定后同样收起，两者互不覆盖；
3. 已选型号行必须是黄色（悬停同款），不得再用深色 --lw-select 回退值（"变黑"根因）；
4. 前握把直接安装在父件正下方、同列；只有真实转接皮轨才允许特殊排列；
5. 选定型号（scopeId / deviceIds）必须真的装进优化方案，装不上要明说而不是偷偷换型号。

前三条是"文件里必须长成这样"的静态约束；后两条用 node 把
`gwBuildLayout()` 与 `GB.optimize()` 抠出来在**真实槽位树 / 真实预设**上跑一遍。
不联网；缺 node 时动态用例自动跳过。
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
APP_JS = ROOT / "app.js"
THEME_CSS = ROOT / "theme-windows-xp.css"
INDEX_HTML = ROOT / "index.html"
BUILDER_JS = ROOT / "gun_builder.js"
LAYOUT_TOOL = ROOT / "tools" / "r1912_layout.js"   # R19.12：固定 6×9 网格探针
ENGINE_TOOL = ROOT / "tools" / "r1910_engine.js"

AK74 = "5bf3e03b0db834001d2c4a9c"
HK416 = "5bb2475ed4351e00853264e3"
ARMYTEK = "59d790f486f77403cb06aec6"     # 手电（需转接座）
GTL21 = "5a800961159bd4315e3a1657"       # 手电 + 激光双功能
BURRIS = "5b2388675acfc4771e1be0be"      # 1–4× 中档瞄具


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _fn(js: str, name: str) -> str:
    i = js.find("function %s(" % name)
    assert i >= 0, "找不到函数 %s" % name
    depth, j = 0, js.index("{", i)
    while j < len(js):
        if js[j] == "{":
            depth += 1
        elif js[j] == "}":
            depth -= 1
            if depth == 0:
                return js[i:j + 1]
        j += 1
    return js[i:]


# ---------------------------------------------------------------- 1. FORGE 三态
def test_forge_optic_selection_collapses_to_one_row():
    """选中具体瞄具后，候选列表必须收起，只留被选中的那一款。"""
    forge = _fn(_read(APP_JS), "renderGunForge")
    assert 'if (typeof f.opticOpen !== "boolean") { f.opticOpen = false; }' in forge, \
        "展开状态必须是显式状态（不能靠 hover 之类的假象）"
    # 展开态：整档候选
    assert "} else if (f.opticOpen) {" in forge and "optList.forEach(function (o) {" in forge
    assert "f.opticId = o.id;" in forge and "f.opticOpen = false;" in forge, \
        "点型号 = 写入真实 id 并收起列表"
    # 收起态：只有已选那一条
    assert "} else if (selOptic) {" in forge and "gw-forge-picked" in forge
    assert forge.count("optBox.appendChild") >= 2, "展开 / 收起两种形态都要真实渲染"
    # 再点档位可以重新展开；换档位清掉旧型号
    assert "f.opticOpen = !f.opticOpen;" in forge, "同一档位点击 = 展开 / 收起切换"
    assert "f.opticTier = tier;" in forge and "f.opticId = \"\";" in forge, "换档位清空具体型号"
    assert 'f.opticTier = ""; f.opticId = ""; f.opticOpen = false;' in forge, "清除要复原未选状态"


def test_forge_tactical_uses_three_buttons_and_collapses():
    """手电 / 激光改成「手电 | 激光 | 清除」三个按钮，选定后同样只显示所选型号。"""
    forge = _fn(_read(APP_JS), "renderGunForge")
    assert '[["light", "手电"], ["laser", "激光"]].forEach(function (pair) {' in forge
    assert 'f.devOpen = (f.devOpen === key) ? "" : key' in forge, "再点同一按钮可收起 / 展开"
    assert "f.devices[key] = id;" in forge and 'f.devOpen = "";' in forge, \
        "选定型号后写入真实 id 并收起列表"
    assert 'f.devices.light = ""' in forge and 'f.devices.laser = ""' in forge, \
        "「清除」取消两个型号约束"
    # 清除不得碰已装配件与预设（只改约束）
    clr = forge[forge.index('devClr.addEventListener("click"'):]
    clr = clr[:clr.index("});") + 3]
    for bad in ("g.installed", "persistGun", "clearGunSlot", "presetId"):
        assert bad not in clr, "清除型号约束不得动装配置：%s" % bad
    # 两个设备各自显示已选型号，互不覆盖
    assert 'host.dataset.dev = key;' in forge
    assert "f.devOpen === key" in forge and "f.devices[key]" in forge


def test_selected_models_are_revalidated_after_gun_change():
    """换枪后必须复核兼容性：兼容的保留、不兼容的清除并写明原因。"""
    forge = _fn(_read(APP_JS), "renderGunForge")
    val = _fn(forge, "forgeValidateSelections")
    assert "forgeTierOptics(f.opticTier).some" in val, "瞄具按新枪的真实兼容列表复核"
    assert "forgeDeviceCompatible(k).indexOf(id) < 0" in val, "设备按新枪的真实槽位复核"
    assert "原选中瞄具与当前枪械不兼容，已清除：" in val
    assert '原选中" + (k === "light" ? "手电" : "激光")' in val
    js = _read(APP_JS)
    sel = _fn(js, "selectGun")
    assert "g.forge.opticTier = \"\";" not in sel, "换枪不再无条件清空型号（改由兼容性复核）"
    assert "g.forge.opticOpen = false;" in sel and "g.forge.devOpen = \"\";" in sel


# ---------------------------------------------------------------- 2. 黄色选中态
def test_selected_row_yellow_beats_xp_button_skin():
    """已选型号必须黄色（与悬停同款），且优先级要压过 style.css 的深色回退值与 XP 按钮皮肤。"""
    theme = _read(THEME_CSS)
    assert 'button.gw-forge-poolrow[data-on="1"]' in theme, "选中态规则必须带元素名（提高优先级）"
    # 根因写清楚：--lw-select 在 .gun-workbench 上没有定义，回退成深色
    assert "--lw-select" in theme and "#2c3646" in theme
    block = theme[theme.index("R19.10：FORGE 型号选择器"):]
    sel = block[block.index('button.gw-forge-poolrow[data-on="1"]'):]
    sel = sel[:sel.index("}")]
    assert "#ffe9a8" in sel and "#c8832a" in sel, "选中 = 深黄底 + 橙边框"
    assert "color: #000000" in sel, "选中行文字必须是黑色（不能黑底黑字）"
    assert "font-weight: 700" in sel
    hover = block[block.index('button.gw-forge-poolrow:hover:not([disabled])'):]
    hover = hover[:hover.index("}")]
    assert "#fff3c4" in hover and "#e8a33d" in hover, "悬停 = 浅黄底 + 橙边框（选中沿用同色系）"
    # 优先级：选中规则 (0,5,2) 必须高于 XP 通用按钮皮肤 (0,3,2) 与 style.css 的 (0,4,0)
    rule = 'html .gun-workbench .gw-forge .gw-forge-opts button.gw-forge-poolrow'
    assert rule in theme
    classes = rule.count(".") + rule.count("[data-on")
    assert classes >= 4, "选择器至少 4 个类 + html/button 两个元素名，才能压过通用按钮皮肤"
    # 选中态还要压过 :hover / :active / :focus（鼠标移开不能变回灰）
    for state in (':hover:not([disabled])', ':active:not([disabled])', ":focus"):
        assert 'button.gw-forge-poolrow[data-on="1"]' + state in theme, "缺少 %s 的选中态" % state


def test_selected_row_uses_real_item_id_not_hover():
    """选中只能由真实物品 id 驱动：data-on 来自 f.opticId / f.devices[key]，不是 hover 类名。"""
    forge = _fn(_read(APP_JS), "renderGunForge")
    row = _fn(forge, "forgeModelRow")
    assert 'row.dataset.on = on ? "1" : "0";' in row
    assert 'row.setAttribute("aria-pressed", on ? "true" : "false");' in row
    assert "hover" not in row and "gw-forge-active" not in row, "不得借用鼠标 hover 状态伪造选中"
    assert "row.dataset.on = f.opticId === o.id ? \"1\" : \"0\";" not in forge
    assert "f.opticId === o.id" in forge, "瞄具行的选中来源是真实 id 比较"
    assert "f.devices[key] === id" in forge, "设备行的选中来源是真实 id 比较"


# ---------------------------------------------------------------- 3. 前握把布局
def test_foregrip_layout_rules_in_engine():
    """R19.12：前握把的父子位置约束在固定 6×9 网格里继续成立。

    判定仍然只看真实槽位树（node.parent），不看名称；父件是 mount 时
    data-parent 与连接线都指向皮轨。锚点列来自父件的最终格子。
    """
    js = _read(APP_JS)
    eng = _fn(js, "gwBuildLayout")
    assert 'gwSidBase(nodes[c.path].sid) === "foregrip"' in eng, "前握把按槽位基名识别"
    assert "var par = nodes[c.path].parent;" in eng, "锚点必须来自真实父槽位（data-parent 同源）"
    assert "wantRow = pc ? pc.row + 1 : GW_ANCHOR.body.row + 1" in eng, "行在父件正下方"
    assert "wantCol = pc ? pc.col : 5" in eng, "列与父件对齐"
    assert "if (wantRow > GW_GRID_ROWS) { wantRow = GW_GRID_ROWS; }" in eng, "不越出 6 行"
    assert "if (pc) { c.anchorSlot = par; c.pinned = true; }" in eng, "前握把钉住，并记录父槽位"
    # 固定锚点格（枪托链 / 弹匣 / 握把 / 拉机柄）不许被前握把抢走
    assert "if (reserved[key] || (holder && holder.pinned)) {" in eng, \
        "固定锚点格不许被前握把侵占，改为沿同列下探"
    assert "for (var rr = wantRow + 1; rr <= GW_GRID_ROWS; rr++)" in eng, "同列下探不换列"
    assert "holder && !holder.pinned" in eng, "被挤走的只能是普通格"


def test_no_hardcoded_coordinates_for_foregrip():
    """前握把位置必须由网格行列表达，不许用固定 left/top 或按枪名写死。"""
    js = _read(APP_JS)
    eng = _fn(js, "gwBuildLayout")
    assert "style.left" not in eng and "style.top" not in eng
    assert "5bf3e03b" not in eng and "M4A1" not in eng
    tree = _fn(js, "renderGunTree")
    assert "card.style.gridRow" in tree and "card.style.gridColumn" in tree
    assert 'setAttribute("data-parent", node.parent || "")' in tree, "data-parent 必须指向真实父槽位"


# ---------------------------------------------------------------- 4. 引擎：具体型号必须落地
def test_engine_preinstalls_selected_device_with_host():
    gb = _read(BUILDER_JS)
    opt = _fn(gb, "optimize")
    assert "(cons.deviceIds || []).forEach(function (id) {" in opt, "选定型号计入必装"
    assert "mustKeepIds[id] = 1" in opt
    assert "lockedPaths[step.path.slice(0, cutAt)] = 1;" in opt, \
        "必装设备的承载父件也要锁定，否则贪心换护木会把设备一起换掉"
    assert "preinstallRequired();" in opt and "for (var prePass = 0; prePass < 3; prePass++)" in opt, \
        "两件设备抢同一战术槽时要能补装"
    ri = _fn(gb, "resolveInstall")
    assert "!cur[p] || cur[p] === targetId" in ri, "优先空槽，避免手电顶掉激光的转接座"
    cc = _fn(gb, "checkConstraints")
    assert 'kind: "deviceId"' in cc and "installable" in cc, \
        "装不上时要说明是「没有装进方案」还是「根本没这个槽位」"


# ---------------------------------------------------------------- 5. 动态：布局不变量
@pytest.mark.skipif(shutil.which("node") is None, reason="需要 node 才能跑布局不变量测试")
def test_foregrip_layout_invariants_on_all_guns():
    """163 把枪的默认装配全跑一遍：前握把父件锚定 / 网格边界 / 重叠 / 压枪身。

    R19.12 的规范变化：弹匣被固定在 r4c7，护木子槽（含前握把）在 r4 同列，
    所以"与弹匣同一行"本身不再算错——真正要守的是**列不同且父件锚定正确**。
    换行只发生在父件自己就在第 5 行（r6c9 之类）时。
    """
    proc = subprocess.run(["node", str(LAYOUT_TOOL)], capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    assert proc.returncode == 0, proc.stderr[:2000]
    data = json.loads(proc.stdout)
    summary = data["summary"]
    fg = summary["foregrip"]
    assert fg["guns"] >= 50, "带前握把槽位的枪不止几把，数据链要覆盖"
    assert fg["direct"] >= 30, "直接安装（父件是护木等）是多数情况"
    assert fg["viaRail"] >= 5, "必须存在真实转接皮轨才能覆盖第二种路径"
    assert not fg["offParent"], "前握把列没对齐父件：%s" % fg["offParent"][:3]
    assert not summary["problems"], "布局不变量被破坏：%s" % summary["problems"][:3]

    for gid, g in data["guns"].items():
        assert "error" not in g, "%s 布局抛异常：%s" % (gid, g.get("error"))
        cells = g["cells"]
        by_slot = {c["slot"]: c for c in cells}
        mags = [c for c in cells if c["base"] == "magazine"]
        seen = {}
        # R19.14.2：顶部扩展时总行数 = 6 + topPad，基准网格仍是 6 行
        max_row = 6 + (g.get("topPad") or 0)
        for c in cells:
            assert 1 <= c["row"] <= max_row and 1 <= c["col"] <= 9, \
                "%s 有格子越出 %d×9：%s" % (g["name"], max_row, c["slot"])
            key = (c["row"], c["col"])
            assert key not in seen, "%s 格子重叠：%s 与 %s" % (g["name"], c["slot"], seen.get(key))
            seen[key] = c["slot"]
            assert not (c["row"] == 3 + (g.get("topPad") or 0) and 6 <= c["col"] <= 8), \
                "%s 有格子压住枪身 3 列：%s" % (g["name"], c["slot"])
        for f in [c for c in cells if c["base"] == "foregrip"]:
            p = by_slot.get(f["parent"]) if f["parent"] else None
            if p:
                assert f["col"] == p["col"], "%s 前握把列没对齐父件" % g["name"]
                # 父件正下方被固定锚点占着时允许沿同一列继续下探（列不变、仍在下方）
                assert p["row"] + 1 <= f["row"] <= 6, \
                    "%s 前握把不在父件正下方" % g["name"]
            if mags:
                assert not (f["row"] == mags[0]["row"] and f["col"] == mags[0]["col"])


# ---------------------------------------------------------------- 6. 动态：型号约束落地
@pytest.mark.skipif(shutil.which("node") is None, reason="需要 node 才能跑引擎约束测试")
def test_selected_models_are_really_installed():
    """瞄具 + 手电 + 激光同时约束：四个方案都必须装上这三件，且终检通过。"""
    proc = subprocess.run(["node", str(ENGINE_TOOL), HK416, BURRIS, "%s,%s" % (ARMYTEK, GTL21)],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert proc.returncode == 0, proc.stderr[:2000]
    data = json.loads(proc.stdout)
    assert len(data["builds"]) >= 3, "至少要给出几种权重的方案"
    assert all(b["ok"] for b in data["builds"]), \
        "有方案没满足具体型号约束：%s" % [b for b in data["builds"] if not b["ok"]][:1]
    assert all(not b["missing"] for b in data["builds"]), "方案里缺所选型号"
    assert data["check"]["ok"], "终检必须通过：%s" % data["check"]["violations"]


@pytest.mark.skipif(shutil.which("node") is None, reason="需要 node 才能跑引擎约束测试")
def test_incompatible_model_reports_reason_instead_of_substituting():
    """AK-74 装不上选定的手电：必须报原因，不能静默换成别的型号。"""
    proc = subprocess.run(["node", str(ENGINE_TOOL), AK74, "-", ARMYTEK],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert proc.returncode == 0, proc.stderr[:2000]
    data = json.loads(proc.stdout)
    assert data["builds"], "即使无解也要给出方案行（并标红说明）"
    assert all(not b["ok"] for b in data["builds"])
    assert all(b["missing"] == [ARMYTEK] for b in data["builds"]), "不得偷偷换型号"
    why = " ".join(b["violations"][0] for b in data["builds"])
    assert "所选战术设备" in why and "手电" in why
    assert not data["check"]["ok"]


# ---------------------------------------------------------------- 7. 版本同步
def test_version_marker_current_synced():
    js = _read(APP_JS)
    html = _read(INDEX_HTML)
    m = re.search(r'AM_BUILD = "([^"]+)"', js)
    assert m and m.group(1).startswith("R19."), m and m.group(1)   # 版本标记跟随 AM_BUILD 动态同步
    build = m.group(1)
    for name in ("style.css", "theme-windows-xp.css", "app.js", "gun_builder.js", "combat_sim.js"):
        assert re.search(re.escape(name) + r"\?v=" + re.escape(build.lower()), html), "%s 版本串未同步" % name
