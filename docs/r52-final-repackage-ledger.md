# R52 最终重打包留痕（任务数据 count 变更）

host=HOMONAS user=MASTERJJ at=2026-11-04 07:58:01

## 结论

- 任务数据加工层补上 objective item 的 `count` 后，`dist` 已全量重建并收进最新数据：`tasks.regular / tasks.pve / tasks.pvps` 三份 JSON 与源码逐字节相同。
- 打包产物中 `×3` 数量角标可见：真实 Chrome（dist + 8796）搜 Prapor「蛋卷冰淇淋 / Ice Cream Cones」出现 `×3` 角标，截图 `docs/r52-final-repackage/smoke/r52-1440-tasks-icecream.png`。
- 冒烟全绿：1440 / 1024 两档首页 + 任务页，非 200/304 = 0、外部请求 0、控制台 error 0。
- 三件套已按新 dist 重出（Portable / AppWindow / Setup），包内任务 JSON、`tasks.css`、`tasks.js` 与 dist 同哈希。

## 1. 测试与清单预检

| 项目 | 结果 |
| --- | --- |
| `python -m pytest tests -q` | **1713 passed / 1 skipped / 0 failed**（109.85 s），与给定新基线一致 |
| `build\verify_package_files.ps1` | 预期 13240 / 实际 13240 / 缺失 0 / 未登记 0，staging 126.7 MB |

清单计数未变（13240）：`data/tasks/*.json` 本来就在 `package_files.ps1` 的运行期 data 清单里，本次只是文件内容变化，不涉及新增/删除文件。

## 2. dist 全量重建

- 端口核查：8791 被他人 python（pid 31232）占用，未触碰；8796 空闲，冒烟使用 8796。
- `build\build.ps1` 全量重建成功：
  - 构建期产物：**14235 个文件 / 154.9 MB**
  - 发布期并入壳（`EFTMapDesktop.exe` + WebView2 两个 DLL）后：**14238 个文件 / 155.8 MB**
  - 关键产物均在：`EFTMap.exe` 2,651,989 B、`EFTMapDesktop.exe`、`Microsoft.Web.WebView2.Core.dll`、`WebView2Loader.dll`、`_internal\favicon.ico` 2,563 B、`_internal\tools\live_prices.py`、`_internal\tools\installer.py`、`_internal\wiki-map.js`
  - 底图 SVG 13 张。

## 3. 任务 JSON 哈希一致性（源码 = dist = zip）

| 文件 | 字节 | SHA256 |
| --- | --- | --- |
| `data/tasks/tasks.regular.json` | 3,253,248 | `9B1AC0811EA3F5342A3431210B6CD56E974189F9DC07E0409D91ACD83BD5E5D5` |
| `data/tasks/tasks.pve.json` | 3,228,836 | `57515C989A70DB4F09847C7DC1DF6747B8ECD0C50252A239553EBC868CAA21BC` |
| `data/tasks/tasks.pvps.json` | 2,802,734 | `8642D420D553FE384E86F281BA78B3B13FFFC17F84A4ECCD9725C7A2182CA562` |
| `data/tasks/traders.json` | 8,223 | `0FF2687109C518FBE17C38F1D336471E46A271E0249C2595D7E633AF9B7A473F` |

三份任务 JSON 与 `traders.json`：源码、`dist\EFTMap\_internal\data\tasks\*`、`EFTMap-Portable-0.1.0.zip` 内同名文件三方 SHA256 完全一致。

`items-with-count` 抽查：

| 文件 | item 带 count 数 | 任务数 |
| --- | --- | --- |
| `tasks.regular.json` | **484**（与要求一致） | 503 |
| `tasks.pve.json` | 484 | 499 |
| `tasks.pvps.json` | 472 | 462 |

抽检「蛋卷冰淇淋」（`59675d6c86f7740a842fc482`）：`findItem` / `giveItem` 的 `55d482194bdc2d1d4e8b456b` 均为 `count=3`。

## 4. 冒烟（dist + 真实 Chrome + 8796）

视口用设备像素换算（本机 dpr≈0.667）：`960x600` → CSS 1440×900，`683x512` → CSS 1024×768（实测 `innerWidth/innerHeight` 分别为 1440×900 / 1024×768）。

