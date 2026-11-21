# R84 · 打包（0.2.0）+ 清单基线 + 三件套 + 新界面冒烟

日期：2026-11-05　版本：`0.2.0`　范围：打包清单、版本号、三件套、冒烟留痕（未 commit）

本轮为界面与流程级重构（四层结构 / XP 素材接入 / 菜单栏迁移 / 游戏版本显示），不是补丁。

> 打包期间另一路又改了 `index.html`、`js/app-menubar.js`、`assets/xp-ui/xp-ui-app.css`
> （顶栏「运行版本」→「游戏版本 1.3.0.48484」，构建号挪进「关于」，860 下缩字号）。
> 按协调要求：第一组三件套**整体丢弃**，并进三个最新文件后重跑回归 + 校验 + 打包，
> 本文所有数字均来自**最后一组**。

---

## 1. 打包清单

### 1.1 新增登记（`build/package_files.ps1` 的 `$RuntimeFiles`）

| 条目 | 说明 |
| --- | --- |
| `js/app-menubar.js` | R80 菜单栏迁移与「游戏版本」读取逻辑；缺它顶栏右侧直接空白 |
| `assets/xp-ui/xp-ui.css`、`xp-ui-app.css`、`manifest.json` | XP 组件层 + 主界面适配层 + 素材清单 |
| `assets/xp-ui/*.png`（**53 张**） | 实际张数为 53（任务书按 28 张估计）；逐条显式登记，防止整目录扫描的路径差异导致丢素材 |
| `assets/icons/zones/zone-eyes.png`、`zone-face-jaw.png` | R79 新增防护区域图标（「眼部」显示依赖 `zone-eyes.png`） |

`assets/` 本来就在 `$RuntimeDirs` 的整目录扫描范围内；这里仍逐条登记，保证「清单 = 运行期真正要加载的文件」可审计。

### 1.2 排除项（`$ExcludePaths`）

| 路径 | 类型 | 理由 |
| --- | --- | --- |
| `assets/xp-ui/demo.html` | Exact | XP 素材组件展示页，`index.html` 不引用，运行期不需要 |
| `assets/xp-ui/_shots/` | Prefix | XP 素材验收截图目录（86 个文件），仅供开发审计 |

### 1.3 双向校验基线（`build\build.ps1 -VerifyOnly`，最终组）

```
完整性校验通过：预期 13300 个文件，staging 实际 13300 个文件，缺失 0，未登记 0。
```

