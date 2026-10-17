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

1. **不读取游戏内存、不注入进程、不做透视/自瞄等任何外挂类功能**；本项目与游戏进程零交互。
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

### 后续（不在本次实现，登记为待办）

任务标记与任务追踪、BOSS/邪教徒刷新点、战利品/BTR、多楼层、自定义标记(pin)、任务物品图标、只读 EFT 日志自动切图。

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
│   ├── launcher.py         # 运行期入口：启动框(进度) + 启动服务 + 打开浏览器
│   └── serve.py            # 运行期：静态服务 + SSE + 截图目录监听（供 launcher 调用）
├── build/
│   └── build.ps1           # 构建脚本：PyInstaller 打包 exe（含图标/数据）
├── tests/
│   ├── test_fetch_data.py
│   ├── test_coord_transform.py
│   ├── test_screenshot_parse.py
│   ├── test_launcher.py
│   └── test_serve.py
├── docs/superpowers/specs/   # 本规格文档
└── README.md
```

---

## 5. 组件设计

### 5.1 静态站点（前端，零依赖原生 JS）

- **渲染**：SVG 作为底图载体。`app.js` 维护 `viewBox`/`transform` 实现平移缩放；标记以绝对定位或 SVG 子元素叠加，随缩放同步。
- **图层**：`data/maps.json` 里每个图层的开关状态驱动显隐；图层开关状态可用 `localStorage` 记忆。
- **搜索**：对当前地图全部标记做子串匹配，命中项高亮并可选居中。
- **玩家层**：独立的玩家 marker + 朝向箭头，数据来自 SSE；有定位时显示，无则隐藏。
- **无构建**：不使用任何打包器；`app.js` 以原生 ES module 组织，直接由静态服务或 `file://` 加载（M2 推荐从本地服务打开）。

### 5.2 `tools/fetch_data.py`（构建期，联网一次）

**实测确认的数据源（2026-10-17）**：

| 数据 | 地址 | 许可 |
| --- | --- | --- |
| 标注点（撤离/过境/出生点/BOSS…） | `https://json.tarkov.dev/{mode}/maps`（`mode` ∈ `regular`/`pve`/`season`，约 8.7 MB） | tarkov.dev 公开数据 |
| 中文名（图名 / `ex_*` 撤离点名 / `tr_*` 过境说明） | `https://json.tarkov.dev/{mode}/maps_zh`（约 22 KB） | 同上 |
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
- `GET /events`：**SSE** 长连接，位置更新时推送 `data: {...}\n\n`。
- 后台线程轮询 EFT 截图目录（默认 `…\Documents\Escape from Tarkov\Screenshots`，可由参数覆盖），解析最新截图文件名的坐标/朝向，写入内存中"最新位置"并广播给 SSE 订阅者。
- 打开浏览器默认由 `launcher.py` 负责；`serve.py` 独立运行时可自行打开，亦可用 `--no-browser` 关闭。
- 默认端口 `8787`，被占用时可用 `--port` 指定。

### 5.4 `tools/launcher.py`（运行期入口 → `eft-map.exe`）

启动流程（每步在启动框内显示进度与状态文字）：

1. **检查数据**：确认 `data/maps.json` 与底图资源存在；缺失则提示（不静默联网）。
2. **启动本地服务**：调用 `serve.py` 起 `127.0.0.1:8787`（含 SSE 与截图监听）。
3. **载入资源**：等待服务就绪/自检通过。
4. **打开浏览器**：调用系统默认浏览器打开 `http://127.0.0.1:8787/`。
5. **运行中**：窗口切换为"运行中"状态，提供「打开界面」「最小化」与「退出」（退出时关闭服务）。

- 启动框用 **tkinter**（标准库），视觉走 **Windows XP（Luna）简约风**：蓝色渐变标题栏、3D 凹凸控件、Tahoma 字体、朴素描边；显示步骤清单 + 进度条。地图 **Web UI 仍为深色战术风**。
- 任一步失败：显示明确错误与"重试/退出"，不静默失败、不留下半启动状态。
- 命令行参数：`--port`、`--screenshots <目录>`、`--no-browser`（供调试/自动化）。
- 与 `serve.py` 的关系：`launcher.py` 是入口与界面壳，`serve.py` 是可被调用的服务模块（同时保留独立 CLI 以便测试）。

---

## 6. 数据模型（`data/maps.json`）

```jsonc
{
  "schema": 1,
  "gameMode": "regular",
  "generatedAt": "2026-10-17T…Z",
  "sources": [ { "name": "…", "url": "…", "license": "MIT / CC BY-NC-SA 4.0" } ],
  "maps": [
    {
      "key": "customs",
      "id": "56f40101d2720b2a4d8b45d6",   // 上游 BSG 场景 id
      "name": "海关",
      "svg": "assets/maps/Customs.svg",
      "svgViewBox": [0, 0, 1062.4827, 535.17401],
      "svgLayer": "Ground_Level",        // 底图显示的 <g> 图层 id
      "worldToSvg": {                    // svgX = a*x + b*z + c ; svgY = d*x + e*z + f
        "a": -0.99299, "b": 0, "c": 693.10,
        "d": 0, "e": 0.98374, "f": 301.99
      },
      "labels": [ { "text": "Big Red", "x": -215, "z": -119 } ],
      "layers": {
        "extracts": [ { "id": "…", "name": "十字路口", "faction": "pmc", "x": 200.98, "z": -153.09 } ],
        "transits": [ { "id": "9", "name": "前往储备站", "x": 650.64, "z": 124.94 } ],
        "spawns":   [ { "x": 569.05, "z": -54.53, "sides": ["scav"], "categories": ["player","bot"] } ]
      }
    }
  ]
}
```

