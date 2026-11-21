"""`serve.AutoShotter` / `serve.ScreenshotPruner` 的测试。

不真的发按键、也不真删文件：`sender` / `foreground` / `prune` 都是注入的替身，
所以测试不依赖本机是否有游戏，也不会打到任何窗口、动不了任何截图。配置与日志跟随器用替身或 tmp_path。
"""

from __future__ import annotations

import os

import pytest

import config
import serve


class FakeFollower:
    """只回答两件事：当前战局阶段、同步到的截图键。"""

    def __init__(self, phase=None, key=None):
        self.phase = phase
        self.key = key

    def snapshot(self):
        return {"raid": None if self.phase is None else {"phase": self.phase}}

    def screenshot_key(self):
        return self.key


class Recorder:
    """假 broadcaster：记下被推的命名事件。"""

    def __init__(self):
        self.events = []

    def publish(self, payload):
        self.events.append(("frame", payload))

    def publish_event(self, name, payload):
        self.events.append((name, payload))


@pytest.fixture(autouse=True)
def _no_real_control_ini(monkeypatch):
    """R107：AutoShotter 会优先读本机 Control.ini；测试必须与「本机装没装游戏」无关。"""
    monkeypatch.setattr(serve.eftlog, "read_screenshot_key_from_control_ini",
                        lambda path=None: None)


def make_shotter(tmp_path, *, enabled=False, key=None, interval_ms=1000,
                 phase=None, follower_key=None, foreground="C:\\EFT\\EscapeFromTarkov.exe"):
    """装好配置 + 替身的 AutoShotter；返回 (shotter, recorder, sent)。"""
    # R108：这些用例要验证 200ms～数秒的真实节奏，必须显式声明会员态，
    # 否则非会员会被服务端锁到 10000ms（见 test_member_gate）。
    config.set_member_state({"member": True, "member_status": "permanent"})
    config.save({"auto_screenshot": {"enabled": enabled, "interval_ms": interval_ms, "key": key}},
                str(tmp_path))
    sent = []

    def sender(name):
        sent.append(name)
        return True, ""

    recorder = Recorder()
    shotter = serve.AutoShotter(
        str(tmp_path),
        follower=FakeFollower(phase=phase, key=follower_key),
        broadcaster=recorder,
        sender=sender,
        foreground=foreground if callable(foreground) else (lambda: foreground),
    )
    return shotter, recorder, sent


# --------------------------------------------------------------- 三个门条件

def test_disabled_never_sends(tmp_path):
    shotter, recorder, sent = make_shotter(tmp_path, enabled=False, key="V", phase="start")
    assert shotter.poll_once(now=10.0) is False
    assert sent == []
    assert "未开启" in shotter.snapshot()["reason"]
    assert shotter.snapshot()["enabled"] is False


def test_missing_key_blocks_and_explains(tmp_path):
    shotter, _, sent = make_shotter(tmp_path, enabled=True, key=None, follower_key=None, phase="start")
    assert shotter.poll_once(now=10.0) is False
    assert sent == []
    assert "截图按键" in shotter.snapshot()["reason"]


def test_only_fires_inside_raid(tmp_path):
    for phase in (None, "matching", "map", "loading", "end"):
        shotter, _, sent = make_shotter(tmp_path, enabled=True, key="V", phase=phase)
        assert shotter.poll_once(now=10.0) is False, phase
        assert sent == [], phase


def test_only_fires_when_game_is_foreground(tmp_path):
    shotter, _, sent = make_shotter(tmp_path, enabled=True, key="V", phase="start",
                                    foreground="C:\\Program Files\\Google\\chrome.exe")
    assert shotter.poll_once(now=10.0) is False
    assert sent == []
    assert "不在前台" in shotter.snapshot()["reason"]


def test_foreground_unknown_process_blocks(tmp_path):
    shotter, _, sent = make_shotter(tmp_path, enabled=True, key="V", phase="start", foreground=None)
    assert shotter.poll_once(now=10.0) is False
    assert sent == []
    assert "无法确认" in shotter.snapshot()["reason"]


def test_blocked_reason_is_pushed_to_page_once(tmp_path):
    """被门条件拦住时也要把状态推给页面：否则页面停在上一次成功发送时的「已发送 N 张」，
    看不到「没在拍」的真实原因（用户实测时正是被这条误导）。"""
    shotter, recorder, sent = make_shotter(
        tmp_path, enabled=True, key="V", phase="start",
        foreground="C:\\Program Files\\Google\\chrome.exe")
    assert shotter.poll_once(now=10.0) is False
    shots = [e for e in recorder.events if e[0] == "shot"]
    assert len(shots) == 1
    assert "不在前台" in shots[0][1]["reason"]
    # 原因没变就不要重复推：轮询很密，重复推会把页面刷爆
    assert shotter.poll_once(now=10.5) is False
    assert len([e for e in recorder.events if e[0] == "shot"]) == 1


