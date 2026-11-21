# R19.11 合并修复 · 交付报告

> 工作区实际停在 R19.10，本轮把 **R19.11 的五项要求 + 最近追加的右侧配件栏修复（原 R19.12）+ SPEAR 逐发模拟弹匣问题** 合并成一轮实现。
> 版本标记：`AM_BUILD = "R19.11"`；`/api/build` 实测 `rev R19.11-a9138812`。未提交 Git，未触碰 `release/`。

---

## 0. 一句话结论（逐项）

| 需求 | 状态 | 证据 |
|---|---|---|
| 100 发容量硬约束 | ✅ 已实现并实际验证 | M4A1 4/4 方案装 SureFire MAG5-100（100 发）；AK-74 无解并列出可选容量 |
| 属性条实心/斜纹语义 | ✅ 已修正并双向验证 | 人机 55→111 / 55→44、散布 1.8→2.4 / 1.8→1.1 四组测量 |
| FORGE BETA → 枪匠大师 | ✅ | 面板标题、hover 注明原名 |
| 顶栏「个人属性」弹窗 | ✅ | 力量/耐力/装备修正/熟练度 + 10 类武器技能，保存/取消/校验 |
| 个人属性持久化 + 全局应用 | ✅ | localStorage `eftmap.profile.v1`，刷新/切页/换枪后仍生效 |
| 基线 / 改装 / 技能 三值 | ✅ | 5 条属性条右侧三值，技能只作用于后坐力与人机 |
| 右侧顶部当前槽位 | ✅ | `#gw-slotinfo` 在 `.gw-cands` 顶部，中栏 `#gw-focus` 已删除 |
| 隐藏不兼容复选框 | ✅ | 17 → 6（隐藏 11），取消后恢复；搜索/列宽不受影响 |
| 红斜纹 + 不可安装 | ✅ | 整条 `repeating-linear-gradient`，pointer-events:none，点击被拒绝并给出原因 |
| M4 一体式枪托 / 缓冲管 | ✅ | 42 个子槽枪托 ID 无一泄漏到枪身根槽；装一体式后子槽消失 |
| 统一兼容性口径 | ✅ | `gunCompatOf` 一处判定，列表/安装入口共用 |
| SPEAR 无弹匣 | ✅ | 根因是数据就绪时序 + 隐式换枪未联动；修复后 6 个 AR-10 弹匣可选 |

---

## 1. 100 发弹匣约束：根因与修法

### 根因
`GB.optimize()` 里 `cons.caps` 只作用在**贪心替换候选**上：

```js
if (cons.caps && cons.caps.length) { … if (capC !== null && caps.indexOf(capC) < 0) { continue; } }
```

但**当前已装弹匣**（来自默认预设）从来不被校验，也不会被主动换掉；贪心只是"不换"，于是 30 发/60 发弹匣原样留在方案里。
`checkConstraints` 事后能发现它违规，UI 也只是把方案标红——这正是任务书说的"知道违规却仍当结果"。

### 修法（`gun_builder.js`）
1. 新增 `enforceMagCapacity(ctx, gunId, cur, cons)`：
   - 用真实槽位树找出所有 `sid ≈ magazine` 的槽位；
   - 已装弹匣容量合规 → 直接锁定；
   - 不合规 → 在该槽 `candidates()` 里挑**容量合规且试装后不被 sanitize 清掉**的一件装上；
   - 容量字段缺失（`cap === null`）一律按"不合规"处理，不当成合规。
2. 贪心**之前**调用，并把装配路径写进 `lockedPaths` → 贪心不可能再换回小弹匣。
3. 贪心结束后再核对一次（父件被换掉的情况），每个方案输出 `capsOk / capsWhy`，并追加 `kind:"caps"` 违规。
4. UI（`renderGunForge`）把 `constraintOk === false` 的方案**从有效列表剔除**，只留一行汇总原因；若全部被剔除，显示"没有满足当前约束的可行方案：…"，并明确写"不会用 30 发之类的弹匣凑数"。
5. 换枪后仍保留的容量约束（例如在 M4 选了 100 再换到 AK-74）会显示成红色斜纹的 `100 发` 芯片，点它可取消——避免"无解提示凭空出现"。

