# EFT 互动地图 · Agent 交接手册

> 交接时间：2026-10-19 · 版本 `0.1.0` · 数据 schema `7` · 路网 schema `1` · 测试 `555 passed`

---

## 0. 先读这一节：当前状态

| 项 | 状态 |
| --- | --- |
| 源码可运行 | ✅ `python tools/launcher.py` 或 `python tools/serve.py` |
| 测试 | ✅ `python -m pytest tests -q` → **555 passed, 1 skipped**（约 36s） |
| 数据 | ✅ `data/maps.json` + `data/meta.json`，schema **7**（新增「显卡」高资子类，见 §6.16），**13 张图**（含实验室 / 迷宫 / 破冰船三张瓦片图，见 §6.13 / §6.18） |
| 路网 | ✅ `data/roadnet.json` + `assets/roadnet/<图>/<层>.bin`（10 张矢量图的静态路网，供前端同层沿道路寻路，见 §6.19） |
| 发布包 | ✅ `release\` 下**三件套**（Portable zip / AppWindow zip / Setup exe）已按第十四轮代码**重打包并上传 GitHub Release v0.1.0**（包内含 `assets/roadnet/` 35 个位图与 `data/roadnet.json`），见 §6.14 / §6.19 |
| **配置位置** | ⚠️ **已改为用户级目录** `%APPDATA%\EFTMap\`（不再放软件目录）——重新打包不再丢设置，见 §6.7 |
| **Git** | ✅ 第十三轮 5 个提交 + 第十四轮 5 个提交**已推送** `origin/main`，工作区干净（仅余本状态行的更新提交），见 §9 |
| 已知未实现 | ❌ 快门声音替换（见 §3 版本号铁律）、账号级任务统计（刻意不做）、**高级子弹刷新点**图层（上游物资点里没有子弹信息，见 §11） |

最近一次实质改动（2026-10-19，第十四轮）：**导航沿道路走**——构建期把 10 张矢量底图的通行区域栅格化成静态路网（`tools/roadnet.py`，纯离线），前端对**同层**相邻途经点做加权 A\*（道路优先）+ 视线简化，见 §6.19。
上一轮（第十三轮）是收录破冰船（icebreaker），见 §6.18；再上一轮是海岸线三狗改锚定气象站 + 撤离点 / 转移点徽章放大 1.5 倍（§6.17）。

---

## 1. 项目是什么

《逃离塔科夫》**离线互动地图**：双击 `EFTMap.exe` → 弹「设置与启动」小窗 → 点「启动 WebUI」→ 自动打开浏览器看到地图。

- 纯 Python 标准库后端 + 零依赖原生 JS 前端，**不引入任何第三方库 / 图标库 / 素材包**
  （唯一例外：用户自己提供并入库的图片素材 `assets/icons/`，见 §2 铁律 2 与 §6.5）
- 底图与标注数据全部内置，**运行期不联网**（唯一联网时机是构建期跑 `tools/fetch_data.py`）
- 默认与游戏进程**零交互**：只读游戏自己写在磁盘上的截图与日志文件
- 唯一例外是**可选的自动截图**（默认关）：用模拟按键让游戏自己截图

---

## 2. 铁律（改动前必须遵守，违反了就是 bug）

1. **运行期不联网**。只读本地文件；不接第三方账号授权，不做远程进度同步。要联网的活只能在 `tools/fetch_data.py` 这一层做。
2. **零依赖**。后端只用 Python 标准库；前端不引任何库。图标默认一律**手画 SVG**（`app.js` 的 `LOOT_ICONS` / `SIGN_ICONS`），**不下载素材**——用户说「直接用 wiki 的图标」时也照样手画近似。
   唯一例外：**用户自己提供**并落在仓库里的图片素材（如 `assets/icons/` 下由 `tools/iconize.py` 抠图导出的 PNG），属于本地文件而非"下载"，可以用 `<image>` 贴图引用（见 §6.5）。
3. **版本号不得升到 1.0**，直到实现快门声音替换功能。版本号只有一处定义：[tools/serve.py](file:///z:/personal/trae/02-塔科夫/eft-interactive-map/tools/serve.py#L41) 的 `VERSION = "0.1.0"`，`tools/launcher.py` 引用它（`launcher.py:42`）。
4. **新增开关一律默认关闭**（自动截图、自动删除截图都是这么定的）。
5. **自动截图**只在「开关开 && 战局中 && 游戏窗口为前台」三个条件同时满足才触发，避免向别的窗口发输入。
6. **自动删除截图**三条安全规则：只删能解析出位置的截图；**始终保留最新 1 张**（否则实时定位失效）；只删「开关开启时刻之后」产生的文件（不误删历史）。
7. **绝对不要给 SVG 元素加 CSS `animation` / `transform`**。浏览器会把整张 `<svg>` 栅格化，`viewBox` 放大等于放大位图 → **整张图连地名文字都变糊**。这是踩过的坑，见 §8。所有描边用 `vector-effect: non-scaling-stroke`，图标定位靠 SVG 属性 `transform`（不是 CSS）。
8. **所有静态文件必须发 `Cache-Control: no-store`**。否则打包后用户看到的还是旧界面（踩过）。相关实现：[tools/serve.py](file:///z:/personal/trae/02-塔科夫/eft-interactive-map/tools/serve.py) 的 `end_headers()` / `_send_cache_header()`，测试在 `tests/test_serve.py`。
9. **不静默丢点**。上游标注落在底图矩形外、或高度落在没有矢量底图的结构里，都要照实保留、按主楼层显示。
10. **改完源码必须重新打包**，否则用户拿到的 exe 里还是旧代码。

---

## 3. 目录结构与文件职责

```
eft-interactive-map/
├── app.js           106 KB  前端全部逻辑（单文件，零依赖，含图标体系）
├── index.html         4 KB  页面骨架（顶部菜单栏 + 工作区）
├── style.css         21 KB  框架 = Windows XP (Luna) 浅色；地图区与标记仍用深色「卡带未来主义」配色
├── README.md         30 KB  面向用户的完整文档（改功能必须同步改这里）
├── data/
│   ├── maps.json           构建期产出（13 张图的底图引用 + 全部标注）；schema 7
│   ├── roadnet.json        路网索引（10 张矢量图各层的格子边长 / 尺寸 / 字节数与各类格子计数）；schema 1
│   └── meta.json           数据溯源（各接口 url/license/sha256 + 计数，含瓦片 `tileMaps` / `tileBytes`）
├── assets/maps/*.svg       13 张底图（10 张上游矢量 SVG + 实验室 / 迷宫 / 破冰船 3 张构建期用瓦片拼的合成 SVG，约 10.0 MB，已入库）
├── assets/maps/tiles/      瓦片 PNG（实验室 / 迷宫 / 破冰船用，每张图一层一组，已入库；合成 SVG 里的 `<image>` 引用的就是它们）
├── assets/roadnet/<图>/<层>.bin  各层路网位图（每格 2 bit 通行码，10 张矢量图共 35 个位图约 779 KB，已入库）
├── assets/icons/*.png      217 个图标素材（64×64 透明 PNG，用户提供源图 + tools/iconize.py 抠图导出，已入库）
├── tools/
│   ├── fetch_data.py       构建期数据管道（唯一联网点；第 5 步会顺带重建路网）
│   ├── roadnet.py          底图 → 静态路网（纯离线栅格化；见 §6.19）
│   ├── iconize.py          抠图工具（把用户提供的 ui图标 抠成 assets/icons 的 64×64 透明 PNG，可复现；竖排图例用 `band` 按行切）
│   ├── serve.py            本地 HTTP 服务 + SSE + 后台线程（VERSION 定义在此）
│   ├── launcher.py         「设置与启动」小窗（tkinter）；加壳版：资源目录有 `appmode.flag` 就在独立应用窗口开界面
│   ├── installer.py        一键安装器（由 build_release.ps1 打成单文件 exe；装到 %LOCALAPPDATA%\EFTMap + 快捷方式 + 卸载项）
│   ├── eftlog.py           游戏日志监控（只读增量文本匹配）
│   ├── keyinput.py         Windows SendInput 模拟按键（自动截图用）
│   ├── screenshot.py       截图目录轮询 + 文件名坐标/朝向解析 + 删除
│   ├── floors.py           楼层结构 + y → 楼层判定
│   ├── coord.py            世界坐标 ↔ SVG 坐标换算
│   └── config.py           配置读写（%APPDATA%\EFTMap\eftmap.config.json）+ 旧位置迁移 + `ui` 偏好块
├── build/build.ps1         PyInstaller onedir 打包脚本 → dist/EFTMap/（**每次整体删旧目录**）
├── build/build_release.ps1 发布三件套 → release/（Portable zip / AppWindow zip / Setup exe；先跑一遍 build.ps1）
├── release/                ⚠️ 发布产物（**已 gitignore，不进仓库**）
├── tests/                  555 条测试，全离线（含 `test_roadnet.py`）
├── build-cache/            ⚠️ 构建期原始缓存，**已 gitignore，不进仓库**
└── docs/superpowers/       设计规格（specs）与计划（plans）
```

前端是**单文件** `app.js`，没有模块拆分——继续沿用这个风格，别引入构建步骤。

---

## 4. 数据管道（构建期唯一联网的地方）

`python tools/fetch_data.py` 的流程：

1. 拉 `the-hideout/tarkov-dev` 的地图配置（MIT）与 `json.tarkov.dev/{mode}/maps` 标注数据
2. `select_maps()` 只保留**有底图可用**的图：上游给了 `svgPath` 的 10 张，外加 `TILE_MAPS` 里的实验室 / 迷宫 / 破冰船（上游只给 `tilePath`）
3. 拉底面 SVG 存到 `assets/maps/`；**实验室 / 迷宫 / 破冰船的瓦片按上游 `transform` / `bounds` 拼成合成 SVG**（破冰船改用人工反推投影覆盖，见 §6.18；瓦片原样存 `assets/maps/tiles/`）；拉中文翻译 `maps_zh` 与中文物品名 `items_zh`
4. 逐图规范化成 `data/maps.json`，写 `data/meta.json`（含每份原始数据的 sha256 与许可）
5. **`[5/5]` 栅格化底图路网**（`tools/roadnet.py`，**纯离线**，只读 `assets/maps/*.svg`）→ `assets/roadnet/<图>/<层>.bin` + `data/roadnet.json`，供前端同层沿道路寻路（见 §6.19）。
   这一步在「已就绪跳过」分支里**也会执行**，所以缺路网不会触发联网重拉；而 `data_ready()` 不检查路网，正是为了让老的缓存态也能补建。

**关键机制：`build-cache/`**。所有原始响应都会先落盘到 `build-cache/`，重跑时优先读缓存 → **改逻辑后可离线重跑**。但该目录**已被 gitignore**，所以：

> **从零克隆的仓库跑 `fetch_data.py` 需要一次联网**。有缓存的机器上可以完全离线重跑。

常用参数：

```bash
python tools/fetch_data.py                  # 全量 13 张图
python tools/fetch_data.py --maps customs,woods   # 只拉指定图
python tools/fetch_data.py --mode pve       # 换数据模式（默认 regular）
python tools/fetch_data.py --force          # 忽略缓存强制重新拉
```

**上游只有 `regular` / `pve` 两套数据集，没有 season。**

数据模型要点（`data/maps.json`）：每张图有 `key` / `id` / `name`（中文图名）/ `worldToSvg` / `bounds` / `floors` / `layers{...}`；
`layers` 里是各图层的点数组：`extracts` / `transits` / `spawns` / `containers` / `loose` / `valuables` / `locks` / `hazards` / `artillery` / `bosses` / `btr` / `stationary` / `labels`。
物资容器分类**只认上游 slug**（`lootContainers[].normalizedName`），**不认中文译名**（同一容器有多个译名，不可靠）。

---

## 5. 运行时

```bash
python tools/launcher.py                   # 启动框 + 自动开浏览器（推荐）
python tools/launcher.py --port 8788 --no-browser
python tools/launcher.py --game-dir "E:\EFT" --screenshots "D:\...\Screenshots"
python tools/launcher.py --app-window        # 在独立无地址栏应用窗口里开界面（加壳版行为，见 §6.14）
python tools/serve.py --no-browser --port 8787     # 只跑静态站点（调前端用）
```

- **界面开在哪**：默认走系统默认浏览器；资源目录里放了 `appmode.flag`（加壳发布包自带）或加了 `--app-window` 时，
  改用系统自带 Edge / Chrome 的 `--app=<url>` 开一个**无地址栏 / 无标签页的独立窗口**，都找不到时**静默退回默认浏览器**（不会打不开）。

- 配置与用户音频落在**用户级目录** `%APPDATA%\EFTMap\`（`eftmap.config.json` + `sounds/`）；自定义音频会自动拷进 `sounds/`，配置里只存文件名。软件目录下的旧配置与 `sounds/` 会在首次启动时**自动迁移**过来（原文件保留不删）。目录可用 `--config-dir` 覆盖。
- 游戏目录 / 截图目录**自动定位，失败允许手动填**
- 游戏日志监控：跟随游戏目录下 `Logs` 里最新会话文件夹，只读增量文本匹配，**不注入进程、不挂钩子**
- 任务统计**只统计本局**的接取 / 完成 / 失败三类事件，没有条件级进度、不跨会话累计
- 游戏截图按键从**日志文件头的 JSON 配置**自动同步（当前是 `V`），无需用户手填

---

## 6. 历次已完成的改动（6.1 – 6.19；第九轮见 §6.14、第十轮 §6.15、第十一轮 §6.16、第十二轮 §6.17、第十三轮 §6.18、第十四轮 §6.19）

### 6.1 修复「地图名字全变成物品名」的 bug ★

**症状**：`data/maps.json` 里 10 张图的名字全是 loot 物品中文名——街区显示成「酒店215房间钥匙」、海关显示成「海关 Tarcone 主管办公室钥匙」、中心区「滤水器」、工厂「金蛋」等。

**根因**：`fetch_data.py` 的 `build_map()` 里，抽「高级资源点」的内层循环把循环变量写成了 `name`：

```python
for item_id in item.get("items") or []:
    name = localize(item_translations, "%s Name" % item_id, None)   # ← 覆盖了上面的地图名
```

而同一个函数前面已经用 `name` 存过地图中文名（`name = localize(translations, "%s Name" % map_id, ...)`），于是函数末尾 `return {"name": name, ...}` 取到的是**该图最后一个地面刷出物品的中文名**。注意：`data/maps.json` 里**每张图的 `id` 字段是正确的**，只有 `name` 被污染。

**修法**：循环变量改名 `item_name`。已补回归测试 `test_build_map_map_name_survives_valuables_pass`（`tests/test_fetch_data.py`）锁死这个 bug。修完离线重跑 `fetch_data.py` 重新生成了 `data/maps.json`。

**已核实**：现在 10 张图名为 塔科夫街区 / 中心区 / 海关 / 工厂 / 立交桥 / 灯塔 / 储备站 / 海岸线 / 码头 / 森林，且发布包里的 `data/maps.json` 与源码一致。浏览器实测左侧地图列表无物品名。

### 6.2 撤离点配色纠正

之前记反了，现在的**正确**配色（写在 [style.css](file:///z:/personal/trae/02-塔科夫/eft-interactive-map/style.css) 的 `:root` 里）：

| 图层 | CSS 变量 | 值 |
| --- | --- | --- |
| PMC 撤离点 | `--extract-pmc` | `#37c46a` 绿 |
| Scav 撤离点 | `--extract-scav` | `#e5a72c` 黄 |
| 合作（共用）撤离点 | `--extract-shared` | `#4a9fe8` 蓝 |
| 转移点 | `--transit` | `#e2513c` 红 |

### 6.3 一批标记从圆点换成手绘 SVG 图标

新增位置类图标体系 `SIGN_ICONS`（`app.js`），形状全部照用户提供的参考截图手画：

| 图层 | 图标 | 颜色 |
| --- | --- | --- |
| 玩家出生点 | 向下三角标 | `#37c46a` 绿 |
| AI PMC 出生点 | 向下三角标 | `#4a9fe8` 蓝 |
| AI Scav 出生点 | 向下三角标 | `#e58b2c` 橙 |
| 狙击手 | 圆环 + 内嵌 X 准星 | `#d0553f` |
| Boss | 骷髅头（白骨 + 深色眼窝鼻孔） | `--boss` |
| 上锁的门 / 后备箱 | 黄色挂锁 + 深灰锁梁 | `--lock` |
| BTR 停靠点 | 红色八边形 | `#e2513c` |
| 高级资源点 | **按物品各自对应**：比特币→金币、钥匙卡→卡片、钥匙→钥匙、私酒→酒瓶、LEDX/除颤器→医疗十字盒；认不出退回宝石 | 见 `SIGN_COLORS` |

出生点三角的颜色**不是内联的**，由图层的 CSS 规则给（`.emk-layer[data-layer="spawn_*"] .emk-sign { --c: ... }`）；高级资源点因为要在**同一图层内按物品区分颜色**，所以由 `SIGN_COLORS` 内联给 `--c`。
左侧图例每行前面用同一套图标（`signIconSvg()` / `lootIconSvg()`）。

### 6.4 打包与校验

`powershell -ExecutionPolicy Bypass -File build\build.ps1` → `dist/EFTMap/EFTMap.exe`（31.1 MB，10 张底图 + `assets/icons/` 图标素材）。
`--add-data "$Root\assets;assets"` 会把 `assets/icons/` 整包带进 `_internal\assets\icons\`，运行期前端用相对路径 `assets/icons/*.png` 就能读到。
已用 SHA256 核对打包产物里的 `app.js` / `style.css` / `data/maps.json` / `assets/icons/*.png` 与源码**逐字节一致**。

### 6.5 图标换成用户提供的素材 + 标记小浮窗 ★

**（一）图标改用图片素材。** 用户觉得手画 SVG「有点丑」，提供了 `D:\personal\trae\02-塔科夫\ui图标`（24 个 PNG，**全部无透明通道**，其中 10 个是带中文文字的近黑长条截图）。处理方式：

- 新增 [tools/iconize.py](file:///z:/personal/trae/02-塔科夫/eft-interactive-map/tools/iconize.py)：用 Pillow 抠图（边框采样估底色 → 阈值分割 → 连通域取主体 → 去右侧中文文字 → 填洞 → 前景色外扩防黑边 → 裁包围盒等比缩放居中），统一导出 **20 个 64×64 透明 PNG** 到 [assets/icons/](file:///z:/personal/trae/02-塔科夫/eft-interactive-map/assets/icons)。`python tools/iconize.py`（加 `--sheet` 会额外出自检拼图）。
- 前端新增 **`ICON_PNG`** 贴图表（`app.js`，key → `assets/icons/*.png`）与 `pngIcon(key, unit)` / `pngIconSvg(key)` / `pngImage(key)`；四个图标工厂函数（`lootIcon` / `lootIconSvg` / `signIcon` / `signIconSvg`）**开头判断：命中 `ICON_PNG` 就返回 `<image>` 贴图，未命中仍走手画 SVG**。
- 贴图坐标与手画图标一致（±8 屏幕像素、外面乘 `unit`、靠父级 `scale(1/z)` 保持屏幕大小恒定）；图例用 `viewBox="-8-8 16 16" width=15 height=15` 的内联 `<svg>`。
- **换了素材的槽位**：12 类物资容器（保险箱 / 夹克 / PC 主机 / 尸体 / 抽屉 / 行李袋 / 彩蛋点 / 医疗箱 / 补给箱 / 工具箱 / 手雷箱 / 武器箱）+ 比特币 + LEDX；**六色实验室钥匙卡按颜色各对一张**（黄/红/绿/蓝/紫 + 生活区）。**仍手画的**：手提箱 / 收银机 / 其他容器、钥匙、私酒、兜底宝石。钥匙卡配色由 `VALUABLE_ICON_RULES`（正则 → key，**具体色卡规则排在通用 `/钥匙卡/` 之前**）决定。

**（二）标记详情改成小浮窗。** 用户原话「和上锁的门一样，点击后有小浮窗」——所以点地图上**任意标记**（物资点 / 出生点 / Boss / 撤离点…）时，在该标记旁边弹一个 HTML `<div id="marker-pop">` 小浮窗（**不是 SVG 元素**，避开「SVG 加 CSS 动画会栅格化变糊」的老坑）。实现：

- `detailRows(map, kind, item)`：从 `showDetail` 抽出**语义化行**（名称 / 类型 / 各 kind 专有行），**小浮窗与左侧完整面板共用**。
- `showMarkerPopup(map, kind, item, node)` / `hideMarkerPopup()`：建 `<div#marker-pop>` append 到 body，用被点标记的 `getBoundingClientRect()` 定位（右边放不下翻到左边，上下夹在视口内），8 秒后自动消失；`onOverlayClick` 里**所有标记**都调它，`locks` 再额外调 `showLockKeyHint`；换图时 `hideMarkerPopup()`。
- **左侧 `#detail-block` 完整详情保留不变**（浮窗只给简略信息）。样式 `.marker-pop*` 在 [style.css](file:///z:/personal/trae/02-塔科夫/eft-interactive-map/style.css)。

### 6.6 修复「海岸线一层切过去空无一物」（缺楼层波段）

**症状**：海岸线底图里有独立的**一层**（`First_Floor`）图层，左侧楼层列表也有「一层」按钮，但点进去看不到任何标记——包括度假村一层那些**上锁的门**。

**根因**：楼层判定靠上游 `layers[].extents` 给的高度区间。上游海岸线只登记了**二层 `[-1,2]` / 三层 `[2,1000]` / 地下层 `[-1000,-5]`**，**没有一层的区间**。于是度假村一层（`y ≈ -2.7～-4`）的门与物资全落进那个没人认领的空档 → 判定成主层「地面层」；切到「一层」时该层一个点都没有。`一层` 之所以还在按钮里，是因为底图 SVG 里认得出这个顶层组（[floors.py](file:///z:/personal/trae/02-塔科夫/eft-interactive-map/tools/floors.py) 会把 SVG 里认得的楼层组补进可选列表），但它**没有对应波段**，永远判不到。

**修法**：在 [fetch_data.py](file:///z:/personal/trae/02-塔科夫/eft-interactive-map/tools/fetch_data.py) 新增补充波段表 **`FLOOR_BAND_EXTRA`**（键是图 key，值是若干 `{svgLayer, label, minY, maxY, areas}`），`build_map` 在 `build_floors` 之后把这些波段追加进 `floors["bands"]`。海岸线补了一条 `First_Floor [-5,-1)`，**并用 `areas` 把范围限定在度假村矩形内**（`[-370,-200,-120,-20]`）——否则度假村外那些 `y` 同样落在 `-5～-1` 的低位地面点（例如河湾附近的 6 个雷区）会被误判成一层。
**验证**：一层现在能看到 4 扇上锁的门（西 112 / 东 107 / 西 104 / 粘有胶带的办公室）+ 94 个度假村一层容器；地面层只剩 6 个室外门，一层的门不再混进来。已补数据级回归测试 `test_data_shoreline_first_floor_band`（`tests/test_floors.py`）：度假村内的低位点判成一层、度假村外的低位点不能跟着误判。

### 6.7 配置落盘到用户目录 + 页面勾选可保存 + 顶部菜单栏 + XP 风格框架 ★（第二轮）

用户原话：「exe 打开后的启动窗 增加一个 保存配置的按钮 不然每次启动都还要改设置 / 进 webui 里面 勾线的这些物资点也可以保存 / 战局与任务 放在 webui 打开后的上方增加的菜单栏里 / webui 整体也做成 windows xp 的风格，已有的图标什么的不变，只改网页框架」。四项决策（经确认）：配置落盘 → **`%APPDATA%\EFTMap`**；页面勾选 → **写进 `eftmap.config.json`**；菜单栏 → **只放「战局与任务」**；XP → **只改框架，地图区保持深色**。

**（一）配置改存用户目录。** 「每次启动都要改设置」的真因不是没保存——启动器本来就会在失焦 / 勾选 / 启动时自动落盘——而是 [build.ps1](file:///z:/personal/trae/02-塔科夫/eft-interactive-map/build/build.ps1#L32) 每次都 `Remove-Item -Recurse -Force $Target` 把 `dist\EFTMap`（含里面的 `eftmap.config.json`）整体删掉。改法：

- [config.py](file:///z:/personal/trae/02-塔科夫/eft-interactive-map/tools/config.py) 新增 `default_storage_dir()`（有 `APPDATA` → `%APPDATA%\EFTMap`，否则 `~/.eftmap`）、`migrate_legacy(dest_dir, legacy_dir)`（**只在目标缺失时**搬 config 与 `sounds/` 下的音频，不删旧文件，失败静默）与 `STORAGE_DIRNAME`。
- `config_path()` / `sounds_dir()` / `save()` 的默认目录一律改成 `default_storage_dir()`——**`save()` 之前用 `app_dir()`、`load()` 用持久化目录，两边不一致，必须统一**。
- **`app_dir()` 函数体一个字没改**：既有测试 `test_app_dir_is_repo_root_when_not_frozen` 断言它等于仓库根，改它就要连带改语义（`app_dir()` 现在的定位是「软件目录」）。
- [launcher.py](file:///z:/personal/trae/02-塔科夫/eft-interactive-map/tools/launcher.py) 与 [serve.py](file:///z:/personal/trae/02-塔科夫/eft-interactive-map/tools/serve.py) 都改用持久化目录，并在**没有显式传 `config_dir` 时**调 `migrate_legacy(app_dir, config.app_dir())` 做一次性迁移。

**（二）启动器加「保存配置」按钮。** `LaunchWindow` 新增 `btn_save = mk("保存配置", self.save_config)` 与一行 `save_note` 提示保存位置（迁移过就带上项数）；点一下 → 绿色「已保存 ✓ <路径>」→ 4 秒后复位成路径提示。

**这里有个必须记住的坑**：`_save()` 现在会先从磁盘读回 `ui` 块再写：

```python
payload = self.current_config()
payload["ui"] = config.load(self.app_dir).get("ui") or {}
config.save(payload, self.app_dir)
```

因为 `build_config()` 的产物**没有 `ui` 键**，`normalize()` 会把它归成 `{}` —— 不补回来，表单每失焦一次就把用户刚在页面上存的图层勾选抹掉一次。已补回归测试 `test_save_keeps_page_ui_prefs` / `test_save_survives_missing_ui_block`（`tests/test_launcher.py`，用 `SimpleNamespace` 替身直接调 `LaunchWindow._save`，不弹窗）。

**（三）页面勾选写回配置。** 新增 `POST /api/prefs`（[serve.py](file:///z:/personal/trae/02-塔科夫/eft-interactive-map/tools/serve.py)）：

- 只认这一条路径，`Content-Length` 必须在 `(0, MAX_PREFS_BODY=64KB]`；JSON 解析失败 → 400；未知路径 → JSON 404。
- `config.save(config.merge_ui(config.load(app_dir), prefs), app_dir)`，然后 `publish_event("config", config_payload(...))` 给所有打开的页面广播一次。
- `config.py` 新增 `ui` 块（`layers` / `map` / `floor_auto` / `floor_filter`）+ `_normalize_ui()` / `merge_ui()`。前端只上报 `layers` / `floor_auto` / `floor_filter` 三项；**`map`（上次看的地图）不纳入服务端同步**，本地 `localStorage` 已覆盖，多一处同步纯属多余。

前端（`app.js`）：`uiPatch()` / `queuePrefs()`（**400ms 防抖**，一批改动合并成一次请求）/ `flushPrefs()`（`fetch` 失败静默，`localStorage` 兜底）/ `mergeLayers()` / `sameLayers()` / `applyUiPrefs()`。写成 `tests/test_serve.py` 的 `/api/prefs` 六条（含坏 body、404、以及「写完后 SSE 真的广播了 `config`」）与 `tests/test_config.py` 的 `ui` 块十五条。

**（四）顶部菜单栏。** [index.html](file:///z:/personal/trae/02-塔科夫/eft-interactive-map/index.html) 改成 `<body>` → `div.menubar#menubar`（`button#menu-raid`「战局与任务」+ `div#raid-block.menu-panel[hidden]`）→ `div.workspace`（包 `aside#sidebar` + `main#stage`）。**所有原元素 id 原样保留**（`raid-status` / `quest-log` / `quest-done` / `shot-status` / `clean-status` / `quest-hint` …），只是从侧栏搬进面板并去掉那个 `<h2>战局与任务</h2>`。`bindMenu()` 负责开关：点按钮 toggle、点面板外收起、`Esc` 收起，维护 `hidden` / `aria-expanded` / `.open`。

**（五）XP 框架。** [style.css](file:///z:/personal/trae/02-塔科夫/eft-interactive-map/style.css) 的 `:root` **保留原来的全部深色语义变量**（`--bg` / `--extract-*` / `--loot-*` / `--player` …）给地图区与标注用，另加一套 `--xp-*`（`--xp-face:#ece9d8` / `--xp-title:#204070` / `--xp-sel:#316ac5` / `--xp-input:#7f9db9` / `--xp-tip:#ffffe1` …）给窗口框架用。改动覆盖：`body` 改纵向 flex、新增 `.menubar` / `.menu-panel` / `.workspace`、`#sidebar` 改浅色面、`.brand` 改 XP 蓝渐变标题条、`.map-item` / `.floor-item` / `.toggle` / `.search` / `.detail` / `.credits` 一律浅色，提示气泡 `.lock-hint` / `.marker-pop` 改 XP 淡黄。**地图区（`#stage` / `.hud` / `.statusbar` / `.error`）与 L412 之后所有 `emk-*` 规则一个字没动**——地图上叠着底图与彩色标注，改浅底反而看不清。`index.html` 里的小图标与 `assets/icons/*.png` 全部不变。

`node --check app.js` 通过；`python -m pytest -q` → **474 passed, 1 skipped**；浏览器实测：无控制台报错、XP 框架与深色地图区正常、菜单开合 / `Esc` / 点外部收起都对、勾掉图层 → 刷新后仍是关着的（配置里也落了 `ui.layers`）。

### 6.8 第三批图标素材：私酒 / 除颤器 / 钥匙 / 黑卡 / Object 两张卡 ★（第三轮）

用户又往 `D:\personal\trae\02-塔科夫\ui图标` 补了素材（17 张 + 后来单独补的 1 张 Object 卡图例），要求「换掉现有手画图标」。经确认只换**数据里真有对应点**的槽位，**不动数据白名单**。

- **换成素材的槽位**：私酒（287 个点，原为手画）→ `val-bottle.png`；便携式除颤器（61 个点，原来与 LEDX 共用 `val-ledx.png`）→ `val-defib.png`；生锈的带血钥匙（1 个点，原为手画）→ `val-key.png`；实验室钥匙卡·黑（13 个点，原来错用黄色卡）→ `val-keycard-black.png`；Object #11SR / #21WS 钥匙卡（各 12 / 13 个点，原来也共用黄色卡）→ `val-card-11sr.png` / `val-card-21ws.png`。**仍手画的**只剩手提箱 / 收银机 / 其他容器，以及高级资源点的「兜底宝石」。
- `VALUABLE_ICON_RULES` 调整：原来的 `/LEDX|除颤|透照|注射|医疗/i → med` 把 `除颤` 拆出去（`/除颤/` → `defib`），新增 `/实验室钥匙卡·黑/` → `black`、`/Object #11SR/i` / `/Object #21WS/i` → 各自卡。**这些具体规则一律排在通用 `/钥匙卡/` 之前**（老规矩）。
- **`tools/iconize.py` 新增 `band` 参数**（`[起, 止]`，0~1 纵向比例）：用户给的「图例」是一张图里竖排多行，而 `strip` 模式只取最左侧那一簇、按 x 聚簇会把上下行连起来。`band` 先把掩膜限制在这一段落，`strip` 的边框屏蔽也跟着 band 的上下边界走。三张图例各按行切开：街区图例第 5 行 → 钥匙、实验室图例第 1 行 → 黑卡、Object 图例上/下两行 → 两张卡。**行边界是脚本扫「无前景像素的横条」量出来的**，写死在 `JOBS` 里（一开始把第 5 行的起点填早了，把上一行的钥匙尾巴带了进来，往回收 0.018 才干净）。
- **没采用的素材**：用户给的 8 把钥匙（废弃工厂 / RB-BK / RB-VO / 314 / RB-PKPM / Chek.13 / 公寓管理员 / Knossos LLC / 化工厂）不在 [fetch_data.py](file:///z:/personal/trae/02-塔科夫/eft-interactive-map/tools/fetch_data.py) 的 `HIGH_VALUE_ITEMS` 白名单里，地图上本来就没有这些点——用户明确**不改白名单**（否则要重建 `maps.json`），所以这些源图不入库，加了也是死资产。
- 用户问过「钥匙图标能不能直接从 wiki 拿」（eftarkov.com 的 keys 排行页）——**不行**：违反 §2 铁律 1「运行期不联网」与铁律 2「图标不下载素材」，且该站没有可再分发许可（项目只分发 MIT / CC BY-NC-SA 并已署名）。正确路径仍是**用户把图放进 `ui图标`，由 `iconize.py` 抠图入库**。

**验证**：`python tools/iconize.py --sheet` 自检拼图里 26 个图标全部干净（无残留文字、无底色渗出）；`node --check app.js` 通过；13 个高级资源点物品名逐一核对，全部命中预期图标；`python -m pytest -q` → **474 passed, 1 skipped**；浏览器实测：地图渲染 1333 个图标节点、18 个唯一素材 HTTP 全部 200，唯一控制台报错是无 favicon 声明的 `/favicon.ico` 404（与本轮改动无关）；重新打包后 `app.js` / `style.css` / `index.html` SHA256 与源码逐字节一致，产物内 `assets/icons/` 26 个文件齐全。

### 6.9 第四批图标素材：固定刷新钥匙 + 上锁的门显示对应钥匙 ★（第四轮）

用户要求：「公寓管理员 / Knossos LLC 之类的钥匙在地图上有百分百固定刷新点的也加进去」「wiki 的图标我都截图下来了，你直接拿去用」「抠完的干净图存回 `ui图标`，没用的删掉」。经 AskUserQuestion 两轮确认口径：

- **钥匙口径**：只收录「刷点物品池里只有它自己」的固定刷新钥匙（`lootLoose[].items` 长度 == 1）；**但上锁的门点击后浮窗里显示的「需要钥匙」也要配上对应图标**（没图就退回通用钥匙图）。
- **非钥匙物品**：只加「TerraGroup "蓝色文件夹" 材料」一件（Labrys 访问钥匙卡 / T7 热成像目镜不加）。
- **素材整理**：`clean/`（抠好的成品）+ `src/`（iconize 用到的源截图）分开放，其余截图全删。

**数据侧**（[fetch_data.py](file:///z:/personal/trae/02-塔科夫/eft-interactive-map/tools/fetch_data.py)）：白名单 `HIGH_VALUE_ITEMS` 净新增 **54 把固定刷新钥匙 + 1 件蓝色文件夹**。清单由 `build-cache/markers-regular.json` 离线实算（`lootLoose[].items` 长度 == 1，共 149 个固定刷新物品，其中含「钥匙」字样 63 个，9 个与既有白名单重复 → 净增 54）。删掉 `data/maps.json` 后 `python tools/fetch_data.py` 离线重建：**高级资源点 753 → 888**，`公寓管理员钥匙` / `Knossos LLC 设施钥匙` / `蓝色文件夹` 均已在册。

**图标侧**（[iconize.py](file:///z:/personal/trae/02-塔科夫/eft-interactive-map/tools/iconize.py)）：`JOBS` 172 条（26 旧 + `val-folder` + 145 个 `key-<物品id前8位>`）。`band` 仍是竖排图例按行切的唯一手段，本轮新条目一律 `ring: 0`（让图标贴住 band 上下边界）。为跑得动 95M 像素的巨型图例，给 `build_mask` / `label` / `keep_left_icon` 加了 `ya/yb` 只扫 band 行、`compose` 前景色外扩限制在小窗口 —— 单任务从 4.07s 降到秒级，且**旧 26 个 PNG 的 SHA256 与优化前逐字节一致**。

**前端侧**（[app.js](file:///z:/personal/trae/02-塔科夫/eft-interactive-map/app.js)）：
- `ICON_PNG` 26 → **172** 项（新增 `key_<id8>` ×145 + `valuable_folder`）。**`style.css` 里没有 `emk-png` 专属规则，加 key 不用改 CSS**。
- 新增 `KEY_ICONS`（**中文物品名 → icon key** 精确表，148 条）：`valuableIconKey()` 先查这张表再走 `VALUABLE_ICON_RULES` 的通用正则 → 让「公寓管理员钥匙」这类贴真图；`Object #11SR / #21WS 钥匙卡` 直接指向既有的 `valuable_card_11sr / 21ws`。
- **上锁的门**：`showLockKeyHint()` 与详情面板 `detailRows()` 的「需要钥匙」行现在都会用 `inlineIcon(valuableIconKey([keyName]))` 贴一个小图标（`detailRows` 新增可选的第 3 列 `row[2]` 存 icon key）；没图的门钥匙退回通用 `val-key.png`。
- 覆盖率（用 `data/maps.json` 实算）：上锁的门 187 个钥匙名中 **144 已配专属图、43 退回通用钥匙图**；高级资源点 62 个物品名中 41 配专属图、21 走通用正则（BTC / 私酒 / LEDX / 除颤器 / 六色卡本来就有规则，OLI 收银机等无图钥匙退回通用钥匙图）。**（→ 这里的 43 个退回项已在第五轮全部补齐，见 §6.10）**

**素材整理**：`ui图标/clean/`（**171 个**按中文名命名的成品——172 张成品里有 1 张视觉重复，`生锈的带血钥匙` 与通用 `val-key.png` 的 PNG 逐字节相同，已去重，故比 `assets/icons/` 少 1）、`ui图标/src/`（44 张 iconize 用到的源截图）、根目录多余截图全删（现只剩 `clean/` 与 `src/` 两个子目录）。

**验证**：`node --check app.js` 通过；`python -m pytest -q` → **474 passed, 1 skipped**；浏览器实测（Chrome DevTools，127.0.0.1 本地服务）：页面无 JS 异常、146 个图标路径 HTTP 全部 200，点击「上锁的门」→ 浮窗与详情面板的「需要钥匙」行都正确贴上图标（`"Aspect"公司办公区钥匙` → `assets/icons/key-64ce5723.png`，`酒店215房间钥匙` → 通用 `val-key.png`）；重新打包后 `app.js` / `style.css` / `index.html` SHA256 与源码一致，产物内 `assets/icons/` **172 个（key-* 145 个）**、`data/maps.json` 齐全。

### 6.10 第五批图标素材：补齐全部仍缺图的门钥匙 ★（第五轮）

用户要求：「再看下」——复查上一轮报告里「43 个仍退回通用钥匙图」的门钥匙，并「一次做完」（量 band → 抠图 → 接线 → 验证 → 打包 → 整理素材）。

**口径**：严格**整名匹配**（去空白 + 全角括号/引号归一后逐名比较，**不用子串匹配**——否则「酒店215房间钥匙」会误命中「酒店2房间钥匙」之类）。实算出上锁的门 187 个钥匙名里 **43 个缺专属条目**；另有 **3 把钥匙只在高级资源点出现**（OLI 收银机钥匙 / TerraGroup 实验室武器测试区域钥匙 / TerraGroup 实验室经理办公室钥匙）；「重新编码后的 A.P. 公寓门锁钥匙卡 (绿)」复用既有 `valuable_card_green` 素材不另抠图。全批共 **新增 46 条 `KEY_ICONS`、45 张新 PNG**（`key-64ce5723.png` 旧批次已有，是脚本正则漏转义 `\"` 造成的重复项，已删）。

**图标侧**：`JOBS` 172 → **218** 条。用「按行亮度均值 + 横向空白间隔分组」的脚本对 21 张 wiki 截图统一量出 46 个目标行 `band`，新条目一律 `ring: 0`；`python tools/iconize.py --sheet` 输出「共输出 46 个文件」，自检拼图逐行核对干净。

**前端侧**：`ICON_PNG` 172 → **218** 项；`KEY_ICONS` 148 → **194** 条。

**现状（用 `data/maps.json` 实算）**：上锁的门 **187 个钥匙名全部已配专属图**（§6.9 里 43 个退回项已清零）；高级资源点 62 个物品名中 **52 有精确条目、10 走通用正则**（那 10 个是 BTC / 私酒 / LEDX / 除颤器 / 六色实验室钥匙卡，`VALUABLE_ICON_RULES` 本来就有规则且已贴素材图）。

**素材整理**：`ui图标/clean/`（**217 个**，与 `assets/icons/` 一一对应；不同钥匙名共用同一图例 icon 的情况很多，属正常）+ `ui图标/src/`（**63 张** iconize 用到的源截图，本轮新增 19 张）；重复截图与调试产物全删。

**验证**：`node --check app.js` 通过；静态一致性检查「`ICON_PNG` 无重复键、引用的 217 个 PNG 全部存在、`KEY_ICONS` 无重复名且值全在 `ICON_PNG`、无未被引用的 `key-*.png`」；`python -m pytest -q` → **474 passed, 1 skipped**；浏览器实测（Chrome DevTools，127.0.0.1:8790）储备站点开「上锁的门」→ 浮窗「需要钥匙：RB-AM钥匙」行出现 `<image>`，`href = assets/icons/key-5d80c88d.png`，无 404；重新打包 `build\build.ps1` 成功（**31.9 MB**），产物内 `app.js` / `style.css` SHA256 与源码一致、`assets/icons/` **217 个（key-* 190 个）**。

---

### 6.11 第六轮：搜索按类型聚合 + 钉选高亮 + 导航路线 ★（第六轮）

用户一次提了 5 件事：搜索结果不理想（搜「物资埋藏桶」应只出这一个类型）、高资点搜不到（比特币 / 私酒）、
要能**钉选**且被钉选的图标**高亮描边**、**实验室与迷宫怎么没有**（且要求开发前先查开源可借鉴项目）、
街区危险区 `x -71.9 / z 0.6 / y 8.5` 位置不对；随后追加**导航**（设目的地 + 自动规划路线）。
用户明确交代：「遇到问题你先绕过，我明天再来解决，你先做你能做的」。

**已实现（前 4 件里的 3 件 + 导航）**

1. **搜索重写**（`app.js` 搜索段）：原先只按单个标记名匹配，现在先把**当前地图**的标记按 `kind + name` 聚合成「类型条目」并缓存
   （`searchIndex()`，换图失效：`selectMap()` 里 `state.searchCache = null`）。子类也一并带出：撤离点带阵营、容器带类别（`containerLabel`）、
   上锁的门带「上锁的门 / 汽车后备箱」。**高级资源点没有 `name`，按其 `items` 数组里的物品名展开成多条条目**——这就是「比特币 / 私酒搜不到」的真因与修法。
   排序 `scoreMatch()`（完全相同 0 / 前缀 1 / 子串 2）→ 再按条数（`count`）→ 名字，取前 30。
   结果行 `searchRow()` = 主按钮（定位）+ **「钉选」** + **「路线」**；副标题 `entrySubtitle()` 形如「物资容器 · 彩蛋点 · 12 处」。
2. **钉选**：按**「类型」**维度记（`kind + name`，如 `containers|物资埋藏桶`），命中的标记统一加 `.emk-pinned` 并在最前面 prepend 一圈
   `circle.emk-pin-ring`（`pinRingRadius()`：撤离 / 转移 11px、图标类 10px、其它 `radius*2.6`，都乘 `unit` 所以屏幕上恒定大小）。
   `isPinnedItem()` 对 `name` / `keyName` / `text` / `items` 四种字段都能命中。持久化：`localStorage`(`eftmap.pins`) + 服务端 `ui.pins`
   （`config._normalize_pins()` / `merge_ui` 已认这个键，上限 300）。点「钉选」时会先 `enableLayersFor(kind, item)` 打开对应图层，
   否则钉选的高亮「没东西可描」。
3. **导航路线**：出发前先说明**本项目没有导航网格**，折线只能是**途经点世界坐标的直线连接**，跨楼层会「穿墙」，面板只报**直线距离**。
   路由点存在 `state.route`（最多 60）+ `routeFromPlayer`（勾选后把实时定位当 1 号点）；`renderRoute()` 画
   `polyline.emk-route-line`（`vector-effect: non-scaling-stroke` 保证线宽恒为屏幕像素）+ 编号圆点 `g.emk-route-node`；
   面板 `renderRoutePanel()` 支持查看 / 删除单点 / 清空 / 反转 / 「从实时定位出发」。入口有三个：搜索结果「路线」、标记详情「加入路线」、
   顶部菜单「导航与路线」（`bindMenu()` 已改成多菜单互斥版）。
4. **街区危险区** `x -71.9 / z 0.6 / y 8.5`：核对 `data/maps.json` 与上游 `maps_live.json` **逐字段一致**，
   且多边形 4 个顶点的质心正是 `(-71.9, 0.6)` → **结论：上游数据本身如此**。按用户「先绕过」的口径**不擅自改**，已写进 README 已知限制。

**实验室 / 迷宫：查过开源项目后判定「今晚不接入」（重要结论，别重复劳动）**

- 检索到的可借鉴项目：`cranberriez/tarkov-mappinator`（`src/maps/calibration.json` 字段与上游同构，SVG 取自 `the-hideout/tarkov-dev-svg-maps`）、
  `the-hideout/tarkov-dev`（上游唯一权威）、`teevik/tarkov-map`、`RedZone02/tarkov-manager`。结论是：**上游自己对这两张图都不用矢量底图**。
- **实验室**：上游 config 里 `the-lab` 只有 `bounds` + `transform [0.575,281.2,0.575,193.7]` + `coordinateRotation 270` + `tilePath (labs_v4/*)`，
  **没有 `svgPath` / `svgBounds`**；mappinator 的 calibration 里也一样（有瓦片、无 svgBounds）。
  社区 SVG 仓库**有** `Labs.svg`（720×586），但 README 明说标签与坐标由使用方自理 → **没有任何校准数据**。
  实测（`Labs.svg` 内联进页面后取 `getBBox()`）顶层三组 `Technical_Level / First_Level / Second_Level` 的并集是
  `x 9.99→709.05`、`y 11.19→576.18`，**宽高比 1.237**（≈ viewBox 的 720/586=1.229）；而 `bounds` 的世界矩形宽高比是 **1.372**。
  两者相差 **10%** ⇒ 这张底图覆盖的世界范围 ≠ `bounds`，照 `compute_world_to_svg` 直接接入会整图横向拉伸 ~10%、
  标记最大偏移 ~40 SVG 单位（约占宽 5.5%），**肉眼可见 → 宁可不放**。
  上次留下的「7/7 撤离、319/319 物资都落在 viewBox 内」只证明**没跑到画布外**，不等于**对得齐**；判定要看宽高比。
  **将来要做**：构建期把上游瓦片拼成单张底图（或做一次人工配准求出真正的 `svgBounds`），再按上游 `transform` / `bounds` 定标。
- **迷宫**：CDN `assets.tarkov.dev/maps/svg/Labyrinth.svg` → **404**；社区 SVG 仓库文件列表里也**没有** Labyrinth.svg；
  上游 `the-labyrinth` 同样只有 `tilePath (labyrinth/main/*)` → **无矢量底图可用**，本项目无法收录。

**验证**：`node --check app.js` 通过；`python -m pytest -q` → **474 passed, 1 skipped**；浏览器实测（Chrome DevTools，127.0.0.1:8787，灯塔图）：
搜「物资埋藏桶」→ **恰好 1 条**「物资埋藏桶 · 物资容器 · 12 处」；点「钉选」→ 按钮变「已钉」、地图上 `g.emk-pinned` **12 个**、
`circle.emk-pin-ring` **12 个**、`localStorage.eftmap.pins` 正确；搜「比特币」→「实体比特币」、搜「私酒」→「“凶狠跑刀崽”私酒」；
连续给两个点加「路线」→ `#route-list` 2 项、`#route-summary`「共 2 个点 · 直线距离约 398 米」、`polyline.emk-route-line` 1 条、
`g.emk-route-node` 2 个。

**新增踩坑**（已进 §8）：钉子环的 CSS 必须写成 `.emk-marker circle.emk-pin-ring`——既有 `.emk-marker circle`（深色描边）
特异性更高，直接写 `.emk-pin-ring` 会被它盖掉；`showDetail()` 取「选中环」时要先跳过 `emk-pin-ring`，否则会拿错半径。

### 6.12 第七轮：高级资源点拆「1 个总开关 + 7 个子类」★（第七轮）

用户口径：「**高级物资点感觉可以做子类细分 下面分比特币 私酒 钥匙类 钥匙卡类，总得（的）高资点同时显示的话有些多**」。
追问后确认三件事：① 子类**七类**（LEDX 与除颤器**也要分开**，不合并成「医疗」）；② **要**一个「高级资源点（全部）」总开关；③
**默认只开 比特币 / 私酒 / 钥匙卡类**（钥匙类、LEDX、除颤器、其他默认关）。

**全部改动都在前端**（`app.js` + `style.css`），**数据不用重跑 `fetch_data.py`**：`valuables` 条目本来就带 `items`（中文物品名数组），
分类只需在 `app.js` 里按物品名做正则判定即可。

1. **分类表** `VALUABLE_CATS`（`app.js` 顶部，紧挨 `isContainer` 之后）：`btc`/`moonshine`/`keycard`/`key`/`ledx`/`defib`/`other`
   七项，各带 `label` + 图例用的 `icon`（`valuable_btc` / `valuable_bottle` / `valuable_keycard` / `valuable_key` / `valuable_med` / `valuable_defib`）+ `match` 正则；
   **`other` 的 `match` 是 `null`**，表示「前面都不命中的兜底」。
   **正则顺序不能乱**：`/钥匙卡/` 必须排在 `/钥匙/` 之前，否则钥匙卡会被「钥匙」那条先吃掉。
   `valuableCatsOf(item)` 逐件物品名判定，返回该点所属的类别数组；有**任何一件**物品名**不命中**任何非 `other` 类别时，
   额外补一个 `other`（这样「同一点既刷 BTC 又刷蓝色文件夹」时，BTC 关掉、其他打开也照样能看到它，不丢点）。
2. **LAYER_SPEC**：「物资」组第一行是**总开关** `{ key:"valuables", master:true }`（沿用旧 key，旧配置不用迁移），
   紧随其后是 7 个**子类项** `{ key:"valuable_<cat>", sub:true, icon, where:isValuableCat(cat) }`。
   `countOfSpec` 因此天然生效：总开关无 `where` → 显示该图高资点总数；子类 → 显示「能刷出这一类」的点数（**各类相加会大于总数，因为一个点可能属多类**）。
3. **总开关的三态**：`syncValuableMaster()` 由 7 个子类**推导**总开关状态（全开 = 勾上、部分开 = `indeterminate` 半勾、全关 = 空），
   并把推导结果写回 `state.layers.valuables`（便于持久化与 `mergeLayers`）。`syncLegendState()` 里**半勾也算「开」**，
   否则总开关那行会被压暗。点总开关 = 一键把 7 个子类全开 / 全关。
4. **渲染去重**（本轮最容易写错的地方）：`renderOverlay()` 里**跳过所有 `kind === "valuables"` 的 spec**，
   改用 `valuableUnionSpec()` ——它的 `where` 是「该点所属类别 ∩ 已开启类别 ≠ 空」，并在**遇到第一个 valuables spec 时整体画一次**。
   不这么做的话，一个同属 2 类的点会在两行开关下各画一遍，**同一点叠两层图标**（旧代码是「一个 kind 一个开关」才成立）。
5. **搜索联动**：`enableLayersFor()` 加了 `!spec.master` 过滤 —— 总开关只是汇总，**勾上它并不让任何点出现**，
   所以搜到某个高资点时应当只打开**它所属的那个子类**（实测：搜「比特币」→ 自动打开「比特币」子类，总开关保持半勾）。
6. **图例**：子类行加 `.legend-sub`（`style.css` 里 `padding-left:22px` 缩进）；`legendIcon()` 把 `spec.icon` 的判断**提到最前**
   （原来 `kind === "valuables"` 早返回通用宝石，会导致子类行显不出各自的图标）。

**默认值**：`DEFAULT_ON` 去掉 `valuables`、加上 `valuable_btc / valuable_moonshine / valuable_keycard`；
`defaultLayers()` 里用 `out.valuables = VALUABLE_CATS.every(...)` 补算总开关。

**实测数据（街区，主楼层）**：该图高资点共 **229**；子类点数 比特币 149 / 私酒 51 / 钥匙卡类 6 / 钥匙类 26 / LEDX 12 / 除颤器 11 / 其他 0；
默认三子类下地图上实际画出 **169** 个高资点标记（229 是含全部楼层的原始计数，`countOfSpec` 不随切层变）。

**验证**：`node --check app.js` 通过；`python -m pytest -q` → **474 passed, 1 skipped**；浏览器实测（Chrome DevTools，隔离上下文，127.0.0.1:8787）：
初始 = 比特币 / 私酒 / 钥匙卡类 勾上、总开关**半勾**、169 个标记；点总开关 → 7 个子类全勾、206 个标记；再点 → 全不勾、0 个标记；
只勾「钥匙类」→ 总开关半勾、26 个标记；搜「比特币」→ 1 条「实体比特币 · 高级资源点 · 149 处」、搜「除颤器」→「便携式除颤器 · 11 处」、
搜「物资埋藏桶」→ 仍恰好 1 条；点该条 → 自动打开「比特币」子类、总开关保持半勾。7 个子类图例行各自显示专属 PNG 图标（非宝石兜底）。

**新增踩坑**（已进 §8）：总开关改的是「别人的」勾选状态，**不能只调 `syncLegendState()`**——它只改 `data-on`，
子类的 `input.checked` 还停在旧值（实测踩到：点总开关后子类框没跟着勾上）。总开关的 change **必须整块 `renderLayerToggles()`**。

### 6.13 第八轮：实验室 / 迷宫用「构建期拼瓦片」接入 ★（第八轮）

用户口径：「**实验室和迷宫先做 明天我再试**」。这两张图第六轮已判「不做」（§6.11），本轮改用**构建期拼瓦片**接入，
**前端一行都没改**（`app.js` / `style.css` / `index.html` 均未动）。数据 schema 由 5 升到 **6**。

**为什么拼瓦片而不是用社区 SVG**：第六轮实测社区 `Labs.svg` 的绘制宽高比（1.237）与上游 `bounds`（1.372）差约 10%
（§6.11），接入会整图拉伸、标记错位；迷宫更是连 SVG 都没有。上游对这两张图只给**瓦片**（`labs_v4/*`、`labyrinth/main/*`），
所以走「**构建期把瓦片按上游自带的 `transform` / `bounds` 摆进一个合成 SVG**」这条路，坐标完全走上游，前端零改动。

1. **`tools/fetch_data.py` 新增整段瓦片逻辑**（`svg_basename` 后、`select_maps` 前）：常量 `TILE_ZOOM = 3`、`TILE_WORKERS = 8`、
   `TILE_EMPTY_MAX = 512`；表 `TILE_MAPS`（`the-lab` / `the-labyrinth`，各带输出 `file` 与构建期补的 `layerIds`）；函数
   `svg_num()`（去浮点噪声，`-0.0` 归一成 `0`）、`tile_pixel_rect(transform, rotation, bounds)`（世界矩形 → base-pixel 矩形）、
   `tile_grid(...)`（像素矩形 → 瓦片 x/y 索引区间）、`layer_world_bounds(entry, layer)`（优先用 `extents[].bounds`，退 `entry.bounds`）、
   `apply_tile_layer_ids(entry, key)`（给上游没有 `svgLayer` 的层补层 id）、`tile_svg_document(viewbox, groups)`、
   `tile_file_name(...)`、`fetch_tile(url, cache_path, force)`（并发下载 + 缓存 + 空瓦片判定）、`build_tile_svg(key, entry, force)`。
   `select_maps` 放宽为「有 `svgPath` **或**在 `TILE_MAPS` 里」；`build_map` 加 `svg_name=None` 形参（合成 SVG 走显式名）。
2. **合成 SVG 的几何**：`viewBox="0 0 W H"`（**原点必须是 0,0**——`coord.compute_world_to_svg` 只按 bounds/viewBox 宽高算 scale 且假定原点在 0,0）。
   顶层每个 `<g id>` 是一层，组内按瓦片在 base-pixel 网格里的真实位置摆 `<image x y width height preserveAspectRatio="none">`，
   `href` / `xlink:href` 都用**相对文档路径** `assets/maps/tiles/<mapkey>/<文件名>`（`document.importNode` 注入内联后按文档 base 解析）。
   旋转为 90° 整数倍时像素两轴各只依赖一个世界轴（270° 时 `pixelX` 只依赖 `z`），世界矩形正好铺满底图矩形。
3. **楼层 id 构建期补**：主层 `First_Floor`；`the-lab` 的 `Second Level` → `Second_Floor`、`Technical` → `Technical_Floor`；
   迷宫主层 `Ground_Level`。`tools/floors.py` 的 `FLOOR_LABELS` 加「`Technical_Floor`: 技术层」、`FLOOR_ORDER` 加 `Technical_Floor: -40`
   （在 `Bunkers: -30` 之上、比 `First_Floor: 1` 低）。
4. **体积权衡**：`TILE_ZOOM = 3` 共 **120 张瓦片、6.17 MB**（labs 三层 1.96 / 1.01 / 0.77 MB + 迷宫 2.44 MB）；
   z=4 约 23 MB 而肉眼无提升，故取 3。空格子返回**200 + 102 字节全透明 PNG**（非 404），用**字节数 ≤ 512** 跳过。
5. **`tools/serve.py`**：`EXTRA_TYPES` 加 `".png": "image/png"`（实测响应头正确）。
6. **测试**：`tests/test_fetch_data.py` 新增「瓦片底图」整段（`tile_pixel_rect` 与 `world_to_svg` 对齐、退化 bounds 抛错、
   `tile_grid` / `layer_world_bounds` / `apply_tile_layer_ids` / `tile_svg_document` / `svg_num`、空瓦片跳过、缺 `tilePath` 报错、
   `TILE_MAPS` 只列无 `svgPath` 的图）；`test_meta_counts_match_reality` 加实算 `tileMaps` / `tileBytes`；
   `test_build_map_uses_explicit_svg_name`；`tests/test_floors.py` 的 schema 断言升为 6。

**验证**：`python -m pytest -q` → **488 passed, 1 skipped**；构建输出「12 张图 / 底图 7.6 MB / 索引 2000 KB」，
labs 一/二/技术层各 34/23/23 张、迷宫 40 张瓦片；浏览器实测（127.0.0.1:8787）：实验室一层截图里地名标注（Security Office /
Conference Room / Server Room 等）与撤离点全部落在对应房间/门口；点「二层」→ `Second_Floor` 全亮、`First_Floor` / `Technical_Floor`
opacity 0.25（下层 ghost）；单看二层的截图与单看一层用 PIL 比对 `mean diff 13.38`（确实渲染了不同内容）；
网络请求 80 张瓦片全 200、无 404；迷宫 `groups == ["Ground_Level"]`、40 张瓦片、楼层块自动隐藏（单层）；
迷宫页搜「钥匙」→ 13 条，首条「停尸房钥匙 · 高级资源点 · 6 处」。

**新增踩坑**（已进 §8）：合成 SVG 的 viewBox **原点必须是 0,0**；上游这两张图的瓦片层**没有 `svgLayer`**，必须在构建期补层 id；
270° 旋转下世界矩形四角映射到 viewBox 的**另外两个对角**（断言要取四角映射后的 min/max）。

---

### 6.14 第九轮：发布三件套（Setup / 解压即用 / 加壳版）+ 上 GitHub ★（第九轮）

用户口径：「**项目可以发布了 直接发github 然后能不能做3个版本 一个是setup一建安装 一个是解压即用 还有一个是加壳版本不用浏览器的webui**」。
三个决策（AskUserQuestion 作答）：GitHub → **装 gh CLI 并由用户登录、我来全流程**；加壳版形态 → **独立应用窗口（`--app` 模式）**；安装包方式 → **PyInstaller 自建 `setup.exe`**。
**前端一行没改**（`app.js` / `style.css` / `index.html` 均未动），只动启动器与构建脚本。

1. **`tools/launcher.py` 加「应用窗口模式」**（加壳版核心）：新增常量 `APP_MODE_FLAG = "appmode.flag"` 与 `_APP_WINDOW_BROWSERS`（Edge 优先、Chrome 次之，
   路径含 `%ProgramFiles(x86)%` / `%ProgramFiles%` / `%LocalAppData%`）；函数 `app_mode_enabled()`（资源目录里有没有那个 flag）、
   `find_app_browser()`（找第一个存在的内核，找不到返回 `None`）、`open_app_window(url)`（`subprocess.Popen([exe, "--app=%s" % url])` 开无地址栏窗口，
   失败或找不到内核就 `return webbrowser.open(url)` 兜底）。`main()` 里 `open_browser` 的装配顺序是
   `--no-browser`（啥都不开）→ `--app-window` 或 `app_mode_enabled()`（开应用窗口）→ 否则默认浏览器。
   新参数 `--app-window`（源码运行时试同一效果）。**行为与普通版完全一致，只是「开界面」那一步换了实现。**
2. **`tools/installer.py`（新建，纯标准库自建安装器，约 260 行）**：`--add-data "$Target;payload"` 把整站塞进安装器；
   向导（tkinter，进度用 `queue.Queue` + `root.after(100, self._pump)` 轮询，避免线程直接碰控件）装到 `%LOCALAPPDATA%\EFTMap`，
   建开始菜单 / 桌面快捷方式（借 PowerShell 的 `WScript.Shell`：写临时 `.ps1` 再 `-File` 调用，避开引号地狱），
   写「控制面板 → 程序和功能」卸载项（`winreg` 的 `HKCU\...\CurrentVersion\Uninstall\EFTMap`），并把自己复制成 `Uninstall.exe`。
   桌面真实路径从 `HKCU\...\Explorer\User Shell Folders\Desktop` 读（防 OneDrive 重定向）；卸载时用 `cmd /c ping … & rmdir /s /q` **延迟删目录**（进程活在目录里删不掉自己）。
   命令：无参 = GUI 向导 / `--silent` 静默装 / `--uninstall` 卸载 / `--dir` 指定目录。`installer.VERSION` 由测试锁死 = `serve.VERSION`。
3. **`build/build_release.ps1`（新建）**：从 `tools/serve.py` 读 `VERSION`（`Select-String`）；跑 `build.ps1` 出 onedir；
   `Compress-Archive -Path $Target` 出 **Portable zip**；复制整站到 `$Staging\EFTMap` 并在 `_internal` 落 `appmode.flag`（`Set-Content -Encoding ascii`）出 **AppWindow zip**；
   PyInstaller onefile（`--noconsole --add-data "$Target;payload" tools\installer.py`）出 **`EFTMap-Setup-<ver>.exe`**。全部只用 PowerShell 自带命令 + 构建期 PyInstaller，**零第三方依赖**。
   `-SkipBase` 可跳过重跑 `build.ps1`。产物统一落 `release\`（已 gitignore）。
4. **`build.ps1` 与 `EFTMap.spec` 未动**（安装器另用一条 onefile 命令，不碰既有 onedir 流程）。
5. **测试**：`tests/test_launcher.py` 新增整段「加壳版（独立应用窗口）」7 条（flag 默认关 / `app_mode_enabled` 读资源目录 flag / `find_app_browser` 取首个存在的、找不到返回 None /
   能起 `--app` 并返回 True / 找不到内核退回默认浏览器 / 起不来也退回）；`tests/test_installer.py`（新建）6 条
   （版本号与 `serve.VERSION` 一致 / 默认目录用 `%LOCALAPPDATA%` / 快捷方式名含 App 名 / 无 payload 时 `install_into` 抛错 / 拷贝 payload 并落注册表 / 不勾桌面就不建桌面快捷方式），
   桩件替换 `create_shortcut` / `write_uninstall_entry` / `installer.sys.executable`（后者需指向**真实存在**的假 exe）。

**验证**：`python -m pytest tests -q` → **501 passed, 1 skipped**（488 原有 + 7 launcher + 6 installer）；
`build_release.ps1` 实跑成功，`release\` 三件套：`EFTMap-Portable-0.1.0.zip`（20.0 MB）/ `EFTMap-AppWindow-0.1.0.zip`（20.0 MB，内含 `EFTMap\_internal\appmode.flag`）/ `EFTMap-Setup-0.1.0.exe`（31.7 MB，单文件）。

**新增踩坑**（已进 §8）：PowerShell 5.1 读**无 BOM 的 UTF-8 `.ps1`** 会按 ANSI 解码 → 中文乱码 + 解析失败，新脚本必须加 UTF-8 BOM；
PyInstaller `--add-data "<目录>;<dest>"` 是**把该目录的「内容」复制进 dest**（不再套一层目录名），故 `payload_root()` = `<bundle>/payload`。

---

### 6.15 第十轮：街区狙击区坐标修正 + 前端四项体验改动 ★（第十轮）

用户口径：「街区的这个危险区位置错了 实际上应该在 x-203/z0 x-273/z12 x-192/z67 x-262/z79 另外这是狙击区域 …
所以没有 y 轴；btr 的站图标在地图上有点小了 可以从现有大小放大一倍；点击地图上的小图标后显示的小浮窗可以增加一个淡入淡出的效果
… 和上锁的门一样 也会显示物资的小图标；再增加一个整体地图上的图标缩放的滑动按钮（4k 屏幕上这些图标太小了，1080p 又差不多）」。
共 5 项：① 修数据 ② BTR 图标 ×2 ③ 浮窗淡入淡出 ④ 浮窗带物资小图标 ⑤ 图标整体缩放滑条。

1. **① 狙击区坐标修正（唯一动数据的一项，schema 不变仍为 6）**：原记录画在 x -40～-103 一带（`x:-71.9 z:0.6 y:8.5`，带高度），
   实际在街区西北角。用户给 4 个顶点，但**按原顺序连会自交（蝴蝶结）**——A(-203,0)→B(-273,12)→C(-192,67)→D(-262,79) 的叉积符号翻转；
   改成 A→B→D→C 后 4 个叉积同号（凸多边形），最终写入 `outline = [[-203,0],[-273,12],[-262,79],[-192,67]]`；
   **`position` 是所有上游危险区共有的约定：等于 `outline` 的面积质心**，所以改轮廓必须同时改中心点 → `x:-232.49 z:38.8`；
   狙击区无高度含义 → **删掉 `y` 字段**。改动落在 `data/maps.json`（数据是入库的，直接改）**并**在 `tools/fetch_data.py` 加覆盖表
   `HAZARD_FIXES` + `apply_hazard_fix(map_key, point)`（键是 `(地图 key, 原 x, 原 z)`，在 `build_map` 的 hazards 循环末行调用），
   否则哪天真跑 `--force` 会被上游数据冲回去。
2. **② BTR 停靠点图标放大一倍**：`makeMarker()` 里 BTR 分支改成 `signIcon(iconKey, unit * 2)`（其它图标仍用 `unit`）。
   实测 DOM：`g.emk-sign-btr` 的 `transform="scale(3.046…)"` = 2 × 其它标记徽章的 `1.523…`。
3. **③ 浮窗淡入淡出**：`#marker-pop` 是 **HTML `<div>`**（不是 SVG 图元，所以能安全用 CSS `opacity` transition——老坑「给 SVG 加动画会整张栅格化」不适用）。
   新增 `POP_FADE_MS = 180` + `markerPopNode`：`hideMarkerPopup()` 不再立刻 `remove()`，而是摘掉 `.show` 类后**延时 `POP_FADE_MS` 再摘除节点**；
   `showMarkerPopup()` 建好用 `requestAnimationFrame` 再加 `.show`（否则同帧加类不会触发过渡）。样式：`.marker-pop { opacity:0; transition: opacity .18s ease-out }` + `.marker-pop.show { opacity:1 }`。
4. **④ 浮窗带物资小图标**：新增 `inlineIconAny(value)`（字符串走 `inlineIcon`、SVG 元素直接包一层 `.inline-ico`），
   浮窗行渲染改为「有图标就先 append 图标再 append 文字」；`detailRows()` 的容器行给 `lootIconSvg(item.group)`、
   高资点行给 `signIconSvg(valuableIconKey(item.items))`，`showDetail()` 同步改用 `inlineIconAny`。
   实测：容器浮窗 `hasSvg=true`、文本「技术物资箱 / 类型 物资容器 / 容器类别 物资箱」；高资浮窗同样 `hasSvg=true`。
5. **⑤ 图标整体缩放滑条**：HUD 里加 `<input id="icon-scale" min=.5 max=3 step=.05>` + 百分比标签。
   **机制：只能乘进 `updateCounterScale()` 的系数**（`var inv = iconScale() / state.z;`）——**绝不能**给 SVG 元素加 CSS `transform`/`animation`（§2 铁律）；
   `state.iconScale` + `iconScale()` + `setIconScale(value, persist)`（钳 0.5–3）；`pinRingRadius()` 与 `showDetail()` 的图标高亮环半径也要乘 `iconScale()`（纯圆点分支不乘，圆点本身随组缩放）。
   持久化走既有链路：`localStorage['eftmap.icon.scale']` + `uiPatch()` 的 `ui.icon_scale` → `tools/config.py` 的 `merge_ui` / `_normalize_ui`（`clamp_icon_scale`，只认真数字、bool 不算）→ SSE `config` → `applyUiPrefs()`。
   实测：滑条设 2.6 → 标记 `scale(1.478) = 2.6/1.759(z)`、标签「260%」、`localStorage` 写入；重载后滑条回到存值。

**验证**：`python -m pytest tests -q` → **515 passed, 1 skipped**（501 原有 + 9 `test_clamp_icon_scale` 参数化 + 2 `_normalize_ui`/`merge_ui` + 3 hazard fix 数据级）；
`node --check app.js` 通过。运行时（本地服务 8899 + Chrome DevTools MCP，街区图）：
修正后的多边形 bbox 81.3×79.4 px 与 4 个顶点的世界跨度（81×79 单位、≈1.004 px/单位）逐边吻合，点开详情显示「世界坐标 x -232.49 / z 38.8」且**无 `y` 与「所在层」行**；
BTR 图标 `scale(3.046)` = 2×；浮窗 `class="marker-pop show"`、`transition: opacity .18s ease-out`、300ms 后 `opacity=1`，
连点两点时**同时存在 2 个 `.marker-pop`**（旧的 0.47 正在淡出）→ 400ms 后回到 1 个。

**新增踩坑**（已进 §8）：改危险区轮廓必须同步改 `position`（面积质心）；用户给的顶点顺序可能是自交的，要按叉积同号重排；浮窗淡出必须延时摘除节点。

---

### 6.16 第十一轮：高资子类修正 + 单一固定浮窗 + 地名绑地图 + 启动器试听 + 位置按截图差分 ★（第十一轮）

用户口径：「点了上锁的门怎么会显示两个浮窗 … 点击后在图标位置显示的浮窗描述最好，但**固定在左上角**那种我比较喜欢；图标缩放我希望**只对图标生效、不对地名生效**，
地名应该**随地图缩放、和地图绑死**；导航现在拉直线，能不能像高德一样沿道路走；启动器里的声音提示后面再加一个**预览提示音**；
检测到有**新的截图**了再自动定位一次，没新截图就不要定位；勾选**私酒**地图上会出现一部分的**钥匙刷新点**；**LEDX** 刷新点有几个图标是**除颤器**（同时刷就用 LEDX 图标，价值高）；
还有个**显卡**也要单独分开加进高资里；`https://solidvents.com/zh-CN/` 可以免费生成矢量图，看看对这个项目有没有用」。
共 8 项（含上一轮的 3 项纠正）。

1. **① 上锁的门只留一个浮窗（固定左上角）**：删掉整段「钥匙小浮窗」（`lockHintTimer` / `hideLockKeyHint()` / `showLockKeyHint()`）与 `style.css` 里全部
   `.lock-hint*` 规则；`onOverlayClick` 只调 `showDetail()` + `showMarkerPopup(state.map, kind, item)`（**去掉 `node` 参数**）。
   `showMarkerPopup()` 的定位改成 `el.stage` 的 `getBoundingClientRect()` + 12px（`position: fixed`，不跟图标跑），内容仍是 `detailRows()` 全部行（含「需要钥匙」+ 该钥匙的专属图标）。
   `selectMap()` 里只留 `hideMarkerPopup()`。**实测**：点锁 → `#marker-pop` 恰 1 个、`.lock-hint` 0 个、`left/top` = `stage.left+12 / stage.top+12`（312px/43px），文本「锁类型 上锁的门 / 需要钥匙 酒店215房间钥匙（酒店215）」+ 1 个 `.inline-ico`；320ms 后仍只有 1 个（旧的已淡出摘除）。
2. **② 地名与地图绑死（不再受图标滑条影响）**：`renderLabels()` 里地名节点**不再 push 进 `state.markerScaleNodes`**、不再带 `__emkBase`，transform 改成纯 `translate(sx sy)`（去 `scale`）；
   字号仍 `12*unit`、描边 `2.4*unit` → 缩放地图时跟着底图等比放大缩小。**实测**：滑条 1→2 时地名屏幕宽度比 **1.000**、标记比 **2.000**；地图滚轮放大时地名比 **1.149**、标记比 **1.000**。
3. **③ 导航沿道路走**：**本轮不做**（用户已确认先保持直线）。要做得引入路网数据（上游没有现成路径图），与「不联网 / 只用本地素材」冲突，留作后续待办。
4. **④(⑤) 高资子类修正**：根因是 `valuableIconKey()` 的**校验顺序**——旧逻辑先全局查 `KEY_ICONS` 精确表、再按 `VALUABLE_ICON_RULES` 的 rule-major 顺序首命中，
   于是「私酒 + 某把钥匙」的点被钥匙图抢走（看起来像钥匙刷新点）、「LEDX + 除颤器」的点被 `/除颤/` 抢走。
   改成**按价值分层遍历规则（外层 rule）、内层扫物品名，命中即止**：`BTC → 私酒 → 显卡 → LEDX(透照/注射) → 除颤 → 六色钥匙卡 / 生活区 / Object 卡 → 钥匙卡 → 钥匙 → 文件夹`，
   同层里若该物品名在 `KEY_ICONS` 里有专属实拍图就贴真图，否则用该层通用图标；末尾再兜底扫一遍 `KEY_ICONS`（如「灯塔便利店储藏室」）。
   **实测**：私酒点 → `emk-png-valuable_bottle`（`val-bottle.png`）；LEDX+除颤器点 → `emk-png-valuable_med`（`val-ledx.png`）。
5. **⑥ 新增「显卡」高资子类（schema 6 → 7）**：上游物品**中文名是「显示卡」**（ShortName 才是「显卡」），
   `tools/fetch_data.py` 的 `HIGH_VALUE_ITEMS` 加 `"显示卡"` + `SCHEMA = 7`；`app.js` 的 `VALUABLE_CATS` 加 `{ key:"gpu", label:"显卡", icon:"valuable_gpu", match:/显卡|显示卡/ }`
   （排在 moonshine 后、keycard 前），`DEFAULT_ON` 加 `valuable_gpu: true`（默认只开 BTC / 私酒 / 显卡 / 钥匙卡类）。
   **显卡没有实拍素材**（`assets/icons/` 与源图 `ui图标\clean\` 里都没有）→ 按实物**手画 SVG**（`SIGN_ICONS.valuable_gpu`：卡身 + 大风扇 + 散热片 + 金手指），`SIGN_COLORS.valuable_gpu = "#8ab6a0"`。
   数据**离线重跑**（走 `build-cache/`，不联网）：12 张图重建完成，valuables 由约 1118 → **1208** 点（其中**仅显卡** 94 点）。
6. **⑦ 启动器「试听」提示音**：`tools/launcher.py` 新增模块级 `DEFAULT_TONES`（与 `app.js` 的 `DEFAULT_TONES` **数值一一对应**）、
   `render_tone_wav()`（三角波 + 15ms 线性起音 + 指数收尾，`wave` 写 16 位单声道）、`preview_wav()`（落临时目录，同 key 只合成一次）、
   `play_audio()`（`.wav` 走 `winsound SND_ASYNC`，其它格式 `os.startfile`）；`_sound_row()` 每个提示音那行加「试听」按钮（一并进 `sound_children`，跟随总开关禁用），
   `_preview_sound(key)`：选了自定义音频就播它、**文件丢了就报错**，没选就播现场合成的内置音——**保证「试听听到的」= 「游戏里响的」**。
7. **⑧ 位置只在有新截图时定位**：`serve.py` 的 `PositionTracker` 本来只在 `name`/`mtime` 变化时才推帧，问题在前端两处**与截图无关**的定位：
   `applyConfig()` 里无条件 `applyAutoZoom()`（页面每次写回图层偏好都会广播 `config` → 视角被弹回玩家位置）、`applyPosition()` 不区分新截图。
   现在 `applyConfig()` 删掉那次调用；`applyPosition()` 算出 `fresh = pos && (name 或 mtime 变了)`，`!fresh` 时只更新状态/玩家标记就 `return`。
8. **⑨ 评估 `solidvents.com`**：那是**参数化图纹生成器**（喇叭网孔 / 散热孔 / 渐变网点 / 半色调，导出 SVG·DXF·STEP），**不是通用矢量插画 / 图标生成器**——
   与本项目的需求（物品图标来自用户实拍素材、底图来自上游瓦片）对不上，且导出物的授权条款未在站点声明，与「只分发 MIT / CC BY-NC-SA」的铁律有冲突风险 → **不引入**。
   若将来要给危险区做半色调网点纹理，可当**一次性离线生成静态素材**的工具用（生成后入库，不引入运行期联网）。

**验证**：`python -m pytest tests -q` → **520 passed, 1 skipped**（515 + 5 条试听相关：`DEFAULT_TONES` 与 `SOUND_KEYS` 对齐、WAV 时长与表一致、`preview_wav` 只合成一次、没选音频播内置音、自定义文件丢失要报错；
另把写死 schema 的 `test_data_is_schema_6` 改成与 `fetch_data.SCHEMA` 对比，免得以后每次升版都要改测试）；`node --check app.js` / `python -m py_compile tools/launcher.py` 通过。
运行时（本地服务 8899 + Chrome DevTools MCP，街区图）：见上面各项「实测」。

**新增踩坑**（已进 §8）：`valuableIconKey` 的校验顺序必须**按价值分层**（旧的「全局先查 KEY_ICONS + rule-major」会让低价值物品抢图）；地名与图标要分开处理（地名不进 `markerScaleNodes`）；与截图无关的事件（配置广播）绝不能触发自动定位。

---

### 6.17 第十二轮：海岸线三狗锚定气象站 + 撤离 / 转移点徽章放大 ★（第十二轮）

用户口径：「另外区别于高资刷新点，再增加一个**高级子弹刷新点**；dev 的上游物资点是否有这些信息？还有各个**撤离点转移点**我希望也是**再大一点**，现在太小了；
然后海岸线，海岸线现在 sanitar 不会刷新在疗养院了，把疗养院的刷新点去除；然后是三狗，三狗现在**只会刷新在海岸线的气象站**，你现在的标点错了」。
经两轮澄清定稿：**Sanitar 不动**（用户口径「只有加油站、码头和豪宅会刷」→ 现数据 8 点全在码头 / 加油站 / ZoneGreenHouses 两簇，**没有一点落在疗养院轮廓内**，用户选择「两簇都保留」）；
**三狗只改海岸线**；**高级子弹不做**。共 2 项落地。

1. **① 海岸线三狗（Knight）改锚定「气象站」**：上游 `bossKnight` 的 `spawnLocations[ZoneMeteoStation].positions` **给了 10 个坐标，但实测全错位**——
   8 个落在村庄一带（世界 `x ≈ 328~462 / z ≈ 55~235`，即 svg 左侧 Village 附近）、2 个落在无线电塔一带（`x ≈ -575/-581`，svg 右侧），没有一个是气象站；
   地图地名 `Weather Station` 在世界 `(-496.0, 257.0)`（svg `999.7, 671.7`）。`tools/fetch_data.py` 新增 **`BOSS_ZONE_FORCE`** 覆盖表
   （键 `(图 key, 上游区域名)`，值 `(图例显示名, 地名文本)`），语义是「**上游给了坐标也照样整段换掉**」，优先级高于只兜 `positions` 为空的 `BOSS_ZONE_ANCHOR`。
   对应 `("shoreline", "ZoneMeteoStation") → ("气象站", "Weather Station")`，于是 Knight 与它的两个护卫（`followerBigPipe` / `followerBirdEye` 与 Knight 共用刷新区）只剩 1 个点、就落在气象站上。
   **实测**（本地服务 8787 + Chrome DevTools MCP）：海岸线 `.emk-marker.emk-bosses` 里有一点 `translate(999.725 671.671)` = 地名的 svg 坐标；搜索「Knight」只剩 1 条（`1 处`）。
2. **② 撤离点 / 转移点徽章放大 1.5 倍**：`app.js` 新增 `BADGE_SCALE = 1.5`，`badgeIcon(variant, unit)` 与 `badgeLabel(text, variant, unit)` 都乘它
   （**徽章 + 名字一起放大**，仍是「屏幕尺寸恒定」那套机制：外层 `scale(iconScale()/z)` 不变）；钉选环 / 选中环半径 11 → **12 屏幕像素**，罩得住变大的徽章。
   **实测**：地图徽章 `getBoundingClientRect()` 由 11 × 13.5 px → **16.5 × 20.3 px**（`scale` 由 2.203 变 3.304 = 1/fit × 1.5）。

**未做 / 评估结论**：**高级子弹刷新点**——见 §11「评估过但不采用（第十二轮）」，上游 `lootLoose` 的 5441 个散落刷点里**一件子弹都没有**（只有「弹药箱」「弹匣箱」这类容器），
与「高级资源点」同原理做不出来，用户据此决定不做。**Sanitar** 无需改动（见上）。

**验证**：`python -m pytest tests -q` → **520 passed, 1 skipped**；`node --check app.js` 通过。
数据是**离线重跑**的（先移走 `data/maps.json` + `data/meta.json` 让 `data_ready()` 判未就绪，走 `build-cache/` 与既有底图，全程不联网）；
重跑前后逐图层比对：**只有 `shoreline.bosses` 变（36 → 27 点）**，其余 11 张图、其余图层与 schema（仍 7）完全一致，`generatedAt` 也随之更新。

**新增踩坑**（已进 §8）：「上游有坐标」不等于「坐标是对的」——人工校正表要能**覆盖非空 positions**；徽章放大要连名字与高亮环半径一起改，否则选中环会罩不住。

---

### 6.18 第十三轮：收录破冰船（人工反推投影）★（第十三轮）

用户在上轮收尾时勾了三项：收录破冰船等剩余地图、三件套实机验证、导航沿道路走。本轮先做第一项——**破冰船（icebreaker）收录**，
复用第八轮的 `TILE_MAPS` + `build_tile_svg` 机制（§6.13，前端一行未改），但**多了一步「人工投影覆盖」**：上游这套 `transform` / `bounds` 照用会把标记甩到船体之外。

**上游数字与实体对不上**（证据链）：

1. 上游 `icebreaker` 配置：`tileSize=256`、`transform=[2.0,125.0,3.5,91.0]`、`coordinateRotation=180`、
   `bounds=[[77,-64.5],[-65.5,67.4]]`、16 个具名层（`00_control_room` … `15_bridge_roof`，主层 `tilePath` 指向 `06_infirmary`）。
2. **两处硬伤**：`transform` 是**各向异性**的（x 缩放 2.0、z 缩放 3.5），而其余 12 张图的 `transform` **全是各向同性**；
   `bounds` 与 **factory 一字不差**，明显是复制来的。
3. 照它算，船体瓦片内容在像素空间只占 `x[96,160] × y[0,256]`，对应世界 `x[-17.5,14.5]、z[-26.0,47.1]`；
   而 icebreaker 实体（56 出生点、1 撤离、78 散落战利品、161 boss）世界跨度是 `x[-11.7,13.6]、z[-78.3,82.3]`
   → 14 个实体的 z 远超船图 → `test_markers_mostly_inside_viewbox` 只有 **84.2%**（9/57 越界）。
4. 直连上游瓦片服务器扫 174 格：**非空仅 `x∈{3,4}, y∈{0..7}` 共 16 格，其余 126 格 404**（不是漏取，是船图与标记口径不一致）。
5. 把瓦片拼起来目视：船体完整（船艏八角形停机坪在上、船艉在下），没被裁切。

**反推自洽投影**（`tools/fetch_data.py` 的 `_ICEBREAKER_*` 常量）：按「船体瓦片内容的像素跨度 ↔ 实体的世界跨度」反推——
船体内容在像素空间占 `y[0,256]`（zoom3 的第 0..7 行，每行 32px），实体 z 跨度 `-78.3 ~ 82.3`（跨度 160.6）
→ **各向同性** `S = 256 / 160.6 ≈ 1.594` px/世界单位；x 取同一个 S（船体内容宽 64px ÷ 1.594 ≈ 40 世界单位，与船长 160 的船型比例相符），
船体内容在像素上居中于 `x=128` → 船中线世界 x ≈ 0.5（`t1 = 128.8`）；`t3 = S × 78.3`。
取景框 = 内容 `x[96,160] y[0,256]` 四周各留 4px（`92, -4, 164, 260`），`bounds` 由取景框**精确反推**（不手写四舍五入的常量）。
`TILE_MAPS["icebreaker"]` 因此多了 `projection` 键，新增函数 `apply_tile_projection(entry, key)` 在构建主循环里把它覆盖到 `entry` 上
（并 `pop("svgBounds")`，免得上游若补了它再盖回 `bounds`），跟在 `apply_tile_layer_ids` 之后调用。

**关键取舍：瓦片下标仍按上游画布取**。人工投影 + 取景框反推出的像素矩形（`92,-4,164,260`）恰好是上游画布
（`-29,-134.75,256,326.9`）的**子集**，所以 `tile_grid` 算出的 `x∈2..5, y∈-1..8`（40 格/层）全部命中已缓存/已存在的瓦片，不会 404；
同时 `image x = x*step - left` 与上游 `index*step` 约定一致，摆放不错位。**前端一行没改**。

**验证**：`ib_overlay.png` 叠图目视通过——出生点沿甲板合理分布、「直升机」撤离点正落在船艏停机坪上、地名也在船艏；
`test_markers_mostly_inside_viewbox` 三张瓦片图全 **100.0%（0 越界）**；全量 `python -m pytest tests -q` → **526 passed, 1 skipped**；
`tools/floors.py` 的 `FLOOR_LABELS` 加 16 条 `Deck_*` 中文名；数据**离线重跑**（移走 `data/*.json` 绕开幂等跳过，走 `build-cache/` 与既有底图），
构建输出「13 张图 / 底图 10.0 MB / 索引 2064 KB」，icebreaker 各层 40 格/层（非空 2~16），`floors.selectable` 16 项、`default = ["Deck_06_Infirmary"]`。
`data/maps.json` 的 icebreaker `viewBox = [0, 0, 72.0, 264.0]`、`worldToSvg` 各向同性（`a == e`）。

**新增踩坑**（已进 §8）：上游 `bounds` 与别的图一字不差就是**复制粘贴的信号**，别信；`transform` 各向异性只在「两个世界轴像素口径不同」时才合法，
本图恰恰不是——要用「瓦片内容像素跨度 ↔ 实体世界跨度」反推各向同性投影，且 `bounds` 必须由取景框**精确反推**（手写两位小数会让
`viewBox` 与索引在 4 位小数写出后差 7e-6，`test_shipped_svg_viewbox_matches_index` 会挂）。

### 6.19 第十四轮：导航沿道路走（构建期静态路网 + 前端同层 A*）★（第十四轮）

用户上轮勾的第三项：导航要**像高德一样沿道路走**，而不是把途经点用直线连起来。约束没变——**运行期零联网、零第三方库**，
所以路网必须**构建期**算好随包分发。

**分工**：`tools/roadnet.py`（新增）在构建期把底图矢量 `assets/maps/*.svg` 栅格化；`app.js` 只在浏览器里做一次加权 A\*。
`tools/fetch_data.py` 加了 `[5/5]` 步调用它（跳过分支也调），`data_ready()` **不检查路网**（缺了也不会触发联网重拉）。

**产物**：`assets/roadnet/<图 key>/<层 id>.bin`（每格 2 bit：0 不可通行 / 1 道路 / 2 可通行地形 / 3 难走，行优先 `idx = j*w+i`，4 格一字节、**低位在前**）
+ `data/roadnet.json`（每图的 `cell` / `origin` / 各层 `w`/`h`/`bytes`/`cells`）。10 张矢量图共 35 个位图、779 KB，索引 11 KB。

**为什么按 CSS 类分类、而不是按组名**：底图里 `<g class="road_tarmac road_small">` 的类名出自 tarkov.dev 的统一图纸规范，
10 张图完全一致；而组名（`Roads` / `road` / `Highways` / `Dirt_Roads`…）各图不统一，不可靠。`resolve_classes()` 取**最近的非空类**
（不能把祖先链并集——海关某层的 `Buildings-1` 是 `floor`，里面嵌的 `XX-1f-locked` 是 `locked`，并集会混成一个语义）。

**绘制顺序：语义优先级 + 一条文档顺序特判**。各图的**文档顺序并不统一**（灯塔的 `water` 画在 `land` 之前当海面底色，
海关的 `water` 却画在 `land` 之后当河塘挖洞），照文档顺序栅格化必然有一类图出错。所以 `PASSES` 按语义排
（地形填 → 道路填 → 道路线 → 难走填 → 难走线 → **水填** → 边界线）。唯一要看文档顺序的是水：
**画在第一个地面图元之前的水面 = 背景海面**（灯塔那个 7 顶点大三角），它在真实底图里被后画的陆地盖住，
而默认码 0 本来就已经是「禁行」，所以直接跳过，别让它在最后一趟把陆地反盖成海 → `_first_ground()`。

**栅格化细节**：填充用扫描线 + 活动边表 + **奇偶规则**（所以多边形里的孔会被挖掉）；描边用 DDA 采样 + 方形膨胀（Chebyshev 半径 = 类别半宽，
`road_small/medium/large` = 5/8/12）；曲线按两端距离定步数展平（4~32 步）；格子边长 `clamp(min(vbw,vbh)/250, 0.5, 4.0)` 再按 `MAX_CELLS=400000` 放大。

**前端 A\***（`app.js` 的「同层路网寻路」段）：懒加载位图（`roadnetNet(mapKey, floorId)`，第一次调用返回 null 并异步下载，
载完/失败都写进 `state.roadnetCache`）、`cellOfPoint`/`pointOfCell`（用 `worldToSvg` 的**逆阵**，带旋转的图（工厂）也成立）、
`snapCell`（起终点落在禁行格时环形外扩，半径 14）、`astar`（数组二叉堆 + lazy deletion、8 邻域、**对角要求两侧正交格都可通行**、
代价表 `[∞,1.0,1.6,3.0]`、octile 启发）、`smoothCells`（LOS 视线简化，0.25 格采样贪心拉直）。
`routeGeometry()` 逐段拼折线：**同层**走 `roadSegment()`（拿不到路网 / 跨层 / 走不通 / 只隔一格 → 返回 null 回落直线），跨层与瓦片图（实验室 / 迷宫 / 破冰船）自然全是直线。

**验证**（Chrome DevTools 实机）：
- 海关「狙击手路障 → 行政区大门」：A\* 原始路径 **313 格中 309 格是道路码**（98.7%），面板显示「（沿道路）」。
- 海关「通往港口的铁路 → 物资埋藏桶」（直线被水域挡住）：折线 7 点、弯曲比 1.18，面板「路程约 418 米（沿道路）」。
- 三个途经点：折线 9 点、无重复坐标、`nodes=3`，面板「共 3 个点 · 路程约 615 米（沿道路）」。
- 灯塔修 `_first_ground` 前后：禁行 51.7% → **4.4%**，其余 9 张图数值**一字未变**（无回归）；全量 `pytest` **555 passed, 1 skipped**。

**本轮踩的两个前端坑（已进 §8）**：① `routeGeometry()` 不能先把所有途经点铺成一排再接拐点，否则第一段画成「起点 → 终点 → 绕回终点」的星形；
② 位图异步到位后要**连面板一起刷新**（`renderOverlay()` 只管折线、不管 `#route-summary`）。

---

## 7. 前端要点（改 `app.js` 前必读）

- **图层开关表** `LAYER_SPEC`：按 6 组组织（撤离点 / 转移点、物资、出生点、钥匙与门、危险区域、其他），每项 `{ key, label, kind, where, dot, icon?, badge?, master?, sub? }`。`DEFAULT_ON` 控制默认开哪几个；**14 类物资容器默认全开**；**高级资源点默认只开 比特币 / 私酒 / 显卡 / 钥匙卡类**（其余 4 个子类默认关）；其余只有撤离点、转移点、危险区、Boss、地名、固定武器默认开。
- **高级资源点子类**（第七轮建、第十一轮扩到 **8 类**）：`VALUABLE_CATS`（8 类，各带 `match` 正则，**`/钥匙卡/` 必须排在 `/钥匙/` 前**）+ `valuableCatsOf(item)` 判归属（有物品名一件都不命中就补 `other`）。「物资」组第一行是 `master:true` 的总开关 `valuables`，后跟 8 个 `sub:true` 的 `valuable_<cat>`。总开关状态由 `syncValuableMaster()` 从子类**推导**（半勾 = 只开了一部分），`syncLegendState()` 里**半勾也算「开」**。
  **渲染不能按开关逐个画**：`renderOverlay()` 里所有 `kind === "valuables"` 的 spec 都跳过，改用 `valuableUnionSpec()`（「所属类别 ∩ 已开启类别 ≠ 空」）整体画一次，否则同一点会在两行开关下叠两层。`enableLayersFor()` 必须过滤 `spec.master`（总开关不参与「打开某图层」）。
  **改子类划分只动 `VALUABLE_CATS` 一处**，`LAYER_SPEC` / `DEFAULT_ON` / 渲染都会跟着走（`DEFAULT_ON` 里记得同步 `valuable_<cat>` 的默认）。
- **图层开关的 change 监听必须挂在容器 `#layer-toggles` 上用事件委托**。图例 DOM 会整体重建，逐个 checkbox 绑定会丢监听 → 会出现「取消勾选后标记仍然显示」的 bug（已踩过，见 §8）。
- **图标尺寸在屏幕上恒定的机制**：底图缩放走 SVG `viewBox`（不用 CSS transform）；标记挂在 `g[transform=translate(...) scale(...)]` 上，图标内容再乘 `unit = 1/state.fit`（1 屏幕像素对应的用户单位）；同时把标记节点收进 `state.markerScaleNodes`，靠父级的 `scale(1/z)` 抵消，保证不随缩放变大变小。**新图标必须走同一套机制**。**「图标」滑条（§6.15）改的是这个恒定尺寸的倍数**：`updateCounterScale()` 里用 `iconScale()/state.z`，**绝不能**给 SVG 元素加 CSS `transform` / `animation`（会被栅格化）。**地名不在 `markerScaleNodes` 里**（第十一轮起）——它要**跟地图绑死**，随 viewBox 缩放等比变大变小，滑条管不着它（见 `renderLabels`）。
- **选中高亮环**：对画图标的图层（`ICON_KINDS = ["containers","valuables","spawns","bosses","locks","btr"]`）统一按 ±10 屏幕像素外接；撤离点 / 转移点是 ±12（第十一轮 11 → 第十二轮 12，跟着放大的徽章走）。高亮环**必须是静态描边**，不能是动画。
- 物资图标：`LOOT_ICONS`（每类由 `body` / `mark` / `hole` / `thin` 等部件组成）、`lootIcon(group, unit)` 画地图上的、`lootIconSvg(group)` 画图例的（`viewBox="-8-8 16 16"`）。
- **图标素材（`ICON_PNG`）**：key → `assets/icons/*.png` 的贴图表。四个工厂函数（`lootIcon` / `lootIconSvg` / `signIcon` / `signIconSvg`）**开头都判断 `if (ICON_PNG[key]) { return pngIcon(key, unit) /* 或 pngIconSvg(key) */; }`**——命中就用 `<image>` 贴图，未命中仍走手画 SVG。**换图标只需往 `ICON_PNG` 加一行 + 放一张 64×64 透明 PNG 到 `assets/icons/`**；新 PNG 必须透明、居中、内容约占画布 86%（照 `tools/iconize.py` 的输出规格）。源图是**竖排图例**（一张图里多行）时，要在 `tools/iconize.py` 的 `JOBS` 里加 `band` 指定那一段，不能整图直接抠（`strip` 只取最左侧那一簇，会把上下行连起来）。
- **具体物品名 → 专属图标**：`KEY_ICONS`（中文名 → icon key 的**精确表**）。`valuableIconKey(names)` **按价值分层遍历 `VALUABLE_ICON_RULES`**（外层规则、内层扫物品名，命中即止；同层里该名字在 `KEY_ICONS` 里有专属实拍图就贴真图，否则用该层通用图标），末尾再兜底扫一遍 `KEY_ICONS`。**规则数组的相对顺序就是价值顺序**（`BTC → 私酒 → 显卡 → LEDX → 除颤 → 钥匙卡 → 钥匙 → 文件夹`），`/钥匙卡/` 在 `/钥匙/` 前——顺序错了就会出现「LEDX 点画成除颤器」「私酒点画成钥匙」这类图不对位的 bug（§6.16）。上锁的门「需要钥匙」行用同一个函数取图标（`inlineIcon()` 把图标塞进 HTML 文案）。**给某件钥匙配专属图 = 往 `ICON_PNG` 加一行 + 往 `KEY_ICONS` 加一行**，两者 key 名一致（`key_<物品id前8位>`）。
- **标记小浮窗**：`showMarkerPopup(map, kind, item)` / `hideMarkerPopup()` 建 `div#marker-pop`（HTML 元素，append 到 body、`position: fixed`），**定位在地图区左上角往里 12px**（`el.stage.getBoundingClientRect()`，不跟图标跑），8 秒消失；`detailRows()` 是浮窗与左侧面板共用的信息行来源。`onOverlayClick` 里**所有标记都调它**（`locks` 也在同一个浮窗里显示「需要钥匙」+ 对应钥匙图标，见 §6.9）。**别把它改成 SVG 元素**（会触发栅格化变糊的老坑，见 §8）。
  **「HTML 元素」这点是关键**：正因为它是 `<div>` 而不是 SVG 图元，才能安全地用 CSS `opacity` transition 做淡入淡出（§6.15）。淡入 = 建好后 `requestAnimationFrame` 再加 `.show`；淡出 = 摘掉 `.show` 后**延后 `POP_FADE_MS` 再 `remove()`**（旧的 `markerPopNode` 与新浮窗可短暂共存）。行渲染统一走 `inlineIconAny(value)`（字符串走 `inlineIcon`、SVG 元素包 `.inline-ico`），`detailRows()` 的物资行自带图标元素（容器给 `lootIconSvg`、高资点给 `signIconSvg`），所以浮窗和「标记详情」都能显示物资小图标。
