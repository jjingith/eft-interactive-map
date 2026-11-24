# -*- coding: utf-8 -*-
"""右上角/状态栏徽标语义演进（R301 数据截止 → R303 应用版本）。

历史：
- R84：显示「游戏版本 1.3.0.48484」，取自本机 EFT 客户端 exe 版本，
  与本项目主数据源 tarkov.dev 无关。
- R301：改为「数据截止 YYYY-MM-DD」，取 data/meta.json 的 generatedAt。
- R303（当前）：按用户要求改为显示**应用自身版本号**（如 v0.2.8.3），
  真值取本地 /api/update-check 的 current_version（= tools/serve.py 的 VERSION）。
  数据快照日期仍在状态栏「数据：」字段与市场页显示，不再占右上角徽标。

不变量：
1. app-menubar.js 用 setAppVersion/loadAppVersion 读 api/update-check 的 current_version；
2. 徽标正文是版本号（vX.Y.Z），有新版本只写入 title，不占正文；
3. 不再有 loadGameVersion/gameVer/loadDataDate/dataDate 的旧逻辑；
4. index.html 徽标初始文案为「版本 —」，title 指向 current_version；
5. 枪械角标的「游戏版本 X 加入」是另一语义（武器上线版本），保留不动。
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


def test_badge_uses_app_version():
    js = read(MENUBAR)
    assert "function setAppVersion(" in js
    assert "function loadAppVersion(" in js
    assert '"api/update-check"' in js, "必须读本地 update-check 接口"
    assert "current_version" in js
    # 正文是 vX.Y.Z；有新版本只进 title
    assert 'var v = "v" + cur' in js
    assert "j.available && j.latest_version" in js


def test_no_old_badge_logic():
    js = read(MENUBAR)
    # 只看代码（去掉注释块），注释里保留历史说明是有价值的
    code = __import__("re").sub(r"/\*[\s\S]*?\*/", "", js)
    for gone in ["loadGameVersion", "gameVer", "loadDataDate", "dataDate",
                 "source.exe_version", "game-truth/meta.json"]:
        assert gone not in code, "旧徽标逻辑残留：%s" % gone
    assert code.count("loadAppVersion()") >= 2


def test_index_badge_copy_is_version():
    html = read(INDEX)
    idx = html.index('id="build-rev"')
    seg = html[idx:idx + 280]
    assert "版本 —" in seg
    assert "current_version" in seg
    assert "数据截止" not in seg and "游戏版本" not in seg
    # 右下角状态栏徽标
    idx2 = html.index('id="sb-rev"')
    seg2 = html[idx2:idx2 + 220]
    assert "版本 —" in seg2 and "数据截止" not in seg2
    # 「关于」面板文案
    assert "右上角与状态栏显示应用版本" in html


def test_data_meta_still_has_generated_at():
    """数据快照日期仍在 meta.json（状态栏数据字段/市场页用），不能因徽标改造丢失。"""
    import json
    j = json.loads(read(META))
    g = str(j.get("generatedAt", ""))
    assert g[:10].count("-") == 2 and len(g[:10]) == 10, \
        "generatedAt 应为 YYYY-MM-DD 开头，实际：%r" % g


def test_gun_version_badge_kept():
    """枪械角标的「游戏版本 X 加入」是另一语义，不能误删。"""
    app = read(APP)
    assert "游戏版本 " in app and "加入" in app
