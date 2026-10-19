# 规格：离线免费版《逃离塔科夫》互动地图（eft-interactive-map）

- 日期：2026-10-17
- 状态：设计已确认，待用户审阅本文档
- 形态：本地网页版（原生 HTML/CSS/JS）+ Python 标准库本地助手，打包为**双击 exe 启动**
- 数据策略：内置离线（构建期一次性拉取，运行期断网可用）
- 启动方式：**点击 exe → 显示带进度的启动框 → 就绪后自动打开浏览器进入 Web UI**

---

## 1. 背景与目标

用户希望拥有一个与 `kaedeori.com/app/interactive` 体验相近的《逃离塔科夫》互动地图，并且**免费、可离线、无外挂性质**。目标不是复制任何既有产品，而是**原创实现**：

- 底图与标注来自公开的、**MIT 许可**的 `the-hideout/tarkov-dev` 数据（见 §11）。
- 实时定位沿用社区公开做法：**监听 EFT 截图目录、解析截图文件名中的坐标**，**不读取游戏内存**。

### 目标（可验证）

1. **双击一个 exe**：弹出带进度的启动框，就绪后自动打开浏览器，进入可拖拽缩放、可切图、可开合图层的塔科夫互动地图。
2. 底图与标注数据全部本地化，**断网可用**。
3. 游玩时把玩家位置与朝向**实时**标在地图上（依据截图文件名解析，不碰游戏进程）。

### 非目标

见 §2、§12。

---

## 2. 边界与合规（硬性约束）

1. **不读取游戏内存、不注入进程、不做透视/自瞄等任何外挂类功能**；本项目**默认**与游戏进程零交互。
   两处例外都**默认关闭**、由用户在界面/文档中明确了解风险后自行决定：
   一是**可选的自动截图**（M5）：用 Windows `SendInput` 模拟按下游戏内截图键，属于「向游戏发送输入」
   而非读写游戏数据，因 EFT 带 BattlEye，**可能被反作弊判定为异常行为**；
   二是**可选的自动删除截图**（M6）：只删除**本工具自己监测的截图目录**里、开关开启后产生的图片文件，
   不触碰任何游戏文件，删除**不可恢复**。
2. **不逆向、不复制 `C:\Program Files\tarkov-kaedeori-client`** 或任何商业客户端的代码/资源。
3. **不复制 `BoringMan314/bm-tarkov-map-tracker`、`Leiserx/TarkovMap` 的代码**：二者在 GitHub 上 `license` 均为 `null`（保留所有权利）。仅可借鉴公开的做法与思路。
4. **不做联机服务器、不做用户数据上传、不做爬虫**。
5. 数据只取 MIT 许可的 tarkov.dev 公开数据；分发时保留来源署名。
6. EFT 商标与原始美术归 Battlestate Games；本项目仅供个人免费使用，公开分发时须注明来源与免责。

---

## 3. 范围与分期

### M1 —— 静态互动地图（离线，含 exe 启动器）

- **exe 启动器**：双击 exe → 启动框显示进度（检查数据 → 启动本地服务 → 载入资源）→ 就绪后自动打开浏览器进入地图页；窗口保留为"运行中"状态（可最小化/退出）。
- 地图选择（下拉/侧栏）。
- 拖拽平移、滚轮缩放、复位。
- 基础图层开关：**撤离点 / 过境点 / 出生点**。
- 点击标记查看详情（名称、类型、坐标）。
- 搜索标记名称并高亮。

### M2 —— 实时定位（截图目录监听）

- `tools/serve.py` 起本地服务，托管静态站点并经 **SSE** 推送玩家位置与朝向。
- 轮询 EFT 截图目录，解析文件名中的坐标与朝向。
- 页面上实时显示玩家点与朝向箭头；支持自动居中、手动锁定。

### M3 —— 图层扩充与多楼层（2026-10-18 起实施）

- 数据面：`data/maps.json` 升到 **schema 3**，在原有撤离/过境/出生点之外补齐
  **危险区（雷区/狙击区，带多边形轮廓）／钥匙门与后备箱／物资容器／散落物资／Boss 刷新点／炮击区／BTR 停靠点**。
- 楼层：每图带 `svgLayers`（底图里真实存在的顶层 `<g>`）与 `floors`
  （`root` 主层、`bands` 可判定高度波段、`switchable` 上游登记的可切换层、
  `selectable` 左侧列表用的可选层（含上游没登记但底图里确实存在的层）、`default` 默认显示层）；
  由上游 `layers[].extents[].height/bounds` 推出，判定规则与上游一致。
- 界面：图层开关按分组列出全部图层；多层图出现楼层列表（全部／单层），
  可跟随截图里的高度 `y` 自动切层，并按楼层过滤标记（标记没有高度信息时一律显示，不猜）。
- 底图换层：直接切 SVG 顶层组的 `display`，不再做旧的「只留一层」子树裁剪。
  只选一层时，**比它低的楼层以 `opacity: 0.25` 半透明垫在下面**（看清方位关系），
  比它高的仍隐藏（否则会挡住视线）；跨层共用的组（楼梯等）不参与这套显隐。
- 物资按容器类别拆开关：容器的类别在构建期按上游 `lootContainers[].normalizedName`（slug）归到 **14 类**
  （对齐参考站 tarkov.kaedeori.com 的图例：保险箱、夹克衫、机箱、Scav尸体、抽屉、旅行包、彩蛋点、
  医疗物资、物资箱、塑料手提箱、工具箱、收银机、手雷箱、武器箱），
  写进每个容器的 `group`；前端每个类别一个复选框、一种配色、一个小图标。
  **不能用中文译名分类**：同一容器有多种译名（`medbag` 既叫「SMU06 医疗包」也叫「SMU06医疗包」）。
  两处按实用习惯合并：`wooden-crate`（木制板条箱，只出弹药）并入武器箱；四类尸体并成「Scav尸体」。
  认不出的 slug 归 `misc`（其他容器）：照常渲染、**不丢点**，但侧栏只在该图真有这类容器时才显示这一行。
- 物资的呈现（M7）：容器点位画成**贴近实物的小图标**（保险箱有转盘、工具箱有提手、尸体是骷髅…），
  侧栏图例用同一套图标；图层开关**默认全开**（否则打开地图看不到物资点，会被当成「物资点丢了」）。
  「其他」组新增**固定武器**（`stationaryWeapons`，NSV / AGS 这类架设武器）。

### M4 —— 日志监控、运行期配置与提示音（2026-10-18 起实施）

- **日志监控**（新增 `tools/eftlog.py`）：跟随**游戏目录下 `Logs` 里最新会话文件夹**，按行文本匹配四个通道
  （`application` 战局生命周期、`backend` 请求行、`push-notifications` 任务 JSON、`errors` 任务失败）；
  产出 `raid`（matching / map / loading / start / end + mapId + raidId）与 `quest`（started / completed / failed，含奖励件数）事件。
- **进图自动切图**：日志里的地图 id 经 `MAP_ID_ALIASES` 映射到本项目地图 key
  （`bigmap→customs`、`sandbox_high→ground-zero`、`tarkovstreets→streets-of-tarkov`、
  `factory4_day/night→factory`、`shopping_mall→interchange`、`rezervbase→reserve` 等），
  映射大小写不敏感；已在该图不重复切换；未收录的图只提示不切。
- **任务事件流**：左侧「战局与任务」面板显示阶段 / 地图 / RaidId / 会话名，以及**本局**接取与完成计数、
  事件流（时间、动作、任务 id、奖励件数）。计数在本局开始时归零。
