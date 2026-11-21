# R20.7 · Preset 页按钮功能逐项对照（db4tarkov → 本地）

> 取证方式：受控 Chrome（CDP 9401/9402）+ `tools/r207_cdp.py`，对 `https://db4tarkov.com/preset`
> 做只读交互与截图；同时用 `main.dart.js` 的字符串常量交叉验证（站点是 Flutter Web，
> 语义层给的是 aria-name，逻辑要从编译产物里核对）。本地一侧用同一套 CDP 脚本实测。
> 结论全部来自实测，不含推测。

## 0. 一个前提：插板列在 1080 布局下**不存在**

这是本轮最容易误判的地方，先说清楚：

| 站点分辨率 | 逻辑宽度 | 护甲候选表有没有 Front/Back/Left/Right 四列 |
|---|---|---|
| 1080P | 1080 | **没有**，只有 Icon / Mov·Turn·Erg / Zone / Kg / Price |
| 1440P + 窗口 ≥ 1440 | 1440 | **有**，多出 Front / Back / Left / Right / Material / Eff Dur / Zone / Slots |

`main.dart.js` 里的判定：

```js
if (width > 1236) { ... n.push(SizedBox(..., child: bjV())) }   // bjV = 插板槽列表/列
```

所以「我记得能选插板」是对的，只是要先把站点切到 1440P 并把窗口拉宽。
1080 布局下看不到插板入口 ≠ 站点没有这个功能。

证据：`screenshots/r207-15-tall.png`（1080，无插板列） / `screenshots/r207-31-1440-wide.png`（1440P，有）。

## 1. 插板怎么选、换护甲后还在不在

**db4 实测流程**（`screenshots/r207-32-header.png`、`r207-33-front-plate.png`）：

1. 点护甲行里的 **Front 格**（格内显示 `V H 60` = 等级 5 / 材质 H / 耐久 60）；
2. 弹出插板列表，按 **Plate Class 6 / 5 / 4** 分组，每行有 名称 / Mov·Turn·Erg / Material / 价格 / Eff / Durability / Kg；
3. 点一行即选中，弹窗关闭，该格变成 `VI H 60 Combined`；
4. 同一行的 Mov/Turn/Erg 立刻从 `-8 / -3 / -5` 变成 `-10.5 / -4 / -6`，价格同步变。

**「换了别的防弹衣，插板还留着」的准确含义**（实测反证）：

- 给 Redut-T5 的 Front 选 Granit Br5 → Redut 行变 `VI H 60 Combined`；
- 再给 6B43 的 Back 选 Cult Termite → 6B43 行变 `VI H 60 Ceramic`；
- **此时 Redut 的 Back 仍是 `V H 60`，没有被 6B43 的选择带跑**。

所以真实语义是：**插板按「护甲行」各自记忆，切走再切回还在**，不是「插板跟着新护甲走」。
（`main.dart.js` 的序列化也印证：`plates{front,back,left,right}` 是 preset 级字段，
但 `bB5/bB7/aq2` 三个策略函数都是遍历**当前这件护甲**的 `armorSlots` 取 `slot.x / slot.z`。）

**本地行为**：`plateStorageKey(slotId, armorId)` 就是 `rootKey/zone@<护甲 id>`，
换护甲互不覆盖、切回来还在 —— **与 db4 一致，无需改**。

## 2. picked / default / priority Plates 三段开关

db4 候选表顶部（`screenshots/r207-32-header.png` 可见），只在 Armor 分类出现。
`main.dart.js`：

```js
if (a.id === "Armor") { ... A.tv(..., p===1, p===2, p===3, false, cb1, cb2, cb3,
                                    null, "picked\nPlates", "default\nPlates", "priority\nPlates", h) }
```

三个回调只做一件事：`k1 = 1/2/3` 然后 `onRefreshBadge + onLoadPreset` —— 说明是**纯计算口径切换**，
不改用户挑的板。

**实测同一件 6B43 的三种口径**：

