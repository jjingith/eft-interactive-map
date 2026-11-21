# R34 地图界面改造 ledger

host=HOMONAS user=MASTERJJ at=2026-11-03T14:32:10+08:00 round=R34-mapui

> 本工作区为局域网共享目录。本文件记录本轮「移除卫星入口 / 矢量图与官方 Wiki 合并下拉 /
> 官方 Wiki 图层复用矢量图分组」的改动范围、哈希、映射表、验证结果与遗留问题。
> 本轮未执行 git 提交，未改动 `release/`、`dist/`。
>
> **后续轮次入口：R41「任务页复刻 db4tarkov + 商人英文名 / 游戏内头像」详见
> [`docs/r41-tasks-redesign-ledger.md`](r41-tasks-redesign-ledger.md)。**
> R41 只改前端（`tasks.js` / `tasks.css` / `data/tasks/traders.json` / 新增测试），
> 未触碰本文件记录的 R34 地图入口改造。

## 1. 改动文件与 SHA256

| 文件 | SHA256 |
|---|---|
| `index.html` | `E088D476AFD1FB7501C57EB6CA65DECDE588D082555A0F225F11065D5EB807F8` |
| `app.js` | `C6BA67B5C5EE2B005D613DD2B26D3E27E3B62275518547A429E4CB1BB2B44915` |
| `wiki-map.js` | `16E782C04CA0F204FCED94CAD4FEE249074552EB93E2BFEE0C6CE75033BE97B5` |
| `style.css` | `67D28D473380B159B365A920AD1AC6386EE5916247E8DC7DA837BDC022C2EDB2` |
| `README.md` | `0274ED11BB987B13CA00629508A92FC664BADA9DEB47AC1A0CF15A2247D6DE33` |
| `tools/serve.py` | `41224C3B812094933DCE6A015381C4CD0A84E827D16A07916392AD149C167B00` |

版本串：`app.js` 的 `AM_BUILD` 与 `index.html` 全部 `?v=` 同步到 `R19.31`；
`tools/serve.py` 的 `/api/build` rev 同步为 `R19.31-<digest>`。运行期 `VERSION` 仍为 `0.1.0`。

## 2. 卫星图入口移除

- `index.html` 删除了 `#base-mode-satellite` 按钮，以及原来的三个 `.base-mode-btn`
  并列按钮；地图区现在只有一个底图下拉（见 §3）。
- `wiki-map.js` 删除了卫星入口相关编排：`fallbackSatellite`、`enableSatellite`、
  `refreshSatelliteAvailability`、`btnSatellite` 引用、`gwmap:satellite-fail` 监听。
  旧 localStorage `eftmap.baseMode="satellite"` 在启动时回落 `vector` 并清掉该值。
- **保留** `app.js` 的卫星数据与渲染能力：`state.satelliteMode`、`loadSatelliteData()`、
  `applySatellite()`、`setSatelliteMode()`、`window.GWMapSatellite` 未删除；
  `data/satellite.json`、`assets/satellite/`、`tools/build_satellite_maps.py` 未动。
- 没有卫星快捷键（全库没有对应 keydown 绑定），因此无需删除快捷键；只清理了入口文案。
- `README.md` 的底图模式说明改为「矢量图 / 官方 Wiki」下拉，并注明卫星数据与渲染能力保留。

## 3. 矢量图 / 官方 Wiki 合并下拉

实现位置：

- `index.html`：`#base-mode`（`#base-mode-trigger` + `#base-mode-menu` + 两个
  `.base-mode-option`），触发器复用 `.map-select` 外观。
- `style.css`：`.base-mode` / `.base-mode-trigger` / `.base-mode-menu` /
  `.base-mode-option`，沿用 XP 边框、文字与选中色令牌，未引入第三方库/CDN。
- `wiki-map.js`：`setMenuOpen()`、`setMode()`、`bind()`。点击触发器展开，点击选项切换，
  点击外部或 `Esc` 收起；`ArrowDown` / `ArrowUp` 打开并把焦点移到当前选项，
  菜单内上下键循环移动焦点。`localStorage` 键名与取值仍为 `eftmap.baseMode`
  （`vector` / `wiki`），默认 `vector`。
- 视图 / 缩放行为未改：仍调用原有的 `ensureMap()`、`applyView()`、`resetView()`；
  `#viewport` / `#wiki-panel` 的显隐、`body.wiki-base`、楼层过滤逻辑保持原状。

## 4. 官方 Wiki 复用矢量图分组

### 4.1 矢量图数据源与渲染方式（调查结论）

- 分组定义：`app.js` 的 `LAYER_SPEC`（8 组：撤离点 / 转移点、物资、赛季文件（通行证）、
  任务 / 剧情、出生点、钥匙与门、危险区域、其他）。每项有 `key` / `label` /
  `kind` / `where` / `dot` / `icon` / `badge`。
- 分组顺序 = `LAYER_SPEC` 数组顺序；UI 用 `.toggle-group` 标题 + `.legend-item` 行
  （勾选框 + 图标 + 名称 + 右侧计数），没有「分组折叠」交互（矢量图也是静态标题）。
- 颜色/图标：`legendIcon(spec)` 生成，撤离点用徽章、容器用物资小图标、其余用色点或 PNG。
- 筛选：`state.layers[key]` + `where(item)`；计零的图层整行不显示；关闭的行加
  `data-on="false"` 压暗。楼层过滤与缩放逻辑不在此列。

### 4.2 复用方式

- `app.js` 新增 `window.GWMapLayerSpec = { groups: LAYER_SPEC, icon: legendIcon }`，
  只暴露定义与图标生成器，不改渲染核心。
- `wiki-map.js` 的 `vectorSpecs()` 读取该定义，`renderPanel()` 按同一 `LAYER_SPEC`
  顺序生成 `.toggle-group` / `.toggle.legend-item` 行；映射到矢量 item 的行直接使用
  矢量 label 与 `legendIcon()`，没有矢量对应的分类使用官方分类名与官方图标。
- 官方分类计数为 0 的行与矢量图一致：不显示。
- 筛选仍走 `state.cats[categoryId]` + `applyFilter()`；关闭行同样压暗。
  「全选 / 全不选」与搜索沿用原逻辑。

### 4.3 Wiki → 矢量 item 映射表（`WIKI_TO_VECTOR`，一对一）

| 官方 category.id | 矢量 LAYER_SPEC item.key | 说明 |
|---|---|---|
| `exfil_pmc` | `extract_pmc` | PMC 撤离点 |
| `exfil_scav` | `extract_scav` | Scav 撤离点 |
| `exfil_transit` | `transits` | 转移点 |
| `container_safe` | `container_safe` | 保险箱 |
| `container_jacket` | `container_jacket` | 夹克衫 |
| `container_pc` | `container_pcblock` | 电脑 → 机箱 |
| `container_dead` | `container_scavbody` | 尸体 → Scav尸体 |
| `container_drawer` | `container_drawer` | 抽屉 |
| `container_duffle` | `container_duffle` | 运动包 → 旅行包 |
| `container_stash` | `container_cache` | 彩蛋点 |
| `container_medical` | `container_med` | 医疗物资 |
| `container_crate` | `container_supply` | 物资箱 |
| `container_suitcase` | `container_suitcase` | 手提箱 |
| `container_tool` | `container_toolbox` | 工具箱 |
| `container_cash` | `container_register` | 收银机 |
| `container_grenade` | `container_grenade` | 手雷箱 |
| `container_weapon` | `container_weapon` | 武器箱 |
| `loot_loose` | `loose` | 散落物资 |
| `spawn_pmc` | `spawn_pmc` | AI PMC 出生点 |
| `spawn_scav` | `spawn_scav` | Scav 出生点 |
| `spawn_sniper` | `spawn_sniper` | 狙击手 |
| `spawn_boss` | `bosses` | Boss 刷新点 |
| `locked` | `locks_door` | 上锁的门 |
| `stationarygun` | `stationary` | 固定武器 |

映射是一对一；若未来出现多对一，需要合并计数与勾选，不能直接叠两行同名（代码注释已写明）。

### 4.4 无矢量对应、但保留在最近分组里的官方分类（`WIKI_EXTRA`）

这些分类在 `LAYER_SPEC` 中没有同名 item，不能硬塞进不相关的矢量开关；本轮按最接近的
矢量分组展示，行名与图标使用官方原始数据：

| 官方 category.id | 放置分组 | 行名 |
|---|---|---|
| `container_ammo` | 物资 | 弹药箱 |
| `container_medcase` | 物资 | 医疗箱 |
| `container_greencrate` | 物资 | 木箱 |
| `loot_key` | 钥匙与门 | 钥匙刷新点 |
| `loot_keycard` | 钥匙与门 | 钥匙卡刷新点 |
| `lever` | 钥匙与门 | 拉杆 / 按钮 |
| `spawn_cultist` | 出生点 | 邪教徒 |
| `spawn_rogueraider` | 出生点 | 黑卫队 |
| `quest` | 其他 | 电力面板 |

未登记的新分类会落到「官方 Wiki 其他分类（未映射）」兜底组，不静默丢点。

### 4.5 反向缺口（矢量图有、官方 Wiki 数据没有）

以下矢量分组 / 开关在官方 Wiki 数据里没有对应分类，因此 Wiki 模式下整组为空、不显示
（与矢量图「0 计数整行隐藏」一致）：

- 高级资源点 `valuables` / 9 个子类、物资容器兜底 `container_misc`
- 赛季文件 `documents` / 8 个子类
- 任务地点 `tasks`、剧情地点 `stories`
- 共用撤离点 `extract_shared`、汽车后备箱 `locks_trunk`
- 玩家出生点 `spawn_player`
- 雷区 / 危险区 `hazards`、炮击区 `artillery`
- BTR `btr`、地名标注 `labels`

本轮没有为这些缺口伪造 Wiki 数据，也没有把它们塞进别的分组。

## 5. 验证

### 5.1 静态检查

