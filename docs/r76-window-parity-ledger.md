# R76 台账：窗口层对齐（kaedeori 七条 + 截图排除开关）

host=HOMONAS user=MASTERJJ at=2026-11-05 14:55:00 +08:00

## 0. 结论先行

七条窗口能力全部落地，且都在真实窗口上取证（`--dump-json` 的窗口状态 + 桌面截图 + 日志）。
控制台问题（R75）保持为 0 控制台窗口；本轮把主窗恢复为「任务栏一个图标」，小地图仍是
`WS_EX_TOOLWINDOW`（不进任务栏、不抢焦点）。三件套一次性重打包完成，清单双向校验 13312/13312。

本轮改动集中在 `tools/host/src/MiniHost.cs`、`tools/host/src/DesktopShell.cs`、`tools/config.py`，
**前端 `app.js` / `index.html` / `style.css` / 地图渲染 0 改动**；未 commit。

测试主机只有一台 1920×1080 显示器（工作区 `0,0,1920,1040`），因此「副屏物理截图」无法产出；
第 5 条用「超大偏移 → 夹回工作区」的可测量证据替代，代码路径同样走 `MonitorFromWindow`。

## 1. 逐条对照（改前 / 改后 / 实测证据）

| # | 能力 | 改前 | 改后 | 实测证据 |
| --- | --- | --- | --- | --- |
| 1 | 尺寸自适应 | 固定 `overlay.size×DPI`（默认 260）；换分辨率不重算 | `auto`：`min(工作区宽,高)×20%×scale`，`scale∈[0.5,3]` 写回配置；`fixed` 保留旧像素模式；每次布局都从当前显示器工作区重算 | 1080p 工作区短边 1040 → **208px**（`run-square`、`run-circle`）；`scale=2` → **416px**（`run-clamp2`）；JSON：`effectiveSize` |
| 2 | 圆形小地图 | 读 `overlay.shape` 但窗口仍是方形 | `SetWindowRgn` + `CreateEllipticRgn`；设置失败时 `DeleteObject` 释放；`square` 用 `SetWindowRgn(hwnd,NULL)` 清除；只作用于顶层窗（WebView2 子 HWND 不被裁） | `mini-circle.png`、`desktop-circle.png`；JSON `shape=circle` |
| 3 | 置顶保活 | 3 秒重钉一次 | **1 秒**重钉 `SetWindowPos(HWND_TOPMOST)`；timer 在 `OnFormClosed` 停止并释放 | JSON `topmost=true`；日志每秒布局保持 topmost；进程退出后无空转 timer |
| 4 | 不抢焦点 | 已有 `WS_EX_NOACTIVATE` + `SW_SHOWNOACTIVATE` | 保留；新增「首显后若前台被小窗抢走则还原」 | `evidence-runtime.txt`：热键隐藏/显示前后前台 HWND 都是 `25693054`，`same=True / same=True` |
| 5 | 多屏夹取 | 用主屏 `SPI_GETWORKAREA`，副屏/拔屏会越界 | `MonitorFromWindow+GetMonitorInfo` 取所在显示器工作区；x/y 双向 clamp；`WM_DISPLAYCHANGE` 重算；唤起前 `ClampToVisible` | `evidence-clamp.txt`：请求偏移 (800,800) → 实际 `(1504,624)`，右下角 `1504+416=1920`、`624+416=1040`，完全在工作区内；`mini-clamped.png`、`desktop-clamp.png` |
| 6 | 还焦 | 无 | 热键前 `GetForegroundWindow`；250ms 后仅当「前台 == 小地图或其子窗」才 `SetForegroundWindow(before)`；其它程序抢走则不碰 | `run-clamp` 热键计数 `hotkeyCount=2`，前台未变，`focusRestoreCount=0`（没有发生抢焦，所以不需要还焦） |
| 7 | 崩溃自愈 | 只在状态栏写「请重启客户端」，WebView2 空白 | `ProcessFailed` + **2 秒健康检查**（控制器 COM 失效即触发）：关闭旧控制器 → 旧环境不可用则重建 Environment → 重建控制器 → 重新导航；后端 health 失败则重启后端；状态栏非阻塞提示 | 强杀 `msedgewebview2.exe`：`run-recover` 日志出现 `WebView2 进程异常` → `已重建并重新导航 次数=1`；`main.ready=true`、`webviewRecoverCount=1`；`main-recovered.png` 359,939 B（崩溃前空白抓图仅 18 KB） |
| + | 截图/录屏隐藏（默认关） | 无 | `SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE=0x11)`，配置键 `overlay.exclude_from_capture`，设置页有开关和一句用途说明 | `run-wda`：`exclude=true applied=true displayAffinity=17`；`evidence-wda.txt` |

