# EFT 互动地图（离线免费版）

《逃离塔科夫》互动地图，**免费、离线、无外挂性质**。

双击 `EFTMap.exe` → 弹出带进度的启动框 → 跑完自动打开浏览器进入地图界面。
底图与标注数据全部内置，运行期**不联网**；与游戏进程**零交互**。

---

## 它是什么 / 不是什么

| 是 | 不是 |
| --- | --- |
| 本地离线的互动地图：撤离点、过境点、出生点、地名标注，可缩放平移、可搜索 | 不是游戏外挂：**不读内存、不注入进程、不做透视/自瞄** |
| 数据里没有的图不硬塞（只收录上游有 SVG 底图的 10 张常用图） | 不做联机同步、不显示他人位置 |
| 底图与数据来自社区公开的 MIT / CC BY-NC-SA 许可资源，逐条署名 | 不含任何游戏资源文件，不爬虫、不上传任何用户数据 |

### 与游戏的关系

实时定位沿用社区公开做法：**监听截图目录、解析截图文件名里的坐标**，全程不碰游戏进程。
（该能力属 M2，**当前版本尚未实现**，见下文「实时定位」。）

---

## 快速开始

### 方式 A：双击发布包（推荐）

1. 拿到 `EFTMap` 发布包（Releases 里若尚未提供，见下文「打包 exe」自行构建一次），解压到任意目录；
2. 双击 `EFTMap.exe`；
3. 启动框跑完「检查数据 → 启动本地服务 → 载入资源 → 打开浏览器」四步后，
   浏览器会自动打开 `http://127.0.0.1:8787/`。

无需安装 Python，无需联网。全程只监听本机 `127.0.0.1`。

### 方式 B：从源码运行

需要 Python 3.9+（开发环境实测 3.14），**不使用任何第三方库**。

```bash
# 1) 首次使用：联网拉取一次数据与底图（构建期唯一一次联网）
python tools/fetch_data.py

# 2) 启动（启动框 + 自动打开浏览器）
python tools/launcher.py
```

可选参数：

```bash
python tools/launcher.py --port 8788      # 换端口
python tools/launcher.py --no-browser     # 只起服务，不自动开浏览器
python tools/launcher.py --screenshots "D:\...\Screenshots"   # M2 实时定位的截图目录
```

### 方式 C：只跑静态站点

不想用启动框、只想调试前端时：

```bash
python tools/serve.py                      # 默认 127.0.0.1:8787，自动开浏览器
python tools/serve.py --no-browser --port 8790
```

> 不要用 `file://` 直接打开 `index.html`：浏览器会拦截本地数据读取，页面会提示改用本地服务。

---

## 界面用法

- **地图**：左侧点选切换；上次看的地图会被记住（`localStorage`）。
- **平移/缩放**：按住左键拖动平移；滚轮以光标为锚点缩放（0.5×–20×）；右上角「复位」回到整图适配。
- **图层**：撤离点 / 过境点 / 出生点 / 地名标注四个开关，状态会被记住。
- **搜索**：输入名称子串，点结果项自动居中并高亮脉冲环，同时弹出「标记详情」（名称、类型、阵营、世界坐标）。
- **状态条**：显示当前地图、光标处的游戏世界坐标、实时定位状态。

---

## 收录地图

默认内置 10 张有 SVG 底图的常用图（底图约 1.4 MB）：

| 地图 | 撤离点 | 过境点 | 出生点 | 地名标注 |
| --- | ---: | ---: | ---: | ---: |
| 塔科夫街区 | 19 | 3 | 420 | 46 |
| 中心区 | 9 | 1 | 193 | 13 |
| 海关 | 28 | 4 | 278 | 24 |
| 工厂 | 10 | 3 | 119 | 27 |
| 立交桥 | 9 | 2 | 232 | 77 |
| 灯塔 | 12 | 4 | 213 | 22 |
| 储备站 | 11 | 3 | 167 | 27 |
| 海岸线 | 19 | 4 | 282 | 20 |
| 码头 | 0 | 0 | 109 | 0 |
| 森林 | 20 | 4 | 332 | 16 |

`--maps a,b,c` 可只拉指定图；`--mode pve` 可换数据模式（默认 `regular`）。

### 已知限制

- **码头**在上游数据里本来就没有撤离点/过境点/地名，只有出生点（默认关闭），所以默认只显示底图。
- 一张图会**只显示它的主楼层**（如工厂为 `Ground_Floor`），避免多楼层叠影。
- 上游有**少量标注落在底图矩形之外**（例如中心区属于 21+ 扩展区的撤离点、工厂东侧部分出生点）。
  这些点**照实保留、不静默丢弃**，视图会按标注包围盒外扩最多 12% 来容纳它们，越界过多的点会被裁掉。
