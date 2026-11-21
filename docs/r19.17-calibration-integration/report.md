# R19.17 校准接入主程序 — 审计报告

生成：2026-10-27 · 构建标记 `AM_BUILD = R19.17` · 证据目录 `docs/r19.17-calibration-integration/`

## 一、结论

主程序正式画布已接入 `data/gun-layout-calibration.json` 的人工校准坐标：
打开页面、切换枪械/预设、安装拆卸配件、重新生成布局时，身份匹配成功的槽位一律使用保存的人工坐标；
无记录 / 无法匹配 / 坐标非法时自动回退原有自动布局，画布永不空白。
校准器继续可改可存，新保存的记录主程序同样生效；校准预览与主画布同一条应用规则（同一函数 `gwApplyCalibToLayout`）。

## 二、修改的文件

| 文件 | 作用 |
| --- | --- |
| `app.js` | ① `ensureLayoutCalib()`：页面打开即载入校准数据（优先 `GET /api/layout-calibration`，失败回落静态 `data/gun-layout-calibration.json`，再失败=空记录自动布局）；② `gwCalibKey/gwCalibRecordsFor/gwApplyCalibToLayout`：按 `slotPath\|slotId\|ownerItemId` 匹配并覆盖显示坐标，重算 topPad/行数/AMMO 格；③ `gwBuildLayout` 返回前套用（`g.noCalib` 跳过，node 探针无全局=自动布局原样）；④ 画布加 `data-calib/-applied/-fallback` 验收钩子；⑤ `GWCalib.build` 基线改 `noCalib:true`，新增 `GWCalib.applyCalibration` 供校准器复用；⑥ `AM_BUILD=R19.17` |
| `calibrator.js` | 校准预览（manual 视图）改走 `GWCalib.applyCalibration`（与主程序同一函数、同一条规则）；顶部扩展行数按最终坐标动态重算；`planMove` 本体区改按逻辑行判定；拖动/撤销/重做/保存/导入导出/备份全部保留 |
| `index.html` | 资源版本 `?v=r19.17`（防旧缓存） |
| `tools/serve.py` | rev 标记 → `R19.17-…`（仅版本串，接口未改） |
| `tools/r1925_engine.js` | 新增：node 引擎审计（全量记录对照 + 18 项合成用例） |
| `tools/r1925_accept.py` | 新增：真实浏览器验收 A–F（CDP） |
| `tests/test_r19_17_round.py` | 新增 12 项专项测试 |
| `tests/test_r19_{2,3,4,5,6,7,10,15,15_1,15_2,16}_round.py` | 版本字面量断言改为跟随 AM_BUILD 动态同步；R19.16 的「主引擎禁止读取校准文件」断言按本轮任务书升级为「必须只读已保存校准文件」（更强断言，未删除） |

## 三、正式布局引擎读取校准数据的流程

1. 页面打开 → `ensureLayoutCalib()` 拉取 `GET /api/layout-calibration`（服务端整包校验后的同一份 `data/gun-layout-calibration.json`）；接口不可用 → 直接 fetch 静态 JSON；再失败 → 空记录（`GW_CALIB_STATE={guns:{}}`），自动布局照常。
2. `gwBuildLayout(g)` 生成真实槽位树与自动布局坐标（原有兼容性/父子关系判断全部不动）。
3. 返回前（`g.noCalib` 不为真时）读 `GW_CALIB_STATE.guns[gunId].slots`，对每个格子算身份 key = `slotPath|slotId|ownerItemId`（owner=父槽安装件，根级空串）。
4. key 严格相等才算命中：命中 → 用记录的 `logicalRow`/`col`（权威逻辑行）覆盖；`role` 非空同步覆盖显示角色。未命中/非法坐标/目标落枪身本体区（逻辑 r3c6–c8）/两记录争一格 → 该条回退自动位，计数进 fallback/unmatched。
5. 已校准格优先于自动格：冲突的自动格挪到最近空格（不丢槽位、不重叠）。
6. 以最终逻辑行重算 `topPad`/行数/显示行（`displayRow=logicalRow+topPad`），`emptyAnchors`/`body.row`/`roles.topOptic` 同步；AMMO 合成格被真实槽位占用时躲到最近空格（如 Milkor 的 camora 占 r5c7 → AMMO 躲到 r5c6）。
7. 渲染层（`renderGunTree`）只消费最终 `L.cells` 坐标，切换枪械/预设/装拆件均重新走 2–6，校准持续生效。

