# R16 基线（修改前真实状态）

- 记录时间：2026-10-22 23:30 前后（本会话实际执行）
- 项目：`D:\personal\trae\02-塔科夫\eft-interactive-map`
- 代理：`http://127.0.0.1:7896`（外部访问）；本地一律 `NO_PROXY=127.0.0.1,localhost,::1`
- 运行环境：Windows，系统 Python **3.14.3** + pytest **9.1.1**，Node **22.22.2**
  （WorkBuddy 自带的托管 Python 3.13.12 **没有 pytest**，不能用它跑测试；`tests/*.py` 调用裸 `node`，需要 node 在 PATH）

## 1. Git 状态（修改前）

| 项 | 值 |
|---|---|
| 分支 | `main` |
| HEAD | `bf438df` 文档：交接手册记录第十五轮提交与三件套发布状态（2026-10-19） |
| 未提交 | 76 项：21 个已跟踪文件被修改 + 55 项未跟踪 |
| 关键未跟踪 | `combat_sim.js`、`data/{ammo,items,gun-rates,bosses,barriers,combat-targets,...}.json`、`tests/js/`、`tests/test_r1{0..5}*.py`、`docs/r1{0..5}-*/` |

本轮**没有**提交、没有推送、没有改动 `release/`。工作区原有改动全部保留。

## 2. 修改前测试基线（真实执行）

```
python -m pytest -q
757 passed, 1 skipped in 49.84s
```

- 该数字与 R15 报告一致，但不覆盖 R16 的六项目标。
- `node --check app.js` / `node --check combat_sim.js` 均为 exit 0。
- `node tests/js/combat_sim_r15_test.js ./combat_sim.js` 27 个场景，与 `docs/r15-fixes/scenario-output.json` 完全一致。

## 3. 修改前代码定位（R16 的落点）

| 目标 | 修改前实现 | 位置 |
|---|---|---|
| A 枪械分组 | 单一平铺下拉 163 项，无口径/平台信息（`data/gun-rates.json` 只有 `n/rpm/modes`） | `app.js` `renderSimGun()` |
| B 弹药/弹匣兼容 | 弹药下拉列出**全部 200 条**弹药（按口径分组），无弹匣型号选择 | `app.js` `buildAmmoSimPanel()` box1 |
| C 压弹窗口 | 一行「弹匣下拉 + 数量 + 装入 + 清空」+ chips | 同上 |
| D Boss 插板池 | 插板候选 = 护甲 socket 的**全部兼容板**，与 Boss 无关 | `app.js` `renderSimArmor()` |
| E Boss 名单 | 4 个（Killa / Reshala / Shturman / Tagilla） | `data/bosses.json` |
| F 方向性护甲 | 所有层按 `KIND_RANK = plate→helmet→liner` 串成一条链，前板与后板都会在入体前被依次计算 | `combat_sim.js` `sortArmorLayers()` / `resolveShot()` |
| G 滚动/按钮 | `.am-sim-cfg` 无独立滚动，长表单被窗口裁切；「开始模拟」在最底部 box6 | `style.css` `.am-sim-cfg`、`app.js` box6 |

## 4. 数据源可用性（实测）

| 来源 | 结果 |
|---|---|
| `https://json.tarkov.dev/regular/items` | **200**（直连与代理均可用，17.3 MB，构建期下载） |
| `https://escapefromtarkov.fandom.com/api.php`（MediaWiki API） | **200**（经代理 + 浏览器 UA；页面 JSON 缓存到 `build-cache/boss-wiki/`） |
| `https://escapefromtarkov.fandom.com/wiki/...`（HTML） | 403 / Cloudflare 安全验证，**不可用** → 改用 API |
| `https://api.tarkov.dev/graphql` | `GraphQL server unavailable`（本轮不可用） |

结论：Boss 数据改用 fandom **MediaWiki API 的 wikitext**（成功、可缓存、可离线重放），
不再依赖 HTML 抓取，也不依赖 GraphQL。
