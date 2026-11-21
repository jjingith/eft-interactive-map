# R75 台账：纯本地客户端 · 无控制台窗口

host=HOMONAS user=MASTERJJ at=2026-11-05 14:10:00 +08:00

## 0. 结论先行

**双击 `EFTMap.exe` / `EFTMapDesktop.exe` 本来就不弹 cmd。** 两条入口的 PE 子系统都是 `GUI(2)`，
壳拉起后端用 `UseShellExecute=false + CreateNoWindow=true`，实测 60 秒内没有新增 `conhost.exe`、
没有新增可见控制台窗口、没有由本次启动派生的浏览器进程。

会闪控制台的是**安装器**：建快捷方式时 `subprocess.run(["powershell", ...])` 没带
`CREATE_NO_WINDOW`，powershell 是控制台子系统程序，父进程（`--noconsole` 的安装器）没有控制台，
系统就给它新建一个可见窗口。本轮已修，并有改前/改后的复现对照（第 2 节 [3]）。

另外一处只在**开发态**会闪：托盘「高级设置」回退到 `python.exe` 分支没有隐藏窗口，本轮一并修掉。

前端视觉零改动；本轮不 commit。

## 1. A：五条启动路径逐条审计

| # | 路径 | 关键事实（证据） | 结论 |
| --- | --- | --- | --- |
| 1 | `dist\EFTMap\EFTMap.exe`（PyInstaller onedir） | PE 可选头 `Subsystem=2`（脚本 `-0x3C`→e_lfanew→`+24+68` 读出 2）；`build\EFTMap.spec` 里 `console=False, windowed=True`；`build\build.ps1` 用 `--onedir --noconsole` | GUI，**不会**分配控制台 |
| 2 | `EFTMapDesktop.exe` 起后端 | `DesktopShell.cs` 后端 `ProcessStartInfo`：`UseShellExecute=false`、`CreateNoWindow=true`（等价 `CREATE_NO_WINDOW`）；PE `Subsystem=2`（`tools\host\build.ps1` 用 `/target:winexe`） | 无 `STARTF_USESHOWWINDOW/SW_HIDE` 也不影响：不创建控制台就没有窗口可显示 |
| 2b | stdio 处理（本轮新增） | 同上：`RedirectStandardOutput/Error=true` + UTF8 + `BeginOutputReadLine/BeginErrorReadLine`，逐行写进 `%LOCALAPPDATA%\EFTMap\logs\desktop.log`，前缀 `[backend:out]` / `[backend:err]` | 与需求「接管道或 NUL」对齐；不再出现 PyInstaller 启动报错无处可看的情况 |
| 3 | `tools\launcher.py` | `harden_stdio()` 在 `main()` 入口统一把 `stdout/stderr/stdin` 为 None 的情况换成 devnull；`--server-only` 分支 `open_browser=lambda url: None`，不起 Tk、不开浏览器；`launch_desktop_shell()` 的 `Popen` 本轮补 `CREATE_NO_WINDOW`（目标本身是 GUI，属于兜底） | 无窗口、无浏览器 |
| 3b | 落到裸 `python.exe` 的路径 | ①壳 `--backend-mode python`（仅开发/调试）；②托盘「高级设置」在仓库根没有 `EFTMap.exe` 时回退 `python.exe --settings-only`。两处均已 `CreateNoWindow=true`（②本轮补） | 开发态也不闪 |
| 4 | 安装器 / 卸载延迟删除 cmd | `installer.py` 的延迟删除：`creationflags = CREATE_NO_WINDOW \| DETACHED_PROCESS`，`cwd=<temp 目录>`（保持原样）；卸载器 `Uninstall.exe` 是 `EFTMap.exe` 的副本（GUI 子系统） | ✓ 未破坏 |
| 4b | 安装器建快捷方式（本轮修复） | 旧：`subprocess.run(["powershell", ...])` 无 flags → 可见 PowerShell 窗口；新：`creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0)` | 见第 2 节 [3] 实测 |
| 5 | 无参数启动是否触发 `os.startfile` / `webbrowser.open` | 全仓库扫描：`os.startfile` 只在 launcher 的「试听音频」按钮；`webbrowser.open` 只在 `open_app_window()` 的兜底（仅 `--browser` / `appmode.flag` 路径）与 `serve.py __main__`（直接跑 serve.py 时）；`overlay.py` 的浏览器拉起只在旧 `/api/overlay` 路径（壳模式禁用） | 无参数双击不触发；实测浏览器派生 = 0 |

