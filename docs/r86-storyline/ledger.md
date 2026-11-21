# R86 剧情系统台账

日期：2026-11-05
范围：`data/stories.json` + 任务页第 5 视图「剧情」+ 地图剧情点深链
原则：不造数据结构；所有数据可回溯到 db4tarkov 客户端或 eftarkov 剧情页原文；每项改动配测试。

---

## 0. 一句话结论

剧情系统已可用：10 条剧情线、266 个步骤、4 个分支（含门票四结局）、剧情树、进度勾选、搜索/筛选/统计、
地图剧情点 → `#stories:<storyId>~<pointKey>` 深链跳转全部打通。缺口（步骤↔地图点位、Ladder、无名者 storyKey）
都在 `dataGaps` 里显式暴露，没有用假数据填。

---

## 1. 逆向结论（真实结构，不是推测）

### 1.1 db4tarkov 任务 / 剧情数据模型

证据：`docs/r39-live-price/main.dart.js.full`（Flutter Web 客户端，18MB bundle）。

Task 对象实际字段（GraphQL 映射，约 99645 行附近）：

| 字段 | 含义 | 剧情系统是否用到 |
| --- | --- | --- |
| `id` | 24 位十六进制任务/步骤 id | 是（步骤 id） |
| `name` | 名称 | 是 |
| `factionName` | 阵营 | 否 |
| `taskImageLink` / `wikiLink` | 封面 / Wiki | 否 |
| `minPlayerLevel` / `minPlayerLevelPVE` | 等级门槛 | 否（本轮） |
| `trader.name` | 发布者；**`"Story"` 是剧情伪商人** | 是（分组依据） |
| `experience` | 经验奖励 | 否 |
| `map.name` | 地图 | 是（地图 chip） |
| `taskRequirements[{task, status[]}]` | 前置任务 + 前置状态（completed / failed …） | 是（前置关系） |
| `objectives[]` | 目标列表（id / description / maps） | 是（步骤 + 地图点位定位） |
| `startRewards` / `finishRewards` | 接取 / 完成奖励 | 否 |
| `traderRequirements[{trader{name}, value, compareMethod}]` | 商人等级 / 声望门槛 | 否 |
| `scavKarma` / `lightkeeperKarma` / `refKarma` | 声望门槛 | 否 |
| **`storyVariable{variableId, compareMethod, value}`** | **剧情变量门控**（约 100760 行读取） | **是（分支 / 结局）** |
| `requireT[]` | 附加解锁条件 | 否 |

结论 1：**剧情线没有独立的 `storyline` 实体**。db4tarkov 用伪商人 `trader.name === "Story"`
（代码里判断写成 `l.w === "Story"`）把剧情任务从普通任务里切出来，剧情任务之间再用
`taskRequirements` 串成链。所以本项目的「剧情线」= 以 `story_*` 变量命名的 Story 任务簇。

结论 2：**结局不是布尔字段，而是剧情变量的取值**。客户端里存在剧情变量表（约 35480 行）：

```
story_the_ticket_ending -> ["survivor", "savior", "fallen", "debtor"]
story_falling_skies
story_boreas_prapor
story_boreas_btr
```

`$.hP` 负责把变量值映射成结局标签 / 图标；`$.drn` 把 `"new_beginning_p5"` 这类 id 解析成 part 序号。
剧情任务用 `storyVariable` 做门控：例：门票的后续步骤要求 `story_falling_skies` 已达到某个分支值。

结论 3：**还有 Ladder（阶梯）机制**（约 170950 行）。文案原句：
“Ladder: unlocks once you've completed enough {faction} quests…”。
实现是 `b5.y2`（阶梯）+ `b5.aS`（门槛数量）+ `b5.t`（比较符）+ `A.zi`（锁定态）+ `A.x1`（名称）：
完成同阵营任务数量达到门槛后整批解锁，不是单条前置。**本轮未落地**，见第 6 节。

### 1.2 eftarkov 剧情页 DOM（呈现层证据）

