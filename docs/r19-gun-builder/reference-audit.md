# R19 参考站审计：db4tarkov.com/gun

审计日期：2026-10-24 · 执行环境：Windows / Chrome（headless=new, CDP）/ 代理 `http://127.0.0.1:7896`
证据目录：`docs/r19-gun-builder/reference/`（截图 + 语义树 dump）

---

## 0. 访问方式与一个关键发现

### 0.1 代理可用性（实测）

```
curl -x http://127.0.0.1:7896 https://db4tarkov.com/gun
→ status=200  size=60308  time=2.67s
```

代理有效。访问方式：Chrome 加 `--proxy-server=http://127.0.0.1:7896`
`--proxy-bypass-list=127.0.0.1;localhost;::1`，CDP 本身直连。

### 0.2 首次访问确实有加载态，但不是"缓存初始化"

任务书提到"初次访问可能显示缓存初始化 / 更新或冲突提示"。实测结论：
**页面首屏确实有一段脚本在探测版本（`_isFirst`、`_web_ver`、`sp-tl` 等），
但它不是阻塞性的引导页**——等 Flutter 首帧渲染完（约 14–22 s）就直接进配枪墙。

第一张截图 `01-gun-landing.png` 就是可交互的配枪墙，没有任何遮罩需要点击。

### 0.3 这个站点是 Flutter Web（决定了后续所有操作方式）

第一次探测时 `document.querySelectorAll('*').length = 63`，
`document.body.innerText` 几乎为空，但截图里界面是完整的。

原因：**db4tarkov 是 Flutter Web 应用**，内容绘制在 canvas / 语义树上，
常规 DOM 查询拿不到任何控件。

解决办法：点击 Flutter 的隐藏语义占位符 `<flt-semantics-placeholder>` 启用无障碍树，
之后每个按钮/输入框都变成带 `aria-label` 和**精确 rect** 的 `<flt-semantics>` 元素，
于是可以像普通网页一样按坐标点击。证据：`semantics-dump.json`、`dom-12-builder.json`。

> 这条对后续复现很重要：不启用语义树，就只能凭截图猜坐标（我第一次点搜索框就点到了
> 顶部导航的 SEASON，因为读图时把 1080 宽的显示尺寸当成了 1600 的实际尺寸）。

---

## 1. 实际观察到的功能清单

下面每一项都标注了证据文件与实测结论。

### 1.1 枪械选择（`01-gun-landing.png`、`10-gun-page.png`）

- **按口径分组的枪械墙**：左列是彩色口径标签（.300 / 5.8x42 / 5.56x45 / 5.45x39 /
  6.8x51 / 7.62x39 / 7.62x51 / 7.62x54R / .308 / .338 / 7.62x25 …），
  右侧是该口径下的枪械卡片网格。
- 卡片上有枪械缩略图、名称、左上角一个数字（实测为**该枪的改装槽数量**）、
  右上角配件数。
- **搜索框**（占位文字 `Type to search — ESC to clear`）：输入即实时过滤，
  实测输入 `AK-74` 后只剩 5.45x39 组的 3–4 把。
- **Secondary 切换**：`Primary` / `Handgun` 两个按钮。
- **Class Filter** / **Caliber Filter** 两个下拉筛选。
- 射击模式快捷筛选：`Auto` / `Single` / `Burst` / `Silent` / `Loud`。

### 1.2 装配界面主体（`12-gun-builder.png`）

选定 AK-74 后进入的界面结构（从语义树逐项确认）：

| 区域 | 实际内容 |
|---|---|
| 顶部工具条 | `Save Gun`、`Remove all attachment on Gun 1`、`Rollback Gun 1`、`FORGE`（生成器面板开关）、`Compare`、`Changes`、`EXPORT BUILD URL`、`IMPORT BUILD`、`SHARE SCREENSHOT` |
| 左上 | `FORGE BETA` 面板：`BASIC` / `ADVANCED（Coming soon）` / `ABOUT`；`GENERATOR SETTINGS` 含 `SUPPRESSED` / `BUYABLE` / `MAGS(10/20/30/45/60/95)` / `SCOPE(CLOSE/MID/RANGE)` / `TACTICAL` / `BLOCKED` / `FORCED`；底部 `GENERATE BUILDS` 按钮，副标题 *"Press GENERATE BUILDS to compute the 3D Pareto frontier"* |
| 中部上 | 一张带网格的折线/散点图，工具条有 `Undo edit` / `Redo edit` / `Jump to best-value build in history` / `LOAD VARIANT` / `Toggle legend` / `Collapse timeline` —— 实测是**装配历史时间线**，x 轴是编辑历史 |
| 中部 | 属性条：`Ergonomics` / `Accuracy` / `Ver Recoil` / `Hor Recoil` / `Velocity` / `OverSwing` / `EvoErgoDelta` / `ArmStamina` / `100% Headshot acc` / `ADS Time (beta)`，部分项带括号旧值 |
| 中下 | **2D 装配图**：枪械按槽位排布，每个槽位一张配件缩略图 + 价格，点击槽位在右侧开候选面板 |
| 底部 | `Buy (42, 864)` / `Ammo Drop` / `Sell ()`；`ITEMS` / `BREAK` 两个标签；配件明细表（名称、价格、属性徽标、`default` 标记） |
| 右侧 | 候选面板，未选槽位时显示占位文字 `Pick a mod` |

### 1.3 配件候选面板（`13-slot-panel.png`，点击枪口槽位后）