- **如实登记的任务进度局限**：日志只给推送通知 → 无条件级进度、无任务中文名（只有 id）、不做跨会话累计。
- **运行期配置**（新增 `tools/config.py`）：`eftmap.config.json` 落在**软件目录**（frozen 时取 exe 所在目录，
  不是 `_MEIPASS`），原子写；`normalize` 把任意脏输入收敛成完整正确类型；读失败一律回退默认、不抛异常。
  项：`game_dir` / `screenshots_dir` / `auto_zoom` / `auto_center` / `auto_start` /
  `auto_screenshot.{enabled,interval_ms,key}` / `sound.{enabled,<key>.{on,file}}`。
- **目录自动定位**：命令行 → 配置 → 自动探测（环境变量 `EFT_GAME_DIR`、常见盘符裸名、常见安装路径）；
  找不到就留空，由用户手填或浏览选择（**不猜、不硬塞**）。
- **定位自动缩放 / 点位自动居中**：拿到位置后按最近一次手动缩放比例（首次 4×）缩放并居中；
  原「跟随」**改名复用**为「自动居中」，不新增重复开关。
- **声音提示**：总开关 + 三个子开关（战局开始 / 开始加载战局 / 开始匹配），每个可选自定义音频文件；
  选取后**复制进软件目录 `sounds/`**（配置只存文件名，换机不丢），未选则用内置 Web Audio 提示音。
  受浏览器自动播放策略限制，需一次用户手势解锁。
- **启动器改为「设置与启动」小窗**：目录行（自动定位 / 浏览…）、地图显示开关、声音分组、状态区，
  底部「启动 WebUI」+「自动启动 WebUI」；**服务不再随窗口自动启动**。

### M5 —— 自动截图（2026-10-18 起实施）

- **目标**：让实时定位在战局中**持续刷新**——按间隔让游戏自己截图，截图文件名里的坐标随之更新。
- **实现**（新增 `tools/keyinput.py` + `serve.AutoShotter`）：Windows `SendInput` 注入
  **按下 + 抬起**，走**扫描码**（`wVk=0` + `KEYEVENTF_SCANCODE[|EXTENDEDKEY]`，DirectInput 类输入才收得到）；
  非 Windows / 不支持的键（鼠标键等）返回原因、**不误点**。
- **三个门条件**（全满足才发键）：① `auto_screenshot.enabled`；② 日志阶段 == `start`（在战局中）；
  ③ 前台窗口进程名 == `EscapeFromTarkov.exe`（模拟按键只能打到前台窗口）。
- **截图键从日志同步**：游戏启动时把整套控制绑定打成 JSON 写进会话日志**开头**
  （`application_000.log` / `output_000.log`），其中 `{"keyName":"MakeScreenshot","variants":[{"keyCode":["V"]},...]}`
  即游戏内截图键；`eftlog.read_screenshot_key()` 只扫**文件头 ~8 MiB**，`LogFollower` 按会话缓存结果。
  `auto_screenshot.key` 为空时运行期自动回落到该同步值。
- **配置**：`auto_screenshot.{enabled,interval_ms,key}`；间隔钳在 **200–60000 ms**（太短会让截图目录爆炸）。
  **默认关闭**。
- **界面**：启动器新增「自动截图」分组（总开关 / 间隔 / 按键 /「从日志同步」/ 反作弊与磁盘增长提示），
  开窗时按键为空则静默同步一次；页面「战局与任务」面板新增一行状态
  （间隔 / 按键 / 已发送张数，未在拍时附原因）。`shot` 状态同时挂进 `/api/health`、`/api/logstate` 与 SSE。
- **风险如实登记**：EFT 带 **BattlEye**，模拟输入**可能被判定为异常行为**，默认关、由用户自行决定；
  截图目录会随间隔持续增长；游戏不在前台时不发键（刻意，避免误打到别的窗口）。

### M6 —— 读出位置后自动删除截图（2026-10-18 起实施）

- **目标**：开启自动截图后截图会持续堆积，让工具在**读出位置之后**把多余老截图删掉，
  免去手动清 `文档\Escape from Tarkov\Screenshots`。
- **实现**（新增 `tools/screenshot.py` 清理区 + `serve.ScreenshotPruner`）：
  `select_deletable(directory, cutoff, keep_newest)` 只**挑选**文件名（便于单测），
  `delete_files()` 真删且失败静默跳过，`prune()` 组合两者；`ScreenshotPruner` 后台线程按轮询周期跑 `poll_once()`。
- **三条安全规则**：
  1. **只删「能解析出位置」的截图**——`parse_screenshot_name` 返回 None 的文件一律不碰；
  2. **保留最新 `keep_newest` 张（=1）**——实时定位依赖最新一张，删了会断（见 8.4）；
  3. **时间闸 `cutoff`**——只删「开关由关变开那一刻之后产生」的文件（按 mtime）。
- **先布防再删**：首次开启（或手改配置把 `since` 清空）时，`poll_once()` 先把当前时刻写进
  `auto_delete.since` 并**跳过本轮**，防止「首次打开即清库」。
- **配置**：`auto_delete.{enabled,since}`，**默认关闭**；`since` 由启动器在「关→开」时记 `time.time()`、关掉即清空。
- **界面/接口**：启动器「自动截图」分组内新增复选框（含「只保留最新 1 张供定位」与不可恢复提示）；
  页面「战局与任务」面板新增一行 `clean` 状态；`clean` 同时挂进 `/api/health`、`/api/logstate` 与 SSE 命名事件。
- **风险如实登记**：删除**不可恢复**；只删开关开启后产生的文件；`server_close` 会停掉 `ScreenshotPruner` 线程。

### M7 —— 物资 14 类细分与图标化（2026-10-18 起实施）

- `data/maps.json` 升到 **schema 4**：容器 `group` 由 7 类改为 14 类（见 §3 M3），新增 `layers.stationary`。
- **缩放清晰度（重要工程约束）**：底图与覆盖层始终是纯矢量，缩放走 `viewBox`（见 §7），
  标记点尺寸恒定靠节点上的 SVG `transform` + `scale(1/z)`。**绝不能给 SVG 元素加 CSS
  `animation` / `transform` 动效**——那会让浏览器把整个 `<svg>` 提升为合成分层并按当前倍率栅格化，
  之后再用 `viewBox` 放大就是放大一张已栅格化的位图，整张图（连地名文字）一起变糊。
  这正是「一放大地图就变糊、原本清楚的字也变糊」的成因；选中高亮环因此改为静态描边（不再脉冲动画）。
  另在 `#map-svg` 与地名文本上声明 `text-rendering / shape-rendering: geometricPrecision`。

### M8 —— 图例重做、出生点图层校正、上锁的门看钥匙（2026-10-18 起实施）

- **删掉「Boss 护卫出生点」图层**：上游 `spawns` 里带 `boss` 类别的点绝大多数是
  `["boss","bot","player"] 共用出生区`（街区 420 个出生点里 183 个是这种共用区，包围盒几乎盖住整张图），
  单独列成一层会让人误以为「Boss 护卫全图刷新」。Boss 本身由 `layers.bosses`（Boss 刷新点）覆盖，够用。
- **改名**：`spawn_pmc` 由「AI PMC / 掠夺者」改为「AI PMC 出生点」（`PmcBot` 与 raider 是同一单位的两种叫法），
  详情里的类别文案同步改为「AI PMC」。
- **图例重做（对齐参考站）**：分组改为 撤离点 / 过境点 / 物资 / 出生点 / 钥匙与门 / 危险区域 / 其他，
  `bosses` 并入「出生点」组；每行 = 彩色小图标 + 名称 + **右侧计数**（按当前地图统计，不随楼层过滤跳动）；
  分组标题与每行之间加细分隔线；未勾选的整行压暗。
- **上锁的门显示钥匙名**：构建期新增 `ITEMS_ZH_URL`（`json.tarkov.dev/{mode}/items_zh`，缓存到
  `build-cache/items_zh.json`），把 `locks[].key` 的物品 id 解析成中文钥匙名，写入点位的 `keyName` / `keyShort`
  （解析不到就不写，前端退回显示 id）。运行期点门 / 后备箱时，在**图例对应那一行右侧弹小浮窗**写出所需钥匙，
  8 秒自动收起，换图或点别处也收起。