### 实测
| 枪 | 约束 | 结果 |
|---|---|---|
| 柯尔特 M4A1 | 100 发 | 4 个有效方案，全部装 `SureFire MAG5-100 AR-15 5.56x45 STANAG 100发弹匣`；应用后画布 `mod_magazine` 就是它 |
| AK-74 5.45x39 | 100 发（换枪继承） | 0 个有效方案、排除 4 个；提示"…该枪可选容量：10 / 20 / 30 / 45 / 60 / 95 发" |
| M4A1 / AK-74 | 30、30+45 回归 | 全部合规，未被新逻辑破坏 |

---

## 2. 属性条：实心=共有区间，斜纹=差异区间

### 旧实现为什么是反的
`gwBar()` 按"高好/低好"各写一套分段，两套里至少一套把斜纹画在了共有区间上：

```js
// 旧（R19.4）
if (!lowerBetter) { if (v > b) { seg(0, b, "stripe-good"); seg(b, v, "solid-" + good); } … }
else              { if (v < b) { seg(0, v, "solid-" + good); seg(v, b, "stripe-" + good); } … }
```

### 新实现
```js
var lowVal = Math.min(b, v), highVal = Math.max(b, v);
seg(0, lowVal, "solid-" + good);        // 共有区间：实心
seg(lowVal, highVal, "stripe-" + good); // 差异区间：斜纹
```
方向（good/bad）只决定颜色，不再决定分段；基线竖线 `left = pct(B)` 固定不动。

### 实测（`bars-tiers.json`）
| 场景 | 属性 | 基线 → 改装 | 实心 | 斜纹 | 基线竖线 |
|---|---|---|---|---|---|
| 高人机方案 | 人机工效 | 55.0 → 111.0 | 0–55 | 55–100 | 55 |
| 高人机方案 | 散布角（变差） | 1.8 → 2.4 | 0–18.2 | 18.2–24.1 | 18.2 |
| 低人机方案 | 人机工效 | 55.0 → 44.0 | 0–44 | 44–55 | 55 |
| 低人机方案 | 散布角（变好） | 1.8 → 1.1 | 0–11 | 11–18.2 | 18.2 |
| 恢复默认 | 全部 | B == C | 单段 neutral | 无 | B |

---

## 3. 枪匠大师改名 + 顶栏个人属性

| 改动 | 文件 |
|---|---|
| 面板标题 `FORGE BETA` → `枪匠大师`（hover 注明"原 FORGE BETA"） | `app.js` `renderGunForge()` |
| 面板内"模拟参数"整块移除，改为只读摘要 + 「打开个人属性…」 | `app.js` `renderGunForge()` |
| 顶栏新增「个人属性」按钮（同一行最右侧，弹窗 `role="dialog"`） | `index.html`（`.menubar`）、`style.css`（`.menu-btn-profile`） |
| 弹窗 DOM（力量/耐力/装备修正/熟练度 + 10 类武器技能 + 保存/取消/错误行） | `index.html`、`style.css`（`.gw-prof-*`） |
| 保存 / 取消 / 校验 / Esc / 遮罩点击 | `app.js` `gwProfileOpen/Close/Submit`、`bindProfileUI()` |

个人属性字段与落点：

