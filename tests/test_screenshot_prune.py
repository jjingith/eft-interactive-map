"""`screenshot.select_deletable` / `delete_files` / `prune` 的测试：挑文件与真删。

挑文件是纯函数（只读目录、不删），这里逐条钉住安全规则：只留最新、只删时间闸之后的、
只碰能解析出位置的；真删部分用 tmp_path 造真实文件。
"""

from __future__ import annotations

import os

import screenshot


def name_at(seconds: int, x: float = -491.46) -> str:
    """造一个可解析的截图文件名（`[n]` 只用来区分同秒重名，不影响解析）。"""
    return "2026-10-17[20-25]_%s, 22.09, -49.75_0.01288, 0.43846, -0.00628, 0.89864 (%d).png" % (x, seconds)


def unparsable_name(seconds: int) -> str:
    """没有位置信息的截图（实测里真有这种：只有日期时间和一个数字）。"""
    return "2026-10-17[20-25]_%d.png" % seconds


def make_shot(directory, name: str, mtime: float) -> str:
    path = os.path.join(directory, name)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("x")
    os.utime(path, (mtime, mtime))
    return path


def make_dir(tmp_path, shots):
    """shots = [(name, mtime)] → 建出目录与文件，返回目录路径。"""
    directory = tmp_path / "Screenshots"
    directory.mkdir()
    for name, mtime in shots:
        make_shot(str(directory), name, mtime)
    return str(directory)


# --------------------------------------------------------------- 挑选规则

def test_keeps_newest_one_parsable_shot(tmp_path):
    """定位靠最新那张，所以最新的必须留下，其余读过位置的可删。"""
    directory = make_dir(tmp_path, [(name_at(i), 1000 + i) for i in range(4)])
    chosen = screenshot.select_deletable(directory, cutoff=None)
    assert chosen == [name_at(0), name_at(1), name_at(2)]      # 按 mtime 升序，先旧后新
    assert name_at(3) not in chosen


def test_cutoff_protects_history(tmp_path):
    """只删开关打开之后产生的截图；历史截图一张都不动。"""
    directory = make_dir(tmp_path, [
        (name_at(0), 100),
        (name_at(1), 200),
        (name_at(2), 3000),
        (name_at(3), 4000),
    ])
    chosen = screenshot.select_deletable(directory, cutoff=1000.0)
    assert chosen == [name_at(2)]            # 100/200 是历史；4000 是最新，保留


def test_cutoff_none_means_no_time_gate(tmp_path):
    directory = make_dir(tmp_path, [(name_at(i), 1000 + i) for i in range(3)])
    assert screenshot.select_deletable(directory, cutoff=None) == [name_at(0), name_at(1)]


def test_unparsable_shots_are_never_deleted(tmp_path):
    """读不到位置的杂图不碰（用户手动拍的菜单截图等照旧留着）。"""
    directory = make_dir(tmp_path, [
        (unparsable_name(9), 1000),
        (name_at(1), 2000),
        (name_at(2), 3000),
    ])
    chosen = screenshot.select_deletable(directory, cutoff=None)
    assert chosen == [name_at(1)]
    assert unparsable_name(9) not in chosen
    assert os.path.exists(os.path.join(directory, unparsable_name(9)))


def test_single_shot_is_kept(tmp_path):
    directory = make_dir(tmp_path, [(name_at(0), 1000)])
    assert screenshot.select_deletable(directory, cutoff=None) == []


def test_empty_and_missing_directory(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    assert screenshot.select_deletable(str(empty), cutoff=None) == []
    assert screenshot.select_deletable(str(tmp_path / "ghost"), cutoff=None) == []


def test_keep_newest_is_configurable(tmp_path):
    directory = make_dir(tmp_path, [(name_at(i), 1000 + i) for i in range(5)])
    assert screenshot.select_deletable(directory, cutoff=None, keep_newest=2) == \
        [name_at(0), name_at(1), name_at(2)]
    assert screenshot.select_deletable(directory, cutoff=None, keep_newest=0) == \
        [name_at(i) for i in range(5)]


def test_non_image_files_ignored(tmp_path):
    directory = make_dir(tmp_path, [(name_at(0), 1000), (name_at(1), 2000)])
    with open(os.path.join(directory, "readme.txt"), "w", encoding="utf-8") as fh:
        fh.write("not a screenshot")
    assert screenshot.select_deletable(directory, cutoff=None) == [name_at(0)]


def test_selection_is_a_lightweight_scan(tmp_path):
    """挑文件就是「列目录 + 解析文件名」，用户的历史量级也要能秒回。"""
    shots = [(name_at(i), 1000 + i) for i in range(300)]
    directory = make_dir(tmp_path, shots)
    chosen = screenshot.select_deletable(directory, cutoff=1005.0)
    # mtime 1000~1004 被时间闸挡住（5 张），最新的 1299 保留（1 张），其余 294 张可删
    assert len(chosen) == 294
    assert chosen[0] == name_at(5)
    assert chosen[-1] == name_at(298)


# --------------------------------------------------------------- 真删

def test_delete_files_removes_and_reports(tmp_path):
    directory = make_dir(tmp_path, [(name_at(0), 1000), (name_at(1), 2000)])
    deleted = screenshot.delete_files(directory, [name_at(0)])
    assert deleted == [name_at(0)]
    assert not os.path.exists(os.path.join(directory, name_at(0)))
    assert os.path.exists(os.path.join(directory, name_at(1)))


def test_delete_files_skips_missing_without_raising(tmp_path):
    directory = make_dir(tmp_path, [(name_at(0), 1000)])
    deleted = screenshot.delete_files(directory, [name_at(0), "already-gone.png"])
    assert deleted == [name_at(0)]        # 删不掉的跳过，不抛异常


def test_prune_end_to_end_keeps_latest(tmp_path):
    directory = make_dir(tmp_path, [(name_at(i), 1000 + i) for i in range(4)])
    removed = screenshot.prune(directory, cutoff=None)
    assert len(removed) == 3
    left = os.listdir(directory)
    assert left == [name_at(3)]


def test_prune_leaves_tenable_position_for_tracker(tmp_path):
    """清完之后 `latest_position` 仍要能取到位置——否则实时定位就断了。"""
    directory = make_dir(tmp_path, [(name_at(i), 1000 + i) for i in range(3)])
    screenshot.prune(directory, cutoff=None)
    found = screenshot.latest_position(directory)
    assert found is not None
    assert found["name"] == name_at(2)
