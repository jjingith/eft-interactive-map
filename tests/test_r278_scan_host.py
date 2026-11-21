"""R278b：把「截图识别宿主」真正装进客户端，并把安装器改成经典分步向导。

用户反馈：朋友装完安装包后「价格识别按快捷键没有反应」。排查结论不是环境缺依赖
（OCR 的 onnxruntime / cv2 / 模型都在包里），而是 **宿主进程 scan.py 从来没被打包**：
它只存在于开发机的登录自启任务里，客户端根本没有进程去注册全局热键。

这里锁住：
1. scan.py / overlay.py 进包（spec + build.ps1 的 --add-data + 必检清单）；
2. 主程序启动后自动拉起宿主、退出时收掉；
3. 宿主单实例（旧自启任务残留时不能抢热键）；
4. 安装器是分步向导，完成页两个勾选（启动互动地图 / 前往爱发电）。
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_scan_host_is_in_pyinstaller_spec():
    spec = (ROOT / "build" / "EFTMap.spec").read_text(encoding="utf-8")
    assert "tools/scan.py', 'tools'" in spec
    assert "tools/overlay.py', 'tools'" in spec


def test_scan_host_is_added_in_build_script():
    script = (ROOT / "build" / "build.ps1").read_text(encoding="utf-8-sig")
    assert "--add-data" in script
    assert "tools\\scan.py;tools" in script
    assert "tools\\overlay.py;tools" in script
    # 必检清单里也要有，否则少文件能静默出包
    assert "tools\\scan.py" in script.split("$MustHave")[1]


def test_launcher_starts_and_stops_ocr_host():
    source = (ROOT / "tools" / "launcher.py").read_text(encoding="utf-8")
    assert "def start_ocr_host(self):" in source
    assert "def stop_ocr_host(self):" in source
    assert "self.start_ocr_host()" in source
    assert "self.stop_ocr_host()" in source
    # 冻结产物里必须通过 --run-tool 跑同一份解释器，不能把 EFTMap.exe 当 python
    assert '"--run-tool", script' in source
    # 允许用环境变量整体关掉（排查 / 自动化）
    assert "EFT_OCR_HOST" in source


def test_scan_host_is_single_instance():
    source = (ROOT / "tools" / "scan.py").read_text(encoding="utf-8")
    assert "def acquire_single_instance(" in source
    assert "CreateMutexW" in source
    assert "SINGLE_INSTANCE_NAME" in source
    assert "if not acquire_single_instance():" in source


def test_scan_host_logs_to_localappdata_when_frozen():
    source = (ROOT / "tools" / "scan.py").read_text(encoding="utf-8")
    assert 'if getattr(sys, "frozen", False):' in source
    assert '"EFTMap", "logs"' in source


def test_scan_host_dependencies_are_bundled():
    """宿主是随包脚本，PyInstaller 不会分析它的 import：PIL 必须显式收进来。

    实测漏了 PIL 时，宿主启动到「热键注册成功」就 ModuleNotFoundError 退出，
    表现正是用户说的「按快捷键没反应」。
    """
    script = (ROOT / "build" / "build.ps1").read_text(encoding="utf-8-sig")
    for module in ("PIL", "PIL.Image", "PIL.ImageDraw", "PIL.ImageGrab", "PIL.ImageFont"):
        # 两种写法都算：直接拼行（"--hidden-import PIL"）或参数数组
        # （"--hidden-import", "PIL"——改成数组是为了把 PyInstaller 的 stderr 重定向到日志，
        #  否则 PowerShell 会把 INFO 当 NativeCommandError 终止构建）。
        assert ("--hidden-import " + module) in script \
            or ('"--hidden-import", "%s"' % module) in script, module
    spec = (ROOT / "build" / "EFTMap.spec").read_text(encoding="utf-8")
    assert "'PIL.ImageGrab'" in spec


def test_run_tool_writes_failure_log():
    source = (ROOT / "tools" / "launcher.py").read_text(encoding="utf-8")
    assert "def _log_tool_failure(" in source
    assert '"run-tool.log"' in source
    assert "_log_tool_failure(script, traceback.format_exc())" in source


def test_installer_is_a_step_by_step_wizard():
    source = (ROOT / "tools" / "installer.py").read_text(encoding="utf-8")
    assert "class InstallWindow:" in source
    assert "WIZARD_TITLES" in source
    assert "def show_page(self, index: int):" in source
    assert "def _next(self):" in source
    assert "def _back(self):" in source
    # 四页：欢迎 / 选项 / 进度 / 完成
    assert "self.page_welcome" in source
    assert "self.page_options" in source
    assert "self.page_progress" in source
    assert "self.page_result" in source


def test_finish_page_has_both_checkboxes():
    source = (ROOT / "tools" / "installer.py").read_text(encoding="utf-8")
    assert 'AFDIAN_URL = "https://afdian.com/item/' in source
    assert "self.launch_var" in source
    assert "self.afdian_var" in source
    assert "启动 \" + APP_NAME + \"（独立窗口）" in source
    assert "前往爱发电页面" in source
    # 完成按钮必须真的按勾选动作
    assert "def _open_after_install(self):" in source
    assert "webbrowser.open(AFDIAN_URL)" in source
