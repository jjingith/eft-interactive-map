# 第十二轮 · 弹药页参考站审计记录（db4tarkov.com/ammo）

- 审计日期：2026-10-21
- 参考地址：`https://db4tarkov.com/ammo`
- 访问方式：真实 Chrome（CDP 端口 9224），通过 `Page.navigate` 打开页面，`Page.captureScreenshot` 落盘，
  语义树取自 `document.querySelector('flt-semantics-host')`（该站为 Flutter Web，canvas 渲染，
  常规 DOM 选择器不可用，交互以坐标点击 + 截图反馈驱动）。
- 截图文件：与本文件同目录的 `ref-ammo-*.png`。

## 1. 页面整体结构

- 顶栏：站点 logo / 导航（Ammo、Gun、Items、Maps 等）与语言切换；深色背景，主色为低饱和橄榄绿。
- 主区：左侧为弹药表格，右侧为固定宽度筛选栏（实测约 240 px，屏幕 1920×1080）。
- 表格顶部有 4 个页签：
  1. `BALLISTICS`（默认，总表）
  2. `DROP pen dmg`（按距离列展开穿透 / 伤害）
  3. `DROP bullet 3m`（按距离列展开弹速 / 下沉，带迷你曲线）
  4. `BALLISTICS graph`（散点图）
- 表格上方有搜索框与当前计数。

对应截图：`ref-ammo-initial.png`、`ref-ammo-table-left.png`、`ref-ammo-table-right.png`。

## 2. 列表列（BALLISTICS 页签）

按截图从左到右核对到的列：

| 列 | 语义 | 备注 |
| --- | --- | --- |
| Caliber | 口径 | 可排序；同口径连续排列 |
| （图标） | 弹药图标 | 小尺寸方形/细长弹体图 |
| Name | 名称 | 最宽列，左对齐 |
| Market | 跳蚤市场价 | 该站对多数弹药显示价格，部分为空 |
| Trader | 商人价 | 形如 `LL2 · ₽123`，带商人等级 |
| Craft | 制作来源 | 无则显示占位 |
| Barter | 以物易物 | 有则显示标记 |
| Pen / Dmg / ArD | 穿透 / 伤害 / 护甲伤害 | 数值，可排序 |
| Acc / Recoil / Frag | 精准度 / 后坐力 / 碎裂 | 百分比或带符号百分比 |
| Speed | 初速 | m/s |
| Ricochet | 跳弹概率 | 百分比 |
| C1 … C6 | 对 1–6 级护甲的穿透评级 | 右端为色块/等级指示 |

- 行底色按口径分组染色（同一口径的行共享一条色带），最右端有一个 0–6 的穿透评级色块。
- 表头可点击排序，观测到默认按口径排列，可切换升/降序。

## 3. 筛选栏

右侧筛选栏包含 5 个分组、共 32 个「口径筹码」（chip）：

1. `PISTOL / SMG`
2. `RIFLE ROUNDS`
3. `PDW`
4. `SHOTGUN ROUNDS`
5. `GRENADE LAUNCHER`

- 每个 chip 为一个具体口径；点击后表格只保留该口径。
- 筛选栏另有 `SHOW` / `RESET` 操作，以及 PEN / DMG / SPEED 的区间输入与 RANGE（100 / 300 / 500 m）选择。
- 霰弹上游只有 `Caliber12g` 一个口径键，参考站拆成 `12g Shot` 与 `12g Slugs` 两个 chip。
  这是本地复刻时必须按「口径 + 弹药类型」匹配、而不能按口径名等值匹配的直接证据。

## 4. 弹药详情弹窗

- 触发：点击列表任意一行，弹出居中大弹窗（不跳转独立页面）。
- 结构：左侧为弹道下沉（Drop）面积图，右侧为距离表。
- 右侧表列：`m` / `Pen` / `Dmg` / `Speed` / `Drop` / `TOF`；从 0 m 到 500 m，每 10 m 一行，共 51 行。
- 图表：横轴 0–500 m，纵轴为负值（0 到约 -500，弹窗可视区到 -250 左右），面积填充。
- 实测关键点（LRNPC 弹药）：0 m 时 Drop = **-6.858 cm**（瞄具高度补偿），50 m 时 **0**（归零距离）。
  完整 51 行数据保存在同目录 `lrnpc-reference-table.json`。
- 弹窗可通过右上角关闭按钮或 Esc 关闭；关闭后列表滚动位置与筛选状态保留；点击另一行会直接切换为另一枚弹药的内容。

对应截图：`ref-ammo-detail-popup.png`、`ref-ammo-detail-chart.png`、`ref-ammo-detail-lrnpc.png`。

## 5. 其它页签

- `DROP pen dmg`：每个距离列内上下两行显示穿透与伤害（0/100/…/500 m），随距离递减。
- `DROP bullet 3m`：显示初速、各距离下沉值与每行迷你曲线。
- `BALLISTICS graph`：散点图，横轴为伤害、纵轴为护甲等级；图上包含点名与虚线基准。

对应截图：`ref-ammo-drop-pen-dmg.png`、`ref-ammo-drop-bullet-3m.png`、`ref-ammo-ballistics-graph.png`。

## 6. 无法确认 / 未照搬的部分（如实记录）

1. **C1–C6 的评级口径**：参考站用 0–6 的色块/等级表示对各级护甲的穿透表现，但页面上没有给出计算式，
   也未在可读文本中暴露阈值。本地据此**不伪造 0–6 评级**，改为展示「穿透概率 %」
   （计算式见 `report.md` 第 4 节），并在单元格 tooltip 中写明护甲值 AV 与概率。
2. **Market 价格**：本地上游数据 `avg24hPrice` 为 null，无法还原参考站的价格列内容，
   本地一律显示「—」并在 tooltip 说明，不按 0 处理（见 `data/ammo.json` 的 `audit.unavailable.flea`）。
3. **Craft 列**：参考站对部分弹药显示制作来源，本地数据没有 craft 记录，显示「—」。
4. **行底色**：参考站按口径给整行染色；本地改为口径列左侧色条 + 分组排序。
   这是**已知视觉差异**，不影响数据与交互。
5. 参考站的具体字体、图标素材未复制进项目（许可与依赖原因），本地全部使用项目自有样式与图标。
