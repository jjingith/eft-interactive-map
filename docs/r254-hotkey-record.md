# R254 · 热键改游戏式按键记录 + 强制修饰键（修单键吞键事故）

用户反馈（2026-11-12 15:34）：

> 这个功能的快捷键 你改成和游戏里一样 按按钮然后记录 这样的修改，
> 刚才不小心按到了 a 和 d 中间的按钮 我现在按不了那个键了。

## 一、事故链（已修复）

旧 UI 是**手打文本框**：用户误触把单个键（`\`，用户记成 WASD 里的键）存进
配置 → 宿主 `RegisterHotKey` 把它注册成**无修饰键的全局热键** → 系统级吞掉
那个游戏按键。

- **紧急恢复**：`%APPDATA%\EFTMap\eftmap.config.json` 的 `ocrScan.hotkey` 由
  `'\\'` 改回 `ctrl+alt+p`（生效配置在 APPDATA，BFF/宿主都读它；项目目录下
  那份是旧文件）。宿主重启后该键已释放（15:49:31 热键注册成功）。

## 二、修复

**① UI 游戏式按键记录**（`index.html` / `app.js` / `style.css`）：
- 文本框换成按钮「ctrl+alt+p」；点击 → 按钮变金色脉动「按下新快捷键…（Esc 取消）」
  → `document` 捕获 `keydown` 实时预览修饰键组合（`Ctrl+…`）→ 按下字母/数字/F1-F24
  即记录并保存（`queuePrefs`，宿主 ≤1s 热更新）；`Esc` / 再点按钮 / 失焦取消。
- **单键一律拒绝**：按下无修饰键的键 → 红色提示「须含 Ctrl/Alt/Shift（避免占用
  游戏键）」1.2s 后回到监听态。这是防误触的关键——单键全局热键必然吞游戏按键。
- 键名规范化：`KeyS → s`、`Digit5 → 5`、`F8 → f8`，与 `overlay.parse_hotkey`
  的解析规则完全对应。

**② 宿主兜底**（`tools/scan.py`）：
- 新增 `hotkey_requires_mod(parsed)`；`resolve_hotkey` 对无修饰键配置记日志并
  **回退默认 ctrl+alt+p**（不崩）；两处热更新循环（`watch_native` / legacy）
  解析出单键 → 标记 invalid → 拒绝注册、保留原热键。
- WndProc 的徽章/选单分支套 `try/except + log_exc`：选单链路任何异常不再炸
  消息循环。

## 三、徽章点击「没反应」的排查

- 实机验证（`WindowFromPoint`）：徽章中心屏幕坐标命中的窗口 = labels_hwnd
  （role 0）✓；空白区命中其他窗口（穿透）✓；`hit_badge` 客户坐标命中 ✓。
  原生链路（NCHITTEST → HTCLIENT → WM_LBUTTONDOWN → toggle_menu → open_menu）
  在当前磁盘版本全部通畅。
- **根因**：用户测试时宿主跑的是 15:19:36 启动的**编辑中途版本**（R253 修
  `SW_HIDE` 缺失、重写 `render_menu` 都在那之后）。重启后加载完整代码即正常。
- 若重启后仍无反应：看 `build/scan-host.log` 有无 `[scan] badge click` 异常。

## 四、回归

- 新增 `tests/test_r254_hotkey_record.py` 8 条：`hotkey_requires_mod` / 单键
  配置回退默认 / 两处热更新循环防护 / 前端按钮契约（input 必须移除）/ 记录
  与拒绝逻辑 / 样式。迁移 `test_r241_ocr_settings.py` 的热键 UI 断言。
- 全量：`build/_pytest_r254.xml`。
