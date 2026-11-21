# R19.4 覆盖率与页面接线

## 覆盖率

| 项 | 值 |
|---|---|
| 应用引用的物品图标总数（本地全集） | 5360 |
| 已切换透明素材 | **5354（99.9%）** |
| 自动 Alpha 检查通过（抽样 412） | 412 |
| 人工对照抽查 | 32 张（`screenshots/transparent-before-after.png`，深/浅/彩/弹药/配件混合，灰底画布上直接可见透明效果） |
| 无可用源图 | 6（上游 404：HK416A5 RAL8000、P90 灾厄、杀人鲸匕首、NKVD 芬卡刀、VPO-101 预设等，全有 reason） |

## 页面接线核查（浏览器实测，_accept.json T 段）

| 页面/组件 | 图标数 | 透明 | 结论 |
|---|---|---|---|
| 配装页（左卡片 + 右列表） | 43 | **43** | ✅ 透明，米色卡底透出 |
| 弹药页（列表/详情/散点/模拟槽） | 200 | **200** | ✅ 透明，深色面板底透出 |
| 配枪工作台（浏览卡/装配卡/候选/主图） | 全部 | ✅ | 截图 t-builder-transparent.png |
| 空槽剪影 | 10 张 | ✅ | 重建为透明底（黑剪影+Alpha），multiply 废止 |

上下文对照：`screenshots/transparent-context-check.png`（同一批图标在米色卡/深色面板/
工作台三种底色下无白块黑块、边缘正常）。

## CSS 审计

移除的图标容器白底：`.tbl-icon`（配装）、`.gw-row-ic`、`.gw-part-ic`、`.gw-card-img`、
`.gw-hero`、FORGE pool/pin 图标、`.lw-sil`（剪影白底兜层）；
废止 `mix-blend-mode: multiply`（theme-windows-xp.css，剪影不再需要）；
保留的 `background` 全部属于页面/卡片容器（XP 主题），不属于图片。
