# R279 · 云端价格本地缓存 + 截图识别环境清单

> 时间：2026-11-14 · 版本 `0.2.7`

用户两条反馈：

1. 价格页仍显示「云端历史是会员数据 / 本机还没有采集到快照」——登录了测试账号也没有曲线。
2. 截图识别现在能框选了，但框完「没反应」。

---

## 一、云端价格本地缓存（登录整包 / 按钮增量 / 过期清理）

### 为什么之前没有曲线

`/api/price-history` 只读**本机**采集器快照；云端虽然每 30 分钟都有采集机上传的
快照，但只有打开物品详情时才现查一次 `/v1/prices/series`，且要求**会员**。
测试账号当时在云端是 `member=false`（本机 `cloud-session.json` 里那份是旧快照），
所以每次都被 403 挡下，页面就显示「云端历史是会员数据」。

### 新口径（按用户要求）

| 时机 | 行为 |
| --- | --- |
| 登录 / 会员态变化 | 自动把当前模式的云端历史**整包下载**到本地（约 15 MB / 模式） |
| 点「获取最新数据」 | 带 `cursor` 走增量，只取上次之后的新快照（通常 0–2 条） |
| 会员过期 / 退出登录 / 云端 403 | 本地缓存**整体清理**（`price_cache.purge()`） |
| 打开物品详情 | 直接读本地缓存（单物品 2–30 ms），不再打云端 |

### 数据流

```
采集机 --每30分钟--> 云端 price_snapshots（regular/pve/pvps 各 ~193 份，21 MB/模式）
                         │
     GET /v1/prices/cache?mode=&since=   （会员；gzip；整包 16.5 MB JSON / 2 MB 线上）
                         ▼
            tools/price_cache.py  →  %APPDATA%\EFTMap\cloud-cache\<mode>.json
                         │            {cursor, snapshots, series:{id:[[ts_ms, price],…]}}
                         ▼
     /api/price-history  ── 本机采集快照优先，缓存补历史（同时间戳去重）
```

缓存按「物品 → 序列」存，而不是照抄 192 份原始快照：原始快照体积大 4 倍，
读一个物品要扫全量；聚合后单模式 15 MB，取值用 `"<id>":[` 在原文里定位再
`raw_decode`（与云端 `/v1/prices/series` 同一套手法），单物品 2–30 ms。

### 接口

| 接口 | 说明 |
| --- | --- |
| `GET /v1/prices/cache?mode=&since=` | 会员；整包 / 增量；返回 `{cursor, snapshots, items, points, series}` |
| `GET /api/price-cache/status` | 本机各模式缓存概况；非会员时**顺手清理**并回 `member:false` |
| `POST /api/price-cache/sync` | `{mode}`；整包/增量同步；403 时清缓存并回 `member_required` |

### 实测（线上，2026-11-14）

| 指标 | 数值 |
| --- | --- |
| 整包（193 份 / 3571 物品 / 685,475 点） | 6.6 s，16.5 MB JSON（gzip 后约 2 MB） |
| 增量（无新数据） | 0.1 s，`status=up_to_date` |
| 增量（1 份新快照） | +3,554 点 |
| 本地单物品读取 | 4–28 ms（首读含 15 MB 文件读盘） |
| `/api/price-history`（带缓存合并） | 0.64 s，本机 269 + 云端 194 → 合并 270 点 |

---

## 二、截图识别「框选后没反应」

### 根因（不是缺环境）

冻结产物里 `ocr.py` 落在 `_internal\ocr.py`，`PROJECT_ROOT` 因此被算成产物根目录，
`OCR_ASSETS_DIR` 指向 `dist\EFTMap\assets\ocr`——而模型实际在
`dist\EFTMap\_internal\assets\ocr`。于是 `/api/ocr/recognize` **一律 503**
「模型文件缺失」，页面提示只停留 2.5 秒就关窗，用户看到的就是「框完什么都没发生」。

同一批的第二个坑：`data/ocr-item-names.json`（5480 条中文短名表）从来没进打包清单，
即使模型能加载，游戏里印的短名（`BS`、`铝热剂`）也匹配不上，识别结果会趋近 0 条。

### 修法

1. `ocr.resolve_assets_dir()`：`_MEIPASS` → `exe/_internal` → `exe` → 源码仓库，
   取第一个三件套齐全的目录；`check_available()` 的报错带上实际查找目录。
2. `build/package_files.ps1` 运行期清单加 `data/ocr-item-names.json`；
   `build.ps1` 必查项加短名表 + 三个模型文件。
3. 失败可见：`scan.html` 失败提示 2.5 s → **6 s**；宿主启动失败弹置顶提示框
   （含日志路径），不再只在 `scan-host.log` 里写一行。
4. `overlay.find_browser()` 补 `%LOCALAPPDATA%` 与 PATH 里的 msedge/chrome。

### 实测（冻结态，0.2.7）

```
EFTMap.exe --run-tool build/_frozen_ocr_probe.py  →  engine OK，45 行，1.57 s
POST /api/ocr/recognize（500×840 截图）           →  HTTP 200，3.7 s，24 条匹配
```

---

## 三、完整功能需要什么环境（假设一台全新 Windows）

| 能力 | 需要什么 | 打包版自带的 |
| --- | --- | --- |
| 主界面（独立窗口） | **WebView2 Runtime**（Win11 自带；Win10 一般自带，安装器会检测并提示下载） | — |
| 后端 / 本地服务 | 无（Python 已冻结进 exe） | Python 运行时、标准库 |
| 截图识别 · 框选窗 | **Edge 或 Chrome**（Win10/11 自带 Edge；LTSC/精简版需自行安装） | 浏览器探测（Program Files / LOCALAPPDATA / PATH / `EDGE_PATH`） |
| 截图识别 · OCR | 无（不需要 Tesseract / .NET / CUDA） | det.onnx 4.7 MB + rec.onnx 10.8 MB + 字典 + numpy + opencv + onnxruntime |
| 截图识别 · 抓屏/叠字 | 无 | Win32 API（ctypes） |
| 价格曲线 | 网络 + 会员账号 | 12 小时内置行情快照（离线可看） |
| 云端缓存 | 网络（首次 15 MB / 模式） | — |
| 权限 | **不需要管理员**，全部写用户目录（`%APPDATA%\EFTMap`、`%LOCALAPPDATA%\EFTMap`） | VC++ 运行库 DLL 已随包（`msvcp140.dll` / `vcruntime140*.dll`） |

结论：一台装好 Edge 的 Windows 10/11 开箱即用；唯一可能要补的是 **WebView2 Runtime**
（安装器已检测并给出下载入口），OCR 本身零外部依赖。