- 撤离点 / 转移点徽章：`BADGE_SHAPE`（盾牌路径）+ `BADGE_RUNNER`（奔跑小人）+ `badgeIcon(variant, unit)` / `badgeIconSvg(variant)` / `badgeLabel(text, variant, unit)`，颜色由 CSS `.emk-badge-<variant> .badge-bg { fill: var(--extract-*) }` 给。**第十二轮起整体乘 `BADGE_SCALE = 1.5`**（徽章与名字都放大，实测 11×13.5 → 16.5×20.3 屏幕像素）；图例那枚 `badgeIconSvg` **不放大**（图例本身尺寸合适）。
- **顶部菜单栏**：`bindMenu()` 管 `#menu-raid` 与 `#raid-block` 的开合（点按钮 toggle / 点面板外收起 / `Esc` 收起）。「战局与任务」整块（含 `#quest-log` 等原 id）都从侧栏搬进了这个面板；**要加新菜单项就往 `.menubar` 里再塞一个 `.menu-wrap`**，别把东西塞回侧栏。
- **界面偏好写回**：`uiPatch()` → `queuePrefs()`（400ms 防抖，`prefPending` 合并同一批键）→ `flushPrefs()` `POST api/prefs`，失败静默（`localStorage` 兜底）。`applyUiPrefs(ui)` 会拿服务端 `ui` 覆盖本地，但**值没变就跳过 `renderLayerToggles()` / `renderOverlay()`**——否则每次 `config` 广播都闪一下。`mergeLayers()` 只认 `state.layers` 里已有的键，服务端塞进来的野键会被忽略。
- **`auto_center` 的单一真源**：`state.cfgAutoCenter` 记住服务端上一次的值，`applyConfig` **只在它真的变化时**才 `setAutoCenter()`。拖动地图会 `setAutoCenter(false)`，那个是**不持久化**的（`setAutoCenter(on, persist)` 的 `persist` 只给 HUD 按钮传 `true`）；不这么做的话，页面每上报一次偏好就触发 `config` 广播，把用户锁定的视角顶回玩家位置。
- UI 框架是 **Windows XP (Luna) 浅色**（菜单栏 / 侧栏 / 弹出面板），但 **地图区与标记仍走原来的深色「卡带未来主义」配色**——用户明确要求「只改网页框架，图标不变」。`:root` 里两套变量（`--xp-*` 与原来那组深色）并按此边界使用，别把地图区也刷成浅色。
- **搜索**：`searchIndex(map)` 把**当前地图**的 `SEARCH_KINDS` 标记按 `kind|name` 聚合成「类型条目」并缓存到 `state.searchCache`（`selectMap()` 里置 `null` 使其失效）。
  `entryNameOf(kind,item)` 决定「名字」取自哪个字段：`labels→text`、`locks→keyName||name`、其余 `name`；
  **`valuables` 没有 `name`，要按 `items[]` 里的物品名展开**（否则比特币 / 私酒永远搜不到）。
  `scoreMatch()` 打分（完全相等 0 / 前缀 1 / 子串 2），排序 score → count → name，只取前 30。结果行 `searchRow()` 三段：主按钮 `focusEntry()` + `.search-pin` + `.search-route`。