- `node --check app.js`：通过。
- `node --check wiki-map.js`：通过。
- ES5 扫描：`app.js` 与 `wiki-map.js` 均无 `let` / `const` / 箭头函数；
  `wiki-map.js` 无反引号。`app.js` 的反引号仅出现在既有注释与 5 行双引号字符串字面量中，
  不是模板字符串表达式；本轮新增代码全部为 ES5。

### 5.2 测试

- `python -m pytest tests -q`：**5 failed, 1620 passed, 1 skipped**。
- 5 个失败均为既有失败，全部在配枪 / 布局模块，与本轮地图 UI 文件无关：
  - `tests/test_r19_11_round.py::test_hide_incompat_filters_without_touching_data`
  - `tests/test_r19_13_round.py::test_row2_anchors_are_driven_by_real_slot_tree`
  - `tests/test_r19_1_round.py::test_candidate_columns_match_reference_order`
  - `tests/test_r19_5_round.py::test_zoning_is_generic_semantic_rules`
  - `tests/test_r6_gun_workbench.py::test_gun_workbench_business_logic`
- 本轮曾因 `AM_BUILD` 升到 R19.31 触发 15 个「资源版本串未同步」失败；
  已把 `index.html` 全部 `?v=` 与 `serve.py` rev 同步到 R19.31，相关测试全部恢复通过。

### 5.3 真实 Chrome 行为验证

页面：`http://127.0.0.1:8791/`，真实 Chrome（CDP），构建标记 `R19.31-ff8648cf`。

- 底图下拉：默认 `矢量图`；点击展开显示「矢量图 / 官方 Wiki」；选中项蓝色高亮；
  点击外部 / `Esc` 收起；`ArrowDown` / `ArrowUp` 打开并聚焦当前选项（JS 键盘事件验证）。
- 模式切换：矢量图 ↔ 官方 Wiki 正常；Wiki 侧栏显示分组面板；缩放/复位按钮可用。
- Wiki 分组：海关（customs）下渲染 5 组 / 28 行：
  `撤离点 / 转移点`、`物资`、`出生点`、`钥匙与门`、`其他`；
  计数与官方 `wiki-maps.json` 一致（517 个标点全部可见）。
- 筛选交互：
  - 关闭 `container_safe`：`container_safe` 可见标记 7 → 0，行 `data-on=false`；
  - 「全不选」：可见标记 0，28 行全部 `data-on=false`；
  - 「全选」：可见标记 517，28 行全部 `data-on=true`。
- 矢量图侧栏未被破坏：`#layer-toggles` 仍为 8 组 / 42 行。

### 5.4 截图

目录：`docs/r34-mapui/shots/`，均为真实 Chrome 视口截图（deviceScaleFactor=1）。

| 文件 | 尺寸 | 内容 |
|---|---|---|
| `1024-dropdown-open.png` | 1024×900 | 下拉展开，矢量图高亮，两个选项可见 |
| `1024-vector.png` | 1024×900 | 矢量图选中，下拉收起，矢量图层面板可见 |
| `1024-wiki.png` | 1024×900 | 官方 Wiki 选中，分组面板上半部分 |
| `1024-wiki-groups-bottom.png` | 1024×900 | 同一面板滚动到底：出生点 / 钥匙与门 / 其他 |
| `1440-dropdown-open.png` | 1440×900 | 下拉展开，矢量图高亮，两个选项可见 |
| `1440-vector.png` | 1440×900 | 矢量图选中，下拉收起 |
| `1440-wiki.png` | 1440×900 | 官方 Wiki 选中，分组面板上半部分 |
| `1440-wiki-groups-bottom.png` | 1440×900 | 同一面板滚动到底：出生点 / 钥匙与门 / 其他 |

截图 SHA256：见本轮验收输出；文件均在上述目录，未提交 git。

## 6. 遗留问题 / 限制

1. 5 个全量 pytest 失败为既有配枪 / 布局问题，本轮未修改相关代码，也未弱化测试。
2. 官方 Wiki 数据没有赛季文件、任务/剧情、危险区、BTR、地名标注、高级资源点等分类；
   这些矢量图分组在 Wiki 模式为空组（不显示），不是本轮漏做。
3. 官方 Wiki 新增但未登记的分类会进入「官方 Wiki 其他分类（未映射）」兜底组；
   上线前若上游新增分类，建议补进 `WIKI_TO_VECTOR` 或 `WIKI_EXTRA`。
4. 自绘下拉覆盖了点击 / 外部点击 / `Esc` / 上下键 / Enter；没有原生 select 的首字母
   快速跳转（type-ahead），本轮未实现。
5. 计数为 0 的官方分类与矢量图一样不显示；若未来需要「显示空分类」，需另加开关。

## 7. 本轮产生 / 追加的文件

- `index.html`、`app.js`、`wiki-map.js`、`style.css`、`README.md`、`tools/serve.py`（改动）
- `docs/r34-mapui/shots/*.png`（8 张验证截图）
- `docs/r34-mapui-ledger.md`（本文件）
- 未 git 提交；未改 `release/`、`dist/`。

---

# 追加：双击 `启动项目.bat` 仍是旧界面的根因与修复

host=HOMONAS user=MASTERJJ at=2026-11-03T18:34:39+08:00 round=R34-bat-fix

## 8. 现象与根因

现象：双击项目根目录 `启动项目.bat` 后，浏览器打开 8787，看到的仍是
「矢量图 / 卫星图 / 官方 Wiki」三个并列按钮的旧界面。

根因链（**不是浏览器缓存**）：

1. 端口 8787 已被**打包版** `dist\EFTMap\EFTMap.exe`（PID 50104，启动于打包验收阶段）
   占用，且该进程一直没退出。
2. 旧版 bat 的「端口已被监听」分支只打印提示并 `start "" "http://127.0.0.1:8787/"`
   ——**不检查占用者是谁**，于是把浏览器交给了旧打包版。
3. 该进程 `/api/build` 返回：`root = dist\EFTMap\_internal`、`rev = R19.30-1a2b3132`、
   `cwd = dist\EFTMap`。其 `index.html`（2026-11-03 10:22:26，54,040 B，
   SHA256 `5CC65197CA96C1D8EF6A0A067B3A8FCCF103DDD3771A355AE4CF3D0518F42C79`）
   里仍是 `#base-mode-vector` / `#base-mode-satellite` / `#base-mode-wiki`
   三个 `.base-mode-btn`（10:21–10:22 的旧构建，早于本轮 13:46–14:30 的改动）。
4. 源码目录的 `index.html`（2026-11-03 14:23:53，54,101 B，
   SHA256 `E088D476AFD1FB7501C57EB6CA65DECDE588D082555A0F225F11065D5EB807F8`）
   才是 `#base-mode-trigger` 下拉。

缓存排查结论：`tools/serve.py` 的 `end_headers()` 对静态文件已发
`Cache-Control: no-store, must-revalidate` + `Pragma: no-cache`；实测
`GET http://127.0.0.1:8787/index.html` 响应头确实带这两个头，且页面资源全部是
`?v=r19.31`（16 处，`v=r19.30` 为 0 处）。因此缓存不是原因，根因是**端口被旧打包版抢占**。

## 9. `启动项目.bat` 原内容与新内容

### 9.1 原内容（2026-10-24 13:06:56，3,539 B，GBK/CRLF）

该文件不在 git 索引里（untracked），无法取 HEAD 版本哈希，以下为原文关键逻辑：

```bat
@echo off
chcp 936 >nul
cd /d "%~dp0"
set "PORT=%~1"
if not defined PORT set "PORT=8787"
rem ... 找 py -3 / python ...
%PY% -c "...connect_ex(('127.0.0.1',%PORT%))..."
if errorlevel 1 goto port_free
echo [3/3] 端口 %PORT% 已经有服务在监听。
echo       不会启动第二个服务，直接帮你打开浏览器：
start "" "http://127.0.0.1:%PORT%/"
exit /b 0
:port_free
%PY% "tools\serve.py" --port %PORT%
```

问题点：只判断「端口有没有人监听」，不判断监听者托管的是哪个目录；
帮助文案还写着早就过期的「页面顶部应显示构建标记：R18.1」。

### 9.2 新内容（2026-11-03 18:2x，6,057 B，GBK/CRLF）

SHA256：`F62AFF61A87DDC5F0AE6FFD8B1AC155A397AA18099CB458D4E91A50AC5CD0201`

- **默认仍是源码版**：`%PY% "tools\serve.py" --port %PORT%`，`cd /d "%~dp0"` 保证
  服务根目录就是本仓库（`serve.py` 的 `ROOT` = 仓库根目录）。
- 参数：
  - 双击 / `启动项目.bat` → 源码版 8787
  - `启动项目.bat 8788` → 源码版 8788
  - `启动项目.bat source 8790` → 源码版 8790
  - `启动项目.bat dist [端口]` → **显式**启动打包版 `dist\EFTMap\EFTMap.exe --port %PORT%`
- 端口已监听时**先核对占用者身份**：请求 `http://127.0.0.1:%PORT%/api/build`，
  取 `root` 与 `%CD%` 做 `normcase(abspath())` 比较：
  - 相同（本仓库源码服务）→ 不重复启动，只打开浏览器；
  - 不同或 `/api/build` 不可解析（例如旧打包版、别的 http.server）→ 判定为「外来占用」，
    自动在 8788–8795 里挑第一个空闲端口，用**源码版**启动并让 `serve.py` 打开该端口页面，
    同时在窗口里明确说明「8787 被旧打包版占用，已改用源码端口」。
- 旧版 `[3/3]` 三步提示改为 `[1/4]`…`[3/4]` 四步；Python 依赖检查逻辑原样保留。
- 「打包版」分支同样是显式的：`启动项目.bat dist` 只启动 `dist\EFTMap\EFTMap.exe`，
  不会回落到源码服务；找不到 `dist\EFTMap\EFTMap.exe` 时以返回码 4 明确报错。

## 10. 修复后按真实操作路径复现

### 10.1 现场清理

