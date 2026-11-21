# EFT 互动地图 · Agent 交接手册

> 交接时间：2026-10-19 · 版本 `0.1.0` · 数据 schema `8` · 物品资料库 schema `1` · 路网 schema `1` · 测试 `611 passed`

---

## 0. 先读这一节：当前状态

> **本表更新于 2026-11-12 12:40（R248 之后）**，为当前实测状态。
> 下方另有一张 2026-10-19 的历史快照，原文保留供对照，不要当成现状。

| 项 | 当前状态（2026-11-09 实测） |
| --- | --- |
| R278 价格曲线云端化 + 截图宿主进包 + 安装向导改经典分步 | ✅ 用户三问：①朋友新装的客户端只显示「当前没有可用样本，所以这里不画线」——根因是 `/api/price-history` 只读**本机** `%LOCALAPPDATA%\EFTPrice\collect\snapshots`，新机器要自己攒样本；云端其实已有采集机每 30 分钟上传的 1432 份快照。修：云端新增 `GET /v1/prices/series`（会员，itemIds 批量，窗口锚最新快照，`"<id>":` 原文定位取值——189 份 21MB 取 1 个物品 2ms；实测 7d 52ms / 30d 46ms / 5 物品批量 212ms），BFF `/api/price-history` 在会员态并上云端曲线（5 分钟 TTL，4 秒短超时，403/离线/异常一律静默回退本机），同时间戳本机优先、不重复计数；前端空态改说「云端历史是会员数据 / 云端暂时连不上」。②朋友按热键没反应——不是缺环境（onnxruntime/cv2/模型都在包里），是 **scan.py 从来没被打包**，只存在于开发机的登录自启；修：spec/build.ps1 加 `tools/scan.py`+`tools/overlay.py`，`Startup.start_ocr_host()` 在四步完成后用 `EFTMap.exe --run-tool` 拉起宿主、`stop()` 收掉，宿主加命名互斥量（旧自启残留时后来者退出）、冻结态日志落 `%LOCALAPPDATA%\EFTMap\logs`。③安装器改经典四步向导（欢迎→选项→进度→完成），完成页两个勾选：启动互动地图 / 前往爱发电（`AFDIAN_URL`）。版本 **0.2.6**；新增 `tests/test_r278_cloud_history.py` 8 条、`test_r278_scan_host.py` 7 条、`test_r278_ocr_host_spawn.py` 6 条；云端 `tests/test_price_series.py` 7 条。 |
| R278 验证 | ✅ 客户端全量 2370 passed / 5 skipped；云端 111 passed；线上 `/v1/prices/series` 实测 200（临时会员令牌验证后已删）；安装向导四页 + 失败页截图验收（560×430 无截断，完成页只剩「完成」）。 |
| R279 云端价格本地缓存 + 截图识别修复 | ✅ 用户：①价格页仍显示「云端历史是会员数据」——根因是测试账号在云端 `member=false`（本机 `cloud-session.json` 是旧快照），且原设计只在打开详情时现查云端，断网/非会员就空白。改：云端新增 `GET /v1/prices/cache`（会员，整包 / `since` 增量，`{series:{id:[[ts_ms,price],…]}}`，实测整包 6.6s / 193 份 / 3571 物品 / 685,475 点 / 16.5 MB JSON，增量 0.1s）+ 客户端 `tools/price_cache.py`（`%APPDATA%\EFTMap\cloud-cache\<mode>.json`，单物品 `"<id>":[` 原文定位 4–28ms）+ BFF `/api/price-cache/{status,sync}`，`/api/price-history` 先读缓存（`cloud.status="cache"`）再回落实时接口；登录/会员态变化自动整包下载，点「获取最新数据」只拉增量，会员过期/退出登录/云端 403 一律 `purge()`。②截图识别「框完没反应」——根因是冻结态 `ocr.py` 在 `_internal\ocr.py`，`PROJECT_ROOT` 算成产物根 → `OCR_ASSETS_DIR` 指不到 `_internal\assets\ocr`，`/api/ocr/recognize` 一律 503；同批第二个坑 `data/ocr-item-names.json` 从未进打包清单。修：`ocr.resolve_assets_dir()` 四级探测 + 清单补短名表/三个模型 + 失败提示 2.5s→6s + 宿主启动失败弹置顶提示（含日志路径）+ `find_browser()` 补 LOCALAPPDATA/PATH。版本 **0.2.7**；新增 `tests/test_r279_price_cache.py` 10 条、`test_r279_ocr_assets.py` 5 条、云端 `tests/test_price_cache.py` 6 条；文档 `docs/r279-cloud-cache-and-ocr-env.md`。 |
| 源码可运行 | ✅ `python tools/launcher.py` 或 `python tools/serve.py`；`tools/serve.py:54` 默认端口 **8787**（历史开发运行端口 8810，口径待统一） |
| 版本 | ✅ `tools/serve.py:51` = **0.2.5**；`release/` 三件套已同步重出为 **0.2.5**（15:44–15:50），源码与发布包版本一致 |
| 测试 | ✅ `python -m pytest tests -q --tb=no` → **1915 passed, 1 skipped, 0 failed**（138.62 s，2026-11-09 14:27）；打包后 15:56 回归由 JUnit 报告确认 **1916 tests / 0 failures / 0 errors / 1 skipped**（145.47 s）。⚠️ 当次进程退出码为 1、且日志未打印 pytest 末行 summary：末段是 SSE 测试的 socketserver 线程 traceback 与批量删除守卫（`SAFE_DELETE_BULK_CONFIRM_REQUIRED`，拦截 `D:\Temp\2\pytest-of-MASTERJJ\garbage-*` 清理），为环境收尾噪音，日志内无 `FAILED` 用例、JUnit 无 failure/error 节点；勿据此把回归判为失败，详见 §0.1 第 1 条。R211 后 `1920 tests / 0 failures / 0 errors / 1 skipped`（142.08 s）；R212 后 **1926 tests / 0 failures / 0 errors / 1 skipped**（137.37 s，`build/_pytest_r212_final.xml`）；R213 后 **1932 tests / 0 failures / 0 errors / 1 skipped**（140.86 s，`build/_pytest_r213.xml`）；R214 后 **1936 tests / 0 failures / 0 errors / 1 skipped**（138.07 s，`build/_pytest_r214_final.xml`）；R215 后 **1939 tests / 0 failures / 0 errors / 1 skipped**（161.02 s，`build/_pytest_r215.xml`）；R216/R217 后 **1955 tests / 0 failures / 0 errors / 1 skipped**（128.35 s，`build/_pytest_r217.xml`，退出码 1 为收尾噪音）；R218 后 **1967 tests / 0 failures / 0 errors / 1 skipped**（144.87 s，`build/_pytest_r218b.xml`，**退出码 0**）；R219 后 **1974 tests / 0 failures / 0 errors / 1 skipped**（143.30 s，`build/_pytest_r219b.xml`，**退出码 0**）；R220 后 **1980 tests / 0 failures / 0 errors / 1 skipped**（119.10 s，`build/_pytest_r220.xml`，**退出码 0**）；R221 后 **1988 tests / 0 failures / 0 errors / 1 skipped**（119.84 s，`build/_pytest_r221b.xml`，**退出码 0**）；R222 后 **2000 tests / 0 failures / 0 errors / 1 skipped**（128.14 s，`build/_pytest_r222.xml`，**退出码 0**）；R223 后 **2006 tests / 0 failures / 0 errors / 1 skipped**（130.47 s，`build/_pytest_r223.xml`，**退出码 0**）；R224 后 **2012 tests / 0 failures / 0 errors / 1 skipped**（132.67 s，`build/_pytest_r224b.xml`，**退出码 0**）；R225 后 **2013 tests / 0 failures / 0 errors / 1 skipped**（143.38 s，`build/_pytest_r225.xml`，**退出码 0**）；R226 后 **2018 tests / 0 failures / 0 errors / 1 skipped**（128.23 s，`build/_pytest_r226.xml`，**退出码 0**）；R227 后 **2024 tests / 0 failures / 0 errors / 1 skipped**（131.95 s，`build/_pytest_r227.xml`，**退出码 0**）；R228 后 **2023 passed / 1 skipped**（合计 2024，145.12 s，`build/_pytest_r228.xml`，**退出码 0**）；R229 后 **2030 passed / 1 skipped**（合计 2031，140.97 s，`build/_pytest_r229.xml`，**退出码 0**）；R230 后 **2031 passed / 1 skipped**（合计 2032，138.95 s，`build/_pytest_r230.xml`，**退出码 0**）；R231 后 **2036 passed / 1 skipped**（合计 2037，138.56 s，`build/_pytest_r231.xml`，**退出码 0**）；R232 后 **2038 passed / 1 skipped**（合计 2039，138.81 s，`build/_pytest_r232.xml`，**退出码 0**）；R233 后 **2047 passed / 1 skipped**（合计 2048，171.43 s，`build/_pytest_r233.xml`，**退出码 0**）；R234 后 **2072 passed / 0 failures / 0 errors / 3 skipped**（141.51 s，`build/_pytest_r234.xml`，**退出码 0**；3 skipped = R234 两个引擎级用例在无 OCR 依赖的测试 Python 上跳过 + 1 个既有 skip）；R236 后 **2076 passed / 0 failures / 0 errors / 4 skipped**（135.10 s，`build/_pytest_r236.xml`，**退出码 0**；4 skipped = R234/R236 共 3 个引擎级用例在无 OCR 依赖的测试 Python 上跳过 + 1 个既有 skip）；R237 后 **2080 passed / 0 failures / 0 errors / 4 skipped**（134.0 s，`build/_pytest_r237.xml`，**退出码 0**）；R239 后 **2093 passed / 0 failures / 0 errors / 4 skipped**（136.45 s，`build/_pytest_r239.xml`，**退出码 0**）；R240 后 **2100 passed / 0 failures / 0 errors / 4 skipped**（147.89 s，`build/_pytest_r240.xml`，**退出码 0**）；R241 后 **2110 passed / 0 failures / 0 errors / 4 skipped**（164.14 s，`build/_pytest_r241.xml`，**退出码 0**；R32 CSS 作用域护栏要求新面板样式挂在 R32 段之前）；R242 后 **2119 passed / 0 failures / 0 errors / 4 skipped**（141.86 s，`build/_pytest_r242.xml`，**退出码 0**）；R243 后 **2123 passed / 0 failures / 0 errors / 4 skipped**（134.20 s，`build/_pytest_r243.xml`，**退出码 0**）；R244 后 **2128 passed / 0 failures / 0 errors / 4 skipped**（143.24 s，`build/_pytest_r244.xml`，**退出码 0**）；R245 后 **2134 passed / 0 failures / 0 errors / 4 skipped**（166.48 s，`build/_pytest_r245.xml`，**退出码 0**）；R246 后 **2134 passed / 0 failures / 0 errors / 4 skipped**（167.89 s，`build/_pytest_r246.xml`，**退出码 0**）；R247 后 **2139 passed / 0 failures / 0 errors / 5 skipped**（154.11 s，`build/_pytest_r247.xml`，**退出码 0**）；R248 后 **2143 passed / 0 failures / 0 errors / 5 skipped**（150.27 s，`build/_pytest_r248.xml`，**退出码 0**） |
| R236 整图分块识别（修「只能识别出几个物体」） | ✅ 用户实测整图只认出几个 → 根因：单次 det 960 把 1080p 压半、14px 游戏字变 7px 检测失明；XiaoMeow 的 RecognizeChunked（256px 块+每块 ≤1.6× 放大）R234 未复刻。MCP 复核 DLL 确认参数后补齐：`_recognize_tiled`（**块 640/步进 320**，窗口每 step 平移，文本宽 L≤W−S 才保证完整入块——256/重叠64px 只保 64px 不够；1080p 24 块 ≈6s）+ 跨块去重 `_dedup_lines`（同文去空格子串/相似>0.75 且 中心距<24px **或 IoU>0.3**——部分框 vs 完整框中心差几十像素）、匹配器两修：token 候选窗口对 len(tok)与len(tok去空格)各开一档+ratio 双形态取高（修 MP-133 错配 MP-153）、≤6 字符 token 用 0.72（修 HUD 'Esape' 擦线配 'eagle'）。**期间单位坑**：TilePlan overlap 是比例，写成 64px → step=1 → 137 万块 7 分钟超时。效果：1920×1080 合成图 12/12 命中、6.4s、零误报（R234 旧行为 11/12 且真实截图更差）。验收 `tests/test_r236_ocr_tiling.py` 7 条 + `r234_accept.py` 两阶段 **35/35**（大图 13/31 行 · OCR 6450ms，8 个指定物品全中）。文档 `docs/r236-ocr-tiling.md` |
| R237 真实截图调优：OCR 短名表 + 碎片守卫 | ✅ 用户提供真实游戏截图（3524×1738 角色装备界面，中文短名显示）。**根因**：游戏显示短名（ComTac VI/OTV/T30/布洛芬…），items.json 的 sn 上游全为 "<id> ShortName" 占位符（EN items 数据被污染；**items_zh 翻译表的 ShortName 才是真的**）。新增 `tools/build_ocr_names.py`（复用 fetch_data 抓取器）→ `data/ocr-item-names.json` 5480 条 id→中文短名；`serve.py` 短名并入匹配索引与 name_to_ids 反查。守卫三连：token/整串层「无 CJK 且 <3 字符碎片」跳过（'un'→RUN 海报、'EC'→EMERCOM、'S1'→SJ1 全消）、token 数字段 ANY 守卫（'mk17' 不错配 Mk47 拉机柄、O/0 误读 GL0CK17 仍可配 Glock 17）。试过 0.70 整串阈值想杀 EXPIE 误配——正确乱串 0.667-0.696 与坏乱串 0.67 同分数带、ratio 不可分 → 回退 0.60 残余 2 误报如实标注。**效果线**：27 匹配/~12 真命中 → **53 匹配/~48 真命中**（19.5s，标注图 build/_ocr_game_annotated3.png：A-2607/CF/LBCR/EXFIL/OTV/SpecterDR/Mk 17 整枪/STANAG×3/M856A1/M67/AFAK/AI-2×2/Esmarch/狗牌包/臂带/绷带/夹板×2/止血剂/止痛药/洛芬/针叶林-1/T30/绒布/绳索/洗发水/45+背包/NICE/玩偶/9x19/9x39 全中）。文档 `docs/r237-ocr-real-screenshot.md` |
| R238 QQ 式截图识别工作流 | ✅ 用户「按设置的快捷键→框选→识别→结果以浮窗显示在框选位置：整体/每格/每公斤价，右上角关闭+口径切换（最新/24h/72h/30天）」。新增 `tools/scan.py`（RegisterHotKey 常驻宿主，默认 **Ctrl+Alt+P**，配置 ocrScan.hotkey 可改；ImageGrab 冻结帧→POST /api/ocr/frame→全屏置顶浏览器窗口，复用 overlay.py 的 find_browser/style_overlay/fit_client）；`scan.html`（冻结帧 1:1、QQ 式遮罩/十字线/尺寸提示、前端 X/Y 各自比例裁剪、**原位浮窗**三列价格+口径循环按钮+✕，关闭=window.close+标题「EFT截图·关闭」双保险）；serve.py 加 `/api/ocr/frame` POST/GET（48MB 上限/单帧覆盖/TTL600s/错 id 404）+ recognize 增 **w72/w30d**（price_history.series days=3/30 本地快照均值、不插值）+ weight。计划任务 `EFTMap-Scan-AutoStart` 登录自启。验收 `tools/r238_accept.py` **14/14**（帧往返/404/autotest 框选→浮窗 3 行三列价/口径循环/关闭标题/无 JS 异常）+ `tests/test_r238_scan.py` 8 条。文档 `docs/r238-scan-workflow.md` |
| R239 透明价格浮窗（小地图式，修 R238 方向偏差） | ✅ 用户纠偏：「浮窗要和小地图一样不影响游戏操作、透明背景只显示价格文字、价格直接显示在对应装备上」。R238 的浏览器交互面板重做为**原生 Win32 分层窗口**（不走浏览器）：标签窗 UpdateLayeredWindow 逐像素透明（背景 alpha=0）+ WS_EX_TRANSPARENT 全窗点击穿透 + WM_NCHITTEST 双保险 + WS_EX_NOACTIVATE 不抢焦点；价格**与装备名同行右移**（单行「主价 · 格X · kgY」，字号随 OCR 行框 0.92×bh，右溢出左移）——排版三轮迭代（直叠→上方→同行）定稿；控制条独立小窗仅 [口径][✕] 按钮可点（按钮外 HTTRANSPARENT），口径 最新→24h→72h→30天 宿主本地重绘不经 BFF。链路：scan.html 交接 POST /api/ocr/overlay/state（白名单瘦身/200条上限）+ 标题「EFT截图·完成」→ 宿主 GET 后关选择窗开浮窗；scan.html #panel 移除。**实现坑**：wintypes 无 WNDCLASSW（自定义 Structure）；GetModuleHandleW/CreateWindowExW 等 64 位 argtypes 不设 → HMODULE 截断 RegisterClassW 静默失败；主循环必须 DispatchMessageW（R238 只 Peek）。`--demo-overlay` 演示：假游戏底图+浮窗截屏取证 build/_r239_overlay_demo.png（价格贴名、背景全透、无伪影）。验收 `tools/r239_accept.py` **15/15**（EXSTYLE 断言：标签窗 0x80800A8 全穿透 / 控制条 0x8080088 可点）+ `tests/test_r239_overlay.py` 11 条 + R238 页面契约更新。文档 `docs/r239-transparent-overlay.md` |
| R240 QQ 式速度：保温窗口 + BMP 冻结帧 | ✅ 用户反馈「按截图键没有 qq 截图快，而且窗口什么都会动一下」。三根因全修：①**窗口保温**——识别完成/取消宿主 `hide_selection`（SW_HIDE）不销毁浏览器，热键帧先上传再 `show_selection` 唤醒（页面 visibilitychange 立即拉帧），热键框选中再按=直接换帧重选，隐藏前记前台窗口、隐藏后 restore_focus 还焦点给游戏；②**页面轮询换帧**——scan.html 可见 150ms/隐藏 800ms 轮询 `GET /api/ocr/frame` 元信息（新端点语义），发现新 id 走 startNewScan（暗色待机→拉帧），`?frame=` 仍兼容，页面绝不自行关窗（window.close 移除）、交接后 resetIdle；③**冻结帧改 BMP**（免压缩，编码≈内存拷贝），BFF 按魔数嗅探 image/bmp/image/png；④**冷启动防闪动**——窗口 `-32000` 屏幕外创建，剥样式/等页/fit_client(top-left) 全部屏外完成再一次性入场；⑤**防竞态**——BFF 交接态加 ts，宿主只消费 `ts ≥ shown_at-0.5` 的完成信号（重开窗口瞬间可能残留上一轮完成标题）。效果：保温路径热键→可框选 ≈0.4s（原 1.5-4s），页面首帧就绪 287ms、同页换帧 253ms，`__scanTestWarm` 标记证明两轮框选**无 reload**。验收 `tools/r240_accept.py` **12/12** + `tests/test_r240_warm_scan.py` 7 条（_OCR_FRAME/_OCR_OVERLAY 全局态跨文件测试需复位）；R238/R239 契约全保留。文档 `docs/r240-fast-scan.md` |
| R241 价格标签档位样式 + 价格识别设置面板 | ✅ 用户：「价格显示在装备名蓝框位置、只显示每件价+每格价不要 kg、字号和游戏内文字一样大（各分辨率不同→可能要解包）……菜单栏小地图按钮右侧加价格识别按钮，免费用户只能设置截图键，会员按价格档位自定义字号/字体/颜色/内外描边/区间」。①版式：价格**锚定 OCR 行框（装备名）左上角**两行堆叠（每件价 + 0.78×每格价），kg 移除；②字号 = OCR 实测游戏文字像素高 × 档位倍率（[0.5,3]）——**不解包**：解出的是静态值，实测高度才随玩家分辨率/UI 缩放自适应；③档位样式（默认 4 档 <5万灰/5-30万白/30-100万绿/≥100万金）：max/color/sizeScale/font(msyh,msyhbd,simhei,simsun)/outer+outerColor/inner+innerColor，config.py 归一化（hex 校验、字符串数字、≤6 档、按 max 升序无上限殿后），描边三层叠加（外圈→内环→字芯）；分档依据=当前口径每件价，价格未知落首档；④菜单栏「价格识别」面板（am-ocr）：热键所有人可改 + 档位行编辑器（会员），queuePrefs({ocrScan}) → /api/prefs；**服务端兜底**：config.merge_ui 非会员丢弃 labelStyle（绕 UI 锁无效）；⑤**热键热更新**：宿主 1s 轮询 ocrScan.hotkey，变更即 Unregister/Register（日志确认，off 可关闭）。R241.1 附带：宿主日志落盘 build/scan-host.log（pythonw 唯一可诊断出口）+ done_stale 防残留完成信号刷屏。验收 `tools/r241_accept.py` **9/9**（面板/档位/热键 f8 配置回声→宿主热切换→还原）+ `tests/test_r241_ocr_settings.py` 10 条 + 演示截图（三档三色叠装备名）。文档 `docs/r241-label-tiers.md` |
| R242 识别净化：栏位标题黑名单 / 物品排除 / 同位去重 | ✅ 用户：「位置不对……识别到装备以外的字如栏位标题『耳机』『头部装备』，臂带和狗牌也不要识别；『格』是什么——是单格吗」。MCP 复核 PriceScanner：小喵 = 光标周围小 ROI（CursorCenteredRegion→ScanAtAsync→Annotate 写 last_ocr_result.png），标题进不了画面；我们扫整页 → 三层净化：①**SECTION_HEADERS** 23 词整行（含去空格）+ token 层拦截（resolve_key 任何层之前；只拦整行不影响『VKBO军用背包』类全名）；②**ITEM_NAME_EXCLUDES**（臂带/臂章/狗牌/dogtag/armband）serve 级按物品名排除；③**计数形态守卫** `21/21` 归一化前查原始文本（斜杠不在 NORM_RE 白名单，归一化后 '0 30'→'030' 绕过——首版漏网实测）+ 整串层纯数字探针拒绝；④**dedup_ocr_matches** 同位去重（阈值 3×字号高）：同 id 近距=同物品多片段留优（肾上腺素×2）、不同 id 近距=按档位层级+分数留优（EXFIL vs EXPIE、LBCR vs SDSK 老误报顺带清除）、远距同 id 保留（两块夹板）；⑤标签第二行「格」→「**单格**」。效果（用户真实截图复验）：53→38 匹配、点名违规残留零。测试 `tests/test_r242_ocr_filters.py` 9 条；R241 merge_ui 测试改 tmp_path（原读真实配置——用户已在面板改过档位，面板真实可用的旁证）。文档 `docs/r242-ocr-filters.md` |
| R243 统一字号 + 精确卢布 | ✅ 用户：「字体必须固定大小（现在大小不一）、单位不要万要精确到个位的卢布、钱向左对齐，你是不是看不到每个物品的方框」。①**字号统一**：label_base_font = 全部识别行框高**中位数**（钳 9-300）一次算定，所有标签同基准（仍是该玩家屏幕游戏文字真实大小，分辨率自适应）；②`fmt_short` 改精确卢布「431,400 ₽」（千分位+个位+₽，万/亿废除）——**字体坑**：雅黑/黑体/宋体均无 U+20BD，PIL 无回退渲染成豆腐框（实测 4 字体 TOFU/Segoe UI OK）→ `_split_ruble` 拆出 ₽ 用 Segoe UI Bold 画，其余用档位字体，描边同套；③左对齐 = 标签左沿钉装备名行框左沿；④**附带修真 bug**：同位置去重垂直阈值 3h 太松（相邻行距≈3h，演示 3 件被并成 2 件）→ 水平 3h / 垂直 **1.2h**。验收 `test_r243_fixed_font.py` 4 条 + 取证截图（三处同字号/₽ 正常/左对齐/两行）；R239/R240/R241 万断言同步更新。文档 `docs/r243-fixed-font-ruble.md` |
| R244 价格标签三行版式（修压名字） | ✅ 用户：「现在价格会和装备名称重叠 应该是再第一行是空格 第二行是单个物品的价格 第三行是耽搁(单格)价格」。`render_labels` 改为**第 1 行整行留空**（= 装备名自身那一行，价格从名字下沿 `ay+max(bh,fs)+gap` 起笔）、第 2 行整体价、第 3 行单格价；行距按**真实墨迹**算 `step=max(fs+2,1.32*fs)`（中文字形比 em 框向下多 ~0.3×字号，实测 30px 字墨迹 33px，原 `fs+gap` 两行粘连）；画布向下多留 `extra_bottom≈2.6×字号`（不超屏幕），框选区贴屏幕下沿时价格仍画在名字下方。真实截图（3524×1738，38 匹配）暴露并修两处碰撞：①密集行距（行距<三行块高）→ 退化为名字右侧单行 `主价 · 单格 …`，右侧夹到同排邻格左沿；②口袋格 ~100px 宽、22px 的「120,000 ₽」宽 112px → 按可用空间**等比收缩**（下限 0.6×，仅该格放不下时触发，宽格子仍统一字号）；③同排邻格 dy≈1px 曾被误判为「下一行阻挡」（洛芬/止血剂）→ 改为 `ny >= ay+max(bh,base_fs)` 才算下一行。验收 `tests/test_r244_label_lines.py` 5 条（第 1 行零墨迹/两段墨迹/extra_bottom/下沿兜底/密集退化），R241+R243 版式断言同步；取证 docs/r244/（合成演示 + 真实截图左栏/口袋放大）。文档 `docs/r244-label-lines.md` |
| R245 修唤醒白屏（点一下才正常） | ✅ 用户：「按截图快捷键后会白屏 得鼠标左键单击一下之后才能正常截图」。三个叠加根因：①**Edge 单实例**——同 `--user-data-dir` 的新启动只会塞进 18:24 的旧进程，R245 的关遮挡/关节流参数从未生效，旧进程还攒了 5 个隐藏窗口，隐藏时被 Windows 判 occluded → 合成挂起 → 白卡直到有鼠标事件；②选择窗沿用 `overlay.style_overlay` 的 **WS_EX_NOACTIVATE**，永不成为前台（实测 fg=False），既收不到 Esc，Chromium 也视其未激活不出首帧；③唤醒瞬间读到上一轮残留的「关闭/完成」标题，宿主立刻把刚显示的窗口隐藏（闪白）。修：`kill_scan_browser()` 只按命令行含扫描 profile 过滤清进程（**不按映像名扫射**，曾误杀 BFF），启动+冷启动前各清一次；浏览器加 `--disable-backgrounding-occluded-windows` / `--disable-renderer-backgrounding` / `--disable-background-timer-throttling` / 关 `CalculateNativeWinOcclusion`；剥样式后去掉 `WS_EX_NOACTIVATE`，入场/唤醒都 `BringWindowToTop`+`SetForegroundWindow`；`show_selection` 加 `RedrawWindow(RDW_UPDATENOW|ALLCHILDREN)`+`DwmFlush`；`hide_selection` 隐藏前复位标题；「关闭」信号改连续两次轮询才收窗（closed_stale）；页面 visibilitychange 强制一次合成提交（opacity 微变 + rAF）。实测（逐帧抓屏）：冷启动与唤醒 +90/210/460ms 纯白占比 **0.00%**（修复前 87.8%~100%）、窗口 fg=True、Esc 正常收窗、唤醒到出画面 ≈250ms（含抓屏+BMP 上传）。验收 `tests/test_r245_scan_wake.py` 6 条（启动参数/强制重绘/标题复位/两次轮询/profile 过滤/页面合成提交）。已知项：Chromium `--app` 客户区顶部保留 ~31px 自绘标题栏（`--start-fullscreen`/`--kiosk` 实测相同），选区坐标按实际显示比例换算仍准确，彻底去除需打包期改 WebView2 宿主。文档 `docs/r245-wake-blank-fix.md` |
| R246 修「热键先弹 PowerShell」 | ✅ 用户：「截图键按下后会弹出 powershell 而后才是截图」。根因：R245 用 `powershell -NoProfile -Command Get-CimInstance…Stop-Process` 清理旧浏览器，宿主是 pythonw（无控制台）→ Windows 给控制台子进程新建窗口（黑框），且 PowerShell 自身启动 ~1s，登录自启时同样弹一次。修：`kill_scan_browser()` 换成 `kill_stale_scan_browsers()`——**纯 ctypes 零子进程**：`overlay._enum_windows()` 按标题 `EFT 截图识别`/`EFT截图·完成`/`EFT截图·关闭` 取 PID + 读 `build/scan-browser.pid`（冷启动时写入），`QueryFullProcessImageNameW` 校验可执行名必须是 msedge/chrome（防 PID 复用误杀）→ `OpenProcess(PROCESS_TERMINATE)`+`TerminateProcess` → 删 pid 文件；实测无进程时 **57ms**、启动清理同秒完成（旧实现 1~2s）。测试 `test_kill_stale_scan_browsers_is_ctypes_only` 固化「清理代码体内不得出现 powershell/subprocess/taskkill」。文档 `docs/r246-no-powershell-popup.md` |
| R247 ShareX 式原生选区（按键反应 38ms） | ✅ 用户：「按截图键反应非常慢，ShareX 很丝滑，能否直接拿来用」。MCP 取证 ShareX `RegionCaptureTransparentWindow`（透明命中层只画选区、不画冻结帧、**关窗后才抓屏**、alpha=1 保持可点）、`RegionCaptureIntegration.WarmUp()`（窗口预热）、`Screenshot.CaptureRectangle(rect)`（按矩形抓）。结论：**不能整项目拿**（GPLv3 / C#+Avalonia+SkiaSharp / 无 OCR 价格逻辑），但做法 1:1 复刻到项目已有的原生分层窗引擎，**未复制其代码**。新增 `NativeSelection`（role 3=全屏命中层 `LWA_ALPHA=1`+十字光标+Esc/右键，role 4=选区边框小位图白实线+黑虚线+尺寸，role 5=预热的顶部提示条）、`watch_native()`（热键→ShowWindow 19ms；预热 ULW 130ms 放启动）、`recognize_region()`（关窗→DwmFlush→只抓选区→直接 POST `/api/ocr/recognize`→本地开透明价格浮窗）；`--legacy-select` 回退旧 Edge 链路（frame/overlay-state 端点保留）。**旧链路慢因**：整屏 BMP 6MB + 两次 HTTP + 唤醒/冷启动 Edge(2~3s) + 页面 150ms 轮询 + 浏览器合成。实测热键→选区窗可见 **38ms**（旧 300ms~3s）、预热后 show 7~21ms、每次热键 0 字节抓屏、0 个新进程；端到端拖拽→OCR 2 件→浮窗。行为变化：改为 **ShareX 透明实时选区**（屏幕不再暗化冻结），需要 QQ 式冻结帧可加 `ocrScan.freezeFrame`（约 +90ms）。测试 `tests/test_r247_native_select.py` 6 条；取证 docs/r247/01-native-select.png；文档 `docs/r247-sharex-native-select.md` |
| R248 修「改 ShareX 后 OCR 结果不出现 / 39 秒」 | ✅ 用户：「截图很流畅但是不会出现 ocr 的结果」「我是用游戏内的截图试的，昨天五六秒，现在改 sharex 反而不行」。**与 ShareX 改造无关**：分段计时 BFF `tookMs` 仅 0.5~4s、HTTP 墙钟 19~24s → 定位 `price_history.series()` 的 collector 分支对每个 `(gz 快照, 物品 id)` 调一次 `_gz_rows()`，每次全文 `gzip.open().read()`：60 物品 × 142 快照 ≈ 8500 次解压 ≈ **24s**（缓存 key 含 item_id 完全无效）；昨天 21 件≈5s、今天 81 件≈39s 即成本随匹配数线性爆炸。修：①`_gz_rows_batch()` 一次解压批量取行 + `(path,mtime,size)` 文本缓存（24 份上限）→ `series(60 ids,30d)` **14.07s→0.41s**；②`serve.py` 把 days=3/30 两次 `series` 合并为一次 `days=30` + 按 points 时间戳本地切 72h（解压再减半）；③`watch_native` 识别放后台线程 + 松手立刻显示「识别中… W×H」提示（复用预热 role5 小窗）+ `recognizing` 防重入（原来用户等不及按热键会 `sess.close()` 误关刚出现的浮窗，日志 12:11:03 同秒印证）。**效果**：1423×836 HTTP 23.89s→**5.69s**、977×598 19.23s→**3.23s**、松手→结果实测 3.0s；热键→选区 37ms 不变。验收 `tests/test_r248_batch_history.py` 4 条（含 monkeypatch 计数 gzip.open 证明 N 物品只解压一次）、`test_r238_scan.py` 多窗口价格契约更新；端到端提示条 150ms 内可见、假 matches 验证浮窗两行价格+控制条正常；取证 docs/r248/。文档 `docs/r248-batch-history.md` |
| R234 截图识别价格（OCR · A 路线完整复现） | ✅ 用户拍板 A（完整复现 ONNX）+「价格用市场界面里的数据」。`assets/ocr/` 新增 PaddleOCR det.onnx/rec.onnx/ppocr_keys_v1.txt（哈希与逆向参考逐一核对）；`tools/ocr.py` 全管线（det 960/32 对齐 → DB 0.30/0.60/1.5/3 → SortBoxes → CropRotate → rec 48×320 batch8 → CTC + 字典 6625 类 → ItemMatcher 四级匹配），重依赖懒加载、无依赖可单测；`serve.py` `POST /api/ocr/recognize`（24MB 上限、引擎缺失 503）+ health.ocr；市场视图「截图识别」面板（文件/拖拽/Ctrl+V/画布框选 ROI，价格走 `GWMarketData.quote` 市场同源）。**调试抓出四个真 bug**：_unclip 交点符号错（det 框截断→rec 全错，修复后 3/3 物品名 0.98+）、rec 通道序 BGR、徽章半径用错框尺寸、纯数字价格标签误配（⑨ 守卫）。匹配器本地化：索引 items.json 真名+复刻 shortNameOf，新增整串模糊兜底（两侧去空格、数字段守卫、real_quick_ratio 剪枝）。依赖：服务端 Python 装 onnxruntime 1.31.1/opencv-headless/numpy（用户拍板破零依赖）；bundled Python 无包 → 引擎用例自动 skip。HTTP 端到端 3/3 匹配+云端价格+战局图零误报；浏览器 `tools/r234_accept.py` **17/17**（截图 docs/r234/）；识别 0.3-0.4s/图。测试 `tests/test_r234_ocr.py` 24 条；R97 fetch 护栏升级为「恰好 2 个本机相对 api/ 请求」。边界：截图库无仓库界面实拍样本（待用户实测）；未做分块识别与浮层宿主；模型 Apache-2.0 打包时需标注。文档 `docs/r234-ocr-price.md` |
| 数据 | ✅ 13 张图 / schema 8；`data/items.json`、`data/flea-prices*.json`（3 份，15:32 按采集器最新数据重生成）、`data/roadnet.json` 均在；四个契约文件 `items.json` / `gunslots.json` / `gun-presets.json` / `ammo.json` 未改 |
| 发布包 | ✅ `release/` 下 0.2.5 三件套：`EFTMap-Portable-0.2.5.zip`（118.3 MB / 124,027,855 B，SHA256 `202f896f…563`）、`EFTMap-AppWindow-0.2.5.zip`（118.3 MB / 124,027,994 B，`874894ba…49d`）、`EFTMap-Setup-0.2.5.exe`（128.8 MB / 135,050,066 B，`1f8fc316…9dd`）。PE 子系统均为 GUI(2)，两个 zip 均含客户端壳；产物内 `app.js` 与 `data/flea-prices.json` 的 SHA256 与源码逐字节一致。**0.2.4 旧三件套已备份在 `build/_prev_release_0.2.4/`**（因发布脚本会清空 `release/`），见 §0.1 第 7 条。⚠️ **R211–R221 的改动（16:30 起）按用户要求暂不打包**：`release/` 与 `dist/` 仍是 15:44–15:50 的产物，不含这十一轮改动，看效果请用 8787 源码服务（`dist/EFTPriceCollector/` 是采集器，已按 R221 重建，不属发布包） |
| 配置位置 | ✅ 用户级目录 `%APPDATA%\EFTMap\`（不随重打包丢失），见 §6.7 |
| Git | ⚠️ 分支 `main`，最近提交 `bf438df`；**677 项未提交**（31 个已跟踪文件修改 + 646 个未跟踪文件），符合「不 commit / push」约束；详见 §9（历史）与 §0.1 |
| R31 / R32 功能 | ✅ 防护区域图例、关于菜单、任务时间语义、自动截图（F10 实机 5/5 到货）、战局门条件、小浮窗 mini 模式与设置面板、离线判据、日志阶段修复均仍在代码中 |
| R211 / R212 界面 | ✅ R211：地图下拉右缘与左侧图层栏齐平（`--eft-sidebar-w`）、底图说明移除；R212：右侧任务栏去掉「任务 / 剧情目标」标题与四档筛选 / 总闸 / 名字开关，改为「普通任务 / 剧情任务」×「已完成 / 未完成」四个标点图层勾选 + 独立「可并行推进」（默认关）；左侧 `LAYER_SPEC` 的 `quests` 组不再渲染但保留供绘制 / 配置使用，勾选通过 `syncTaskLayerMaster()` 回写 `state.layers.tasks/stories`，列表与地图共用 `taskListPass()`。测试 `tests/test_r211_map_select_width.py`、`tests/test_r212_task_layer_toggles.py` |
| R213 界面 | ✅ 点选图标不再画外接圆圈（`.emk-ring` 撤除），改为沿图标 alpha 轮廓的 3px 硬描边，从内到外 1px 灰 / 1px 白 / 1px 黑：`#emk-select-outline` 用 `feComponentTransfer` 二值化 alpha + 三层 `feMorphology` 膨胀相减 + `feFlood` 上色，半径按 `getScreenCTM` 换算成屏幕像素，3.4s 自删。右侧任务 / 物资刷新点**共用一个搜索框**（`el.search === el.taskSearch`，`syncSharedSearch()` 统一写入）。收起键恢复 30×30 正方形、标题带 34px（R212 曾压成 32×20 导致变扁）。测试 `tests/test_r213_outline_search_collapse.py` |
| R214 大小调节 | ✅ 真实页面 CDP 实测：常规任务标 / 剧情标**本来就已**随「图标」滑条线性缩放（50%→8.8px、100%→17.6px、190%→33.44px），本轮锁住该行为未改坏。补齐两处确实漏掉的：① `renderTaskPin()` 的「任务目标钉点」改用 `translate + scale(inv)` 并登记 `markerScaleNodes`，半径补 `ICON_SIZE_ANCHOR` 保持原观感；② 任务 / 剧情名字标签与钉点名字登记进 `labelNodes`，字号 / 描边跟「地名」大小滑条（实测 50%→6.92、190%→26.31，与地名同比例），用 `alpha:false` 隔离地名透明度，任务名字不会被压淡。`renderOverlay()` 无条件清空 `labelNodes`（地名图层关闭时不再留陈旧节点），`tasks.css` 去掉 `.task-pin-label` 的 `font` 简写与固定 `stroke-width` 以免覆盖 SVG 属性。测试 `tests/test_r214_icon_scale_task_markers.py` |
| R215 右侧收口 | ✅ 右侧面板底部遗留的「物资刷新点」独立区块（`<section class="block task-panel-search">` + `<h2>` + 上边框 + 独立滚动）已整块撤除；`#pinned-list`（钉选列表）与 `#search-results`（物资搜索结果）两个功能容器保留、直接作为 `#task-panel` 子元素接在任务列表后，仍由顶部唯一的共用搜索栏驱动，默认 `hidden` 不占高度。`style.css` 删掉 `.task-panel-search` 规则，两个容器补 `flex: 0 0 auto` 与左右 8px 对齐。测试 `tests/test_r215_remove_spawn_frame.py` |
| R216 子栏皮肤 | ✅ 症状：任务界面默认「任务书」，四个子栏按钮是 XP 风格，**点到别的 UI 就变掉**。根因不是样式缺失：旧 `renderList()` 给 `.tk-shell` 加 `db4` 类且从不摘除，`tasks.css` 里 `.tk-shell.db4 .tk-tab` 的覆盖把 XP 位图（`btn-normal.png` / `btn-pressed.png`）换成了渐变。修复：整壳不再常驻 `db4`，改由 `setView()` 按子页 `classList.toggle("db4", state.view === "list")`；删除 `.tk-shell.db4 .tk-tab` / `.tk-mode` 覆盖块。CDP 实测 list / story / progress 三态下页签 `border-image-source` 均为 `btn-normal.png`（选中项 `btn-pressed.png`）、高 24px，切子页不再变样。测试 `tests/test_r216_task_tab_skin.py`；`test_r41_tasks_ui` 的旧断言「给整壳加 db4」同步迁移为「按子页开关」 |
| R217 说明集中 | ✅ 三处说明搬到顶部菜单「关于」，原位置不再重复：① 任务详情底部的「赛季服说明」；② 我的进度底部的「进度只保存在本机浏览器（localStorage）…」；③ 剧情页底部的「数据来源：eftarkov 剧情页」（`https://www.eftarkov.com/storyline`，已实测 200）。关于面板新增 `.about-notes` 三行（赛季服 / 进度 / 剧情），长句完整换行、不做省略号截断；赛季周期由 `syncAboutSeasonNote()` 从 `data/tasks/season.json` 填，**不写死日期**，元信息缺失时退回「暂缺」。CDP 实测：三行 `white-space: normal`、`scrollWidth == clientWidth`、赛季说明 3 行 / 进度说明 2 行；任务详情无 `.tk-detail-foot`、进度页无 localStorage 文案、剧情页无来源链接，其余内容正常渲染，控制台 0 错误。`tasks.css` 删掉 `.tk-detail-foot` / `.tk-detail-warn` / `.tk-story-src` 三条死规则。测试 `tests/test_r217_about_notes.py`；`tests/test_r32_about.py` 里「赛季提示必须留在详情页」的两条旧断言按本轮需求迁移为「在关于里 + 详情页不再渲染」 |
| R218 历史价格曲线 | ✅ 市场详情弹窗里原来的「72h 价格曲线 / 数据积累中」占位**落地成真曲线**：新增 `tools/price_history.py` 只读 `data/flea-price-history/index.json` + 采集快照，按模式 / 物品 / 时间窗拼真实序列；新增 `GET /api/price-history?mode=&itemId=\|itemIds=&days=`（最多 60 个物品，days 上限 90，越界不报错只收敛）。前端 `js/market.js` 用纯 SVG 画折线 + 面积 + 十字光标 + 悬浮读数（最近低价 / 24h 均价），范围 24h / 7 天 / 30 天 / 全部，涨红跌绿；**单点只画一条水平虚线与一个点**并写明「至少 2 个快照才连线」，0 快照 / 该物品无价 / 接口失败各有独立文案；不插值、不补点、不跨模式顶替。`market.css` 新增 `.mk-hist-*` 一套 XP 风格（白底内凹面板、蓝色选中范围键）。对照 db4tarkov：其市场表格有 `HistoricalPrice(72h)` 列（每物品 72h 的 `{timestamp,price,offerCount}`，列宽 140/200，15 分钟自动刷新），数据来自 `eft-cdn.dvcstudiox.workers.dev/json/realtime/market_tm_<mode>.json`；我方运行期零联网，只能吃本机采集快照，按快照累积，口径不同但结论同源。验证（CDP 真实页面）：真实数据 1 个快照 → 单点虚线；拦截 `/api/price-history` 注入 6 点 → 折线 + 面积 + 刻度 420 000…340 000；悬浮读数 `352 000 ₽ / 388 000 ₽`；边界 `?mode=` 缺 itemId → 400、`mode=nope` → 400、`days=999` → 90、`mode=pve` 不串 regular 数据。测试 `tests/test_r218_price_history.py`（12 条）；`tests/test_r97_market.py` 两条旧断言按迁移原则改写（禁止一切 fetch → 只允许唯一本机 `api/price-history`；「数据积累中」/「HTTP 429」→ 新的真实状态文案） |
| R219 配装价格回流 | ✅ 用户反馈「获取方式的样式被上一个 agent 改坏、还多了几个价格栏」。**归因先查清：不是 bug，是 R74 的有意产品改动**——台账 `docs/r74-presets-modes-prices-ledger.md` §C「配装价格只留两项」把价格从「获取方式」合并列拆成 `p24`（跳蚤 24h 均价）/ `p7d`（跳蚤 7d 均价）两列，并给 `#lw-prices` 加了 `hidden`；本轮按用户要求回退到第十轮的合并口径。落地：删 `p24Col`/`p7dCol` 定义与 12 处列集（armor/rig/backpack/headphones/glasses/face/helmet/plate/attach/melee/gun 全部以 `srcCol` 收尾）、枪械预设表两列并作一列「跳蚤价格 148px」、`renderSrcCell` 恢复「来源图标 + `.lw-src-price` + `.lw-src-req` + `.lw-src-lv`」、`srcGroup` 列宽 126→168px、`#lw-prices` 去掉 `hidden`（最新 / 24h 均价 / 7 日均价三个 pills 回到配装页）、`fetchPriceSnapshot` 的 `notify` 在 `state.view === "loadout"` 时补 `refreshGearTable()`（否则切完模式仍停在构建期兜底值）。⚠️ **本轮最关键的隐性 bug**：`data/items.json` 的记录**不带自引用 `id`**（表以 id 为键），旧写法 `priceQuoteOf(rec.id)` 永远传 `undefined` → 恒为 null → 永远回退构建期快照，模式切换表面上「毫无反应」；改为 `fleaPriceInfo(id, rec, mode, basis)` / `modeFleaPrice(id, rec, mode, basis)` / `tradeView(t, rec, id)` 显式传 id，5 处调用点同步。云端契约缺口：实测 `/v1/prices` 只给「物品→单个价格 `l`」，三模式 `has_a` 全为 0，`tools/prices_source.py` 补两条**只补缺失、不覆盖已有值**的路径——`_fill_avg24h()`（`GET /v1/prices/history?mode=&basis=24h`，计 `avg24hFilled`）与 `_backfill_from_bundle()`（**同模式**内置快照，计 `avg24hFromBundled`）；两条都没有就保持缺失，绝不用 last / 7d / 别的模式顶替。浮窗随模式与档位变：「跳蚤市场 · 允许购买（PvP · 24h 均价）／来源：当前模式的行情快照」，回退时写明「退回构建期 items.json 快照（单模式快照，不是 PvE 行情）」，两处都缺写「不拿别的口径 / 别的模式顶替」。验证（CDP 真实页面 10/10）：表头末列 = 获取方式、无「跳蚤 24h 均价」「跳蚤 7d 均价」、pills 三档可见；同一行 Vulkan-5 `366,666 ₽`（PvP·最新）→ `391,709 ₽`（PvP·24h 均价）→ `790,754 ₽`（PvE·24h 均价）；`srcGroup` 40 行 0 溢出（曾有 `scrollWidth 182 > clientWidth 167`，`.lw-src { overflow:hidden }` + `.lw-src-req { max-width:104px }` 修掉）；截图 `D:/Temp/2/r219/loadout-price.png`、`zoom-src.png`。测试：新增 `tests/test_r219_loadout_price_cell.py`（8 条，含 Node 抽函数 8 组断言与服务端三条）；按「只迁移不放宽」改写 `test_loadout_workbench` / `test_r10_armor_table` / `test_r11_armor_grouping` / `test_r74_presets_modes_prices`（`test_c_loadout_price_has_only_flea_24h_and_7d_columns` → `test_c_loadout_price_lives_in_the_source_cell_only`）/ `test_r32_about` / `test_r40_armor_effdur` / `test_r6_gun_workbench` / `test_r78_mode_prices`（云端载荷断言改为 `l`+`a`+`avg24hFromBundled`）。验收脚本 `tools/r219_accept.py` 复用 `tools/r181_accept.py` 的 `find_chrome`/`launch`/`CDP`，**必须用干净 profile + `Network.setCacheDisabled`**，否则 Chrome 磁盘缓存会喂旧 `app.js`，导致「切 PvE 价格没变」的假失败 |
| R220 行情新鲜度与云端停摆 | ✅ 用户贴出一行自相矛盾的提示：「数据截止 11-09 15:01（**20 小时前**）· 非实时 · 已过期 **8 小时 54 分钟**」。查出两层问题。**① 客户端缓存冻结年龄**：`load_bundled` 把 `ageSec`/`stale` 连同归一化快照一起缓存，命中缓存 `return dict(cached)` 直接返回旧值（实测报 31 254 s、真实 32 928 s，落后 27.9 分钟且 4 秒内 `delta=0`）；`js/market.js` 前半句「N 小时前」用 `snapshotAt` 现算、后半句「已过期」读这个冻结值，于是打架。修：`prices_source` 命中缓存时 `hit.update(_age_fields(hit["snapshotAt"], now))`；前端新增 `liveAgeSec()` / `liveStale()`，行内、悬停、过期横幅三处**一律现算**，服务端 `ageSec` 只在时间戳不可解析时兜底；`_error_text` 改读 `CloudError.to_dict()` 的真实键 `error`（旧代码读 `message`/`detail`，读不到——修完失败原因从「云端请求失败」变成服务端原话「云端暂时不可达，请稍后再试」）。**② 云端 8443 停摆 21 小时**（这才是「20 小时前」的真因，不只是显示问题）：`run.py` 原先 `httpd.socket = context.wrap_socket(httpd.socket, server_side=True)` 把**监听** socket 包成 SSLSocket，TLS 握手因此跑在 `serve_forever()` 的 accept 主线程里——只要有一个客户端连上却不发 ClientHello（超时/被 kill/断网都会留下这种半开连接），主线程就永久阻塞在 `tcp_recvmsg`：端口仍在 LISTEN、进程仍活着、**老连接还能用**、所有新连接堆在 backlog 里超时。现场证据：listener `Recv-Q 6`、主线程内核栈 `sk_wait_data → tcp_recvmsg → sk_wait_data`、4 条 ESTAB 全来自本机 IP、一条 CLOSE-WAIT 积压 518 B、`journalctl` 停在 23:34:55、采集机 `--upload-status` 三模式全 `WinError 10060`（最后一次成功 13:51）。修：监听 socket 保持明文，`ApiServer.ssl_context` 交给 `process_request_thread()` 在**每条连接自己的线程**里握手（握手超时 10 s、空闲 60 s），`request_queue_size` 5→128，`run.py` 不再 wrap 监听 socket；两侧各留回归用例。**③ 采集机 exe 是旧构建**：`dist/EFTPriceCollector/EFTPriceCollector.exe`（11-09 13:15）仍发 `Authorization: Bearer …` 而不发 `X-Ingest-Token`（用本机探针抓包证实：`TOKEN_LEN 0`、`AUTH Bearer 7ae973b5…`），对 0.6.x 服务端恒 401；用 `tools/build_price_collector.ps1`（PyInstaller 6.22.3 / `C:\Python314`）重建后 `--upload` 三模式均成功。验证：最小复现里旧写法半开连接下正常请求 6.0 s 握手超时、新写法 0.01 s 返 200；线上同一测试 0.00 s 返 401（无 token 属预期）；云端批次 15:01 → **10:31（当天）**，`/api/price-snapshot` 返回 `source=cloud / live=true / ageSec≈1700 / stale=false`，界面「数据截止 10:31（29 分钟前）· 近实时」且无过期横幅；`tools/r220_accept.py` 7/7（新鲜态与过期态各一套断言）。服务器改动前已备份到 `/root/eft-cloud-backup-20261110-105607/`。测试：`tests/test_r220_price_freshness.py`（5 条）+ eft-cloud `tests/test_tls_accept.py`（3 条），eft-cloud 全量 78 passed |
| R221 上传节流对齐采集周期 | ✅ 用户反馈「市场的 数据现在还不是实时的 数据截止 10:31（57 分钟前）」。**先量三处再动手，避免瞎调**：① 本地 `/api/price-snapshot` 三模式 `source=cloud`，`ageSec=3480` 与 `now - snapshotAt` 的 3480 s **完全相等** → R220 的现算修复有效，不是显示问题；② 采集器 `collect/state.json` 显示 11:01:03–06 刚抓过、`heartbeat` 三模式 `ok:true / status:200 / notModified:false`，且今天 23 个快照 **23 个不同 SHA256** → 抓取端完全跟得上上游；③ 云端 `price_snapshots` 最新批次 `generated_at=10:31` 而 `stored_at=11:00` → **10:31 的数据拖到 11:00 才入库**。根因：`tools/price_upload.py` 的 `DEFAULT_CONFIG["minIntervalSec"] = 3600`，计划任务却是每 30 分钟一轮（`price_collect.DEFAULT_INTERVAL_MIN = 30`），于是「隔一轮才上传一次」，云端 `generated_at` 永远滞后 30–60 分钟；`upload-state.json` 里 `lastAttemptAt=11:00:20` 但 `lastGeneratedAt=10:31:05` 就是铁证。**上游节奏实测**：`json.tarkov.dev` 的 `Last-Modified` 为 11:30:29 / 11:30:51 / 11:31:16，即每 30 分钟发一版 —— 所以 30 分钟采集已是物理最优，**数据年龄的数学下限就是 0–30 分钟**，秒级「实时」不可能达成，除非上游改频率。修：`minIntervalSec` 3600 → **1500 s（25 分钟）**，略小于采集周期保证每轮都上传、同时仍挡住短时间重复上传；同步改 `%LOCALAPPDATA%\EFTPrice\upload.json`（运行期读配置，**不必等重建即生效**）、两处代码注释与 `--no-upload` 帮助文案、`js/market.js` 两处「采集机每小时上传」→「每 30 分钟采集并上传」。顺手修 `EFTPriceCollector.exe --help` 必崩：`sys.stdout.reconfigure(encoding="utf-8")` 原先写在 `ap.parse_args()` **之后**，而 `--help` 在 `parse_args` 内部就打印，走 Windows 默认 cp1252 → `UnicodeEncodeError`；把该段整体提到 argparse 之前。验证：手动 `--upload` 后云端 `generated_at` 变为 11:31:01 / 11:31:03 / 11:31:05，`/api/price-snapshot` 年龄 3 分钟；`tools/r220_accept.py` 7/7，界面「12 分钟前 · 近实时」，浮窗已同步新文案；采集器重建（8.9 MB，11:36）后 `--help` 正常且显示「默认 25 分钟节流」。端到端模拟：把 `lastSuccessAt` 回拨 31 分钟后跑 `--once --mode all`，**上传闸门放行**（进到内容幂等判断，不再报 `interval`），随后已还原为真实上传时刻 11:34:13。测试：新增 `tests/test_r221_upload_cadence.py`（8 条：静态不变量「`minIntervalSec` 必须严格小于采集周期」、旧「按小时节流」文案不得残留、31 分钟前成功过必须放行、5 分钟前仍节流、`force` 绕过、`nextUploadAt` 按配置推算、disabled 不误报 interval）；全量 `build/_pytest_r221b.xml` **1988 tests / 0 failures / 0 errors / 1 skipped**（119.84 s，退出码 0） |
| R222 历史曲线接上采集器快照库 | ✅ 用户贴出「还没有历史快照 / 采集脚本每次成功抓取会在 data/flea-price-history/ 落一份快照…当前没有可用样本」，问「这是为什么」。三层根因逐层证实：① **打包目录里根本没有这个文件夹**——`dist/EFTMap/_internal/data` 36 个文件无 `flea-price-history`，`load_index()` 直接返回 `no-index`，永远走空态；② **源码目录也只剩 1 份**——`data/flea-price-history/2026-11-08T144256.json` 是 11-08 14:42 构建期 `r20_fetch_prices.py` 落的，而日常采集器 `price_collect.py` **全文件零处 history 写入**，它写的是 `%LOCALAPPDATA%\EFTPrice\collect\snapshots\<模式>\<日期>\<HHMMSS>.json.gz`；现场实测 regular 78 / pve 76 / pvps 47 份，全是真数据，只是没人读；③ **那份归档只属 `gameMode=regular`**，模式一换过滤后归零，PvE/PvPS 报同一句话。修：`price_history.py` 增加第二个**只读**来源 `collector_entries()`（目录约定复用 `collector_prices.root_dir()`，`EFT_PRICE_ROOT` 可覆盖、空串即关闭），用文件名定时间戳免解压，再用 `JSONDecoder.raw_decode` 只抠目标物品那一行——实测 14 ms/份 → 3 ms/份（24h 47 份 0.29 s、7d 80 份 0.26 s）；两来源合并按时间排序、**同一时间戳只算一份**（优先采集器）、坏 gz 只记 `skipped`；超 2000 份截断但置 `truncated` 由 UI 明示，不静默丢；当前模式为空时回 `availableModes`，前端改说「PvE 有 76 份」。前端把空态拆成三种（该模式没有 / 区间没有 / 真的没有），删掉「采集脚本会写 data/flea-price-history/」这句假话，footer 加「（采集器 79 份 + 历史归档 1 份）」。测试：新增 `tests/test_r222_collector_history.py` 13 条（坏 gz、跨模式不串、时间戳去重、截断标记、与采集器目录常量一致），`test_r218` 加 autouse fixture 把 `EFT_PRICE_ROOT` 指到空目录（否则读到开发机真实快照）。验收 `tools/r222_accept.py` **11/11**：PvP 7 天 80 点（11-08 14:42 → 11-10 12:01，覆盖 3 天）、24h 47 点，界面样本数与接口 count 完全一致；全量 **2000 passed / 1 skipped**（128.14 s，`build/_pytest_r222.xml`，退出码 0） |
| R223 删除 Collected 计数 | ✅ 用户问「然后怎么还有这个 Collected 计数（仅本机，不跨设备）」。查清来路：这块是 R97 对齐参考站时**按结构照搬**的（参考站详情面板左列 `Collected: FIR [− 0 +] non-FIR [− 0 +]`），我们没有游戏内存/存档读取通道，只能做成手点计数器写 `localStorage['eftmap.market.collected.v1']`；R19.47 曾拍板「保留但标注范围」，于是加了标题限定、`未记录` 徽标与免责说明——标注是诚实的，**功能是空的**。删除前用真实浏览器探针实测 7/7：点 `+` 两次 → FIR 变 `2`、确实落盘 `{"<id>":{"f":2,"n":0}}`、刷新后仍在，但**页面没有任何地方消费这个数字**（行内无徽标、工具栏无「只看已收集」筛选、无导出）。修：`js/market.js` 删 `LS_COLLECTED` / `collected` / `readCollected()` / `saveCollected()` / `counterOf()` / `renderCollected()` / 左列 `<div class="mk-collected">` / `ui.collectedBox` / `[data-count]` 事件委托 / 初始化调用；`market.css` 删 `.mk-collected` 与 `.mk-count-*` 五条。**边界**：① 删 UI ≠ 删数据——旧 `localStorage` 记录原样保留，代码不 `removeItem`（用例守住）；② `.mk-count`（工具栏「显示 120 / 3540 条」）是另一个东西，保留并有用例防误删。测试：新增 `tests/test_r223_collected_removed.py` 6 条；`test_r97_market` 里「必须出现 FIR / non-FIR / 仅保存在本机」三条断言随功能删除**反转为「不得复活」**（改向而非放宽）。验收 `tools/r223_accept.py` **8/8**（无 `.mk-collected`、页面搜不到两块文案、左列仍有价格摘要与 Sell to、左列 347 px 无空白、Uses Tab 可切换、无 JS 报错）；`tools/r222_accept.py` 回归 **11/11**（7 天 80 点 / 24h 47 点，图表未受牵连）。文档 `docs/r97-market-module/01-structure-comparison.md` 新增 §13 记录删除理由与边界 |
| R224 曲线时间轴按区间铺满 | ✅ 用户反馈「24 小时 / 7 天 / 30 天 怎么都是一样的曲线」，并要求「没数据也要完整显示时间轴，没数据的部分不显示线」。根因：`drawHistoryChart()` 用 `rows[0]` / `rows[last]`（**数据首尾**）当时间轴两端——接口本身是对的（`days=1`→47 点、`days=7`→86 点、`days=30`→86 点），但本地只有约 2 天数据，7 天与 30 天返回同一批 86 点，被各自拉伸到整幅画布，渲染像素级雷同。修：新增 `histWindow(windowStart, days, points)`（有区间就 `[windowStart, +N 天]`，`days=0` 才用数据首尾，`windowStart` 缺失按最后一点回推）、`X(t)` 改按窗口换算并裁掉窗口外异常点、横轴改「起点 / 中点 / 终点」三刻度（`mk-hist-axis-x`）；新增 `histGapMs()`（采样间隔**偏低中位数** × 2.5，下限 45 分钟）与 `histSegments()`，**断档处断开**：每段独立 `M…L…` 与面积，孤立采样画 r=2 的点，段间不连线不补点。页脚去掉自相矛盾的「覆盖 N 天」（那是**自然日个数**，与 24h 窗口并列必然打架），改为「区间 A → B（24h）· 样本 N 个 · 有数据 23 小时 30 分（占 98%）」，占比 < 60% 时补一句「只有 X 有采集，其余 Y 没有样本」；两行口径说明合并为一句。验收 `tools/r224_accept.py` **22/22**：24h / 7 天 / 30 天 数据起点 x = 74 / 427 / 520，折线宽度 7 天 120 vs 30 天 28；11-08 14:42→20:45 那段 6 小时空档在 7 天/30 天里被切断（孤立点 1 个），24h 内 30 分钟连续采样不断线；轴首末刻度分别等于接口 `windowStart` / `windowStart + days`。测试 `tests/test_r224_hist_window.py` 6 条（静态契约 + Node 抽函数 + 三档坐标不得重合的纯算术）；`test_r218` 里「不代表中间真实成交」按新文案迁移为「不是逐笔成交」并加一条「没有样本的时间段不画线」（改向不放宽）。文档 `docs/r97-market-module/01-structure-comparison.md` 新增 §14 |
| R225 曲线图下注释全部去掉 | ✅ 用户贴出图下三行（区间 / 样本数 / 有数据 42 小时 13 分（占 6%）、「这个区间里只有…其余 28 天 5 小时没有样本」、「线 = 最近低价…不是逐笔成交…」）并说「这个注释直接去掉 不需要显示」。这三行正是 R224 为解释旧页脚而加的，信息全对但冗长。修：`js/market.js` 删 `.mk-hist-foot` / `.mk-hist-gapnote` / 口径说明整段，`histDurText()` 因无调用方一并删除；`market.css` 删 `.mk-hist-foot` / `.mk-hist-single` / `.mk-hist-single-line`。**连带修正**：单点（只有 1 个快照）原本画一条横贯全宽的虚线加一个点、靠图下文字解释；文字没了那条线会被读成「价格一直是这个数」，改为**只画点不画线**。**唯一保留**：`data.truncated` 为真时仍说「区间内共 N 份，这里只画最近 M 份（上限）」——那是数据缺失边界，不说会读成「更早真的没有数据」，日常（<2000 份）看不到。验收 `tools/r224_accept.py` 改造后 **43/43**：三档图下 `paraCount=0`、`tailText=''`，同时轴仍按区间铺满（起点 24h 80 / 7 天 426 / 30 天 520）、断档仍断开。测试：`test_r224` 页脚用例改向为「图下必须一个段落都没有」，`test_r218` 三条文案断言改为「不得复活」并补 `mk-hist-single-line` 不得存在；全量 **2013 passed / 1 skipped**。文档 `docs/r97-market-module/01-structure-comparison.md` 新增 §15 |
| R226 Obtain 不露上游字段名 | ✅ 用户贴出 Obtain 两行，指定去掉三处：「上游 types 未含 noFlea」「（minLevelForFlea）」「；上表 src 只说明上游标记的获取方式」。修 `renderObtain()`：可上跳蚤分支只留「上架等级 Lv N」，禁售分支改「不能在跳蚤挂单或购买。」（原「上游 types 含 noFlea；…」，顺带对称化），空交易提示只留「当前模式行情没有该物品的商人买价或兑换配方。」。判定结论、来源芯片、商人买价/兑换列表原样保留。**未动 `renderBanned()`**：Banned 禁售判定 tab 的主题就是「怎么判的」，`上游 types 含 noFlea` 在那里是内容不是噪音，用例专门守住不被连带删。验收 `tools/r226_accept.py` **17/17**，两件物品（FN SCAR-H 有商人买价 / M855 弹药包无 buy 无 barter）可见文本均不含 `noFlea`、`minLevelForFlea`、`上游 types`、`上表 src`，且保留「可上跳蚤」「上架等级 Lv 25/0」与那句空交易提示。测试 `tests/test_r226_obtain_copy.py` 5 条：静态抽**字符串字面量**（踩过坑：第一版用 `"noFlea" not in body`，被 `if (row.noFlea)` 这个代码变量判失败）+ Node 桩渲染三态。全量 **2018 tests / 0 failures / 0 errors / 1 skipped**。文档 `docs/r97-market-module/01-structure-comparison.md` 新增 §16 |
| R227 弹药说明不再显示 | ✅ 用户贴出弹药侧栏底部那段（`共 200 件弹药 / 31 种口径。价格口径 lastPrice，来源 实时不可用，已回退快照（PvP）；C1–C6 为对 1–6 级护甲的穿透概率（公开公式计算）。弹道曲线为本地 G1 阻力仿真，非线上行情。`）并说「这个也不要显示 隐藏掉」。拆开看四段全是重复或说明：件数/口径数已被工具栏 `#am-count`（`200 / 200 件`）覆盖；`价格口径 lastPrice` 已被侧栏顶部三段按钮的高亮覆盖；`来源 …` 已被 `#am-hint`（`价格来源：…`）覆盖；`C1–C6`/`G1 仿真` 属口径说明。修：`app.js` 删整段 `innerHTML` 拼接，`srcInfo` 提前复用并把 `detail` 悬浮从 `#am-note` 移到 `#am-hint`（`el.amHint.title = srcInfo.detail`），`amPriceLabel()` 唯一调用方消失后一并删除；`#am-note` 改为只在两种边界写入并显示，其余 `textContent=""` + `hidden=true`；`style.css` 加 `.am-note[hidden]{display:none}`（否则留 11px 空隙）。**保留两种边界提示**（只在主动切到该筛选时出现）：① 来源 CRAFT → 「本地 ammo.json 的 src 实测只有 trader / barter / none…结果为空」；② 价格口径 avg7d → 「上游不提供 7 日均价，该列一律显示 —」。这两句属「结果会变空」的告示，删了会被当成 bug。验收 `tools/r227_accept.py` **34/34**：默认态 `hidden=true`/`offsetParent=null`/高度 0/文本空；切到 avg7d 出现提示（h=33）并切回隐藏；CRAFT 提示 + 表格「没有匹配的弹药」；RESET 恢复 200 行且再次隐藏；`#am-count`=`200 / 200 件`、`#am-hint` 与 title 仍在；无 JS 异常。测试 `tests/test_r227_ammo_note_hidden.py` 6 条（文案不得复活 / `amPriceLabel` 已删 / 无提示必须 hidden / detail 已迁移 / CSS 隐藏 / Node 桩实跑三态）；`test_r44` 一条断言随实现迁移到 `el.amHint.title`。全量 **2024 tests / 0 failures / 0 errors / 1 skipped**。文档 `docs/r227-ammo-note.md` |
| R228 口径按钮统一宽度 | ✅ 用户「子弹界面右侧的筛选按钮 我希望所有子弹的按钮都一样宽」。改前 `.am-chips` 是 `display:flex; flex-wrap:wrap`，`.am-chip` 宽度 = 文字自然宽 + padding，同屏 32 个按钮 **36.1–95.9px** 参差、每行 4–5 个不等。修（只动 `style.css`）：`.am-chips` → `display:grid; grid-template-columns: repeat(3, minmax(0,1fr))`，侧栏 300px − padding 20 − 分组边框 2 = 276 → **每列 90px**；`.am-chip` 补 `min-width:0 / text-align:center / white-space:nowrap / overflow:hidden / text-overflow:ellipsis`（`minmax(0,…)` 必需：裸 `1fr` 的最小值仍是 `auto`，长内容会把列撑宽）。窄屏 `@media (max-width:1100px)` 侧栏变整行，改 `repeat(auto-fill, minmax(96px,1fr))`，否则 3 列被拉成 300px 大条。**只改布局不改尺寸**：height / padding / font 由 `assets/xp-ui/xp-ui-app.css` 的 `html body .am-workbench button:not(.am-tab):not(.am-seg-btn)…`（特异性 0,6,3，最后加载）决定，改 style.css 那几条不生效。验收 `tools/r228_accept.py` **18/18**：1600 视口 grid / 列轨 `90px 90px 90px` / 32 个按钮宽度簇 `[90]` / 五个分组内部各自 `[90]` / ≤3 个每行共 12 行（原 9 行）/ 侧栏横向滚动 0 / 选中态不变宽 / 1000 视口 9 列 105.7px 仍单值 / 无 JS 异常。已知边界：`40mm 俄制榴弹` 出省略号（XP 下内容区仅 64px，该名约 73px，是全 32 条里唯一超标者；次长 `12 号独头弹` 约 58px 正常），全称仍在 `title`，要消除需改 2 列（行数 →16）、侧栏加宽到 ~325px 或换短名。全量 **2023 passed / 0 failed / 1 skipped**（合计 2024，与 R227 持平，纯 CSS 无新增用例）。文档 `docs/r228-ammo-chip-width.md` |
| R229 口径按钮按「有没有子弹」置灰 | ✅ 用户「子弹页面 右侧的筛选 我希望点击后 如果是不显示的子弹 按钮就变灰 现在不知道哪些显示 哪些不显示」。**语义**：灰 = 该口径在当前其它筛选条件下一发都不剩（点了也不会有结果），不是禁用（放宽条件会亮回来），不加 `disabled`/`aria-disabled`，title 补「当前筛选下 0 发子弹」；「当前显示哪些」由 `aria-pressed` 表达，两者不重复。**最关键取舍**：统计必须按**不含口径过滤**的 `amRowsBase()`，用 `amRows()` 会让选中一个口径后其余 31 个全被判空、和选中态重复。`app.js` 改：从 `amChipHit` 抽出 `amChipOneHit(k,a)`（含霰弹/独头弹 atyp 拆分）、新增 `amChipCounts(pool)`、`amRowsBase()`（原 amRows 去掉口径过滤）、`amFilterByCal(pool)`、`amChipEmptyState()`（只写 `data-empty=0/1` 与 title）、`syncAmmoChipEmpty(pool)`（只刷灰态不重建 DOM）；`amRows()` 保留为组合；`renderAmmo()` 改为先算一次 pool 再分别喂表格与灰态；**搜索 input 是特例**——只走 `createTable.setSearch()` 不重绘，那里单独补 sync 并用 `amFilterByCal(pool).length` 更新计数。`style.css` 给 `[data-empty="1"]` 暗字暗底、选中但空另给暗青底 `#53616b`；`theme-windows-xp.css` 用整体 `opacity`（未选中 .45 / 选中 .7）——XP 按钮是位图九宫格且 `xp-ui-app.css` 用 `html body .am-workbench button:not(...)`（0,6,3）压过 background/color，改色不生效，且不用 `filter:grayscale` 以免洗掉按下态。验收 `tools/r229_accept.py` **14/14**：默认 32 个全亮且 R228 的 90px 等宽不回归；搜索 `9x19` 只有它不灰（31 灰，表格 9 行），灰按钮 computed opacity 0.45 vs 正常 1；点选一个已灰的口径，其余灰态**集合不变**、表格 0 行；清搜索 / RESET 回基线；`PEN≥40` 15 灰 17 亮；**逐个点选 32 个口径验证 `data-empty=1` ⟺ 单独选中后 0 行，32 个全吻合**；无 JS 异常。测试 `tests/test_r229_chip_empty.py` 7 条（静态契约 + Node 抽函数实跑计数 / 选中不影响计数 / atyp 不串）。全量 **2030 passed / 0 failures / 0 errors / 1 skipped**（合计 2031，`build/_pytest_r229.xml`，退出码 0）。文档 `docs/r229-chip-grey.md` |
| R230 口径按钮改为「亮=当前显示」，按下立即变化 | ✅ 用户澄清「凡是被口径过滤掉、当前没在显示的口径也一律变灰，只留选中的亮着 要的就是这个啊」「而且你现在做的是搜索 我要的是右侧的筛选按钮 按下后就有变化」——**R229 方向做反了**（按不含口径过滤的 `amRowsBase()` 统计，点口径按钮时侧栏纹丝不动）。改向：**灰态按最终显示行 `amFilterByCal(pool)` 算**。没选口径 → 有子弹的都亮、0 发的灰；选中 1 个 → 只剩它亮、其余 31 个立刻灰；选中多个 → 只亮那几个；被选中但被其它条件筛成 0 发 → 仍灰（确实没显示），`aria-pressed` 保留。灰不是禁用，点一下就加入选中集合，两种灰的 title 分开说「当前未选中，表格不显示该口径（点击可加入）」/「当前筛选下 0 发子弹」。`app.js`：`amChipEmptyState(chip,key,shown,base)`；`syncAmmoChipEmpty(pool,shownRows)` 内部 `amChipCounts(shown)` 判亮灰 + `amChipCounts(base)` 只用于解释原因；三处调用点都传 rows——`renderAmmo()`（`syncAmmoChipEmpty(pool,rows)`，**点口径按钮走这条**）、`renderAmmoFilterUI()`（按 `amFilterByCal(pool)` 写初始态）、搜索 `input`（不重绘表格，单独同步）。`amChipCounts` 是纯计数函数、`amRows()` 不变（散点图仍用），CSS 沿用 R229 灰态。验收 `tools/r230_accept.py` **19/19**（全部真实点击，不拿搜索当触发源）：默认 32 全亮；**按 `9x19` 立刻只剩它亮、31 灰、表格 9 件、灰 opacity .45 vs 亮 1、灰 title 说明未选中**；再按 `5.45x39` 两亮 30 灰（9→22 件）；再按一次取消只剩它亮（22→13 件）；SHOW 手枪组只亮该组 8 个；搜索 9x19 后按 0 发的 `5.45x39` 仍灰且表格 0 行；RESET 全亮；`PEN≥40` 17 亮 15 灰；**逐个点选 32 个口径，每次只亮「选中且有子弹」的那一个，全吻合**；R228 等宽不回归；无 JS 异常。测试 `tests/test_r229_chip_empty.py` 断言**改向不放宽**（8 条）：base 池→最终行、新增「点口径路径必须重算」、Node harness 验「按最终行计数时未选中口径归零」+ 两种灰 title。`tools/r229_accept.py` / `docs/r229-chip-grey.md` 加作废标注，新文档 `docs/r230-chip-visible-state.md`。全量 **2031 passed / 0 failures / 0 errors / 1 skipped**（合计 2032，`build/_pytest_r230.xml`；日志末段 SSE 线程 `ConnectionAbortedError` 与批量删除守卫是既有收尾噪音，JUnit 无 failure/error） |
| R231 弹药空结果不再出现「放大图」背景 | ✅ 用户「把所有子弹隐藏后 子弹页面背后的背景好像是什么图强行放大后的样子 请改掉」。排查：空态下 `#ammo-view` 内所有元素的 `background-image` / 祖先链 / `<img>` / 伪元素**全都没有图**，元凶是 `assets/xp-ui/xp-ui-app.css` 三个工作台共用的 `border-image: url("table-frame.png") 2 fill / 2px stretch !important`——该图只有 64×64（白底 + 一圈细内框线），`fill` 把中间切片 stretch 到 1282×715 滚动区，细线被放大成左右/底部一圈模糊灰带；**有 200 行时被行盖住，全筛掉才露出来**。对比实验：单独关掉 `.tbl-scroll` 的 border-image → 灰带消失；单独关掉 `#am-workbench` 的 `menu-panel-bg.png 12 fill` → 截图毫无变化（且它与枪匠/配装/任务共用，不动）。修：把 `.am-workbench .am-table .tbl-scroll` 从共用位图规则里摘出，单独给 `border: 1px solid var(--xp-border-dark, #aca899) !important; background-color: #fff !important`（与 `theme-windows-xp.css` 既有列表口径一致；必须 `!important`，否则 `style.css` 的 `border:0` 特异性更高会变无边框）；配装 / 枪匠保持 `table-frame.png`。验收 `tools/r231_accept.py` **12/12**：有数据 200 行 / 全隐藏 0 件时弹药滚区都是 `borderImageSource=none` + `1px` + 白底；枪匠/配装仍用 table-frame.png 未回归；R228 的 90px 等宽 + R230 清空搜索后 32 个全亮不回归；无 JS 异常。测试 `tests/test_r231_ammo_table_frame.py` 5 条静态契约（弹药段 CSS **剥掉注释后**不得含位图/fill/stretch——注释为解释原因会提到这些词，R226 踩过同样的坑）。文档 `docs/r231-ammo-table-bg.md`。全量 **2036 passed / 0 failures / 0 errors / 1 skipped**（合计 2037，`build/_pytest_r231.xml`） |
| R232 所有表格滚区统一去掉位图 fill 拉伸 | ✅ 用户「你检查一下 我发现好几个地方都会有而是表格滚动区的边框位图被放大」。R231 只摘了弹药页，本轮用 CSSOM 逐视图扫所有「`border-image` 带 `fill` 且容器远大于位图」的元素，确认同类问题有**两条规则**：① `table-frame.png`(64×64) `2 fill / 2px stretch !important` 还作用于 `.loadout-workbench .tbl-scroll`(1095×559)、`.gun-workbench .tbl-scroll` 与各视图共用的隐藏模板；② 更通用的 `html body .tbl-scroll { groupbox.png(280×154) 6 fill / 2px stretch }` 覆盖所有不在工作台内的表格（任务/市场/弹窗）。两条都会把位图中间细内框线拉成模糊灰带、空结果时最明显。`style.css` 的 `.tbl-scroll` 基础定义与 `theme-windows-xp.css` 三张工作台的规则本来就是纯色 + 1px 实线，所以从**源头纯删除**：15.2 通用组摘掉 `.tbl-scroll`、15.7 整块删掉 `table-frame.png` 规则，CSS 声明里不再有该图；保留 R231 给弹药页的 `!important` 1px 白底（`style.css` 对该选择器写了 `border:0` 必须压住）；工作台外壳 `menu-panel-bg.png 12 fill` 不动（R231 实测关掉无可见变化且四工作台共用）。验收 `tools/r232_accept.py` **10/10**：逐视图（地图/任务/弹药/配枪/配装/市场）枚举全部 9 个 `.tbl-scroll`，computed `borderImageSource` 全为 `none`（改前配装/枪匠/模板是 table-frame、通用是 groupbox）；可见滚区（弹药 1282×715、配装 1095×559）都是 `1px` + `rgb(255,255,255)`；R231 空态 / R228 90px 等宽 / R230 默认 32 全亮不回归；无 JS 异常。**体检还查到但本轮未改**：`titlebar.png`(719×36) 拉到 `gw-page` 1582×666 / `am-groups` 278×559、`groupbox.png` 拉到 `gw-browse` **1556×3541** / `am-side` / `lw-board` / `task-list`、`menu-panel-bg.png` 拉到四个工作台 1584×757——都是 XP 面板/标题栏底板（中间是纯色或渐变，不是细线），属皮肤改动需用户确认；清单存 `docs/r232/report.json` 的 `remainingFillContainers`。测试 `tests/test_r231_ammo_table_frame.py` 断言**改向不放宽**（7 条：全 CSS 声明不得有 table-frame.png、groupbox 组不含 .tbl-scroll、任何以 .tbl-scroll 本身为目标的规则不得带 fill/stretch 位图——跳过滚动条轨道与 `.tbl-scroll .tbl-head` 的 1px 九宫格）。全量 **2038 passed / 0 failures / 0 errors / 1 skipped**（合计 2039，`build/_pytest_r232.xml`）。文档 `docs/r232-all-tbl-scroll.md` |
| R233 配装预设提示改会员引导 + 会员云存储接通 | ✅ 用户「配装栏这个提示改成『免费版预设保存在本地 会员享受云存储』，然后看看能不能做到云存储并实现」。调研 `eft-cloud`：**服务端零改动即可**——`_require_member()`(service.py:1621) 会员门禁、`sync_items(account_id,key,value,hash,version)`(schema.sql:162-181) 账号级通用 KV、`/v1/sync/{state,push,fetch}` 增量同步、`js/cloud.js` + `tools/cloud.py` 客户端链路**均已投产**；`docs/cloud-service-plan.md` 预留的专用 `/v1/presets`+专用表是标注「暂不实现」的重方案，不用走。实现：`app.js` 空态提示改 `PRESET_STORAGE_NOTE`（悬浮说明走前端唯一会员入口 `isMember()`）、`presetPost()` 成功后派发 `gw:presets-saved`、监听 `eftmap:presets-remote-applied` 刷新缓存重绘；`js/cloud.js` `collectValues()` 改 Promise 并加 `preset.weapon`/`preset.loadout` 两键（`{schema:1,presets:[…]}`）、`applyRemote()` 拆出 `applyPresetRemote()` 走 POST `/api/presets action=replace`、`syncNow()` 适配 Promise、新增监听 `gw:presets-saved` 复用 3s debounce；`tools/serve.py` `/api/presets` 新增 `action=replace`（只收数组，交给统一 `presets.save()` 归一化+原子写）。免费版在 `syncNow`/`scheduleSync`/BFF `is_member()` 三重拦截，零云请求；本地文件仍是第一事实源（冲突保留本地、损坏文件拒绝覆盖、超 240000 字符跳过并在同步消息里明示、读不到预设不拿空数组冒充）。验收 `tools/r233_accept.py` **16/16**（**全程 fetch mock、POST 不落盘，绝不碰真实 %APPDATA% 预设**）：文案精确、悬浮说明按会员态、会员点「立即同步」→ GET 两类预设 → `/api/cloud/sync` 带 5 键 → 远端整包 POST `action=replace` 写回 `wp_cloud1`；免费版按钮 disabled 且派发保存事件等过 debounce 后零 `/api/cloud/sync`；R228 等宽 / R232 表格白底不回归；无 JS 异常。测试 `tests/test_r233_preset_cloud.py` 9 条（静态契约 + HTTP 级 `serve.create_server` 整包替换/坏 payload 不覆盖/损坏 409 + Node harness 实跑 collectValues/applyPresetRemote）。**已知边界**：真实云端上传未实跑（无会员会话，mock 覆盖前端→BFF 全链路；服务端 `/v1/sync/*` 是已投产接口）；`/v1/sync/*` 无频率限流；会员开通仍只有 CLI。全量 **2047 passed / 0 failures / 0 errors / 1 skipped**（合计 2048，`build/_pytest_r233.xml`）。文档 `docs/r233-preset-cloud-sync.md` |
| 在线行情 | ✅ **云端已恢复**（2026-11-10 11:0x）：`47.96.68.209:8443` 从本机 TCP 0.01 s 可连、HTTPS 正常应答；采集机 10:31 批次三模式已入库（PvP 3549 / PvE 3744 / PvPS 3404 条有价），会员读价 `source=cloud`。⚠️ 云端的 24h 均价仍只有单价格口径：`/v1/prices` 只给 `l`，`avg24hFromBundled` 从**同模式内置快照**补齐（该文件是 11-09 15:01 的，所以「24h 均价」档的数据比「最新」档旧，属已标注的降级）。另有「在线行情开关 `livePrices.enabled`」，**默认关闭**；显式开启后才访问 tarkov.dev。云账号 / 会员 / 在线行情为用户明确推动的产品方向（`eft-cloud` 已上线 0.6.1），早期「运行期不联网」的绝对表述已演进为受控例外，见 §0.1 |
| 已知未实现 | ❌ 快门声音替换（版本号不得升 1.0）、账号级任务统计（刻意不做）、高级子弹刷新点图层（上游无数据）、**截图识别价格 OCR**（需 `onnxruntime` + 15.5 MB 模型，与零新增依赖冲突，仅有算法规格） |