```
eftmap.profile.v1 = {
  v: 1,
  strength: 0–51,            // 力量
  endurance: 0–51,           // 耐力
  equipErgo: -1..1,          // 装备人机修正（沿用旧 gwsim 语义）
  weaponSkillDefault: 0–51,  // 枪械技能默认等级
  skillByClass: { ar:…, pistol:… },  // 按武器类别覆盖（留空=沿用默认）
  mastery: 0–51              // 武器熟练度（与类别技能分开保存，不混用）
}
```
- 校验：非数字 / 超范围 / 非整数都会在弹窗内红字提示并**拒绝保存**（实测输入 99 → "力量等级 超出合法等级范围（0–51）"，且 localStorage 未被写入）。
- 迁移：没有新键时读旧 `eftmap.gwsim.v1`（力量 + 装备修正），不丢用户设置。
- 全局应用：`gunCompute()` / `gunComputeSkilledOf()` 都走同一份 profile；保存后 `renderGun()` 立即重算，切页/换枪/刷新/重启后仍生效。

---

## 4. 基线 / 改装 / 技能：三条独立路径

```js
gunStatTiers() = {
  baseline: GB.compute(默认装配, {strengthLevel:0, equipErgo:0}),   // 无任何个人属性
  modded:   GB.compute(当前装配, {strengthLevel:0, equipErgo:0}),   // 无任何个人属性
  skilled:  gwApplySkillStats(GB.compute(当前装配, profile), 类别技能等级)
}
```
- 属性条几何：`baseline` vs `modded`（只表达改装差异，技能不参与画条）。
- 右侧数值：`基线 B | 改装 C | 技能 S`；技能等级为 0 或属性不受技能影响时 `S = C`（不虚构差异）。
- 整枪属性表 / 对比面板 / 隐藏属性（ArmStamina、AimSway）用 `skilled`；**优化器内部用未加技能的原始属性**（避免个人等级改变方案排序，已在代码注释写明）。

实测示例（`profile.json`）：力量 40 / 耐力 25 / 默认技能 30 / 手枪技能 45

| 枪 | 属性 | 基线 | 改装 | 技能 |
|---|---|---|---|---|
| M4A1（突击步枪 30 级） | 人机工效 | 55.0 | 55.0 | 58.3（×1.06） |
| M4A1 | 垂直后坐 | 78.1 | 78.1 | 71.1（×0.91） |
| M4A1 | 散布角 / 初速 | 1.8 / 922 | 同基线 | 同改装（不受技能影响） |
| Glock 17（手枪 45 级） | 人机工效 | 91.0 | 91.0 | 99.2（×1.09） |
| Glock 17 | 垂直后坐 | 302.0 | 302.0 | 261.2（−13.5%） |
| 技能改回 0 级 | 全部 | — | — | 技能 = 改装 |

---

## 5. 技能公式、类别映射、来源与待核验

| 项 | 取值 | 说明 |
|---|---|---|
| 武器类别技能 · 后坐力 | **−0.3% / 级**，精英封顶 −15% | 三处社区资料一致 |
| 武器类别技能 · 人机工效 | **+0.2% / 级**，封顶 +10% | 同上；乘法叠加在当前装配值上 |
| 力量 | 不进武器人机/后坐；只影响角色侧（跳跃/负重/移动/瞄准耐力消耗 −0.4%/级） | 代码里只用作 ArmStamina 输入（沿用 EFTForge 公式 `str×0.004`） |
| 耐力 | 不进武器属性（体力/屏息恢复类） | 仅保存与展示，不伪造加成 |
| 装填速度 / 切枪速度 | 社区资料有（+0.4% / +0.8% 每级），**本模拟器不计算** | 见"待核验/未实现" |

来源：`escapefromtarkov.fandom.com/wiki/Assault_Rifles`、`eftarkov.com/skill`、`tarkovbox.com/gamewiki`、`tarkovforge.com/skills/assault-rifles`（互为交叉印证）。
**标注**：上述均为社区整理数值，非官方发布；`GW_SKILL_EFFECT` 已集中成常量，便于后续按官方数据替换。

