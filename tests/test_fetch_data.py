"""数据拉取脚本测试：解析辅助、规范化、幂等与失败不破坏已有产出。

全部离线：网络函数用桩件替换，只有 test_data_ready_* 会读真实产出。
"""

import json
from pathlib import Path

import pytest

import fetch_data as fd
import coord
import floors

ROOT = Path(__file__).resolve().parent.parent


# --------------------------------------------------------------------------- #
# 解析辅助
# --------------------------------------------------------------------------- #
def test_parse_svg_viewbox_from_viewbox_attr():
    svg = '<svg viewBox="0 0 1062.4827 535.17401"><g/></svg>'
    assert fd.parse_svg_viewbox(svg) == [0.0, 0.0, 1062.4827, 535.17401]


@pytest.mark.parametrize(
    "attr,expected",
    [
        ('viewBox="-10 -20 100 200"', [-10.0, -20.0, 100.0, 200.0]),
        ('viewBox="0,0,50,60"', [0.0, 0.0, 50.0, 60.0]),
    ],
)
def test_parse_svg_viewbox_variants(attr, expected):
    assert fd.parse_svg_viewbox("<svg %s></svg>" % attr) == expected


def test_parse_svg_viewbox_falls_back_to_width_height():
    assert fd.parse_svg_viewbox('<svg width="40" height="30"></svg>') == [0.0, 0.0, 40.0, 30.0]


@pytest.mark.parametrize("bad", ["", "<html></html>", "<svg></svg>", '<svg width="40"></svg>'])
def test_parse_svg_viewbox_rejects_garbage(bad):
    with pytest.raises(ValueError):
        fd.parse_svg_viewbox(bad)


def test_parse_svg_top_layers_only_takes_direct_children():
    """每一层是 SVG 根下的顶层组；层内的子组不能算成层。"""
    svg = ('<svg><g id="Ground_Level"><g id="Trees"/><g id="Roads"><g id="Deep"/></g></g>'
           '<g id="Second_Floor"><g id="Rooms"/></g></svg>')
    assert fd.parse_svg_top_layers(svg) == ["Ground_Level", "Second_Floor"]


def test_parse_svg_top_layers_ignores_unnamed_and_self_closing():
    svg = '<svg><g><g id="Hidden"/></g><g id="Basement"/><g id="Empty"/><path d="M0 0"/></svg>'
    assert fd.parse_svg_top_layers(svg) == ["Basement", "Empty"]


def test_parse_svg_top_layers_empty_on_garbage():
    assert fd.parse_svg_top_layers('<svg width="1"></svg>') == []


def test_prettify_key():
    assert fd.prettify_key("ground-zero") == "Ground Zero"
    assert fd.prettify_key("customs") == "Customs"


def test_localize_uses_translation_or_falls_back():
    table = {"ex_customs_scav_gasstation": "老加油站"}
    assert fd.localize(table, "ex_customs_scav_gasstation", "fallback") == "老加油站"
    assert fd.localize(table, "unknown_key", "fallback") == "fallback"
    assert fd.localize(table, None, "fallback") == "fallback"
    assert fd.localize(table, "", "fallback") == "fallback"


@pytest.mark.parametrize(
    "node,expected",
    [
        ({"x": 1.5, "z": -2.5}, (1.5, -2.5)),
        ([3, 4], (3, 4)),
        ((5, 6), (5, 6)),
        ({}, (None, None)),
        (None, (None, None)),
        ("nope", (None, None)),
        ([1], (None, None)),
    ],
)
def test_flatten_positions(node, expected):
    assert fd.flatten_positions(node) == expected


def test_outline_2d_flattens_and_rounds():
    assert fd.outline_2d([{"x": 1.23456, "z": -2.34567}, [3, 4], {"x": 5}]) == [[1.23, -2.35], [3.0, 4.0]]


def test_outline_2d_empty_when_garbage():
    assert fd.outline_2d(None) == []
    assert fd.outline_2d([None, "nope", {}]) == []


def test_point_3d_keeps_height_and_extra_fields():
    assert fd.point_3d({"x": 1, "y": 2.5, "z": 3}, {"name": "雷区"}) == {
        "x": 1.0, "z": 3.0, "y": 2.5, "name": "雷区"
    }


def test_point_3d_omits_missing_height():
    assert "y" not in fd.point_3d({"x": 1, "z": 3})


@pytest.mark.parametrize("node", [None, "nope", {"x": 1}, {"z": 1}, {}])
def test_point_3d_rejects_incomplete_points(node):
    assert fd.point_3d(node) is None


# --------------------------------------------------------------------------- #
# 选图
# --------------------------------------------------------------------------- #
def _config_fixture():
    return [
        {
            "normalizedName": "g1",
            "maps": [
                {"key": "customs", "svgPath": "/maps/svg/Customs.svg", "transform": [1, 0, 1, 0]},
                {"key": "lab", "tilePath": "/tiles/lab"},
            ],
        }
    ]


def test_select_maps_only_keeps_maps_with_svg():
    selected = fd.select_maps(_config_fixture(), [])
    assert list(selected) == ["customs"]


def test_select_maps_requested_subset():
    assert list(fd.select_maps(_config_fixture(), ["customs"])) == ["customs"]


def test_select_maps_rejects_unknown_key():
    with pytest.raises(ValueError) as exc:
        fd.select_maps(_config_fixture(), ["laboratory"])
    assert "laboratory" in str(exc.value)


# --------------------------------------------------------------------------- #
# 单图规范化
# --------------------------------------------------------------------------- #
def _build_entry(**overrides):
    entry = {
        "key": "customs",
        "svgPath": "/maps/svg/Customs.svg",
        "svgLayer": "Ground_Level",
        "transform": [0.239, 168.65, 0.239, 136.35],
        "coordinateRotation": 180,
        "bounds": [[698, -307], [-372, 237]],
        "labels": [{"text": "Big Red", "position": [200, 100]}],
    }
    entry.update(overrides)
    return entry