- **工程教训（重要）**：图例 DOM 会随数据到达 / 换图重绘，**监听必须用事件委托挂在容器 `#layer-toggles` 上**。
  之前把 `change` 监听逐个绑在 checkbox 节点上，`renderLayerToggles()` 一重建就把监听一起丢了，
  表现为「取消勾选后地图上还照样画着」。现在改为容器级委托 + `syncLegendState()` 同步压暗状态。

### M9 —— 转移点并入撤离组、高级资源点、撤离点徽章款式（2026-10-18 起实施）

- `data/maps.json` 升到 **schema 5**（M8 的 `keyName` + 本节的 `layers.valuables`）。
- **「过境点」改称「转移点」并合并分组**：图例第一组由两个分组（撤离点 / 过境点）并成
  「撤离点 / 转移点」一组共 4 项（共用撤离点 / PMC 撤离点 / Scav 撤离点 / 转移点）；
  `KIND_LABEL.transits` 等文案同步改为「转移点」。
- **新增 `layers.valuables`（高级资源点）**：与「散落物资」同源（上游 `lootLoose`），
  构建期按物品池筛出高价值的那部分——判定名单是 `HIGH_VALUE_ITEMS`（**中文物品名**，不用 id：id 随版本变），
  含实体比特币、私酒、LEDX、便携式除颤器、各色实验室钥匙卡、Object #21WS / #11SR 钥匙卡、稀有钥匙。
  点带 `items`（该点可能刷出的中文物品名，去重），详情里显示「可能刷出」。
  注意：上游另有 7 张**没有 SVG 底图**的图（破冰船 `icebreaker`、实验室 `the-lab` 等）也有这类刷点，
  本项目不收录那些图，所以名单里少数物品（如 Boreas 破冰船钥匙卡）在当前产出里数量为 0，保留以备将来补图。
- **撤离点 / 转移点画成徽章**（照参考站截图）：彩色盾牌 + 奔跑小人，**图标正下方是该点的名字**，
  按阵营配色（PMC 橙红 `#e2542a` / Scav 黄 `#e5a72c` / 共用青 `#46d3e8` / 转移绿 `#3ed467`），
  图例里用同款小徽章。名字用 `paint-order: stroke` + 深色描边保证压在底图上仍清晰。
  形状是纯路径（`BADGE_SHAPE` + `BADGE_RUNNER`），零依赖、不用图标库。
- **图标与文字仍按屏幕像素恒定**：徽章与名字都在 `g[transform=scale(1/fit)]` 里，
  再由 `markerScaleNodes` 的 `scale(1/z)` 抵消缩放；文字的字号 / 描边同样乘 `unit`，
  避免放大后字变得巨大。选中高亮环对图标 / 徽章按外接尺寸取（容器与高级资源点 ±10、徽章 ±11 屏幕像素）。

### M10 —— 配色纠正、位置类图标化、地图名覆盖 bug（2026-10-18 起实施）

- **撤离点配色纠正**（上一版记反了）：PMC 撤离点 = 绿 `#37c46a`、Scav 撤离点 = 黄 `#e5a72c`（不变）、
  合作 / 共用撤离点 = 蓝 `#4a9fe8`、转移点 = 红 `#e2513c`。
  `--extract-*` / `--transit` 三个色变量与 `.emk-badge-*` / `.emk-tag-*` 同步改。
- **新增位置类图标体系 `SIGN_ICONS`**（`app.js`）：出生点、Boss、狙击手、上锁的门、BTR、高级资源点不再用半径圆点，
  改画手绘 SVG 图标（**零依赖，照参考站截图重现形状，不引第三方素材**）：
  - 出生点 = 向下的三角标，颜色按图层区分：玩家绿 `#37c46a` / AI PMC 蓝 `#4a9fe8` / AI Scav 橙 `#e58b2c`
    （颜色由 `.emk-layer[data-layer="spawn_*"] .emk-sign` 的 `--c` 给，不是内联）；
  - 狙击手 = 圆环 + 内嵌 X 的准星（`disc` + `cross`）；
  - Boss = 骷髅头（`light` 白骨 + `dark` 眼窝 / 鼻孔）；
  - 上锁的门 / 后备箱 = 黄色挂锁 + 深灰锁梁（`bar` + `lockbody`）；
  - BTR 停靠点 = 红色八边形 `#e2513c`；
  - **高级资源点按物品取各自对应的图标**：`VALUABLE_ICON_RULES` 按中文物品名匹配
    （比特币→金币、钥匙卡→卡片、钥匙→钥匙、酒→酒瓶、LEDX/除颤/注射→医疗十字盒，都不中就退回宝石），
    颜色写在 `SIGN_COLORS` 里、内联给 `--c`（同一图层里要按物品区分颜色）。
- **图例同步换图标**：`legendIcon()` 对有 `spec.icon` 的行用 `signIconSvg()`，
  高级资源点用宝石；颜色由 `LEGEND_COLORS`（`dot-*` → CSS 变量）给。
- **图标仍需按屏幕像素恒定**：位置图标与物资图标一样在 `scale(unit)` 里，靠 `markerScaleNodes` 的 `scale(1/z)` 抵消；
  所有描边一律 `vector-effect: non-scaling-stroke`，且**不给 SVG 元素加 CSS 动画 / transform**（M8 的教训，会触发整张 SVG 栅格化）。
  选中环对图标图层统一按 ±10 屏幕像素取（`ICON_KINDS`）。
- **修复地图名被物品名覆盖的 bug**：`build_map()` 里抽高级资源点的内层循环把变量写成了 `name`，
  与同函数 L321 算好的地图名同名，导致 `return` 里 `"name": name` 取到的是该图最后一个地面物品的中文名
  （所以十张图分别显示成「酒店215房间钥匙」「海关 Tarcone 主管办公室钥匙」这类）。
  循环变量改名 `item_name`，并补回归测试 `test_build_map_map_name_survives_valuables_pass`。
  修完重跑 `tools/fetch_data.py`（走 `build-cache/` 离线）重新生成 `data/maps.json`。

### 后续（已登记，尚未实现）

任务标记与任务追踪、自定义标记(pin)、任务物品图标。

---

## 4. 目录结构

```
eft-interactive-map/
├── index.html              # 单页互动地图
├── style.css               # 样式（深色战术主题）
├── app.js                  # 渲染与交互（SVG 平移/缩放/图层/搜索/标点）
├── assets/
│   ├── maps/*.svg          # 离线底图（tarkov.dev，MIT）
│   └── icon.ico            # exe 图标（卡带/战术风）
├── data/
│   ├── maps.json           # 地图清单 + 每图坐标变换 + 图层标注
│   └── meta.json           # 数据来源、拉取时间、tarkov.dev 版本
├── tools/
│   ├── fetch_data.py       # 构建期：从 tarkov.dev 拉 SVG + 数据（联网一次）
│   ├── floors.py           # 构建期：上游楼层配置 → 可切换层与高度波段
│   ├── launcher.py         # 运行期入口：设置与启动小窗 + 启动服务 + 打开浏览器
│   ├── serve.py            # 运行期：静态服务 + SSE + 截图监听 + 日志跟随 + 自动截图 + 自动删除（供 launcher 调用）
│   ├── eftlog.py           # 运行期：Logs 会话跟随，日志行 → 战局 / 任务事件（含截图键同步）
│   ├── config.py           # 运行期：eftmap.config.json 读写 + 自定义提示音导入
│   ├── keyinput.py         # 运行期：模拟按键（SendInput）+ 前台窗口进程判定
│   └── screenshot.py       # 运行期：截图文件名 → 坐标 / 朝向 + 清理挑选规则
├── build/
│   └── build.ps1           # 构建脚本：PyInstaller 打包 exe（含图标/数据）
├── tests/
│   ├── test_fetch_data.py
│   ├── test_floors.py
│   ├── test_coord_transform.py
│   ├── test_screenshot_parse.py
│   ├── test_config.py
│   ├── test_eftlog.py
│   ├── test_keyinput.py
│   ├── test_autoshot.py
│   ├── test_screenshot_prune.py
│   ├── test_launcher.py
│   └── test_serve.py
├── eftmap.config.json      # 运行期配置（gitignore；由启动器写入软件目录）
├── sounds/                 # 用户导入的提示音（gitignore）
├── docs/superpowers/specs/   # 本规格文档
└── README.md
```

