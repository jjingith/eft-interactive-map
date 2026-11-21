# R50 · 末轮打包台账（任务页新样式入包）

host=HOMONAS user=MASTERJJ at=2026-11-04 07:08:04 (Asia/Shanghai)
项目：`d:\personal\trae\02-塔科夫\eft-interactive-map`
版本：**0.1.0**（按约束未升版本）

本轮目标：把 R49 视觉打磨后的任务页（`tasks.css` + `tasks.js` 物品图标渲染）收进 dist，
全量重建、冒烟、复出三件套，并留痕。

改动文件：
- `tests/test_r41_tasks_ui.py` —— 仅同步一条过期断言（见第 1 节），非业务逻辑
- 其余全部由脚本重建，`tasks.css` / `tasks.js` / `app.js` / `gun_builder.js` / `combat_sim.js` 未改

## 1. 基线测试与清单预检

### 1.1 pytest（首次）
`python -m pytest tests -q` → **1707 passed, 1 failed, 1 skipped**（108.20 s）

失败项：
```
tests/test_r41_tasks_ui.py::test_db4_tokens
AssertionError: '#0e0e0e' not in tasks.css
```
原因：R49 打磨把任务页基准底色 `--db4-bg` 从 `#0e0e0e` 提亮到 `#121212`，而该用例仍在断言旧值。
这是**测试断言过期**，不是样式回退。

处理：把该用例的令牌元组首项改为 `#121212`（其余 `#151515` / `#262626` / `#e6e6e6` / `#f08a24` 不变），
并加一行注释说明为何改。没有放宽断言范围，也没有删用例。

### 1.2 pytest（同步后复跑）
`python -m pytest tests -q` → **1708 passed, 1 skipped, 0 failed**（107.15 s）

### 1.3 清单预检
`powershell -ExecutionPolicy Bypass -File build\verify_package_files.ps1`

- 预期 **13240** / 实际 **13240**，缺失 0，未登记 0，staging **126.22 MB**。
- **未改 `build/package_files.ps1`**：`tasks.css`、`tasks.js` 本来就在 `index.html` 的自动扫描覆盖范围内
  （`index.html` 里有 `tasks.css?v=r19.34` 与 `tasks.js?v=r19.34`），计数不变。

## 2. 端口核查与 dist 全量重建

| 端口 | 状态 |
| --- | --- |
| 8787–8790 | 空闲 |
| **8791** | **被他人 python（pid 31232）占用** → 记录，未杀 |
| 8792–8795 | 空闲 |
| 8796 | 空闲 → 本轮冒烟使用 |
| 8797 | 空闲（备用） |

`powershell -ExecutionPolicy Bypass -File build\build.ps1`（全量，无手工补丁）：

- staging 校验通过 → 删 `build\_work` 与 `dist\EFTMap` → PyInstaller onedir 重建。
- 产物：**14235 个文件 / 154.3 MB**（并入客户端壳前）；`产物清单校验通过：13240 个运行期文件全部存在`。
- 底图 SVG 13 张。

关键文件（干净 dist）：

| 文件 | 大小 |
| --- | --- |
| `EFTMap.exe` | 2,651,989 B |
| `_internal\favicon.ico` | 2,563 B |
| `_internal\tools\live_prices.py` | 29,410 B |
| `_internal\tools\installer.py` | 16,710 B |
| `_internal\wiki-map.js` | 25,314 B |
| `_internal\tasks.css` | **41,004 B** |
| `_internal\tasks.js` | **150,745 B** |

`tasks.css` / `tasks.js` 的 SHA256 与仓库源码**逐字节相同**：

```
src / dist  tasks.css  B3B57272B18CFFFB3A0FD505D725A116CDF94F1E8722703E524C8C381D061F4B
src / dist  tasks.js   DDF24D4CD932A5B932302B012D87CD5CFF8C5CE9A86DCB3CB30AA1E00DD0B7E5
```

