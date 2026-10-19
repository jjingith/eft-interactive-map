"""楼层结构测试：上游配置 → 可切换楼层 + y 落在哪一层的判定。

纯函数测试覆盖 floors.py；最后几条读真实 data/maps.json，校验产出里的楼层结构自洽
（波段区间递增、可切换层确实出现在底图顶层组里）。
"""

import json
from pathlib import Path

import pytest

from floors import FLOOR_LABELS, band_key, build_floors, detect_band, floor_label

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "maps.json"


# --------------------------------------------------------------------------- #
# 楼层命名
# --------------------------------------------------------------------------- #
def test_floor_label_maps_svg_layer_to_chinese():
    assert floor_label("Second_Floor") == "二层"
    assert floor_label("Bunkers") == "地堡"


def test_floor_label_falls_back_to_upstream_name_then_default():
    assert floor_label(None, "2nd Floor") == "2nd Floor"
    assert floor_label("Unknown_Layer", "Roof") == "Roof"
    assert floor_label(None) == "主层"
    assert floor_label("Unknown_Layer") == "主层"


def test_every_layer_used_in_data_has_a_label():
    """标签表要覆盖上游所有会出现的 svgLayer 名，免得界面上冒出英文 id。"""
    assert {"Ground_Level", "Ground_Floor", "First_Floor", "Second_Floor", "Third_Floor",
            "Fourth_Floor", "Fifth_Floor", "Basement", "Underground_Level", "Bunkers"} <= set(FLOOR_LABELS)


# --------------------------------------------------------------------------- #
# 楼层结构
# --------------------------------------------------------------------------- #
def _entry(layers=None, svg_layer="Ground_Level"):
    return {"key": "customs", "svgLayer": svg_layer, "layers": layers if layers is not None else []}


def test_build_floors_keeps_root_and_switchable():
    entry = _entry([
        {"name": "Ground floor", "svgLayer": "Ground_Level", "extents": [{"height": [0, 3]}]},
        {"name": "2nd Floor", "svgLayer": "Second_Floor", "extents": [{"height": [3, 6]}]},
    ])
    floors = build_floors(entry, ["Ground_Level", "Second_Floor"])
    assert floors["root"]["svgLayer"] == "Ground_Level"
    assert floors["root"]["label"] == "地面层"
    assert [s["svgLayer"] for s in floors["switchable"]] == ["Second_Floor"]
    assert floors["default"] == ["Ground_Level"], "只有主层默认显示"


def test_build_floors_skips_layers_without_svg_layer():
    """储备站的 2~5 层只有瓦片没有矢量图层：能判定，但不能切换（否则切到空白图）。"""
    entry = _entry([
        {"name": "Ground", "svgLayer": "Ground_Level", "extents": [{"height": [0, 3]}]},
        {"name": "2nd Floor", "extents": [{"height": [3, 6]}]},
    ])
    floors = build_floors(entry, ["Ground_Level"])
    assert floors["switchable"] == []
    assert len(floors["bands"]) == 2, "两层都应能判定"
    assert floors["bands"][1]["svgLayer"] is None
    assert floors["bands"][1]["label"] == "2nd Floor", "没有 svgLayer 时用上游层名当提示"


def test_build_floors_drops_switchable_absent_from_svg():
    entry = _entry([{"name": "2nd", "svgLayer": "Second_Floor", "extents": [{"height": [3, 6]}]}])
    assert build_floors(entry, ["Ground_Level"])["switchable"] == []


def test_build_floors_switchable_passes_when_svg_layers_unknown():
    """没传 svg_layers（旧调用）时不做存在性过滤，只按 svgLayer 去重。"""
    entry = _entry([
        {"name": "2nd", "svgLayer": "Second_Floor", "extents": []},
        {"name": "2nd again", "svgLayer": "Second_Floor", "extents": []},
    ])
    assert [s["svgLayer"] for s in build_floors(entry)["switchable"]] == ["Second_Floor"]


def test_build_floors_default_includes_show_layers():
    """上游标 show=true 的层默认与主层叠加显示（立交桥商场一层）。"""
    entry = _entry([
        {"name": "G", "svgLayer": "Ground_Level", "extents": []},
        {"name": "1F", "svgLayer": "First_Floor", "show": True, "extents": []},
        {"name": "2F", "svgLayer": "Second_Floor", "extents": []},
    ])
    floors = build_floors(entry, ["Ground_Level", "First_Floor", "Second_Floor"])
    assert floors["default"] == ["Ground_Level", "First_Floor"]


def test_build_floors_normalizes_bounds_to_sorted_areas():
    entry = _entry([{"name": "2F", "svgLayer": "Second_Floor",
                     "extents": [{"height": [3, 6], "bounds": [[[10, 20], [0, 5]]]}]}])
    assert build_floors(entry, ["Second_Floor"])["bands"][0]["areas"] == [[0, 5, 10, 20]]