# --------------------------------------------------------------- 成功路径

def test_sends_key_when_all_gates_pass(tmp_path):
    shotter, recorder, sent = make_shotter(tmp_path, enabled=True, key="V", phase="start")
    assert shotter.poll_once(now=10.0) is True
    assert sent == ["V"]
    assert shotter.snapshot()["sent"] == 1
    assert shotter.snapshot()["available"] is True
    assert shotter.snapshot()["lastSentAt"] == 10.0
    shots = [e for e in recorder.events if e[0] == "shot"]
    assert len(shots) == 1 and shots[0][1]["sent"] == 1


def test_interval_throttles_repeated_sends(tmp_path):
    shotter, _, sent = make_shotter(tmp_path, enabled=True, key="V", phase="start", interval_ms=1000)
    assert shotter.poll_once(now=100.0) is True
    assert shotter.poll_once(now=100.5) is False       # 未到间隔
    assert sent == ["V"]
    assert shotter.poll_once(now=101.0) is True        # 到点再发
    assert sent == ["V", "V"]
    assert shotter.snapshot()["sent"] == 2


def test_key_falls_back_to_log_sync(tmp_path):
    shotter, _, sent = make_shotter(tmp_path, enabled=True, key=None, follower_key="V", phase="start")
    assert shotter.poll_once(now=10.0) is True
    assert sent == ["V"]
    assert shotter.snapshot()["key"] == "V"


def test_config_key_wins_over_log_sync(tmp_path):
    shotter, _, sent = make_shotter(tmp_path, enabled=True, key="F12", follower_key="V", phase="start")
    assert shotter.poll_once(now=10.0) is True
    assert sent == ["F12"]


def test_sender_failure_is_reported_not_raised(tmp_path):
    # R108：验证间隔节奏，声明会员态以保留 200–60000 的可调区间
    config.set_member_state({"member": True, "member_status": "permanent"})
    config.save({"auto_screenshot": {"enabled": True, "interval_ms": 1000, "key": "V"}}, str(tmp_path))
    sent = []

    def bad_sender(name):
        sent.append(name)
        return False, "按键未送达"

    shotter = serve.AutoShotter(str(tmp_path), follower=FakeFollower(phase="start"),
                                sender=bad_sender, foreground=lambda: "EscapeFromTarkov.exe")
    assert shotter.poll_once(now=10.0) is False
    assert shotter.snapshot()["sent"] == 0
    assert "未送达" in shotter.snapshot()["reason"]


def test_sender_exception_does_not_kill_poller(tmp_path):
    # R108：验证间隔节奏，声明会员态以保留 200–60000 的可调区间
    config.set_member_state({"member": True, "member_status": "permanent"})
    config.save({"auto_screenshot": {"enabled": True, "interval_ms": 1000, "key": "V"}}, str(tmp_path))

    def boom(name):
        raise OSError("no window")

    shotter = serve.AutoShotter(str(tmp_path), follower=FakeFollower(phase="start"),
                                sender=boom, foreground=lambda: "EscapeFromTarkov.exe")
    assert shotter.poll_once(now=10.0) is False
    assert "出错" in shotter.snapshot()["reason"]


# --------------------------------------------------------------- 快照与线程

def test_snapshot_shape(tmp_path):
    shotter, _, _ = make_shotter(tmp_path, enabled=True, key="V", interval_ms=1500)
    snap = shotter.snapshot()
    assert set(snap) == {"enabled", "intervalMs", "key", "sent", "lastSentAt", "available", "reason",
                         "mode", "arrived", "misses"}
    assert snap["intervalMs"] == 1500
    assert snap["available"] is True
    # R32：注入方式默认仍是扫描码（历史行为）；没做过校验时 arrived 必须是 None 而不是 False
    assert snap["mode"] == "scan"
    assert snap["arrived"] is None
    assert snap["misses"] == 0


def test_snapshot_reflects_interval_clamp(tmp_path):
    shotter, _, _ = make_shotter(tmp_path, enabled=True, key="V", interval_ms=5)
    assert shotter.snapshot()["intervalMs"] == config.SHOT_INTERVAL_MIN


def test_start_and_stop_are_safe(tmp_path):
    shotter, _, sent = make_shotter(tmp_path, enabled=True, key="V", phase="start", interval_ms=200)
    shotter.stop()               # 没启动过也能停
    shotter.start()
    shotter.stop()
    shotter.stop()               # 可重复
    assert shotter._thread is None


# =============================================================== R32 到货校验
# 「按键送出去了」不等于「截图产生了」。这里用真实的目录 + 手写 mtime 来验：
#   发键 → 记基线 → grace 内出现更新的文件 = 到货；一直没动静 = 没到货。

