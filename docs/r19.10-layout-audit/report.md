# R19.10 交付报告：FORGE 选择器状态机 · 已选黄色高亮 · 前握把父子布局

本轮只做修复，不重做工作台：工作台三栏、属性条、默认基准值、弹药、成本/价格、预设与筛选全部保持 R19.9 行为。

- 构建标记：`AM_BUILD = "R19.10"`，`index.html` 五个 `?v=r19.10`，`tools/serve.py` 的 `rev` 前缀同步。
- 实测视口：**1920×919** 与 **1384×805**；两种视口下 `document.documentElement.scrollWidth === innerWidth`（无横向溢出）。
- 控制台错误 0，外部请求 0（离线）。

---

## 1. FORGE 选中项"变黑"的根因

不是配色偏好问题，是**层叠优先级 + 变量回退**共同造成的：

| 层 | 选择器 | 优先级 | 结果 |
|---|---|---|---|
| `style.css` | `.gun-workbench .gw-forge-opts .gw-forge-poolrow[data-on="1"]` | (0,4,0) | `background: var(--lw-select, #2c3646)` |
| `theme-windows-xp.css` | `html .gun-workbench button:not(.gw-hit):not(.gw-card)` | (0,3,2) | 被上面那条压过后不再生效 |
| `theme-windows-xp.css`（R19.9 遗留） | `html .gun-workbench .gw-forge-poolrow[data-on="1"]` | (0,3,1) | 只设了 `border-color` / `box-shadow`，**没设底色**，且优先级最低 |

`.gun-workbench` 在 XP 令牌段里**没有定义 `--lw-select`**（只有 `.loadout-workbench` 有），于是回退值 `#2c3646` 生效 →
实测计算样式 `background-color: rgb(44, 54, 70)`，正是"选中变黑"。R19.3 给 `.gw-card` 修过同一个坑，FORGE 型号行当时漏了。
（修复前的原始测量见 `before-fix-computed-styles.json`：选中行 `bg=rgb(44,54,70)`，且选定之后该档候选**依旧全部铺开**、没有收起。）

**修法**（`theme-windows-xp.css` 新增章节 "R19.10：FORGE 型号选择器"）：

```css
html .gun-workbench .gw-forge .gw-forge-opts button.gw-forge-poolrow[data-on="1"],   /* (0,5,2) */
… :hover / :active / :focus {
  background: linear-gradient(180deg, #fff6d2 0%, #ffe9a8 100%);
  border-color: #c8832a;
  box-shadow: inset 0 0 0 1px #f2ca77;
  color: #000000; font-weight: 700;
}
html .gun-workbench .gw-forge .gw-forge-opts button.gw-forge-poolrow:hover:not([disabled]) { /* 浅黄 #fff3c4 + #e8a33d */ }
```

- 选择器带 `button` 元素名 + 5 个类/属性 = **(0,5,2)**，同时压过 style.css 的 (0,4,0) 与 XP 按钮皮肤的 (0,3,2)；
- `:hover` / `:active` / `:focus` / `:focus-visible` 各写了选中态，**鼠标移开不会掉回灰色**；
- 档位 / 手电 / 激光按钮的"已带约束但列表收起"用 `[data-on="1"]:not([aria-pressed="true"])` 淡淡的黄底，展开时仍是 Luna 蓝色按下态；
- 选中状态只由 `data-on`（来自真实 `f.opticId` / `f.devices[key]` 与物品 id 的比较）驱动，没有借用 hover 类名。

改动文件：`theme-windows-xp.css`（新增样式）、`app.js`（`renderGunForge` 三态状态机）、`style.css` 未动（保留旧规则，被更高优先级覆盖）。

---

## 2. 选择 / 展开 / 收起 / 更换 / 清除的实际行为

### 2.1 瞄具（近 / 中 / 远）

| 操作 | 行为 | 实测 |
|---|---|---|
| 初始 | 只有「近 中 远」+ 无候选 | `optBoxes = []` |
| 点「中」 | 展开该档位全部兼容瞄具，档位按钮蓝色按下 | 17 行（416A5 中档兼容数） |
| 点某型号 | 立即写入真实 id、**收起列表只留这一款** | 1 行，`data-on=1` |
| 鼠标移开 | 仍是黄色（`linear-gradient(#fff6d2 → #ffe9a8)` / 黑字 / 700） | `pickedYellow = true` |
| 再点「中」 | 重新展开同一档位，已选那行仍高亮 | 17 行，`reopenKeepsSelected = true` |
| 选另一款 | 旧型号整行消失，新型号顶上并保持黄色 | 1 行，名称由 Burris → ELCAN |
| 「清除」 | 型号行消失、档位回到未选、`cons.scopeId` 移除 | 0 行，`已选` 状态清空 |