## 2. 截图与原始证据

| 文件 | 内容 |
| --- | --- |
| `docs/r76-window-parity/main-shell.png` | 主窗：无边框 + 自绘标题栏 + 页面 |
| `docs/r76-window-parity/mini-square.png` | 方形旧态（208×208，auto 基准） |
| `docs/r76-window-parity/mini-circle.png` | 圆形新态（SetWindowRgn 裁剪） |
| `docs/r76-window-parity/desktop-circle.png` | 全屏截图：圆形小地图落在右下角 |
| `docs/r76-window-parity/mini-clamped.png` / `desktop-clamp.png` | scale=2、超大偏移被夹回工作区（416×416 @ 1504,624） |
| `docs/r76-window-parity/main-recovered.png` | 强杀 WebView2 后自动恢复的主窗 |
| `docs/r76-window-parity/run-*/logs/window-state.json` | 每次运行的 style/exStyle/bounds/workArea/shape/affinity 原始值 |
| `docs/r76-window-parity/evidence-runtime.txt` | conhost=0、进程树、热键前后前台 HWND |
| `docs/r76-window-parity/evidence-clamp.txt` | 夹取数值 |
| `docs/r76-window-parity/evidence-recover.txt` | 崩溃自愈日志 |
| `docs/r76-window-parity/evidence-wda.txt` | WDA 开关日志 |
| `docs/r76-window-parity/evidence-smoke.txt` | 打包产物冒烟 |

窗口样式关键值（实取）：

- 小地图：`style=0x96000000`、`exStyle=0x080900A8`
  = `WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOPMOST`
- 主窗：`exStyle=0x00050100`（含 `WS_EX_APPWINDOW`，不再有 `WS_EX_TOOLWINDOW`）

## 3. 与 kaedeori 的差异

| 点 | kaedeori（Electron） | 我们（WinForms + WebView2） | 结论 |
| --- | --- | --- | --- |
| 主窗 | `frame:false` 自绘标题栏 | WinForms 无边框 + 原生标题栏控件 + `WM_NCHITTEST`/DWM 圆角 | 外观等价 |
| 主窗透明度 | `transparent:true` | WinForms 普通窗口，不做整窗透明 | **不照搬**：透明主窗会让 WebView2 合成变复杂，收益低 |
| 小窗置顶层级 | `alwaysOnTop:"screen-saver"` | `HWND_TOPMOST` 每秒重钉 | 等价（游戏全屏独占仍可能覆盖，属系统限制） |
| 小窗无焦点/穿透 | `focusable:false` + `setIgnoreMouseEvents` | `WS_EX_NOACTIVATE` + `WS_EX_TRANSPARENT`，全图时关穿透 | 等价 |
| 小窗形状 | 靠 CSS/透明底做圆 | `SetWindowRgn` 真正窗口区域 | 更彻底（窗口命中区也是圆的） |
| 崩溃恢复 | 主进程 reload | 重建 WebView2 控制器（必要时重建 Environment）+ 后端重启 | 等价且更细 |
| 分发 | Electron + Node，约 400 MB | PyInstaller + 系统 WebView2 | 保持轻量、离线 |

## 4. 风险面

**用户能感知的行为变化**

- 主窗**重新出现在任务栏**（1 个图标）；小地图仍不进任务栏。
- 小地图默认尺寸从固定 260 px 变为工作区短边 20%（1080p = 208 px）；可在设置里 0.5–3 缩放。
- 小地图可以切成圆形；形状随配置持久化。
- 打开「截图/录屏中隐藏」后，小地图在截图、录屏、直播画面里不可见（Win10 2004+）。
- 置顶重钉从 3 秒缩短到 1 秒，被其它置顶窗口压住的恢复更快；CPU 开销可忽略。
- 热键召唤不再改变前台窗口；若确实被小窗抢到前台，会在 250ms 内还原。

