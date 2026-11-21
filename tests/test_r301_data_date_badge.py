# -*- coding: utf-8 -*-
"""R301：右上角/状态栏徽标从「游戏版本」改为「数据截止」（对齐 tarkov.dev）。

问题：右上角与右下角显示「游戏版本 1.3.0.48484」，真值来自
data/game-truth/meta.json 的 source.exe_version —— 那是**本机 EFT 客户端**版本
（R58b 从 D:\\GAMES\\EFT 提取），与本项目主数据源 tarkov.dev 无关。
用户指出：数据都从 tarkov.dev 抓，版本应向 tarkov.dev 对齐。

关键事实：tarkov.dev 数据体系**没有游戏版本字段**（静态 items / data/meta.json /
fetch_data.py 都只有 generatedAt）。所以改为显示 tarkov.dev 快照生成时间
data/meta.json 的 generatedAt（取日期部分），文案「数据截止」，不再冒充游戏版本。

不变量：
1. app-menubar.js 用 setDataDate/loadDataDate 读 data/meta.json 的 generatedAt；
2. 不再有 loadGameVersion / gameVer / 顶栏「游戏版本 X」文案；
3. index.html 徽标初始文案与 title 都是「数据截止」；
4. 枪械角标的「游戏版本 X 加入」是另一语义（真实上线版本），保留不动。
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MENUBAR = ROOT / "js" / "app-menubar.js"
INDEX = ROOT / "index.html"
META = ROOT / "data" / "meta.json"
APP = ROOT / "app.js"


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def test_badge_uses_tarkovdev_generated_at():
    js = read(MENUBAR)
    assert "function setDataDate(" in js
    assert "function loadDataDate(" in js
    assert '"data/meta.json"' in js, "必须读主数据源快照 meta.json"
    assert "generatedAt" in js
    assert "数据截止 " in js
    # 日期裁剪：generatedAt 形如 2026-11-15T... → 取前 10 位
    assert "raw.slice(0, 10)" in js


def test_no_old_game_version_badge_logic():
    js = read(MENUBAR)
    # 只看代码（去掉 /* ... */ 注释块），注释里保留旧字段名用于解释改动缘由是有价值的
    code = __import__("re").sub(r"/\*[\s\S]*?\*/", "", js)
    for gone in ["loadGameVersion", "gameVer", "source.exe_version",
                 "game-truth/meta.json", "game-truth/ammo_ballistic.json"]:
        assert gone not in code, "旧的「游戏版本」代码残留：%s" % gone
    # 两个调用点都换成新函数
    assert code.count("loadDataDate()") >= 2


def test_index_badge_copy_is_data_date():
    html = read(INDEX)
    idx = html.index('id="build-rev"')
    seg = html[idx:idx + 260]
    assert "数据截止" in seg
    assert "generatedAt" in seg
    assert "游戏版本" not in seg
    # 右下角状态栏徽标
    idx2 = html.index('id="sb-rev"')
    seg2 = html[idx2:idx2 + 220]
    assert "数据截止" in seg2 and "游戏版本" not in seg2
    # 「关于」面板文案
    assert "右上角与状态栏显示数据截止日期" in html


def test_data_meta_has_generated_at():
    import json
    j = json.loads(read(META))
    g = str(j.get("generatedAt", ""))
    assert g[:10].count("-") == 2 and len(g[:10]) == 10, \
        "generatedAt 应为 YYYY-MM-DD 开头，实际：%r" % g


def test_gun_version_badge_kept():
    """枪械角标的「游戏版本 X 加入」是另一语义，不能误删。"""
    app = read(APP)
    assert "游戏版本 " in app and "加入" in app