类别映射（`GW_SKILL_CLASSES` / `GW_SKILL_CLASS_OF`）直接复用「口径 / 种类」分页那套枪械类别，不另造一套：
突击步枪、卡宾枪、冲锋枪、精确射手步枪、栓动狙击步枪、机枪、霰弹枪、手枪、左轮、榴弹发射器。
`gun-compat.json` 里 `cls` 对个别枪（如 SV-98 → `assault-rifles`）是旧的粗分类，所以**技能类别不读它**，改读物品真实 `cats`（与分页筛选同源）。

**待核验**：
1. 后坐力/人机每级系数是否仍适用于当前版本（社区三方一致但非官方）；
2. 精英（51 级）封顶值是否与线性累计一致（现取 min(cap, level×rate)）；
3. 装填/切枪速度与"武器熟练度（Mastering）"未接入任何属性计算（保留字段，避免混用）。

---

## 6. 右侧候选栏（原 R19.12 追加项）

### 6.1 当前槽位信息
`#gw-slotinfo` 位于 `.gw-cands` 最顶部，顺序：**当前槽位 → 隐藏不兼容 → 搜索 → 表头 → 列表**，
`topOffset = 0`，`beforeSearch = true`，中栏 `#gw-focus` 已删除（`inCenter = false`）。
显示规则：`当前槽位：<槽位名>` + 一行上下文（`父件 机匣 · 已装 …` / `N 个可选型号`）；弹药模式显示 `当前槽位：子弹 · <口径> · 已选 …`。
实测六个槽位（`panel-compat.json`）：枪托、护木、瞄具、弹匣、前握把、子弹全部正确切换。

### 6.2 红斜纹
```css
.gun-workbench .tbl-row.tbl-conflict::after {
  content:""; position:absolute; inset:0; pointer-events:none; z-index:2;
  background: repeating-linear-gradient(45deg, rgba(178,28,28,.30) 0 5px, rgba(178,28,28,.10) 5px 11px);
  box-shadow: inset 3px 0 0 #a51f1f;
}
```
- 覆盖整条（实测 `coverW = 行宽`），`:hover` / `[aria-selected]` / `:focus` 各有一条保持规则；
- `pointer-events:none` 不拦截点击；文字保持暗红、图片不被遮死；
- 行内还直接写出原因（`gw-row-why`："与已安装的「…」互斥（上游 conflictingItems）"），状态列显示 `⛔ 不可装`。

### 6.3 隐藏不兼容
勾选后 `refreshGunTable()` 在**搜索之后**过滤 `r.conflict`，只改显示：
17 → 6（"已隐藏 11 个"）；取消勾选 → 17/11 恢复；搜索词与列宽不受影响。
全部被过滤时给出可区分原因的空态："没有匹配「ubr gen2」的兼容配件（另有 11 个不兼容项已隐藏）…"。

### 6.4 统一兼容性口径
`gunCompatOf(id, node)` 是唯一判据（`gunCompat` 只是带缓存的包装，键含"当前装配指纹"）：

1. 当前槽位 `allow` 是否收录；
2. 与**已装件**（含本槽位的下级）上游 `conflictingItems` 是否互斥；
3. **试装**：把本槽位（及其下级）替换成候选后跑 `GB.sanitize` —— 候选自己被清掉 → `kind:"self"`；
4. 试装是否连带清掉**无关**已装件 → `kind:"evict"`（"会连带卸下 …"）。

同一结论喂给：候选行（斜纹/状态/原因）、隐藏过滤、`gunEquip` 安装入口、FORGE 应用前 `checkConstraints`。
安装入口始终经过 `gunInstallCheck`，没有 `pointer-events:none` 之类的假拦截；脚本/键盘触发同样被拒（实测点击冲突行：已装件未变 + 提示原因）。

### 6.5 M4 一体式枪托 / 缓冲管
结构性事实（`stock` 模式实测，`m4-stock-chain.json`）：

