# R16-A / R16-B：枪械分组与弹药 / 弹匣兼容

## 1. 数据来源与字段

构建脚本：`tools/build_weapon_compat.py`（**只在构建期读上游**，运行期只读本地 JSON）

| 用途 | 字段 | 可信度 |
|---|---|---|
| 口径 | `properties.caliber`（如 `Caliber556x45NATO`）→ 用 `data/ammo.json` 的 `cal → caln` 显示为 `5.56x45` | **verified**（上游精确字段） |
| 可用弹药 | `properties.allowedAmmo`（精确弹药 ID 数组）→ 仅保留本地 `ammo.json` 存在的 ID | **verified** |
| 可用弹匣 | 本地 `data/items.json` 中该枪 `slots[sid=mod_magazine].allow`（精确弹匣 ID 数组，构建期同源导出） | **verified** |
| 武器类别 | `handbookCategories` 的 `normalizedName`（assault-rifles / smgs / pistols…） | **verified** |
| 平台（枪族） | 上游**没有**平台字段 → 构建期用 `tools/build_weapon_compat.py` 里的显式「型号前缀 → 平台」表逐枪落表到 `data/gun-platforms.json` | **estimated**（人工整理，逐枪可审计） |

运行期**不做任何名称字符串匹配**：`app.js` 只读 `gun-compat.json` / `gun-platforms.json` 的字段。

## 2. 产出与覆盖

`data/gun-compat.json`（schema 1）：

```
counts: guns 163 / withCaliber 163 / withAmmo 163 / withMags 159
        withPlatform 87 / withoutPlatform 76 / ammoIdsNotInLocalDb 1
```

- **159/163** 有可拆弹匣；4 把没有 `mod_magazine` 槽（内置/不可换）：
  `MP-43-1C 双管霰弹枪`、`MP-43 截短双管`、`MP-18 单发步枪`、`FN GL-40 榴弹发射器`。
  UI 对这些枪显示「该枪无独立弹匣槽（内置 / 不可换）」，容量标 `missing`，不伪造容量。
- **1 个弹药 ID** 在上游白名单里但不在本地 200 条弹药库中（Milkor M32A1 的 `5ede47641cf3836a88318df1`），
  记入 `ammoMissing`，界面不会展示。
- **76 把**没有命中所属平台前缀 → `platform = null`，UI 归到「其他<武器类别>」组，
  不猜测平台（这些组仍按口径正确归类）。

### 代表性对照（真实数据）

| 枪 | 口径 | 平台 | 可用弹药 | 可用弹匣 |
|---|---|---|---|---|
| 柯尔特 M4A1 | 5.56x45 | AR-15 平台 | 11 种 | **24** 个 |
| AK-101 | 5.56x45 | AK 平台 | 11 种（与 M4A1 **同一组**） | **3** 个（与 M4A1 **完全不重叠**） |
| AKS-74N | 5.45x39 | AK 平台 | 13 种 | 13 个 |

`set(M4A1.mags) & set(AK101.mags) == ∅` 已被测试固定（`test_same_caliber_different_platform_magazines`）。
这正是「同口径不能自动认定兼容」的证据：口径相同、弹匣完全不同。

## 3. UI 实现

- 枪械下拉：`optgroup` 标签为 **「口径 · 平台」**（如 `5.56x45 · AR-15 平台`），组内按中文名稳定排序；
  口径按枪数降序排列，平台按枪数降序。
- 口径快速筛选：`[data-sim="cal-filter"]`，选中后只保留该口径的组，选项显示 `5.56x45（18）`。
- 换枪联动（`amSimOnGunChanged()`）：
  1. 弹匣不在新枪白名单 → 换成新枪「最常见容量」的弹匣（避免默认落到 10 发小弹匣）；
  2. 已装弹药逐发过滤，不兼容的发数**移除并提示**；
  3. 超过新弹匣容量 → 截断并提示；
  4. 重新渲染弹药下拉、弹匣下拉、队列与容量提示。
- 弹药下拉只列 `allowedAmmo`；白名单为空时**禁用**并显示 missing，不退回「全部弹药」。
- 引擎侧硬校验（`CS.simulate` 的 `constraints`）：UI 被绕过、DOM 被改、直接构造参数时依然会被拒绝：
  - `ammo not allowed by gun: <id>`
  - `magazine not allowed by gun: <id>`
  - `gun has no detachable magazine: <id>`

## 4. 混压弹匣（B3）

队列仍是「按装入顺序的弹药 ID 数组」，逐发消耗：

- 每类弹药一行（连续段聚合），上下箭头整段移动，`×` 删除整段；
- 容量按所选弹匣 `cap` 限制，装入按钮会提示「只装入了剩余空间 N 发」；
- 引擎收到的 `magazine` 数组与页面队列**同一份状态**（`amSimBuildEngineCfg` 逐 ID 映射到弹药对象）。

## 5. 已知缺口

- 平台表是**人工整理**（estimated）：`HK416 / MCX / MDR` 归到 AR-15 平台属于「同族衍生」口径判断，
  不是官方分类；`SA-58`（FAL）保留在「其他突击步枪」，未强行归类。
- 弹匣白名单取「基础枪械的机匣槽」。如果某枪装不同口径转换套件（如 9x19 转换），
  本模型不会跟随套件改口径/改弹匣（当前数据里没有该套件的槽位映射）。
- 弹药白名单是**枪械级**，不区分枪管长度/口径转换件。