- **钉选**：状态是 `state.pins = [{kind,name}]`，唯一键 `kind + name`（同名不同类型算两条）。标记侧判定走 `isPinnedItem(kind,item)`（比 `name` / `keyName` / `text` / `items`）。
  高亮环是 marker 的 **firstChild**（`circle.emk-pin-ring`，`prepend` 保证在图标底下）——所以 `showDetail()` 里取「选中环」时**必须先跳过它**。
  CSS 必须写 `.emk-marker circle.emk-pin-ring`（既要盖住 `.emk-marker circle` 的深色描边，又要 `vector-effect: non-scaling-stroke` + px 线宽）。持久化同图层：`localStorage` + `ui.pins`。
- **导航路线**：`state.route`（`{kind,name,x,z,y}` ≤60）+ `state.routeFromPlayer`。`routePoints()` 在勾了「从实时定位出发」且 `state.player` 存在时把玩家位置插到最前。
  折线 `polyline.emk-route-line` 必须带 `vector-effect="non-scaling-stroke"`（覆盖层直系子元素没有 `scale(1/z)` 补偿，不加会被缩放拉粗）；
  编号节点 `g.emk-route-node` 要 push 进 `state.markerScaleNodes` 并设 `__emkBase`，否则缩放时不会随标记保持屏幕大小。`renderRoute()` 在 `renderLabels` 之后、`updateCounterScale()` 之前调用。
