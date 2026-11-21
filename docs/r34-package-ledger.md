# R34 打包留痕（dist 已重建；冒烟发现 4 个缺失图标后停止）

host=HOMONAS user=MASTERJJ at=2026-11-03T10:11:41+08:00 round=R34-package

> 本工作区为局域网共享目录。本文件记录本轮打包前置检查、清单校验、复核结论与后续结果。
> 2026-11-03T10:16 复核：13238 的两个新增文件确认为运行期 i18n 文件，接受 13238 作为新基准。
> 2026-11-03T10:38 冒烟：页面全部可开、无外网、指定脚本 200；但发现 2 把新枪的 4 个图标 404，
> 按「任何一步异常就停在原地报告」停止，未执行 release 重建。

## 1. 步骤 1：前置检查（通过）

- 分支 `main`，HEAD `bf438df75a011d9875e6ce71427f2390a7d254de`（2026-10-19 18:17:08）。
- `git status --short` 共 457 行，原始输出：`docs/r34-package/git-status-before.txt`。
- 精确检查 `build\build.ps1` / `build\build_release.ps1` / `EFTMap.exe` 进程：**无并行打包 / 无运行中的 EFTMap**。
- 版本来源 `tools/serve.py`：`VERSION = "0.1.0"`。
- dist 基线：`dist\EFTMap` 1531 个文件、43,934,568 B、
  mtime 2026-10-19T19:26:16～19:26:18。
- release 基线：3 个文件、83,864,415 B：
  - `EFTMap-AppWindow-0.1.0.zip` 23,872,795 B，SHA256 `B9F57EA3E02CDBF0FD6937B42F523C3A85648ACF629CFEDFCD009D8449549766`
  - `EFTMap-Portable-0.1.0.zip` 23,872,656 B，SHA256 `1483C0276304E5F3D33C782E28547432CD9D095B89AAF221E9DDA62EBCCCD512`
  - `EFTMap-Setup-0.1.0.exe` 36,118,964 B，SHA256 `2560415F12F18132EF01D5FA93C58CB0D96CCAFA20067D7F2760C25562B08470`
- `dist\EFTMap\EFTMap.exe` SHA256 `CF61CCF40881A84F6AC7BFC23C71FD5192A3152FC0A037920AD6E846B1C0CB84`。
- 完整文件清单：`docs/r34-package/baseline-dist_EFTMap.csv`、`docs/r34-package/baseline-release.csv`、
  `docs/r34-package/baseline-summary.txt`。

## 2. 步骤 2：清单校验（未通过，已停止）

命令：

```powershell
powershell -ExecutionPolicy Bypass -File build\verify_package_files.ps1
```

实际输出：

```text
完整性校验通过：预期 13238 个文件，staging 实际 13238 个文件，缺失 0，未登记 0。
staging 路径：...\build\_staging_check
staging 体积：126.1 MB
```

- staging 分类：总 13238 = assets 13179 + data 42 + 其余 17。
- 用户给出的基准：13236/13236，缺失 0。
- 实际比基准 **+2**（13238 vs 13236）。按指示先停下复核；复核后确认这两个是
  运行期 i18n 文件，**接受 13238 作为新基准并继续**（见 §3）。
- 校验本身自洽：缺失 0、未登记 0；不是漏文件，而是清单总数比用户基准多 2。

## 3. 步骤 2 复核：+2 文件定位（已接受 13238）

当前 `build/package_files.ps1` 显式收录 `data/i18n/ui-zh.json`、`names.json`、
`items-zh.json`、`poi-zh.json` 四个运行期文件。目录中前两者是旧文件（10/27–10/28），
后两者今天新建：

| 相对路径 | 大小 | mtime | 来源 | 运行期引用 |
|---|---:|---|---|---|
| `data/i18n/names.json` | 8,827 B | 2026-11-03T09:43:10.0097560+08:00 | `$script:RuntimeFiles`（data 显式清单，不是 assets 自动收录） | `i18n.js:73` 固定加载 |
| `data/i18n/items-zh.json` | 2,329 B | 2026-11-03T09:43:10.0117528+08:00 | `$script:RuntimeFiles`（data 显式清单） | `i18n.js:74` 固定加载 |

判断依据：

- 当前 staging 13238；把这两个 `RuntimeFiles` 条目去掉正好是 13236，
  且 `data/i18n` 其余文件的创建时间均为 10/27–10/28，只有这两个是 09:43:10 新建。
