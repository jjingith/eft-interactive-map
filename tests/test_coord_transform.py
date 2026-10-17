"""坐标变换测试：仿射系数推导、旋转、以及"标注必须落在底图内"的数据校验。"""

import json
import re
from pathlib import Path

import pytest

from coord import compute_world_to_svg, world_to_svg

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "maps.json"

# 上游 the-hideout/tarkov-dev 的每图配置（原文抄录，用于锁定公式）
CUSTOMS = {
    "transform": [0.239, 168.65, 0.239, 136.35],
    "rotation": 180,
    "bounds": [[698, -307], [-372, 237]],
    "viewBox": [0.0, 0.0, 1062.4827, 535.17401],
}
FACTORY = {
    "transform": [1.629, 119.9, 1.629, 139.3],
    "rotation": 90,
    "bounds": [[77, -64.5], [-65.5, 67.4]],
    "viewBox": [0.0, 0.0, 130.81831, 141.23242],
}


def load_data():
    if not DATA.exists():
        pytest.skip("data/maps.json 不存在（需先运行 tools/fetch_data.py）")
    return json.loads(DATA.read_text(encoding="utf-8"))


def corners_of(cfg):
    (x1, z1), (x2, z2) = cfg["bounds"]
    return [(min(x1, x2), max(z1, z2)), (max(x1, x2), min(z1, z2))]


def approx_pair(actual, expected, tol=1e-6):
    return abs(actual[0] - expected[0]) <= tol and abs(actual[1] - expected[1]) <= tol


# --------------------------------------------------------------------------- #
# 基本不变式：矩形两角点必须正好映射到底图矩形的两个对角
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
@pytest.mark.parametrize("bounds", [[[0, 0], [100, 100]], [[100, 100], [0, 0]], [[100, 0], [0, 100]]])
def test_rect_corners_map_to_viewbox_corners(rotation, bounds):
    """bounds 的书写顺序不应影响结果：两个角点必须正好落在底图矩形的两个对角。

    旋转 90°/270° 时底图相对世界坐标是转过来的，因此落在 (0,H) 与 (W,0) 上。
    """
    viewbox = [0.0, 0.0, 100.0, 200.0]
    coeff = compute_world_to_svg([1.0, 0.0, 1.0, 0.0], rotation, bounds, viewbox)
    mapped = [world_to_svg(coeff, x, z) for x, z in ((0, 100), (100, 0))]
    expected = [(0.0, 0.0), (100.0, 200.0)] if rotation % 180 == 0 else [(0.0, 200.0), (100.0, 0.0)]
    for corner in expected:
        assert any(approx_pair(p, corner) for p in mapped), "缺角点 %s：%s" % (corner, mapped)
    assert len(mapped) == len(expected)


@pytest.mark.parametrize("cfg", [CUSTOMS, FACTORY], ids=["customs", "factory"])
def test_map_bounds_corners_hit_viewbox_exactly(cfg):
    coeff = compute_world_to_svg(cfg["transform"], cfg["rotation"], cfg["bounds"], cfg["viewBox"])
    w, h = cfg["viewBox"][2], cfg["viewBox"][3]
    mapped = [world_to_svg(coeff, x, z) for x, z in corners_of(cfg)]
    expected = [(0.0, 0.0), (w, h)] if cfg["rotation"] % 180 == 0 else [(0.0, h), (w, 0.0)]
    for corner in expected:
        assert any(approx_pair(p, corner, 1e-6) for p in mapped), "缺角点 %s：%s" % (corner, mapped)


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_quarter_turns_stay_axis_aligned(rotation):
    coeff = compute_world_to_svg([1.0, 0.0, 1.0, 0.0], rotation, [[0, 0], [100, 100]], [0, 0, 100, 100])
    assert abs(coeff["a"] * coeff["b"]) < 1e-12, "旋转 90° 整数倍不应产生混合项"
    assert abs(coeff["d"] * coeff["e"]) < 1e-12
    assert abs(coeff["a"]) + abs(coeff["b"]) > 0
    assert abs(coeff["d"]) + abs(coeff["e"]) > 0


def test_rotation_90_hand_mapped_values():
    # rot90、transform=[1,0,1,0]、单位矩形 → svgX = -z + 100，svgY = -x + 100
    coeff = compute_world_to_svg([1.0, 0.0, 1.0, 0.0], 90, [[0, 0], [100, 100]], [0, 0, 100, 100])
    assert approx_pair(world_to_svg(coeff, 0, 0), (100.0, 100.0))
    assert approx_pair(world_to_svg(coeff, 100, 0), (100.0, 0.0))
    assert approx_pair(world_to_svg(coeff, 0, 100), (0.0, 100.0))


