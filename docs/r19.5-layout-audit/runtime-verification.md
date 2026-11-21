# R19.5e 运行链路诊断（runtime-verification）

诊断时间：2026-10-25 16:45–17:10（Asia/Taipei）
项目目录：`D:\personal\trae\02-塔科夫\eft-interactive-map`
本轮只做取证与版本标记，未改布局结构、未覆盖 `release/`、未提交/推送 Git。

---

## 0. 先声明取证边界

**无法直接连接用户实际打开的那个浏览器标签页。** 本机 Chrome 主进程（PID 22900，2026-10-23 21:25 启动）命令行里没有 `--remote-debugging-port`，`DevToolsActivePort` 也不存在，因此无法用 CDP 读取该标签页的 DOM 与计算样式。

- 全端口扫描后只发现两个相关监听：`127.0.0.1:8787`（项目服务）与 `127.0.0.1:9333`（**本次诊断自建的隔离 Chrome 实例**，不是用户浏览器）。
- 本机没有运行 Edge / Firefox / Brave / Opera，所以用户页面只可能在 PID 22900 这一个 Chrome 里。

替代取证手段（全部为实测，不推断）：

1. Windows UI Automation 读取该 Chrome 窗口的地址栏与 Document 视口；
2. 主配置 `History` 的访问时间与 transition 类型；
3. 主配置 `Cache_Data` 的响应体与写入时间；
4. 主配置 `Local Storage` 的界面状态；
5. 隔离 Chrome 实例（同 URL、同服务、`Network.setCacheDisabled`）的真实渲染测量；
6. 直接对 8787 发 HTTP 请求并逐字节比对磁盘文件。

> 这也意味着：**用户标签页「当前这一屏」的像素级状态无法由我直接断言**，只能由下文的服务端/浏览器缓存证据 + 页面新增的版本徽标来确认。

---

## 1. 用户实际访问的 URL 与端口

UI Automation 读取窗口 `EFT 互动地图 · 离线免费版 - Google Chrome`（窗口矩形 `10,10 1400×900`）：

| 项 | 实测值 |
|---|---|
| 地址栏（`地址和搜索栏` ValuePattern） | `127.0.0.1:8787` |
| 实际 URL | `http://127.0.0.1:8787/` |
| 协议 | HTTP（非 file://，非 release/ 静态文件） |
| Document 视口 | `18,97 1384×779` |

注意：这个 1400×900 的窗口属于**我自建的隔离实例**（见第 2 节的命令行差异），不是用户的窗口。用户窗口是同一 Chrome 主进程下 `-8,-8 1936×1056` 的最大化窗口（Document 视口 `0,121 1920×919`），当时前台标签是 ChatGPT，地图页是该窗口里的后台标签页。

- History 里本地入口只有 `http://127.0.0.1:8787/`（59 次访问，最近一次 16:36:28），**没有任何 `file://` 或 `release/` 入口**；`8791` 只在 10-19 访问过 1 次，与地图无关。

---

## 2. 端口监听进程、命令行与工作目录

```
TCP  127.0.0.1:8787   LISTENING  7212     ← 诊断开始时的服务进程
TCP  127.0.0.1:9333   LISTENING  11768    ← 本次诊断自建的隔离 Chrome（--remote-debugging-port=9333）
```

进程链（`Win32_Process`）：

| PID | 父 PID | 进程 | 命令行 | 创建时间 |
|---|---|---|---|---|
| 2704 | 2596 | cmd.exe | `cmd /c "D:\personal\trae\02-塔科夫\eft-interactive-map\启动项目.bat"` | 10-24 14:19:43 |
| 30908 | 2704 | py.exe | `py -3 "tools\serve.py" --port 8787` | 10-24 14:19:44 |
| **7212** | 30908 | python.exe | `C:\Python314\python.exe "tools\serve.py" --port 8787` | 10-24 14:19:44 |
| 11768 | — | chrome.exe | `chrome.exe --remote-debugging-port=9333 --user-data-dir=D:\Temp\r195d_chrome ... --window-size=1400,900 http://127.0.0.1:8787/` | 10-25 16:47:11 |

`启动项目.bat` 的关键行（第 4、97 行）：`cd /d "%~dp0"` → `%PY% "tools\serve.py" --port %PORT%`，默认 `PORT=8787`。因此：