def _markers_fixture():
    return {
        "customs": {
            "id": "56f40101d2720b2a4d8b45d6",
            "normalizedName": "customs",
            "name": "56f40101d2720b2a4d8b45d6 Name",
            "extracts": [
                {"name": "ex_customs_scav_gasstation", "faction": "scav", "position": {"x": 310.71, "y": 1.0, "z": -174.95}},
                {"name": "no_position"},
            ],
            "transits": [{"description": "tr_customs_DESC_reserve", "position": {"x": 1, "y": 0, "z": 2}}],
            "spawns": [{"position": {"x": -3.14159, "z": 2.71828}, "sides": ["scav", "pmc"], "categories": ["bot"]}],
        }
    }


def _schema2_markers():
    """带新图层（危险区/钥匙门/物资/Boss/炮击区/BTR）的上游标注数据。"""
    markers = _markers_fixture()
    markers["customs"].update({
        "hazards": [
            {"hazardType": "minefield", "position": {"x": 1, "y": 4, "z": 2},
             "outline": [{"x": 0, "z": 0}, {"x": 0, "z": 5}, {"x": 5, "z": 5}]},
            {"hazardType": "sniper", "position": {"x": 9, "y": 12, "z": 9}},          # 无 outline → 退化成点
            {"hazardType": "minefield", "position": {"x": 9, "z": 9}, "outline": [{"x": 0}]},  # 轮廓不足 → 点
        ],
        "locks": [
            {"lockType": "door", "needsPower": True, "key": "key_dorm_118",
             "position": {"x": 1, "y": 0, "z": 1}},
            {"lockType": "trunk", "position": {"x": 2, "y": 0, "z": 2}},
            {"position": {"x": 3, "y": 0, "z": 3}},                                   # 缺 lockType → door
            {"position": {"x": 4}},                                                   # 缺 z → 丢弃
        ],
        "lootContainers": [
            {"lootContainer": "578f87a3245977110c0b2a97", "position": {"x": 5, "y": 0, "z": 5}},
            {"lootContainer": "unknown_container", "position": {"x": 6, "y": 0, "z": 6}},
        ],
        "lootLoose": [
            {"position": {"x": 7, "y": 1, "z": 7}},                                   # 无物品池 → 只是散落物资
            {"position": {"x": 8, "y": 1, "z": 8}, "items": ["btc", "booze", "junk"]},  # 有高级物品
            {"position": {"x": 9, "y": 1, "z": 9}, "items": ["ledx", "ledx"]},         # 同名去重
            {"position": {"x": 10, "y": 1, "z": 10}, "items": ["junk"]},               # 都不高级
            {"position": {"x": 11}, "items": ["btc"]},                                 # 缺 z → 丢弃
        ],
        "bosses": [{
            "mob": "bossKilla",
            "spawnChance": 0.35,
            "spawnLocations": [
                {"name": "二楼", "positions": [{"x": 8, "y": 3, "z": 8}, {"x": None, "z": 8}]},
                {"positions": [{"x": 9, "y": 0, "z": 9}]},
            ],
        }],
        "artillery": {"zones": [{"position": {"x": -50, "y": 2, "z": -50},
                                 "outline": [{"x": -60, "z": -60}, {"x": -40, "z": -60}, {"x": -40, "z": -40}]}]},
        "btrStops": [{"name": "btr_customs_stop_1", "x": 11, "y": 0, "z": 11}, {"x": 12, "y": 0}],
    })
    return markers


def _schema2_translations():
    return {
        "56f40101d2720b2a4d8b45d6 Name": "海关",
        "ex_customs_scav_gasstation": "老加油站",
        "tr_customs_DESC_reserve": "前往储备站",
        "bossKilla Name": "Killa",
        "btr_customs_stop_1": "BTR 一号站",
    }


def test_build_map_layer_hazards_keeps_outline_and_type():
    item = fd.build_map(_build_entry(), _schema2_markers(), _schema2_translations(), [0.0, 0.0, 10.0, 10.0])
    hazards = item["layers"]["hazards"]
    assert len(hazards) == 3
    assert hazards[0]["type"] == "minefield"
    assert hazards[0]["outline"] == [[0.0, 0.0], [0.0, 5.0], [5.0, 5.0]]
    assert "outline" not in hazards[1], "没有轮廓的危险区不应带 outline"
    assert "outline" not in hazards[2], "顶点不足三个也算不上多边形"


def test_hazard_fix_replaces_wrong_sniper_zone():
    """街区那片狙击区上游画在 x -40～-103 一带，实际在街区西北角：连中心点一起换成修正值。"""
    upstream = {"x": -71.9, "z": 0.6, "y": 8.5, "type": "sniper",
                "outline": [[-103.42, -24.8], [-92.71, 35.32], [-40.38, 26.0], [-51.09, -34.12]]}
    fixed = fd.apply_hazard_fix("streets-of-tarkov", upstream)
    assert fixed["type"] == "sniper"
    assert fixed["outline"] == [[-203.0, 0.0], [-273.0, 12.0], [-262.0, 79.0], [-192.0, 67.0]]
    assert (fixed["x"], fixed["z"]) == (-232.49, 38.8), "中心点要跟着新轮廓走"
    assert "y" not in fixed, "狙击区是整片垂直区域，没有高度含义"


def test_hazard_fix_leaves_other_hazards_untouched():
    point = {"x": 1.0, "z": 2.0, "y": 3.0, "type": "minefield"}
    assert fd.apply_hazard_fix("streets-of-tarkov", point) is point, "没登记的坐标原样返回"
    assert fd.apply_hazard_fix("customs", {"x": -71.9, "z": 0.6})["x"] == -71.9, "别的图不受影响"


