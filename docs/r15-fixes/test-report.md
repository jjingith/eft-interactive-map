# R15 测试报告（真实执行）

## 1. 修改前基线

```
cd D:\personal\trae\02-塔科夫\eft-interactive-map
python -m pytest -q
732 passed, 1 skipped in 57.70s
```

（该数字与上一轮报告一致，但它不覆盖本轮 6 项交互/机制问题，详见 `baseline.md`。）

同时记录：

```
node --check app.js        # exit 0
node --check combat_sim.js # exit 0
```

## 2. 修改后全量回归

```
python -m pytest -q
757 passed, 1 skipped in 48.68s
```

样式最终调整（铭牌/血条/总量）后的最后一次全量回归：

```
python -m pytest -q
757 passed, 1 skipped in 48.22s
```

- 新增 **25** 项（`tests/test_r15_fixes.py`），未删除、未跳过、未弱化任何旧测试。
- 唯一 skip 为既有用例，与本轮无关。

专项运行：

```
python -m pytest tests\test_r15_fixes.py -q      # 25 passed
node tests\js\combat_sim_r15_test.js             # 输出场景 JSON 供 Python 断言
```

## 3. 新增测试清单（25）

### A. 射速（4）

| 用例 | 断言 |
|---|---|
| `test_rpm_interval_matches_gun_data` | rpm 600/900/150 的逐发时刻分别为 `[100,200] / [67,133] / [400,800]` |
| `test_rpm_required_no_silent_fallback` | `rpm=0` 与缺失 `rpm` 均抛 `rpm required (>0)` |
| `test_gun_rates_dataset_complete` | `data/gun-rates.json` 163 把、`missingCount=0`、每项 `rpm>0`、来源为 tarkov.dev |
| `test_ui_rpm_is_readonly_and_tied_to_gun` | `#am-sim` 无 rpm 数字框；存在 `gun-pick`/`gun-info`；模式下拉仅在多模式时渲染 |

### D. Boss 装备池（4）

| 用例 | 断言 |
|---|---|
| `test_bosses_dataset_health_and_pools` | 4 个 Boss、逐部位血量和 = `total`；`platesPolicy` 合法；护卫血量/装备缺失时标 `missing` |
| `test_bosses_pool_ids_exist_in_items` | 所有池内装备 id 均存在于 `data/items.json`（5480 件） |
| `test_generic_pools_are_not_enforced` | PMC/Scav `enforced=false` 且 `confidence=estimated` |
| `test_ui_pool_filter_and_cleanup_wiring` | 静态断言：`amSimTargetPool`、`amSimGearCatalog(kind, allowed)`、非池内清空逻辑 |

### E. 多层护甲（9）

| 用例 | 场景 |
|---|---|
| `test_plate_penetrated_then_liner_blocks` | 情况 B：穿板后被内衬挡住，人体仅钝伤 10.29 |
| `test_no_liner_control_full_pen_body_damage` | 对照：无内衬时人体 34.29 |
| `test_blunt_reduced_by_soft_backing` | 情况 A：钝伤 8（有内衬）vs 10（无内衬） |
| `test_through_both_layers_state_chain` | 情况 C：依次穿板与内衬，人体 28.32 |
| `test_durability_feeds_next_shot` | 情况 D：第 1 发挡板（40→22），第 2 发以 22 耐久判定并穿透 |
| `test_liner_durability_independent` | 板 40→25→10、内衬 30→23→16，互不同步清零 |
| `test_material_affects_durability_loss` | 陶瓷损 18 vs 芳纶损 6 |
| `test_class_affects_penetration_result` | 3 级穿透、5 级挡住 |
| `test_armor_scenarios_reproducible` | 同种子两次结果逐字段一致 |

### F. 障碍物（6）

| 用例 | 场景 |
|---|---|
| `test_barriers_dataset_structured` | 9 条、字段齐全、`confidence=estimated`、`thickness=null` 且标注 missing |
| `test_barrier_baseline_single_and_multi` | 无遮挡 50 → 单层 42.5 → 双层 31.875 |
| `test_barrier_block_terminates_shot` | 混凝土墙挡下：人体 0 且 `layers=[]` |
| `test_barrier_order_changes_result` | 铁皮在前被挡（0）vs 木板在前（31.875） |
| `test_barrier_then_armor_uses_reduced_state` | 木板→板→内衬：42.5 / 26.23 / 19.44 |
| `test_barrier_scenarios_reproducible` | 同种子两次一致 |

