# R19.5 测试结果（test-results）

## 自动化

| 套件 | 结果 |
|---|---|
| 全量 pytest | **916 passed, 1 skipped**（+6 条 test_r19_5_round.py） |
| Node 枪械引擎 | 28 passed, 0 failed |

R19.5 新测试：空间画布替换纵向树、分区规则通用性（禁止按枪硬编码）、
参考站视觉元素（空槽标签/角标/重量）、R19.4 交互契约保留、中栏层级顺序、版本标记。

旧断言等价迁移（无删减弱化）：
- R13 切片终点 `renderGunTreeList(` → `gwPartCard(`（函数重构，语义不变）；
- R19.2/3/4 构建标记 19.4 → 19.5；
- F6 差异摘要禁词对新文案同样生效（实现中已规避该措辞）。

## 浏览器验收（tools/r195_accept.py）

| 项 | 1920×1080 | 1264×705 |
|---|---|---|
| 三枪画布分区断言 | 全部通过 | 全部通过（flex 换行，无溢出） |
| 三枪 7 步交互流程 | 通过 | 通过 |
| 连接线 | AK-74 9 / M4A1 6 / MP5 3 | 同 |
| 控制台错误 | 0 | 0 |
| 外部请求 | 0 | 0 |
| 横向溢出 | 无 | 无 |

截图 11 张：`screenshots/`（三枪×两视口整页、右键后、画布特写、对照图 2 张）。

## 过程中发现并修复的问题

1. **SVG className 只读**：`svg.className = x` 在 SVG 元素上抛 TypeError（SVGAnimatedString）——
   改 `setAttribute("class", …)`；首个验收运行因该异常画布完全空白，修复后重跑全绿。
2. **验收脚本跨视口数据覆盖**：两个视口写同一组键导致 1264 结果覆盖 1920——分键存储。
3. **重载后 localStorage 恢复 build 模式**：浏览页隐藏导致选枪点击落空——pick 前显式切口径页
   + gw-current 验证重试 + elementFromPoint 落点校验（该修复属于验收脚本，非产品代码）。

## 未完成（如实）

1. 参考站顶部可折叠节点图视图未做第二视图（空间画布一体化承担，差异已在
   before-after-comparison.md 声明）。
2. 参考站节点图带点阵背景纹理——本地画布为面板底色（视觉细节，非结构差异）。
3. ADS 估算 / 霰弹 MOA 口径 / 上游 404 物品——沿承 R19.3/R19.4 结论不变。

---

# R19.5b 第二次整改测试结果

## 真实截图对照（本轮核心证据）

| 步骤 | 结果 |
|---|---|
| 参考截图视口实测 | y=121–1040 → **1920×919**（1px 行扫描，geometry-measurements.md §1） |
| 实时参考站 | **经代理真实加载成功**（live-site-attempt.png = Caliber 视图；驱动点击后 live-site-workbench.png = 工作台），DOM/像素交叉验证三栏几何 |
| 本地对齐视口截图 | local-after.png（1920×919，AK-74 工作台） |
| 50% 叠加 | overlay-50.png——三栏边界/候选行/中栏分区重合 |
| 差分热力 | diff.png——残余差异集中在主题配色与中文行高 |
| 几何实测 | FORGE ±1px / 中栏宽 ±1px / 右候选右缘精确对齐 / 右留白 60px 精确（§4） |

## 三栏几何改后（对齐视口实测）

FORGE [0,103,487] │ 中栏 [499,103,491] │ 右候选 [1001,103,859]（右缘 1860=参考），
右留白 60px；overflowX=false。中栏新增 LOAD VARIANT 行 + 节点关系画布（点阵+垂直节点链）。

## 回归

- 全量 pytest **916 passed, 1 skipped**（结构改动后重跑）。
- 三枪 7 步交互流程（r195_accept）双视口重跑：安装 iconChanged ✓、右键卸载 ergo 实时变化 ✓、
  恢复默认回官方预设 ✓、切枪无残留 ✓、0 控制台错误 / 0 外部请求 ✓。
- 新增截图：builder-ak74 / builder-m4a1 / builder-mp5（1920×1080）、builder-1264（1264×705）、
  local-before / local-after / overlay-50 / diff / reference-viewport / live-site-×2。

## 残余差异（如实）

1. LOAD VARIANT 行高 122px（参考 26px）：中文标签+摘要换行所致，结构/功能一致。
2. 节点画布高 198px（参考 147px）：节点链展开 6 行 vs 参考折叠 3 节点。
3. 主题配色差异（XP vs 暗色）——任务要求保留 XP，不算布局差异。
4. 磁盘上未找到独立的新版截图附件；基准采用项目内 `ui图标\改枪台界面.png`
   （其特征与任务书描述的"1920×1080 桌面截图"完全一致），已存为
   `reference-db4-gun-20261025.png` 并以实时站加载成功做了交叉验证。


---

# R19.5d 测试结果（test-results.md）

## 自动化

| 套件 | 结果 |
|---|---|
| 全量 pytest | **916 passed, 1 skipped** |
| Node 枪械引擎 | 28 passed, 0 failed |

旧断言迁移（1 处，依据本轮第五节"缩小卡片"要求）：
`test_square_cards_and_right_click` 的卡片尺寸断言 64×64 → **52×52**
（仍断言"正方形"这一契约，未删任何行为断言）。

## 真实浏览器

- `tools/r195b_shots.py`：1920×919 对齐视口 local-after + 几何实测 + overlay-50 + diff；
  1920×1080 builder-ak74/m4a1/mp5；1264×705 builder-1264。
- `tools/r195_accept.py`：三枪 × 7 步交互（见 interaction-test.md），双视口全过。
- 控制台 0 错误、外部请求 0、横向溢出 false。

## 测量结论

三栏 461 : 461 : 922 = **1 : 1.00 : 2.00**（右留白 60 保留）；配件网格 y=441（参考 ≈400）；
画布 137px 与参考精确一致；隐藏属性 66px（10 字段）无状态徽标。

## 未完成（如实）

1. **FORGE 3D Pareto 前沿图未实现**：参考站需点 GENERATE BUILDS 后由 WebGL 绘制三维前沿；
   本地无等价渲染与数据，按"不伪造图形"原则不画假曲线，保留方案文本列表。
2. 参考站工作台内部手势在 headless CDP 下不可触发（见 devtools-investigation/interaction-notes.md），
   参考侧交互证据依赖截图两态对比；本地交互全部有真实浏览器证据。
3. 配件网格 y=441 vs 参考 ≈400：隐藏块承载 10 字段（参考 5 字段）+ 16px 焦点行所致。
