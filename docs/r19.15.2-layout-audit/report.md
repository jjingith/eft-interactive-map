# R19.15.2 AK 燕尾槽基座固定锚点修复报告

> 版本：`R19.15.2`（`/api/build` rev = `R19.15.2-be907f59`，资源 `?v=r19.15.2`）
> 证据：真实槽位树（gun_builder）+ 布局输出（gwBuildLayout）+ 真实浏览器 DOM（163 把枪逐枪实测，禁缓存）。

## 1. 上一轮错在哪

上一轮把「第三个位置」实现成了**该行第 3 个非空槽位**（按序号算），结果：

- 大多数 AK 的第 2 行只有 3–4 个真实槽位，基座只能是第 1/2 位，于是横向落在 **r2c5**；
- 序号随该枪槽位数量变化，不同枪锚点不一致；
- 报告把「按规则约束下的最优排列」当成完成，属于擅自把固定坐标改成近似位置。

本轮按用户明确指令改为**固定网格坐标**，并删除旧实现（`row2Ordinal` / `placeDovetailMounts` 已不存在）。

## 2. 新的实现（app.js，阶段 2.5，紧随主体链）

```
reserve r2c3  → 燕尾槽基座固定锚点
reserve r1c3  → 基座正上方的真实瞄具槽
reserve r1c4  → 瞄具右侧的额外真实配件槽
```

- 三格先 reserve，后续任何阶段（前照门/战术/MPR45/瞄具/通用找位）都**不得占用**；
- 基座判定不变：`mount` + 父件为机匣或根级 + `allow` 里直接列 `pt=Scope` 物品（真实槽位树，不看名）；
- 瞄具槽 = 基座的真实 `mod_scope` 子槽 → r1c3；其他真实子槽 → r1c4（瞄具右侧）；
- 瞄具再有真实子槽 → 继续向上，超出第 1 行走既有 `topPad` 顶部扩展；
- 同一把枪若有两个燕尾槽类基座：主基座固定 r2c3，第二个顺延 r2c4，并在 `exceptions` 里写明。

## 3. 实测坐标（布局 vs DOM 双证）

| 枪 | 槽位 | 修复前 | 修复后（布局） | DOM |
|---|---|---|---|---|
| AK-74N | `mod_mount_000` | r2c5 | **r2c3** | r2c3（x=392, y=246, 58×58） |
| AUG A3 | `mod_reciever/mod_mount` | r2c5 | **r2c3** | r2c3（x=392, y=247） |
| AUG A3 | 其上瞄具槽 `…/mod_scope` | — | **r1c3** | r1c3（x=392, y=180） |
| AUG A3 | 额外配件槽 `…/mod_tactical` | — | **r1c4** | r1c4（x=453, y=180） |
| AK-74N（装 Kobra 燕尾槽基座） | 基座 / 瞄具 / 战术 | — | r2c3 / r1c3 / r1c4 | 同左 |

截图：`screenshots/before/ak74n-before-1920x919.png`（基座偏在 c5）、`screenshots/after/ak74n-after-canvas-zoom.png`、`screenshots/after/aug-after-canvas-zoom.png`（可直接看到「瞄具槽在上、基座居中、战术槽在右」）。

## 4. 全量结果（28 把兼容枪 / 32 个基座槽位）

| 断言 | 结果 |
|---|---|
| 主基座落在 r2c3（本体正上方一行、第三列） | **28 / 28** |
| 布局输出 == 真实 DOM 坐标 | **32 / 32** |
| 真实瞄具槽在基座正上方同列 | **3 / 3**（其余枪当前未装带瞄具子槽的基座件，真实树无该槽，未伪造） |
| 额外真实配件槽在瞄具右侧 | **2 / 2** |
| 顶部扩展后相对关系不变 | Saiga-12K 红线 rows=7 / topPad=1，基座 r3、瞄具 r2 —— 仍「正上方同列」 |

全量 163 把枪三方对照：`domTreeMismatch 0`、`domCoordMismatch 0`、重复/重叠/越界 0、主体行违规 0、镜座低于本体行 0、燕尾槽三类违规 0、异常 0。

## 5. 已声明的冲突与例外（不静默）

1. **前照门让位 2 例**：`Saiga-12K 12 铅径自动霰弹枪`、`AS"巨浪"MOD.4`。这两把枪的**枪口恰好在 c3**，其前照门原本锚在 r2c3，与燕尾槽硬锚点冲突。按「用户锚点优先」处理：前照门让到同一行最近的 r2c2，并在 `exceptions` 记录；审计工具单列 `frontSightYieldedToDovetail`（2），`frontSightMisaligned` 仍为 **0**。
2. **同一枪第二个燕尾槽类基座 4 例**：VSS、AS VAL、SR-3M、AS VAL MOD.4 —— 主基座 r2c3，第二个 r2c4（真实存在的另一个侧轨接口，未删除、未合并）。
3. **未安装基座件的枪**：`mod_scope` 是基座件的子槽，基座没装时真实树里不存在该槽，画布不显示空瞄具槽（否则就是伪造槽位）。装上任一带瞄具子槽的基座（如 Axion Kobra 燕尾槽适配导轨基座）后，瞄具槽/战术槽立即出现在 r1c3 / r1c4。

## 6. 与既有功能一致

右侧候选列表、手动装卸、枪匠大师、预设全部走 `gun_builder.buildTree` + `sanitize`，本次只改视觉坐标分配，未改物品 ID / allow / 父子关系；`renderGunTree` 直接消费 `L.cells`，因此画布、候选、优化器、预设看到的是同一棵槽位树。

保留：六行九列、顶部扩展、不存在槽位不画格框、真实空槽可点、B.A.D r4c6、弹匣 r4c7、后握把 r4c8、子弹 r5c7、拉机柄 r2c9、MPR45 纵向链、Nightforce 两槽、AXMC 上/下机匣与后托、M10 镜座、马林击锤链与扳机 r4c8、ASH-12 主体行压缩。

## 7. 测试

- 新增 `tests/test_r19_15_2_round.py`（10 项）：固定锚点、瞄具同列正上方、额外槽在右、四份审计 JSON 契约、全量三方对照零违规。
- `tests/test_r19_15_1_round.py` 的燕尾槽断言同步升级为固定锚点（更强）。
- `tools/r1913_audit.js` 增加「燕尾槽让位」独立计数，`frontSightMisaligned` 断言不变。
- 全量 **1067 passed / 1 skipped**。

## 8. 审计物料（`docs/r19.15.2-layout-audit/`）

`ak-dovetail-final.json`、`ak-dovetail-optic-chain.json`、`ak-dovetail-side-slots.json`、`ak-dovetail-regression.json`、`all-gun-layout-audit.json`、`layout-dom-after.json`、`dom-all-after.json`、`screenshots/{before,after}/`。
