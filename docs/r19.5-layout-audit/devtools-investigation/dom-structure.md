# 参考站 DOM / 渲染结构调查（dom-structure.md）

## 决定性结论：参考站是 Flutter Web（CanvasKit），没有可分析的 widget DOM

| 证据 | 实测值 |
|---|---|
| `document.body` 元素数 | **26**（仅 Flutter 外壳 + reCAPTCHA） |
| `document.body.innerText` 长度 | **0** |
| `flutter-view` / `flt-glass-pane` | 均存在（true / true） |
| `<canvas>` 数量 | 0（CanvasKit 用 WebGL 表面，不走 2D canvas 节点） |
| 入口脚本 | `/flutter.js`、`/main.dart.js` |
| 语义树节点（开启 accessibility 后） | 519 → 工作台态 201 个 `flt-semantics`，多数 label 为空 |

推论：**不能用 Elements/Computed CSS 逆向参考站布局**——元素不存在于 DOM。
等价可用信息只有两种：(a) Flutter 语义树的 label+rect；(b) 截图像素测量。
本项目的布局复刻以此二者为据，并在 `computed-styles.json` 中如实记录"CSS 不可得"。

## 语义树可见的工作台几何（1920×919，AK-74N 工作台态）

| 区域 | 实测 rect [x,y,w,h] | 说明 |
|---|---|---|
| 顶部主导航 | [0,0,1920,48] | 全宽 |
| 次级工具栏（Caliber/Class/Table/Gun） | Caliber [0,52,44,30] … Gun [132,52,44,30] | 行高 30 |
| 工具按钮组（Compare 等） | [450..724, 53, 32×30] | — |
| **中栏面板** | **[480, 88, 512, 831]** | 中栏宽 **512**，自 y=88 |
| LOAD VARIANT 行 | y 88–135（按钮 24×24 @y101，标题 @y108） | **高约 47** |
| **装配画布** | **[499, 144, 462, 137]** | **462×137**，点阵背景 |
| **属性条** | y=304/316/328/340/352（**行距 12**） | 标签 x≈496–520，值 x≈930 |
| **隐藏属性** | ArmStamina @ [485, 399, 100, 14] | 块 y≈373–413 |
| 配件网格 | 自 y≈400 起（像素测量）；槽位卡 ~64px | 枪械居中，卡片环绕 |
| 右候选面板 | x≈1000–1860 | 未选槽位时显示 "Pick a mod" |

## 仍未知 / 无法取得

- Flutter widget 树的类名与约束（无 DOM）。
- 参考站的布局代码（不读取/不绕过服务端代码；仅行为观察）。
- 语义树对候选行、槽位卡的 label 覆盖不全（多数为空），因此行级细节以像素测量为准。
