# R46 打包与验收台账

host=HOMONAS user=MASTERJJ at=2026-11-04 04:55:00 (Asia/Shanghai)
项目：`d:\personal\trae\02-塔科夫\eft-interactive-map`
版本：**0.1.0**（按约束未升版本）

本轮只改打包/验收链路：
- `build/package_files.ps1`：显式收录 `wiki-map.js`，并把 `data/editions.json`、`data/armor-bt.json`、`data/armor-ricochet.json` 写进清单（它们本来就由 JS 字面量扫描自动带入，显式化只为可审计，计数不变）。
- `build/build.ps1`：PyInstaller 增加两条 `--add-data`（`tools/live_prices.py`、`tools/r20_fetch_prices.py`），`MustHave` 增加这两个文件的产物检查。
- `tools/launcher.py`：新增隐藏入口 `--run-tool <脚本> [参数...]`，用 `runpy` 在同一份冻结解释器里执行随包脚本；同时把 stdout/stderr 重配置为 UTF-8/replace，避免 windowed 产物弹 traceback 对话框挂住子进程。
- `tools/serve.py`：仅把两处后台抓取命令改为 `_python_script_cmd()`；源码运行仍是 `python tools/xxx.py`，冻结产物改为 `EFTMap.exe --run-tool tools/xxx.py`。业务逻辑未动。
- 未改 `app.js` / `style.css` / `index.html` / `tasks.js` / `combat_sim.js` / `tools/live_prices.py`。

## 1. 清单预检

`powershell -ExecutionPolicy Bypass -File build\verify_package_files.ps1`

- 结果：**13239 个文件**，staging **126.21 MB**（上一份台账基线 13238 / 126.1 MB）。
- 增减：**净 +1**，唯一新增显式项 `wiki-map.js`。
  - `index.html` 这一轮前端改动后不再有 `<script src="wiki-map.js">`，自动扫描因此会漏掉它；但 `index.html` 仍保留 `#wiki-viewport` 面板 DOM，`build.ps1` 也把 `wiki-map.js` 列为必需产物，所以显式收录，避免功能回退时产物缺文件。若确认该功能永久废弃，应同时删掉这条和 `build.ps1` 的必查项。
  - `data/editions.json`、`data/armor-bt.json`、`data/armor-ricochet.json`：已核对在 staging 中（由 `app.js` 里的字面量路径扫描自动带入），计数不变。
  - `data/tasks/*.json`、`data/i18n/*`、`assets/icons-traders/**`：均在 staging 中；商人头像共 35 个文件，最早 2026-10-20，已包含在上一轮基线，不构成新增。
  - 未打入：`docs/`、`.shots/`、`逆向参考/`、`build-cache/`、`ui-showcase.*`。

## 2. `tools/live_prices.py` 在打包产物中的可用性（关键风险）

### 原实现与失败原因
`serve.py` 的 `spawn_live_fetch()` 检查 `root/tools/live_prices.py`，然后 `Popen([sys.executable, fetcher, ...])`。
在 onedir 冻结产物里：
1. `_internal/tools/live_prices.py` 根本不存在（`tools/` 源码不进包）；
2. `sys.executable` 是 `EFTMap.exe`，不是 python，不能把 `.exe` 当解释器执行 `.py`。

`spawn_flea_refresh()` 调用 `tools/r20_fetch_prices.py` 有同样的两处问题（这是前端「刷新行情」按钮走的 `/api/prices/refresh` 路径）。本轮一并修掉。

### 修法
- 打包：`--add-data "$Root\tools\live_prices.py;tools"`、`--add-data "$Root\tools\r20_fetch_prices.py;tools"`，落在 `_internal/tools/`，正好等于冻结态的 `root`。
- 启动：冻结态用 `EFTMap.exe --run-tool <脚本> <原参数>`，`launcher.run_tool()` 用 `runpy.run_path(..., run_name="__main__")` 执行，退出码原样返回；不进入 GUI 启动流程。
- 编码：`run_tool` 把 stdout/stderr 统一为 UTF-8/replace。之前实测 `--status --json` 在 cp1252 控制台上抛 `UnicodeEncodeError`，PyInstaller windowed 模式会弹 traceback 对话框并**挂住子进程**；修复后不再出现。

