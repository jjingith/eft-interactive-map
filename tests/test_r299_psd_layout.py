# -*- coding: utf-8 -*-
"""R299：配装左栏按用户 PSD（配装参考布局.psd，512×512）1:1 重做。

用户裁定：
- 左侧装备栏就是 PSD 的 512×512 画布，1 PSD 像素 = 1 CSS 像素；
- 每个装备名贴在该装备右上角，浮在图标上，透明底；
- 防弹衣 / 头盔 / 背包（以及 PSD 里同样有属性带的眼镜）下方只写三项数值，
  不再重复「移动 / 转身 / 人机」标签。

本测试锁结构，不做像素截图对比。
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PSD = Path(r"D:\personal\trae\02-塔科夫\ui图标\配装参考布局.psd")
STYLE = ROOT / "style.css"
APP_JS = ROOT / "app.js"
XP_APP = ROOT / "assets" / "xp-ui" / "xp-ui-app.css"


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


# PSD 关键槽位：name -> (x, y, w, h)。来自 psd-tools 逐层 bbox。
PSD_SLOTS = {
    # helmet cell 用「头盔组」图层 bbox 作容器(188,15,145×111)，
    # 本体卡片在组内偏移 (34,34) → 绝对 (222,49)
    "helmet": (188, 15, 145, 111),
    "armband": (46, 76, 36, 35),         # PSD 臂带图层
    "dogtag": (88, 76, 35, 35),          # PSD 狗牌图层
    "left": (46, 118, 77, 34),           # 眼镜（耳机同列 y=172）
    "mid": (145, 128, 39, 39),           # 面罩
    "armor": (209, 146, 103, 103),
    "rig": (357, 146, 103, 103),
    "backpack": (357, 269, 103, 103),
    "gun": (46, 269, 266, 103),
    "primary2": (46, 374, 266, 103),
}
# 头盔组配件槽（相对组左上角 188,15）：PSD 图层语义 → 坐标
PSD_ATTACH_POS = {
    "nvg": (0, 36),     # 配件1 兼容夜视仪类配件
    "rail": (113, 36),  # 配件2 导轨
    "rear": (113, 77),  # 配件3 后部（耳机/后部装甲）
    "top": (57, 0),     # 配件4 顶部
    "face": (0, 77),    # 配件5 面部（正面面罩）
}


def test_psd_readable_and_canvas_is_512():
    try:
        from psd_tools import PSDImage
    except ImportError:
        return  # 解析库是设计期工具，未安装时跳过（不阻断 CI）
    if not PSD.is_file():
        return
    psd = PSDImage.open(str(PSD))
    assert (psd.width, psd.height) == (512, 512)
    names = {str(layer.name) for layer in psd.descendants()}
    for expect in ("头盔", "防弹衣", "胸挂", "背包", "主武器1", "主武器2",
                   "头部防护部位图", "护甲防护部位图", "面罩类", "臂带", "狗牌"):
        assert expect in names, "PSD 缺少图层：%s" % expect


def test_css_uses_fixed_512_canvas():
    css = read(STYLE)
    assert "--lw-side-w: 512px;" in css, "左栏必须固定 512px"
    assert "--lw-p: 1px;" in css, "1 PSD 像素必须等于 1 CSS 像素"
    board = css[css.index(".loadout-workbench .lw-board {"):]
    board = board[:board.index("}")]
    assert "width: 512px;" in board
    assert "height: 512px;" in board
    assert "position: relative;" in board, "画布要参与文档流，后面的费用/预设区才能排在下方"
    # 主题层不能再用边框 / 额外宽度把 PSD 坐标推偏
    xp = read(XP_APP)
    assert "html body .loadout-workbench .lw-board {" in xp
    assert "width: 512px;" in xp and "height: 512px;" in xp


def test_css_has_every_slot_exact_psd_coordinate():
    css = read(STYLE)
    for cell, (x, y, w, h) in PSD_SLOTS.items():
        rule = '[data-cell="%s"]' % cell
        i = css.index(rule)
        seg = css[i:i + 220]
        assert "left: calc(%d * var(--lw-p))" % x in seg, \
            "%s 的 left 与 PSD 不符（应为 %d）" % (cell, x)
        assert "top: calc(%d * var(--lw-p))" % y in seg, \
            "%s 的 top 与 PSD 不符（应为 %d）" % (cell, y)
        assert "width: calc(%d * var(--lw-p))" % w in seg, \
            "%s 的 width 与 PSD 不符（应为 %d）" % (cell, w)


def test_card_sizes_follow_psd():
    css = read(STYLE)
    for token in ("width: calc(77 * var(--lw-p));",     # 头盔
                  "width: calc(39 * var(--lw-p));",     # 面罩
                  "width: calc(103 * var(--lw-p));",    # 防弹衣/胸挂/背包
                  "width: calc(266 * var(--lw-p));"):   # 两把主武器
        assert token in css, "缺卡片尺寸：%s" % token
    assert "height: calc(34 * var(--lw-p));" in css, "眼镜应为 77×34"


def test_helmet_attach_and_zone_deco_positions():
    css = read(STYLE)
    # R300c：按 PSD 图层语义定位（夜视仪 / 导轨 / 后部 / 顶部 / 面部），
    # 不再用 nth-child——不同头盔的 slots[] 顺序不同，按顺序会整体错位。
    for pos, (x, y) in PSD_ATTACH_POS.items():
        m = re.search(
            r'\.lw-node\[data-pos="%s"\]\s*\{\s*left:\s*(?:0|calc\((\d+) \* var\(--lw-p\)\));\s*'
            r'top:\s*(?:0|calc\((\d+) \* var\(--lw-p\)\));' % pos, css)
        assert m, "缺头盔配件语义槽 %s 的定位" % pos
        got = (int(m.group(1) or 0), int(m.group(2) or 0))
        assert got == (x, y), "配件槽 %s 位置 %s 与 PSD %s 不符" % (pos, got, (x, y))
    # 语义判定必须在 app.js 里按槽位定义计算（AirFrame 的 面罩→夜视仪→基座→护颚 顺序）
    js = read(APP_JS)
    assert "function helmetSlotPos(" in js
    for token in ('sid === "mod_nvg"', 'sid === "mod_mount"', "helmetSlotPos(kn && kn.def)"):
        assert token in js, "头盔配件语义定位缺少：%s" % token
    # R300d：子配件贴父配件外侧（左父→左、右/顶父→右），间距统一 2 PSD px（32+2=34）
    assert "var HELMET_SLOT_XY" in js
    assert "function helmetChildOffset(" in js
    assert "dir * 34 * level" in js
    assert 'row.style.left = "calc(" + xy[0] + " * var(--lw-p))"' in js
    assert "left: calc(195 * var(--lw-p));" in css
    assert "top: calc(34 * var(--lw-p));" in css
    assert "left: calc(-17 * var(--lw-p));" in css
    assert "top: calc(44 * var(--lw-p));" in css


def test_equipment_names_are_top_right_and_transparent():
    css = read(STYLE)
    block = css[css.index(".loadout-workbench .lw-cell-name {"):]
    block = block[:block.index("}")]
    assert "position: absolute;" in block
    assert "right: calc(1 * var(--lw-p));" in block
    assert "top: calc(1 * var(--lw-p));" in block
    assert "max-width: calc(100% - 4px);" in block, \
        "名字应锚定右上角并向装备图标上延伸，不能再缩成 34px 小条"
    assert "text-align: right;" in block
    assert "background: transparent;" in block
    assert "border: 0;" in block

    # 空槽位名同样贴右上角、无底
    label = css[css.index(".loadout-workbench .lw-cell-label {"):]
    label = label[:label.index("}")]
    assert "position: absolute;" in label
    assert "right: calc(1 * var(--lw-p));" in label
    assert "text-align: right;" in label
    assert "background: transparent;" in label

    xp = read(XP_APP)
    assert "background: transparent !important;" in xp.split("html body .lw-cell-label {", 1)[1]


def test_local_debuff_strips_show_numbers_only_at_psd_positions():
    css = read(STYLE)
    block = css[css.index(".loadout-workbench .lw-cell-debuff {"):]
    block = block[:block.index("}")]
    assert "position: absolute;" in block
    assert "grid" not in block
    for token in ("left: calc(34 * var(--lw-p));",
                  "top: calc(113 * var(--lw-p));",   # 头盔属性带 y=128 - 15
                  "top: calc(36 * var(--lw-p));",    # 眼镜属性带 y=154 - 118
                  "top: calc(105 * var(--lw-p));"):  # 防弹衣/背包 y=251/374 - 146/269
        assert token in css, "缺 PSD 属性带定位：%s" % token
    js = read(APP_JS)
    assert "lw-debuff-lab" not in js, "属性带不应再渲染「移动 / 转身 / 人机」标签"
    assert 'lab.textContent = "移动 / 转身 / 人机"' not in js


def test_armband_and_dogtag_slots_are_rendered():
    """PSD 里的臂带 / 狗牌必须作为可点根槽位渲染，不能只画装饰。"""
    js = read(APP_JS)
    assert '{ cell: "armband",  keys: ["armband"] }' in js
    assert '{ cell: "dogtag",   keys: ["dogtag"] }' in js
    assert '{ key: "armband",    label: "臂带", rule: "armband" }' in js
    assert '{ key: "dogtag",     label: "狗牌", rule: "dogtag" }' in js
    css = read(STYLE)
    assert '[data-cell="armband"]' in css
    assert '[data-cell="dogtag"]' in css


def test_weapons_without_psd_slot_stay_inside_512_canvas():
    """PSD 未画手枪/近战：保留功能，放进右下空白区，不撑破 512 画布。"""
    js = read(APP_JS)
    assert '{ cell: "holster"' in js and '{ cell: "melee"' in js
    css = read(STYLE)
    assert '[data-cell="holster"]' in css and '[data-cell="melee"]' in css
    holster = css[css.index('[data-cell="holster"]'):]
    holster = holster[:holster.index("}")]
    assert "top: calc(390 * var(--lw-p))" in holster
    melee = css[css.index('[data-cell="melee"]'):]
    melee = melee[:melee.index("}")]
    assert "top: calc(452 * var(--lw-p))" in melee
    assert "top: calc(452 * var(--lw-p))" in css