## 2. B：实测对照（改前 / 改后）

测试方法：`docs\r75-local-client-no-console\measure-console.ps1`（脚本会先结束残留 EFTMap 进程，
采集基线 `conhost.exe` 集合 / 可见控制台窗口集合 / 浏览器主进程集合，再启动目标，
25 秒后比对；随后 60 秒采样壳 + 后端 + WebView2 的全部 TCP 端点）。

| 场景 | 改前 | 改后 | 证据 |
| --- | --- | --- | --- |
| 双击 `dist\EFTMap\EFTMap.exe` | 新增 conhost 0；新增可见控制台 0；派生浏览器 0；壳窗口 `exstyle=0x00010180`（TOOLWINDOW，不进任务栏） | 同上：conhost 0 / 控制台 0 / 浏览器 0 | `evidence\01-EFTMap-exe.txt` |
| 双击 `dist\EFTMap\EFTMapDesktop.exe` | 同上 | 同上：conhost 0 / 控制台 0 / 派生浏览器 0（新增的两条 chrome 是既有浏览器实例 `pid=33672` 的 renderer 子进程，`本次启动派生=False`） | `evidence\02-EFTMapDesktop-exe.txt` |
| 安装器建快捷方式（powershell） | **新增 1 个可见控制台窗口**：`title=管理员: ...\WindowsPowerShell\v1.0\powershell.exe` | 新增 0；`installer.create_shortcut()` 用真实生产代码复测：窗口 0、`.lnk` 生成成功、返回 `ok` | `evidence\03-installer-powershell.txt` |
| PE 子系统 | `EFTMap.exe=2`、`EFTMapDesktop.exe=2` | 同（打包流程新增断言，非 GUI 直接 fail） | `build\build_release.ps1` |

补充说明（避免误判）：

- 改前两条入口已经是 GUI，所以「改前也有控制台」只出现在**安装器**这一条；这一点用隔离复现证实，
  不是靠读代码推断。
- 那次新增的 `chrome.exe --type=renderer` 属于系统里**已存在**的 Chrome（父进程 `33672`，
  创建于上午 09:21，命令行无 `--app=`），与本次启动无关；脚本已按「祖先链里是否出现我们的 PID」判定。
- 实测时小地图窗口是可见的（`title=EFT 小地图`），因为用户配置里 `overlay.enabled=true`；
  这是既有行为，不是残留进程。

## 3. C：纯本地证明

**系统侧取证（60 秒采样，壳 + 后端 + 全部 WebView2 子进程）**

| 启动方式 | 采到的端点（去重） | 非回环远端连接 |
| --- | --- | --- |
| `EFTMap.exe` | `127.0.0.1:8787`、`127.0.0.1:1725..1733`（WebView2 IPC）、`0.0.0.0:0 [Listen/Bound]` | **（无）** |
| `EFTMapDesktop.exe` | `127.0.0.1:<port>`、`127.0.0.1:1972..1982`（WebView2 IPC）、`0.0.0.0:0 [Listen/Bound]` | **（无）** |

**代码侧证据**

- WebView2 环境参数已带 `--disable-background-networking` 等离线开关（`DesktopShell.cs` 创建环境处），
  杜绝 Chromium 后台联网（组件更新 / 变体 / 遥测）。
- 前端离线判据：`tests/_offline_guard.py` 的「加载型」模式 + 白名单，`tests/test_offline_guard.py` 通过。
- 在线行情是唯一的外连能力，默认关闭：`config.py` `LIVE_PRICES_DEFAULTS = {"enabled": False}`；
  不开启时不访问 `json.tarkov.dev`。
- 本轮回归：`pytest tests/test_offline_guard.py tests/test_launcher.py tests/test_serve.py tests/test_r42_live_prices.py`
  → **172 passed**。

## 4. D：修复清单与影响面

