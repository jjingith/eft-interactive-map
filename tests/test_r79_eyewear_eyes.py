"""R79：带眼部防护的 eyewear 必须在数据与渲染两侧都可见；任务界面不再出现 tarkov.dev 外链。

背景：
- 上游 tarkov.dev 对眼镜类不返回 properties.zones，`data/items.json` 的 `z` 为空，
  配装界面「防护区域」列看不到「眼部」。R79 用 game-truth 的 armorColliders 补齐。
- 右侧任务点浮窗与任务行原本挂着 tarkov.dev 攻略外链，按「业务界面不外链」统一移除。

这些断言直接读仓库数据与源码，不依赖浏览器：
1. 6B34 护目镜（5b432be65acfc433000ed01f）的 z 必须含 Eyes；
2. 「仅眼部」必须有独立图标映射且文件存在；
3. 眼镜 / 面罩的候选列表必须带 zoneIco 列；
4. app.js 不再渲染 tarkov.dev 任务链接，task-points.json 不再生成 href。
"""

import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ITEMS = os.path.join(ROOT, "data", "items.json")
TASK_POINTS = os.path.join(ROOT, "data", "task-points.json")
APP_JS = os.path.join(ROOT, "app.js")
ZONE_ICON = os.path.join(ROOT, "assets", "icons", "zones", "zone-head-eyes.png")

C_6B34 = "5b432be65acfc433000ed01f"      # 6B34防破片护目镜
C_MASK = "5b432b2f5acfc4771e1c6622"      # 破碎面具（头盔类，含眼部）


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _items():
    return json.loads(_read(ITEMS))["items"]


def test_r79_6b34_eyewear_has_eyes_zone():
    """数据侧：6B34 护目镜必须带 Eyes，且来源是 game-truth 的 armorColliders。"""
    rec = _items().get(C_6B34)
    assert rec, "items.json 应包含 6B34 护目镜"
    assert rec.get("cat") == "glasses", "6B34 应为 glasses 类目"
    zones = rec.get("z") or []
    assert zones == ["Eyes"], "6B34 的防护区域应为 Eyes，实际 %r" % (zones,)

    # 破碎面具（带眼护的面罩）同样不能漏
    mask = _items().get(C_MASK)
    assert mask and "Eyes" in (mask.get("z") or []), "破碎面具应含眼部防护"


def test_r79_eyes_only_icon_registered_and_exists():
    """渲染侧：只有「眼部」的物品要有独立图标，不能退化成文本或空白。"""
    src = _read(APP_JS)
    # R295：头部换成用户 20261118 手绘新版（zone-head-*）
    assert '"眼部": "assets/icons/zones/zone-head-eyes.png"' in src, \
        "app.js 应登记「眼部」→ zone-head-eyes.png"
    assert os.path.isfile(ZONE_ICON), "zone-head-eyes.png 必须随仓库打包"

    # 面罩常见的「面部+下颚」也不能缺图
    assert '"面部|下颚": "assets/icons/zones/zone-head-face-jaw.png"' in src
    assert os.path.isfile(os.path.join(ROOT, "assets", "icons", "zones", "zone-head-face-jaw.png"))


def test_r79_glasses_and_face_tables_show_zone_column():
    """渲染侧：眼镜 / 面罩候选列表必须带「防护区域」列（原来只有头盔/护甲有）。"""
    src = _read(APP_JS)
    for key in ("glasses", "face"):
        start = src.index('rootKey === "%s"' % key)
        block = src[start:src.index(";", start)]
        assert "zoneIcoCol" in block, "%s 列表缺少 zoneIcoCol 防护区域列" % key


def test_r79_task_ui_has_no_tarkov_dev_link():
    """任务界面：源码不再生成 tarkov.dev 攻略链接，数据不再带 href。"""
    src = _read(APP_JS)
    assert "tarkov.dev/task/" not in src, "app.js 不应再拼 tarkov.dev 任务链接"
    assert "appendTaskGuide" not in src, "appendTaskGuide 已删除"
    assert "tarkov.dev 攻略" not in src, "任务行不应再有 tarkov.dev 攻略文案"

    data = _read(TASK_POINTS)
    assert '"href"' not in data, "task-points.json 不应再输出 href 外链"
    assert data.count("tarkov.dev") <= 2, "仅允许 about 出处元数据保留 tarkov.dev"
