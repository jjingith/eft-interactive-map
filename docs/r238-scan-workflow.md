# R238 · QQ 式截图识别工作流（热键 → 框选 → 原位浮窗）

## 用户原话（2026-11-11 16:00）

> 「能否做成和qq截图一样 按用户设置的快捷键 然后框选要识别的地方 然后再进行识别
> 还会然后识别的结果和小地图一样 以浮窗结果显示 就显示在框选的位置
> 显示整体价格和每格价格以及每公斤价格 然后在浮窗右上角有关闭键 和切换价格的键
> 点击后在最新价格 24小时均价 72小时均价 30天均价直接切换」

## 工作流（全部按需求逐条落地）

```
全局热键（默认 Ctrl+Alt+P；配置 ocrScan.hotkey / --hotkey 可改）
→ ImageGrab 抓整屏冻结帧 → POST /api/ocr/frame（内存单帧，10 分钟 TTL）
→ 全屏无边框置顶浏览器窗口加载 /scan.html（QQ 式：暗化遮罩 + 十字线 + 尺寸提示）
→ 框选（Esc / 右键取消；误点退出）
→ 前端按图像坐标裁剪 → POST /api/ocr/recognize
→ 原位浮窗（显示在框选位置）：
    每行 = 物品名 + 每件 / 每格 / 每公斤 三列价格
    右上角 [口径按钮]：最新价 → 24h均价 → 72h均价 → 30天均价 循环（纯前端切换）
    右上角 [✕]：关闭浮窗并退出截图识别（宿主回到热键等待）
```

## 架构（沿用项目「宿主窗口 + 网页」惯例，复用 overlay.py 成熟件）

| 组件 | 职责 |
| --- | --- |
| `tools/scan.py`（新增，常驻后台） | 全局热键注册（RegisterHotKey 消息循环）→ 冻结帧抓取/上传 → 全屏宿主窗口（find_browser / style_overlay / fit_client 全部复用）→ 窗口关闭回热键等待 |
| `scan.html`（新增，BFF 静态服务） | 冻结帧 1:1 显示、框选、前端裁剪（X/Y 各自比例换算，DPI/拉伸不错位）、原位浮窗、口径循环、关闭（window.close + 标题改「EFT截图·关闭」双保险） |
| `serve.py` | `POST/GET /api/ocr/frame`（48MB 上限、单帧覆盖、TTL 600s、错误 id 404）；`recognize` 增 **w72 / w30d 均价**（`price_history.series` days=3/30，本地快照均值、不插值）与 **weight**（每公斤价） |
| 计划任务 `EFTMap-Scan-AutoStart` | 登录自启 pythonw scan.py（Hidden/IgnoreNew/无时限），与 8787 服务、PBH 同一套 autostart 体系 |

价格口径实现：服务端一次算齐 `{lastLow, avg24h, w72, w30d}` + `gw/gh/weight`，
浮窗切口径**纯前端换算**（每件=所选口径值；每格=÷(gw×gh)；每公斤=÷weight），
不重复请求。72h 窗口=3 天、30d=30 天；某窗口没有快照就没有该字段（不估算）。

## 验收

- 浏览器 `tools/r238_accept.py` **14/14**：帧上传/取回/错误 id 404；autotest 框选 →
  浮窗 ≥3 行（3 个物品名全中）；三列价格非全空（含 0.01kg 钥匙每公斤 38,999,900 ₽
  的极端校验）；口径循环 `["24h均价","72h均价","30天均价","最新价"]`；关闭 → 标题
  变「EFT截图·关闭」；无 JS 异常。截图 `docs/r238/01-scan-panel.png`。
- 单测 `tests/test_r238_scan.py` **8 条**：帧往返/覆盖/TTL/404（HTTP 级 create_server）、
  recognize 多窗口静态契约、scan.py 契约（热键默认/冻结帧/关闭标题）、scan.html
  契约（三列/四档口径/autotest/X-Y 裁剪）、overlay.parse_hotkey 复用。
- 宿主冒烟：计划任务 Running（pythonw PID），热键已注册。
- 全量 pytest：见 `AGENT_HANDOFF.md`（`build/_pytest_r238.xml`）。

## 用法

- 开机自启已配置（登录后常驻、零窗口）；手动方式：`pythonw tools/scan.py`
- 游戏内按 `Ctrl+Alt+P` → 框选 → 松手出浮窗 → 右上角切换口径 / 关闭
- 改热键：`--hotkey` 参数或配置文件 `ocrScan.hotkey`（设置面板入口待后续轮）

## 边界（如实）

- MVP 只抓**主屏**（多屏扩展待需求）；冻结帧是抓取瞬间的画面（QQ 同款冻结语义）。
- 72h/30d 均价依赖本机采集器快照积累（新装环境无历史 → 该两档显示 —）。
- 扫描窗口需要交互（不点击穿透）；浮窗在窗口内、跟随框选位置夹紧到视口内。