- 瓦片图（实验室、迷宫、破冰船等）暂不收录，留待后续。

---

## 实时定位（规划中，当前未实现）

M2 计划：`serve.py` 轮询 EFT 截图目录（默认 `文档\Escape from Tarkov\Screenshots`，
可用 `--screenshots` 覆盖），解析截图文件名中的坐标与朝向，经 **SSE** 推给页面，
页面上显示玩家点与朝向箭头，支持自动居中/手动锁定。

- 截图目录不存在或无权限时，**实时定位被停用**，地图其余功能照常。
- 文件名解析不出来时**忽略该文件、不误报**，界面显示「定位不可用」。
- 定位点与地图标注共用同一套坐标换算，因此天然对齐。

具体文件名格式以真实样本确定（见 `tests/test_screenshot_parse.py`）。

---

## 打包 exe

```powershell
powershell -ExecutionPolicy Bypass -File build\build.ps1
```

产出 `dist\EFTMap\EFTMap.exe`（PyInstaller onedir，站点文件随包分发，双击即用）。
脚本会在打包后自检 exe 与站点文件是否齐全，缺一即报错退出。
PyInstaller 仅在**构建期**需要，运行期不需要。

---

## 开发与测试

```bash
python -m pytest -q          # 全量单测
```

- **只有 `tools/fetch_data.py` 联网**，测试用本地样本与桩件，不触网。
- 坐标推导由不变量锁定：底图矩形的两个角点必须精确映射到 `(0,0)`/`(W,H)`，
  且每张图 ≥ 90% 的标注点落在 `viewBox` 内（推导写错会立刻失败）。
- 数据管线幂等：数据就绪时再跑一次不联网；拉取失败**不破坏已有数据**。

```
eft-interactive-map/
├── index.html / style.css / app.js   # 前端（原生 JS/CSS，零依赖，无构建）
├── data/                             # maps.json + meta.json（构建期产出）
├── assets/maps/                      # 10 张底图 SVG
├── tools/
│   ├── fetch_data.py                 # 构建期：拉数据与底图（联网一次）
│   ├── coord.py                      # 世界坐标 → SVG 坐标的仿射系数
│   ├── serve.py                      # 运行期：静态服务 + 健康检查（+ M2 的 SSE）
│   └── launcher.py                   # 运行期入口：启动框 + 四步编排
├── build/build.ps1                   # PyInstaller 打包脚本
├── tests/                            # pytest 单测
└── docs/superpowers/                 # 设计规格与实施计划
```

---

## 数据来源与许可

| 来源 | 内容 | 许可 | 义务 |
| --- | --- | --- | --- |
| [the-hideout/tarkov-dev](https://github.com/the-hideout/tarkov-dev) | 地图配置、翻译 | **MIT** | 保留版权与许可声明 |
| [json.tarkov.dev](https://json.tarkov.dev/) | 标注数据（撤离/过境/出生点） | tarkov.dev 社区公开数据 | 署名 tarkov.dev |
| [the-hideout/tarkov-dev-svg-maps](https://github.com/the-hideout/tarkov-dev-svg-maps) | 底图 SVG | **CC BY-NC-SA 4.0** | 署名 + **非商业** + 同许可再分发 |

- 每个来源的 URL、sha256 与许可都记在 `data/meta.json` 里。
- `assets/maps/` 下的底图沿用 **CC BY-NC-SA 4.0**，因此**本项目的底图部分不得商用**，
  再分发时必须保持同一许可并署名。界面侧栏底部与 `data/meta.json` 均已注明来源。

---

## 免责

- 《逃离塔科夫》（Escape from Tarkov）的商标与全部原始美术归 **Battlestate Games** 所有。
  本项目不含任何游戏资源文件，仅供个人免费使用。
- 本项目**永久免费、严禁售卖**：不设付费版、不卖激活码、不提供「付费优先支持」。
  若你是付费获得的，说明你被骗了。
- 本项目不提供任何作弊、修改游戏或影响对局公平性的功能，也不与游戏进程发生任何交互。

---

## 文档

- 设计规格：[docs/superpowers/specs/2026-10-17-eft-interactive-map-design.md](docs/superpowers/specs/2026-10-17-eft-interactive-map-design.md)
- 实施计划：[docs/superpowers/plans/2026-10-17-eft-interactive-map-plan.md](docs/superpowers/plans/2026-10-17-eft-interactive-map-plan.md)
