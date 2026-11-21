# -*- coding: utf-8 -*-
"""R295：配装界面头部防护区域图换成用户 20261118 手绘新版。

新版是「底图 + 8 个部位层」的白底素材（头顶/后脑/面部/下颚/眼部/耳部/喉部/后颈），
由 tools/gen_zone_head_handraw.py 去白底、剔红标后按真实 z 叠放成组合图。

关键不变量：
1. 映射表里头部键全部指向 zone-head-*，且文件真实在盘；
2. items.json 里**全类别**（头盔/面罩/护颚/眼镜）出现过的头部组合必须精确命中；
3. 颈部语义分叉：头部装备 NeckFront/NeckBack → 喉部/后颈；护甲仍 → 脖颈。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_JS = ROOT / "app.js"
ITEMS = ROOT / "data" / "items.json"
ZONES = ROOT / "assets" / "icons" / "zones"
GEN = ROOT / "tools" / "gen_zone_head_handraw.py"

HEAD_ORDER = ["头顶", "后脑", "面部", "下颚", "眼部", "耳部", "喉部", "后颈"]
HEAD_CORE = {"ParietalHead", "BackHead", "HeadCommon", "Jaw", "Eyes", "Ears"}
HEAD_WORDS = {
    "ParietalHead": "头顶", "BackHead": "后脑", "HeadCommon": "面部",
    "Jaw": "下颚", "Eyes": "眼部", "Ears": "耳部",
}
NECK_WORDS = {"NeckFront": "喉部", "NeckBack": "后颈"}
HEAD_ONLY = set(HEAD_ORDER)


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def mapping() -> dict[str, str]:
    js = read(APP_JS)
    i = js.index("var ZONE_ICON_BY_WORDS = {")
    block = js[i:js.index("\n  };", i)]
    return dict(re.findall(r'"([^"]+)":\s*"assets/icons/zones/([^"]+)"', block))


def head_key(zs: list[str]) -> str | None:
    """与 app.js zoneIconKey 的头部语义一致：只有含 HEAD_CORE 才把 Neck* 当头部部位。"""
    if not (HEAD_CORE & set(zs)):
        return None
    words = []
    for z in zs:
        w = HEAD_WORDS.get(z) or NECK_WORDS.get(z)
        if w and w not in words:
            words.append(w)
    return "|".join(w for w in HEAD_ORDER if w in words) if words else None


def test_generator_script_exists():
    assert GEN.is_file(), "缺少头部生成脚本 tools/gen_zone_head_handraw.py"
    src = read(GEN)
    for token in ("strip_layer", "is_red", "HEAD_ORDER", "zone-head-"):
        assert token in src, "生成脚本缺少关键逻辑：%s" % token


def test_all_head_mapping_points_to_new_icons():
    table = mapping()
    heads = {k: v for k, v in table.items() if v.startswith("zone-head-")}
    assert len(heads) >= 25, "头部映射应为 25 种组合，实际 %d" % len(heads)
    for key, fname in heads.items():
        assert (ZONES / fname).is_file(), "头部映射指向的文件不存在：%s → %s" % (key, fname)
    # 旧头部图不应再被任何头部键引用
    for key, fname in table.items():
        if not fname.startswith("zone-head-"):
            assert not (HEAD_ONLY & set(key.split("|"))), \
                "头部键仍指向旧图：%s → %s" % (key, fname)


def test_base_icon_exists():
    assert (ZONES / "zone-head-base.png").is_file(), "缺少头部底图 zone-head-base.png"


def test_every_real_head_combo_has_icon():
    """全类别扫描 items.json：出现过的头部组合必须全部命中，不允许静默降级。"""
    table = mapping()
    items = json.loads(read(ITEMS))["items"]
    combos = {}
    for iid, rec in items.items():
        zs = rec.get("z") or []
        if not isinstance(zs, list):
            continue
        key = head_key(zs)
        if key:
            combos.setdefault(key, (iid, rec.get("n")))
    assert len(combos) >= 25, "头部组合数异常：%d" % len(combos)
    miss = [(k, v[1]) for k, v in combos.items() if k not in table]
    assert not miss, "以下头部组合没有图标：%s" % miss


def test_neck_words_split_by_head_context():
    js = read(APP_JS)
    # 头部语境：喉部 / 后颈
    assert 'if (z === "NeckFront") { return headMode ? "喉部" : "脖颈"; }' in js
    assert 'if (z === "NeckBack") { return headMode ? "后颈" : "脖颈"; }' in js
    # 词表顺序必须与生成脚本一致
    m = re.search(r"var ZONE_WORD_ORDER = \[([\s\S]*?)\];", js)
    order = re.findall(r'"([^"]+)"', m.group(1))
    assert order[-8:] == HEAD_ORDER, "ZONE_WORD_ORDER 头部段与生成脚本不一致：%s" % order[-8:]


def test_armor_neck_still_uses_torso_icon():
    """护甲（无头部核心区）的 NeckFront 仍应命中躯干 zone-neck.png，不能被画成喉部。"""
    table = mapping()
    key = head_key(["RibcageUp", "RibcageLow", "NeckFront"])
    assert key is None, "护甲不应进入头部词表"
    assert table.get("脖颈") == "zone-neck.png"
