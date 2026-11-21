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
    # R32：默认间隔从 1000 提到 5000（1 秒一张 = 每小时约 2 GB），断言改为盯常量
    # R108：默认是非会员，间隔落锁定值 10000ms
    assert cfg["auto_screenshot"] == {"enabled": False,
                                      "interval_ms": config.SHOT_INTERVAL_LOCKED_MS,
                                      "key": None, "cleanup_on_raid_end": False}
    assert cfg["account"] == {"member": False}   # R108：默认非会员
    assert cfg["auto_delete"] == {"enabled": False, "since": None}
    assert cfg["sound"]["enabled"] is False
    for key in config.SOUND_KEYS:
        assert cfg["sound"][key] == {"on": True, "file": None}
    assert cfg["host"] == config.HOST_DEFAULT       # 默认只监听本机回环


def test_clamp_host_whitelists_values():
    """监听地址只认白名单：0.0.0.0（局域网）/ 127.0.0.1（本机）；怪值一律回落回环。"""
    assert config.clamp_host("0.0.0.0") == "0.0.0.0"
    assert config.clamp_host("127.0.0.1") == config.HOST_DEFAULT
    assert config.clamp_host(" 0.0.0.0 ") == "0.0.0.0"      # 去掉首尾空白后仍走白名单
    for junk in (None, "", "192.168.1.5", "::", 42, True):
        assert config.clamp_host(junk) == config.HOST_DEFAULT


def test_normalize_keeps_only_whitelisted_host():
    assert config.normalize({"host": "0.0.0.0"})["host"] == "0.0.0.0"
    assert config.normalize({"host": "evil.example.com"})["host"] == config.HOST_DEFAULT


# --------------------------------------------------------------- 配装视图偏好

def test_clamp_sens_treats_zero_as_valid():
    """0 是合法的游戏内灵敏度，不能被当成「没填」丢掉。"""
    assert config.clamp_sens(0) == 0.0
    assert config.clamp_sens("0") == 0.0
    assert config.clamp_sens(0.4321) == 0.432
    assert config.clamp_sens(2) == 1.0
    assert config.clamp_sens(-1) == 0.0


@pytest.mark.parametrize("junk", [None, "", "abc", [], {}, True, False, float("nan"), float("inf")])
def test_clamp_sens_rejects_junk(junk):
    assert config.clamp_sens(junk) is None


def test_normalize_gear_keeps_only_given_slots():
    gear = config._normalize_gear({"helmet": "  h1  ", "armor": "", "rig": 42, "bogus": "x"})
    assert gear == {"helmet": "h1", "armor": None, "rig": None}
    assert config._normalize_gear(None) == {}
    for slot in config.GEAR_SLOTS:
        assert slot in ("helmet", "headphones", "glasses", "face", "armband", "dogtag",
                        "armor", "rig", "backpack",
                        "primary1", "primary2", "holster", "melee")


def test_normalize_ui_keeps_view_loadout_sens():
    ui = config.normalize({"ui": {"view": "loadout", "loadout": {"helmet": "h1"}, "sens": 0}})["ui"]
    assert ui["view"] == "loadout"
    assert ui["loadout"] == {"helmet": "h1"}
    assert ui["sens"] == 0.0
    assert "view" not in config.normalize({"ui": {"view": "nope"}})["ui"], "白名单外的视图名丢掉"


def test_normalize_ui_leaves_new_keys_absent_when_unset():
    ui = config.normalize({"ui": {"floor_auto": True}})["ui"]
    for key in ("view", "loadout", "sens"):
        assert key not in ui


def test_merge_ui_merges_loadout_per_slot_and_takes_view_sens():
    cfg = config.normalize({"ui": {"loadout": {"helmet": "h1", "armor": "a1"}, "view": "map"}})
    merged = config.merge_ui(cfg, {"ui": {"view": "gun", "loadout": {"armor": "a2"}, "sens": 0.25}})
    assert merged["ui"]["view"] == "gun"
    assert merged["ui"]["loadout"] == {"helmet": "h1", "armor": "a2"}, "未提到的槽位要保留"
    assert merged["ui"]["sens"] == 0.25