证据：`build-cache/eftarkov/storyline-*.html`（10 个页面快照 + index），来源
`https://www.eftarkov.com/storyline/<24位id>`。

| DOM 属性 / 类 | 含义 |
| --- | --- |
| `data-obj-id` | 步骤（objective）id |
| `data-story-sort` | 步骤 / 分支排序键 |
| `data-step-done` | 步骤完成态（站点侧，本地不用） |
| `.story-choice-card` | 分支卡（一个抉择） |
| `data-choice-key` | 分支键（如 `case_choice2`） |
| `data-source-key` | 该分支由哪条上游剧情触发的键 |
| `data-option-value` | 选项原始值（**站点顺序与中文标签顺序不一致**） |
| `data-story-og-group` | 页面分组 |

门票（`68da33fe00868edcb6025ac4`）真实四结局：

| 中文标签 | 语义值 | 站点原始 value 顺序 |
| --- | --- | --- |
| 救星 | `savior` | 第 1 |
| 幸存者 | `survivor` | 第 3 |
| 陨落之人 | `fallen` | 第 4 |
| 旧债沉疴 | `debtor` | 第 2 |

处理方式：构建器按语义重排为 `survivor / savior / fallen / debtor`，同时保留 `rawValue` 便于回溯，
测试 `test_ticket_has_four_real_endings` 断言这一映射。

---

## 2. 本地数据结构

生成器：`tools/build_stories.py`（可重复执行，输出确定：`ensure_ascii=False, indent=2` + 末尾换行）
输入：`build-cache/eftarkov/storyline-*.html` + `data/task-points.json`
输出：`data/stories.json`

```jsonc
{
  "schema": 1,
  "generatedAt": "...",
  "source": { "site": "eftarkov.com", "pages": [...], "db4tarkov": "main.dart.js", "points": "data/task-points.json" },
  "counts": { "stories": 10, "steps": 266, "choices": 4, "endings": 1 },
  "dataGaps": [ { "type": "orphan-points|step-without-map|no-story-key", "message": "..." } ],
  "stories": [
    {
      "id": "68da33fe00868edcb6025ac4",
      "slug": "the-ticket",
      "storyKey": "story_the_ticket",          // 对应 db4tarkov storyVariable.variableId
      "nameZh": "门票", "nameEn": "The Ticket",
      "steps": [ { "id": "<objectiveId>", "order": 10, "name": "...", "maps": ["customs"], "points": [...], "mapMatch": "prefix" } ],
      "choices": [ { "key": "case_choice2", "role": "ending|choice|prerequisite",
                     "title": "...", "desc": "...", "order": 110,
                     "options": [ { "value": "savior", "rawValue": "savior", "name": "救星", "desc": "...", "endingKey": "..." } ],
                     "variableId": "story_the_ticket_ending" } ],
      "prerequisites": [ { "storyId": "68cbcdc4...", "choiceKey": "case_choice", "options": [...] } ],
      "maps": ["customs", "..."],
      "stepCount": 23, "pointCount": 23,
      "sourcePage": "https://www.eftarkov.com/storyline/68da33fe00868edcb6025ac4"
    }
  ]
}
```

关键约定：

- `role`：`desc`/`title` 含「结局」→ `ending`；带 `data-source-key` → `prerequisite`；其余 `choice`。
- 步骤↔点位：先按完整 objectiveId 精确匹配；失败再按前 8 位匹配，且**同一前缀只归第一个步骤**，
  命中时标 `mapMatch: "prefix"`。匹配率低是真实数据缺口，写入 `dataGaps`。
- 10 条剧情线：They Are Already Here / Accidental Witness / The Unheard / Blue Fire / The Ticket /
  Batya / Boreas / Tour / The Labyrinth / Falling Skies。

---

## 3. 实现

### 3.1 视图（tasks.js）

