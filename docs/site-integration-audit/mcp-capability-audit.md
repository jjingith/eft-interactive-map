# MCP 能力审计（R20 第一阶段 3.1 / 3.2）

> 审计时间：2026-10-29
> 审计方式：**只依据当前会话真实可调用的工具与真实执行结果**，不依据「安装成功」提示推断能力。
> 环境：Chrome 156.0.8078.47（headless=new，`--no-proxy-server`），CDP 端点 `http://127.0.0.1:9333`。

---

## 0. 结论先行

| 结论 | 内容 |
|---|---|
| 是否存在「浏览器控制类 MCP」 | **存在，但不是内置 connector，而是自定义 stdio MCP `rea`**（`rea-agents`，node24 启动，`--mcp`）。它通过 **CDP** 观察/截取页面，属于「连接已有浏览器」型，不自带导航能力。 |
| 真正可用的浏览器通道 | **`rea` MCP（只读取证）+ 本机 Chrome/CDP 脚本（导航与交互）** 两条腿。前者合规、证据结构化；后者灵活、可点可截。 |
| 不能做的事 | MCP 不能写文件、不能自带浏览器导航（除 `capture_browser_scenario` 的 start_url）、默认不保留请求头/正文/cookie/存储值（策略过滤）。 |
| 对本次研究的实际影响 | db4tarkov 是 Flutter(canvas) 站点，**DOM 文本提取不可行**，只能「语义树 + 截图」；eftarkov 是服务端渲染，DOM 提取可行。 |

---

## 1. 已接入的 MCP 清单（核实方式：会话工具列表 + `list_installed_plugins`）

| 名称 | 类型 | 接入方式 | 与本任务相关能力 |
|---|---|---|---|
| `rea` | 自定义 stdio MCP | `node rea.mjs --mcp` | **CDP 浏览器观察 / 截图 / DOM / 脚本 / 网络元数据**（本次核心） |
| `connector-proxy` | 内置网关 | http | `domain_search`、`knowledge_search`、`search_plugins` 等，**无浏览器** |
| `github` | connector | http | 仓库读写，**无浏览器** |
| `agent-mail` | connector | http | 邮件 |
| `genie-baas` | connector | http | 云数据库/存储 |
| `space-library` | connector | http | 资料库检索 |
| `sheetagent` | 自定义 stdio | node | 表格读写 |
| `weixinpay` | 内置插件 | stdio | 支付 |

`list_installed_plugins` 结果：仅 `github` 处于 `connected / bound / enabled`；其余自定义 MCP 由 `CODEBUDDY_MCP_CONFIG` 注入，属于「已接入但不在 connector 列表里」的一类——**这正是任务书警告的「不能凭安装提示推断能力」的典型场景**。

---

## 2. 能力矩阵（逐项实测）

图例：**✅ 已实测可用** / **🟡 部分可用（有明确限制）** / **❌ 不可用** / **❔ 未实测**