| 模式 | Mov / Turn / Erg | 说明 |
|---|---|---|
| picked（没挑过板） | -9 / -5.5 / -7 | 只算护甲本体 |
| default | -14.5 / -10 / -10 | 按默认板填满，惩罚最重 |
| priority | -13 / -8.5 / -9 | 价格优先，居中 |

**本地原来没有这一段**，本轮补上（见 §4）。

## 3. 其余按钮逐项对照

图例：✅ 行为一致 ／ 🟡 形态不同但语义等价 ／ ❌ 本轮前缺失，已补

| # | db4 控件 | db4 行为 | 本地位置 | 状态 |
|---|---|---|---|---|
| 1 | 左侧 8 个槽位（Headwear / Glasses / Face Cover / Headset / Armor·Armored Rig / Chest Rig / Gun / Backpack） | 点槽位 → 右侧列表切到该槽位候选 | 左侧卡片板同名槽位 | ✅ |
| 2 | 列表行点击 | 装备；同一行再点 = 卸下 | 同 | ✅ |
| 3 | `only TraderLvl` | **复选开关**，只显示「商人等级够得着」的装备 | 「商人等级 ≤」下拉（选等级而非勾选） | 🟡 |
| 4 | `only FleaLvl` | **复选开关**，只显示「跳蚤已解锁」 | 「跳蚤等级 ≤」下拉（数据来自 `data/flea-levels.json`） | 🟡 |
| 5 | `picked / default / priority Plates` | 三段互斥，切插板口径 | 新增三段互斥按钮 | ❌→✅ |
| 6 | 搜索框 | 按名称过滤当前列表 | 顶栏搜索框 | ✅ |
| 7 | `Both / Armor / Armored Rig` | 三个 tab 切分类 | 顶部分类 tab（护甲 / 弹挂甲等） | 🟡 |
| 8 | 表头 `Mov/Turn/Erg` 排序 | 点列头切换升/降 | 「移动 / 转身 / 人机」三个排序按钮 | 🟡 |
| 9 | 表头 `Kg` 排序 | 点列头排序 | 新增「重量」排序按钮 | ❌→✅ |
| 10 | 表头 `Price` 排序 | 点列头排序 | 新增「价格」排序按钮 | ❌→✅ |
| 11 | `Max Kg` / `Min Built-in` / `Max Penalty` | 数值输入筛选 | 「重量 ≤」/「防弹等级 ≥」/「惩罚 ≤」 | ✅ |
| 12 | `3-slot / 4-slot` | 两个写死按钮，按插板槽数过滤 | 新增「板位数」下拉，**选项按真实数据生成**（本地这批数据只有 2 板和 4 板，写死 3 会得到空表） | ❌→✅ |
| 13 | `Front / Back / Left / Right` 插板格 | 点格子 → 插板列表 → 选中回填 | 表格同名四列 + 模态「选择插板」窗 | ✅ |
| 14 | 插板列表分组 `Plate Class N` | 按等级分组 | 按护甲等级分组（沿用同类分组） | ✅ |
| 15 | `Move/Turn/Ergo` 汇总（左上） | 全身合计 | 左侧「移动 / 转身 / 人机」 | ✅ |
| 16 | `Kg` 汇总 | 全身重量 | 左侧「千克」 | ✅ |
| 17 | `Final Cost` + `Buy()` / `Sell` | 整套买入 / 卖出合计 | 「总价」+「买入 / 卖出」 | ✅ |
| 18 | 底部已装备清单（护甲名 / 重量 / 惩罚 / 价格 / 等级） | 逐件列出，含插板行 | 已装备物品行（含插板） | ✅ |
| 19 | 顶部 ↻ / 💾 / 📋 三个图标 | 重置配装 / 保存 / 载入 | `PRESET ▾`（新建 / 另存为 / 覆盖 / 重命名 / 加载 / 删除 / 导入 / 导出） | 🟡（本地功能更全） |
| 20 | 护甲槽上方 `0 / 0 / 0` | 三个数值（随装备变化） | 护甲槽上「插板位置数 N」+ `0 / 0 / 0` | ✅ |

