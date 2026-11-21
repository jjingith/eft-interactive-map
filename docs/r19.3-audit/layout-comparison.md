# R19.3 布局对照与实测（P6）

## 1920×1080 工作台实测（getBoundingClientRect，浏览器真实值）

| 区域 | x | 宽 | 占比 | 参考截图对应 |
|---|---|---|---|---|
| 顶部工具条 gw-top | 0 | 1920 | — | 版本/导航行 |
| 视图工具条 gw-modes | 0 | 1920 | 高 33px | Caliber│Class│Table│Gun + FORGE/Compare |
| FORGE 左栏 | 0 | **461** | 24 percent | 约 500px（26 percent） |
| 中栏装配区 | 461 | **653** | 34 percent | 约 460px（24 percent）——本地中文标签更宽 |
| 右栏候选 | 1114 | **806** | 42 percent | 约 900px（47 percent） |
| 中栏主图 gw-hero | 485 | 605×172 | — | 枪械视觉区 |
| 属性条 gw-bars | 473 | 629×117 | — | Ergonomics/Recoil 条组 |
| 装配卡 gw-tree | 473 | 629×747 | — | 配件卡片网格 |
| 弹药卡 gw-ammo | 473 | 629×49 | — | 弹药行 |
| 底部成本+时间线 | 473 | 629×150 | — | Final Cost + Buy/Sell + 时间线 |
| 候选搜索框 | 1115 | 805×31 | — | "Type to search — ESC to clear" |

1264×705：无横向溢出（浏览页与工作台均验证），截图 `screenshots/p6-builder-1264.png`。

## 与参考截图的残余差异（如实）

1. LOAD VARIANT / 内置预设下拉在顶栏，参考站在中栏顶部（本地信息层级等价、位置不同）。
2. 参考站 FORGE 有 SUPPRESSED/BUYABLE/MAGS/SCOPE/TACTICAL/BLOCKED/FORCED 约束控件与
   3D Pareto —— 本地引擎无这些约束，**不做假控件**，只保留已实现的目标芯片+生成+应用。
3. 参考站中栏画布树（节点连线）——本地为纵向卡片树（递归/装卸完整）。
4. 参考站 Changes 页签（配件版本改动）——本地无历史版本数据。
5. 配色为 XP Luna 主题（按任务要求保留，不复制参考站暗色）。
6. 三栏比例 24/34/42 vs 参考 26/24/47：中栏承担了参考站"画布+卡片区"两块内容，
   候选列收窄以适配中文配件名。
