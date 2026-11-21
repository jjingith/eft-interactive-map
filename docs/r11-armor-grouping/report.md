# 第十一轮交付报告：防护区域图标补全与基础防弹等级分组排序

日期：2026-10-21
范围：仅配装工作台右侧装备列表（防弹衣 / 防弹弹挂 / 头盔），局部修复，非重新设计。
产物目录：`docs/r11-armor-grouping/`（本报告、`protection-zone-audit.json`、`verify-results.json`、6 张验收截图）

---

## 一、结论速览

| 项 | 结果 |
| --- | --- |
| 问题 A（防护区域图标） | 三类共 194 件装备逐一审计：Armor 49/49、Rig 59/59（另 46 件无区域数据属正常）、Helmet 39/39（另 1 件「破碎面具」无 z 字段属正常）。映射表扩到 22 条，17 张图标已入库，5 张新组合图待用户补源图（清单见第四节），补图前运行期 onerror 自动降级、无裂图 |
| 问题 B（基础防弹等级列 + 分组排序） | `baseArmorClassOf()` 本体口径函数 + `基础防弹等级` 列（名称之后、移动/转身/人机之前）+ `baseClGroupRank` 分组主序；浏览器实测三类别组内排序、组序恒定、未知组排最后 |
| 测试 | 基线实测 681 passed / 1 skipped / 0 failed（与 r10 报告一致）；最终全量 **691 passed / 1 skipped / 0 failed** |
| 回归 | 眼镜 7 列、背包 11 列与 r10 完全一致；地图相关功能零改动；无运行期网络请求 |

---

## 二、基线核对（先于一切修改）

- 第十轮报告基线：681 passed / 1 skipped。本轮开始时重跑全量套件实测确认 **681 passed / 1 skipped / 0 failed**，与报告一致。
- 先检查后修改，检查项全部完成：
  - `app.js`：`zoneIcoCol`、`zoneCol`（插板弹窗旧调用方）、`ZONE_WORDS`、`ZONE_ICON_BY_WORDS`、`createTable` 的 `sorted()` 与行渲染；
  - `data/items.json`：三类装备的 `z` / `cl` / `slot` / `cat` / `pt` 字段；
  - 第十轮 `tests/test_r10_armor_table.py` 与 `verify-results.json`、`measure-6b43.json`。
- 修改过程中全量套件曾出现 3 failed，全部是 r11 结构性改动与旧静态断言的**预期冲突**（详见第七节），按语义等价原则更新断言，未删除、未放宽任何测试。

---

## 三、问题 A：根因与修复

### 3.1 根因（两个，均已在代码层修复）

1. **映射表缺组合**：`ZONE_ICON_BY_WORDS` 只有 17 条，无法覆盖全部真实数据组合。例如 9 件防弹衣 + 13 件弹挂的组合为「胸部|胃部|侧面」，5 件头盔组合含「头顶|后脑|面部|眼部|耳部」等，映射表没有对应键。
2. **头盔走旧渲染路径**：头盔列 `helmetZoneCol` 沿用 `zoneText` 纯文字渲染（`zoneCol` 同款），即使图标存在也不显示；armor/rig 已走 `zoneIcoCol` 图标路径，两类行为不一致。

### 3.2 修复方式（统一机制，最小改动）

