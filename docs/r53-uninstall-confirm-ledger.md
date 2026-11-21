# R53 卸载器双击确认留痕

host=HOMONAS user=MASTERJJ at=2026-11-04 08:17:32

## 结论

- 双击 `Uninstall.exe`（无参数）现在先弹原生中文确认框，选「是」才卸载，选「否」静默退出，不再打开启动器。
- 「程序和功能」的 `UninstallString` 一字未改，实测无弹框、直接卸载。
- 选「否」安全：进程退出码 0，安装目录 14239 个文件原样保留，注册表与两个快捷方式都在，无新窗口/新进程残留。
- 新 Setup 133,418,098 B，SHA256 `440CFA09D1C5052776F029338F2B9E14B5BDF592046C2F56E1D8A4D4CC40D9CA`。
- `python -m pytest tests -q`：**1713 passed / 1 skipped**（97.85 s），不低于基线。

> ⚠ 与「dist 未变，不必重建」的前提不同：双击入口是 `EFTMap.exe`（`Uninstall.exe` 就是它的副本，R47 设计），
> 所以确认逻辑必须改在 `launcher.py`，`EFTMap.exe` 因此变化，dist 与另外两个包也一并重出，保证三件套一致。

## 1. 改法

只改 [tools/launcher.py](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/tools/launcher.py)（新增约 50 行），不碰业务逻辑：

1. `main()` 一进来，在 `--run-tool` 与正常启动之前先判断：
   - `argv` 为空，且 `basename(sys.executable).lower() == "uninstall.exe"` → 走确认卸载；
   - 其余（含 `--run-tool ... --uninstall --dir ...`）路径完全不变。
2. `uninstall_after_confirm()`：
   - 纯标准库 `ctypes.windll.user32.MessageBoxW`，flags `MB_YESNO(0x4) | MB_ICONQUESTION(0x20) | MB_SETFOREGROUND(0x10000)`；
   - 标题 `EFT 互动地图 · 卸载`；
   - 正文（按 `uninstall()` 的真实行为措辞）：
     > 确定要卸载《逃离塔科夫》互动地图吗？
     > 卸载将删除安装目录里的全部程序文件（含默认位置 %LOCALAPPDATA%\EFTMap 的缓存）、开始菜单与桌面快捷方式，并移除「程序和功能」中的卸载项。
     > 个人设置保存在 %APPDATA%\EFTMap，卸载后会保留。
   - `IDYES(6)` → `run_tool([<安装目录>\_internal\tools\installer.py, "--uninstall", "--dir", <安装目录>])`，与 `--uninstall --dir ...` 是同一条代码路径（`runpy` 执行 `installer.main()`）；
   - 其它（`IDNO`、关闭叉、弹框失败）→ 返回 0，不启动服务、不开浏览器/WebView 窗口。
3. windowed 产物没有控制台也不影响 `MessageBoxW`；卸载目录的延迟删除（`%TEMP%\*.cmd` 重试 15 次）沿用 R47 实现。

## 2. 实测证据

环境：`release\EFTMap-Setup-0.1.0.exe` 静默安装到 `D:\Temp\r53-install`。

| 场景 | 操作 | 结果 |
| --- | --- | --- |
| 双击 → 是 | `Start-Process D:\Temp\r53-install\Uninstall.exe`（无参数），确认框出现后 `WM_COMMAND IDYES` | 弹框标题/措辞正确（截图）；进程退出码 **0**；安装目录、注册表项、开始菜单/桌面快捷方式在 10 秒内全部消失 |
| 双击 → 否 | 同样双击，确认框出现后 `WM_COMMAND IDNO` | 进程退出码 **0**；安装目录仍在（14239 个文件）；`HKCU\...\Uninstall\EFTMap` 仍在；两个 `.lnk` 仍在；无 `EFTMap/Uninstall` 进程、无新窗口 |
| 程序和功能 | `Uninstall.exe --run-tool ...\installer.py --uninstall --dir ...`（即注册表里的原始 `UninstallString`） | **无确认框**（1.5 s 内探测 `#32770` 窗口为空）；退出码 **0**；目录/注册表/快捷方式全部清除 |

截图：[r53-uninstall-confirm.png](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/docs/r53-uninstall-confirm/r53-uninstall-confirm.png)
（标题「EFT 互动地图 · 卸载」、正文与「是(Y)/否(N)」按钮；同一张也已放到 `docs/r52-final-repackage/smoke/` 便于延续归档。）

安装后注册表值（未变）：

```
"D:\Temp\r53-install\Uninstall.exe" --run-tool "D:\Temp\r53-install\_internal\tools\installer.py" --uninstall --dir "D:\Temp\r53-install"
```

## 3. 构建与产物

因为 `EFTMap.exe` 变了，按顺序做了：`build\build.ps1`（清单 13240/13240 全过，154.9 MB）→ `build\build_release.ps1 -SkipBase`（三件套重出）。

| 产物 | 体积（字节） | SHA256 |
| --- | --- | --- |
| `EFTMap-Setup-0.1.0.exe` | 133,418,098 | `440CFA09D1C5052776F029338F2B9E14B5BDF592046C2F56E1D8A4D4CC40D9CA` |
| `EFTMap-Portable-0.1.0.zip` | 122,557,911 | `587B2A73DC366582C30F7B831955509B0536C2D9D0445F2E522857359F4FD8FF` |
| `EFTMap-AppWindow-0.1.0.zip` | 122,558,050 | `C852B8B71FE449B816C02C5D4620965C5C6D66FDEA3CCAA4FFB5FF17C9EDA6ED` |

任务数据未受影响：`dist\EFTMap\_internal\data\tasks\tasks.regular.json` 仍是 `9B1AC081…E5D5D`（与 R52 一致）。

## 4. 测试

`python -m pytest tests -q` → **1713 passed, 1 skipped, 0 failed**（97.85 s）。

## 5. 收尾

- 测试安装目录 `D:\Temp\r53-install` 已不存在；`D:\Temp\r53-shots` 为一次性截图源。
- 未执行任何 git 提交。
- 截图里的 Chrome 窗口（`EFT 互动地图 · 离线免费版`）是 R52 冒烟遗留的浏览器标签，不是本次卸载动作打开的新窗口。