- **沿道路寻路**（第十四轮）：`data/roadnet.json` 是**可选**的（`boot()` 里 `.catch(() => null)`），缺了导航照样能用、全走直线。位图按 `<图 key>/<层 id>` 懒加载进 `state.roadnetCache`（`null` = 该层没有位图，别再重试）。**只要动 `routeGeometry()` / `routeDistance()` / `renderRoutePanel()`，务必让「折线点数」与「面板文案」同源**——它们都吃 `routeGeometry()` 的返回值；位图是**异步**到位的，`roadnetNet()` 载完要同时调 `renderOverlay()` **和** `renderRoutePanel()`（前者只管折线，不管 `#route-summary`，漏了就会一直显示上一次的「（直线）」）。
- **`[hidden]` 强制 `display:none !important`**（写在样式顶部）：菜单面板、`#floor-block`、`#detail-block`、`#search-results` 都靠它；`.menubar` / `.block` 的 `display` 规则别写 `!important` 去盖它。
- **底图（含瓦片合成的 SVG）**：`buildSvg()` 把 SVG 根的全部 children `document.importNode` 进 `#emk-base`；`applyFloorVisibility()` 按**顶层 `<g id>`** 切 `display` / `opacity`（`GHOST_OPACITY = 0.25`，只选一层时下层 ghost），`mapFloorTops(map).length < 2` 时隐藏楼层块。实验室 / 迷宫的底图是构建期拼的**合成 SVG**——组内是 `<image href="assets/maps/tiles/…">`（相对文档路径），**前端不需要为瓦片做任何特殊处理**，走的就是同一套 `importNode` + 顶层组切层逻辑。`<image>` 也**绝不能**加 CSS `animation` / `transform`（同样会触发整张 SVG 栅格化变糊，见 §8）。

