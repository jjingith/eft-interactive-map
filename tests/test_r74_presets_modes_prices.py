"""R74 三条验收：配装栏枪械预设 / 模式唯一切换入口 / 配装价格只剩跳蚤 24h + 7d。"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "app.js")
INDEX = os.path.join(ROOT, "index.html")
TASKS_JS = os.path.join(ROOT, "tasks.js")
TASKS_CSS = os.path.join(ROOT, "tasks.css")


def _text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def test_a_loadout_has_no_gun_preset_section():
    """R299 后续：配装栏不再重复展示枪械预设区，枪械预设在配枪栏维护。"""
    html = _text(INDEX)
    js = _text(APP)
    assert 'id="lw-gun-presets"' not in html
    assert 'id="lw-gp-list"' not in html
    assert "还没有保存的枪械预设" not in html
    assert "还没有保存的枪械预设" not in js
    assert "去配枪栏新建" not in js
    assert "function renderLwGunPresets()" not in js
    assert "renderLwGunPresets();" not in js


def test_b_only_one_mode_switch_entry_survives():
    html = _text(INDEX)
    js = _text(APP)
    tasks_js = _text(TASKS_JS)
    tasks_css = _text(TASKS_CSS)
    # 顶栏全局分段按钮是唯一入口
    assert html.count('id="game-mode-bar"') == 1
    # 任务页不再自带模式分段 / 切换按钮
    assert "tk-seg-btn" not in tasks_js
    assert "data-tkmode" not in tasks_js
    assert "切换入口只在右上角" in tasks_js
    # 任务页不能把全局条藏掉（R72 的隐藏规则必须撤掉）
    assert 'body[data-view="tasks"] .scope-cluster #game-mode-bar { display: none; }' not in tasks_css
    # 枪匠面板只保留只读标签，跟随全局模式
    assert "gs-mode-tag" in js
    assert "模式：" in js and "右上角切换" in js
    # 全局联动仍然挂在一个函数上
    assert "function applyDataScope(" in js
    assert "applyDataScope({ mode: scopeMode() })" in js


def test_c_loadout_price_lives_in_the_source_cell_only():
    """R74 定下「配装价格只走跳蚤口径」，R219 把承载方式从「两列」改回「获取方式格内」。
    本测试守住真正的不变量：配装表**只有一处**价格、口径仍是跳蚤、档位可切换。"""
    js = _text(APP)
    html = _text(INDEX)
    # R219：独立的两列价格撤掉，价格并入获取方式格（不再重复占宽）
    assert 'key: "p24", label: "跳蚤 24h 均价"' not in js
    assert 'key: "p7d", label: "跳蚤 7d 均价"' not in js
    assert "var p24Col" not in js and "var p7dCol" not in js
    assert 'className = "lw-src-price"' in js
    # 旧的单一 Price 列也不回来
    assert not re.search(r'key: "price", label: "Price"', js)
    # 7d 上游缺失必须如实标注，且不允许用别的口径 / 别的模式冒充
    #   · 价格档定义里写明「需≥7 个快照日；不足时显示 —，不插值」
    #   · 格内缺价时写明「不拿别的口径 / 别的模式顶替」
    assert "avg7daysPrice" in js and "不插值" in js
    assert "不拿别的口径 / 别的模式顶替" in js
    # R265：价格档 pills 上移到二级工具条 #vt-prices（配装页不再单独一份）
    assert 'id="vt-prices"' in html
    assert 'id="lw-prices"' not in html
    assert not re.search(r'id="vt-prices"[^>]*hidden', html)
    # 关于面板改成新口径
    about = html[html.index('id="about-block"'):html.index("<!-- R19.11", html.index('id="about-block"'))]
    assert "随右上角 PvP / PvE / PvPS 与价格档" in about
    assert "买卖价同源" not in about