### 产物内实测（`dist\EFTMap\EFTMap.exe`，临时配置/缓存目录）
证据：[live-prices-test.txt](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/docs/r46-package/live-prices-test.txt)

- 启动：`EFTMap.exe --server-only --port 8790 --config-dir <temp> --runtime-file <temp>`
- `livePrices.enabled=true`，`/api/live-prices/status` 返回 `enabled=True mode=regular fetcher=tools/live_prices.py`
- `POST /api/live-prices/refresh` → **HTTP 202**，`started=true`
- 缓存写入：`live-prices-regular.json` **466575 bytes**，`live-prices-regular.last-attempt.json` 记录 `status=200, bytes=17344505, count=3541, ok=true`
- `GET /api/live-prices?mode=regular` → `available=True count=3541`，样本价格正常（如 `5447a9cd4bdc2dbd208b4567` `l=38877 a=68242`）
- 结论：**安装版/便携版的「刷新行情」可用**。

代理验证（按用户规则先测再请求）：`127.0.0.1:7896` TCP 可连；`HEAD https://json.tarkov.dev/regular/items` 经代理返回 **HTTP 200**（ETag `d16e5f0df746446f48a6b699055959f5`）。未关闭 TLS 校验，本地地址全程直连。

## 3. 重建 dist

`powershell -ExecutionPolicy Bypass -File build\build.ps1` → 成功。

- `dist\EFTMap\EFTMap.exe` 2,651,280 B
- `dist\EFTMap\EFTMapDesktop.exe` 92,160 B
- `Microsoft.Web.WebView2.Core.dll` 698,208 B、`WebView2Loader.dll` 194,912 B
- `_internal\tools\live_prices.py` 29,410 B、`_internal\tools\r20_fetch_prices.py` 14,912 B、`_internal\wiki-map.js` 均在
- dist 合计 **155.26 MB / 14236 个文件**

## 4. 冒烟（真实 Chrome，打包后端 `dist\EFTMap\EFTMap.exe --server-only`，port 8795）

网络总计 **858 条请求**，逐条核对状态码：

- 非 200/304：`favicon.ico` 1 次 404（既有可忽略）；以及两个已知缺口物品在 3 个图标目录下的 404（见「仍存在的问题」）。
- 外部请求：**0**（全部 `127.0.0.1:8795` 或 `data:`）。`livePrices` 默认关闭：`/api/live-prices/status` 返回 `enabled=False`，页面无任何外网请求。
- 控制台：唯一 error 是资源 404（favicon + 上述图标），无脚本异常。
- 页面：
  - 地图：`#map-svg` 正常渲染；
  - 任务（新任务页）：PvP `共 503 个任务`；切 PvE 后 `共 499 个任务`；切 PvPS 后 `共 462 个任务`；模式名/存储回写正常（`eftmap.gameMode`）；
  - 配装：加载完整（3447 字符，40 条护甲列表）；
  - 配枪：163 把枪、档位/价格口径可见；
  - 弹药：`200 / 200 件`；
  - 账号抽屉：5 张版本权益卡，文案含「不影响任务与价格」；
  - 关于页：数据来源（tarkov.dev，MIT）+ 价格说明均在。

截图（均为实际视口像素，已存 `docs/r46-package/smoke/`）：

- 1440×900：`r46-1440-map.png`、`r46-1440-tasks-pvp.png`、`r46-1440-tasks-pve.png`、`r46-1440-loadout.png`、`r46-1440-gun.png`、`r46-1440-ammo.png`、`r46-1440-account.png`、`r46-1440-about.png`
- 1024×768：`r46-1024-map.png`、`r46-1024-tasks.png`

## 5. release 三件套

`powershell -ExecutionPolicy Bypass -File build\build_release.ps1 -SkipBase`

| 产物 | 体积 | SHA256 |
| --- | --- | --- |
| `EFTMap-Portable-0.1.0.zip` | 116.85 MB | `ECDC700ED2340296340EA42C2E8EED745BF643B56B579F1CA7ED3D91CD708388` |
| `EFTMap-AppWindow-0.1.0.zip` | 116.85 MB | `21F38A664E8A152C1A135A529FE919B339BF645C3EFC1D7BE36CB5ABF4B8C55A` |
| `EFTMap-Setup-0.1.0.exe` | 127.20 MB | `F4DBA5F665669536FF86BBAF70F8EAB35C84793C1D4C5B2222E7553B209C8B63` |

