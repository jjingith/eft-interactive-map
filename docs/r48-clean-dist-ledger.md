# R48 · 干净重建 dist + `--help` 崩溃修复台账

host=HOMONAS user=MASTERJJ at=2026-11-04 06:13:08 (Asia/Shanghai)
项目：`d:\personal\trae\02-塔科夫\eft-interactive-map`
版本：**0.1.0**（按约束未升版本）

本轮目标：**dist 由源码干净重建、且与已发布包内容一致**，外加修掉 R47 末尾点出的
`EFTMap.exe --help` 崩溃。

改动文件（仅一个）：
- `tools/launcher.py` —— 新增 `harden_stdio()`（第 1235 行），`main()` 首行调用（第 1444 行）

未改任何业务逻辑，未碰 `app.js` / `gun_builder.js` / `combat_sim.js`。dist 与三件套全部由脚本重建，
**没有做任何手工补丁**（这是与 R47 的关键区别：R47 是手工往 dist 里补 favicon / installer.py / index.html）。

## 1. `EFTMap.exe --help` 的 `UnicodeEncodeError` / 挂进程

### 1.1 根因
`--help` 不走 `--run-tool`，而 `--run-tool` 那次修复只覆盖了自己那条路径。windowed（`--noconsole`）
产物在无控制台启动时 `sys.stdout` / `sys.stderr` 可能就是 `None`；argparse 的 `--help` 直接写
stdout，于是：

- 有控制台但代码页是 cp1252 → 写中文描述抛 `UnicodeEncodeError`；
- 无控制台（stdout=None）→ `AttributeError: 'NoneType' object has no attribute 'write'`。

两种情况都会触发 PyInstaller 的 traceback 对话框，进程挂在那里等人点「确定」——这就是之前
`EFTMap.exe --help` 挂 11632 s 的原因。

### 1.2 修法（统一在入口处，不靠改文案绕）
```python
def harden_stdio() -> None:
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        if stream is None:                       # windowed 无控制台
            try:
                setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))
            except OSError:
                continue
            stream = getattr(sys, name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass
```
`main()` 第一行就调 `harden_stdio()`。重定向输出时流是真实管道，仍然照常写；无控制台时兜底到
`os.devnull`，argparse 正常工作且不弹框。任何一步失败都静默跳过，不影响启动主流程。

### 1.3 验收（干净重建产物 `dist\EFTMap\EFTMap.exe`）
| 场景 | 退出码 | stdout | stderr | 对话框 / 残留进程 |
| --- | --- | --- | --- | --- |
| 重定向（`Start-Process -Wait -RedirectStandardOutput`） | **0** | 1650 B UTF-8，中文描述完整 | 0 B | 无 |
| 不重定向（无控制台窗口形态） | **0** | — | — | 无对话框，无残留进程 |

首行输出 `usage: EFTMap.exe [-h] [--host HOST] ...`，末几行中文（`--server-only 的后端日志路径`、
`--settings-only 只打开 tkinter 高级设置窗口…`）显示正常，没有替换字符。

## 2. 端口核查（先查后跑，别人的进程不动）

| 端口 | 状态 |
| --- | --- |
| 8787 | 空闲 |
| 8788–8790 | 空闲 |
| **8791** | **被他人 python 进程占用（pid 31232，3:37 启动）** → 记录，未杀 |
| 8792–8795 | 空闲 |
| 8796 | 空闲 → 本轮冒烟使用 |

## 3. 干净重建 dist

`powershell -ExecutionPolicy Bypass -File build\build.ps1`

- 先按 `package_files.ps1` staging 并做完整性校验，再删 `build\_work` 与 `dist\EFTMap`，再交给 PyInstaller。
- 结果：**14235 个文件 / 154.3 MB**（此时尚未并入客户端壳）。
- `MustHave` 与 `Test-ExpectedFilesPresent` 全部通过。

`powershell -ExecutionPolicy Bypass -File build\verify_package_files.ps1`：

```
完整性校验通过：预期 13240 个文件，staging 实际 13240 个文件，缺失 0，未登记 0。
staging 体积：126.2 MB
```

产物关键文件（干净 dist）：

| 文件 | 大小 |
| --- | --- |
| `EFTMap.exe` | 2,651,989 B |
| `_internal\favicon.ico` | 2,563 B |
| `_internal\tools\live_prices.py` | 29,410 B |
| `_internal\tools\installer.py` | 16,710 B |
| `_internal\wiki-map.js` | 25,314 B |

