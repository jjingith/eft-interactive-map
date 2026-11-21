"""R278c：主程序随启随停截图识别宿主。

宿主（tools/scan.py）以前只存在于开发机的登录自启任务里；装好的客户端没有这个
进程，热键自然不会响应。客户端现在改成：服务就绪后由主程序拉起宿主，退出时收掉。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


class _FakePopen:
    instances: list["_FakePopen"] = []

    def __init__(self, cmd, **kwargs):
        self.cmd = list(cmd)
        self.kwargs = dict(kwargs)
        self.terminated = False
        self.killed = False
        self.returncode = None
        _FakePopen.instances.append(self)

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = 0

    def kill(self):
        self.killed = True
        self.returncode = -9

    def wait(self, timeout=None):
        return self.returncode


@pytest.fixture(autouse=True)
def _fresh_instances():
    _FakePopen.instances = []
    yield
    _FakePopen.instances = []


def _startup(tmp_path):
    import launcher

    tools = tmp_path / "tools"
    tools.mkdir(parents=True)
    (tools / "scan.py").write_text("# fake host\n", encoding="utf-8")
    startup = launcher.Startup(root=str(tmp_path), port=8799, open_browser=lambda url: None)
    startup.url = "http://127.0.0.1:8799"
    return launcher, startup


def test_frozen_build_starts_host_through_run_tool(tmp_path, monkeypatch):
    launcher, startup = _startup(tmp_path)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "EFTMap.exe"), raising=False)
    monkeypatch.setattr(launcher.subprocess, "Popen", _FakePopen)
    monkeypatch.delenv("EFT_OCR_HOST", raising=False)

    startup.start_ocr_host()

    assert len(_FakePopen.instances) == 1
    cmd = _FakePopen.instances[0].cmd
    assert cmd[0].endswith("EFTMap.exe")
    assert cmd[1] == "--run-tool", "冻结产物必须用同一份解释器跑随包脚本"
    assert cmd[2].endswith("scan.py")
    assert cmd[-2:] == ["--server", "http://127.0.0.1:8799"]


def test_source_mode_runs_scan_with_current_interpreter(tmp_path, monkeypatch):
    launcher, startup = _startup(tmp_path)
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(launcher.subprocess, "Popen", _FakePopen)
    monkeypatch.delenv("EFT_OCR_HOST", raising=False)

    startup.start_ocr_host()

    cmd = _FakePopen.instances[0].cmd
    assert cmd[0] == sys.executable
    assert cmd[1].endswith("scan.py")
    assert "--run-tool" not in cmd


def test_env_switch_disables_host(tmp_path, monkeypatch):
    launcher, startup = _startup(tmp_path)
    monkeypatch.setattr(launcher.subprocess, "Popen", _FakePopen)
    monkeypatch.setenv("EFT_OCR_HOST", "0")

    startup.start_ocr_host()
    assert _FakePopen.instances == []


def test_missing_script_does_not_raise(tmp_path, monkeypatch):
    launcher = _startup(tmp_path)[0]
    startup = launcher.Startup(root=str(tmp_path / "empty"), port=8799,
                               open_browser=lambda url: None)
    startup.url = "http://127.0.0.1:8799"
    monkeypatch.setattr(launcher.subprocess, "Popen", _FakePopen)
    monkeypatch.delenv("EFT_OCR_HOST", raising=False)

    startup.start_ocr_host()      # 不抛：宿主缺失不能拖垮主流程
    assert _FakePopen.instances == []


def test_stop_terminates_host(tmp_path, monkeypatch):
    launcher, startup = _startup(tmp_path)
    monkeypatch.setattr(launcher.subprocess, "Popen", _FakePopen)
    monkeypatch.delenv("EFT_OCR_HOST", raising=False)

    startup.start_ocr_host()
    host = _FakePopen.instances[0]
    startup.stop_ocr_host()
    assert host.terminated is True
    assert startup.ocr_host is None


def test_run_starts_host_after_browser(tmp_path, monkeypatch):
    """顺序锁死：服务/自检/开界面之后才起宿主（宿主启动会先探 /api/health）。"""
    launcher, startup = _startup(tmp_path)
    calls = []
    monkeypatch.setattr(startup, "step_check_data", lambda: calls.append("data"))
    monkeypatch.setattr(startup, "step_start_server", lambda: calls.append("server"))
    monkeypatch.setattr(startup, "step_self_check", lambda: calls.append("health"))
    monkeypatch.setattr(startup, "step_open_browser", lambda: calls.append("browser"))
    monkeypatch.setattr(startup, "start_ocr_host", lambda: calls.append("host"))

    startup.run()
    assert calls == ["data", "server", "health", "browser", "host"]
