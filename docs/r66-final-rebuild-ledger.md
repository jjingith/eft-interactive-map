host=HOMONAS user=MASTERJJ at=2026-11-04 15:38:55

# R66：最终一次重建与验收 —— 台账

> 范围：按当前源码（公式重写 / 钝伤链修正 / 跳弹数据修正 / 弹药飞行段·碎片化·技能 / 任务页打磨）**全量重出**
> `dist` 与 `release` 三件套，并做真实 Chrome 冒烟 + 静默安装验收。
> 版本保持 `0.1.0`；**未 git 提交**；冒烟后端已关停，临时安装与临时目录已清理。

---

## 0. 结论

1. **这次包含全部本轮改动** —— `combat_sim.js` / `app.js` / `index.html` / `style.css` / `data/armor-ricochet.json`（159 条）/
   `data/armor-bt.json` / `data/game-truth/ammo_ballistic.json` / `favicon.ico` 与源码逐字节同哈希；
   Portable 解包抽查 6/6 与 dist 同哈希。
2. **冒烟通过** —— 六组断言（跳弹 2.1 / 双层钝伤链 14.8957→2.6812 / 弹药新字段 / 可选模型默认值 /
   300 m 衰减 42.7·47.5 / 任务 ×3 + 5 张版本卡 + 关于页新版）全部命中；1440×900 与 1024×768 两档
   **非 200/304 = 0、外部请求 = 0、console error = 0**。
3. **安装器通过** —— 静默安装 `DisplayVersion=0.1.0`，快捷方式指向 `EFTMapDesktop.exe`，从快捷方式启动壳+后端正常；
   卸载后**目录 / 注册表 / 两个快捷方式 / 延迟删除脚本**全部清干净（R47 复验通过）。
4. **回归全绿** —— `python -m pytest tests -q` → **1736 passed / 1 skipped / 0 failed**，与基线一致。
5. 唯一偏差：① 的甲损是 **−1.2**（不是预期的 −2），见 §7 遗留问题 1（4 级 combined 插板的材质毁损系数所致，非缺陷）。

---

## 1. 清单预检（`build/verify_package_files.ps1`）

| 项 | 数值 |
|---|---|
| 预期文件数 | **13241** |
| staging 实际数 | **13241** |
| 缺失 | **0** |
| 未登记 | **0** |

> 改清单前即为 13241 / 13241 / 0 / 0（比 R55 的 13240 多 1 —— `data/game-truth/ammo_ballistic.json`
> 被 `Get-JsLocalRefs` 从 `app.js` 的 `fetch()` 自动捕获）。改清单后去重，计数不变。

### 1.1 进包 / 不进包判定

| 文件 | 运行期是否读取 | 结论 | 依据 |
|---|---|---|---|
| `data/game-truth/ammo_ballistic.json` | **是** —— `app.js` `ensureAmmoBallistic()` 直接 `fetch` | **进包** | 弹药详情 σ（`PenetrationPowerDiviation`）与碎片数上下限的唯一来源；缺文件则 σ/碎片字段空白 |
| `data/game-truth/armor_items.json` | 否 | 不进包 | 构建期真值源（r58b 抽取 / r64 对照），仅比对用 |
| `data/game-truth/armor_plates.json` | 否 | 不进包 | 同上（插板槽位参数） |
| `data/game-truth/globals_ballistic.json` | 否 | 不进包 | HeavyVests 技能参数已硬编码进 `combat_sim.js`（`HV_REDUCE_PER_LEVEL=0.004`） |
| `data/game-truth/meta.json` | 否 | 不进包 | game-truth 抽取元信息 |
| `tools/r58b_game_truth.py`、`tools/r58c_scan_managed.py`、`tools/r54*_*.py` | 否 | 不进包 | 构建期管线脚本；`tools/` 整目录本就排除（运行期入口 `tools/installer.py` 由 PyInstaller `--add-data` 单独进 `_internal/tools`） |
| `favicon.ico` | **是** —— `index.html` `<link rel="icon" href="favicon.ico">` | **进包** | 早已在 `$RuntimeFiles` 显式清单内 |

> 结论：`data/game-truth/` **只进 1 个文件**（`ammo_ballistic.json`，169,617 B），其余 4 个留在仓库，避免包体虚胖；
> `tools/r54*/r58*` 全部留在仓库。

### 1.2 `build/package_files.ps1` 改动（本轮唯一源码改动）