接手时优先读 **§0.1**：上一个会话在 2026-11-03 09:57 写完 R29.3 后未再更新本手册；
项目内 R33 起改用逐轮台账，而**完整的按日会话记忆在 `.trae-cn` 主记录目录**（路径见 §0.1），
11-03 之后的改动与验证结论以该处为准。

**历史快照（2026-10-19，第十六轮；以下原文保留）**

| 项 | 状态 |
| --- | --- |
| 源码可运行 | ✅ `python tools/launcher.py` 或 `python tools/serve.py` |
| 测试 | ✅ `python -m pytest tests -q` → **611 passed, 1 skipped** |
| 数据 | ✅ `data/maps.json` + `data/meta.json`，schema **8**（第十五轮：`HIGH_VALUE_ITEMS` 加「情报文件夹」，并把「其他高价值」子类拆成「情报」+「蓝色文件夹」，见 §6.20），**13 张图**（含实验室 / 迷宫 / 破冰船三张瓦片图，见 §6.13 / §6.18）；另有**物品资料库** `data/items.json`（5480 件）+ `data/gunslots.json`（163 枪 / 497 套）+ `assets/icons-items/`（5480 个 webp），见 §6.21 |
| 路网 | ✅ `data/roadnet.json` + `assets/roadnet/<图>/<层>.bin`（10 张矢量图的静态路网，供前端同层沿道路寻路，见 §6.19） |
| 发布包 | ⚠️ `release\` 下**三件套**（Portable zip / AppWindow zip / Setup exe）当前仍是**第十四轮代码**的产物（含 `assets/roadnet/` 35 个位图与 `data/roadnet.json`，见 §6.14 / §6.19）；**第十五 / 十六轮的前端 / 数据改动尚未重打包**，待用户确认后重出三件套并更新 GitHub Release v0.1.0。**注意：第十六轮新增的 `assets/icons-items/` 有 5480 个 webp（约 14.9 MB）、`data/items.json` 约 3.8 MB，重打包后产物会明显变大。** |
| **配置位置** | ⚠️ **已改为用户级目录** `%APPDATA%\EFTMap\`（不再放软件目录）——重新打包不再丢设置，见 §6.7 |
| **Git** | ⚠️ 第十三 / 十四 / 十五轮的提交**已推送** `origin/main`；**第十六轮改动（app.js / index.html / style.css / tools/config.py / tools/fetch_data.py / tools/serve.py / tools/launcher.py / tests / README / docs / AGENT_HANDOFF）尚未提交**，见 §9 |
| 已知未实现 | ❌ 快门声音替换（见 §3 版本号铁律）、账号级任务统计（刻意不做）、**高级子弹刷新点**图层（上游物资点里没有子弹信息，见 §11）、**配枪视图**（阶段二：`data/gunslots.json` 已就绪但界面仍是占位，见 §6.21） |

最近一次实质改动（2026-10-19，第十六轮）：**联网给工具做「局域网访问」（解决跨机自动截图不可达）+ 整合物品资料库 + 落地配装视图（三栏：槽位 / 汇总减益与灵敏度补偿 / 物品大表）**，见 §6.21。
上一轮（第十五轮）是高资子类拆分等一组体验改动（§6.20）；再上一轮是导航沿道路走（§6.19）。

---

## 0.1 R33–R210 变更索引与工作日志位置（补于 2026-11-09）

上一个会话在 **2026-11-03 09:57** 写完本手册的 R29.3 段落（同一时刻产出 `docs/r32-xiaomeow-re/REPORT.md`）后停止更新手册；
三分钟后（11-03 10:00）开始改用**逐轮台账**，`r33-path-migration-ledger.md` 的抬头明确写了
「后续改动请沿用同样的头部格式」。因此 §6 / §9 / §11 及 §11 末尾「当前工作树干净度」都是第十六轮历史记录，
**接手时以 §0 为准，查细节按本节索引找台账**。

### 工作日志实际落在四处（2026-11-09 15:05 更正）

> **更正**：本节初版写「工作区按日日志 11-02 断档至 11-09」，该结论只适用于 WorkBuddy 侧的
> `D:\personal\trae\.workbuddy\memory\`。用户指出的 `.trae-cn` 路径才是主记录，覆盖完整，以下表为准。

| 位置 | 内容 | 覆盖范围 |
| --- | --- | --- |
| **`C:\Users\Administrator\.trae-cn\memory\projects\-d-personal-trae--p2-cb0fc76ba06adbda72e8\`（主记录）** | `project_memory.md`（46 KB / 259 行，分「硬约束 / 工程约定 / 经验教训」三节，最后更新 11-07 23:20）；按日目录 `20261018`–`20261109` 下 `topics.md`（主题汇总）与 `session_memory_<会话标识>.jsonl`（结构化字段：意图 / 动作 / 结果 / 经验）。**共 324 条会话记忆**：10-18 14、10-19 58、10-20 17、10-21 8、10-22 4、10-25 5、10-29 7、11-01 17、11-02 21、11-03 14、11-04 38、11-05 36、11-06 15、11-07 16、11-08 39、11-09 15 | 2026-10-18 ~ 11-09 14:15 |
| `docs/rNN-*-ledger.md`（项目内，**38 份**） | 逐轮台账：改动清单、文件摘要值（SHA256）、验证命令、测试基线、明确列出的数据缺口 | R33 → R77，11-03 10:00 ~ 11-05 16:20 |
| `docs/rNN-*/report.md` / `ledger.md` 及顶层方案文档 | R78 起改子目录报告：`r78-mini-zoom/`、`r79-eyewear-eyes/report.md`、`r84-release/report.md`、`r86-storyline/ledger.md`、`r97-market-module/01-structure-comparison.md`；另有 `ui-baseline-audit.md`、`ui-component-spec.md`、`xp-ui-*.md`、`db4tarkov-market-pipeline.md`、`cloud-service-plan.md`、`denuvo-principles-and-local-tool-protection.md` | R78 → R97，11-05 ~ 11-08 |
| 会话归档 `C:\Users\Administrator\.workbuddy\projects\d-personal-trae\*.jsonl` | 完整对话与工具调用原始记录。主会话 `71ab786e…`（约 152 MB，10-22 23:18 起持续到 11-09）；`edefed53…`（1.07 MB，11-09 14:04–14:35，内容是技能与 MCP 配置，非项目进度） | 2026-10-22 ~ 11-09 |

⚠️ **汇总层曾于 11-08 之后中断，已于 2026-11-09 15:2x 补齐**：当时 `project_memory.md` 停于 11-07 23:20、
`topics.md` 的 11-08 版本仅 1 行（286 B）且被截断、11-09 无该文件，但 `session_memory_*.jsonl` 一直写到 11-09 14:15，
属于**自动会话记忆完整、人工汇总与总手册没跟上**，与「前一个 agent 未及出手册」的判断一致。
现已按会话记忆回填 `20261108/topics.md`（保留被截断的原行，追加 10 条明细）、新建 `20261109/topics.md`（6 个会话 15 条）、
在 `project_memory.md` 末尾追加「Session Summary 2026-11-09（补录）」章节（含两条产品线、三层行情、打包链、PyInstaller 环境、汇总层写入纪律）。
WorkBuddy 侧 `.workbuddy\memory\` 确有 11-02→11-09 断档，且 11-09 那份只记技能与 MCP 配置，不能替代主记录。

### R33 → R210 主线（可按台账与会话记忆回溯）

| 阶段 | 内容 |
| --- | --- |
| R33–R52（11-03 ~ 11-04） | 逆向素材路径迁移；打包链重写；实时价格（`r39` / `r42` / `r44`）；任务页重做（`r41`）；版本与账号体系（`r43` / `r45`）；安装器、清理与发布包反复重出（`r46`–`r52`） |
| R53–R77（11-04 ~ 11-05） | 卸载确认；弹道与护甲公式重写（`r54` / `r56` / `r57` / `r59` / `r62` / `r64` / `r65`）；配装表（`r67`）；任务面板与 XP 风格（`r68`–`r77`）；窗口一致性（`r76`） |
| R78–R97（11-05 ~ 11-07） | 迷你缩放、护目镜、发布；剧情系统（10 条线 / 266 步 / 4 分支，缺口显式暴露）；XP UI 素材与覆盖审计（整体覆盖率 91.2%）；ADS 速度统一计算入口；剧情级联弹窗缓存修复；小地图开关与独立视图状态 |
| 11-08（会话记忆 39 条，多会话并行） | 客户端：0.2.1 / 0.2.2 打包与黑边修复、云账号同步、会员门控与 10 秒节流、手动截图误删修复、日志与截图目录自动探测、价格采集器独立为 exe、市场模块分块开发；**并行项目 `eft-cloud`**：阿里云 ECS 部署（公网 8443）、SMTP 发信、60 秒发码冷却、0.3.0 → 0.4.0 上线、永久会员授权；调研：db4tarkov 价格更新机制、R209 逆向、R210 防破解 |
| R209 / R210（11-09） | 两份**只分析未改源码**的方案文档：`r209-kaedeori-loadout-and-membership-review.md`（结论：不做重会员体系，短期免费核心 + 赞助）、`r210-local-anti-crack-plan.md`（结论：只做构建指纹 + 资源完整性自检 + 分发水印，不做 Denuvo 式保护） |
| 11-09（会话记忆 15 条） | 客户端：R19.53 回归验收（1882 通过）、云同步会员化（1886 通过）、**0.2.4 重打包**（12:08，1896 通过 + 覆盖安装升级实测 + 产物 SHA256）、市场页切本地采集器快照并接入 PvPS 独立接口、三层行情系统（免费内置 / 会员云端 / 离线回退，164 项相关测试）、消音/非消音对比、配装「获取方式」列恢复方案调研；服务端 `eft-cloud`：0.5.0 上线、0.6.0 价格上传与读取、0.6.1 上线（5100 条数据）、fail2ban 403 误封修复、会员读价格链路闭环（三模式数据量 3551 / 3742 / 3409）。**最后测试基线 1915 通过 / 0 失败**，与 2026-11-09 14:27 复核一致 |

**11-09 的代码改动有完整会话记录**（主记录 `20261109/` 六个文件、15 条），项目内则缺逐轮台账，
单看 `docs/` 会误判为「无记录」；源码级细节仍需版本差异比对（`git diff`）确认。

### 未闭环项（接手优先处理）

1. ~~**重出发布包**~~ → ✅ **2026-11-09 15:50 已闭环**：按 §2 铁律 10 重出 0.2.5 三件套（详见 §0 发布包行）。
   执行链：`build.ps1 -VerifyOnly` 校验清单 13390 项（缺失 0 / 多余 0）→ 修掉 15:01 重构引入的三个 ps1 双 BOM → 备份 0.2.4 → `tools/build_bundled_prices.py` 重生成三模式内置快照（源数据 0.46 h，新鲜度通过）→ `build_release.ps1` 完整打包（PyInstaller 6.22.3 / Python 3.14.3，耗时约 24 分钟，退出码 0）→ 产物 SHA256 与源码一致性校验通过。
   **打包后回归**：`python -m pytest tests -q --tb=no --junitxml=build/_pytest_0.2.5.xml` → JUnit `tests=1916, failures=0, errors=0, skipped=1, time=145.472`（15:56）。进程退出码 1 且终端未打印末行 summary，原因是收尾阶段的 socketserver 线程 traceback 与批量删除守卫拦截 pytest 临时目录清理，日志无 `FAILED` 用例、XML 无 failure/error 节点；结论以 JUnit 为准，与 14:27 基线一致。日志在 `build/_pytest_0.2.5.log`。
   **遗留**：未在真实机器上做 0.2.5 覆盖安装升级实测（0.2.4 当时做过），如要对外发布需补这一步；未发 GitHub Release，未提交 git。
2. **端口口径**：`DEFAULT_PORT = 8787`（`tools/serve.py:54`）；历史日志里的 `8810` 是开发时手动指定的运行端口，两者需统一。主记录还提示 8787 被旧打包版进程占用时会误访旧页面。
3. **铁律 1 的语义已演进**：用户明确推动云账号 / 会员 / 在线行情，`eft-cloud` 已上线 0.6.1；在线行情开关默认关闭，符合「新开关默认关」。早期「运行期不联网」的绝对表述已不适用，应把受控例外写进 §2 铁律以消除歧义。
4. **价格 OCR 未实现**：`docs/r32-xiaomeow-re/REPORT.md` §3 有完整算法规格（DB 后处理 / CTC / 模糊匹配 / 阈值）；落地需 `onnxruntime` 与 15.5 MB 模型，与「零新增依赖」冲突，按当时决策停在方案层。
5. **配装「获取方式」列（2026-11-09 15:4x 源码核对后更正）**：11-09 14:14 的会话记忆写「该列在 R74 被连带移除、`srcCol` / `renderSrcCell` 成死代码」，**与当前源码不符，勿据此动手**。
   实测 `app.js:12287` 的 `srcCol`（label「获取方式」，独立图标列）被 12304–12352 共 12 处列集引用，`renderSrcCell` 在 `app.js:11651` 正常渲染；
   `docs/r74-presets-modes-prices-ledger.md` 的标题即为「配装枪械预设 / 模式唯一入口 / **价格两列**」——R74 是有意把价格从「并入获取方式」的合并列
   （旧版 `srcColPrice` / `renderSrcCell(cell,row,merged)`，见 `docs/r19.17-*`、`r19.19-*` 的 backup/app.js）拆成独立的 24h / 7d 两列，
   **移除的是合并列而非获取方式列本身**。数据未丢、设计未破。若仍要恢复合并版，属于产品口径回退而非 bug 修复，需用户明确表态；调研给出的三种方案原文未落入汇总层，只能从会话归档回溯。
6. **手册与汇总层自身**：§6、§9、§11 为历史章节，勿按其中数字判断现状；本手册头部版本行（0.1.0 / 611 passed）同样是 10-19 的历史值。
   `.trae-cn` 的 `project_memory.md` 与 11-08 / 11-09 的 `topics.md` 已于 2026-11-09 15:2x 补齐（见本节开头的四处日志位置表下方说明）。
7. **打包链执行要点（2026-11-09 实跑验证）**：① `build/build.ps1 -VerifyOnly` 可只做 staging 清单校验、不碰 `dist/` 与 `release/`，实测清单 13390 项、缺失 0 / 多余 0；
   ② **PyInstaller 6.22.3 只装在 `C:\Python314`**，命令行默认 `python` 是 3.13.14 且无该模块，`build_release.ps1` 内部用 PATH 里的 `python -m PyInstaller`，执行前必须把 `C:\Python314` 置于 PATH 首位；
   ③ `build_release.ps1` 会**先整个删除 `release/`** 再产出三件套，重打包前务必把旧版本产物备份到该目录之外（本次备份在 `build/_prev_release_0.2.4/`，SHA256 已比对一致）；
   ④ 15:01 重构的三个 ps1 曾带**双 UTF-8 BOM**，PowerShell 5.1 会报 `Unexpected attribute 'CmdletBinding'`，已修为单 BOM；以后写 .ps1 必须保留且只保留一个 BOM；
   ⑤ `build.ps1` 默认先跑 `tools/build_bundled_prices.py` 重生成三模式内置快照，源数据超 12 小时直接拒绝打包，可用 `-SkipBundledPrices` 复用现有快照。
8. **R211–R219 待统一打包（2026-11-09 17:0x 起，用户明确要求「这只是小改动，接下来还有别的改的，到时候再说」）**：前七轮纯前端，R218 多了一个后端只读接口 `tools/price_history.py` + `/api/price-history`（打包时会被 PyInstaller 一并收进去，`data/flea-price-history/` 需随包带上），R219 是纯前端 + `tools/prices_source.py` 的云端取价补齐（`/v1/prices/history` 与同模式内置快照回填 `avg24h`，不新增依赖）；`release/` 与 `dist/` 仍是 15:44–15:50 的 0.2.5 产物。
   后续界面改动收齐后按第 7 条重出三件套；在此之前不要拿发布包判断这九轮效果，用 `http://127.0.0.1:8787/index.html` 源码服务（`Cache-Control: no-store`，Ctrl+F5 即可）。
   18:0x 曾发现该服务进程自行退出、端口无监听，已按 `C:\Python314\python.exe tools/serve.py --no-browser` 恢复并核对 HTTP 响应与磁盘逐字节一致；若再次打不开，先查 8787 监听再按此命令恢复。

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
   > **2026-11-09 口径修订（原句作为历史基线保留）**：用户已明确推动云账号 / 会员 / 在线行情产品线，配套服务端 `eft-cloud` 已上线 0.6.1。本条现按**受控例外**执行：默认仍完全离线；只有用户显式开启 `livePrices.enabled`、或主动登录云账号后才访问网络；所有新增开关默认关闭（铁律 4）；免费档读内置 `data/flea-prices*.json` 快照、不发起云端请求，断网自动回退。构建期联网仍只在 `tools/fetch_data.py` 与价格采集器这一层。**勿按原句否定已上线功能，也勿把受控例外当成默认可联网。**
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
├── app.js           203 KB  前端全部逻辑（单文件，零依赖，含图标体系 + 视图切换 / 配装视图）
├── index.html         9 KB  页面骨架（顶部菜单栏 + 视图切换 + 工作区 + 三个视图面板）
├── style.css         34 KB  框架 = Windows XP (Luna) 浅色；地图区与标记仍用深色「卡带未来主义」配色
├── README.md         30 KB  面向用户的完整文档（改功能必须同步改这里）
├── data/
│   ├── maps.json           构建期产出（13 张图的底图引用 + 全部标注）；schema 8
│   ├── items.json          物品资料库（5480 件物品的属性 / 槽位 / 价格快照）；schema 1，约 3.8 MB
│   ├── gunslots.json       配枪槽位与预设（163 把枪 / 497 套预设），供阶段二「配枪视图」用
│   ├── roadnet.json        路网索引（10 张矢量图各层的格子边长 / 尺寸 / 字节数与各类格子计数）；schema 1
│   └── meta.json           数据溯源（各接口 url/license/sha256 + 计数，含瓦片 `tileMaps` / `tileBytes`）
├── assets/maps/*.svg       13 张底图（10 张上游矢量 SVG + 实验室 / 迷宫 / 破冰船 3 张构建期用瓦片拼的合成 SVG，约 10.0 MB，已入库）
├── assets/maps/tiles/      瓦片 PNG（实验室 / 迷宫 / 破冰船用，每张图一层一组，已入库；合成 SVG 里的 `<image>` 引用的就是它们）
├── assets/roadnet/<图>/<层>.bin  各层路网位图（每格 2 bit 通行码，10 张矢量图共 35 个位图约 779 KB，已入库）
├── assets/icons/*.png      219 个图标素材（64×64 透明 PNG，用户提供源图 + tools/iconize.py 抠图导出，已入库）
├── assets/icons-items/*.webp  5480 个物品图标（64×64 透明 webp，构建期从 assets.tarkov.dev 拉取，约 14.9 MB，已入库；配装 / 配枪视图用）
├── tools/
│   ├── fetch_data.py       构建期数据管道（唯一联网点；第 5 步会顺带重建路网；另拉物品资料库 / 配枪槽位 / 物品图标，见 §6.21）
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

## 6. 历次已完成的改动（6.1 – 6.21；第九轮见 §6.14、第十轮 §6.15、第十一轮 §6.16、第十二轮 §6.17、第十三轮 §6.18、第十四轮 §6.19、第十五轮 §6.20、第十六轮 §6.21）

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

### 6.20 第十五轮：高资子类拆分 + 地名滑条 + 保存配置 + 浮窗常驻 + 途径点拖动排序 + 钉选常驻 ★（第十五轮）

用户本轮提出 5 项（前后多次提交，部分需求之前那次丢了、其实没做完，这轮一并补齐）：

**① 新增两个地名滑条**：在右上角「图标」滑条下方加「地名」滑条（50%–300%）与「地名透明度」滑条（0%–100%）。
- 铁律不变：地名节点**不在 `state.markerScaleNodes` 里**、不带 `__emkBase`，其 `transform` 只写 `translate(sx sy)`，随地图 viewBox 等比缩放；
  所以**不能**给地名加 CSS transform（会栅格化变糊）。`renderLabels()` 把每个 `<text>` 记进 `state.labelNodes = [{node, size, stroke}]`
  （`size = 12*unit`、`stroke = 2.4*unit` 是**基准值**，不含缩放）；`applyLabelStyle()` 就地改 attribute
  （`font-size = size*labelScale`、`stroke-width = stroke*labelScale`、`opacity = labelAlpha`），**不重跑 `renderOverlay`**（拖动才不卡、也不会把地名重排到路线之上）。
- 新增 `LS_LABEL_SCALE`/`LS_LABEL_ALPHA`、`LABEL_SCALE_MIN/MAX`、`LABEL_ALPHA_MIN/MAX`、`state.labelScale/labelAlpha`、
  `labelScale()/labelAlpha()/setLabelScale()/setLabelAlpha()`；`uiPatch()` 增 `label_scale`/`label_alpha`，`restorePrefs()`/`applyUiPrefs()` 同步读写。

**② 顶栏「保存配置」按钮**：`index.html` 的 `.menubar` 里「导航与路线」之后加 `#save-config`；`bindUI()` 绑 click →
`savePrefsNow()`（**清掉 400ms 防抖 timer 后立即 `flushPrefs()`**）→ 按钮变「已保存 ✓」并 disabled，1200ms 后复原。

**③ 标记浮窗常驻 + 关闭按钮 + 加入途径点 + 途径点拖动排序**：
- 浮窗**不再自动消失**：删掉原来的 8 秒 `markerPopTimer`，`hideMarkerPopup()` 也不再清 timer；
  只有「点别的标记（`showMarkerPopup` 开头先 `hideMarkerPopup()` 切过去）」或「点浮窗右上角 `.marker-pop-close`（×）」才收起。
- 浮窗结构重写：`.marker-pop-head`（`.marker-pop-title` 标题 + `.marker-pop-close`）× 若干 `.marker-pop-row` + 底部 `.marker-pop-actions` 里的 `.marker-pop-add`「加入导航途径点」→ 点击调 `addRoutePoint(kind, name, item)`，
  name 取 `item.name || item.items[0] || KIND_LABEL[kind] || kind`（高资点没有 name，用第一个物品名当途经点名）。
- 途径点**拖动排序**：`makeRouteItemDraggable(li, routeIdx)` 用 HTML5 drag（`draggable="true"` + dragstart/dragend/dragover/drop），
  按指针落在目标行的**上半 / 下半**决定 `drop-before`/`drop-after`；`moveRoutePoint(from,to)` 里 `if (to > from) to -= 1;` 再 splice（**先扣自身位移**，否则拖动元素被重建会中断 drag）。
  **实时定位起始行不设 draggable**（它由 `routeFromPlayer` 决定，不能手动挪）。

**④ 钉选常驻搜索栏下方**：`index.html` 在 `#search` 与 `#search-results` 之间加 `#pinned-list`；`renderPins()` 用 `searchIndex(map)` 建 `byId`
  渲染「已钉选（N）」+ 每条 `.pinned-item`（`.pinned-hit` 定位按钮调 `focusEntry` / `.pinned-off`「取消钉选」调 `togglePin`）；无钉选或地图未就绪时整块 `hidden`。
  调用点：`togglePin()` 末尾、`applyUiPrefs` 的 `pins` 分支、`selectMap()` 里 `renderSearchResults()` 之后。

**⑤ 高资子类拆「其他高价值」为「情报」+「蓝色文件夹」（共 9 类）+ 显卡换实拍图**：
- `VALUABLE_CATS` 去掉 `other`，改成 `intel`（`/情报/`）与 `folder`（`/文件夹|材料/`），共 9 类。
  **顺序敏感**：物品名「情报文件夹」同时含「情报」和「文件夹」，`valuableCatsOf()` 对**每个物品名只取第一条命中的类**，所以 `/情报/` 必须排在 `/文件夹|材料/` 前。
- `valuableCatsOf()` 未命中不再补 `other`，返回空数组；兜底放在 `valuableUnionSpec().where`：`if (!cats.length) { return on.length > 0; }`
  （**未命中任何子类的点在任一子类开启时照样画**，避免上游新增物品名后凭空消失）。
- 图标：`iconize.py` 新增 3 条 JOBS（源图在 `D:\personal\trae\02-塔科夫\ui图标`）：`val-gpu.png`（显卡实拍，替换原手画 SVG）、
  `val-intel.png`（情报）、`val-folder.png`（覆盖旧蓝色文件夹图）；删掉 `SIGN_ICONS`/`SIGN_COLORS` 里的手画 `valuable_gpu`。
  `ICON_PNG` 加 `valuable_gpu` / `valuable_intel`；`VALUABLE_ICON_RULES` 在 `/文件夹|材料/` 前插 `[/情报/, "valuable_intel"]`。
- 数据：`tools/fetch_data.py` 的 `HIGH_VALUE_ITEMS` 加「情报文件夹」，`SCHEMA` **7 → 8**，离线重跑（`data/maps.json` len = 2051107，schema = 8）。
  校验：73 个不同高资物品名**全部能被 9 类规则命中**（unmatched = 0）。

**默认开关**：高资默认仍只开 **比特币 / 私酒 / 显卡 / 钥匙卡类**（4 个），其余 5 个子类默认关。
**配置白名单**：`tools/config.py` 的 `_normalize_ui()` / `merge_ui()` 加 `label_scale`（钳 0.5–3.0）/ `label_alpha`（钳 0.0–1.0），新增 `clamp_label_scale()`/`clamp_label_alpha()`；
`tests/test_config.py` 补 4 条测试 → 全量 **571 passed, 1 skipped**。
**文档**：`README.md`（9 子类 / 常驻钉选 / 浮窗常驻 + 关闭 + 加入途径点 / 地名滑条 + 保存配置 / schema 8 / 图标 219 / 测试 571）、`docs/USAGE.md`（子类「情报 / 蓝色文件夹」、浮窗不再自动收起、钉选常驻、途经点拖动排序、导航段纠正为「同层沿道路」）。

**发布**：本轮改动已按功能分 5 批提交并推送（`3582839` → `1bc9b7c`），三件套已重新打包并替换 GitHub Release v0.1.0 的资产（详见 §9）。

---

### 6.21 第十六轮：局域网访问（跨机自动截图）+ 物品资料库 + 配装视图 ★（第十六轮）

用户当轮诉求分两条：**(A) 解决「自动截图不生效 / 不自动切图」**、**(B) 按「先整合物品资料库，再做配装」的顺序落地配装功能**（见 `docs/loadout-gun-simulator-roadmap.md` 阶段一 §A→§F）。

**① 局域网访问（解决跨机自动截图）**
- **根因**：自动截图靠 Windows `SendInput` 模拟按键，**只能打进本机的前台窗口**。用户场景是「游戏跑在另一台机（游戏目录是 UNC `\\JJPC\...`）」，工具在别的机器上 → `SendInput` 物理上打不到游戏窗口，该功能**跨机不可达**，不是 bug。解法是让工具**监听 `0.0.0.0`**，让用户能在**游戏那台机上**打开界面（同机前台，模拟按键才有效）。
- `tools/serve.py`：`DEFAULT_HOST` + `create_server(..., host=...)`；`url_for(host, port)` 把 `0.0.0.0` / `""` 映射回 `127.0.0.1` 显示；新增 `lan_address()`（纯 `socket` 探测本机非回环 IPv4，**不发包**）、`url_for_lan(port)`、`lan_hint(host, port)`（只在监听 `0.0.0.0` 时给提示，含「防火墙放行」提醒）；新增 `is_network_path()` 识别 UNC 路径（好提示「模拟按键跨机无效」）；CLI 加 `--host`。
- `tools/config.py`：`HOST_CHOICES = ("127.0.0.1", "0.0.0.0")` / `HOST_DEFAULT`，新增 `clamp_host()` 收敛白名单（非法值回落回环）。
- `tools/launcher.py`：小窗加「允许局域网访问」勾选 + 显示局域网 URL + 防火墙提示。

**② 物品资料库（`tools/fetch_data.py`）**
- 新增物品资料库段：常量 `ITEMS_URL = https://json.tarkov.dev/{mode}/items`、`ITEM_ICON_URL = https://assets.tarkov.dev/{id}-icon.webp`、`ITEMS_SCHEMA = 1`、`ICON_WORKERS = 16`、`ICONS_DIR = ROOT/"assets"/"icons-items"`。
- `build_items()` 把上游物品压缩成精简字段（`_compact` 丢掉 0/None/空容器）：`n` 中文名 / `pt` 类型 / `ic` 有无图标 / `gw,gh` 尺寸 / `w` 重量 / `p{b,l,a,lo,hi}` 价格档 / `slot` 装备槽（`GEAR_SLOT_TYPES`：`ItemPropertiesHelmet→helmet`、`ArmorAttachment→face`、`Glasses→glasses`、`Armor→armor`、`ChestRig→rig`、`Backpack→backpack`）/ `pen{t,s,e}` 减益 / `cl` Class / `dur` 耐久 / `cats` / `hb` / `conflict` / `mod{e,r,a}` / `slots[]`（配枪槽位）。`build_gunslots()` 出 163 把枪 / 497 套预设（阶段二用）。`_download_icons()` 并发拉 webp。
- `run()` 支持「只补物品」捷径（`_items_only(args)` / `_merge_sources()` / `_now_iso()`），`data_ready()` **保持 maps-only 语义**（地图数据就绪即不联网，物品资料库单独走）。
- **产物体积**：`data/items.json` 5480 件 / 3.8 MB；`data/gunslots.json` 163 枪 497 预设 / 0.36 MB；`assets/icons-items/` 5480 个 webp / 14.9 MB。**这些体积会明显撑大打包产物**（见 §0 发布包行）。

**③ 配装视图（前端）**
- `tools/config.py`：`VIEWS = ("map","loadout","gun")` / `VIEW_DEFAULT`、`GEAR_SLOTS`、`SENS_DEFAULT/MIN/MAX = 0.5/0/1`、`clamp_sens()`（**0 合法**、布尔挡掉、非数/NaN 返回 `None`=未填）、`_normalize_gear()`（**只保留真给过来的槽**，避免与 `merge_ui` 逐槽语义冲突）；`_normalize_ui` 纳管 `view`/`loadout`/`sens`，`merge_ui` 逐槽合并。
- `index.html`：顶栏加 `#view-switch`（三个 `.view-btn[data-view=map|loadout|gun]`，`role=tab`）；原 `aside#sidebar` + `main#stage` 包进 `<div id="map-view" class="view-pane">`；新增 `<section id="loadout-view" class="view-pane view-3col" hidden>`（第一栏 6 槽 + 汇总 + 灵敏度；第二栏减益；第三栏大表）与 `<section id="gun-view" class="view-pane gun-placeholder" hidden>`（阶段二占位）。
- `style.css`：`.view-switch` / `.view-btn[aria-selected=true]`、`.view-3col`（`grid-template-columns: 300px minmax(320px,1fr) minmax(420px,1.4fr)`）、槽位卡 `.gear-slot*`、`.gear-summary`、`.gear-sens`、减益条 `.pen-row*`、通用大表 `.tbl*`（表头 sticky、`--tbl-cols` 由 JS 注入、`.tbl-scroll{overflow:auto}` 兜底横向滚动）、`.gun-placeholder`。视图互斥靠全局 `[hidden]{display:none!important}`。
- `app.js`：`state` 加 `view/loadout/sens/items/itemsPromise/itemsError/gearCatalog/gearTable`；`boot()` 收齐新 el 并 `bindLoadoutUI()`；`restorePrefs()`/`uiPatch()`/`applyUiPrefs()` 接入 `view`/`loadout`/`sens`（`ui.view` 不等才 `setView` 防自回环；`"sens" in ui` 判存在，**0 也合法**）。尾部新增一整段配装模块（约 30+ 函数）：
  - `setView(name,persist)`：切 `aria-selected` + `[hidden]` 互斥；进配装 `openLoadout()`（懒加载 `items.json`）；回地图且地图就绪时 `updateMetrics()`/`applyView()`/`renderOverlay()`。
  - `ensureItems()`：**懒加载** `data/items.json`（失败可重试）；`gearCatalog()` 缓存带槽位的装备清单（470 件）。
  - `createTable(host, opts)`：**通用分片大表**（sticky 表头 + 点列排序 + 搜索 + 下拉过滤 + **每片 200 行** + 滚动到底追加 + `rowSelected` 高亮），返回 `{render,setRows,refreshSelection}`。
  - 渲染：`renderLoadout`/`renderGearSlots`/`renderGearSummary`/`renderGearPenalties`（三条减益条按最大值归一）/`renderSensOut`（**推荐灵敏度 = 当前 ÷ (1 + 转身减益/100)**）/`syncSensInput`（`document.activeElement` 守卫，**不打断正在输入**）/`buildGearTable`（8 列，默认按名称升序）/`equipItem`（**再点同一件=卸下**）/`clearGearSlot`/`clearLoadout`/`afterLoadoutChange`/`persistLoadout`/`setSens`/`bindLoadoutUI`。
  - 图标：`itemIconUrl(id) = "assets/icons-items/" + id + ".webp"`；价格 `itemPrice` 优先 `avg(a)` → `last(l)` → `low(lo)` → `high(hi)` → `base(b)`；单位为 ₽ 并千分位。
- **ES5 约束**：`app.js` 全篇 `var` + `function`，无箭头函数 / 模板字符串 / `let`/`const`——新代码同样遵守。

**④ 测试与文档**
- 新增 `tests/test_fetch_data.py`「物品资料库」段 13 例、`tests/test_config.py`「配装视图偏好」6 例、`tests/test_serve.py` 静态断言 2 例（`data/items.json` 可服务且含带槽位装备、`assets/icons-items/*.webp` 返回 `image/webp`）→ 全量 **611 passed, 1 skipped**。
- `README.md`（视图切换 + 配装视图 + 目录树加 items/gunslots/icons-items + 测试 611 + 许可表加 items/图标来源）、`docs/USAGE.md`（新增「配装视图」整节 + 配置项表补 `ui.view/loadout/sens`）、本手册。

**⑤ 已用浏览器实测**（`python tools/serve.py`）：视图切换互斥、6 槽顺序、装备 / 卸下、汇总（件数 / 总重 / 总价 / 最高 Class）、三条减益、灵敏度补偿（0.4 → 0.412，减益 -3.0%）、大表排序 / 搜索 / 分片（200 → 400）、清空、`localStorage` 与 `%APPDATA%\EFTMap\eftmap.config.json` 的 `ui.view`/`ui.loadout`/`ui.sens` 落盘、刷新后停在配装视图、切回地图重排正常、console 无 error。
- **未做**（用户当天睡觉，明确「不打包、不发 Release、不打断」）：**未重新打包三件套、未发 GitHub Release**；**配枪视图仍为占位**（阶段二：`data/gunslots.json` 已就绪，待做槽位树 + 配件大表 + 实时属性面板）。

**遗留 / 待用户半夜后决定**：① 三件套是否重打包（新增图标 14.9 MB 会显著变大，可考虑只把 `assets/icons-items` 打进「配装可用」的版本、或压缩图标）；② 配枪视图是否现在做。

---

## 7. 前端要点（改 `app.js` 前必读）

- **图层开关表** `LAYER_SPEC`：按 6 组组织（撤离点 / 转移点、物资、出生点、钥匙与门、危险区域、其他），每项 `{ key, label, kind, where, dot, icon?, badge?, master?, sub? }`。`DEFAULT_ON` 控制默认开哪几个；**14 类物资容器默认全开**；**高级资源点默认只开 比特币 / 私酒 / 显卡 / 钥匙卡类**（其余 5 个子类默认关）；其余只有撤离点、转移点、危险区、Boss、地名、固定武器默认开。
- **高级资源点子类**（第七轮建、第十一轮扩到 8 类、第十五轮拆「其他高价值」为「情报」+「蓝色文件夹」共 **9 类**）：`VALUABLE_CATS`（9 类，各带 `match` 正则，**`/钥匙卡/` 必须排在 `/钥匙/` 前**、**`/情报/` 必须排在 `/文件夹|材料/` 前**）+ `valuableCatsOf(item)` 判归属（**每个物品名只取第一条命中的类**；整体未命中任何子类时返回空数组，渲染兜底见 `valuableUnionSpec`）。「物资」组第一行是 `master:true` 的总开关 `valuables`，后跟 9 个 `sub:true` 的 `valuable_<cat>`。总开关状态由 `syncValuableMaster()` 从子类**推导**（半勾 = 只开了一部分），`syncLegendState()` 里**半勾也算「开」**。
  **渲染不能按开关逐个画**：`renderOverlay()` 里所有 `kind === "valuables"` 的 spec 都跳过，改用 `valuableUnionSpec()`（「所属类别 ∩ 已开启类别 ≠ 空」）整体画一次，否则同一点会在两行开关下叠两层。`enableLayersFor()` 必须过滤 `spec.master`（总开关不参与「打开某图层」）。
  **改子类划分只动 `VALUABLE_CATS` 一处**，`LAYER_SPEC` / `DEFAULT_ON` / 渲染都会跟着走（`DEFAULT_ON` 里记得同步 `valuable_<cat>` 的默认）。
- **图层开关的 change 监听必须挂在容器 `#layer-toggles` 上用事件委托**。图例 DOM 会整体重建，逐个 checkbox 绑定会丢监听 → 会出现「取消勾选后标记仍然显示」的 bug（已踩过，见 §8）。
- **图标尺寸在屏幕上恒定的机制**：底图缩放走 SVG `viewBox`（不用 CSS transform）；标记挂在 `g[transform=translate(...) scale(...)]` 上，图标内容再乘 `unit = 1/state.fit`（1 屏幕像素对应的用户单位）；同时把标记节点收进 `state.markerScaleNodes`，靠父级的 `scale(1/z)` 抵消，保证不随缩放变大变小。**新图标必须走同一套机制**。**「图标」滑条（§6.15）改的是这个恒定尺寸的倍数**：`updateCounterScale()` 里用 `iconScale()/state.z`，**绝不能**给 SVG 元素加 CSS `transform` / `animation`（会被栅格化）。**地名不在 `markerScaleNodes` 里**（第十一轮起）——它要**跟地图绑死**，随 viewBox 缩放等比变大变小，图标滑条管不着它（见 `renderLabels`）。第十五轮另加「地名」/「地名透明度」两个滑条：`renderLabels()` 把每个 `<text>` 记进 `state.labelNodes`（含基准 `size`/`stroke`，不含缩放），`applyLabelStyle()` **就地改 attribute**（`font-size`/`stroke-width`/`opacity`），**不重跑 `renderOverlay`**、也**绝不给地名加 CSS transform**。
- **选中高亮环**：对画图标的图层（`ICON_KINDS = ["containers","valuables","spawns","bosses","locks","btr"]`）统一按 ±10 屏幕像素外接；撤离点 / 转移点是 ±12（第十一轮 11 → 第十二轮 12，跟着放大的徽章走）。高亮环**必须是静态描边**，不能是动画。
- 物资图标：`LOOT_ICONS`（每类由 `body` / `mark` / `hole` / `thin` 等部件组成）、`lootIcon(group, unit)` 画地图上的、`lootIconSvg(group)` 画图例的（`viewBox="-8-8 16 16"`）。
- **图标素材（`ICON_PNG`）**：key → `assets/icons/*.png` 的贴图表。四个工厂函数（`lootIcon` / `lootIconSvg` / `signIcon` / `signIconSvg`）**开头都判断 `if (ICON_PNG[key]) { return pngIcon(key, unit) /* 或 pngIconSvg(key) */; }`**——命中就用 `<image>` 贴图，未命中仍走手画 SVG。**换图标只需往 `ICON_PNG` 加一行 + 放一张 64×64 透明 PNG 到 `assets/icons/`**；新 PNG 必须透明、居中、内容约占画布 86%（照 `tools/iconize.py` 的输出规格）。源图是**竖排图例**（一张图里多行）时，要在 `tools/iconize.py` 的 `JOBS` 里加 `band` 指定那一段，不能整图直接抠（`strip` 只取最左侧那一簇，会把上下行连起来）。
- **具体物品名 → 专属图标**：`KEY_ICONS`（中文名 → icon key 的**精确表**）。`valuableIconKey(names)` **按价值分层遍历 `VALUABLE_ICON_RULES`**（外层规则、内层扫物品名，命中即止；同层里该名字在 `KEY_ICONS` 里有专属实拍图就贴真图，否则用该层通用图标），末尾再兜底扫一遍 `KEY_ICONS`。**规则数组的相对顺序就是价值顺序**（`BTC → 私酒 → 显卡 → LEDX → 除颤 → 钥匙卡 → 钥匙 → 文件夹`），`/钥匙卡/` 在 `/钥匙/` 前——顺序错了就会出现「LEDX 点画成除颤器」「私酒点画成钥匙」这类图不对位的 bug（§6.16）。上锁的门「需要钥匙」行用同一个函数取图标（`inlineIcon()` 把图标塞进 HTML 文案）。**给某件钥匙配专属图 = 往 `ICON_PNG` 加一行 + 往 `KEY_ICONS` 加一行**，两者 key 名一致（`key_<物品id前8位>`）。
- **标记小浮窗**：`showMarkerPopup(map, kind, item)` / `hideMarkerPopup()` 建 `div#marker-pop`（HTML 元素，append 到 body、`position: fixed`），**定位在地图区左上角往里 12px**（`el.stage.getBoundingClientRect()`，不跟图标跑）；结构是 `.marker-pop-head`（`.marker-pop-title` + `.marker-pop-close`「×」）+ 若干 `.marker-pop-row` + `.marker-pop-actions`（`.marker-pop-add`「加入导航途径点」→ `addRoutePoint()`）。**第十五轮起不再自动消失**（删掉原来的 8 秒 `markerPopTimer`），只在点别的标记（`showMarkerPopup` 开头先 `hideMarkerPopup()` 切换）或点右上角关闭按钮时收起；`detailRows()` 是浮窗与左侧面板共用的信息行来源。`onOverlayClick` 里**所有标记都调它**（`locks` 也在同一个浮窗里显示「需要钥匙」+ 对应钥匙图标，见 §6.9）。**别把它改成 SVG 元素**（会触发栅格化变糊的老坑，见 §8）。
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
  **第十五轮起钉选项常驻搜索栏下方**：`index.html` 的 `#search` 与 `#search-results` 之间加 `#pinned-list`，`renderPins()` 用 `searchIndex(map)` 建 `byId` 后渲染「已钉选（N）」+ 每条 `.pinned-item`（`.pinned-hit` 定位 / `.pinned-off` 取消钉选）；无钉选或地图未就绪时 `hidden`。重绘触发点：`togglePin()` 末尾、`applyUiPrefs` 的 `pins` 分支、`selectMap()` 里 `renderSearchResults()` 之后。
