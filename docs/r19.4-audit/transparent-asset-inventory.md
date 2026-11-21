# R19.4 全项目物品图标盘点

## 资产目录与用途

| 目录 | 内容 | Alpha | 处置 |
|---|---|---|---|
| `assets/icons-items/*.webp`（5360） | 原 64px 不透明深色底物品图 | 无 | **原始素材，只读保留**；作为透明版缺失时的回退 |
| `assets/icons-transparent/*.png`（5354） | 64px 透明底 PNG（R18.2 白底目录更名，产物本来就是透明的） | 有 | **全项目统一图标源** |
| `assets/guns-full/*.png`（161） | 完整整枪渲染（默认预设） | 有（上游 Alpha） | 保留原 Alpha，未再处理 |
| `assets/presets-full/*.png`（368） | 官方预设整枪渲染 | 有 | 同上 |
| `assets/ui/placeholders/*.png`（10） | 空槽剪影 | **R19.4 重建为透明底**（黑剪影+Alpha） | 白底废止 |
| `assets/slot-glyphs/`、`assets/icons/`、`assets/icons-traders/` | UI 图形 / 商人图标（非物品图） | — | 不在本轮范围 |

## 代码引用审计（itemIconUrl / setGearIcon / setGunFullImg / setItemImg）

| 调用点 | 页面 | 现状 |
|---|---|---|
| `setItemImg` ×5 + SVG href ×1 | 弹药列表/散点/详情/模拟槽/装填弹窗 | ✅ 透明版（三级回退） |
| `setGearIcon` ×8 | 配装列表/配枪候选/装配卡/FORGE 钉选 | ✅ 透明版 |
| `setGunFullImg` ×2 | 枪械浏览卡/工作台主图 | ✅ 整枪透明渲染，回退 setGearIcon |
| `renderGunVisual` hero / `gwGunCard` | 工作台/浏览 | ✅ |
| 旧 `renderGunBrowse`（itemIconUrl 直引） | —— | ✅ **死代码已删除**（重复函数定义，运行时不可达） |

覆盖统计：候选 5360（=本地 icons-items 全集 ∪ 装备/枪械/配件/预设件），生成 5355，
缺失 5（全部有 reason 记录）；运行期任何物品图标都有透明对应物或明确回退。
