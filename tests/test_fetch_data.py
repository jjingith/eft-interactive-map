"""数据拉取脚本测试：解析辅助、规范化、幂等与失败不破坏已有产出。

全部离线：网络函数用桩件替换，只有 test_data_ready_* 会读真实产出。
"""

import json
from pathlib import Path

import pytest

import fetch_data as fd

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
    payload = {"schema": 1, "maps": maps if maps is not None else [{"key": "customs", "svg": "assets/maps/Customs.svg"}]}
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
