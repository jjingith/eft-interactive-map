# R17 修改清单（change-log）

## combat_sim.js

1. **护甲耐久损毁公式重写**（任务 A）
   - 删除 `ard × mat × clamp(pen/(cls×10), 0.5, 2) × …`（两处单位/夹持错误）；
   - 新经验式：`base = ard(0-100) × 材质毁损系数 × 穿深 × 0.012`；
     穿透 ×0.85（wiki 10–15%）；未穿 `0.55 + 0.55×min(1, ratio)` 夹持 [0.55, 1.10]；下限 1；
   - 每层日志新增 `durBase / durMul / durConfidence='estimated'`；
   - 0 耐久行为保留但显式标注 `zeroDurConfidence='estimated'` + 说明。
2. **黑化分散倍率修正**（补充任务）
   - 腿 0.49 → **0.7**（wiki Health system verified）；臂 0.49、胃 1.05 不变并标注 verified。
3. **穿过人体碰撞箱的估算续命中**（补充任务，默认关闭）
   - `cfg.throughBody='estimate'`：弹体 ×0.6 衰减后按**正常命中**结算到续命中部位；
     `CS.THROUGH_BODY_NEXT` 映射；日志 `throughBody{confidence:'estimated'}`。
4. **`CS.buildMagazineFromPreset(slots, capacity)`**（任务 C）
   - 纯函数：Top → Loop 循环 → Bottom；容量/配置校验；warnings（末轮截断 / 循环区为空）。

## app.js

1. **预设压弹编辑器**（任务 C）：五行（首发/循环×3/末发）、本地图标、弹药下拉（枪械白名单）、
   数量输入（循环行=每轮发数）、拖拽交换分区身份 + 等价按钮、「按预设装填弹匣」；
   换枪时清空预设行里不兼容的弹药并提示。
2. **口径联动加固**（任务 B）：`ensureAmmo()` 晚到补渲染；弹药下拉 `dataset.gun/cal` 归属标记；
   数据未加载时显示「正在加载弹药数据…」；面板显示 **R17 构建 · compat 日期** 可见标记。
3. 顶部操作条 hint 接入构建标记。

## style.css

- 新增 `.am-sim-presrows / .am-sim-prrow / .am-sim-pr-* / .am-sim-genbtn / .am-sim-dragsource / .am-sim-droptarget`。

## tests

- 新增 `tests/js/combat_sim_r17_test.js`（A/C/肉体三类场景原始输出）；
- 新增 `tests/test_r17_fixes.py`（31 项断言，含用户案例固定回归）；
- 未删除、未跳过、未修改任何既有测试。

## docs

- 新增 `docs/r17-fixes/`：baseline / armor-durability-research / caliber-filter-investigation /
  magazine-preset-design / body-damage-research / change-log / test-report / screenshots。

---

## R17S（补充任务）修改清单

### index.html
- `app.js` / `combat_sim.js` / `style.css` 引用加 `?v=r17s2`：旧会话 memory cache 不再吃旧脚本。

### app.js
1. **预设压弹重做（R17S-一）**
   - 删 `preset-ammo` 下拉 → 每行 44×44 可点击方框（`sim-preset-pick`）+ 弹窗（`ammo-dialog`），
     列表只含当前枪械 allowedAmmo、按穿透力**数值**升序、点击写入；
   - 删旧独立「填子弹」UI（`ammo-pick` / `mag-count` / `sim-load`）及对应 handler，
     删除无调用的 `renderSimAmmoOptions`；队列「清空」保留；
   - Top/Loop/Bottom 序列生成器 `buildMagazineFromPreset`（combat_sim.js）原样保留；
   - 换枪清理（`amSimOnGunChanged`）同步清预设行不兼容弹药。
2. **命中分布互斥复选（R17S-四）**：`hit-fixed` / `hit-dist` 两个 checkbox，
   change 事件保证「不允许双选、不允许双不选」；`renderSimHitMode` 同步勾选态与显示区。
