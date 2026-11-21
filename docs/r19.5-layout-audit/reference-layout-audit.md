# R19.5 参考布局审计（reference-layout-audit）

## 审计方式

重新逐区查看 `ui图标\改枪台界面.png`（1920×1080 原图，中栏 460–1130px 全高放大核对），
再实测本地 R19.4 页面（浏览器 getBoundingClientRect），逐项记录差异后重构。

## 参考站中栏结构（自上而下）

| # | 区域 | 参考站呈现 | R19.4 本地（改前） | 差异结论 |
|---|---|---|---|---|
| 1 | LOAD VARIANT 条 | 深色横条+小按钮组 | 顶栏下拉（位置不同） | 等价（信息在顶栏，层级保留） |
| 2 | 节点画布 | 点阵背景 + 可折叠装配图 | 无 | 由 #5 空间画布承担（见下） |
| 3 | 属性条 | Ergonomics/Accuracy/Ver/Hor/Velocity，基线括号值 | ✅ R19.4 已有（条纹+基线） | 一致 |
| 4 | 隐藏属性 | OverSwing/EvoErgoDelta/ArmStamina/爆头/ADS | ✅ R19.3 已有（双列紧凑） | 一致 |
| 5 | **空间槽位网格** | **枪械居中；上排机匣顶附件；中排枪管链向左/枪托向右；下排弹匣·握把；底部 rail attachments 分隔带；空槽=虚线占位+槽位短标签；卡上有 ± 属性角标** | ❌ **纵向递归卡片树（一列到底）** | **本轮重构核心** |
| 6 | Final Cost + Buy/Sell | 底部 | ✅ 已有 | 一致 |
| 7 | ITEMS 列表 | 底部逐件 delta+default | ✅ 已有（改装时间线） | 一致 |

## 纵向树 → 空间画布的实现（app.js renderGunTree 重写）

- **分区规则（通用，非逐枪坐标）**：`gwZoneOf(rootSid)`——`scope/tactical/sight_*`→顶带；
  `magazine/charge/pistol_grip/foregrip/bipod`→底带；`stock`→右链；
  `mount/trigger/hammer/catch`→（子树含瞄具类子槽时→顶带，否则）底部 rail attachments 带；
  其余（barrel/muzzle/gas_block/handguard/reciever/launcher）→左链。
- **链序**：左链 DFS 铺平后**反转**（根件贴枪、枪口端在外，对照参考站中排）；右链自然序。
- **子槽**：与父件同簇成行（`.gw-cluster`），换父件后随树重建自动刷新（复用 buildTree）。
- **连接线**：SVG `<path>` elbow 折线，布局完成后按真实 DOM 位置绘制
  （`requestAnimationFrame` + getBoundingClientRect，无硬编码坐标）。
- **空槽**：虚线占位框内嵌槽位短标签（MUZZLE / SIGHT_REAR…，对照参考站）。
- **卡片角标**：已装件上方 人机|后坐 ±徽标（对照参考站卡上 -3/-2.5 数字）。
- **枪械本体**：画布中央——完整整枪渲染 + 官方预设匹配标签 + 枪名 + 当前/基准重量（对照 3.50/3.86 kg）。
- **信息条**：原主图移入画布后，`gw-visual` 改为参考站 LOAD VARIANT 式摘要条
  （名称/口径/槽位摘要/成本 chips/预设匹配标签）。

## 改后实测（1920×1080，_accept.json v1920）

中栏 653px：画布 629px 占满；AK-74 画布 9 根卡+4 子卡、9 条连接线；
muzzle 左链（枪左侧）、stock 右链、magazine 底带、gas_block 左链——分区全部正确；
1264×705：画布 406px，flex 换行无横向溢出。


---

# R19.5b 第二次整改（真实截图对照轮）

工作方法更换：不再凭印象——(1) 参考截图视口逐行实测裁剪；(2) **经代理在真实浏览器中
加载 db4tarkov.com/gun 并驱动进工作台**（`screenshots/live-site-attempt.png` /
`live-site-workbench.png`，与用户截图交叉验证三栏几何）；(3) 本地按对齐视口 1920×919 截图，
50% 叠加 + 差分热力逐项核对。

新增/修正（详见 geometry-measurements.md）：
1. **三栏几何按实测重做**：486/490/858 fr 比 + 右侧 60px 留白（参考站不满宽——推翻此前
   "满宽三栏"与任务书估计值）。
2. **LOAD VARIANT 行**移入中栏顶（gw-ref/gw-default 迁入，id 不变）。
3. **装配关系点阵画布**（#gw-nodecanvas）：点阵背景 + 左侧垂直节点链（真实树数据、
   状态点色、点击选中槽位），对照参考站 LOAD VARIANT 下的折叠节点画布。
4. renderGunVisual 精简为行内摘要（去重 chips）。
交互验收（r195_accept 双视口）与全量 pytest（916 passed）改后重跑全绿。