def test_negative_rotation_normalized_like_270():
    a = compute_world_to_svg([1.0, 0.0, 1.0, 0.0], 270, [[0, 0], [100, 100]], [0, 0, 100, 100])
    b = compute_world_to_svg([1.0, 0.0, 1.0, 0.0], -90, [[0, 0], [100, 100]], [0, 0, 100, 100])
    for key in "abcdef":
        assert abs(a[key] - b[key]) < 1e-12


def test_degenerate_bounds_rejected():
    with pytest.raises(ValueError):
        compute_world_to_svg([1.0, 0.0, 1.0, 0.0], 0, [[0, 0], [0, 10]], [0, 0, 10, 10])
    with pytest.raises(ValueError):
        compute_world_to_svg([1.0, 0.0, 1.0, 0.0], 0, [[0, 0], [10, 10]], [0, 0, 0, 10])


# --------------------------------------------------------------------------- #
# 黄金值：锁定上游配置 → 系数的推导（防止改动引入回归）
# --------------------------------------------------------------------------- #
def test_customs_coefficients_match_golden():
    data = load_data()
    entry = next(m for m in data["maps"] if m["key"] == "customs")
    coeff = compute_world_to_svg(
        CUSTOMS["transform"], CUSTOMS["rotation"], CUSTOMS["bounds"], CUSTOMS["viewBox"]
    )
    for key in "abcdef":
        assert abs(entry["worldToSvg"][key] - coeff[key]) < 1e-9, key


def test_factory_coefficients_match_golden():
    data = load_data()
    entry = next(m for m in data["maps"] if m["key"] == "factory")
    coeff = compute_world_to_svg(
        FACTORY["transform"], FACTORY["rotation"], FACTORY["bounds"], FACTORY["viewBox"]
    )
    for key in "abcdef":
        assert abs(entry["worldToSvg"][key] - coeff[key]) < 1e-9, key


# --------------------------------------------------------------------------- #
# 数据校验：标注必须基本落在底图矩形内
# --------------------------------------------------------------------------- #
def _all_points(entry):
    points = []
    for layer in ("extracts", "transits", "spawns"):
        for item in entry["layers"][layer]:
            points.append((layer, item.get("name", ""), item["x"], item["z"]))
    for label in entry["labels"]:
        points.append(("label", label["text"], label["x"], label["z"]))
    return points


def test_markers_mostly_inside_viewbox():
    data = load_data()
    failures = []
    for entry in data["maps"]:
        w, h = entry["viewBox"][2], entry["viewBox"][3]
        points = _all_points(entry)
        if not points:
            continue
        outside = []
        for kind, name, x, z in points:
            sx, sy = world_to_svg(entry["worldToSvg"], x, z)
            nx, ny = sx / w, sy / h
            if not (-0.01 <= nx <= 1.01 and -0.01 <= ny <= 1.01):
                outside.append("%s/%s (%.2f, %.2f)" % (kind, name[:16], nx, ny))
        ratio = 1 - len(outside) / len(points)
        if ratio < 0.9:
            failures.append("%s: 仅 %.1f%% 落在底图内，越界示例 %s" % (entry["key"], ratio * 100, outside[:5]))
        else:
            # 允许少数上游自身越界的点，但要显式打印出来备查
            print("%-18s 内点比例 %.1f%%（越界 %d/%d）" % (entry["key"], ratio * 100, len(outside), len(points)))
    assert not failures, "\n".join(failures)


def test_shipped_svg_viewbox_matches_index():
    """底图文件自身的 viewBox 必须与索引一致，否则整张图会缩放错位。"""
    data = load_data()
    for entry in data["maps"]:
        path = ROOT / entry["svg"]
        assert path.exists(), "底图缺失：%s" % entry["svg"]
        tag = re.search(r"<svg\b[^>]*>", path.read_text(encoding="utf-8", errors="replace"))
        assert tag, "%s 不是合法 SVG" % entry["svg"]
        raw = re.search(r'viewBox="([-\d.eE+,\s]+)"', tag.group(0)).group(1)
        nums = [float(p) for p in re.split(r"[,\s]+", raw.strip()) if p]
        for got, want in zip(nums, entry["viewBox"]):
            assert abs(got - want) < 1e-6, "%s viewBox 不一致：%s vs %s" % (entry["svg"], nums, entry["viewBox"])


def test_svg_layer_id_exists_in_file():
    """索引里指定的 svgLayer 必须真的存在于底图里，否则前端会显示空白。"""
    data = load_data()
    for entry in data["maps"]:
        layer = entry.get("svgLayer")
        if not layer:
            continue
        text = (ROOT / entry["svg"]).read_text(encoding="utf-8", errors="replace")
        assert 'id="%s"' % layer in text, "%s 中找不到图层 %s" % (entry["svg"], layer)
