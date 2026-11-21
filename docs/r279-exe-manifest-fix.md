# R279-fix · EFTMap 0.2.7 EXE「找不到序数 380」排查与干净重建

> 日期：2026-11-14 · 输出包：`release-test/EFTMap-Setup-0.2.7.exe`
> 原故障样本 `release/EFTMap-Setup-0.2.7.exe` **原样保留**，未覆盖、未删除。

---

## 1. 打包技术确认（第一阶段）

| 项 | 结论 |
| --- | --- |
| package.json / electron-builder / NSIS / Inno Setup / pyproject.toml / requirements.txt | **均不存在** |
| 实际工具 | **PyInstaller 6.22.3**（`C:\Python314\python.exe`，Python 3.14.3） |
| 基础包 | `build\build.ps1` → `--onedir --noconsole`，产物 `dist\EFTMap`（367.8 MB） |
| 发布脚本 | `build\build_release.ps1`：两个 zip（`Compress-Archive`）+ 单文件安装器 |
| 安装器生成方式 | `python -m PyInstaller --noconfirm --onefile --noconsole --name EFTMap-Setup-<版本> --add-data "<dist\EFTMap>;payload" tools\installer.py` |
| 安装器源码 | `tools\installer.py`（Tk 四页向导，payload 为整站） |
| spec | `build\EFTMap-Setup-0.2.7.spec`（自动生成的标准 spec，`console=False`，无自定义 manifest 参数） |
| 版本 | `tools/serve.py` 与 `tools/installer.py` 均为 `0.2.7`（未改） |

### 中断点与未完成产物

`build\_release_r279.log` 停在 `Analysis` 阶段（14:33 用户中断），当时两个 zip 已经产出（14:28 / 14:32），
**安装器 exe 尚未生成**。之后为补打安装器连续尝试 4 次：

| 日志 | 输出目录 | 结果 |
| --- | --- | --- |
| `_setup_r279.log` | `release/` | `EndUpdateResourceW` error(5) 反复重试，被中止 |
| `_setup_r279b.log` | `build/_setup_out/` | 同上 |
| `_setup_r279c.log` | `build/_setup_out/` | 引入 wrapper 打桩后，卡在 `CopyIcons`（补丁打错模块） |
| `_setup_r279d.log` | `build/_setup_out2/` | wrapper 补丁修正后 **26 s 构建成功** ← 产出了故障 exe |

未完成产物：`build/_work_installer`（混用多次的旧 workpath）、`build/_setup_out{,2}`、
10 个 `RCX*.tmp`（资源更新失败残留）、`build/_release` 暂存目录。**新旧版本文件确有混合**：
`release/` 里两个 zip 是 14:28/14:32 的正常产物，exe 是 15:04 用 wrapper 产出的坏包。

### 故障样本（保留）

| 项 | 值 |
| --- | --- |
| 路径 | `release\EFTMap-Setup-0.2.7.exe` |
| 大小 | 227,180,749 bytes（216.66 MB） |
| 修改时间 | 2026-11-14 15:04:25 |
| SHA256 | `920A6D15C03E3EB886EBCF53D2FE1C3B9B58E884AC6254A8038B906AE4581C93` |

---

## 2. 序数 380 根因（第二阶段）

### 直接证据：PE 资源表

用 `build/_pe_manifest.py`（只读 PE 资源解析，本轮新增）对比：

| 文件 | PE DataDirectory[2] 资源目录 | RT_MANIFEST(24) |
| --- | --- | --- |
| `release\EFTMap-Setup-0.2.7.exe`（故障） | **RVA=0, size=0（完全没有资源目录）** | 无 |
| `dist\EFTMap\EFTMap.exe`（同版本内部主程序） | RVA=0x51000, size=62492 | 有，1293 字节，含 `Microsoft.Windows.Common-Controls 6.0.0.0` |
| `PyInstaller\bootloader\Windows-64bit-intel\runw.exe` | RVA=0, size=0 | 无（bootloader 本身不带清单） |

> 关键点：PyInstaller 的 bootloader **本来没有 Manifest**，必须靠构建期的
> `winmanifest.write_manifest_to_executable()` 写入。跳过它 = EXE 没有
> Common Controls 6.0 依赖声明 → Windows 加载 comctl32.dll v5.x →
> 启动时找不到 `LoadIconMetric`（序数 380）。

### 出错对象

**是安装程序自身的 PyInstaller bootloader**，不是 payload 内的应用：

- Windows 报错路径是 Setup exe 本身，处于**加载器阶段**（onefile 还没解压 payload）；
- payload 内的 `EFTMap.exe` 清单完整、启动正常；
- 对照实验（`--help`）：故障样本 70 s 不退出（被加载器错误框挂住），修复包 `ExitCode=0`。