- 基线：**13300 个文件 / 133,496,299 B（127.31 MB）**
- 打包后解压 Portable 复核：
  - `_internal\assets\xp-ui\` 共 **56 个文件** = 53 PNG + `xp-ui.css` + `xp-ui-app.css` + `manifest.json`
  - `demo.html` 不存在、`_shots` 不存在（排除生效）
  - `js\app-menubar.js`、`assets\icons\zones\zone-eyes.png`、`zone-face-jaw.png` 均在包内
  - `_internal\data\game-truth\meta.json` **不在包内**（开发机扫描产物），回退文件
    `_internal\data\game-truth\ammo_ballistic.json` 在包内且 `source.exe_version = 1.3.0.48484`

---

## 2. 版本号

`0.1.0 → 0.2.0`：代码内只有两处硬编码，均已改，并有测试锁死二者一致。

| 文件 | 位置 |
| --- | --- |
| `tools/serve.py` | `VERSION = "0.2.0"` |
| `tools/installer.py` | `VERSION = "0.2.0"`（与 `serve.py` 一致） |

非运行期历史示例（未改）：`docs/STARTUP.md` 提到 `0.1.0`；`tests/test_shot_selftest.py` 里的
`0.1.0` 是 EFT 游戏日志版本，与本项目版本无关。

---

## 3. 回归

```
python -m pytest tests -q
1747 passed, 1 skipped in 98.05s
```

（输出中出现的 Traceback 是负向用例的预期打印，退出码 0。）

---

## 4. 三件套（最终组，`release\`）

> **本表为 R84 组，已作废**（该组早于 R85 小地图缩放修复）。最终三件套、大小与 SHA256 见 **§8.5**。

| 产物 | 字节 | 显示体积 | SHA-256 |
| --- | --- | --- | --- |
| `EFTMap-Setup-0.2.0.exe` | 133,731,122 | 127.54 MB | `D91470FB956D46E9433C1056CD9E258063C7CA9944A5869BF875403AD043761E` |
| `EFTMap-Portable-0.2.0.zip` | 122,878,638 | 117.19 MB | `EEB1F1AA53766B26159D6C530356671646FD9FAF65DFB879D17551F827E688C7` |
| `EFTMap-AppWindow-0.2.0.zip` | 122,878,777 | 117.19 MB | `9BC7A2E4AF15498594124F054F4A23CAB7FF4387FE5D176CA4B7691D7D7AD072` |

PE 子系统：`EFTMap.exe` = GUI(2)、`EFTMapDesktop.exe` = GUI(2)、`EFTMap-Setup-0.2.0.exe` = GUI(2)。

---

## 5. 冒烟（按新界面）

### 5.1 原生壳（`EFTMap.exe` 直接拉起 Portable，`--port 8799`）

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| 无控制台窗口 | PASS：启动前后 `conhost.exe` 新增 **0** | `portable-shell.png` |
| 不开外部浏览器 | PASS：启动前后 `msedge.exe` 新增 **0**（只有 13 个 `msedgewebview2.exe` 运行时进程） | 同上 |
| 桌面壳正常 | PASS：`EFTMapDesktop.exe` 两个可见窗口——主窗口 `1280×720`（EFT 互动地图）、小地图 `208×208`（EFT 小地图） | 同上 |
| 非「兼容模式」 | PASS：标题无「兼容」，WebView2 正常装载 | 同上 |

> 端口用 8799：8787 被另一会话的开发服务器占用（`python tools/serve.py --port 8787`），未杀他人进程。

### 5.2 DOM 冒烟（打包内后端 `EFTMap.exe --server-only --port 8799`，headless Chrome 1440×900）

**26 / 26 通过**，明细见 `evidence/smoke-results.json`。

| 项 | 结果 |
| --- | --- |
| 四层结构 | 菜单栏 **34**、工具条 33、上下文栏 36、状态栏 24，均可见 |
| 菜单能开 | 「文件」展开，`aria-expanded=true`，2 个菜单项 |
| 右上角游戏版本 | `游戏版本 1.3.0.48484`（不是 `R19.35-…`）；悬停 title = `游戏版本 1.3.0.48484 · 来源 data/game-truth/ammo_ballistic.json（source.exe_version，本地 EFT 客户端文件版本） · 数据日期 2026-11-04 12:57:38` |
| 状态栏游戏版本 | `游戏版本 1.3.0.48484`（同步） |
| 关于页构建号 | `构建版本：R19.35-be7a3762（仅用于排查；右上角与状态栏显示游戏版本）`（R85 重打包后复核） |
| 视图切换 | 任务 / 弹药 / 配装 / 地图，`aria-selected=true`，状态栏分别「视图：任务 / 弹药 / 配装 / 地图」，上下文栏始终可见 |
| 切视图后小地图仍是地图 | 四个视图下 `#map-view svg` 均存在；独立打开 `?mini=1` 页时 `#map-svg` 加载完成：`viewBox=-1537.11 0 3679.55 831.58`、**951 条 path**（底图确实在画） |
| 小地图独立窗口（壳） | 主窗口停在「配装」时，第二个窗口仍按 `?mini=1&…` 强制地图视图；R85 起无玩家位置时按 zoom 收缩、以地图几何中心为锚，不再固定整图总览 |
| 小地图缩放·解锁（滚轮） | `210%`（滚轮上滚 +10%；基线 200% 来自持久化配置） |
| 小地图缩放·锁定（热键入口） | `window.__tkMiniZoom(1)` → 返回值 2.2、徽标 `220%`（壳 `RegisterHotKey` → `ExecuteScriptAsync("window.__tkMiniZoom(...)")` 同一入口，`tools/host/src/MiniHost.cs:862`） |
| 任务栏行 | 54 行，首行宽 313 px（可见） |
| 单条开关 | `checked true → false`，行 `is-off` 同步为 true |
| 四档筛选 | 全部 54 / 未完成 54 / 已完成 0 / 可并行 44，`#task-count` 同步 |
| 右键「任务详细」 | 菜单可见，项文本「任务详细」、`disabled=false` |
| 右键跳转 | `#tasks:6391359b9444fb141f4e6ee6`，状态栏「视图：任务」 |
| 配装 6B34 眼部 | 眼镜槽候选表 1 行，`img alt="眼部"` 命中（`zone-eyes.png`） |
| console error | 0 |