def shot_file(directory, name, mtime):
    path = directory / name
    path.write_text("x", encoding="utf-8")
    os.utime(str(path), (mtime, mtime))
    return path


def make_verified_shotter(tmp_path, *, directory, clock=None, key="V", interval_ms=1000):
    # R108：验证间隔节奏，声明会员态以保留 200–60000 的可调区间
    config.set_member_state({"member": True, "member_status": "permanent"})
    config.save({"auto_screenshot": {"enabled": True, "interval_ms": interval_ms, "key": key}},
                str(tmp_path))
    sent = []

    def sender(name):
        sent.append(name)
        return True, ""

    return serve.AutoShotter(
        str(tmp_path),
        follower=FakeFollower(phase="start"),
        broadcaster=Recorder(),
        sender=sender,
        foreground=lambda: "EscapeFromTarkov.exe",
        directory=str(directory),
        clock=clock or (lambda: 0.0),
    ), sent


def test_arrival_true_when_new_screenshot_appears(tmp_path):
    shots = tmp_path / "Screenshots"
    shots.mkdir()
    shot_file(shots, shot_name(0), 1000.0)

    shotter, sent = make_verified_shotter(tmp_path, directory=shots)
    assert shotter.poll_once(now=10.0) is True
    assert sent == ["V"]
    assert shotter.snapshot()["arrived"] is None          # 刚发出去，还没到判定时刻

    shot_file(shots, shot_name(1), 2000.0)                # 游戏把截图写出来了
    shotter.poll_once(now=10.4)                           # 过了 grace（1.2s）之前的一拍也算
    assert shotter.snapshot()["arrived"] is True
    assert shotter.snapshot()["misses"] == 0


def test_arrival_false_when_directory_stays_silent(tmp_path):
    shots = tmp_path / "Screenshots"
    shots.mkdir()
    shot_file(shots, shot_name(0), 1000.0)

    shotter, _ = make_verified_shotter(tmp_path, directory=shots)
    assert shotter.poll_once(now=10.0) is True
    shotter.poll_once(now=10.5)                           # 还在 grace 里，不下结论
    assert shotter.snapshot()["arrived"] is None

    shotter.poll_once(now=12.0)                           # 超过 1.2s 仍没动静
    assert shotter.snapshot()["arrived"] is False
    assert shotter.snapshot()["misses"] == 1
    assert "没有出现新截图" in shotter.snapshot()["reason"]


def test_two_misses_switch_injection_mode(tmp_path):
    """连续两次「没到货」就自己换成虚拟键码再试——别让用户去猜（参考实现就是 vk）。"""
    shots = tmp_path / "Screenshots"
    shots.mkdir()
    shot_file(shots, "old.png", 1000.0)

    shotter, sent = make_verified_shotter(tmp_path, directory=shots, interval_ms=200)
    shotter.poll_once(now=1.0)
    assert sent == ["V"]
    shotter.poll_once(now=3.0)                            # 第一次没到货（顺便发第二拍）
    assert shotter.snapshot()["arrived"] is False
    assert shotter.snapshot()["mode"] == "scan"

    shotter.poll_once(now=5.0)                            # 第二次没到货
    assert shotter.snapshot()["mode"] == "vk"
    assert "虚拟键" in shotter.snapshot()["reason"]
    assert len(sent) == 3


def test_arrival_note_survives_a_successful_send(tmp_path):
    """「没到货」的提示不能被下一拍的成功发送立刻清掉——否则用户根本看不到。"""
    shots = tmp_path / "Screenshots"
    shots.mkdir()
    shot_file(shots, "old.png", 1000.0)

    shotter, _ = make_verified_shotter(tmp_path, directory=shots, interval_ms=200)
    shotter.poll_once(now=1.0)
    shotter.poll_once(now=3.0)                            # 没到货 + 又发了一拍
    assert shotter.snapshot()["arrived"] is False
    assert "没有出现新截图" in shotter.snapshot()["reason"]


def test_arrival_note_clears_when_a_screenshot_finally_arrives(tmp_path):
    shots = tmp_path / "Screenshots"
    shots.mkdir()
    shot_file(shots, "old.png", 1000.0)

    shotter, _ = make_verified_shotter(tmp_path, directory=shots, interval_ms=200)
    shotter.poll_once(now=1.0)
    shotter.poll_once(now=3.0)
    assert shotter.snapshot()["arrived"] is False

    shot_file(shots, "new.png", 5000.0)
    shotter.poll_once(now=3.2)
    snap = shotter.snapshot()
    assert snap["arrived"] is True
    assert snap["misses"] == 0
    assert snap["reason"] is None