| 项 | 数值 |
|---|---|
| `mod_stock` 根槽候选 | 17 = **10 个缓冲管**（自带 `mod_stock*` 子槽）+ **7 个一体式枪托**（无子槽） |
| 缓冲管子槽里的枪托 ID | 42 个 |
| 这 42 个里有几个能直接挂枪身根槽 | **0**（`leakToRoot = 0`） |
| 装上一体式（UBR GEN2）后 | `mod_stock` 只剩它一件，子槽 `mod_stock/mod_stock_000` 消失 |

判据不靠名字：**有没有 stock 子槽**就是"缓冲管 vs 一体式"的结构差异；"需要缓冲管的枪托"只出现在缓冲管的子槽里。
互斥关系来自上游 `conflictingItems`：装上 `Hera Arms CQR AR-15 一体化枪托`（握把槽）后，`mod_stock` 的 17 个候选里 **11 个变红**（A2/UBR/TROY/ERGO/Phase5 等），原因写"与已安装的「Hera …」互斥"。
反向也拦：装着缓冲管 + M4SS 枪托时点 Hera → "⛔ 无法安装 … 与已安装的「High Standard M4SS AR-15 枪托」互斥（未改动改装）"。

---

## 7. SPEAR 6.8×51 没有可选弹匣：根因与修法

**不是"按弹药口径筛弹匣"**：`data/gun-compat.json` 里 SPEAR 的 `mags` 是正确的 6 个 AR-10 7.62×51 弹匣（Lancer L7AWM 20/25、KAC 10/20、PMAG 20 SR-LR、X Products 50 发弹鼓）。
真正原因是**渲染时序 + 隐式换枪**：

1. `renderSimMagPicker()` 在 `items.json` 还没加载完时执行 → `simAllowedMags()` 里 `itemRec(id)` 全部返回 null → 候选被丢光 → 界面显示"该枪数据里没有可用弹匣（missing）"，而**之后再没有重渲染**；
2. 用「口径筛选」把当前枪换掉时（`rebuildSimGunOptions` 内部改写 `s.gunId`），只调了 `renderSimGun()`，**没有走 `amSimOnGunChanged()`** → 弹匣下拉停在上一把枪的弹匣上（实测：枪已变 SPEAR，弹匣还写着 Chiappa Rhino 6 发弹巢）。

修法（`app.js`）：
- `gunMagIds(gunId)`：优先用 `GB.buildTree` 的 `mod_magazine` allow（**与改枪界面同一套规则**），引擎/物品未就绪才回退 `gun-compat.json`；`simAllowedMags()` 改为调用它。
- `renderSimMagPicker()`：区分"物品数据加载中…"与"真的没有弹匣（missing）"。
- `renderAmmoSim()`：`ensureItems().then(...)` 补一次弹匣/预设渲染。
- `renderSimGun()`：检测到 `s.gunId` 被隐式改掉时调用 `amSimOnGunChanged()`（换弹匣、清不兼容弹药、按容量截断）。

实测：SPEAR → 6 个弹匣可选、容量"已装 0 / 20 发"；换弹匣后容量刷新；M4A1 24 个、MCX .300 24 个、口径筛选切到 6.8×51 后仍是 SPEAR 的 6 个（不再残留上一把枪的弹匣）。
数据一致性：SPEAR / M4A1 / Glock 17 的槽位树弹匣清单与 `gun-compat.json` **完全相同**（`mags` 模式实测 sameSet=true）。

---

## 8. 截图、DOM 测量与测试

