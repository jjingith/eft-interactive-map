# 实施计划：离线免费版《逃离塔科夫》互动地图（M1 → M2）

- 日期：2026-10-17
- 规格（唯一权威设计）：`docs/superpowers/specs/2026-10-17-eft-interactive-map-design.md`
- 说明：技能列表中没有 `writing-plans` 技能，故本计划为自建版本；规格中的设计已获用户批准。

---

## 0. 已核实的关键事实（实现时按此写，不要再重新调研）

### 数据源与访问方式（2026-10-17 实测）

| 用途 | 地址 | 头部要求 |
| --- | --- | --- |
| 标注点（raw，8.7 MB） | `https://json.tarkov.dev/regular/maps` | **不要**带 `User-Agent`（默认头最稳） |
| 中文翻译（22 KB） | `https://json.tarkov.dev/regular/maps_zh` | 同上 |
| 每图配置 | `https://raw.githubusercontent.com/the-hideout/tarkov-dev/main/src/data/maps.json` | 浏览器 UA |
| 底图 SVG | `https://assets.tarkov.dev/maps/svg/<Name>.svg` | **必须**浏览器 UA，否则 403 |
| 中文名翻译（备用） | `https://raw.githubusercontent.com/the-hideout/tarkov-dev/main/src/translations/zh/maps.json` | 只含图名，不含 `ex_*`/`tr_*` |

- **禁止 `HEAD`**；大文件超时 ≥ 60s。
- `api.tarkov.dev/graphql` 已不可用（返回 `GraphQL server unavailable`）——不要依赖它。
- 纯标准库偶发被 Cloudflare 拦（1010）：`fetch_data.py` 内置 `curl.exe` 兜底。
- 原始大文件缓存到 `build-cache/`（已 gitignore）。

### 数据结构要点（来自实测）

- `maps` 是 **dict**，键为 BSG 场景 id（如 `56f40101d2720b2a4d8b45d6`）；每项键含
  `id / name / normalizedName / extracts / transits / spawns / bosses / locks / …`。
- `name` 是占位符（`"<id> Name"`），**真实名称必须用 `maps_zh`**（键形如 `<id> Name`）替换。
- `extracts[].name` 是 i18n 键（`ex_customs_scav_gasstation`）→ 用 `maps_zh` 查中文（实测有值，如「老加油站」）。
  `faction` ∈ `pmc`/`scav`/`shared`，`position` 为 `{x, y, z}`。
- `transits[].description` 是 `tr_*_DESC` 键 → 中文如「前往储备站」；`position` 为 `{x,y,z}`。
- `spawns[]` 含 `position`、`sides`（`pmc`/`scav`）、`categories`（`player`/`bot`）、`zoneName`。
- 每图配置：`transform:[t0,t1,t2,t3]`、`coordinateRotation`（度，部分图缺省=0）、
  `bounds:[[xMax,zMin],[xMin,zMax]]`、`svgPath`（如 `/maps/svg/Customs.svg`）、
  `svgLayer`（底图 `<g>` id，如 `Ground_Level`）、`labels`（`{text?, position:{x,z}}`）。
  **`svgPath` 为空 = 该图只有瓦片，M1 不收录。**

### 坐标公式

见规格 §7（`transform` + `coordinateRotation` + `bounds` + SVG `viewBox` → 6 个仿射系数）。
构建期算成 `worldToSvg = {a,b,c,d,e,f}`：
`svgX = a*x + b*z + c`；`svgY = d*x + e*z + f`。

---

## 1. 里程碑与顺序

依赖顺序：`fetch_data` → 数据/底图 → 前端静态站 →（可先用手工核对）→ `serve` → `launcher`(XP 进度框) → 打包 → M2 实时定位。

- **M1**：离线静态互动地图 + 双击 exe 启动器（XP 风启动框 → 自动开浏览器）。
- **M2**：截图目录监听 + SSE 实时位置/朝向。

---

## 2. M1 任务清单

