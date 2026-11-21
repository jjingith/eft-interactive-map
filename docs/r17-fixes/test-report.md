# R17（含 R17S 补充）测试报告

日期：2026-10-23 · 执行环境：Windows / Python 3.14 / Node 22.22.2 / Chrome headless CDP

## 1. 命令与结果

| 命令 | 结果 |
|---|---|
| `C:\Python314\python.exe -m pytest -q`（修改前基线） | **784 passed, 1 skipped**（47s 级） |
| `C:\Python314\python.exe -m pytest -q`（R17+R17S 全部完成后） | **817 passed, 1 skipped**（约 47s） |
| `node --check app.js` / `node --check combat_sim.js` | exit 0 / exit 0 |
| `node tests/js/combat_sim_r17_test.js ./combat_sim.js` | 全部引擎场景通过（数值见 §3） |
| `node tests/js/combat_sim_r15_test.js ./combat_sim.js` | 27 场景通过，与 `docs/r15-fixes/scenario-output.json` 一致 |

新增/迁移测试说明（均为等价迁移或新增，无删除/跳过/弱化）：

- `test_r17_fixes.py`：+`test_ui_hit_mode_mutex_and_seed_wiring`、+`test_index_html_versioned_assets`；
  `test_ui_preset_loader_wiring` 改断言「方框 + 弹窗」新交互且旧 UI 已删；
  `test_ui_ammo_list_reload_hooks` 改断言 `AM_BUILD="R17S2"` 与 `?v=r17s2`。
- `test_r16_completeness.py`：白名单硬校验断言从旧装填按钮路径迁移到弹窗写入路径
  （`allowNow.indexOf(ca) < 0`），同一不变量。
- `test_r14_simui.py`：`hit-mode` 下拉断言迁移为 `hit-fixed`/`hit-dist` 互斥复选框断言；
  script 顺序断言允许 `?v=` 版本参数。

## 2. 引擎专项（护甲损毁 / 黑化分散 / 续命中）

- 用户案例回归：5.56 HP（pen 7, ard 22）× 5 级陶瓷 Granit（耐久 50）→
  每发甲损 ≈ 1.1（修复前 7），8 发打不穿；`durConfidence='estimated'` 记录在层日志。
- 材质区分：陶瓷/钢/钛/铝同弹同等级下损毁量按材质毁损系数分离。
- 穿透 vs 未穿透：同弹同板未穿透时甲损更高（×0.99 vs ×0.85 系数路径）。
- 黑化分散：臂 0.49 / 腿 0.7 / 胃 1.05（wiki Health system verified），腿倍率由 0.49 修正。
- 续命中（throughBody='estimate'，默认关）：手臂穿透后命中胸腔按正常命中结算，
  不套用黑化倍率；开关不影响入体伤害，只影响对侧板耐久。

## 3. 真实浏览器验收（Chrome CDP，headless，127.0.0.1:8791）

### 3.1 六口径 × 弹药弹窗（R17S-二）

| 枪械 | 口径 | 弹窗弹药数 | 口径集合 | 穿透力升序 | 弹匣数 |
|---|---|---|---|---|---|
| M4A1 | 5.56x45 | 11 | {5.56x45} | ✅ (3,7,11…) | 24 |
| AKS-74N | 5.45x39 | 13 | {5.45x39} | ✅ (9,13,15…) | 13 |
| AKM | 7.62x39 | 9 | {7.62x39} | ✅ (15,20,26…) | 17 |
| 雷明顿 Model 700 | 7.62x51 | 8 | {7.62x51} | ✅ (15,30,37…65) | 9 |
| MP5 | 9x19 | 9 | {9x19} | ✅ (2,8,10…) | 3 |
| MP-133 | 12g | 17 | {12g} | ✅ | 7 |

### 3.2 预设压弹（R17S-一）

- Top3 + Loop(HP×1, RRLP×1) + Bottom2 → 30 发 STANAG：
  `Warmageddon×3（1–3）→ HP/RRLP 交替 22 发（4–27，循环截断正确）→ M856×2（29–30）`，30/30 ✅
