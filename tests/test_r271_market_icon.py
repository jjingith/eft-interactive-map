"""R271：二级工具条的「市场」按钮没有图标。

现象（2026-11-13 12:17）：地图 / 任务 / 弹药 / 配枪 / 配装 左侧都有图标，
只有「市场」左边空着一格 16px。

原因：`xp-ui-app.css` 只给五个视图写了
`#view-btn-xxx .vt-ico { background-image: url("icon-xxx.png") }`，
`#view-btn-market` 漏了这条规则；而按钮里的内联 SVG 又统一被
`.vt-ico svg { display: none }` 收掉 —— 于是既没有位图、也看不到矢量图。

这里锁死：六个视图按钮都必须有对应的位图规则，且图片文件真实存在。
"""

import os
import re

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSS = os.path.join(ROOT, "assets", "xp-ui", "xp-ui-app.css")
ICON_DIR = os.path.join(ROOT, "assets", "xp-ui")

# R286：新增「市场大盘」按钮，它同样是内联 SVG + 位图规则，一并锁死。
VIEWS = ["map", "tasks", "ammo", "gun", "loadout", "market", "market-board"]


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def test_every_view_button_has_icon_rule():
    css = _read(CSS)
    missing = []
    for v in VIEWS:
        pat = r'#view-btn-%s\s+\.vt-ico\s*\{[^}]*background-image:\s*url\("([^"]+)"\)' % v
        if not re.search(pat, css):
            missing.append(v)
    assert not missing, "这些视图按钮缺少图标规则：%s" % missing


def test_market_icon_file_exists_and_is_16px():
    path = os.path.join(ICON_DIR, "icon-market.png")
    assert os.path.exists(path), "缺 assets/xp-ui/icon-market.png"
    im = Image.open(path)
    assert im.size == (16, 16), "图标必须是 16×16，实际 %s" % (im.size,)
    assert im.mode in ("RGBA", "LA"), "图标要带透明通道，否则按钮底会被方块盖住：%s" % im.mode


def test_icon_files_referenced_by_css_all_exist():
    css = _read(CSS)
    refs = re.findall(r'url\("(icon-[a-z0-9\-]+\.png)"\)', css)
    missing = [r for r in set(refs) if not os.path.exists(os.path.join(ICON_DIR, r))]
    assert not missing, "CSS 引用了不存在的图标：%s" % missing
