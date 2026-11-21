# R69 · 累计改动并包（R67 + R68）与三件套交付

host=HOMONAS user=MASTERJJ at=2026-11-04 20:22 +08:00

范围：工作区累计未提交改动
- R67：配装名称列 232px 两行、防护区域排序（`app.js` / `style.css`）
- R68：任务页移除「商人任务」选单、任务页 XP 主题、头盔附加件多层、耐久文案（`tasks.js` / `tasks.css` / `app.js` / `combat_sim.js` / `style.css` / `index.html`）

本轮**未 git 提交**，版本仍 `0.1.0`（`tools/serve.py` L53）。未改动打包脚本。

---

## 一、清单预检

`powershell -ExecutionPolicy Bypass -File build\verify_package_files.ps1`

| 指标 | 数值 |
|---|---|
| 预期文件 | **13241** |
| staging 实际 | **13241** |
| 缺失 | **0** |
| 未登记 | **0** |
| staging 体积 | **126.9 MB** |

- 本轮无新增运行期文件（无新样式、无新模块），清单未补录、未改 `build/package_files.ps1`。
- `tasks.css`（43042 B）、`tasks.js`（150784 B）、`theme-windows-xp.css`、`style.css`、`app.js`、`combat_sim.js` 均在 staging 内，由既有清单收集规则覆盖。

---

## 二、dist 全量重建

`powershell -ExecutionPolicy Bypass -File build\build.ps1`（零手工补丁）

| 指标 | 数值 |
|---|---|
| 运行期文件 | **13241 个全部存在** |
| 产物体积（构建报告） | **155.1 MB** |
| PyInstaller / Python | 6.22.3 / 3.14.3 |
| 构建 Rev | `R19.34-390715b6` |
| 主程序 | `dist\EFTMap\EFTMap.exe`（19:49:18） |
| 底图 SVG | 13 张 |
| dist 全量（含 release 并入的桌面壳与 3 个 DLL） | **14239 文件 / 156.0 MB** |

### 源 ↔ dist 逐字节哈希（SHA256）

| 文件 | 源码 = dist | 哈希 |
|---|---|---|
| `tasks.css` | MATCH | `C72BFFD66E9582F5B8303D62D4675D0D997F07080B124EBAC8B07FC2F7E507C5` |
| `tasks.js` | MATCH | `8D3D0DE4617ECE7237EAA17BDB12D1FD25B172A615C2664F2D0F6DAF5DB1180B` |
| `app.js` | MATCH | `876DDFB2C13C5A59B57D16B43EE9CAE58DD91AA23ADB39EF08198D147045B6A4` |
| `style.css` | MATCH | `5176915900CBF3C4634C4EB26D1A42F72C66BD6D00A74D1B7E8D30C636F30E57` |
| `theme-windows-xp.css` | MATCH | `1D0B3AFC7279DBAF30B896616EDBD4670D0DD4E21E5F350B375FE9D4C3A1D384` |

---

## 三、真浏览器冒烟（dist 内 `EFTMap.exe`）

后端：`dist\EFTMap\EFTMap.exe --server-only --port 8788 --config-dir D:\Temp\r69-smoke-config --runtime-file D:\Temp\r69-smoke-runtime.json --log-file D:\Temp\r69-smoke-server.log`
（避开他人占用的 8791 / 8795 / 8796 / 8797 / 8798；未触碰占用进程）

`/api/build`：`rev=R19.34-390715b6`、`server_version=0.1.0`、`root=dist\EFTMap\_internal`。
渲染：Chrome DevTools MCP，DPR 0.667；`960x600x0.667` = CSS 1440×900，`683x512x0.667` = CSS 1024×768。

### 3.1 断言表

