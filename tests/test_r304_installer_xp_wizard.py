"""R304：安装器改版为 Windows XP 时代的经典 InstallShield 向导。

两类检查：
1. **静态检查**（不依赖显示器）：布局常量、文案、失败页形态、DPI 换算；
2. **真实建窗冒烟**：真的创建一个 Tk 窗口、切四页、进失败页。没有图形环境
   （纯 SSH / CI）时自动 skip，不让打包流水线因为这个红掉。

安装引擎（`install_into` / 卸载 / 旧版清理）的用例在 test_installer.py，
这次改版只动显示层，所以那边一条都不该变。
"""

from __future__ import annotations

from pathlib import Path

import pytest

import installer

ROOT = Path(__file__).resolve().parent.parent
SOURCE = (ROOT / "tools" / "installer.py").read_text(encoding="utf-8")


# ---------------------------------------------------------------- 静态结构
def test_wizard_uses_classic_split_layout():
    """左侧品牌区 + 右侧白底内容 + 底部导航条，尺寸按任务书来。"""
    assert (installer.WIN_W, installer.WIN_H) == (640, 430)
    assert 150 <= installer.LEFT_W <= 170
    assert installer.BAR_H >= 40
    assert "def _build_brand_panel(self)" in SOURCE
    assert "def _build_bottom_bar(self)" in SOURCE
    assert "def _build_content(self)" in SOURCE
    # 换页只替换右侧内容：左侧与底栏只在建窗时构建一次
    assert SOURCE.count("def _build_brand_panel") == 1
    assert SOURCE.count("def _build_bottom_bar") == 1


def test_left_panel_has_brand_and_map_decoration():
    assert "C_BLUE_TOP" in SOURCE and "C_BLUE_BOTTOM" in SOURCE
    assert "_plate_image" in SOURCE            # 应用图标
    assert "等高线" in SOURCE                   # 地图纹理装饰
    assert "安装向导" in SOURCE


def test_bottom_bar_buttons_are_classic():
    """传统立体按钮：raised + 米灰底 + 黑焦点框，不用 ttk 扁平主题。"""
    assert 'relief="raised"' in SOURCE
    assert 'bg=C_BAR_BG' in SOURCE
    assert 'highlightcolor="#000000"' in SOURCE
    assert "上一步" in SOURCE and "下一步" in SOURCE and "取消" in SOURCE


# ---------------------------------------------------------------- 文案
FORBIDDEN_PHRASES = [
    "会装什么",
    "不会动什么",
    "这套向导会",
    "顺手做点什么",
    "了解会员与支持作者",
    "下面两个勾选",
    "通常需要十几秒",
]


def test_copy_has_no_explanatory_ai_style():
    """安装器不是使用手册：解释性、营销式表达一律不要。"""
    for phrase in FORBIDDEN_PHRASES:
        assert phrase not in SOURCE, "安装器文案里仍有：%s" % phrase


def test_four_page_titles_match_spec():
    titles = [title for title, _body in installer.WIZARD_TITLES]
    assert titles[0] == "欢迎使用 EFT 互动地图安装向导"
    assert titles[1] == "选择安装位置"
    assert titles[2] == "正在安装 EFT 互动地图"
    assert titles[3] == "EFT 互动地图安装完成"
    assert installer.FAIL_TITLE[0] == "安装未能完成"


def test_welcome_page_shows_version_path_and_keep_note():
    body = installer.WIZARD_TITLES[0][1]
    assert "安装程序将在电脑上安装 EFT 互动地图" in body
    assert "单击「下一步」继续" in body
    assert "重新安装或更新时，当前用户的配置和预设会保留。" in SOURCE
    assert '"版本", VERSION' in SOURCE
    assert "default_install_dir()" in SOURCE


def test_options_page_keeps_browse_and_shortcut_choices():
    assert "在桌面创建快捷方式" in SOURCE
    assert "开始菜单快捷方式将自动创建。" in SOURCE
    assert "浏览…" in SOURCE
    assert "下载 WebView2" in SOURCE
    assert installer.WEBVIEW2_URL.startswith("https://go.microsoft.com/fwlink/")


def test_webview2_is_not_a_blocking_prerequisite():
    """缺运行时只提示、不拦安装：说明文案在页面里，不再弹模态框。"""
    assert "仍可继续安装" in SOURCE
    assert "缺少 WebView2 运行时" not in SOURCE


