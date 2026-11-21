# R71 台账：双击 exe 必须打开独立窗口（禁止默认弹浏览器）

host=HOMONAS user=MASTERJJ at=2026-11-04 23:45:55 +08:00

## 0. 用户现在该双击哪个文件

**双击 `EFTMap.exe` 或安装器生成的开始菜单/桌面快捷方式**（快捷方式 Target 固定为
`EFTMapDesktop.exe`）。结果：打开 1044×720 无边框独立窗口，自定义标题栏可拖动/最小化/关闭，
任务栏不出现窗口按钮（`WS_EX_TOOLWINDOW`），默认浏览器进程数不变（new=0），后端在 8787 提供数据。

## 1. 诊断结论（为什么原来会开浏览器）

| 入口 | R71 前行为 | 判定条件 | 结论 |
| --- | --- | --- | --- |
| `EFTMap.exe` 双击（无参数） | `main()` 落到 `run_legacy_ui()`：起 Tk 启动窗 + `auto_start` 起服务并 `webbrowser.open` | **没有显式 `--server-only` 就走浏览器路径**（并非“壳文件缺失才走”） | 根因：默认分支选错，与壳是否存在无关 |
| `EFTMapDesktop.exe` 双击 | 直接起无边框壳 | — | 本来正确，但用户拿到的入口不是它 |
| `EFTMap-AppWindow.exe` | 旧版浏览器 `--app` 兼容入口 | 显式 `--app-window` 才使用 | 未参与默认路径 |
| 快捷方式 Target | `launch_exe()` 优先 `EFTMapDesktop.exe`，缺失才回退 `EFTMap.exe` | 安装包内壳存在时正确 | 早期安装包未并入壳时 Target 会落到 `EFTMap.exe` → 触发上表浏览器路径 |

结论：不是 WebView2 或壳坏了，而是 **`EFTMap.exe` 无参数默认分支**在旧代码里就是“Tk + 浏览器”。
修复把默认分支改成壳，并对“壳缺失”单独做显式提示。

## 2. 修复点

| 文件 | 改动 |
| --- | --- |
| `tools/launcher.py` | 新增 `--browser`；无参数/普通参数 → `launch_desktop_shell()`；`desktop_shell_path()` 依次查 exe 目录、`_internal`、`tools/host/bin`；壳缺失/启动失败 → 中文 MessageBox（默认「否」），只有选「是」才回退浏览器；保留 `--server-only`、`--settings-only`、`--app-window`；`--help` 注明 EFTMap.exe 仅作壳的后端启动器 |
| `tools/host/src/DesktopShell.cs` | `ShowInTaskbar=false`；`CreateParams` 加 `WS_EX_TOOLWINDOW (0x80)`、去 `WS_EX_APPWINDOW (0x40000)`；`FallbackForm` 不再在 `Shown` 自动开浏览器，只显示中文说明与「用浏览器打开」按钮（用户主动点击才开） |
| `tools/installer.py` | 未改逻辑：`launch_exe()` 已优先 `EFTMapDesktop.exe`；本台账实测用其生产函数 `create_shortcut()` 生成 `.lnk` 验证 Target |
| `build/build.ps1` / `build/build_release.ps1` | 收尾提示改为“双击 EFTMap.exe 打开无边框独立窗口”；说明快捷方式 Target 为壳 |
| `tests/test_launcher.py` | 新增 4 条：`--browser` 默认关闭、无参数只走壳、`--server-only` 不走壳/UI、`--browser` 走 UI |

端口/进程复用：壳自身单实例 Mutex/Event 已覆盖“再次双击 EFTMap.exe”路径；第二次启动会激活旧窗口并退出，
不会起第二份后端。壳启动后端仍用 `EFTMap.exe --server-only --shell-mode --parent-pid`，Job Object 随壳退出回收。

## 3. 六条验收（最终 dist 实测，非读代码）

| # | 场景 | 结果 | 证据 |
| --- | --- | --- | --- |
| 1 | 双击 `EFTMap.exe` 无参数 | 无边框窗口 1044×720；`caption=False toolwindow=True exstyle=0x00010180`；浏览器 62→62 new=0；端口 8787 | `smoke/01-zero-arg-final.png`、`smoke/browser-evidence.txt` |
| 2 | 双击快捷方式（Target=`EFTMapDesktop.exe`） | 同上：1044×720、toolwindow、浏览器 63→63 new=0 | `smoke/02-shortcut-final.png` |
| 3 | `EFTMap.exe --server-only` | health=200、无壳窗口、浏览器 64→64、退出后端口回收 | `browser-evidence.txt` |
| 4 | `EFTMap.exe --browser` | 显式打开浏览器，浏览器进程 62→66（新增 4 个） | `browser-evidence.txt` |
| 5 | 壳改名缺失 | 中文 MessageBox 496×243（标题「EFT 互动地图 · 独立窗口不可用」），默认「否」，浏览器 63→63，未起服务 | `smoke/03-missing-shell-final.png` |
| 6 | 关窗后回收 | `shell=0 backend=0 port8787=0` | `browser-evidence.txt` |

补充：真实安装目录的快捷方式未在本机存在（读 `%APPDATA%` 开始菜单与桌面均无 `EFT 互动地图.lnk`），
因此用 `installer.create_shortcut()` 的生产实现生成临时 `.lnk`（Target 指向壳）完成第 2 条；
真实安装时会话路径为 ASCII `%LOCALAPPDATA%\EFTMap`，`launch_exe()` 解析结果同样是 `EFTMapDesktop.exe`。

托盘截图说明：当前非交互会话执行 `CopyFromScreen` 返回 “handle is invalid”，无法截取系统托盘区域；
无边框窗口实拍已包含自绘标题栏（最小化/最大化/关闭），任务栏按钮缺失以 `WS_EX_TOOLWINDOW`
（`exstyle=0x00010180`）与 `ShowInTaskbar=false` 实测值作为等价证据。

## 4. 构建与产物

- `build.ps1`：清单预检 **13241 / 13241**，0 缺失、0 未登记；产物 155.1 MB。
- `build_release.ps1 -SkipBase`：并入壳 3 个文件（`EFTMapDesktop.exe`、`Microsoft.Web.WebView2.Core.dll`、`WebView2Loader.dll`）。
- 三件套（release/）：

| 文件 | 体积 | SHA256 |
| --- | --- | --- |
| `EFTMap-AppWindow-0.1.0.zip` | 116.91 MB | `69A7A5239E7DA4073D00582641F76BD43929AFCEC2EB1F17ED75BBB9F3260F7D` |
| `EFTMap-Portable-0.1.0.zip` | 116.91 MB | `B032430F4E2F744C5B02AF2250C64F97C1E85E19B68C6E7A67BD7823A68BA773` |
| `EFTMap-Setup-0.1.0.exe` | 127.27 MB | `AA1DE153213AF9B2A4A156317956768BD3DB4D1ADD9F2FDB619B0F11807B22DD` |

`pytest tests -q`：**1740 passed, 1 skipped**（R71 新增 4 条 launcher 回归全过）。

未 git commit。