- 新增统一渲染函数 [renderZoneIconCell(cell, row, allowText)](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/app.js#L4364-L4412)：
  - 图标命中 → `img`（armor/rig 用 `lw-zone-ico`，头盔用 `tbl-zone-ico`）；
  - 无图标 → `allowText=false`（armor/rig）显 `—` 占位、`true`（头盔）文字降级；
  - 文件未入库（待补图）→ `img.onerror` 回退，不显示裂图；
  - 悬停一律给完整中文部位名，且图上没有的部位（如 SpineTop/SpineDown/Plate_*_back 投影不出词的）以「＋后背」小字与悬停说明补充，避免误读。
- [zoneIcoCol](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/app.js#L7369-L7373) 与头盔 `helmetZoneCol` 均委托该函数，旧调用方 [renderZoneCell](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/app.js#L4410-L4412) 保持薄封装兼容（插板弹窗等不受影响）。
- `ZONE_ICON_BY_WORDS` 扩至 **22 条**（[L4296-L4319](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/app.js#L4296-L4319)）；新增组合同步写入 [tools/iconize.py ZONE_JOBS](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/tools/iconize.py#L272-L314)（原样复制 + ASCII 改名，不抠底）。
- 规范化保持 `ZONE_WORD_ORDER` 12 词固定序；**未合并任何区域**——颈部≠耳部≠眼部≠下颚，Pelvis/PelvisBack→腹股沟、Left/RightSideChestDown→侧面 等别名归并仅发生在同义部位之间。
- 审计函数 [zoneIconAudit](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/app.js#L4342-L4358) 供测试与页面核对。

### 3.3 覆盖率审计（数据级，全部 194 件逐一检查）

产物：[protection-zone-audit.json](protection-zone-audit.json)（`mapping_entries=22`、`icons_on_disk` 17 张、`pending_user_icons` 5 张）。

| 类别 | 总数 | 有区域数据且映射成功 | 有区域数据但缺映射 | 无区域数据（无需图标，不伪造） |
| --- | --- | --- | --- | --- |
| Armor（slot=armor） | 49 | 49 | 0 | 0 |
| Chest Rig（slot=rig） | 105 | 59 | 0 | 46 |
| Headwear（cat=helmet） | 40 | 39 | 0 | 1（破碎面具） |

- 三类 **unmapped_combo = 0**：所有有效防护区域均已正确映射；`miss_items` 均为空。
- 46 件弹挂与 1 件头盔无 `z` 数据，属任务书第四种情况，未伪造图标。
- 大小写变体：`case_variants` 为空，未发现别名问题。
- 浏览器交叉核对：armor 防护区域列 40 img 全部加载 + 9 个「—」（=9 件待补组合，精确一致）；头盔 34 img + 5 文字降级 + 1 无数据（=40，精确一致）。

---

## 四、待补图标清单（5 张，用户自备源图后一键入库）

补图后执行 `python tools/iconize.py` 即按 ASCII 名复制入库（源图缺失时脚本跳过并提示，不阻塞其他任务）。源图目录：`D:\personal\trae\02-塔科夫\ui图标\` 下对应子目录。

| # | 目标文件名（assets/icons/zones/） | 高亮部位 | 源目录 / 源文件名 | 影响装备 |
| --- | --- | --- | --- | --- |
| 1 | `torso-chest-stomach-side.png` | 胸部＋胃部＋左右侧面（无颈部、无腹股沟） | `防弹衣防弹胸挂防护部位图\防护部位-胸部胃部侧面.png` | 22 件（防弹衣 9：PACA、BNTI Module-3M、MF-UNTAR 等；弹挂 13：ANA Tactical M1/M2 插板胸挂等） |
| 2 | `torso-neck-chest-stomach-groin.png` | 颈部＋胸部＋胃部＋腹股沟（无侧面） | `防弹衣防弹胸挂防护部位图\防护部位-颈部胸部胃部腹股沟.png` | 2 件（6B5-15 / 6B5-16 Zh-86 Uley 防弹胸挂） |
| 3 | `head-top-back-face-jaw-eyes-ears-neck.png` | 头顶＋后脑＋面部＋下颚＋眼部＋耳部＋颈部 | `头盔防护部位图\防弹部位-头顶后脑面部下颚眼部耳部颈部.png` | 2 件（杰克南瓜灯战术南瓜头盔、SHPM 消防盔） |
| 4 | `head-top-back-face-eyes-ears.png` | 头顶＋后脑＋面部＋眼部＋耳部（无下颚、无颈部） | `头盔防护部位图\防弹部位-头顶后脑面部眼部耳部.png` | 1 件（PSH-97 "Jeta" 头盔） |
| 5 | `head-top-face-jaw-eyes-ears.png` | 头顶＋面部＋下颚＋眼部＋耳部（无后脑、无颈部） | `头盔防护部位图\防弹部位-头顶面部下颚眼部耳部.png` | 2 件（Tagilla "UBEY" / "Gorilla" 电焊面罩） |

- 共 **29 件装备**的图标等待补图；补图前这些行 armor/rig 显示「—」、头盔显示文字（设计内降级，悬停可见完整部位说明）。
- 绘制参考：每张图与同目录已有图同风格（线稿 + 高亮），文件名即高亮部位清单；`ZONE_JOBS` 中的 `words` 数组即校验口径，映射一致性测试会交叉核对。

---

## 五、问题 B：基础防弹等级列与分组排序

### 5.1 本体等级函数（正确字段，不复用 maxArmorClassOf）

[baseArmorClassOf(rec)](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/app.js#L4691-L4693)：只读装备自身 `cl`，为正有限数才返回，否则 `null`（表格显「—」，不伪造 0 级）。**不看插板、不看其他装备、不看左侧角标**；`maxArmorClassOf()`（含插板口径）未被用作分组依据。防弹衣 / 弹挂 / 头盔三类共用同一 `cl` 字段，数据级测试验证了三类字段结构一致（ helmets 40 件、armor 49 件、rig 105 件全量断言）。

### 5.2 列位置与显示

- 列定义 [baseClCol](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/app.js#L7214-L7215)：`基础防弹等级`，悬停注明「仅装备本体防弹等级，不计入已安装插板」；缺级显 `—`。
- 防弹衣 / 弹挂：20 列 → **21 列**（[L7408-L7413](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/app.js#L7408-L7413)），顺序 `ico, n, baseCl, pen, 前插板, 后插板, 左插板, 右插板, 内衬合计, 内衬×8, 防护区域, 重量, 获取方式`，未挤掉任何字段。
- 头盔：原「护甲等级」列由「基础防弹等级」替代（同一 `cl` 本体口径，用户已裁定豁免"不得替换"条款），列数保持，位置移至名称之后（[L7434](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/app.js#L7434)）。

### 5.3 分组排序（本轮核心）

- [baseClGroupRank(node, row)](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/app.js#L7456-L7462)：仅 armor/rig/helmet 根槽位生效；升序返回 `-baseCl` → 6→5→4…1；无等级返回 `1e9` → **未知组固定排最后**；其他类别 / 插板弹窗 / 附件槽返回 0，等价于不分组，行为与之前完全一致。
- 接线：[buildGearTable 的 groupOf](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/app.js#L7486-L7486) 每次渲染按当前节点动态判定，`createTable.sorted()` 把 `groupOf` 作为**主序比较器（不乘排序方向）**——用户点任何属性列只在同组内部排序，组序恒 6→…→1→未知，不受升降序影响。

### 5.4 浏览器实测（详见 verify-results.json）

| 类别 | 列数 | 行数 | 组序（默认） | 组内排序验证 |
| --- | --- | --- | --- | --- |
| 护甲 | 21 | 49 | 6→5→4→3→2（组大小 9/17/9/8/6） | 点重量列：组内单调降序，组序不变，表头重量▼；再点：组内升序，组序仍 6→2 |
| 胸挂 | 21 | 105 | 6→5→4→3→2→1→「—」 | 46 件无等级全部位于最后 |
| 头盔 | 13 | 40 | 5→4→3→2→1→「—」 | 同机制 |

---

## 六、修改清单

| 文件 | 修改 |
| --- | --- |
| [app.js](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/app.js) | ① `ZONE_ICON_BY_WORDS` 17→22 条（L4296）；② `zoneIconAudit`（L4342）；③ 统一渲染 `renderZoneIconCell`（L4364）；④ `renderZoneCell` 改薄封装（L4410）；⑤ `baseArmorClassOf`（L4691）；⑥ `zoneIcoCol` 委托统一渲染（L7369）；⑦ `baseClCol` 新列（L7214）；⑧ armor/rig 21 列装配（L7408）；⑨ 头盔列集 cl→baseCl（L7434）；⑩ `baseClGroupRank`（L7456）；⑪ `groupOf` 接线（L7486）；⑫ 行数据补 `baseCl` / `zoneIcon` / `zoneUnmapped` 字段（行渲染处，配合上述改动） |
| [tools/iconize.py](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/tools/iconize.py) | `ZONE_JOBS` 追加 5 条复制任务（L286-L300），源图缺失时跳过并提示 |
| [tests/test_loadout_workbench.py](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/tests/test_loadout_workbench.py) | 图标计数 17→22 并与审计 JSON pending 清单交叉核对（缺图必须登记）；harness 提取清单补 `renderZoneIconCell` / `baseArmorClassOf`；T18 改用仍未映射组合断言 null；T22 列序断言更新为 21 列 / 头盔 13 列 |
| [tests/test_r10_armor_table.py](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/tests/test_r10_armor_table.py) | zone 列静态断言改为统一渲染机制断言（语义保持：armor/rig 不显文字、缺失→「—」） |
| 新增数据级测试 | 三类装备防护区域映射覆盖率审计（有区域必命中，无区域登记），审计产物落 `protection-zone-audit.json` |

未改动：地图渲染、地图图标、路线、定位、搜索、任务、设置、枪械预设、人物预设、护甲板安装、右键卸除等既有功能；无新增运行期第三方依赖；前端保持 ES5。

---

## 七、测试

- **基线（修改前）**：681 passed / 1 skipped / 0 failed。
- **修改中一次全量**：688 passed / 1 skipped / **3 failed**——均为旧静态断言与 r11 结构的预期冲突：
  1. 图标映射计数 17→22 + 新增 5 条映射指向尚未入库的文件（撞上「文件必须存在」检查）→ 改为与审计 JSON 的 pending 清单精确交叉核对（缺图必须登记，不得静默缺图）；
  2. node harness 报 `baseArmorClassOf is not defined` / `renderZoneIconCell is not defined` → harness 提取清单补这两个函数；
  3. `zoneIcoCol` 块内 className 断言与统一渲染实现不匹配 → 改断言统一渲染函数与委托接线，语义不变。
- **最终全量**：**691 passed / 1 skipped / 0 failed**（681 基线 + r11 新增 10 项）。

---

## 八、真实浏览器验收证据

环境：serve.py @ 127.0.0.1:8787，Chrome（MCP DevTools + CDP 双通道）；截图前 `Page.reload(ignoreCache)` 强制禁缓存并做 21 列断言防护（防旧标签页跑旧 JS 的假阳性）。

| 截图 | 证明内容 |
| --- | --- |
| [verify-armor-21col-grouped.png](verify-armor-21col-grouped.png) | 护甲 21 列表头逐字确认、baseCl 在名称后、49 行按 6→2 分组 |
| [verify-armor-zone-col-scrolled.png](verify-armor-zone-col-scrolled.png) | 表格横向滚到最右，防护区域列 40 图标 + 9「—」真实渲染 |
| [verify-rig-grouped-top.png](verify-rig-grouped-top.png) | 胸挂 21 列、分组顶部自 6 级开始 |
| [verify-rig-unknown-group-last.png](verify-rig-unknown-group-last.png) | 胸挂 46 件无等级「—」全部在列表最后 |
| [verify-helmet-zone-icons.png](verify-helmet-zone-icons.png) | 头盔 13 列、34 图标 + 5 文字降级 + 1 无数据 |
| [verify-glasses-regression.png](verify-glasses-regression.png) | 眼镜 7 列回归不变 |

- 控制台错误核查：仅 1 类 `404 × 8 次`，经网络日志提取，URL 全部命中 5 张待补图标（`torso-chest-stomach-side.png`×4、其余 4 张×1），无其他缺失资源，属设计内降级。
- 6B43 定向核对：baseCl=6、`torso-neck-shoulder-chest-stomach-side-groin.png` 已加载、悬停完整部位说明。
- baseCl 悬停提示实测：「仅装备本体防弹等级，不计入已安装插板」。

---

## 九、与 r10 报告核对说明

- r10 的 20 列专属布局在本轮变为 21 列（新增列插入而非替换/合并，头盔列替换系用户裁定豁免）；
- r10 交付的列宽拖动与持久化、冲突整行标红、悬停浮窗、获取方式列、内衬/插板分列等全部保留并在本轮回归中复验；
- r10 报告基线 681 passed / 1 skipped 与本轮实测一致，未发现报告虚报。

## 十、剩余事项与承诺

1. 5 张待补组合图（第四节清单）等待用户提供源图；入库后执行 `python tools/iconize.py` 即 exact 命中，无需再改代码。
2. 未推送远程仓库、未覆盖正式发布版本；本轮修改仅涉及 app.js、iconize.py、两个测试文件与 docs/r11-armor-grouping/ 产物。
3. 过程临时脚本（D:\Temp\r11_*.py/js）均在项目目录之外，不进入打包产物。
