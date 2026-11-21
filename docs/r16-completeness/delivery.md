# R16 交付说明（A–E）

> 本轮依据《R16 执行任务书》执行：先核实现状，再改代码、补数据、跑回归、做真实浏览器验收。
> 未提交 Git、未推送、未改 `release/`。所有数字均为本机实测。

## A. 本轮实际修改内容

| # | 目标 | 根因 | 修复文件 |
|---|---|---|---|
| A | **枪械按口径/平台分组** | `data/gun-rates.json` 只有 `n/rpm/modes`，下拉是 163 项平铺；上游 `properties.caliber` 从未被提取 | 新增 `tools/build_weapon_compat.py`、`data/gun-compat.json`、`data/gun-platforms.json`；`app.js` `rebuildSimGunOptions()` / `renderSimGun()`；`style.css` |
| B | **弹药/弹匣兼容** | 弹药下拉列全部 200 条（只按口径分组）；根本没有弹匣型号选择，射速/弹药/弹匣三者无关联 | `app.js` `simAllowedAmmo()` / `simAllowedMags()` / `renderSimAmmoOptions()` / `renderSimMagPicker()` / `amSimOnGunChanged()` / `amSimBuildEngineCfg()`；`combat_sim.js` `constraints` 校验 |
| C | **压弹窗口** | 原来只有「下拉 + 数量 + 装入」一行 | `app.js` box1 重构（loader head / rows / footer / mag icon）、`renderSimMagList()`、`renderSimLoaderHead()`、`sim-mag-up/down`；`style.css` `.am-sim-loader*` |
| D | **Boss 插板池** | 插板候选 = 护甲 socket 的全部兼容板，与 Boss 无关；`bosses.json` 没有「Boss 实际带哪块板」 | `tools/build_boss_data.py`（默认插板取该护甲**游戏默认预设**的 `containsItems` 顺序并校验落在对应插板槽）；`app.js` `amSimPlatePolicy()`（按面白名单）+ `amSimApplyBossDefaults()` |
| E | **Boss 全量** | 只有 4 个 Boss，且无护卫/精英分类 | `data/bosses.json` 重建为 **17 Boss + 4 精英**（schema 仍为 1，新增 `revision`/`elites`/`followers`/`defaultPlates`）；`docs/r16-completeness/boss-loadouts.json` |
| F | **方向性护甲** | 层按 `KIND_RANK` 串成一条链，前板与后板都进同一条入体前链路 | `combat_sim.js`：`dir` 输入、层 `side`、`sideMatches()`、`layersSkipped`、`exitModel`（默认关）；`app.js` 方向选择 + `amSimSideFromZone()` + 日志方向列/未经过层/出口事件 |
| G | **左栏滚动 + 按钮** | `.am-sim-cfg` 无独立滚动，长表单被裁切；按钮在末尾 box6 | `style.css`（`max-height/overflow-y/sticky/窄屏单列`）、`app.js` 顶部 `am-sim-runbar` |
| H | **界面联动** | 换枪/换目标后旧弹药、旧弹匣、旧插板会残留 | `amSimOnGunChanged()`、`target-kind`/`target-pick` 清空并重落预设、`armor-pick` 清插板、方向变更重渲染护甲面板 |

辅助：`tests/test_r16_completeness.py`（27 项）、`tests/js/combat_sim_r16_test.js`、`docs/r16-completeness/`（8 个文件 + 8 张截图）。

## B. Boss 完整性（详见 `boss-roster.md` / `boss-loadouts.json`）

- **正式 Boss 17**：Killa 890、Reshala 752、Shturman 812、Tagilla 1220、Glukhar 1010、Sanitar 1270、
  Kaban 1300、Kollontay 1055、Partisan 950、Knight 1120、Big Pipe 910、Birdeye 795、Zryachiy 1655、
  Shadow of Tagilla 1305、Vengeful Killa 960、The Wedge 880、Santa Claus 1040。
  **17/17** 血量逐项和 == 页面标注总量（脚本校验）。
- **精英 4**（独立目标类型）：Cultist Priest 850、Cultist Warrior 850、Rogue 775、Black Division 790。
- **护卫**：8 个 Boss 有独立护卫血量表（Reshala / Shturman / Glukhar×3 / Sanitar / Kaban×3 /
  Kollontay×2 / Zryachiy / The Wedge）；**护卫装备池全部 missing**（页面只有文字描述）。
