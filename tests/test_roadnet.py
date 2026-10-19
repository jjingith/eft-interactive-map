"""路网构建脚本测试：路径解析、类解析、栅格化、2 bit 打包与产物完整性。

全部离线：只有 test_artifacts_* 会读 data/ 与 assets/roadnet/ 下的真实产出。
"""

import json
from pathlib import Path

import pytest

import roadnet as rn

ROOT = Path(__file__).resolve().parent.parent


# --------------------------------------------------------------------------- #
# 路径解析
# --------------------------------------------------------------------------- #
def test_parse_path_absolute_and_relative_mix():
    sub = rn.parse_path("M1 2 L3 4 h5 v6 Z", 1.0)
    assert len(sub) == 1
    assert sub[0]["closed"] is True
    assert sub[0]["pts"] == [(1.0, 2.0), (3.0, 4.0), (8.0, 4.0), (8.0, 10.0)]


def test_parse_path_implicit_lineto_after_moveto():
    """``M`` 之后的连续坐标对按 lineto 处理（SVG 规范如此，底图里大量使用）。"""
    sub = rn.parse_path("M0 0 10 0 10 10", 1.0)
    assert sub[0]["pts"] == [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)]
    assert sub[0]["closed"] is False


def test_parse_path_multiple_subpaths_and_unclosed():
    sub = rn.parse_path("M0 0 L1 1 M5 5 L6 6 Z", 1.0)
    assert len(sub) == 2
    assert sub[0]["closed"] is False
    assert sub[1]["pts"] == [(5.0, 5.0), (6.0, 6.0)]
    assert sub[1]["closed"] is True


def test_parse_path_cubic_is_flattened_within_bounds():
    sub = rn.parse_path("M0 0 C0 10 10 10 10 0", 1.0)
    pts = sub[0]["pts"]
    assert pts[0] == (0.0, 0.0) and pts[-1] == (10.0, 0.0)
    assert len(pts) >= rn.CURVE_MIN_STEPS
    assert all(0.0 <= x <= 10.0 and 0.0 <= y <= 10.0 for x, y in pts)