def test_build_floors_keeps_band_without_bounds():
    entry = _entry([{"name": "3F", "svgLayer": "Third_Floor", "extents": [{"height": [6, 100]}]}])
    assert build_floors(entry, ["Third_Floor"])["bands"][0]["areas"] == []


@pytest.mark.parametrize("bad_extents", [
    [{"height": None}], [{"height": [1]}], [{"height": "3-6"}], [{}], None,
])
def test_build_floors_ignores_broken_extents(bad_extents):
    entry = _entry([{"name": "2F", "svgLayer": "Second_Floor", "extents": bad_extents}])
    assert build_floors(entry, ["Second_Floor"])["bands"] == []


def test_build_floors_skips_broken_bounds_but_keeps_band():
    entry = _entry([{"name": "2F", "svgLayer": "Second_Floor",
                     "extents": [{"height": [3, 6], "bounds": [[[0, 0]], "nope", None]}]}])
    assert build_floors(entry, ["Second_Floor"])["bands"][0]["areas"] == []


def test_build_floors_selectable_covers_svg_only_floor_groups():
    """底图里有、上游 layers[] 里没有的楼层组也要能选，否则它只能一直盖在别的层上面。"""
    entry = _entry([{"name": "2nd Floor", "svgLayer": "Second_Floor", "extents": []}])
    floors = build_floors(entry, ["Ground_Level", "First_Floor", "Second_Floor"])
    assert [s["svgLayer"] for s in floors["selectable"]] == ["Ground_Level", "First_Floor", "Second_Floor"]
    assert [s["svgLayer"] for s in floors["switchable"]] == ["Second_Floor"], "上游登记的可切换层不变"
    assert [s["isRoot"] for s in floors["selectable"]] == [True, False, False]


def test_build_floors_selectable_ignores_non_floor_top_groups():
    """楼梯这类跨层共用的组不是楼层，不该出现在楼层列表里（它会一直可见）。"""
    entry = _entry([])
    floors = build_floors(entry, ["Stairs_Common", "Ground_Level"])
    assert [s["svgLayer"] for s in floors["selectable"]] == ["Ground_Level"]


def test_build_floors_selectable_orders_bottom_to_top():
    entry = _entry([{"name": "2nd Floor", "svgLayer": "Second_Floor", "extents": []}])
    floors = build_floors(entry, ["Second_Floor", "Ground_Level", "Basement", "First_Floor"])
    assert [s["svgLayer"] for s in floors["selectable"]] == \
        ["Basement", "Ground_Level", "First_Floor", "Second_Floor"]


def test_build_floors_selectable_without_svg_layers_keeps_known_layers():
    entry = _entry([{"name": "2nd Floor", "svgLayer": "Second_Floor", "extents": []}])
    assert [s["svgLayer"] for s in build_floors(entry)["selectable"]] == ["Ground_Level", "Second_Floor"]


# --------------------------------------------------------------------------- #
# 坐标判定
# --------------------------------------------------------------------------- #
@pytest.fixture
def floors():
    """二层带矩形约束（只覆盖 x,z ∈ [0,10]），三层整图都算。"""
    return build_floors(_entry([
        {"name": "2F", "svgLayer": "Second_Floor",
         "extents": [{"height": [3, 6], "bounds": [[[0, 0], [10, 10]]]}]},
        {"name": "3F", "svgLayer": "Third_Floor", "extents": [{"height": [6, 100]}]},
    ]), ["Second_Floor", "Third_Floor"])


def test_detect_band_without_height_falls_back_to_root(floors):
    assert detect_band(floors, 5, None, 5)["isRoot"] is True


def test_detect_band_by_height_only(floors):
    assert detect_band(floors, None, 7, None)["svgLayer"] == "Third_Floor"


def test_detect_band_respects_area_constraint(floors):
    assert detect_band(floors, 5, 4, 5)["svgLayer"] == "Second_Floor"
    assert detect_band(floors, 50, 4, 50)["isRoot"] is True, "落在区间但不在矩形内 → 主层"
    assert detect_band(floors, None, 4, None)["isRoot"] is True, "需要矩形但缺 x/z → 主层"


def test_detect_band_first_match_wins(floors):
    """重叠波段按上游顺序取第一个命中，三层要等二层区间结束才生效。"""
    assert detect_band(floors, 5, 6, 5)["svgLayer"] == "Third_Floor"
    assert detect_band(floors, 5, 4, 5)["svgLayer"] == "Second_Floor"


