# R19.3 六项问题根因与修改记录

> 版本：R19.2 → **R19.3**（构建标记与资源 `?v=r19.3` 同步更新）。
> 验收：`tools/r193_accept.py`（真实浏览器，1920×1080 + 1264×705），`_accept.json`，
> 0 控制台错误、0 外部请求。全量 pytest 894 passed（含 7 条 R19.3 新测试）。

## P1 浏览页显示机匣而非整枪

- **根因（数据链证据）**：浏览卡绑定的是枪械本体 id（如 AK-74 `5bf3e03b0db834001d2c4a9c`），
  图标取 `assets/icons-items/{gunId}.webp`。EFT 里枪托/握把/枪管是**独立 mod 配件**，
  本体展示图只渲染机匣+枪管+弹匣（AK-74 本体图 253×64，右端截断在机匣尾——R18.2 已实测）。
  完整整枪渲染只存在于**预设**上：`assets.tarkov.dev/{presetId}-base-image.webp`
  （AK-74 默认预设 `5c0c1ce886f77401c119d014` → 316×127 含木托）。不是数据映射错误、
  也不是默认装配没加载——是项目此前根本没有完整枪械图像资源。
- **修改**：新建 `tools/build_gun_images.py`（构建期）：163 把枪各自取 `gun-stats.json` 记录的
  defaultPreset + 该枪全部 373 条官方预设，下载透明底整枪渲染 → Alpha 包围盒裁剪 →
  等比缩放（高 112px / 宽≤400px）→ `assets/guns-full/{gunId}.png`（161/163）与
  `assets/presets-full/{presetId}.png`（368/373）。manifest 记录 gun→preset 映射、源 URL、
  原始尺寸。**没有把配件图标叠放合成**。浏览卡接线 `setGunFullImg`（缺失回退白底图标）。
- **结果**：163 张卡片 161 张指向整枪渲染；12 枪抽查（突击/冲锋/狙击/霰弹/手枪等）
  12/12 加载成功；对照图 `weapon-image-before-after.png`。
- **缺失 2 把（如实）**：HK 416A5 RAL8000（`6a2a77cae232fdab260b484a`）、
  FN P90 灾厄（`6a799f200b38edb61b0aca7b`）——上游 base-image 404（与 R18.2 起已知的
  4 件 404 是同一批物品），走回退链显示白底物品图标。

## P2 悬停黄、选中黑

- **根因（计算样式实测）**：三层叠加。
  1. 选中态 `.gw-card[aria-current="true"]` 用 `var(--lw-select, #2c3646)`，XP 主题没覆盖
     该变量 → 深色回退 rgb(44,54,70)，配黑色文字 → "黑底黑字"；
  2. 更深一层：卡片是 `<button>`，被 R18 的 XP 按钮皮肤
     `html .gun-workbench button:not(.gw-hit)`（含 hover 渐变，特异性 (0,2,2)~(0,4,2)）接管，
     悬停时把背景换成浅色渐变——这就是"悬停发黄"的来源；
  3. 按下的芯片（aria-pressed）同样落深色回退（对比度实测 1.72）。
- **修改**：结构性修复——三段按钮皮肤规则追加 `:not(.gw-card)`（卡片不是 XP 按钮）；
  新增主题规则：悬停 `#fff3c4` / 选中 `#ffe9a8`（`:hover` 联选保证移走鼠标不变）/
  `:focus-visible`、`:focus`、`:active` 橙色描边或同黄底；文字保持深色。
- **实测**：悬停 rgb(255,243,196)、选中 rgb(255,233,168) + 黑字、切视图返回仍黄、
  换选另一把枪新卡黄旧卡恢复、0 控制台错误。四阶段截图 + `selected-hover-states.png`。

## P3 工作台文字白字落白底

- **根因**：对比度审计脚本（TreeWalker 遍历全部文本节点 + WCAG 对比度计算）实测 6 处：
  `.gw-current` #fff on #fff = 1.00、`.gw-visual-name` #fff = 1.09、`.gw-chip b` #e7edf5 = 1.18、
  `.lw-focus-title` #fff = 1.22、增减差值绿 #7dbb5e ≈ 2.1、pressed 芯片 1.72。
- **修改**：全部在 `theme-windows-xp.css` 用 `html .gun-workbench …` 作用域修复
  （无全局选择器）：名称/当前枪/焦点标题/数值 → #000，Final Cost → #1e5c1e，
  语义色加深（up #2e6b2e / down #a03327，保留绿好红差方向）。
- **实测**：复跑审计 = **0 处低对比**（阈值 2.6:1）；AK-74 / M4A1 / Glock 17 三枪截图文字全部可读。

## P4 工作台整枪主图 + 反映装配变化

- **方案调查**：EFTForge（AGPL-3.0）源码里**没有**任意装配的整枪合成（它也只展示配件卡与
  属性面板）；tarkov.dev 只渲染**预设**整枪。任意组合的光栅合成没有可靠几何来源，
  任务书也明确禁止"把配件图标随意叠成假整枪"。
- **实现（诚实两态方案）**：中央主图 = 真实整枪渲染，
  ① 当前装配**恰好等于某条官方预设** → 显示那条预设的整枪渲染，标签"官方预设：X"；
  ② 否则 → 默认预设整枪渲染 + 黄色标签"基准预设（已改动 N 件）" +
     **差异条**：与默认装配逐槽位对比，每个改动件一块瓦片（图标 + 槽位名 + 新旧件名），
     点击跳转该槽位。装配引擎零改动（递归槽位/allow/清理/成本/预设全部复用）。
  回退链：预设整枪图 → 白底物品图标 → 隐藏；任一环节失败不影响装配操作。