| 场景 | 请求数 | 200 / 304 | 非 200/304 | 外部请求 | 控制台 error |
| --- | --- | --- | --- | --- | --- |
| 1440 首页 + 任务页（PvP） | 252 | 240 / 12 | 0 | 0 | 0 |
| 1024 首页 + 任务页（PvE）+ 账号抽屉 | 242 | 74 / 168 | 0 | 0 | 0 |

功能断言：

- 任务数：PvP **503**（1416 条目标 / 222 条前置）、PvE **499**（1384 条目标 / 221 条前置），与数据一致。
- 账号抽屉：5 张版本卡（标准版 / 留守版 / 准备逃离版 / 未闻者版 / 黑暗边缘版）。
- 行情：`POST /api/live-prices/refresh` → **202**（同源 `X-EFTMap-Client: web` + `Origin`，`via=web`）；缓存写盘 `C:\Users\Administrator\AppData\Local\EFTMap\cache\live-prices-regular.json` **466,560 B @ 07:43:22**；`GET /api/live-prices` → `count=3541`、`fetchedAt=2026-11-04T07:43:22+08:00`。
- 数量角标：PvP 全量列表渲染 55 个 `.db4-item-n`（169 个物品格）；搜「蛋卷冰淇淋」后 1 行 / 1 格 / 角标 `×3`。

截图（`docs/r52-final-repackage/smoke/`）：

- `r52-1440-home.png`
- `r52-1440-tasks-icecream.png` ← **×3 角标取证**
- `r52-1440-tasks-pvp.png`
- `r52-1024-home.png`
- `r52-1024-tasks-pve.png`
- `r52-1024-account.png`

## 5. traders.json 副作用抽查

`data/tasks/traders.json` 的增强字段仍在：16 个商人全部 `nameEn` 英文名、`nameZh` 中文名、`portrait` 路径非空（16/16），例如 Prapor `assets/icons-traders/portraits/54cb50c76803fa8b248b4571.webp`、Therapist、Fence、Skier、Peacekeeper、Mechanic 均正常。

## 6. 三件套（`build\build_release.ps1 -SkipBase`）

| 产物 | 体积（字节） | SHA256 |
| --- | --- | --- |
| `EFTMap-Portable-0.1.0.zip` | 122,557,964 | `65E9AA6636C4F5445C267063EE1F689BD48C732CA5C7DA48B4FE8C642002EE43` |
| `EFTMap-AppWindow-0.1.0.zip` | 122,558,103 | `D6EA406B12FFB28DFD13F033C9DADC7E6C87D21E78E9A561DA711953519078EA` |
| `EFTMap-Setup-0.1.0.exe` | 133,418,298 | `75592C642D6A0131415B86A56CF70F9765C2E88C48DD7448048AADB6CC237F7F` |

Portable 解包抽查（zip 内路径为 `EFTMap\...`）：

- `EFTMap\_internal\data\tasks\tasks.regular.json` 3,253,248 B → `9B1AC081…E5D5D`（与 dist 同哈希）
- `EFTMap\_internal\data\tasks\tasks.pve.json` / `tasks.pvps.json` / `traders.json` 同样一致
- `EFTMap\_internal\tasks.css` 41,004 B → `B3B57272…1F4B`
- `EFTMap\_internal\tasks.js` 150,745 B → `DDF24D4C…B7E5`

## 7. 收尾

- 冒烟后端已 `POST /api/shutdown` 正常退出（pid 51288），8796 已释放；未触碰 8791。
- 临时目录 `D:\Temp\r52-cfg`、`D:\Temp\r52-shots`、`D:\Temp\2\r52-*.png` 为一次性产物。
- 未执行任何 git 提交。

## 8. 仍存问题

- `Uninstall.exe` 双击仍会打开启动器（R47 遗留）。
- 版本号仍为 0.1.0，未升版。
- PyInstaller 产物不可复现（同源码两次构建 exe 哈希不同）。
- 数量角标现在可见了，但依赖数据管线持续输出 `count`；后续若上游任务数据重抓时丢失 `count`，角标会再次消失。