- 服务由**项目自带的启动脚本**拉起，不是打包产物、不是 `release/`、不是第二份拷贝；
- 命令行用的是**相对路径** `tools\serve.py`，结合 bat 的 `cd /d "%~dp0"`，可确定工作目录就是项目根目录。

> 磁盘上 `tools\serve.py` 的 mtime 是 10-20 23:04:21，早于进程启动时间 10-24 14:19:44，所以运行中的进程加载的就是当前这份 serve.py，不存在"服务端代码陈旧"。

---

## 3. 服务实际托管的根目录

`GET http://127.0.0.1:8787/api/health`：

```json
{ "ok": true, "app": "eft-interactive-map", "version": "0.1.0",
  "root": "D:\\personal\\trae\\02-塔科夫\\eft-interactive-map", ... }
```

`ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))`，即 `tools/` 的上一级。结论：**该进程托管的目录与 `D:\personal\trae\02-塔科夫\eft-interactive-map` 完全一致**。

重启后新增的 `/api/build` 直接回传 `cwd`，再次确认：

```
PID=29996  CMD="C:\Python314\python.exe" "tools\serve.py" --port 8787 --no-browser
cwd = D:\personal\trae\02-塔科夫\eft-interactive-map
root = D:\personal\trae\02-塔科夫\eft-interactive-map
```

同时排除了"多份同名项目 / 多个开发服务器"：全机 Python/Node 监听进程只有该项目服务、一个 AstrBot 实例和一个 WorkBuddy 的 node 进程，没有第二个托管本项目的服务。

---

## 4. 浏览器实际加载的资源

### 4.1 用户配置的访问与缓存时间线（关键证据）

主配置 `History`（`Chrome 时间` 已换算为本地时间）：

| 本地时间 | transition | URL |
|---|---|---|
| 16:36:28 | `RELOAD`（0x30000008 = CHAIN_START/END + RELOAD） | `http://127.0.0.1:8787/` |
| 16:34:29 | `RELOAD` | `http://127.0.0.1:8787/` |
| 16:01:40 | `RELOAD` | `http://127.0.0.1:8787/` |
| 15:52:42 | `RELOAD` | `http://127.0.0.1:8787/` |

`style.css` 的磁盘 mtime 为 **16:11:47**（即 R19.5d 落盘时间）。也就是说，用户**在 R19.5d 落盘之后又重载了两次**。

主配置 `Cache_Data` 的响应体与写入时间进一步锁定了版本：

| 缓存文件 | 大小 | 写入时间 | 内容判定 |
|---|---|---|---|
| `f_003a84` | 158935 | 11:34:53 | 旧 style.css（无 `minmax(188px`） |
| `f_003a85` | 701389 | 11:34:53 | 旧 app.js |
| `f_003ab5` | 713963 | 16:01:40 | 当前 app.js（SHA 与磁盘一致） |
| **`f_003ab8`** | **178890** | **16:34:29** | **R19.5d 的 style.css**（含 `minmax(188px, 1fr)`，含 2 处 `486fr` 旧规则） |
| `f_003abc` | 21308 | 16:36:28 | 当时的 index.html（未含本轮徽标） |
| `f_003abd` | 56411 | 16:36:28 | theme-windows-xp.css |
| `f_003abe` | 41992 | 16:36:28 | gun_builder.js |

**结论：用户浏览器在 16:34:29 确实取到了 178890 字节的 R19.5d 样式表，16:36 又重载了一整套页面资源。** 这否定了"浏览器从未加载新 CSS"的假设。

> 同一条链路也暴露了一个**真实隐患**：`style.css` 从 R19.5b→R19.5d 一直用同一个查询串 `?v=r19.5`，缓存里同时留着 151059 / 158935 / 178890 三代 body。版本号不随内容变化，就没有任何机制能保证下一次改动一定被重新取用。本轮已把查询串改为 `?v=r19.5e`，并在页面加了可读的版本徽标。

### 4.2 真实浏览器的请求 URL（隔离实例，禁用缓存，1920×919）

| 请求 URL | 状态 | 类型 | 命中缓存 |
|---|---|---|---|
| `http://127.0.0.1:8787/` | 200 | text/html | false |
| `http://127.0.0.1:8787/style.css?v=r19.5e` | 200 | text/css | false |
| `http://127.0.0.1:8787/theme-windows-xp.css?v=r19.5e` | 200 | text/css | false |
| `http://127.0.0.1:8787/app.js?v=r19.5e` | 200 | text/javascript | false |
| `http://127.0.0.1:8787/gun_builder.js?v=r19.5e` | 200 | text/javascript | false |
| `http://127.0.0.1:8787/combat_sim.js?v=r19.5e` | 200 | text/javascript | false |
| `http://127.0.0.1:8787/api/build?ts=…` | 200 | application/json | false |