`build_release.ps1` 在打 release 前会把客户端壳并入 dist（发布期追加，不是 dist 自身内容）：

| 文件 | 大小 |
| --- | --- |
| `EFTMapDesktop.exe` | 92,160 B |
| `Microsoft.Web.WebView2.Core.dll` | 698,208 B |
| `WebView2Loader.dll` | 194,912 B |

并入后 `dist\EFTMap` = **14238 个文件 / 155.3 MB**。

## 4. 一致性比对：新 dist vs 上一轮已发布包

对照组：`release\EFTMap-Portable-0.1.0.zip`（R47 出品的上一版）解出的 `EFTMap`，**14238 个文件**；
新干净 dist 在并入壳之前 **14235 个文件**。

### 4.1 相对路径集合
| 差异方向 | 数量 | 文件 |
| --- | --- | --- |
| 只在旧包（新 dist 没有） | 3 | `eftmapdesktop.exe`、`microsoft.web.webview2.core.dll`、`webview2loader.dll` |
| 只在新 dist（旧包没有） | **0** | — |

这 3 个正是 `build_release.ps1` 在打 release 时才 `Copy-Item` 进 dist 的客户端壳文件，
属于**发布期追加**，不在 `build.ps1` 的产物范围内。除它们之外，路径集合完全相同。

### 4.2 内容哈希（`.js` / `.css` / `.html` / `.json` / `.py` / `.exe`，共 69 个）
| 结果 | 数量 | 说明 |
| --- | --- | --- |
| SHA256 相同 | 67 | 站点源码、数据、样式、脚本逐字节一致 |
| SHA256 不同 | 2 | 见下 |

两处差异：

1. `_internal\data\roadnet.json`
   - 体积相同（均为 **11399 B**）；
   - **只有顶层 `generatedAt` 时间戳不同**，其余所有键（网格、路点、图结构）逐层比对完全一致；
   - 属构建期重新生成的时间戳，**语义等价**，不是内容回退。
2. `EFTMap.exe`
   - 本轮重建 + `harden_stdio()` 源码改动 → 二进制必然不同；
   - 这是唯一「真实内容差异」，也正是必须重出三件套的原因。

### 4.3 结论
**站点内容与已发布包一致**（唯一差异是 `roadnet.json` 的 `generatedAt` 时间戳，属时间戳类差异）；
但 **`EFTMap.exe` 含本轮 `--help` 修复**，旧包的 exe 不含该修复，因此不能沿用旧 SHA256，
按「内容不一致 → 重出三件套」处理。

## 5. 三件套重出

`powershell -ExecutionPolicy Bypass -File build\build_release.ps1 -SkipBase`

| 产物 | 新体积 | 新 SHA256 | （对照）R47 旧 SHA256 |
| --- | --- | --- | --- |
| `EFTMap-Portable-0.1.0.zip` | 122,537,517 B（116.86 MB） | `78C2D929382369643FFE1D451A2FC9118F26D89D0EC636B09DDCA5C654BE937C` | `5CD0…61AD` |
| `EFTMap-AppWindow-0.1.0.zip` | 122,537,656 B（116.86 MB） | `72566CEE990DF17D0A6C603FE4DCDC857DBC91B414C55AE07111AC12C5142766` | `4573…44D5` |
| `EFTMap-Setup-0.1.0.exe` | 133,394,934 B（127.22 MB） | `F01B11A0EB748FC8BEC4BF96F6650F2C0CB76BB008B4C8FD0479C1157C32D0D2` | `AEF2…853D` |

Portable zip 抽查（共 **14243** 项）：

| 包内路径 | 大小 | 结论 |
| --- | --- | --- |
| `EFTMap\EFTMap.exe` | 2,651,989 B | 与干净 dist 一致 |
| `EFTMap\EFTMapDesktop.exe` | 92,160 B | 在 |
| `EFTMap\Microsoft.Web.WebView2.Core.dll` | 698,208 B | 在 |
| `EFTMap\WebView2Loader.dll` | 194,912 B | 在 |
| `EFTMap\_internal\favicon.ico` | 2,563 B | 在 |
| `EFTMap\_internal\tools\live_prices.py` | 29,410 B | 在 |
| `EFTMap\_internal\tools\installer.py` | 16,710 B | 在 |
| `EFTMap\_internal\wiki-map.js` | 25,314 B | 在 |