def test_done_page_has_only_two_plain_options():
    assert "安装完成后启动 " in SOURCE
    assert "访问爱发电页面" in SOURCE
    assert 'self.launch_var = tk.BooleanVar(value=True)' in SOURCE
    assert 'self.afdian_var = tk.BooleanVar(value=False)' in SOURCE
    assert 'text="完成"' not in SOURCE      # 文案是动态设的，不能写死
    assert '"完成"' in SOURCE


# ---------------------------------------------------------------- 进度 / 失败
def test_progress_bar_is_a_marquee_without_fake_percent():
    """复制进度拿不到逐文件反馈，就用经典循环块，不编百分比。"""
    assert 'mode="indeterminate"' not in SOURCE
    assert "def _bar_tick(self)" in SOURCE
    assert "def _bar_finish(self)" in SOURCE
    assert "35%" not in SOURCE and "68%" not in SOURCE


def test_failure_page_stays_compact_and_keeps_diagnostics():
    # 不再把窗口撑成 780x620
    assert 'geometry("780x620")' not in SOURCE
    assert "复制错误信息" in SOURCE
    assert "打开日志" in SOURCE
    assert 'text="重试"' not in SOURCE and '"重试"' in SOURCE
    # 完整异常仍然写日志、也仍然可复制
    assert "write_error_log" in SOURCE


def test_install_error_message_becomes_readable_reason():
    """引擎抛的中文原因不能被关键字规则吞成「未识别的错误」。"""
    exc = installer.InstallError("安装目录不为空，且不是本程序的旧版本：C:\\x\n请换一个空目录。")
    assert installer.classify_error(exc).startswith("安装目录不为空")
    # 非 InstallError 仍走原来的关键字分类
    assert "磁盘空间不足" in installer.classify_error(
        OSError(28, "No space left on device"))


def test_unknown_error_still_asks_for_log():
    assert "未识别的错误" in installer.classify_error(RuntimeError("boom"))


# ---------------------------------------------------------------- DPI
def test_dpi_helpers():
    assert installer._blend("#000000", "#ffffff", 0.0) == "#000000"
    assert installer._blend("#000000", "#ffffff", 1.0) == "#ffffff"
    assert installer._blend("#0b2c60", "#1b56a4", 0.5) == "#134182"


def test_dpi_awareness_is_declared_before_window_creation():
    """不声明 DPI 感知，系统会把窗口当位图拉伸，125%/150% 下发虚。"""
    assert "def _enable_dpi_awareness()" in SOURCE
    gui = SOURCE[SOURCE.index("def run_gui()"):]
    assert gui.index("_enable_dpi_awareness()") < gui.index("tk.Tk()")


# ---------------------------------------------------------------- 真实建窗
def _make_window(monkeypatch):
    tk = pytest.importorskip("tkinter")
    from tkinter import filedialog, messagebox, ttk

    monkeypatch.setattr(installer, "tk", tk)
    monkeypatch.setattr(installer, "ttk", ttk)
    monkeypatch.setattr(installer, "filedialog", filedialog)
    monkeypatch.setattr(installer, "messagebox", messagebox)
    try:
        root = tk.Tk()
    except Exception as exc:  # noqa: BLE001 - 无图形环境（CI/SSH）就跳过
        pytest.skip("没有可用的图形环境：%s" % exc)
    root.withdraw()
    return root, installer.InstallWindow(root)


def test_window_builds_and_switches_all_pages(monkeypatch):
    root, win = _make_window(monkeypatch)
    try:
        assert win.title_label.cget("text") == installer.WIZARD_TITLES[0][0]
        assert str(win.btn_next.cget("text")) == "下一步"
        assert str(win.btn_back.cget("state")) == "disabled"

        win.show_page(1)
        assert win.title_label.cget("text") == "选择安装位置"
        assert str(win.btn_next.cget("text")) == "安装"
        assert str(win.btn_back.cget("state")) == "normal"

        win.show_page(2)
        assert str(win.btn_next.cget("text")) == "正在安装…"
        assert str(win.btn_next.cget("state")) == "disabled"
        assert str(win.btn_cancel.cget("state")) == "disabled"

        win._fail({"exc": installer.InstallError("磁盘空间不足。请清理磁盘后重试。"),
                   "log_path": "", "state": {}})
        assert win.title_label.cget("text") == "安装未能完成"
        assert "磁盘空间不足" in win.fail_reason.cget("text")
        assert str(win.btn_next.cget("text")) == "重试"
        assert str(win.btn_cancel.cget("text")) == "关闭"
        assert "磁盘空间不足" in win.error_text.get("1.0", "end-1c")
    finally:
        root.destroy()