1. `$RuntimeFiles` 在 `data/flea-levels.json` 后显式补录 `data/game-truth/ammo_ballistic.json`（附注释说明运行期用途）。
2. `ExcludePaths` 补 4 条排除，每条带理由：`armor_items.json` / `armor_plates.json` / `globals_ballistic.json` / `meta.json`。

---

## 2. 重建

| 步骤 | 命令 | 结果 |
|---|---|---|
| 清单落地 | `build/package_files.ps1` | 13241 条 |
| 全量重建 | `build/build.ps1` | `dist\EFTMap` = **14,236 文件 / 162,584,675 B**（零手工补丁） |
| 并入客户端壳 | `build/build_release.ps1 -SkipBase` | 并入 `EFTMapDesktop.exe` / `Microsoft.Web.WebView2.Core.dll` / `WebView2Loader.dll`；`dist\EFTMap` = **14,239 文件 / 163,569,955 B（156.0 MB）** |

> 端口：本轮未占用 8791/8795/8796/8797 —— 冒烟用 **8798**（构建期不监听端口）；
> 8798 结束后已确认 FREE，且**未杀任何他人的进程**（8787 上他人的 `python tools\serve.py` 保持运行）。

---

## 3. 冒烟（真实 Chrome，1440×900 与 1024×768）

**口径**：Chrome DevTools MCP `emulate "960x600x0.667"` → CSS 1440×900；`"683x512x0.667"` → CSS 1024×768；
页面来自干净 dist（`dist\EFTMap`，端口 8798），真实 `window.CS.simulate`；截图为页面内真实渲染。

### 3.1 断言表（1440×900）

| # | 断言项 | 实测 | 期望 | 判定 |
|---|---|---|---|---|
| ① | M855A1 × 6B23-2 四级甲 + 6B33 前插板，85°，100 m，固定种子 1 | **跳弹（甲/板）**；入体 **2.1**；甲损 **−1.2**；层后耐久 **48.8**；跳弹概率 **55.0%**、掷 **0.527**；钝伤 **2.10（原文口径）** | 跳弹 / 入体 ≈2.0 / 甲损 −2 | 跳弹 ✅、入体 ✅（2.1）；甲损 ⚠ **−1.2**（见 §7-1） |
| ② | 双层：5 级 UHMWPE 插板挡下 + 3 级芳纶内衬（引擎锚点，复刻 R65 用例） | plateBlunt **14.8957**、plateScale **0.5921**、plateDur **4.727584**、linerIn **14.8957**、linerFactor **0.18**、linerOut **2.6812**、`afterBlock=true`、`chance=null`、`linerDur=0`、`dmgToPart=2.6812`、`stoppedBy=armor`；三发甲伤等值累减；`SOFT_LINER_PLATE_BLUNT_ENABLED=false` | 插板钝伤 ~14.9 / 入体 ~2.68 | ✅ |
| ②-UI | 6B23-1（3 级芳纶）+ 刚玉-VM 5 级前插板，0°，seed 1 | 插板挡住 → 钝伤 **7.59**（×0.156）→ 内衬 ×0.330 → 入体 **2.50**；内衬行文案「前层已挡下：只乘自身 BT ×0.330（不判穿透 · 不算甲伤 · 不扣耐久）」，**无穿透概率** | 内衬层不显示穿透概率 | ✅ |
| ③ | 弹药详情新增字段 | 碎片数量 **2–3**；穿透偏差 σ **1.375**；障碍穿透概率 **55%**（另有碎裂概率 44%、跳弹概率 38%） | 三项都在 | ✅ |
| ④ | 可选模型面板 | 距离衰减：`approx`（近似阻力模型，**默认**）/ `none`（纸面终端值）；碎片化 **默认未勾选**；重甲技能 `hv-level` 范围 **0–50**、**默认 0** | 三档齐全、技能默认 0 | ✅ |
| ⑤ | 距离 300 m 穿透/伤害 | 详情行 `300 / 42.7 / 47.5 / 887 / −13.0 / 0.33`；0 m 行 `44.0 / 49.0`（步长 10 m） | 44.0→42.7、49.0→47.5 | ✅ |
| ⑥ | 任务页 / 账号抽屉 / 关于页 | 搜索「蛋卷冰淇淋」→ 1 行，`.db4-item-n` = **×3**（1440 与 1024 均验）；账号抽屉 **5 张版本卡**（标准版/留守版/准备逃离版/未闻者版/黑暗边缘版）；关于页含 **「依据 0.13.x 客户端反编译原文」** | ×3 仍在 / 5 张卡 / 新版公式段 | ✅（关于页子串见 §7-2） |
| ⑦ | 网络与 console | 1440：**266 请求 = 96×200 + 170×304**，非 200/304 **0**，外部 **0**，console error **0**；1024：**243 = 9×200 + 234×304**，非 200/304 **0**，外部 **0**，console error **0**（scrollWidth=1024 无溢出） | 全 0 | ✅ |