- 停掉占用 8787 的旧打包版进程：`Stop-Process -Id 50104`（旧 `dist\EFTMap\EFTMap.exe`）。
  仅结束进程，**未改 `dist/` 任何文件**：`dist\EFTMap\_internal\index.html` 仍是
  10:22:26 / `5CC65197…`，`EFTMap.exe` mtime 仍是 10:20:59。

### 10.2 双击等效启动

用 PowerShell 直接执行 `启动项目.bat`（等价于双击，`run_in_background`），
`serve.py` 在 8787 就绪后 `/api/build` 返回：

```json
{"rev": "R19.31-ff8648cf", "pid": 44712,
 "cwd": "D:\\personal\\trae\\02-塔科夫\\eft-interactive-map",
 "root": "D:\\personal\\trae\\02-塔科夫\\eft-interactive-map"}
```

- 实际服务文件（源码目录，非 dist）：
  - `index.html` 54,101 B / `E088D476…`
  - `style.css` 263,873 B / `67D28D47…`
  - `app.js` 1,123,377 B / `C6BA67B5…`
  - `wiki-map.js` 25,074 B / `16E782C0…`
- `GET /index.html`：`200`，`Cache-Control: no-store, must-revalidate`，`Pragma: no-cache`；
  页面含 `base-mode-trigger`（True）、`base-mode-satellite`（False）、`.base-mode-btn`（0 个）。
- `GET /wiki-map.js` 含 `WIKI_TO_VECTOR`（True），25,074 B。
- 页面 `meta[name=build-rev]` = `R19.31-ff8648cf`，与 `/api/build` 一致。
- 端口判定脚本实测：对 8787（本仓库源码）退出码 0；对临时外来 `python -m http.server`
  （8792，无 `/api/build` → 404）退出码 1，会走外来占用分支。

### 10.3 真实 Chrome 截图（同 URL `http://127.0.0.1:8787/`）

真实 Chrome（CDP，`deviceScaleFactor=1`），构建标记 `R19.31-ff8648cf`。

| 文件 | 尺寸 | 体积 | SHA256 | 内容 |
|---|---|---|---|---|
| `docs/r34-mapui/shots/bat-1024-dropdown-open.png` | 1024×900 | 472,763 B | `E0E947F5C11BA8B3F432C5DA75DE95241A5A5163887492C23A88660A8DE831F8` | 下拉展开，`矢量图` 蓝色高亮，`官方 Wiki` 可见，无卫星按钮 |
| `docs/r34-mapui/shots/bat-1024-wiki.png` | 1024×900 | 481,522 B | `4DD10C193BA663ED58F42A973CD7E72C4A6041848DED54B6C1A6B456B1B7D4E3` | `官方 Wiki` 选中，左侧按矢量图同款分组，街区底图 + 604 标点已渲染 |
| `docs/r34-mapui/shots/bat-1440-dropdown-open.png` | 1440×900 | 799,663 B | `DD9B5454B3C879D7B04A2C674E29F8288471B83C722334C00195A4524D461206` | 同上下拉展开（1440 宽） |
| `docs/r34-mapui/shots/bat-1440-wiki.png` | 1440×900 | 802,073 B | `D980A0802C4E48CA68787961FCB787A89408ADDE1C2E90B4980462321B015810` | Wiki 选中 + 分组面板 + 右上角 `R19.31-ff8648cf` |

运行时读数（1440 与 1024 一致）：

- `#base-mode-value` = `官方 Wiki`；
- Wiki 分组 = 5 组（`撤离点 / 转移点`、`物资`、`出生点`、`钥匙与门`、`其他`）；
- 当前默认地图为塔科夫街区（Streets）：分组行 27 行、`#wiki-markers` 下 604 个标点
  （0 计数行按既有规则不显示；不同地图的行数会随官方分类计数变化）。

## 11. 静态检查与测试（本轮）

- `node --check app.js`：通过。
- `node --check wiki-map.js`：通过。
- ES5 扫描：`app.js`、`wiki-map.js` 均无 `let` / `const` / 箭头函数；
  `app.js` 的反引号全部落在 `//` / `/** */` 注释内，不是模板字符串；`wiki-map.js` 无反引号。
- `python -m pytest tests -q`：**5 failed, 1620 passed, 1 skipped in 85.82s**。
  5 个失败与 §5.2 完全相同（既有配枪 / 布局问题，本轮未改、未弱化）：
  `test_r19_11_round`、`test_r19_13_round`、`test_r19_1_round`、`test_r19_5_round`、
  `test_r6_gun_workbench`。

## 12. 本轮追加产物

- `启动项目.bat`（改写，GBK/CRLF，SHA256 `F62AFF61…`）
- `docs/r34-mapui/shots/bat-1024-dropdown-open.png`、`bat-1024-wiki.png`、
  `bat-1440-dropdown-open.png`、`bat-1440-wiki.png`
- 本 ledger 追加章节
- 未 git 提交；未改 `release/`；未改 `dist/` 文件（只结束了旧打包版进程 PID 50104）。

---

# 追加：官方 Wiki 模式下右侧「任务 / 剧情目标」面板消失

host=HOMONAS user=MASTERJJ at=2026-11-03T19:37:31+08:00 round=R34-wiki-taskpanel

## 13. 定性：原本谁渲染、为什么消失

### 13.1 这块在矢量图模式下由谁渲染

- 容器：`index.html` 的 `<aside class="panel" id="task-panel" aria-label="任务与剧情目标">`，
  样式 `.panel#task-panel`（330px，右侧固定栏）。
- 渲染函数：`app.js` 的 `renderTaskPanel()`（R20.12，约 L1635）。
  - 数据：`data/task-points.json` → `attachTaskPoints()` 把 `maps.<key>.tasks/stories`
    挂到 `state.map`，再由 `taskGroupsOf()` 合并成「剧情在前、任务在后」的分组。
  - 行：`taskRow(g)` 生成标题 / 英文名 / 目标 / 楼层小按钮；点击走 `focusTaskGroup()`。
  - 依赖：不依赖图层开关；但点击定位用 `svgX/svgY`（`map.worldToSvg`），是**矢量图世界坐标**。
- 点位结构：`{x, z, floor, floorName, floorId, floorLabel}`（如街区 36.427 / 126.207，`Ground_Level`）。
- 计数：当前默认地图「塔科夫街区」共 41 个任务 + 13 个剧情 = 54 行 / 150 个点位。

### 13.2 为什么切到 Wiki 就没了

不是 JS 清空，也不是 wiki-map.js 接管后漏复刻，而是**一条 CSS 把整块隐藏**：

```css
/* 改动前 style.css */
body.wiki-base #viewport,
body.wiki-base #hud,
body.wiki-base .statusbar,
body.wiki-base #floor-block,
body.wiki-base #layers-block,
body.wiki-base #detail-block,
body.wiki-base #task-panel { display: none !important; }
```

因此是**「面板整块不存在（display:none）」而不是「面板在但内容为空」**：

| 状态 | 面板节点 | computed display | `.task-row` DOM | 可见性 |
|---|---|---|---|---|
| 改动前 Wiki | 存在 | `none` | 54 行（JS 没有清空，只是整块不可见；按代码推断，改前未做 DOM 采样） | 整块不可见 |
| 改动后 Wiki | 存在 | `flex`（330px） | 0 行 | 空态说明可见 |
| 矢量图 | 存在 | `flex`（330px） | 54 行 | 列表可见 |

### 13.3 为什么不能直接在 Wiki 图层画这些点

- 官方 `data/wiki-maps.json` 只有 `categories[]`（id/name/nameZh/count/icon）与
  `markers[]`（categoryId + 像素坐标 + 图标），**没有任务 / 剧情分类**；
  最接近的 `quest` 只是「电力面板」。
- 任务点来自 `data/task-points.json`，是矢量图世界坐标（x/z + floorId）；
  官方图层是图片像素坐标（街区 4097×2142）。两者之间**没有 `worldToImage` 仿射参数，
  也没有锚点对照表**，无法可靠换算，硬画会错位。
- 结论：不伪造点位，改为保留面板 + 明确空态说明。

## 14. 改动

| 文件 | 大小 | SHA256 | 改动 |
|---|---|---|---|
| `style.css` | 264,397 B | `9B70812E7A8D2B4C7D4C5272FD0DD32C6C9D9F3119468803D91DAC83A9164177` | 从 `body.wiki-base` 隐藏列表里移除 `#task-panel`，新增 `body.wiki-base #task-panel { display:flex !important; }`；Wiki 下隐藏 `.task-panel-search`（物资搜索属于矢量坐标）；新增 `.task-wiki-empty` 排版 |
| `app.js` | 1,126,851 B | `21FB20463474135F43B7829072A36B273779462C532419443374E46B8435C6AA` | `renderTaskPanel()` 增加 Wiki 分支；新增 `setTaskControlsForWiki()`、`renderWikiTaskEmpty()`；`initTaskPanel()` 监听 `gwmap:mode` 重渲染 |
| `wiki-map.js` | 25,314 B | `20F4277B44DB45625EF3131646AE3E039978B9A47F3984921561BA53C2890B83` | `setMode()` 在切换后 `dispatchEvent(new CustomEvent("gwmap:mode"))` |

空态文案（Wiki 模式）：

1. 「官方 Wiki 图层没有任务 / 剧情点位数据，这里不画点。任务栏保留，用来说明差异与缺失字段。」
2. 「塔科夫街区 在矢量图模式下有 41 个任务、13 个剧情（共 150 个点位）；切回「矢量图」即可查看列表并在地图上定位。」
3. 缺失的数据：
   - 官方图层任务分类：`wiki-maps.json` 的 `categories` 里没有 task / story 类目（最接近的 `quest` 只是「电力面板」）；
   - 任务点位展示字段：`name`、`objective`、`href`、`trader`、`floorId`（官方 `markers` 只有 `categoryId`、图标与像素坐标）；
   - 坐标映射：矢量图世界坐标 `(x, z)` → 官方图层像素坐标的 `worldToImage` 仿射参数（a–f），或至少 3 组锚点对照。

同时 Wiki 模式下任务栏的搜索框、重置、「显示全部」、标注名字开关统一 `disabled`，
避免出现「能点但没效果」的控件；切回矢量图自动恢复。

