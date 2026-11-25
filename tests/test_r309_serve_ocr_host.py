"""R309：源码模式（`启动项目.bat` → serve.py）也要拉起截图识别宿主。

R308 移除启动器后，双击 bat 只起 serve.py；而注册全局热键的宿主
（tools/scan.py）原来只由 launcher.py 拉起，表现为「按 Ctrl+Alt+P 没反应、
没有框选窗」。现在 serve.py 在服务就绪后补上 spawn，退出时收掉。
"""

from __future__ import annotations

import sys

import serve

ROOT = None  # 占位，避免与 serve.ROOT 混淆


class _FakePopen:
    instances: list["_FakePopen"] = []

    def __init__(self, cmd, **kwargs):
        self.cmd = list(cmd)
        self.kwargs = dict(kwargs)
        self.terminated = False
        self.returncode = None
        _FakePopen.instances.append(self)

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = 0


def _reset() -> None:
    _FakePopen.instances = []


def _fake_root(tmp_path):
    tools = tmp_path / "tools"
    tools.mkdir(exist_ok=True)
    (tools / "scan.py").write_text("# fake host\n", encoding="utf-8")
    return tmp_path


def test_source_mode_spawns_scan_with_current_interpreter(tmp_path, monkeypatch):
    _reset()
    monkeypatch.setattr(serve, "ROOT", str(_fake_root(tmp_path)))
    monkeypatch.setattr(serve.subprocess, "Popen", _FakePopen)
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.delenv("EFT_OCR_HOST", raising=False)

    proc = serve.start_ocr_host("http://127.0.0.1:8787")

    assert proc is _FakePopen.instances[0]
    assert proc.cmd[0] == sys.executable
    assert proc.cmd[1].endswith("scan.py")
    assert "--run-tool" not in proc.cmd, "源码模式直接用当前解释器跑脚本"
    assert proc.cmd[-2:] == ["--server", "http://127.0.0.1:8787"]


def test_config_dir_is_forwarded_to_host(tmp_path, monkeypatch):
    _reset()
    monkeypatch.setattr(serve, "ROOT", str(_fake_root(tmp_path)))
    monkeypatch.setattr(serve.subprocess, "Popen", _FakePopen)
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.delenv("EFT_OCR_HOST", raising=False)

    serve.start_ocr_host("http://127.0.0.1:8787", str(tmp_path / "cfg"))

    assert _FakePopen.instances[0].cmd[-4:] == [
        "--server", "http://127.0.0.1:8787", "--config-dir", str(tmp_path / "cfg")]


def test_frozen_build_uses_run_tool(tmp_path, monkeypatch):
    _reset()
    monkeypatch.setattr(serve, "ROOT", str(_fake_root(tmp_path)))
    monkeypatch.setattr(serve.subprocess, "Popen", _FakePopen)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "EFTMap.exe"), raising=False)
    monkeypatch.delenv("EFT_OCR_HOST", raising=False)

    serve.start_ocr_host("http://127.0.0.1:8787")

    cmd = _FakePopen.instances[0].cmd
    assert cmd[0].endswith("EFTMap.exe")
    assert cmd[1] == "--run-tool"


def test_env_switch_disables_host(tmp_path, monkeypatch):
    _reset()
    monkeypatch.setattr(serve, "ROOT", str(_fake_root(tmp_path)))
    monkeypatch.setattr(serve.subprocess, "Popen", _FakePopen)
    monkeypatch.setenv("EFT_OCR_HOST", "0")

    assert serve.start_ocr_host("http://127.0.0.1:8787") is None
    assert _FakePopen.instances == []


def test_missing_script_returns_none(tmp_path, monkeypatch):
    _reset()
    monkeypatch.setattr(serve, "ROOT", str(tmp_path))
    monkeypatch.setattr(serve.subprocess, "Popen", _FakePopen)
    monkeypatch.delenv("EFT_OCR_HOST", raising=False)

    assert serve.start_ocr_host("http://127.0.0.1:8787") is None
    assert _FakePopen.instances == []


def test_main_starts_host_and_stops_it(tmp_path, monkeypatch):
    """顺序：服务 listen → 起宿主；Ctrl+C 退出时把宿主一起收掉。"""
    _reset()
    events: list[str] = []

    class _Host(_FakePopen):
        def __init__(self):
            super().__init__(["scan.py"], cwd=str(tmp_path))

        def terminate(self):
            events.append("host-stop")
            super().terminate()

    class _FakeHttpd:
        server_address = ("127.0.0.1", 8799)

        class shotter:
            @staticmethod
            def snapshot():
                return {"enabled": False}

        class pruner:
            @staticmethod
            def snapshot():
                return {"enabled": False}

        def serve_forever(self):
            raise KeyboardInterrupt

        def server_close(self):
            events.append("server-close")

    host = _Host()
    monkeypatch.setattr(serve, "resolve_settings",
                        lambda args: {"screenshots": None, "game_dir": None,
                                      "app_dir": str(tmp_path)})
    monkeypatch.setattr(serve, "create_server", lambda *a, **k: _FakeHttpd())
    monkeypatch.setattr(serve, "start_ocr_host",
                        lambda url, config_dir=None: events.append("host-start") or host)

    assert serve.main(["--port", "8799", "--no-browser"]) == 0
    assert events == ["host-start", "server-close", "host-stop"]