状态字段：`f.opticTier`（档位）、`f.opticId`（具体型号 = 真实物品 id）、`f.opticOpen`（是否展开）。
点档位是展开/收起开关；换档位清空 `opticId` 并自动展开。收起态只有一行，并且**名字允许折行**（`.gw-forge-picked`），不靠省略号藏型号名。

三档逐一实测（HK 416A5，`_accept.json → forge.tierSummary`）：

| 档位 | 兼容型号数 | 选定后行数 | 黄色 | 重新展开行数 | 清除后行数 | 档位按钮复位 |
|---|---|---|---|---|---|---|
| 近（固定 1×） | 23 | 1 | ✓ | 23（保留选中） | 0 | ✓ |
| 中（≤4×） | 17 | 1 | ✓ | 17（保留选中） | 0 | ✓ |
| 远（>4×） | 17 | 1 | ✓ | 17（保留选中） | 0 | ✓ |

反例（Glock 17，原厂套筒没有瞄具槽）：三档都显示
"当前枪械在这个档位没有兼容瞄具（按真实槽位与一级转接座判定）。"，**不会**把全库瞄具铺出来充数。

### 2.2 手电 / 激光

三个按钮固定为 **手电 | 激光 | 清除**（有选中型号时才出现「清除」）：

- 点「手电」→ 展开手电兼容型号列表（按当前枪械真实槽位 + 一级转接座过滤，416A5 为 13 款）；再点一次收起。
- 选具体型号 → 写入真实 id、收起列表，只留下所选型号那一行；点它或再点「手电」可重新展开更换。
- 「激光」同构。
- 「清除」→ 两个设备的型号约束一起取消、列表收起、回到未选状态；**只改约束**，不碰 `g.installed`、不调用 `persistGun`、不影响已保存预设（有单元测试盯住这一点）。
- 两个设备互不覆盖：同时选中时两行都在，各自带「手电」/「激光」/「手电+激光」功能标签。

### 2.3 换枪后的有效性复核

`selectGun()` 不再无条件清空型号（R19.9 的做法），改为由 `forgeValidateSelections()` 按新枪真实兼容性复核：

- 兼容 → 保留；
- 不兼容 → 清除，并在面板底部给出一句可读说明。实测（416A5 → Glock 17）：

```
原选中瞄具与当前枪械不兼容，已清除：Burris FullField TAC30 1-4x24 30 毫米 步枪瞄准镜；
原选中手电与当前枪械不兼容，已清除：Armytek Predator Pro v3 XHP35 HI手电
```

Glock GTL 21 本来就是 Glock 17 的合法手电/激光组合，所以它**继续保留**并保持黄色——这正是"兼容就留、不兼容才清"的预期。

---

## 3. 具体型号确实约束了优化结果

约束链路未变，但本轮补掉了 R19.9 的两处漏洞：

1. `GB.optimize()` 的"贪心后补装必装件"只覆盖 `required` / `scopeId`，**漏了 `deviceIds`** → 贪心换掉护木后设备被 `sanitize` 清掉，结果只剩"未满足"。
   现在 `deviceIds` 与瞄具一起进入补装列表，并**锁定承载它的父件槽位**（护木 / 机匣 / 转接座），防止贪心把"战术槽更少的护木"换上来。
2. `GB.resolveInstall()` 以前按槽位树顺序取第一个 `allow` 命中项，会**覆盖**同槽里已有的必装设备（手电被激光顶掉，连转接座一起没）。
   现在优先选**空槽**（或已装同款），再退到被占用的槽位；配合 3 轮预装重试，两件设备各占一个真实槽位。

实测（HK 416A5 + Burris TAC30 + Armytek 手电 + Glock GTL 21，`node tools/r1910_engine.js`）：

```
低后坐力 / 高人机工效 / 轻量化 / 性价比 → 4/4 方案 constraintOk=true，missing=[]
终检 checkConstraints → ok=true
```

浏览器里再走一遍 UI：生成 → 应用 → 画布已装件 id 与所选三件完全一致（`constraintHits` 全 true），
应用前仍执行 `GB.checkConstraints` 终检，不通过就拒绝应用。

反例（AK-74 选 Armytek 手电，真实没有该槽位）：4 个方案全部标红并写明
"所选战术设备「Armytek …」未装入方案：装配树里没有可安装它的槽位（可能被其它配件选择占用或被转接座替换）"，
**没有静默换成别的设备**。