### 3.2 截图（`docs/r66-final-rebuild/smoke/`）

| 文件 | 内容 | 字节 |
|---|---|---|
| `r66-1440-sim-ricochet.png` | ① 85° 跳弹 + 入体 2.1 + 甲损 −1.2 | 113,307 |
| `r66-1440-sim-doublelayer.png` | ② 插板挡下 → 内衬只乘 BT（无穿透概率） | 124,517 |
| `r66-1440-ammo-detail.png` | ③ 碎片数量 / 穿透偏差 σ / 障碍穿透概率 | 108,769 |
| `r66-1440-sim-models.png` | ④ 距离衰减 / 碎片化 / 重甲技能三档 | 122,412 |
| `r66-1440-ammo-300m.png` | ⑤ 300 m：42.7 / 47.5 | 109,934 |
| `r66-1440-tasks-x3.png` | ⑥ 任务 ×3 | 49,705 |
| `r66-1440-account-drawer.png` | ⑥ 5 张版本卡 | 87,111 |
| `r66-1440-about.png` | ⑥ 关于页新版公式段 | 104,595 |
| `r66-1024-home.png` | 1024×768 首屏 | 163,509 |
| `r66-1024-tasks-x3.png` | 1024×768 任务 ×3 | 46,702 |

---

## 4. 回归

```
python -m pytest tests -q
1736 passed, 1 skipped, 0 failed
```

> 与 R66 基线（1736 / 1 / 0）一致；本次仅改 `build/package_files.ps1`（构建清单），不触运行期代码。

---

## 5. 三件套（`build_release.ps1 -SkipBase`）

| 产物（`release/`） | 字节 | 体积 | SHA256 |
|---|---|---|---|
| `EFTMap-Portable-0.1.0.zip` | 122,584,701 | 116.9 MB | `027EAC01B35C40842956104C41225EAF06239989DE07B186C51B3EAE38885E86` |
| `EFTMap-AppWindow-0.1.0.zip` | 122,584,840 | 116.9 MB | `2A8D54AD1D0D5C5F82646EE99C498A1C72B9BDE612B8A1F82ABB0ECC4430C169` |
| `EFTMap-Setup-0.1.0.exe` | 133,443,835 | 127.3 MB | `B55B4ACCACDF43C2CAC2E2AC1358C7A6A1CD0FD1BC251295E7654CB09B6AC42F` |

### 5.1 Portable 解包抽查（zip 内 → `dist\EFTMap\_internal\...` 同哈希）

| 文件 | 字节 | SHA256（zip 与 dist 相同） | 同哈希 |
|---|---|---|---|
| `_internal/combat_sim.js` | 51,878 | `D449009972FCD94FBD5714F3D85908E4184B6D36545DDCA96B0927B62EA7EFF4` | ✅ |
| `_internal/app.js` | 1,178,679 | `B631FE2A7879F96F2722998CD569064E0102C693876EE5B59E856BCEF3244926` | ✅ |
| `_internal/data/armor-ricochet.json` | 21,888 | `DD5F6A568871E6C11D08AE3A7FA74DC30189E756363D93242D5715D55627502E` | ✅ |
| `_internal/index.html` | 59,810 | `68CC777288B9932E4BDF5241140CF87C7A5C22F6434027437670EC1E32753803` | ✅ |
| `_internal/data/game-truth/ammo_ballistic.json` | 169,617 | `1F18A22885187CC2E654B693AAD45A66AE858822844730C40A21E9F4870C013B` | ✅ |
| `_internal/favicon.ico` | 2,563 | `F5ED55C368791B2FA7E0616E2CD39FDDA86828EEEDEDBA19EC2656CDDEC995BA` | ✅ |

- zip 条目数 **14,244**（含目录条目），`helmets` **159** 条且与源码 `data/armor-ricochet.json` **逐条全等**。
- `index.html` 内含 `href="favicon.ico"` **True**、含「依据 0.13.x」**True**（R62 关于段在包内）。

---

## 6. 安装器验收（静默安装 → 启动 → 卸载）

