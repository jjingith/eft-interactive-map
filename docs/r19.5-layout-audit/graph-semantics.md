# R19.5d 图形语义（graph-semantics.md）

## 参考站图形区域的实际含义（证据来源：devtools-investigation/）

| 图形 | 参考站实际行为 | 证据 |
|---|---|---|
| **装配关系节点图** | LOAD VARIANT 下方的**点阵画布**：左侧一条垂直节点链（绿/蓝状态点 + 节点 + 连线），节点=枪械/安装槽位；未选槽位时右栏显示 "Pick a mod" | 语义树 canvas rect [499,144,462,137] + 截图 i2-workbench.png |
| **属性条 ×5** | 画布下方 5 行（Ergonomics/Accuracy/Ver Recoil/Hor Recoil/Velocity），行距 12px，数值右对齐，含基线括号值 | 语义树 y=304/316/328/340/352 |
| **隐藏属性** | 属性条下方 2 列紧凑块（OverSwing / EvoErgoDelta / ArmStamina / 100% Headshot / ADS Time），约 40px 高 | 语义树 ArmStamina @[485,399] + 截图 |
| **配件槽位网格** | 自 y≈400 起：枪械居中卡 + 环绕的槽位卡（含空槽占位标签 MUZZLE/SCOPE/STOCK），卡上有 ± 属性角标 | 截图 i2-workbench.png |
| **FORGE 权衡图** | FORGE 面板底部文案："Press GENERATE BUILDS to compute the **3D Pareto Frontier**" —— 生成后才绘制的 3D 前沿图 | 截图 FORGE 区文本 |

## 本地对应实现（R19.5d）

- **装配关系图** = `#gw-nodecanvas`：点阵背景 + 垂直节点链，节点=枪械 + 前 4 个根槽位
  （真实装配数据），状态点：官方预设匹配→绿、已改→蓝、空槽→空心；点击节点选中该槽位，
  右栏候选随之切换。**不放入任何配件图片**。
- **属性条** = 5 条（人机/散布角/垂直/水平后坐/初速），保留 R19.4 的基线灰线、
  蓝红方向色与斜纹区间；装配变化后整条重算重绘。
- **隐藏属性** = 3 列紧凑键值（R19.5d 起无 ✓/≈ 徽标），数值与差值保留。
- **槽位网格** = 52px 方形卡（含空槽虚线占位+槽位短标签），枪械居中 78px 图。
- **FORGE 3D Pareto 图：未实现**（参考站需生成后由 WebGL 绘制三维前沿，本地无等价
  数据/渲染栈）。按"不伪造"原则不画假曲线；FORGE 仍提供 4 个方案的文本列表与
  目标值对比。此为**已知未完成项**，已列入 test-results.md。