| 能力 | 承载工具 | 结论 | 实测证据 |
|---|---|---|---|
| 网页访问（打开目标站） | `rea` 无独立 navigate；`capture_browser_scenario.start_url` | 🟡 | `rea` 侧未实测 start_url（见 §4）；**改用本机 Chrome 导航实测成功**：db4tarkov 200（Cloudflare）、eftarkov 200（nginx），见 `raw/db4-*.json` `raw/eft-*.json` 的 `url` 字段 |
| 浏览器操作（点击/输入/切标签） | `capture_browser_scenario.actions` | 🟡 | MCP 侧 ❔ 未实测；**本机 CDP `Input.dispatchMouseEvent` 实测**：可以点击，但 Flutter canvas 的命中不稳定（见 §3.3） |
| DOM 分析 | `inspect_web_page` | ✅（受策略过滤） | 对 db4tarkov 返回 **114 个 DOM 节点**（含 `FLUTTER-VIEW`/`FLT-CANVAS-CONTAINER`/`CANVAS`）、8 个脚本、6 个资源、9 条 console；同时 `policy_filtered_sections` 列出被过滤项（accessibility/script_sources/metadata/resources） |
| 截图 | `capture_web_screenshot` | ✅ | 返回内容寻址 PNG artifact（`sha256: fc1b9408…`, 34,225 bytes, 1584×905），见 `evidence_id ev_869b47e9…` |
| 网络分析 | `inspect_web_page.network` | 🟡 | 返回 `requests: []`——因为 **观察窗口从 attach 开始**，本次 attach 晚于页面加载。要拿请求必须在导航前 attach。**改用本机 CDP `Network.*` 事件实测成功**：单页 146 次请求、可统计 host 分布（见 `raw/db4b-flow.json` `hosts`） |
| JavaScript 分析 | `inspect_web_page.scripts` + `export_web_scripts` | 🟡 | 脚本清单 ✅（`main.dart.js` **18,558,820 bytes**、`canvaskit.wasm` 5.7MB）；**源码默认不采集**（`source.included=false, reason="source capture was not selected"`），`export_web_scripts` ❔ 未实测 |
| 文件操作（把审计结果写盘） | — | ❌ | `rea` 无写文件工具；**改用本地 Python 脚本落盘**（`docs/site-integration-audit/`，本次已写入 raw/ screenshots/ 共 21 个文件） |
| 数据提取（结构化） | DOM/语义树 | 🟡 | eftarkov：DOM 文本可用（`/task-tree` 正文 44,993 字符、`/hideout` 1.69MB HTML）；db4tarkov：`innerText` 常为 0，必须点开 Flutter 语义占位符后读 `[aria-label]`（实测取到 12 个一级栏目 + 各页筛选项） |
| 自动化验收（操作本地项目并读结果） | `rea` 连接本项目 CDP | 🟡 | 本项目已有 `tools/r181_accept.py`（CDP 封装）+ R19.29 验收脚本（12/12 通过）。`rea` 可连同一端点做只读取证，但不能替代「点击—断言」流程 |

---

## 3. 实际工作链路验证（对应任务书 3.2 的 8 项）

### 3.1 打开两个目标站

| 站点 | 结果 | 关键观察到的事实 |
|---|---|---|
| `https://db4tarkov.com/` | ✅ 打开，但会 302 到 `/gun` | HTML 仅 60KB 外壳，正文由 Flutter canvas 绘制；首次进入需下载数据（页面显示 “Downloading Season Flea Market…”，**约 30–45 秒**才可交互） |
| `https://www.eftarkov.com/` | ✅ 打开 | nginx 服务端渲染，HTML 77KB 内含真实内容（公告、商人补货倒计时、最新任务、服务器状态） |

> 直连测试（绕过系统代理 `http://127.0.0.1:9031`）：
> `db4tarkov.com` HTTP 200 / 60,675 bytes / 1.1s / `server: cloudflare`；
> `www.eftarkov.com` HTTP 200 / 76,970 bytes / 0.2s / `server: nginx`。
> **结论：本机可直接访问两个站点，无需代理。**

### 3.2 进入有实际交互的子页面

- db4tarkov：`/gun` `/market` `/quest` `/keep` `/preset` `/ammo` `/map` `/barter` `/craft` `/changes` `/season` `/logs` —— **12 个栏目全部进入并截图**。
- eftarkov：`/task` `/task-tree` `/hideout` `/ammo` `/resale` `/fabrication` `/exchange` `/boss` `/map/653e6760…` —— **9 个页面进入并截图**。

### 3.3 读取页面结构 + 保存截图

- 截图：`docs/site-integration-audit/screenshots/`（db4 13 张 + eft 10 张，1600×1000 PNG）。
- 结构：`raw/*.json` 内含 `aria[]`、`links[]`、`requests[]`、`console[]`、`hosts`。
- **Flutter 站点的坑**：`document.body.innerText` 在数据加载完成前是 0；导航项**不在**语义树里（只有页面内容会进），因此「点导航」只能靠坐标。这一点已记录为限制，没有伪造成功率。

### 3.4 是否需要登录 / 动态加载 / 访问限制

