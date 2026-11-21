# R210 · 本地软件防破解：从原理对比到可落地方案

> 记录：HOMONAS / MASTERJJ · 2026-11-08 00:04 · 来源会话：本地软件防破解调研（自检推进）
> 性质：**方案文档，未改任何源码**。上一阶段只完成了外部资料收集（`D:\personal\trae\.workbuddy\_denuvo_wiki.txt`，Denuvo 维基原文），本文件补上「落到我们项目怎么做」这一段。
> 对象假设：本文以本项目 `EFTMap`（`eft-interactive-map`，0.2.0，PyInstaller onedir 分发）为保护对象。若实际要保护的是别的软件，第 2–4 节结论仍成立，第 5 节的工程量需按项目重算。

---

## 0. 结论速览

| 问题 | 结论 |
|---|---|
| 要不要做 Denuvo 式保护 | **不要**。需要自研 VM + 许可后端 + 逐版本维护；对本项目投入产出比接近 0。 |
| 现在最该做什么 | **只做「可追溯 + 可提示」的轻量层**：构建指纹、资源完整性自检、分发水印。0.5–2 天可完成，不改变使用体验。 |
| 能不能靠本地授权码收费 | **不建议作为主收费手段**。本地校验一定能被 patch；只能当「付费开关」，不能当护城河。 |
| 真正收得住钱的东西 | 服务端价值（云预设、公开构筑库、持续更新、客服）。但这与本项目铁律 1「运行期不联网」冲突，**属于产品级决策，需用户拍板**。 |
| 本次已定的做法 | 先落 L0/L1/L2；L3 等有真实付费验证再上；L4 暂不启动。见 §7 决策记录。 |

---

## 1. 现状事实（先查清再谈方案）