def test_arrival_skipped_without_directory(tmp_path):
    """不知道截图目录时不校验：arrived 保持 None，绝不能报「没到货」冤枉游戏。"""
    shotter, _, _ = make_shotter(tmp_path, enabled=True, key="V", phase="start", interval_ms=200)
    assert shotter.poll_once(now=10.0) is True
    shotter.poll_once(now=20.0)
    assert shotter.snapshot()["arrived"] is None
    assert shotter.snapshot()["misses"] == 0


def test_arrival_skipped_when_directory_does_not_exist(tmp_path):
    """目录配错了同样不下结论：把「目录设错了」误报成「游戏没截图」比不校验更糟。"""
    ghost = tmp_path / "NoSuchDir"
    shotter, _ = make_verified_shotter(tmp_path, directory=ghost, interval_ms=200)
    assert shotter.poll_once(now=1.0) is True
    shotter.poll_once(now=5.0)
    assert shotter.snapshot()["arrived"] is None
    assert shotter.snapshot()["misses"] == 0


# =============================================================== R19.44 归属判定
# 「手动截图永不删除」是硬承诺。旧实现把归属窗口写成 max(1.2, 间隔×0.8)，
# 非会员间隔锁到 10 秒后窗口变成 8 秒：用户在这段时间里手动拍的图会被误记进
# auto-screenshot-manifest.json，战局结束时被 RaidEndCleaner 删掉。
# 新规则：窗口固定 1.2 秒；窗口内必须**恰好一张**新图才归属，其余一律放弃并留日志。

def make_manifest_shotter(tmp_path, *, directory, interval_ms=1000, member=True):
    """带清理清单的 AutoShotter；返回 (shotter, sent, manifest)。"""
    config.set_member_state(
        {"member": member, "member_status": "permanent" if member else "none"})
    config.save({"auto_screenshot": {"enabled": True, "interval_ms": interval_ms, "key": "V"}},
                str(tmp_path))
    sent = []
    manifest = serve.ShotManifest(str(tmp_path))

    def sender(name):
        sent.append(name)
        return True, ""

    shotter = serve.AutoShotter(
        str(tmp_path),
        follower=FakeFollower(phase="start"),
        broadcaster=Recorder(),
        sender=sender,
        foreground=lambda: "EscapeFromTarkov.exe",
        directory=str(directory),
        clock=lambda: 0.0,
        manifest=manifest,
    )
    return shotter, sent, manifest


def test_manual_screenshot_inside_long_interval_window_is_not_recorded(tmp_path, capsys):
    """复现 R19.43 的数据丢失：非会员 10 秒档，用户在发键后 3 秒手动截图。

    修前窗口是 8 秒，这张手动图会被当成「自动截图到货」写进清单，战局结束被删。
    修后窗口固定 1.2 秒：超出窗口 → 放弃归属，不写清单，只留日志。
    """
    shots = tmp_path / "Screenshots"
    shots.mkdir()
    shot_file(shots, shot_name(0), 1000.0)

    shotter, sent, manifest = make_manifest_shotter(
        tmp_path, directory=shots, interval_ms=10000, member=False)
    assert shotter.poll_once(now=10.0) is True
    assert sent == ["V"]

    shot_file(shots, shot_name(1), 1500.0)   # 用户在发键后 3 秒手动按了截图键
    shotter.poll_once(now=13.0)

    snap = shotter.snapshot()
    assert snap["arrived"] is False
    assert "放弃" in snap["reason"]
    assert manifest.list() == [], "手动截图绝不能被写进清理清单"

    err = capsys.readouterr().err
    assert "[auto-shot]" in err and "放弃" in err, err


def test_multiple_new_screenshots_are_all_abandoned(tmp_path, capsys):
    """窗口里出现两张新图时无法区分来源 → 整批放弃，一张都不记。

    不能「猜最新那张是自动的」：猜错就是把用户的手动截图删掉。
    """
    shots = tmp_path / "Screenshots"
    shots.mkdir()
    shot_file(shots, shot_name(0), 1000.0)

    shotter, _, manifest = make_manifest_shotter(tmp_path, directory=shots)
    assert shotter.poll_once(now=10.0) is True

    shot_file(shots, shot_name(1), 1500.0)
    shot_file(shots, shot_name(2), 1501.0)
    shotter.poll_once(now=10.5)

    snap = shotter.snapshot()
    assert snap["arrived"] is False
    assert "放弃" in snap["reason"]
    assert "2 张" in snap["reason"]
    assert manifest.list() == []
    # 放弃归属不代表按键失败：不能计入 misses，更不能因此切换注入方式
    assert snap["misses"] == 0
    assert snap["mode"] == "scan"
    assert "[auto-shot]" in capsys.readouterr().err