> 🟡 不打算强行改成和 db4 一样的形态：本地这三处是**超集**（下拉能选具体等级、PRESET 能存取多套），
> 换成复选开关反而降级。语义等价、可筛选结果一致即可。

## 4. 本轮改了什么

### 4.1 插板策略三段开关（`state.plateMode`）

- `index.html`：`#lw-plate-mode` 三个按钮（`data-lwpmode=1/2/3`），只在护甲 / 弹挂甲槽位显示；
- `app.js`：
  - `hardPlateSockets(rec)` —— 取一件护甲**可拆的硬板位**（`fx=0`）；
  - `autoPlatePick(socket, mode)` —— default 取「防护等级最高、其次耐久最高」，priority 取「价格最低」；
  - `autoPlatesFor(rec, mode)` —— **先在所有硬板位的交集里挑一款，整件护甲用同一款**
    （参考站默认就是前后同款），交集为空才逐板位各挑各的；
  - `effectivePlate(armorId, rootKey, slotId)` —— 用户挑的优先，没有才用自动板，并打 `auto` 标记；
  - `equippedList()` 在 2/3 模式下把自动板作为**虚拟行**并入统计，**不写 `state.loadout`**；
  - 表格行内的「移动·转身·人机」也把当前生效插板算进去（否则会出现左侧已按插板算、行内还是本体值的割裂）。

**关键约束（已用测试钉住）**：切回 picked 后用户原来挑的插板必须原样还在。
实测往返：

```
picked   -9.0% / -5.5% / -7.0%   10.80 KG   无总价（缺价）
default  -14.5% / -10.0% / -9.0% 21.10 KG   188,658 ₽
priority -11.0% / -7.0% / -8.0%  15.00 KG   121,298 ₽
picked   -9.0% / -5.5% / -7.0%   10.80 KG   无总价   ← 完整恢复
```

### 4.2 板位数筛选

`state.lwSlots`（0/2/3/4），只对 armor / rig 生效；选项**按当前候选的真实板位分布生成**
（本地这批数据：2 板 20 件、4 板 21 件，没有 3 板），选了数据里不存在的值会自动归零。

### 4.3 Kg / Price 排序

`createTable` 的 `opts.sorters` 加 `kg`、`price` 两个虚拟键；`price` 对无报价行给 `1e15` 哨兵，
升序时排最后，不会把「缺价」当成最便宜排在最前面。

## 5. 与 db4 仍有差异的地方（如实记录）

| 项 | db4 | 本地 | 影响 |
|---|---|---|---|
| default 口径的数值 | 6B43 `-14.5 / -10 / -10` | `-14.5 / -10 / -9` | 侧板允许的板不同，人机差 1。方向与量级一致 |
| priority 口径的数值 | 6B43 `-13 / -8.5 / -9` | `-11 / -7 / -8` | 「价格优先」的具体排序键 db4 里是 `price` + 另一个字段复合，本地只用价格 |
| 插板列可见性 | 逻辑宽 > 1236 才出现 | 一直显示（响应式列宽） | 本地 1080 也能选插板，属于超集 |
| only TraderLvl / only FleaLvl | 复选开关 | 下拉选等级 | 语义等价 |

## 6. 验证

```
python -m pytest tests/test_r20_7_plate_mode.py -q         → 12 passed
python -m pytest tests/test_loadout_workbench.py \
                 tests/test_r20_6_preset_parity.py -q      → 51 passed
python -m pytest tests -q --ignore=tests/test_installer.py → 1439 passed, 6 failed, 1 skipped
```

那 6 个失败是**本轮之前就存在的结构耦合测试**（`test_r11_armor_grouping` /
`test_r19_1` / `test_r19_5` / `test_r19_11` / `test_r19_13` / `test_r6_gun_workbench`），
失败原因都是「按字符串切代码段，切完发现标记改名/位置变了」（例如 `if (opts.groupOf)`、
`gunPushHistory`、`gunColumns` 的提取边界），与插板、排序、筛选无关，本轮**未改动**它们。

