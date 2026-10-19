"""EFT 互动地图 · 一键安装器。

打包成**单文件 exe**（见 `build\\build_release.ps1`）：随包的 `payload/` 就是整站
（`EFTMap.exe` + `_internal/`）。运行后：

* 把 payload 复制到安装目录（默认 `%LOCALAPPDATA%\\EFTMap`）；
* 建开始菜单快捷方式，（可选）桌面快捷方式；
* 写入「控制面板 → 程序和功能」的卸载项；
* 顺手把自己复制成安装目录里的 `Uninstall.exe`。

**纯标准库**：快捷方式借 PowerShell 的 `WScript.Shell`，注册表用 `winreg`。

命令：
    EFTMap-Setup.exe              打开安装向导
    EFTMap-Setup.exe --silent     静默安装（默认目录 + 桌面快捷方式，装完不自动启动）
    EFTMap-Setup.exe --uninstall  卸载（安装目录里的 Uninstall.exe 调这个）
"""

from __future__ import annotations

import argparse
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import winreg

import tkinter as tk
from tkinter import filedialog, ttk

APP_NAME = "EFT 互动地图"
VERSION = "0.1.0"          # 与 tools/serve.py 的 VERSION 一致（有测试锁死）
REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\EFTMap"
APP_EXE = "EFTMap.exe"
UNINSTALL_EXE = "Uninstall.exe"
PAYLOAD_DIRNAME = "payload"

# 借 PowerShell 的 WScript.Shell 建 .lnk，免得依赖 pywin32
_SHORTCUT_SCRIPT = """param([string]$Lnk,[string]$Target,[string]$WorkDir,[string]$Icon)
$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut($Lnk)
$sc.TargetPath = $Target
$sc.WorkingDirectory = $WorkDir
$sc.IconLocation = $Icon
$sc.Save()
"""


# ---------------------------------------------------------------- 路径
def bundle_root() -> str:
    """打包后 PyInstaller 解出的临时资源目录；源码运行时是 tools/ 的上级。"""
    return getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def payload_root() -> str:
    """随包的整站目录（EFTMap.exe + _internal）。"""
    return os.path.join(bundle_root(), PAYLOAD_DIRNAME)


def default_install_dir() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "EFTMap")


def start_menu_dir() -> str:
    appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs")


def desktop_dir() -> str:
    """桌面真实位置（可能被 OneDrive 重定向），从「用户 Shell 文件夹」读。"""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders") as key:
            value, _kind = winreg.QueryValueEx(key, "Desktop")
        return os.path.expandvars(value)
    except OSError:
        return os.path.join(os.path.expanduser("~"), "Desktop")


def shortcut_paths() -> tuple[str, str]:
    name = APP_NAME + ".lnk"
    return (os.path.join(start_menu_dir(), name), os.path.join(desktop_dir(), name))


# ---------------------------------------------------------------- 快捷方式 / 注册表
def create_shortcut(lnk: str, target: str, work_dir: str, icon: str) -> None:
    os.makedirs(os.path.dirname(lnk), exist_ok=True)
    handle = tempfile.NamedTemporaryFile("w", suffix=".ps1", delete=False, encoding="utf-8")
    try:
        handle.write(_SHORTCUT_SCRIPT)
        handle.close()
        subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                        "-File", handle.name, "-Lnk", lnk, "-Target", target,
                        "-WorkDir", work_dir, "-Icon", icon],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    finally:
        try:
            os.remove(handle.name)
        except OSError:
            pass


def dir_size_kb(path: str) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                pass
    return total // 1024


def write_uninstall_entry(install_dir: str) -> None:
    uninstall = '"%s" --uninstall' % os.path.join(install_dir, UNINSTALL_EXE)
    values: list[tuple[str, object]] = [
        ("DisplayName", APP_NAME + "（离线版）"),
        ("DisplayVersion", VERSION),
        ("Publisher", "EFTMap"),
        ("InstallLocation", install_dir),
        ("UninstallString", uninstall),
        ("QuietUninstallString", uninstall + " --silent"),
        ("DisplayIcon", os.path.join(install_dir, APP_EXE) + ",0"),
        ("EstimatedSize", dir_size_kb(install_dir)),
        ("NoModify", 1),
        ("NoRepair", 1),
    ]
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, REG_KEY) as key:
        for name, value in values:
            if isinstance(value, int):
                winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, value)
            else:
                winreg.SetValueEx(key, name, 0, winreg.REG_SZ, str(value))


def remove_uninstall_entry() -> None:
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, REG_KEY)
    except FileNotFoundError:
        pass


# ---------------------------------------------------------------- 安装 / 卸载
def install_into(install_dir: str, desktop: bool = True, on_step=None) -> None:
    """把 payload 复制过去、建快捷方式、写卸载项。`on_step` 用于给界面报进度。"""
    def step(text: str):
        if on_step is not None:
            on_step(text)

    src = payload_root()
    if not os.path.isdir(src):
        raise RuntimeError("安装包缺少 payload（构建有问题，重新打包即可）")

    step("正在复制程序文件…")
    os.makedirs(install_dir, exist_ok=True)
    shutil.copytree(src, install_dir, dirs_exist_ok=True)

    exe = os.path.join(install_dir, APP_EXE)
    step("正在创建开始菜单快捷方式…")
    start_lnk, desk_lnk = shortcut_paths()
    create_shortcut(start_lnk, exe, install_dir, exe)
    if desktop:
        step("正在创建桌面快捷方式…")
        create_shortcut(desk_lnk, exe, install_dir, exe)

    step("正在登记卸载信息…")
    shutil.copy2(sys.executable, os.path.join(install_dir, UNINSTALL_EXE))
    write_uninstall_entry(install_dir)
    step("安装完成。")