- 两者都被 `i18n.js` 直接 `fetchJSON`（英文名/物品名翻译链），属于运行期数据；
  不是 `raw/`、`*.bak.json`、调试图等开发中间产物。
- 结论：**接受 13238 作为新基准**；未修改排除表、未删文件、未跳过校验。
- `data/i18n/names.json` 存在大小写重复键（`Prapor`/`prapor`），
  PowerShell `ConvertFrom-Json` 会拒绝；浏览器 JSON.parse 可接受。该文件仍按原文打包。

## 4. 包内容包含他人今天上午的数据更新

以下 40 个 staging 文件 mtime 在 09:30–10:00，其中 `app.js` 09:38 是本次 R19.8f 的改动；
其余 **39 个**是另一位操作者/数据管线在 **09:41–09:43** 刷新的运行期数据，
本轮打包会把它们一起打进包：

- `data/items.json`、`data/roadnet.json`
- `data/i18n/names.json`、`data/i18n/items-zh.json`
- `assets/roadnet/**` 共 35 个 `.bin`

完整路径、大小、mtime 清单：`docs/r34-package/external-data-refresh.txt`（42 行 = 头 2 行 + 40 文件）。

## 5. 步骤 3：重建 dist（通过）

命令：`powershell -ExecutionPolicy Bypass -File build\build.ps1`

结果：

- 清单校验 13238/13238，缺失 0。
- PyInstaller 6.22.3 / Python 3.14.3 构建成功。
- `dist\EFTMap` 重建后：**14,230 个文件、161,610,109 B**（PyInstaller 运行时 + 13238 站点文件）。
- `dist\EFTMap\EFTMap.exe` 2,588,015 B，SHA256 `7C3039C64A97883F4B0550E4BAC82D78CC0095B9F110B52448DC36432FD5BEEA`。
- 前端一致性：
  - `app.js` 与 `dist\EFTMap\_internal\app.js` SHA256 一致（含越界保护，guard 在 `_internal\app.js:4785`）。
  - `combat_sim.js` 与包内文件一致；i18n 两个新增文件与包内一致。
- 包内未发现 `ui-showcase.*`、`data/**.bak.json`、`data/tasks/raw/`。

## 6. 步骤 4：冒烟（页面通过，发现 4 个图标 404，停止）

环境：`dist\EFTMap\EFTMap.exe --server-only --port 8788`（打包产物自带 serve），
Chrome CDP 隔离上下文打开 `http://127.0.0.1:8788/`。

通过项：

- 主页面、地图（越界保护生效，viewBox 落在图内）、任务、配装、配枪、弹药、官方 Wiki 模式均可打开。
- 官方 Wiki 模式 `604 / 604` 图层加载。
- 指定脚本/样式全部 200：`tasks.js`、`wiki-map.js`、`gun_builder.js`、`combat_sim.js`、
  `i18n.js`、`calibrator.js`、`styles/*`、`js/*`。
- 外部网络请求：**0**（369 个请求全部指向 `127.0.0.1:8788` 或 data URI）。
- 控制台错误：仅 `favicon.ico` 404。

截图证据：

- `docs/r34-package/smoke/map.png`
- `docs/r34-package/smoke/tasks.png`
- `docs/r34-package/smoke/loadout.png`
- `docs/r34-package/smoke/gun.png`
- `docs/r34-package/smoke/ammo.png`
- `docs/r34-package/smoke/wiki.png`
- 网络摘要：`docs/r34-package/smoke/network-summary.txt`

异常（停止原因）：

- 4 个图标 404：
  - `assets/guns-full/6a15ae2ae5267ba21c07f98f.png`
  - `assets/guns-full/6a78b7f8c2016eb33e0027cd.png`
  - `assets/icons-transparent/6a15ae2ae5267ba21c07f98f.png`
  - `assets/icons-items/6a15ae2ae5267ba21c07f98f.webp`
- 对应物品：
  - `6a15ae2ae5267ba21c07f98f` = HK 416A5 5.56x45 突击步枪（RAL 8000）
  - `6a78b7f8c2016eb33e0027cd` = FN P90 5.7x28 冲锋枪（灾厄）
- 原因：这两把枪由 09:42 的外部 `data/items.json` 刷新新增，但源目录没有对应图像；
  `verify_package_files.ps1` 只校验已存在文件，因此不在清单里。
- 影响：配枪/配装页可打开，但选中这两把新枪时会出现破图；不是缺失脚本/样式。
- 按「任何一步异常就停在原地报告」，未执行步骤 5/6（release 重建与安装器验收）。