- 第 5 个 tab：`["story", "剧情"]`；视图白名单统一加入 `"story"`。
- 骨架：`#tk-story` → `.tk-story-wrap` = 左索引（搜索 / 筛选 / 统计 / 列表）+ 右剧情树。
- 剧情树节点类型：`step`（可勾选完成）、`choice`（分支卡，含结局标签）、`pre`（前置剧情，可点击跳转）。
- 状态：`done / avail / locked` 三态，`is-focus` 高亮深链落点。
- 超过 12 步折叠，`data-story-expand` 展开/收起（实测 14 ↔ 25 个节点）。
- 空态：无匹配剧情线 / 加载中 / 加载失败各有文案；缺数据用 `dataGaps` 折叠块如实列出。
- 地图 chip 使用 `STORY_MAP_LABELS`（取自 `data/maps.json` 的 key → 中文名），不显示 `ground-zero` 之类原始 key。

### 3.2 进度与隔离

- `localStorage`：`eftmap.stories.progress.v1`（进度）、`eftmap.stories.ui.v1`（浏览状态）。
- 与任务进度 `eftmap.tasks.progress.v1` 完全分离；三模式 `regular / pve / pvps` 各一份。

### 3.3 深链与地图联动

- 路由：`#stories`、`#stories:<storyId>`、`#stories:<storyId>~<pointKey>`。
- `#stories` 与 `#tasks` 同等待遇：首屏直开（`app.js` 启动段 `deepStory`）、`hashchange` 消费、浏览器后退回地图。
- 地图剧情点（`story-<storyId>-<objectiveKey>`）→ `storyRouteFromGroupId` → hash；
  `unlock` 后缀视为无锚点。
- 浮窗跳转按钮 `.marker-pop-jump`（「打开剧情详情」）与右键菜单「剧情详细」两条入口。
- `?mini=1` 零影响：浮窗按钮带 `!state.mini` 守卫，小地图不消费 `#stories`，不改视图。

---

## 4. 验证

### 4.1 自动化

| 项 | 命令 | 结果 |
| --- | --- | --- |
| 全量测试 | `python -m pytest tests -q` | **1762 passed, 1 skipped** |
| R86 专项 | `python -m pytest tests/test_r86_story.py -q` | **15 passed** |
| 语法 | `node --check app.js` / `node --check tasks.js` | 均通过 |
| ES5 | `test_es5_only` | tasks.js 全文 + app.js R86 段无 let/const/箭头/模板串 |

环境说明：项目内未找到 `.venv-spike`（根目录、`02-塔科夫`、`d:\personal\trae` 递归均无），
本次使用系统 Python 3.14 的 `python -m pytest`。R84 基线为 1747，本轮新增 15 项 R86 专项，合计 1762。

### 4.2 浏览器冒烟（Chrome DevTools，localhost:8791）

| 场景 | 实测 |
| --- | --- |
| 首屏 `#stories:68da33fe...` | `view=story`，`storyReady=true`，列表 10 条 |
| 门票详情 | 标题「门票」，节点 14（折叠）/ 25（展开），结局卡 1 张 / 4 个选项，前置卡 1 张 |
| 筛选「含结局」 | 10 → 1 条 |
| 搜索「门票」 | 命中 1 条；搜索不存在词 → 空态文案 |
| 深层链接 `~6ab925ce` | 步骤解析为 `6ab925ce1100cc35cd200601`，`is-focus=1` |
| 勾选步骤 | `eftmap.stories.progress.v1` 写入 `steps.<sid>.<stepId>=true`，统计变 `1 / 266` |
| 选择结局 | 写入 `choices.<sid>.case_choice2="savior"`，`.tk-story-opt.is-on=1` |
| 展开/收起 | 节点 25 ↔ 14 |
| 地图剧情点 → 浮窗「打开剧情详情」 | 落到 `#stories:68da36cf7cff54fc6109874a~6ab8a9c4fdddc708c7cdb101`，剧情线 Batya，步骤已定位 |
| `?mini=1#stories:...` | menubar=none，context/status 缺失，无 `.marker-pop-jump`，无 `.gw-win`；hash 改成 `#stories:...` 后地图仍是 `#map-svg:block`，`.tk-story` 0×0 |
| 控制台 | error/warn 均为 0 |