## 15. 验证

真实 Chrome + CDP（`deviceScaleFactor=1`），服务为源码 `tools/serve.py`（8787），
页面构建标记 `R19.31-1502674f`。

DOM 探测（同一会话依次切换）：

- 矢量图 1024：`panelDisplay=flex`、`panelWidth=330`、`taskRows=54`、`count=54`、搜索可用。
- Wiki 1024 / 1440：`panelDisplay=flex`、`panelWidth=330`、`taskRows=0`、`emptyNodes=1`、`count=0`、
  `searchDisabled=true`、`showAllDisabled=true`、`namesDisabled=true`、`.task-panel-search` 为 `none`。
- 切回矢量图：`taskRows=54`、`count=54`、控件全部恢复可用。

| 截图 | 尺寸 | 体积 | SHA256 |
|---|---|---|---|
| `docs/r34-mapui/shots/task-1024-wiki.png` | 1024×900 | 285,924 B | `9EEC91DD473337DBCD5CADA9E092E6BFF559F73B17316096A5343C2ECFF279E6` |
| `docs/r34-mapui/shots/task-1440-wiki.png` | 1440×900 | 602,857 B | `9F208970B8242357D85DA4E659CFF60C56AB433799417F8D7FD60823DEF4B5A2` |
| `docs/r34-mapui/shots/task-1024-vector.png` | 1024×900 | 473,296 B | `9E6EBAEDF582393F7E5CCD8D1FACDFD4B7A30D4089CE22FD6A756D0201AA1A4D` |

静态检查与测试：

- `node --check app.js` / `node --check wiki-map.js`：通过。
- ES5：两文件均无 `let` / `const` / 箭头函数；`app.js` 的反引号只出现在字符串与注释中
  （如 `ItemPropertiesMelee` 文案），不是模板字符串。
- `python -m pytest tests -q`：**5 failed, 1620 passed, 1 skipped in 83.21s**，
  仍为既有配枪 / 布局失败（`test_r19_1_round`、`test_r19_5_round`、`test_r19_11_round`、
  `test_r19_13_round`、`test_r6_gun_workbench`），本轮未改未弱化。

## 16. 仍缺的数据

- 官方图层任务分类：`wiki-maps.json` 需要 task / story 类目（当前只有 `quest`=电力面板）。
- 官方任务点位字段：`name`、`objective`、`href`、`trader`、`floorId`。
- 坐标换算：`worldToImage` 仿射 a–f，或 ≥3 组「矢量世界坐标 ↔ 官方像素坐标」锚点。

未 git 提交；未动 `release/`（LastWriteTime 仍 11:18:43）、未动 `dist/`（`_internal\index.html` 仍 10:22:26）。

---

host=HOMONAS user=MASTERJJ at=2026-11-03T20:17:33+08:00 round=R35-wiki-remove

## 17. R35：撤除「官方 Wiki」底图模式（只留矢量图，可逆做法）

用户决定：不再提供「官方 Wiki」底图，只保留矢量图。本轮只撤 **UI 与入口**，所有 Wiki 代码 /
数据 / 资源 / 测试**原样保留**，随时可恢复。未 git 提交，未动 `release/`、`dist/`。

### 17.1 改动文件与 SHA256

| 文件 | 体积 | SHA256 |
|---|---|---|
| `index.html` | 53,325 B | `62C7EFE5088C6AF11CBF616CB7F4D79C601BCEF215F1DF330841BE257FB8130C` |
| `app.js` | 1,123,584 B | `6D6C9637FE7F455E28E785A0B68CD53B66A6038BA6472872D992D6EE6D446C1E` |
| `style.css` | 263,055 B | `C054DCB6E599C396CBBA36C2713E41AD33FE523751341597B9F3754CDA3327B7` |
| `tools/serve.py` | 85,861 B | `250543EF7BFBB8F9F8ED10D6EE91CED61BD5BE2289D99301C1F9B37DBBC27DB3` |

移除范围：

- `index.html`：删掉整个底图选择器 `<div class="base-mode" id="base-mode">`（含 `#base-mode-trigger`、
  `#base-mode-value`、`#base-mode-menu`、两个 `.base-mode-option`）；地图块下方只留一句静态说明
  `<p class="muted base-mode-note" id="base-mode-note">底图：矢量图（按楼层拆分，支持全部标点）。</p>`
  ——不再有「只剩一项的假下拉」。删除 `<script src="wiki-map.js?v=r19.31">`，`wiki-map.js` 不再加载。
  全部资源版本 `?v=r19.31` → `?v=r19.32`（共 15 处）。
- `app.js`：顶部新增 `localStorage.removeItem("eftmap.baseMode")`；`AM_BUILD = "R19.32"`；
  `renderTaskPanel()` 恢复为纯矢量版（不再有 Wiki 空态分支）；删除 `setTaskControlsForWiki()` /
  `renderWikiTaskEmpty()` 与 `window.addEventListener("gwmap:mode", …)`。
- `style.css`：删除 `.base-mode` / `.base-mode-trigger` / `.base-mode-menu`（含 `[hidden]`）/ `.base-mode-option`
  / `:hover` / `.is-on` 全部规则，只保留 `.base-mode-note`；删除上一轮为 Wiki 任务栏加的两条覆盖
  （`body.wiki-base #task-panel{display:flex!important}`、`body.wiki-base .task-panel-search{display:none!important}`）
  与 `.task-wiki-empty` 四条规则——即 Wiki 空态整体收掉，不留死代码路径。
- `tools/serve.py`：`"rev": "R19.32-" + digest[:8]`（与 `AM_BUILD`、`index.html` 的 `?v=` 同步）。

保留（未改、未删）：`body.wiki-base #viewport/#hud/.statusbar/#floor-block/#layers-block/#detail-block`
的隐藏规则、全部 `#wiki-*` / `.wiki-*` 样式、`index.html` 里的 `#wiki-panel`、`#wiki-viewport`、`#wiki-svg`、
`#wiki-pop`、`.wiki-hud`，以及 `app.js` 的 `window.GWMapSatellite` 与 `window.GWMapLayerSpec`
（`wiki-map.js` 不加载时无消费者，仅为恢复保留）。

残留确认：

- `index.html` 中 `wiki-map.js` 的 `<script>` 标签 = 0；`id="base-mode"` = 0；`base-mode-trigger` = 0。
- `app.js` 中无 `baseMode` 变量/节点引用；`gwmap:select` 仍会派发，但此时无监听者，是无副作用的空操作。
- 旧底图键在脚本启动时直接 `removeItem`，因此 `localStorage.getItem("eftmap.baseMode") === null`
  （浏览器实测为 `None`），`wiki` / `satellite` / `vector` 三种旧值一律不再影响底图，页面固定矢量图。

### 17.2 保留的 Wiki 文件清单（可逆，路径 + 体积 + SHA256）

| 文件 | 体积 | SHA256 |
|---|---|---|
| `wiki-map.js` | 25,314 B | `20F4277B44DB45625EF3131646AE3E039978B9A47F3984921561BA53C2890B83` |
| `data/wiki-maps.json` | 404,121 B | `E9D6D8A620316CA12C3FEBB21AD469A461A949CB2DB7C3D8EB3CA54981DC46A8` |
| `tools/fetch_wiki_maps.py` | 10,312 B | `044DB2DEC48979419F95447F702E0A8D53BFE9B854CA4C7B19C669180ECCD727` |
| `assets/wiki-maps/customs.webp` | 939,194 B | `9D8B00BB9340249A80B4C5C59E08DC04C9259A7A520F9FDD3F8BAB40C4E1170A` |
| `assets/wiki-maps/factory.webp` | 1,290,634 B | `2462CF426A8A26896CDF0ED7AFB6A2AA76BA62F813F49FC7655C74307F3F764A` |
| `assets/wiki-maps/ground-zero.webp` | 844,474 B | `0C065BCF9182B9DCC65AC061D4E4563CB6FBFBD4D878A26A1B4A0F0CE14A17B8` |
| `assets/wiki-maps/icebreaker.webp` | 2,708,014 B | `183EF95FB90E36A011B6F2578C0766AD52B6C0C7878E18EFB89A37C9EE3ACBFF` |
| `assets/wiki-maps/interchange.webp` | 9,567,240 B | `B5F36AB969D53E655665FC3D417798220B0E6E3A459376336FF6DA3545A07590` |
| `assets/wiki-maps/lighthouse.webp` | 616,414 B | `FA6D49F8735762CC728AEE6E5B8982CF068F8E0A32A4BC8AD7B13E987C3323BD` |
| `assets/wiki-maps/reserve.webp` | 614,128 B | `6D4497CFCADBD2E55262BC61B5D70B58289D1FDF4E7EA07637F3BCF3F193AC28` |
| `assets/wiki-maps/shoreline.webp` | 1,472,048 B | `E6817F716D96B262B6FCE53FFA8ECB17B0080630FB225E80E8ABC7BF11AD82CC` |
| `assets/wiki-maps/streets-of-tarkov.webp` | 1,537,862 B | `74B60950F5BED65F336C8A83C086C6C8B29D99C696118D725AF6581E40466E1C` |
| `assets/wiki-maps/terminal.webp` | 2,039,876 B | `770F30422E992927AFDECCE6C5A17E2380276CED6A3493AEDE398E33F4334D9C` |
| `assets/wiki-maps/the-lab.webp` | 441,678 B | `EDDB0617C541B49337FAB05DFA6E22B536746A35E787766BBB2F4E0D1E1555DB` |
| `assets/wiki-maps/the-labyrinth.webp` | 510,116 B | `0AD56157443525491777E21782F7B139FA8662C2175DCD578217316F10E14599` |
| `assets/wiki-maps/woods.webp` | 1,660,596 B | `0427AA5E30F3EE296FB7C45317DAFE036CFCE935C067F11C5A70409F43849393` |