## 7. 本轮产生的文件

- `docs/r34-package/meta.txt`
- `docs/r34-package/git-status-before.txt`
- `docs/r34-package/baseline-dist_EFTMap.csv`
- `docs/r34-package/baseline-release.csv`
- `docs/r34-package/baseline-portable-entries.txt`
- `docs/r34-package/baseline-summary.txt`
- `docs/r34-package/verify-before.txt`
- `docs/r34-package/external-data-refresh.txt`
- `docs/r34-package/smoke/*.png`、`smoke/network-summary.txt`
- `docs/r34-package-ledger.md`（本文件）
- `build/_staging_check/`（verify 脚本生成的临时校验收件，不属于 dist/release）

## 9. R34-package-2：补图尝试（失败，停止）

host=HOMONAS user=MASTERJJ at=2026-11-03T10:51:52+08:00 round=R34-package-2

### 9.1 实测代理与源

- 代理 `http://127.0.0.1:7896` 可用：已知物品
  `https://assets.tarkov.dev/5447a9cd4bdc2dbd208b4567-icon.webp` → **200 image/webp 1928 B**。
- 全程未使用 `curl -k` / 未关闭 TLS 校验。
- 两个新 ID 的 tarkov.dev CDN 变体全部 **404**：
  - `6a2a77cae232fdab260b484a-base-image.webp`（HK 默认预设）→ 404
  - `6a799f200b38edb61b0aca7b-base-image.webp`（P90 默认预设）→ 404
  - `6a15ae2ae5267ba21c07f98f-base-image.webp` / `-icon.webp` / `-512.webp` / `-grid-image.webp` → 404
  - `6a78b7f8c2016eb33e0027cd-base-image.webp` / `-icon.webp` / `-512.webp` / `-grid-image.webp` → 404
- `https://json.tarkov.dev/regular/items`（200，17,344,045 B）中，这两个物品的
  `iconLink` / `gridImageLink` / `baseImageLink` 全部指向 `unknown-item-*` 占位图。
  按用户规则「同名占位不接受」，**没有写入占位图**。
- 本地 `build-cache`、`assets`、`逆向参考`（db4tarkov-local / tarkov.kaedeori /
  build-re-gunsmith）均未找到这两个 ID 的现成图像；本机也没有 EFT Icon Cache。
- `api.tarkov.dev/graphql` 返回 422 `GraphQL server unavailable. Try again later.`，
  未作为唯一依据。

### 9.2 当前状态