### 为什么会缺 Manifest

`build/_setup_wrapper.py`（14:35 引入的一次性构建包装器）为绕开
`EndUpdateResourceW` 的 `ERROR_ACCESS_DENIED`，把下列函数全部打桩为 no-op：

```python
winresource.remove_all_resources          = lambda *a, **k: None
winmanifest.write_manifest_to_executable  = lambda *a, **k: None
versioninfo.write_version_info_to_executable = lambda *a, **k: None
icon.CopyIcons                            = lambda *a, **k: None
```

PyInstaller 在 `api.py` 里是**先打日志再调用**，所以日志里依旧出现
`Embedding manifest in EXE`，实际上什么都没写 —— 这也是它最容易骗过检查的地方。

### 为什么会引入这个 wrapper（次生问题）

`build/_res_probe.py` 最小 Win32 探针（本轮新增）实测：

| 目标位置 | `BeginUpdateResource` | `EndUpdateResourceW` |
| --- | --- | --- |
| `D:\personal\trae\...\release\`、D:\Temp、D:\Download（已在 Defender 排除） | 成功 | **error(5) 拒绝访问，每次约 92 s** |
| `C:\Users\Administrator\AppData\Local\Temp\` | 成功 | 成功 |
| D: 盘 + `bDeleteExistingResources=False` | 成功 | 仍 error(5) |

两个卷都是 NTFS，`Get-MpPreference` 的受控文件夹访问为 0、加 Defender 排除也无效 →
是 **D: 卷上的文件系统过滤/安全驱动拦截了对 PE 资源的写回**，与 PyInstaller、业务代码、
依赖版本都无关（PyInstaller 6.22.3 在 13:04/13:19 曾正常构建 0.2.6）。
C: 盘原生 PyInstaller 探针 21 s 完成且 Manifest 正确嵌入，证明工具链本身没问题。

---

## 3. 修复与干净重建（第三阶段）

**未修改任何业务代码、地图数据、资源文件或功能逻辑；未改 spec；未动 lockfile；未提交 Git。**

| 动作 | 说明 |
| --- | --- |
| `build/_setup_wrapper.py` | **保留文件、改为防护版**：误调用即报错退出（exit 2），杜绝再产出无 Manifest 的 EXE |
| `build/build_release.ps1` | Setup 段的 `--distpath/--workpath` 改到 `$env:TEMP\EFTMap-Setup-Build-<版本>`（C: 盘，可用 `EFTMAP_SETUP_BUILD_DIR` 覆盖），构建成功后 `Copy-Item` 回 `release\`；新增 `Get-PeResourceRva()` 防回归校验：**资源目录 RVA=0 直接抛错**，不再让缺 Manifest 的包流出；清理改删独立临时目录。zip 打包、PE 子系统校验、壳校验等逻辑均未改动 |
| 构建缓存 | **未删除任何构建缓存目录**：根因不是缓存损坏，`build/_work_installer`、`_setup_out{,2}`、`_release`、`_probe_pyi` 全部保留作审计证据，重建时改用全新独立 workpath + `--clean`。曾尝试清理 10 个失败残留 `RCX*.tmp`，因句柄占用未能全部删除（无害的资源更新临时文件，路径集中在 `build/_probe_pyi/out`、`build/_setup_out`） |
| 系统改动 | 撤销上一轮误加的 Defender 排除 `...\build\_setup_out`（`Remove-MpPreference`），排除列表恢复为原始两项 |
| 新增工具 | `build/_pe_manifest.py`（PE 清单只读解析）、`build/_res_probe.py`（资源 API 探针），仅用于排查 |

**构建命令**（原生 PyInstaller，无包装器，`--clean`，输出全部在独立临时目录）：

```powershell
$root='D:\personal\trae\02-塔科夫\eft-interactive-map'
$base='C:\Users\Administrator\AppData\Local\Temp\eftmap-r279build'
python -m PyInstaller --noconfirm --clean --onefile --noconsole `
  --name "EFTMap-Setup-0.2.7" `
  --distpath "$base\out" --workpath "$base\work" --specpath $base `
  --paths "$root\tools" --add-data "$root\dist\EFTMap;payload" `
  "$root\tools\installer.py"