3. **随机种子策略（R17S-五）**：`seedFixed` 复选框；未勾选时输入框禁用，
   每次模拟 `amSimRandomSeed()` 用 `crypto.getRandomValues` 生成新基种子
   （crypto 不可用 → Math.random fallback 并记录 `seedSource`，不静默固定）；
   勾选后手填种子可复现；单次/多次结果摘要都记录「基种子 X（来源）」。
4. 构建标记 `AM_BUILD = "R17S2"`（与 ?v= 同步）。

### style.css
- 新增 `.am-sim-chk / .am-sim-prbox / .am-sim-przone / .am-sim-ammodlg / .am-sim-dlg*` 等样式。

### tests
- `test_r17_fixes.py`：`test_ui_preset_loader_wiring` 改为断言新交互（方框/弹窗/旧 UI 已删/数值排序）；
  新增 `test_ui_hit_mode_mutex_and_seed_wiring`、`test_index_html_versioned_assets`；
  `test_ui_ammo_list_reload_hooks` 断言 R17S2 标记。
- `test_r16_completeness.py`：`test_ui_ammo_and_mag_filter_wiring` 的白名单校验断言
  从旧装填按钮路径（`allowedNow.indexOf(pick.value)`）迁移到弹窗写入路径
  （`allowNow.indexOf(ca)`）——同一不变量、新入口，非弱化。

---

## R17S2（二次修正）修改清单

### combat_sim.js
- `buildMagazineFromPreset`：首发/末尾改为**多条目数组**（旧实现 `!top`/`!bottom` 静默忽略
  第二条及以后的固定区配置）；输出顺序 = 首发区配置顺序 → 循环 → 末尾区配置顺序。

### app.js
- 预设编辑器重写：三分区渲染（`AM_SIM_ZONES` + `.am-sim-zsec`），行结构
  角色标签→序号→方框→名称→数量→×；换区按钮删除；`amSimPresetDrop` +
  `amSimFirstEmptyInZone` 实现新拖放语义（空槽迁移 / 无空槽整行迁移 / 同区排序）。
- `sim-preset-clear` 同时清数量；弹窗 document 级 mousedown 外点关闭。
- 删除逐发预览列表：`renderSimMagList` 精简为弹匣图标 + 容量提示；
  `amSimQueueBlocks` / `amSimMoveQueueBlock` / `sim-mag-up/down/del` 移除。
- （工程事故修复：一次批量替换未落盘导致预设函数整块丢失，已用等价内容恢复并
  逐函数 grep + node --check 验证。）

### style.css
- 新增 `.am-sim-zsec / .am-sim-zhead / .am-sim-ztitle / .am-sim-zempty` 分区样式与拖放高亮。

### tests
- `tests/js/combat_sim_r17_test.js` +5 场景（exact30 / multiFixed / threeLoop / topMultiOnly / capTruncTop）。
- `tests/test_r17_fixes.py`：+`test_preset_exact30_no_missing_rounds`（逐位 30 发断言）、
  +`test_preset_multi_entry_fixed_zones`、+`test_preset_three_loop_ammo_alternates`、
  +`test_preset_top_multi_only_and_capacity_truncation`、+`test_ui_zone_sections_and_drag_model`；
  `test_ui_preset_loader_wiring` 更新（换区按钮已删、预览 chip 已删、分区/拖放语义存在）。

---

## R17S3（定点补丁）修改清单

### app.js
- 弹窗根节点挂 document.body（`amSimDlgRoot`，fixed 浮层 + 事件委托），inline 容器删除；
  pick 支持同行二次点击切换；新增 Esc 关闭；外点 mousedown 关闭改查 body 根。
- `amSimAmmoShort`：口径前缀剥离的型号缩写映射；行徽标（.am-sim-prshort）与
  弹窗选项共用。
- 拖拽：槽位加稳定 uid；`amSimPresetDrop(s, fromUid, targetZone, targetUid, pos)`；
  dragover 显示 before/after 插入指示（am-sim-dropbefore/after）；同区按插入位置
  真排序，跨区迁移按插入位置落位（不再总追加末尾）。