- `assets/wiki-maps/`：13 个 webp，合计 24,242,274 B（上表逐文件哈希）。
- `assets/wiki-icons/`：61 个 png，合计 92,728 B，目录级聚合 SHA256
  `6E2D55BCE60F2F41E580075F0ADA46EEC9DFB63F9CCB453D0A0D908A94074B27`
  （聚合方式：按文件名排序后拼接各文件 SHA256，再取 SHA256）。
  注意这 61 张图标**矢量图也在用**（`app.js` 的图标表指向 `assets/wiki-icons/*.png`），不属于可删资源。
- 测试：`tests/` 下没有 Wiki 底图专属用例（只有 `test_r17_fixes.py`、`test_r19_22_round.py` 里出现
  "wiki" 字样的数据来源注释），因此**无需 skip、也未删除任何用例**。
- 另保留：`docs/r20.21-wiki-mode-*.png`、`docs/r34-mapui/shots/*wiki*.png` 等历史截图，未动。

### 17.3 验证（真实 Chrome，源码服务 `rev=R19.32-31e864d8`，root=仓库根）

DOM 探测（1024×900）：

| 项 | 街区（streets-of-tarkov） | 海关（customs） | 街区@1440 |
|---|---|---|---|
| `#base-mode-trigger` / `#base-mode-menu` | 无 | 无 | 无 |
| `.base-mode` / `.base-mode-option` 节点数 | 0 | 0 | 0 |
| 卫星按钮（`#base-mode-satellite` / `.base-mode-btn`） | 0 | 0 | 0 |
| `#task-panel` 计算样式 | `display:flex`，宽 330 | 同上 | 同上 |
| `#task-list .task-row` 行数 | **54** | **58** | **54** |
| `#task-count` | `54` | `58` | `54` |
| `.task-panel-search`（物资刷新点） | `display:block` | 同上 | 同上 |
| `#task-search` 可用 | `disabled=false` | 同上 | 同上 |
| `localStorage.eftmap.baseMode` | `null` | `null` | `null` |
| `#wiki-viewport` | `display:none`（hidden 保留） | 同上 | 同上 |
| 注入钩子 `__errs` / CDP 控制台 | `[]` / `[]` | `[]` | `[]` |

交互验证（街区 1024）：

- 任务搜索输入「信号」→ 3 行；点「重置」→ 恢复 54 行。
- 点第一条任务行后再点「显示全部任务 / 剧情点」→ 54 行，按钮带 `is-on`。
- 「地图标注图标上显示任务、剧情名字」复选框：关 → 开，`localStorage.eftmap.task.names=1`，无报错。
- 物资刷新点搜索输入「钥匙」→ `#search-results` 显示、`.search-item` 30 条（上一轮被隐藏的搜索已恢复）。
- 地图「复位」→ `viewBox="0 -235.6258410913705 605.32395 1302.829212182741"`，相机行为未改。
- 控制台：0 报错；`favicon.ico` 仍为 **404**（既有问题，本轮未处理，仅记录）。

| 截图 | 尺寸 | 体积 | SHA256 |
|---|---|---|---|
| `docs/r34-mapui/shots/r35-1024-streets.png` | 1024×900 | 473,600 B | `283B6DE9B3946B2173CC935665B7C6FE486A3CC78A02E73E0F63F9BCFF0C4BEB` |
| `docs/r34-mapui/shots/r35-1440-streets.png` | 1440×900 | 697,540 B | `6EA30CB87A1220A97CAF83C838F915E7066B83C766D4E3276AEF64F6496FB2D9` |
| `docs/r34-mapui/shots/r35-1024-material-search.png` | 1024×900 | 474,647 B | `C7CA9D74F76C6ED462AA30E466286114220BC20412F5543CBFDCF7135D5E7341` |

### 17.4 静态检查与测试

- `node --check app.js`、`node --check wiki-map.js`：通过。
- ES5 扫描（`app.js`）：`let` / `const` / 箭头函数 / 模板字符串 命中 **0**（反引号仅出现在注释与普通字符串中）。
- `python -m pytest tests -q`：**5 failed, 1620 passed, 1 skipped in 81.26s**。
  仍为既有配枪/布局失败：`test_r19_1_round::test_candidate_columns_match_reference_order`、
  `test_r19_5_round::test_zoning_is_generic_semantic_rules`、
  `test_r19_11_round::test_hide_incompat_filters_without_touching_data`、
  `test_r19_13_round::test_row2_anchors_are_driven_by_real_slot_tree`、
  `test_r6_gun_workbench::test_gun_workbench_business_logic`。本轮未修、未弱化。
- Wiki 相关用例处置：无专属用例，**未 skip、未删除**；`test_r17_fixes.py` / `test_r19_22_round.py`
  中的 "wiki" 仅出现在弹道/数据来源注释里，不校验底图入口。

### 17.5 dist / release 现状（只记录，不重建）

- `dist/EFTMap/_internal/index.html` 仍为 2026-11-03 10:22:26 的旧版（`?v=r19.30`），
  仍含 `base-mode`、`wiki-map.js`、`wiki-panel`；`dist/EFTMap/_internal/wiki-map.js` 为 18,604 B 旧副本。
- `release/` 三个产物仍是 11:14–11:18 构建的旧版（含 Wiki 底图），本轮未重建。

### 17.6 若要「彻底删除」Wiki 底图，需要动的文件（等用户确认）

1. `wiki-map.js`（25,314 B）— 删除。
2. `data/wiki-maps.json`（404,121 B）— 删除。
3. `assets/wiki-maps/**`（13 个 webp，24.2 MB）— 删除。
4. `tools/fetch_wiki_maps.py`（10,312 B）— 删除。
5. `index.html`：`#wiki-panel`（L191–202）、`#wiki-viewport`（L224–232）。
6. `style.css`：全部 `#wiki-*` / `.wiki-*` 规则；`body.wiki-base` 六条隐藏规则；`.base-mode-note`。
7. `app.js`：`window.GWMapSatellite` 与 `window.GWMapLayerSpec` 导出、`setSatelliteMode` /
   `applySatellite` / `removeSatellite` / 卫星数据加载（约 L2040–2090、L3155–3169），
   以及 `gwmap:select` 派发（无消费者）。
8. `tests/`：无 Wiki 专属用例，无需改动；`test_r17_fixes.py` / `test_r19_22_round.py` 的注释可留。
9. `assets/satellite/**`（卫星图资源）若一并弃用，可同时删除；`assets/wiki-icons/**` **不能删**
   （矢量图图标在用）。
10. `dist/**`、`release/**` 旧副本：需重新打包才能同步；不在本轮范围。

---

host=HOMONAS user=MASTERJJ at=2026-11-03T21:25:32+08:00 round=R36-layer-collapse

## 18. R36：左侧图层面板分组可单独收起 / 展开

8 个分组全部可折叠（撤离点 / 转移点、物资、赛季文件、任务 / 剧情、出生点、钥匙与门、
危险区域、其他），**没有无法折叠的分组**。未 git 提交，未动 `release/`、`dist/`、地图渲染与相机。

### 18.1 改动文件与 SHA256

| 文件 | 体积 | SHA256 |
|---|---|---|
| `app.js` | 1,127,392 B | `68D9CC90A84A1921C25745440C954FE2D10F73924A5C3027BE7BA8CF8EFC43F9` |
| `style.css` | 264,825 B | `9E0EA321048305AC2087317E763752893229A3DE4A95E71B6133E6996F48EAC0` |
| `index.html` | 53,325 B | `BDA659A5A6E50E4EA5920DC7E932797AA5D49D16953D32C500B78924B0F832C6` |
| `tools/serve.py` | 85,861 B | `78FCDB00CAF113F3C3A7253DE741AE2BE248CE25BFA734F539F3D413DA024A9B` |

- 版本串三处同步到 `R19.33`：`app.js` 的 `AM_BUILD`、`index.html` 的 `?v=r19.33`（15 处）、
  `tools/serve.py` 的 `"rev": "R19.33-"`。

### 18.2 实现方式

- `LAYER_SPEC` 每个分组新增稳定 `id`：`extracts` / `loot` / `docs` / `quests` / `spawns` /
  `locks` / `hazards` / `misc`。折叠状态只认这个 id，**不按渲染顺序、不按标题文字**，换图共用。
- `renderLayerToggles()` 每组的 DOM 结构：
  `div.legend-group[data-group-id]` → `div.toggle-group.legend-group-head`（内含原生
  `button.legend-group-toggle[aria-expanded][aria-controls="legend-body-<id>"]`：`span` 箭头 ▾ +
  `span` 标题）+ 独立的 `span.legend-group-count`（计数）→ `div.legend-group-body#legend-body-<id>`（各行）。
- 折叠头是原生 `<button>`：可聚焦，Enter / Space 由浏览器原生处理；`aria-expanded` 表示展开状态，
  `aria-controls` 指向组内列表的 `id`（实测 8 组全部一致）。
- 计数放在 button **外面**，点数字不会折叠；各行复选框在 body 内，也不参与折叠点击。
- 切换只做「改内存 → 写 localStorage → 就地更新 `aria-expanded` 与 `body.hidden`」，
  不重建列表，键盘操作后焦点不丢；收起仅隐藏 `legend-group-body`，复选框 DOM 与勾选状态保留。
- 视觉沿用 `--xp-title` / `--xp-line` / `--xp-muted` / `--xp-sel` / `.toggle-group` 的间距与分隔线；
  另外用 `html #layer-toggles .legend-group-toggle[data-flash="1"]` 屏蔽全局「按钮点击闪黄」，
  避免折叠头像被按下的操作按钮（截图复查已确认无黄底）。
- 分组计数 = **该组当前可见的图例行数**（不是点位总数，避免总开关与子类重复计数）；
  `title` 提示写明「本组共 N 个图层开关」。计数随地图重算（海关 / 街区不同）。

### 18.3 localStorage 键与结构

- 键名：`eftmap.layerCollapsed`
- 结构：`{"spawns":true,"locks":true}`（只存 true，展开时写回 false 而不是删键；整体仍为对象）
- 读取容错：`loadLayerCollapsed()` 解析 JSON，只保留 `LAYER_SPEC` 里存在且值为布尔的分组 id，
  不认识 / 旧版本 / 手改的 id 直接丢弃（不报错、不写回），启动时 `state.layerCollapsed = loadLayerCollapsed()`。