### 布局与离线（2）

| 用例 | 断言 |
|---|---|
| `test_ui_order_gun_barrier_target_armor` | `app.js` 中面板构造顺序：枪械 → 弹匣 → 障碍物 → 目标类型 → 目标护甲 → 命中分布 |
| `test_runtime_offline_no_external_dependency` | 运行期资源全为本地相对路径 / `127.0.0.1`，无外部 CDN/API |

## 4. 引擎场景数据（确定性，固定种子）

`tests/js/combat_sim_r15_test.js` 输出（节选）：

```
rpm600 [100,200]   rpm900 [67,133]   rpm150 [400,800]
throwRpm0 / throwRpmMissing → "rpm required (>0)"
ePlatePenLinerBlock  body=10.29  plate: pen 40→39 dmg 50→34.29  liner: blocked blunt 10.29
ePlatePenNoLiner     body=34.29
eBluntWithLiner      blunt=8 (softBacking=true)   eBluntNoLiner blunt=10
eThroughBoth         body=28.32
eDurDrop             shot1 dur 40→22 blocked; shot2 durBefore=22 penetrated
eLinerIndependent    plate 40→25→10 ; liner 30→23→16
eMatCeramic          plate dur 40→22 ; eMatAramid 40→34
eClass3 penetrated ; eClass5 blocked
fBase 50 ; fOne 42.5 ; fTwo 31.875
fOrderAB 0 (metal chance .6 roll .72) ; fOrderBA 31.875
fBlocked 0 layers=[] ; fThenArmor plate 36→35 / 42.5→26.23 → 19.44
eReproA == eReproA2 ; fReproA == fReproA2
```

## 5. 真实浏览器验收

环境：Chrome CDP `127.0.0.1:9224`，页面 `http://127.0.0.1:8787/`。
所有操作通过 UI 元素（下拉 `change`、按钮 `click`）触发，未直接调用引擎函数。

| 步骤 | 操作 | 结果 | 截图 |
|---|---|---|---|
| 1 | 弹药页 → 逐发模拟，读取 6 个配置框标题 | `射击枪械 / 弹匣 / 障碍物 / 目标类型 / 目标护甲 / 命中分布` | `r15-01-panel-order.png` |
| 2 | 依次切换 M4A1 / AKS-74N / PKM | `800 rpm·75ms / 650 rpm·92.3ms / 650 rpm·92.3ms`，模式下拉出现 | `r15-02-gun-rpm-readonly.png` |
| 3 | 目标类型 → Boss → Tagilla | 护甲候选 2、头盔候选 2（Killa 为 1/1） | `r15-03-boss-pool-tagilla.png` |
| 4 | 给 Killa 配 6B13 M + 前后插板 + 内衬；加入木板；M995×4 | 逐层日志：掩体 → 前板 → 后板 → 钝伤（×0.8）；第 2 发板概率 2.2%，第 3 发因耐久下降升到 36.6% | `r15-04-barrier-plate-log.png` |
| 5 | 上述 4 发结束后查看血量 | Killa `胸腔 197/210`、总量 `877/890` | `r15-05-target-hp-after-run.png` |
| 6 | 跑满 5 发 | 击杀后血量面板进入死亡样式，总量 315/440 | `r15-06-target-hp-dead.png` |
| 7 | ×5 局，种子 12345 跑两次 | 两次统计完全一致；换种子文本变化 | `r15-07-multi-run-seed.png` |
| 8 | 木板+铁皮 vs 铁皮+木板 | 首层概率 60% vs 36%，结果不同 | `r15-08-barrier-multilayer-order.png` |
| 9 | 窗口尺寸 1904×814 / 1264×705 | 无横向溢出；窄窗口下血量面板在折叠线以下但不破版 | `r15-09-...1904.png`、`r15-12-...1264x705.png` |

### 控制台与网络审计

```
consoleIssues: []      exceptions: []
externalRequests: []   failedRequests: []
requests: 247 条，全部为 http://127.0.0.1:8787/
```

结论：运行期零外部请求，控制台无报错。

## 6. 未覆盖 / 未验证

- 半自动模式的实际节奏（扳机次数）未建模：仍按 `60000/rpm` 名义间隔。
- 0 耐久护甲、跳弹角度、障碍厚度均无可靠依据，见 `armor-layer-research.md` §6 与 `barrier-research.md` §7。
- Killa / Tagilla 护卫无血量与装备数据，因此不提供该目标。