- 删除 `renderSimMagList` / `capTagRefresh` / `sim-clear-mag` 及 build 中
  lfoot（弹匣图标+清空队列）/loadRows/magList；`AM_BUILD="R17S3"`。

### style.css
- `.am-sim-ammodlg` 改 fixed 浮层；删除旧队列 CSS 段；新增
  `.am-sim-prshort`（缩写徽标）、`.am-sim-dropbefore/after`（插入指示）、
  `.am-sim-dlgicon/.am-sim-dlgshort`。

### index.html
- 资源版本 `?v=r17s3`。

### tests
- `tests/js/combat_sim_r17_test.js`：+loopCAB（循环区顺序驱动弹序）、+topOrder。
- `test_r17_fixes.py`：+顺序驱动弹序两条、+短名映射区分性断言；静态断言更新为
  body 弹窗/Esc/uid/插入指示/旧队列代码已删；R14 旧入口断言迁移。

---

## R17S4（拖拽插入 + 五类口径 + 命中率）修改清单

### combat_sim.js
- `simulate`：新增 `cfg.hitChance`。每发独立命中判定；`>=1`/`<=0` 不消耗 rng（保证 100% ≡ 关闭）。
  未命中走 `resolveShot({missTarget:true})`：掩体照常结算，跳过护甲/人体；弹药与时间照常推进。
  未命中调用 `pickPart` 被跳过（不伪造部位）。结果新增 `hits/misses/hitChance`。
- `resolveShot`：新增 `missTarget` 短路（掩体之后、护甲之前）：`miss=true`、无穿甲/伤害、无耐久变化。
- `applyDamage` 仅在 `hit` 且未死亡时调用。
- `buildMagazineFromPreset`：循环区条目 >5 时拒绝（错误信息「循环区最多 5 种弹药」）。

### app.js
- 预设模型改为**可变条目**（zone 只是条目属性），删除固定五槽位/空槽迁移；
  每区新增「＋ 添加一行」；`AM_SIM_ZONE_MAX=5`（循环 = 最多 5 种弹药）。
- `amSimPresetDrop` 重写：跨区为**插入**（前/后由指针位置决定），源区不留副本、不覆盖目标；
  同区为真排序。全部按 `uid` 定位（`amSimIdxByUid`），不再用数组下标识别行。
- 口径：新增 `data/caliber-groups.json` + `ensureSimCalGroups` + `amSimCalMeta`；
  `rebuildSimGunOptions` 按五大类固定顺序分 optgroup、组内弹径降序；未识别口径单列。
- 命中率 UI：`hit-rate-on` 复选框 + `hit-rate` 输入（未勾选时 display:none）；`renderSimHitRate`；
  `amSimCfgFromUI` 夹取 0–100、非法值 0；cfg 仅在启用时传 `hitChance`。
- 日志：新增「命中」列（命中/未命中），未命中行部位/结果明确标注；汇总显示命中数与命中率。
- `AM_BUILD="R17S4"`。

### index.html
- 资源版本 `?v=r17s4`。

### data
- 新增 `data/caliber-groups.json`（29 个口径 → 五类 + 弹径 + 例外注记）。

### tests
- `combat_sim_r17_test.js`：+命中率 5 场景（off/100/0/50 复现/未命中+掩体）、+循环 6 种拒绝；
  +loopCAB / topOrder 顺序驱动弹序（上一轮补充任务遗留）。
- `test_r17_fixes.py`：+命中率 5 项、循环上限、口径分组覆盖/排序、UI 接线；
  既有拖拽/弹窗断言迁移到 R17S4 语义（插入 + uid + 可变条目）。

---

## R17S4（拖拽插入 + 五类口径 + 命中率）修改清单