### 18.4 验证（真实 Chrome，`rev=R19.33-0fe8fddf`）

街区（streets-of-tarkov）展开态基线：`extracts 4 / loot 24 / docs 3 / quests 2 / spawns 5 /
locks 2 / hazards 1 / misc 3`，行数与计数一致。

| 状态 | 出生点 | 钥匙与门 | 其它 6 组 | 勾选状态 |
|---|---|---|---|---|
| 1024 全部展开 | aria=true, hidden=false | aria=true | 全部 true | 出生点已勾 1 项、钥匙与门 1 项 |
| 1024 收起两组 | aria=false, body 高 0 | aria=false | 仍 true / 可见 | 收起前后 `checked` 完全一致 |
| 1024 刷新后 | aria=false | aria=false | 仍 true | 仍一致 |
| 1440 三态 | 与 1024 相同 | 相同 | 相同 | 相同 |

其它验证：

- 点「出生点」计数数字 → `aria-expanded` 仍为 `true`（不误折叠）。
- 键盘：聚焦出生点折叠头按 Enter → `aria-expanded` 由 `false` 变 `true`，焦点仍在按钮上。
- 换图：切海关后分组 id 不变、折叠状态保持，计数重算为 `loot 23 / spawns 4 / hazards 2 / misc 2`；
  切回街区恢复 `loot 24 / spawns 5 / hazards 1 / misc 3`（此时 `spawns` 因上一步键盘测试为展开，
  `locks` 保持收起——说明状态按组独立）。
- 控制台 0 报错；`favicon.ico` 404 仍为既有问题。

| 截图 | 体积 | SHA256 |
|---|---|---|
| `docs/r34-mapui/shots/r36-1024-expanded.png` | 475,495 B | `B737F7988000A5F6B8B680CDA812E7CAF2E25276B076734BB3E38152156B56B5` |
| `docs/r34-mapui/shots/r36-1024-collapsed.png` | 475,866 B | `71490496DA0AE620475B3114F626569962CD0EC7B8C0D2F54FA96D9A8F7FE0B1` |
| `docs/r34-mapui/shots/r36-1024-reloaded.png` | 475,873 B | `1F12ECA06AC0EC3DB6C101C909AA9C6FD4B9E59A32846C02F07C3EB8A8EED552` |
| `docs/r34-mapui/shots/r36-1440-expanded.png` | 701,884 B | `714F7D5868F8B072923F5810F6BFC81BDC2A89118CAF825A9FF6C61452F1916D` |
| `docs/r34-mapui/shots/r36-1440-collapsed.png` | 701,529 B | `D093257B030D2BF951D8A88F6B9E921B41C37CBF51312DEF4D2380DFE9AF3F97` |
| `docs/r34-mapui/shots/r36-1440-reloaded.png` | 701,584 B | `B235C076AEE84BBA0BD4D78D71C268C4CD82E196C04DBC62560CE5D338023A03` |

### 18.5 静态检查与测试

- `node --check app.js`：通过；ES5 扫描（`let` / `const` / 箭头函数 / 模板字符串）：**0 命中**。
- `python -m pytest tests -q`：**5 failed, 1620 passed, 1 skipped in 83.84s**；失败仍是既有 5 个
  （`test_r19_11_round`、`test_r19_13_round`、`test_r19_1_round`、`test_r19_5_round`、
  `test_r6_gun_workbench`），本轮未改、未弱化。
- `dist/EFTMap/_internal/index.html` 仍 2026-11-03 10:22:26，`release/` 三产物仍 11:14–11:18，均未改动。

## 19. R37 · 「数据来源 / 版权 / 数据版本」整段迁入「关于」

host=HOMONAS user=MASTERJJ at=2026-11-03T22:08:14+08:00 round=R37-about-move

### 19.1 迁出 / 迁入位置

- **迁出**：`index.html` 里 `aside#sidebar` 底部的 `<footer class="credits">`，原先含
  两个硬编码 `<p>`（`数据来源…` / `《逃离塔科夫》商标…`）与一个动态 `<p id="meta-line" class="muted">`。
  现在 footer 只剩一行极简提示：`数据与许可说明见顶部菜单「关于」。`（1 个 `<p>`，无分隔线）。
- **迁入**：已有的顶部菜单「关于」下拉（`#menu-about` + `#about-block`，`.menu-panel.about-panel`，
  `bindMenu()` 管开合 / 外部点击 / Esc），在「任务攻略里的时间说明」之后新增
  `<h4>数据来源与许可</h4>` + 三段 `<p class="about-note">`。原「关于」里同名的
  `<h4>数据来源</h4>` 改为 `<h4>数据范围与复核状态</h4>`，避免出现两个同名标题。
- **动态行**：`renderMetaLine()` 写入目标由 `meta-line` 改为 `about-meta-line`（加了空节点保护），
  格式串与取值来源完全不变（仍读 `data/meta.json` 的 `generatedAt / gameMode / counts`）。
- **版本串**：`AM_BUILD`、`index.html` 全部 15 处 `?v=`、`tools/serve.py` 的 rev 同步到 `R19.34`。

### 19.2 改动文件与 SHA256

| 文件 | SHA256 |
|---|---|
| `index.html` | `3F697F0F9902AE399C5B91364A34F6861F3E18300F798E865538020C91F3374A` |
| `app.js` | `BC3BC7D1640F0C37BAC9AADBF317BCEEF61E54D57CBE7869248EA3FAFF235E12` |
| `tools/serve.py` | `D0712551B6242A336BED5BFA9F082C3A3D9CC01205E9BA3636FE8D0DC672FEF6` |
| `style.css` | `9E0EA321048305AC2087317E763752893229A3DE4A95E71B6133E6996F48EAC0`（本轮未改） |

### 19.3 逐字比对（含标点）

基线取 `dist/EFTMap/_internal/index.html`（迁移前的未改动打包副本，本轮不动 dist）里的
footer 原文，与浏览器 `textContent` 归一空白后逐段 `==` 比较；第三段按 `data/meta.json` 现算。

| 段落 | 结果 |
|---|---|
| `数据来源：tarkov.dev 公开数据（…，MIT）；底图 SVG（…，CC BY-NC-SA 4.0，非商业）；图层图标为 tarkov.dev 互动地图分类图标（官方 Wiki 互动地图同款）。` | **exact=True** |
| `《逃离塔科夫》商标与原始美术归 Battlestate Games。本工具永久免费、严禁售卖，与游戏进程零交互。` | **exact=True** |
| `数据版本：2026-10-20T15:10:05Z · 模式 regular · 13 张图 / 146 个撤离点 / 6408 个物资点 / 643 个 Boss 点` | **exact=True**（动态生成，与 `data/meta.json` 一致） |

链接保留（2 个，`target="_blank" rel="noopener"` 未动）：
`the-hideout/tarkov-dev` → `https://github.com/the-hideout/tarkov-dev`；
`tarkov-dev-svg-maps` → `https://github.com/the-hideout/tarkov-dev-svg-maps`。

### 19.4 验证（真实 Chrome，`rev=R19.34-b04fe7c5`）

| 项目 | 1024×768 | 1440×900 |
|---|---|---|
| 侧栏 footer 文本 | `数据与许可说明见顶部菜单「关于」。` | 同 |
| footer `<p>` 数 / 高度 / 上边框 | 1 / 47px / `0px none` | 同 |
| 旧 `#meta-line` 节点 | 不存在 | 不存在 |
| 侧栏文本含「永久免费 / 严禁售卖 / BY-NC-SA」 | 否 | 否 |
| 关于面板（宽 / 高 / max-height） | 430 / 553 / 552.96px | 430 / 575 / 648px |
| 关于面板溢出 | `overflow-y:auto`，scrollH 573 > clientH 551（可滚动） | scrollH 573 = clientH 573（无需滚动） |
| 面板横向溢出 | scrollW 428 = clientW 428，无 | 同 |
| 三段文字完整可见 | 3/3 `fullyInPanel=True` | 3/3 `fullyInPanel=True` |
| 面板右侧边界 | right=493 ≤ 1024，不顶出屏幕 | right=906 ≤ 1440 |
| 面板遮挡检查 | 各段中心 `elementFromPoint` 均落在面板内 | 同 |
| Esc 关闭 | `hidden=True`,`aria-expanded=false` | 同 |
| 控制台报错 / 外部请求 | 0 / 0 | 0 / 0 |
| 页面横向溢出 | 无 | 无 |

### 19.5 截图

| 截图 | 体积 | SHA256 |
|---|---|---|
| `docs/r34-mapui/shots/r37-1024-map.png` | 437,957 B | `1E643DE1AC6077D8721E6372031761C6023553A6BF45A4F2D6E768C5A71552D2` |
| `docs/r34-mapui/shots/r37-1024-map-footer.png` | 428,165 B | `62BDA9570D9914AC334ED5AA679F782F855157A57ADC54DEAEA5B7B153509046` |
| `docs/r34-mapui/shots/r37-1024-about.png` | 66,313 B | `525018EDCCCECA7086C6BA8E599DD0432025E6C35E5612B6C8F1EECC0AC7E601` |
| `docs/r34-mapui/shots/r37-1440-map.png` | 698,287 B | `8F7C25FCC8D1663AE61E6578088FED0C4B2D7FEDACF7FD6AE09E91BC4A87B9ED` |
| `docs/r34-mapui/shots/r37-1440-map-footer.png` | 688,913 B | `01435EB140A10EA9E50B743697B205E955CAA24213ACBB1E4F9C7B20D5F6C2E2` |
| `docs/r34-mapui/shots/r37-1440-about.png` | 68,716 B | `89E8E4618524C81A61036462F8FCECB622600C0BF0DF90F70DFF89EDDC98288E` |

`*-map-footer.png` 是把侧栏滚到底后截的（1024 scrollTop=1078、1440 scrollTop=929），
用来确认底部只剩一行提示、上方没有空占位或多余分隔线。

