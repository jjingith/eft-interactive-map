# R255 · 设置面板精简 + 会员门禁 + 全屏识别 + 数据获取节流

用户反馈（2026-11-12 16:00）：档位自定义太繁琐、注释太繁琐、会员交互不明、
免费版能切口径、要全屏识别、热键要能恢复默认、F5 自动拉数据费服务器带宽。

## 一、价格档位精简（前端）

- 每档从 8 个控件精简为两行：`档位N:`（+ 删）→ 第二行 `[颜色方框][上限价格(万，留空=无上限)]`。
- 字号 / 字体 / 外描边 / 内描边控件全部移除；`collectOcrTiers()` 保存时写固定
  兼容字段（sizeScale=1 / font=msyhbd / outer=true 黑外描 / inner=false），
  `scan.py` 渲染契约不变。
- 面板注释精简：「按热键框选装备，价格直接叠在装备上。」「按每件价格分档上色。」
- 标题「价格档位样式」→「价格档位」。

## 二、会员门禁

- **非会员点档位区域 → 小弹窗**（金色边提示「价格档位自定义是会员功能；
  免费版价格固定灰白色显示」，2.6s 自毁）；控件不再 disable（要能收到点击），
  用 `.is-member-locked` 半透明表达。
- **免费版浮窗固定灰白**：`scan.load_label_tiers()` 先查 `config.is_member()`，
  非会员一律返回 `_OCR_MEMBER_GREY_TIERS`（#b9c0c9 单档），配置里的彩色档位
  不生效。
- **免费版浮窗口径按钮禁用**：`render_control(..., member=)` 灰字画法；
  `OverlaySession.member = config.is_member(config_dir)`；WndProc 点击 mode
  按钮时非会员直接忽略（免费版拿不到服务器行情，四口径同值）。

## 三、全屏识别 + 恢复默认热键

- 热键行上方新增勾选框「全屏识别（不框选，直接识别整个屏幕）」
  → `ocrScan.fullScreen`（所有人可用）；`watch_native` 热键分支现读该配置，
  勾上 → 不弹选区，`_full_screen_worker` 抓整屏走同一条 recognize_region
  管线（有「全屏识别中…」提示、防重入），结果照常开浮窗。
- 热键按钮右侧新增「恢复默认」→ 一键回 `ctrl+alt+p`（防单键事故）。

## 四、数据获取 20 分钟节流（省带宽/省服务器）

- `prices_source.snapshot_for` 新增模块级节流：**每模式每 20 分钟最多打一次
  云端**；窗口内（无论 force 与否）返回缓存的云端快照 + `throttled:true` +
  `throttledRetryAfter` 秒数；没有缓存（服务刚重启）退内置快照并标 throttled。
- BFF `/api/price-snapshot` 支持 `force=1`（手动按钮用）；F5 / 自动加载永远
  不带 force → 20 分钟窗口内全是缓存，**云端带宽上限 = 每 20 分钟 1 次**。
- 市场页截止徽标左边新增「获取最新数据」按钮（`market.js manualFetch`）：
  前端 localStorage 预判 20 分钟 → 超频只显示红字「获取次数过于频繁（每
  20 分钟限一次，N 分钟后再试）」不请求；BFF 返回 throttled 也红字；成功后
  reload 刷新表格。红字 5s 自隐。

## 五、回归

- 新增 `tests/test_r255_settings_and_throttle.py` 16 条：云端节流（窗口内
  force/非 force 都缓存、满 20 分钟放行、非会员零云端调用）/ force 查询传递 /
  非会员灰白档 / render_control 会员形态与WndProc 忽略 / fullScreen 归一化与
  worker / 前端契约（档位精简、会员弹窗、全屏绑定、恢复默认、manualFetch）/
  R6 @keyframes 护栏复核。
- 全量：`build/_pytest_r255.xml`。BFF 与宿主已重启（16:21:39），线上实测
  force 二连击第二次即 `throttled:true`。