| 站点 | 登录 | 动态加载 | 访问限制 |
|---|---|---|---|
| db4tarkov | 有账号体系（`accounts.google.com`、文案 “Login to save your progress”），**浏览数据无需登录** | 全部动态（Flutter + Firebase/Supabase + 自有 CDN） | 存在 **Firebase App Check**（`firebase-app-check-database`、`recaptchaSiteKey`）与 Cloudflare；未见验证码拦截浏览 |
| eftarkov | 有 `/login` `/register`，**浏览无需登录** | 服务端渲染，按页加载 | 未见拦截 |

### 3.5 可观察到的请求与数据

| 站点 | 主要 host（实测计数） | 含义 |
|---|---|---|
| db4tarkov | `cdn.db4tarkov.com`(97) `db4tarkov.com`(21) `eft-cdn.dvcstudiox.workers.dev`(5) `firebase.googleapis.com` `firebaseinstallations.googleapis.com` `*.supabase.co` `json.tarkov.dev` `fonts.gstatic.com` `accounts.google.com` `static.cloudflareinsights.com` | 图标走自有 CDN；业务数据走自有 Workers CDN + Firebase(Firestore) + Supabase；**`json.tarkov.dev` 说明它自己也消费 tarkov.dev 公开数据**；字体走 Google Fonts（外部依赖） |
| eftarkov | 仅 `www.eftarkov.com`（29–79 次/页） | 纯服务端渲染，无第三方接口调用 |

### 3.6 保存审计结果到项目文档

✅ 已完成：本目录下 `raw/`（21 个 JSON）、`screenshots/`（23 张 PNG）、`*.md`（本套文档）。**由本地 Python 脚本写入，不经过 MCP**（MCP 无写文件能力）。

### 3.7 MCP 连接本地测试服务 / localhost 代理问题

- 本项目验收脚本启动 Chrome 时固定带 `--no-proxy-server`；R19.29 验收（463 次请求）host 只有 `127.0.0.1`，**证明 localhost 未被送进代理**。
- 本次研究同样使用 `--no-proxy-server`，否则本机 headless Chrome 会把 `127.0.0.1` 也交给 `http://127.0.0.1:9031` 代理，页面变成 `chrome-error://chromewebdata/`（本会话早期已实际踩到：页面 title 只剩 `127.0.0.1`）。

### 3.8 打不开时的记录口径

本次两个站点均打开成功，无失败记录。**未验证项**：断网/受限网络下的表现、目标站在中国大陆网络环境下的可达性（**未知**，未做多网络环境对比）。

---

## 4. 未实测项（明确列出，不用推断代替）

| 项 | 状态 | 原因 |
|---|---|---|
| `capture_browser_scenario` 的 `start_url` + `actions` 全链路（MCP 自己启动浏览器并点击） | ❔ 未实测 | 其 canonical 输入 schema 未公开（compact profile），首次调用风险高；本轮已用本机 CDP 覆盖同类能力，不影响研究结论 |
| `export_web_scripts` / `recover_javascript_sources` | ❔ 未实测 | db4 的 `main.dart.js` 是 18.5MB Dart 编译产物，无 sourcemap，反编译收益极低 |
| `observe_web_session` | ❔ 未实测 | 需要「用户手动操作」窗口；本次用脚本主动导航已足够 |
| `inspect_web_network_capture` 的请求体/响应体 | ❔ 未实测 | `rea` 默认 `policy_filtered`，正文需显式授权；且任务书要求不抓私有后端 |

---

## 5. 对后续开发的直接约束（写进方案）

1. **不要把 `rea` 当作浏览器自动化框架**：它擅长「取证 + 结构化证据」，不擅长「连续交互流程」。后续每个模块的浏览器验收继续用项目既有 `tools/r181_accept.py`（CDP）。
2. **db4tarkov 不能作为可抓取的数据源**：Flutter canvas + App Check + 无公开 API，任何「解析它的页面拿数据」的方案都不可行且不合规。只能作为**功能与交互的参考**（任务书 2.4 的定位）。
3. **eftarkov 的 HTML 可解析**，但内容是其站点整理的中文译文与图片素材，**版权需单独确认**；只能用于「功能形态参考」，不能整站复制。
4. **审计证据必须落盘成可复现脚本**：`tools/r20_site_probe.py`（单页取证）与 `tools/r20_flow_probe.py`（站内流程）已入库，后续任一结论都可重跑复现。