- 行 1 拖到行 3：`[top,loop,loop,loop,bottom] → [loop,loop,top,loop,bottom]`，弹药/数量随行迁移 ✅
- 截图：`r17s-01-ammo-dialog-m4a1.png`、`r17s-02-preset-filled.png`、`r17s-03-after-drag.png`

### 3.3 命中模式互斥（R17S-四）

`初始 {固定✓,随机✗}` → 点随机 `{固定✗,随机✓}`（部位行隐藏、权重区显示）→
再点随机取消 → 自动回到固定 ✅ → 点固定保持固定 ✅（全程无双选/双不选）。

### 3.4 随机种子（R17S-五）

- 默认输入框禁用 ✅；两次运行基种子 `388584842` → `976605057`（每次不同）✅；
- 来源均为 `crypto.getRandomValues` ✅；摘要显示「基种子 X（crypto.getRandomValues）」✅；
- 勾选固定种子 → 输入框启用，填 12345 两次运行：结果摘要逐字符一致（可复现）✅；
- 取消勾选 → 输入框再次禁用 ✅。

### 3.5 环境

- 控制台错误 0、未捕获异常 0；
- 资源请求全部 `127.0.0.1:8791`，**外部请求 0**（运行期离线保持）；
- 页面加载 `combat_sim.js?v=r17s2`、`app.js?v=r17s2`（缓存修复生效）；
- 截图：`r17s-04-seed-result.png`。

## 4. 未解决问题

- 弹窗为页面内浮层，与参考图的弹体轮廓竖排图案仍有视觉差异（见 magazine-preset-design.md §7.3）；
- 护甲损毁公式仍为 `estimated`（官方未公开服务器公式），参数与依据见 armor-durability-research.md；
- throughBody 续命中模型为估算（默认关闭）；
- Git 工作区仍为未提交状态（遵循「不擅自提交」约束）。

---

## 5. R17S2 二次修正（2026-10-23 追加）

### 5.1 测试

| 命令 | 结果 |
|---|---|
| `python -m pytest -q` | **822 passed, 1 skipped**（47.51s；R17S 前 817 → +5 引擎/UI 专项，无删除/弱化） |
| `node --check app.js` / `combat_sim.js` | exit 0 / exit 0 |

新测试：`test_preset_exact30_no_missing_rounds`（30 发逐位断言）、
`test_preset_multi_entry_fixed_zones`、`test_preset_three_loop_ammo_alternates`、
`test_preset_top_multi_only_and_capacity_truncation`、`test_ui_zone_sections_and_drag_model`。

### 5.2 真实浏览器验收（Chrome CDP，8 项全部通过）

| # | 操作 | 结果 |
|---|---|---|
| 1 | 空布局 | 三分区（1/3/1 行）+ 标题分隔，共 5 行，全部 draggable ✅ |
| 2 | 五行选弹（弹窗） | 逐行写入成功，行内显示图标+名称+穿/伤 ✅ |
| 3 | 弹窗外部点击 | 自动关闭，已选弹药保留 ✅ |
| 4 | 小叉叉 | 只清空本行（弹药+数量），其余 3 行不受影响 ✅ |
| 5 | 行1 拖入循环区 | 配置迁入循环空槽，首发恢复空槽 ✅ |
| 6 | 拖回首发（可逆） | 首发重新有弹，循环出现空槽 ✅ |
| 7 | 循环行拖入已占用首发 | 首发区 2 个条目（多弹药），该弹不再参与循环 ✅ |
| 8 | 装填 30 发 | 「已装 30 / 30 发 · 剩余 0」，预览列表 DOM = 0（已删非隐藏）✅ |
| 9 | 30 发逐发日志（Tagilla） | 编号 1–30 连续无跳号；逐发弹药与预期序列逐位一致（seqMatch=true）：1–3 HP → 4–28 RRLP/M856 交替 25 发 → 29–30 FMJ ✅ |
| 10 | 循环区内两行交换 → 重装填 → 模拟 | 第 4/5 发弹药随新循环顺序互换（shot4=M856, shot5=RRLP）✅ |
| 11 | 控制台 / 网络 | 0 错误、0 异常、外部请求 0、无横向溢出 ✅ |