- **导航路线**：`state.route`（`{kind,name,x,z,y}` ≤60）+ `state.routeFromPlayer`。`routePoints()` 在勾了「从实时定位出发」且 `state.player` 存在时把玩家位置插到最前。
  **第十五轮起途经点可拖动排序**：`renderRoutePanel()` 里每个带删除按钮的途经点行调 `makeRouteItemDraggable(li, routeIdx)`（HTML5 drag，按落点上半 / 下半决定 `drop-before`/`drop-after`），`moveRoutePoint(from,to)` **`if (to>from) to-=1;` 后再 splice**（先扣自身位移，避免拖动元素被重建中断 drag）；**实时定位起始行不设 `draggable`**。标记浮窗底部的「加入导航途径点」按钮也走 `addRoutePoint()`。
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

## 9. Git 状态（第九轮已发布 GitHub v0.1.0；第十轮分 2 批、第十一轮分 3 批、第十二轮分 2 批 + 文档提交、第十三轮分 3 批、第十四轮分 4 批 + 提交表补录、第十五轮分 6 批已推送；**第十六轮改动尚未提交、未重打包**）

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

第十五轮（2026-10-19，**已提交并推送**）：

| 提交 | 内容 |
| --- | --- |
| `3582839` | 图标：新增显卡实拍图 + 情报 / 蓝色文件夹图（`iconize.py` 3 条 JOBS） |
| `4f1ac2a` | 数据：高资物品池加「情报文件夹」并离线重跑（schema 7 → 8） |
| `1f186fd` | 前端：高资子类拆「情报」+「蓝色文件夹」+ 地名滑条 + 保存配置 + 浮窗常驻 + 途径点拖动排序 + 钉选常驻 |
| `ed45390` | 配置 / 测试：`label_scale` / `label_alpha` 白名单 + 钳制函数（补 4 条单测） |
| `ee8fae0` | 文档：README / `docs/USAGE.md` / 本手册同步第十五轮 |
| `1bc9b7c` | 文档：修正图标素材计数（220 → 219，本轮净增 2 个 PNG，`ui图标/clean/` 同步为 218） |

