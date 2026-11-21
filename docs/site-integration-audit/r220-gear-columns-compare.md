# 配装装备「属性列」对比：db4 `/preset` ↔ 本地配装表（R22.0）

> 取证：rea/CDP 9401（db4 `/preset`，Flutter 语义树 + 高清截屏）+ 9402（本地）。
> 本地列定义以 `app.js` `gearColumns()`（约 8334–8394 行）为准，逐槽位类别返回。
> 结论先行：**每个种类的属性列都与 db4 不一致**（用户目测属实），且本地把「胸挂」套用了护甲 21 列版式是明显错配。

---

## 0. db4 各槽位的属性列（rea 取证基准）

db4 `/preset` 左侧纸娃娃 8 槽：Headwear / Glasses / Headset / Face Cover / Armor·Armored Rig / Chest Rig / Gun / Backpack。
点开某槽后，右侧「Choose gear」候选表的列（从左到右，`X` = 该列 db4 有）：

| 槽位 | db4 属性列（顺序） |
|---|---|
| **Headwear / Helmet**（头盔） | Icon · **Name** · **Mov/Turn/Erg** · **Expand**(跳弹角 65°) · **Material**(材质+毁损 90) · **Eff**(有效耐久/耐久 218) · **[Armor Class N]**→N 个部位等级+耐久格(V 30…) · **Zone**(部位图标) · **Deafening**(High/Low) · **Kg** · **Price** |
| **Glasses**（眼镜） | **Name** · **Mov/Turn/Erg** · **Kg** · **Price** |
| **Headset**（耳机） | **Name** · **Distance** · **Ambient** · **Dry** · **Resonance** · **Kg** · **Price** |
| **Face Cover**（面罩） | Icon · **Name** · **Mov/Turn/Erg** · **Kg** · **conflicting items**(互斥物品图) · **Price** |
| **Armor / Armored Rig**（护甲+装甲胸挂） | **Name** · **Mov/Turn/Erg** · **Front** · **Back** · **Left** · **Right**(4 插板格) · **Material** · **Eff** · **[Armor Class N]**→9 个部位等级+耐久格 · **Zone** · **Cap** · **SE** · **Slots** · **Kg** · **Price** |
| **Chest Rig**（无甲胸挂） | **Name** · **Mov/Turn/Erg** · **Cap** · **SE** · **Slots** · **Kg** · **Price** |
| **Backpack**（背包） | Icon · **Name** · **Mov/Turn/Erg** · **Allowed Only**(仅允许) · **Excluded Items**(排除) · **Cap** · **SE** · **Slots** · **Kg** · **Price** |
| **Gun**（枪） | （非属性列表：是 Gun1–7 预设槽 + 属性条的预设管理界面） |

**db4 隐藏在行内的信息**：Icon 格叠「短名 / 材质徽章 / 耐久」；插板格叠「等级+耐久」；等级用罗马数字(III)。

---

## 1. 本地各槽位的属性列（`gearColumns()` 现状）

本地对每个根槽位返回的列（冲突列插在名称后、获取方式固定最右，armor/rig 例外）：

| 本地槽位 | 本地属性列（顺序） | 列数 |
|---|---|---|
| **helmet**（头盔） | Name · 冲突 · baseCl(基础防弹等级) · pen(移/转/人机) · mat(装甲材质) · destr(损毁系数) · dur(基础耐久) · effDur(有效耐久) · helmetZone(防护区域) · slots(槽位) · w(重量) · price · src(获取方式) | 13 |
| **glasses**（眼镜） | Name · 冲突 · cl(护甲等级) · pen · w · price · src | 7 |
| **headphones**（耳机） | Name · 冲突 · pen · 距离系数 · 环境音量 · 干音量 · 失真 · w · price · src | 10 |
| **face**（面罩） | Name · 冲突 · pen · 互斥物品 · w · price · src | 7 |
| **armor / rig**（护甲+胸挂**共用**） | ico(图标) · Name · baseCl · pen · 前插板 · 后插板 · 左侧板 · 右侧板 · 内衬材质及总耐久 · 9×内衬列 · 防护区域(图标) · w · src(含价格) | **21** |
| **backpack**（背包） | Name · 冲突 · pen · 占用格 · 容量 · 仅允许 · 排除物品 · 槽位 · w · price · src | 11 |
| **plate**（插板弹窗） | Name · 冲突 · cl · dur · w · mat · destr · effDur · zone · src(含价格) | 10 |
| **attach / melee / gun(待接入)** | Name · 冲突 · 类型 · pen · w · price · src | 7 |

---

## 2. 逐类差异清单（本地 vs db4）

> 要素：字段集合、标签、顺序、缺失 / 多余 / 错位。

### 2.1 头盔 Helmet
- db4 **有**、本地**缺**：`Expand`（跳弹角）、`Deafening`(听力防护 High/Low)、**分部位等级+耐久格**（Armor Class N 下的 V 30/V 30…）、Zone 图标列的「等级罗马数字」呈现。
- db4 **无**、本地**多**：`冲突`、`baseCl(基础防弹等级)`、`损毁系数`、`基础耐久`、`槽位`、`获取方式`。
- 呈现差异：db4 把「材质+毁损」合一格(Material 90)、把「有效耐久/耐久」合一格(Eff 218)；本地拆成 材质/损毁系数/基础耐久/有效耐久 四列。
- 顺序：db4 = Name→MTE→Expand→Material→Eff→部位格→Zone→Deafening→Kg→Price；本地 = Name→冲突→baseCl→pen→材质→损毁→基础耐久→有效耐久→区域→槽位→w→price→src。

