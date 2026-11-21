# R55 收尾打包台账（armor-bt 数据变更 → dist / 三件套重出）

host=HOMONAS user=MASTERJJ at=2026-11-04 09:57:30

## 结论

- **dist 已包含新护甲数据**：`dist\EFTMap\_internal\data\armor-bt.json` 与源码 `data\armor-bt.json` 大小 46,814 B、SHA256 完全相同（`29FF92FE…AE52E`）。
- **9 件此前缺口抽查全过**：bt 全部非 `null`，且 dist 中逐件与源码一致（9/9 PASS，failures 0）。
- **测试**：`python -m pytest tests -q` → **1718 passed / 1 skipped / 0 failed**（104.63 s）。
- **清单**：`verify_package_files.ps1` → 预期 13240 / 实际 13240 / 缺失 0 / 未登记 0，staging 126.7 MB（`data/armor-bt.json` 本就在清单内，计数未变）。
- **冒烟（真实 Chrome，跑的是 dist 里的 EFTMap.exe）**：1440 与 1024 各测首页 + 任务页，非 200/304 = 0、外部请求 0、控制台 error 0；PvP 503 / PvE 499；`×3` 角标仍在；`POST /api/live-prices/refresh` → 202 且缓存已重写。
- **三件套**：Portable 122,563,261 B / AppWindow 122,563,400 B / Setup 133,423,518 B；Portable 内 `EFTMap\_internal\data\armor-bt.json` 与 dist 同哈希。
- **剩余**：不 git 提交（按要求）；冒烟用后端进程需关停；行情上游本次返回 3539 条（R52 为 3541，上游漂移，非包内问题）。

## 1. 数据源与内容核对

`data/armor-bt.json`（只读校验）：

| 项 | 值 |
| --- | --- |
| 文件大小 | 46,814 B |
| SHA256 | `29FF92FEE99E6D9889937318ABF9FFFA943FB9BBC6D89F23B12E61E99DFAE52E` |
| items 数 | 168（源码） / 168（dist） |
| `bt` 为 null | 0 |
| `material-fallback` 命中 | 0 |
| btSource 分布 | `gunsmith` 159 / `tarkov.dev:armorSlots.bluntThroughput` 5 / `gunsmith-inverted` 4 |

与需求描述一致（159 / 4 / 5，fallback 归零）。

## 2. 测试与清单预检

- `python -m pytest tests -q` → `1718 passed, 1 skipped in 104.63s`（0 failed）。
- `build\verify_package_files.ps1`：
  - 运行清单：`build\package_files.ps1`
  - `完整性校验通过：预期 13240 个文件，staging 实际 13240 个文件，缺失 0，未登记 0。`
  - staging 体积 126.7 MB。
  - `data/armor-bt.json` 原已在清单内，本次数据变更不改文件条数，故计数仍为 13240。

## 3. dist 全量重建

- 端口：8791（他人 python pid 31232）、8795 未触碰；8796 已被他人 python 占用（pid 52104），改用 **8797**。
- `build\build.ps1` 全量重建成功：
  - 重建后 dist：14,235 文件；`EFTMap.exe` 2,653,615 B。
  - `build_release.ps1 -SkipBase` 并入客户端壳（`EFTMapDesktop.exe` / `Microsoft.Web.WebView2.Core.dll` / `WebView2Loader.dll`）后：**14,238 文件 / 163,377,875 B**。
- `data/armor-bt.json` 源码 ↔ dist：

| 位置 | 大小 | SHA256 |
| --- | --- | --- |
| `data/armor-bt.json` | 46,814 | `29FF92FEE99E6D9889937318ABF9FFFA943FB9BBC6D89F23B12E61E99DFAE52E` |
| `dist\EFTMap\_internal\data\armor-bt.json` | 46,814 | `29FF92FEE99E6D9889937318ABF9FFFA943FB9BBC6D89F23B12E61E99DFAE52E` |

一致。

## 4. 9 件此前缺口抽查（bt 非 null 且与源码一致）