---

## 5. 组件设计

### 5.1 静态站点（前端，零依赖原生 JS）

- **渲染**：SVG 作为底图载体。`app.js` 维护 `viewBox`/`transform` 实现平移缩放；标记以绝对定位或 SVG 子元素叠加，随缩放同步。
- **图层**：`data/maps.json` 里每个图层的开关状态驱动显隐，开关按分组列出（撤离/过境／出生点分类／危险区／物资／钥匙门／Boss/BTR／地名）；
  状态用 `localStorage` 记忆。面状图层（雷区、炮击区）画多边形而非点。
- **楼层**（M3）：多层图的楼层列表可切「全部／单层」，只切换 SVG 顶层组的 `display`；
  跟随模式下按截图高度 `y` 落在哪个高度波段自动切层；开「按楼层过滤」时隐藏不属于当前层的标记，
  **没有高度信息的标记一律显示**（不猜），炮击区这类整图级图层不参与过滤。
- **搜索**：对当前地图全部标记做子串匹配，命中项高亮并可选居中。
- **玩家层**：独立的玩家 marker + 朝向箭头，数据来自 SSE；有定位时显示，无则隐藏。
- **自动居中 / 定位自动缩放**（M4）：右上角按钮（原「跟随」改名）切换自动居中；拖动地图即切「已锁定」。
  开自动缩放后，位置到达时按最近一次手动比例（首次 4×）缩放并居中。
- **战局与任务面板**（M4）：`raid` / `quest` / `shot` / `clean` 事件驱动；显示阶段 / 地图 / RaidId / 会话名与本局计数、事件流，
  自动截图状态行（间隔 / 按键 / 已发送张数 / 未在拍原因，M5），
  以及一行自动删除状态（已删除张数 / 保留最新 1 张 / 未开启原因，M6）。
- **提示音**（M4）：`matching` / `loading` / `start` 三种阶段各一个提示音，可换成自定义音频（`/sounds/<file>`），
  默认用 Web Audio 合成音；首次需用户手势解锁（浏览器自动播放策略）。
- **无构建**：不使用任何打包器；`app.js` 以原生 ES module 组织，直接由静态服务或 `file://` 加载（M2 推荐从本地服务打开）。

### 5.2 `tools/fetch_data.py`（构建期，联网一次）

**实测确认的数据源（2026-10-17）**：

| 数据 | 地址 | 许可 |
| --- | --- | --- |
| 标注点（撤离/过境/出生点/BOSS…） | `https://json.tarkov.dev/{mode}/maps`（`mode` ∈ `regular`/`pve`/`season`，约 8.7 MB） | tarkov.dev 公开数据 |
| 中文名（图名 / `ex_*` 撤离点名 / `tr_*` 过境说明） | `https://json.tarkov.dev/{mode}/maps_zh`（约 22 KB） | 同上 |
| 物品中文名（上锁的门的钥匙名 + 高级资源点判定） | `https://json.tarkov.dev/{mode}/items_zh`（约 700 KB，`data` 为 `<物品 id> Name` / `<物品 id> ShortName` 的扁平表） | 同上 |
| 每图配置（`transform`/`coordinateRotation`/`bounds`/`svgPath`/`svgLayer`/`labels`） | `https://raw.githubusercontent.com/the-hideout/tarkov-dev/main/src/data/maps.json` | MIT |
| 底图 SVG | `https://assets.tarkov.dev/maps/svg/<Name>.svg` | 源仓库 `the-hideout/tarkov-dev-svg-maps` 为 **CC BY-NC-SA 4.0** |

**访问约束（实测踩坑，必须照做）**：
- `assets.tarkov.dev` 必须带**浏览器式 `User-Agent`**，否则 Cloudflare 返回 403；`json.tarkov.dev` 反之（默认头更稳）。
- 一律**不要用 `HEAD` 探测**；单个大文件超时留 ≥ 60s。
- `https://api.tarkov.dev/graphql` 实测返回 `{"errors":["GraphQL server unavailable..."]}`（服务端不可用），**不作为主源**；仅在 `--refresh-markers` 时作为可选补充。
- 纯 Python 标准库在部分网络下会被 Cloudflare 拦（error 1010），脚本需内置 `curl.exe` 兜底（Windows 自带）。

**行为**：
- 拉取后规范化输出到 `data/maps.json` 与 `assets/maps/*.svg`，写 `data/meta.json`（来源、许可、模式、拉取时间、上游版本）。
- 只保留 M1 需要的字段（撤离/过境/出生点 + labels），原始 8.7 MB 大文件落在 gitignore 的 `build-cache/`。
- 幂等：已有数据且未 `--force` 时跳过；失败**不破坏已有数据**，退出码非 0 并给出明确提示。
- `--maps a,b,c` 只拉指定图；默认集合为**有 SVG 底图的 10 张常用图**。

### 5.3 `tools/serve.py`（运行期，Python 标准库）

- 用 `http.server.ThreadingHTTPServer` 托管静态站点根目录。
- `GET /api/position`：返回最近一次解析到的玩家位置（JSON）。
- `GET /api/health`：自检（数据就绪、收录图数、实时定位 / 日志监控是否可用、目录与会话名）。
- `GET /events`：**SSE** 长连接；位置是**无名帧**（`data: {…}`），其余为命名事件
  `config` / `state` / `raid` / `quest` / `shot` / `clean`（`event: <name>` + `data: {…}`）。无 `Content-Length` 时按 HTTP/1.1 用
  `Connection: close` 表达流式，**不能**用标准库的 chunked（会给每帧再包一层长度前缀）。
- `GET /api/config`：启动器写入的运行期配置；`GET /api/logstate`：日志跟随状态 + 累积战局 / 任务快照 + `shot` + `clean`；
  `GET /sounds`（列表）与 `GET /sounds/<file>`（自定义提示音，`realpath` 前缀校验防越权）。
- 五个后台线程：**位置监听**（轮询截图目录，只在位置真的变了才广播）、**日志跟随**
  （`eftlog.LogFollower`，跟随最新会话，产出 `raid` / `quest` 事件）、**配置监听**（盯 `eftmap.config.json` 的 mtime，
  一改就广播 `config`，启动器里改开关页面立刻生效）、**自动截图**（`AutoShotter`，M5：三个门条件通过才发键）、
  **自动删除截图**（`ScreenshotPruner`，M6：读出位置后按三条安全规则清理），线程均随 `server_close()` 停止。
- 对文件系统的主动操作只有两项，**都默认关闭**：自动截图（`SendInput` 发键）与自动删除截图（删文件）；
  其余一律只读。
- 打开浏览器默认由 `launcher.py` 负责；`serve.py` 独立运行时可自行打开，亦可用 `--no-browser` 关闭。
- 默认端口 `8787`，被占用时可用 `--port` 指定。
- 参数优先级：命令行 → 配置 → 自动定位；`--no-logs` 可显式关掉日志监控（**「目录留空」也表达关闭意图，
  不会被自动定位顶回来**）。

### 5.4 `tools/launcher.py`（运行期入口 → `eft-map.exe`）

