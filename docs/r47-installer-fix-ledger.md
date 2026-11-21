# R47 · 安装器卸载残留 + favicon 修复台账

host=HOMONAS user=MASTERJJ at=2026-11-04 05:47:41 (Asia/Shanghai)
项目：`d:\personal\trae\02-塔科夫\eft-interactive-map`
版本：**0.1.0**（按约束未升版本）

本轮只动打包/安装器链路，未改业务逻辑，未碰 `app.js` / `gun_builder.js` / `combat_sim.js`
（另一会话正在改配枪/弹道前端）。

改动文件：
- `tools/installer.py` —— 卸载器换实现 + `Uninstall.exe` 改成 `EFTMap.exe` 副本 + tkinter 改为按需加载
- `build/build.ps1` —— `--add-data` 与 `MustHave` 增加 `tools/installer.py`
- `build/package_files.ps1` —— 清单加入 `favicon.ico`（上一轮 R47 起始时已加）
- `index.html` —— 加一行 `<link rel="icon" type="image/x-icon" href="favicon.ico">`
- `favicon.ico` —— 新生成（2563 B）
- `dist/EFTMap/_internal/` —— 手工补 `favicon.ico`、`index.html` 那行、`tools/installer.py`
  （**不重建 dist**：避免把另一会话未完成的前端改动打进去）

## 1. 卸载器删不掉自己的 `Uninstall.exe`

### 1.1 上一轮为什么残留
旧实现：

```python
subprocess.Popen('cmd /c ping 127.0.0.1 -n 2 >nul & rmdir /s /q "%s"' % install_dir, shell=True, ...)
```

两个硬伤：
1. **cmd 的工作目录就是安装目录**（`shell=True` 继承父进程 cwd），cmd 自己占着目录，`rmdir` 永远删不掉根目录；
2. **只删一次**。`Uninstall.exe` 进程还没退出时文件被锁，第一次 `rmdir` 失败就结束，不重试。

### 1.2 改法一：`%TEMP%` 里的「一次性 cmd + 重试 + 自删」（保留）
`installer.py` 新增 `_schedule_dir_removal()`：
- 在 `%TEMP%` 写一个一次性脚本 `eftmap-uninstall-<pid>.cmd`，用 **mbcs（ANSI）编码 + CRLF**，中文安装路径能被 cmd 正确识别；
- 用 `DETACHED_PROCESS | CREATE_NO_WINDOW` 启动，**`cwd=%TEMP%`**（这一条是旧实现缺的关键）；
- 脚本每秒重试 `rd /s /q`，最多 15 次；删完用 `(goto) 2>nul & del "%~f0"` 自删；
- 卸载主进程只做三件事：删两个快捷方式、删注册表项、扔下这个脚本后立刻退出。

为什么选它而不是 `MoveFileEx(MOVEFILE_DELAY_UNTIL_REBOOT)`：后者要**重启**才生效，
用户的验收是「卸载后 10 秒内目录消失」，重启删除方案在本次验收口径下不成立。
`MoveFileEx` 还有个副作用——删除动作排到重启，中间若用户重装会留下同名文件的删除指令。

### 1.3 改法二：`Uninstall.exe` 不再复制 127 MB 的安装包本体
**这是本轮新发现的问题，也是实测卡 10 秒的真正原因。**

旧 `install_into()` 是 `shutil.copy2(sys.executable, install_dir/Uninstall.exe)`。
`sys.executable` 在这里是 **127.21 MB 的单文件（onefile）安装包**。于是：
- 安装目录多出一份 127 MB 的完整安装包（上一轮安完 282.46 MB，其中一半是这个副本）；
- 每次运行 `Uninstall.exe` 都要先把整个 payload 解压到 `%TEMP%`。

实测（空目录卸载，只量启动+调度）：`Uninstall.exe --uninstall --silent --dir <空目录>` →
**126.4 秒**才退出。这种量级下「卸载后 10 秒目录消失」根本无从谈起。

改成：**`Uninstall.exe` = 同目录 `EFTMap.exe`（onedir 启动器，2.53 MB）的副本**，
卸载逻辑仍只有 `installer.py` 这一份源码，通过窗口版产物已有的隐藏入口执行：

```
"<安装目录>\Uninstall.exe" --run-tool "<安装目录>\_internal\tools\installer.py" \
    --uninstall --dir "<安装目录>"
```

配套改动：
- `build/build.ps1` 增加 `--add-data "$Root\tools\installer.py;tools"`，并在 `MustHave` 里查 `_internal\tools\installer.py`；
  （与上一轮 `live_prices.py` / `r20_fetch_prices.py` 同一套做法）