| 事实 | 证据 |
|---|---|
| 分发形态是 PyInstaller **onedir**，整个目录可直接复制运行 | [build.ps1](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/build/build.ps1#L53) 的 `python -m PyInstaller`；`build_release.ps1` 打 Portable / AppWindow / Setup 三件套 |
| 后端是 Python：`.pyc` 可被 `pyinstxtractor` 解包、再被反编译到接近源码 | PyInstaller 公开特性，无需本项目证据 |
| 前端全部明文：`app.js` 约 1.25 MB、`index.html`、`style.css`、`data/*.json` | [app.js](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/app.js) 等仓库文件 |
| 运行期不联网、不接第三方账号 | [AGENT_HANDOFF.md](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/AGENT_HANDOFF.md) 铁律 1 |
| 目前**没有任何** license / 激活 / 机器码 / 完整性校验代码 | 对 `tools/`、`build/` 全量检索 `license|激活|授权|machine|机器码` 无命中（只有 installer / PyInstaller 字样） |
| 分发渠道是 GitHub Release + 三件套 | AGENT_HANDOFF §0「发布包」行 |

**推论**：任何拿到 exe 的人，在 10 分钟内就能得到可读的 Python 逻辑与全部前端代码。所以「防拷贝」不是技术问题，是**成本问题**——只能抬高门槛，不能消灭。

---

## 2. 威胁模型（按真实概率排序）

| 编号 | 攻击者 | 行为 | 现有防护 | 轻量方案能否覆盖 |
|---|---|---|---|---|
| T1 | 普通用户 | 把整个文件夹/zip 转发给朋友 | 无 | **不能**（除非在线校验，违背铁律 1） |
| T2 | 搬运号 | 改软件名/图标/关于页，去掉作者署名后二次分发 | 无 | **能**（完整性自检 + 署名水印） |
| T3 | 有点技术的人 | 用 pyinstxtractor 解包、改前端/数据、重新打包 | 无 | 部分（只增加改名成本，不阻止） |
| T4 | 灰产 | 量产注册码 / 做通用 patch | 无 | **不能**（本地校验必被绕） |

结论：轻量方案主要解决 **T2/T3 的「去署名」**，这也是本项目最可能真实遇到的损失形态（被人换个名字说是自己的）。T1/T4 靠技术防不住。

---

## 3. 原理对比（各方案在我们这里的真实收益）

| 方案 | 原理 | 挡谁 | 对本项目收益 | 代价 |
|---|---|---|---|---|
| Denuvo 式 | 构建期把热路径改成自定义字节码 + 被偷常量 + 硬件指纹 + 在线激活 + 反调试 | T1/T3/T4 | **极低**：Python/JS 应用没有原生热路径可抽；还要自建许可后端 | 数月工程 + 长期维护 + 用户投诉 |
| VMProtect / Themida | 代码虚拟化 + 加壳 | T3/T4 | 低：只保护启动器壳，前端与数据仍是明文；有误报与杀软风险 | 商业授权费 + 兼容性测试 |
| Nuitka 编译 | Python → C → 原生 exe | T3 | 中低：提高反编译门槛，但前端/JSON 照旧可读 | 构建链改造，可能破坏「零依赖」与现有打包脚本 |
| PyArmor | 字节码加密 + 运行时解密 | T3 | 中低：能挡直接反编译，运行期仍需解密，可被 hook | 引入第三方运行时，与铁律 2 冲突 |
| 纯混淆（变量名/控制流） | 改名 + 插入无效分支 | T3 | 低 | 可读性下降，维护成本上升 |
| **完整性自检 + 构建指纹** | 构建期生成资源 SHA-256 清单，启动抽查 | T2/T3（改名改资源） | **高性价比** | 半天，零依赖（`hashlib` 标准库） |
| **可见水印 / 渠道码** | 关于页与截图角落写入 build_id、渠道标识 | T2（追溯泄露源） | **高性价比** | 半天 |
| 本地签名 license（Ed25519） | 离线签发授权文件，客户端公钥验签 | 仅「守规矩的用户」 | 低 | 1–3 天；必然被 patch |
| 服务端权益 | 云同步 / 更新通道 / 公开库 | T1/T4 | **最高**，但需联网 | 违背铁律 1，需产品决策 |

---

## 4. 推荐架构（离线、零依赖、渐进）

```
L0 构建指纹      build_id + 版本单点 + LICENSE/署名文件        必做，0.5 天
L1 完整性自检    assets/data/前端 关键文件 SHA-256 清单，启动抽查 必做，1 天
L2 分发水印      关于页 / 页面角标 / 截图水印显示 build_id+渠道   必做，0.5 天
L3 本地授权(可选) Ed25519 签名的 license 文件，仅作付费开关      暂缓，等商业化验证
L4 服务端权益    云预设 / 公开构筑库 / 更新通道                  暂不启动，需改铁律 1
```

### L0 · 构建指纹（必做）
- 打包时把 `git rev-parse --short HEAD`、构建时间、渠道（`portable|setup|dev`）写入 `build_info.json`，随包分发。
- 关于页显示 `版本 0.2.0 · 构建 <hash> · 渠道 <x>`。
- 价值：出现改包/冒充时能立刻判断是不是原版产物。

### L1 · 完整性自检（必做）
- 构建期对 `index.html / app.js / style.css / data/*.json / assets/icons 关键集` 生成 `integrity.json`（路径 → sha256）。
- 启动时抽样校验（全量校验 5k+ 物品图标太慢，抽样 + 首屏关键文件全量）。
- **只提示不阻断**：不一致时在关于页与日志里标「本副本已被修改」，不退出、不禁用功能。
- 理由：阻断等于给破解者一个明确的「改这里就通过」的目标；提示则保留追溯价值，且不误伤用户自己改配置。

### L2 · 分发水印（必做）
- 关于页固定显示作者与仓库地址；页面右下角/截图导出带 `build_id` 小字。
- 可选：给不同渠道（自己发 / 朋友 / 群）生成不同渠道码，泄露时可定位来源。

### L3 · 本地授权（暂缓）
- 形态：`license.json`（user、expiry、features、sig），公钥内置，Ed25519 验签（标准库无 Ed25519，需自带纯 Python 实现或改用 HMAC——HMAC 密钥在客户端等于公开，只能防误改，不能防伪造）。
- 定位：**付费版开关**，不是防盗版。上线前先确认真的有人愿意付钱。

### L4 · 服务端权益（暂不启动）
- 若要做，最小形态是「云预设同步 + 公开构筑库」，与 R209 对 Kaedeori 的分析一致：卖持续服务，不卖文件。
- 前置条件：修改铁律 1，需用户明确同意；涉及域名、备案、支付与客服。

---

## 5. 明确不做

- Denuvo 式自研 VM / 许可后端 / 逐版本差异化。
- VMProtect、Themida、驱动级保护、反调试、反虚拟机。
- 硬件码强绑定、强制在线校验、无客服的机器锁。
- 对本地功能收费（会被复制，且伤害口碑）。
- 用关闭 TLS 校验、静默上传用户数据等方式「保护」自己。

---

## 6. 验收标准（若后续实施 L0–L2）

1. `python -m pytest tests -q` 全绿；新增 `tests/test_integrity.py` 覆盖：清单缺失、文件被改、抽样通过三种情况。
2. 打包后 `build_info.json` 存在且 hash 与 git HEAD 一致（`tests/test_build_info.py` 或打包脚本内断言）。
3. 手动改一个 `data/*.json` 字节后启动，关于页出现「本副本已被修改」，其余功能不受影响。
4. 关于页能看到版本 / 构建 / 渠道三项；截图导出带 build_id。
5. 不引入任何第三方运行时依赖（`pip list` 不变）。

---

## 7. 决策记录（本轮自主决定，按最稳妥方案）

| 时间 | 决定 | 理由 | 后续触发条件 |
|---|---|---|---|
| 2026-11-08 00:04 | 只推进 L0/L1/L2，不写代码，先出方案 | 三项都是零依赖、可回退、不改变用户体验；L3/L4 涉及收费与铁律 1，超出「最稳妥」范围 | 用户确认后再排期实施 |
| 2026-11-08 00:04 | L1 采用「只提示不阻断」 | 阻断会给破解者明确靶点，也可能误伤自行改配置的用户 | 若确认存在大规模改包分发，再评估加强 |
| 2026-11-08 00:04 | 不采用 Denuvo / VMProtect / 硬件锁 | 与 R209 §3.6 结论一致：本地 DRM 对 Python/JS 应用收益极低 | 无 |
| 2026-11-08 00:04 | L4 暂不启动 | 需修改铁律 1（运行期不联网），属产品级决策 | 用户明确同意改铁律且验证付费意愿 |

---

## 8. 遗留与待确认

1. **保护对象确认**：本文按 `EFTMap` 写。如果「本地软件」指别的产品（例如 `08-ProbablyStolen-Mod` 或其他工具），需要重算第 5 节。
2. **收费意图**：目前项目无账号、无支付、无更新通道；若短期不打算收费，L3 可直接砍掉，只留 L0–L2。
3. **铁律 1 是否松动**：不改铁律就永远无法防 T1（整包转发）。这是产品取舍，不是技术缺口。
4. 外部资料仅收集到 Denuvo 维基原文，未做更多一手逆向；第 3 节对 Denuvo 原理的描述来自公开资料归纳，未在本机验证。

---

## 9. 实施接入点与实测成本（2026-11-08 00:40 复核，只读）

> 执行：HOMONAS / MASTERJJ · 2026-11-08 00:40 · 性质：**只读核实 + 追加本章，未改任何源码/构建脚本**

### 9.1 对 §1 事实的复核结果

| §1 的说法 | 复核结果 | 证据 |
|---|---|---|
| 分发是 PyInstaller onedir | 成立 | [build.ps1](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/build/build.ps1#L53-L65) 的 `--onedir --noconsole` |
| 前端全部明文 | 成立 | `app.js` 1.19 MB / `style.css` 0.27 MB / `index.html` 0.07 MB（实测字节数） |
| 目前没有任何授权代码 | 成立 | `tools/`、`build/` 全量检索 `license|激活|授权|机器码`，仅命中 `fetch_data.py` 里的**数据许可**字段，无激活/校验逻辑 |
| 运行期不联网 | 未在本轮复核 | 依赖 [AGENT_HANDOFF.md](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/AGENT_HANDOFF.md) 铁律 1 的既有约束 |

### 9.2 L0 / L1 / L2 接入点（按现有文件，不需要新架构）

| 层 | 接入位置 | 具体改动 | 必须注意 |
|---|---|---|---|
| L0 构建指纹 | [build.ps1](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/build/build.ps1#L41-L42) 的 `Test-RuntimePackage` **之后**、PyInstaller **之前** | 向 `$Staging` 写 `build_info.json`（git hash / 构建时间 / 渠道） | staging 阶段会对「未登记文件」直接 throw（[package_files.ps1](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/build/package_files.ps1#L400-L415)）；因此生成物要么在测试之后写入，要么登记进 `RuntimeFiles`；`-VerifyOnly` 分支（[build.ps1](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/build/build.ps1#L33-L37)）要同步 |
| L0 展示 | [app.js](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/app.js#L2036-L2046) 的 `renderMetaLine()`（`about-meta-line`） | 在「版本 / 模式 / 计数」后追加 `构建 <hash> · 渠道 <x>` | 该行目前读的是 `data/meta.json`，新增字段要兼容旧 meta（缺失时显示「未知」） |
| L1 清单 | 复用 [package_files.ps1](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/build/package_files.ps1#L16-L205) 的 `RuntimeFiles` + `RuntimeDirs` | 生成 `integrity.json`（路径 → sha256），随包分发 | 清单口径与「实际进包文件」必须同源，否则会漏检 |
| L1 校验挂点 | [serve.py](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/tools/serve.py#L2332-L2353) 的 `create_server()`，`index.html` 存在性检查之后 | 启动时异步抽样校验，结果缓存 | 不能在请求线程里做全量校验；失败只记录，不阻断 |
| L1 结果出口 | [serve.py](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/tools/serve.py#L1698-L1699) 的 `/api/health` | 增加 `integrity: {ok, checked, mismatched}` | 保持 health 的其他字段不变，避免 launcher 自检误判 |
| L2 水印 | 关于页 + 截图导出路径 | 关于页固定署名与仓库地址；截图角落写 `build_id` | 截图导出实现本轮**未定位到具体函数**，实施前需先找到导出入口 |

### 9.3 L1 实测成本（本机，2026-11-08 00:39）

- 首屏 13 个关键文件（`index.html / app.js / style.css / tasks.js / tasks.css / wiki-map.js / gun_builder.js / combat_sim.js / i18n.js / data/items.json / data/maps.json / data/meta.json / data/search-index.json`）全量 SHA-256：**19.6 ms**。
- 资产目录共 **5,670 个文件 / 25.7 MB**（`icons-items` 5,356 / 14.8 MB；`maps` 279 / 10.1 MB；`roadnet` 35 / 0.8 MB）。
- 20% 抽样（1,134 个文件）：**325.3 ms**；按此比例外推全量约 1.6 s（**推算值，未实测**）。
- 结论：§4 的「首屏关键文件全量 + 资产抽样」在启动耗时可接受范围内；20% 是安全起点，不必一次全量。

### 9.4 本轮追加的决策

| 时间 | 决定 | 理由 |
|---|---|---|
| 2026-11-08 00:40 | 只补接入点与实测数据，不写实现代码 | 保持上一轮「先方案、后实施」的边界；接入点已精确到文件与行，等用户拍板即可开工 |
| 2026-11-08 00:40 | L1 抽样比例定为 20%（可按机器性能上调） | 实测 325 ms，远低于用户可感知阈值；全量 1.6 s 会明显拖慢冷启动 |
| 2026-11-08 00:40 | 构建指纹写出时机固定在 staging 校验之后 | 避免触发 `Test-RuntimePackage` 的「未登记文件」硬报错，也避免污染 `-VerifyOnly` |

---

## 10. 实施前最后两个未知项已查清（2026-11-08 01:03，只读）

> 执行：HOMONAS / MASTERJJ · 2026-11-08 01:03 · 性质：**只读复核 + 追加本章，未改任何源码/构建脚本**
> 目的：§9.2 留下「截图导出入口未定位」与「build_info 如何进包」两个未知项，本章给出确定答案；同时修正 §1 一处事实遗漏。

### 10.1 修正：项目已有运行期文件指纹，L1 不必从零搭

§1 写的「没有任何完整性校验代码」不准确。实际已存在一套**运行期指纹**：

| 已有能力 | 位置 | 实际作用 |
|---|---|---|
| `GET /api/build` 返回 `rev` + 每个文件的 `sha256/size/mtime` | [serve.py](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/tools/serve.py#L338-L365) | 对 `BUILD_ASSETS` 现算摘要 |
| `BUILD_ASSETS` 只有 6 个文件：`index.html / style.css / theme-windows-xp.css / app.js / gun_builder.js / combat_sim.js` | [serve.py](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/tools/serve.py#L336-L343) | 覆盖首屏脚本，不含 `data/*.json` 与资产 |
| 页面把 `rev` 写进 `data-build-rev` / `meta[name=build-rev]` / 关于面板 `about-build-line` | [index.html](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/index.html#L1115-L1136) | 用于确认「浏览器加载的是不是磁盘这一版」 |

**关键边界**：它 hash 的是**当前磁盘上的文件**，没有可信基线，所以只能证明「前后端版本一致」，**不能证明文件未被篡改**。因此：

- L1 仍需要构建期生成 `integrity.json`（可信基线）；但**接入点可以直接扩 `BUILD_ASSETS`**，不需要新端点、新架构。
- L0 的 `build_id` 可以并入同一个 `/api/build` 响应，前端 `about-build-line` 已有渲染位，改动面比 §9.2 估计的更小。

### 10.2 「截图导出」不存在，L2 需要改口径

对 `app.js` 全量检索 `toBlob|toDataURL|ClipboardItem|下载|export png`：

- 只有 JSON 下载：预设导出 [app.js](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/app.js#L13173-L13182) `downloadJSON()`；枪械构筑导出 [app.js](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/app.js#L14993)。
- **没有任何「构筑图导出为 PNG」或截图导出函数**（与 R209 §2.1 里 Kaedeori 有 `copyToClipboard` 的差异一致）。

**结论**：§4 的 L2「截图角落写 build_id」目前没有落点，不应作为必做项。L2 收敛为两件事：

1. 关于页显示 `版本 · 构建 <hash> · 渠道`（复用 `about-build-line` / `about-meta-line`）。
2. 页面角标保留 `data-build-rev`（已有），渠道码只写进关于页，不新增图片导出功能。

若以后真的要「构筑图导出 PNG」，那是独立功能（R209 §2.5 已估 1–2 天），不应算进防破解方案。

### 10.3 `build_info.json` 进包的确定路径

| 事项 | 确定答案 | 证据 |
|---|---|---|
| 文件登记 | 必须加进 `$script:RuntimeFiles` | [package_files.ps1](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/build/package_files.ps1#L16-L205) 是显式白名单 |
| 未登记后果 | `Test-RuntimePackage` 对「看起来会进包但未登记」直接 throw | [package_files.ps1](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/build/package_files.ps1#L380) |
| 调用顺序 | staging 校验在 [build.ps1](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/build/build.ps1#L41-L42)，`-VerifyOnly` 在 [#L33-L37](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/build/build.ps1#L33-L37) | 两处都要能看到 `build_info.json` |
| 展示位 | 关于页 `about-meta-line` 现在把 `meta.generatedAt` 当「版本」显示，无构建号 | [app.js](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/app.js#L2036-L2046) |

**建议实施顺序**（等用户拍板后再动）：先 `RuntimeFiles` 登记 → 再生成 `build_info.json` → 再改 `about-meta-line` 加「构建/渠道」并兼容旧 `meta.generatedAt` 缺失。任何一步先做都会让另一处报错或显示「未知」。

### 10.4 本轮追加的决策

| 时间 | 决定 | 理由 |
|---|---|---|
| 2026-11-08 01:03 | L1 直接扩展 `/api/build` 与 `BUILD_ASSETS`，不新建端点 | 已有实现可复用，改动面最小、可回退 |
| 2026-11-08 01:03 | L2 去掉「截图水印」，只做关于页构建号 + 渠道码 | 项目不存在图片导出功能，硬做等于新增功能，超出防破解范围 |
| 2026-11-08 01:03 | 仍不写实现代码 | 与 00:40 决策一致；保护对象与收费意图未确认前，动构建脚本风险大于收益 |

### 10.5 同一时段的跨会话状态核验（只读）

| 会话 | 核验方式 | 结果 |
|---|---|---|
| 塔科夫互动地图 · 自动截图四项 | 代码检索 + 定向测试 | 日志目录/截图目录/截图键/间隔 ms/战局结束清理均有落点（[index.html](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/index.html#L428-L447)、[serve.py](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/tools/serve.py#L600-L720)、[eftlog.py](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/tools/eftlog.py#L345-L424)）；`pytest tests/test_autoshot.py tests/test_config.py tests/test_eftlog.py` → **249 passed / 1.99 s** |
| 同上 · 遗留 | 静态检查 | [test_autoshot.py](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/tests/test_autoshot.py) 仍有 4 组同名测试重复定义（后者覆盖前者）；仍未见重新打包产物 |
| Kaedeori 逆向 | 文档终态 | R209 已完成并收口，无新增改动 |
| 防破解调研 | 文档终态 | 本章为 00:40 之后的唯一增量，仍属方案层 |

## 11. 三项待确认决策已落定（2026-11-08 05:50，MASTERJJ@HOMONAS，只读，未改源码）

> §8 留有 3 个必须用户拍板的问题，导致本文一直停在「方案层」。按用户授权「遇到需要决策的地方按最稳妥方案定并记录下来」，本章把它们定下来，本文自此从「待确认」转为「可开工」。

### 11.1 决策 1：保护对象 = 本项目 EFTMap

| 项 | 决定 |
|---|---|
| 保护对象 | **`eft-interactive-map`（EFTMap 0.2.0，PyInstaller onedir）** |
| 理由 | 全文 §1–§10 的接入点（`build/package_files.ps1`、`build/build.ps1`、`tools/serve.py`、`app.js`）都在这个项目里，是唯一同时具备「打包分发链 + 前端明文 + 现已 604 项未提交改动」的对象；换成别的软件，这些行号全部失效 |
| 反向条件 | 若用户实际要保护的是 `08-ProbablyStolen-Mod` 或其他工具，§2 威胁模型与 §3 原理对比仍成立，§4/§9 接入点需按目标项目重算 |

### 11.2 决策 2：短期不收费 → L3 直接删除

| 项 | 决定 |
|---|---|
| 现状 | 项目无账号、无支付、无更新通道；R209（Kaedeori）结论也是「不卖文件、卖持续服务」 |
| 决定 | **L3 本地授权（Ed25519 license）直接删除，不再列入待办** |
| 理由 | 本地校验必被 patch（§3、§5），在没有真实付费样本前做它只有维护成本；保留 L0/L1/L2 三项 |
| 重启条件 | 出现「确实有人愿意付费」的证据后，再按 §4 L3 形态重启评估 |

### 11.3 决策 3：铁律 1 不松动 → 主动放弃 T1

| 项 | 决定 |
|---|---|
| 铁律 1 | **保持「运行期不联网」不变** |
| 决定 | 接受「整包转发（T1）无法防」，方案目标收敛为 T2/T3 的「去署名 / 换皮二次分发」 |
| 理由 | 为防 T1 引入在线激活会同时违背铁律 1 与「零依赖」，代价远大于本项目真实损失形态；写进文档是为了避免以后反复讨论同一件事 |

**由此，L0/L1/L2 的收益边界被明确写死：能做的是「可追溯 + 可提示」，不能做的是「防复制」。**

### 11.4 实施边界（本轮不写代码的原因）

这不属于「决策」，是执行前的客观条件，单独记录：

- 当前工作树 `git status` = **604 项未提交改动**，最后一次提交停在 2026-10-19（R16–R19.42 全部产物都在工作区里，未入库）。
- 按项目记忆的共享工作区规则（局域网内可能有他人在操作同一工作区，禁止无痕覆盖 / 混入他人改动），**不在这棵脏树上直接修改 `build.ps1` / `package_files.ps1` / `serve.py` / `app.js`**。
- 开工前置条件（按顺序）：①确认这 604 项改动的归属与是否可入库；②在独立分支或独立副本上实施 L0→L1→L2；③每步改动带 `MASTERJJ@HOMONAS` + 时间留痕到本文件。
- 实施顺序沿用 §10.3：`RuntimeFiles` 登记 → 生成 `build_info.json` → `about-meta-line` 显示构建/渠道 → 扩 `BUILD_ASSETS` 与 `/api/build` 的 `integrity` 字段。
- 验收仍按 §6 五条，不改口径。

### 11.5 本轮状态

| 会话 | 状态 |
|---|---|
| 防破解调研 | **从「阻塞于产品决策」转为「决策已落定、等实施前置条件」**；本轮未改任何源码/构建脚本 |
| 机器/时间 | `MASTERJJ@HOMONAS`，2026-11-08 05:50 |

### 11.6 自检轮（2026-11-09 08:05，只读）

- 工作树实测：**622 项未提交**（31 modified + 591 untracked，0 deleted），分支 `main`，最后一次提交仍为 2026-10-19；较本文 §11.4 记录的 604 项增加 18 项，全部来自 R19.42 之后的轮次产物。
- 结论不变：在归属未确认前不在脏树上改 `build.ps1` / `package_files.ps1` / `serve.py` / `app.js`，§11.4 的三步前置条件继续有效。
- 本轮未提交、未 stash、未改任何源码；仅追加本条留痕。机器 / 时间：`MASTERJJ@HOMONAS`，2026-11-09 08:05。

### 11.7 自检轮（2026-11-10 11:05，只读）

- 工作树实测：**717 项未提交**（31 modified + 686 untracked，0 deleted），分支 `main`，最后一次提交仍为 2026-10-19；较 §11.6 的 622 项增加 95 项，全部为 untracked 新增文件（modified 数不变），推测来自 11-10 的行情价 R220/R221 轮次产物。
- 结论不变：归属未确认前不在脏树上改构建脚本与核心源码，§11.4 三步前置条件继续有效。L0/L1/L2 实施继续暂缓，不阻塞其他并行开发线。
- 本轮未提交、未 stash、未改任何源码；仅追加本条留痕。机器 / 时间：`MASTERJJ@HOMONAS`，2026-11-10 11:05。

### 11.8 自检轮（2026-11-10 22:40，只读）

- 工作树实测：**717 项未提交**（31 modified + 686 untracked，0 deleted），分支 `main`，最后一次提交仍为 2026-10-19 18:17；与 §11.7（11:05）逐项一致，本轮无新增。
- 结论不变：归属未确认前不在脏树上改构建脚本与核心源码，§11.4 三步前置条件继续有效。L0/L1/L2 实施继续暂缓。
- 本轮未提交、未 stash、未改任何源码；仅追加本条留痕。机器 / 时间：`MASTERJJ@HOMONAS`，2026-11-10 22:40。