def test_build_map_layer_valuables_only_keeps_high_value_pools():
    """高级资源点 = 散落刷点里物品池含 BTC / 私酒 / LEDX… 的那些点；其余留给「散落物资」层。"""
    items = {"btc Name": "实体比特币", "booze Name": "“凶狠跑刀崽”私酒",
             "ledx Name": "LEDX皮肤透照仪", "junk Name": "螺栓"}
    item = fd.build_map(_build_entry(), _schema2_markers(), _schema2_translations(),
                        [0.0, 0.0, 10.0, 10.0], item_translations=items)
    layers = item["layers"]

    assert len(layers["loose"]) == 4, "缺 z 的散落点被丢掉"
    valuables = layers["valuables"]
    assert len(valuables) == 2, "只有两个点的物品池里有高级物品"
    assert valuables[0]["items"] == ["实体比特币", "“凶狠跑刀崽”私酒"]
    assert valuables[1]["items"] == ["LEDX皮肤透照仪"], "同一个点里重复出现的物品只记一次"
    assert [v["x"] for v in valuables] == [8.0, 9.0]


def test_build_map_valuables_empty_without_translations():
    """拿不到物品名时宁可不给点，也不要凭 id 猜。"""
    item = fd.build_map(_build_entry(), _schema2_markers(), _schema2_translations(), [0.0, 0.0, 10.0, 10.0])
    assert item["layers"]["valuables"] == []


def test_build_map_map_name_survives_valuables_pass():
    """回归：抽高级资源点时用过同名循环变量，会把地图名覆盖成最后一个物品名。"""
    items = {"btc Name": "实体比特币", "booze Name": "“凶狠跑刀崽”私酒",
             "ledx Name": "LEDX皮肤透照仪", "junk Name": "螺栓"}
    item = fd.build_map(_build_entry(), _schema2_markers(), _schema2_translations(),
                        [0.0, 0.0, 10.0, 10.0], item_translations=items)
    assert item["name"] == "海关", "地图名必须来自 <图 id> Name，不能被物品名顶掉"


def test_build_map_layer_locks():
    item = fd.build_map(_build_entry(), _schema2_markers(), _schema2_translations(), [0.0, 0.0, 10.0, 10.0])
    locks = item["layers"]["locks"]
    assert [l["type"] for l in locks] == ["door", "trunk", "door"]
    assert locks[0]["needsPower"] is True
    assert locks[1]["needsPower"] is False
    assert len(locks) == 3, "缺 z 的锁丢掉了"


def test_build_map_lock_resolves_key_name():
    """上锁的门要把钥匙物品 id 换成中文钥匙名（拿不到名字就不加这个字段，前端会退回显示 id）。"""
    item_translations = {"key_dorm_118 Name": "宿舍118房间钥匙", "key_dorm_118 ShortName": "宿舍118"}
    item = fd.build_map(
        _build_entry(), _schema2_markers(), _schema2_translations(), [0.0, 0.0, 10.0, 10.0],
        item_translations=item_translations,
    )
    locks = item["layers"]["locks"]
    assert locks[0]["key"] == "key_dorm_118"
    assert locks[0]["keyName"] == "宿舍118房间钥匙"
    assert locks[0]["keyShort"] == "宿舍118"
    # 没有钥匙 / 译名表里查不到：不该硬塞一个空名字
    assert "keyName" not in locks[1]
    assert "keyName" not in locks[2]


def test_build_map_layer_containers_and_loose_use_translations():
    translations = dict(_schema2_translations())
    translations["578f87a3245977110c0b2a97 Name"] = "木制板条箱"
    item = fd.build_map(_build_entry(), _schema2_markers(), translations, [0.0, 0.0, 10.0, 10.0])
    containers = item["layers"]["containers"]
    assert containers[0]["name"] == "木制板条箱", "有翻译就用翻译"
    assert containers[1]["name"] == "其他容器", "缺翻译时回退到类别中文名，不显示上游 id"
    assert containers[0].get("group") == "misc", "没给 slug 表时一律归其他容器"
    assert item["layers"]["loose"][0] == {"x": 7.0, "z": 7.0, "y": 1.0}, "散落物资只有坐标"


def test_container_groups_cover_known_slugs_once():
    keys = [entry[0] for entry in fd.CONTAINER_GROUPS]
    assert keys == ["safe", "jacket", "pcblock", "scavbody", "drawer", "duffle", "cache",
                    "med", "supply", "suitcase", "toolbox", "register", "grenade", "weapon"]
    slugs = [slug for _key, _label, group_slugs in fd.CONTAINER_GROUPS for slug in group_slugs]
    assert len(slugs) == len(set(slugs)), "同一个 slug 只该属于一个类别（否则开关会重复计数）"
    for _key, label, _slugs in fd.CONTAINER_GROUPS:
        assert label
    labels = [label for _key, label, _slugs in fd.CONTAINER_GROUPS]
    assert len(labels) == len(set(labels)), "类别名重复会让侧栏出现两个同名开关"


@pytest.mark.parametrize("slug, expected", [
    ("safe", "safe"),
    ("bank-cash-register", "register"),
    ("cash-register", "register"),
    ("weapon-box", "weapon"),
    ("wooden-crate", "weapon"),
    ("wooden-ammo-box", "weapon"),
    ("grenade-box", "grenade"),
    ("medbag", "med"),
    ("medcase", "med"),
    ("medical-supply-crate", "med"),
    ("pc-block", "pcblock"),
    ("ration-supply-crate", "supply"),
    ("technical-supply-crate", "supply"),
    ("ground-cache", "cache"),
    ("shturmans-stash", "cache"),
    ("buried-barrel-cache", "cache"),
    ("dead-scav", "scavbody"),
    ("scav-body", "scavbody"),
    ("pmc-body", "scavbody"),
    ("civilian-body", "scavbody"),
    ("lab-technician-body", "scavbody"),
    ("jacket", "jacket"),
    ("drawer", "drawer"),
    ("duffle-bag", "duffle"),
    ("plastic-suitcase", "suitcase"),
    ("toolbox", "toolbox"),
    ("", "misc"),
    (None, "misc"),
    ("brand-new-container-from-upstream", "misc"),
])
def test_container_group_by_slug(slug, expected):
    assert fd.container_group(slug) == expected