- 标注点存**游戏世界坐标** `(x, z)`；`worldToSvg` 是构建期算好的仿射系数，前端只做一次乘法即可落到 SVG `viewBox` 坐标系。
- 系数由 `transform` + `coordinateRotation` + `bounds` + SVG 的 `viewBox` 推导（见 §7），并由单元测试锁定（含"所有标注点必须落在 viewBox 内"的自动校验）。

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

- `coordinateRotation` 逐图不同（海关 180°、工厂 90°、实验室 270°、部分图无旋转），上述公式统一处理，不写特例。
- 截图文件名给的是同一套世界坐标 `(x, z)`（y 为高度，本项目不用），与标注点共用 `worldToSvg`，因此**定位点天然与标注对齐**。
- **单元测试**覆盖：
  1. 两个 `bounds` 角点经 `worldToSvg` 必须落在 `(0,0)` / `(W,H)`（容差 1e-6）；
  2. 每张图**全部**撤离/过境/出生点/label 必须落在 `[-1%, 101%] × viewBox`（超出即说明朝向推导错了，测试直接失败）；
  3. 同一 `(x, z)` 在构建期与运行期（JS/阶段函数）算出的结果一致（黄金样本对照）。

---

## 8. 实时定位机制

1. `serve.py` 轮询截图目录，取最新文件；若与上次不同则解析。
2. 解析截图文件名中的坐标段与朝向段（**具体格式以真实样本确定**；编写单元测试覆盖正/异常样本，解析失败**不报错、不误报**，仅记录 limitation）。
3. 内存中更新"最新位置"，通过 SSE（`/events`）推给所有已打开页面；页面用 `EventSource` 接收并更新玩家 marker 与箭头。
4. 页面另以 `/api/position` 作首屏同步（SSE 未连通时的兜底）。

---

## 9. 错误处理与降级

| 场景 | 行为 |
| --- | --- |
| 无网络（首次未拉数据） | `fetch_data.py` 明确报错并保留旧数据；站点可正常打开已有图 |
| 截图目录不存在/无权限 | `serve.py` 记录警告，停用实时定位，页面其余功能正常 |
| 截图文件名无法解析 | 忽略该文件，SSE 不推送脏数据；可打印调试日志 |
| 端口被占用 | `serve.py` 报错并提示用 `--port` 更换 |
| 前端定位失效 | 页面显示"定位不可用"状态，不阻塞地图浏览 |

---

## 10. 测试策略

- **Python 单元测试（pytest）**：`fetch_data` 的规范化与幂等、坐标变换往返、截图文件名解析（正/异常）、`serve` 的位置广播与 SSE 帧格式、`launcher` 的启动步骤编排（用桩件替换起服务与开浏览器，避免测试中真的弹窗/开浏览器）。
- **前端**：MVP 阶段以手工核对为主；关键交互（平移/缩放/图层）可通过在浏览器中手测验证；不引入前端测试框架（保持零依赖）。
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
- 任务/BOSS/战利品/多楼层/自定义标记/日志自动切图：**M1、M2 之外，后续迭代**。

---

## 13. 交付物

1. 可运行的离线互动地图站点（`index.html` + `app.js` + `style.css` + `assets/` + `data/`）。
2. 构建期数据拉取脚本 `tools/fetch_data.py`。
3. 运行期助手（静态服务 + SSE + 截图定位）`tools/serve.py` 与启动器 `tools/launcher.py`。
4. **可双击的 `eft-map.exe`**（启动框 + 进度 + 自动打开浏览器）及构建脚本 `build/build.ps1`。
5. Python 单元测试 `tests/`。
6. `README.md`（安装、拉数据、启动、定位配置、来源署名与免责）。

---

## 14. 风险与缓解

| 风险 | 缓解 |
| --- | --- |
| **上游 API 长时间不可用**（`api.tarkov.dev/graphql` 实测已挂） | 改用 `json.tarkov.dev` 静态镜像（实测可用）；原始大文件落 `build-cache/`，打包只需精简后的 `data/maps.json` |
| 资源站 Cloudflare 拦截（403 / error 1010） | 按 §5.2 的头部规则请求；Python 失败自动回退 `curl.exe` |
| tarkov.dev 坐标系与截图坐标系不一致 | 统一用同一套 `worldToSvg`；"全部标注点必须落在 viewBox 内"的测试会在推导错误时立即失败 |
| EFT 截图文件名格式随版本变化 | 解析器宽容降级、不误报；以真实样本补测试 |
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

### 15.2 待确认（实现中可能调整）

- exe 图标：先用简约占位图标，后续可替换为你指定的图标。
- M1 收录的具体地图清单：实现时按 tarkov.dev 数据可得的常用图确定，并在 `README.md` 列出。