- 面板标题就是槽位名（`Muzzle`），右上角 ×。
- 面板内有自己的**搜索框**（`Type to search — ESC to clear`）。
- 表格列：**图标 / Recoil / Ergo / Acc / Vel / Loud / Slot / Prc（价格）/ 来源**。
- 属性变化用颜色区分正负（绿/红）。
- 当前已装的那一项**高亮 + 末尾标 `default`**。
- 价格列后面跟商人图标 + 等级角标（锁形图标表示未解锁）。
- 面板底部汇总：`-24.9 / 8.4 / 6.4 / 9.4 / Total Cost: 864`。

### 1.4 双枪比较（`14-compare.png`）

- 点 `Compare` 后主区变成**并排两栏**：左边当前装配，右边空栏。
- 顶部提示条原文：*"Compare 2 guns side by side. Useful when checking different attachments
  on the same gun, or comparing 2 different guns with similar builds. **Mutually exclusive
  with Forge.**"*
- 空栏中央有两个操作：`Choose ↓`（选另一把枪）和 `Copy ↗`（复制当前装配）。
- 空栏的属性区列出全部字段但值为空。

### 1.5 配件改动提示（`15-changes.png`）

点 `Changes` 后弹出说明，原文：

> *"Show the old stats of each attachment **before the actual patch (1.2.0.0.47888)**.
> Check the Changes page for a full overview of all buffed/nerfed items"*

- 所以它显示的是**"当前补丁之前"的旧属性**，靠的是上游维护的补丁前后对照数据。
- 顶部导航里另有独立的 `CHANGES` 页面（带 `1.2.0.0` 版本角标）。
- 开启后属性区会出现括号里的旧值（如 `Ver Recoil (71) 71`、`Hor Recoil (180.6) 181`）。

### 1.6 价格与商人

- 右上角有价格口径切换：`lastPrice` / `avg24h` / `avg7d` / `only FleaLvl` / `only TraderLvl`，
  以及 `Trader level / PMC Setting` 设置按钮。
- 页头 `PVE` / `PVP` / `SS (43d)` 三个模式开关 —— **PVP 与 PVE 是两套独立数据**。
- 底部 `Buy (42, 864)` 是整枪落地价合计，`Sell ()` 是整枪卖出价合计。

### 1.7 其他可见能力

- `Gunsmith` / `TierMaker` / `Streamer` / `Variant` / `Saved` 五个派生入口
  （枪匠任务、分级表、主播配装、同系列变体、已保存）。
- `EXPORT BUILD URL` / `IMPORT BUILD` / `SHARE SCREENSHOT`：配置分享三件套。
- 装配图支持 `LOAD VARIANT`（切换同系列变体并保留/重算配件）。

---

## 2. 与本地项目的差距（审计当时的基线 = R18.2）

| 参考站能力 | 本地 R18.2 状态 | 差距 |
|---|---|---|
| 按口径分组的枪械墙 | 已有（`renderGunBrowse` 按枪名里的口径 token 分组） | 缺 Class / Caliber 下拉与射击模式筛选 |
| 搜索 | 已有 | — |
| 选枪后自动装默认装配 | **没有**（选完是空枪） | 本轮补齐 |
| 递归槽位树 | 已有（`addGunSlots` 递归 + 父件卸载清子槽） | — |
| 槽位候选表 | 已有，但只有 重量/价格/人机工效/后坐力修正/可扩展槽 五列 | 缺 Acc / Vel / Loud |
| 2D 装配图 | 已有（`renderGunVisual`） | 缺"点槽位开候选面板"的模态交互 |
| 整枪属性 | **只有 人机工效（简单累加）、后坐力（累加百分比）、重量、价格** | 缺 精度/射速/瞄准距离/弹匣容量/初速；且公式与真实不一致 |
| 对比 | **没有** | 本轮补齐 |
| 预设保存/导入/导出/分享 | 只有"用户预设"（%APPDATA% 的整包武器预设，不是单枪装配） | 本轮补齐装配级预设 |
| 枪口/瞄具组合 | **没有** | 本轮补基础能力 |
| 自动配枪（FORGE） | **没有** | 本轮补简化优化器 |
| 配件改动（Changes） | **没有** | 无历史数据，只能标缺失 |
| 弹道联动（弹药/初速） | **没有** | 本轮补初速联动 |
| PVP / PVE 双数据 | 只有单套（常规模式） | 不做 |

---

## 3. 无法验证 / 不做的部分（如实标注）

1. **`FORGE` 的 Pareto 前沿**：面板可见、按钮可点，但生成结果需要点击后等待计算，
   本次审计只确认了**功能存在与它的参数表**（MAGS / SCOPE / TACTICAL / BLOCKED / FORCED），
   没有把它的输出结果逐条记录（会让审计无限延长）。因此本地的优化器是**独立实现**，
   不声称与 FORGE 结果一致。
2. **`Changes` 的数据来源**：只看到"before the actual patch (1.2.0.0.47888)"这句说明，
   没有找到它背后的历史属性数据接口。本地没有历史版本数据，因此**不实现**，只标缺失。
3. **装配历史时间线的交互细节**（Undo/Redo/Jump to best-value 的具体行为）：
   只确认了控件存在，没有逐项操作验证。
4. **`Sell ()` 的结算规则**：价格列可见，但没有核实商人收购价与跳蚤手续费的计算口径。
5. **PVP / PVE 数据差异**：页头开关可见，但没有对比两套数据的具体差异。

> 以上 5 项在 `feature-matrix.md` 里统一标为「参考站有 / 本地未实现」或「未核实」，
> 不计入本轮交付。