控制台无报错。另外发现两张枪械图 404（`assets/guns-full/6a15ae2ae5267ba21c07f98f.png`、`assets/guns-full/6a78b7f8c2016eb33e0027cd.png`），属于既有素材缺口，与本次布局无关，仅记录。

### 4.3 HTTP 响应与磁盘逐字节比对

| 文件 | 字节 | HTTP SHA-256(前 12) | 磁盘 SHA-256(前 12) | 一致 | 响应头 |
|---|---|---|---|---|---|
| index.html | 22798 | `2d1622bafcbc` | `2d1622bafcbc` | 是 | `Cache-Control: no-store, must-revalidate` |
| style.css | 179249 | `d69296019ba3` | `d69296019ba3` | 是 | 同上 |
| theme-windows-xp.css | 56411 | `2010f24e0dab` | `2010f24e0dab` | 是 | 同上 |
| app.js | 713963 | `02dd579e5a95` | `02dd579e5a95` | 是 | 同上 |
| gun_builder.js | 41992 | `082ac715159f` | `082ac715159f` | 是 | 同上 |
| combat_sim.js | 33961 | `4432c61290d3` | `4432c61290d3` | 是 | 同上 |

（上表为本轮加入版本标记后的状态。诊断开始时抓取的 R19.5d 版 `style.css` 为 178890 字节、SHA-256 前 12 位 `CB3F6703F4A9`，与当时磁盘一致；`Last-Modified` 与磁盘 mtime 一一对应。）

结论：**没有"磁盘已更新、HTTP 仍返回旧内容"的情况**，服务端不做任何缓存或构建拷贝。

---

## 5. 可从实际页面读取的运行版本标记（本轮新增）

### 5.1 服务端

`tools/serve.py` 新增 `GET /api/build`，按请求实时计算 6 个前端资源的 `size / mtime / sha256` 并汇总成短指纹：

```json
{ "ok": true, "rev": "R19.5e-3a2cb94c", "server_version": "0.1.0",
  "pid": 29996, "cwd": "D:\\personal\\trae\\02-塔科夫\\eft-interactive-map",
  "root": "D:\\personal\\trae\\02-塔科夫\\eft-interactive-map",
  "started_at": 1792919140,
  "assets": [ { "file": "index.html", "size": 22798, "mtime": 1792919112, "sha256": "2d1622…" }, … ] }
```

`rev` 由这 6 个文件的 sha256 串再取哈希，**任一文件改动都会变**，不依赖人工改版本号。

### 5.2 页面端

`index.html` 顶栏末尾新增徽标 `<span id="build-rev" class="build-rev">rev —</span>`，页面加载后由内联 ES5 脚本请求 `api/build?ts=…` 并写入：

- 徽标文本：`rev R19.5e-3a2cb94c`
- `<html data-build-rev="R19.5e-3a2cb94c">`
- `<meta name="build-rev" content="R19.5e-3a2cb94c">`
- 控制台：`[EFTMap] build-rev = R19.5e-3a2cb94c`

实测（隔离实例，真实渲染）：`{"attr":"R19.5e-3a2cb94c","badge":"rev R19.5e-3a2cb94c"}`，截图见 `screenshots/runtime-r195e-1920x919.png`（右上角可见徽标）。

**用户自检方法**：在打开的地图页按 `Ctrl+F5`，看顶栏最右侧。显示 `rev R19.5e-3a2cb94c` = 已加载本轮版本；显示 `rev —` 或别的值 = 仍是旧页面。

---

## 6. 真实 DOM 测量值

测量方式：隔离 Chrome 实例（同一 URL、同一服务、`Network.setCacheDisabled`），点击 `配枪 → 类别 → 第一把枪 → 工作台` 进入 `.gw-buildpage`，用 `getComputedStyle` + `getBoundingClientRect` 读取。

### 6.1 1920×919（用户窗口的 Document 视口）