## 7. 截图索引

| 文件 | 内容 |
|---|---|
| `screenshots/r207-15-tall.png` | db4 1080P：没有插板列 |
| `screenshots/r207-31-1440-wide.png` | db4 1440P：出现 Front/Back/Left/Right |
| `screenshots/r207-32-header.png` | db4 宽屏表头 + 三段开关特写 |
| `screenshots/r207-33-front-plate.png` | db4 插板选择弹窗（按 Plate Class 分组） |
| `screenshots/r207-33-local-default-final.png` | 本地 default 策略：行内惩罚与左侧统计同步 |
| `screenshots/r207-34-local-picked-final.png` | 本地 picked 策略：同一行回到本体值 |
| `screenshots/local-06-picker.png` | 本地「选择插板」模态窗 |

---

## 8. R20.7b 补丁：板位显示三态（用户反馈）

**反馈原话**：「点选别的护甲后，原先那个护甲的插板槽图标会清空；我希望在没有自己选择插板前，
槽位里显示默认的插板图标，但是灰色的。」

### 8.1 改了什么

原来 `plateSlotState()` 只在 `state.loadout[rootKey] === armorId`（这件护甲正穿着）时才读插板记录，
所以换到别的护甲，上一件的板位立刻回落成「未安装」——记录还在，但看不见。

现在拆成**三态**，与「是否穿在身上」解耦：

| 状态 | 触发条件 | 视觉 | 计入重量/惩罚 |
|---|---|---|---|
| `on` | 正穿着这件护甲 + 该板位有用户挑的板（或策略自动板） | 实线框 + 彩色图标 | ✅ |
| `kept` | **这件护甲没穿**，但该板位有用户挑过的记录 | 点线框 + 彩色图标（整体 72% 不透明） | ❌ |
| `default` | 没有用户记录、也没有策略自动板 | 虚线框 + **去色**剪影（`saturate(0)` + 42%），数值条 50% | ❌ |

### 8.2 为什么 `kept` 不直接用 `on`

R19.26 有一条硬契约：**未装备的护甲不能报「已安装」**（否则统计、冲突判断、右键卸除都会把它
当成真穿在身上）。`test_loadout_workbench.py` 的 U3 / T25.6 三处断言都在守这条：

```js
api.plateSlotStates("armorA", "armor", state.items.armorA)[0].state !== "on"
```

所以新增了 `kept` 这个独立状态：图标照常显示（满足「别清空」），语义上不是「已安装」（守住老契约）。

### 8.3 为什么用 `saturate(0)` 而不是 `grayscale(1)`

`test_r18_1_round.py` 有一条全局禁令：`assert "filter: grayscale(1)" not in css`
（那条禁令是 R18.1 为了让面罩剪影不再被去色而立的）。插板占位要的只是「变灰」，
用 `saturate(0)` 视觉等价，且不与那条规则打架。

### 8.4 顺带修的两件事

- 点击：`default` / `kept` 格都可点（default → 装这块默认板或换别的；kept → 先穿上这件护甲再换）。
- 性能：`autoPlatesFor()` 现在被**每一行**调用（要算默认板占位），加了 `armorId|mode` 缓存，
  避免 49 行 × 4 板位每次重算。

### 8.5 实测

```
6B43（给前板挑了 Cult Termite，然后切到 6B45）：
  Front = kept    VIT65        点线框、彩色图标
  Back  = default VIT65        虚线框、灰
  Left  = default VIC20        虚线框、灰
  Right = default VIC20        虚线框、灰
6B45（装备中）：
  四格 = on，实线 + 彩色
刷新页面后两者都还在（记录落在 localStorage 的 loadout 里）
```

截图：`screenshots/r207-46-final.png`（局部放大）、`screenshots/r207-47-full.png`（整页）。