def test_container_slugs_reads_upstream_defs():
    markers_data = {"lootContainers": {"id-a": {"normalizedName": "medbag"}, "id-b": None}}
    assert fd.container_slugs(markers_data) == {"id-a": "medbag", "id-b": None}
    assert fd.container_slugs({}) == {}


def test_build_map_container_group_uses_slug_map():
    """容器类别按上游 slug 判定，不是拿中文译名去猜。"""
    slug_map = {"578f87a3245977110c0b2a97": "medbag", "unknown_container": "duffle-bag"}
    item = fd.build_map(_build_entry(), _schema2_markers(), _schema2_translations(),
                        [0.0, 0.0, 10.0, 10.0], None, None, slug_map)
    groups = [point["group"] for point in item["layers"]["containers"]]
    assert groups == ["med", "duffle"], "类别由 slug 决定"


def test_build_map_layer_bosses_flattens_locations():
    item = fd.build_map(_build_entry(), _schema2_markers(), _schema2_translations(),
                        [0.0, 0.0, 10.0, 10.0], mobs={"bossKilla": {"name": "bossKilla Name"}})
    bosses = item["layers"]["bosses"]
    assert len(bosses) == 2, "缺 x 的刷新点应被跳过"
    assert bosses[0]["name"] == "Killa", "Boss 名走 mobs 表的翻译键"
    assert bosses[0]["where"] == "二楼"
    assert bosses[0]["chance"] == 0.35
    assert "where" not in bosses[1], "上游没给位置名就不编一个"
    assert bosses[1]["chance"] == 0.35, "概率挂在 Boss 上，与位置无关"


def test_build_map_layer_artillery_and_btr():
    item = fd.build_map(_build_entry(), _schema2_markers(), _schema2_translations(), [0.0, 0.0, 10.0, 10.0])
    artillery = item["layers"]["artillery"]
    assert len(artillery) == 1
    assert len(artillery[0]["outline"]) == 3
    btr = item["layers"]["btr"]
    assert len(btr) == 1, "缺 z 的 BTR 站应被跳过"
    assert btr[0]["name"] == "BTR 一号站"

    untranslated = fd.build_map(_build_entry(), _schema2_markers(), {}, [0.0, 0.0, 10.0, 10.0])
    assert untranslated["layers"]["btr"][0]["name"] == "BTR 停靠点", "缺翻译时兜底名字"


def test_build_map_records_floors_and_svg_layers():
    entry = _build_entry(layers=[
        {"name": "Ground floor", "svgLayer": "Ground_Level", "extents": [{"height": [0, 3]}]},
        {"name": "2nd Floor", "svgLayer": "Second_Floor", "extents": [{"height": [3, 6]}]},
        {"name": "3rd Floor", "extents": [{"height": [6, 9]}]},
    ])
    item = fd.build_map(entry, _schema2_markers(), _schema2_translations(),
                        [0.0, 0.0, 10.0, 10.0], svg_layers=["Ground_Level", "Second_Floor"])
    assert item["svgLayers"] == ["Ground_Level", "Second_Floor"]
    assert [s["svgLayer"] for s in item["floors"]["switchable"]] == ["Second_Floor"]
    assert item["floors"]["default"] == ["Ground_Level"]


def test_build_map_without_new_layers_still_produces_empty_arrays():
    """上游缺某些图层时也要给出空数组，前端不必到处判空。"""
    item = fd.build_map(_build_entry(), _markers_fixture(), {}, [0.0, 0.0, 10.0, 10.0])
    for kind in ("hazards", "locks", "containers", "loose", "valuables", "bosses", "artillery", "btr"):
        assert item["layers"][kind] == [], kind


def test_build_map_localizes_and_rounds():
    translations = {
        "56f40101d2720b2a4d8b45d6 Name": "海关",
        "ex_customs_scav_gasstation": "老加油站",
        "tr_customs_DESC_reserve": "前往储备站",
    }
    item = fd.build_map(_build_entry(), _markers_fixture(), translations, [0.0, 0.0, 1062.4827, 535.17401])

    assert item["key"] == "customs"
    assert item["name"] == "海关"
    assert item["svg"] == "assets/maps/Customs.svg"
    assert item["svgLayer"] == "Ground_Level"
    assert set(item["worldToSvg"]) == set("abcdef")
    assert item["svgBounds"] == [[698.0, -307.0], [-372.0, 237.0]]

    extracts = item["layers"]["extracts"]
    assert len(extracts) == 1, "无 position 的标注应被跳过"
    assert extracts[0]["name"] == "老加油站"
    assert extracts[0]["faction"] == "scav"
    assert extracts[0]["x"] == 310.71

    assert item["layers"]["transits"][0]["name"] == "前往储备站"
    spawn = item["layers"]["spawns"][0]
    assert spawn["sides"] == ["pmc", "scav"], "sides 应排序"
    assert spawn["x"] == -3.142, "坐标应保留三位小数"
    assert item["labels"][0] == {"text": "Big Red", "x": 200.0, "z": 100.0}


def test_build_map_falls_back_when_translation_missing():
    item = fd.build_map(_build_entry(), _markers_fixture(), {}, [0.0, 0.0, 10.0, 10.0])
    assert item["name"] == "Customs", "缺翻译时回退到 key 的美化写法"
    assert item["layers"]["extracts"][0]["name"] == "ex_customs_scav_gasstation"