---

## 8. 踩过的坑（别重犯）

| 坑 | 真因 | 正确做法 |
| --- | --- | --- |
| 放大地图整张变糊 | 给 SVG 元素加了 CSS 脉冲动画 → 浏览器把整个 `<svg>` 栅格化 | 移除动画，改静态描边 + `text-rendering: geometricPrecision` |
| 图例取消勾选后标记还在 | 图例 DOM 重建后逐个绑的 `change` 监听丢了 | 容器事件委托 + 状态同步 |
| 打包后还是旧界面 | 浏览器缓存 | 服务端 `Cache-Control: no-store`，并让用户 `Ctrl+Shift+R` |
| 按目录名拼日志文件名匹配失败 | 日志**目录**带 `log_` 前缀、**文件名**不带 | 从实际文件名反推会话名 |
| `curl` / `urllib` 访问 `127.0.0.1` 报 502 | 本机设了 `HTTP_PROXY` 环境变量，本地请求被送去代理 | 加 `--noproxy "*"`，或 Python 用 `ProxyHandler({})` 建 opener |
| 误判物资点数量不一致 | 上游还有若干**未收录**的图（破冰船 icebreaker 等）也有刷点 | 比对时先排除这些图 |
| 图名被物品名顶掉 | 循环变量与地图名变量同名（§6.1） | 变量命名避开，并加回归测试 |
| 切到某层空无一物（如海岸线一层） | 上游没给该层的高度波段，该层标记全落到主层（§6.6） | 用 `FLOOR_BAND_EXTRA` 补波段（必要时加 `areas` 限定范围），并加数据级回归测试 |
| 重新打包后设置全没了 | `build.ps1` 每次 `Remove-Item -Recurse -Force dist\EFTMap`，连里面的 `eftmap.config.json` 一起删 | 配置与 `sounds/` 改存 `%APPDATA%\EFTMap\`，首次启动自动迁移（§6.7） |
| 页面上刚勾掉的图层过一会儿又自己亮了 | 启动器 `_save()` 落盘时 `build_config()` 不带 `ui` 键，`normalize()` 归成 `{}` 把偏好抹了 | `_save()` 先从磁盘读回 `ui` 再写；测试 `test_save_keeps_page_ui_prefs` 锁死（§6.7） |
| 勾一个图层整个右侧地图闪一下 | 页面 `POST /api/prefs` → 服务端广播 `config` → `applyUiPrefs` 无条件重绘 | `sameLayers()` 浅比较，值相同就直接跳过重绘 |
| 拖动地图后视角被弹回玩家位置 | `applyConfig` 无条件把服务端 `auto_center` 写回页面状态，而页面又在频繁上报偏好 | `state.cfgAutoCenter` 只在服务端值**真的变化**时才 `setAutoCenter()`；拖动那个 `false` 不持久化 |
| 浅色框架改完，几行次要文字颜色没跟着变（或被压掉） | `.muted` 原来声明在样式**底部**，同优先级下会盖过更早声明的单类规则 | 把 `.muted` 提到样式顶部，深色状态条另用 `.statusbar .muted` 改回浅灰 |
| 抠竖排图例时把上下行的图标一起抠进来 | `strip` 按 x 聚簇，上下行同一列会被并成一簇；`band` 起点填早了还会吃到上一行尾部 | 用 `band` 按行切；行边界靠脚本扫「无前景像素的横条」量出来再写死（§6.8） |
| 抠图优化后抠出的是「整行文字条带」而不是钥匙 | 把底色阈值写成「任一底色距离 > T 就算前景」（= max），浅色行背景会因离另一簇底色够远而被判成前景 | 阈值必须是 **min**：取到所有底色簇的**最近距离**再比 T（`build_mask`）；优化**绝不能改语义**，改完用旧图标的 SHA256 对比证明逐字节一致（§6.9） |
| 批量产物导出后「干净图」文件名对不上中文名 | 生成脚本里 icon key 用连字符（`key-xxxx`）、导出表用下划线（`key_xxxx`），查表 miss 就退化成原 key 名 | 查表前统一分隔符（`replace("-","_")` 或反向）；批量重命名后再核对数量与抽查几个名字（§6.9） |
| 钉选的高亮环看不见（还是原来的深色细描边）/ 点选标记时高亮脉冲环半径取错 | 新环 `circle.emk-pin-ring` 的 CSS 特异性低于既有的 `.emk-marker circle`（被盖掉）；它又被 `prepend` 成 marker 的 **firstChild**，`showDetail()` 原本直接取 `firstChild` | 选择器写全 `.emk-marker circle.emk-pin-ring` 并去掉 JS 里的 `stroke-width` 属性；取「选中环」前先跳过 `.emk-pin-ring`（§6.11） |
| 点「高级资源点（全部）」后子类的勾选框没跟着勾上 | 总开关的 change 只调了 `syncLegendState()` ——它只改 `data-on`（压暗），**不动 `input.checked`**；子类框还停在旧状态 | 总开关的 change 必须**整块 `renderLayerToggles()`** 重画图例（§6.12） |
| 一个同属两类的高资点被画了两遍（叠两层图标） | 旧渲染是「一个 kind 一个开关」，valuables 有 1 总开关 + 7 子开关后按 spec 逐个画就重复了 | `renderOverlay()` 里跳过所有 `kind === "valuables"` 的 spec，用 `valuableUnionSpec()` 按并集整体画一次（§6.12） |
| 构建期拼的底图整张位移 / 与标记对不齐 | 合成 SVG 的 `viewBox` 原点没放 **0,0**——`compute_world_to_svg` 只按 bounds/viewBox 的**宽高**算 scale，且假定原点在 0,0 | 合成 SVG 一律 `viewBox="0 0 W H"`（§6.13） |
| 实验室 / 迷宫切层切不动、图层识别不出来 | 上游这两张图的瓦片层**没有 `svgLayer`** 字段（矢量图才有） | 构建期 `apply_tile_layer_ids()` 给层补 id（`First_Floor` / `Second_Floor` / `Technical_Floor` / `Ground_Level`）（§6.13） |
| 拉瓦片时把「空白格」当成真瓦片下载/绘制，或误判成 404 报错 | 上游空格子返回的是 **200 + 102 字节的全透明 PNG**，不是 404 | 用**字节数 ≤ `TILE_EMPTY_MAX`（512）**判定并跳过（§6.13） |
| 瓦片对齐的单测断言写成「某角点 → (0,0)」失败 | 旋转为 90° 整数倍时，世界矩形的四个角点映到 viewBox 的**另外两个对角**（270° 时 `pixelX` 只依赖 `z`） | 断言取**四个世界角点映射后的 min/max** 恰好等于 `0 / W / 0 / H`（§6.13） |
| 新写的 `.ps1` 一跑就报 `Unexpected token` / `The string is missing the terminator`，中文全是乱码 | PowerShell 5.1 读**无 BOM 的 UTF-8 `.ps1`** 时按 ANSI（GBK）解码，中文变乱码 + 引号错乱 | 新脚本一律加**UTF-8 BOM**：`[System.IO.File]::WriteAllText($p,$text,(New-Object System.Text.UTF8Encoding($true)))`；对比 `build.ps1` 首 3 字节 `EF BB BF` 佐证（§6.14） |
| 安装器里 `payload_root()` 找不到资源 | 误以为 `--add-data "<目录>;<dest>"` 会再套一层目录名 | 它是把该目录的**内容**复制进 dest：`--add-data "$Target;payload"` → `<bundle>/payload/EFTMap.exe`，故 `payload_root()` = `<bundle>/payload`（§6.14） |
| 改了危险区轮廓，地图上多边形对了但点开的详情/居中位置还是老地方 | 上游所有危险区的 `position` **就是 `outline` 的面积质心**，只改轮廓不改中心点就对不上 | 改轮廓必须同步算质心改 `position`（或让 `position` 留空由轮廓推）；狙击类危险区**无高度含义，不要写 `y`**（§6.15） |
| 按用户给的 4 个顶点连线，画出来是**蝴蝶结（自交）** | 顶点顺序不保证是凸多边形环序，A→B→C→D 的相邻叉积会变号 | 按「相邻三点叉积全部同号」重排环序（如 A→B→D→C），再入数据（§6.15） |
| 浮窗淡出看不见效果（旧的直接消失）或淡入没过渡 | `hideMarkerPopup()` 立刻 `remove()` 节点；建好后同帧加 `.show` 类不会触发 transition | 淡出要**延后 `POP_FADE_MS` 再摘除**；淡入用 `requestAnimationFrame` 再加 `.show`（§6.15） |
| 想给地图图标加「整体缩放」时手感发糊 | 若用 CSS `transform` / `animation` 去缩 SVG 里的标记 → 整张 `<svg>` 被栅格化（§2 铁律） | 缩放只能**乘进 `updateCounterScale()` 的系数**（`iconScale()/state.z`），并同步乘进高亮环半径（§6.15） |
| 同一刷点同时刷「私酒 + 钥匙」时图标画成钥匙 / 「LEDX + 除颤器」画成除颤器（图不对位） | `valuableIconKey()` 旧逻辑**先全局查 `KEY_ICONS` 精确表**再走 rule-major 的正则首命中 → 价值低的物品抢到图标 | 改成**按价值分层**遍历规则（外层规则、内层扫物品名，命中即止，同层优先专属实拍图），规则数组顺序即价值顺序（§6.16） |
| 改「整体图标缩放」滑条时地名跟着一起变大变小（用户要的是地名跟地图走） | 地名节点也被 push 进了 `state.markerScaleNodes`，于是被乘上 `iconScale()/state.z` | 地名**不进** `markerScaleNodes`、不带 `__emkBase`，transform 只写 `translate(sx sy)` —— 随 map `viewBox` 等比缩放（§6.16） |
| 拖好视角后每次勾图层 / 改偏好，画面又被弹回玩家位置 | `applyConfig()` 里无条件 `applyAutoZoom()`；而页面每写回一次偏好都会广播一次 `config` | **与截图无关的事件绝不能触发自动定位**：`applyConfig()` 不调 `applyAutoZoom()`；`applyPosition()` 只在 `name`/`mtime` 变了（真有新截图）时才定位一次（§6.16） |
| 以为「上游 `positions` 非空」就等于「坐标是对的」（海岸线三狗标在村庄上） | 上游 `ZoneMeteoStation` 的 10 个坐标整段错位，却仍是合法数据 | 人工校正表要能**覆盖非空 `positions`**：`BOSS_ZONE_FORCE`（整段换掉，优先于只兜空的 `BOSS_ZONE_ANCHOR`）——「有坐标」≠「坐标对」（§6.17） |
| 放大徽章后钉选 / 选中高亮环罩不住图标 | 环半径写死 11 屏幕像素，而徽章已放大 1.5 倍 | 放大徽章要**连名字与高亮环半径一起改**（`BADGE_SCALE` + 环 11 → 12）（§6.17） |
| 破冰船收录后标记大半被甩到船体之外（内点率只有 84.2%） | 上游 `transform` **各向异性**（x 2.0 / z 3.5，其余图全各向同性），`bounds` 又与 **factory 一字不差**（明显复制）——瓦片船图与标记世界坐标不是一个口径 | 别信这套投影：用「瓦片内容像素跨度 ↔ 实体世界跨度」反推**各向同性**投影，走 `TILE_MAPS[...]["projection"]` + `apply_tile_projection()` 覆盖；`bounds` 由取景框**精确反推**（§6.18） |
| 反推投影后 `viewBox` 与瓦片索引差 7e-6，`test_shipped_svg_viewbox_matches_index` 挂 | `bounds` 手写成两位小数 → 像素矩形是 72.00199 而 SVG 文档按 4 位小数写出 "72.002" | `bounds` 必须由取景框常量**精确反推**（不做四舍五入），`right-left`/`bottom-top` 才能与索引逐位一致（§6.18） |
| 灯塔这张图 51.7% 的标记落进「禁行格」、76% 的栅格被判禁行 | 它的 `<g class="water">` 是个 7 顶点**背景海面**，文档顺序里画在 `land` **之前**；而栅格化按语义把水排到**最后**一趟 → 水面反盖陆地 | 水面要分两类：**画在第一个地面图元之前的水 = 背景海面**（默认码 0 已经表示禁行，直接跳过），之后的才是要从陆地挖掉的池塘 → `_first_ground()`（§6.19） |
| 沿道路寻路时折线画成「起点 → 终点 → 绕回终点」的星形，路程也虚高 | `routeGeometry()` 先把**所有**途经点铺成一排（`wps.slice()`）再逐段接 A\* 拐点 → 段内点跑到了段首末点**后面** | 折线必须**按段顺序**拼：先放首个途经点，再逐段接「中间拐点 → 本段末端点」（§6.19） |
| 位图异步载入后折线变沿道路了，`#route-summary` 却还写着「（直线）」 | `roadnetNet()` 载完只调了 `renderOverlay()`，而它只重画折线、**不管导航面板** | 载完要同时调 `renderOverlay()` + `renderRoutePanel()`；「折线」与「面板文案」必须同源（都吃 `routeGeometry()`）（§6.19） |