- `installer.py` 的 tkinter 改成**按需加载**（`run_gui()` 里注入 `tk/ttk/filedialog`）。
  卸载路径跑在 windowed 的 `EFTMap.exe` 里，不能因为缺 `ttk`/`filedialog` 连卸载都起不来；
- 注册表 `UninstallString` / `QuietUninstallString` 换成上面的命令（`--dir` 显式传入，不依赖 cwd）。

副作用（已接受）：直接双击安装目录里的 `Uninstall.exe` 会打开启动器窗口，而不是卸载向导；
「控制面板 → 程序和功能」走的是注册表命令，行为正确。旧设计双击是会打开*安装向导*，同样不是卸载。

### 1.4 实测（真实安装 → 卸载 → 校验）

环境噪声先说清：这台机器**进程创建本身极慢**（Defender 实时扫描）：
`python -c pass` = **11 s**，`powershell -NoProfile -c exit` = **121 s**。
所以下面的墙钟时间要按这个基线读。

| 步骤 | 结果 |
| --- | --- |
| 静默安装 `EFTMap-Setup-0.1.0.exe --silent --dir %LOCALAPPDATA%\EFTMap-R47Final` | exit 0，14239 个文件 |
| 安装目录里的 `Uninstall.exe` | **2.53 MB**（是 `EFTMap.exe` 副本，不再是 127 MB 安装包） |
| `_internal\tools\installer.py` | 存在 |
| `_internal\favicon.ico` / `index.html` 的 `rel="icon"` | 存在 / 存在 |
| `DisplayVersion` | 0.1.0 |
| `EstimatedSize` | 161596 KB（约 157.8 MB；上一轮是 payload 外加 127 MB 安装包副本，约 282 MB） |
| `UninstallString` | `"...\Uninstall.exe" --run-tool "...\_internal\tools\installer.py" --uninstall --dir "..."` |
| 执行卸载（同一命令 + `--silent`） | `Uninstall.exe` **exit 0**，**0.4 s** 退出 |
| 目录消失 | **6.6 s**（含 `Uninstall.exe` 在内全部删净） |
| 安装目录 | **完全消失**（含 `Uninstall.exe`），`Test-Path` = False |
| 注册表 `HKCU\...\Uninstall\EFTMap` | 已删除 |
| 开始菜单 / 桌面「EFT 互动地图.lnk」 | 均已删除 |
| `%TEMP%\eftmap-uninstall-*.cmd` 残留 | **0**（脚本自删成功） |
| 测试目录 | 已清理（`EFTMap-R47*` 全部不存在），`%TEMP%\r47-*` 也已清空 |

**临时目录复验（严格按验收口径）**：装到 `%TEMP%\eftmap-r47-temp-install`
（`D:\Temp\2\eftmap-r47-temp-install`，路径带独立盘符）→ 静默安装 exit 0，**14239 个文件**；
执行卸载 → exit 0，**5.4 s 安装目录完全消失**（含 `Uninstall.exe`），注册表项已删，
无 `eftmap-uninstall-*.cmd` 残留；测试目录已删净。

对照实验（旧设计，仅换 `Uninstall.exe` 来源之前）：同样量级的目录，卸载进程退出后
才轮到 `rd`，目录约 **26 s** 消失 —— 说明「延迟 cmd + 重试」这条路本身是通的，
真正拖时间的是 127 MB 单文件的自解压。

补充：**冷态首跑会明显更慢**。新拷贝出来的 `Uninstall.exe` 第一次运行时会被 Defender 首扫，
本机曾观察到首次卸载耗时到分钟级；同一台机器热态复跑就是上表的 0.4 s / 6.6 s。
这是环境噪声（本机 `python -c pass` 都要 11 s），不是卸载逻辑的固有成本。

中间还遇到一次测试脚手架自身的干扰：用 `cmd.exe /c "<QuietUninstallString>"` 启动、
并重定向 stdout 时，一次性 cmd 继承了管道句柄，测试结束时被连同进程树一起收掉，
留下一个 `eftmap-uninstall-<pid>.cmd`（目录未删）。改用 `Start-Process` 直接拉起、不重定向后，
上面那条时间线是干净的；真实用户从「程序和功能」卸载不经过任何管道，不受影响。

## 2. `favicon.ico` 404

项目里没有现成 `.ico`，用现有品牌色新生成一个（**纯 PowerShell + System.Drawing，无第三方依赖、无外网、无占位图**）：

