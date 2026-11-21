"""R108：会员态与两道截图门控。

覆盖用户要求的四类用例：
1. 非会员请求 5000ms → 实际生效 10000ms；
2. 非会员 3 秒内连续两次截图 → 位置只更新一次（解禁后取最新一张，不排队补发）；
3. 会员 5000ms → 按 5000ms 生效，且位置更新不节流；
4. 现有 interval 测试按新语义调整的说明见 test_config.py / test_autoshot.py 的注释。

这里的会员态来自**服务端下发**（`config.set_member_state` 写入进程内缓存），
本地配置文件里的 `account.member` 一律忽略，手改不再解锁。
"""

from __future__ import annotations

import os

import config
import serve


class FakeClock:
    """可手动推进的单调时钟（秒）。"""

    def __init__(self, start: float = 100.0):
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


def write_shot(directory, x: str, z: str, when: float) -> str:
    """写一个真实格式的截图文件名，并显式设置 mtime（latest_position 按 mtime 取最新）。"""
    name = "2026-11-08[12-00]_%s, 1.00, %s_0.0, 0.0, 0.0, 1.0 (0).png" % (x, z)
    path = os.path.join(str(directory), name)
    with open(path, "wb") as fh:
        fh.write(b"fake")
    os.utime(path, (when, when))
    return path


# --------------------------------------------------------------- 会员态单一入口

def test_default_is_non_member(tmp_path):
    assert config.default_config()["account"] == {"member": False}
    # 配置缺失 / 空目录 → 非会员，不抛异常
    assert config.is_member(str(tmp_path)) is False


def test_is_member_ignores_local_config_and_reads_server_state(tmp_path):
    # 手改本地配置不再能「解锁」
    config.save({"account": {"member": True}}, str(tmp_path))
    assert config.is_member(str(tmp_path)) is False

    # 只有服务端下发（cloud.py 收到 me / 登录 / 刷新响应后写入）才生效
    config.set_member_state({"member": True, "member_status": "permanent"})
    assert config.is_member(str(tmp_path)) is True
    config.set_member_state({"member": False, "member_status": "none"})
    assert config.is_member(str(tmp_path)) is False


# --------------------------------------------------------------- 门控 1：间隔

def test_non_member_interval_request_5000_becomes_10000(tmp_path):
    """非会员请求 5000ms → 实际生效 10000ms（存储、合并、运行时三层都锁）。"""
    assert config.clamp_interval(5000, member=False) == config.SHOT_INTERVAL_LOCKED_MS

    shot = config.normalize({"auto_screenshot": {"interval_ms": 5000}})["auto_screenshot"]
    assert shot["interval_ms"] == config.SHOT_INTERVAL_LOCKED_MS

    merged = config.merge_ui({}, {"auto_screenshot": {"interval_ms": 5000}})
    assert merged["auto_screenshot"]["interval_ms"] == config.SHOT_INTERVAL_LOCKED_MS

    # 运行时（AutoShotter.settings）同样不认 5000
    config.save({"auto_screenshot": {"enabled": True, "interval_ms": 5000, "key": "V"}},
                str(tmp_path))
    shotter = serve.AutoShotter(str(tmp_path), foreground=lambda: "")
    assert shotter.settings() == (True, config.SHOT_INTERVAL_LOCKED_MS, "V")


def test_member_interval_request_5000_stays_5000(tmp_path):
    """会员请求 5000ms → 按 5000ms 生效。"""
    assert config.clamp_interval(5000, member=True) == 5000

    config.set_member_state({"member": True, "member_status": "permanent"})
    shot = config.normalize({"auto_screenshot": {"interval_ms": 5000}})["auto_screenshot"]
    assert shot["interval_ms"] == 5000

    merged = config.merge_ui({}, {"auto_screenshot": {"interval_ms": 5000}})
    assert merged["auto_screenshot"]["interval_ms"] == 5000

    config.save({"auto_screenshot": {"enabled": True, "interval_ms": 5000, "key": "V"}},
                str(tmp_path))
    shotter = serve.AutoShotter(str(tmp_path), foreground=lambda: "")
    assert shotter.settings() == (True, 5000, "V")

    # 反过来：配置文件写 member=true 但服务端没下发 → 仍然按非会员锁 10000ms
    config.set_member_state(None)
    config.save({"account": {"member": True},
                 "auto_screenshot": {"enabled": True, "interval_ms": 5000, "key": "V"}},
                str(tmp_path))
    locked = serve.AutoShotter(str(tmp_path), foreground=lambda: "")
    assert locked.settings() == (True, config.SHOT_INTERVAL_LOCKED_MS, "V")


