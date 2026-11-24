# -*- coding: utf-8 -*-
"""R303：安装器关闭仍在运行的旧版程序。

安装前若旧版 EFTMap 还在跑，它的 exe/DLL 被占用，清理会把旧目录改名成
.old-*（垃圾残留），甚至让新版启动到旧文件。修复：cleanup 前先关进程。

安全约束（必须锁死）：
1. 按**可执行路径**限定在目标安装目录内，不能按进程名全局杀；
2. 只关白名单文件名（EFTMap.exe / EFTMapDesktop.exe / Uninstall.exe）；
3. 非 Windows / PowerShell 不可用 / 无匹配进程都返回 0，不抛异常、不阻断安装。
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INSTALLER = ROOT / "tools" / "installer.py"


def _load():
    spec = importlib.util.spec_from_file_location("inst_r303", str(INSTALLER))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_close_script_scopes_by_path_and_whitelist():
    inst = _load()
    script = inst._CLOSE_PROCS_SCRIPT
    # 路径前缀匹配（OrdinalIgnoreCase），不是按名字全局 Stop-Process
    assert "StartsWith($target" in script
    assert "OrdinalIgnoreCase" in script
    assert "-notcontains $name" in script  # 文件名白名单
    assert "Stop-Process -Id $p.ProcessId -Force" in script
    assert "Get-CimInstance Win32_Process" in script  # 用 WMI 拿可执行路径


def test_close_returns_zero_on_non_windows(monkeypatch):
    inst = _load()
    monkeypatch.setattr(inst.os, "name", "posix")
    assert inst.close_running_old_app("C:\\some\\dir") == 0


def test_close_returns_count_from_powershell(monkeypatch):
    inst = _load()
    monkeypatch.setattr(inst.os, "name", "nt")

    class FakeResult:
        stdout = "2\n"
        stderr = ""

    calls = {}

    def fake_run(args, **kwargs):
        calls["args"] = args
        return FakeResult()

    monkeypatch.setattr(inst.subprocess, "run", fake_run)
    n = inst.close_running_old_app("C:\\Program Files\\EFTMap")
    assert n == 2
    assert "powershell" in calls["args"][0].lower()
    # 传入了安装目录与白名单
    assert any("EFTMap" in str(a) for a in calls["args"])
    assert any(inst.APP_EXE in str(a) for a in calls["args"])  # -ExeNames 白名单


def test_close_swallows_errors(monkeypatch):
    inst = _load()
    monkeypatch.setattr(inst.os, "name", "nt")

    def boom(*a, **k):
        raise OSError("no powershell")

    monkeypatch.setattr(inst.subprocess, "run", boom)
    assert inst.close_running_old_app("C:\\x") == 0  # 不阻断安装


def test_installer_version_matches_serve():
    inst = _load()
    import sys
    sys.path.insert(0, str(ROOT / "tools"))
    import serve
    assert inst.VERSION == serve.VERSION