- **默认插板**：12/17 有（5 个没有可识别护甲或预设无板：Partisan、Birdeye、Zryachiy、The Wedge、Santa）。
- **Tagilla 实例**：Crye AVS（Tagilla 版）+ Cult Termite（6 级）+ Global Armor’s Steel（4 级），
  UI 前/后下拉各只剩这一块，池外插板（含 1 级板）无法选入。
- **不可虚构的部分**：39 条 wiki 链接找不到物品 ID（帽子/货币/任务物品），逐条留在 `unclassified`；
  Raiders 页面是重定向、无血量表 → 不提供 Raider 目标。

## C. 前后插板机制（详见 `armor-direction-research.md`）

| 情形 | 当前计算路径 |
|---|---|
| 正面命中前插板 | 只经过 `side=front` 的硬板 → 前软内衬；后板/后内衬进 `layersSkipped`，**不参与减伤、不掉耐久** |
| 正面命中无前板覆盖 | 链条为空或只剩软甲，人体吃满伤害；不会因为「有后板」而减伤 |
| 背面命中 | 对称处理：只过后板与后软甲 |
| 左/右侧命中 | 只过该侧侧板（若有），前/后板都跳过 |
| 穿过躯干撞后板 | 仅当 `exitModel='estimate'` 时作为**入体后的独立事件**计算，只扣对侧板耐久并单独记账；人体伤害与关闭时逐位相等（测试锁定） |

不确定性：出口碰撞的 `0.6/0.35` 系数无依据；社区报告可能源于命中框/旧版本，**不当作官方规则**。

## D. 测试与验收（详见 `test-report.md`）

```
修改前：python -m pytest -q → 757 passed, 1 skipped (49.84s)
修改后：python -m pytest -q → 784 passed, 1 skipped (54.11s)   # +27，无删除/跳过/弱化
node --check app.js / combat_sim.js → exit 0
node tests/js/combat_sim_r16_test.js ./combat_sim.js → 13 组场景
```

真实浏览器（Chrome 155 headless + CDP 9226，`tools/serve.py --port 8791`）：

- 分组 74 组（`5.56x45 · AR-15 平台` / `5.45x39 · AK 平台`…），口径筛选 20/19/18/15 把；
- M4A1：弹药 11、弹匣 24、默认 30 发；AK-101：弹药 11（同组）、弹匣 3（与 M4A1 零交集）；
- AKS-74N：5.45x39、弹药 13、弹匣 13；
- Tagilla：默认护甲 AVS、前 Cult Termite 6 级 / 后 Global Steel 4 级，每面仅 1 个候选；
- 正面/背面：日志出现「方向」列，并显式列出「本方向未经过：…」；
- 左栏 `scrollHeight 2256 / clientHeight ~637`，滚到底部 sticky 按钮仍可见；1264×705 无横向溢出；
- 目标切换（Boss→PMC）清空护甲/头盔/插板；四个主视图（地图/配装/配枪/弹药）逐个打开无报错；
- `consoleErrors=0`、`exceptions=0`、253 条请求全部 `127.0.0.1:8791`、**外部请求 0**。

截图：`docs/r16-completeness/screenshots/r16-01..08-*.png`。

## E. 网络与项目保护

| 项 | 实际情况 |
|---|---|
| 代理 | `http://127.0.0.1:7896` 实测可用（`json.tarkov.dev` 200、fandom API 200） |
| 本地直连 | 一律 `NO_PROXY=127.0.0.1,localhost,::1`；本地服务与 CDP 只走直连 |
| 失败记录 | fandom **HTML** 被 Cloudflare 拦（403/安全验证）→ 改用 MediaWiki API；`api.tarkov.dev/graphql` 返回 `GraphQL server unavailable`（未使用） |
| 运行期离线 | 页面所有请求均本地相对路径；`data/gun-compat.json`、`gun-platforms.json`、`bosses.json` 全部本地读取 |
| 构建期可复现 | 上游 JSON 缓存在 `build-cache/`（`items-regular.json`、`boss-wiki/*.json`），脚本可离线重跑 |
| Git | 未提交、未推送；工作区仍有 82 项未提交（含本轮新增文件），原有改动未动 |
| 既有功能 | 地图 / 路线 / 任务 / 配装工作台 / 配枪页未改；全量 784 项测试与四视图实测均正常 |