def test_single_new_screenshot_within_window_is_recorded(tmp_path):
    """反向防过严：窗口内恰好一张新图，仍要正常归属并写清单（否则自动图永远删不掉）。"""
    shots = tmp_path / "Screenshots"
    shots.mkdir()
    shot_file(shots, shot_name(0), 1000.0)

    shotter, _, manifest = make_manifest_shotter(tmp_path, directory=shots)
    assert shotter.poll_once(now=10.0) is True

    path = shot_file(shots, shot_name(1), 1500.0)
    shotter.poll_once(now=10.4)

    snap = shotter.snapshot()
    assert snap["arrived"] is True
    assert snap["misses"] == 0
    assert manifest.list() == [os.path.abspath(str(path))]


def test_late_automatic_screenshot_is_skipped_even_on_member_interval(tmp_path):
    """窗口与发送间隔无关：会员 1 秒档下，1.2 秒后才写出的图同样放弃归属。

    这是刻意选择的漏删方向——宁可留下自动图，也不冒删手动图的风险。
    """
    shots = tmp_path / "Screenshots"
    shots.mkdir()
    shot_file(shots, shot_name(0), 1000.0)

    shotter, _, manifest = make_manifest_shotter(tmp_path, directory=shots, interval_ms=1000)
    assert shotter.poll_once(now=10.0) is True

    shot_file(shots, shot_name(1), 1500.0)
    shotter.poll_once(now=12.5)

    snap = shotter.snapshot()
    assert snap["arrived"] is False
    assert "超出" in snap["reason"]
    assert manifest.list() == []


def test_shoot_once_ignores_gates_and_interval(tmp_path):
    """「试拍一张」不受门条件与间隔限制：没开自动截图、不在战局、刚发过，都能发。"""
    shots = tmp_path / "Screenshots"
    shots.mkdir()
    config.save({"auto_screenshot": {"enabled": False, "interval_ms": 5000, "key": "V"}}, str(tmp_path))
    sent = []
    shotter = serve.AutoShotter(
        str(tmp_path), follower=FakeFollower(phase="map"),
        broadcaster=Recorder(), sender=lambda n: (sent.append(n), (True, ""))[1],
        foreground=lambda: "chrome.exe", directory=str(shots))
    result = shotter.shoot_once()
    assert result["ok"] is True and result["key"] == "V"
    assert result["verifying"] is True
    assert sent == ["V"]


def test_shoot_once_reports_missing_key(tmp_path):
    config.save({"auto_screenshot": {"enabled": False, "interval_ms": 1000, "key": None}}, str(tmp_path))
    shotter = serve.AutoShotter(str(tmp_path), follower=FakeFollower(phase="start"),
                                broadcaster=Recorder(), sender=lambda n: (True, ""),
                                foreground=lambda: "EscapeFromTarkov.exe")
    result = shotter.shoot_once()
    assert result["ok"] is False
    assert "截图按键" in result["reason"]


def test_combo_key_is_passed_through_unchanged(tmp_path):
    """组合键写法原样交给注入层（解析在 keyinput 里做），AutoShotter 不做二次加工。"""
    shotter, _, sent = make_shotter(tmp_path, enabled=True, key="Ctrl+Shift+F10", phase="start")
    assert shotter.poll_once(now=10.0) is True
    assert sent == ["Ctrl+Shift+F10"]


def test_worker_thread_sends_at_least_once(tmp_path):
    """把 TICK 压到很小，验证后台线程真的会按间隔发键（不停留在「只能手动调用」）。"""
    import time

    shotter, _, sent = make_shotter(tmp_path, enabled=True, key="V", phase="start", interval_ms=200)
    shotter.tick = 0.02
    shotter.start()
    try:
        deadline = time.monotonic() + 3
        while not sent and time.monotonic() < deadline:
            time.sleep(0.02)
    finally:
        shotter.stop()
    assert sent, "后台线程应至少发送一次"


# =============================================================== ScreenshotPruner
# 自动删除截图：这里只测「什么时候删、删完计什么数」，真正挑文件的规则在
# test_screenshot_prune.py 里；prune 是注入的替身，所以测试不真删任何文件。

def shot_name(i: int) -> str:
    return "2026-10-17[20-25]_-491.46, 22.09, -49.75_0.01288, 0.43846, -0.00628, 0.89864 (%d).png" % i


def make_pruner(tmp_path, *, enabled=False, since=None, directory="DIR", prune=None, clock=None):
    """装好配置 + 替身的 ScreenshotPruner；返回 (pruner, recorder, calls)。"""
    config.save({"auto_delete": {"enabled": enabled, "since": since}}, str(tmp_path))
    calls = []

    def fake_prune(directory_arg, cutoff, keep_newest):
        calls.append((directory_arg, cutoff, keep_newest))
        return [shot_name(len(calls))]

    recorder = Recorder()
    kwargs = {}
    if clock is not None:
        kwargs["clock"] = clock
    pruner = serve.ScreenshotPruner(directory, str(tmp_path), broadcaster=recorder,
                                    prune=prune or fake_prune, **kwargs)
    return pruner, recorder, calls