def test_build_map_prefers_svg_bounds_over_bounds():
    """储备站的 svgBounds 与瓦片 bounds 不同，必须优先用 svgBounds，否则标注整体偏移。"""
    entry = _build_entry(svgBounds=[[289, -274], [-303, 272]])
    a = fd.build_map(entry, _markers_fixture(), {}, [0.0, 0.0, 100.0, 100.0])
    b = fd.build_map(_build_entry(), _markers_fixture(), {}, [0.0, 0.0, 100.0, 100.0])
    assert a["worldToSvg"] != b["worldToSvg"]
    assert a["svgBounds"] == [[289.0, -274.0], [-303.0, 272.0]]


def test_build_map_without_bounds_raises():
    entry = _build_entry(bounds=None, svgBounds=None)
    with pytest.raises(ValueError) as exc:
        fd.build_map(entry, _markers_fixture(), {}, [0.0, 0.0, 10.0, 10.0])
    assert "bounds" in str(exc.value)


def test_build_map_missing_markers_raises():
    with pytest.raises(ValueError):
        fd.build_map(_build_entry(), {"woods": {}}, {}, [0.0, 0.0, 10.0, 10.0])


def test_build_map_uses_explicit_svg_name():
    """瓦片图的底图是构建期拼出来的合成 SVG，文件名不能从上游 svgPath 推。"""
    item = fd.build_map(_build_entry(), _markers_fixture(), {}, [0.0, 0.0, 10.0, 10.0],
                        svg_name="TheLab.svg")
    assert item["svg"] == "assets/maps/TheLab.svg"


# --------------------------------------------------------------------------- #
# 瓦片底图（实验室 / 迷宫）
# --------------------------------------------------------------------------- #
# 实验室的真实配置：transform 与 bounds 都取自上游，用来验证合成底图的 viewBox
# 与 worldToSvg 严丝合缝（换算出底图矩形的角点必须正好落在 viewBox 的对角上）。
LAB_TRANSFORM = [0.575, 281.2, 0.575, 193.7]
LAB_BOUNDS = [[-80, -477], [-287, -193]]


def test_tile_pixel_rect_agrees_with_world_to_svg():
    """合成底图的 viewBox 取像素包围盒的宽高；worldToSvg 必须把 bounds 四个角点都映到 viewBox 边界上。

    旋转是 90° 的整数倍时，像素两轴各只依赖一个世界轴，因此世界矩形正好铺满底图矩形——
    底图与标记因此严丝合缝（换成社区 SVG 的「对不齐」正是这里出的问题）。
    """
    left, top, right, bottom = fd.tile_pixel_rect(LAB_TRANSFORM, 270, LAB_BOUNDS)
    viewbox = [0.0, 0.0, right - left, bottom - top]
    coeff = coord.compute_world_to_svg(LAB_TRANSFORM, 270, LAB_BOUNDS, viewbox)
    (x1, z1), (x2, z2) = LAB_BOUNDS
    points = [coord.world_to_svg(coeff, x, z)
              for x in (min(x1, x2), max(x1, x2)) for z in (min(z1, z2), max(z1, z2))]
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    assert min(xs) == pytest.approx(0.0)
    assert max(xs) == pytest.approx(right - left)
    assert min(ys) == pytest.approx(0.0)
    assert max(ys) == pytest.approx(bottom - top)


def test_build_tile_svg_rejects_degenerate_bounds():
    """bounds 在像素空间退化（宽或高为 0）时不能硬拼，否则 viewBox 会非法。"""
    entry = {"key": "the-labyrinth", "tilePath": "https://example.invalid/{z}/{x}/{y}.png",
             "transform": [0.0, 0.0, 0.0, 0.0], "coordinateRotation": 0,
             "bounds": [[0, 0], [8, 8]], "layers": []}
    with pytest.raises(ValueError) as exc:
        fd.build_tile_svg("the-labyrinth", entry, force=False)
    assert "退化" in str(exc.value)


@pytest.mark.parametrize("left,top,right,bottom,tile,zoom,expected", [
    (0.0, 0.0, 100.0, 100.0, 100.0, 2, (0, 3, 0, 3)),      # 一格恰好覆盖 1/4 底图
    (1.0, 2.0, 3.0, 4.0, 100.0, 2, (0, 0, 0, 0)),          # 完全落在同一格内
    (0.0, 0.0, 100.0, 100.0, 100.0, 0, (0, 0, 0, 0)),      # zoom 0：一格盖满
])
def test_tile_grid_range(left, top, right, bottom, tile, zoom, expected):
    assert fd.tile_grid(left, top, right, bottom, tile, zoom) == expected


def test_tile_grid_covers_rect():
    """下标范围必须完整盖住矩形，否则底图上会有空白条。"""
    left, top, right, bottom = fd.tile_pixel_rect(LAB_TRANSFORM, 270, LAB_BOUNDS)
    step = 175.0 / (2 ** fd.TILE_ZOOM)
    x0, x1, y0, y1 = fd.tile_grid(left, top, right, bottom, 175.0, fd.TILE_ZOOM)
    assert x0 * step <= left and (x1 + 1) * step >= right
    assert y0 * step <= top and (y1 + 1) * step >= bottom
    assert 0 < (x1 - x0 + 1) * (y1 - y0 + 1) < 400, "瓦片数量应在合理量级"


def test_layer_world_bounds_prefers_extent_bounds():
    entry = {"bounds": [[-80, -477], [-287, -193]]}
    layer = {"extents": [{"height": [3, 6], "bounds": [[[-101, -422], [-271, -270]]]}]}
    assert fd.layer_world_bounds(entry, layer) == [[-271, -422], [-101, -270]]
    assert fd.layer_world_bounds(entry, None) == entry["bounds"], "无 bounds 时退回整图"
    assert fd.layer_world_bounds(entry, {"extents": []}) == entry["bounds"]