### combat_sim.js
- `simulate`：新增 `cfg.hitChance`。每发独立命中判定；`>=1`/`<=0` 不消耗 rng（保证 100% ≡ 关闭）。
  未命中走 `resolveShot({missTarget:true})`：掩体照常结算，跳过护甲/人体；弹药与时间照常推进。
  未命中调用 `pickPart` 被跳过（不伪造部位）。结果新增 `hits/misses/hitChance`。
- `resolveShot`：新增 `missTarget` 短路（掩体之后、护甲之前）：`miss=true`、无穿甲/伤害、无耐久变化。
- `applyDamage` 仅在 `hit` 且未死亡时调用。
- `buildMagazineFromPreset`：循环区条目 >5 时拒绝（错误信息「循环区最多 5 种弹药」）。

### app.js
- 预设模型改为**可变条目**（zone 只是条目属性），删除固定五槽位/空槽迁移；
  每区新增「＋ 添加一行」；`AM_SIM_ZONE_MAX=5`（循环 = 最多 5 种弹药）。
- `amSimPresetDrop` 重写：跨区为**插入**（前/后由指针位置决定），源区不留副本、不覆盖目标；
  同区为真排序。全部按 `uid` 定位（`amSimIdxByUid`），不再用数组下标识别行。
- 口径：新增 `data/caliber-groups.json` + `ensureSimCalGroups` + `amSimCalMeta`；
  `rebuildSimGunOptions` 按五大类固定顺序分 optgroup、组内弹径降序；未识别口径单列。
- 命中率 UI：`hit-rate-on` 复选框 + `hit-rate` 输入（未勾选时 display:none）；`renderSimHitRate`；
  `amSimCfgFromUI` 夹取 0–100、非法值 0；cfg 仅在启用时传 `hitChance`。
- 日志：新增「命中」列（命中/未命中），未命中行部位/结果明确标注；汇总显示命中数与命中率。
- `AM_BUILD="R17S4"`。

### index.html
- 资源版本 `?v=r17s4`。

### data
- 新增 `data/caliber-groups.json`（29 个口径 → 五类 + 弹径 + 例外注记）。

### tests
- `combat_sim_r17_test.js`：+命中率 5 场景（off/100/0/50 复现/未命中+掩体）、+循环 6 种拒绝；
  +loopCAB / topOrder 顺序驱动弹序（上一轮补充任务遗留）。
- `test_r17_fixes.py`：+命中率 5 项、循环上限、口径分组覆盖/排序、UI 接线；
  既有拖拽/弹窗断言迁移到 R17S4 语义（插入 + uid + 可变条目）。

---

## R17S5（空行可拖）修改清单

### app.js
- `amSimPresetDrop`：删除 `if (!src.ammoId) { ... "这一行还没有弹药 ..." }` 拦截 —— 空行与已选弹药行同样可拖，
  拖拽只改「分区 + 顺序」。
- 上限语义拆分：新增 `amSimPresetZoneAmmoCount()`（只数已配置弹药）；
  跨区插入仅对**带弹药**的条目校验「该区 5 种弹药」，空行只受 `AM_SIM_ZONE_ROWS_MAX = 8` 行数保护。
- `sim-preset-add` / 「＋ 添加一行」按钮：改用行数上限（含空行），提示文案区分「5 种弹药」与「8 行」。
- `sim-preset-choose`：把空行填成弹药时校验该区弹药种类上限（防绕过），拒绝时提示且原配置不变。
- 拖拽提示文案：空行追加「（该行仍为空，可点方框选择弹药）」；预设说明补充「空行也可，不需要先选弹药」。
- `AM_BUILD = "R17S5"`。

### index.html
- 资源版本 `?v=r17s5`（样式/combat_sim/app 三处）。

### tests
- 新增 `tests/js/preset_drag_model_test.js`：运行时从 `app.js` **抽取真实实现**（`amSimPresetDrop` 等）
  跑 9 组确定性场景（空行跨区/区内排序/上限/uid 稳定性/不覆盖目标）。
- 新增 `tests/test_r17s5_empty_drag.py`：11 项断言（含源码级「拦截已删除」「draggable 无条件」「构建标记 R17S5」）。