def test_pruner_disabled_does_nothing(tmp_path):
    pruner, recorder, calls = make_pruner(tmp_path, enabled=False, directory=str(tmp_path))
    assert pruner.poll_once() == []
    assert calls == []                       # 关着就压根不扫目录
    assert "未开启" in pruner.snapshot()["reason"]
    assert recorder.events == []


def test_pruner_without_directory_explains(tmp_path):
    pruner, _, calls = make_pruner(tmp_path, enabled=True, since=1.0, directory=None)
    assert pruner.poll_once() == []
    assert calls == []
    assert "截图目录" in pruner.snapshot()["reason"]


def test_pruner_arms_instead_of_deleting_on_first_run(tmp_path):
    """`since` 为空时先布防、这一轮一张都不删（手改配置或首次开启都不会清库）。"""
    pruner, _, calls = make_pruner(tmp_path, enabled=True, since=None, directory=str(tmp_path))
    assert pruner.poll_once(now=1700.0) == []
    assert calls == []
    assert config.load(str(tmp_path))["auto_delete"] == {"enabled": True, "since": 1700.0}
    assert "就绪" in pruner.snapshot()["reason"]


def test_pruner_deletes_and_counts(tmp_path):
    import screenshot

    directory = tmp_path / "Screenshots"
    directory.mkdir()
    for i in range(3):
        path = directory / shot_name(i)
        path.write_text("x", encoding="utf-8")
        os.utime(str(path), (1000 + i, 1000 + i))

    pruner, recorder, _ = make_pruner(tmp_path, enabled=True, since=0.0, directory=str(directory),
                                      prune=screenshot.prune)
    assert pruner.poll_once(now=50.0) == [shot_name(0), shot_name(1)]
    assert pruner.snapshot()["deleted"] == 2
    assert pruner.snapshot()["lastDeletedAt"] == 50.0
    assert [e[0] for e in recorder.events] == ["clean"]
    assert os.listdir(directory) == [shot_name(2)]        # 最新一张留给定位


def test_pruner_keeps_newest_for_position_tracking(tmp_path):
    """清完之后定位仍要能用——这是「保留最新 1 张」存在的理由。"""
    import screenshot

    directory = tmp_path / "Screenshots"
    directory.mkdir()
    for i in range(3):
        path = directory / shot_name(i)
        path.write_text("x", encoding="utf-8")
        os.utime(str(path), (1000 + i, 1000 + i))

    pruner, _, _ = make_pruner(tmp_path, enabled=True, since=0.0, directory=str(directory))
    pruner.poll_once()
    assert screenshot.latest_position(str(directory)) is not None


def test_pruner_reports_nothing_to_clean(tmp_path):
    """空目录什么都不删、也不推事件（这里用真的 prune，因为要验证「挑出来是空的」）。"""
    import screenshot

    empty = tmp_path / "Screenshots"
    empty.mkdir()
    pruner, recorder, _ = make_pruner(tmp_path, enabled=True, since=0.0, directory=str(empty),
                                      prune=screenshot.prune)
    assert pruner.poll_once() == []
    assert "暂无可清理" in pruner.snapshot()["reason"]
    assert pruner.snapshot()["deleted"] == 0
    assert recorder.events == []


def test_pruner_missing_directory_degrades(tmp_path):
    pruner, _, _ = make_pruner(tmp_path, enabled=True, since=0.0, directory=str(tmp_path / "ghost"))
    assert pruner.poll_once() == []
    assert "不存在" in pruner.snapshot()["reason"]


def test_pruner_rejects_garbage_files_without_crashing(tmp_path):
    """目录里混着垃圾文件名时只跳过，不抛异常也不误删。"""
    import screenshot

    directory = tmp_path / "Screenshots"
    directory.mkdir()
    (directory / "乱七八糟.tmp").write_text("x", encoding="utf-8")
    (directory / "2026-10-17[20-25]_123.png").write_text("x", encoding="utf-8")   # 无位置信息

    pruner, _, _ = make_pruner(tmp_path, enabled=True, since=0.0, directory=str(directory),
                               prune=screenshot.prune)
    assert pruner.poll_once() == []
    assert sorted(os.listdir(directory)) == ["2026-10-17[20-25]_123.png", "乱七八糟.tmp"]