---

## 9. Git 状态（第九轮已发布 GitHub v0.1.0；第十轮分 2 批、第十一轮分 3 批、第十二轮分 2 批 + 文档提交、第十三轮分 3 批、第十四轮分 4 批 + 提交表补录）

**仓库已建立并发布**：<https://github.com/jjingith/eft-interactive-map>（Public）· Release `v0.1.0` 附三件套 ·
topics：`escape-from-tarkov / tarkov / interactive-map / offline / eft / python`。分支 `main`（原 `master` 已改名）。

基线提交 `a335b81`，第四～九轮改动按功能分 8 批提交，本轮新增/收尾：

| 提交 | 内容 |
| --- | --- |
| `1dcc559` | 用户级配置模块：配置与提示音改存 `%APPDATA%\EFTMap`，重打包不再丢设置 |
| `7ede857` | 游戏日志监控 + 自动截图 / 自动删图 / 按键输入（进图自动切图、本局任务统计） |
| `fee8da5` | 收录实验室与迷宫：构建期按上游 `transform`/`bounds` 拼瓦片成合成 SVG，schema → 6 |
| `1b9f16b` | XP(Luna) 浅色框架 + 图层图标 / 高资子类 / 搜索聚合与钉选 / 导航路线（217 图标素材） |
| `5aa2b3f` | 启动器加「应用窗口模式」+ 自建安装器 + `build_release.ps1`（Setup / 解压即用 / 加壳版） |
| `060204a` | 文档：README 与交接手册（发布三版本、踩坑、Git 状态） |
| `a07e565` | 测试：补齐截图按键输入的单元测试 |
| `0312a47` | 文档：README 按作者其他项目的统一风格重写（目录 / 免费声明 / 发布包表格 / 目录结构 / 自测 / 打赏） |
| `a0db682` | 文档：主页精简为概览（功能每条一句、收录地图只列名），细表与逐项详解移入 `docs/USAGE.md` |

