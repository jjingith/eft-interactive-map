# R19.14.1 布局规则合并修复：B.A.D. / MPR45 竖直链 / Nightforce 主链+侧分支 / 顶部扩展 / 外观隐藏

日期：2026-10-26
实际版本：`R19.14.1-69230132`（`/api/build` 实测，pid 23508）
改动文件：`app.js`、`index.html`、`tools/serve.py`、`tests/test_r19_13_round.py`、新增 `tests/test_r19_14_layout_rules.py`、新增 `tools/r1916_accept.py`、`tools/r1916_slots.js`、`tools/r1916_probe*.js`
未改动：`docs/r19.14-six-rows/`、`docs/r19.13-layout-audit/` 等历史审计；未执行 git reset/commit/push；未触碰 `release/`。

---

## 一、开工前的状态核对（事实依据）

| 项 | 实测 |
|---|---|
| `git status --short` | 工作区有大量历史未提交修改（R19 各轮），本会话只在其上增量 |
| `AM_BUILD` | 修复前 `R19.14`（对应 `R19.14-bdf447da`） |
| `/api/build` | 修复前服务未运行；重启后 `R19.14-bdf447da`，修复后 `R19.14.1-69230132` |
| 已有 R19.14 报告 | `docs/r19.14-layout-changes/report.md`（空白格隐藏，已落地且浏览器实测通过） |

**关键：上一轮报告只覆盖「空白格显示」，未包含本轮 5 项布局规则。** 已实测确认修复前确实不符合：

| 规则 | 修复前实测 | 位置 |
|---|---|---|
| B.A.D. 在 r4c6 | M4A1 落在 **r4c5**；SCAR-L 落在 r4c1、SCAR-H 落在 r4c2 | 8 把枪全部错位 |
| MPR45 子槽同列向上 | 子槽被横向塞到 **r2c3 / r2c2 / r2c1**，满了才退回 r1c4 | 36 个 MPR45 槽位全部横排 |
| Nightforce Multimount 主链+侧分支 | 4 个分支散落 r1c5 / **r1c7 / r1c8 / r1c9**（无主链/分支概念） | SV-98 实测 |
| 顶部扩展 | 无扩展机制，第 1 行以上直接放不下记例外 | 引擎无 topPad |
| 外观合成区 | `renderGunSkin(shot)` 始终执行，含「外观合成 · N 层」文字 | 画布左上 |

---

## 二、修改内容（app.js）

### 1. B.A.D. 锚点 r4c6

```js
bad: { row: 4, col: 6 }        // GW_ANCHOR 新增
reserve(GW_ANCHOR.bad);        // 预留，普通附件不得漂入
```

放置逻辑：`order.filter(p => gwIsBadSlot(nodes[p]))` → `take(4+bi, 6, p, true)`。
判定仍只读真实 allow 数据（全部为 B.A.D / 辅助释放杆），不看枪名。

### 2. MPR45 子槽严格同列向上

```js
var railTop = 1;
railQueue.forEach(k => {
  while (railTop >= -GW_TOP_MAX && !take(railTop, 4, k, true)) railTop -= 1;
  cell(railTop, 4, k, "top1", {...});   // 固定 c4，逐层 -1
  railTop -= 1;
});
```

删除原「c3 → c2 → c1 横向找空位」逻辑。空间不足时向上扩展，不横移。

### 3. Nightforce Multimount 主链 + 侧分支

判据（真实数据，非名称猜测）：子槽 `allow` **全部是 `pt === "Scope"`** → 主光学链；否则 → 侧分支。

- 主链：沿 **c5** 同列向上（`topCursor` 1 → 0 → -1…）；
- 侧分支：主链**右侧** c6 起，先铺满第 1 行再下一行，不交错。

实测 Multimount 四个子槽：`_000`（4 个纯 Scope）→ 主链 c5；`_001–_003`（红点/测距仪/底座 `WeaponMod`）→ 侧分支 c6/c7/c8。

### 4. 顶部扩展（基准 6 行）

```js
var GW_TOP_MAX = 4;
// take() 允许 row 到 -GW_TOP_MAX
// 布局收口：
var topPad = minRow < 1 ? (1 - minRow) : 0;
cells.forEach(c => c.row += topPad);
var totalRows = GW_GRID_ROWS + topPad;
```