截图：`screenshots/r17s2-01..05`。

---

## 5. R17S2 二次修正（2026-10-23 追加）

### 5.1 测试

| 命令 | 结果 |
|---|---|
| `python -m pytest -q` | **822 passed, 1 skipped**（47.51s；R17S 前 817 → +5 引擎/UI 专项，无删除/弱化） |
| `node --check app.js` / `combat_sim.js` | exit 0 / exit 0 |

新测试：`test_preset_exact30_no_missing_rounds`（30 发逐位断言）、
`test_preset_multi_entry_fixed_zones`、`test_preset_three_loop_ammo_alternates`、
`test_preset_top_multi_only_and_capacity_truncation`、`test_ui_zone_sections_and_drag_model`。

### 5.2 真实浏览器验收（Chrome CDP，8 项全部通过）

| # | 操作 | 结果 |
|---|---|---|
| 1 | 空布局 | 三分区（1/3/1 行）+ 标题分隔，共 5 行，全部 draggable ✅ |
| 2 | 五行选弹（弹窗） | 逐行写入成功，行内显示图标+名称+穿/伤 ✅ |
| 3 | 弹窗外部点击 | 自动关闭，已选弹药保留 ✅ |
| 4 | 小叉叉 | 只清空本行（弹药+数量），其余 3 行不受影响 ✅ |
| 5 | 行1 拖入循环区 | 配置迁入循环空槽，首发恢复空槽 ✅ |
| 6 | 拖回首发（可逆） | 首发重新有弹，循环出现空槽 ✅ |
| 7 | 循环行拖入已占用首发 | 首发区 2 个条目（多弹药），该弹不再参与循环 ✅ |
| 8 | 装填 30 发 | 「已装 30 / 30 发 · 剩余 0」，预览列表 DOM = 0（已删非隐藏）✅ |
| 9 | 30 发逐发日志（Tagilla） | 编号 1–30 连续无跳号；逐发弹药与预期序列逐位一致（seqMatch=true）：1–3 HP → 4–28 RRLP/M856 交替 25 发 → 29–30 FMJ ✅ |
| 10 | 循环区内两行交换 → 重装填 → 模拟 | 第 4/5 发弹药随新循环顺序互换（shot4=M856, shot5=RRLP）✅ |
| 11 | 控制台 / 网络 | 0 错误、0 异常、外部请求 0、无横向溢出 ✅ |

截图：`screenshots/r17s2-01..05`。

---

## 6. R17S3 定点补丁（2026-10-23 追加）

### 6.1 测试

| 命令 | 结果 |
|---|---|
| `python -m pytest -q`（修改前基线） | 822 passed, 1 skipped |
| `python -m pytest -q`（修改后） | **825 passed, 1 skipped**（47.12s；+3 引擎/映射测试，R14 旧入口断言等价迁移） |
| `node --check app.js / combat_sim.js` | exit 0 / exit 0 |

### 6.2 真实浏览器验收（Chrome CDP，全部通过）