# 日志：$root\build\_setup_r279fix.log
```

- 耗时 2 m 57 s，`exit=0`，日志中 **无任何 WARNING / ERROR / EndUpdateResource 重试**；
- `Copying icon to EXE` / `Embedding manifest in EXE` / `Appending PKG archive` 均为真实执行；
- 新 exe 的 RT_MANIFEST 1293 字节，含
  `<assemblyIdentity name="Microsoft.Windows.Common-Controls" version="6.0.0.0" .../>`；
- 从 C: 盘复制到 **`release-test\EFTMap-Setup-0.2.7.exe`**，`release/` 内故障样本未动。

---

## 4. 实际验证（第四阶段）

| # | 验证项 | 结果 |
| --- | --- | --- |
| 1 | 安装包启动 | ✅ 进程 `EFTMap-Setup-0.2.7` 存活、`Responding=True`；`--help` 退出码 0（故障样本对照：70 s 挂住） |
| 2 | 向导界面 | ✅ `PrintWindow` 截图 `build/_r279fix_wizard.png`：标题「EFT 互动地图 0.2.7 · 安装」、欢迎页、三个底部按钮完整渲染，无错误框 |
| 3 | 完整安装流程 | ✅ `--silent --dir release-test\_installed` 退出码 0，落 **14,471 个文件 / 392,944,257 bytes**，含 `EFTMap.exe`、`EFTMapDesktop.exe`、`Uninstall.exe`、`_internal/`；清单见 `release-test/_install_verify.txt` |
| 4 | 安装后主程序启动 | ✅ `--server-only --port 8793` 正常监听；默认双击路径也能拉起 `EFTMapDesktop.exe`（Responding=True） |
| 5 | 主界面加载 | ✅ `GET /` 200（78,085 B）、`/app.js` 200（1,303,471 B）、`/market.css` 200 |
| 6 | 地图/资源/本地数据 | ✅ `/data/maps.json` 200、`/data/items.json` 200、`/data/ocr-item-names.json` 200、`/assets/maps/Customs.svg` 200（13 张 SVG 随包）、`/assets/ocr/det.onnx` 200；`/api/build`、`/api/price-cache/status` 均 200 |
| 7 | 无数序 380 / DLL 错误 | ✅ 最近 30 分钟 Windows 应用程序事件日志无 `序数 / ordinal / LoadIconMetric / SideBySide / comctl32 / EFTMap` 相关错误；故障样本与修复包对照实验结论一致 |

> 说明：本机桌面会话无交互前台窗口（`GetForegroundWindow()=0`），无法用鼠标真实点击向导四步，
> 因此「完整安装事务」用安装器自带的 `--silent` 路径执行（与 GUI 共用 `install_into()`：
> payload 校验 → 暂存复制 → 原子换入 → 快捷方式 → 卸载项）；GUI 界面用 `PrintWindow` 截图验收。

### 本次验证产生的环境改动（保留，未擅自删除）

- 桌面 `C:\Users\Administrator\Desktop\EFT 互动地图.lnk`
- 开始菜单 `...\Start Menu\Programs\EFT 互动地图（离线版）.lnk`
- HKCU 卸载项 `EFTMap`
- 已安装目录 `release-test\_installed`

验证前这些条目**均不存在**。如需清理，运行安装器自带的卸载入口即可
（`EFTMap-Setup-0.2.7.exe --uninstall --dir "<release-test\_installed 绝对路径>"`）。
本次未代为执行卸载：该命令被会话安全策略拦截，且删除桌面文件属于需用户确认的高风险操作。

---

## 5. 交付物

| 项 | 值 |
| --- | --- |
| 新安装包 | `release-test\EFTMap-Setup-0.2.7.exe` |
| 大小 | 227,244,537 bytes（216.72 MB） |
| SHA256 | `B828F2329515E8D4B95636FD69BDB7D0464856CE92472082672BD947AD7F22A9` |
| 构建日志 | `build\_setup_r279fix.log`（原生构建，无警告） |
| 历次失败日志 | `build\_setup_r279{,b,c,d}.log`、`build\_release_r279.log` |
| 验证截图 | `build\_r279fix_wizard.png` |
| 安装清单 | `release-test\_install_verify.txt` |
| 故障样本 | `release\EFTMap-Setup-0.2.7.exe`（SHA256 `920A6D15…A8038B906AE4581C93`，未改动） |

### 发布脚本的防回归改造（已做，未在 release/ 上重跑）

`build\build_release.ps1` 的 Setup 段已改为「C: 盘临时目录构建 → 拷回 release\」，
并加了资源目录 RVA 校验。验证结果：

- PowerShell 语法解析：`ParseFile` 错误数 **0**；
- 新增校验的等效计算：修复包 `resourceRVA=0x51000` → 通过；故障样本 `resourceRVA=0x0` → 会被脚本直接拦下；
- 本次**没有重跑 `build_release.ps1`**：它会重写 `release\` 下的三个产物，违反
  「保留现有安装包作为故障样本」的要求。其 Setup 段的等价 PyInstaller 命令已独立完整执行
  并验证成功（见 `build\_setup_r279fix.log`），两个 zip 也保持原样。

下次要出正式发布包时，先备份或移走 `release\` 里的故障样本，再正常执行
`powershell -ExecutionPolicy Bypass -File build\build_release.ps1 -SkipBase` 即可。