**纯内部变化（用户无感）**

- 显示器工作区来源从 `SPI_GETWORKAREA` 改为 `MonitorFromWindow`；`WM_DISPLAYCHANGE` 重算。
- WebView2 新增 2 秒健康检查与控制器重建；关闭窗口时定时器一并释放。
- 配置新增 `overlay.size_mode` / `overlay.scale` / `overlay.exclude_from_capture`（旧配置自动补默认值）。

## 5. 打包与冒烟（与 R75 合并为一次）

| 产物 | 大小 | SHA256 |
| --- | --- | --- |
| `release\EFTMap-Portable-0.1.0.zip` | 118.5 MB | `B575ADD0C714DE0EEE979ADDDD31A62F02D209A9509000FC8A90F6A3CBD4628A` |
| `release\EFTMap-AppWindow-0.1.0.zip` | 118.5 MB | `2885A6CDDAD9774DAA7BDF4B17BC403BAA95C72BCD0AFBDA190E40C3ED76CA54` |
| `release\EFTMap-Setup-0.1.0.exe` | 128.8 MB | `4DF309C6EA21DE49A9FD9268415846F8F4B8CBF175A31CBC90276A192564CD73` |

- 清单双向校验：预期 **13312**、staging 实际 **13312**、缺失 0、未登记 0（`verify-after-build.txt`）。
- 构建内断言：`EFTMap.exe` / `EFTMapDesktop.exe` / Setup 的 PE 子系统全部 `GUI(2)`；两个 zip 都含 `EFTMapDesktop.exe`。
- 冒烟（解压 Portable 后走真实入口 `EFTMap.exe`）：壳 `EFTMapDesktop.exe` 起来 → 子进程 `EFTMap.exe` 监听 `127.0.0.1:8787`、`msedgewebview2.exe` 同进程树 → `conhost` 子进程 **0**（`evidence-smoke.txt`）。
- 未执行 Setup 的实际安装，避免在用户桌面创建/覆盖快捷方式；安装器 PE 与功能未改，R75 已实测其无控制台窗口。

## 6. 用户可自测的验收步骤

1. 解压 `EFTMap-Portable-0.1.0.zip`，双击 `EFTMap.exe`：
   - 任务栏只有 **1 个** EFT 图标；
   - `Get-CimInstance Win32_Process -Filter "Name='conhost.exe'" | ? {$_.ParentProcessId -eq (Get-Process EFTMapDesktop).Id}` 应为空。
2. 设置 → 小地图：尺寸模式 `auto`、缩放 `1`、形状 `circle`，保存。
   - 小地图应变成圆形，1080p 下边长约 208 px；改成 `2` 后约 416 px。
3. 进游戏（全屏/窗口化），按 `Ctrl+Shift+M` 召唤/收起小地图：游戏不应失焦；再按一次应回到原位置且完整可见。
4. 把偏移改为 800 再保存：小地图应停在屏幕边缘内侧，而不是跑出屏幕。
5. 打开「截图/录屏中隐藏小地图」后截图：小地图不应出现在截图里；关闭后恢复正常。
6. 任务管理器结束 `msedgewebview2.exe`：主窗应在约 2–4 秒内自动恢复，而不是一直白屏。

## 7. 已知限制

- 全屏独占（Exclusive Fullscreen）游戏可能压过任何 `HWND_TOPMOST`；1 秒重钉只能提高窗口化/无边框全屏下的存活率。
- `WDA_EXCLUDEFROMCAPTURE` 需要 Windows 10 2004+；旧系统调用失败时保持关闭（日志有返回值）。
- 圆形区域是几何裁剪，WebView2 页面本身仍是方形渲染，圆外不可见但也不可点击。
- 本机单显示器，副屏切换只验证了 clamp 路径；双屏实机需再补一次「拖到副屏后收起/唤起」的截图。