def test_apply_tile_layer_ids_fills_missing_svg_layer():
    """上游这几层只有 name，没有 svgLayer；不补的话楼层判定与切换整个不工作。"""
    entry = {"layers": [{"name": "Second Level"}, {"name": "Technical"}, {"name": "Other"}]}
    fd.apply_tile_layer_ids(entry, "the-lab")
    assert entry["svgLayer"] == "First_Floor"
    assert entry["layers"][0]["svgLayer"] == "Second_Floor"
    assert entry["layers"][1]["svgLayer"] == "Technical_Floor"
    assert "svgLayer" not in entry["layers"][2], "没登记的层不该被乱塞 id"


def test_tile_svg_document_wraps_images_in_named_groups():
    groups = [
        ("Ground_Level", [{"x": 0.0, "y": 0.0, "w": 32.0, "h": 32.0,
                           "href": "assets/maps/tiles/the-labyrinth/a.png"}]),
        ("Second_Floor", []),
    ]
    text = fd.tile_svg_document([0.0, 0.0, 64.0, 32.0], groups)
    assert 'viewBox="0 0 64 32"' in text
    assert '<g id="Ground_Level">' in text and '<g id="Second_Floor">' in text
    assert 'href="assets/maps/tiles/the-labyrinth/a.png"' in text
    assert fd.parse_svg_viewbox(text) == [0.0, 0.0, 64.0, 32.0]
    assert fd.parse_svg_top_layers(text) == ["Ground_Level", "Second_Floor"]


def test_svg_num_trims_noise():
    assert fd.svg_num(0.0) == "0"
    assert fd.svg_num(-0.0) == "0"
    assert fd.svg_num(1.5) == "1.5"
    assert fd.svg_num(1.234567) == "1.2346"


def test_build_tile_svg_skips_empty_tiles_and_writes_document(monkeypatch, tmp_path):
    """空格子（上游返回的全透明小图）必须跳过；有内容的瓦片落盘并写进合成 SVG。"""
    monkeypatch.setattr(fd, "ASSETS_DIR", tmp_path / "assets" / "maps")
    monkeypatch.setattr(fd, "TILE_ASSET_DIR", tmp_path / "assets" / "maps" / "tiles")
    monkeypatch.setattr(fd, "TILE_CACHE_DIR", tmp_path / "build-cache" / "tiles")

    big = b"x" * 800          # 有内容
    monkeypatch.setattr(fd, "fetch_tile",
                        lambda url, cache, force: big if url.endswith("/0/0.png") else b"y" * 100)

    # transform 的 t3=64 把世界 z 轴翻到正像素方向：底图恰好覆盖 2×2 格瓦片（步长 32）
    entry = {
        "key": "the-labyrinth",
        "tilePath": "https://example.invalid/lab/{z}/{x}/{y}.png",
        "tileSize": 256,
        "transform": [1.0, 0.0, 1.0, 64.0],
        "coordinateRotation": 0,
        "bounds": [[0, 0], [64, 64]],
        "layers": [],
    }
    viewbox, tops, written = fd.build_tile_svg("the-labyrinth", entry, force=False)
    assert tops == ["Ground_Level"]
    assert written == len(big), "只统计真正落盘的有内容瓦片"
    svg = (tmp_path / "assets" / "maps" / "TheLabyrinth.svg").read_text(encoding="utf-8")
    assert 'href="assets/maps/tiles/the-labyrinth/Ground_Level_3_0_0.png"' in svg
    assert svg.count("<image ") == 1, "空格子不该写进底图"
    assert viewbox == [0.0, 0.0, 64.0, 64.0]


def test_build_tile_svg_requires_tile_path():
    entry = {"key": "the-labyrinth", "bounds": [[0, 0], [8, 8]], "layers": []}
    with pytest.raises(ValueError) as exc:
        fd.build_tile_svg("the-labyrinth", entry, force=False)
    assert "tilePath" in str(exc.value)


def test_tile_maps_only_lists_maps_without_svg_path():
    """TILE_MAPS 是「上游没有矢量底图、只能拼瓦片」的白名单；别把有 SVG 的图也塞进来。"""
    assert set(fd.TILE_MAPS) == {"the-lab", "the-labyrinth", "icebreaker"}
    for cfg in fd.TILE_MAPS.values():
        assert cfg["file"].endswith(".svg")
        assert cfg["layerIds"]
        if cfg.get("rootLayer"):
            # 显式指定主层的图（破冰船）：上游主层 tilePath 与某个具名层重复，不能再写 (None, …)
            assert all(name is not None for name, _layer_id in cfg["layerIds"])
        else:
            assert cfg["layerIds"][0][0] is None


def test_apply_tile_layer_ids_honours_explicit_root_layer():
    """破冰船：主层 tilePath 指向具名层 Infirmary，用 rootLayer 指定主层，避免拼出重复组。"""
    entry = {"layers": [{"name": "Infirmary"}, {"name": "Bridge"}]}
    fd.apply_tile_layer_ids(entry, "icebreaker")
    assert entry["svgLayer"] == "Deck_06_Infirmary"
    assert entry["layers"][0]["svgLayer"] == "Deck_06_Infirmary"
    assert entry["layers"][1]["svgLayer"] == "Deck_14_Bridge"


def test_apply_tile_projection_replaces_broken_upstream_geometry():
    """破冰船：上游 transform 各向异性、bounds 与 factory 雷同，必须整体换成人工投影。"""
    entry = {"transform": [2.0, 125.0, 3.5, 91.0], "bounds": [[77, -64.5], [-65.5, 67.4]],
             "svgBounds": [[1, 2], [3, 4]]}
    fd.apply_tile_projection(entry, "icebreaker")
    assert entry["transform"] == list(fd._ICEBREAKER_TRANSFORM)
    assert entry["bounds"] == [list(pair) for pair in fd._ICEBREAKER_BOUNDS]
    assert "svgBounds" not in entry          # 上游若补了它，会盖掉刚覆盖的 bounds
    assert entry["transform"][0] == entry["transform"][2], "反推的投影必须各向同性"


