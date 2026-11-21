# R64 · 跳弹参数与破碎面具护甲等级数据修正台账

host=HOMONAS user=MASTERJJ at=2026-11-04 14:20:52 +08:00

- 项目：`d:\personal\trae\02-塔科夫\eft-interactive-map`
- 范围：**只改数据**（`data/armor-ricochet.json` 6 条跳弹参数 + `data/items.json` 破碎面具 `cl=1`）。不改正则/公式（`combat_sim.js`、`app.js` 未由本轮改动）、不重建 dist/release、不 git 提交。
- 真值来源：`data/game-truth/armor_items.json`（EFT `1.3.0.48484`，从 `resources.assets` 只读提取），字段路径 `items.<id>.props.RicochetParams`（x/y/z）与 `items.<id>.props.armorClass`。
- 执行脚本：`tools/r64_apply_datafix.py`（纯标准库，逐条从上述真值文件重读后写入；不读上一轮报告里的数字）。

---

## 1. 跳弹参数 6 条（逐条从真值重读 → 最小替换）

| # | id | 名称 | 改前 x/y/z | 改后 x/y/z | 真值路径 |
|---|---|---|---|---|---|
| 1 | `66bdc28a0b603c26902b2011` | DevTac Ronin ballistic helmet（devtac_old，面罩） | 0.9 / 0.4 / 75 | **0 / 0 / 75** | `items.66bdc28a0b603c26902b2011.props.RicochetParams` |
| 2 | `675956062f6ddfe8ff0e2806` | MTEK FLUX Ballistic helmet (MultiCam Alpine) | 0.9 / 0.5 / 65 | **0.9 / 0.5 / 40** | 同上 |
| 3 | `6759655674aa5e0825040d62` | MTEK FLUX Ballistic helmet (Olive Drab) | 0.9 / 0.5 / 65 | **0.9 / 0.5 / 40** | 同上 |
| 4 | `67597ceea35600b4c10cea86` | MTEK STRIKE Ballistic helmet (Coyote) | 0.9 / 0.5 / 65 | **0.9 / 0.4 / 75** | 同上 |
| 5 | `67597d241d5a44f2f605df06` | MTEK STRIKE Ballistic helmet (Coyote/MultiCam Arid) | 0.9 / 0.5 / 65 | **0.9 / 0.4 / 75** | 同上 |
| 6 | `5aa7e4a4e5b5b000137b76f2` | ZSh-1-2M helmet (Black cover) | 0.8 / 0.3 / 75 | **0.7 / 0.3 / 75** | 同上 |

⚠ 任务书第 1 点把 STRIKE 写成 `(0.9,0.4,75) → (0.9,0.5,65)`，方向与真值相反（真值确为 `x=0.9,y=0.4,z=75`）。按「以 `data/game-truth/` 为准、不照抄报告」的要求，写入的是**真值**；改后 `ricochet_same=159/159` 复核一致。

结构未动：schema `eftmap.armor-ricochet/1`、`source` 块与其余 153 条逐值不变（脚本内断言 + 备份对比，见 §5）。
备份：`C:\Users\Administrator\Documents\Trae-CN\temp_20261104_02\r64-backup-armor-ricochet.json.135103`。

---

## 2. 破碎面具 `cl` 补 1

| 项 | 值 |
|---|---|
| id | `5b432b2f5acfc4771e1c6622`（破碎面具，`cat=helmet`，`dur=40`） |
| 改前 | 记录**无 `cl` 字段**（前端 `helm.cl \|\| 0` → 显示 0 级） |
| 改后 | `"dur":40,"cl":1,"cats":[...]`（仅插入 `cl:1`） |
| 真值 | `items.5b432b2f5acfc4771e1c6622.props.armorClass = 1` |

并发保护与最小替换：

- 改前 stat：`6093854 B`，mtime `2026-11-04 13:31:40`；实际修改 `13:51:03` —— 间隔 19 分钟，**5 分钟内无人改动**；仍按稳妥做法先备份。
- 备份：`...\r64-backup-items.json.135103`，其 sha256 = `ac81f0aa82ef456f126e0d0314275c4349f9729c1da2ddf066c63d9d0aba6191`（= 改前测试基线，证明后续测试失败确由本次改动引起，而非他会话）。
- 只在该 id 记录的 4000 字符窗口内，于 `"dur":40,"cats":` 唯一锚点前插入 `"cl":1,`；未整文件重写。改后 `6093861 B`（+7 B），sha256 = `599aef5e0a7132372e3394ee0b9b840630b6a974ef19afe41f828e65c694172d`。
- 全量逐键 diff（当前 vs 备份）：5480 条中仅此 1 条不同；该条 keys `16 → 17`，新增 `{cl}`，`cl: None → 1`，其余字段 0 变化。
- 备注：`data/items.json` 在 14:13、14:17 被其它会话重写（mtime 变动），但 sha256 始终为 `599aef5e…`，内容未变；破碎面具 `cl=1` 仍在。

---

## 3. 哈希契约同步（`data/meta.json`）

| 字段 | 改前 | 改后 |
|---|---|---|
| `items.bytes` | 6094867（早已漂移，非本次引入） | **6093861**（与磁盘一致） |
| `items.sha256` | `ac81f0aa…19` | **`599aef5e…2d`** |