| # | 任务 | 产物 | 验收 |
| --- | --- | --- | --- |
| T1 | 仓库骨架 | `.gitignore`（含 `build-cache/`、`dist/`、`*.spec`、`__pycache__`）、`README.md` 占位、`tools/`、`assets/maps/`、`data/`、`tests/` | 目录齐备，`.gitignore` 已生效 |
| T2 | `tools/fetch_data.py` | 拉取 3 个 JSON + N 个 SVG → 规范化 | `python tools/fetch_data.py` 成功产出 `data/maps.json`（≤ 1 MB）与 10 张 SVG；重复运行幂等 |
| T3 | 坐标变换模块 `tools/coord.py` | `compute_world_to_svg(transform, rotation, svg_bounds, viewbox)` 纯函数（已随 T2 落地，T3 补测试） | 单测：矩形两角点 → `(0,0)`/`(W,H)`；旋转 0/90/180/270；每图 ≥90% 标注点在 viewBox 内；海关黄金值对照 |
| T4 | `index.html` + `style.css` | 深色战术风外壳：侧栏（图列表/图层开关/搜索）、地图画布、右下角状态条（定位状态、来源署名） | 浏览器打开可见骨架，无控制台报错 |
| T5 | `app.js` | 加载 `data/maps.json`、内嵌 SVG（`fetch` + 注入 DOM）、平移/缩放/复位、图层显隐（`localStorage` 记忆）、点击标记看详情、搜索高亮居中、仅显示 `svgLayer` 组、labels 可开关 | 手工核对 10 张图：底图不串层、标记落点合理、缩放平移跟手 |
| T6 | `tools/serve.py`（M1 部分） | `http.server` 托管项目根目录；`--port`/`--no-browser`；端口占用报错清晰 | `curl 127.0.0.1:8787/data/maps.json` 200；浏览器能打开站点 |
| T7 | `tools/launcher.py`（M1 部分） | 4 步启动流程（检查数据 → 起服务 → 自检（`/api/health`）→ 开浏览器）+ tkinter XP(Luna) 风进度框；失败可重试/退出；运行态可「打开界面/最小化/退出」 | 桩件单测：编排顺序、失败路径、退出清理；手工：双击可视进度框并自动开浏览器 |
| T8 | `build/build.ps1` | PyInstaller `onedir` 打包 `EFTMap.exe`（含 `assets/`、`data/`、`index.html`、`style.css`、`app.js`、`tools/`）；可选 `.ico` | 打包后双击 `EFTMap.exe` 走完 T7 流程；产物可离线运行 |
| T9 | `README.md` | 安装、拉数据、启动、定位配置、**来源署名 + 免责 + CC BY-NC-SA 声明 + 永久免费严禁售卖** | 逐项对照规格 §11 许可表 |
| T10 | M1 收尾 | 全量 pytest 绿；手工核对记录（截图）写入提交信息 | `pytest -q` 通过 |

## 3. M2 任务清单

| # | 任务 | 产物 | 验收 |
| --- | --- | --- | --- |
| T11 | 截图文件名解析 `tools/screenshot.py` | 宽容解析器（返回 `x, z, yaw` 或 `None`）；`parse_*` 纯函数 | 单测：正/异常/半匹配样本；解析失败**不报错不误报** |
| T12 | `serve.py` SSE + 监听线程 | `GET /api/position`、`GET /api/health`、`GET /events`（SSE）；后台线程轮询截图目录（默认 `Documents\Escape from Tarkov\Screenshots`），变更才广播 | 单测：帧格式 `data: {...}\n\n`、订阅者广播、目录不存在时降级不停服 |
| T13 | 前端实时层 | `EventSource` 订阅；玩家 marker + 朝向箭头；自动居中/手动锁定；「定位不可用」状态；首屏 `/api/position` 兜底 | 手工：投喂样本截图文件名 → 地图上出现并移动玩家点 |
| T14 | 打包与文档更新 | launcher 参数 `--screenshots`、README 定位章节、版本号 | 端到端：改文件名 → 浏览器实时更新 |

---

## 4. 测试清单（pytest，全部离线、用本地样本与桩件）

| 文件 | 覆盖 |
| --- | --- |
| `tests/test_coord_transform.py` | 仿射推导：矩形角点映射到 `(0,0)`/`(W,H)`、旋转 0/90/180/270、每图 ≥90% 标注点落在 viewBox 内（用真实 `data/maps.json`，缺失则 skip）、海关黄金值对照 |
| `tests/test_fetch_data.py` | 规范化：占位名替换为中文、`ex_*`/`tr_*` 解析、字段裁剪、幂等（不重复拉取）、失败不破坏已有数据 |
| `tests/test_screenshot_parse.py` | 正/异常/半匹配样本、返回 `None` 而非抛错 |
| `tests/test_serve.py` | `/api/health`、`/api/position`、SSE 首帧与广播、目录缺失降级 |
| `tests/test_launcher.py` | 步骤编排（桩件替换起服务/开浏览器）、失败路径、退出清理 |
| `tests/fixtures/` | 裁剪过的小样本 JSON、假截图文件名列表（**不含**任何游戏资源） |

---

## 5. 提交策略

- 每个任务或每组相关任务独立提交；身份用 `git -c user.name="EFT Interactive Map" -c user.email="noreply@example.invalid"`（本机无 git 身份，**不得写入配置**）。
- 提交信息中文，说明"为什么"。

## 6. 待用户提供 / 待确认

- EFT 截图文件名的**真实样本**（至少 2–3 个账号截图文件名）：M2 解析器先按宽容规则实现并测试，拿到样本后补真实用例。
- exe 图标：先用简约占位图标。