def test_apply_tile_projection_keeps_upstream_for_other_tile_maps():
    """没写 projection 的瓦片图（实验室 / 迷宫）保持上游 transform / bounds 不动。"""
    entry = {"transform": [0.575, 281.2, 0.575, 193.7], "bounds": [[1, 2], [3, 4]]}
    fd.apply_tile_projection(entry, "the-lab")
    assert entry["transform"] == [0.575, 281.2, 0.575, 193.7]
    assert entry["bounds"] == [[1, 2], [3, 4]]


def test_icebreaker_projection_maps_frame_to_expected_pixels():
    """反推的投影必须把取景框映射回瓦片像素矩形（内容四周各留 4 px）。

    瓦片下标就是按这个像素矩形取的，改 _ICEBREAKER_* 之前先看这条回归锁。
    """
    rect = fd.tile_pixel_rect(fd._ICEBREAKER_TRANSFORM, 180, fd._ICEBREAKER_BOUNDS)
    expected = (fd._FRAME_LEFT, fd._FRAME_TOP, fd._FRAME_RIGHT, fd._FRAME_BOTTOM)
    for got, want in zip(rect, expected):
        assert abs(got - want) < 1e-6, "取景框映射到 %s，期望 %s" % (rect, expected)


def test_tile_map_layer_ids_all_have_floor_labels():
    """瓦片图的组 id 必须有中文层名，否则楼层列表会整排显示成「主层」。"""
    for cfg in fd.TILE_MAPS.values():
        for _name, layer_id in cfg["layerIds"]:
            assert layer_id in floors.FLOOR_LABELS, "%s 没有中文层名" % layer_id


# --------------------------------------------------------------------------- #
# 写入与幂等
# --------------------------------------------------------------------------- #
def test_write_atomic_replaces_and_leaves_no_tmp(tmp_path):
    target = tmp_path / "out.json"
    target.write_bytes(b"old")
    fd.write_atomic(target, b"new")
    assert target.read_bytes() == b"new"
    assert not list(tmp_path.glob("*.tmp"))


def _prepare_project(tmp_path, maps=None):
    """在临时目录里造一份“已就绪”的产出结构。"""
    (tmp_path / "data").mkdir()
    (tmp_path / "assets" / "maps").mkdir(parents=True)
    payload = {"schema": fd.SCHEMA,
               "maps": maps if maps is not None else [{"key": "customs", "svg": "assets/maps/Customs.svg"}]}
    (tmp_path / "data" / "maps.json").write_text(json.dumps(payload), encoding="utf-8")
    for entry in payload["maps"]:
        (tmp_path / entry["svg"]).write_text("<svg/>", encoding="utf-8")
    return tmp_path


