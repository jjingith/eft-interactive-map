# R247 ShareX 式原生选区：把「按键到出画面」从秒级压到毫秒级

> 用户反馈（2026-11-12 11:38）：
> 「奇怪 现在按截图键反应非常慢啊  https://github.com/ShareX/ShareX 你看下sharex
> 他的截图就不会有这种反应 很丝滑 能否直接拿来用」

## 一、能不能「直接拿来用」

**不能整项目拿，但让它丝滑的做法已经 1:1 复刻进来了。**

| 障碍 | 说明 |
|---|---|
| 许可证 | ShareX 是 **GPL v3**（源码文件头明确），整项目并入会触发 GPL 分发义务 |
| 技术栈 | C# / .NET / Avalonia / SkiaSharp，与我们 Python + 本地 BFF 完全不同 |
| 功能 | ShareX 只有截图/标注，没有 OCR 物品名 → 市场价 → 透明价格浮窗这一整套 |
| 依赖 | 要为此引入整个 .NET 运行时和数十个工程，体积与维护成本不可接受 |

**没有复制它的任何一行代码**，只采用了它的机制（Win32 层，本就属于系统 API）；
项目 R239 起已有 `UpdateLayeredWindow` 原生透明浮窗引擎，正好是现成基建。

### MCP 取证（GitHub 源码）

- `ShareX.ScreenCaptureLib/Presentation/RegionCapture/RegionCaptureTransparentWindow.cs`
  > “Selects a rectangle over the live desktop **instead of a frozen screenshot** …
  > The caller captures the screen **after the window closes**.”
  >
  > `Background = new SolidColorBrush(Color.FromArgb(1, 0, 0, 0));`
  > 注释：「Fully transparent pixels let clicks through to the windows below,
  > so keep an invisible alpha of 1.」
  > → 透明命中层、只画选区边框（白实线 + 黑虚线）、松手关窗后才抓屏。

- `RegionCaptureIntegration.cs`
  > `WarmUp()`：「Builds a region capture window once without showing it,
  > so the **first capture after startup does not pay for** JIT, XAML loading,
  > styles, templates, icons and font enumeration.」
  > → 窗口预热，热键零初始化。

- `Screenshot.cs` / `CaptureRegion.cs`
  > 抓屏按矩形（`CaptureRectangle(rect)`），不是先抓整屏再裁剪。

## 二、我们慢在哪（旧链路）

```
热键 → 整屏 BMP(6MB) → POST /api/ocr/frame → 唤醒 / 冷启动 Edge
     → 页面 150ms 轮询发现新帧 → GET 6MB → 解码显示 → 框选
     → 裁剪 → POST /api/ocr/recognize → 交接态 → 浮窗
```

- 开机第一次：`Edge` 冷启动 **2~3 秒**；
- 保温唤醒：抓屏 + 两次 HTTP(6MB) + 页面轮询 + 浏览器合成 **300~500ms**；
- 还叠着 R245/R246 为「白屏 / 弹 PowerShell」加的一堆 workaround（标题轮询、
  `closed_stale`、进程清理、`NOACTIVATE`…）——根因都是**把浏览器当截图宿主**。

## 三、新链路（R247 默认，`--legacy-select` 可回退）

```
宿主启动：建好三个原生分层窗并预热第一张 ULW 位图（一次性 252ms）
热键     → ShowWindow（19ms；实测按键到窗口可见 38ms）
拖拽     → 只重绘「选区大小」的小位图（白实线 + 黑虚线 + 尺寸）
松手     → 关窗 → DwmFlush → 只抓选区 → 直接 POST /api/ocr/recognize
         → 本地开透明价格浮窗（复用 R239/R244 全部样式）
```

**三个窗口各司其职**（都复用 `create_overlay_window` / `set_layered_bitmap`）：

| role | 用途 | 样式 |
|---|---|---|
| 3 | 全屏命中层 | `WS_EX_LAYERED` + `LWA_ALPHA=1`，整窗可点、光标十字、收 Esc / 右键 |
| 4 | 选区边框层 | 逐像素 alpha，小位图，`WS_EX_TRANSPARENT` 全穿透 |
| 5 | 顶部提示条 | 小位图，全穿透，预热时画好 |

要点：

- **不用 colorkey**：colorkey 的透明像素会把鼠标穿透到下层，框选收不到事件；
  用常量 alpha=1（ShareX 注释同样强调）；
- **预热**：第一次 `UpdateLayeredWindow` 实测付 **130ms** GDI 初始化，放在宿主启动时；
  之后热键路径不再有 ULW；
- **松手才抓屏**：既避免把选区边框截进识别图，也把整屏 6MB 传输彻底省掉；
- 档位样式、单格价、热键热更新、Esc/右键取消、✕ 关浮窗全部保留；
- 旧 Edge 链路代码保留但默认不调用（`/api/ocr/frame`、`/api/ocr/overlay/state`
  端点也保留，供 legacy 与验收脚本使用）。

## 四、实测

| 指标 | 旧 | R247 |
|---|---|---|
| 热键 → 出选区界面 | 冷启动 2~3s / 保温 300~500ms | **38ms**（宿主 `show()` 19ms） |
| 预热后重复 `show()` | — | 7~21ms（5 次循环） |
| 每次热键抓屏 | 1920×1080 BMP ~6MB + 上传 + 回下 | **0 字节** |
| 启动的进程 | Edge 主进程 + 多渲染进程 | **0**（宿主自身） |
| 拖拽重绘 | 整页合成 | 选区大小的小位图 |
| 端到端 | — | 拖拽 → OCR 2 件 → 浮窗（日志 `识别完成：2 件 / 3594 ms`） |

> 3594ms 是**松手之后**的识别耗时（含服务端首次装载 OCR 引擎），不属于「按键反应」；
> 按键到可框选是 38ms。

## 五、验收

- `tests/test_r247_native_select.py` 6 条：预热契约、热键路径禁抓整屏/禁开浏览器、
  只抓选区 + `DwmFlush`、WndProc 键鼠消息、默认原生 + legacy 回退、
  预热后 `show() < 50ms`（无交互桌面或缺 numpy 时自动 skip）；
- 端到端注入 `Ctrl+Alt+P` + 鼠标拖拽，日志确认 `选区窗已显示 19 ms` →
  `识别完成：2 件`，期间无 Edge / 控制台窗口，收场后无残留窗口；
- 取证图 `docs/r247/01-native-select.png`：透明背景上的选区白/黑虚线框、尺寸文字、
  顶部提示条。

## 六、行为变化与边界

- 现在是 **ShareX 透明实时选区**：屏幕不再暗化冻结，而是保持实时画面只叠一个选区框
  （ShareX 当前版本就是这样）。游戏装备界面本身是静态的，实际使用无差别；
  若仍要 QQ 那种「整屏变暗的冻结帧」，可加 `ocrScan.freezeFrame` 开关，用本地抓屏
  画进命中层（约 +90ms，仍远快于旧链路），保留作为可选项；
- MVP 仍只支持主屏；多屏需在 `NativeSelection` 里按 `GetSystemMetrics(SM_XVIRTUALSCREEN)`
  建跨屏窗口；
- 独占全屏下原生分层窗与小地图同机制（用户已验证小地图可用）。