- **实测**（accept P4，MP5/AK-74 流程）：进入=官方预设渲染 → 换件=标签变"已改动 1 件"
  +差异条出现 → 恢复默认=回到官方预设渲染 → 换枪无残留（M4A1 独立渲染）。
  **残余限制（如实）**：任意改装组合无法生成照片级整枪图（无几何来源），改动通过
  标签+差异条体现，而非枪身某区域的像素替换。

## P5 瞄准类属性公式（本轮最大成果）

- **来源**：EFTForge `backend/stats.py`（自述 "Every formula here reproduces the game exactly"）
  + `frontend/modules/calculations.js`（两边由 11 组黄金向量锁定）。
  检索记录：仓库树 475 文件 → 定位 stats.py / calculations.js / stats-panel.js /
  build_calc.py / 黄金 JSON；**已读实现代码**而非 README。
- **实现（独立重写进 gun_builder.js，未复制其代码）**：
  - `TrueErgoDelta = min(max(eff,0),100) − (W≤3 ? 0 : 100×(1−3/W))`，`OverSwing = TED<0`
  - `AimSway = clamp((W×(1−eff/100) − 3) / (7−3), 0, 1)×100%`（3kg 起摆、7kg 满幅）
  - `ArmStamina = 80 / (√(max(W×(1−√eff/25),0)) × 1.1 × (1−力量级×0.004))` 秒
  - **MOA = (100/2.9089) × COI × (1−Σ精度修正/100) × 弹药系数**，枪管 COI 覆盖枪械基础值
    ——这同时解决了 R19 以来"精度无法换算 MOA"的遗留问题
  - 满弹匣弹药重量计入重量后再算 TED/过摆/耐力（EFTForge 同规则）
  - 模拟参数显式化：力量等级（默认 10，EFTForge 默认）、装备人机修正（默认 0），
    FORGE 面板可改，改动即时刷新
- **验证**（`tools/_verify_forge.py`，373 条官方预设）：
  - 黄金向量 11/11 复现（TED/OverSwing/AimSway/ArmStamina，含负值与边界 case）
  - 人机：n=373，平均残差 +0.002，中位 0.000，p95 0.1
  - 垂直/水平后坐：中位 0.3，p95 0.5
  - **MOA：n=373，中位 0.01**；非霰弹 342 样本中位 0.01 / p95 3.43；霰弹 31 样本中位
    偏差 13.8（≈2× 系统性口径差异）→ 霰弹枪的 MOA 在引擎里单独降级为估算并注明
- **ADS**：EFTForge 全库检索无 aiming time；db4 的 ADS 标注 (beta) 且公式未公开。
  保留社区拟合式 `max(0.2, 2.35−0.028×ergo)`，conf=estimated，悬停写明检索结论。
  （检索路径：EFTForge stats.py/calculations.js/stats-panel.js 逐文件 grep、SPT 服务器资料、
  tarkov.dev；缺失变量=官方客户端 AimSpeed 曲线系数。）
- **实测**（accept P5）：M4A1 TED 72.0 / OS 否 / Sway 0% / ArmStamina 55.1s；
  力量 10→30 后 ArmStamina 55.1→**60.1s**（模拟参数生效）；Glock TED 91 / MOA 11.69。

## P6 工作台布局对照 `改枪台界面.png`

- **实测（1920，浏览器 getBoundingClientRect）**：
  工具条 39px + 视图条 33px；FORGE **x=0 w=461（24%）** / 中栏 **x=461 w=653（34%）** /
  候选 **x=1114 w=806（42%）**（参考站 ≈500/460/900 = 26%/24%/47%）——本轮把三栏从
  246/830/614 调整到参考比例；中栏内部：主图 485,605×172、属性条 629×117、装配卡 629×747、
  弹药卡 49、底部成本+时间线 150；候选面板搜索框 805×31，列表占满右栏高度。
  1264×705 下无横向溢出（含工作台）。
- **修改**：`gw-buildpage` 网格列改为 `minmax(216px,24%) / minmax(400px,1fr) / minmax(300px,42%)`；
  FORGE 面板层级按参考图重排（标题/副标题/模拟参数/优化目标/生成按钮/结果）。
- **残余差异（如实）**：参考站 LOAD VARIANT 在中栏顶部（本地内置预设下拉在顶栏）；
  参考站有 Changes 时间线页签与 FORGE 的 MAGS/SCOPE/BLOCKED/FORCED 约束控件（本地无对应
  数据/引擎能力，不造假控件）；配色为 XP 主题（按任务要求保留）。
  逐项见 `layout-comparison.md`。

## 修改文件清单

| 文件 | 作用 |
|---|---|
| `tools/build_gun_images.py`（新） | 161+368 张完整整枪渲染生成器 + manifest |
| `assets/guns-full/` `assets/presets-full/`（新） | 整枪图产物（4.7MB + 11MB） |
| `gun_builder.js` | EFTForge 公式（TED/OverSwing/AimSway/ArmStamina/MOA）+ 强度/装备人机输入 |
| `tools/build_gun_stats.py` | （上轮已含 ra；本轮无改动） |
| `app.js` | setGunFullImg / matchingOfficialPreset / 主图+差异条 / 模拟参数 UI / R19.3 标记 |
| `index.html` | ?v=r19.3 |
| `style.css` | 整枪卡/主图/差异条/模拟参数/三栏比例 |
| `theme-windows-xp.css` | 按钮皮肤 :not(.gw-card) + 黄色高亮 + 对比度修复 |
| `tools/r193_accept.py`、`tools/_contrast_audit.py`、`tools/_verify_forge.py` | 验收工具 |
