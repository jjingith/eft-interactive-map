# R246 修「按截图键先弹 PowerShell，再出截图」

> 用户反馈（2026-11-11 22:34）：
> 「现在截图键按下后会弹出powershell 而后才是截图 麻烦修正」

## 一、原因

R245 为了防止「Edge 单实例把新窗口塞进旧进程」，在**每次冷启动前**调用了一段 PowerShell：

```
powershell -NoProfile -NonInteractive -Command "Get-CimInstance Win32_Process | ... Stop-Process ..."
```

宿主是 `pythonw`（无控制台），启动控制台程序时 Windows 会给它**新建一个控制台窗口**——
所以你按下热键后先看到一个黑色 PowerShell 窗，等 PowerShell 起完（~1 秒）才开始截图。
启动时（登录自启）也会弹一次。

## 二、修复

`kill_scan_browser()`（PowerShell 版）替换为 `kill_stale_scan_browsers()`——**纯 ctypes，
零子进程、零窗口**：

1. `overlay._enum_windows()` 枚举顶层窗口，标题命中 `EFT 截图识别` / `EFT截图·完成` /
   `EFT截图·关闭` 的窗口 → `GetWindowThreadProcessId` 拿到 PID；
2. 再并上 `build/scan-browser.pid`（上次冷启动时写下的浏览器主进程 PID）；
3. `_image_name()` 用 `QueryFullProcessImageNameW` 二次校验**可执行名必须是 msedge.exe /
   chrome.exe**（防 PID 复用误杀无辜进程）；
4. `OpenProcess(PROCESS_TERMINATE)` + `TerminateProcess` 结束主进程（子进程随之退出）；
5. 删除 PID 文件。

实测：无进程可清时 **57ms**（主要是枚举窗口），有进程时同量级 + 250ms 等待句柄释放。
杀进程仍然只针对扫描宿主自己的浏览器，**绝不按映像名扫射**（R240.1 用
`taskkill /IM pythonw.exe` 误杀过 BFF，这条教训保留）。

## 三、验证

- 代码层面：清理路径内不再出现 `powershell` / `subprocess` / `taskkill`（测试固化断言）；
- 运行层面：宿主重启日志 `启动清理：结束旧的扫描浏览器进程 1 个（纯 ctypes，无子进程）`，
  启动耗时同秒完成（旧实现要 1~2 秒）；
- 直接调用 `kill_stale_scan_browsers()` 计时 **57ms**。

> 说明：本轮做交互验证时当前桌面没有前台窗口（`GetForegroundWindow()=0`，会话处于锁定/
> 无交互状态），无法用注入热键复现按键路径；热键链路本身未改动，冷启动前的清理已从
> 「PowerShell 子进程」换成「ctypes 调用」，不会再有窗口弹出。

## 四、测试

`tests/test_r245_scan_wake.py` 中原 `test_kill_scan_browser_only_scoped_to_profile`
改写为 `test_kill_stale_scan_browsers_is_ctypes_only`：

- 必须用 `_enum_windows` + `BROWSER_PID_PATH` 定位进程；
- 必须有 `TerminateProcess` 与可执行名白名单校验；
- 清理代码体内**禁止**出现 `powershell` / `subprocess` / `taskkill`。
