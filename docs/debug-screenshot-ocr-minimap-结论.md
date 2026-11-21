# Debug Session: screenshot-ocr-minimap

## 用户症状
1. 自动截图不生效（启动器/小地图里开启后，战局中仍不按间隔截图）。
2. OCR 识别重复名称物资时出现问号徽章；点开具体物资选择框「过于巨大且不能点选」，疑似图层排序 / 遮挡 / 指针事件问题。
3. 截图后小地图有时不更新（主界面或游戏内小窗偶发不同步）。

## 环境
- PROJECT_ROOT: `d:\personal\trae\02-塔科夫\eft-interactive-map`
- 应用：本地 Python 服务 + WebView2/Chrome 页面 + `tools/overlay.py` 小地图浮窗
- DEBUG_EVIDENCE_DIR: `C:\Users\Administrator\AppData\Local\Temp\trae-debug\eft-map\screenshot-ocr-minimap`
- Debug Server: 启动后写入 `<DEBUG_EVIDENCE_DIR>/screenshot-ocr-minimap.env`
- 证据日志：`<DEBUG_EVIDENCE_DIR>/trae-debug-log-screenshot-ocr-minimap.ndjson`

## 可证伪假设（A-E）

### A：自动截图被「日志目录 / 战局阶段」卡住
`_log_dir_getter()` 只看 `game_dir/Logs`，如果该目录只有旧会话、真实日志在 `%LOCALAPPDATA%\Temp\Battlestate Games\EFT\Logs`，阶段会一直停在 `end`。
- 证据点：`detect_logs_dir()` 各候选目录的最新会话与 mtime；`_log_dir_getter()` 返回值；`AutoShotter.poll_once()` 的 phase/reason。

### B：自动截图按键 / 前台窗口 / 发送失败
即使阶段正确，`key` 为空、前台不是 `EscapeFromTarkov.exe` 或 `SendInput` 失败都会静默拦住。
- 证据点：`AutoShotter.settings()`、`foreground()`、`_send()` 返回值。

### C：OCR 选择框尺寸异常
候选数量多或字号放大时，`render_menu()` 计算出的菜单宽高超过屏幕，导致「过于巨大」。
- 证据点：`open_menu()` 的 `img.size`、`fs`、候选数量、屏幕尺寸、最终 `px/py`。

### D：OCR 选择框被遮挡 / 命中测试失败
role 6 菜单窗被 role 0 标签窗压住，或 `SetCapture` / `WM_NCHITTEST` / 坐标缩放导致点击落在错误窗口。
- 证据点：`open_menu()` 后菜单与标签窗的 z-order、`WindowFromPoint(行中心)`、`GetCapture()`；`menu_click()` 收到的客户坐标与命中行。

### E：小地图更新链路提前返回 / 竞态
`applyPosition()` 可能因 `fresh=false`、`insideMap=false`、`state.mini.follow=false` 或 SSE 竞态没有执行 `applyMiniView()`。
- 证据点：小窗 `applyPosition()` 的 fresh / insideMap / mini.follow / 分支；`PositionTracker.poll_once()` 的 prev/found/changed。

## 进度
- [x] 启动 Debug Server（http://127.0.0.1:7777，健康检查通过）
- [x] 静态定位三个链路的插桩点
- [x] 插桩并复现
- [x] 读取证据、确认/否定假设
- [x] 最小修复
- [x] post-fix 对比
- [x] 清理插桩与调试产物


## 结论与修复（R285，本轮接手完成）

证据日志 6.2 MB / 7 类事件，结论如下：

| 假设 | 判定 | 依据 / 处置 |
| --- | --- | --- |
| A 日志目录/阶段 | **成立** | `game_dir/Logs` 最新会话停在 11/02，`AutoShotter._block` 报 `phase=end`；`enabled=true`、`key=SysReq`、`available=true` 说明其余门都过。改为 `game_dir/Logs` 优先、其它候选存在明显更新（>1 天）的有效会话才切换。 |
| B 按键/前台 | 否定 | 同上，`_block` 只命中阶段门，未出现按键或前台拦截。 |
| C 菜单尺寸 | **成立** | `open_menu` 记到 `fs=38`、菜单 `931×728`、屏幕 `1024×768`。字号原样沿用标签行高中位数。已与标签字号解耦（上限 16px），并按屏幕 55%×65% 自适应收缩，字号下限降到 9px，不裁剪候选。 |
| D 遮挡/命中 | **成立，但根因与预设不同** | `window_from_point == menu_hwnd` 只说明 `open_menu` 当刻层级正确；`OverlaySession._redraw()` 末尾会把标签窗与控制条重新 `_topmost()`，同为 `WS_EX_TOPMOST` 的窗口按调用顺序叠放，重绘后菜单窗被压到下面，真实点击落在标签窗非徽章区（`HTTRANSPARENT`）直接穿透。harness 用 `SendMessageW` 直接投递消息，绕过了命中测试，所以日志显示"点中"。已在重绘后恢复菜单层级；另把点击打开的菜单设为常驻，禁用 200ms 悬停自动收起。 |
| E 小地图竞态 | **成立** | `applyPosition` 时序：位置帧到达时 `map=null`、`follow=false`，稍后地图与跟随才就绪，但 `fresh` 已为 false，不会再调 `applyMiniView()`。已在底图几何就绪（`mapSvgReady=true`）后补算一次跟随。 |

**清理**：三个文件里的 `#region debug-point` 插桩与 `_dbg` 上报函数全部删除；
排查专用 Debug Server（127.0.0.1:7777）已停止；本文档归档到 `docs/`。
**回归**：新增 `tests/test_r285_autoshot_menu_minimap.py`（10 条）；
`test_serve.py` / `test_autoshot.py` / `test_eftlog.py` 等 188 条通过；
全量回归维持 18 条既有失败（0.2.7.6 起存在的过时静态契约），未新增。
