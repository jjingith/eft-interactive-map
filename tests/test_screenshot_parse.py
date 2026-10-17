"""`tools/screenshot.py` 的测试：真实文件名解析、朝向约定回归、容错。

样本全部是 **真实截图文件名**（目录里 6588 张统计出来的形态），只含文件名与
文件时间戳，不含任何游戏资源。测试用 tmp_path 造目录，不碰用户的真实截图目录。
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

import screenshot

# --------------------------------------------------------------- 真实样本

# 6483/6588 张的形态：位置 + 四元数 + 额外值
WITH_EXTRA = "2026-09-16[20-25]_-491.46, 22.09, -49.75_0.01288, 0.43846, -0.00628, 0.89864_5.98 (0).png"
# 10 张的形态：没有额外值
NO_EXTRA = "2026-09-19[10-44]_65.66, 12.04, -944.35_0.00291, -0.99382, 0.00173, 0.11091 (0).png"
# 95 张的形态：完全没有位置信息（只有日期时间，或只有一个孤零零的数字）
ONLY_TIMESTAMP = "2026-09-16[20-22] (0).png"
LONELY_NUMBER = "2026-09-16[20-22]_9.40 (0).png"
LONELY_NUMBER_2 = "2026-09-16[20-24]_5.80 (0).png"
ONLY_TIMESTAMP_2 = "2026-09-18[20-55] (0).png"


@pytest.mark.parametrize(
    "name, x, y, z, yaw",
    [
        (WITH_EXTRA, -491.46, 22.09, -49.75, 52.005760373885636),
        (NO_EXTRA, 65.66, 12.04, -944.35, -167.26469152502364),
        ("2026-09-19[21-03]_-241.88, 0.62, -94.43_0.03500, -0.71294, 0.03668, 0.69939_10.41 (0).png",
         -241.88, 0.62, -94.43, -91.10915115579786),
        ("2026-09-16[20-18]_-2.43, 1.36, 7.12_-0.00928, 0.00511, 0.00005, 0.99994 (0).png",
         -2.43, 1.36, 7.12, 0.5854847631041568),
        ("2026-09-16[20-26]_-486.22, 22.38, -46.93_0.06357, 0.59631, -0.04745, 0.79883_6.11 (0).png",
         -486.22, 22.38, -46.93, 73.28268865421303),
        # 负四元数的等价表示（q 与 -q 是同一旋转）也要算对
        ("2026-09-16[20-27]_-448.47, 20.02, -42.94_-0.05021, -0.79960, 0.06781, -0.59457_6.24 (0).png",
         -448.47, 20.02, -42.94, 106.9610683586674),
    ],
)
def test_real_names_parse(name, x, y, z, yaw):
    got = screenshot.parse_screenshot_name(name)
    assert got is not None
    assert (got["x"], got["y"], got["z"]) == pytest.approx((x, y, z))
    assert got["yaw"] == pytest.approx(yaw, abs=1e-9)
    assert got["name"] == name


def test_parses_date_and_time():
    got = screenshot.parse_screenshot_name(WITH_EXTRA)
    assert got["date"] == "2026-09-16"
    assert got["time"] == "20-25"


@pytest.mark.parametrize("name", [ONLY_TIMESTAMP, LONELY_NUMBER, LONELY_NUMBER_2, ONLY_TIMESTAMP_2])
def test_names_without_position_return_none(name):
    """没有位置信息时返回 None —— 宁可没有定位，也不要误报一个假位置。"""
    assert screenshot.parse_screenshot_name(name) is None


def test_collects_the_95_unparseable_from_real_directory():
    """真实目录里那 95 张（仅有时间戳 / 仅有一个数字）一张都不该被解析出位置。"""
    import glob

    directory = r"C:\Users\imzjj\Documents\Escape from Tarkov\Screenshots"
    if not os.path.isdir(directory):
        pytest.skip("本机没有真实截图目录")
    bad = []
    for name in os.listdir(directory):
        if screenshot.PATTERN.match(name) and screenshot.parse_screenshot_name(name) is None:
            bad.append(name)
        if len(bad) >= 3:
            break
    assert bad, "预期真实目录里存在无位置信息的文件名"
    for name in bad:
        assert screenshot.parse_screenshot_name(name) is None


def test_partial_quaternions_are_rejected():
    """四元数缺一个分量就当解析失败，不允许「凑够一半也算」。"""
    assert screenshot.parse_screenshot_name("2026-09-16[20-25]_-491.46, 22.09, -49.75_0.1, 0.4, -0.0 (0).png") is None
    assert screenshot.parse_screenshot_name("2026-09-16[20-25]_-491.46, 22.09_0.1, 0.4, -0.0, 0.9 (0).png") is None


# --------------------------------------------------------------- 朝向约定回归

# 这两对是**真实相邻连拍**（文件 mtime 相差 < 3 s，位移 1.1~1.4 m，在走动）：
# 位移方向应与朝向一致，这是定标 (x,y,z,w) 约定的依据，这里固化成回归测试。
WALK_PAIRS = [
    (
        "2026-09-19[21-03]_-241.88, 0.62, -94.43_0.03500, -0.71294, 0.03668, 0.69939_10.41 (0).png",
        "2026-09-19[21-03]_-243.01, 0.60, -94.58_0.03515, -0.71293, 0.03653, 0.69940_10.41 (0).png",
    ),
    (
        "2026-09-19[21-03]_-254.30, 0.64, -94.37_0.04095, -0.70399, 0.04102, 0.70784_10.42 (0).png",
        "2026-09-19[21-03]_-255.63, 0.64, -94.36_0.03992, -0.71211, 0.04068, 0.69975_10.42 (0).png",
    ),
]


@pytest.mark.parametrize("first, second", WALK_PAIRS)
def test_yaw_matches_walking_direction_in_real_pairs(first, second):
    import math

    a = screenshot.parse_screenshot_name(first)
    b = screenshot.parse_screenshot_name(second)
    move_dir = math.degrees(math.atan2(b["x"] - a["x"], b["z"] - a["z"]))
    diff = abs(math.degrees(math.atan2(math.sin(math.radians(move_dir - a["yaw"])),
                                      math.cos(math.radians(move_dir - a["yaw"])))))
    assert diff <= 15.0, "真实连拍里朝向与位移方向相差 %.1f°，说明四元数约定被改坏了" % diff


def test_yaw_is_in_half_open_range():
    assert screenshot.yaw_from_quaternion(0.0, 1.0, 0.0, 0.0) == pytest.approx(180.0)   # 正好 180° 归一化到 +180
    for name in (WITH_EXTRA, NO_EXTRA):
        yaw = screenshot.parse_screenshot_name(name)["yaw"]
        assert -180.0 < yaw <= 180.0


def test_identity_quaternion_means_facing_positive_z():
    """四元数接近单位元 → 朝向 +z（yaw≈0）。这是 Unity 里「面朝 +z」的默认姿态。"""
    got = screenshot.parse_screenshot_name("2026-09-16[20-18]_-2.43, 1.36, 7.12_-0.00928, 0.00511, 0.00005, 0.99994 (0).png")
    assert abs(got["yaw"]) < 1.0


def test_world_forward_matches_convention():
    import math

    assert screenshot.world_forward(0.0) == pytest.approx((0.0, 1.0), abs=1e-12)
    assert screenshot.world_forward(90.0) == pytest.approx((1.0, 0.0), abs=1e-12)
    assert screenshot.world_forward(180.0) == pytest.approx((0.0, -1.0), abs=1e-12)
    assert screenshot.world_forward(-90.0) == pytest.approx((-1.0, 0.0), abs=1e-12)


# --------------------------------------------------------------- SVG 角度

# 海关的仿射系数（来自 data/maps.json，注意 a 与 e 符号相反：该图底图上下是反的）
CUSTOMS = {"a": -0.9929744859813084, "b": 0.0, "c": 693.0961912149533,
           "d": 0.0, "e": 0.9837757536764705, "f": 302.0191563786764}


@pytest.mark.parametrize("yaw, expected", [(0.0, 90.0), (90.0, 180.0), (180.0, -90.0), (-90.0, 0.0)])
def test_svg_angle_follows_map_axes(yaw, expected):
    """箭头角度必须过仿射线性部分：海关底图 +z 朝下、+x 朝左，不能直接用 yaw 当屏幕角。"""
    assert screenshot.svg_angle_degrees(CUSTOMS, yaw) == pytest.approx(expected, abs=1e-9)


def test_svg_angle_is_orthogonal_pair_agnostic():
    """朝向相差 90°，屏幕角也应相差 90°（仿射只做旋转+缩放，不破坏角度差）。"""
    a = screenshot.svg_angle_degrees(CUSTOMS, 0.0)
    b = screenshot.svg_angle_degrees(CUSTOMS, 90.0)
    assert (b - a) % 180.0 == pytest.approx(90.0, abs=1e-6)


def test_svg_angle_never_explodes_on_zero_coeff():
    assert screenshot.svg_angle_degrees({"a": 0, "b": 0, "c": 0, "d": 0, "e": 0, "f": 0}, 30.0) == 0.0


# --------------------------------------------------------------- 目录扫描

def test_latest_position_uses_mtime_not_name_order(tmp_path):
    """必须按 mtime 取最新：文件名里的 (n) 是重名去重序号，不是时间序。"""
    old = tmp_path / "2026-09-19[10-44]_1.00, 1.00, 1.00_0.0, 0.0, 0.0, 1.0_1.0 (9).png"
    new = tmp_path / "2026-09-19[10-45]_2.00, 2.00, 2.00_0.0, 0.0, 0.0, 1.0_1.0 (0).png"
    old.write_bytes(b"x")
    new.write_bytes(b"x")
    now = time.time()
    os.utime(old, (now - 100, now - 100))
    os.utime(new, (now, now))

    got = screenshot.latest_position(str(tmp_path))
    assert got["x"] == 2.00
    assert got["name"] == new.name


def test_latest_position_skips_unparseable_newest(tmp_path):
    """最新那张没有位置信息时，应往回找到最近一张有位置的，而不是直接放弃。"""
    good = tmp_path / "2026-09-19[10-44]_5.00, 5.00, 5.00_0.0, 0.0, 0.0, 1.0 (0).png"
    bad = tmp_path / "2026-09-19[10-45]_7.50 (0).png"
    good.write_bytes(b"x")
    bad.write_bytes(b"x")
    now = time.time()
    os.utime(good, (now - 50, now - 50))
    os.utime(bad, (now, now))

    assert screenshot.latest_position(str(tmp_path))["x"] == 5.00


def test_latest_position_returns_none_for_empty_or_missing_dir(tmp_path):
    assert screenshot.latest_position(str(tmp_path)) is None
    assert screenshot.latest_position(str(tmp_path / "nope")) is None
    assert screenshot.latest_position(None) is None


def test_latest_position_ignores_non_image_files(tmp_path):
    (tmp_path / "notes.txt").write_text("2026-09-19[10-44]_1.00, 1.00, 1.00_0.0, 0.0, 0.0, 1.0 (0).png")
    (tmp_path / "thumb.png.bak").write_bytes(b"x")
    assert screenshot.latest_position(str(tmp_path)) is None


def test_latest_position_reads_jpg_too(tmp_path):
    (tmp_path / "2026-09-19[10-44]_3.00, 3.00, 3.00_0.0, 0.0, 0.0, 1.0 (0).jpg").write_bytes(b"x")
    assert screenshot.latest_position(str(tmp_path))["z"] == 3.00


def test_list_screenshot_files_sorted_ascending(tmp_path):
    for i, name in enumerate(["a.png", "b.png", "c.png"]):
        p = tmp_path / name
        p.write_bytes(b"x")
        os.utime(p, (1000 + i, 1000 + i))
    got = screenshot.list_screenshot_files(str(tmp_path))
    assert [n for _, n in got] == ["a.png", "b.png", "c.png"]


# --------------------------------------------------------------- 容错

@pytest.mark.parametrize("value", [
    None, 123, "", "   ", "screenshot.png", "2026-09-19[10-44].png",
    "2026-09-19[10-44]_abc, def, ghi_1, 2, 3, 4 (0).png",
    "2026-13-99[99-99]_1, 2, 3_0, 0, 0, 1 (0).png",       # 日期格式对但内容非法也照样读得出来，不算异常
    "2026-09-19[10-44]_1, 2, 3_0, 0, 0, 1 (0).PNG",
    "\ufeff2026-09-16[20-25]_-491.46, 22.09, -49.75_0.01288, 0.43846, -0.00628, 0.89864_5.98 (0).png",
])
def test_never_raises(value):
    """扫描目录时什么怪名字都可能遇到，解析器只能返回 None，绝不能抛异常。"""
    got = screenshot.parse_screenshot_name(value)
    assert got is None or isinstance(got["x"], float)