def _redirect_dirs(monkeypatch, tmp_path):
    monkeypatch.setattr(fd, "ROOT", tmp_path)
    monkeypatch.setattr(fd, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(fd, "ASSETS_DIR", tmp_path / "assets" / "maps")
    monkeypatch.setattr(fd, "CACHE_DIR", tmp_path / "build-cache")


def test_data_ready_true_with_real_output():
    if not (ROOT / "data" / "maps.json").exists():
        pytest.skip("尚未生成 data/maps.json")
    assert fd.data_ready([]) is True


def test_data_ready_false_when_index_missing(monkeypatch, tmp_path):
    _redirect_dirs(monkeypatch, tmp_path)
    (tmp_path / "data").mkdir()
    assert fd.data_ready([]) is False


def test_data_ready_false_when_svg_missing(monkeypatch, tmp_path):
    _prepare_project(tmp_path)
    _redirect_dirs(monkeypatch, tmp_path)
    (tmp_path / "assets" / "maps" / "Customs.svg").unlink()
    assert fd.data_ready([]) is False


def test_data_ready_false_when_selection_differs(monkeypatch, tmp_path):
    _prepare_project(tmp_path)
    _redirect_dirs(monkeypatch, tmp_path)
    assert fd.data_ready(["customs", "woods"]) is False


def test_data_ready_false_for_old_schema(monkeypatch, tmp_path):
    """旧结构缺新图层与楼层，必须判定为未就绪，逼出一次重新生成。"""
    _prepare_project(tmp_path)
    _redirect_dirs(monkeypatch, tmp_path)
    index = tmp_path / "data" / "maps.json"
    index.write_text(json.dumps({"schema": fd.SCHEMA - 1, "maps": [{"key": "customs", "svg": "assets/maps/Customs.svg"}]}),
                     encoding="utf-8")
    assert fd.data_ready([]) is False


def test_run_skips_without_any_network_when_ready(monkeypatch):
    """幂等核心断言：产出已就绪时，run() 不得发起任何下载。"""
    if not (ROOT / "data" / "maps.json").exists():
        pytest.skip("尚未生成 data/maps.json")

    def boom(*args, **kwargs):
        raise AssertionError("就绪状态下不应联网")

    monkeypatch.setattr(fd, "fetch", boom)
    assert fd.run(fd.parse_args([])) == 0


def test_run_failure_keeps_existing_data(monkeypatch, tmp_path, capsys):
    _prepare_project(tmp_path)
    _redirect_dirs(monkeypatch, tmp_path)
    (tmp_path / "build-cache").mkdir()
    before = (tmp_path / "data" / "maps.json").read_bytes()

    def boom(*args, **kwargs):
        raise RuntimeError("模拟断网")

    monkeypatch.setattr(fd, "fetch", boom)
    monkeypatch.setattr(fd, "load_json_cached", boom)

    assert fd.main(["--force"]) == 1
    assert (tmp_path / "data" / "maps.json").read_bytes() == before, "失败不得破坏已有产出"
    assert (tmp_path / "assets" / "maps" / "Customs.svg").read_text(encoding="utf-8") == "<svg/>"
    assert "错误" in capsys.readouterr().err


def test_load_json_cached_uses_cache_without_network(monkeypatch, tmp_path):
    monkeypatch.setattr(fd, "CACHE_DIR", tmp_path)

    def boom(*args, **kwargs):
        raise AssertionError("命中缓存时不应联网")

    monkeypatch.setattr(fd, "fetch", boom)
    (tmp_path / "x.json").write_bytes(b'{"a": 1}' + b" " * 600)
    payload, raw = fd.load_json_cached("http://example.invalid/x", "x.json", force=False, timeout=1)
    assert payload == {"a": 1} and len(raw) > 512


def test_load_json_cached_force_refetches(monkeypatch, tmp_path):
    monkeypatch.setattr(fd, "CACHE_DIR", tmp_path)
    (tmp_path / "x.json").write_bytes(b'{"a": 1}' + b" " * 600)
    monkeypatch.setattr(fd, "fetch", lambda *a, **k: b'{"a": 2}')
    payload, _ = fd.load_json_cached("http://example.invalid/x", "x.json", force=True, timeout=1)
    assert payload == {"a": 2}


def test_parse_args_defaults():
    args = fd.parse_args([])
    assert args.mode == "regular" and args.maps == "" and args.force is False
    assert fd.parse_args(["--maps", "customs,woods"]).maps == "customs,woods"


# --------------------------------------------------------------------------- #
# 真实产出：计数与图层完整性
# --------------------------------------------------------------------------- #
def _real_data():
    index = ROOT / "data" / "maps.json"
    if not index.exists():
        pytest.skip("尚未生成 data/maps.json")
    return json.loads(index.read_text(encoding="utf-8"))


def _real_meta():
    path = ROOT / "data" / "meta.json"
    if not path.exists():
        pytest.skip("尚未生成 data/meta.json")
    return json.loads(path.read_text(encoding="utf-8"))


def test_meta_counts_match_reality():
    """概览条上的计数必须等于实际数据，不然用户看到的数字就是假的。"""
    data = _real_data()
    meta = _real_meta()
    maps = data["maps"]

    actual = {"maps": len(maps), "labels": sum(len(m["labels"]) for m in maps)}
    for kind in ("extracts", "transits", "spawns", "hazards", "locks", "containers", "loose",
                 "valuables", "bosses", "artillery", "btr", "stationary"):
        actual[kind] = sum(len(m["layers"][kind]) for m in maps)
    actual["locksNamed"] = sum(1 for m in maps for lk in m["layers"]["locks"] if lk.get("keyName"))
    actual["containerGroups"] = {}
    for item in maps:
        for point in item["layers"]["containers"]:
            key = point["group"]
            actual["containerGroups"][key] = actual["containerGroups"].get(key, 0) + 1
    # 瓦片底图的落地量：计数与字节数必须等于 assets/maps/tiles 下真实存在的 PNG
    tile_root = ROOT / "assets" / "maps" / "tiles"
    tiles = list(tile_root.glob("**/*.png"))
    actual["tileMaps"] = len({p.relative_to(tile_root).parts[0] for p in tiles})
    actual["tileBytes"] = sum(p.stat().st_size for p in tiles)

    assert meta["counts"] == dict(sorted(actual.items())), "概览计数应与 maps.json 完全一致"
    # 概览里只报 14 个正式类别；出现「其他容器」说明上游新增了没归类的容器
    assert set(meta["counts"]["containerGroups"]) == {key for key, _label, _slugs in fd.CONTAINER_GROUPS}


def test_meta_and_maps_agree_on_schema_and_mode():
    data = _real_data()
    meta = _real_meta()
    assert meta["schema"] == data["schema"] == fd.SCHEMA
    assert meta["gameMode"] == data["gameMode"]


def test_real_data_every_map_has_all_layer_kinds():
    data = _real_data()
    expected = {"extracts", "transits", "spawns", "hazards", "locks", "containers", "loose",
                "valuables", "bosses", "artillery", "btr", "stationary"}
    for item in data["maps"]:
        assert set(item["layers"]) == expected, "%s 图层不全" % item["key"]


def test_real_data_hazard_outlines_are_polygons():
    data = _real_data()
    for item in data["maps"]:
        for hazard in item["layers"]["hazards"]:
            if "outline" in hazard:
                assert len(hazard["outline"]) >= 3, "%s 的轮廓顶点不足 3 个" % item["key"]
                for point in hazard["outline"]:
                    assert len(point) == 2 and all(isinstance(v, (int, float)) for v in point)


def test_real_data_streets_sniper_zone_is_corrected():
    """产出里要留着修正后的街区狙击区：轮廓、中心点、以及「没有 y」都要对得上。"""
    data = _real_data()
    streets = [m for m in data["maps"] if m["key"] == "streets-of-tarkov"][0]
    fixed = [h for h in streets["layers"]["hazards"] if h.get("x") == -232.49]
    assert len(fixed) == 1, "修正后的狙击区没落进产出（是不是又跑了没带修正表的 fetch_data？）"
    assert fixed[0]["outline"] == [[-203.0, 0.0], [-273.0, 12.0], [-262.0, 79.0], [-192.0, 67.0]]
    assert "y" not in fixed[0]


def test_real_data_bosses_carry_chance_and_name():
    data = _real_data()
    bosses = [b for m in data["maps"] for b in m["layers"]["bosses"]]
    assert bosses, "一张 Boss 刷新点都没有，前端图层就没意义"
    for boss in bosses:
        assert boss["name"]
        assert 0 <= boss["chance"] <= 1, "刷新概率应在 0~1"


def test_real_data_every_container_has_known_group():
    """容器类别是前端拆开关的依据：每个容器都得有，且只能是那 14 类之一。"""
    data = _real_data()
    known = {key for key, _label, _slugs in fd.CONTAINER_GROUPS}
    seen = set()
    for item in data["maps"]:
        for point in item["layers"]["containers"]:
            assert point["group"] in known, "%s 里有类别未知的容器：%s" % (item["key"], point)
            seen.add(point["group"])
    assert seen == known, "至少有一类容器在实际产出里从未出现，开关会是空的：%s" % (known - seen)
