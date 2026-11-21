# R245 修「按热键后白屏，点一下鼠标才正常」

> 用户反馈（2026-11-11 22:05）：
> 「按截图快捷键后会白屏 得鼠标左键单击一下之后才能正常截图」

## 一、根因（三层叠加，都有实测证据）

### 1. Edge 单实例：新启动参数从未生效，旧进程攒了一堆隐藏窗口

Edge/Chrome 对同一个 `--user-data-dir` 是**单实例**：`--app=...` 的新启动不会创建新进程，
而是把窗口塞进**已在运行的旧进程**。于是：

- R245 新加的「关遮挡暂停 / 关后台节流」参数**全部无效**（进程是 18:24 起的，参数还是老的）；
- 旧进程里累积了 **5 个**隐藏的扫描窗口（每次冷启动加一个）；
- Windows 的遮挡检测把隐藏窗口判为 occluded → Chromium 暂停合成 → 唤醒后 DWM 只有一张白卡，
  **直到有鼠标事件**才重新出帧。这就是「点一下才正常」。

证据：`Get-CimInstance Win32_Process` 里所有渲染进程的父进程都是 17468（18:24 创建），
后续 20:02 / 21:20 / 21:53 / 22:07 的「启动」都只是给旧进程开新窗口。

### 2. 选择窗带了 `WS_EX_NOACTIVATE`，永远不会成为前台窗口

`overlay.style_overlay()` 是为**被动 HUD（小地图）**写的，会加 `WS_EX_NOACTIVATE`。
框选窗复用它之后：

- 窗口永远 `fg=False` → **Esc 收不到**（页面 keydown 根本不触发）；
- Chromium 视窗口为「未激活」，隐藏→显示后不产出首帧（白屏的另一半原因）。

### 3. 上一轮的「关闭/完成」标题残留，宿主读到就把刚显示的窗口隐藏

页面要到 `visibilitychange` 才把标题复位，比宿主 150ms 轮询晚。唤醒时宿主先读到
`EFT截图·关闭`，立刻执行收窗——用户看到的就是「闪一下白就没了」。

## 二、修复

| 位置 | 改动 |
|---|---|
| `tools/scan.py` | 新增 `scan_profile_dir()` / `kill_scan_browser()`：**只**结束命令行含扫描 profile 路径的 msedge/chrome 进程（不按映像名扫射），宿主启动与冷启动前各清一次 |
| 浏览器启动参数 | `--disable-backgrounding-occluded-windows`、`--disable-renderer-backgrounding`、`--disable-background-timer-throttling`、`--disable-features=…,CalculateNativeWinOcclusion` |
| `launch_scan_window` | 剥样式后**去掉 `WS_EX_NOACTIVATE`**（框选窗必须能拿键盘），入场时 `BringWindowToTop` + `SetForegroundWindow` |
| `show_selection` | `BringWindowToTop` + `SetForegroundWindow` + `RedrawWindow(RDW_INVALIDATE|ERASE|FRAME|ALLCHILDREN|UPDATENOW)` + `DwmFlush()` |
| `hide_selection` | 隐藏前把窗口标题复位成 `EFT 截图识别`，从源头消灭残留标题竞态 |
| `watch` | 「关闭」信号改为**连续两次轮询**都读到才收窗（`closed_stale`，与完成信号同款保护） |
| `scan.html` | `visibilitychange` 时强制一次合成提交（`opacity 0.999 → rAF → 1`） |

## 三、验证（本机实测，逐帧抓屏统计）

| 场景 | 亮度均值 | 纯白占比 |
|---|---|---|
| 冷启动（首次热键） | 25 | **0.00%** |
| 保温唤醒 +90ms | 25 | **0.00%** |
| 保温唤醒 +210ms | 16 | **0.00%** |
| 保温唤醒 +460ms | 16 | **0.00%** |

- 窗口 `fg=True`（前台），Esc 能正常收窗（日志「选择已取消」）；
- 唤醒到出画面 ≈ 250ms（其中 ~150ms 是抓屏 + BMP 上传，属正常链路）；
- 修复前同一套脚本在冷启动/唤醒都测到 87.8%~100% 的纯白帧（且窗口 `fg=False`、Esc 无效）。

## 四、已知项（不在本次范围）

- Chrome/Edge 的 `--app` 窗口会在客户区顶部保留 ~31px 的自绘标题栏（渲染区 1920×1049）。
  选区的坐标换算按图像实际显示尺寸（X/Y 各自比例）计算，**裁剪结果仍准确**，只是顶部 31px
  画面被标题栏遮住、无法框选。这是 Chromium 的行为，`--start-fullscreen` / `--kiosk` 实测
  同样保留（已对比）。如需彻底去掉，需要改成无边框 Electron/WebView2 宿主，属于打包阶段的事。
- 冷启动仍要拉起浏览器（约 2-3 秒），保温路径不受影响。