### 2.2 眼镜 Glasses
- db4 仅 **Name · Mov/Turn/Erg · Kg · Price**（4 列）。
- 本地多：`冲突`、`护甲等级`、`获取方式`（7 列）。
- 缺/多：本地多了 3 列；核心三列(MTE/Kg/Price)在但顺序被插入项打乱。

### 2.3 耳机 Headset
- db4 = **Name · Distance · Ambient · Dry · Resonance · Kg · Price**（7 列）。
- 本地 = Name · 冲突 · pen · 距离系数 · 环境音量 · 干音量 · 失真 · w · price · src。
- 对应：距离系数↔Distance、环境音量↔Ambient、干音量↔Dry、失真↔Resonance（4 项齐，但**标签中文名不同**）。
- db4 **无**、本地**多**：`冲突`、`pen(移动/转身/人机)`、`获取方式`。db4 耳机**没有** Mov/Turn/Erg 列。

### 2.4 面罩 Face Cover
- db4 = **Icon · Name · Mov/Turn/Erg · Kg · conflicting items · Price**（6 列，互斥物品是**图标串**）。
- 本地 = Name · 冲突 · pen · 互斥物品(件数) · w · price · src。
- 差异：db4 互斥物品是图标缩略串；本地是「N 件」计数。本地多 `冲突`、`获取方式`，缺 Icon 独立列。

### 2.5 护甲 / 胸挂 Armor·Rig ← **最大错配**
- **本地把 armor 与 rig 共用同一套 21 列**（前/后/左/右插板 + 内衬总耐久 + 9 内衬列 + 防护区域）。
- db4 **拆成两类**：
  - **Armor / Armored Rig**（有甲，含 23 件装甲胸挂）：Front/Back/Left/Right 插板 + Material + Eff + 9 个部位等级格 + Zone + **Cap + SE + Slots** + Kg + Price。
  - **Chest Rig**（无甲胸挂，如 BlackRock / UMTBS / ANA Alpha）：仅 **Name · MTE · Cap · SE · Slots · Kg · Price**，**完全没有插板/内衬/防护区域列**。
- 本地对**无甲胸挂也画插板/内衬列**，是用户「每个种类都有不同」最直观的错配。
- 缺：db4 护甲有 `Cap`(容量) `SE`(空间效率) `Slots`(槽位) 三列，本地护甲表**没有**。
- 多：本地有 `图标` `baseCl` `获取方式(含价格)`，db4 靠 Icon 格 + 分组表头 + Price 列承载。

### 2.6 背包 Backpack
- db4 = **Icon · Name · Mov/Turn/Erg · Allowed Only · Excluded Items · Cap · SE · Slots · Kg · Price**（10 列）。
- 本地 = Name · 冲突 · pen · 占用格 · 容量 · 仅允许 · 排除物品 · 槽位 · w · price · src。
- 对应：容量↔Cap、仅允许↔Allowed Only、排除物品↔Excluded Items、槽位↔Slots。
- db4 **有**、本地**缺**：`SE`(空间效率)、Icon 独立列。
- db4 **无**、本地**多**：`冲突`、`占用格`、`获取方式`。
- 顺序：db4 = Icon→Name→MTE→Allowed→Excluded→Cap→SE→Slots→Kg→Price；本地顺序不同且插入 冲突/占用格。

---

## 3. 横向共性问题

1. **本地几乎每类都多了 `冲突` 列 + `获取方式` 列**；db4 无「冲突」独立列（冲突走整行标红/名称悬停）、末列是纯 `Price`。
2. **本地普遍缺 `SE`(空间效率=容量/(宽×高))** 与 `Cap`/`Slots` 在护甲类的呈现。
3. **标签本地化用词与 db4 不同**（耳机 4 项、护甲材质等），若要「像素级一致」需统一为 db4 口径。
4. **armor/rig 未按「有无护甲」分列**，导致无甲胸挂错用护甲版式（最严重）。
5. db4 把「材质+毁损」「有效耐久/耐久」合并呈现，本地拆列；db4 用罗马数字等级格，本地用文字。

---

## 4. 已执行口径（R22.0「按 db4 来」）与遗留

**口径 A（严格对齐 db4 的列集合 + 顺序）已执行**（app.js `gearColumns()` 逐类改写 + 测试断言更新）：

- 胸挂从「护甲 21 列」错配改回参考站 **Chest Rig 口径**（Name | 移/转/人机 | Cap | SE | Slots | Kg | Price）——用户「每个种类都有不同」最直观的错配已修。
- 各类列集合/顺序对齐参考站；本地独有信息换参考站口径承载，不丢点：基础防弹等级→分组主序（baseClGroupRank）、获取方式→末列价格、冲突→整行标红、毁损→并入 Material 格（`材质 系数`）、基础耐久→并入 Eff 格（`有效/基础`）。
- 新增 **空间效率（SE = 容量 / 占用格）** 列（Cap/SE/Slots 对齐参考站）。

**遗留（数据源约束，非缺口）**：db4 的 **跳弹角(Expand)** 与 **听力防护(Deafening)** 两列上游 `items.json` 未采集该字段，且契约数据不重建、不编造，故本地省略——需扩 `tools/fetch_data.py` 采集并重建数据才有真值（属另一独立改动）。

**遗留（可选增强）**：参考站末列 Price 带来源红图标；本地末列仅价格数字，来源明细走价格悬停/物品详情（未做来源图标）。

**验证**：`pytest tests --ignore=test_installer` 回到基线 **6 failed(预存在 §14)/1448 passed/1 skipped**；CDP 9402 实测胸挂表 = Cap/SE/Slots 口径、护甲表 = Material/Eff/插板/内衬口径，均无报错。