def test_pruner_prune_error_propagates_from_poll_once(tmp_path):
    """`prune` 抛异常时 `poll_once` 会抛出——兜住它的是后台线程循环，不是这个函数。"""
    def boom(*_a):
        raise OSError("dir gone")

    pruner, _, _ = make_pruner(tmp_path, enabled=True, since=0.0, directory=str(tmp_path), prune=boom)
    with pytest.raises(OSError):
        pruner.poll_once()


def test_pruner_thread_survives_prune_error(tmp_path):
    """清理出错不能让监听线程死掉（否则「自动删除」会静默失效）。"""
    import time

    calls = []

    def flaky(*_a):
        calls.append(1)
        if len(calls) == 1:      # start() 自带的首轮，放过去
            return []
        raise OSError("dir gone")

    pruner, _, _ = make_pruner(tmp_path, enabled=True, since=0.0, directory=str(tmp_path), prune=flaky)
    pruner.poll_interval = 0.02
    pruner.start()
    try:
        deadline = time.monotonic() + 3
        while len(calls) < 3 and time.monotonic() < deadline:
            time.sleep(0.02)
        assert pruner._thread is not None and pruner._thread.is_alive()
    finally:
        pruner.stop()


def test_pruner_snapshot_shape(tmp_path):
    pruner, _, _ = make_pruner(tmp_path, enabled=True, since=123.0, directory=str(tmp_path))
    snap = pruner.snapshot()
    assert set(snap) == {"enabled", "since", "keepNewest", "deleted", "lastDeletedAt",
                         "available", "reason"}
    assert snap["enabled"] is True
    assert snap["since"] == 123.0
    assert snap["keepNewest"] == 1
    assert snap["available"] is True


def test_pruner_unavailable_when_no_directory_or_since(tmp_path):
    no_dir, _, _ = make_pruner(tmp_path, enabled=True, since=1.0, directory=None)
    assert no_dir.snapshot()["available"] is False
    no_since, _, _ = make_pruner(tmp_path, enabled=True, since=None, directory=str(tmp_path))
    assert no_since.snapshot()["available"] is False


def test_pruner_start_and_stop_are_safe(tmp_path):
    empty = tmp_path / "Screenshots"
    empty.mkdir()
    pruner, _, _ = make_pruner(tmp_path, enabled=True, since=0.0, directory=str(empty))
    pruner.stop()                 # 没启动过也能停
    pruner.start()
    pruner.stop()
    pruner.stop()                 # 可重复
    assert pruner._thread is None


def test_pruner_worker_thread_polls(tmp_path):
    """后台线程要真的在跑（否则「自动删除」只在启动那一刻生效）。"""
    import time

    directory = tmp_path / "Screenshots"
    directory.mkdir()
    pruner, _, calls = make_pruner(tmp_path, enabled=True, since=0.0, directory=str(directory))
    pruner.poll_interval = 0.02
    pruner.start()
    calls.clear()                 # start() 自己会先跑一轮，这里只看线程后续的轮次
    try:
        deadline = time.monotonic() + 3
        while not calls and time.monotonic() < deadline:
            time.sleep(0.02)
    finally:
        pruner.stop()
    assert calls, "后台线程应至少清理一轮"


# =============================================================== R32 跨机器拓扑
# 游戏装在另一台电脑（游戏目录是 UNC 网络路径）时，模拟按键**物理上打不到**对方的前台窗口。
# 这时必须直接说清楚并停下：硬发键只会把内容打进本机前台的程序里。

def test_network_game_dir_refuses_to_send(tmp_path):
    config.save({"game_dir": r"\\JJPC\EFT",
                 "auto_screenshot": {"enabled": True, "interval_ms": 1000, "key": "V"}},
                str(tmp_path))
    sent = []
    shotter = serve.AutoShotter(str(tmp_path), follower=FakeFollower(phase="start"),
                                broadcaster=Recorder(),
                                sender=lambda n: (sent.append(n), (True, ""))[1],
                                foreground=lambda: "EscapeFromTarkov.exe")
    assert shotter.poll_once(now=10.0) is False
    assert sent == []
    reason = shotter.snapshot()["reason"]
    assert "另一台电脑" in reason
    assert "JJPC" in reason


def test_network_game_dir_blocks_shoot_once(tmp_path):
    config.save({"game_dir": r"\\JJPC\EFT",
                 "auto_screenshot": {"enabled": True, "interval_ms": 1000, "key": "V"}},
                str(tmp_path))
    sent = []
    shotter = serve.AutoShotter(str(tmp_path), follower=FakeFollower(phase="start"),
                                broadcaster=Recorder(),
                                sender=lambda n: (sent.append(n), (True, ""))[1],
                                foreground=lambda: "EscapeFromTarkov.exe")
    result = shotter.shoot_once()
    assert result["ok"] is False
    assert sent == []
    assert "另一台电脑" in result["reason"]