def test_parse_path_smooth_cubic_reuses_previous_control():
    rotated = rn.parse_path("M0 0 C0 10 10 10 10 0 S20 -10 20 0", 1.0)[0]["pts"]
    reflected = rn.parse_path("M0 0 C0 10 10 10 10 0 C10 -10 20 -10 20 0", 1.0)[0]["pts"]
    assert rotated[-len(reflected) // 2:] != [] and rotated[-1] == reflected[-1]


@pytest.mark.parametrize("d", ["", "M", "L1 1", "M1"])
def test_parse_path_tolerates_truncated_input(d):
    for sub in rn.parse_path(d, 1.0):
        assert len(sub["pts"]) >= 1


def test_parse_path_skips_arc_subpath():
    """底图里不该有弧线；真出现就丢掉这一条命令，而不是拿错几何去栅格化。"""
    sub = rn.parse_path("M0 0 A5 5 0 0 1 10 0 L20 0", 1.0)
    assert sub[0]["pts"] == [(0.0, 0.0), (20.0, 0.0)]   # 弧线没贡献任何点，后面的 L 照常


# --------------------------------------------------------------------------- #
# SVG 扫描与类解析
# --------------------------------------------------------------------------- #
def test_resolve_classes_prefers_leaf_then_nearest_ancestor():
    assert rn.resolve_classes({"road_small"}, [{"land"}, {"floor"}]) == {"road_small"}
    assert rn.resolve_classes(set(), [{"land"}, set(), {"floor"}]) == {"floor"}
    assert rn.resolve_classes(set(), [set(), set()]) == set()


def test_scan_layers_groups_by_top_level_group_and_skips_defs():
    svg = (
        '<svg><defs><path class="land" d="M0 0 L1 1 L0 1 Z"/></defs>'
        '<style>.land { fill:#000 }</style>'
        '<g id="Ground_Level"><g class="land"><path d="M0 0 L2 0 L2 2 Z"/></g>'
        '<polygon class="water" points="0,0 4,0 4,4"/></g>'
        '<g id="Second_Floor"><path d="M0 0 L1 0 L1 1 Z"/></g></svg>'
    )
    layers = rn.scan_layers(svg)
    assert list(layers) == ["Ground_Level", "Second_Floor"]
    assert [sorted(x["classes"]) for x in layers["Ground_Level"]] == [["land"], ["water"]]
    assert layers["Second_Floor"][0]["classes"] == set()      # 直属层组里没有类的叶子会被跳过
    assert layers["Ground_Level"][1]["d"].endswith("Z")        # polygon 被转写成等价的 path


def test_scan_layers_ignores_leaves_outside_any_layer_group():
    assert rn.scan_layers('<svg><path d="M0 0 L1 1 L0 1 Z"/></svg>') == {}


# --------------------------------------------------------------------------- #
# 栅格化
# --------------------------------------------------------------------------- #
def test_fill_path_fills_interior_square():
    grid = rn.Grid([0, 0, 10, 10], 1.0)
    grid.fill_path(rn.parse_path("M2 2 L8 2 L8 8 L2 8 Z", 1.0), rn.CODE_ROAD)
    assert grid.counts()["road"] == 36            # 6×6 格
    assert grid.codes[0] == rn.CODE_BLOCK         # 默认是禁行


def test_fill_path_uses_even_odd_rule_for_holes():
    """外框套内孔时，孔里要回到「禁行」——靠奇偶规则，不靠后画的覆盖。"""
    grid = rn.Grid([0, 0, 12, 12], 1.0)
    grid.fill_path(rn.parse_path("M0 0 L12 0 L12 12 L0 12 Z M4 4 L8 4 L8 8 L4 8 Z", 1.0), rn.CODE_TERRAIN)
    assert grid.codes[6 * 12 + 6] == rn.CODE_BLOCK     # 孔中心
    assert grid.codes[2 * 12 + 2] == rn.CODE_TERRAIN    # 环形部分
    assert grid.counts()["terrain"] == 144 - 16


def test_stroke_path_thickens_by_half_width():
    thin = rn.Grid([0, 0, 10, 10], 1.0)
    thin.stroke_path(rn.parse_path("M0 5 L10 5", 1.0), rn.CODE_ROAD, 0.1)
    thick = rn.Grid([0, 0, 10, 10], 1.0)
    thick.stroke_path(rn.parse_path("M0 5 L10 5", 1.0), rn.CODE_ROAD, 1.6)
    assert thin.counts()["road"] < thick.counts()["road"]


def test_grid_counts_reports_connectivity():
    grid = rn.Grid([0, 0, 10, 10], 1.0)
    grid.fill_path(rn.parse_path("M0 0 L2 0 L2 2 L0 2 Z", 1.0), rn.CODE_TERRAIN)
    grid.fill_path(rn.parse_path("M9 9 L10 9 L10 10 L9 10 Z", 1.0), rn.CODE_TERRAIN)
    counts = grid.counts()
    assert counts["terrain"] == 5
    assert counts["components"] == 2
    assert counts["largest"] == 4                 # 2×2 那块比 1×1 大


def test_encode_packs_two_bits_per_cell_low_first():
    blob = rn.encode(bytes([rn.CODE_BLOCK, rn.CODE_ROAD, rn.CODE_TERRAIN, rn.CODE_ROUGH]))
    assert blob == bytes([0b11_10_01_00])
    assert rn.encode(bytes([rn.CODE_ROUGH])) == bytes([0b000000_11])


def test_encode_pads_short_tail():
    assert len(rn.encode(bytes([1, 1, 1]))) == 1


# --------------------------------------------------------------------------- #
# 宽度与格子边长
# --------------------------------------------------------------------------- #
def test_half_width_prefers_inline_stroke_width():
    assert rn._half_width({"road_small"}, "stroke-width:7") == 3.5


def test_half_width_falls_back_to_class_table():
    assert rn._half_width({"road_large"}, "") == 6.0
    assert rn._half_width({"fence"}, "") == 0.5


def test_pick_cell_respects_short_side_and_cell_cap():
    assert rn.pick_cell([0, 0, 130, 141]) == 0.52          # 小图取到细度 0.52（下限 0.5 之上）
    big = rn.pick_cell([0, 0, 4000, 4000])
    assert int(4000 / big) * int(4000 / big) <= rn.MAX_CELLS


# --------------------------------------------------------------------------- #
# 绘制顺序：背景海面
# --------------------------------------------------------------------------- #
def test_first_ground_skips_water_drawn_before_the_ground():
    """灯塔那种「水画在陆地之前」的底图，水是海面底色，不能再压回陆地上。"""
    leaves = [
        {"classes": {"water"}, "d": "M0 0 L8 0 L8 8 L0 8 Z", "style": ""},
        {"classes": {"land"}, "d": "M2 2 L6 2 L6 6 L2 6 Z", "style": ""},
    ]
    assert rn._first_ground(leaves) == 1
    grid, count = rn.build_layer({"Ground_Level": leaves}, "Ground_Level", [0, 0, 8, 8], 1.0)
    assert count == 2
    assert grid.counts()["terrain"] == 16          # 海面没把 4×4 的陆地盖掉


def test_build_layer_carves_water_drawn_after_the_ground():
    """海关那种「水画在陆地之后」的底图，水是陆地里的河塘，要挖回禁行。"""
    leaves = [
        {"classes": {"land"}, "d": "M0 0 L8 0 L8 8 L0 8 Z", "style": ""},
        {"classes": {"water"}, "d": "M2 2 L6 2 L6 6 L2 6 Z", "style": ""},
    ]
    assert rn._first_ground(leaves) == 0
    grid, _ = rn.build_layer({"Ground_Level": leaves}, "Ground_Level", [0, 0, 8, 8], 1.0)
    assert grid.codes[3 * 8 + 3] == rn.CODE_BLOCK
    assert grid.counts()["terrain"] == 64 - 16


def test_first_ground_without_any_ground_never_skips():
    assert rn._first_ground([{"classes": {"water"}}, {"classes": {"trees"}}]) == 0


def test_build_layer_reports_leaf_count_even_when_all_ignored():
    leaves = [{"classes": {"shadow"}, "d": "M0 0 L4 0 L4 4 Z", "style": ""}]
    grid, count = rn.build_layer({"Ground_Level": leaves}, "Ground_Level", [0, 0, 8, 8], 1.0)
    assert count == 1
    assert grid.counts()["largest"] == 0


# --------------------------------------------------------------------------- #
# 产物
# --------------------------------------------------------------------------- #
def test_artifacts_present_for_every_registered_layer():
    index_path = ROOT / "data" / "roadnet.json"
    if not index_path.exists():
        pytest.skip("尚未构建路网（python tools/roadnet.py）")
    index = json.loads(index_path.read_text(encoding="utf-8"))
    assert index["schema"] == rn.SCHEMA
    assert index["maps"], "路网索引里一张图都没有"
    for key, item in index["maps"].items():
        assert item["cell"] > 0
        assert len(item["origin"]) == 2
        for layer_id, layer in item["layers"].items():
            path = ROOT / layer["file"]
            assert path.exists(), "%s/%s 位图缺失" % (key, layer_id)
            expect = (layer["w"] * layer["h"] + 3) // 4
            assert path.stat().st_size == expect == layer["bytes"]
            assert layer["cells"]["largest"] > 0, "%s/%s 没有任何可通行区域" % (key, layer_id)


def test_artifacts_cover_all_vector_maps_and_skip_tile_maps():
    index_path = ROOT / "data" / "roadnet.json"
    maps_path = ROOT / "data" / "maps.json"
    if not index_path.exists() or not maps_path.exists():
        pytest.skip("尚未构建数据（python tools/fetch_data.py）")
    index = json.loads(index_path.read_text(encoding="utf-8"))["maps"]
    maps = json.loads(maps_path.read_text(encoding="utf-8"))["maps"]
    for entry in maps:
        svg = ROOT / entry["svg"]
        vector = svg.exists() and "<path" in svg.read_text(encoding="utf-8", errors="replace")
        if vector:
            assert entry["key"] in index, "矢量图 %s 没有路网" % entry["key"]
        else:
            assert entry["key"] not in index, "瓦片底图 %s 不该有路网" % entry["key"]


def test_check_reports_no_problem(capsys):
    if not (ROOT / "data" / "roadnet.json").exists():
        pytest.skip("尚未构建路网")
    assert rn.check(quiet=True) == 0