**「设置与启动」小窗**（560×600，tkinter）：目录分组（游戏目录 / 截图目录，各带「自动定位」「浏览…」）、
地图显示分组（定位自动缩放、点位自动居中）、声音分组（总开关 + 三个子开关，各带「选取音频…」）、
自动截图分组（总开关 + 间隔 ms + 按键 +「从日志同步」+ 反作弊与磁盘增长提示，M5；
外加「读出位置后自动删除旧截图」复选框 + 不可恢复提示，M6）、
状态区（`检查数据 / 启动本地服务 / 载入资源 / 打开浏览器`）与底部按钮行（启动 WebUI / 自动启动 WebUI / 打开界面 / 最小化 / 退出）。
**服务不再随窗口自动启动**：由「启动 WebUI」按钮触发，或勾上「自动启动 WebUI」后开窗即触发。

点击「启动 WebUI」后的流程（每步在状态区显示进度与状态文字）：

1. **检查数据**：确认 `data/maps.json` 与底图资源存在；缺失则提示（不静默联网）。
2. **启动本地服务**：调用 `serve.py` 起 `127.0.0.1:8787`（含 SSE、截图监听与日志跟随）。
3. **载入资源**：等待服务就绪/自检通过。
4. **打开浏览器**：调用系统默认浏览器打开 `http://127.0.0.1:8787/`。
5. **运行中**：提供「打开界面」「最小化」与「退出」（退出时关闭服务）。

- 视觉走 **Windows XP（Luna）简约风**：蓝色渐变标题栏、3D 凹凸控件、Tahoma 字体、朴素描边。地图 **Web UI 仍为深色战术风**。
- 任一步失败：显示明确错误与"重试/退出"，不静默失败、不留下半启动状态。
- 无图形环境时退化为纯控制台启动（先读配置再 `Startup.run()`），保证自动化/CI 里可用。
- 命令行参数：`--port`、`--screenshots <目录>`、`--game-dir <目录>`、`--config-dir <目录>`、`--no-browser`。
- 与 `serve.py` 的关系：`launcher.py` 是入口与界面壳，`serve.py` 是可被调用的服务模块（同时保留独立 CLI 以便测试）。
- **副作用只落两处**：`eftmap.config.json`（原子写，tmp + `os.replace`）与 `sounds/`（用户导入的音频）。
  frozen 打包后 `app_dir()` 取 **exe 所在目录**（不是 `_MEIPASS`），否则每次重启都丢配置。

### 5.5 `tools/config.py`（运行期配置，纯标准库）

- 唯一读写处：`eftmap.config.json`（软件目录）、`sounds/`（自定义提示音）。
- 配置键（M4/M5/M6）：`game_dir` / `screenshots_dir` / `auto_zoom` / `auto_center` / `auto_start`、
  `auto_screenshot.{enabled,interval_ms,key}`、`auto_delete.{enabled,since}`、`sound.{enabled,<key>.on,<key>.file}`。
- 纯数据结构 + 纯函数：`normalize(raw)` 把任意来源（手改 JSON、旧版本、半截文件）收敛成**完整且类型正确**的配置；
  读写路径全部可注入（便于单测）。
- `app_dir()`：frozen → `sys.executable` 所在目录；源码运行 → 仓库根。
- `save` 原子写（先写 `.tmp` 再 `os.replace`），避免半截文件把配置写坏；`load` 任何异常一律回退默认。
- `import_sound(src)`：把所选音频**复制**进 `sounds/`（重名加 `_1`/`_2` 后缀、源已在 `sounds/` 内则复用、
  非法扩展名拒绝），返回落盘文件名；`resolve_sound(name)` 返回存在的绝对路径或 `None`。
  配置只存文件名 → 换机器、重装、清缓存都不会因绝对路径失效而丢声音。

### 5.6 `tools/eftlog.py`（日志跟随，纯标准库）

- 只做**文件跟随 + 行文本匹配**（见 §8.2），不解析二进制、不挂钩子、不读游戏进程。
- 关键常量：`SESSION_RE`（会话目录名 `log_<日期>_<时-分-秒>_<版本>`）、`MAP_RE`（`scene preset path:maps/<id>_preset.bundle`）、
  `RAID_ID_RE`（`[Transit] …, RaidId:<hex>`）、`MATCH_END_RE`（`client/match/local/end`）、
  `QUEST_FAIL_RE`（`Quest with id <id> wasn't found!`）、`QUEST_START_SUFFIX` / `QUEST_DONE_SUFFIX`（`description` / `successMessageText`）。
- `session_base()` **从会话目录里的实际文件名反推** <会话名>（真实日志的文件名**不带** `log_` 前缀，只凭目录名拼会一字不中，
  兜底再退化为"去掉 `log_` 前缀"）。
- `split_balanced(text)` 按括号配平提取完整 JSON 对象（字符串内的括号不计），供跨行推送通知使用。
- 产出事件结构：`{"type":"raid"|"quest", "ts", "phase"/"action", "mapId"/"questId", "raidId"/"rewards", …}`。
- 快照含 `available` / `reason` / `session` / `logDir` / `gameDir` / `raid` / `quests`（任务上限 60 条）。
- **截图键同步**（M5）：会话日志**开头**有整套控制绑定的 JSON，`parse_controls_keys()` /
  `pick_screenshot_key()` 从 `keyBindings` 里取 `MakeScreenshot`；`read_screenshot_key(game_dir)` 只扫
  `application` / `output` 通道的**文件头**（`KEY_SCAN_BYTES ≈ 8 MiB`）；`LogFollower.screenshot_key()`
  **按会话缓存**（换会话才重扫），供 `AutoShotter` 回落使用。

### 5.7 `tools/keyinput.py`（模拟按键，纯标准库，M5）

- `lookup(name)`：键名 → `Key(vk, scan, extended)`；覆盖字母 / 数字 / F1–F12 / 具名键 / 小键盘 / 方向键，
  归一化（去空白、下划线、连字符 + 小写）后查表；鼠标键、组合键返回 `None`（**不误点**）。
- `send_key(name)`：Windows `SendInput` 注入**按下 + 抬起**，`wVk=0` 走**扫描码** + `KEYEVENTF_SCANCODE`
  （扩展键另加 `KEYEVENTF_EXTENDEDKEY`）；返回 `(ok, 原因)`，非 Windows / 不支持 / 被拦截都给原因。
- `foreground_process_name()` / `foreground_is(name)`：`GetForegroundWindow` → `GetWindowThreadProcessId`
  → `OpenProcess` + `QueryFullProcessImageNameW`，拿前台窗口进程全路径；取不到返回 `None`（安全降级）。
- 整个模块**不联网、不注入进程、不挂钩子**，只调用系统输入 API 与查询前台窗口。

---

## 6. 数据模型（`data/maps.json`）