def uninstall(install_dir: str) -> None:
    """删快捷方式与注册表项，再交给 cmd 延迟删目录（本进程就活在目录里）。"""
    for lnk in shortcut_paths():
        try:
            os.remove(lnk)
        except OSError:
            pass
    remove_uninstall_entry()
    subprocess.Popen('cmd /c ping 127.0.0.1 -n 2 >nul & rmdir /s /q "%s"' % install_dir,
                     shell=True, creationflags=subprocess.CREATE_NO_WINDOW)


# ---------------------------------------------------------------- 安装向导
class InstallWindow:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.events: queue.Queue = queue.Queue()
        self.done = False

        root.title(APP_NAME + " · 安装")
        root.geometry("470x230")
        root.resizable(False, False)

        frame = tk.Frame(root, padx=14, pady=12)
        frame.pack(fill="both", expand=True)

        tk.Label(frame, text="安装位置：").grid(row=0, column=0, sticky="w")
        self.dir_var = tk.StringVar(value=default_install_dir())
        tk.Entry(frame, textvariable=self.dir_var, width=42).grid(row=0, column=1, sticky="we")
        tk.Button(frame, text="浏览…", command=self._browse).grid(row=0, column=2, padx=(6, 0))

        self.desktop_var = tk.BooleanVar(value=True)
        tk.Checkbutton(frame, text="创建桌面快捷方式", variable=self.desktop_var) \
            .grid(row=1, column=0, columnspan=3, sticky="w", pady=(8, 0))

        tk.Label(frame, text="装到本机后，双击快捷方式即可启动（启动框 → 自动打开界面）。",
                 wraplength=430, justify="left", fg="#555555") \
            .grid(row=2, column=0, columnspan=3, sticky="w", pady=(10, 0))

        self.bar = ttk.Progressbar(frame, mode="indeterminate", length=430)
        self.bar.grid(row=3, column=0, columnspan=3, sticky="we", pady=(12, 4))

        self.status = tk.Label(frame, text="点「开始安装」把程序装到本机。", anchor="w")
        self.status.grid(row=4, column=0, columnspan=3, sticky="we")

        buttons = tk.Frame(frame)
        buttons.grid(row=5, column=0, columnspan=3, sticky="e", pady=(12, 0))
        self.btn_quit = tk.Button(buttons, text="取消", width=10, command=self._cancel)
        self.btn_quit.pack(side="right")
        self.btn_install = tk.Button(buttons, text="开始安装", width=12, command=self._start, default="active")
        self.btn_install.pack(side="right", padx=(0, 8))
        self.btn_launch = tk.Button(buttons, text="启动", width=10, state="disabled", command=self._launch)

        frame.columnconfigure(1, weight=1)
        self.root.after(100, self._pump)

    def _browse(self):
        chosen = filedialog.askdirectory(initialdir=self.dir_var.get() or default_install_dir())
        if chosen:
            self.dir_var.set(chosen)

    def _start(self):
        if not self.btn_install["state"] == "normal":
            return
        target = self.dir_var.get().strip() or default_install_dir()
        desktop = bool(self.desktop_var.get())
        self.btn_install.configure(state="disabled", text="正在安装…")
        self.btn_quit.configure(state="disabled")
        self.bar.start(12)
        threading.Thread(target=self._worker, args=(target, desktop), daemon=True).start()

    def _worker(self, target: str, desktop: bool):
        try:
            install_into(target, desktop=desktop, on_step=self.events.put)
            self.events.put(("__done__", target))
        except Exception as exc:  # 安装失败要说清原因，别让用户对着进度条干等
            self.events.put(("__error__", str(exc)))

    def _pump(self):
        try:
            while True:
                item = self.events.get_nowait()
                if isinstance(item, tuple):
                    kind, value = item
                    if kind == "__done__":
                        self._finish(value)
                    elif kind == "__error__":
                        self._fail(value)
                    return
                self.status.configure(text=item)
        except queue.Empty:
            pass
        self.root.after(100, self._pump)

    def _finish(self, target: str):
        self.done = True
        self.bar.stop()
        self.bar.configure(mode="determinate", value=100)
        self.status.configure(text="安装完成：" + target)
        self.btn_install.configure(text="已安装")
        self.btn_quit.configure(state="normal", text="关闭")
        self.btn_launch.pack(side="right", padx=(0, 8))

    def _fail(self, message: str):
        self.bar.stop()
        self.status.configure(text="安装失败：" + message, fg="#C00000")
        self.btn_install.configure(state="normal", text="重试")
        self.btn_quit.configure(state="normal")

    def _launch(self):
        target = self.dir_var.get().strip() or default_install_dir()
        exe = os.path.join(target, APP_EXE)
        if os.path.isfile(exe):
            subprocess.Popen([exe], cwd=target)
        self.root.destroy()

    def _cancel(self):
        self.root.destroy()


def run_gui() -> int:
    root = tk.Tk()
    InstallWindow(root)
    root.mainloop()
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=APP_NAME + " 安装器")
    parser.add_argument("--silent", action="store_true", help="静默安装（默认目录 + 桌面快捷方式）")
    parser.add_argument("--uninstall", action="store_true", help="卸载")
    parser.add_argument("--dir", default=None, help="指定安装 / 卸载目录")
    args = parser.parse_args(argv)

    if args.uninstall:
        uninstall(args.dir or os.path.dirname(os.path.abspath(sys.executable)))
        return 0
    if args.silent:
        install_into(args.dir or default_install_dir(), desktop=True)
        return 0
    return run_gui()


if __name__ == "__main__":
    sys.exit(main())