| # | 操作 | 结果 |
|---|---|---|
| 1 | 点击第 1 行方框 | 弹窗出现：`parentNode===body`、`position:fixed`、`z-index:9990`、不在左栏内 ✅ |
| 2 | 弹窗列表 | 11 项（M4A1 全兼容弹药）、穿透力**数值**升序（3→7→11→18→23→26→31→38→44…）、每项含本地图标+缩写徽标+口径+穿/伤/甲伤 ✅ |
| 3 | 选择写入 | 只写入目标行，图标+缩写+名称立即更新 ✅ |
| 4 | 再次点击该行方框 | 弹窗重开可换型号（同行二次点击=切换）✅ |
| 5 | 点击外部 / 按 Esc | 均自动关闭，已选弹药不丢失 ✅ |
| 6 | 五行徽标 | HP / MK 255 Mod / M856 / FMJ——同口径不同型号可区分（左下角叠加，Tooltip 全名）✅ |
| 7 | 装填按钮下方 | 弹匣图标 0、清空队列按钮 0、load-rows 0、maglist 0（DOM 级删除非隐藏）；容量提示保留（0/30→30/30）✅ |
| 8 | 30 发模拟（Tagilla） | 逐发日志 30 发：1–3 HP → 4–28 RRLP/M856 交替 → 29–30 FMJ ✅ |
| 9 | 拖拽交换循环两行（插入指示 after） | 指示条显示 ✅；重新装填+模拟后第 4 发 RRLP→**M856**、循环交替整体翻转（orderChanged=true）✅ |
| 10 | 固定种子 777 两次运行 | 30 发逐发日志完全一致（reproducible=true）✅ |
| 11 | 环境 | 构建标记 R17S3；0 控制台错误、0 异常、外部请求 0、无横向溢出 ✅ |

截图：`screenshots/r17s3-01..05`。

### 6.3 尚存缺陷

- 弹窗为页面内 styled 浮层（非游戏客户端截图式外观）；名称超长的霰弹类弹药
  缩写回退为截断原名（Tooltip 补全）。

---

## 6. R17S3 定点补丁（2026-10-23 追加）

### 6.1 测试

| 命令 | 结果 |
|---|---|
| `python -m pytest -q`（修改前基线） | 822 passed, 1 skipped |
| `python -m pytest -q`（修改后） | **825 passed, 1 skipped**（47.12s；+3 引擎/映射测试，R14 旧入口断言等价迁移） |
| `node --check app.js / combat_sim.js` | exit 0 / exit 0 |

### 6.2 真实浏览器验收（Chrome CDP，全部通过）

| # | 操作 | 结果 |
|---|---|---|
| 1 | 点击第 1 行方框 | 弹窗出现：`parentNode===body`、`position:fixed`、`z-index:9990`、不在左栏内 ✅ |
| 2 | 弹窗列表 | 11 项（M4A1 全兼容弹药）、穿透力**数值**升序（3→7→11→18→23→26→31→38→44…）、每项含本地图标+缩写徽标+口径+穿/伤/甲伤 ✅ |
| 3 | 选择写入 | 只写入目标行，图标+缩写+名称立即更新 ✅ |
| 4 | 再次点击该行方框 | 弹窗重开可换型号（同行二次点击=切换）✅ |
| 5 | 点击外部 / 按 Esc | 均自动关闭，已选弹药不丢失 ✅ |
| 6 | 五行徽标 | HP / MK 255 Mod / M856 / FMJ——同口径不同型号可区分（左下角叠加，Tooltip 全名）✅ |
| 7 | 装填按钮下方 | 弹匣图标 0、清空队列按钮 0、load-rows 0、maglist 0（DOM 级删除非隐藏）；容量提示保留（0/30→30/30）✅ |
| 8 | 30 发模拟（Tagilla） | 逐发日志 30 发：1–3 HP → 4–28 RRLP/M856 交替 → 29–30 FMJ ✅ |
| 9 | 拖拽交换循环两行（插入指示 after） | 指示条显示 ✅；重新装填+模拟后第 4 发 RRLP→**M856**、循环交替整体翻转（orderChanged=true）✅ |
| 10 | 固定种子 777 两次运行 | 30 发逐发日志完全一致（reproducible=true）✅ |
| 11 | 环境 | 构建标记 R17S3；0 控制台错误、0 异常、外部请求 0、无横向溢出 ✅ |

截图：`screenshots/r17s3-01..05`。

### 6.3 尚存缺陷

- 弹窗为页面内 styled 浮层（非游戏客户端截图式外观）；名称超长的霰弹类弹药
  缩写回退为截断原名（Tooltip 补全）。