```jsonc
{
  "schema": 5,
  "gameMode": "regular",
  "generatedAt": "2026-10-17T…Z",
  "sources": [ { "name": "…", "url": "…", "license": "MIT / CC BY-NC-SA 4.0" } ],
  "maps": [
    {
      "key": "customs",
      "id": "56f40101d2720b2a4d8b45d6",   // 上游 BSG 场景 id
      "name": "海关",
      "svg": "assets/maps/Customs.svg",
      "viewBox": [0, 0, 1062.4827, 535.17401],
      "svgLayer": "Ground_Level",        // 主层（底图 <g> 图层 id）
      "svgLayers": ["Ground_Level", "Second_Floor", "Third_Floor"],  // 底图里真实存在的顶层组
      "floors": {
        "root":       { "svgLayer": "Ground_Level", "label": "地面层", "minY": null, "maxY": null, "areas": [], "isRoot": true },
        "bands":      [ { "svgLayer": "Second_Floor", "label": "二层", "minY": 3.0, "maxY": 6.0,
                          "areas": [[x1, z1, x2, z2]] } ],   // areas 为空 = 该高度整图都算这一层
        "switchable": [ { "svgLayer": "Second_Floor", "label": "二层" } ],
        "selectable": [ { "svgLayer": "Ground_Level", "label": "地面层", "isRoot": true },
                        { "svgLayer": "Second_Floor", "label": "二层" } ],   // 由下到上：左侧楼层列表的顺序
        "default":    ["Ground_Level"]
      },
      "worldToSvg": {                    // svgX = a*x + b*z + c ; svgY = d*x + e*z + f
        "a": -0.99299, "b": 0, "c": 693.10,
        "d": 0, "e": 0.98374, "f": 301.99
      },
      "labels": [ { "text": "Big Red", "x": -215, "z": -119 } ],
      "layers": {
        "extracts":   [ { "name": "十字路口", "faction": "pmc", "x": 200.98, "y": 1.0, "z": -153.09 } ],
        "transits":   [ { "name": "前往储备站", "x": 650.64, "z": 124.94 } ],
        "spawns":     [ { "x": 569.05, "z": -54.53, "sides": ["scav"], "categories": ["player","bot"] } ],
        "hazards":    [ { "type": "minefield", "x": …, "z": …, "outline": [[x1, z1], …] } ],  // 无 outline = 退化成点
        "locks":      [ { "type": "door" | "trunk", "needsPower": true, "key": "物品 id",
                          "keyName": "宿舍118房间钥匙", "keyShort": "宿舍118", "x": …, "z": … } ],  // keyName M8；解析不到则不写
        "containers": [ { "name": "木制板条箱", "x": …, "z": …, "group": "weapon" } ],  // group 见 §M3/M7：14 类之一（或兜底的 misc）
        "loose":      [ { "x": …, "z": … } ],                       // 散落物资，只有坐标
        "valuables":  [ { "x": …, "z": …, "items": ["实体比特币", "LEDX皮肤透照仪"] } ],  // 高级资源点，M9
        "bosses":     [ { "name": "Killa", "where": "二楼", "chance": 0.35, "x": …, "z": … } ],
        "artillery":  [ { "x": …, "z": …, "outline": [[x1, z1], …] } ],  // 地图外沿的炮击/死亡区
        "btr":        [ { "name": "Emercom营地", "x": …, "z": … } ],
        "stationary": [ { "name": "NSV 重机枪", "x": …, "z": … } ]      // 固定武器（架设武器），M7
      }
    }
  ]
}
```

- 标注点存**游戏世界坐标** `(x, y, z)`；`worldToSvg` 是构建期算好的仿射系数，前端只做一次乘法即可落到 SVG `viewBox` 坐标系。
  `y` 可缺省（少数上游标注没有高度），缺省时该标记不参与楼层过滤。
- 系数由 `transform` + `coordinateRotation` + `bounds` + SVG 的 `viewBox` 推导（见 §7），并由单元测试锁定（含"所有标注点必须落在 viewBox 内"的自动校验）。
- `schema` 变更即视为产出过期：`data_ready()` 会判定为未就绪并强制重新生成，避免前端读到缺字段的旧数据。

---

## 7. 坐标变换

tarkov.dev 用 Leaflet `CRS.Simple` + 自定义 `transformation` 渲染，语义已从其源码读出（`src/pages/map/index.jsx`）：

```
# 输入：transform = [t0, t1, t2, t3]，rotation = coordinateRotation（度），bounds = [[xMax, zMin], [xMin, zMax]]，SVG viewBox = (0, 0, W, H)
c = cos(rotation), s = sin(rotation)
X' = x*c - z*s
Z' = x*s + z*c
pixelX = t0 * X' + t1
pixelY = -t2 * Z' + t3          # Leaflet 的 scaleY = -t2

# SVG 铺满由 bounds 两个角点在 pixel 空间构成的矩形，SVG 左上角 = 该矩形的最小 x / 最小 y
kx = W / (max(pixelX) - min(pixelX))      # 两个角点（xMax,zMin）与（xMin,zMax）之间取 min/max
ky = H / (max(pixelY) - min(pixelY))
svgX = (pixelX - min(pixelX)) * kx
svgY = (pixelY - min(pixelY)) * ky
```

构建期把上式展开成 `worldToSvg` 的 6 个系数（纯线性，前端只做 2 次乘法 + 2 次加法）。

- 底图矩形取上游每图配置的 `svgBounds`（有则用），否则取 `bounds`——两者可能不同（如储备站的 `svgBounds` 更高，用错会让标注整体纵向偏移）。
- `coordinateRotation` 逐图不同（海关 180°、工厂 90°、实验室 270°、部分图无旋转），上述公式统一处理，不写特例。
- 截图文件名给的是同一套世界坐标 `(x, z)`（y 为高度，本项目不用），与标注点共用 `worldToSvg`，因此**定位点天然与标注对齐**。
- **上游数据存在少量越界标注**：实测 10 张图里有几张的点落在底图矩形之外（如 Ground Zero 的 3 个撤离点属于 21+ 扩展区、工厂东侧几个出生点超出约 7%），这些点在上游站点同样位于底图范围外。策略：**数据照实保留、不静默丢弃**；前端按标注包围盒给底图留少量外边距，越界过多者自然被裁掉，并在「关于/说明」中登记该限制。
- **单元测试**覆盖：
  1. 底图矩形的两个角点经 `worldToSvg` 必须落在 `(0,0)` / `(W,H)`（容差 1e-6）；
  2. 每张图 **≥ 90%** 的标注点（撤离/过境/出生点/标签）落在 `[-1%, 101%] × viewBox` 内，并打印越界点清单——比例骤降即说明朝向或矩形推导错了；
  3. 海关若干已知 `(x, z)` → 期望 SVG 坐标的黄金值对照（锁定公式，防回归）。

---

## 8. 实时定位与日志监控机制

### 8.1 实时定位（截图目录）

1. `serve.py` 轮询截图目录，取最新文件；若与上次不同则解析。
2. 解析截图文件名中的坐标段与朝向段（**具体格式以真实样本确定**；编写单元测试覆盖正/异常样本，解析失败**不报错、不误报**，仅记录 limitation）。
3. 内存中更新"最新位置"，通过 SSE（`/events`）推给所有已打开页面；页面用 `EventSource` 接收并更新玩家 marker 与箭头。
4. 页面另以 `/api/position` 作首屏同步（SSE 未连通时的兜底）。

### 8.2 日志监控（`tools/eftlog.py`，M4）

1. `LogFollower(game_dir)` 的 `logs_dir = <game_dir>/Logs`；每轮取**最新的会话文件夹**
   （`log_<日期>_<时-分-秒>_<版本>`），换会话即清空偏移与解析器、从新会话开头重新接入。
2. 每个通道**独立记字节偏移**（`_offsets[path]`）做增量读；首次接入只回读尾部 1 MiB（避免把几 MB 旧日志全撸一遍）；
   文件被截断/重建时偏移归零；**最后一行若没有换行符就等到下次**，不解析半截行。
3. `LineParser.feed(channel, line)` 按行做正则匹配：`application` 出 `matching` / `map` / `loading` / `start`；
   `push-notifications` 是**多行 JSON**，用一个跨行缓冲按括号配平提取完整对象（字符串内的括号不计），
   再解析 `type` / `templateId` / `hasRewards` / `items.data`；`errors` 出任务失败。
4. 战局状态是**增量**的（地图 id 与 RaidId 出现在不同行），快照只留一条会丢上下文，
   因此用 `merge_raid(prev, ev)` 把前文串起来（新一轮 matching 时清空、end 时保留）。
5. 事件经 `publish_event("<type>", ev)` 以 SSE 命名事件 `raid` / `quest` 广播；快照由 `/api/logstate`
   与连接建立时的 `state` 事件下发（页面中途打开也能补齐）。
6. 只读文件、不注入进程、不改游戏文件；任何意外都不让监听线程死掉（`_loop` 内 `try/except` 续跑）。