**发布状态**：`release\EFTMap-Portable-0.1.0.zip`（22.8 MB，SHA256 `1483c027…cd512`）/ `EFTMap-AppWindow-0.1.0.zip`（22.8 MB，`b9f57ea3…49766`）/ `EFTMap-Setup-0.1.0.exe`（34.4 MB，`2560415f…b08470`）三件套已重建并用 `gh release upload v0.1.0 --clobber` 替换 GitHub Release v0.1.0 的三个资产，Release 正文同步第十五轮与新的 SHA-256。

第十六轮（2026-10-19，**改动已完成、尚未提交、未重打包**）：

| 提交 | 内容 |
| --- | --- |
| （待提交） | 局域网访问：`serve.py` 加 `host` / `lan_address` / `url_for_lan` / `lan_hint` / `is_network_path` / `--host`；`config.py` 加 `HOST_CHOICES` + `clamp_host`；`launcher.py` 加「允许局域网访问」 |
| （待提交） | 数据：`fetch_data.py` 加物品资料库段（`build_items` / `build_gunslots` / `_download_icons` / 「只补物品」捷径）→ `data/items.json` / `data/gunslots.json` / `assets/icons-items/` |
| （待提交） | 配置 / 测试：`config.py` 配装持久化（`VIEWS` / `GEAR_SLOTS` / `clamp_sens` / `_normalize_gear`）+ 全部新增单测 |
| （待提交） | 前端：视图切换 + 三栏配装视图（`index.html` / `style.css` / `app.js`） |
| （待提交） | 文档：README / `docs/USAGE.md` / 本手册同步第十六轮 |

