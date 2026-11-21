"""`tools/installer.py` 的测试：纯函数与安装流程（快捷方式 / 注册表用桩件替换）。

不真的建 .lnk、不真的写注册表——那两件事分别由 PowerShell 与 `winreg` 负责，
这里只验证**编排**：payload 复制到位、卸载器落地、快捷方式数量对、注册的是安装目录。
"""

from __future__ import annotations

import shutil
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


def test_webview2_version_reads_registry(monkeypatch):
    class _Key:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(installer.winreg, "OpenKey", lambda hive, sub: _Key())
    monkeypatch.setattr(installer.winreg, "QueryValueEx", lambda key, name: ("120.0.0.0", 1))
    assert installer.webview2_version() == "120.0.0.0"


def test_webview2_version_none_when_absent(tmp_path, monkeypatch):
    """注册表和目录都没有时返回 None（安装向导据此提示下载，不能抛异常）。"""
    def missing(*args, **kwargs):
        raise OSError("no key")

    monkeypatch.setattr(installer.winreg, "OpenKey", missing)
    monkeypatch.setenv("ProgramFiles(x86)", str(tmp_path / "pf86"))
    monkeypatch.setenv("ProgramFiles", str(tmp_path / "pf64"))
    assert installer.webview2_version() is None


def test_webview2_url_is_official():
    assert installer.WEBVIEW2_URL.startswith("https://go.microsoft.com/fwlink/")


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


# ---------------------------------------------------------------- 升级：旧版检测 / 清理
def test_detect_existing_install_only_for_same_target(tmp_path):
    """目标目录里有可用的卸载器才算「同一份旧安装」；无关目录不能误判。"""
    target = tmp_path / "installed"
    (target / "_internal" / "tools").mkdir(parents=True)
    (target / installer.APP_EXE).write_bytes(b"old")
    (target / installer.UNINSTALL_EXE).write_bytes(b"old-uninstaller")
    (target / "_internal" / "tools" / "installer.py").write_text("x", encoding="utf-8")

    info = installer.detect_existing_install(str(target))
    assert info is not None and info["source"] == "uninstaller"

    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()
    (unrelated / "notes.txt").write_text("not our app", encoding="utf-8")
    assert installer.detect_existing_install(str(unrelated)) is None


def test_cleanup_renames_leftover_when_delete_fails(tmp_path, monkeypatch):
    """删不掉的旧目录必须改名成 `<dir>.old-<时间戳>`，不能直接失败挡住新安装。"""
    target = tmp_path / "installed"
    target.mkdir()
    (target / installer.APP_EXE).write_bytes(b"locked")
    monkeypatch.setattr(installer, "_remove_tree", lambda path, **kwargs: False)

    result = installer.cleanup_existing(str(target), info={"source": "leftover"})

    assert result["found"] and result["removed"]
    assert result["renamed_to"] and Path(result["renamed_to"]).is_dir()
    assert not target.exists()


def test_install_into_uninstalls_old_version_before_copy(tmp_path, monkeypatch):
    """有旧版本时必须先静默卸载、等目录清空，再把新文件放进去。"""
    payload = _stub_payload(tmp_path)
    target = tmp_path / "installed"
    (target / "_internal" / "tools").mkdir(parents=True)
    (target / installer.APP_EXE).write_bytes(b"old")
    (target / installer.UNINSTALL_EXE).write_bytes(b"old-uninstaller")
    (target / "_internal" / "tools" / "installer.py").write_text("x", encoding="utf-8")

    calls: list[str] = []

    def fake_uninstaller(path, info, timeout=30.0):
        calls.append(path)
        shutil.rmtree(path)          # 模拟旧卸载器清掉程序目录
        return True

    monkeypatch.setattr(installer, "_run_legacy_uninstaller", fake_uninstaller)
    monkeypatch.setattr(installer, "payload_root", lambda: str(payload))
    monkeypatch.setattr(installer, "create_shortcut", lambda *a, **k: None)
    monkeypatch.setattr(installer, "write_uninstall_entry", lambda d: None)

    steps: list[str] = []
    installer.install_into(str(target), desktop=False, on_step=steps.append)

    assert calls == [str(target)]
    assert "正在清理旧版本…" in steps
    assert (target / installer.APP_EXE).read_bytes() == b"app"
    assert steps[-1] == "安装完成。"


def test_install_into_refuses_nonempty_unrelated_dir(tmp_path, monkeypatch):
    """目标目录里有别人的文件时不能自动清空，必须给出可读错误且保持原样。"""
    payload = _stub_payload(tmp_path)
    target = tmp_path / "installed"
    target.mkdir()
    (target / "keep.txt").write_text("keep", encoding="utf-8")
    monkeypatch.setattr(installer, "payload_root", lambda: str(payload))

    with pytest.raises(installer.InstallError):
        installer.install_into(str(target), desktop=False)

    assert (target / "keep.txt").read_text(encoding="utf-8") == "keep"


# ---------------------------------------------------------------- 解包加固 / 诊断
def test_release_payload_retries_once_after_failed_copy(tmp_path, monkeypatch):
    payload = _stub_payload(tmp_path)
    target = tmp_path / "installed"
    real_copytree = shutil.copytree
    attempts = {"n": 0}

    def flaky_copytree(src, dst, *args, **kwargs):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise OSError("模拟首次复制失败")
        # 恢复原函数再委托：copytree 递归子目录时会再次调用模块级 copytree，
        # 不恢复就会把递归调用也计进 attempts。
        monkeypatch.setattr(installer.shutil, "copytree", real_copytree)
        return real_copytree(src, dst, *args, **kwargs)

    monkeypatch.setattr(installer.shutil, "copytree", flaky_copytree)
    monkeypatch.setattr(installer.time, "sleep", lambda seconds: None)

    steps: list[str] = []
    installer._release_payload(str(payload), str(target), steps.append)

    assert attempts["n"] == 2
    assert (target / installer.APP_EXE).read_bytes() == b"app"
    assert any("重试" in text for text in steps)


def test_write_error_log_records_traceback_and_mei_inventory(tmp_path, monkeypatch):
    """失败日志必须有 traceback、_MEI 实际文件清单与当前安装状态。"""
    mei = tmp_path / "mei"
    mei.mkdir()
    (mei / "sample.dll").write_bytes(b"payload")
    log_path = tmp_path / "logs" / "install.log"
    monkeypatch.setenv(installer.LOG_ENV, str(log_path))
    monkeypatch.setattr(installer, "payload_root", lambda: str(tmp_path / "payload"))

    try:
        raise RuntimeError("模拟解包失败")
    except RuntimeError as exc:
        written = installer.write_error_log(
            exc, install_dir=str(tmp_path / "target"),
            state={"cleaned_old": True}, mei_dir=str(mei))

    text = Path(written).read_text(encoding="utf-8")
    assert "Traceback" in text
    assert "模拟解包失败" in text
    assert "sample.dll" in text
    assert "旧版本已清理" in text
    assert "失败分类：" in text