def test_local_game_dir_is_not_blocked(tmp_path):
    """本地盘符不能被误判成网络路径（否则本地用户会被这条提示挡住）。"""
    config.save({"game_dir": r"D:/Games/EFT",
                 "auto_screenshot": {"enabled": True, "interval_ms": 1000, "key": "V"}},
                str(tmp_path))
    shotter, _, sent = make_shotter(tmp_path, enabled=True, key="V", phase="start")
    config.save({"game_dir": r"D:/Games/EFT",
                 "auto_screenshot": {"enabled": True, "interval_ms": 1000, "key": "V"}},
                str(tmp_path))
    assert shotter.poll_once(now=10.0) is True
    assert sent == ["V"]


# =============================================================== R32 跨机器拓扑
# 游戏装在另一台电脑（游戏目录是 UNC 网络路径）时，模拟按键**物理上打不到**对方的前台窗口。
# 这时必须直接说清楚并停下：硬发键只会把内容打进本机前台的程序里。

def test_network_game_dir_refuses_to_send(tmp_path):
    config.save({"game_dir": r"\\JJPC\\EFT",
                 "auto_screenshot": {"enabled": True, "interval_ms": 1000, "key": "V"}},
                str(tmp_path))
    sent = []
    shotter = serve.AutoShotter(str(tmp_path), follower=FakeFollower(phase="start"),
                                broadcaster=Recorder(),
                                sender=lambda n: (sent.append(n), (True, ""))[1],
                                foreground=lambda: "EscapeFromTarkov.exe")
    assert shotter.poll_once(now=10.0) is False
    assert sent == []
    reason = shotter.snapshot()["reason"]
    assert "另一台电脑" in reason
    assert "JJPC" in reason


def test_network_game_dir_blocks_shoot_once(tmp_path):
    config.save({"game_dir": r"\\JJPC\\EFT",
                 "auto_screenshot": {"enabled": True, "interval_ms": 1000, "key": "V"}},
                str(tmp_path))
    sent = []
    shotter = serve.AutoShotter(str(tmp_path), follower=FakeFollower(phase="start"),
                                broadcaster=Recorder(),
                                sender=lambda n: (sent.append(n), (True, ""))[1],
                                foreground=lambda: "EscapeFromTarkov.exe")
    result = shotter.shoot_once()
    assert result["ok"] is False
    assert sent == []
    assert "另一台电脑" in result["reason"]


def test_local_game_dir_is_not_blocked(tmp_path):
    """本地盘符不能被误判成网络路径（否则本地用户会被这条提示挡住）。"""
    config.save({"game_dir": r"D:\Games\EFT",
                 "auto_screenshot": {"enabled": True, "interval_ms": 1000, "key": "V"}},
                str(tmp_path))
    shotter, _, sent = make_shotter(tmp_path, enabled=True, key="V", phase="start")
    config.save({"game_dir": r"D:\Games\EFT",
                 "auto_screenshot": {"enabled": True, "interval_ms": 1000, "key": "V"}},
                str(tmp_path))
    assert shotter.poll_once(now=10.0) is True
    assert sent == ["V"]


def test_injected_game_dir_wins_over_config(tmp_path):
    """实际生效的游戏目录来自命令行/自动探测，配置文件里常常是空的——
    「是不是网络路径」必须按**生效的那个**判断，不能只读 config。"""
    config.save({"game_dir": None,
                 "auto_screenshot": {"enabled": True, "interval_ms": 1000, "key": "V"}},
                str(tmp_path))
    sent = []
    shotter = serve.AutoShotter(str(tmp_path), follower=FakeFollower(phase="start"),
                                broadcaster=Recorder(),
                                sender=lambda n: (sent.append(n), (True, ""))[1],
                                foreground=lambda: "EscapeFromTarkov.exe",
                                game_dir=r"\\JJPC\EFT")
    assert shotter.poll_once(now=10.0) is False
    assert sent == []
    assert "另一台电脑" in shotter.snapshot()["reason"]


def test_injected_game_dir_wins_over_config(tmp_path):
    """实际生效的游戏目录来自命令行/自动探测，配置文件里常常是空的——
    「是不是网络路径」必须按**生效的那个**判断，不能只读 config。"""
    config.save({"game_dir": None,
                 "auto_screenshot": {"enabled": True, "interval_ms": 1000, "key": "V"}},
                str(tmp_path))
    sent = []
    shotter = serve.AutoShotter(str(tmp_path), follower=FakeFollower(phase="start"),
                                broadcaster=Recorder(),
                                sender=lambda n: (sent.append(n), (True, ""))[1],
                                foreground=lambda: "EscapeFromTarkov.exe",
                                game_dir=r"\\JJPC\EFT")
    assert shotter.poll_once(now=10.0) is False
    assert sent == []
    assert "另一台电脑" in shotter.snapshot()["reason"]