release 阶段并入客户端壳后：`dist\EFTMap` = **14238 个文件**（`EFTMapDesktop.exe` 92,160 B、
`Microsoft.Web.WebView2.Core.dll` 698,208 B、`WebView2Loader.dll` 194,912 B）。

## 3. 干净 dist 冒烟（真实 Chrome，8796）

后端：`dist\EFTMap\EFTMap.exe --server-only --port 8796 --config-dir <temp> --runtime-file <temp> --log-file <temp>`

视口说明：本机 Chrome 处于 150% 缩放（`devicePixelRatio≈0.667`），用 DevTools 视口模拟得到
**CSS 视口精确 1440×900 与 1024×768**（截图落盘为对应设备像素）。

### 3.1 网络与控制台断言

| 场景 | 请求数 | 非 200/304 | 外部请求 | 控制台 error |
| --- | --- | --- | --- | --- |
| 1440 首页 | 238 | **0** | **0** | **0** |
| 1440 任务页（PvP→PvE） | — | **0** | **0** | **0** |
| 1024 首页 | 238 | **0** | **0** | **0** |
| 1024 任务页 | 239 | **0** | **0** | **0** |

- `GET /favicon.ico` → **200**（1440 与 1024 各一次）
- 控制台唯一一条是 `[EFTMap] build-rev = R19.34-e46799d2`（info），无 error / warn
- 本轮**没有任何 404**（R46 记录的两个图标缺口在首页/任务页加载路径上未触发）

### 3.2 任务页内容与样式断言

| 断言 | 实测 |
| --- | --- |
| 任务数 PvP | **共 503 个任务** |
| 任务数 PvE | **共 499 个任务** |
| 模式回写 | `localStorage.eftmap.gameMode = regular / pve` |
| 任务行底色 | `rgb(26, 26, 26)`（`#1a1a1a`） |
| 任务行分隔线 | `border-bottom 1.5px rgb(23, 23, 23)`（`#171717`，1.5px 为 150% 缩放下的 CSS 舍入） |
| 经验单行框 | `line-height: 20px`，边框 `rgb(52, 52, 52)`（`#343434`），单行不换行 |
| Complete | `color: rgb(61, 155, 255)`（`#3D9BFF`），`text-align: right` |
| 物品图标 | `.db4-item-cell` **32 × 32 px**，内部图片自然尺寸 64×64（2x 资源） |
| 物品数量角标 | 见下「已知缺口」 |
| 账号抽屉 | `#account-block` → `.account-cards` **5 张权益卡**，含「不影响任务与价格」说明 |

**物品数量角标**：`tasks.js:2544` 的分支是 `if ((it.count || 1) > 1)` 才渲染 `.db4-item-n`。
本轮用 DOM 探针验证了样式本身可用（9px 字号、`rgba(8,8,8,0.72)` 底、白色字、绝对定位在 32px 格子的右下角），
但**当前三份任务数据里没有任何 objective item 带 `count` 字段**：

```
tasks.regular.json / tasks.pve.json / tasks.pvps.json → items-with-count = 0
```

所以真实数据下角标恒不触发，1440 截图里看不到它（详见第 7 节「仍存在的问题」）。

### 3.3 地图 / 账号抽屉

- 地图：`#map-svg` 渲染节点 6064 个。
- 账号抽屉：5 张卡（标准版 / 留守版 等），文案「任务与价格不随版本变化…」在位。

### 3.4 `POST /api/live-prices/refresh`

| 步骤 | 结果 |
| --- | --- |
| 默认（`livePrices.enabled=false`） | 按设计 **409**，不联网 |
| 临时配置开启后 `POST /api/live-prices/refresh` | **HTTP 202**，`started=true`、`via=token` |
| 缓存写盘 | `live-prices-regular.json` **466,568 B**，mtime **06:59:41** |
| `GET /api/live-prices?mode=regular` | `available=True`，**count=3541** |