### 19.6 静态检查与测试

- `node --check app.js / tasks.js / combat_sim.js / gun_builder.js`：全部通过。
- ES5 扫描（`let` / `const` / 箭头函数）：**0 命中**。
- `python -m pytest tests -q`：**5 failed, 1620 passed, 1 skipped in 84.21s**；失败仍是既有 5 个
  （`test_r19_1_round`、`test_r19_5_round`、`test_r19_11_round`、`test_r19_13_round`、
  `test_r6_gun_workbench`），本轮未改、未弱化、未跳过。
- 相关用例单独跑：`test_r32_about` / `test_r15_fixes` / `test_serve` / `test_offline_guard` /
  `test_r20_3_hash_contract` → **145 passed**。`tests/test_r32_about.py` 依赖的面板切片
  （`id="about-block"` 到第一个 `</div>`）仍然覆盖新增内容，无需改断言。
- 未执行 git 提交；`dist/EFTMap/_internal/index.html`（10:22:26）与 `release/` 三产物未改动。

---

# 追加 §20：配装页「无内衬护甲仍显示有效耐久」诊断

host=HOMONAS user=MASTERJJ at=2026-11-03T22:24:04+08:00 round=TaskH-armor-effdur-diagnosis

> **本轮未改代码。** 只做只读诊断：未改 `app.js`、未改 `combat_sim.js` 公式、未改任何
> `data/*.json`、未改测试。未执行 git 提交，未改动 `release/`、`dist/`。

## 20.1 显示链路（文件与行号）

| 环节 | 位置 | 说明 |
|---|---|---|
| 分母：材质损毁系数 | `app.js` 5904–5910 `materialDestructibility()` | 取 `items.json` 的 `audit.materials[mat].d`，材质级默认值，缺材质返回 `null`；不存在逐件系数 |
| 本体有效耐久 | `app.js` 5911–5917 `effectiveDurability(rec)` | `rec.dur / materialDestructibility(rec.mat)` |
| 内衬明细 | `app.js` 8701–8742 `linerBreakdown(rec)` | 只统计 `aps[].fx` 为真的固定软内衬；`fx=0` 或无 `fx` 时 `total/eff` 均为 `null` |
| 显示取值 | `app.js` 9703–9713 `effDurValue(rec)` | `r.liners && r.liners.eff > 0` → 内衬合计；**否则回退本体 `effectiveDurability(rec)`** |
| 单元格渲染 | `app.js` 9714–9733 `effDurCol(rec)` | 悬停提示「纸面耐久 / 损毁系数」；无值显示「—」 |
| 护甲 / 装甲胸挂表 | `app.js` 9991–9993（`armorCols` 内 `effDurCol`） | 行内直接显示该列 |
| 插板弹窗 | `app.js` 9973–9975 | 插板（`kind=plate`）同样走 `effDurCol` |
| 头盔表 | `app.js` 10011–10013 | 头盔同样走 `effDurCol`（代码注释明确此回退是给「头盔等无内衬」的） |
| 模拟建层 | `app.js` 21325–21377 `amSimArmorLayers` | 只对 `aps[].fx` 建软内衬层、对已装插板建板层；**不消费** `effectiveDurability`，也不消费承运背心本体 `dur` |

结论性显示条件：**护甲行一律计算并显示「有效耐久」**——有固定软内衬时显示内衬合计
`Σ(dur/d)`；没有内衬时并不是留空，而是走 `effDurValue` 的兜底，显示
`纸面耐久 ÷ 材质损毁系数`。判定只区分「`fx` 内衬合计是否可用」，**没有「是否真的存在内衬」
的前置过滤**。分母固定为材质损毁系数（`Aramid 0.1875`、`UHMWPE 0.3375` 等），不是逐件值。

## 20.2 清单（配装页护甲根槽位候选：`slot=armor` + 装甲胸挂，共 108 件）

| 分组 | 件数 |
|---|---|
| 无固定软内衬（`aps[].fx` 为 0）但显示有效耐久 | **10** |
| 有固定软内衬（`aps[].fx` ≥ 1），按内衬合计显示 | **98** |
| 其中 `bt` 走材质兜底（`material-fallback`） | 无内衬 **1** 件 / 有内衬 **4** 件 |

无内衬 10 件（全部是**插板背心 / 插板胸挂**，`aps` 只有 `Front_plate` / `Back_plate` 等硬板插槽，
`z` 只有 `Plate_*` 命中区，没有 `soft_armor_*`）：

| # | 物品 id | 名称 | 等级 | 材质 | 纸面耐久 | 损毁系数 | 显示的有效耐久 |
|---|---|---|---|---|---|---|---|
| 1 | `5fd4c474dd870108a754b241` | 5.11 Hexgrid 插板背心 | 6 | UHMWPE | 100 | 0.3375 | 296.3 |
| 2 | `628b9784bcf6e2659e09b8a2` | S&S Precision PlateFrame 插板胸挂（Goons 特别版） | 5 | UHMWPE | 120 | 0.3375 | 355.6 |
| 3 | `628cd624459354321c4b7fa2` | Tasmanian Tiger SK 插板胸挂（黑系复合迷彩） | 6 | UHMWPE | 110 | 0.3375 | 325.9 |
| 4 | `63737f448b28897f2802b874` | Hexatac HPC 插板背心（黑系复合迷彩） | 5 | Aramid | 90 | 0.1875 | 480.0 |
| 5 | `64a5366719bab53bd203bf33` | Eagle Allied Industries MBSS 插板胸挂（狼棕色） | 3 | Aramid | 70 | 0.1875 | 373.3 |
| 6 | `66b6295a8ca68c6461709efa` | Tasmanian Tiger MKIII 插板胸挂（狼棕色） | 5 | Aramid | 110 | 0.1875 | 586.7 |
| 7 | `67ab2eecfe82855dcc0f2af6` | Hexatac HPC 插板背心（复合迷彩） | 5 | Aramid | 90 | 0.1875 | 480.0 |
| 8 | `693fd0e9deee848f70054999` | Crye Precision JPC 插板胸挂（复合迷彩） | 5 | Aramid | 110 | 0.1875 | 586.7 |
| 9 | `693fd1200ec97e98040bd3f9` | Tac-Kek JayPC 插板胸挂（黑色） | 1 | Aramid | 180 | 0.1875 | 960.0 |
| 10 | `693fd13aa490096a05028cc8` | Tac-Kek JayPC 插板胸挂（橄榄绿） | 1 | Aramid | 180 | 0.1875 | 960.0 |

有内衬 98 件的完整字段表见清单文件（`docs/r38-armor-effdur/audit-noliner.json` 的
`hasLiner` 数组）。这 98 件全部按内衬合计显示，与本体 `dur/d` 无关。

数据缺口：

- 无内衬 10 件中，`items.json` **缺 `bt`** 的只有 1 件：`5fd4c474dd870108a754b241`
  （5.11 Hexgrid，`armor-bt.json` 以 `material-fallback` 提供 `bt=0.26`）；
- 其余 9 件 `bt` 均为逐件值（`0.2259` / `0.2277` / `0.241` / `0.35` / `1`）；
- 10 件的 `dur`、`mat`、`cl`、`aps`、`z` 均完整；`audit.materials` 无缺材质（缺 `d` 计数 0）；
- 有内衬 98 件中 `material-fallback` 共 4 件：`NFM THOR ×3`、`ANA Tactical M1`（与本次问题无关）。

## 20.3 属于 a/b/c/d 哪一种

**判定：c** ——这些护甲确实没有内衬、也不该显示有效耐久，是渲染条件漏了过滤。

数据证据：

1. 10 件的 `aps` 全部只有硬板插槽（`Front_plate` / `Back_plate`，`fx` 字段缺失或为假），
   **没有任何 `fx` 固定软内衬**，也没有 `soft_armor_*` 非固定软层；
2. 10 件的 `z` 只有 `Plate_Granit_SAPI_chest` / `Plate_Granit_SAPI_back` 等**板命中区**，
   没有 `RibcageUp` / `SpineTop` / `Pelvis` 等软甲覆盖区；
3. 它们的「有效耐久」不是插板的值：插板是 `cat=plate` 的独立物品，有各自的 `dur/mat`，
   在插板弹窗里独立显示；10 件承运背心的数值是**本体 `dur ÷ 材质系数`**；
4. 代码注释 `app.js` 9705–9706 写明这条回退是「头盔等无内衬的取 `effectiveDurability()`
   （本体 dur ÷ 本体材质系数）」，但护甲 / 装甲胸挂行没有内衬时同样命中该分支——回退范围
   从「头盔」泄漏到了「无内衬护甲行」。

排除：

- **a 不成立**：这些不是硬质插板（`cat` 为 `Armor` / `ChestRig`，不是 `plate`），插板本身另有显示；
- **b 不成立**：`z` 只有板命中区，没有板 + 软层一体的整体装甲区，损毁系数并不适用于整件；
- **d 不成立**：`d` 按 `audit.materials[mat]` 取材质级默认值（本项目数据模型没有逐件 `d`），
  取值一致且正确；问题在于把这套系数套用到「没有软层」的承运背心本体上，不是取错逐件值。

边界说明：头盔表（`cat=helmet`，40 行）同样走本体 `effDurCol`，这是代码既有的明确设计
（头盔本体就是防护体），不在本次「护甲」口径内；若用户也要求头盔隐藏，需另做判定。

## 20.4 三种修法选项与影响面

