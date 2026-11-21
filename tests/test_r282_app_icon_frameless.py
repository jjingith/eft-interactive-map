"""R282（0.2.7.4）：应用图标替换 + 主窗口彻底无边框。

用户给了新图标（02-塔科夫/图标.png），要求：
1. 应用统一用这张图（exe / 壳 / 托盘 / 安装器 / 浏览器标签）；
2. 去掉主窗口原有的 40px 自绘标题栏，页面铺满整窗，只保留页面内的窗口按钮。

本文件只做静态契约与图标文件校验；真实窗口外观由壳的 `--capture` 截图人工核对。
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent


def read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


# --------------------------------------------------------------- 图标文件

def test_app_icon_and_favicon_are_the_same_multi_size_ico():
    app_icon = ROOT / "assets" / "app.ico"
    favicon = ROOT / "favicon.ico"
    assert app_icon.is_file(), "assets/app.ico 必须存在（壳 / 安装器 / 安装包共用）"
    assert favicon.is_file(), "站点 favicon.ico 必须存在"
    # 同一份图标：两个文件应逐字节一致（都由图标.png 生成）
    assert app_icon.read_bytes() == favicon.read_bytes()

    sizes = Image.open(app_icon).info.get("sizes") or set()
    for need in ((16, 16), (32, 32), (48, 48), (256, 256)):
        assert need in sizes, "ICO 缺少 %s 尺寸：%s" % (need, sizes)


def test_index_html_still_points_at_favicon():
    html = read("index.html")
    assert 'rel="icon"' in html and "favicon.ico" in html


# --------------------------------------------------------------- 壳：图标 + 无边框

def test_host_build_embeds_icon_in_exe_and_managed_resource():
    ps1 = read("tools/host/build.ps1")
    assert "$appIcon = Join-Path $repoRoot \"assets\\app.ico\"" in ps1
    assert '"/win32icon:$appIcon"' in ps1
    assert '"/resource:$appIcon,AppIcon"' in ps1

    shell = read("tools/host/src/DesktopShell.cs")
    assert 'GetManifestResourceStream("AppIcon")' in shell
    assert "Icon = AppIcon();" in shell
    assert "_tray.Icon = AppIcon(16);" in shell
    # 旧标题栏与默认图标都不能回来
    assert "_titleBar" not in shell
    assert "MakeTitleButton" not in shell
    assert "TitleHeight" not in shell


def test_shell_has_no_native_title_bar_and_injects_page_controls():
    shell = read("tools/host/src/DesktopShell.cs")
    # 页面内注入：tk-frameless + 三个按钮 + 拖动
    assert "FramelessChromeScript" in shell
    assert "AddScriptToExecuteOnDocumentCreatedAsync(FramelessChromeScript)" in shell
    for token in ("tk-frameless", "win-controls", "shell:min", "shell:max",
                  "shell:close", "shell:drag", "BeginWindowDrag", "OnDragTick",
                  "GetAsyncKeyState(0x01)"):
        assert token in shell, token
    # WebView2 子窗持有鼠标捕获，主窗拖动不能依赖 ReleaseCapture + WM_NCLBUTTONDOWN
    assert "Native.BeginDrag(Handle)" not in shell
    # 只对主窗口生效：小地图 URL 跳过
    assert "mini=(?:1|true)?" in shell
    # 脉冲式 WebMessage 契约
    assert "WebMessageReceived += OnMainWebMessage" in shell
    assert "IsWebMessageEnabled = true" in shell


def test_webview_fills_window_except_status_strip():
    shell = read("tools/host/src/DesktopShell.cs")
    assert "int top = _status != null && _status.Visible ? _status.Height : 0;" in shell
    # 顶部的 HTCAPTION 命中已删除（否则页面顶部 40px 永远收不到点击）
    assert "p.Y < TitleHeight" not in shell
    assert "IntPtr(Native.HTCAPTION)" not in shell


def test_frameless_css_is_scoped():
    css = read("style.css")
    assert "body.tk-frameless #app-brand" in css
    assert "html body.tk-frameless #app-menubar-right #win-controls" in css
    assert "html body.tk-frameless #win-controls .win-btn" in css
    assert "html body.tk-frameless #win-controls .win-close" in css


# --------------------------------------------------------------- 打包链

def test_main_build_and_setup_use_the_icon():
    build = read("build/build.ps1")
    assert '"--icon", $appIcon' in build
    release = read("build/build_release.ps1")
    assert '"--icon", $appIcon' in release
    # 安装向导窗口图标需要运行期文件：payload/assets/app.ico
    assert 'Join-Path $Target "assets"' in release
    assert 'Join-Path $iconDir "app.ico"' in release


def test_installer_window_uses_the_icon():
    py = read("tools/installer.py")
    assert "def app_icon_path()" in py
    assert 'os.path.join(base, "payload", "assets", "app.ico")' in py
    assert "root.iconbitmap(icon)" in py