### 8.3 自动截图（`serve.AutoShotter` + `tools/keyinput.py`，M5）

1. `AutoShotter` 线程（步长约 0.1s）**每轮都重新读配置**（`config.load(app_dir)`），
   所以启动器里改开关/间隔/按键后**无需重启服务**即刻生效。
2. **门条件**（全满足才发键）：① `auto_screenshot.enabled`；② `LogFollower` 快照里 `raid.phase == "start"`；
   ③ `foreground_process_name()` 的文件名 == `EscapeFromTarkov.exe`（模拟按键只能打到前台窗口）。
3. 满足后按 `interval_ms` 节流（`now - lastSentAt >= interval/1000`），调 `keyinput.send_key(key)`；
   截图键取 `auto_screenshot.key`，为空则回落到 `LogFollower.screenshot_key()`（日志同步到的游戏内截图键）。
4. 每次发键成功推一个 SSE 命名事件 `shot`（负载 = `AutoShotter.snapshot()`）；`shot` 快照同时挂进
   `/api/health`、`/api/logstate` 与连接建立时的 SSE 首帧，页面首屏即可显示。
5. 快照字段：`enabled` / `intervalMs` / `key` / `sent` / `lastSentAt` / `available` / `reason`；
   `reason` 如实写明当前为何没在拍（未开启 / 未取得按键 / 不在战局中 / 游戏不在前台 / 发送失败）。
6. 线程随 `_Server.server_close()` 停止（与位置 / 日志 / 配置监听一起），不留残线程。

### 8.4 自动删除截图（`serve.ScreenshotPruner` + `tools/screenshot.py`，M6）

1. `ScreenshotPruner` 线程与 `AutoShotter` 同频轮询（步长 0.1s），**每轮重新读配置**，
   启动器里改动开关即刻生效；同样随 `_Server.server_close()` 停止。
2. `poll_once()` 的分支顺序（决定安全性）：未开启 → 不动；截图为空 → 不动；
   `since` 为空（首次开启/被手改） → **先布防**（写 `since = now`）并跳过本轮；目录不存在 → 不动；
   否则调 `screenshot.prune(directory, since, KEEP_NEWEST)`。
3. `select_deletable()` 三条规则叠加后产出待删名单：`parse_screenshot_name` 非空、
   不在「最新 `keep_newest` 个」保护集合内、`mtime >= cutoff`。
   `delete_files()` 逐个 `os.remove` 并静默跳过失败项（文件被占用/已被删）。
4. **保留最新 1 张是功能正确性前提**：`PositionTracker` 依赖 `latest_position()`，
   目录里若一张可解析图都不剩，位置会被置空并广播 `available:false`，实时定位直接断。
5. 每轮真删到东西时推一个 SSE 命名事件 `clean`（负载 = `ScreenshotPruner.snapshot()`）；
   `clean` 快照同时挂进 `/api/health`、`/api/logstate` 与连接建立时的 SSE 首帧。
6. 快照字段：`enabled` / `since` / `keepNewest` / `deleted` / `lastDeletedAt` / `available` / `reason`。

---

## 9. 错误处理与降级

| 场景 | 行为 |
| --- | --- |
| 无网络（首次未拉数据） | `fetch_data.py` 明确报错并保留旧数据；站点可正常打开已有图 |
| 截图目录不存在/无权限 | `serve.py` 记录警告，停用实时定位，页面其余功能正常 |
| 截图文件名无法解析 | 忽略该文件，SSE 不推送脏数据；可打印调试日志 |
| 游戏目录/`Logs` 不存在或无会话 | 日志监控 `available=false` 并给出原因，页面显示"日志监控未启用"；其余功能正常 |
| 日志里出现没收录的图 | 只提示"识别到地图 X 但未收录"，**不硬切底图** |
| 自动截图：游戏不在前台 / 不在战局中 / 未取得按键 | 不发键，只更新 `shot.reason`（页面与 `/api/*` 可见），**绝不误打到别的窗口** |
| 自动截图：`SendInput` 被系统或安全软件拦截 | 记下原因、计数不增，下一轮继续尝试（不崩线程、不硬发） |
| 自动截图：按键不在支持范围（鼠标键、组合键、拼错的键名） | 视为「未取得有效按键」并给出说法，不发送 |
| 自动删除：开关首次开启 / `since` 被清空 | **先布防**（写入当前时刻）并跳过本轮，**一张都不删**，避免误清历史截图 |
| 自动删除：文件被占用 / 已被删走 | `delete_files` 静默跳过该文件，下一轮再挑到；**不抛异常、不崩线程** |
| 自动删除：目录里读不出位置的文件（手动菜单截图等） | 不纳入待删名单，**一律保留** |
| 自动删除：删到没得删（已只剩最新 1 张） | 保留最新 1 张供定位，`clean` 计数不增，实时定位不受影响 |
| 配置丢失/损坏/被手改坏 | `config.load()` 回退默认值不抛异常；`normalize` 逐项收敛类型 |
| 端口被占用 | `serve.py` 报错并提示用 `--port` 更换 |
| 前端定位失效 | 页面显示"定位不可用"状态，不阻塞地图浏览 |

---

## 10. 测试策略

- **Python 单元测试（pytest）**：`fetch_data` 的规范化与幂等、坐标变换往返、截图文件名解析（正/异常）、`serve` 的位置广播与 SSE 帧格式、`launcher` 的启动步骤编排（用桩件替换起服务与开浏览器，避免测试中真的弹窗/开浏览器）、`floors` 的楼层命名/波段判定/可选层推导，以及**容器类别覆盖**（14 类各 slug 唯一归属、实际产出里每类都非空、认不出的 slug 归「其他容器」、概览的 `containerGroups` 与 maps.json 完全一致）。
  M4 追加：`config` 的默认值/脏输入收敛/读写往返/原子写不留临时文件/损坏回退/音频导入（改名、不覆盖、复用、拒非法扩展名）与 `app_dir()`；
  `eftlog` 的目录与文件名契约、`split_balanced`（多行/未闭合/字符串内括号/两个对象）、`parse_notification`、
  各通道解析、**跨阶段保住 mapId**（`merge_raid` 的三个用例）、增量读与步进、换会话重连、最后一行截断、尾窗限制；
  `serve` 的 `/api/config`、`/api/logstate`、`/sounds` 列表与服务（含越权 404）、SSE `config`/`state`/`raid`/`quest` 帧、
  参数优先级（命令行 → 配置 → 自动定位）。
  M5 追加：`keyinput` 的键名归一化/键表（字母、数字、F 键、具名键、扩展键标志）/不支持键拒绝/
  `SendInput` 走扫描码的 INPUT 构造/非 Windows 降级/前台进程名比较；
  `config` 的 `auto_screenshot` 默认值、脏输入收敛、`clamp_interval` 边界（200/60000/负数/非数字/布尔）；
  `eftlog` 的控制绑定解析（`variants` 首个非空、字典与列表两种形状、头部截取生效）与 `read_screenshot_key`
  只取最新会话 / 回落 `output` 通道 / `screenshot_key()` 按会话缓存；
  `serve` 的 `AutoShotter` 三个门条件、间隔节流、配置键优先于日志同步键、发送失败与异常不外抛、
  `shot` 进 `/api/health` 与 `/api/logstate`、SSE `shot` 首帧、`server_close` 停线程；
  `launcher.build_config` 的 `auto_screenshot` 契约与间隔钳制。
  M6 追加：`screenshot.select_deletable` / `prune` 的挑选规则（只挑可解析、保留最新 N、时间闸保护历史、
  非图片忽略、目录缺失/空目录、量级样例首尾顺序）与真删（含跳过缺失文件的静默失败），
  并回归「清完仍能 `latest_position` 定位」；
  `serve.ScreenshotPruner` 的禁用不扫目录、无目录说明、**首次布防不删**（断言 `since` 落盘）、
  真删计数 + `clean` 事件 + 只留最新、空目录与目录不存在、垃圾文件不误删、prune 异常从 `poll_once`
  抛出但**线程遇错不死**、快照形状、`available` 两种为 False 情形、start/stop 安全、**后台线程真的会轮询**；
  `config` 的 `auto_delete` 默认值/脏输入收敛（坏 `since` → None、数字串接受）/读写往返；
  `serve` 的 `clean` 进 `/api/health` 与 `/api/logstate`、SSE `clean` 首帧、`server_close` 停 pruner 线程；
  `launcher.build_config` 的 `auto_delete` 契约（关闭时 `since` 必须为 None）与往返。