---

## 4. 前握把的真实父子槽位关系

### 4.1 三种真实安装链（由槽位树 `node.parent` 判定，不看名称关键词）

| 类型 | 判定 | 摆放规则 |
|---|---|---|
| 直接安装 | 父件不是 `mount`（护木 / 机匣 / 枪管 / 提把…） | 父件**正下方、同列**，钉住不让位 |
| 转接皮轨 | 父件本身就是 `mount`（皮轨 / 安装座） | 皮轨正下方、同列（`data-parent` 仍指向皮轨） |
| 根前握把 | 无父件（枪身侧插槽） | 贴在枪身首列正下方 |

实现要点（`app.js` → `gwBuildLayout`）：

1. 前握把先**钉住**（`pinned`），行 = 父件行 + 1，列 = 父件列；
2. 若"正下方"正好落在**枪身 3 列**上（父件在顶部轨道时必然如此），枪身不可移动 → 前握把整行下移一层，**列仍对齐父件**；
3. 弹匣 / 后握把是**没有父子位置约束**的根槽位，与前握把同行时整组下移一行（连带下挂链子槽，但绝不带走主轴 / 上机匣线）；
4. 列分配跑两轮：父件（皮轨）自己被挤动时，第二轮用父件最终列重新对齐前握把；
5. 冲突时只挤走**普通格**（先向左、再向右），前握把永不让位；战术装置让开别人的父子锚定列，放不下才进子弹行下方的底行。

### 4.2 三把实测枪（1920×919）

| 枪 | 类型 | 前握把槽位 | 父槽位 | grid（行/列） | 与弹匣同行 | 在握把右侧 | 连接线起点 |
|---|---|---|---|---|---|---|---|
| HK 416A5 | 直接 | `mod_reciever/mod_handguard/mod_foregrip` | `mod_reciever/mod_handguard` | r3/c4 ← r2/c4 | 否（弹匣 r4） | 否 | 父件底边中心 |
| SIG MCX .300 | 直接（同父件还有 2 个导轨槽） | `mod_reciever/mod_handguard/mod_foregrip` | `mod_reciever/mod_handguard` | r3/c4 ← r2/c4 | 否（弹匣 r4） | 否 | 父件底边中心 |
| FN SCAR-H | 转接皮轨 | `mod_reciever/mod_mount_000/mod_foregrip` | `mod_reciever/mod_mount_000` | r4/c4 ← r2/c4 | 否（弹匣 r5） | 否 | 皮轨底边中心 |

全量数据（163 把枪、56 把带前握把槽位）：**直接 41 / 转接皮轨 12 / 根槽位 5**，
不变量检查（列对齐父件、不与弹匣同行、不在后握把右侧、无重叠、不压枪身）**0 违规**。

**移除皮轨的链式反应（实测）**：SCAR-H 装上"ASh-12 垂直前握把"后，右键卸下"FN SCAR 底轨" →
前握把槽位随父件一起消失（真实槽位树里不再有 `…/mod_mount_000/mod_foregrip`），画布重算为 20 格、连接线同步重画，控制台无报错。
即"皮轨没了 → 前握把不可能还挂在上面"，没有残留成合法装配。

---

## 5. 截图与 DOM 测量产物

全部在 `docs/r19.10-layout-audit/`：