def test_member_interval_still_clamped_to_generic_range():
    assert config.clamp_interval(10, member=True) == config.SHOT_INTERVAL_MIN
    assert config.clamp_interval(999999, member=True) == config.SHOT_INTERVAL_MAX


# --------------------------------------------------------------- 门控 2：位置节流

def test_non_member_position_updates_once_per_10s(tmp_path):
    """非会员 3 秒内连续两次截图 → 位置只更新一次；解禁后取最新一张。"""
    clock = FakeClock()
    write_shot(tmp_path, "1.00", "1.00", when=clock.t - 10)
    tracker = serve.PositionTracker(str(tmp_path), member=lambda: False, clock=clock)

    assert tracker.poll_once() is True
    assert tracker.snapshot()["position"]["x"] == 1.00

    # 3 秒后出现第二张截图：仍在锁定期内，不扫描、不广播
    clock.advance(3)
    write_shot(tmp_path, "2.00", "2.00", when=clock.t)
    assert tracker.poll_once() is False
    assert tracker.snapshot()["position"]["x"] == 1.00
    # 再轮询一次也还是 False —— 不会因为「攒了两张」而补发
    assert tracker.poll_once() is False
    assert tracker.snapshot()["position"]["x"] == 1.00

    # 距上次接受满 10 秒后解禁，直接取最新的第二张
    clock.advance(7.5)
    assert tracker.poll_once() is True
    assert tracker.snapshot()["position"]["x"] == 2.00


def test_member_position_is_not_throttled(tmp_path):
    """会员：1 秒内连续两张截图都立即生效。"""
    clock = FakeClock()
    write_shot(tmp_path, "1.00", "1.00", when=clock.t - 10)
    tracker = serve.PositionTracker(str(tmp_path), member=lambda: True, clock=clock)

    assert tracker.poll_once() is True
    clock.advance(1)
    write_shot(tmp_path, "2.00", "2.00", when=clock.t)
    assert tracker.poll_once() is True
    assert tracker.snapshot()["position"]["x"] == 2.00


def test_force_bypasses_non_member_throttle(tmp_path):
    """进战局用 force=True 绕过：上一局坐标已无意义，不能等 10 秒。"""
    clock = FakeClock()
    write_shot(tmp_path, "1.00", "1.00", when=clock.t - 10)
    tracker = serve.PositionTracker(str(tmp_path), member=lambda: False, clock=clock)
    assert tracker.poll_once() is True

    clock.advance(1)
    write_shot(tmp_path, "2.00", "2.00", when=clock.t)
    assert tracker.poll_once() is False       # 正常轮询仍被节流
    assert tracker.poll_once(force=True) is True
    assert tracker.snapshot()["position"]["x"] == 2.00


def test_member_state_is_read_live_from_config(tmp_path):
    """会员态来自可调用对象：配置改成会员后无需重建 tracker。"""
    clock = FakeClock()
    write_shot(tmp_path, "1.00", "1.00", when=clock.t - 10)
    state = {"member": False}
    tracker = serve.PositionTracker(str(tmp_path), member=lambda: state["member"], clock=clock)
    assert tracker.poll_once() is True

    clock.advance(1)
    write_shot(tmp_path, "2.00", "2.00", when=clock.t)
    assert tracker.poll_once() is False       # 非会员被节流

    state["member"] = True
    assert tracker.poll_once() is True        # 立刻变成会员行为