## 四、校准记录统计（当前 JSON）

- 有效校准枪械：**152 把**；有效校准记录：**397 条**（全部 `source=manual`，身份键均符合 `slotPath|slotId|ownerItemId`）。
- 默认装配下全量对照：**成功应用 397 条，回退 0 条**（`engine-apply-audit.json`：applied=397 / unmatched=0 / fallback=0 / exactCoords=397）。
- 动态场景下无法匹配的记录（换父件后 ownerItemId 变化、条件子槽未安装等）按设计回退自动位，合成用例 `ownerIsolation`/`ownerChangeNoCross`/`unmatchedFallback` 验证不串位。

## 五、实际验证

| 测试 | 内容 | 结果 |
| --- | --- | --- |
| A 已校准枪械 | AK-74N(3 条)/Milkor M32A1(8)/FN SCAR-L(14)/Sako TRG M10(2) 逐条对照主画布 DOM | 全部命中保存坐标（match=records，applied 计数=记录数） |
| B 未校准枪械 | 马林 MXLR（0 条记录） | `data-calib=0`，12 张槽位卡正常渲染，自动布局 |
| C 配件变化 | AK-74N 燕尾槽装上导轨基座 → 换装 Kobra 瞄具 → 卸下 | 装/换/卸全程 `mod_mount_000` 保持 r2c7（校准位）；新条件子槽（mod_scope/mod_tactical）走自动布局；卸下后子槽清零、卡数复原 13 |
| D 持久化 | 校准器拖 `mod_stock`→r6c2 保存 → 刷新主程序 → 清除还原 | 刷新后主画布实测 r6c2（数据来自 JSON 文件）；清除后记录消失 |
| E 数据安全 | 测试前后 152 枪 / 397 条记录逐条坐标对照 | 内容完全一致；测试写入的临时记录已清除，文件还原为原始字节（sha256=6f75a901…8914 与测试前一致，含 `.bak.json`） |
| F 一致性 | 校准器 manual 预览 vs 主画布（AK-74N 13 格） | 13/13 坐标完全一致 |

回退机制验证：B（无记录）+ 合成用例（伪造 key / 非法坐标 / 本体区 / 争格 / 换 owner）全部回退自动布局，无空白画布。

## 六、测试

- **全量 pytest：1117 passed / 1 skipped / 0 failed**（本轮前 1105 passed；新增 12 项专项全部通过，1 skip 为无 node 环境豁免）。
- 引擎审计 18 项检查全过（`engine-apply-audit.json.checks`）。
- 浏览器验收 A–F 无失败项（`browser-accept.json.failures=[]`），console 无报错。

## 七、以后如何更新正式布局

1. 打开 `http://127.0.0.1:8787/index.html?layoutCalibrator=1` 调整坐标并**保存**（写入 `data/gun-layout-calibration.json`）。
2. 回到主程序**刷新页面**（F5）即可生效——正式布局每次生成都读已保存文件，无需其它操作。
3. 校准只改显示坐标，不影响兼容性、父子关系与配装数据；删除某枪记录（校准器「清除人工校准」）即恢复该枪自动布局。

## 八、产物清单

- `engine-apply-audit.json` — 全量 397 条应用对照 + 18 项合成检查
- `browser-accept.json` — 浏览器 A–F 证据（含逐枪坐标对照、装拆件前后快照）
- `screenshots/` — A/B/C/D/F 各阶段截图
- `backup/` — 修改前 app.js / calibrator.js / index.html / 校准文件原始副本（sha256 记录）