| 选项 | 做法 | 影响件数 | 对模拟 / 逐发计算 |
|---|---|---|---|
| **A 仅 UI 隐藏** | `effDurValue` 只在「护甲 / 装甲胸挂行」且内衬合计不可用时返回 `null`；需给行加作用域标记，避免误伤插板弹窗（插板也走 `effDurCol`，但它的 `liners` 同为 `null`） | 隐藏 **10** 行；98 行有内衬、38 个插板行、40 个头盔行不变 | **无影响**：`combat_sim.js` 不读该值；`amSimArmorLayers` 只按插板与 `fx` 内衬建层，不读承运背心 `dur` |
| **B 修数据与判定** | 补全 liner / 背衬结构字段，按真实结构判断 | 也是 **10** 件需要标记；但上游数据里这 10 件确实没有软层，补「内衬」等于伪造数据 | 若只加结构与判定，无影响；若真的写入软层/耐久，会改变 `amSimArmorLayers` 的层数，**影响逐发模拟** |
| **C 保持现状 + tooltip** | 数值照旧，在悬停提示说明「无内衬时为本体耐久 ÷ 材质系数」 | 0 件变化；仅 10 行提示文案变化 | 无影响 |

推荐：**A**。数据已证明 10 件无软内衬，显示本体换算值没有物理意义；A 只改显示分支，
不影响模拟与逐发计算，也不伪造数据。实现时需用行级作用域（如 `r.linerScope='armor'`）
而不是直接看 `r.liners === null`，否则插板弹窗会被一起隐藏。若希望保留信息，可叠加 C 的
tooltip 解释，但不应影响 A 的隐藏结果。

## 20.5 证据

- 截图：`docs/r38-armor-effdur/taskh-1024-armor-noliner-effdur.png`（138,481 B，
  SHA256 `DCD67E80801066D578519FFF5BB2301ED022260637D6491BD1C500B2781F38D2`）——
  真实 Chrome 1024×768，护甲槽选中后筛选「Hexatac HPC」，两行 `有效耐久 480`，
  前部内衬列全部为「—」，提示「损毁系数：0.19」。
- 清单：`docs/r38-armor-effdur/audit-noliner.json`（102,220 B，
  SHA256 `88D38027E1F4C913D3F19BC3CC672395757BDFA855A53A6FD350AC667474624C`），
  含 `noLiner`（10）与 `hasLiner`（98）两张完整表及 `btSource`。
- 问题实例字段（`63737f448b28897f2802b874`）：`cl=5`、`dur=90`、`mat=Aramid`、
  `bt=0.2259`、`z=[Plate_Granit_SAPI_chest, Plate_Granit_SAPI_back]`、
  `aps=[{zone:Front_plate, plates:19}, {zone:Back_plate, plates:19}]`，无 `fx`。
  页面显示 `90 / 0.1875 = 480`。

## 20.6 留痕与边界

- **本轮未改代码**；`app.js`、`combat_sim.js`、`data/*.json`、测试均未修改。
- 未执行 git 提交；未改动 `release/`、`dist/`；未改 `combat_sim.js` 的公式。
- 本轮只新增 `docs/r38-armor-effdur/` 两份证据文件与本 ledger §20。

---

# 追加 §21：无内衬护甲隐藏有效耐久（A 方案）+ 价格说明迁入「关于」

host=HOMONAS user=MASTERJJ at=2026-11-03T22:46:50+08:00 round=R40-armor-effdur

> 本轮改 `app.js`、`index.html`，新增 `tests/test_r40_armor_effdur.py` 与
> `docs/r40-armor-effdur/` 截图。`combat_sim.js`、`data/*.json`、`release/`、`dist/`
> 均未改动；未执行 git 提交。

## 21.1 改动文件与 SHA256

| 文件 | SHA256 |
|---|---|
| `app.js` | `F658AEAA98958B70D6364252038D574912E1E42980E96BD2A5CCC68DD6DCA5AD` |
| `index.html` | `08AC56AC06274E47C59D80448A885D0794693F18F5BF9234A31DE84689370A35` |
| `tests/test_r40_armor_effdur.py` | `17D53815E84A84DFBCE1394678695E20B4C2466EF18D136DDB1F5E76BD45793D` |

版本串未改（仍为 `R19.34`）；`tools/serve.py` 已发 `no-store`，无需靠版本号破缓存。

## 21.2 A 方案实现（行级作用域）

1. `advCtx` 造行处新增 `linerScope`：
   - `rootKey === "armor" || "rig"` 的根表行 → `"armor"`（按内衬口径判空）；
   - 插板选择窗（`node.kind === "plate"`）→ `"plate"`（继续显示本体值）；
   - 头盔等其它根（`rootKey === "helmet"`）→ `null`（继续走本体
     `effectiveDurability()`）。
2. `effDurValue(r)` 增加前置分支：`r.linerScope === "armor"` 且内衬合计
   `liners.eff` 不可用时返回 `null`。**没有用硬编码 id 列表**；结构判定仍由既有
   `linerBreakdown()` 的 `aps[].fx` 驱动。
3. `effDurCol.render` 在空值时输出 `—`，并对被隐藏的护甲行设置
   `title="无固定软内衬（仅硬质插板插槽）：纸面耐久 ÷ 损毁系数不适用"`。
4. `row.effDur` 本体数值与 `effectiveDurability()` 保留；`combat_sim.js` 未改。

影响件数：护甲根槽位候选 108 件中，**10 件隐藏**，98 件有内衬照常显示；
38 个插板行、40 个头盔行路径未进入新分支。

## 21.3 真实 Chrome 数值核对（1024，前后同页对比）

| 类型 | 物品 | 改前 | 改后 |
|---|---|---|---|
| 无内衬 | Hexatac HPC ×2 | 480 / 480 | **— / —** |
| 有内衬 | 6B43 屏障-Sh | 1867 | 1867 |
| 有内衬 | 6B23-2 / 6B23-1 | 832 / 832 | 832 / 832 |
| 插板 | AR500 Legacy / ESAPI IV / Granit Br5 | 120 / 92 / 100 | 120 / 92 / 100 |
| 头盔 | Altyn / Rys-T / Gorilla | 154 / 218 / 76 | 154 / 218 / 76 |

10 件无内衬行全部实测为 `—`（DOM `data-key=effDur`），且每行都带上述 title：
`5fd4c474dd870108a754b241`、`628b9784bcf6e2659e09b8a2`、`628cd624459354321c4b7fa2`、
`63737f448b28897f2802b874`、`64a5366719bab53bd203bf33`、`66b6295a8ca68c6461709efa`、
`67ab2eecfe82855dcc0f2af6`、`693fd0e9deee848f70054999`、`693fd1200ec97e98040bd3f9`、
`693fd13aa490096a05028cc8`。

## 21.4 价格说明迁入「关于」

- 配装页左侧 `<p class="lw-note lw-foot">` 整段删除，`#loadout-workbench` 内不再出现该文字，
  `lw-foot` 不再出现在 HTML 中；未见空占位或多余分隔线。
- 「关于」`#about-block` 内新增独立 `<h4>价格说明</h4>` + 单段 `p.about-note`，逐字文本：
  `价格为构建期快照，非实时行情。商人买入 / 卖出价取自上游 buyFromTrader / sellToTrader，构建期已提取；买卖价与「获取方式」列同源，运行期不联网。`
- Chrome 1024 与 1440 实测：文本 `===` 原文，标点与空格一致；数据来源第一段与
  「永久免费、严禁售卖、与游戏进程零交互」段落也逐字一致（见 `r40-verify.json`）。
- 关于面板：1024 下 `clientW=428 / scrollW=428`、`clientH=551 / scrollH=669`，可滚动；
  价格段滚到底后整体落在面板内；`body` 横向溢出 0。1440 同（无溢出）。
  `Esc` 两档均关闭面板。

## 21.5 截图

目录 `docs/r40-armor-effdur/`，真实 Chrome（1024×768 / 1440×900，DSF=1）：

| 文件 | 尺寸/字节 | SHA256 |
|---|---|---|
| `r40-1024-armor-noliner.png` | 137,967 | `2A542C22B1ADA176BB3C9F0364ACB0DDBBCF0DAC3A48928945FFED539035C758` |
| `r40-1024-armor-liner.png` | 131,260 | `E10458D31D3EDA984986082979BDFDFCCD3245EA0950311FA23679A786D02FE2` |
| `r40-1024-about-top.png` | 144,317 | `D0534DCB9BE7ABAD1B44E87F039D1376984D2EAA8570CCC555C040C5D70D3F7B` |
| `r40-1024-about-bottom.png` | 144,712 | `850688956C6A1836D08529FF599783C7F424AB3C0EACAA75E8D03D49CAEA25E6` |
| `r40-1440-armor-noliner.png` | 176,256 | `C4B5B18EC4DF30830FAD52CFCB335DF697353BFC46B5031EB87F03A17F4D58EF` |
| `r40-1440-armor-liner.png` | 167,576 | `C7C6DE754491F950B4A0C7E1551434ED6675EBFF289B8CD49F1E7BDA3FB1B1D0` |
| `r40-1440-about-top.png` | 227,607 | `60713671790A8B201F79E2FA3D7C7583A975792DF162C77820392FEAE9DE8685` |
| `r40-1440-about-bottom.png` | 226,354 | `2929882C765D5C0FF7AB90B820580EC5F48A1B2315F238C52103FB9BA2112F5F` |

## 21.6 测试与静态检查

- `node --check app.js`：通过。
- ES5 扫描：无 `let` / `const` / 箭头函数；新增代码没有模板字符串。
- `python -m pytest tests -q`：**5 failed, 1625 passed, 1 skipped**（新增 5 条用例全过；
  5 个失败为既有配枪/布局问题：`test_r19_1`、`test_r19_5`、`test_r19_11`、`test_r19_13`、
  `test_r6_gun_workbench`，未修改、未删除）。
- 新增 `tests/test_r40_armor_effdur.py`：
  - 无内衬护甲 → 空值；
  - 有内衬护甲 → `liners.eff`（1867 / 832）；
  - 插板 120、头盔 154 不变；
  - 行级 `linerScope` 与 `node.kind === "plate"` 存在，10 个 id 不出现在 `app.js`；
  - 价格说明逐字只在关于出现一次，配装工作区无 `lw-foot`。

## 21.7 边界

- 未 git 提交；未改动 `release/`、`dist/`；未改 `combat_sim.js` 公式与数据文件。
- 关于面板在 1024 下需要滚动才能看到价格段（已有滚动条，无横向溢出），截图分
  top/bottom 两张呈现。