| # | id | 名称 | bt | btSource | dist 与源码一致 |
| --- | --- | --- | --- | --- | --- |
| 1 | `69cbfe44897389c1870b2337` | Crye Precision AirFrame 头盔（瘟疫侵袭） | 0.1314 | tarkov.dev:armorSlots.bluntThroughput | 是 |
| 2 | `6a567ae55cbe811cbe0136a8` | Crye Precision AirFrame 头盔（慢工出烂活） | 0.1314 | tarkov.dev:armorSlots.bluntThroughput | 是 |
| 3 | `6a568dda1d89fcfb35010389` | MTEK STRIKE 防弹头盔（碳纤维） | 0.1548 | tarkov.dev:armorSlots.bluntThroughput | 是 |
| 4 | `6a576f2105af50743903b74c` | ANA Tactical M1 插板胸挂（数码丛林迷彩） | 0.33 | tarkov.dev:armorSlots.bluntThroughput | 是 |
| 5 | `6a670ae11ab6ac490a0b9a99` | DevTac 浪人面罩（实验室安保） | 0.1548 | tarkov.dev:armorSlots.bluntThroughput | 是 |
| 6 | `5fd4c474dd870108a754b241` | 5.11 Hexgrid 插板背心 | 0.26 | gunsmith-inverted | 是 |
| 7 | `609e8540d5c319764c2bc2e9` | NFM THOR 隐蔽型强化防弹背心 | 0.33 | gunsmith-inverted | 是 |
| 8 | `60a283193cb70855c43a381d` | NFM THOR 一体式防弹护甲 | 0.36 | gunsmith-inverted | 是 |
| 9 | `68a89146212dbbeead0d5636` | NFM THOR 隐蔽型强化防弹背心（头眼） | 0.33 | gunsmith-inverted | 是 |

failures 0 / 9 件全 PASS。

## 5. 冒烟（真实 Chrome，dist 产物）

后端：`dist\EFTMap\EFTMap.exe --host 127.0.0.1 --port 8797 --no-browser --server-only --config-dir D:\Temp\r55-cfg`（pid 45040，`livePrices.enabled=true`），页面 `http://127.0.0.1:8797/`。

### 1440×900（设备视口 960×600 @dpr 0.667）

- 首页（地图）与任务页均正常渲染，无横向/纵向溢出（`scrollWidth=innerWidth`）。
- 网络：**322 请求 = 78×200 + 244×304**；非 200/304 = **0**；外部请求（非 127.0.0.1 / data: / blob:）= **0**。
- 控制台 error = **0**。
- 任务数：**PvP 503 / PvE 499**（`共 503 个任务 · 筛选命中 503`、`共 499 个任务 · 筛选命中 499`）。
- 任务页搜索「蛋卷冰淇淋」→ 唯一结果行 `蛋卷冰淇淋 Ice Cream Cones Lv 6 · 森林`，目标「在战局中找到 5.45x39 6L31 60发弹匣 **×3**」，`.db4-item-n` 断言 `×3` 命中。

### 1024×768（设备视口 683×512 @dpr 0.667）

- 首页（地图）与任务页正常渲染，无溢出。
- 网络：**240 请求 = 9×200 + 231×304**；非 200/304 = **0**；外部请求 = **0**。
- 控制台 error = **0**。
- 任务页为 PvE 499（界面偏好沿用），列表 499 行。

### 在线行情 refresh

- `POST /api/live-prices/refresh`（同源 + `X-EFTMap-Client: web`）→ **202**，59 ms，返回 `started=true / mode=regular`。
- 缓存重写：`C:\Users\Administrator\AppData\Local\EFTMap\cache\live-prices-regular.json` → 09:48:20、466,319 B（刷新前为 07:43:22、466,560 B）。
- `GET /api/live-prices?mode=regular` → 200，`available=true / stale=false / count=3539`。上游比 R52 的 3541 少 2 条，属上游数据漂移，与本次打包无关。

### 截图归档

目录：`docs/r55-final-package/smoke/`

| 文件 | 说明 |
| --- | --- |
| `r55-1440-home.png` | 1440 首页（地图） |
| `r55-1440-tasks.png` | 1440 任务页（PvP 503 行） |
| `r55-1440-tasks-icecream.png` | 1440 搜索「蛋卷冰淇淋」→ `×3` 角标 |
| `r55-1024-home.png` | 1024 首页（地图） |
| `r55-1024-tasks.png` | 1024 任务页（PvE 499 行） |

## 6. 三件套（`build_release.ps1 -SkipBase`）

| 产物 | 体积 (B) | SHA256 |
| --- | --- | --- |
| `EFTMap-Portable-0.1.0.zip` | 122,563,261 | `DA9DBB17657A68118066E96F70BEA9F5C794DF8CC21C7C22E0D53F93F4A0F3BE` |
| `EFTMap-AppWindow-0.1.0.zip` | 122,563,400 | `26A4EF07B801530F50043796F69913C80558D6F46E3D6C60531589B33AE1B36A` |
| `EFTMap-Setup-0.1.0.exe` | 133,423,518 | `A9307C111BAB6A7094A3842ED95DEB497EFBA2F37A131F813A349632A084AAB7` |

Portable 解包校验：zip 内条目 `EFTMap\_internal\data\armor-bt.json`，46,814 B，SHA256 `29FF92FEE99E6D9889937318ABF9FFFA943FB9BBC6D89F23B12E61E99DFAE52E` —— 与 dist / 源码同哈希。

## 7. 未做与遗留

- 未 git 提交（按要求）。
- 冒烟后端仍在 8797 运行，收尾后关停。
- 未改动任何源码/测试；本轮仅为数据变更后的重打包与验证。