def test_band_key_prefers_svg_layer_then_label_at_height(floors):
    second = detect_band(floors, 5, 4, 5)
    assert band_key(floors, second) == "Second_Floor"
    assert band_key(floors, floors["root"]) == "Ground_Level", "主层用它的 svgLayer 当 key"

    no_svg_layer = build_floors(_entry([{"name": "2F", "extents": [{"height": [3, 6]}]}]))
    assert band_key(no_svg_layer, no_svg_layer["bands"][0]) == "2F@3.0"


# --------------------------------------------------------------------------- #
# 真实产出
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def data():
    if not DATA.exists():
        pytest.skip("尚未生成 data/maps.json")
    return json.loads(DATA.read_text(encoding="utf-8"))


def test_data_schema_matches_generator(data):
    """产出里的 schema 必须与生成器当前声明的一致（写死数字会让每次升版都得改测试）。"""
    import fetch_data as fd

    assert data.get("schema") == fd.SCHEMA, "schema 变了就说明前端要么该升级、要么产出过期"


def test_data_floor_structure_is_consistent(data):
    for item in data["maps"]:
        svg_layers = item["svgLayers"]
        floors = item["floors"]
        assert item["svgLayer"] in svg_layers, "%s 的主层不在顶层组里" % item["key"]
        assert floors["root"]["svgLayer"] == item["svgLayer"]
        for layer in floors["default"]:
            assert layer in svg_layers, "%s 默认显示的层 %s 不在顶层组里" % (item["key"], layer)
        for band in floors["bands"]:
            assert band["minY"] < band["maxY"], "%s 有无效高度区间" % item["key"]
        for switch in floors["switchable"]:
            assert switch["svgLayer"] in svg_layers, "%s 可切换层不在顶层组里" % item["key"]


def test_data_has_multi_floor_maps_with_switchable_layers(data):
    """至少要有一张真能切层的图（储备站/海关），否则楼层功能等于没做。"""
    multi = [m for m in data["maps"] if m["floors"]["switchable"]]
    assert multi, "没有任何可切换楼层的图"
    for item in multi:
        ids = [s["svgLayer"] for s in item["floors"]["switchable"]]
        assert item["svgLayer"] not in ids, "主层不该出现在可切换列表里"


def test_data_selectable_floor_ids_are_real_svg_groups(data):
    """可选楼层必须真的存在于底图的顶层组里，否则界面上会出现点了没反应的按钮。"""
    for item in data["maps"]:
        selectable = [s["svgLayer"] for s in item["floors"]["selectable"]]
        assert item["svgLayer"] in selectable, "%s 的主层不在可选列表里" % item["key"]
        assert len(selectable) == len(set(selectable))
        for svg_id in selectable:
            assert svg_id in item["svgLayers"], "%s 的可选层 %s 不在底图里" % (item["key"], svg_id)
        # 非楼层的顶层组（shoreline 的 Stairs_Common）不该混进可选列表
        extra = [s for s in item["svgLayers"] if s not in selectable]
        assert "Stairs_Common" in extra or not extra, "只允许楼梯这类跨层共用组不被当成楼层"


def test_data_switchable_layers_appear_in_bands(data):
    """可切换层必须能在 bands 里被判定到，否则切了层也自动跟随不上。"""
    for item in data["maps"]:
        band_layers = {b["svgLayer"] for b in item["floors"]["bands"] if b["svgLayer"]}
        for switch in item["floors"]["switchable"]:
            assert switch["svgLayer"] in band_layers, "%s 的 %s 无法判定" % (item["key"], switch["svgLayer"])


def test_data_shoreline_first_floor_band(data):
    """海岸线底图里有独立的一层（First_Floor），上游却没给对应高度波段。

    没有补充波段时，度假村一层（y 约 -2.7～-4）的门与物资会被算进主层「地面层」，
    界面上切到「一层」就空无一物（含那些上锁的门）。这里锁死补充波段的判定：
    度假村内的低位点判成一层，度假村外的低位点不能跟着误判。
    """
    item = next(m for m in data["maps"] if m["key"] == "shoreline")
    band_layers = {b["svgLayer"] for b in item["floors"]["bands"]}
    assert "First_Floor" in band_layers, "海岸线一层缺少判定波段"
    assert "First_Floor" in [s["svgLayer"] for s in item["floors"]["selectable"]], "一层的按钮要在可选列表里"
    # 度假村一层的门（y≈-2.7，坐标落在度假村内）必须判成一层
    assert detect_band(item["floors"], -189.2, -2.70, -85.5)["svgLayer"] == "First_Floor"
    # 度假村外的低位地面点（y 同样落在 -5~-1）不能被误判成一层
    assert detect_band(item["floors"], -607.0, -4.0, -387.0)["svgLayer"] != "First_Floor"