def test_normalize_fills_defaults_for_partial_input():
    cfg = config.normalize({"game_dir": "E:\\EFT"})
    assert cfg["game_dir"] == "E:\\EFT"
    assert cfg["screenshots_dir"] is None
    assert cfg["auto_center"] is True
    assert cfg["auto_screenshot"]["enabled"] is False
    assert cfg["auto_screenshot"]["interval_ms"] == config.SHOT_INTERVAL_LOCKED_MS
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
    config.set_member_state({"member": True, "member_status": "permanent"})
    cfg = config.normalize({
        # R108：会员才保留 200–60000 的任意值；配置里的 account.member 已不再生效，
        # 会员态只来自服务端下发（见 test_member_gate）
        "account": {"member": True},
        "auto_screenshot": {"enabled": "yes", "interval_ms": 1500, "key": "  V  "},
    })
    assert cfg["auto_screenshot"] == {"enabled": True, "interval_ms": 1500, "key": "V",
                                      "cleanup_on_raid_end": False}


def test_normalize_auto_screenshot_defaults_when_absent_or_wrong_type():
    for junk in (None, "on", 42, []):
        cfg = config.normalize({"auto_screenshot": junk})
        assert cfg["auto_screenshot"] == {"enabled": False,
                                          "interval_ms": config.SHOT_INTERVAL_LOCKED_MS,
                                          "key": None,
                                          "cleanup_on_raid_end": False}, junk


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


def test_merge_ui_can_toggle_auto_screenshot_without_touching_interval_or_key():
    """R106：左侧栏「自动截图」只写 enabled，间隔与截图键仍归启动器管。"""
    config.set_member_state({"member": True, "member_status": "permanent"})
    base = {"auto_screenshot": {"enabled": False, "interval_ms": 2500, "key": "F10"}}
    merged = config.merge_ui(base, {"auto_screenshot": {"enabled": True}})
    assert merged["auto_screenshot"] == {"enabled": True, "interval_ms": 2500, "key": "F10",
                                         "cleanup_on_raid_end": False}
    # 非布尔值不算「用户意图」，不要误开 / 误关
    assert config.merge_ui(base, {"auto_screenshot": {"enabled": "yes"}})["auto_screenshot"]["enabled"] is False


# --------------------------------------------------------------- 小地图五档米制半径（R106）

def test_default_mini_radius_is_the_middle_tier():
    assert config.default_config()["overlay"]["mini_radius_m"] == 100
    assert config.OVERLAY_MINI_RADIUS_CHOICES == (25, 50, 100, 200, 300)


@pytest.mark.parametrize("raw,expect", [
    (None, 100), ("abc", 100), (float("nan"), 100),
    (0, 25), (10, 25), (24, 25), (25, 25),
    (49, 50), (75, 100), (99, 100),     # 两档正中 → 取更大档（视野更宽）
    (150, 200), (260, 300), (999, 300),
    ("200", 200),
])
def test_nearest_mini_radius_snaps_to_five_tiers(raw, expect):
    assert config.nearest_mini_radius_m(raw) == expect


@pytest.mark.parametrize("map_scale,expect", [
    (1.0, 100),    # 旧默认：150 米视野高 = 半径 75 → 吸附到 100
    (3.0, 25),     # 旧最放大：半径 25
    (2.0, 50),     # 37.5 → 50
    (1.5, 50),
    (0.5, 200),    # 150 → 正中，取更大档
])
def test_old_map_scale_migrates_to_radius(map_scale, expect):
    cfg = config.normalize({"overlay": {"map_scale": map_scale}})
    assert cfg["overlay"]["mini_radius_m"] == expect