返回新增 `rows: totalRows` / `topPad`；`body.row`、`ammoRow`、`emptyAnchors` 同步 +topPad。
固定锚点相对位置不变（整体一起下移），六行基准不变；没有上置链时 `topPad = 0`。

### 5. 隐藏实时外观合成区

```js
var GW_SKIN_ENABLED = false;
if (GW_SKIN_ENABLED) { renderGunSkin(shot); }
```

`renderGunSkin`、`GW_SKIN_ANCHOR`、`GW_SKIN_MAX_LAYERS` 全部保留；置 true 即可恢复。
真实槽位卡、安装状态、槽位树布局不受影响。

---

## 三、真实浏览器验收（`layout-rules.json` + 截图）

Chrome CDP，`Network.setCacheDisabled=true`，1920×919，加载 `app.js?v=r19.14.1`。

| 验收点 | 实测结果 |
|---|---|
| B.A.D. 在 r4c6 | **通过** — M4A1 `mod_charge_001` → `r4c6`，`atR4C6: true` |
| MPR45 同列向上 | **通过** — 链 r3c4（MPR45）→ r2c4（基座）→ r1c4（瞄具），`allSameCol: true`，`strictlyUpward: true` |
| 三层触发顶部扩展 | **通过** — `rows: 7`、`topPad: 1`，枪身随之下移（body r4） |
| 移除后收缩 | **通过** — `rowsAfter: 6`、`topPadAfter: 0`、`shrunk: true` |
| Nightforce 主链 + 侧分支 | **通过** — 主链 `mod_scope_000` r1c5 = ATACR；侧分支 r1c6 / r1c7 / r1c8 三个空槽同排向右 |
| 不存在槽位无格框 | **通过** — `phantomCount: 0`（含空坐标 `elementFromPoint` 命中测试） |
| 真实空槽可交互 | **通过** — 4 个空槽，点 `mod_reciever/mod_scope` → 右栏候选出现 |
| 六行九列稳定 | **通过** — `rows 6 / cols 9`，行高 `[56, 57.8, 85.5, 57.8, 57.8, 57.8]` 全非零 |
| 外观合成区隐藏 | **通过** — `.gw-skin` 不存在、`.gw-skin-tag` 为 null；枪身卡仍在 body r3，子弹格文案正常 |

### 截图（`docs/r19.14-layout-changes/screenshots/`）

| 文件 | 内容 |
|---|---|
| `G-bad-r4c6-m4a1-1920.png` | M4A1：B.A.D 空槽在枪身正下方第一格（r4c6），六行无占位格 |
| `H-mpr45-vertical-chain-3layers-1920.png` | SA-58：MPR45 三层同列（r3c4→r2c4→r1c4），顶部多一行 |
| `I-mpr45-after-remove-1920.png` | 移除两层后恢复 6 行，MPR45 上方只剩一个真实空槽 |
| `J-nightforce-main-and-side-1920.png` | SV-98：ATACR 主链 c5 顶行，右侧 c6–c8 三个分支槽同排 |
| `K-m4a1-no-ghost-no-skin-1920.png` | 无占位格、无外观合成区，槽位与子弹格正常 |

---

## 四、测试

- 新增 `tests/test_r19_14_layout_rules.py`（7 项）：B.A.D 锚点、MPR45 竖直链、主链/侧分支分流、顶部扩展收口、六行基准、外观开关、浏览器审计断言。
- 迁移 `tests/test_r19_13_round.py` 中一条与新需求冲突的旧断言：原锁「c3→c1 横向」，改为锁「c4 竖直向上且不得横移」（更强，不弱化）。
- 版本标记迁移到 `R19.14.1`（`AM_BUILD` / `?v=` / `/api/build` rev）。
- 全量：**1019 passed / 1 skipped**。

---

## 五、保留项（未回归）

- R19.13.1 六行显示修复：行轨道 `minmax(var(--gw-row-min,56px), auto)`，空行不塌缩；
- R19.12 枪匠大师完整兼容性、默认弹药、SPEAR 逐发模拟：仅改布局与外观开关，未触碰相关判定代码；
- 枪口纵向链、前握把父子链、护木第六行、瞄具 r2c5 / 照门 r2c8 / 拉机柄 r2c9 / 前照门枪口列等 R19.13 规则。
