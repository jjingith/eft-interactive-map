"""EFT 互动地图 · 一键安装器。

打包成**单文件 exe**（见 `build\\build_release.ps1`）：随包的 `payload/` 就是整站
（`EFTMap.exe` + `_internal/`）。运行后：

* 安装前检测并**静默卸载同目录的旧版本**（只清理程序目录，保留 `%APPDATA%\\EFTMap`
  里的配置与预设）；没有旧版本时不做任何多余动作、不弹窗；
* 把 payload 先复制到同盘的暂存目录，校验文件数量/总大小后再原子换入安装目录，
  失败时清理暂存、不把用户留在半成品目录里；
* 建开始菜单快捷方式，（可选）桌面快捷方式；
* 写入「控制面板 → 程序和功能」的卸载项；
* 在安装目录写 `Uninstall.exe`（同目录 `EFTMap.exe` 的副本，见 `uninstall_script`）；
* 任何失败都把完整 traceback + `_MEI` 解包目录的实际文件清单写入
  `%LOCALAPPDATA%\\EFTMapInstaller\\install.log`，界面同时给出可复制的错误全文与
  「打开日志」按钮（静默模式则把日志路径写到 stderr）。

`Uninstall.exe` **不再**是安装包自身的副本：本安装包是 127 MB 的单文件 exe，
每启动一次都要先把 payload 解压到 %TEMP%，实测卸载要 ~2 分钟且多占 127 MB 磁盘。
改成 onedir 的 `EFTMap.exe` 副本后启动是秒级，卸载逻辑仍只有这一份源码，
由窗口版产品自带的 `--run-tool` 入口执行 `_internal/tools/installer.py`。

**纯标准库**：快捷方式借 PowerShell 的 `WScript.Shell`，注册表用 `winreg`。

命令：
    EFTMap-Setup.exe              打开安装向导
    EFTMap-Setup.exe --silent     静默安装（默认目录 + 桌面快捷方式，装完不自动启动）
    EFTMap-Setup.exe --uninstall  卸载（直接调 installer.py 时用；安装版走上面那条 --run-tool）
"""

from __future__ import annotations

import argparse
import os
import platform
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import webbrowser
import winreg

# tkinter 只在图形安装向导里用。卸载路径跑在 windowed 的 EFTMap.exe 里
# （`Uninstall.exe --run-tool installer.py`），那里不一定带了 ttk/filedialog；
# 不在模块级 import tkinter，缺 GUI 组件也不会连卸载都跑不起来。
# 具体模块由 run_gui() 注入到下面这三个名字。
tk = None
ttk = None
filedialog = None
messagebox = None

APP_NAME = "EFT 互动地图"
VERSION = "0.2.8.2"          # 与 tools/serve.py 的 VERSION 一致（有测试锁死）
REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\EFTMap"
APP_EXE = "EFTMap.exe"
APP_SHELL = "EFTMapDesktop.exe"   # 无边框客户端壳；与 EFTMap.exe 同目录出包
UNINSTALL_EXE = "Uninstall.exe"
PAYLOAD_DIRNAME = "payload"

# 诊断日志固定落在用户 LocalAppData 下（**不能**放安装目录，否则清理旧版时会把证据删掉）。
# 测试 / 特殊排查可用环境变量 EFT_MAP_INSTALL_LOG 指到别处。
LOG_DIRNAME = "EFTMapInstaller"
LOG_FILENAME = "install.log"
LOG_ENV = "EFT_MAP_INSTALL_LOG"
_LOG_MAX_BYTES = 4 * 1024 * 1024


# 安装期可预期失败的统一异常（GUI / --silent 都据此写日志并给出中文原因）。
class InstallError(RuntimeError):
    """带可读原因的安装失败；`eftmap_install_state` 记录失败时走到哪一步。"""


# WebView2 Runtime：Win10 干净机器可能没有。缺它时桌面壳只能进兼容模式（浏览器打开），
# 所以安装向导在开始前就要提示，并给出官方下载地址（微软 Evergreen Bootstrapper，常青版）。
WEBVIEW2_URL = "https://go.microsoft.com/fwlink/p/?LinkId=2124703"
WEBVIEW2_CLIENT_KEY = r"Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"

# 借 PowerShell 的 WScript.Shell 建 .lnk，免得依赖 pywin32
_SHORTCUT_SCRIPT = """param([string]$Lnk,[string]$Target,[string]$WorkDir,[string]$Icon)
$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut($Lnk)
$sc.TargetPath = $Target
$sc.WorkingDirectory = $WorkDir
$sc.IconLocation = $Icon
$sc.Save()
"""

# 建 .lnk 用的临时名：必须**纯 ASCII**（见 create_shortcut 注释）
_TMP_LNK_NAME = "_eftmap_shortcut_tmp.lnk"


# ---------------------------------------------------------------- 路径
def bundle_root() -> str:
    """打包后 PyInstaller 解出的临时资源目录；源码运行时是 tools/ 的上级。"""
    return getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def payload_root() -> str:
    """随包的整站目录（EFTMap.exe + _internal）。"""
    return os.path.join(bundle_root(), PAYLOAD_DIRNAME)


def launch_exe(install_dir: str) -> str:
    """快捷方式 / 启动目标：优先客户端壳，壳缺失时回退浏览器版 EFTMap.exe。"""
    shell = os.path.join(install_dir, APP_SHELL)
    return shell if os.path.isfile(shell) else os.path.join(install_dir, APP_EXE)


def default_install_dir() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "EFTMap")