### 3.5 截图

存于 `docs/r50-final-package/smoke/`：

- [r50-1440-home.png](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/docs/r50-final-package/smoke/r50-1440-home.png)
- [r50-1440-tasks-pvp.png](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/docs/r50-final-package/smoke/r50-1440-tasks-pvp.png)
- [r50-1440-tasks-pve.png](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/docs/r50-final-package/smoke/r50-1440-tasks-pve.png)
- [r50-1024-home.png](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/docs/r50-final-package/smoke/r50-1024-home.png)
- [r50-1024-tasks.png](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/docs/r50-final-package/smoke/r50-1024-tasks.png)
- [r50-1024-account.png](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/docs/r50-final-package/smoke/r50-1024-account.png)

## 4. 三件套（重出）

`powershell -ExecutionPolicy Bypass -File build\build_release.ps1 -SkipBase`

| 产物 | 体积 | SHA256 |
| --- | --- | --- |
| `EFTMap-Portable-0.1.0.zip` | 122,536,867 B（116.86 MB） | `8B4AC3D6BB77CD970D7B39E52BC7FDEC2D6EF99D0DD19EC17F17F2B39564EE65` |
| `EFTMap-AppWindow-0.1.0.zip` | 122,537,006 B（116.86 MB） | `28117AF7283727EAAB4CA3870B3E57EC34563692DBE3D834C6433CFB8570358A` |
| `EFTMap-Setup-0.1.0.exe` | 133,395,826 B（127.22 MB） | `E62FED237CC548ADBDA1E13E9DE22EEA071E09A855BC00E5ED70CAFDC19D3E3A` |

与 R48 对照（R48：Portable `78C2…937C`、AppWindow `7256…2766`、Setup `F01B…D0D2`）**全部变化**，
符合预期（dist 内容已更新）。

### 4.1 包内 tasks 文件一致性

Portable zip 共 **14243** 项，解出两项后与 `dist\EFTMap\_internal` 比对：

| 文件 | zip 内大小 | zip SHA256（前缀） | 与 dist 一致 |
| --- | --- | --- | --- |
| `EFTMap\_internal\tasks.css` | 41,004 B | `B3B57272B18CFFFB…` | **是** |
| `EFTMap\_internal\tasks.js` | 150,745 B | `DDF24D4CD932A5B9…` | **是** |

同时抽查 `favicon.ico` 2,563 B、`EFTMapDesktop.exe` 92,160 B、两个 WebView2 DLL、
`_internal\tools\live_prices.py` 29,410 B 均在包内。

## 5. 回归

`python -m pytest tests -q` → **1708 passed, 1 skipped, 0 failed**（107.15 s）

## 6. 环境与清理

- 冒烟后端已通过 `POST /api/shutdown` 正常退出，无残留 `EFTMap` 进程。
- 临时目录 `D:\Temp\2\r50-cfg`、`D:\Temp\2\r50-zip`、`D:\Temp\2\r50-*.png` 已清理（截图已归档到 docs）。
- 未做 git 提交。

## 7. 仍存在的问题

1. **物品数量角标在真实数据下不可达**：`tasks.js` 的 `it.count > 1` 分支已随包发布，样式也验证正常，
   但三份任务数据的 objective item 都没有 `count` 字段（`items-with-count = 0`），
   因此界面上永远只有一个图标、没有 `×N` 角标。这不是打包问题，是任务数据管线没把数量带出来；
   要在界面上真正看到角标，需要在 `tools/fetch_tasks*.py`（或数据加工层）补上 item count。
2. `8791` 端口被他人 python（pid 31232）占用，本轮未干预。
3. PyInstaller 产物二进制不可复现：同源码重建 exe 字节仍会变，SHA256 只代表本次构建。
4. R47 遗留：双击 `Uninstall.exe` 会打开启动器（正规卸载入口正常）。
5. 版本仍为 0.1.0；正式发版建议升 0.2.0。