---

## 7. R17S4（2026-10-23 追加）

### 7.1 测试

| 命令 | 结果 |
|---|---|
| `python -m pytest -q`（修改前基线） | 825 passed, 1 skipped |
| `python -m pytest -q`（修改后） | **833 passed, 1 skipped**（47.3s，新增 8 项；旧断言按新语义等价迁移） |
| `node --check app.js / combat_sim.js` | exit 0 / exit 0 |

新增：命中率 5 项（100% ≡ 关闭、0% 无伤害无磨损、50% 可复现、未命中仍结算掩体）、循环上限、
口径分组覆盖（29/29）与组内降序、UI 接线。

### 7.2 真实浏览器验收

| 项 | 结果 |
|---|---|
| 首发 D 拖入循环首位 | 首发空、循环 D,A,B,C（A/B/C 全保留），装填 30/30 ✅ |
| 末尾 D 拖入循环第 2 位 | 循环 A,D,B,C、末尾空 ✅ |
| 循环 B 拖入首发 / 循环 C 拖到首位 | 首发 B、循环 A,C / 循环 C,A,B ✅ |
| 循环加到 5 种 | 5 条全部保留，30 发按 5 种循环 6 轮 ✅ |
| 第 6 种被拒 | 添加按钮 disabled；拖入被拒且配置零变化 + 提示 ✅ |
| 五类口径 | 组标签顺序与期望一致、全部组内 dia 降序、无未匹配口径 ✅ |
| 口径筛选/换枪 | 5.45 → 15 把一致；M4A1 24 弹匣 / AK-101 3 弹匣，弹药列表随后更新 ✅ |
| 命中率默认关 | 复选框未勾选、输入框 display:none 不可见 ✅ |
| 0% | 命中 0/未命中 30，目标存活、护甲 65/65 未扣、弹药耗尽 ✅ |
| 100% | 与关闭同样 29 发击杀（逐发完全一致由引擎测试锁定）✅ |
| 50% × 同种子两次 | 13 命中/17 未命中，两次结果逐字一致 ✅ |
| 命中率 + 随机命中 | 部位出现头/胸/胃，未命中仍存在，两模式互斥且组合正确 ✅ |
| 环境 | 构建 R17S4、0 控制台错误、0 外部请求、无横向溢出 ✅ |

截图：`r17s4-01..08`。

---

## 7. R17S4（2026-10-23 追加）

### 7.1 测试

| 命令 | 结果 |
|---|---|
| `python -m pytest -q`（修改前基线） | 825 passed, 1 skipped |
| `python -m pytest -q`（修改后） | **833 passed, 1 skipped**（47.3s，新增 8 项；旧断言按新语义等价迁移） |
| `node --check app.js / combat_sim.js` | exit 0 / exit 0 |

新增：命中率 5 项（100% ≡ 关闭、0% 无伤害无磨损、50% 可复现、未命中仍结算掩体）、循环上限、
口径分组覆盖（29/29）与组内降序、UI 接线。

### 7.2 真实浏览器验收

| 项 | 结果 |
|---|---|
| 首发 D 拖入循环首位 | 首发空、循环 D,A,B,C（A/B/C 全保留），装填 30/30 ✅ |
| 末尾 D 拖入循环第 2 位 | 循环 A,D,B,C、末尾空 ✅ |
| 循环 B 拖入首发 / 循环 C 拖到首位 | 首发 B、循环 A,C / 循环 C,A,B ✅ |
| 循环加到 5 种 | 5 条全部保留，30 发按 5 种循环 6 轮 ✅ |
| 第 6 种被拒 | 添加按钮 disabled；拖入被拒且配置零变化 + 提示 ✅ |
| 五类口径 | 组标签顺序与期望一致、全部组内 dia 降序、无未匹配口径 ✅ |
| 口径筛选/换枪 | 5.45 → 15 把一致；M4A1 24 弹匣 / AK-101 3 弹匣，弹药列表随后更新 ✅ |
| 命中率默认关 | 复选框未勾选、输入框 display:none 不可见 ✅ |
| 0% | 命中 0/未命中 30，目标存活、护甲 65/65 未扣、弹药耗尽 ✅ |
| 100% | 与关闭同样 29 发击杀（逐发完全一致由引擎测试锁定）✅ |
| 50% × 同种子两次 | 13 命中/17 未命中，两次结果逐字一致 ✅ |
| 命中率 + 随机命中 | 部位出现头/胸/胃，未命中仍存在，两模式互斥且组合正确 ✅ |
| 环境 | 构建 R17S4、0 控制台错误、0 外部请求、无横向溢出 ✅ |