| 断言 | 1440×900 | 1024×768 |
|---|---|---|
| 首页地图 SVG | true | true |
| 导航项 | 5（地图/配装/配枪/弹药/任务） | 5 |
| 任务页页签 | 4（任务树/任务列表/任务详情/我的进度） | 4 |
| 商人任务选单 `#tk-traders` | **不存在** | **不存在** |
| PvP 任务行 | **503** | **503** |
| PvE 任务行 | **499** | **499** |
| 切回 PvP | 503 | 503 |
| 任务页深色残留（RGB<60 背景） | **0** | **0** |
| 任务页壳底色 | `rgb(236,233,216)`（XP face） | 同左 |
| 任务行底色 | `rgb(255,255,255)` | — |
| 配装候选行（护甲） | 108 | 108 |
| 名称列宽 | **232px** | **232px** |
| 行外框 / `clientHeight` / `scrollHeight` | 80 / 77 / 77 | 80 / 77 / 77 |
| 名称格纵向溢出 | **0 / 108** | **0 / 108** |
| 名称文本纵向溢出 | **0 / 108** | **0 / 108** |
| 名称最大行数（行高 16.2） | **2** | **2** |
| 「防护区域」首点降序违例 | **0** | **0** |
| 再点升序违例 | **0** | **0** |
| 两次排序 id 集合一致 | true（108 行不丢不重） | true |
| 覆盖部位数范围 / 空值行 | 1–6 / 0 | 1–6 / 0 |
| 逐发模拟：头盔可选附加件 | Altyn：**1 槽 / 3 选项**（未安装 + 2 面罩） | 同左 |
| 逐发模拟：层序 | **1 面罩 → 2 头盔本体 → 3/4/5 内衬** | 同左 |
| 关于页 | 展开 430×648，无横向溢出 | 430×553，无横向溢出 |
| 账号抽屉卡数 | **5** | **5** |
| 页面级横向溢出 | 0（docW = 1440） | 0（docW = 1024） |

补充证据（逐发模拟实跑，固定种子，SSA AP，命中头，3 发）：
- 第 1 发：面罩 50→38.6（穿透）→ 头盔 81→70.4（穿透）→ 内衬 27→18.4 / 27→21.8。
- 汇总文案：`Altyn面罩 耐久 17.378… / 出厂满 50`、`Altyn 突击头盔（橄榄绿） 耐久 50.568… / 出厂满 81`（R68 问题 4 的文案已在包内）。

### 3.2 网络 / 控制台

重新加载后完整走一遍全部页面（地图 → 任务 PvP/PvE → 配装护甲 → 逐发模拟 → 关于 → 账号）：

| 指标 | 结果 |
|---|---|
| 请求总数 | 404 |
| 非 200 / 304 | **0**（全部 200 或 304） |
| 外部主机请求 | **0**（资源域全部 `http://127.0.0.1:8788`，另有 1 条 `data:` 内联 SVG） |
| console error | **0** |

（会话早期有 2 条 `ERR_CONNECTION_*` 来自冒烟前重启后端时的旧连接，重载后已不再出现，不计入。）

### 3.3 截图（10 张）

目录 `docs/r69-final-package/smoke/`：

| 文件 | 内容 |
|---|---|
| `r69-home-1440.png` | 1440×900 首页地图 |
| `r69-tasks-1440.png` | 1440×900 任务页（4 页签、无商人选单、XP 浅底） |
| `r69-loadout-1440-zone-desc.png` | 1440×900 配装护甲候选，防护区域降序、名称两行 |
| `r69-sim-1440-altyn.png` | 1440×900 逐发模拟：Altyn + 面罩附加件已选 |
| `r69-about-1440.png` | 1440×900 关于页 |
| `r69-account-1440.png` | 1440×900 账号抽屉 5 卡 |
| `r69-home-1024.png` | 1024×768 首页 |
| `r69-tasks-1024.png` | 1024×768 任务页 |
| `r69-loadout-1024.png` | 1024×768 配装护甲候选（防护区域降序） |
| `r69-sim-1024-altyn.png` | 1024×768 逐发模拟（Altyn + 面罩） |

---

## 四、release 三件套

`powershell -ExecutionPolicy Bypass -File build\build_release.ps1 -SkipBase`（版本 0.1.0）

| 产物 | 体积 | 字节 | SHA256 |
|---|---|---|---|
| `EFTMap-Portable-0.1.0.zip` | **116.9 MB** | 122587944 | `818B2874660AAC126B1CB682C2F09BCD1E2025DB4371FFAEB7579558D0C094FB` |
| `EFTMap-AppWindow-0.1.0.zip` | **116.9 MB** | 122588083 | `9AD773D7B68E2A98F1BE54D661F7626E978EEFFCCD2D99349CB734C854EC7FB2` |
| `EFTMap-Setup-0.1.0.exe` | **127.3 MB** | 133447292 | `D885C1D97EA8A7C5678FC2730D1FFBD52E1E8E0BECABDDBC12A8E16CCC768F5B` |