| 文件 | 内容 |
|---|---|
| `screenshots/1-optic-list-open.png` | 中档瞄具候选展开（17 行） |
| `screenshots/tier-near-picked.png` / `tier-mid-picked.png` / `tier-far-picked.png` | 近 / 中 / 远 三档"选定后只剩一款 + 黄色" |
| `screenshots/pistol-tier-near.png` / `-mid.png` / `-far.png` | 手枪（无瞄具槽）三档的"无兼容瞄具"提示 |
| `screenshots/2-optic-picked-collapsed.png` | 选定后收起，只剩一款 + 黄色（鼠标已移开） |
| `screenshots/3-light-open.png` | 手电候选展开 |
| `screenshots/4-light-picked.png` | 手电选定后收起 + 黄色 |
| `screenshots/5-light-laser-picked.png` | 手电 + 激光同时保留（各自一行） |
| `screenshots/forge-both-picked-1920.png` / `-1384.png` | 1920 / 1384 两种视口下"瞄具 + 手电 + 激光"三行全部黄色 |
| `screenshots/forge-after-gun-switch.png` | 换到 Glock 17 后不兼容型号被清除、兼容的保留 |
| `screenshots/fg-hk416-direct.png` | 直接安装：前握把在护木正下方 |
| `screenshots/fg-mcx-direct.png` | 同父件带 2 个导轨槽（网格冲突）仍对齐护木 |
| `screenshots/fg-scar-rail.png` | 转接皮轨：前握把在皮轨列下方 |
| `screenshots/fg-hk416-1384.png` | 1384×805 下的前握把布局 |
| `screenshots/page-1384.png` | 1384×805 整页（无横向溢出） |
| `foregrip-grid.json` | 每把枪的 `--gw-cols/--gw-rows`、枪身格、前握把 / 父件 / 弹匣 / 后握把的 `data-slot`、`data-parent`、`grid-row`、`grid-column`、连接线 `d`、不变量布尔值 |
| `forge-styles.json` | 7 个状态（未选 / 展开 / 选中 / 重新展开 / 更换 / 双选 / 换枪后）每行的 `background-image`、`color`、`border-color`、`font-weight`、`data-on` |
| `layout-all-guns.json` | 163 把枪默认装配的完整布局（每格行/列/车道/父槽位/是否钉住）+ 不变量汇总 |
| `_accept.json` | 浏览器验收原始记录（含生成/应用后的已装 id） |

---

## 6. 自动化测试

新增 `tests/test_r19_10_round.py`（12 条，全部通过）：

- 静态：瞄具"选中即收起"的三态、设备三按钮与"清除只改约束"、换枪复核；
- 静态：黄色规则的选择器强度必须 ≥ (0,4,x)，且必须覆盖 `:hover/:active/:focus`；`data-on` 只能来自真实 id；
- 静态：布局引擎必须按 `anchorSlot` / `viaRail` / `parent.row+1` / `parent.col` 定位，禁止 `style.left/top` 与按枪名硬编码；
- 静态：引擎必须把 `deviceIds` 计入必装、锁定承载父件、`resolveInstall` 优先空槽；
- 动态（node，真实数据）：163 把枪布局不变量（直接 ≥30、转接 ≥5、0 违规）；
- 动态（node，真实数据）：416A5 三件型号约束 4/4 方案落地 + 终检通过；AK-74 反例必须报原因且不换型号。

全量回归：`964 passed, 1 skipped`（跳过的是既有的需外部条件的用例）。
本轮迁移了三处历史断言（不弱化，只换成新契约）：R19.7 战术装置排位、R19.8 瞄具/设备"点型号即选中"（改为"选中即收起"）、版本串 R19.9 → R19.10。

---

## 7. 已知限制（未在本轮解决）

1. **顶部皮轨上的前握把**：父件在 `top1/top2` 轨道时，"正下方"必然是枪身 3 列 → 前握把整行下移到枪身下方（列仍与皮轨对齐），因此与父件隔了一行（如 SCAR-H：皮轨 r2、前握把 r4）。这是"枪身不可移动"下的既定取舍，连接线仍指向皮轨。
2. **瞄具档位候选**仍沿用 R19.8 的 `forgeInstallCompat`（直接槽位 + 一级转接座），而手电/激光已改成引擎同源的 `resolveInstall`；两者口径尚不统一。
3. **FORGE 3D Pareto 前沿**仍未实现（R19.9 遗留）。
4. 「清除」按任务书只给一个按钮，因此手电与激光会**一起清除**；单独撤掉某一个需要重新展开该设备再选，或点「清除」后重选另一件。
5. 为守住"选定型号必须装进方案"，优化器会锁定该设备的承载父件槽位，这会**略微缩小**搜索空间（换护木的自由度下降），属于硬约束的正当代价。
6. 仍有 6 件物品缺透明图标（上游 404），与本轮无关。

---

## 8. 复现命令

```bash
# 本地服务（若未启动）
python tools/serve.py --port 8787 --no-browser

# 浏览器验收（截图 + DOM 测量，1920x919 与 1384x805）
python tools/r1910_accept.py

# 163 把枪的布局不变量（node，真实槽位树 / 默认预设）
node tools/r1910_layout.js > docs/r19.10-layout-audit/layout-all-guns.json

# 具体型号约束是否真的装进方案（正 / 反例）
node tools/r1910_engine.js 5bb2475ed4351e00853264e3 5b2388675acfc4771e1be0be \
     59d790f486f77403cb06aec6,5a800961159bd4315e3a1657
node tools/r1910_engine.js 5bf3e03b0db834001d2c4a9c - 59d790f486f77403cb06aec6

# 全量测试
python -m pytest -q
```
