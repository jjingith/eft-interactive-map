# R16 测试与验收报告（真实执行）

## 1. 修改前基线

```
cd D:\personal\trae\02-塔科夫\eft-interactive-map
python -m pytest -q
757 passed, 1 skipped in 49.84s
```

## 2. 修改后全量回归

```
python -m pytest -q
784 passed, 1 skipped in 54.11s
```

- 新增 **27** 项（`tests/test_r16_completeness.py`），未删除、未跳过、未修改任何既有测试。
- 唯一 skip 是既有用例（与本轮无关）。
- `node --check app.js` / `node --check combat_sim.js`：exit 0。

专项：

```
python -m pytest tests/test_r16_completeness.py -q      # 27 passed
node tests/js/combat_sim_r16_test.js ./combat_sim.js    # 输出 13 组场景，由 Python 断言
python -m pytest tests/test_r15_fixes.py tests/test_r14_sim.py tests/test_r14_simui.py -q   # 41 passed（无回归）
```

## 3. R16 测试清单（27）

### 方向性护甲（F，10）

| 用例 | 断言要点 |
|---|---|
| `test_direction_front_uses_only_front_layers` | 正面 layers 只有 front；后板/后内衬进 `layersSkipped` |
| `test_direction_back_uses_only_back_layers` | 背面只有 back 层 |
| `test_direction_left_uses_side_plate_only` | 左侧只碰左侧板；前/后/右都被跳过 |
| `test_front_without_front_plate_takes_full_damage` | 只有后板时正面 `layers=[]`、满伤 50 |
| `test_penetrate_then_liner_blocks_and_back_plate_untouched` | 穿板后被内衬挡住 → 只有钝伤；后板不掉耐久 |
| `test_exit_model_does_not_change_body_damage` | 出口碰撞开/关，人体伤害逐位相等 |
| `test_engine_rejects_illegal_ammo_and_magazines` | 三种非法输入都抛错 |
| `test_direction_reproducible` | 同种子两次完全一致 |
| `test_legacy_layers_without_side_still_chain` | 无 side 的旧数据仍串联（R15 不回归） |
| `test_helmet_applies_from_both_directions` | 头盔与方向无关 |

### 枪械分组与兼容（A/B，5）

`test_gun_compat_covers_all_guns`、`test_same_caliber_different_platform_magazines`、
`test_ammo_ids_exist_and_mag_ids_are_magazines`、`test_platform_dataset_and_calibers`、
`test_ui_ammo_and_mag_filter_wiring`

### Boss 名单 / 装备池（D/E，7）

`test_boss_roster_complete`、`test_boss_health_sums`、`test_boss_equipment_ids_valid`、
`test_tagilla_default_plates`、`test_default_plates_are_armor_compatible`、
`test_low_class_plate_cannot_enter_boss_pool`、`test_boss_followers_not_mixed`

### 文档 / UI / 布局 / 离线（5）

`test_docs_and_screenshots_present`、`test_ui_gun_grouping_wiring`、
`test_ui_direction_and_plate_policy_wiring`、`test_ui_scroll_and_sticky_run_button`、
`test_runtime_offline_no_external_dependency`

## 4. 真实浏览器验收（Chrome 155 headless + CDP，非 DOM 断言）

环境：`python tools/serve.py --port 8791 --no-browser --no-position --no-logs` → `http://127.0.0.1:8791`；
Chrome `--headless=new --remote-debugging-port=9226`，全部通过真实 `change`/`click` 事件操作。

| # | 操作 | 实测结果 | 截图 |
|---|---|---|---|
| 1 | 打开逐发模拟，读枪械下拉分组 | 74 个 `optgroup`，标签形如 `5.56x45 · AR-15 平台`、`5.45x39 · AK 平台` | `r16-01-gun-groups.png` |
| 2 | 口径筛选 | 选项 `9x19（20）/ 7.62x51（19）/ 5.56x45（18）/ 5.45x39（15）…` | 同上 |
| 3 | 选 M4A1 | 信息条：`AR-15 平台 · 5.56x45 · 突击步枪 · 可用弹药 11 种 · 可用弹匣 24 个`；默认弹匣 30 发 | `r16-02` |
| 4 | 选 AK-101（同口径不同族） | 弹药仍 11 种（同一组）；弹匣 **3** 个，与 M4A1 **零交集** | 记录于 `r16-smoke.json` |
| 5 | 选 AKS-74N | 口径切到 5.45x39，弹药 13 种、弹匣 13 个 | `r16-03` |
| 6 | 装填 6 发并运行 | 队列行 `5.56x45毫米 FMJ ×6（第 1–6 发）`，击杀于第 2 发，日志含方向列 | `r16-02` |
| 7 | 选 Boss → Tagilla | 护甲自动切到 `Crye Precision AVS（Tagilla 版）· 6级`；HP 面板 1220/1220 | `r16-04` |
| 8 | 查看前后插板下拉 | 前插板只有 `Cult Termite（6级 65 耐久）`；后插板只有 `Global Armor's Steel（4级 45 耐久）` | `r16-04` |
| 9 | 切方向 = 背面，装 4 发 | 日志首行 `方向 背面`，只命中 `Global Armor's Steel（后插板）`；明细写明「本方向未经过：Cult Termite（前插板）」 | `r16-06` |
| 10 | 切回正面 | 日志只出现前板；后板仅出现在"未经过"列表 | `r16-05` |
| 11 | 左侧栏滚动到底 | `scrollTop=1524 / scrollHeight=2256 / clientHeight=732`；顶部执行条 `visible=true`；页面无横向溢出 | `r16-07` |
| 12 | 1264×705 | `docW=1264`、`winW=1264`、无横向溢出；布局仍为 `372px + 604px` | `r16-08` |
| 13 | Boss → PMC 切换 | 护甲/头盔/插板全部清空（`armor="" helmet="" plates=[]`），不会残留 Killa 装备 | — |
| 14 | 控制台 / 网络 | `consoleErrors=[]`、`exceptions=[]`、请求全部为 `127.0.0.1:8791`，外部请求 0 | — |

## 5. 截图清单

`docs/r16-completeness/screenshots/`

| 文件 | 内容 |
|---|---|
| `r16-01-gun-groups.png` | 枪械分组 + 口径筛选 + 射速/平台信息 |
| `r16-02-ammo-mag-filtered.png` | M4A1 弹药/弹匣过滤 + 压弹窗口 + 逐发日志 |
| `r16-03-aks74-compat.png` | AKS-74N：口径/弹药/弹匣整组切换 |
| `r16-04-boss-tagilla-plates.png` | Tagilla 默认护甲 + 前后插板（每面仅预设板） |
| `r16-05-dir-front.png` | 正面射击日志（只经过前侧层） |
| `r16-06-dir-back.png` | 背面射击日志（只经过后侧层） |
| `r16-07-sticky-run-button.png` | 滚动到底部时顶部执行条仍可见 |
| `r16-08-narrow-1264x705.png` | 窄屏无横向溢出 |

## 6. 未解决 / 未验证

- 未在游戏客户端内实测任何机制；所有"方向性"结论来自代码 + 数据集 + wiki 页面，
  社区帖子的现象未被重新抓取验证（见 `armor-direction-research.md`）。
- `api.tarkov.dev/graphql` 不可用，Boss 血量未走 API 交叉核对（只用 fandom 页面 + 页面总量一致性校验）。
- 压弹窗口与参考图仍有 5 处差异（见 `ammo-window-review.md` §3）。
- UI 验收脚本未入库（临时目录），未固化为 CI 测试。