布局修正记录：`.tk-story-wrap` 初版未撑满面板（实测 1043 / 1542 px），补 `flex:1 1 auto; width:100%`
后为 1542 / 1542，右栏 264 px 不变；地图 chip 由原始 key 改为中文名。

截图：本机 Chrome headless 在当前沙箱内无法落盘（MCP 截图接口也限制在工作区外），
因此本轮以 DOM 测量 + 上述实测数值为证据；截图待环境允许后补到本目录。

补充说明：`?mini=1` 下任务模块的骨架仍会被挂载（R77 起的既有行为，与剧情无关），
但 `.gw-win` 数量为 0、`#tk-story` 尺寸 0×0，不参与布局；本轮额外在 `applyTaskHashRoute`
入口加了 `state.mini` 守卫，hash 变化也不会把主视图切成任务/剧情。

兼容性回归：既有任务树 / 列表 / 详情 / 进度四个视图与窗口层、任务栏、小地图缩放、XP UI 的测试
全部包含在 1762 项里通过；本轮只改 `tasks.js` 的剧情分支、`tasks.css` 的 `tk-story-*` 段、`app.js`
的深链段，没有改任务渲染与地图渲染逻辑。

---

## 5. 哈希（SHA256）

| 文件 | SHA256 | bytes |
| --- | --- | --- |
| `data/stories.json` | `82267570d1a06aff5b3573a8ba29ed4d3c77dc35ac4b90d5362c2c0bdc518264` | 67002 |
| `tools/build_stories.py` | `764a7a3fd4f5fc153e22d2553b513998b1ef1d25754ef13faa63c242056c18b8` | 14938 |
| `tasks.js` | `c572ce1fe1a925802e0e18c19e719f8eb8cbf16381d6bfa0d5b9310307191fa6` | 196656 |
| `tasks.css` | `022da6f112ba214f9ca0495523253132b7da77017d9494256e663bb841f0b44e` | 58648 |
| `app.js` | `46054ad17fb6961b8a7f90a85cdfe4cbb95aec640f47537e1252734e875471b3` | 1221696 |
| `tests/test_r86_story.py` | `e58aa136c607db2a5744561875b9475d1d2244bf28e18173cc6f55e8e80d8108` | 9016 |

`data/meta.json` 未改：它是物品 / 枪械数据清单（`items` / `gunslots` / `icons` …），
不含 `stories` 条目；本轮也没有改任何既有 `data/*.json`，因此不存在哈希基线需要同步。
游戏版本仍以 `data/game-truth/meta.json` 的 `source.exe_version` 为准，本轮未触碰。

---

## 6. 未完成 / 下一步

1. **步骤↔地图点位匹配率**：门票 23 步仅 1 步精确命中，Batya 38 步命中 7。
   下一步从 db4tarkov `objectives[].id` 直接导出点位映射，替换「前 8 位 + 地图序号」的推断规则。
2. **Ladder（阶梯）**：按阵营完成数量批量解锁，尚未进入数据模型与 UI。需要新增
   `ladders[{faction, threshold, compareMethod, storyIds[]}]` 与树上「阶梯门槛」节点。
3. **无名者（The Unheard）没有 `story_*` 变量**：已写入 `dataGaps`，待确认它是否属于主线。
4. **结局图谱**：目前每条剧情线只展示自己的结局卡；跨剧情线的结局汇总视图（哪条线影响哪个结局）未做。
5. **进度导入导出**：任务进度已有导入导出，剧情尚未接同一套。
6. **奖励 / 等级 / 声望门槛**：db4tarkov 字段已逆向出来，UI 未展示。
7. **截图与视觉回归**：当前环境无法落盘截图，建议下一轮补 1024 / 1440 两张并接入视觉对比。

## 7. 需要拍板（未替用户决定）

1. 剧情进度是否要与游戏日志（`eftlog`）自动同步，还是保持纯手动勾选？
2. 是否要把 Ladder 做进剧情树（会影响树的层级与解锁语义），还是单独一个「阶梯」页？
3. 站点 `data-option-value` 与中文标签顺序不一致，当前按语义重排并保留 `rawValue`；是否接受这种处理？