插入过程中曾误改到 `sources[0]`（gunsmith 源）的 `sha256/bytes`，**已还原**为 `c53a327dcdcff67a49b9fe2d150731edb4c1611dfc2f75db2ce97444dee2ef77 / 109867`；最终 `git diff data/meta.json` 中只剩 items 街区段的既有新增。

---

## 4. 测试基线更新（依赖旧哈希，非放宽断言）

| 文件 | 行 | 旧值 → 新值 | 依据 |
|---|---|---|---|
| `tests/test_r20_5c_browse_parity.py` | 173 | `ac81f0aa…19` → `599aef5e…2d` | 破碎面具 `cl` 补 `1`（真值 `armorClass=1`），`items.json` 内容哈希随之变化 |
| `tests/test_r20_6_preset_parity.py` | 175 | 同上 | 同上 |

未跳过一个用例、未放宽任何断言。

---

## 5. 一致性校验（`python tools/r58b_game_truth.py compare`）

| 指标 | 改前 | 改后 |
|---|---|---|
| `bt_same` | 158 | **158（不变）** |
| `ricochet_same` | **153** | **159（= 全部 159 条）** |
| 跳弹差异条数 | 6 | **0** |
| `diff_count`（BT + 跳弹合计） | **12** | **6** |
| `cls_same` / `dur_same` | 58 / 58 | 58 / 58（不变） |
| `local_missing_in_game` / `game_missing_in_local` | 4 / 755 | 4 / 755（不变） |

改前数字用备份文件对同一真值重算所得：`same 153 / diff 6`；改后 `same 159 / diff 0`。剩余 6 条 `diff` 全部属于 BT 层级口径问题（本体 vs 板），不在本轮范围。差异清单已刷新：`docs/r58b-game-truth-diff.json`。

---

## 6. 前端验证（真实 Chrome，端口 8797，视口 1440×900）

- 服务：`python tools/serve.py --port 8797`（8790/8791/8796 已被其它会话占用）。
- 路径：`弹药` → `逐发模拟`。
- **ZSh-1-2M（本次改动条之一）**：头盔 `ZSh-1-2M 头盔（黑色盔罩） · 4级`，命中 `头`，角度 `89°`，`Warmageddon (穿3)`，固定种子 `1`。
  - 结果列：`跳弹（甲/板）`，**首层概率 67.3%**。
  - 校验：`0.3 + 0.4×(89−75)/(90−75) = 0.6733` → 只可能来自新值 `x=0.7`；若仍是旧值 `x=0.8`，应为 `0.3+0.5×0.9333 = 76.7%`。**参数已生效。**
- **devtac_old（`66bdc28a…`）**：该件是面罩（facecover），`cat` 无值，逐发模拟的头盔目录 41 项中**不包含它**（`devtacInPicker=false`），UI 无法把它选为头盔层（既有目录规则，与本轮数据无关）。改在同页直接验证数据+引擎：
  - 页面内 `fetch data/armor-ricochet.json` → `{"x":0,"y":0,"z":75}`；
  - `CS.ricochetChance(当前值, a)` → `75°/80°/85°/89°/90°` 全部 **0**；
  - 同函数喂旧值 `(0.9,0.4,75)` → `0.400 / 0.567 / 0.733 / 0.867 / 0.900`。即：改前会跳弹（89° 时 86.7%），改后恒为 0。
- **破碎面具**：模拟头盔下拉显示 **`破碎面具 · 1级`**（改前按 `cl||0` 会显示 0 级）。
- 截图：`.shots/r64-ricochet-zsh-8797.png`（1440×900，214258 B，PNG IHDR 实测 1440×900）。画面含：`头盔 1 ZSh-1-2M 头盔（黑色盔罩） · 4级`、`→ 跳弹（89° · 概率 67.3% · 掷 0.527）`。
- 验证脚本（临时，未入库）：`C:\Users\Administrator\Documents\Trae-CN\temp_20261104_02\r64_frontend_check.py`。

---

## 7. 测试

`python -m pytest tests -q`：

- 本会话首次全量：**1722 passed, 1 skipped**（本轮数据改动完成后）。
- 过程中出现的 16 / 6 个失败来自**另一会话正在同时改 `combat_sim.js` / `app.js` / `tests/test_r62_golden.py`**（改到一半的状态），失败项均为甲伤/穿透 golden 与 R19.8b 分层，与跳弹数据无关。
- 对方告一段落后的稳定复跑：**1730 passed, 1 skipped, 0 failed**（用例数从 1722 增至 1730 系对方新增）。

---

## 8. 产物清单

| 文件 | 动作 |
|---|---|
| `data/armor-ricochet.json` | 改 6 条（见 §1），其余 153 条与 schema/source 不变 |
| `data/items.json` | 仅 `5b432b2f…` 插入 `"cl":1` |
| `data/meta.json` | items 块 `bytes/sha256` 同步 |
| `tests/test_r20_5c_browse_parity.py` | 基线哈希更新（1 行） |
| `tests/test_r20_6_preset_parity.py` | 基线哈希更新（1 行） |
| `docs/r58b-game-truth-diff.json` | compare 重新生成 |
| `.shots/r64-ricochet-zsh-8797.png` | 前端截图 |
| `tools/r64_apply_datafix.py` | 本轮修正脚本（新增） |