| 项 | 实测 |
|---|---|
| `.gw-buildpage` 矩形 | `x=0 y=103 w=1920 h=816`，`display:grid`，`hidden=false` |
| `grid-template-columns` | **`461px 461px 922px`**（严格 1:1:2） |
| `column-gap` / `padding-right` | `8px` / `60px`（≥1700px 媒体查询生效） |
| 三栏 x/宽 | FORGE `0/461`，中栏 `469/461`，候选表 `938/922`（右缘 1860 + 60 留白 = 1920） |
| `.gw-part` 配件卡 | **52×52**（9 个抽样一致，`cssW/cssH` 均为 `52px`） |
| `.gw-part` 两两重叠 | **0** |
| `.gw-gun` 枪械卡 | `232×151` |
| `.gw-canvas` | `x=481 y=441 422×399`，`scrollWidth=420 / clientWidth=420` |
| 隐藏属性 `.gw-stat-conf` | 共 10 个，`display!=none` 的 **0 个**（全部隐藏） |
| 横向溢出 | 无（`scrollWidth=1920`） |

### 6.2 1384×805（同规则、窄视口）

| 项 | 实测 |
|---|---|
| `grid-template-columns` | `340px 340px 680px`（仍是 1:1:2） |
| 三栏 x/宽 | `0/340`、`348/340`、`696/680` |
| `.gw-part` | 52×52，重叠 0 |
| `.gw-gun` | `190×139`（≤1500px 的 `max-width:190px` 生效） |
| 隐藏属性徽标 | 0 个可见 |

### 6.3 R19.5c 与 R19.5d 的实际差异（同页注入旧规则实测，1920×919）

| 指标 | R19.5c（旧规则） | R19.5d（当前） | 差异 |
|---|---|---|---|
| 三栏宽度 | `502 / 507 / 887` | `461 / 461 / 922` | −41 / −46 / +35 px |
| `.gw-part` | `64×64` | `52×52` | −12 px |
| `.gw-gun` | `260×157` | `232×151` | −28 / −6 px |
| 隐藏属性徽标可见数 | `10 / 10` | `0 / 10` | 全部隐藏 |

---

## 7. 与磁盘 R19.5d 文件的比较

- `style.css` 磁盘中确实存在 R19.5d 规则块，且是级联中最后一条：

```css
.gun-workbench .gw-buildpage {
  grid-template-columns: minmax(188px, 1fr) minmax(296px, 1fr) minmax(300px, 2fr);
  column-gap: 8px;
}
.gun-workbench .gw-hidden .gw-stat-conf { display: none; }
.gun-workbench .gw-part { width: 52px; height: 52px; padding: 3px; }
.gun-workbench .gw-gun { min-width: 128px; max-width: 232px; padding: 2px 6px; }
.gun-workbench .gw-gun-img { max-height: 78px; }
@media (max-width: 1500px) { .gun-workbench .gw-gun { max-width: 190px; } .gun-workbench .gw-gun-img { max-height: 66px; } }
```

- 浏览器里 `document.styleSheets` 命中的 `.gw-buildpage` 规则共 5 条，最后一条正是上面这条；`getComputedStyle` 输出 `461px 461px 922px`，即最后一条生效。
- HTTP 返回与磁盘 SHA 完全一致（§4.3）；缓存里 16:34:29 落下的 body 大小 178890 与 R19.5d 的 style.css 字节数一致，且包含 `minmax(188px`。
- 因此在"文件是否正确送达浏览器"这一层，**没有发现任何不一致**。

---

## 8. 导致页面"看起来没更新"的确切原因

按证据可排除的项：

| 假设 | 结论 | 证据 |
|---|---|---|
| 服务不是这份项目 | 排除 | §2 启动链 + §3 `root` |
| 端口/URL 不是 8787 | 排除 | §1 地址栏 + History 唯一入口 |
| HTTP 返回旧内容 | 排除 | §4.3 逐字节一致 + `no-store` |
| 浏览器从未取到 R19.5d CSS | 排除 | §4.1 缓存 `f_003ab8` 178890 @16:34:29 |
| Service Worker 拦截 | 排除 | `app.js` 无 `serviceWorker` 注册；页面无 SW 目标 |
| CSS 级联被旧规则覆盖 | 排除 | §6.1 计算值与 R19.5d 规则一致 |

剩下的确切原因有两条，且互为补充：