第十轮（2026-10-19）新增：

| 提交 | 内容 |
| --- | --- |
| `5f8e65c` | 数据：街区狙击区危险区坐标修正（4 顶点凸环序 + 质心 + 去 `y`）+ `HAZARD_FIXES` 覆盖表 |
| `f67ee43` | 前端：图标整体缩放滑条 / BTR 图标 ×2 / 浮窗淡入淡出 + 物资小图标（含 `config.py` 的 `icon_scale` 与 14 条测试） |

第十一轮（2026-10-19）新增：

| 提交 | 内容 |
| --- | --- |
| `3a6d17b` | 数据+前端：高资子类修正（私酒不再串钥匙点、LEDX 优先于除颤器）+ 新增「显卡」子类（schema 7）+ 上锁的门合并为单一固定浮窗 + 地名与地图绑死 + 位置仅在新截图时定位 |
| `81e990a` | 启动器：声音提示每行加「试听」按钮（不选音频时现场合成内置提示音）+ 5 条单测 |
| `7806323` | 文档：README / `docs/USAGE.md` / 本手册同步第十一轮（含 `solidvents.com` 评估结论：不引入，见 §11） |

第十二轮（2026-10-19）新增：

| 提交 | 内容 |
| --- | --- |
| `537c541` | 数据：海岸线三狗（Knight）刷新点改锚定「气象站」地名（新增 `BOSS_ZONE_FORCE` 覆盖表，离线重跑，海岸线 boss 36 → 27 点） |
| `4e6eff3` | 前端：撤离点 / 转移点徽章整体放大 1.5 倍（`BADGE_SCALE` + 名字 + 高亮环半径 11 → 12） |
| `5b26d9a` | 文档：本手册 §6.17 / §7 / §8 / §9 / §11 同步第十二轮（含「高级子弹刷新点」评估结论：不采用） |

