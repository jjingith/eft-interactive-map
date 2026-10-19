"""`tools/config.py` 的测试：默认值收敛、读写容错、音频导入与解析。

这个模块是「配置的唯一定义处」，界面与 serve 都只通过它读写，
所以这里把「脏输入 → 干净配置」和「文件缺失/损坏不炸」两条底线钉死。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

import config


# --------------------------------------------------------------- 默认值与收敛

def test_default_config_shape_and_defaults():
    cfg = config.default_config()
    assert cfg["version"] == 1
    assert cfg["auto_center"] is True          # 点位自动居中默认开
    assert cfg["auto_zoom"] is False
    assert cfg["auto_start"] is False
    assert cfg["auto_screenshot"] == {"enabled": False, "interval_ms": 1000, "key": None}
    assert cfg["auto_delete"] == {"enabled": False, "since": None}
    assert cfg["sound"]["enabled"] is False
    for key in config.SOUND_KEYS:
        assert cfg["sound"][key] == {"on": True, "file": None}


def test_normalize_fills_defaults_for_partial_input():
    cfg = config.normalize({"game_dir": "E:\\EFT"})
    assert cfg["game_dir"] == "E:\\EFT"
    assert cfg["screenshots_dir"] is None
    assert cfg["auto_center"] is True
    assert cfg["auto_screenshot"]["enabled"] is False
    assert cfg["auto_screenshot"]["interval_ms"] == config.SHOT_INTERVAL_DEFAULT
    assert cfg["sound"]["enabled"] is False
    assert cfg["sound"]["matching"] == {"on": True, "file": None}


@pytest.mark.parametrize("junk", [None, "", 42, [], "not-a-dict"])
def test_normalize_survives_non_dict(junk):
    assert config.normalize(junk) == config.default_config()


def test_normalize_coerces_types():
    cfg = config.normalize({
        "game_dir": "  E:\\EFT  ",
        "screenshots_dir": "",
        "auto_zoom": "yes",
        "auto_center": 0,
        "auto_start": "1",
        "sound": {"enabled": "true", "matching": {"on": False, "file": "  bell.mp3 "}},
    })
    assert cfg["game_dir"] == "E:\\EFT"             # 两头空白去掉
    assert cfg["screenshots_dir"] is None           # 空串按没填处理
    assert cfg["auto_zoom"] is True
    assert cfg["auto_center"] is False
    assert cfg["auto_start"] is True
    assert cfg["sound"]["enabled"] is True
    assert cfg["sound"]["matching"] == {"on": False, "file": "bell.mp3"}
    # 未提到的子开关保持默认值，而不会被整体丢掉
    assert cfg["sound"]["raid_start"] == {"on": True, "file": None}


def test_normalize_ignores_wrong_typed_sound_block():
    cfg = config.normalize({"sound": "loud"})
    assert cfg["sound"]["enabled"] is False
    assert cfg["sound"]["raid_start"] == {"on": True, "file": None}


# --------------------------------------------------------------- 自动截图配置

def test_normalize_auto_screenshot_block():
    cfg = config.normalize({
        "auto_screenshot": {"enabled": "yes", "interval_ms": 1500, "key": "  V  "},
    })
    assert cfg["auto_screenshot"] == {"enabled": True, "interval_ms": 1500, "key": "V"}


def test_normalize_auto_screenshot_defaults_when_absent_or_wrong_type():
    for junk in (None, "on", 42, []):
        cfg = config.normalize({"auto_screenshot": junk})
        assert cfg["auto_screenshot"] == {"enabled": False, "interval_ms": 1000, "key": None}, junk


def test_normalize_empty_key_becomes_none():
    cfg = config.normalize({"auto_screenshot": {"enabled": True, "key": "   "}})
    assert cfg["auto_screenshot"]["key"] is None


@pytest.mark.parametrize("raw,expect", [
    (1500, 1500),
    ("1500", 1500),
    ("1000.7", 1000),
    (999999, config.SHOT_INTERVAL_MAX),   # 上限：间隔太大会拖到下一局才拍
    (1, config.SHOT_INTERVAL_MIN),        # 下限：间隔太短会让截图目录爆炸
    (-5, config.SHOT_INTERVAL_MIN),
    (None, config.SHOT_INTERVAL_DEFAULT),
    ("abc", config.SHOT_INTERVAL_DEFAULT),
    (True, config.SHOT_INTERVAL_MIN),     # True 会被当成 1，再被钳到下限
])
def test_clamp_interval(raw, expect):
    assert config.clamp_interval(raw) == expect


def test_clamp_interval_always_within_range():
    for raw in (-10 ** 9, 0, 199, 200, 60000, 60001, 10 ** 9):
        assert config.SHOT_INTERVAL_MIN <= config.clamp_interval(raw) <= config.SHOT_INTERVAL_MAX


def test_auto_screenshot_round_trips_through_file(tmp_path):
    saved = config.save({"auto_screenshot": {"enabled": True, "interval_ms": 250, "key": "V"}},
                        str(tmp_path))
    assert config.load(str(tmp_path))["auto_screenshot"] == saved["auto_screenshot"]


# --------------------------------------------------------------- 自动删除截图配置

def test_normalize_auto_delete_block():
    cfg = config.normalize({"auto_delete": {"enabled": "on", "since": 1700000000.5}})
    assert cfg["auto_delete"] == {"enabled": True, "since": 1700000000.5}


def test_normalize_auto_delete_defaults_when_absent_or_wrong_type():
    for junk in (None, "yes", 7, []):
        cfg = config.normalize({"auto_delete": junk})
        assert cfg["auto_delete"] == {"enabled": False, "since": None}, junk


def test_normalize_auto_delete_bad_since_becomes_none():
    """`since` 是「布防时刻」的时间闸，脏值必须收敛成 None（服务端会重新布防，不会误删）。"""
    for junk in ("", "abc", None, [], {}):
        cfg = config.normalize({"auto_delete": {"enabled": True, "since": junk}})
        assert cfg["auto_delete"]["since"] is None, junk


def test_normalize_auto_delete_accepts_numeric_strings():
    cfg = config.normalize({"auto_delete": {"since": "1700000000"}})
    assert cfg["auto_delete"]["since"] == 1700000000.0


def test_auto_delete_round_trips_through_file(tmp_path):
    saved = config.save({"auto_delete": {"enabled": True, "since": 1700000000.0}}, str(tmp_path))
    assert config.load(str(tmp_path))["auto_delete"] == saved["auto_delete"]


# --------------------------------------------------------------- 读写

def test_paths_are_under_given_directory(tmp_path):
    assert config.config_path(str(tmp_path)) == str(tmp_path / "eftmap.config.json")
    assert config.sounds_dir(str(tmp_path)) == str(tmp_path / "sounds")


def test_save_then_load_round_trip(tmp_path):
    saved = config.save({"auto_zoom": True, "game_dir": "E:\\EFT"}, str(tmp_path))
    assert saved["auto_zoom"] is True
    assert config.load(str(tmp_path)) == saved

    raw = json.loads((tmp_path / config.CONFIG_NAME).read_text(encoding="utf-8"))
    assert raw["auto_zoom"] is True          # 落盘的是收敛后的干净结构


def test_save_is_atomic_and_leaves_no_temp_file(tmp_path):
    config.save({"auto_zoom": True}, str(tmp_path))
    names = os.listdir(str(tmp_path))
    assert names == [config.CONFIG_NAME]


def test_load_falls_back_to_default_when_missing(tmp_path):
    assert config.load(str(tmp_path)) == config.default_config()


def test_load_falls_back_to_default_when_corrupt(tmp_path):
    (tmp_path / config.CONFIG_NAME).write_text("{ 不是 json", encoding="utf-8")
    assert config.load(str(tmp_path)) == config.default_config()


# --------------------------------------------------------------- 音频导入

def _audio(tmp_path, name, payload=b"fake-audio"):
    path = tmp_path / name
    path.write_bytes(payload)
    return str(path)


def test_import_sound_copies_into_sounds_dir(tmp_path):
    app = tmp_path / "app"
    app.mkdir()
    src = _audio(tmp_path, "my bell.mp3")
    name = config.import_sound(src, str(app))

    assert name == "my bell.mp3"
    dest = app / "sounds" / name
    assert dest.read_bytes() == b"fake-audio"
    assert config.resolve_sound(name, str(app)) == str(dest)


def test_import_sound_does_not_overwrite_existing(tmp_path):
    app = tmp_path / "app"
    app.mkdir()
    first = config.import_sound(_audio(tmp_path, "bell.wav", b"one"), str(app))
    second = config.import_sound(_audio(tmp_path, "bell.wav", b"two"), str(app))

    assert (first, second) == ("bell.wav", "bell_1.wav")
    assert (app / "sounds" / first).read_bytes() == b"one"     # 第一份没被覆盖
    assert (app / "sounds" / second).read_bytes() == b"two"


def test_import_sound_reuses_file_already_in_sounds_dir(tmp_path):
    app = tmp_path / "app"
    app.mkdir()
    src = _audio(tmp_path, "bell.mp3")
    name = config.import_sound(src, str(app))
    again = config.import_sound(str(app / "sounds" / name), str(app))
    assert again == name
    assert len(list((app / "sounds").iterdir())) == 1


@pytest.mark.parametrize("bad", ["bell.txt", "bell", "bell.exe"])
def test_import_sound_rejects_unsupported_extension(tmp_path, bad):
    with pytest.raises(ValueError):
        config.import_sound(_audio(tmp_path, bad), str(tmp_path / "app"))


def test_import_sound_rejects_missing_source(tmp_path):
    with pytest.raises(FileNotFoundError):
        config.import_sound(str(tmp_path / "nope.mp3"), str(tmp_path / "app"))


def test_import_sound_sanitizes_illegal_characters(tmp_path):
    app = tmp_path / "app"
    app.mkdir()
    # Windows 下拿不到带 `\` 的真实文件名，这里只验证清洗函数本身
    assert "/" not in config._safe_name("a/b?c")
    assert "*" not in config._safe_name("a*b")
    assert config._safe_name("") == "sound"


def test_resolve_sound_none_and_missing(tmp_path):
    app = tmp_path / "app"
    app.mkdir()
    assert config.resolve_sound(None, str(app)) is None
    assert config.resolve_sound("", str(app)) is None
    assert config.resolve_sound("ghost.mp3", str(app)) is None      # 文件不在就返回 None


def test_sounds_dir_created_on_demand(tmp_path):
    app = tmp_path / "app"
    app.mkdir()
    assert not (app / "sounds").exists()
    config.ensure_sounds_dir(str(app))
    assert (app / "sounds").is_dir()


def test_app_dir_is_repo_root_when_not_frozen():
    assert Path(config.app_dir()) == Path(__file__).resolve().parent.parent


# --------------------------------------------------------------- 用户级持久化目录

def test_default_storage_dir_prefers_appdata(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert Path(config.default_storage_dir()) == tmp_path / config.STORAGE_DIRNAME


def test_default_storage_dir_falls_back_to_home(monkeypatch):
    monkeypatch.delenv("APPDATA", raising=False)
    assert Path(config.default_storage_dir()) == Path.home() / ".eftmap"


def test_config_and_sounds_default_to_storage_dir(tmp_path, monkeypatch):
    """不传目录时读写都落在用户级目录：与软件目录解耦，重新打包 exe 不会带走设置。"""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert config.config_path() == str(tmp_path / config.STORAGE_DIRNAME / config.CONFIG_NAME)
    assert config.sounds_dir() == str(tmp_path / config.STORAGE_DIRNAME / "sounds")
    config.save({"auto_zoom": True})
    assert config.load()["auto_zoom"] is True


def test_migrate_legacy_moves_config_and_sounds(tmp_path):
    legacy = tmp_path / "app"
    legacy.mkdir()
    (legacy / config.CONFIG_NAME).write_text(json.dumps({"auto_zoom": True}), encoding="utf-8")
    sounds = legacy / "sounds"
    sounds.mkdir()
    (sounds / "bell.mp3").write_bytes(b"audio")
    (sounds / "notes.txt").write_text("x", encoding="utf-8")      # 非音频不搬

    dest = tmp_path / "userdir"
    moved = config.migrate_legacy(str(dest), str(legacy))

    assert sorted(moved) == sorted([config.CONFIG_NAME, "bell.mp3"])
    assert config.load(str(dest))["auto_zoom"] is True
    assert (dest / "sounds" / "bell.mp3").read_bytes() == b"audio"
    assert (legacy / config.CONFIG_NAME).is_file()                # 旧文件不删
    assert not (dest / "sounds" / "notes.txt").exists()


def test_migrate_legacy_never_overwrites_existing_destination(tmp_path):
    """用户目录里已经有配置时不动它——那才是最新的设置。"""
    legacy = tmp_path / "app"
    legacy.mkdir()
    (legacy / config.CONFIG_NAME).write_text(json.dumps({"auto_zoom": True}), encoding="utf-8")
    dest = tmp_path / "userdir"
    dest.mkdir()
    (dest / config.CONFIG_NAME).write_text(json.dumps({"auto_zoom": False}), encoding="utf-8")

    assert config.migrate_legacy(str(dest), str(legacy)) == []
    assert config.load(str(dest))["auto_zoom"] is False


def test_migrate_legacy_is_noop_without_legacy_files(tmp_path):
    assert config.migrate_legacy(str(tmp_path / "dest"), str(tmp_path / "empty")) == []


def test_migrate_legacy_ignores_identical_directories(tmp_path):
    legacy = tmp_path / "app"
    legacy.mkdir()
    (legacy / config.CONFIG_NAME).write_text(json.dumps({"auto_zoom": True}), encoding="utf-8")
    assert config.migrate_legacy(str(legacy), str(legacy)) == []


# --------------------------------------------------------------- 界面偏好（ui 块）

def test_ui_block_defaults_to_empty():
    """空 ui = 「还没在页面上保存过偏好」，前端据此回退到本地偏好，而不是被空偏好覆盖。"""
    assert config.default_config()["ui"] == {}


def test_normalize_ui_keeps_only_given_keys():
    cfg = config.normalize({"ui": {"layers": {"a": True, "b": "no"}, "floor_auto": True, "junk": 1}})
    assert cfg["ui"] == {"layers": {"a": True, "b": False}, "floor_auto": True}


@pytest.mark.parametrize("junk", [None, "on", 42, []])
def test_normalize_ui_survives_junk(junk):
    assert config.normalize({"ui": junk})["ui"] == {}


def test_normalize_ui_requires_real_booleans_for_floor_flags():
    """`floor_auto` / `floor_filter` 只认真布尔：别的类型（0/1、"yes"）都当没给。"""
    cfg = config.normalize({"ui": {"floor_auto": 1, "floor_filter": "yes"}})
    assert cfg["ui"] == {}


def test_ui_round_trips_through_file(tmp_path):
    saved = config.save({"ui": {"layers": {"loose": False}, "floor_filter": False}}, str(tmp_path))
    assert config.load(str(tmp_path))["ui"] == saved["ui"]


def test_merge_ui_only_overrides_given_keys():
    base = {"auto_zoom": True, "ui": {"layers": {"a": True, "b": True}, "floor_filter": False}}
    merged = config.merge_ui(base, {"ui": {"layers": {"a": False}}})
    assert merged["ui"]["layers"] == {"a": False, "b": True}
    assert merged["ui"]["floor_filter"] is False
    assert merged["auto_zoom"] is True


def test_merge_ui_can_set_auto_center():
    assert config.merge_ui({"auto_center": True}, {"auto_center": False})["auto_center"] is False
    # 没给 auto_center 就不要动它（页面拖图只是本地动作，不该被顺手写回）
    assert config.merge_ui({"auto_center": False}, {"ui": {"floor_auto": True}})["auto_center"] is False


@pytest.mark.parametrize("junk", [None, "x", 3, []])
def test_merge_ui_ignores_junk_prefs(junk):
    assert config.merge_ui({"auto_zoom": True}, junk)["auto_zoom"] is True


# --------------------------------------------------------------- 图标整体缩放

@pytest.mark.parametrize("raw,expect", [
    (None, config.ICON_SCALE_DEFAULT),
    ("abc", config.ICON_SCALE_DEFAULT),
    (float("nan"), config.ICON_SCALE_DEFAULT),      # json 里可以出现裸 NaN，别让它污染缩放系数
    (0, config.ICON_SCALE_DEFAULT),                 # 0 或负数没法当缩放系数
    (-2, config.ICON_SCALE_DEFAULT),
    (0.1, config.ICON_SCALE_MIN),                   # 下钳到滑条左端
    (9, config.ICON_SCALE_MAX),                     # 上钳到滑条右端
    (1, 1.0),
    ("1.6", 1.6),                                   # 手改配置文件写了字符串也认
])
def test_clamp_icon_scale(raw, expect):
    assert config.clamp_icon_scale(raw) == expect


def test_normalize_ui_keeps_icon_scale_only_as_a_number():
    cfg = config.normalize({"ui": {"icon_scale": 1.5, "junk": 1}})
    assert cfg["ui"] == {"icon_scale": 1.5}
    assert config.normalize({"ui": {"icon_scale": "big"}})["ui"] == {}
    assert config.normalize({"ui": {"icon_scale": True}})["ui"] == {}   # 布尔不算数字


def test_merge_ui_writes_icon_scale_without_touching_other_keys():
    base = {"ui": {"layers": {"loose": True}, "floor_auto": True}}
    merged = config.merge_ui(base, {"ui": {"icon_scale": 2.5}})
    assert merged["ui"] == {"layers": {"loose": True}, "floor_auto": True, "icon_scale": 2.5}

