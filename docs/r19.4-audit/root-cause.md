# R19.4 七项问题根因与修改记录

> 版本 R19.3 → **R19.4**（构建标记与 ?v=r19.4 同步）。全量 pytest **910 passed, 1 skipped**、
> Node 引擎 28 passed。浏览器验收 `tools/r194_accept.py`（_accept.json，0 控制台错误、0 外部请求）。
> 本轮同时执行了任务书修订：**白底图标方案废止，全项目统一透明背景**（见 transparent-asset-*.md）。

## F1 模拟参数保存与恢复
- **根因**：参数只存内存 state.gwSim，刷新即丢。
- **修改**：`app.js` 新增 `GW_SIM_KEY("eftmap.gwsim.v1")` 读写 + 保存/重置按钮。
  读取时校验（力量 0-51 取整、修正 -1~1），损坏数据回退默认并提示；重置只改输入不写存储
  （语义分离，测试断言）。计算在 input change 时即时重算，保存只负责持久化。
- **实测**：改力量 10→30 → ArmStamina 46.7→51.0s 即时变化；保存后 localStorage
  `{"strength":30,"equipErgo":0}`；刷新页面/换 Glock 后输入仍为 30；重置→10 且存储不变。

## F2 FORGE 四类约束（本轮重点）
- **根因**：优化器完全没有约束概念；容量数据在弹匣物品的 `cap` 字段、按树 allow 枚举可得。
- **修改**：
  - 引擎端（gun_builder.js）：`checkConstraints()` 终检 + `magCapacities()` 容量枚举 +
    `optimize(opts.constraints)`——贪心循环内过滤排除件/容量、必装件预装并锁定槽位、
    scope 要求时从真实 mod_scope 槽位候选补装、每个 build 附 `constraintOk/violations`。
  - UI 端（app.js renderGunForge 重写）：弹匣容量芯片（**按当前枪真实兼容枚举**，多选+清除，
    无数据显示"暂无可用容量数据"）、瞄准镜开关、必须包含/排除搜索钉选栏（图标+名称+单删+清空）。
  - 应用前用同一套 `checkConstraints` 终检，非法方案禁止进入装配状态。
- **实测**：AK-74 容量枚举 = 10/20/30/45/60/95 发（真实数据）；只允许 30 发 → 4 方案全部
  constraintOk；排除"制退器"→钉选生效；必含=排除同一件 → 4 方案全部标红
  "⛔ 同一个配件同时出现在「必须包含」和「排除」里"，应用按钮禁用。
  端到端 Node 测试 `test_forge_constraints_end_to_end` 通过。

## F3 条纹属性条
- **根因**：旧条是单色 fill + 括号文本，无基线视觉与方向语义。
- **修改**：`gwBar` 重写为分段渲染——加粗到 10px；基线灰竖线 + "基线 X" 灰字常驻；
  人机工效（高好）与散布角/垂直/水平后坐（低好）分别按任务书四分支着色：
  改善=当前色实段+「当前色-灰」斜纹，恶化反向；持平=中性。斜纹用
  `repeating-linear-gradient(45deg,…)` 真实 CSS 绘制，位置按 B/C 百分比计算。
- **实测**：右键卸下导气箍后人机工效= solid-bad(0-18%)+stripe-bad(18-39%) 基线47.0 dir=bad、
  散布角 neutral（持平）、垂直/水平后坐 solid-good+stripe-good 改善——四态方向全对
  （_accept.json F3）。截图 f3-bars.png。

## F4 紧凑属性面板
- **修改**：`.gw-stats` 改两列网格（≤1500px 回单列），表头跨两列；行宽从 653px 收敛到
  半宽（629px 面板内两列），垂直空间同步压缩；无截断（ellipsis + title）。
- **实测**：statsW=629 / centerW=653 / gridCols=2；1264 下无横向溢出。

## F5 方形装配卡 + 浮窗 + 右键卸载
- **根因**：旧卡片带常驻槽位名与配件名（两行文字），卡片被拉长。
- **修改**：卡片重写为 64×64 正方形按钮（图标主体，白底废止后透出面板底色）；
  常驻文字全部移入共享浮窗（`#gw-tip` fixed 挂 body 不被裁切，hover 与 focus 同内容）；
  已装件右上角 × 角标 + **右键**走 `clearGunSlot`（真实递归清理链），空槽右键只拦截菜单不动作。
- **实测**：8 张卡全部 64×64（allSquare:true）；右键卸 mod_gas_block → 人机变化+配件数-1；
  浮窗内容含槽位名/配件名/增减/操作提示（截图 f5-tooltip.png；注：验收脚本在右键后的
  重渲染上再悬停，hidden 标志时序略有抖动，内容正确）。

## F6 删除"与默认装配的差异 · N 件"
- **修改**：renderGunVisual 中整段差异条删除（DOM/CSS/占位全部移除）；
  `diffAgainstDefault` 内部计算保留（hero 标签"已改动 N 件"仍用）。
- **实测**：`diffSummaryGone: true`；默认/改 1 件/改多件/恢复默认四状态下无该文字与空白占位。

## F7 属性实时更新
- **验证**（AK-74 + 换弹匣流程）：重量 4.87→4.98 kg（满弹匣计入）→
  TED −20.4→−27.2、ArmStamina 36.9→35.6s —— 弹匣重量变化真实传导进过摆/耐力公式；
  右键卸件后人机/后坐条即时重着色（F3 证据）。所有视图共享 gunCompute 单一计算源。

## 透明图标全局修订（任务书修订件）
见 `transparent-asset-inventory.md` / `transparent-asset-pipeline.md` /
`transparent-asset-coverage.md` / `transparent-asset-quality.md`。要点：
`assets/icons-items-white/` 更名 `assets/icons-transparent/`（产物本来就是透明底 PNG，
白底只是当年 CSS 容器给的）；候选集扩展到**本地全部 5360 个物品图标**（含弹药），
生成 **5354 张**（6 件上游 404 有记录）；剪影重建为透明底（黑剪影+Alpha）；
全项目 10+ 处 CSS 白底与 multiply 混合废止；弹药页 7 处 itemIconUrl 调用切到 `setItemImg`
（透明→原webp→隐藏三级回退）。原始 `assets/icons-items/` 一个文件未动。
