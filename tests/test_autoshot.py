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


def make_shotter(tmp_path, *, enabled=False, key=None, interval_ms=1000,
                 phase=None, follower_key=None, foreground="C:\\EFT\\EscapeFromTarkov.exe"):
    """装好配置 + 替身的 AutoShotter；返回 (shotter, recorder, sent)。"""
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
    assert set(snap) == {"enabled", "intervalMs", "key", "sent", "lastSentAt", "available", "reason"}
    assert snap["intervalMs"] == 1500
    assert snap["available"] is True


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