| 文件 | 改动 | 用户可感知的影响 |
| --- | --- | --- |
| `tools\installer.py` | 建快捷方式的 powershell 调用加 `CREATE_NO_WINDOW` | 安装/覆盖安装时**不再闪 PowerShell 窗口** |
| `tools\host\src\DesktopShell.cs` | 后端 stdout/stderr 接管道并写入 `desktop.log`；`OpenAdvancedSettings` 的 python 回退加 `CreateNoWindow` | 正常使用无变化；日志多出 `[backend:out] / [backend:err]` 行（排障用） |
| `tools\launcher.py` | 拉起壳的 `Popen` 加 `CREATE_NO_WINDOW`（兜底） | 无可见变化 |
| `tools\serve.py` | `/api/overlay` 拉起子进程加 `CREATE_NO_WINDOW`；冻结产物改用 `--run-tool` 而不是把 `EFTMap.exe` 当 python | 仅浏览器回退模式相关；壳模式不受影响 |
| `tools\overlay.py` | 两处 `taskkill` 加 `CREATE_NO_WINDOW` | 旧浮窗关闭路径不再闪控制台 |
| `build\build_release.ps1` | 发布前断言 `EFTMap.exe` / `EFTMapDesktop.exe` / Setup 的 PE 子系统 = 2；校验两个 zip 里确实有 `EFTMapDesktop.exe` | 打包失败会更早、更明确；产物更可信 |

未改动：`app.js` / `index.html` / `style.css` / 地图渲染 / 小地图窗口逻辑 / 任何前端资源。

## 5. 出包（与 R76 合并为一次）

按本轮指令「先修控制台，再动窗口层，最后一次性重打包」，R76 完成后只跑了一次全量打包。

| 产物 | 大小 | SHA256 |
| --- | --- | --- |
| `release\EFTMap-Portable-0.1.0.zip` | 118.5 MB | `B575ADD0C714DE0EEE979ADDDD31A62F02D209A9509000FC8A90F6A3CBD4628A` |
| `release\EFTMap-AppWindow-0.1.0.zip` | 118.5 MB | `2885A6CDDAD9774DAA7BDF4B17BC403BAA95C72BCD0AFBDA190E40C3ED76CA54` |
| `release\EFTMap-Setup-0.1.0.exe` | 128.8 MB | `4DF309C6EA21DE49A9FD9268415846F8F4B8CBF175A31CBC90276A192564CD73` |

- 打包流程断言：`EFTMap.exe` / `EFTMapDesktop.exe` / Setup 的 PE 子系统全部 `GUI(2)`；
  Portable / AppWindow 两个 zip 都含 `EFTMapDesktop.exe`（否则直接 fail）。
- 清单双向校验（打包后重跑）：预期 **13312**、staging **13312**、缺失 0、未登记 0。
  原始输出：`docs\r76-window-parity\verify-after-build.txt`、`release-build.log`、`release-hashes.txt`。
- 冒烟（解压 Portable，走真实入口 `EFTMap.exe`）：`EFTMapDesktop.exe` → 子进程
  `EFTMap.exe` 监听 `127.0.0.1:8787` + `msedgewebview2.exe`；**conhost 子进程 0**；任务栏 1 个图标。
  原始输出：`docs\r76-window-parity\evidence-smoke.txt`。
- Setup 未实机安装（避免写入用户桌面快捷方式）；安装器代码本轮未改，PE 校验通过。

## 6. 用户可自测的验收步骤

1. 卸载旧版 → 运行新的 `EFTMap-Setup-0.1.0.exe`：**整个安装过程不应出现任何 PowerShell / cmd 窗口**；
   装完自动拉起主窗口。
2. 双击桌面快捷方式（Target 应为 `EFTMapDesktop.exe`）：任务栏/桌面上**没有黑色控制台窗口**。
3. 打开任务管理器 → 详细信息：应看到 `EFTMapDesktop.exe` 与其子进程 `EFTMap.exe`，
   **不应出现与它们相关的 `conhost.exe`**。也可以在 PowerShell 里跑：
   `Get-CimInstance Win32_Process -Filter "Name='conhost.exe'" | Select ProcessId,ParentProcessId,CreationDate`
   启动前后的新增条数应为 0。
4. 断网后启动：页面、地图、任务数据均应正常；只有主动打开「在线行情」才会访问 `json.tarkov.dev`。
5. 资源监视器 →「网络」→ 勾选两个进程：远端地址只应出现 `127.0.0.1` / 本机回环。

## 7. 已知限制

- `启动项目.bat` 是开发脚本，双击必然带一个 cmd 窗口；它不是发布入口，发布物里也不含它。
- 若用户从已有 cmd 里手动敲 `EFTMap.exe`，那个 cmd 是用户自己开的，不属于本软件派生。
- 安装器仍会写临时 `.ps1` 由 powershell 执行（`CREATE_NO_WINDOW` 只是隐藏窗口），
  这是没有 .NET SDK、不引第三方库前提下的取舍。
