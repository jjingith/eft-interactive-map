# R241 · 价格标签档位样式 + 价格识别设置面板

日期：2026-11-11 18:33–19:00 · 前置：R240（QQ 式速度）

## 用户需求（原话）

> 「显示的位置不对……只显示价格和单格价格 不要 kg 价格……两个价格显示在我大概
> 框蓝框的位置 然后字体大小和游戏内的装备上的字体一样大……菜单栏的小地图按钮
> 右侧 加个价格识别的按钮……免费用户就是能点开 但是只能设置截图键 会员用户才能
> 进行自定义设置 如按照价格档位设置字体颜色 每个档位都能设置字号 字体类型 字体
> 颜色 是否有外描边 外描边颜色 是否有内描边 内描边颜色 每个档位的区间设置」

## 四项落地

### ① 标签锚定装备名（版式重做）

- 价格**直接叠在 OCR 行框（装备名）左上角**，两行堆叠：第一行每件价（当前口径）、
  第二行每格价（0.78× 字号）；**公斤价移除**；
- 右/下溢出夹紧在区域内（R239 的"同行右移"版式废弃）。

### ② 字号与游戏文字一致——用实测，不用解包

- 各玩家分辨率 / UI 缩放不同，解包游戏字体配置得到的是**静态值**，套不到不同
  分辨率上；OCR 本身就量出了游戏文字在**该玩家屏幕上的实际像素高**（行框高 bh），
  `字号 = bh × 档位倍率`——这才是"和游戏文字一样大"的唯一可靠基准；
- 倍率上限放宽到 3.0（高分辨率不再被 26px 截顶），下限 0.5，绝对值钳 [9, 200]。

### ③ 价格档位样式（会员可自定义）

- 配置 `ocrScan.labelStyle.tiers`（默认 4 档）：
  `<5万 灰 #b9c0c9 / 5万–30万 白 #f2f2ee / 30万–100万 绿 #7fd48a / ≥100万 金 #f2c14e>`；
- 每档字段：`max`（区间上限，null=无上限末档）、`color`、`sizeScale`（字号倍率）、
  `font`（msyh/msyhbd/simhei/simsun）、`outer`+`outerColor`（外描边）、
  `inner`+`innerColor`（内描边）；
- 描边三层叠加绘制：外圈（stroke W 外色）→ 内环（stroke W-wI 内色）→ 字芯（本色）；
- 分档依据 = 当前口径的**每件价格**；价格未知落第一档（最素）；
- 归一化（config.py `_normalize_ocr_tier/_normalize_ocr_scan`）：颜色 hex 校验、
  倍率钳 [0.5, 3]、字体键白名单、字符串数字上限、≤6 档、按 max 升序且无上限殿后。

### ④ 价格识别设置面板（菜单栏）

- index.html 菜单栏「小地图设置」**右侧**新增「价格识别」入口（am-ocr / am-ocr-panel）；
- **截图热键**：所有人可改；宿主 watch 循环每 1s 轮询 `ocrScan.hotkey`，变更即
  Unregister/Register（日志"热键已切换为 …（即时生效）"），off/none=no 关闭；
- **价格档位样式**（会员）：动态档位行编辑器（上限万 / 字号倍率 / 字体下拉 /
  文字色 / 外描边开关+色 / 内描边开关+色 / 删除），≤6 档；改动走 `queuePrefs
  ({ocrScan: …})` → `/api/prefs` → config 广播回声回填；
- **会员门禁**：前端 `isMember()` → `.is-member-locked` + 全部输入禁用（热键除外）；
  服务端兜底：`config.merge_ui` 里非会员提交的 `labelStyle` **直接丢弃**（手搓
  请求绕不过 UI 锁）；`normalize()` 落盘前再收敛一遍。

## 实现清单

- `tools/config.py`：OCR_SCAN_DEFAULTS / OCR_FONT_KEYS / _normalize_hex_color /
  _normalize_ocr_tier / _normalize_ocr_scan；default_config、normalize、merge_ui 接入；
- `tools/scan.py`：render_labels 重写（锚定+两行+档位样式+_draw_styled 三层描边）；
  _font 改按字体键（_FONT_FILES）；_tier_for / load_label_tiers（模块级可单测）；
  OverlaySession(region, matches, config_dir)——重绘时现读配置（改档位下次
  识别 / 口径切换即生效）；watch 热键热更新（1s 轮询）；
- `index.html` / `app.js` / `style.css`：菜单块、el 注册、applyOcrSettings /
  renderOcrTierRows / collectOcrTiers / bindOcrSettings、applyConfig 回填钩子、面板样式。

## 验收

- `tests/test_r241_ocr_settings.py` 10 条：默认档位、脏输入归一（字符串数字/坏色/
  排序/钳位）、merge_ui 会员门禁（非会员剥离 / 会员可写）、_tier_for 选档（含
  价格未知落首档、1,000,000 边界）、渲染（两行无 kg、锚定 bbox、档位色、字号
  随 bh）、宿主/页面/config 契约；
- `tools/r241_accept.py` **9/9**：配置默认值、面板打开、4 档行渲染、热键可编辑、
  会员锁与 `account.member` 一致、热键改 f8 → 配置回声 → **宿主日志确认热切换**、
  无 JS 异常、热键还原 ctrl+alt+p；
- 演示截图 `build/_r239_overlay_demo.png`：价格叠在装备名上、两行、三档三色、
  无 kg、背景透明（styles 按 EXSTYLE 复验 0x80800A8/0x8080088 不变）；
- 全量见 `build/_pytest_r241.xml`。

## 边界

- 档位样式改动在**下次识别或口径切换**时生效（浮窗重绘时现读配置）；
- 内描边实现为三层叠加（外圈/内环/字芯），不是字形内缩的真"内描边"，观感接近；
- 档位 ≤6、倍率 [0.5, 3]、颜色仅 #RRGGBB（透明度由渲染层固定）；
- 热键格式非法时页面不校验（宿主 parse 失败保留原热键，日志可查）。