def test_explicit_mini_radius_wins_over_legacy_map_scale():
    """新键存在时不再看旧 map_scale（升级后的配置两份都在，不能被旧值拽回去）。"""
    cfg = config.normalize({"overlay": {"map_scale": 3.0, "mini_radius_m": 200}})
    assert cfg["overlay"]["mini_radius_m"] == 200


def test_merge_ui_accepts_mini_radius_and_migrates_legacy_map_scale():
    assert config.merge_ui({}, {"overlay": {"mini_radius_m": 300}})["overlay"]["mini_radius_m"] == 300
    # 旧客户端只发 map_scale 时也要生效（1.0 → 100，3.0 → 25）
    assert config.merge_ui({}, {"overlay": {"map_scale": 3.0}})["overlay"]["mini_radius_m"] == 25
    # 非档位值吸附，而不是原样落盘
    assert config.merge_ui({}, {"overlay": {"mini_radius_m": 123}})["overlay"]["mini_radius_m"] == 100


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


@pytest.mark.parametrize("raw,expect", [
    (0, 0.0),                                      # 新刻度允许 0%（迁移旧 0 / 负值的落点）
    (-1, 0.0),
    (5, 5.0),
    (9, config.ICON_SCALE_V2_MAX),                 # 上钳到新刻度右端
])
def test_clamp_icon_scale_v2_range(raw, expect):
    assert config.clamp_icon_scale(raw, v2=True) == expect


def test_normalize_ui_keeps_icon_scale_v2_flag():
    cfg = config.normalize({"ui": {"icon_scale": 5, "icon_scale_v2": True}})
    assert cfg["ui"] == {"icon_scale": 5.0, "icon_scale_v2": True}
    # 没有新刻度标记时仍按旧区间收敛，避免旧配置被误存成新刻度
    assert config.normalize({"ui": {"icon_scale": 9}})["ui"] == {"icon_scale": config.ICON_SCALE_MAX}


@pytest.mark.parametrize("raw,expect", [
    (0, 0.1),                                      # R98：低于 10% 钳到 10%
    (0.1, 0.1),
    (1.727, 1.727),                                # 旧百分比直接沿用，渲染尺寸不变
    (1.9, 1.9),
    (5.45, config.ICON_SCALE_V3_MAX),              # 超出 190% 钳到 190%
])
def test_clamp_icon_scale_v3_range(raw, expect):
    assert config.clamp_icon_scale(raw, v3=True) == expect


def test_normalize_ui_keeps_icon_scale_v3_flag():
    cfg = config.normalize({"ui": {"icon_scale": 1.727, "icon_scale_v3": True}})
    assert cfg["ui"] == {"icon_scale": 1.727, "icon_scale_v3": True}
    # v3 优先于 v2：同时带两个标记时按新刻度收敛，只保留 v3
    cfg = config.normalize({"ui": {"icon_scale": 2.5, "icon_scale_v2": True, "icon_scale_v3": True}})
    assert cfg["ui"] == {"icon_scale": 1.9, "icon_scale_v3": True}


def test_merge_ui_writes_icon_scale_without_touching_other_keys():
    base = {"ui": {"layers": {"loose": True}, "floor_auto": True}}
    merged = config.merge_ui(base, {"ui": {"icon_scale": 2.5}})
    assert merged["ui"] == {"layers": {"loose": True}, "floor_auto": True, "icon_scale": 2.5}


# --------------------------------------------------------------- 地名缩放 / 透明度

@pytest.mark.parametrize("raw,expect", [
    (None, config.LABEL_SCALE_DEFAULT),
    ("abc", config.LABEL_SCALE_DEFAULT),
    (float("nan"), config.LABEL_SCALE_DEFAULT),
    (0, config.LABEL_SCALE_MIN),                    # R98：0 / 负数钳到 10%，不再回落 100%
    (0.1, config.LABEL_SCALE_MIN),
    (9, config.LABEL_SCALE_MAX),
    ("1.6", 1.6),
])
def test_clamp_label_scale(raw, expect):
    assert config.clamp_label_scale(raw) == expect