- **前端**：MVP 阶段以手工核对为主；关键交互（平移/缩放/图层/切层）可通过在浏览器中手测验证；不引入前端测试框架（保持零依赖）。
- 所有联网行为仅在 `fetch_data.py` 中发生，测试用本地样本与桩件，不触网。

---

## 11. 依赖与许可

- 前端：**零第三方依赖**（原生 JS/CSS）。
- 助手：**Python 3 标准库**（`http.server`、`json`、`os`、`threading`、`pathlib`、`tkinter` 等），零第三方。
- **打包（仅构建期）**：用 **PyInstaller** 将 `launcher.py` 打成 `EFTMap.exe`（含 tkinter）；运行期不依赖 PyInstaller。若打包不可行，退路是 `python tools/launcher.py` + 一个 `.cmd` 双击脚本（同样满足"双击启动 + 进度框"）。
- 数据许可（**分发时必须逐条署名**，写入 `README.md`、`data/meta.json` 与界面「关于」）：

| 来源 | 许可 | 义务 |
| --- | --- | --- |
| `the-hideout/tarkov-dev`（地图配置、翻译、API 数据） | **MIT** | 保留版权与许可声明 |
| 标注数据 `json.tarkov.dev` | 源自 tarkov.dev 社区数据 | 署名 tarkov.dev |
| 底图 SVG `the-hideout/tarkov-dev-svg-maps` | **CC BY-NC-SA 4.0** | 署名 + **非商业** + 同许可再分发（因此本项目的 SVG 底图部分不得商用，且需保持同许可） |

- EFT 商标/原始美术：归 Battlestate Games；本项目个人免费使用、不含任何游戏资源文件。

---

## 12. 未实现 / 不做（登记）

- 不读游戏内存、不注入、不做透视/自瞄类功能。
- 不做联机同步与他人位置显示。
- 不做爬虫、不上传任何用户数据。
- 不逆向商业客户端。
- 只读游戏写在磁盘上的截图与日志；**不改游戏文件、不挂钩子**。
- 仍不做：任务标记与任务追踪、自定义标记(pin)、任务物品图标（多楼层 / 战利品分类 / 日志自动切图已在 M3、M4 落地）。
- **不做账号级任务统计**（已完成 / 未完成 / 进行中 / 未解锁）：账号任务状态不在本地日志里（见 §15.1），
  需要联网才能获取，与「运行期不联网」冲突；页面只显示**本局**接取 / 完成 / 失败三类事件。

---

## 13. 交付物

1. 可运行的离线互动地图站点（`index.html` + `app.js` + `style.css` + `assets/` + `data/`）。
2. 构建期数据拉取脚本 `tools/fetch_data.py`。
3. 运行期助手：静态服务 + SSE + 截图定位 + 日志跟随（`tools/serve.py`、`tools/screenshot.py`、`tools/eftlog.py`）。
4. 运行期配置与提示音管理 `tools/config.py`（`eftmap.config.json` + `sounds/`）。
5. 启动器 `tools/launcher.py`（设置与启动小窗 + 启动 WebUI）。
6. **可双击的 `EFTMap.exe`**（小窗 + 进度 + 自动打开浏览器）及构建脚本 `build/build.ps1`。
7. Python 单元测试 `tests/`。
8. `README.md`（安装、拉数据、启动、定位/日志配置、来源署名与免责）。

---

## 14. 风险与缓解

| 风险 | 缓解 |
| --- | --- |
| **上游 API 长时间不可用**（`api.tarkov.dev/graphql` 实测已挂） | 改用 `json.tarkov.dev` 静态镜像（实测可用）；原始大文件落 `build-cache/`，打包只需精简后的 `data/maps.json` |
| 资源站 Cloudflare 拦截（403 / error 1010） | 按 §5.2 的头部规则请求；Python 失败自动回退 `curl.exe` |
| tarkov.dev 坐标系与截图坐标系不一致 | 统一用同一套 `worldToSvg`；"矩形角点必须映射到 (0,0)/(W,H)"与"≥90% 标注点落在 viewBox 内"的测试会在推导错误时立即失败 |
| EFT 截图文件名格式随版本变化 | 解析器宽容降级、不误报；以真实样本补测试 |
| 上游标注有少量点落在底图范围外 | 数据照实保留；前端按标注包围盒留少量外边距，越界过多者被裁掉；README 登记该限制 |
| 底图素材版权（BSG + CC BY-NC-SA） | 明确署名；**本项目非商业**；README 声明底图部分沿用 CC BY-NC-SA 4.0 |
| 地图资源体积较大 | 默认只内置 10 张有 SVG 的常用图（约 1.6 MB）；瓦片图（实验室/迷宫/破冰船）留待后续 |
| 端口/防火墙影响本地服务 | 仅监听 127.0.0.1；提供 `--port` 与 `--no-browser` |
| PyInstaller 打包 exe 被杀软误报或启动慢 | 优先 `onedir`（更稳、启动快）；必要时说明可源码运行；不加载任何可疑动态代码 |

---

## 15. 决策记录

### 15.1 已确认

- 形态：本地网页版（原生 JS）；启动方式：**双击 exe → 启动框(进度) → 自动打开浏览器**。
- 数据策略：内置离线（构建期一次性拉取 tarkov.dev 的 MIT 数据）。
- 实时定位：截图目录监听（**不读游戏内存**）。
- 首版范围：先做最小可用（M1）；实时定位在 M2。
- 项目落点：`d:\trae\blender\eft-interactive-map`。
- M1 地图规模：先内置**常用几张**（如海关、工厂、森林等），其余后续再补。
- 打包形态：**onedir**（`EFTMap.exe` + 依赖文件夹）。
- 启动框主题：**Windows XP（Luna）简约风**；地图 Web UI：深色战术风。
- exe 名称：`EFTMap.exe`（可改）。
- 版本管理：已 `git init` 并提交本规格。
- 自动截图（M5）：**默认关闭**，只在「已开启 + 在战局中 + 游戏窗口在前台」三条件全满足时按间隔发键；
  按键走 `SendInput` 扫描码，且按键名优先读日志同步（`MakeScreenshot`）。反作弊风险如实登记。
- 自动删除截图（M6）：**默认关闭**，只删「能解析出位置、且晚于开关开启时刻」的截图，
  **始终保留最新 1 张**供实时定位（这是功能正确性前提，非保守设置）；首次开启先布防、本轮不删。
- 账号级任务统计（已完成/未完成/进行中/未解锁）：**不做**。实测账号任务状态不在本地
  （`backend_000.log` 里的 `getMainQuestsList` 响应 body 未落盘；`output`/`errors` 里的 quest 命中均为 IL2CPP 符号；
  `%APPDATA%` 下只有 `Settings\*.ini`）。要账号级状态必须联网拉取，与「运行期不联网、只读本地文件」冲突。
  可视范围内只保留「本局接取/完成/失败」三类事件（M4）。

### 15.2 待确认（实现中可能调整）

- exe 图标：先用简约占位图标，后续可替换为你指定的图标。
- M1 收录的具体地图清单：实现时按 tarkov.dev 数据可得的常用图确定，并在 `README.md` 列出。