- 未写入 `assets/guns-full`、`assets/icons-transparent`、`assets/icons-items` 的任何文件。
- 清单仍为 13238，不是 13242。
- `dist\EFTMap` 仍是上一轮已构建版本（14,230 文件 / 161,610,109 B），
  仍带 4 个缺失图标；`release\` 仍是旧基线，未重建。
- 失败点：上游 tarkov.dev 尚未提供这两把新枪的真实渲染图，无法沿用现有管线补齐。

### 9.3 需要用户决定

1. 等待 tarkov.dev / 官方素材更新后再补图并打包；
2. 提供这两把枪的官方图像文件（同源同规格）后继续；
3. 明确接受 `unknown-item-*` 占位图（当前规则明确不接受，默认不做）。

### 9.4 本轮产生/追加的文件

- `docs/r34-package/icon-fetch-attempt.txt`
- `docs/r34-package-ledger.md`（本节）

## 10. R34-package-3：客户端壳并入与 release 验收（通过）

host=HOMONAS user=MASTERJJ at=2026-11-03T11:31:02+08:00 round=R34-package-3

### 10.1 已知问题：4 张图标缺失（用户选择方案 1 接受）

- 缺失：
  - `assets/guns-full/6a15ae2ae5267ba21c07f98f.png`
  - `assets/guns-full/6a78b7f8c2016eb33e0027cd.png`
  - `assets/icons-transparent/6a15ae2ae5267ba21c07f98f.png`
  - `assets/icons-items/6a15ae2ae5267ba21c07f98f.webp`
- 对应物品：
  - `6a15ae2ae5267ba21c07f98f` = HK 416A5 5.56x45 突击步枪（RAL 8000）
  - `6a78b7f8c2016eb33e0027cd` = FN P90 5.7x28 冲锋枪（灾厄）
- 原因：上游 `assets.tarkov.dev` 对应 ID 全部 404；`json.tarkov.dev/regular/items` 的
  `iconLink` / `gridImageLink` / `baseImageLink` 只给 `unknown-item-*` 占位图。
  按「同名占位不接受」，未写占位图（详见 §9.1、`docs/r34-package/icon-fetch-attempt.txt`）。
- 影响范围：仅在配枪/配装页选中这两把枪时缩略图破图；页面、脚本、地图与其他物品不受影响。
- 处理：记为已知问题，随 0.1.0 release 发布；待上游出图后补图并重新打包。

### 10.2 发布脚本与安装器的最小改动

`build/build_release.ps1`（SHA256 `12ECF3C268221359CC531931E5ADAE749F0C4EA99AC2A576D57C6D83919138`）：

- 头注释从「后续客户端壳阶段（本轮不做）」改为「客户端壳已并入产物」。
- 在 `Test-Path dist\EFTMap\EFTMap.exe` 之后、三个打包动作之前新增 `$HostBin` 复制块
  （第 49–57 行）：从 `tools\host\bin` 复制
  `EFTMapDesktop.exe`、`Microsoft.Web.WebView2.Core.dll`、`WebView2Loader.dll`
  到 `dist\EFTMap`，任一缺失即 throw。
- 因为 Portable / AppWindow / Setup payload 都基于 `dist\EFTMap`，这一处改动同时覆盖三个产物；
  未重写发布逻辑。

`tools/installer.py`（SHA256 `C65B286BE8E9A2D1AC2BEA87A29E067C3C4B250BBA6FF581577FF166A7F802CD`）：

- 新增 `APP_SHELL = "EFTMapDesktop.exe"`（第 38 行）与 `launch_exe()`（第 67–70 行）：
  壳存在则用壳，否则回退 `EFTMap.exe`。
- 快捷方式/安装后启动/`DisplayIcon` 改用 `launch_exe()`（第 155、190、315 行）。
- 未改安装流程、payload 布局、注册表其余字段。
- `python -m pytest tests\test_installer.py -q`：**7 passed**。

### 10.3 重建 release

命令（`-SkipBase`：dist 已在 R34-package 重建并冒烟，避免再次删建 dist）：

```powershell
powershell -ExecutionPolicy Bypass -File build\build_release.ps1 -SkipBase
```

日志关键行：版本 0.1.0；并入 3 个壳文件；Portable / AppWindow / Setup 全部成功；
PyInstaller 6.22.3 + Python 3.14.3。

| 产物 | 体积 | 版本 | SHA256 |
|---|---:|---|---|
| `release\EFTMap-Portable-0.1.0.zip` | 122,417,917 B（116.75 MB） | 0.1.0（文件名） | `FB3FDFAEAF2AFBE9F5D0C35297BBE68EF7CC2BBB9FAE8E9B81A7C39F58C73DAB` |
| `release\EFTMap-AppWindow-0.1.0.zip` | 122,418,056 B（116.75 MB） | 0.1.0（文件名） | `0742DFF7E589E6B1127631E6DAC2B517AF36C1E68AFA99BA7CF34B611145FE4B` |
| `release\EFTMap-Setup-0.1.0.exe` | 133,274,698 B（127.10 MB） | 0.1.0（文件名/安装器常量） | `1BAC950D4CC2A0D25337D6AA3E303131E0FEFD3C84B49B695086647EFCC7C169` |

- Setup exe 没有 FileVersion/ProductVersion 资源（PyInstaller 未设置）；
  版本依据是文件名、`installer.VERSION` 与安装后的注册表 `DisplayVersion=0.1.0`。
- 相比旧基线（3 个文件 83,864,415 B；zip 23.87 MB / Setup 36.1 MB），新产物显著变大，
  原因是 dist 站点从 43.9 MB 增至 161.6 MB（新增 assets/data/前端），并非打包异常。
- 产物清单与哈希证据：`docs/r34-package/release-artifacts.txt`。

### 10.4 解压核对（Portable / AppWindow）

证据：`docs/r34-package/release-content-audit.txt`。

- Portable：14,233 文件 / 155.06 MB；AppWindow：14,234 文件 / 155.06 MB
  （AppWindow 多 `_internal\appmode.flag`，内容 `1\n`）。
- 两者顶层均含：
  - `EFTMap.exe` 2,588,015 B / `7C3039C6...FD5BEEA`
  - `EFTMapDesktop.exe` 92,160 B / `8FC43F98...CEC3B8F`
  - `Microsoft.Web.WebView2.Core.dll` 698,208 B / `D60E6E94...B98505`
  - `WebView2Loader.dll` 194,912 B / `3426DCC...A8ABEE`
  - 壳三文件哈希与 `tools\host\bin` 源文件一致。
- `_internal` 前端文件均在：`tasks.js` 143,006 B、`wiki-map.js` 18,604 B、
  `gun_builder.js` 68,480 B、`combat_sim.js` 41,379 B、`i18n.js` 15,031 B、
  `calibrator.js` 36,910 B；`styles/` 2 文件、`js/` 3 文件。
- 排除项：`ui-showcase.*` 0；`data/**/*.bak.json` 0；`data/tasks/raw/` 不存在。
- Portable 解压后可直接双击 `EFTMapDesktop.exe`（与 `EFTMap.exe` 同目录，壳检测到后端后启动）。

### 10.5 安装器验收（silent）

- 命令：`release\EFTMap-Setup-0.1.0.exe --silent --dir <%LOCALAPPDATA%\EFTMap-R34Accept>`。
- 退出码 0，耗时 41.4 s。
- 安装目录 `C:\Users\Administrator\AppData\Local\EFTMap-R34Accept`：
  **14,234 文件 / 282.16 MB**（含复制进安装目录的 `Uninstall.exe` 127.1 MB）。
- 关键文件齐全：`EFTMap.exe`、壳三文件、`_internal` 六个新前端文件、`styles/`、`js/`、`Uninstall.exe`；
  安装包不带 `appmode.flag`（正确，普通安装由壳托管窗口）。
- 快捷方式：开始菜单与桌面均生成 `EFT 互动地图.lnk`（每份 2,178 B）。
  - WScript.Shell 直接用中文 .lnk 路径读取会返回空值（WSH ANSI 路径限制），
    复制成 ASCII 临时名后读取确认：
    `TargetPath = ...\EFTMapDesktop.exe`、`WorkingDirectory = 安装目录`、
    `IconLocation = ...\EFTMapDesktop.exe,0`。
- 从桌面快捷方式启动：`EFTMapDesktop.exe` 正常拉起后端 `EFTMap.exe`；
  主窗 1280×720 @ (0,0)，`style=0x16040000`（无 `WS_CAPTION`），`visible=true`；
  日志出现「托盘已创建」，托盘右键菜单含显示/隐藏/设置/退出。
- 注册表 `HKCU\...\Uninstall\EFTMap`：`DisplayVersion=0.1.0`、
  `InstallLocation=...\EFTMap-R34Accept`、`DisplayIcon=...\EFTMapDesktop.exe,0`。
- 用户配置 `%APPDATA%\EFTMap\shell.json` 原 `trayEnabled=false`（2026-11-02 23:19
  一次 `--no-tray` 测试残留），改为 `true`（默认值）后快捷方式启动显示托盘；
  当前保持 `true`。这是验收中唯一的用户配置改动。
- 证据：`docs/r34-package/installer-acceptance.txt`、`docs/r34-package/installer-shell/`
  （`main.png` 530,876 B、`mini.png` 100,317 B、`tray-menu.png` 4,669 B、
  `window-state.json` 3,026 B、`desktop.log` 27 行）。
- 验收后卸载：`Uninstall.exe --uninstall --dir <安装目录>` 退出码 0，
  开始菜单/桌面快捷方式与注册表项均已删除；目录仅剩 `Uninstall.exe`
  （自删除时序问题：cmd 以安装目录为 cwd，`rmdir` 删不掉当前目录里的自身），已手动清理。
  验收安装未保留；交付安装使用正式默认目录即可。

### 10.6 版本建议（未自行修改）

- 本轮按用户约束保持 `0.1.0`，三个产物、安装器常量、注册表版本均为 0.1.0。
- 但本轮 release 相对旧 0.1.0 基线内容变化很大（站点 43.9 MB → 161.6 MB、新增前端与客户端壳），
  若用于对外分发，建议下一轮把 `tools/serve.py` 与 `tools/installer.py` 的版本升到
  `0.1.1`（或 `0.2.0`）后重新打包，避免与旧 0.1.0 产物同名混淆。

### 10.7 本轮产生/追加的文件

- `docs/r34-package/release-artifacts.txt`
- `docs/r34-package/release-content-audit.txt`
- `docs/r34-package/installer-acceptance.txt`
- `docs/r34-package/installer-shell/{main.png,mini.png,tray-menu.png,window-state.json,desktop.log}`
- `docs/r34-package-ledger.md`（本节）
- 代码改动：`build/build_release.ps1`、`tools/installer.py`（未提交 git）

