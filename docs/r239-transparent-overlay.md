# R239 · 透明价格浮窗（小地图式，不挡游戏操作）

日期：2026-11-11 16:30–17:05 · 前置：R238（QQ 式框选工作流）

## 用户纠偏（原话）

> 「不对 我的需求是显示的浮窗和小地图一样 是不影响游戏操作的
> 而且 应该是透明背景 只显示价格文字 然后价格文字是直接显示在对应装备上的」

R238 把结果显示成了浏览器内的交互面板（占窗口、挡游戏）——方向错了。R239 重做
结果层：**原生 Win32 分层窗口，不走浏览器**。

## 形态

- **标签窗**（每件物品一组价格）：
  - `UpdateLayeredWindow` 逐像素 alpha：背景全透明（alpha=0），只有价格文字可见；
  - `WS_EX_TRANSPARENT` 全窗点击穿透 + `WM_NCHITTEST→HTTRANSPARENT` 双保险——
    鼠标事件全部落到游戏，完全不打断操作（与小地图 overlay 同机制）；
  - 价格文字**与装备名同行右移**（单行「主价 · 格 X · kg Y」），字号随 OCR 行框高
    （0.92×bh，11–26px），右溢出左移夹紧——不与上下行文字打架；
  - `WS_EX_NOACTIVATE`：永不抢焦点，游戏窗口保持激活。
- **控制条窗**（独立小原生窗，区域右上角）：`[最新价]`（口径循环按钮）+ `[✕]`；
  仅按钮矩形可点（WM_NCHITTEST 按钮外 HTTRANSPARENT），可点也不抢焦点。
- **口径循环**：最新价 → 24h均价 → 72h均价 → 30天均价，纯宿主本地重绘（不经过
  BFF）；每件价格派生（每格=base/格数、每公斤=base/重量）随口径一起换。
- 价格文本紧凑格式：`43.1万 / 9万 / 9,999 / 1.23亿`；72h/30d 无快照如实 `—`。

## 链路

```
热键(Ctrl+Alt+P) → 冻结帧 → scan.html 框选（交互，不变）
  → /api/ocr/recognize 识别
  → POST /api/ocr/overlay/state {region, matches}  ← R239 新端点（白名单瘦身/200条上限）
  → scan.html 标题「EFT截图·完成」
  → 宿主 GET 交接态 → 关选择窗 → 开原生透明浮窗
  → ✕ / 再按热键 → 全关回等待
```

scan.html R239 起不再渲染结果面板（`#panel` 移除）；零匹配提示 1.4s 后自动关。

## 实现（tools/scan.py）

- `create_overlay_window(role)`：0=标签（+TRANSPARENT）1=控制条 2=演示底图；
  `WNDCLASSW` 自定义 Structure（`ctypes.wintypes` 没有它——首跑踩坑）；
- `set_layered_bitmap()`：PIL RGBA → numpy 预乘 → CreateDIBSection → ULW；
  **64 位坑**：`GetModuleHandleW`/`CreateWindowExW` 等必须设 argtypes/restype，
  否则 HMODULE 截断 → RegisterClassW 静默失败 → CreateWindowExW 报错 0；
- `render_labels`/`render_control`：PIL 逐像素绘制（msyh 字体缓存、描边保证
  任意背景可读）；`fmt_short`/`price_views` 纯函数可单测；
- 主循环必须 `DispatchMessageW`（R238 只 Peek 不 Dispatch，原生 WndProc 收不到点击）；
- 消息循环 `while Peek: …` 改为「处理 WM_HOTKEY + 一律 Dispatch」。

## 验收（tools/r239_accept.py，15/15）

- A HTTP：交接态往返/白名单瘦身/200 条截断/缺 region 400；
- B 浏览器：autotest 框选 → 识别 3 件 → 标题「EFT截图·完成」→ 交接区域与匹配
  正确、无 JS 异常（区域是图像坐标，允许显示比例换算 ±1.2）；
- C 宿主 `--demo-overlay`：合成帧 → OCR → 假游戏底图 + 透明浮窗 → 截屏取证
  （`build/_r239_overlay_demo.png`）：价格与装备名同行、背景全透明、无伪影、
  控制条正常；EXSTYLE 断言：标签窗 `0x80800A8`（全穿透）、控制条 `0x8080088`
  （无 TRANSPARENT，按钮可点）。
- 排版三轮迭代：同位置直叠（名字被盖）→ 名字上方（密集行互相打架）→
  **同行右移单行**（定稿）。
- `tests/test_r239_overlay.py` 11 条 + R238 页面契约更新（面板 → 交接）；
  全量 **2093 passed / 0 failures / 4 skipped**（136.45s，`build/_pytest_r239.xml`，
  退出码 0）。计划任务 `EFTMap-Scan-AutoStart` 已重启装载。

## 边界

- 浮窗按框选瞬间位置绘制——游戏内 UI 滚动后价格留在原处（再框一次即可）；
- MVP 主屏；72h/30d 依赖本机采集器快照积累；游戏独占全屏模式下分层窗口能否
  显示取决于游戏（无边框/窗口化没问题，与小地图一致）；
- 控制条两按钮矩形会拦截该处点击（极小面积，其余全部穿透）。
