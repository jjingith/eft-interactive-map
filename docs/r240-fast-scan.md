# R240 · QQ 式速度：保温窗口 + BMP 冻结帧

日期：2026-11-11 17:11–17:35 · 前置：R239（原生透明浮窗）

## 用户反馈（原话）

> 「还有一个 就是现在按截图键 没有qq截图那样快 而且窗口什么都会动一下」

## 三个根因（都在选择窗的冷启动路径上）

1. **每次热键拉起浏览器进程**：Popen chrome → 等窗口 → 等页面标题 → 固定
   sleep 0.6+0.3s → fit_client（最多 3 轮 ×0.25s）——累计 1.5-4s；
2. **整屏 PNG 编码数百毫秒**（4K 更明显）；
3. **「动一下」**：窗口先带标题栏在默认位置出现 → style_overlay 剥样式 →
   move_window 挪到全屏 → fit_client 缩放，全程用户可见。

## R240 解法

### ① 窗口保温（QQ 截图的本质：进程和窗口都常驻）

- 识别完成 / 用户取消：宿主 **ShowWindow(SW_HIDE) 隐藏**选择窗，不再销毁浏览器
  进程（R238/R239 是 PostMessage(WM_CLOSE)+taskkill）；
- 下一热键：帧**先上传**再 `show_selection`（SW_SHOW + TOPMOST + 激活）——页面
  `visibilitychange` 立即拉新帧（浏览器对隐藏页节流定时器，唤醒事件兜底）；
- 热键在框选中再按：不关窗，直接换帧重选（页面轮询自动跟上）；
- 隐藏前记下前台窗口（`overlay.foreground_hwnd`），隐藏后 `restore_focus` 还给游戏。

### ② 页面轮询换帧（scan.html）

- `GET /api/ocr/frame`（不带 id）→ 元信息 `{ok, id, fmt}`（R240 新语义）；
- 页面可见 150ms / 隐藏 800ms 轮询；发现新 id → `startNewScan`：暗色待机 → 拉帧 →
  框选就绪；交接后 `resetIdle` 回待机（页面**绝不自行关闭窗口**，`window.close` 移除）；
- `?frame=<id>` 仍支持（冷启动省一次轮询 / 验收用）。

### ③ 冻结帧改 BMP

- `grab_frame` 改存 BMP（免压缩，编码≈内存拷贝）；BFF 按魔数嗅探
  （`BM`→image/bmp / PNG→image/png），4K 帧约 24MB < 48MB 上限；
- localhost 传输 6MB ~10ms，页面 img 解码 BMP 原生支持。

### ④ 冷启动防闪动（只有首次/窗口被杀后才走）

- 浏览器窗口以 `--window-position=-32000,-32000` 创建：剥样式、等页面、
  `fit_client(corner="top-left")` 全部在**屏幕外**完成，最后一次性移入 (0,0)——
  用户永远看不到「带标题栏 → 剥掉 → 挪位置」；（浏览器若把 -32000 钳回可见区，
  只是退回旧行为。）

### ⑤ 防竞态

- 重开窗口瞬间页面可能仍带着上一轮的「完成」标题：BFF 交接态新增 `ts`，
  宿主只消费 `ts >= shown_at - 0.5` 的完成信号；页面在 startNewScan/
  visibilitychange 时复位标题。

## 效果（tools/r240_accept.py，12/12）

| 指标 | R238/R239 | R240 |
|---|---|---|
| 热键→可框选（保温路径） | 1.5-4s（拉浏览器+编码+sleeps） | **抓帧~0.2s + 换帧 ≤0.15s ≈ 0.4s** |
| 页面侧首帧就绪（无 frame 参数） | — | **287ms**（轮询 150ms 档实测） |
| 同页第二轮换帧 | 需重拉浏览器 | **253ms**，`__scanTestWarm` 标记证明**无 reload** |
| 「动一下」 | 标题栏剥除/挪位/缩放全程可见 | 保温路径零移动；冷启动屏幕外完成 |

两轮框选交接均 ≥3 件、ts 递增、区域一致、无 JS 异常。

## 测试与回归

- `tests/test_r240_warm_scan.py` 7 条：BMP 嗅探/Content-Type、元信息端点、坏 id 404、
  交接态 ts、宿主保温契约（BMP/-32000/show_selection/hide_selection/phase/shown_at/
  restore_focus）、页面轮询契约（visibilitychange/150-800ms/startNewScan/resetIdle/
  无 window.close）；`_OCR_FRAME`/`_OCR_OVERLAY` 是 serve 模块级全局，跨文件测试
  需复位（R239 文件补 `_reset_overlay`）；
- R238/R239 契约全部保留通过；全量见 `build/_pytest_r240.xml`；
- 计划任务 `EFTMap-Scan-AutoStart` 重启装载。

## 边界

- 保温窗口常驻一个隐藏浏览器（独立 user-data-dir，内存 ~100-200MB）——用户可
  关闭该窗口，宿主检测到后下次热键重新冷启动；
- 隐藏页轮询被浏览器节流到 800ms 无妨（唤醒靠 visibilitychange 立即拉取）；
- 真实热键手感（含保温路径的端到端延迟）待用户游戏内实测。