- 尺寸 **16 / 32 / 48** 三帧，全部 32bpp PNG 帧（ICO 目录 3 项，`type=1`）；
- 配色取自 `style.css`：底色 `#12140E`、品牌色环 `#8FAE4B`（`--accent`）、准星与中心点 `#D8E6B0`；
- 文件 `favicon.ico` = **2563 B**。

接入：
- `index.html` 在 `<title>` 后加一行 `<link rel="icon" type="image/x-icon" href="favicon.ico">`；
- `build/package_files.ps1` 的 RuntimeFiles 增加 `"favicon.ico"`（清单 13239 → **13240** 个文件 / 126.2 MB）；
- `build/build.ps1` 的 `MustHave` 增加 `_internal\favicon.ico`。

浏览器实测（Chrome DevTools MCP，真实页面 `http://127.0.0.1:8796/`，后端为安装版产物）：

- `link[rel=icon]` 解析为 `http://127.0.0.1:8796/favicon.ico`；
- 网络面板：`GET /favicon.ico` → **200**，`Content-Type: image/x-icon`；
- 控制台 `list_console_messages(types=["error"])` → **无任何 error**（上一轮那条 favicon 404 的 error 已消失）。

新包内抽查同样通过：Portable zip 里有 `EFTMap/_internal/favicon.ico`，
新安装目录里 `_internal\favicon.ico` 存在且 `index.html` 带 `rel="icon"`。

## 3. 重建 Setup 并复验

`powershell -ExecutionPolicy Bypass -File build\build_release.ps1 -SkipBase`
（dist 未重建，只手工补了 `favicon.ico`、`index.html` 一行、`tools/installer.py` 三个文件）

| 产物 | 体积 | SHA256 |
| --- | --- | --- |
| `EFTMap-Portable-0.1.0.zip` | 116.86 MB | `5CD06712D50ABF586B8947BAEC7EF45309032294946B4942C726F0B208C661AD` |
| `EFTMap-AppWindow-0.1.0.zip` | 116.86 MB | `4573B91C78208B68E14ACB3C421A2389EB5131B6438FC26FF5A5A847207844D5` |
| `EFTMap-Setup-0.1.0.exe` | 127.21 MB | `AEF2F938448A3B7E459545ED6ABDD00F61D47F7029EEC635EF19BA9A1398853D` |

包内抽查（Portable zip，共 14243 项）：
- `EFTMap\_internal\favicon.ico` 存在；
- `EFTMap\_internal\tools\installer.py` 存在，**16710 B**（与源码一致）；
- 安装后 `_internal\index.html` 带 `rel="icon"`。

## 4. 回归

`python -m pytest tests -q` → **1708 passed, 1 skipped**（103.11 s），**0 failed**。

说明：上一轮记录的 5 个配枪失败用例（`test_r19_11_round` / `test_r19_13_round` /
`test_r19_1_round` / `test_r19_5_round` / `test_r6_gun_workbench`）本轮**全部通过**。
本轮没有改过这些用例或对应前端文件，是另一会话的配枪/弹道改动带来的结果；用例总数仍为 1709。

## 5. 仍存在的问题

1. **冷态首跑慢是环境问题，不是逻辑问题**：这台机器上任何新 exe 首次运行都要被 Defender 首扫
   （`python -c pass` 都要 11 s）。热态实测卸载 **0.4 s 退出 / 6.6 s 目录删净**，已落进 10 秒口径；
   冷态首跑（刚装好第一次卸载）可能到分钟级。若要在冷态也稳定压进 10 秒，只能改本机白名单
   或减少安装文件数（14239 个），不是安装器能单方面解决的。
2. **双击 `Uninstall.exe` 会打开启动器**（见 1.3 副作用）；正规卸载入口（设置/控制面板）正常。
3. `EFTMap.exe --help`（windowed 产物）在中文描述上会 `UnicodeEncodeError`，
   并弹 PyInstaller traceback 对话框挂住进程。属既有问题，本轮未处理（不属卸载链路）。
4. 已知上游图标缺口（HK 416A5 RAL 8000、P90 灾厄）仍 404，未用占位图，与上一轮一致。
5. `dist` 是**手工补丁**而非重建（为了不打包另一会话进行中的前端改动），
   下一轮正式重建时 `favicon.ico` 与 `tools/installer.py` 会由 `build.ps1` 自动带入，请以此为准核对。
6. 版本仍 0.1.0；建议正式发版时升 0.2.0（理由见 `r46-package-ledger.md` 第 9 节）。

未做 git 提交。