def webview2_version() -> str | None:
    """返回已安装的 WebView2 Runtime 版本；没装返回 None。

    先查三处注册表（HKCU / HKLM 64 / HKLM 的 WOW6432Node，覆盖 Evergreen 各安装方式），
    都没有再看 ``EdgeWebView\\Application`` 目录兜底。任何一步读不到都不抛异常——
    检测失败等同于「没装」，由界面提示用户去装，不能因此让安装器崩掉。
    """
    for hive, prefix in ((winreg.HKEY_CURRENT_USER, r"Software\\"),
                         (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\\"),
                         (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\\WOW6432Node\\")):
        try:
            with winreg.OpenKey(hive, prefix + WEBVIEW2_CLIENT_KEY) as key:
                value, _kind = winreg.QueryValueEx(key, "pv")
        except OSError:
            continue
        if isinstance(value, str) and value.strip() and value.strip() != "0.0.0.0":
            return value.strip()

    for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles")):
        if not base:
            continue
        app = os.path.join(base, "Microsoft", "EdgeWebView", "Application")
        try:
            names = [d for d in os.listdir(app) if os.path.isdir(os.path.join(app, d))]
        except OSError:
            continue
        names = [d for d in names if d != "0.0.0.0" and any(ch.isdigit() for ch in d)]
        if names:
            return sorted(names)[-1]
    return None


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
    """建一个 .lnk。

    ⚠ 不能把中文名直接交给 `WScript.Shell`：它内部会按**系统 ANSI 代码页**
    （简体中文机器上常见是英文的 1252）转换路径，`互动地图` 会变成 `????`，
    `Save()` 随即 `FileNotFoundException`，快捷方式根本建不出来。
    所以先建到同目录的**纯 ASCII 临时名**，再用 `os.replace` 改成真正的名字
    —— Python 的文件名 API 走宽字符，中文名是安全的。
    （内容里的安装目录同理：默认目录是 ASCII，正常；若用户装到含中文的目录，
    WSH 仍会破坏该路径，属已知限制。）
    """
    directory = os.path.dirname(lnk)
    os.makedirs(directory, exist_ok=True)
    tmp = os.path.join(directory, _TMP_LNK_NAME)
    for stale in (tmp,):
        try:
            os.remove(stale)
        except OSError:
            pass
    handle = tempfile.NamedTemporaryFile("w", suffix=".ps1", delete=False, encoding="utf-8")
    try:
        handle.write(_SHORTCUT_SCRIPT)
        handle.close()
        kwargs = {"check": True, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
        if os.name == "nt":
            # powershell 是控制台子系统程序；安装器本身是 --noconsole 产物，
            # 不加这个就会在建快捷方式时闪一个 PowerShell/cmd 窗口（R75）。
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                        "-File", handle.name, "-Lnk", tmp, "-Target", target,
                        "-WorkDir", work_dir, "-Icon", icon], **kwargs)
    finally:
        try:
            os.remove(handle.name)
        except OSError:
            pass
    os.replace(tmp, lnk)


def dir_size_kb(path: str) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                pass
    return total // 1024


def uninstall_script(install_dir: str) -> str:
    """安装目录里随包的卸载逻辑（正常是 `_internal/tools/installer.py`）。

    `Uninstall.exe` 是 `EFTMap.exe` 的副本，卸载逻辑交给它的隐藏入口
    `--run-tool` 执行，Windows 才会把「谁在锁文件」算在 Uninstall.exe 头上，
    延迟删除脚本只需等这一个短命进程退出。
    """
    internal = os.path.join(install_dir, "_internal")
    if not os.path.isdir(internal):
        internal = install_dir
    return os.path.join(internal, "tools", "installer.py")


def write_uninstall_entry(install_dir: str) -> None:
    uninstall = '"%s" --run-tool "%s" --uninstall --dir "%s"' % (
        os.path.join(install_dir, UNINSTALL_EXE),
        uninstall_script(install_dir),
        install_dir,
    )
    values: list[tuple[str, object]] = [
        ("DisplayName", APP_NAME + "（离线版）"),
        ("DisplayVersion", VERSION),
        ("Publisher", "EFTMap"),
        ("InstallLocation", install_dir),
        ("UninstallString", uninstall),
        ("QuietUninstallString", uninstall + " --silent"),
        ("DisplayIcon", launch_exe(install_dir) + ",0"),
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


# ---------------------------------------------------------------- 诊断日志
def install_log_path() -> str:
    """失败日志的固定路径：`%LOCALAPPDATA%\\EFTMapInstaller\\install.log`。

    刻意不放在安装目录里：清理旧版本 / 回滚时安装目录会被整体移走，日志不能跟着丢。
    """
    override = os.environ.get(LOG_ENV, "").strip()
    if override:
        return os.path.abspath(override)
    base = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
    return os.path.join(base, LOG_DIRNAME, LOG_FILENAME)


def _human_bytes(num: float) -> str:
    value = float(num)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return ("%d B" % value) if unit == "B" else ("%.1f %s" % (value, unit))
        value /= 1024.0
    return "%d B" % num


def _inventory(path: str, *, list_files: bool = True) -> tuple[int, int, list[str]]:
    """统计目录的文件数量与总字节数；`list_files` 为真时同时返回逐文件明细。"""
    count = 0
    total = 0
    listing: list[str] = []
    if not os.path.isdir(path):
        return count, total, listing
    for root, _dirs, files in os.walk(path):
        for name in files:
            full = os.path.join(root, name)
            try:
                size = os.path.getsize(full)
            except OSError:
                size = 0
            count += 1
            total += size
            if list_files:
                listing.append("%12d  %s" % (size, os.path.relpath(full, path)))
    return count, total, listing


def _exception_text(exc: BaseException) -> str:
    try:
        text = str(exc)
    except Exception:  # noqa: BLE001 - 极端情况下 str() 也会抛
        text = "<str(exc) 失败>"
    if isinstance(exc, shutil.Error):
        try:
            text += "\n逐项：" + "\n".join("%r" % item for item in exc.err)
        except Exception:  # noqa: BLE001
            pass
    return text


def classify_error(exc: BaseException) -> str:
    """把底层异常翻译成用户能看懂、能采取行动的中文原因。"""
    text = _exception_text(exc).lower()
    if any(k in text for k in ("errno 28", "winerror 112", "no space left", "disk full",
                               "空间不足", "磁盘已满")):
        return "磁盘空间不足。请清理磁盘（尤其是 %TEMP% 和安装所在盘）后重试。"
    if any(k in text for k in ("winerror 225", "virus", "病毒", "threat", "blocked by")):
        return "安全软件拦截了安装文件。请把安装包与安装目录加入杀毒/防护软件白名单后重试。"
    if any(k in text for k in ("winerror 32", "winerror 33", "sharing violation", "lock violation",
                               "being used", "正在使用", "占用")):
        return "目标文件被占用。请先关闭正在运行的 EFT 互动地图（含兼容模式浏览器窗口），再重试。"
    if any(k in text for k in ("winerror 5", "access is denied", "errno 13", "permissionerror",
                               "拒绝访问")):
        return ("没有写入权限，或被安全软件阻止。请换一个当前用户可写的目录，"
                "或检查杀毒软件的拦截记录。")
    if any(k in text for k in ("winerror 206", "filename too long", "too long", "路径过长")):
        return "路径过长。请把安装位置改到更短的目录（例如 C:\\EFTMap）后重试。"
    if any(k in text for k in ("winerror 3", "cannot find", "no such file", "找不到", "临时目录")):
        return "临时目录不可用或安装包文件缺失。请确认 %TEMP% 可写、磁盘未满，并重新运行安装包。"
    return "未识别的错误。请把日志文件发给开发者，里面记录了完整调用栈与解包目录清单。"


def describe_install_state(state: dict | None) -> str:
    state = state or {}
    if state.get("released_files"):
        return ("程序文件已释放到安装目录，但后续步骤（快捷方式 / 卸载登记）未完成。"
                "可以直接重试；安装器会先清理这次写入的文件。")
    if state.get("release_started"):
        return "程序文件尚未写入安装目录（复制已在暂存目录中止并清理），目标目录保持原状。"
    if state.get("cleaned_old"):
        return "旧版本已清理，新文件尚未写入。可以点「重试」重新安装。"
    return "未对安装目录做任何改动。可以点「重试」重新安装。"


def write_error_log(exc: BaseException, *, install_dir: str | None = None,
                    state: dict | None = None, mei_dir: str | None = None) -> str:
    """把完整诊断写入固定日志文件，返回日志路径。

    内容包括：失败分类、异常全文、traceback、运行环境、磁盘余量，以及用户明确要求的
    `_MEI` 解包目录实际文件清单（逐文件大小）。磁盘上留存一份，便于朋友把整份日志发回来。
    """
    path = install_log_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
    except OSError:
        path = os.path.join(tempfile.gettempdir(), LOG_FILENAME)
        os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        if os.path.getsize(path) > _LOG_MAX_BYTES:
            os.replace(path, path + ".1")
    except OSError:
        pass

    mei = mei_dir if mei_dir is not None else getattr(sys, "_MEIPASS", None)
    lines = [
        "=" * 78,
        "时间：" + time.strftime("%Y-%m-%d %H:%M:%S"),
        "安装器版本：" + VERSION,
        "安装目录：" + (os.path.abspath(install_dir) if install_dir else "（未知）"),
        "安装状态：" + describe_install_state(state),
        "失败分类：" + classify_error(exc),
        "运行形态：" + ("PyInstaller onefile（已解包到 _MEI）"
                       if getattr(sys, "_MEIPASS", None) else "源码运行"),
        "可执行文件：" + sys.executable,
        "命令行：" + " ".join(sys.argv),
        "工作目录：" + os.getcwd(),
        "Python：" + platform.python_version() + "（" + platform.platform() + "）",
        "临时目录：" + tempfile.gettempdir(),
    ]
    for label, probe in (("临时目录可用空间", tempfile.gettempdir()),
                         ("安装盘可用空间", install_dir)):
        free = _directory_free_bytes(probe) if probe else None
        if free is not None:
            lines.append("%s：%s" % (label, _human_bytes(free)))
    lines.extend([
        "",
        "异常类型：" + type(exc).__name__,
        "异常信息：",
        _exception_text(exc),
        "",
        "Traceback：",
        traceback.format_exc().rstrip() or "（无活动异常上下文）",
    ])

    if mei and os.path.isdir(mei):
        count, total, listing = _inventory(mei, list_files=True)
        lines.extend(["", "[_MEI 解包目录] " + mei,
                      "文件数量：%d    总大小：%s" % (count, _human_bytes(total))])
        lines.extend(listing)

    payload = payload_root()
    if os.path.isdir(payload):
        count, total, _listing = _inventory(payload, list_files=False)
        lines.extend(["", "[payload 源目录] " + payload,
                      "文件数量：%d    总大小：%s" % (count, _human_bytes(total))])

    if install_dir and os.path.isdir(install_dir):
        count, total, listing = _inventory(install_dir, list_files=True)
        lines.extend(["", "[安装目录当前内容] " + os.path.abspath(install_dir),
                      "文件数量：%d    总大小：%s" % (count, _human_bytes(total))])
        lines.extend(listing)
    lines.append("")

    with open(path, "a", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines) + "\n")
    return path


# ---------------------------------------------------------------- 旧版本检测 / 清理
def _norm_path(path: str) -> str:
    if not path:
        return ""
    try:
        return os.path.normcase(os.path.abspath(path)).rstrip("\\/")
    except OSError:
        return path


def _query_registry_value(key, name: str) -> str:
    try:
        value, _kind = winreg.QueryValueEx(key, name)
    except OSError:
        return ""
    return str(value).strip()


def _registry_uninstall_entries() -> list[dict]:
    """按 HKCU → HKLM(64) → HKLM(WOW6432Node) 找本程序的卸载项。"""
    candidates = (
        ("HKCU", winreg.HKEY_CURRENT_USER, REG_KEY),
        ("HKLM", winreg.HKEY_LOCAL_MACHINE, REG_KEY),
        ("HKLM32", winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\EFTMap"),
    )
    entries: list[dict] = []
    for name, hive, sub in candidates:
        try:
            with winreg.OpenKey(hive, sub) as key:
                location = _query_registry_value(key, "InstallLocation")
                uninstall_string = _query_registry_value(key, "UninstallString")
                quiet = _query_registry_value(key, "QuietUninstallString")
        except OSError:
            continue
        if location or uninstall_string:
            entries.append({"name": name, "hive": hive, "sub": sub, "location": location,
                            "uninstall_string": uninstall_string, "quiet": quiet})
    return entries


def _entry_install_dir(entry: dict) -> str:
    location = entry.get("location") or ""
    if location:
        return location
    uninstall_string = entry.get("uninstall_string") or ""
    if not uninstall_string:
        return ""
    if uninstall_string.startswith('"'):
        end = uninstall_string.find('"', 1)
        exe = uninstall_string[1:end] if end > 0 else uninstall_string.strip('"')
    else:
        exe = uninstall_string.split(" ")[0]
    return os.path.dirname(exe)


def detect_existing_install(install_dir: str) -> dict | None:
    """判断目标目录里是否已有本程序的旧安装 / 上次失败残留；没有则返回 None。

    只认**同一个目标目录**：注册表项装在别处时不会被误删（避免影响用户其他副本）。
    判据：目标目录里有可用的 Uninstall.exe+卸载脚本、注册表 InstallLocation 正好指向
    目标目录、或目录里有本程序痕迹（EFTMap.exe / _internal）。
    """
    path = os.path.abspath(install_dir)
    target = _norm_path(path)
    uninstall_exe = os.path.join(path, UNINSTALL_EXE)
    script = uninstall_script(path)
    has_uninstaller = os.path.isfile(uninstall_exe) and os.path.isfile(script)

    registry_match = None
    for entry in _registry_uninstall_entries():
        if _norm_path(_entry_install_dir(entry)) == target:
            registry_match = entry
            break

    has_marker = any(os.path.exists(os.path.join(path, name))
                     for name in (APP_EXE, APP_SHELL, "_internal"))
    if not (has_uninstaller or registry_match or has_marker):
        return None

    if has_uninstaller:
        source = "uninstaller"
    elif registry_match:
        source = "registry"
    else:
        source = "leftover"
    return {
        "path": path,
        "source": source,
        "uninstall_exe": uninstall_exe if os.path.isfile(uninstall_exe) else "",
        "script": script,
        "registry": registry_match,
    }


def _is_empty_dir(path: str) -> bool:
    try:
        return not os.listdir(path)
    except OSError:
        return False


def _remove_tree(path: str, attempts: int = 3, delay: float = 1.0) -> bool:
    """删目录，失败重试几次（给仍在退出的旧进程一点时间）。返回是否已不存在。"""
    for index in range(attempts):
        try:
            shutil.rmtree(path)
        except FileNotFoundError:
            return True
        except OSError:
            pass
        if not os.path.exists(path):
            return True
        if index + 1 < attempts:
            time.sleep(delay)
    return not os.path.exists(path)


def _best_effort_remove(path: str) -> None:
    if not path:
        return
    try:
        if os.path.isdir(path):
            shutil.rmtree(path)
        elif os.path.exists(path):
            os.remove(path)
    except OSError:
        pass


def _rename_leftover(path: str) -> str:
    """删不掉的旧目录改成 `<dir>.old-<时间戳>`，既不挡新安装、又保留用户数据线索。"""
    stamp = time.strftime("%Y%m%d-%H%M%S")
    candidate = "%s.old-%s" % (path, stamp)
    index = 1
    while os.path.exists(candidate):
        candidate = "%s.old-%s-%d" % (path, stamp, index)
        index += 1
    try:
        os.replace(path, candidate)
    except OSError as exc:
        raise InstallError(
            "旧版本目录既删不掉也改不了名：%s\n（%s）\n"
            "请关闭正在运行的程序，或手动删除该目录后重试。" % (path, exc))
    return candidate


def _wait_until_absent(path: str, timeout: float = 25.0, interval: float = 0.5) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not os.path.exists(path):
            return True
        time.sleep(interval)
    return not os.path.exists(path)


def _run_legacy_uninstaller(install_dir: str, info: dict, timeout: float = 30.0) -> bool:
    """静默调用旧版 Uninstall.exe 并**等它退出**。

    `Uninstall.exe` 是旧版 EFTMap.exe 的副本，真正卸载由
    `--run-tool <安装目录>\\_internal\\tools\\installer.py --uninstall --dir <目录>` 执行；
    它只删程序目录、快捷方式和注册表项，**不动 %APPDATA%\\EFTMap** 里的配置与预设。
    旧卸载器退出后还会甩出一个延迟删除 cmd，因此调用方要继续轮询目录是否消失。
    """
    exe = info.get("uninstall_exe") or os.path.join(install_dir, UNINSTALL_EXE)
    script = info.get("script") or uninstall_script(install_dir)
    if not (os.path.isfile(exe) and os.path.isfile(script)):
        return False
    args = [exe, "--run-tool", script, "--uninstall", "--dir", os.path.abspath(install_dir)]
    kwargs: dict = {"cwd": tempfile.gettempdir(), "close_fds": True}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        proc = subprocess.Popen(args, **kwargs)
    except OSError:
        return False
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
    return True


def cleanup_existing(install_dir: str, on_step=None, info: dict | None = None) -> dict:
    """卸载 / 清理同目录旧版本。返回 `{found, removed, renamed_to, used_uninstaller}`。

    顺序：静默跑旧卸载器并等待 → 等目录消失 → 删不掉的目录改名为 `.old-<时间戳>`。
    没有旧版本时直接返回，既不等待也不弹窗。
    """
    path = os.path.abspath(install_dir)
    info = info or detect_existing_install(path)
    result = {"found": bool(info), "removed": False, "renamed_to": "", "used_uninstaller": False}
    if not info:
        return result

    if on_step is not None:
        on_step("正在清理旧版本…")
    if info.get("uninstall_exe") and os.path.isfile(info.get("script") or ""):
        if on_step is not None:
            on_step("正在等待旧版本卸载完成…")
        result["used_uninstaller"] = _run_legacy_uninstaller(path, info)
        _wait_until_absent(path, timeout=25.0)

    registry = info.get("registry")
    if registry:
        # 旧卸载器通常已删掉 HKCU 项；若注册表仍指向本目录，就把对应 hive 的这一项清掉。
        try:
            winreg.DeleteKey(registry["hive"], registry["sub"])
        except OSError:
            pass

    if os.path.isdir(path):
        if not _remove_tree(path):
            if on_step is not None:
                on_step("旧版本文件仍被占用，正在改名保留…")
            result["renamed_to"] = _rename_leftover(path)
    result["removed"] = not os.path.exists(path)
    return result


# ---------------------------------------------------------------- 解包加固
def _nearest_existing_dir(path: str) -> str:
    probe = os.path.abspath(path)
    while probe and not os.path.isdir(probe):
        parent = os.path.dirname(probe)
        if parent == probe:
            break
        probe = parent
    return probe


def _directory_free_bytes(path: str) -> int | None:
    try:
        return shutil.disk_usage(_nearest_existing_dir(path)).free
    except OSError:
        return None


def _preflight_payload(src: str, install_dir: str) -> tuple[int, int]:
    """复制前的可读性预检：payload 完整、目标盘空间够、%TEMP% 可写。"""
    if not os.path.isdir(src):
        raise InstallError("安装包缺少 payload（构建有问题，重新打包即可）")
    count, total, _listing = _inventory(src, list_files=False)
    if count == 0 or not os.path.isfile(os.path.join(src, APP_EXE)):
        raise InstallError(
            "安装包内的程序文件不完整（缺少 %s 或文件为空），请重新下载 / 重新打包安装包。"
            % APP_EXE)
    free = _directory_free_bytes(install_dir)
    if free is not None and free < total + 64 * 1024 * 1024:
        raise InstallError(
            "磁盘空间不足：程序文件约 %s，目标盘当前可用 %s。请清理磁盘后重试。"
            % (_human_bytes(total), _human_bytes(free)))
    try:
        handle, probe = tempfile.mkstemp(prefix="eftmap-write-probe-")
        os.close(handle)
        os.remove(probe)
    except OSError as exc:
        raise InstallError(
            "临时目录不可写（%s）：%s\n"
            "可能是磁盘已满、路径不可写或被安全软件限制，请检查后重试。"
            % (tempfile.gettempdir(), exc))
    return count, total


def _staging_path(install_dir: str) -> str:
    return "%s.new-%d" % (install_dir, os.getpid())


def _release_payload(src: str, install_dir: str, on_step=None) -> None:
    """先复制到同盘暂存目录，校验数量/大小后再原子换入安装目录；失败清理并重试一次。

    直接 `copytree(src, install_dir)` 一旦中途失败会把用户留在半成品目录里，
    而且 `shutil.Error` 的字符串是一长串异常元组，界面根本看不清。暂存 + 校验 + 重试
    解决这两个问题：目标目录要么是旧版（尚未动），要么是完整的新版。
    """
    def step(text: str):
        if on_step is not None:
            on_step(text)

    staging = _staging_path(install_dir)
    for attempt in (1, 2):
        if attempt == 2:
            step("复制失败，已清理临时文件，正在重试…")
        _best_effort_remove(staging)
        step("正在复制程序文件…")
        try:
            shutil.copytree(src, staging, dirs_exist_ok=True)
            expected = _inventory(src, list_files=False)[:2]
            actual = _inventory(staging, list_files=False)[:2]
            if actual != expected:
                raise InstallError(
                    "解包校验失败：安装包内 %d 个文件 / %s，暂存目录实际 %d 个文件 / %s。"
                    "通常是临时目录（%s）空间不足或安全软件拦截，请清理后重试。"
                    % (expected[0], _human_bytes(expected[1]), actual[0],
                       _human_bytes(actual[1]), tempfile.gettempdir()))
            if os.path.exists(install_dir):
                if os.path.isdir(install_dir):
                    if not _remove_tree(install_dir):
                        raise InstallError("目标目录仍被占用，无法替换：%s" % install_dir)
                else:
                    os.remove(install_dir)
            os.replace(staging, install_dir)
            return
        except Exception:
            _best_effort_remove(staging)
            if attempt == 2:
                raise
            time.sleep(0.4)


# ---------------------------------------------------------------- 安装 / 卸载
def install_into(install_dir: str, desktop: bool = True, on_step=None, *,
                 auto_clean: bool = True) -> None:
    """复制 payload、建快捷方式、写卸载项；安装前自动清理同目录旧版本。"""
    def step(text: str):
        if on_step is not None:
            on_step(text)

    target = os.path.abspath(install_dir)
    src = payload_root()
    state = {"cleaned_old": False, "release_started": False,
             "released_files": False, "cleanup": None}
    try:
        # 0) 先确认安装包本身可用，避免「旧版卸了、新文件却根本不存在」。
        step("正在检查安装包…")
        _preflight_payload(src, target)

        # 1) 旧版本 / 上次失败残留。没有旧版就完全跳过，不等待、不弹窗。
        existing = detect_existing_install(target)
        if existing:
            state["cleanup"] = cleanup_existing(target, on_step, existing)
            state["cleaned_old"] = True
        elif os.path.isdir(target) and not _is_empty_dir(target):
            raise InstallError(
                "安装目录不为空，且不是本程序的旧版本：%s\n"
                "为避免误删其他文件，安装器不会自动清空该目录。"
                "请换一个空目录，或手动清理后重试。" % target)

        # 2) 暂存复制 → 校验 → 原子换入。
        state["release_started"] = True
        _release_payload(src, target, on_step)
        state["released_files"] = True

        # 3) 快捷方式 / 卸载器 / 注册表。
        exe = launch_exe(target)
        step("正在创建开始菜单快捷方式…")
        start_lnk, desk_lnk = shortcut_paths()
        create_shortcut(start_lnk, exe, target, exe)
        if desktop:
            step("正在创建桌面快捷方式…")
            create_shortcut(desk_lnk, exe, target, exe)

        step("正在登记卸载信息…")
        # 卸载器 = 同目录的 EFTMap.exe 副本（onedir 启动秒级）；逻辑在 installer.py。
        # 不要复制 sys.executable：那是 127 MB 的单文件安装包，启动要解压两分钟。
        app_exe = os.path.join(target, APP_EXE)
        if not os.path.isfile(app_exe):
            raise InstallError("安装目录缺少 %s（文件释放不完整），请重试。" % APP_EXE)
        shutil.copy2(app_exe, os.path.join(target, UNINSTALL_EXE))
        write_uninstall_entry(target)
        step("安装完成。")
    except Exception as exc:  # noqa: BLE001 - 交给 GUI / --silent 写日志
        try:
            exc.eftmap_install_state = state
        except Exception:  # noqa: BLE001 - 某些内建异常不允许挂属性
            pass
        raise


_CLEANUP_CMD = """@echo off
setlocal
set "TARGET={target}"
set "N=0"
:retry
ping -n 2 127.0.0.1 >nul
rd /s /q "%TARGET%" 2>nul
if not exist "%TARGET%" goto done
set /a N+=1
if %N% lss 15 goto retry
:done
(goto) 2>nul & del /f /q "%~f0"
"""


def _schedule_dir_removal(install_dir: str) -> None:
    """延迟删除安装目录：Windows 不允许删除正在运行的 exe（Uninstall.exe）。

    做法：在 %TEMP% 写一个一次性 cmd（ANSI/mbcs 编码，中文路径可识别），
    以 DETACHED 方式启动后立刻退出；cmd 每秒重试 `rd /s /q`，最多 15 次，
    删完后用 `(goto) 2>nul & del "%~f0"` 删掉自己。
    关键点：cmd 的工作目录必须设为 %TEMP%，否则它会把安装目录当 cwd 占住，
    导致 rmdir 永远删不干净（旧实现即如此）。纯标准库，无第三方依赖。
    """
    target = os.path.abspath(install_dir).replace("%", "%%")
    tmpdir = tempfile.gettempdir()
    script = os.path.join(tmpdir, "eftmap-uninstall-%d.cmd" % os.getpid())
    with open(script, "w", encoding="mbcs", newline="\r\n") as fh:
        fh.write(_CLEANUP_CMD.replace("{target}", target))
    flags = subprocess.CREATE_NO_WINDOW | getattr(subprocess, "DETACHED_PROCESS", 0)
    subprocess.Popen(["cmd.exe", "/c", script], cwd=tmpdir,
                     creationflags=flags, close_fds=True)


def uninstall(install_dir: str) -> None:
    """删快捷方式与注册表项，再交给 %TEMP% 的 cmd 在进程退出后删目录。"""
    for lnk in shortcut_paths():
        try:
            os.remove(lnk)
        except OSError:
            pass
    remove_uninstall_entry()
    _schedule_dir_removal(install_dir)


# ---------------------------------------------------------------- 安装向导
AFDIAN_URL = "https://afdian.com/item/cb09a30cdf4411f1959f52540025c377"

WIZARD_TITLES = [
    ("欢迎使用 " + APP_NAME, "这套向导会把程序装到本机，全程不需要联网。"),
    ("选择安装位置", "默认装到当前用户目录，不需要管理员权限。"),
    ("正在安装", "正在把文件复制到本机，完成后会自动校验。"),
    ("安装完成", "下面两个勾选决定关闭安装器后要不要顺手做点什么。"),
]


class InstallWindow:
    """经典四步向导：欢迎 → 安装选项 → 安装中 → 完成。

    为什么不用第三方 UI 库：安装器只有这一个窗口，原生 tk/ttk 已经够用，
    少一个依赖就少一类「朋友机器上打不开」的故障。窗口尺寸写死，避免
    高 DPI 下按字符宽度自动撑开后按钮跑出屏幕。

    完成页的两个勾选按产品要求给：一个启动互动地图，一个前往爱发电页面。
    """

    def __init__(self, root: tk.Tk):
        self.root = root
        self.events: queue.Queue = queue.Queue()
        self.done = False
        self.installing = False
        self.page = 0
        self.log_path = ""
        self.install_target = ""

        root.title(APP_NAME + " " + VERSION + " · 安装")
        root.geometry("560x430")
        root.minsize(560, 430)
        root.resizable(False, False)

        header = tk.Frame(root, padx=18)
        header.pack(fill="x", pady=(14, 0))
        self.title_label = tk.Label(
            header, text="", anchor="w",
            font=("Microsoft YaHei UI", 13, "bold"))
        self.title_label.pack(fill="x")
        self.sub_label = tk.Label(
            header, text="", anchor="w", justify="left", wraplength=520, fg="#555555")
        self.sub_label.pack(fill="x", pady=(4, 0))
        tk.Frame(root, height=1, bg="#A0A0A0").pack(fill="x", padx=18, pady=(10, 0))

        self.body = tk.Frame(root, padx=18, pady=10)
        self.body.pack(fill="both", expand=True)

        self._build_welcome()
        self._build_options()
        self._build_progress()
        self._build_result()
        self.pages = [self.page_welcome, self.page_options,
                      self.page_progress, self.page_result]

        footer = tk.Frame(root, padx=18)
        footer.pack(fill="x", side="bottom", pady=(0, 12))
        self.status = tk.Label(footer, text="点「下一步」继续。", anchor="w", fg="#444444")
        self.status.pack(side="left", fill="x", expand=True)

        self.btn_next = tk.Button(footer, text="下一步", width=11,
                                  command=self._next, default="active")
        self.btn_next.pack(side="right")
        self.btn_back = tk.Button(footer, text="上一步", width=9, command=self._back)
        self.btn_back.pack(side="right", padx=(0, 8))
        self.btn_cancel = tk.Button(footer, text="取消", width=9, command=self._cancel)
        self.btn_cancel.pack(side="right", padx=(0, 8))

        self.root.protocol("WM_DELETE_WINDOW", self._cancel)
        self.root.after(100, self._pump)
        self.show_page(0)

    # ---------------------------------------------------------------- 页面构建
    def _new_page(self) -> "tk.Frame":
        return tk.Frame(self.body)

    def _build_welcome(self):
        page = self._new_page()
        self.page_welcome = page
        tk.Label(page, text="点「下一步」开始安装。", anchor="w").pack(fill="x", pady=(2, 8))

        box = tk.Frame(page, bd=1, relief="groove", padx=12, pady=10)
        box.pack(fill="x")
        rows = [
            ("会装什么", "互动地图主程序、独立窗口外壳、卸载程序。"),
            ("不会动什么", "你的配置与预设（%APPDATA%\\EFTMap）会保留，升级不丢。"),
            ("运行环境", "Windows 10 / 11 64 位；建议装有 WebView2 运行时（下一步会检测）。"),
            ("安装位置", default_install_dir()),
        ]
        for i, (key, text) in enumerate(rows):
            tk.Label(box, text=key, anchor="nw", width=9, fg="#204070").grid(
                row=i, column=0, sticky="nw", pady=(0, 6))
            tk.Label(box, text=text, anchor="w", justify="left", wraplength=390).grid(
                row=i, column=1, sticky="w", pady=(0, 6))
        box.columnconfigure(1, weight=1)

        tk.Label(page, text="下一步可以改安装位置、决定要不要建桌面快捷方式。",
                 anchor="w", fg="#777777").pack(fill="x", pady=(10, 0))

    def _build_options(self):
        page = self._new_page()
        self.page_options = page

        tk.Label(page, text="安装位置：", anchor="w").grid(row=0, column=0, sticky="w")
        self.dir_var = tk.StringVar(value=default_install_dir())
        tk.Entry(page, textvariable=self.dir_var, width=46).grid(
            row=0, column=1, sticky="we", padx=(0, 6))
        tk.Button(page, text="浏览…", command=self._browse).grid(row=0, column=2)

        self.desktop_var = tk.BooleanVar(value=True)
        tk.Checkbutton(page, text="创建桌面快捷方式", variable=self.desktop_var).grid(
            row=1, column=0, columnspan=3, sticky="w", pady=(12, 0))

        tk.Label(page, text="装好后双击快捷方式即可启动（启动框 → 自动打开界面）。",
                 anchor="w", fg="#777777").grid(
            row=2, column=0, columnspan=3, sticky="w", pady=(6, 0))

        # WebView2 检测结果：Win10 干净机器可能没有运行时，缺它时桌面壳会退成兼容模式。
        self.webview2 = webview2_version()
        wv2_row = tk.Frame(page)
        wv2_row.grid(row=3, column=0, columnspan=3, sticky="we", pady=(14, 0))
        if self.webview2:
            wv2_text = "WebView2 运行时：已就绪（%s）" % self.webview2
            wv2_fg = "#1A7F37"
        else:
            wv2_text = ("未检测到 WebView2 运行时（Win10 常见）。可以继续安装，但启动后会进入"
                        "兼容模式（用浏览器打开），没有独立窗口；建议先安装运行时。")
            wv2_fg = "#C00000"
        self.wv2_label = tk.Label(wv2_row, text=wv2_text, wraplength=370,
                                  justify="left", anchor="w", fg=wv2_fg)
        self.wv2_label.pack(side="left", fill="x", expand=True)
        if not self.webview2:
            tk.Button(wv2_row, text="下载并安装", command=self._open_wv2).pack(
                side="right", padx=(6, 0))

        page.columnconfigure(1, weight=1)

    def _build_progress(self):
        page = self._new_page()
        self.page_progress = page
        tk.Label(page, text="正在把文件复制到本机…", anchor="w",
                 font=("Microsoft YaHei UI", 10)).pack(fill="x", pady=(18, 0))
        self.bar = ttk.Progressbar(page, mode="indeterminate", length=500)
        self.bar.pack(fill="x", pady=(12, 6))
        tk.Label(page, text="安装期间请不要关闭窗口。文件较大，通常需要十几秒到一分钟。",
                 anchor="w", fg="#777777").pack(fill="x")

    def _build_result(self):
        page = self._new_page()
        self.page_result = page

        self.result_title = tk.Label(page, text="安装完成", anchor="w",
                                     font=("Microsoft YaHei UI", 12, "bold"), fg="#1A7F37")
        self.result_title.pack(fill="x")
        self.result_path = tk.Label(page, text="", anchor="w", fg="#555555")
        self.result_path.pack(fill="x", pady=(4, 10))

        self.result_opts = tk.Frame(page)
        self.result_opts.pack(fill="x")
        self.launch_var = tk.BooleanVar(value=True)
        self.afdian_var = tk.BooleanVar(value=False)
        tk.Checkbutton(self.result_opts, text="启动 " + APP_NAME + "（独立窗口）",
                       variable=self.launch_var).pack(anchor="w")
        tk.Checkbutton(self.result_opts, text="前往爱发电页面（了解会员与支持作者）",
                       variable=self.afdian_var).pack(anchor="w", pady=(6, 0))
        self.result_note = tk.Label(
            page, text="两个勾选都可以不选；以后从开始菜单或桌面快捷方式启动即可。",
            anchor="w", fg="#777777")
        self.result_note.pack(fill="x", pady=(10, 0))

        # 失败详情面板：默认隐藏；出错后展开成可滚动、可全选复制的多行文本，
        # 避免长错误被固定宽度窗口截断（朋友看到的 `安装失败: [('C:\...\_MEI...` 即此问题）。
        self.error_frame = tk.Frame(page)
        self.error_frame.pack(fill="both", expand=True, pady=(10, 0))
        self.error_frame.pack_forget()
        self.error_frame.columnconfigure(0, weight=1)
        self.error_frame.rowconfigure(0, weight=1)
        self.error_text = tk.Text(self.error_frame, height=12, wrap="word",
                                  relief="sunken", borderwidth=1)
        scroll = ttk.Scrollbar(self.error_frame, orient="vertical",
                               command=self.error_text.yview)
        self.error_text.configure(yscrollcommand=scroll.set)
        self.error_text.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        detail_row = tk.Frame(self.error_frame)
        detail_row.grid(row=1, column=0, columnspan=2, sticky="we", pady=(6, 0))
        self.log_label = tk.Label(detail_row, text="", anchor="w", justify="left",
                                  wraplength=470)
        self.log_label.pack(side="left", fill="x", expand=True)
        tk.Button(detail_row, text="复制错误", command=self._copy_error).pack(
            side="right", padx=(6, 0))
        tk.Button(detail_row, text="打开日志", command=self._open_log).pack(side="right")

    # ---------------------------------------------------------------- 翻页
    def show_page(self, index: int):
        self.page = index
        for i, page in enumerate(self.pages):
            if i == index:
                page.pack(fill="both", expand=True)
            else:
                page.pack_forget()
        title, sub = WIZARD_TITLES[index]
        if index == 3 and not self.done:
            title, sub = "安装未完成", "排查后点「重试」；安装器会先清理本次残留。"
        self.title_label.configure(text=title)
        self.sub_label.configure(text=sub)

        if index in (0, 1):
            if not self.btn_back.winfo_manager():
                # 用 before= 插回「安装」与「取消」之间，否则 side=right 会让它跑到最左
                self.btn_back.pack(side="right", padx=(0, 8), before=self.btn_cancel)
            self.btn_back.configure(state="normal" if index == 1 else "disabled")
            self.btn_cancel.configure(state="normal", text="取消")
            self.btn_next.configure(state="normal", text="下一步" if index == 0 else "安装")
            # 状态栏文字跟着按钮走：第二页的按钮已经是「安装」，不能再写「点下一步」。
            self.status.configure(
                text="点「下一步」继续。" if index == 0 else "点「安装」开始写入文件。",
                fg="#444444")
        elif index == 2:
            self.btn_back.pack_forget()
            self.btn_next.configure(state="disabled", text="正在安装…")
            self.btn_cancel.configure(state="disabled")
        else:
            self.btn_back.pack_forget()
            self.btn_cancel.configure(state="normal", text="关闭")

    def _next(self):
        if self.page == 0:
            self.show_page(1)
            return
        if self.page == 1:
            self._start()
            return
        if self.page == 3:
            if self.done:
                self._open_after_install()
                return
            # 失败页的「重试」：回到安装选项，让用户改完目录 / 勾选再装一次。
            self.error_frame.pack_forget()
            self.root.resizable(False, False)
            self.root.minsize(560, 430)
            self.root.geometry("560x430")
            self.show_page(1)
            self.status.configure(text="改正后点「安装」重试。", fg="#444444")

    def _back(self):
        if self.page == 1:
            self.show_page(0)

    def _open_wv2(self):
        webbrowser.open(WEBVIEW2_URL)

    def _browse(self):
        chosen = filedialog.askdirectory(initialdir=self.dir_var.get() or default_install_dir())
        if chosen:
            self.dir_var.set(chosen)

    def _start(self):
        if self.installing:
            return
        # 缺 WebView2 时必须先给出明确提示与安装方式，而不是装完启动才发现没有独立窗口。
        if not self.webview2 and messagebox is not None:
            go_download = messagebox.askyesno(
                "缺少 WebView2 运行时",
                "未检测到 Microsoft Edge WebView2 运行时。\n\n"
                "程序可以继续安装，但启动后会进入兼容模式（用浏览器打开），"
                "没有独立窗口与内置菜单。\n\n"
                "现在去下载并安装 WebView2 运行时吗？\n\n" + WEBVIEW2_URL)
            if go_download:
                webbrowser.open(WEBVIEW2_URL)
                return
        target = self.dir_var.get().strip() or default_install_dir()
        desktop = bool(self.desktop_var.get())
        self.install_target = target
        # 重试前清空上一次的错误面板与日志路径，状态回到正常颜色。
        self.error_text.delete("1.0", "end")
        self.error_frame.pack_forget()
        self.log_label.configure(text="")
        self.log_path = ""
        self.status.configure(text="正在准备安装…", fg="#000000")
        self.installing = True
        self.show_page(2)
        self.bar.configure(mode="indeterminate")
        self.bar.start(12)
        threading.Thread(target=self._worker, args=(target, desktop), daemon=True).start()

    def _worker(self, target: str, desktop: bool):
        try:
            install_into(target, desktop=desktop, on_step=self.events.put)
            self.events.put(("__done__", target))
        except Exception as exc:  # noqa: BLE001 - 失败必须写完整日志，不能只留半句被截断的报错
            state = getattr(exc, "eftmap_install_state", None)
            try:
                log_path = write_error_log(exc, install_dir=target, state=state)
            except Exception:  # noqa: BLE001 - 写日志失败也不能吞掉原始异常
                log_path = ""
            self.events.put(("__error__", {"exc": exc, "log_path": log_path, "state": state}))

    def _pump(self):
        # 注意：处理完成/失败事件后不能 return，否则「重试」时事件再没人消费，窗口会假死。
        try:
            while True:
                item = self.events.get_nowait()
                if isinstance(item, tuple):
                    kind, value = item
                    if kind == "__done__":
                        self._finish(value)
                    elif kind == "__error__":
                        self._fail(value)
                    continue
                self.status.configure(text=item)
        except queue.Empty:
            pass
        self.root.after(100, self._pump)

    def _finish(self, target: str):
        self.done = True
        self.installing = False
        self.install_target = target
        self.bar.stop()
        self.bar.configure(mode="determinate", value=100)
        self.result_title.configure(text="安装完成", fg="#1A7F37")
        self.result_path.configure(text="安装位置：" + target)
        self.error_frame.pack_forget()
        self.result_opts.pack(fill="x")
        self.result_note.pack(fill="x", pady=(10, 0))
        self.show_page(3)
        self.btn_next.configure(text="完成", state="normal")
        self.btn_cancel.pack_forget()
        self.status.configure(text="安装完成 · 可在开始菜单找到「" + APP_NAME + "」",
                              fg="#1A7F37")

    def _fail(self, report: dict):
        exc = report.get("exc")
        log_path = report.get("log_path") or ""
        self.log_path = log_path
        self.installing = False
        reason = classify_error(exc) if exc is not None else "未知错误"
        detail = [
            "安装未完成。",
            "",
            "当前状态：" + describe_install_state(report.get("state")),
            "",
            "失败原因：" + reason,
            "",
            "异常：" + type(exc).__name__ + ": " + _exception_text(exc),
        ]
        if log_path:
            detail.extend(["", "完整诊断日志（含 traceback 与 _MEI 解包目录文件清单）：", log_path])
            self.log_label.configure(text="日志文件：" + log_path)
        else:
            detail.extend(["", "诊断日志写入失败；请把上方异常全文复制发给开发者。"])
            self.log_label.configure(text="日志写入失败，请复制上方错误全文")
        detail.extend(["", "排查后点「重试」即可；安装器会先清理本次残留，不需要手动删目录。"])

        self.error_text.delete("1.0", "end")
        self.error_text.insert("1.0", "\n".join(detail))
        self.result_title.configure(text="安装未完成", fg="#C00000")
        self.result_path.configure(text="失败原因：" + reason)
        self.result_opts.pack_forget()
        self.result_note.pack_forget()
        self.show_page(3)
        self.error_frame.pack(fill="both", expand=True, pady=(10, 0))
        self.btn_next.configure(text="重试", state="normal")
        self.btn_cancel.configure(state="normal", text="关闭")
        self.status.configure(text="安装失败：" + reason, fg="#C00000")
        self.root.resizable(True, True)
        self.root.minsize(640, 480)
        self.root.geometry("780x620")

    def _open_log(self):
        if not self.log_path or not os.path.isfile(self.log_path):
            return
        try:
            subprocess.Popen(["notepad.exe", self.log_path])
        except OSError:
            try:
                os.startfile(self.log_path)  # type: ignore[attr-defined]
            except OSError:
                webbrowser.open("file:///" + self.log_path.replace("\\", "/"))

    def _copy_error(self):
        text = self.error_text.get("1.0", "end-1c")
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
        except Exception:  # noqa: BLE001 - 剪贴板偶发被占用，不能因此再抛错
            pass
        if self.log_path:
            self.log_label.configure(text="已复制错误全文。日志文件：" + self.log_path)
        else:
            self.log_label.configure(text="已复制错误全文。")

    def _open_after_install(self):
        """完成页的「完成」：按勾选启动程序 / 打开爱发电，然后关窗。"""
        target = self.install_target or self.dir_var.get().strip() or default_install_dir()
        try:
            if self.launch_var.get():
                exe = launch_exe(target)
                if os.path.isfile(exe):
                    subprocess.Popen([exe], cwd=target)
        finally:
            if self.afdian_var.get():
                webbrowser.open(AFDIAN_URL)
            self.root.destroy()

    def _cancel(self):
        if self.installing:
            if messagebox is not None and not messagebox.askyesno(
                    "安装尚未完成", "安装还在进行，现在关闭会中断。确定关闭吗？"):
                return
        self.root.destroy()


def app_icon_path() -> str:
    """R282：安装向导窗口图标。onefile 产物在解包目录的 payload/assets，
    仓库内直接跑时用根 assets/app.ico；找不到就保持 Tk 默认图标。"""
    base = getattr(sys, "_MEIPASS", "")
    candidates = (
        os.path.join(base, "payload", "assets", "app.ico"),
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "app.ico"),
    )
    for path in candidates:
        if os.path.isfile(path):
            return path
    return ""


def run_gui() -> int:
    global tk, ttk, filedialog, messagebox
    import tkinter as tk_mod
    from tkinter import filedialog as filedialog_mod, messagebox as messagebox_mod, ttk as ttk_mod
    tk, ttk, filedialog, messagebox = tk_mod, ttk_mod, filedialog_mod, messagebox_mod
    root = tk.Tk()
    icon = app_icon_path()
    if icon:
        try:
            root.iconbitmap(icon)
        except Exception:
            pass
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
        if not webview2_version():
            # --noconsole 产物看不到 stderr，但脚本调用 / 日志重定向时仍能留痕。
            if sys.stderr is not None:
                sys.stderr.write("警告：未检测到 WebView2 Runtime，安装后独立窗口不可用；"
                                 "请先安装 " + WEBVIEW2_URL + "\n")
        target = args.dir or default_install_dir()
        try:
            install_into(target, desktop=True)
        except Exception as exc:  # noqa: BLE001 - 静默模式同样必须留下完整诊断
            state = getattr(exc, "eftmap_install_state", None)
            try:
                log_path = write_error_log(exc, install_dir=target, state=state)
            except Exception:  # noqa: BLE001
                log_path = ""
            if sys.stderr is not None:
                sys.stderr.write("安装失败：%s\n完整诊断日志：%s\n"
                                 % (exc, log_path or "（写入失败）"))
            return 2
        return 0
    return run_gui()


if __name__ == "__main__":
    sys.exit(main())