> **第十六轮未打包、未发布**：用户当天睡觉前明确「不打包、不发 Release」。`release\` 里的三件套仍是**第十四轮代码**的产物。

> **提交作者**：仓库里**没有** `user.name` / `user.email` 配置（既非 local 也非 global），历史提交靠环境变量写的
> `jjingith <imzjj1996@gmail.com>`。裸环境提交时要先 `$env:GIT_AUTHOR_NAME='jjingith'; $env:GIT_AUTHOR_EMAIL='imzjj1996@gmail.com';
> $env:GIT_COMMITTER_NAME='jjingith'; $env:GIT_COMMITTER_EMAIL='imzjj1996@gmail.com'`（或临时设置身份），否则 `git commit` 直接报 `Author identity unknown`。
> 另：PowerShell **不支持** `$(cat <<'EOF' …)` heredoc 写多行提交信息，要改用多个 `-m`。

**入库范围**：`data/`、`assets/maps/`（含 `assets/maps/tiles/` 120 张瓦片 PNG 约 6.2 MB）、`assets/roadnet/`（35 个路网位图）、`assets/icons/*.png`（219 个）、
`tools/`、`tests/`、`build/`、根目录 `index.html` / `style.css` / `app.js`、`AGENT_HANDOFF.md`、`docs/`。
**不入库**（`.gitignore` 已排除）：`dist/`、`release/`、`build-cache/`、`build/_work*/`、`eftmap.config.json`、`sounds/`、`*.spec`。

> 图标源图目录 `D:\personal\trae\02-塔科夫\ui图标` 在**仓库之外**，不属于本仓库；已整理成 `clean/`（218 个抠好的成品）+ `src/`（63 张 iconize 源截图）。

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

- **配枪视图（第六轮已实现）**：`#gun-view` 已是真实改装工作台——搜索 163 把枪 → 真实槽位树 → 合法候选表 →
  装 / 换 / 卸 + 冲突禁装 + 换父件清理失效子槽 + 实时重量 / 价格 / 人机工效 / 后坐力。
  内置参考预设来自 `data/gun-presets.json`（373 套可装载，25 套上游配件与槽位允许关系不匹配、标为未解，不猜测）。
  用户枪械预设存 `%APPDATA%\EFTMap\weapon-presets.json`，配装工作台的主武器 1 / 主武器 2 / 手枪槽通过
  `@wp:<预设 id>` 稳定引用选用；删除被引用预设时会明确提示，不会静默换枪。
  路线图见 `docs/loadout-gun-simulator-roadmap.md`。参考站 `db4tarkov.com`（只复刻功能、不拷贝代码 / 素材），数据取自 `the-hideout/tarkov-dev`。
- **物品资料库**：**已于第十六轮整合**——`data/items.json`（5480 件）+ `assets/icons-items/`（5480 个 webp），配装视图直接消费（见 §6.21）。
  前端**运行期不联网**，资料库只在构建期拉一次；价格是**构建期快照，非实时市场价**。
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
- 灯塔 / 森林 / 迷宫 / 码头是单层图，不显示楼层列表；码头没有撤离点与地名
- 多层图默认只显示主楼层；少数越界的点会被视图外扩最多 12% 容纳，越界过多的会被裁掉
- **自动截图只能对本机的游戏窗口生效**（第十六轮）：它用 Windows `SendInput` 模拟按键，**只能打进本机前台窗口**，跨机物理不可达。
  所以「游戏在另一台机」时必须**在游戏那台机上**打开界面（工具已支持监听 `0.0.0.0`，见 §6.21），不能只开在地图机上指望它给游戏发键。
- **配装价格是构建期快照**：`data/items.json` 里的价格来自构建期拉取，**不是实时市场价**，只用于配装时估量级。
- **配置是「按机器（用户目录）」共享的一份**：同时开多个浏览器窗口时，界面偏好（`ui.layers` 等）**后写覆盖先写**；页面本地还有 `localStorage` 兜底，所以离线勾选不会丢，但联网窗口之间不保证实时一致。前端只在**值真的变化**时才上报，日常用不出问题。
- **钥匙图标已补齐**：第五轮后上锁的门 187 个钥匙名**全部有专属图**（§6.9 遗留的 43 个退回项已清零）。高级资源点物品名中仍有 11 个走 `VALUABLE_ICON_RULES` 通用正则（BTC / 私酒 / **显卡（显示卡）** / LEDX / 除颤器 / 六色实验室钥匙卡——这些本来就有规则且已贴素材图 / 手画图，不是缺失；其中**显卡是唯一没有实拍素材、手画 SVG 的子类**，见 §6.16）。若以后 wiki 长图例又有新增钥匙，按 §6.9 / §6.10 的流程加：**严格整名匹配**算缺口 → 量 `band` → `tools/iconize.py` 抠图 → 登记 `ICON_PNG` + `KEY_ICONS`。

**当前工作树干净度**：**第十六轮改动全部未提交**（见 §9），改动文件为 `app.js` / `index.html` / `style.css` / `tools/config.py` / `tools/fetch_data.py` / `tools/serve.py` / `tools/launcher.py` / `tests/` / `README.md` / `docs/USAGE.md` / 本手册，外加新增的 `data/items.json` / `data/gunslots.json` / `assets/icons-items/`（5480 个 webp）。`build-cache/` 里另有一批早期诊断用的 `inspect_*.py` 临时脚本，属中间产物，可随时删（不入库）。