### 8.1 产物（`docs/r19.11-merged-audit/`）
| 文件 | 内容 |
|---|---|
| `screenshots/A1-m4-100-cap.png` | M4A1 选 100 发 → 4 个有效方案 |
| `screenshots/A2-ak74-100-nosolution.png` | AK-74 继承 100 约束 → 0 个方案 + 无解原因 + 斜纹 100 芯片 |
| `screenshots/B0…B3-bars-*.png` | 默认 / 人机升高 / 人机降低 / 恢复默认 四条状态 |
| `screenshots/C1-profile-modal.png`、`C2-profile-invalid.png` | 个人属性弹窗、非法输入报错 |
| `screenshots/C3-profile-applied-bars.png`、`C4-profile-pistol-override.png`、`C5-profile-zero-skill.png` | 技能后三值 / 手枪类别覆盖 / 零等级回归 |
| `screenshots/D1…D7-*.png` | 枪托候选、冲突斜纹、悬停、点击被拒、隐藏开/关、搜索+隐藏、空态 |
| `screenshots/D2a-integrated-blocked-by-tube.png` | 装缓冲管时点一体式枪托被拒 |
| `screenshots/D7-m4-child-stock.png`、`D8-m4-integrated-stock.png`、`D9-m4-integrated-candidates.png` | M4 子枪托槽 / 一体式装配 / 装后候选 |
| `screenshots/D8-ammo-slotinfo.png` | 子弹槽的右栏上下文 |
| `screenshots/E1…E3-sim-*.png` | SPEAR 弹匣、换弹匣容量、口径筛选 |
| `screenshots/Z-1384-panel.png`、`Z-1384-profile.png` | 1384×805 下的右栏与弹窗 |
| `capacity-check.json` / `bars-tiers.json` / `profile.json` / `panel-compat.json` / `m4-stock-chain.json` / `sim-mags.json` | 上述每一项的结构化测量（含 grid、样式、ID、原因） |
| `_accept.json` | 浏览器验收原始记录（含控制台与请求） |

### 8.2 DOM 测量要点
- 视口：1920×919 与 1384×805 均 `scrollWidth === innerWidth`（无横向溢出）。
- 属性条：`trackW` 340（1384 下）、数值列 `valW` 156；5 条属性条**无一条**文本被裁（`valClipped=false`）。
- 右栏：#gw-slotinfo `topOffset=0`、位于搜索框之上；斜纹层 `pointer-events:none`、`z-index:2`、覆盖整行。
- 控制台错误 0，外部请求 0（离线）。

### 8.3 自动化测试
`980 passed, 1 skipped`（全量）。本轮新增/迁移：
- 新增 `tests/test_r19_11_round.py`（16 条）：容量硬约束（静态 + node 真数据）、属性条语义与三值路径、技能公式范围、改名、profile 持久化/校验/类别映射、右栏顺序、隐藏过滤、斜纹 CSS、统一判据、M4 枪托结构、模拟器弹匣同源与加载态。
- 新增 `tools/r1911_engine.js`（`caps` / `mags` / `stock` 三种探针）与 `tools/r1911_accept.py`（浏览器验收）。
- 迁移（非弱化）：`gw-focus` → `gw-slotinfo` 的中栏/右栏顺序断言、R19.4 的模拟参数与斜纹语义断言、版本串 R19.10 → R19.11。

> 测试通过不等于视觉通过：上面每张截图都实际打开核对过（斜纹是否盖满整条、三值是否可读、弹窗是否 XP 风格、M4 装一体式后子槽是否真的消失）。

---

## 9. 未解决 / 数据缺口

1. **技能系数未经官方确认**：0.3%/0.2% 每级来自三处社区资料交叉一致，仍标注"待官方核验"；装填/切枪速度、Mastering 未接入计算。
2. **`data/gun-compat.json` 的 `cls` 口径偏粗**（SV-98 被归到 assault-rifles）。技能类别已改走物品真实 `cats` 规避；兼容表本身没有重生成（需要上游快照，本轮不联网重跑构建）。
3. **上游没有 `conflictingItems` 的枪托对**（例如"A2 长缓冲管 + 只能配固定托"这类物理约束）无法凭空判定——现有数据只保证 `allow` 与显式互斥，报告中不做名称猜测。
4. **个人属性不含"技能后重量/成本"**：这两项与人物技能无关，保持原值（符合"不得虚构修正"）。
5. **`release/` 未更新**：按要求不覆盖；发布包里仍是旧版本。
