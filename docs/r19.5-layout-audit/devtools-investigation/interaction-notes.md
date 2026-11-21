# 参考站交互记录（interaction-notes.md）

## 已完成（真实浏览器 + CDP 输入事件）

| # | 操作 | 结果 | 证据 |
|---|---|---|---|
| 1 | 打开 `/gun`（经代理 127.0.0.1:7896） | Caliber 卡片墙加载 | `reference-screenshots/i1-caliber.png` |
| 2 | 点击 5.45x39 组 AK-74 卡（语义树实测该卡 [654,363,72,72]） | **进入工作台**（FORGE/画布/属性条/槽位网格/成本全部出现） | `i2-workbench.png` |
| 3 | 开启 Flutter accessibility | `flt-semantics` 519→201 节点，取得上表几何 | `semantics-raw.json` |
| 4 | 工作台内点击槽位 / 候选行（多组坐标 + 双击） | **未生效**：三步截图逐像素相同（右栏 changedPx=0, ratio=0.0；中栏同样 0.0） | `i3-slot-clicked.png` / `i4-part-installed.png` / `interaction-shots.json` |

## 阻碍因素（如实记录，不假装已捕获）

- 参考站工作台全部渲染在 Flutter CanvasKit 表面上，headless Chrome 的 `Input.dispatchMouseEvent`
  能完成"口径页 → 工作台"的点击（第 2 步成功），但在工作台内部的卡片/列表上不再触发手势，
  疑似 Flutter gesture arena 在 headless 下需要真实 pointer 时间戳/轨迹。
- 未尝试绕过（不注入脚本篡改页面、不读取其源码）。

## 因此交互行为证据来源

1. 本表第 2 步的**前后截图差异**（口径页 → 工作台，布局整体切换）；
2. 参考站在不同会话中呈现的两态截图：未选槽位时右栏 "Pick a mod"（`i2`）与
   用户提供的已选槽位截图（右栏为候选表）；
3. 用户提供的 4 张截图（口径/类别/表格/工作台）；
4. **本地**对应交互全部有真实浏览器自动化证据（`tools/r195_accept.py`：点槽位→候选切换、
   安装→图标变化、右键卸载→人机实时变化、恢复默认→官方预设、切枪无残留）。
