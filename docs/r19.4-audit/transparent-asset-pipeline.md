# R19.4 透明素材管线

## 来源优先级（实际执行）

1. **已有透明底源图**（全部 5354 张走这条路）：上游 `assets.tarkov.dev/{id}-base-image.webp`
   是 RGBA 原始渲染 —— Alpha 即真实轮廓。读取实际像素确认（扩展名不可信）。
2. 构建期背景分割：**未使用** —— 深色物品+深色底在 64px 素材上无可靠逐像素边界
   （R18.2 已实测 matting/区域生长两条路全部破坏细节），上游透明源图覆盖了全部需求。
3. 人工修正蒙版：未触发（异常清单为空）。

## 流程（tools/build_gear_icons.py，可重复执行）

```
候选集 = 配装装备(pt/slot/cat) ∪ 枪械 ∪ 槽位allow ∪ 官方预设件 ∪ 本地icons-items全集(5360)
  → 按需下载 base-image（缓存 build-cache/gear-icons-src/，增量）
  → Alpha<16 视为全透明 → bbox 裁剪 → 等比缩放 56px → 64×64 透明画布居中
  → assets/icons-transparent/{id}.png + manifest（源URL/原始尺寸/alpha占比/结果）
```

- `--verify` 只校验不联网；增量重建只处理缺失项。
- 白底生成逻辑**废止**：目录更名 + 文档/测试全部迁移；产物从未烘焙白底
  （白底历史上只由 CSS 容器提供，本轮连容器白底一并移除）。
- 剪影管线（build_slot_placeholders.py）：render() 改输出 RGBA（黑剪影 + Alpha），
  ink_ratio 按 alpha 统计，manifest render.mode=RGBA/paper=transparent。

## Alpha 检查（抽样 412 / 全部 RGBA）

| 项 | 值 |
|---|---|
| RGBA 模式 | 412/412 |
| 有真实透明像素 | 412/412 |
| 无透明 / 近不透明 | 0 / 0 |
| 缺失（上游 404） | 5 件（名单见 manifest.missing，全部带原因） |