截图：`r17s4-01..08`。

---

## 8. R17S5（空行可拖，2026-10-23 追加）

### 8.1 测试

| 命令 | 结果 |
|---|---|
| `python -m pytest -q`（修改前基线） | 833 passed, 1 skipped |
| `python -m pytest tests/test_r17s5_empty_drag.py -q` | **11 passed**（0.43s） |
| `python -m pytest -q`（修改后全量） | **844 passed, 1 skipped**（47.32s，+11 新增，无删除/跳过/弱化） |
| `node --check app.js / combat_sim.js` | exit 0 / exit 0 |

新增测试：
- `tests/js/preset_drag_model_test.js`：9 组确定性场景，**运行时从 app.js 抽取真实 `amSimPresetDrop`**
  （不是复制一份逻辑），断言「空行跨区插入 / 区内排序 / 不覆盖目标 / 循环满 5 种时空行仍可入 /
  带弹药行被拒 / 连续拖动 uid 稳定 / 行数上限」。
- `tests/test_r17s5_empty_drag.py`：11 项，含源码级断言「`这一行还没有弹药` 已不存在」
  「`if (!src.ammoId) { return { moved: false` 拦截已删除」「`row.draggable = true` 无条件」
  「构建标记 R17S5 / index.html ?v=r17s5」。

### 8.2 真实浏览器验收（Chrome CDP 1500×1700，全部通过）

拖拽实现方式（如实记录）：真实鼠标 `mousePressed` → 连续 `mouseMoved` 触发原生 `dragstart`
（页面 `dragstart` 监听执行，`dataTransfer` 携带行 uid），落点用浏览器级拖拽事件
（`Input.setInterceptDrags` + `Input.dragIntercepted` → `dragEnter`/`dragOver`/`drop`），
页面收到的是与真人拖拽相同的 `dragover` / `drop` 事件。未调用任何内部数组函数。
> 说明：无头 Chrome 对纯合成鼠标只派发 `dragstart`、**不派发 `drop`**（实测计数 start=1 / over=2 / drop=0），
> 因此落点必须由浏览器级拖拽事件补全；这一点已写入设计文档，避免夸大。

| # | 操作 | 结果 |
|---|---|---|
| 1 | 五行全空时点第 1 行方框… | 不涉及；本项验证初始态 5 行全空、全部 `draggable` ✅ |
| 2 | 空首发行 → 循环第 1 行之前 | 首发空、循环 4 行（空行插到首位），指示 `before`，无阻止提示 ✅ |
| 3 | 空末发行 → 循环第 2 行之后 | 循环 `[u1,u2,空,u3,u4]`、末尾空，指示 `after` ✅ |
| 4 | 空循环行 → 首发区 | 首发 `[空]`、循环少一行，角色变「首发」✅ |
| 5 | 循环区内空行调序 | uid 顺序 `1,2,5,4 → 4,1,2,5`，条目数不变 ✅ |
| 6 | 拖动后再点该行方框选弹 | 弹窗 11 项、写入成功、徽标「Warmageddo」、角色仍「循环」✅ |
| 7 | 循环 5 种弹药 + 空行拖入 | 允许（6 行 / 弹药仍 5 种），首发清空 ✅ |
| 8 | 5 种弹药时空行再选第 6 种 | 拒绝并提示「循环区已有 5 种弹药（上限）…原配置未改动」，filled 仍 5 ✅ |
| 9 | 文案 / 环境 | 全程无「这一行还没有弹药」；构建 R17S5；0 控制台错误、0 异常、0 外部请求、无横向溢出 ✅ |