## 6. 干净 dist 冒烟（真实 Chrome，不用手工补丁版）

后端：`dist\EFTMap\EFTMap.exe --server-only --port 8796 --config-dir <temp> --runtime-file <temp> --log-file <temp>`
（pid 29896；为复测行情刷新启用 `livePrices` 后重启为 pid 52372）

### 6.1 网络与控制台
| 项目 | 结果 |
| --- | --- |
| 首页加载请求总数 | 239（解析到 238 条 reqid，另 1 条为 `data:` 内联） |
| 非 200/304 | **0** |
| `GET /favicon.ico` | **200** |
| 外部请求（非 `127.0.0.1:8796`） | **0** |
| 控制台 error / warn | **0** |
| 切到 PvE 后请求总数 | 243，非 200/304 = **0** |

上一轮记录的两个已知图标缺口（HK 416A5 RAL 8000、P90 灾厄）在本轮首页加载路径上没有触发，
未用占位图，仍保持上游原样。

### 6.2 页面内容
| 项目 | 结果 |
| --- | --- |
| 地图 | `#map-svg` 存在，SVG 节点 6064 个 |
| 任务数（PvP） | **共 503 个任务** |
| 任务数（PvE） | **共 499 个任务** |
| 模式回写 | `localStorage.eftmap.gameMode = pve` |

截图（`docs/r48-clean-dist/smoke/`）：

- [r48-map.png](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/docs/r48-clean-dist/smoke/r48-map.png)
- [r48-tasks-pvp.png](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/docs/r48-clean-dist/smoke/r48-tasks-pvp.png)
- [r48-tasks-pve.png](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/docs/r48-clean-dist/smoke/r48-tasks-pve.png)

### 6.3 `POST /api/live-prices/refresh`（本轮必须复测项）
默认 `livePrices.enabled=false`，接口按设计返回 **409**（不联网）。临时配置开启后：

- `GET /api/live-prices/status` → `enabled=true`、`fetcher=tools/live_prices.py`；
- `POST /api/live-prices/refresh`（`X-EFTMap-Token` + `{"mode":"regular"}`）→ **HTTP 202**，
  `started=true`、`via=token`、`reason=已在后台启动在线行情更新（regular）`；
- 抓取完成（`live-prices-regular.last-attempt.json`）：
  `status=200`、`bytes=17,345,133`、`count=3541`、
  `sha256=db58e232d9c700c66480de5121b462563b7aab7a315a9d41991c7dd0999e4382`、`at=2026-11-04T06:07:57+08:00`；
- 缓存写盘：`live-prices-regular.json` **466,567 B**，mtime 同步更新到 06:07:57。

结论：**干净重建产物里「刷新行情」链路仍可用**（`--run-tool` + 随包 `tools/live_prices.py` 正常）。

中间踩到一个坑：用 PowerShell 5 的 `Set-Content -Encoding UTF8` 改配置会写入 **BOM**，
Python `json.load` 解析失败后回落默认配置，于是 `enabled` 仍读成 `false`。
改用 `[System.IO.File]::WriteAllText(..., UTF8Encoding($false))` 无 BOM 写入后正常。
这只是测试脚手架的写法问题，不影响产品代码。

## 7. 回归

`python -m pytest tests -q` → **1708 passed, 1 skipped, 0 failed**（99.05 s；后台复跑 114.91 s）。

与 R47 一致：用例总数 1709，无失败。

## 8. 仍存在的问题

1. `8791` 端口被他人 python（pid 31232）长期占用，本轮记录在案、未干预；冒烟改走 8796。
2. 两个上游图标缺口（HK 416A5 RAL 8000、P90 灾厄）仍未修，按规则不使用占位图。
3. PyInstaller 产物**二进制不可复现**：同一份源码重建，exe 字节也会变。因此三件套 SHA256
   只代表「这一次构建」，不能当作源码等价校验；源码等价性请用第 4 节的文件级比对口径。
4. R47 遗留：双击 `Uninstall.exe` 会打开启动器（正规卸载入口正常）。
5. 版本仍为 0.1.0；正式发版建议升 0.2.0（理由见 `r46-package-ledger.md` 第 9 节）。

未做 git 提交。
