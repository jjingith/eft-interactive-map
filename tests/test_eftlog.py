"""`tools/eftlog.py` 的测试。

日志目录与行格式都按**实测**的真实 EFT 日志复刻（见模块 docstring 的表格），
用 tmp_path 造会话目录与日志文件，不读真实游戏日志。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

import eftlog

SESSION = "log_2026.10.17_19-42-17_1.2.5.0.48146"
BASE = "2026.10.17_19-42-17_1.2.5.0.48146"       # 文件名里不带 `log_` 前缀
TS = "2026-10-17 19:52:43.123"


def make_session(root, session=SESSION, files=("application", "backend", "push-notifications", "errors")):
    """造一个真实结构的会话目录，返回其路径（`root` 是 `Logs` 目录）。"""
    path = Path(root) / session
    path.mkdir(parents=True, exist_ok=True)
    base = session[4:] if session.startswith("log_") else session
    for channel in files:
        (path / ("%s %s_000.log" % (base, channel))).write_text("", encoding="utf-8")
    return str(path)


@pytest.fixture
def game(tmp_path):
    """造一个像 `E:\\EFT` 的游戏根目录（里面有个空 `Logs`），返回其路径。

    LogFollower 收的是**游戏根目录**，`Logs` 由它自己拼；别把 Logs 目录本身传进去。
    """
    root = tmp_path / "EFT"
    (root / "Logs").mkdir(parents=True)
    return str(root)


def logs_of(game_dir):
    return os.path.join(game_dir, "Logs")


def log(session_dir, channel, *lines, ts=TS):
    """往某通道追加行（自动补时间戳前缀）。"""
    name = [n for n in os.listdir(session_dir) if n.endswith(" %s_000.log" % channel)][0]
    with open(os.path.join(session_dir, name), "a", encoding="utf-8") as fh:
        for line in lines:
            fh.write("%s | %s\n" % (ts, line))


def finder(**kw):
    """一个只负责累积事件的假 broadcaster。"""
    events = []

    class Fake:
        def publish(self, payload):
            events.append(("frame", payload))

        def publish_event(self, name, payload):
            events.append((name, payload))

    return Fake(), events


# --------------------------------------------------------------- 目录/文件名

def test_latest_session_picks_newest_directory(tmp_path):
    make_session(tmp_path, "log_2026.10.16_10-00-00_1.1.0.1.46777")
    make_session(tmp_path, "log_2026.10.17_19-42-17_1.2.5.0.48146")
    make_session(tmp_path, "log_2026.10.15_09-00-00_1.1.0.1.46777")
    newest = eftlog.latest_session(str(tmp_path))
    assert os.path.basename(newest) == SESSION


def test_latest_session_ignores_files_and_foreign_names(tmp_path):
    (tmp_path / SESSION).write_text("我是一个文件，不是目录", encoding="utf-8")
    (tmp_path / "logs_backup").mkdir()
    (tmp_path / "log_不合法").mkdir()
    assert eftlog.latest_session(str(tmp_path)) is None


def test_latest_session_missing_dir_returns_none(tmp_path):
    assert eftlog.latest_session(str(tmp_path / "nope")) is None


def test_session_base_and_channel_path(tmp_path):
    session = make_session(tmp_path)
    assert eftlog.session_base(session) == BASE
    assert os.path.basename(eftlog.channel_path(session, "application")) == "%s application_000.log" % BASE


def test_session_base_falls_back_to_directory_name(tmp_path):
    """文件还没生成时（游戏刚启动）只能从目录名推，必须去掉 `log_` 前缀。"""
    empty = Path(tmp_path) / SESSION
    empty.mkdir()
    assert eftlog.session_base(str(empty)) == BASE


# --------------------------------------------------------------- JSON 配平

def test_split_balanced_extracts_multiline_object():
    text = 'Got notification {\n  "type": "new_message",\n  "message": {"dt": 1}\n}\ntail'
    objects, rest = eftlog.split_balanced(text)
    assert len(objects) == 1
    assert json.loads(objects[0])["type"] == "new_message"
    assert rest == ""


def test_split_balanced_keeps_unclosed_tail():
    objects, rest = eftlog.split_balanced('{"a": {"b": 1}')
    assert objects == []
    assert rest == '{"a": {"b": 1}'


def test_split_balanced_ignores_braces_inside_strings():
    text = '{"text": "a } b { c"}[not json]'
    objects, _ = eftlog.split_balanced(text)
    assert len(objects) == 1
    assert json.loads(objects[0])["text"] == "a } b { c"


def test_split_balanced_extracts_two_objects():
    objects, _ = eftlog.split_balanced('{"a":1}\n{"b":2}')
    assert [json.loads(o) for o in objects] == [{"a": 1}, {"b": 2}]


# --------------------------------------------------------------- 通知解析

def notification(quest_id, suffix, has_rewards=False, items=None, dt=1760709163.0):
    message = {"type": "10", "text": "quest started", "hasRewards": has_rewards,
               "templateId": "%s %s" % (quest_id, suffix), "dt": dt}
    if items is not None:
        message["items"] = {"data": items}
    return json.dumps({"type": "new_message", "message": message})


def test_parse_notification_quest_started():
    ev = eftlog.parse_notification(notification("60e71e8ed54b755a3b53eb67", "description"))
    assert ev["type"] == "quest"
    assert ev["action"] == "started"
    assert ev["questId"] == "60e71e8ed54b755a3b53eb67"
    assert ev["ts"] == "2026-10-17 19:52:43.000" or ev["ts"].endswith(".000")


def test_parse_notification_quest_completed_counts_rewards():
    ev = eftlog.parse_notification(notification("5c0bd7d6d17c8f0dcd47a615", "successMessageText",
                                                has_rewards=True, items=[{}, {}, {}]))
    assert (ev["action"], ev["questId"], ev["rewards"], ev["hasRewards"]) == \
        ("completed", "5c0bd7d6d17c8f0dcd47a615", 3, True)


def test_parse_notification_completed_without_items_counts_zero():
    ev = eftlog.parse_notification(notification("q1", "successMessageText", has_rewards=True))
    assert ev["rewards"] == 0


@pytest.mark.parametrize("block", [
    "not json at all",
    "[]",
    '{"type": "something_else", "message": {"templateId": "q1 description"}}',
    '{"type": "new_message"}',
    '{"type": "new_message", "message": {"templateId": "nodescription"}}',
    '{"type": "new_message", "message": {"templateId": " description"}}',
    '{"type": "new_message", "message": {"templateId": "q1 unknownSuffix"}}',
])
def test_parse_notification_returns_none_for_noise(block):
    assert eftlog.parse_notification(block) is None


# --------------------------------------------------------------- 行解析

def test_parser_application_lifecycle_lines():
    parser = eftlog.LineParser()
    assert parser.feed(eftlog.APPLICATION, TS + " | MatchingCompleted:0 real:0 diff:0") == [
        {"type": "raid", "ts": TS, "phase": "matching"}]

    events = parser.feed(
        eftlog.APPLICATION,
        TS + " | scene preset path:maps/Sandbox_high_preset.bundle rcid:Sandbox_high.ScenesPreset.asset")
    assert events == [{"type": "raid", "ts": TS, "phase": "map", "mapId": "sandbox_high"}]

    assert parser.feed(eftlog.APPLICATION, TS + " | LocationLoaded:10.98 real:14.98 diff:4") == [
        {"type": "raid", "ts": TS, "phase": "loading"}]


def test_parser_raid_start_carries_transit_raid_id():
    parser = eftlog.LineParser()
    parser.feed(eftlog.APPLICATION,
                TS + " | [Transit] Flag:Common, RaidId:65f1a2b3c4d5e6f7a8b9c0d1, Count:0, Locations:Sandbox_high -> ")
    assert parser.feed(eftlog.APPLICATION, TS + " | PlayerSpawnEvent:22.21(22.21)") == [
        {"type": "raid", "ts": TS, "phase": "start", "raidId": "65f1a2b3c4d5e6f7a8b9c0d1"}]


def test_parser_backend_match_end():
    parser = eftlog.LineParser()
    assert parser.feed(eftlog.BACKEND, TS + ' | Request: client/match/local/end, responseText: ') == [
        {"type": "raid", "ts": TS, "phase": "end"}]
    assert parser.feed(eftlog.BACKEND, TS + ' | Request: client/quest/list, responseText: ') == []


def test_parser_errors_quest_failed():
    parser = eftlog.LineParser()
    assert parser.feed(eftlog.ERRORS, TS + " | Quest with id 5c0bd7d6d17c8f0dcd47a615 wasn't found! Side = Scav") == [
        {"type": "quest", "ts": TS, "action": "failed", "questId": "5c0bd7d6d17c8f0dcd47a615"}]


def test_parser_push_needs_full_balanced_object():
    parser = eftlog.LineParser()
    assert parser.feed(eftlog.PUSH, "Got notification {") == []
    assert parser.feed(eftlog.PUSH, '  "type": "new_message",') == []
    assert parser.feed(eftlog.PUSH, '  "message": {"templateId": "q1 description", "dt": 1}') == []
    events = parser.feed(eftlog.PUSH, "}")
    assert [e["questId"] for e in events] == ["q1"]


def test_parser_application_unknown_line_is_quiet():
    parser = eftlog.LineParser()
    assert parser.feed(eftlog.APPLICATION, TS + " | some totally unremarkable line") == []


# --------------------------------------------------------------- 跟随器

def test_follower_requires_game_dir():
    follower = eftlog.LogFollower(None)
    assert follower.enabled() is False
    assert follower.poll_once() == []
    snap = follower.snapshot()
    assert snap["available"] is False
    assert "未配置游戏目录" in snap["reason"]


def test_follower_reports_missing_logs_dir(tmp_path):
    follower = eftlog.LogFollower(str(tmp_path / "EFT"))
    assert follower.enabled() is True
    assert follower.poll_once() == []
    assert "日志目录不存在" in follower.snapshot()["reason"]


def test_follower_reports_no_session_yet(game):
    follower = eftlog.LogFollower(game)
    follower.poll_once()
    assert "还没有会话文件夹" in follower.snapshot()["reason"]


def test_follower_reads_existing_session_incrementally(game):
    session = make_session(logs_of(game))
    log(session, "application", "MatchingCompleted:0 real:0 diff:0")
    follower = eftlog.LogFollower(game, poll_interval=0.05)

    first = follower.poll_once()
    assert [e["phase"] for e in first] == ["matching"]

    # 没有新内容时不该重复产出
    assert follower.poll_once() == []

    log(session, "application", "PlayerSpawnEvent:22.21(22.21)")
    second = follower.poll_once()
    assert [e["phase"] for e in second] == ["start"]
    assert follower.snapshot()["raid"]["phase"] == "start"


def test_follower_collects_quests_and_trims_history(game):
    session = make_session(logs_of(game))
    follower = eftlog.LogFollower(game)
    follower.MAX_QUESTS = 3

    for i in range(5):
        log(session, "push-notifications", notification("quest%d" % i, "description", dt=1))
    follower.broadcaster = finder()[0]
    events = follower.poll_once()

    assert len(events) == 5
    quests = follower.snapshot()["quests"]
    assert [q["questId"] for q in quests] == ["quest2", "quest3", "quest4"]   # 只留最近 3 条


def test_follower_keeps_map_id_across_raid_phases(game):
    """快照只留最新一条 raid 事件，但地图 id 是更早的行给出的——必须串起来记住。

    否则页面在半途打开时拿不到 mapId，就没法「进图自动切地图」。
    """
    session = make_session(logs_of(game))
    follower = eftlog.LogFollower(game)
    for line in (
        "MatchingCompleted:0 real:0 diff:0",
        "scene preset path:maps/Bigmap_preset.bundle rcid:Bigmap.ScenesPreset.asset",
        "LocationLoaded:10.98 real:14.98 diff:4",
        "[Transit] Flag:Common, RaidId:65f1a2b3c4d5e6f7a8b9c0d1, Count:0, Locations:Bigmap -> ",
        "PlayerSpawnEvent:22.21(22.21)",
    ):
        log(session, "application", line)
    follower.poll_once()

    raid = follower.snapshot()["raid"]
    assert raid["phase"] == "start"
    assert raid["mapId"] == "bigmap"                     # 来自更早的 map 行
    assert raid["raidId"] == "65f1a2b3c4d5e6f7a8b9c0d1"


def test_merge_raid_resets_on_new_matching():
    prev = {"type": "raid", "ts": "t1", "phase": "start", "mapId": "bigmap", "raidId": "abc"}
    fresh = eftlog.merge_raid(prev, {"type": "raid", "ts": "t2", "phase": "matching"})
    assert fresh["mapId"] is None and fresh["raidId"] is None
    assert fresh["phase"] == "matching" and fresh["ts"] == "t2"

    identified = eftlog.merge_raid(fresh, {"type": "raid", "ts": "t3", "phase": "map", "mapId": "woods"})
    assert (identified["mapId"], identified["raidId"]) == ("woods", None)   # 上一局的 raidId 不该跟过来


def test_merge_raid_keeps_context_on_end():
    prev = {"type": "raid", "ts": "t1", "phase": "start", "mapId": "woods", "raidId": "abc"}
    ended = eftlog.merge_raid(prev, {"type": "raid", "ts": "t9", "phase": "end"})
    assert (ended["mapId"], ended["raidId"]) == ("woods", "abc")           # 便于复盘刚打完哪一局


def test_follower_broadcasts_named_events(game):
    session = make_session(logs_of(game))
    log(session, "application", "MatchingCompleted:0 real:0 diff:0")
    fake, events = finder()
    follower = eftlog.LogFollower(game, broadcaster=fake)
    follower.poll_once()
    assert events and events[0][0] == "raid"
    assert events[0][1]["phase"] == "matching"


def test_follower_switches_to_new_session(game):
    logs = logs_of(game)
    old = make_session(logs, "log_2026.10.16_10-00-00_1.1.0.1.46777")
    follower = eftlog.LogFollower(game)
    assert follower.poll_once() == []

    log(old, "application", "MatchingCompleted:0 real:0 diff:0")
    assert [e["phase"] for e in follower.poll_once()] == ["matching"]

    new = make_session(logs, SESSION)
    log(new, "application", "LocationLoaded:10.98 real:14.98 diff:4")
    events = follower.poll_once()
    assert os.path.basename(follower.snapshot()["session"]) == SESSION
    # 换会话后偏移清零，只读新会话里的行（旧会话的 matching 不会重放）
    assert [e["phase"] for e in events] == ["loading"]


def test_follower_survives_partial_last_line(game):
    """日志正在写、最后一行只写了一半时必须等下一轮，不能当成完整行解析。"""
    session = make_session(logs_of(game))
    name = "%s application_000.log" % BASE
    with open(os.path.join(session, name), "w", encoding="utf-8") as fh:
        fh.write(TS + " | MatchingCompleted:0 real:0 diff:0\n" + TS + " | PlayerSpawnEv")

    follower = eftlog.LogFollower(game)
    assert [e["phase"] for e in follower.poll_once()] == ["matching"]

    with open(os.path.join(session, name), "a", encoding="utf-8") as fh:
        fh.write("ent:22.21(22.21)\n")
    assert [e["phase"] for e in follower.poll_once()] == ["start"]


def test_follower_start_and_stop_are_safe(game):
    session = make_session(logs_of(game))
    log(session, "application", "MatchingCompleted:0 real:0 diff:0")
    follower = eftlog.LogFollower(game, poll_interval=0.05)
    follower.start()
    follower.stop()
    follower.stop()          # 可重复调用
    follower.start()         # 停掉之后还能再起
    follower.stop()


def test_application_tail_window_limits_initial_read(game):
    """新会话首次接入只回读尾部，避免一次吞掉几百 MB 的旧日志。"""
    session = make_session(logs_of(game))
    name = "%s application_000.log" % BASE
    with open(os.path.join(session, name), "w", encoding="utf-8") as fh:
        fh.write((TS + " | 填充行，用来把真正关心的行推出窗口\n") * 40000)
        fh.write(TS + " | MatchingCompleted:0 real:0 diff:0\n")

    follower = eftlog.LogFollower(game)
    follower.INITIAL_TAIL = 512
    assert [e["phase"] for e in follower.poll_once()] == ["matching"]


# --------------------------------------------------------------- 控制绑定（截图键同步）

# 复刻实测日志：整套设置被打成一个 JSON，`keyBindings` 里每项带 keyName + variants。
# 真实日志的这行里，截图键的 variants 是 `[{"keyCode":["V"]},{"keyCode":[]}]`。
CONTROLS_JSON = (
    '{"graphics":{"ssr":1},'
    '"keyBindings":['
    '{"keyName":"LeanLockRight","variants":[{"keyCode":["E"]},{"keyCode":[]}],"pressType":"Press"},'
    '{"keyName":"MakeScreenshot","variants":[{"keyCode":["V"]},{"keyCode":[]}],"pressType":"Press"},'
    '{"keyName":"ToggleInfo","variants":[{"keyCode":["I"]},{"keyCode":[]}],"pressType":"Press"}'
    ']}'
)


def controls_line(ts="2026-10-17 19:42:20.400", payload=CONTROLS_JSON):
    """实测格式：`时间|版本|Info|application|{...}`（注意是竖线直连，不是 ` | `）。"""
    return "%s|1.2.5.0.48146|Info|application|Settings updated on command line: %s\n" % (ts, payload)


def test_parse_controls_keys_extracts_all_bindings():
    keys = eftlog.parse_controls_keys(controls_line())
    assert keys["MakeScreenshot"] == "V"
    assert keys["ToggleInfo"] == "I"
    assert keys["LeanLockRight"] == "E"


def test_pick_screenshot_key():
    assert eftlog.pick_screenshot_key({"MakeScreenshot": "V", "ToggleInfo": "I"}) == "V"
    assert eftlog.pick_screenshot_key({"misc": "V"}) is None
    assert eftlog.pick_screenshot_key({}) is None


def test_parse_controls_keys_prefers_first_non_empty_variant():
    """首个变体为空时（如 `[{"keyCode":[]},{"keyCode":["F12"]}]`）要看下一个。"""
    payload = ('{"keyBindings":[{"keyName":"MakeScreenshot",'
               '"variants":[{"keyCode":[]},{"keyCode":["F12"]}]}]}')
    assert eftlog.pick_screenshot_key(eftlog.parse_controls_keys(payload)) == "F12"


def test_parse_controls_keys_tolerates_plain_string_variants():
    payload = '{"keyBindings":[{"keyName":"MakeScreenshot","variants":["V"]}]}'
    assert eftlog.pick_screenshot_key(eftlog.parse_controls_keys(payload)) == "V"


def test_parse_controls_keys_handles_dict_and_list_shapes():
    as_dict = '{"keyBindings":{"MakeScreenshot":{"variants":[{"keyCode":["B"]}]}}}'
    assert eftlog.pick_screenshot_key(eftlog.parse_controls_keys(as_dict)) == "B"

    keyed_by_name = '{"keyBindings":[{"name":"MakeScreenshot","key":"N"}]}'
    assert eftlog.pick_screenshot_key(eftlog.parse_controls_keys(keyed_by_name)) == "N"


def test_parse_controls_keys_returns_empty_without_bindings():
    assert eftlog.parse_controls_keys("就是一行普通日志，没有 JSON") == {}
    assert eftlog.parse_controls_keys('{"graphics":{"ssr":1}}') == {}
    assert eftlog.parse_controls_keys('{"keyBindings":[]}') == {}


def test_scan_screenshot_key_reads_file_head(tmp_path):
    path = tmp_path / "application_000.log"
    path.write_text(controls_line(), encoding="utf-8")
    assert eftlog.scan_screenshot_key(str(path)) == "V"


def test_scan_screenshot_key_missing_or_empty(tmp_path):
    assert eftlog.scan_screenshot_key(str(tmp_path / "ghost.log")) is None
    empty = tmp_path / "empty.log"
    empty.write_text("", encoding="utf-8")
    assert eftlog.scan_screenshot_key(str(empty)) is None


def test_scan_screenshot_key_respects_head_limit(tmp_path):
    """控制绑定在文件很前面，但若给出极小的头部窗口就应当读不到（验证真有做头部截取）。"""
    path = tmp_path / "application_000.log"
    path.write_text(("x" * 5000) + controls_line(), encoding="utf-8")
    assert eftlog.scan_screenshot_key(str(path), head_bytes=2048) is None
    assert eftlog.scan_screenshot_key(str(path), head_bytes=20000) == "V"


def test_read_screenshot_key_from_latest_session(game):
    logs = logs_of(game)
    old = make_session(logs, "log_2026.10.16_10-00-00_1.1.0.1.46777")
    with open(os.path.join(old, "2026.10.16_10-00-00_1.1.0.1.46777 application_000.log"),
              "w", encoding="utf-8") as fh:
        fh.write(controls_line())

    new = make_session(logs, SESSION)
    with open(os.path.join(new, "%s application_000.log" % BASE), "w", encoding="utf-8") as fh:
        fh.write(controls_line(payload=CONTROLS_JSON.replace('"V"', '"B"')))

    # 只认最新会话，所以拿到的是新会话里的键
    assert eftlog.read_screenshot_key(game) == "B"


def test_read_screenshot_key_falls_back_to_output_channel(game):
    session = make_session(logs_of(game))
    name = "%s output_000.log" % BASE
    with open(os.path.join(session, name), "w", encoding="utf-8") as fh:
        fh.write(controls_line())
    assert eftlog.read_screenshot_key(game) == "V"


def test_read_screenshot_key_without_game_dir_or_session(tmp_path):
    assert eftlog.read_screenshot_key(None) is None
    assert eftlog.read_screenshot_key(str(tmp_path / "EFT")) is None


def test_follower_screenshot_key_is_cached_per_session(game):
    session = make_session(logs_of(game))
    with open(os.path.join(session, "%s application_000.log" % BASE), "w", encoding="utf-8") as fh:
        fh.write(controls_line())
    follower = eftlog.LogFollower(game)

    calls = []
    original = eftlog.read_screenshot_key
    eftlog.read_screenshot_key = lambda *a, **k: (calls.append(1), original(*a, **k))[1]
    try:
        assert follower.screenshot_key() == "V"
        assert follower.screenshot_key() == "V"
        assert len(calls) == 1          # 同会话内只扫一次
    finally:
        eftlog.read_screenshot_key = original

    follower.poll_once()
    assert follower.screenshot_key() == "V"


def test_follower_screenshot_key_none_without_game_dir():
    follower = eftlog.LogFollower(None)
    assert follower.screenshot_key() is None