证据：`evidence/portable-shell.png`、`portable-minimap.png`、`mini-208-headless.png`、`smoke-menu-open.png`、
`smoke-mini-zoom.png`、`smoke-tasks.png`、`smoke-task-context.png`、`smoke-loadout-glasses.png`、
`smoke-results.json`。

壳日志（`%LOCALAPPDATA%\EFTMap\logs\desktop.log`）关键行：

```
21:44:31.238  资源 HTTP 404：http://127.0.0.1:8799/data/game-truth/meta.json
21:44:31.303  主页面加载完成
21:44:30.788  小地图窗口已创建…url=…?mini=1&…&zoom=1.4
```

`meta.json` 404 是设计内路径：该文件只在开发机扫描时存在，包内回退到
`ammo_ballistic.json` 的同一字段，因此右上角仍显示 `1.3.0.48484`（不是「游戏版本 —」）。

---

## 6. 已知残留

1. **OS 级热键真实按键注入未做**：验证到「壳调用链（静态）+ JS 入口实际生效」两层；
   `RegisterHotKey` 的实际按键事件需要真实桌面会话注入，冒烟环境未注入。
2. **端口 8787 被占**：本轮壳冒烟改用 8799，属环境问题，不是产物问题。
3. **小地图缩放基线会沿用配置**：冒烟从上次会话保存的 `130%` 起算，因此数值是 `140% → 150%`，
   断言按「相对变化」判定，不锁定绝对值；壳日志里的 `zoom=1.4` 也来自同一份配置。
   ~~另外无玩家坐标时 `applyMiniView` 会提前返回（`app.js:6158`），所以这两次验证覆盖的是
   「入口 + 徽标数值 + 配置持久化」，viewBox 不变；有游戏内坐标时才会按 `meters/zoom` 重算视野。~~
   **R85 已修复**：无坐标不再提前返回，四档缩放的 viewBox 均真实变化；见 §8。
4. **小地图无玩家位置时是整图总览**：`follow=1` 但没有游戏内坐标，回退到整图 fit-all，
   208×208 下标记非常密（`portable-minimap.png` / `mini-208-headless.png`）；属既有回退逻辑，
   不是本轮布局改动引入，底图 path 951 条确认在画。
   **R85 起改为按 zoom 收缩、锚点地图几何中心**：仍无坐标时不再保持整图总览，
   但 100% 视野由 `mini.meters` 决定（见 §8.2 A），不是「假的缩放反馈」。
5. 首轮三件套（早于最新三个 UI 文件）已按协调要求丢弃，未留存哈希，不作为结论。

---

## 7. 机器标签

```
tag=r84
date=2026-11-05
version=0.2.0
manifest_expected=13300
manifest_actual=13300
manifest_missing=0
manifest_unregistered=0
manifest_bytes=133496299
pytest=1747passed_1skipped
setup_bytes=133731122
setup_sha256=D91470FB956D46E9433C1056CD9E258063C7CA9944A5869BF875403AD043761E
portable_bytes=122878638
portable_sha256=EEB1F1AA53766B26159D6C530356671646FD9FAF65DFB879D17551F827E688C7
appwindow_bytes=122878777
appwindow_sha256=9BC7A2E4AF15498594124F054F4A23CAB7FF4387FE5D176CA4B7691D7D7AD072
pe_subsystem=gui2
smoke_native=pass
smoke_dom=26/26
game_version=1.3.0.48484
game_version_source=data/game-truth/ammo_ballistic.json
commit=false
```

---

## 8. R85 · 小地图缩放修复 + 重打包（最终组）

### 8.1 问题与修法