第十三轮（2026-10-19）新增（**破冰船收录 = 第十三轮**）：

| 提交 | 内容 |
| --- | --- |
| `2a59c2d` | 数据：收录破冰船（`TILE_MAPS["icebreaker"]` + 人工反推投影 `_ICEBREAKER_*` / `apply_tile_projection`，13 张图 / 底图 10.0 MB） |
| `0e003ea` | 启动器：安装器快捷方式改「先建 ASCII 临时名再 `os.replace` 成中文名」修中文 .lnk 被破坏 |
| `1dff576` | 文档：README 收录范围同步（13 张图 / 3 张瓦片图 / 破冰船 16 层）+ 本手册 §6.18 / §9 / §11 |

第十四轮（2026-10-19）新增（**导航沿道路走 = 第十四轮**）：

| 提交 | 内容 |
| --- | --- |
| `b59e721` | 构建期：`tools/roadnet.py` 底图栅格化成静态路网（`_first_ground` 背景海面特判）+ `fetch_data.py` 接入 `[5/5]` 步 |
| `5bed4d0` | 数据：10 张矢量图的静态路网（35 个位图 779 KB + 索引 11 KB） |
| `52e26d3` | 前端：导航沿道路走（同层加权 A\* + 视线简化；修折线点序与面板文案不刷新两个 bug）+ `index.html` 文案 |
| `409e63f` | 文档 / 打包：README + 本手册同步第十四轮，`build.ps1` 打包校验加路网产物 |
| `161d7e0` | 文档：补第十四轮提交表 hash |

> **提交作者**：仓库里**没有** `user.name` / `user.email` 配置（既非 local 也非 global），历史提交靠环境变量写的
> `jjingith <imzjj1996@gmail.com>`。裸环境提交时要先 `$env:GIT_AUTHOR_NAME='jjingith'; $env:GIT_AUTHOR_EMAIL='imzjj1996@gmail.com';
> $env:GIT_COMMITTER_NAME='jjingith'; $env:GIT_COMMITTER_EMAIL='imzjj1996@gmail.com'`（或临时设置身份），否则 `git commit` 直接报 `Author identity unknown`。
> 另：PowerShell **不支持** `$(cat <<'EOF' …)` heredoc 写多行提交信息，要改用多个 `-m`。

**入库范围**：`data/`、`assets/maps/`（含 `assets/maps/tiles/` 120 张瓦片 PNG 约 6.2 MB）、`assets/roadnet/`（35 个路网位图）、`assets/icons/*.png`（217 个）、
`tools/`、`tests/`、`build/`、根目录 `index.html` / `style.css` / `app.js`、`AGENT_HANDOFF.md`、`docs/`。
**不入库**（`.gitignore` 已排除）：`dist/`、`release/`、`build-cache/`、`build/_work*/`、`eftmap.config.json`、`sounds/`、`*.spec`。

> 图标源图目录 `D:\personal\trae\02-塔科夫\ui图标` 在**仓库之外**，不属于本仓库；已整理成 `clean/`（217 个抠好的成品）+ `src/`（63 张 iconize 源截图）。

> **发布后注意**：`release/` 是产物目录、不入库，所以**重打包后要重新上传 Release 资产**：
> `gh release upload v0.1.0 --clobber release\*`（`gh` 在 `C:\Users\Administrator\gh-cli\bin\gh.exe`；
> 命令前要先 `$env:GH_TOKEN=$null`，否则环境变量里那个无写权限的 GitHub App 令牌会抢占授权）。

---

## 10. 常用命令

```bash
# 测试（约 30s，全离线）
python -m pytest tests -q

# 前端语法检查（没有构建步骤，只有这一道关）
node --check app.js

# 重跑数据（有 build-cache 时离线；改过 fetch_data.py 必须重跑并核对 data/maps.json）
# 实验室 / 迷宫会顺带重拼瓦片底图：瓦片缓存在 build-cache/tiles/，成品 PNG 落 assets/maps/tiles/
# 第 5 步会顺带重建路网（纯离线，只读 assets/maps/*.svg）
python tools/fetch_data.py

# 只重建路网（改过 tools/roadnet.py 或底图 SVG 后跑这个；全程离线）
python tools/roadnet.py                    # 读 data/maps.json，重建全部路网
python tools/roadnet.py --maps customs,woods
python tools/roadnet.py --check            # 只校验已有产物（存在 + 大小对得上 + 有连通块），不重建

# 本地调试前端
python tools/serve.py --no-browser --port 8787     # 然后浏览器开 http://127.0.0.1:8787/

# 打包（约 1 分钟）→ dist\EFTMap\EFTMap.exe
powershell -ExecutionPolicy Bypass -File build\build.ps1

# 发布三件套（约 2 分钟）→ release\ 下 Portable zip / AppWindow zip / Setup exe
powershell -ExecutionPolicy Bypass -File build\build_release.ps1
powershell -ExecutionPolicy Bypass -File build\build_release.ps1 -SkipBase   # 已有 dist 时跳过重跑 build.ps1
```

调试时想看「用户真实的配置」在哪：`%APPDATA%\EFTMap\eftmap.config.json`（`echo $env:APPDATA` 拼一下即可）。
要拿一份干净配置做对照，可以直接把它删掉再启动——文件不存在时 `config.load()` 会回落到默认值。

**改完必做**：① `node --check app.js` ② `python -m pytest tests -q` ③ 浏览器实测 ④ 重新打包 ⑤ 核对产物里 `index.html` / `style.css` / `app.js` 含本轮新代码 ⑥ 同步改 `README.md`。

---

## 11. 待办与已知限制

**未实现（有意或待做）**

- **导航沿道路走（类高德）**：**已于第十四轮实现**——构建期 `tools/roadnet.py` 把 10 张矢量底图栅格化成静态路网
  （`assets/roadnet/<图>/<层>.bin` + `data/roadnet.json`，纯离线），前端对**同层**相邻途经点做加权 A\*（道路优先）+ 视线简化，见 §6.19。
  留在直线的情形是有意的：**跨楼层**、以及**只有瓦片底图的实验室 / 迷宫 / 破冰船**（它们没有 `<path>`，栅格化不出路网）。
- **快门声音替换**：未实现；在它实现前**版本号不许升到 1.0**。
- **账号级任务统计**（已完成 / 未完成 / 进行中 / 未解锁）：核查过本地日志与磁盘，该信息不在本地存储、需要联网拉取，与本项目「运行期不联网」冲突，**刻意不做**。别去加。
- **瓦片图**：**实验室 / 迷宫已于第八轮收录**（构建期把上游瓦片按 `transform` / `bounds` 拼成合成 SVG，见 §6.13）；
  **破冰船（icebreaker）已于第十三轮收录**（复用同一机制，另加 `projection` 人工投影覆盖上游那套对不上的 `transform` / `bounds`，见 §6.18）。
  至此上游**已无「只有瓦片却未收录」的图**（其余 10 张都是上游矢量 SVG）——若上游将来新增瓦片图，复用 §6.13 的 `TILE_MAPS` + `build_tile_svg` 机制，
  必要时照 §6.18 加 `projection` 覆盖表即可。
  （第六轮的旧结论「不收录」已被第八轮推翻：当时判定社区 `Labs.svg` 宽高比与上游差约 10%、迷宫连 SVG 都没有 → 改走**构建期拼瓦片**这条路，见 §6.11 / §6.13。）
- **GitHub 发布**：**已于第九轮完成**——仓库 <https://github.com/jjingith/eft-interactive-map>（Public），Release `v0.1.0` 附三件套。
  `gh` CLI 在 `C:\Users\Administrator\gh-cli\bin\gh.exe`（设备码授权登录，token 含 `gist, read:org, repo`）；用 `gh` 前记得先 `$env:GH_TOKEN=$null`。
- **三件套实机验证**（第九轮遗留）：加壳版 zip 解压后能否真的开独立应用窗口、Setup 能否装到 `%LOCALAPPDATA%\EFTMap` 并建好开始菜单 / 桌面快捷方式与卸载项，**尚未在用户机器上实测**。

**评估过但不采用（第十二轮）**

- **「高级子弹刷新点」图层**：用户希望像高级资源点那样单列一层。**上游没有这个信息**——把 12 张图（含未收录图的原始数据）的
  `lootLoose` 散落刷点全部本地化后逐条查（**5441 个刷点**，涉及 350 个物品 id，全部解析成功），**没有任何一个点刷子弹**；
  弹药类只以**容器**形式出现（「弹药箱」16 处 /「弹匣箱」17 处），已有物资容器图层覆盖。既然拿不到「哪个点刷哪种子弹」，
  做出来只能是假的，用户据此决定**不做**（其它互动地图也没有这个分类，与结论一致）。

**评估过但不采用（第十一轮）**

- **`https://solidvents.com/zh-CN/`（免费矢量图生成）**：它是**参数化图纹生成器**（喇叭网孔 / 散热孔 / 渐变网点 / 半色调，导出 SVG·DXF·STEP），
  **不是通用矢量插画 / 图标生成器**。本项目图标来自用户实拍素材（`tools/iconize.py` 抠图）、底图来自上游瓦片与社区 SVG，
  与该站能力不匹配；其导出物的授权条款也未声明，与「只分发 MIT / CC BY-NC-SA」的铁律有冲突风险 → **不引入**。
  若将来要做危险区的半色调纹理，可把它当**一次性离线生成静态素材**的工具用（产出物入库并标许可），绝不放进运行期流程。

**设计上的既有局限（README 里已如实写明，不要当成 bug 去"修"）**

- 任务进度只能统计本局、无视条件级进度、不跨会话累计
- 光凭坐标无法反推在哪张图（上游坐标范围大量重叠），「哪张图」由日志决定
- 灯塔 / 森林 / 迷宫是单层图，不显示楼层列表；码头没有撤离点与地名
- 多层图默认只显示主楼层；少数越界的点会被视图外扩最多 12% 容纳，越界过多的会被裁掉
- **配置是「按机器（用户目录）」共享的一份**：同时开多个浏览器窗口时，界面偏好（`ui.layers` 等）**后写覆盖先写**；页面本地还有 `localStorage` 兜底，所以离线勾选不会丢，但联网窗口之间不保证实时一致。前端只在**值真的变化**时才上报，日常用不出问题。
- **钥匙图标已补齐**：第五轮后上锁的门 187 个钥匙名**全部有专属图**（§6.9 遗留的 43 个退回项已清零）。高级资源点物品名中仍有 11 个走 `VALUABLE_ICON_RULES` 通用正则（BTC / 私酒 / **显卡（显示卡）** / LEDX / 除颤器 / 六色实验室钥匙卡——这些本来就有规则且已贴素材图 / 手画图，不是缺失；其中**显卡是唯一没有实拍素材、手画 SVG 的子类**，见 §6.16）。若以后 wiki 长图例又有新增钥匙，按 §6.9 / §6.10 的流程加：**严格整名匹配**算缺口 → 量 `band` → `tools/iconize.py` 抠图 → 登记 `ICON_PNG` + `KEY_ICONS`。

**当前工作树干净度**：`build-cache/` 里有若干本轮诊断用的 `inspect_*.py` 临时脚本，属于中间产物，可随时删（不入库）。`tools/_debug_sheet*.png`（`iconize.py --sheet` 的自检拼图）本轮已删。

---

## 12. 关键文档索引

- 面向用户的完整文档：[README.md](file:///z:/personal/trae/02-塔科夫/eft-interactive-map/README.md)（功能说明、计数表、数据来源与许可、日志格式、配置项）
- 设计规格（含 M7 / M8 / M9 / M10 各轮决策记录与教训）：[2026-10-17-eft-interactive-map-design.md](file:///z:/personal/trae/02-塔科夫/eft-interactive-map/docs/superpowers/specs/2026-10-17-eft-interactive-map-design.md)
- 实施计划：[2026-10-17-eft-interactive-map-plan.md](file:///z:/personal/trae/02-塔科夫/eft-interactive-map/docs/superpowers/plans/2026-10-17-eft-interactive-map-plan.md)