Portable zip 共 14241 项，已抽查：`_internal\tools\live_prices.py`、`_internal\tools\r20_fetch_prices.py`、`_internal\wiki-map.js`、`data/editions.json`、`data/armor-bt.json`、`data/armor-ricochet.json`、`icons-traders\portraits`（16 项）全部在包内。

## 6. 安装器验收

静默安装到 `%LOCALAPPDATA%\EFTMap-R46Accept`（未触碰默认安装目录）：

- `EFTMap-Setup-0.1.0.exe --silent --dir <临时目录>` → exit 0；安装 14237 个文件，282.46 MB（含复制为 `Uninstall.exe` 的 127.20 MB 安装器本体）。
- 注册表 `HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\EFTMap`：`DisplayVersion=0.1.0`、`InstallLocation` 指向临时目录、`UninstallString="...\Uninstall.exe" --uninstall`。
- 快捷方式（开始菜单 + 桌面，名为「EFT 互动地图.lnk」）：二进制内容确认目标为 `%USERPROFILE%\AppData\Local\EFTMap-R46Accept\EFTMapDesktop.exe`，工作目录为安装目录（`.lnk` 是英文壳 + 中文文件名，WScript COM 读中文路径会返回空，改用字节串核对）。
- 从开始菜单快捷方式启动：`EFTMapDesktop.exe`（pid 52696，窗口标题「EFT 互动地图」，responding=True）+ 后端 `EFTMap.exe`（pid 48320）；随机端口 `127.0.0.1:4889`；`desktop.log` 记录「托盘已创建」「主页面加载完成」，主页面仅 `favicon.ico` 404。
- 卸载：`Uninstall.exe --uninstall --silent --dir <临时目录>` → exit 0，注册表项与两个快捷方式均删除；异步 `rmdir` 10 秒后仍残留 1 个文件，已手工清理临时目录（属安装器既有小瑕疵，不影响用户默认安装路径）。

## 7. 回归

`python -m pytest tests -q` → **1703 passed, 5 failed, 1 skipped**（116.90s）。

失败均为既有配枪用例，未改动、未弱化：
- `tests/test_r19_11_round.py::test_hide_incompat_filters_without_touching_data`
- `tests/test_r19_13_round.py::test_row2_anchors_are_driven_by_real_slot_tree`
- `tests/test_r19_1_round.py::test_candidate_columns_match_reference_order`
- `tests/test_r19_5_round.py::test_zoning_is_generic_semantic_rules`
- `tests/test_r6_gun_workbench.py::test_gun_workbench_business_logic`

## 8. 仍存在的问题

1. **已知图标缺口（上游 404，已接受，不用占位图）**：HK 416A5 RAL 8000（`6a15ae2ae5267ba21c07f98f`）与 P90 灾厄（`6a78b7f8c2016eb33e0027cd`）。冒烟实际观察到这两个 id 在 `assets/guns-full`、`assets/icons-transparent`、`assets/icons-items` 三个目录均 404（共 12 条请求，含重渲染）。
2. `favicon.ico` 404 仍存在（既有，可忽略）。
3. 卸载器异步删除会残留自身 `Uninstall.exe`（等待时间内），需要再删一次；建议后续改用 MoveFileEx/重启删除方案。
4. 构建产物 `build\_staging` 目录里曾出现与自动清单不一致的旧文件，本轮以 `verify_package_files.ps1` 的扫描结果为准（13239）。

## 9. 版本建议

建议下一版升到 **0.2.0**，理由：
- 本轮内容与上一份 0.1.0 相比已不是补丁级：新增任务页复刻、PvP/PvE/PvPS 模式选择器、账号/版本权益抽屉、在线行情（含安装版可用性修复）、护甲公式切换、商人头像等；
- 打包层新增两个随包抓取脚本与隐藏运行时入口，安装产物行为发生变化；
- 继续沿用 0.1.0 会让用户无法从「版本/关于」区分旧包与新包，也不利于安装器覆盖升级判断。

按本次约束未自行升版本，仅给出建议。