---

## 12. 关键文档索引

- 面向用户的完整文档：[README.md](file:///z:/personal/trae/02-塔科夫/eft-interactive-map/README.md)（功能说明、计数表、数据来源与许可、日志格式、配置项）
- 设计规格（含 M7 / M8 / M9 / M10 各轮决策记录与教训）：[2026-10-17-eft-interactive-map-design.md](file:///z:/personal/trae/02-塔科夫/eft-interactive-map/docs/superpowers/specs/2026-10-17-eft-interactive-map-design.md)
- 实施计划：[2026-10-17-eft-interactive-map-plan.md](file:///z:/personal/trae/02-塔科夫/eft-interactive-map/docs/superpowers/plans/2026-10-17-eft-interactive-map-plan.md)

---

## 13. UI 设计系统（R19.24 建立，后续开发必读）

- 规范：`docs/ui-system/design-spec.md`；现状审计：`docs/ui-system/audit.md`；组件清单：`docs/ui-system/component-catalog.md`
- 实现：`styles/design-tokens.css`（`--ui-*` 令牌）、`styles/ui-components.css`、`js/ui-components.js`（`window.GWUI`）
- 可交互样板：`http://127.0.0.1:8787/ui-showcase`（本地静态页，不联网、不含业务数据）
- **硬规则**：新页面只用 `ui-*` 组件 + `--ui-*` 令牌；禁止私有按钮/输入/表格/弹窗样式、裸十六进制色、裸字号、裸 `z-index`
- 浮层必须挂 `body`（`GWUI.dialog/menu/tooltip` 已内建）；用了 `GWUI.tooltip.attach` 的元素**不要再设 `title`**（会双提示）
- 组件类名可加"钩子类"（如 `tk-table`）以兼容既有测试选择器，但钩子类里**不得写视觉属性**
- 已迁移试点：任务模块「商人任务中心」（工具栏 / 表格 / 状态徽标 / 数据说明弹窗 / 模式列提示）
- 未迁移：弹药页两个弹窗、配枪、配装、校准器、任务树 / 详情 / 进度页——迁移顺序与风险见 `design-spec.md` §7.2
- 验收命令：`python tools/ui_accept.py --port 9791 --base http://127.0.0.1:8790`（含令牌一致性、组件状态、
  弹窗焦点归还、悬浮层不被裁切、1280/1680 无溢出、**所有请求必须同源**、截图）

---

## 14. R20.7 · 预设页按钮功能对照与插板策略（本轮）

- 对照文档（逐按钮表 + 实测数值）：`docs/r20.7-preset-parity/preset-buttons-parity.md`
- 取证工具：`tools/r207_cdp.py`（连接受控 Chrome，导航 / 取 aria / 点击 / 局部截图 / 跑 JS 片段）

**三条容易踩错的结论**（写进这里避免以后重新踩）：

1. **db4 的插板列只在逻辑宽 > 1236 时出现**。1080P 布局下护甲表根本没有 Front/Back/Left/Right，
   要先把站点切 1440P 并把窗口拉到 ≥1440 才看得到。`main.dart.js` 里 `width > 1236` 是硬判定。
2. **插板是「按护甲行各自记忆」，不是「跟着新护甲走」**。给 A 选前板、给 B 选后板，
   A 的后板仍保持原样。本地的 `plateStorageKey(slotId, armorId)` 语义与之相同，**没动**。
3. **picked / default / priority 是纯计算口径**，切回 picked 时用户挑的板必须原样还在。
   本地用 `equippedList()` 里的**虚拟行**实现，绝不写 `state.loadout`（有测试钉住）。

**本轮新增**

- `state.plateMode`（1 picked / 2 default / 3 priority）+ `#lw-plate-mode` 三段按钮（仅护甲/弹挂甲显示）
- `hardPlateSockets` / `autoPlatePick` / `autoPlatesFor` / `effectivePlate`：
  default = 防护等级优先、priority = 价格最低；**同款优先**（先取所有板位交集里最优的一款，整件护甲用同一款）
- 表格行内「移动·转身·人机」并入当前生效插板（对齐参考站行内会随插板变化）
- `state.lwSlots` + `#lw-slots`「板位数」筛选，选项**按真实数据生成**（本地只有 2 板 / 4 板）
- 排序器补 `kg` / `price`，`price` 无报价用 `1e15` 哨兵（升序垫底，不把缺价当最便宜）

**实测往返（6B43）**：picked `-9/-5.5/-7, 10.80kg` → default `-14.5/-10/-9, 21.10kg, 188,658₽`
→ priority `-11/-7/-8, 15.00kg, 121,298₽` → 切回 picked **完整恢复**。

**测试**：新增 `tests/test_r20_7_plate_mode.py`（12 项，含 node 真跑 autoPlatePick）；
`tests/test_r20_6_preset_parity.py` 里「3 个排序按钮」的写死断言改为「≥3 且键唯一」（因新增 kg/price）。

**既有失败（本轮未触碰）**：`test_r11_armor_grouping` / `test_r19_1` / `test_r19_5` /
`test_r19_11` / `test_r19_13` / `test_r6_gun_workbench` 共 6 项，原因都是「按字符串切代码段、
切完发现标记改名或位置变了」，与本轮改动无关，未修改、未跳过。

### 14.1 R20.7b 补丁（用户反馈：板位图标不该被清空）

- 板位显示拆成三态：`on`（穿着 + 有板，实线彩色）/ `kept`（**没穿但记录在**，点线 + 72% 不透明）
  / `default`（没挑过 → 默认插板**灰显占位**，虚线 + `saturate(0)` + 42%）。
- **`kept` 不能直接用 `on`**：R19.26 有硬契约「未装备的护甲不能报已安装」，
  `test_loadout_workbench.py` 的 U3 / T25.6 三处断言在守它。新状态既让图标还在，又不破坏语义。
- **去色用 `saturate(0)` 不用 `grayscale(1)`**：`test_r18_1_round.py` 有一条全局禁令
  `filter: grayscale(1) not in css`（R18.1 为面罩剪影立的），别去撞它。
- `autoPlatesFor()` 现在每行都调用（要算默认板占位），已加 `armorId|mode` 缓存。
- `default` / `kept` 格都可点击（default → 装默认板或换；kept → 先穿护甲再换）。

### 14.2 R20.7c 配装页右栏放不下（布局实测）

**病因**（实测，见 `docs/r20.7-preset-parity/layout-width-analysis.md`）：

- 右栏容器 `.tbl-scroll` 只有 **1039px**，护甲/弹挂表 21 列实测 **1613px**，溢出 **574px**；
- 溢出的 574px 几乎全部来自**九个内衬明细列**（每列 64px，共 **576px**）；
- `.tbl-scroll` 是双轴滚动，横向滚动条躺在 `scrollHeight=2033px` 的内容底部，
  正常浏览够不到 → 表现成「右侧列被裁掉」（可见到「脖颈内衬」为止，后面 7 列全不见）。

**参考站为什么不溢出**：db4 也是 ~19 列，但列宽压到 20–40px、名称列两行换行，
而且**根本没有内衬细分列**（内衬信息折进 Material / Eff Dur），832px 就装下了。

**修法**：`state.lwLinerDetail`（默认 `false`）+ 筛选条「内衬明细」复选框。
折叠后 21 → 12 列、表宽 **1037 / 容器 1039**，`scrollWidth == clientWidth`，溢出 0；
勾上可展开回 21 列。

**分层关键**：`gearColumns()` 永远返回完整 21 列（列定义/顺序是 T24、R11 测试钉着的契约），
折叠放在新的 `visibleGearColumns()` 里只做渲染层过滤。别把 filter 直接写进 `gearColumns`，
会同时打破 `test_r11_armor_rig_21_columns`、`test_r20_armor_rig_20col_assembly_static`
和 `test_slot_driven_model_dynamic` 里 T24 的内衬列宽断言。

### 14.3 R20.7d 像素级复刻（行高 52 + 名称列窄而双行）

参考站实测（1440P，CDP 语义节点 rect）：护甲行 `group` 高 **52**、插板格 **52×52**、
Name 列宽 **130**、名称单元格是**两行**（粗体短名 + 灰色全名）。

本地改动：

- `--lw-table-row-height` 40 → **52**（插板格用 `calc(行高 - 1px)`，自动跟成 52×52）；
- 名称列在**渲染层**（`visibleGearColumns`）钉到 `minmax(150px,170px)`，余量给最右的获取方式列；
- 名称单元格两行：`shortNameOf()` 从中文全名推导短名（**不能用数据里的 sn**——实测是
  `"545cdb... ShortName"` 这种占位串，而 items.json 已进 SHA-256 契约不能重建），
  规则是「截掉第一个中文括号前的内容，取连续英文/数字片段」。

**两个坑（写下来别再踩）**

1. **别用列宽版本号整批作废旧列宽**。`COLW_VERSION` 那版把「用户拖过的列宽优先」契约打破了
   （test_app_js_col_width_persisted_per_category + slot_model 的 U5/T24 四处断言挂），
   **已撤回**。现在只清配置里那条历史脏数据 `n=203`
   （服务端 `%APPDATA%\EFTMap/eftmap.config.json` 的 `ui.colw` + 浏览器 localStorage 的
   `eftmap.colw`，备份 `*.bak-r207`），代码层面不动持久化逻辑。
2. **CSS 有更具体的选择器压着**：`.tbl-row .tbl-cell[data-key="n"] > span` 带
   `white-space: nowrap`，会盖掉两行规则（computed style 显示 nowrap）。两行规则必须写成
   `... > span.lw-name-plain` 才压得住。

测试：`test_r20_7_plate_mode.py` 增到 21 项（含 node 真跑 shortNameOf）；全量 1445 passed / 6 failed
（仍是那 6 个预存在的字符串切段测试）。

### 14.4 R20.7e 像素级复刻（图标放大 + 防护区域扣黑底 + 内衬九列恢复）

用户三条反馈：图标太小、防护区域要统一扣黑底、**内衬属性不许删（要改成参考站那样）**。

- **防护区域扣黑底**：新增 `tools/r20_7_strip_zone_bg.py`，按亮度分档处理
  `assets/icons/zones/*.png`（<96 透明、≥150 提亮 1.35、中间调 alpha 过渡），
  原图备份 `assets/icons/zones-orig/`。改完是**白色护甲剪影 + 透明底**，与参考站一致。
- **图标放大**：装备图标 30 → 44px（`.tbl-icon`），防护区域 22 → 40px（`.lw-zone-ico`）。
- **图标格叠加**（参考站 Icon 格结构）：物品图上叠「顶部短名 / 左下材质徽章 / 右下耐久」，
  格内压 `rgba(16,20,24,.55)` 深色半透明（本地物品图是浅底，参考站是深底）。
- **内衬九列恢复常驻**：`lwLinerDetail` 默认改回 `true`；宽度按参考站的紧凑度重排
  （图标 52 / 名称 128 / 基础防弹 52 / 机动 76 / 插板 4×32 / 内衬汇总 84 / 内衬 9×32 /
  防护区域 52 / 重量 48 / 获取方式吃余量），固定宽合计 908px，**21 列一屏放得下不再溢出**；
  内衬格内容改成**两行**（等级 / 耐久，与参考站一致），表头缩到 9px。
- 列宽仍**只改渲染层**（`LW_R20_WIDTHS` + `visibleGearColumns`），
  `gearColumns` 与 `LW_COL_DEFAULTS` 一字未动。

测试：全量 1447 passed / 6 failed（仍是那 6 个预存在的字符串切段测试）。

---

## 15. R20.8 · db4 三页复刻 + 枫织客户端脱壳（本轮）

本轮两件事：**(A)** 对照 `db4tarkov.com` 的 `preset / ammo / gun` 做像素级 + 功能级复刻；
**(B)** 用 rea 脱壳 `tarkov-kaedeori-client`，把能复刻的地图 / 任务能力搬进来。

### 15.1 取证工具（新增，可复现）

| 工具 | 用途 |
| --- | --- |
| `tools/r208_unpack_asar.py` | Electron `app.asar` **只读解包**（`--list` 只看结构） |
| `tools/r208_scan_kaedeori.py` | 扫打包 JS 里的 URL / API 路径 / 中英文关键词 |
| `tools/r207_cdp.py`（既有） | CDP 取证：`nav` / `aria` / `shot` / `eval` / `click` |

**asar 格式两个实测坑**（工具里已规避，别再踩）：

1. **JSON 头没有长度前缀**。直接 `payload[4:4+n]` 会解出乱码；
   必须 `json.JSONDecoder().raw_decode(payload)`——尾部还有 4/8 字节对齐 padding，
   `json.loads` 整段会报 `Extra data`。
2. 数据区基址 = `8 + headerBuf 总长度`（本例 **3017812**），不是 `16 + payload 长度`。

### 15.2 弹药页复刻（对照 db4 `/ammo`）

参考站侧栏语义树实测（`role="Navigation menu"`，宽 320）：价格口径 3 段、
来源 4 段、only TraderLvl（复选 + 滑条）、metric/imperial、5 个武器类别分组、
4 组数值滑条。本地补齐：

- **侧栏重排**为参考站顺序：价格口径 → 来源 → only TraderLvl → 单位 → 口径分组 → 区间 → RANGE；
  宽度 252 → **300px**（参考站 320，本地表格列更多，取 300 兼顾两边）。
- **价格口径**（`amFilterState().priceMode`）：`lastPrice`→`lastLowPrice`、
  `avg24h`→`avg24hPrice`（都取自 `data/flea-prices.json`）；
  **`avg7d` 上游 tarkov.dev 不提供**，一律显示 `—` 并在侧栏底部说明原因（不编造）。
- **来源**（`f.source`）：MARKET / TRADER / CRAFT / BARTER，再点一次同一段即取消。
  `ammo.json` 的 `src` 实测只有 `trader / barter / none`——**没有 craft**，
  选中 CRAFT 结果为空并在 `am-note` 里如实提示。
- **only TraderLvl**：复选 + LL1–LL4 滑条，取 `items.json` 最低买入等级。
- **单位制**（`f.units`）：metric / imperial。初速 m/s↔ft/s、弹道下沉 cm↔in、距离 m↔yd，
  DROP 两个 tab 的列标题与 RANGE 下拉都跟着单位走。
- 表格 `Market` 列改名跟随口径；`Speed` 列带单位后缀。

### 15.3 配枪页复刻（对照 db4 `/gun`）

参考站工具条右端实测：`only FleaLvl` / `only TraderLvl` / `Trader level · PMC Setting`。
本地补齐（`gwViewState()` 新增 4 个字段）：

- `onlyFlea` + `fleaLvl`（跳蚤解锁等级 1–15，15 = 游戏内上限，等同不筛），
  复用 R20.6 的 `fleaLevelOf()`；**没有 `data/flea-levels.json` 时不静默放行**，
  明确提示并拒绝勾选（与配装页同一口径）。
- `onlyTrader` + `traderLvl`（LL1–LL4），复用 `traderMinLevel()`。
- 参考站的 PMC Setting 是 40×40 图标按钮（点开再选等级），本地改成同功能的行内
  **数值框 + 滑条**，少一次点击；未勾选时等级控件置灰。
- 注意：`el.gwTraderLv` 已被工作台「商人等级」占用（`gw-trader-lv`），
  新增的用 `el.gwTraderLvNum`，**别覆盖**。

**参考站 gun 页签组**（`Gunsmith(NEW) / TierMaker / Streamer / Variant / Saved`）：
`Streamer`（主播手工配装，需联网拉 CMS，离线做不到，**按钮 `disabled` 并写明原因**）；
其余四项见 **§15.8**——其中 `Gunsmith / TierMaker / Variant` 本轮已复刻，`Saved` 直接复用
本地既有的「枪械预设」弹窗（功能上等价且更全：可保存 / 载入 / 改名 / 删除）。

### 15.4 同心测距圈（来自枫织客户端，新增图层）

脱壳发现枫织客户端设置项原文：「在互动地图中开关 **100–400 米同心测距圈**」。
这个功能纯前端可算，已复刻：

- 新增图层 `range_rings`（**默认关闭**，符合「新增开关一律默认关闭」铁律），
  档位 `RANGE_RINGS = [100, 200, 300, 400]`。
- 半径换算 `svgUnitsPerMeter(map)`：`worldToSvg` 是仿射 `[a b c / d e f]`，
  x / z 两轴缩放可能不等（各图底图来源不同），**取两轴平均**，避免圆被拉成椭圆。
- 圆**不做反向缩放**（半径是真实地理距离，必须随地图缩放），
  描边用 `vector-effect: non-scaling-stroke` 保持线宽恒定；
  依赖 `state.player`，没定位时画不出来（正常行为，开关保持可勾选）。
- `renderOverlay()` 里 `spec.kind === "rings"` 要跳过通用点位渲染，
  由 `renderRangeRings()` 单独画（画在玩家之下）。

### 15.5 脱壳结论：地图 / 任务数据**不能**从它复刻

详细报告：`D:\personal\trae\02-塔科夫\逆向参考\tarkov.kaedeori\extracted\report\HANDOFF.md`

- ✅ **脱壳成功**：78 MB `app.asar` 完整解包（目录 6219 / 文件 12146 / 66.4 MB，无失败）。
  应用是 **Electron + React 18 + Vite**，v1.5.8「枫织梦境助手客户端」。
- ❌ **没有内嵌地图 / 任务数据**：「撤离」「刷新点」「钥匙」「Boss」在全部打包 JS 里
  命中 **0 次**；「任务」只有 7 次且全在快捷搜索的标签文案里。
- ⚠️ **数据在远端且需鉴权**：`/api/tarkov/item|task|docs/detail` 走
  `https://member.kaedeori.com`（要登录）。抓它既越权也无授权许可，
  且违反「运行期不联网」铁律——**不做**。
- ✅ **本地其实更全**：地图 13 张离线内置；任务三模式 PvE 499 / PvPS 462 / PvP 503 条
  + 攻略 + 商人 + 赛季，全都离线。`extracted/` 是中间产物，**不入库**。

### 15.6 本轮改动文件

`index.html`（弹药侧栏重排 + 配枪等级筛选组 + gun 页签组 `.gw-extra` + 三个抽屉骨架）、
`app.js`（弹药 4 组口径 + 配枪 2 组等级 + 同心测距圈 + Gunsmith/TierMaker/Variant 三组函数）、
`style.css`（`am-seg` / `am-traderlvl` / `gw-lvlgrp` / 同心测距圈 / 侧栏 300px / R20.8 GUNSMITH+TIERMAKER+VARIANT）。
新增 `tools/r208_unpack_asar.py`、`tools/r208_scan_kaedeori.py`、
`tools/build_gunsmith.py`（数据层）与生成物 `data/gunsmith.json`。

**测试**：全量 `pytest tests -q --ignore=tests/test_installer.py`
→ **1448 passed / 6 failed / 1 skipped**（2 分 4 秒）。
6 个失败仍是 §14 记录的**预存在**字符串切段测试，未新增。
⚠️ 直接跑 `pytest tests` 会因 `tests/test_installer.py` 导入 `tkinter` 失败而**中断收集**
（当前 Python 环境没有 tkinter），与本轮改动无关——绕开办法就是加 `--ignore`。

### 15.7 一个不要误判的现象：弹药侧栏「不见了」

`style.css:3668` 有一条 **`@media (max-width: 1100px)`**（第十二轮就有）：
窄屏下 `.am-workbench` 变单列、`.am-side` 的 `grid-column` 改 1、`grid-row` 改 2，
即**侧栏堆到表格上方**。
所以窗口 ≤1100px 时看不到「右侧栏」是**响应式设计**，不是 bug。
排查时注意：`getComputedStyle` 只看得到结果，**必须递归遍历 `@media` 块内的规则**
（`cssRules` 不会自动展开条件组），否则会误以为 CSS 没生效。

**要不要把断点从 1100 降到 ~1000**（让 1024–1080 的窗口也显示右侧栏）属于取舍：
本地表格有 20 列（约 1200px 固定宽），主区只剩 780px 会横向滚动；
参考站只有 11 列（约 832px）所以 704px 装得下。**本轮未改**，留给用户定。

### 15.8 gun 页签组补齐：Gunsmith / TierMaker / Variant（本轮新增）

参考站 `/gun` 顶栏右侧实测有 `Gunsmith(NEW) / TierMaker / Streamer / Variant / Saved`。
本地在 `.gw-extra` 里加了同组按钮，三模式（PvP / PvE / PvPS）共用。

**数据层**：`tools/build_gunsmith.py` 直接从**构建缓存原始任务数据**提取枪匠任务，
补回了构建后 `data/tasks/tasks.<mode>.json` 漏掉的 `buildAttributes`（10 项属性约束）与
`containsCategory`；并对每条必装配件用与前端 `buildTree()` 同规则的 BFS 递归求解出**装配链**
（前端可写入 `installed` 完成一键装配）。产出 `data/gunsmith.json`（schema=1，三模式各 30 条共 90 条，
紧凑格式，幂等 `--check` 通过；438 项空约束占位被剔除，86 个必装配件 BFS 展开后 100% 可达）。

**Gunsmith 抽屉**（`#gw-gspanel`，右滑）：左栏任务列表 `LV{等级} {任务名} / {枪械名}`，右栏要求详情。
- 三模式切换（存 `localStorage["eftmap.gsmode"]`）+ 搜索 + 一键装配 + 逐条校验。
- 一键装配：先 `selectGun` 装官方默认，再遍历 `must` 逐条 `gwGsApplyChain`（主链失败自动换 `alts`），
  再遍历 `cats`，缺失的用 `gwGsChainForCategory` **自动补装**（超出 db4 能力：db4 只列出要求）。
- 约束校验 `gwGsCheck`：用 `gunCompute()` 取当前属性，`recoil=recoilV+recoilH`，
  `effectiveDistance` 取 `gun-stats` 的 `eff`（**不是** `sightingRange`），`durability/height/width`
  本地无数据则标「无法自动校验」。实测 AKM：装 2 件必装配件 + 自动补装消音器，5 满足 / 1 未满足 / 1 无法校验。

**TierMaker 抽屉**（`#gw-tierpage`，五档拖放板）：`TIER_RANKS` 五档
`S #d0553f / A #e0913c / B #d8b23f / C #6fae5a / D #4a86b8`；HTML5 `draggable` 卡片，
5 个档位 drop 区 + 未分级池（拖回=取消）；档位存 `localStorage["eftmap.gwtier"]`。
刷新（重渲染）/ 删除（清空分级）两按钮可用，分享需联网故禁用。

**Variant 抽屉**（`#gw-varpanel`，右滑）：提示语 `All Variants from the gun include buy from Trader / Barter`，
按「跳蚤市场 / 商人购买 Buy / 以物易物 Barter」三段列出当前枪的全部获取途径。
数据现实：172 把枪只有 18 把带 `buy`、2 把带 `barter`；上游 855 条 barter 里奖励是枪械的仅 4 条且都是信号枪——
缺数据时面板如实写明（不编造）。面板开着时换枪 / 改装配，内容通过 `renderGunModeUI` 末尾钩子实时刷新。

**互斥**：Gunsmith 与 Variant 抽屉都贴在同一右滑位，`gwGsToggle` 与 `gwVarToggle` 互相关闭；
`Esc` 关闭各自面板。

**本轮新增 / 改动文件**：`tools/build_gunsmith.py`（数据层）、`data/gunsmith.json`（生成物）；
`index.html`（`.gw-extra` 页签组 + `#gw-gspanel` + `#gw-tierpage` + `#gw-varpanel`）；
`app.js`（esc / GS_MODES / GS_FIELD / GS_NO_LOCAL + gwGs* + gwTier* + gwVar* 三组函数 + 元素注册 + 事件绑定）；
`style.css`（R20.8 GUNSMITH / TIERMAKER / VARIANT 三段，锁在 `.gun-workbench` 作用域）；
`tools/r20_validate_data.py`（`gunsmith.json` 加入白/可选名单）；

**回归**：`pytest tests -q --ignore=tests/test_installer.py`
→ **1448 passed / 6 failed / 1 skipped**（约 1 分 53 秒），6 个失败仍是 §14 记录的预存在切段测试，未新增。
`node --check app.js` / `gun_builder.js` 通过；`python tools/build_gunsmith.py --check` 通过；
`python tools/r20_validate_data.py` → PASS（errors=0，2 条历史 meta.bytes warning，sha256 一致）。
**未改动**契约数据（`items.json` / `gunslots.json` / `gun-presets.json`）；**未 commit / push**；8810 服务保留。

### 15.9 弹药表对齐 db4 的 11 列 + 材质彩色徽章（本轮收尾，用户拍板「按 db4 来」）

用户指令原文：「你说的两点就按照 db4 来 db4 只有 11 列 那你也改成 11 列」。
含义：弹药表从本地原 21 列（多了 Icon/Market/Trader/Craft/Barter 来源列，且 DROP 被拆成 C1–C6 六列）
**严格对齐 db4 `/ammo` 的 11 列**；同时把配装页 / 枪械页的材质徽章从「首字母徽章」改成 **db4 同款按材质着色的彩色徽章**。

**db4 弹药表真实列（CDP 语义树取证结论）**：
`Caliber · Name · Pen · Dmg · ArD · Acc · Recoil · Frag · Speed · Ricochet · DROP(含 1–6 级穿透概率)`。
DROP 是含 6 个子值的**单列**（db4 计为 1 列），不是六列。

**改动 1 · `amColumnsFor()` 的 ballistics 分支重写为 11 列**（`app.js` ~17923 起）：
- 列由 `[amCalCol(), amNameCol()]` 起手，**删除** flea/buy/craft/barter 四个来源列与 icon 列；
- 数值列顺序固定为 `pen / dmg / ard / acc / rec / frag / v0 / ric`，表头 label 用英文（Pen/Dmg/ArD…），
  运行时由项目既有本地化层翻译成中文显示（口径/穿透/护甲伤害/精度/后坐力/破片/跳弹/DROP），**非误映射**；
- **DROP 合并为单列** `key:"drop"`（label `DROP`，width 152px，align center）：render 内
  `for (var lv = 1; lv <= 6; lv++)` 循环 6 级，调用 `amPenChance(r.pen, lvl)` 算穿透概率，
  子值 `am-drop-c` 按 `data-tone`（ok≥0.6 / warn≥0.3 / bad>0 / zero=0）上色，title 写明对应 AV（10/20/…/60）。
- 排序 `sortValue` 用 `amPenChance(r.pen, 1)`（1 级穿透概率），其余列用各自数值。

**改动 2 · 材质彩色徽章**（`app.js` ~4575、调用点 ~7806 与 ~8217）：
- 新增 `MATERIAL_COLORS` 调色板（塔科夫通用材质色板）：钢 ArmoredSteel=#8a8f96、铝 Aluminium=#b8c0c8、
  钛 Titan=#7f9cb3、芳纶 Aramid=#c9b458、聚乙烯 UHMWPE=#5b8fd9、陶瓷 Ceramic=#e0d8c8、玻璃 Glass=#5fb3b3、复合 Combined=#9b7bb3；
- `materialBadge(mat)` 改为返回中文短标签（芳纶/聚乙烯/复合/钛/铝/钢/陶瓷/玻璃），`materialBadgeClass(mat)` 返回 `mat-<材质键小写>`；
- 两处调用点改为 `mb.className = "... " + materialBadgeClass(...)`：枪械页插板条 `.lw-plate-mat`、配装页护甲图标 `.lw-ico-mat`。
- `style.css`：DROP 列样式 `.am-drop`/`.am-drop-c`，`.lw-plate-mat` 改圆角 pill，**全局** `.mat-*` 配色加 `!important`
  （原因：`.lw-plate-mat` 基础规则 specificity 0,2,0 会压过全局 `.mat-*` 0,1,0，且插板条在 `.gun-workbench` 作用域，
  故 `.mat-*` 必须放全局并 `!important`）。CDP 实测 8 种材质全部正确上色。

**改动 3 · 回归测试更新（不删弱旧测试）**：
`tests/test_r12_ammo.py::test_ammo_table_columns_and_sort_semantics` 原本硬编码旧 21 列结构
（断言 `'key: "c" + lv'` 与 `'for (i = 1; i <= 6; i++)'`），与新 11 列 DROP 单列冲突 → 改为断言
`'key: "drop"'` / `'for (var lv = 1; lv <= 6; lv++)'` / `'amPenChance(r.pen, lvl)'`，
保留对 `caln/n/pen/dmg/ard/acc/rec/frag/v0/ric` 十列 key 与 `searchKeys`/`amPenChance`/距离衰减的断言。
改前该用例失败使总数为 **7 failed**，改后回到基线 **6 failed / 1448 passed / 1 skipped**。

**验证**：CDP 9402（本地）截图确认弹药表头 11 列，DROP 单元格含 6 子值（如 `100 100 100 100 70 50`），与 db4 一致；
材质徽章两处 173 个全部正确上色；`node --check app.js` 通过。
**临时取证脚本 `_r209_*.js`、截图 `r209_*.png`、aria `r209_*_aria.txt` 已清理**。
**未改动**契约数据；**未 commit / push**；8810 服务保留。

### 15.10 空槽剪影：黑色 → 灰白 + 灰描边（R21.0，用户拍板「用 rea」，仅改剪影）

**用户两点**：① 配装左侧装备栏 UI 是否和 db4 具体布局不一样？（问答，未改）② 空装备栏从黑色剪影改成
灰白剪影 + 灰色描边（只改这一个，用 rea）。

**rea 取证（CDP 9401 db4 / 9402 本地，均 1440×900）**：
- 布局**确实不同**：db4 左侧是居中列（Headwear 顶 + Glasses/Face/Headset/shirt 簇左 + Armor+ChestRig 中 +
  Gun+Backpack 下 + 底部 FinalCost/Buy/Sell）；本地是「人物档案」网格风（头部剪影居中、槽位网格、武器槽在下、总计区）。
  本轮只答不问、不改布局。
- db4 空槽 = 深灰盒(#4a4a4a) + 更浅灰剪影；本地空槽 = **白卡(#fff) + 黑剪影**（R18.1 旧规格）。

**改动**：`tools/build_slot_placeholders.py` 的 `INK=(0,0,0)` 改为 `INK_FILL=(208,208,208)` 灰白填充 +
`INK_STROKE=(140,140,140)` 灰描边 + `STROKE_PX=7`；`render()` 重写：透明底画布先贴灰白内部（腐蚀主体），
再贴「主体−腐蚀主体」得到的**内描边**（贴着剪影内侧边缘，不悬空、不在凹角断开）。
离线重生成 10 张 PNG（仅用本地 `_src`，无联网）。
`style.css` 的 `.lw-sil` 背景由白兜层改为 `transparent`（白卡透出，剪影自带灰白+灰描边）；
`.lw-cell[data-state=empty]` 背景保持白卡（用户只要求改剪影）。
**注意**：首版写成「膨胀主体−主体」的**外描边**，用户反馈描边悬空且不连贯；已改为「主体−腐蚀主体」的**内描边**。

**回归测试更新（不删弱旧测试）**：`test_r18_1_round.py::test_placeholder_pngs_are_black_on_white` 与
`test_r18_2_round.py::test_gun_png_still_black_on_white` 原断言「纯黑主体」与新规格冲突 → 改为断言
灰白填充(亮度≥175) + 可区分灰色描边(亮度100~175) + 无纯黑像素 + 四角透明。`test_white_icon_*` 系列走
`assets/icons-transparent`（独立集合），不受影响。

**验证**：CDP 缓存清除后重载本地，空槽特写确认浅灰剪影填充 + 可见深灰描边，白卡上清晰可见；
`pytest tests -q --ignore=tests/test_installer.py` → **1448 passed / 6 failed / 1 skipped**（与基线一致，无新增）。
8810 服务 HTTP 200 且已服务新 PNG；契约数据未改；未 commit/push。

### 15.11 装备属性列对齐 db4 /preset（R22.0，用户「按 db4 来」逐类改列）

**用户指令**：「用 rea 对比 https://db4tarkov.com/preset 装备的属性列是不是有不同，就我目测现在每个种类的都有不同，改正！」

**rea 取证（CDP 9401 db4 `/preset`，Flutter 语义树 + 高清截屏，逐槽点开取列）**：db4 各槽属性列各异——
头盔 `Name|Mov/Turn/Erg|Expand(跳弹角)|Material(材质+毁损)|Eff(耐久/有效)|部位等级格|Zone|Deafening(听力)|Kg|Price`；
眼镜 `Name|MTE|Kg|Price`；耳机 `Name|Distance|Ambient|Dry|Resonance|Kg|Price`；面罩 `Icon|Name|MTE|Kg|conflicting items|Price`；
护甲/装甲胸挂 `Name|MTE|Front/Back/Left/Right 插板|Material|Eff|9 个部位等级格|Zone|Cap|SE|Slots|Kg|Price`；
无甲胸挂 `Name|MTE|Cap|SE|Slots|Kg|Price`；背包 `Icon|Name|MTE|Allowed|Excluded|Cap|SE|Slots|Kg|Price`。
**最大错配**：本地把「胸挂」套用护甲 21 列插板/内衬版式，但参考站无甲胸挂走 Cap/SE/Slots。

**改动（口径 A「按 db4 来」，`app.js` `gearColumns()` 逐类改写）**：
- **胸挂**改回参考站 Chest Rig 口径（Name|MTE|Cap|SE|Slots|Kg|Price），修错配；**armor** 走参考站 Armor 口径
  （Name|MTE|4 插板|Material|Eff|9 内衬|Zone|Cap|SE|Slots|Kg|Price）；其余逐类对齐（见 `r220-gear-columns-compare.md`）。
- 本地独有信息换参考站口径承载**不丢点**：基础防弹等级→分组主序（baseClGroupRank 保留）、获取方式→末列价格、
  冲突→整行标红、毁损→并入 Material 格（`材质 系数`）、基础耐久→并入 Eff 格（`有效/基础`）。
- 新增 **`seCol` 空间效率（SE = 容量/占用格）** 列；`matCol/effDurCol` 改为合并显示毁损/耐久（对齐参考站格）。
- 移除列定义后置的 `conflictCol/srcCol` 注入与 `baseClCol/linerSumCol` 主表用法（变量仍在，分组/渲染复用不删）。

**遗留（数据源约束）**：db4 的跳弹角(Expand)/听力防护(Deafening)两列上游 `items.json` 未采集该字段，
契约数据不重建、不编造，故本地省略——要真值需扩 `tools/fetch_data.py` 并重建数据（独立改动）。
末列 Price 未做来源红图标（参考站有），来源明细走价格悬停/详情。

**测试断言更新（不删弱旧测试，只改断言以匹配新列集）**：`test_r10_armor_table.py::test_r20_armor_rig_20col_assembly_static`、
`test_r11_armor_grouping.py::test_r11_armor_rig_21_columns` / `test_r11_helmet_column_set`、
`test_loadout_workbench.py::test_slot_driven_model_dynamic`（SLOT_MODEL_JS 的 T20/T22/T24 列集断言 + colOf 宽度）——
全部从「21 列 + 冲突/获取方式」旧契约断言改为参考站列集断言。

**验证**：`pytest tests -q --ignore=tests/test_installer.py` → **1448 passed / 6 failed / 1 skipped**（回到基线，
6 failed 为 §14 预存在切段测试）；CDP 9402 实测胸挂表头 = `名称|移动/转身/人机|容量|空间效率|槽位|重量|FLEA 价`、
护甲表 = 插板 + Material(材质+毁损)/Eff(有效/基础) + 内衬 + Cap/SE/Slots，均无 JS 报错。
契约数据（items.json 等）未改；未 commit/push；8810/9401/9402 服务保留。

### 15.12 跳弹角/听力防护两列 + 价格来源红图标（R22.1，用户「补充上」）

**用户指令**：「跳弹角(Expand)/听力防护(Deafening) 这两个你看一下 tarkov.dev 有没有，应该是有的，你补充上；
然后价格来源红图标你可复刻吗」。

**核实（联网查 json.tarkov.dev 上游 items 数据，即 `tools/fetch_data.py` 的构建期数据源）**：
上游 `properties` 实测含 **`deafening`**（112 头盔：High/Low/None）与 **`ricochetX/Y/Z`**（229 护甲/头盔/插板，
Z=跳弹角，单位度，取值 60/65/70/75/80/85，与参考站 Expand 列的 65°/75° 吻合；X/Y 为跳弹概率阈值）。
用户判断正确——数据在 tarkov.dev 有，之前只因 `build_items` 未采集而缺失。

**落库（不改契约数据 items.json）**：因 items.json 已进 SHA-256 契约（app.js 既有注释「items.json 已进 SHA-256
契约，不能为了改这个字段重建整份数据」），且有 `flea-prices.json` 独立文件先例，新增 **`data/item-extra.json`**
（独立文件，`{id: {df, rc}}`）承载跳弹角/听力防护，**items.json 一字未改**（SHA-256 契约、hash 测试全保持）。
`tools/fetch_data.py` 构建期同步生成 `item-extra.json`（`_build_items_stage`，与 items.json 同源 raw_data）。

**呈现（app.js）**：
- `ensureItems()` 加载 `item-extra.json` 并把 `df`/`rc` 合并进 item 记录（`rec.df`/`rec.rc`），缺文件不阻塞。
- 头盔列集（对齐参考站 db4 Helmet）：`名称 | 移/转/人机 | 跳弹角 | Material | Eff | 防护区域 | 听力防护 | 重量 | 价格`。
  新增 `expandCol`（跳弹角=rc.z，悬停给 X/Y 概率阈值）、`deafCol`（听力防护 High/Low/None，着色）。
- **价格来源红图标**：末列价格格内价格数字 + 来源小图标（红底红边徽标 `.lw-price-src`，悬停来源明细），
  复刻参考站末列 Price 的红来源图标。

**测试断言更新（不删弱旧测试）**：`test_r11_armor_grouping.py::test_r11_helmet_column_set` 补 expandCol/deafCol；
`test_loadout_workbench.py` T22 头盔列键改 `n,pen,rcz,matLabel,effDur,zoneText,df,w,price`。

**验证**：`pytest tests --ignore=test_installer` → **1448 passed / 6 failed / 1 skipped**（回 §14 预存在基线，
items.json hash `ac81f0aa…` 未变、hash 契约测试全绿）；CDP 9402 实测头盔表 `跳弹角` 列显示 65°/70°/75°/85°、
`听力防护` 列显示 High/Low/None（着色）、末列价格带红色来源徽标。`fetch_data.py` 编译过 + 143 项测试全绿。
契约数据 items.json 未改；未 commit/push；8810/9401/9402 保留。

### 15.13 防弹胸挂→防弹衣槽 + 与胸挂互斥（R22.2 补完，用户追问「为什么没做」）

用户追问「防弹胸挂→防弹衣槽 + 与胸挂互斥 这个为什么没做」。上轮只做了互斥规则、路由留了半步
（怕改路由让 T19 槽位模型测试行查表落空）。本轮**改路由 + 同步更新 T14/T19 断言**（铁律「只更新断言」）。

**改动**：
- `inRootSlot()`：装甲胸挂（`isArmoredRig`，pt=ChestRig 且 aps[] 带护甲）归**防弹衣槽**（参考站
  Armor Armored Rig 口径），不再进胸挂槽。
- `conflictKinds()`：装甲弹挂 ↔ 普通胸挂（`isChestRig`）互斥（R22.2 已加）。
- `candidateSource()`：防弹衣槽来源注明「+ 装甲胸挂」；胸挂槽来源注明「排除装甲胸挂」。
- **T14 重写**：原「防弹衣↔装甲弹挂互斥」→ 新「装甲弹挂↔胸挂双向互斥」（含 4 个子检查）。
- **T19 重写**：槽位候选（防弹衣含装甲胸挂、胸挂排除装甲胸挂）+ 互斥场景 + 红态解除。
- T1（`test_slot_driven_model_dynamic`）护甲候选断言补装甲胸挂。

**验证**：`pytest tests --ignore=test_installer` → **1448 passed / 6 failed / 1 skipped**（基线）；
CDP 9402 实测：护甲槽来源「slot === "armor" + 装甲胸挂（参考站 Armor Armored Rig 口径）」共 108 件；
胸挂槽来源「slot === "rig"（排除装甲胸挂）」共 46 件，候选表无装甲弹挂。

### 15.14 Price 列商人头像修复 + 商人图标头像化 + tarkov.dev 全量数据工具（R23.0）

**用户报**：「price 栏为什么没有商人头像，tarkovdev 应该是有的」+「是否可以做个功能获取 tarkov-dev 的所有数据」。

**根因（真 bug）**：`priceCol.render` 只取 `row.trades[0]`。上游 `trade` 数组普遍把 `flea`
排在第一位（4626 件里 3955 件首笔是 flea），于是来源徽标永远只有购物车，
`t.level`（好感等级）与 `t.icon`（商人图标）永远不显示。数据本身是齐的：
2613 件有商人购买、779 件有兑换、忠诚等级 1–4 齐全。

**改动**：
1. `app.js` 新增 `pickPriceSource()`：按 `buy → barter → flea` 择优，价格列据此渲染
   「用户要的样式」——商人购买=小人、兑换=双向箭头、跳蚤=购物车，再接商人头像 + 罗马数字。
   跳蚤来源不再重复画「头像」（flea.svg 本身就是购物车，否则出现两个购物车）。
2. `LW_COL_DEFAULTS` 的 `price` 由 **94px → 148px**（10 处），否则「价格+图标+头像+罗马」
   溢出被裁（实测 scrollWidth 104 > clientWidth 93）。
3. `style.css`：去掉价格来源的外层红底红框（参考站是纯内联图标），头像改圆形+细边。
4. `tools/fetch_data.py::_trader_svg`：自绘商人图标从「圆形+缩写」升级为
   **头像式半身剪影**（圆底 + 头部圆 + 肩部弧 + 小缩写，按商人名稳定取色）。
   **仍不下载上游肖像**——许可复核（`assets/icons-traders/manifest.json` 的 licenseReview）
   确认 tarkov-dev 的 MIT 只覆盖源代码，游戏角色美术无可再分发许可，版权归 Battlestate Games。
5. 新增 **`tools/fetch_tarkovdev.py`**（构建期工具，零依赖）：把 `json.tarkov.dev` 当前公开的
   11 个数据集（items / items_zh / traders / traders_zh / barters / tasks / tasks_zh /
   maps / maps_zh / **crafts** / **hideout**）抓到 `build-cache/tarkovdev/{mode}/`，
   并落 manifest（url / bytes / sha256 / topKeys / records）。只写 build-cache（已 gitignore），
   **不改 `data/*.json` 契约**，运行期依然零联网。原有的 items/traders/barters/tasks/maps
   之外，本轮补齐了此前管线没有的 crafts（214 条）与 hideout（26 条）。

**用法**：
```
python tools/fetch_tarkovdev.py --list
python tools/fetch_tarkovdev.py                      # regular 全部
python tools/fetch_tarkovdev.py --mode all --summary # 两种模式 + 概览
python tools/fetch_tarkovdev.py --only crafts,hideout --force
```

**验证**：
- 回归 `pytest tests --ignore=test_installer` → **1448 passed / 6 failed / 1 skipped**（基线，无新增）。
- CDP 9402 实测：108 个价格徽标中 **106 个带头像、59 个带罗马等级**；
  特写确认「63,735 ₽ 🛒 / — ↔ ⬤PR IV / 170,000 ₽ 👤 ⬤PR IV / 101,080 ₽ 👤 ⬤PR III」。
- 全量工具实跑：11 份 / 29.3 MB / 32s，manifest 落盘；`--mode pve --only traders,crafts` 亦通。

**边界**：上游图片素材（含商人肖像、物品大图）依旧不抓；运行期不联网。

### 15.15 有效耐久改为「算出来的结果」（R23.1，用户「没显示计算结果」）

**用户报**：有效耐久应当是**纸面耐久 ÷ 损毁系数 的结果**，现在只显示「耐久数字 / 损毁系数」，没出结果。

**根因**：`effDurCol.text` 把两个原始数拼成 `"81 / 0.53"` 直接输出，等于没有做除法；
而 `effectiveDurability()`（本体 dur ÷ 系数）与 `linerBreakdown().eff`（Σ 每个内衬 dur×系数）
其实早就算好了，列里没用。

**改动**（`app.js`）：
- 新增 `effDurValue(row)`：优先取内衬口径 `liners.eff`（护甲/弹挂，逐块内衬各用自己的材质系数，
  混合材质也正确），否则取本体 `effDur`（头盔等），都没有 → `—`。
- `effDurCol` 改为只显示**计算结果**（单值，如 `1867`），并补 `sortValue` 让排序按真实值；
  两个原始数（纸面耐久 / 损毁系数）移到**悬停浮层**说明算法，信息不丢。

**验证**：
- 护甲：`芳纶 350 → 1867`、`芳纶 354 → 1888`（6B43）、`芳纶 165 → 880`；
  头盔：`90 / 0.4125 → 218`（Rys-T，与 db4 Eff 列一致）、`81 → 154`、`75 → 200`。
- 回归 `pytest tests --ignore=test_installer` → **1448 passed / 6 failed / 1 skipped**（基线，无新增）。

### 15.16 商人名改回英文 + 商人头像改用游戏素材（R23.2，用户决定）

**用户指出**：① 商人名为什么用机翻，直接用英文名；② 商人头像直接用游戏素材，理由是「所有互动地图类工具都用游戏素材，本项目的装备图标也是」，用途为学术研究、非商用。

**① 商人名**
- 根因：`app.js::traderName()` 走 `window.GWI18n.nameZh("trader", …)`，数据来自
  `data/i18n/traders.json` 的 `nameZh`，实际是机翻：`Prapor→大老板`、`Fence→篱笆`、`Skier→滑雪`。
- 改法：`traderName()` 直接返回数据里的英文原名，不再过 i18n；
  `data/i18n/traders.json` 的 `nameZh` 统一改为与 `nameEn` 一致并重跑 `tools/build_i18n.py`。
- 例外：`radio-station / btr-driver / ref / survivor` 这 4 位在 `items.json` 里存的就是中文
  （`无线电台 / BTR司机 / 竞技场裁判 / 幸存者`），而 items.json 是 SHA-256 契约不可改 →
  显示层按上游 `normalizedName` 确定性还原：`Radio Station / BTR Driver / Ref / Survivor`
  （`TRADER_SLUG_UPPER = { btr: "BTR" }` 处理缩写），不做机翻。

**② 商人头像改用游戏素材**
- 新增常量 `TRADER_PORTRAIT_URL = https://assets.tarkov.dev/{id}.webp`；
  `_download_trader_portraits()` 构建期增量下载到 `assets/icons-traders/portraits/{traderId}.webp`
  （16/16，248 KB），与既有物品图标 `assets/icons-items/*.webp` 同源同口径。
- `traderIconUrl()` 改为返回肖像路径；`traderIconFallbackUrl()` + `setImgFallback()` 提供
  「加载失败回落自绘 SVG」兜底（价格格与获取方式列都挂 onerror）。
- `assets/icons-traders/manifest.json`：`licenseReview` 保留为历史记录并标注 `status: superseded`，
  新增 `decision`（2026-10-30 项目所有者决定）与 `portraits` 清单（url/bytes/sha256），
  避免文档与现状自相矛盾。自绘 SVG 全部保留，作为兜底。

**验证**：
- rea 实测（截图 `r232_portraits.png`）：价格列头像为真实游戏肖像（圆形），
  形如 `170,000 ₽ 👤 ⬤Prapor IV`；浮窗文案为 `Prapor LL4（IV） · 解锁购买`；
  `ref` 显示 `Ref LL3 · 解锁兑换配方`；页内 108 个来源徽标中中文商人名 0 处。
- 回归 `pytest tests --ignore=test_installer` → **1448 passed / 6 failed / 1 skipped**（基线）；
  `test_loadout_workbench` 的 2 条旧断言（「一律自绘 .svg、不引用 .webp」）按新规格更新，
  并把 `traderEnglishFromSlug / traderIconFallbackUrl / setImgFallback / TRADER_PORTRAIT_DIR /
  TRADER_SLUG_UPPER` 补进 harness 提取清单。

### 15.17 Price 列按 db4 口径改正：显示**商人售价**而非跳蚤价（R24.0，用户「完全不一样」）

**用户报**：用 rea 再对比，Price 列完全不一样。

**rea 逐值比对得到的结论（这是根因，不是样式问题）**：
db4 `/preset` 的 Price = **商人直购价**，右侧罗马数字是**该商人的好感等级**；商人不出售时
该格只画一个**红色划掉的购物车**、不给数字。实测对账（同名物品，两边逐一核对）：

| 物品 | db4 | 改前本地 | 改后本地 |
|---|---|---|---|
| Eberlestock F4 终结者（虎纹） | `226,381 IV [3]` | 跳蚤价 `… ₽ 🛒` | **`226,381 IV`** ✓ |
| Gruppa 99 T20（茶褐） | `40,880 III [5]` | 跳蚤价 | **`40,880 III`** ✓ |
| Mystery Ranch SATL（叶绿） | `200,325 IV [1]` | 跳蚤价 | **`200,325 IV`** ✓ |
| 6B43 屏障-Sh / 5.11 Hexgrid 等 | 红划购物车（无数字） | 有跳蚤价 | **红划购物车** ✓ |

**改动**：
- `app.js`：`priceCol` 重写——`cheapestBuy(trades)` 取「`k="buy"` 且有正数价格」中**最便宜**的一条，
  渲染 `金额(无货币符号) + 小人图标 + 商人头像 + 罗马等级`；无 buy → `srcGlyph("unavailable")`
  （购物车 + 斜杠，红色），并在格子悬停里保留跳蚤价（信息不丢）。
  删除旧的 `pickPriceSource()`（按 buy→barter→flea 择优，口径已不适用）。
  新增 `fmtMoneyPlain()`（千分位、无 ₽）；`srcGlyph()` 增加 `unavailable` 分支并写 `data-kind`。
- `style.css`：`.lw-price-glyph` 改灰 `#7a7a7a`（`[data-kind="unavailable"]` 仍红）；
  头像改 **14px 方形 `object-fit: cover`、无圆环**；罗马数字改**深色** `#3a3a3a`
  （本地表是浅底——直接照抄 db4 的浅色字会看不清，这一点是本地适配，不是偏离）。

**已知差异（不编造）**：db4 价格后还有一个**青色 `[N]`**（F4 `[3]` / T20 `[5]` / SATL `[1]`）。
逐项排查确认它**不是**来源条数（这三件都只有 1 条 buy）、上游 `traders` 数据集也不含库存/限购字段，
故本地不显示该括号，不做估算。

**验证**：回归 `pytest tests --ignore=test_installer` → **1448 passed / 6 failed / 1 skipped**（基线）；
rea 实测截图 `r240b_local_price3.png`、整表 `r240b_local_full.png`。

### 15.18 价格列齐平 / 背包去重列 / 近战去重 / 左栏防护区域图 / 材质两行（R25.0）

用户一次报五项，逐项处理：

**① 商人头像、等级、渠道小标参差不齐**
根因：价格数字宽度不同（`63,735` vs `1.02`），后面的徽标被推着走。
改：`style.css` 给 `.lw-price-num` 定宽右对齐（`min-width:74px; text-align:right`），
「无商人出售」的红划购物车改 `margin:0 auto` 居中。rea 实测：11 个价格徽标全部落在 **x=1760**。

**② 背包多出图标列**
根因：背包 / 护面同时有独立 `icoCol` **和** `renderNameCell` 里的图标 → 每行两个图标
（实测背包 48 个图标格 + 47 个名称格内图标）。改：这两类去掉 `icoCol`，图标只留在名称格。
实测背包图标格 48 → **0**。

**③ 近战重复**
- `NKVD 芬卡工具刀` 上游有两个 id，除 id/shortName 外字段完全一致 → `candidatesOf` 近战分支
  按**名称**去重（27 → 26 条）。
- `“杀人鲸”推刃匕首` 经查**不是重复**：上游 `normalizedName` 是 `kasatka-push-dagger`，
  与「鲨鱼」的 `akula-push-dagger` 是两件不同物品；它只是**没有官方美术**
  （`iconLink` = `unknown-item-icon.jpg`）。故不删条目，改给一个中性「?」占位
  （`ICON_PLACEHOLDER` 内联 SVG），避免与「鲨鱼」看起来一模一样。

**④ 左栏人物轮廓 → 防护区域图**
- `LW_BOARD` 的 `mid` 格去掉固定 `deco:"torso"`，改成 `zoneDeco:"armor"`；
  头盔格新增 `zoneDeco:"helmet"`（位于头盔卡右侧）。
- 新增 `zoneDecoEl()`：读 `state.loadout[slot]` → `zoneIconFile(rec.z)`，换装时整块面板重建，
  因此天然实时跟随。无图时**文字降级**列出真实部位名（不拿别的组合的图冒充）；
  没装备时防弹衣位保留躯干剪影、头盔位不画。
- 区域图是白色线稿，浅色面板看不清 → 给深色底板（`#1e1e1e`）承托。
- 注：`ZONE_ICON_BY_WORDS` 里有 5 条是**登记的待补图**（r11 审计 `pending_user_icons`），
  不能删；缺失一律走既有 `onerror` 文字降级。

**⑤ 装甲材质改成两行**
第 1 行材质名带彩色底（复用 `.mat-*` 色板，与插板材质徽章同色），第 2 行纸面护甲值总和；
混材质时第 1 行并排多个色标。`linerBreakdown()` 增出 `matKeys` 供取色。

**验证**：回归 `pytest tests --ignore=test_installer` → **1448 passed / 6 failed / 1 skipped**（基线）；
`test_loadout_workbench` T22 的背包 / 护面列集断言按新规格更新（去 `ico`）。

### 15.19 头盔区域图 / 全列居中 / 价格多途径多行 + 行高 1.5 倍（R26.0）

**① 头盔防护区域在左栏变成文字，且位置不对**
- 根因一（为什么是文字）：`zoneIconFile()` 只查映射表、**不看文件是否存在**。SHPM 消防盔的
  组合 `头顶|后脑|面部|下颚|眼部|耳部|颈部` 在映射里有条目，但 PNG 属于「5 张待用户补图」，
  加载 404 → `onerror` 直接降级成文字，**子集回退没机会执行**。
- 根因二（位置）：`deco` 被当成 grid 的下一行追加，所以跑到卡片下方。
- 改法：
  - 新增 `zoneIconSubset()`：找一张「词集合是该装备区域的**真子集**、且覆盖最多」的图；
    `tryImage()` 改成三级回退 **精确图 → 子集图（附「＋颈部」标注）→ 文字**，
    只少画不多画，绝不把没防护的部位画成有防护。
  - CSS：`[data-cell="helmet"]` 改成两列 grid（`1fr auto`），区域图落到第 2 列 →
    **位于头盔卡右侧**；debuff 条仍占第 1 列第 2 行。

**② 除名称列外全部居中 + 调列宽**
- `.loadout-workbench .tbl-cell` / `.tbl-head .tbl-cell` / `.tbl-num` / `.tbl-mid` 全改 `center`，
  单列 `.tbl-cell[data-key="n"]` 保持 `left`。
- 列宽：`helmet.matLabel` 92 → 110、`helmet.zoneText` 88 → 150（文字降级要换行）；
  防护区域文字格允许 `white-space: normal`。实测溢出格 **0**。

**③ Price 多途径逐行 + 行高 1.5 倍**
- `priceCol.render` 重写：`priceSources()` 把 `buy / barter / flea` 全部列出，
  按 买 → 兑换 → 跳蚤 排序（同类按价格升序），每条一行，行内 = 金额 + 图标 + 头像 + 罗马等级。
- 字号缩小：行 10px、头像 12px、图标 11px、罗马 9px。
- `--lw-table-row-height` 52 → **78**（1.5 倍），插板格随变量自动变高。
- 实测：`Vulkan-5` 两行（`↔ IV` + `393,692`）、`BNTI LShZ-2DTM` 两行
  （`108,697 IV` + `73,924`）、单来源的仍是一行。

**验证**：回归 `pytest tests --ignore=test_installer` → **1448 passed / 6 failed / 1 skipped**（基线）；
`test_r7_visual_replication_rules`（全列左对齐 → 除名称外居中）与
`test_r20_7_plate_mode::test_row_height_matches_reference`（52 → 78）按新规格更新断言。

### 15.20 价格图标对齐 + 藏身处制作/任务标记 + XP 风格关闭键（R27.0）

**① 获取途径图标不在同一竖线**
根因：`.lw-price-line` 用 `justify-content: center` 且块宽自适应——跳蚤行少了头像/设施图标，
内容变窄就整体右移，箭头/小人/购物车自然错位。
改：`.lw-price-lines` **固定块宽 130px + `margin:0 auto`**，`.lw-price-line` 改 `flex-start`。
实测：护甲表 10 行、胸挂表全部行（含 craft）的 glyph 左边界**全部 x=1637**。

**② 新增「藏身处制作」获取途径**
- 数据（构建期，落 `data/item-extra.json`，不动 items.json 契约）：
  `_build_crafts_stations()` 读上游 `crafts` + `hideout`，产出
  `crafts = {产物 id: [[设施, 设施等级, 任务 id], …]}`、`stations = {设施: {n, icon}}`，
  并下载 26 张设施图标到 `assets/icons-hideout/`（`assets.tarkov.dev/station-{name}.png`）。
  实测 26 设施 / 203 种产物 / 26 张图标全齐。`fetch_data.py` 已接入，重建可复现。
- 前端：`tradeViews(rec, id)` 追加 craft 条目；`craftView()` 生成说明浮窗；
  价格行顺序 = **购买 → 兑换 → 藏身处制作 → 跳蚤**；
  行内 = 齿轮图标 + **设施图标** + 设施等级（罗马数字）。

**③ 任务解锁标记**
购买 / 兑换 / 制作只要有任务要求（`trade.u` / `craft.taskUnlock`），行尾加一个
**金黄色描边的问号**（`.lw-price-quest`），悬停显示前置任务名。
实测头盔表出现 8 个标记，如 `Altyn → 任务解锁：清空外围`。

**④ 关闭键统一成 XP 风格**
原先各模块各自一套（`.marker-pop-close` / `.route-del` / `.lw-modal-x` / `.lw-node-x` /
`.lw-ci-x` / `.gb-panel-x`，其中一处还没类名）。统一收口：加粗红色 ×（#c02626）+
1px 灰框 + 浅底 + 框内居中，hover 变浅红底。给漏类名的那颗补 `pin-x`。

**验证**：`pytest tests/test_fetch_data.py tests/test_loadout_workbench.py` 171 passed；
rea 实测截图 `r270_price3.png`（对齐）、`r270_craft.png`（齿轮+设施图标+II）、`r270_x.png`（关闭键）。

### 15.21 空槽占位改灰色轮廓线稿 + 左栏装备图高清化（R28.0）

用户两个诉求：①「左侧配装栏没选装备的时候，图案换成灰色的装备轮廓图，描边要精细」；
②「装备的图怎么都这么糊，能搞到高清的吗」。

**① 空槽占位：实心剪影 → 灰色细线轮廓**
- `tools/build_slot_placeholders.py` 的 `render()` 重写：
  取形态学梯度 `膨胀(主体) − 腐蚀(主体)` 得到**骑在真实轮廓线上**的细环，
  内部不填充（`FILL_ALPHA = 0`，白卡底色透出），线色 `#808080`，线宽 `STROKE_PX = 5.2` 输出像素
  （`OUT_SCALE = 4` → 约 1.3 显示 px）。
- 两个必须踩过的坑（都记进函数注释，避免重做）：
  1. **PIL 的 Max/MinFilter 在图像边界会退化**：主体紧贴包围盒时轮廓会出现虚线断口。
     先 pad `2*close_r + 2*ring_r + 6` 再滤波、最后裁回。
  2. **Alpha 阈值化留下亚像素细缝**（护甲下摆、耳机头梁）：膨胀会把细缝填成「实心短棒」，
     看起来像断线的点。先做闭运算（`CLOSE_PX = 0.6` 显示 px）并掉细缝，轮廓才能一条到底。
- 输出画布放大到卡片尺寸的 **4 倍**（如 armor 106×105 → 424×420），HiDPI 屏不再发虚。
- 缓存：文件名不变会被浏览器继续用旧图（实测改完仍显示实心块）→ `silSrc()` 追加
  `?v=<SIL_VER>`（`app.js` 的 `SIL_VER = "r28"`，以后再改占位图只改这一处）。

**② 左栏装备图高清化**
- 上游只有 `-base-image.webp` 是**透明底**（127–316 px）；`-image.webp` 虽 512×350 但
  **RGB 纯黑底**（实测角落 (0,0,0)），深色装备抠图必然失败（旧记录的两条失败路径仍成立）。
  故高清源取 base-image：253→240 轻微缩放，浏览器再把 240 缩到 106 显示 = 缩小采样，边缘锐利。
- 新增 **`tools/build_gear_icons_hd.py`**：读 `build-cache/gear-icons-src/`（已下好的 5355 张
  透明底原图，60 MB）**离线**生成 `assets/icons-hd/{id}.webp`（画布 256 / 内容 240 / WebP q90）。
  目标集合 = 配装根槽位装备 + 插板 + 枪械 + 近战（669 件；枪械/近战在 `cat` 上是 null，
  只按 `cat` 筛会整类漏掉，必须同时认 `pt`）。产出 **665 张 / 6.1 MB / 平均 9.4 KB**。
- 前端：新增 `GEAR_ICON_HD_DIR` / `gearIconHdUrl()` / `setGearIconHd()`，
  **仅左栏槽位卡片**改用 `setGearIconHd`（65–106 px 才需要）；表格行图标仍 64px
  （显示 24–28 px，缩小采样本来就锐利，没必要翻倍体积）。缺失自动回落 64px → 中性占位。
- 实测（rea 9402）：四张槽位卡 `naturalWidth = 256`、显示 76/106 px；
  头盔特写对比图 `r280_hd_compare.png` 里背带扣、盔沿、表面明暗明显更锐利。

**已知缺口（不编造）**：`HK 416A5 (RAL 8000)`、`FN P90（灾厄）`、`“杀人鲸”推刃匕首`、
`NKVD 芬卡工具刀（重发条目）` 这 4 件上游没有 base-image（`--fetch` 也取不到），
仍走 64px/占位兜底；其中“杀人鲸”本就是官方无美术的条目。

**验证**：回归 `pytest tests --ignore=test_installer` → **1448 passed / 6 failed / 1 skipped**（基线）；
`test_r18_1_round` 的占位图断言按新规格重写（线稿：墨迹 < 30%、包围盒内 < 55%、画布 = 卡片 ×4、
无纯黑），`test_r18_2_round::test_right_side_has_bulky_part` 的「墨迹密度」判据在线稿下失效，
改判「右端竖向展开幅度」。构建标记同步 `AM_BUILD = R19.30` / `index.html ?v=r19.30` / `serve.py rev`。

### 15.22 空槽占位改为「原图转素描滤镜」（R29.1，用户「就不能直拿原图套个转素描的滤镜制作吗」）

**用户反馈**：R28.0 的「结构素描」（人工构造外轮廓 + 内侧厚度线 + 中轴虚线 + 剖面线 + 排线）
太丑——那些构造线是画上去的几何线，与真实装备对不上。用户要求**直接拿原图套素描滤镜**。

**改动**（`tools/build_slot_placeholders.py`）：
- `_sketch_gray()`：用**局部对比度**提取笔触（素描滤镜的常见做法）——
  `base = 高斯模糊(灰度, r)`、`stroke = max(0, base − gray)`（只有比周围更暗的像素才算笔触）、
  `sketch = 255 − clamp(stroke × K)`。结构（织带、口袋、缝线、扣具）**全部来自原图本身**。
- **笔触限幅** `SKETCH_CAP = 150`：深色装备的局部对比度会爆到满值，不限幅就涂成一块黑
  （背包/防弹衣实测从「黑团」变成有内部结构的浅灰线稿）。
- **形状轮廓层** `OUTLINE_PX = 2.0` / `OUTLINE_ALPHA = 0.70`：取形态学梯度骑在真实轮廓线上。
  薄物件（眼镜/匕首/耳机）几乎没有内部明暗，只靠笔触会「几乎空白」，
  这一层保证外形永远可辨；不透明度压到 0.7 避免变成黑框。
- Alpha = max(笔触层, 轮廓层)，**纸面透明** → 白卡、选中蓝卡、深色卡上都自然，不露白方块。
- 参数（`radius 0.055 / gain 2.6 / cap 150 / outline 2px·0.7`）由 3 组对比图实测选出：
  旧值（gain 3.4 不限幅）暗部糊成黑团，新值在 1x 实际尺寸下八件装备形状全部清晰可辨。
- 缓存：`silSrc()` 的 `?v=` 参数从 `r29` → `r29.1`（同名 PNG 会继续吃浏览器缓存）。

**验证**：
- rea 实测：左栏空槽（眼镜/护面/耳机/主武器/手枪/近战）显示为铅笔线稿，形状与结构清晰；
  浏览器内主武器特写确认枪管/机匣/弹匣/枪托线稿分明；DOM 确认全部 `?v=r29.1` 生效、
  `naturalWidth` 分别为 252/424/1040/608（= 卡片 ×4）。
- 回归 `pytest tests --ignore=test_installer` → **1448 passed / 6 failed / 1 skipped**（基线）。
- 两条钉旧规格的断言按新规格更新（只更新断言，不删测试）：
  `test_r18_1_round` 的 manifest 判据改为 `style == "pencil-sketch"` + 必有限幅/轮廓层；
  `test_r18_2_round::test_gun_png_still_black_on_white` 的墨迹统计从「alpha > 200」
  改为「alpha ≥ 128」（纸面透明后几乎没有完全不透明像素）。

### 15.23 空槽占位重做：原生分辨率提笔触 + 铅笔灰线稿（R29.2，用户「不好看 重做」）

**用户反馈**：R29.1 的素描滤镜版「不好看」。

**根因（不是滤镜选得不好，是处理顺序错了）**：占位源图只有 **127–253 px**
（`_src/{id}.webp`），而 R29.1 的 `render()` 先把源图**放大到 4× 画布（424 px）**再提笔触——
细节在放大时就已被插值糊掉，之后无论用哪种算子提线，得到的都是「糊笔触」。
这跟 R28.0「高清装备图」那次的结论是同一条：**放大不会产生新细节**。

**改动**（`tools/build_slot_placeholders.py`）：
- **笔触在源分辨率提取**，最后只做一次等比放大（`OUT_SCALE` 4 → **2**，即卡片 ×2）。
  源分辨率下提线得到的才是真细节（护甲的口袋织带、胸挂的弹匣袋、背包的缝线都清晰可辨）。
- 笔触层增加**归一化 + 阈值 + 对比**三步：
  - 归一化到 0..255——不同装备对比强度差异极大，固定阈值会让深色件没线、浅色件全糊；
  - `SKETCH_FLOOR = 40`：低于此值视为纸面留白；
  - `SKETCH_CONTRAST = 1.6`：提对比，线条硬朗不发虚。
- 笔触颜色改为**铅笔灰 `SKETCH_INK = 110`（#6e6e6e）**，不再用「笔触灰度当颜色」——
  之前是把灰度图当颜色通道，笔触越重颜色越淡，视觉上发虚、像石膏。
- 轮廓层改用 **Alpha 边缘**（膨胀−腐蚀）而非放大后的掩膜，`OUTLINE_ALPHA = 0.60`。

**为什么不是 dodge blend**：经典 dodge 素描在**白底照片**上效果好，但占位源是
「透明底的深色 3D 产品图」，dodge 会把整个物体压成实心黑块（实测四组参数全是剪影）。
同理 XDoG 阈值化也会因大片区域响应接近而变成实心剪影。
最终选定「**局部对比度提笔触 + Alpha 边缘补轮廓**」——结构全部来自原图，且不会被大片区域吞掉。

**参数选定过程**：横向对比了 4 组算法 × 4 组参数（dodge / XDoG / 局部对比度 / 阈值化线稿）
的 1× 与 2× 实际尺寸渲染图，逐张看图后定下
`radius 0.055 / gain 2.6 / cap 150 / floor 40 / contrast 1.6 / ink #6e6e6e / outline 0.60`。

**验证**：
- rea 实测：左栏空槽（眼镜/护面/耳机/主武器/手枪/近战）显示为浅灰铅笔线稿，
  内部结构可辨、不是黑块、不是实心剪影；`?v=r29.2` 生效（`naturalWidth` = 卡片 ×2）。
- 回归 `pytest tests --ignore=test_installer` → **1448 passed / 6 failed / 1 skipped**（基线）。
- `test_r18_1_round` 的 manifest 判据按新规格更新：新增 `floor` / `contrast` / 笔触灰度区间，
  `outScale` 下限 3 → 2，并要求 manifest 记录 `nativeRes`（**笔触在源分辨率提取**这条关键约束，
  防止以后有人为了「更清晰」又改回先放大后提线）。

### 15.24 空槽占位改为「游戏内实拍卡面」（R29.3，用户「糊糊的不好看，能否获取到塔科夫游戏内的装备栏图案直接换上」）

**用户决定**：弃用自制素描/线稿，**直接采用游戏内空槽卡面**。用户提供两张游戏内截图
（`D:/personal/trae/02-塔科夫/逆向参考/游戏内截图.png` 3840×2160、`D:/personal/trae/02-塔科夫/逆向参考/游戏内截图2.png` 1185×2071）。

**做法**：从截图 2（游戏内「装备」页）按固定坐标裁出 10 个空槽卡面
（深色斜纹底 + 浅灰半透明装备渲染），居中裁到目标宽高比后缩放到卡片 ×2。
**不做二次绘制、不做阈值抠图**——实测过阈值分离：装备图案与斜纹底亮度接近（图案是
半透明渲染，亮度 48–79、卡底 16–47），阈值法必然失败；dodge/XDoG 也因「透明底深色 3D
产品图」特性压成实心块（R29.1/2 的教训）。直接裁切是最忠实做法。

**裁切坐标**（记录在 `manifest.json` 的 `extract` 块，可重建）：
- helmets 等 8 格取截图 2 对应卡位；
- `primary` 需避开画面下方的人物腿部剪影（游戏内角色预览透过半透明卡显示），
  收紧为 `(110,1045,700,1190)` 只取枪身；
- `helmet`/`armor` 同样右移避开左侧人物轮廓。

**配套改动**：
- `style.css`：`.lw-sil` 改 `object-fit: cover` + `background:#1b1b1b`（游戏卡是不透明实底，
  不再是透明线稿）。
- `app.js`：`SIL_VER` → `r29.3`（同名 PNG 强制换缓存）。
- 顺手修掉紧挨着的既有缺陷：**防护区域装饰图**（R25.0）是实心白色形状，在 30×36 小框里
  糊成白块 → 框放大到 78u×92u、`filter:brightness(0.5)` 压成中灰（≈116），
  与游戏卡浅灰图案同调，不抢注意力。

**测试断言迁移**（只更新断言，不删测试；4 个文件 7 条）：
- `test_r18_1_round`：规格从「透明底线稿」改为「游戏内实拍卡面」——判据改为
  整体偏暗（mean<55）+ 有亮度层次（std>4）+ 图案信号（亮于中位数+8 的像素 >8%）
  + 无大面积饱和纯黑/纯白；溯源从 `itemId/sourceFile` 改为 `source.file` + `extract[key].box`
  （裁切坐标必须落在源截图范围内，可重建）。
- `test_r18_2_round`：枪械三条（预设溯源 / 扳机护圈镂空 / 透明底）全部迁移为
  「直接裁切 + 不透明实底 + 图案有内部结构」口径。
- `test_r10_armor_table`：面部溯源从 `itemId` 改为 `extract.face.box`。
- `test_r19_4_round`：`RGBA 透明` 改为 `不透明实底 + 四角为深色卡底`。

**验证**：
- 回归 `pytest tests --ignore=test_installer` → **1448 passed / 6 failed / 1 skipped**（基线）。
- rea 实测：左栏 10 个空槽全部显示游戏卡（`?v=r29.3`、`naturalWidth` = 卡片 ×2）；
  主武器无人物剪影污染；防护区域图呈中灰不抢眼。

---

### 15.25 0.2.7.2：战局跟随 / 小地图跟随 / 小地图距离 / 自动截图 / OCR 撞名

用户实测两条老问题 + 本轮新增两条（自动截图、识别撞名）。版本号 `0.2.7.2`
（`tools/serve.py` 与 `tools/installer.py` 同步，有测试锁死）。

**#1 读取日志识别战局失效（自动截图也一起失效）**

根因：`LogFollower.start()` 在「此刻还没有日志目录」时直接 return，线程永不启动。
启动器先起后端、后写 `game_dir`；或游戏装在别处、默认探测延迟命中 → 监控彻底不开，
`phase` 永远不是 `start`，**依赖 `phase == "start"` 的自动截图也就一枪不发**。
修法：`start()` 不再早退，线程每轮 `poll_once` 经 `log_dir_getter` 动态重探目录。
`create_server` 传入的 getter 依次尝试：显式 `game_dir` → 配置 `game_dir` → `default_game_dir()`。

**#2 小地图锁死在街区**

新建 SSE `map` 通道：主窗口 `selectMap` 后 `POST /api/active-map {map}` → 后端记
`httpd.active_map` 并广播 `map` 事件；小地图窗口监听 `map` 做 `selectMap`（主窗口忽略，防回声）。
`/events` 首次连接会把当前 `active_map` 作为 `map` 事件**先推一次**，后开的小地图立即对齐。
另修：日志里带后缀的地图 id（`factory4_escape` / `labyrinth_pvp`）在 `resolveMapKey` 里
去后缀再查一次，否则「识别到地图但不收录」。

**#3 小地图距离档位不生效**

`onMiniRadius` 选档时若 `autoZoom` 开着，`applyMiniAutoZoomLevel()` 会强制把半径改回 100 米，
表现为「选了 25 米没反应」。修法：手动选距离 = 要固定半径 → 顺手取消 `autoZoom` 并写
`mini_auto_zoom:false`，避免小地图窗口在 `applyConfig` 里被自动缩放盖回去。

**#4 自动截图不生效**

是 #1 的下游（`phase` 卡住）。另做两处加固：

- 前台进程判定从「严格等于 `escapefromtarkov.exe`」放宽为 `is_game_process()`，
  同时接受 BattlEye 引导进程 `EscapeFromTarkov_BE.exe`；
- 被阶段门挡住时，若 `follower` 根本不可用，reason 改为「游戏日志未就绪…」并带上
  follower 的具体原因，界面上能一眼分辨「不在战局」与「日志没读到」。

**#5 识别时同名不同物无法区分（钥匙卡）**

根因：`data/ocr-item-names.json` 里 **3 件不同物品**的中文短名都是「钥匙卡」
（`5c94bbff…` TerraGroup实验室访问钥匙卡 / `5efde6b4…` 蓝色记号钥匙卡 /
`619cbf9e…` 钥匙卡收纳盒）。`_ocr_catalog` 的 `name_to_ids["钥匙卡"]` 因此有 3 个 id，
旧逻辑按「每格价最高」直接挑 → 白卡被显示成**收纳盒**的价（用户实测「明显不对」）。
修法三条：

1. `_ocr_name_collision()`：候选**按全名折叠**（同一物品重复录入不算歧义），
   长度 ≥2 → match 级 `ambiguous` + `candidates`；
2. 排序增加「全名以该显示名**结尾**」优先——短名通常是全名末段
   （`TerraGroup实验室访问钥匙卡` 命中，`钥匙卡收纳盒` 不命中），同档再比每格价；
3. `scan.is_ambig_price` 认 match 级歧义 → 浮窗**只画 ? 徽章不报价**（与弹药口径歧义同款），
   徽章可点开候选表（标题按来源显示「选择物品」/「选择口径」）；市场页识别结果同步标 ?。
   `scan.ambig_candidates()` 统一读 `price.candidates` 与 match 级 `candidates`。

**撞名审计**：新增 `tools/audit_ocr_collisions.py`，输出 `docs/OCR短名撞名清单.md` ——
全量 **608 组 / 1702 件**，其中价差 ≥3 倍的**高危组 191 组**（最夸张：「地图」36000×、
「武器箱」10932×、「狗牌」344×、「变电站」154×）。

**构建为什么一直失败（重要）**

前几轮把 `EndUpdateResourceW` 的 `ERROR_ACCESS_DENIED` 记成本机 D: 卷的过滤驱动，
还加过 Defender 排除项——**都不对**。实测在正常桌面会话下 C:/D: 都能正常写 PE 资源
（`EndUpdateResourceW` 返回 1，C: 2.2s / D: 0.3s）。真因是**构建进程跑在受限沙箱里**，
PE 资源写回被沙箱拦掉。另外两个脚本自身还有一个独立 bug：`$ErrorActionPreference="Stop"`
下直接调 `python -m PyInstaller`，而 PyInstaller 把正常 INFO 写到 stderr，PowerShell 会把它
当 `NativeCommandError` **终止脚本**——表现就是「在 PyInstaller 那一步失败，日志里只有 INFO 行」。
现已改成「参数数组 + `*>` 重定向到日志 + 只看 `$LASTEXITCODE`」。临时 Defender 排除项已移除。

**验证**

- 真实日志（`D:\Games\EFT\Logs\log_2026.11.02_…`）跑 `LogFollower`：
  `matching → map(factory_day / customs) → loading → start → end`，截图键同步到 `SysReq`。
- 新增 `tests/test_r270_name_collision.py`（8 条）；真实数据模拟「钥匙卡」：
  选中 `蓝色记号钥匙卡`（不再挑收纳盒），3 件候选全列出。

---

### 15.26 0.2.7.3：会员「显示已到期但功能可用」+ 赠送时长改为加到账号上

用户报（2026-11-15）：账号 `2092567443@qq.com` 显示已到期，但会员功能还能用；
怀疑是「注册赠送的免费时长」导致的，要求免费时长像充值一样**加在账号上**。

**查证结论（先纠正误判）**

- 服务端 `GET /v1/admin/accounts/detail` 显示：`member_status=active`、
  `member_expires_at=2027-11-14T05:59:43+00:00`、`plan=grant`；审计里有
  `2026-11-13` 兑换 365 天 → `2026-11-14 03:32` 撤销 → `05:59` 重新开通 365 天。
- 也就是说**账号本来就是有效会员**，功能可用是对的；错的是**显示**：
  `js/cloud.js` 的 `formatExpire()` 只输出 `MM-DD HH:mm`，把「2027-11-14」
  渲染成「11-14 13:59」，看起来像昨天就过期了 —— 这正是「显示已到期」的来源。
- 本机试用确实存在（`%APPDATA%\EFTMap\local-trial.json`，3 天，到 11-16），
  但它**当时并未生效**（文件里的 `email` 字段为空，`local_trial()` 返回 None），
  而且 `member_state()` 早已禁止「expired 被试用顶替」。所以它不是本次症状的原因。

**但机制确实是错的（用户诉求成立）**：注册赠送走的是客户端 `local-trial.json`
——账号本身仍是「未开通」，换台机器就没了，而且和账号是两本账。

**改动**

1. **服务端（`eft-cloud`，已部署到 47.96.68.209）**
   - 新增 `EFT_REGISTER_FREE_DAYS`（默认 3，`0` = 关闭）。
   - `verify_email` 在 `purpose=register` 的成功事务里调用
     `_grant_register_free_days()`，用与卡密兑换**完全相同**的口径
     `max(now, 原到期) + N 天` 写进 `member_expires_at`；永久会员不写到期时间；
     审计动作记为 `register_trial`（与管理员 `grant_member` 区分）。
   - 顺带修一个隐藏 bug：验证响应原本用**验证前**的 `challenge` 行算会员快照，
     刚赠送完也会回报 `member=false`；现在回读验证后的账号行。
   - 部署前对比过线上/本地差异（`config.py` + `service.py` 只有上述三处 hunk），
     备份为 `app/*.bak.20261115104703`，重启后 `systemctl is-active` = active、
     `/v1/redeem/tiers` 200。
   - 新增 `tests/test_register_free_days.py`（5 条：写入账号 / 叠加 / 永久不降级 /
     0 天不赠送 / 审计分开），云服务全量 **122 passed**；`conftest` 里
     `register_free_days=0` 以保持既有用例「刚注册=非会员」的前提。

2. **客户端**
   - `js/cloud.js`：`formatExpire()` 改为带年份（`YYYY-MM-DD`），徽标追加
     「（剩 N 天）」，新增 `daysLeft()`；trial 文案去掉「本机试用」。
   - `tools/cloud.py`：注册成功后不再写 `local-trial.json`；移除 3 处
     `set_current_trial_email` 调用。
   - `tools/config.py`：`member_state()` **只认服务端快照**，删除本机试用兜底；
     旧的 `local-trial.json` 不删、不再读取。
   - `tests/test_r273_member_trial.py` 按新契约重写（12 条），新增「徽标必须带年份」。
   - 客户端全量 `pytest tests` → **2416 passed / 5 skipped**。

3. **数据补救**：该账号欠的 3 天赠送已通过管理接口叠加到账号上
   （`2027-11-14T05:59:43Z` → `2027-11-17T05:59:43Z`，`plan=grant`，status=active）。

**遗留**：本机 `local-trial.json` 仍留在 `%APPDATA%\EFTMap`，已不参与任何判定；
如需清理由用户自行删除。
