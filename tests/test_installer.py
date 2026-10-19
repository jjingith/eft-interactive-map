"""`tools/installer.py` 的测试：纯函数与安装流程（快捷方式 / 注册表用桩件替换）。

不真的建 .lnk、不真的写注册表——那两件事分别由 PowerShell 与 `winreg` 负责，
这里只验证**编排**：payload 复制到位、卸载器落地、快捷方式数量对、注册的是安装目录。
"""

from __future__ import annotations

from pathlib import Path

import pytest

import installer
import serve


def test_installer_version_matches_serve():
    """安装器写进卸载项的版本号必须跟服务端版本一致（两处别各写各的）。"""
    assert installer.VERSION == serve.VERSION


def test_default_install_dir_uses_localappdata(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert installer.default_install_dir() == str(tmp_path / "EFTMap")


def test_shortcut_paths_use_app_name(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setattr(installer, "desktop_dir", lambda: str(tmp_path / "desk"))
    start, desk = installer.shortcut_paths()
    name = installer.APP_NAME + ".lnk"
    assert start.endswith(name) and "Start Menu" in start
    assert desk == str(tmp_path / "desk" / name)


def test_install_into_requires_payload(tmp_path, monkeypatch):
    monkeypatch.setattr(installer, "payload_root", lambda: str(tmp_path / "missing"))
    with pytest.raises(RuntimeError):
        installer.install_into(str(tmp_path / "out"))


def _stub_payload(tmp_path: Path) -> Path:
    payload = tmp_path / "payload"
    (payload / "_internal").mkdir(parents=True)
    (payload / installer.APP_EXE).write_bytes(b"app")
    (payload / "_internal" / "index.html").write_text("x", encoding="utf-8")
    return payload


def test_install_into_copies_payload_and_registers(tmp_path, monkeypatch):
    payload = _stub_payload(tmp_path)
    install_dir = tmp_path / "installed"
    shortcuts: list[str] = []
    registered: list[str] = []
    setup_exe = tmp_path / "setup.exe"
    setup_exe.write_bytes(b"setup")

    monkeypatch.setattr(installer, "payload_root", lambda: str(payload))
    monkeypatch.setattr(installer, "create_shortcut", lambda lnk, *a, **k: shortcuts.append(lnk))
    monkeypatch.setattr(installer, "write_uninstall_entry", lambda d: registered.append(d))
    monkeypatch.setattr(installer.sys, "executable", str(setup_exe))

    steps: list[str] = []
    installer.install_into(str(install_dir), desktop=True, on_step=steps.append)

    assert (install_dir / installer.APP_EXE).read_bytes() == b"app"
    assert (install_dir / "_internal" / "index.html").read_text(encoding="utf-8") == "x"
    assert (install_dir / installer.UNINSTALL_EXE).exists()        # 自己留一份当卸载器
    assert len(shortcuts) == 2                                     # 开始菜单 + 桌面
    assert registered == [str(install_dir)]
    assert steps and steps[-1] == "安装完成。"


def test_install_into_skips_desktop_shortcut_when_unchecked(tmp_path, monkeypatch):
    payload = _stub_payload(tmp_path)
    shortcuts: list[str] = []
    setup_exe = tmp_path / "setup.exe"
    setup_exe.write_bytes(b"setup")

    monkeypatch.setattr(installer, "payload_root", lambda: str(payload))
    monkeypatch.setattr(installer, "create_shortcut", lambda lnk, *a, **k: shortcuts.append(lnk))
    monkeypatch.setattr(installer, "write_uninstall_entry", lambda d: None)
    monkeypatch.setattr(installer.sys, "executable", str(setup_exe))

    installer.install_into(str(tmp_path / "installed"), desktop=False)
    assert len(shortcuts) == 1


def test_create_shortcut_builds_ascii_tmp_then_renames(tmp_path, monkeypatch):
    """WScript.Shell 会按系统 ANSI 代码页破坏中文名（`互动地图` → `????`），
    所以必须先建到纯 ASCII 临时名，再用 os.replace 改成真正的中文名。"""
    lnk = tmp_path / "EFT 互动地图.lnk"
    seen: dict = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        idx = cmd.index("-Lnk")
        passage = Path(cmd[idx + 1])
        assert passage.name.isascii(), "临时名必须是纯 ASCII，否则 WSH 仍会失败"
        passage.write_bytes(b"lnk-bytes")

        class _R:
            returncode = 0

        return _R()

    monkeypatch.setattr(installer.subprocess, "run", fake_run)
    installer.create_shortcut(str(lnk), r"C:\app\EFTMap.exe", r"C:\app", r"C:\app\EFTMap.exe")

    assert lnk.read_bytes() == b"lnk-bytes"                       # 已改名到中文名
    assert not (tmp_path / installer._TMP_LNK_NAME).exists()       # 临时名不残留