**问题**：无玩家坐标时 `applyMiniView` 在 `!state.player` 处提前返回。小地图停在整图总览，
缩放只改徽标与配置，`viewBox` 不动 —— 用户看到「缩了但画面没动」的假反馈。
另外初始 `state.baseVb = [0,0,1,1]` 会让「底图尚未注入」被误判成几何可用。

| 修改 | 说明 |
| --- | --- |
| `app.js` `applyMiniView` | 不再因 `!state.player` 提前返回；几何可用时照常按 `meters/zoom` 收缩 `viewBox` |
| `app.js` `miniAnchor()` | 锚点优先「当前图内的玩家」→「最近一次已知位置」→「当前地图 `baseVb` 几何中心」；跨图坐标一律不采用 |
| `app.js` `miniGeometryReady()` | 只有 `state.map` + `mapSvgReady` + `baseVb` + 有效 `fit` + 有效画布尺寸同时成立才算可用 |
| `app.js` `state.mapSvgReady` | `selectMap` 开始时置 `false`，底图 SVG 注入完成（`buildSvg`）后置 `true`；底图失败时保持 `false` |
| `app.js` `state.lastPlayer` | 定位回包成功时缓存；定位帧暂空时仍能作为锚点 |
| `app.js` `setMiniZoom` | 几何不可用不显示百分比，改挂「等待定位」；几何可用时行为不变 |
| `app.js` `#mini-geo-badge` | 小地图新增「等待定位」状态；与百分比徽标互斥显示 |
| `style.css` | `body.tk-mini #mini-geo-badge` 样式，仍全部限定在 mini 作用域内 |
| `tests/test_r32_minimap.py` | 更新为 R85 断言：不再要求越界时提前 `applyView`，改为校验锚点只在当前图内取坐标 |

有坐标时的玩家锚路径保持原样（`miniAnchor` 返回玩家点 → `centerOnPoint`，与 R78 的
`centerOnPlayer` 等价）。

### 8.2 验证（打包内后端 `EFTMap.exe --server-only --port 8792`，headless Chrome 208×208）

用注入脚本替换 `/api/position`（返回空）、并把底图请求置为失败，模拟两种状态。

**A. 无坐标：四档缩放（Customs，506 条 path）**

| zoom | `viewBox` | 宽 | 百分比徽标 | 等待定位 |
| --- | --- | --- | --- | --- |
| 0.5× | `382.295 116.004 297.892 297.892` | 297.892 | `50%` 可见 | 隐藏 |
| 1× | `456.768 190.477 148.946 148.946` | 148.946 | `100%` 可见 | 隐藏 |
| 2× | `494.005 227.714 74.473 74.473` | 74.473 | `200%` 可见 | 隐藏 |
| 3× | `506.417 240.126 49.649 49.649` | 49.649 | `300%` 可见 | 隐藏 |

- `vbChanged=true`、`widthShrinks=true`：四档 `viewBox` 全部不同且随 zoom 单调收缩。
- 四档中心恒为 `(531.241, 264.950)` = 当前地图几何中心；缩放是真实的矢量收缩。
- 证据：`r85-nopos-0.5x.png` / `r85-nopos-1x.png` / `r85-nopos-2x.png` / `r85-nopos-3x.png`。

**B. 恢复坐标：R78 玩家锚回归**

合成定位 `(x=34.6, z=-7.8)`（Customs 图内），四档下玩家标记的屏幕坐标：

| zoom | 玩家标记屏幕坐标 | `viewBox` |
| --- | --- | --- |
| 0.5× | (104, 104) | `509.793 145.400 297.892 297.892` |
| 1× | (104, 104) | `584.266 219.873 148.946 148.946` |
| 2× | (104, 104) | `621.503 257.109 74.473 74.473` |
| 3× | (104, 104) | `633.915 269.521 49.649 49.649` |

- `maxJitter=0`：跨倍率完全稳定，R78 的「玩家标记像素位置不随倍率漂移」未被改坏。
- 绝对值为 (104,104) 是因为本次 stage 为无内边距的 208×208（中心即 104）；R78 的约 (100,103)
  来自带内边距的窗口，判据是「跨倍率稳定」，不是固定绝对值。
- 证据：`r85-player-anchor.png`。

**C. 底图未加载 + 等待定位**