1. **R19.5d 只改了 CSS，没有改 DOM。** `app.js` mtime 15:54:06、`index.html` 15:52:00 都早于 R19.5d（16:11:47）。用户要求的核心是"图形区域不能再是一堆配件图片"（第 5 条）与"装配卡片缩小、间距压缩、隐藏属性紧凑"（第 4/5 条），而 `app.js` / `index.html` 里 `.gw-canvas` + 绝对定位 `.gw-part` 的渲染方式一行未动。实测 1920×919 下中间栏仍然是：节点画布 → 属性条 → 隐藏属性 → **枪图周围散落的 9 个配件图片卡**。也就是说，用户看到的"结构"和 R19.5c 完全一样。

2. **可感知差异的量级很小。** 在用户的实际视口 1920×919 上，R19.5c→R19.5d 的差异只有三栏 −41/−46/+35 px、卡片 64→52 px、枪卡 260→232 px、徽标从 10 个变成 0 个。前两项是"整体缩了一圈"，没有改变任何分区的存在、层级或数量；唯一显眼的"去徽标"又位于中栏下部一个 40–100px 高的区块里，容易被忽略。因此在"页面有没有变化"这个判断上，用户得出"没有变化"是符合实际观感的。

> 换言之：**运行链路是正确的，浏览器确实加载了 R19.5d；问题出在 R19.5d 的改动本身只是表面数值微调，没有触及用户指出的结构性问题。**

---

## 9. 仍未直接验证的一环（如实标注）

- 用户那个已打开标签页的**当前 DOM / 截图**未取得：该 Chrome 未开调试端口，无法附加。本节所有"实际页面"测量来自**同一服务的另一个真实 Chrome 实例**。
- 若要 100% 确认该标签页的版本，请按 §5.2 重载并读取顶栏徽标；这是本轮新增、唯一能由用户在真实页面上直接看到并核对的版本证据。

---

## 10. 本轮对代码的改动（仅为加版本标记，无布局改动）

| 文件 | 改动 |
|---|---|
| `tools/serve.py` | 新增 `import hashlib`、`STARTED_AT`、`BUILD_ASSETS`、`_sha256_file()`、`build_info()`，并在 `do_GET` 里加 `/api/build` |
| `index.html` | 顶栏新增 `#build-rev` 徽标；内联 ES5 脚本读取 `api/build` 写入徽标 / `meta` / `<html data-build-rev>`；资源查询串改为 `?v=r19.5e` |
| `style.css` | 仅新增 `.build-rev` 徽标样式（6 行），未改任何布局规则 |

**服务重启记录**：原进程 PID 7212（由 `启动项目.bat` 拉起）已停止，以同一解释器和同一参数重启为 PID 29996；额外加了 `--no-browser` 以免再弹一个标签页。若需要恢复原来的启动方式，直接重新双击 `启动项目.bat` 即可（端口占用时会走它自己的"已占用"分支）。

---

## 11. 结论与等待确认

1. `http://127.0.0.1:8787/` 由本项目 `tools/serve.py` 托管，root = `D:\personal\trae\02-塔科夫\eft-interactive-map`，与预期一致。
2. 浏览器在 16:34:29 已取到 R19.5d 的 `style.css`（178890 字节），16:36:28 又整页重载；磁盘与 HTTP 响应完全一致，无缓存/Service Worker 干预。
3. 实际渲染测量证明 R19.5d 的规则**确实生效**（三栏 461/461/922、卡片 52×52、徽标 0 可见）。
4. 因此"页面没有变化"不是更新失败，而是 **R19.5d 只做了 CSS 数值微调，用户指出的图形区结构问题（一堆配件图片）完全没动**，这与用户的验收口径直接冲突。
5. 版本标记 `R19.5e-3a2cb94c` 已可从真实页面读取，供下一轮每次改动后核对。

按任务要求，此处停止，等待确认问题原因后再决定是否进入布局/结构整改。

---

## 附：证据文件

| 文件 | 说明 |
|---|---|
| `docs/r19.5-layout-audit/screenshots/runtime-r195e-1920x919.png` | 真实 Chrome 在用户视口（1920×919）加载当前服务的 build 页截图，右上角为版本徽标 |
| `D:\Temp\r195d_measure.json` | 本轮 1920×919 的完整测量 JSON（列宽 / 卡片 / 重叠 / 徽标 / 请求列表 / 控制台） |
| `D:\Temp\r195d_legacy.js` | 同页注入 R19.5c 旧规则的对照脚本 |
| `D:\Temp\r195d_probe\hist.py` | History 访问时间导出（主配置 / 隔离配置） |
| `D:\Temp\r195d_probe\cache2.py` `cache3.py` | Cache_Data 内对应版本的 body 与写入时间核对 |