@pytest.mark.parametrize("raw,expect", [
    (None, config.LABEL_ALPHA_DEFAULT),
    ("abc", config.LABEL_ALPHA_DEFAULT),
    (float("nan"), config.LABEL_ALPHA_DEFAULT),
    (-1, config.LABEL_ALPHA_MIN),                   # 负的透明度钳到 0
    (2, config.LABEL_ALPHA_MAX),                    # 超过 1 钳到 1
    (0, 0.0),                                       # 0 = 全透明是合法值，不能当脏值丢掉
    (0.35, 0.35),
])
def test_clamp_label_alpha(raw, expect):
    assert config.clamp_label_alpha(raw) == expect


def test_normalize_ui_keeps_label_scale_and_alpha_only_as_numbers():
    cfg = config.normalize({"ui": {"label_scale": 1.5, "label_alpha": 0.4, "junk": 1}})
    assert cfg["ui"] == {"label_scale": 1.5, "label_alpha": 0.4}
    assert config.normalize({"ui": {"label_scale": "big"}})["ui"] == {}
    assert config.normalize({"ui": {"label_alpha": False}})["ui"] == {}   # 布尔不算数字


def test_merge_ui_writes_label_prefs_without_touching_other_keys():
    base = {"ui": {"layers": {"loose": True}, "icon_scale": 1.2}}
    merged = config.merge_ui(base, {"ui": {"label_scale": 2.0, "label_alpha": 0.0}})
    assert merged["ui"] == {"layers": {"loose": True}, "icon_scale": 1.2,
                            "label_scale": config.LABEL_SCALE_MAX, "label_alpha": 0.0}


# --------------------------------------------------------------- R107 自动探测 / 清理
def test_normalize_keeps_log_dir_and_cleanup_flag():
    cfg = config.normalize({"log_dir": "  D:\\EFT\\Logs  ",
                            "auto_screenshot": {"cleanup_on_raid_end": True}})
    assert cfg["log_dir"] == "D:\\EFT\\Logs"
    assert cfg["auto_screenshot"]["cleanup_on_raid_end"] is True
    # 缺省必须是关：清理会删文件，不能默认开
    assert config.normalize({})["auto_screenshot"]["cleanup_on_raid_end"] is False


def test_merge_ui_accepts_interval_cleanup_and_manual_dirs():
    config.set_member_state({"member": True, "member_status": "permanent"})
    merged = config.merge_ui({}, {
        "auto_screenshot": {"interval_ms": 1234, "cleanup_on_raid_end": True},
        "log_dir": "  D:\\logs  ",
        "screenshots_dir": "D:\\shots",
    })
    assert merged["auto_screenshot"]["interval_ms"] == 1234
    assert merged["auto_screenshot"]["cleanup_on_raid_end"] is True
    assert merged["log_dir"] == "D:\\logs"
    assert merged["screenshots_dir"] == "D:\\shots"


def test_merge_ui_clamps_interval_from_page():
    # R108：会员态下才按 200–60000 钳；非会员一律 10000（见 test_member_gate）
    config.set_member_state({"member": True, "member_status": "permanent"})
    merged = config.merge_ui({}, {"auto_screenshot": {"interval_ms": 10}})
    assert merged["auto_screenshot"]["interval_ms"] == config.SHOT_INTERVAL_MIN
    merged = config.merge_ui({}, {"auto_screenshot": {"interval_ms": 999999}})
    assert merged["auto_screenshot"]["interval_ms"] == config.SHOT_INTERVAL_MAX


def test_merge_ui_clearing_dir_returns_to_auto_detect():
    """留空 = null，服务端下次探测回到自动识别。"""
    merged = config.merge_ui({"log_dir": "D:\\logs", "screenshots_dir": "D:\\shots"},
                             {"log_dir": None, "screenshots_dir": "   "})
    assert merged["log_dir"] is None
    assert merged["screenshots_dir"] is None