| 项 | 结果 |
| --- | --- |
| 底图请求 | 模拟失败，`#error` 显示，path 0 |
| 状态徽标 | `等待定位` 可见（`opacity=1`） |
| 百分比徽标 | 隐藏（`opacity=0`，文本为空） |
| 缩放尝试 | `__tkMiniZoom` 返回 2.0 但 `viewBox` 仍为 `null`（未发生任何视觉变化） |

即：拿不到地图几何时不给任何「已缩放」的假反馈。证据：`r85-waiting-no-basemap.png`。

机器可读结果：`evidence/r85-mini-zoom.json`（console error 0）。

**D. 全量 DOM 冒烟复核（最终三件套同源后端）**

```
SUMMARY: 26/26 passed
```

覆盖四层结构、菜单、视图切换、游戏版本 `1.3.0.48484` + 来源、任务栏开关/四档筛选/右键跳转、
配装 6B34「眼部」、小地图滚轮与热键入口（`210% → 220%`，构建号 `R19.35-be7a3762`）。
证据：`evidence/smoke-results.json`（已按最终包覆盖）。

### 8.3 回归

```
python -m pytest tests -q
1747 passed, 1 skipped
```

### 8.4 清单基线（重打包后）

```
完整性校验通过：预期 13300 个文件，staging 实际 13300 个文件，缺失 0，未登记 0。
```

- **13300 个文件 / 133,501,224 B（127.31 MB）**
- 相比 R84 组的 `133,496,299 B` 增加 **4,925 B**，全部来自 `app.js` / `style.css` 的修复与
  `#mini-geo-badge` 样式；文件数与登记表未变。

### 8.5 三件套（最终组，`release\`）

| 产物 | 字节 | 显示体积 | SHA-256 |
| --- | --- | --- | --- |
| `EFTMap-Setup-0.2.0.exe` | 133,734,064 | 127.54 MB | `96E395CC065ABDA6616F04B8E4E1566F27DCCA641E1F0A7866B87EAC676B1E5A` |
| `EFTMap-Portable-0.2.0.zip` | 122,880,770 | 117.19 MB | `69595B9DCFB383E39C8CFED311B31E0DE5CBE0F1893EC49389D5500F2CE87888` |
| `EFTMap-AppWindow-0.2.0.zip` | 122,880,909 | 117.19 MB | `8874696AD184B096E529003A8847DE3390CB1E4DC3BE9AEAA5055445590F2200` |

`EFTMap.exe` / `EFTMapDesktop.exe` NE 子系统仍为 GUI(2)，与 R84 一致。
R84 组（§4）的九个哈希全部作废，不作为结论。

### 8.6 残留状态

- 第 3 条（无坐标时缩放是假反馈）：**已修复**，见 §8.1–8.2。
- 第 4 条（无坐标时整图总览）：行为已变——无坐标时按 zoom 收缩、锚点地图几何中心，
  不再停留在整图总览；100% 视野由 `mini.meters` 决定。
- 第 1 条（OS 级热键真实按键注入）与第 2 条（端口占用）状态不变。

### 8.7 机器标签

```
tag=r85
date=2026-11-05
version=0.2.0
base_tag=r84
manifest_expected=13300
manifest_actual=13300
manifest_missing=0
manifest_unregistered=0
manifest_bytes=133501224
pytest=1747passed_1skipped
setup_bytes=133734064
setup_sha256=96E395CC065ABDA6616F04B8E4E1566F27DCCA641E1F0A7866B87EAC676B1E5A
portable_bytes=122880770
portable_sha256=69595B9DCFB383E39C8CFED311B31E0DE5CBE0F1893EC49389D5500F2CE87888
appwindow_bytes=122880909
appwindow_sha256=8874696AD184B096E529003A8847DE3390CB1E4DC3BE9AEAA5055445590F2200
pe_subsystem=gui2
minimap_nopos_viewbox_changed=true
minimap_player_anchor=stable_104_104_jitter0
minimap_waiting_state=no_percent_badge_viewbox_unchanged
smoke_dom=26/26
game_version=1.3.0.48484
game_version_source=data/game-truth/ammo_ballistic.json
commit=false
```