def test_retry_goes_back_to_options(monkeypatch):
    root, win = _make_window(monkeypatch)
    try:
        win.show_page(2)
        win._fail({"exc": RuntimeError("boom"), "log_path": "", "state": {}})
        win._next()                      # 失败页的「重试」
        assert win.page == 1
        assert str(win.btn_next.cget("text")) == "安装"
    finally:
        root.destroy()


def test_button_order_survives_page_round_trip(monkeypatch):
    """「上一步 / 下一步 / 取消」的顺序要固定。

    side="right" 下先 pack 的在最右，从安装中页回到选项页时如果插错位置，
    会变成「安装 / 上一步 / 取消」——肉眼很容易漏掉。
    """
    root, win = _make_window(monkeypatch)
    try:
        win.show_page(2)                 # 进度页把「上一步」摘掉
        win.show_page(1)                 # 重新插回
        root.update_idletasks()
        ordered = sorted([(win.btn_back.winfo_x(), "上一步"),
                          (win.btn_next.winfo_x(), "安装"),
                          (win.btn_cancel.winfo_x(), "取消")])
        assert [name for _x, name in ordered] == ["上一步", "安装", "取消"]
        assert win.btn_back.winfo_x() < win.btn_next.winfo_x() < win.btn_cancel.winfo_x()
    finally:
        root.destroy()


# ---------------------------------------------------------------- 静默模式
def test_create_shortcut_retries_transient_replace_error(tmp_path, monkeypatch):
    """覆盖已有 .lnk 时被杀软/资源管理器短暂占用（WinError 5）不能判死刑。

    实测踩到过：程序文件已全部就位，最后一步改名失败，整个安装停在失败页。
    """
    lnk = tmp_path / "EFT 互动地图.lnk"
    lnk.write_bytes(b"old")
    calls = {"replace": 0}
    real_replace = installer.os.replace

    def flaky_replace(src, dst):
        calls["replace"] += 1
        if calls["replace"] == 1:
            raise PermissionError(13, "Access is denied", str(src), str(dst))
        return real_replace(src, dst)

    def fake_run(cmd, **kwargs):
        idx = cmd.index("-Lnk")
        Path(cmd[idx + 1]).write_bytes(b"new-lnk")

        class _R:
            returncode = 0

        return _R()

    monkeypatch.setattr(installer.subprocess, "run", fake_run)
    monkeypatch.setattr(installer.os, "replace", flaky_replace)
    monkeypatch.setattr(installer.time, "sleep", lambda _s: None)

    installer.create_shortcut(str(lnk), r"C:\app\EFTMap.exe", r"C:\app",
                              r"C:\app\EFTMap.exe")

    assert calls["replace"] == 2          # 第一次失败后重试成功
    assert lnk.read_bytes() == b"new-lnk"


def test_create_shortcut_timeout_is_a_readable_install_error(tmp_path, monkeypatch):
    """PowerShell 被安全软件卡住时不能无限等，要给出可读原因。"""
    def slow_run(cmd, **kwargs):
        raise installer.subprocess.TimeoutExpired(cmd, 120)

    monkeypatch.setattr(installer.subprocess, "run", slow_run)
    with pytest.raises(installer.InstallError):
        installer.create_shortcut(str(tmp_path / "x.lnk"), r"C:\a.exe", "C:\\",
                                  r"C:\a.exe")


def _stub_payload(tmp_path: Path) -> Path:
    payload = tmp_path / "payload"
    (payload / "_internal").mkdir(parents=True)
    (payload / installer.APP_EXE).write_bytes(b"app")
    (payload / "_internal" / "index.html").write_text("x", encoding="utf-8")
    return payload


def test_silent_install_still_works(tmp_path, monkeypatch):
    """--silent 不建窗口，但仍要走完整安装流程（改版不能碰这条路径）。"""
    payload = _stub_payload(tmp_path)
    target = tmp_path / "installed"
    setup_exe = tmp_path / "setup.exe"
    setup_exe.write_bytes(b"setup")
    registered: list[str] = []

    monkeypatch.setattr(installer, "payload_root", lambda: str(payload))
    monkeypatch.setattr(installer, "create_shortcut", lambda *a, **k: None)
    monkeypatch.setattr(installer, "write_uninstall_entry", registered.append)
    monkeypatch.setattr(installer.sys, "executable", str(setup_exe))
    monkeypatch.setattr(installer, "webview2_version", lambda: "120.0.0.0")

    assert installer.main(["--silent", "--dir", str(target)]) == 0
    assert (target / installer.APP_EXE).read_bytes() == b"app"
    assert (target / installer.UNINSTALL_EXE).exists()
    assert registered == [str(target)]
