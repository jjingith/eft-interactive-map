# -*- coding: utf-8 -*-
"""r14 阶段D：逐发击杀模拟器 UI 接线与数据文件静态测试"""
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(ROOT, "index.html")
APP_JS = os.path.join(ROOT, "app.js")
TARGETS = os.path.join(ROOT, "data", "combat-targets.json")


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def test_combat_targets_json_schema():
    """目标预设文件：schema=1、7 部位齐全、血量与全身合计校验。"""
    data = json.loads(_read(TARGETS))
    assert data.get("schema") == 1
    parts_order = data.get("partsOrder")
    assert parts_order == ["head", "chest", "stomach", "leftArm", "rightArm", "leftLeg", "rightLeg"]
    presets = data.get("presets", [])
    assert len(presets) >= 5
    for p in presets:
        assert p.get("k") and p.get("n")
        parts = p.get("parts", {})
        assert set(parts.keys()) == set(parts_order)
        total = p.get("total")
        assert total == sum(parts.values()), p["k"]
    # 来源记录与腿部 60→65 修正说明必须保留
    assert "source" in data
    assert "65" in json.dumps(data)


def test_index_html_script_order():
    """combat_sim.js 必须在 app.js 之前加载，且存在 sim tab 与 am-sim 容器。"""
    html = _read(INDEX)
    m_cs = re.search(r'<script src="combat_sim\.js(\?v=[^"]*)?"></script>', html)
    m_app = re.search(r'<script src="app\.js(\?v=[^"]*)?"></script>', html)
    assert m_cs and m_app
    assert m_cs.start() < m_app.start()
    assert 'data-tab="sim"' in html
    assert 'id="am-sim"' in html


def test_app_js_sim_wiring():
    """app.js 逐发模拟接线存在：tab 分支、引擎调用、UI 构建与绑定。"""
    js = _read(APP_JS)
    assert "combat_sim.js 未加载" in js or "window.CS" in js
    assert "CS.simulate" in js
    assert "renderAmmoSim" in js
    assert "buildAmmoSimPanel" in js
    assert "bindAmmoSimUI" in js
    assert "amSimBuildEngineCfg" in js
    # 命中分布修复：dist 权重交给引擎，引擎内部归一化（combat_sim.js 侧断言见 combat_sim_test.js 场景11）
    assert '"dist"' in js
    # R17S：hit-mode 下拉改为互斥复选框（hit-fixed / hit-dist）
    assert ('data-sim", "hit-fixed"' in js and 'data-sim", "hit-dist"' in js) or 'hit-mode' in js
    # 弹匣编辑与护甲层操作入口
    # R17S3：sim-load（旧独立填弹）与 sim-clear-mag（旧队列清空）已随旧 UI 删除，
    # 清空/修改一律走五行各自的方框、数量与小叉叉
    for act in ("sim-preset-pick", "sim-preset-load", "sim-layer-preset", "sim-run"):
        assert act in js
    # 不误改无关模块：地图核心函数仍存在
    assert "function renderMap" in js or "renderMap(" in js


def test_combat_sim_engine_raw_weight_fix():
    """引擎 pickPart 须按权重总和归一化（r14 阶段D 浏览器验收发现的修复点）。"""
    js = _read(os.path.join(ROOT, "combat_sim.js"))
    assert "sum += v" in js or "sum > 0" in js
    # 归一化抽签：r = rng() * sum
    assert "rng() * sum" in js