截图：`docs/r17-fixes/screenshots/r17s5-01..08`。

---

## 8. R17S5（空行可拖，2026-10-23 追加）

### 8.1 测试

| 命令 | 结果 |
|---|---|
| `python -m pytest -q`（修改前基线） | 833 passed, 1 skipped |
| `python -m pytest tests/test_r17s5_empty_drag.py -q` | **11 passed**（0.43s） |
| `python -m pytest -q`（修改后全量） | **844 passed, 1 skipped**（47.32s，+11 新增，无删除/跳过/弱化） |
| `node --check app.js / combat_sim.js` | exit 0 / exit 0 |

新增测试：
- `tests/js/preset_drag_model_test.js`：9 组确定性场景，**运行时从 app.js 抽取真实 `amSimPresetDrop`**
  （不是复制一份逻辑），断言「空行跨区插入 / 区内排序 / 不覆盖目标 / 循环满 5 种时空行仍可入 /
  带弹药行被拒 / 连续拖动 uid 稳定 / 行数上限」。
- `tests/test_r17s5_empty_drag.py`：11 项，含源码级断言「`这一行还没有弹药` 已不存在」
  「`if (!src.ammoId) { return { moved: false` 拦截已删除」「`row.draggable = true` 无条件」
  「构建标记 R17S5 / index.html ?v=r17s5」。

### 8.2 真实浏览器验收（Chrome CDP 1500×1700，全部通过）

拖拽实现方式（如实记录）：真实鼠标 `mousePressed` → 连续 `mouseMoved` 触发原生 `dragstart`
（页面 `dragstart` 监听执行，`dataTransfer` 携带行 uid），落点用浏览器级拖拽事件
（`Input.setInterceptDrags` + `Input.dragIntercepted` → `dragEnter`/`dragOver`/`drop`），
页面收到的是与真人拖拽相同的 `dragover` / `drop` 事件。未调用任何内部数组函数。
> 说明：无头 Chrome 对纯合成鼠标只派发 `dragstart`、**不派发 `drop`**（实测计数 start=1 / over=2 / drop=0），
> 因此落点必须由浏览器级拖拽事件补全；这一点已写入设计文档，避免夸大。

| # | 操作 | 结果 |
|---|---|---|
| 1 | 五行全空时点第 1 行方框… | 不涉及；本项验证初始态 5 行全空、全部 `draggable` ✅ |
| 2 | 空首发行 → 循环第 1 行之前 | 首发空、循环 4 行（空行插到首位），指示 `before`，无阻止提示 ✅ |
| 3 | 空末发行 → 循环第 2 行之后 | 循环 `[u1,u2,空,u3,u4]`、末尾空，指示 `after` ✅ |
| 4 | 空循环行 → 首发区 | 首发 `[空]`、循环少一行，角色变「首发」✅ |
| 5 | 循环区内空行调序 | uid 顺序 `1,2,5,4 → 4,1,2,5`，条目数不变 ✅ |
| 6 | 拖动后再点该行方框选弹 | 弹窗 11 项、写入成功、徽标「Warmageddo」、角色仍「循环」✅ |
| 7 | 循环 5 种弹药 + 空行拖入 | 允许（6 行 / 弹药仍 5 种），首发清空 ✅ |
| 8 | 5 种弹药时空行再选第 6 种 | 拒绝并提示「循环区已有 5 种弹药（上限）…原配置未改动」，filled 仍 5 ✅ |
| 9 | 文案 / 环境 | 全程无「这一行还没有弹药」；构建 R17S5；0 控制台错误、0 异常、0 外部请求、无横向溢出 ✅ |

截图：`docs/r17-fixes/screenshots/r17s5-01..08`。