注入桌面壳文件：`EFTMapDesktop.exe`、`Microsoft.Web.WebView2.Core.dll`、`WebView2Loader.dll`。

---

## 五、安装器验收（R47 / R53 结论复验）

| 步骤 | 结果 |
|---|---|
| 静默安装 `EFTMap-Setup-0.1.0.exe --silent --dir D:\Temp\r69-install` | exit 0 |
| 安装目录顶层 | 6 项：`EFTMap.exe`(2653615)、`EFTMapDesktop.exe`(92160)、`Uninstall.exe`(2653615)、`_internal`、`Microsoft.Web.WebView2.Core.dll`(698208)、`WebView2Loader.dll`(194912) |
| `_internal` 文件数 / 整包体积 | **14235** / **158.5 MB** |
| 开始菜单快捷方式 | 存在：`…\Start Menu\Programs\EFT 互动地图.lnk` |
| 桌面快捷方式 | 存在：`C:\Users\Administrator\Desktop\EFT 互动地图.lnk` |
| 注册表卸载项 | `HKCU\…\Uninstall\EFTMap`：DisplayName=EFT 互动地图（离线版）、DisplayVersion=0.1.0、EstimatedSize=162339、InstallLocation=D:\Temp\r69-install、UninstallString 指向 `Uninstall.exe --run-tool …installer.py --uninstall --dir …` |
| 从快捷方式启动 | 壳 `EFTMapDesktop.exe` + 后端 `EFTMap.exe` 双进程；后端监听 `127.0.0.1:1670` |
| 后端自检 | `/api/build` 200：`rev=R19.34-390715b6`、`ver=0.1.0` |
| 卸载（按注册表 UninstallString） | exit 0 |
| 清理计时 | **目录 + 注册表 + 2 个快捷方式全部消失用时 6.25 s（≤10 s）** |

（注：卸载只清安装目录/注册表/快捷方式；`%LOCALAPPDATA%\EFTMap` 下的配置、日志、WebView2 缓存按设计保留，与 R47/R53 结论一致。本次测试安装目录此前已清空，测试后未残留。）

---

## 六、回归

```
C:\Python314\python.exe -m pytest tests -q
1736 passed, 1 skipped in 101.58s
```

**0 failed**，与基线 1736 passed / 1 skipped 一致。

---

## 七、结论与未通过项

- 三件套**全部通过验收**：清单 0 缺失 / 0 未登记，5 个关键文件源=dist 哈希一致，冒烟断言全部达标（非 200/304 = 0、外部请求 0、console error 0），安装→启动→卸载闭环 6.25 s 清干净，回归 1736 passed / 0 failed。
- **未通过项：无**（本轮冒烟未发现需要修复的问题，因此无「先修再重出」记录）。

### 遗留（不在本轮范围）

1. **本机 5 条弹药缺碎片数量**：R63 台账记录本地 `MinFragmentsCount` / `MaxFragmentsCount` 为 **195 / 200**，缺 5 条 `6a…` 条目（上游 218/218）。碎片化只能按 `+0.5× / 1 片` 的保守估计实现。
2. **修复后耐久上限缺失**：`items.json` 只有出厂 `dur`，没有「修复后可恢复上限 / 耐久上限」。R68 问题 4 只做了文案定性（当前耐久 / 出厂满），公式与数据未扩字段；要做精确修复上限需上游/游戏真值补数据。
3. **版本号建议**：功能与 UI 均为增量修复，无协议/数据格式破坏性变更。当前 `0.1.0` 可保留；若要给这批累计 UI/模拟改动一个可识别的交付标记，建议下一次对外包用 `0.1.1`（或 `0.2.0` 若把头盔多层视为新特性），并在 `tools/serve.py` 与安装器 `VERSION` 同步。

### 清理

- 冒烟后端已停止（端口 8788 释放，无 `EFTMap` 残留进程）。
- `D:\Temp\r69-install`、`D:\Temp\r69-smoke-config`、`D:\Temp\r69-smoke-runtime.json`、`D:\Temp\r69-smoke-server.log` 已删除；`D:\Temp\2` 的 10 张临时截图已移入 `docs/r69-final-package/smoke/` 并清理原图。
- **未 git 提交**。