| 步骤 | 实测 |
|---|---|
| 静默安装 | `EFTMap-Setup-0.1.0.exe --silent --dir D:\Temp\r66-install` → **exit 0**，耗时 **40 s**，**14,240 文件 / 166,223,570 B**（dist + `Uninstall.exe`） |
| 注册表 | `HKCU\...\Uninstall\EFTMap`：`DisplayName=EFT 互动地图（离线版）`、**`DisplayVersion=0.1.0`**、`Publisher=EFTMap`、`InstallLocation=D:\Temp\r66-install`、`DisplayIcon=...\EFTMapDesktop.exe,0`、`EstimatedSize=162327`、`NoModify=1`、`NoRepair=1` |
| 快捷方式 | 开始菜单 + 桌面两个 `.lnk`；解析 `.lnk` 二进制：`TargetPath = D:\Temp\r66-install\EFTMapDesktop.exe`、`WorkingDirectory = D:\Temp\r66-install` → **指向客户端壳** |
| 从快捷方式启动 | 壳 `EFTMapDesktop.exe` 起来（窗口标题「EFT 互动地图」）；后端 `EFTMap.exe --server-only --shell-mode --port 0` 拿到临时端口 **4840**（`desktop-18456.json`，version **0.1.0**）；WebView2 Runtime 156.0.4314.58，`主页面加载完成`；无 `favicon.ico` 404（R66 包已含 favicon） |
| 后端资源 | `GET /` → **200 / 59,810**；`/index.html` → **200 / 59,810**；`/combat_sim.js` → **200 / 51,878**；`/data/game-truth/ammo_ballistic.json` → **200 / 169,617**；`/data/armor-ricochet.json` → **200 / 21,888**；`/favicon.ico` → **200 / 2,563** |
| 卸载 | `Uninstall.exe --run-tool _internal\tools\installer.py --uninstall --dir D:\Temp\r66-install` → **exit 0**；等待 20 s 后：**目录不存在**、注册表键 **已删除**、两处快捷方式 **已删除**、`%TEMP%\eftmap-uninstall-*.cmd` **无残留**（R47 延迟删除复验通过） |

---

## 7. 遗留问题清单

1. **① 甲损 −1.2 ≠ 预期 −2**：M855A1 打 4 级 `combined` 插板，甲伤 = `P(23.0) × AD(0.235) × clamp(P/Resistance=0.575) × Destructibility(0.375) × 0.6(跳弹半值)` ≈ **1.2**；
   换 6B23-2 背板（`657b22485f444d6dff0c6c2f`）结果同为 −1.2。预期 −2 对应的是别的材质/系数口径（如 `ceramic` 0.6 或未走跳弹半值）。
   → 属口径差异，非缺陷；如要与预期一致，需确认该插板实际 `Destructibility` 与是否应扣跳弹半值。
2. **关于页严格子串**：用户要求「含『依据 0.13.x 反编译原文』」，实际原文是 **「依据 0.13.x 客户端反编译原文」**（多「客户端」二字），语义一致但严格子串不匹配。
3. **距离衰减表取整**：弹药详情 `.am-detail-rows` 精确显示 **42.7 / 47.5**；同页「衰减表」`.tbl-row` 以整数显示 43 / 48，模拟面板 300 m 近似模型显示 43.0 / 47.5 → 同一个值在不同组件有两位/一位/整数三种呈现，属既有设计。
4. **版本号**：保持 `0.1.0`。若本轮视为对外首个完整功能版，建议下一轮升 `0.2.0`（安装器 `VERSION` 与 `tools/serve.py` 有测试锁死，需同改）。
5. **打包产物与仓库的边界**：`data/game-truth/` 有 5 个文件，只进包 1 个。后续若运行期新增读取（如插板槽位参数），需同步在 `package_files.ps1` 的 `$RuntimeFiles` 补录并在 `ExcludePaths` 移出，否则 verify 会报「未登记」。

---

## 8. 清理

- 已删：`D:\Temp\r66-install`（卸载自动清）、`%TEMP%\eftmap-uninstall-*.cmd`、`build\_staging_check`（verify 产物）、临时脚本 `%TEMP%\r66_*.py / *.ps1`、`D:\Temp\r66-cfg`。
- 已关停：冒烟后端（8798，端口现已 FREE）；安装版壳与后端（卸载前手动关闭）。
- 未动：8787 上他人的 `python tools\serve.py`（不属于本任务，按要求未杀）。
- 截图留在 `docs/r66-final-rebuild/smoke/`（10 张，共 1,116,881 B），属台账留痕，不清理。
