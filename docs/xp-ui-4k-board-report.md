# XP UI 第二张 4K 合体板：入场体检 / 切片 / 验收

**一句话结论：这次生成的图能用——28 个元素全部抠出并切成 1x 件，底色、完整性、紫边、三态尺寸全部通过；唯一不合格的是「窗口关闭键」被画成橄榄黄（ΔE 61.7–83.9，归一化救不了，需单独重生成或 CSS 改色）。**

---

## 0. 关键数字

| 项 | 结果 | 判定 |
|---|---|---|
| 画布 | 3840×2160，ratio 1.7778 | 16:9 ✓ |
| 键色 | `#F51CF7`（四边均值 245,28,247） | — |
| 边条 std（20px 四边 + 四角） | 最大 **2.63**（右内角 20×20） | <3，底色纯净 ✓ |
| 元素识别 | 12 左列 + 4 中列 + 12 右列 = **28/28** | 全识别 ✓ |
| 落在期望坐标框内的元素 | **0 / 28** | ✗（模型自行组版，见 §2.3） |
| 底板被塞图标 / 三角烤进底板 | 0 / 0 | ✓ |
| 文字 / 水印 / 外投影 / 外发光 | 无 | ✓ |
| 洋红残留像素 | **0** | ✓ |
| 深底 `#1b1b1b` 外沿 3px 环带命中 | **0** | ✓ |
| 输出 PNG 外沿同判据命中 | **0 / 3770**（0.000%） | ✓ |
| 色板同族（ΔE ≤ 3.5） | 25 件里 **25** 件 | ✓ |
| 明显漂移 | 仅 `win-btn-close` 三态（ΔE 61.70–83.91） | ✗ |
| 三态 / 五态外部尺寸一致 | 7 组 + 按钮 5 态全部一致 | ✓ |
| manifest | 25（原）+ 28（新）= **53 条** | ✓ |

---

## 一、目录盘点

同目录共 **5 张**，其中 4 张是原始源图（09:55–09:58），1 张是新生成图：

| 文件 | 尺寸 | mtime | 判定 |
|---|---|---|---|
| XP-Style Button States — Textle_952bcd15.png | 3520×2336 | 09:55 | 原始源图 |
| XP-Style Window Chrome — Textle_e8a477c1.png | 3520×2336 | 09:56 | 原始源图 |
| XP-Style Form Controls — Textle_78ca08b3.png | 2368×1776 | 09:57 | 原始源图 |
| XP-Style Title Plaques & Status_ebc3e75a.png | 3520×2336 | 09:58 | 原始源图 |
| **Create ONE 4K sprite sheet for_6bd58ee2.png** | **3840×2160** | **13:07** | **新生成（本报告对象）** |

原始 4 张只被读取，未改动、未覆盖、未重命名。新图文件名即提示词首句，尺寸精确等于 3840×2160，与「一张画布一次生成、8 倍绘制」的要求一致。

---

## 二、入场体检

### 2.1 画布与比例

3840×2160，W/H = 1.77778，严格 16:9。✓

### 2.2 底色纯度（判据：std > 3 直接判「需重生成」）

| 取样区 | 均值 | 通道 std（R/G/B） | 最大 std |
|---|---|---|---|
| 上边条 20px | 244.43, 26.87, 246.74 | 1.11 / **1.75** / 0.77 | 1.75 |
| 下边条 20px | 245.26, 27.12, 246.75 | 0.83 / **2.10** / 1.30 | 2.10 |
| 左边条 20px | 244.66, 29.68, 247.08 | 1.54 / **1.92** / 0.84 | 1.92 |
| 右边条 20px | 245.15, 28.90, 247.23 | 0.92 / **1.85** / 0.87 | 1.85 |
| 左上角 20×20 | 243.74, 28.53, 245.88 | 1.63 / 1.78 / 1.06 | 1.78 |
| 右上角 20×20 | 243.90, 28.00, 246.22 | 1.20 / 2.17 / 1.02 | 2.17 |
| 左下角 20×20 | 244.16, 27.82, 246.20 | 1.81 / 2.56 / 1.72 | 2.56 |
| **右下角 20×20** | 244.60, 28.02, 246.02 | 1.05 / **2.63** / 1.22 | **2.63** |

实测键色 `#F51CF7`。最大 std = 2.63 < 3，**底色纯度合格**，不需要重生成。

> 说明：G 通道 std 偏高是因为洋红的 G 只有 28，噪声相对占比大；绝对波动 ≤10 级，抠图容差 25 完全覆盖。

### 2.3 逐元素定位：实际 bbox vs 期望 bbox

期望框来自本报告 §6 的合体提示词坐标表（3840×2160、8x、三列分区、边距 ≥160、元素间距 ≥120）。实际框是画布上该元素非洋红像素的实测包围盒。

| # | 元素 | 期望 8x (x,y,w,h) | 实际 8x (x,y,w,h) | Δx | Δy | Δw | Δh | 宽误差% | 高误差% |
|---|------|------------------|------------------|----|----|----|----|--------|--------|
| 1 | scroll-v-track | 420,560,168,568 | 223,386,174,1371 | −197 | −174 | +6 | +803 | +3.6% | +141.4% |
| 2 | scroll-v-thumb | 708,560,168,248 | 542,386,182,405 | −166 | −174 | +14 | +157 | +8.3% | +63.3% |
| 3 | scroll-v-thumb-hover | 708,928,168,248 | 542,850,182,401 | −166 | −78 | +14 | +153 | +8.3% | +61.7% |
| 4 | scroll-v-thumb-pressed | 708,1296,168,248 | 542,1311,182,406 | −166 | +15 | +14 | +158 | +8.3% | +63.7% |
| 5 | scroll-v-arrow-up | 996,560,216,200 | 872,386,227,211 | −124 | −174 | +11 | +11 | +5.1% | +5.5% |
| 6 | scroll-v-arrow-up-hover | 996,880,216,200 | 872,742,227,214 | −124 | −138 | +11 | +14 | +5.1% | +7.0% |
| 7 | scroll-v-arrow-up-pressed | 996,1200,216,200 | 872,1098,227,212 | −124 | −102 | +11 | +12 | +5.1% | +6.0% |
| 8 | scroll-v-arrow-down | 1284,560,216,200 | 1234,386,222,211 | −50 | −174 | +6 | +11 | +2.8% | +5.5% |
| 9 | scroll-v-arrow-down-hover | 1284,880,216,200 | 1234,742,222,214 | −50 | −138 | +6 | +14 | +2.8% | +7.0% |
| 10 | scroll-v-arrow-down-pressed | 1284,1200,216,200 | 1234,1098,222,212 | −50 | −102 | +6 | +12 | +2.8% | +6.0% |
| 11 | scroll-v-glyph-up | 420,1248,88,56 | 926,1432,160,86 | +506 | +184 | +72 | +30 | +81.8% | +53.6% |
| 12 | scroll-v-glyph-down | 420,1424,88,56 | 926,1627,161,90 | +506 | +203 | +73 | +34 | +83.0% | +60.7% |
| 13 | slider-v-track | 1660,560,136,480 | 1707,386,144,1102 | +47 | −174 | +8 | +622 | +5.9% | +129.6% |
| 14 | slider-v-thumb | 1916,560,264,152 | 1995,386,440,224 | +79 | −174 | +176 | +72 | +66.7% | +47.4% |
| 15 | slider-v-thumb-hover | 1916,832,264,152 | 1995,758,440,227 | +79 | −74 | +176 | +75 | +66.7% | +49.3% |
| 16 | slider-v-thumb-pressed | 1916,1104,264,152 | 1995,1131,440,234 | +79 | +27 | +176 | +82 | +66.7% | +53.9% |
| 17 | win-btn-min | 2340,560,264,152 | 2678,361,254,236 | +338 | −199 | −10 | +84 | −3.8% | +55.3% |
| 18 | win-btn-min-hover | 2340,832,264,152 | 2678,721,254,244 | +338 | −111 | −10 | +92 | −3.8% | +60.5% |
| 19 | win-btn-min-pressed | 2340,1104,264,152 | 2678,1092,254,231 | +338 | −12 | −10 | +79 | −3.8% | +52.0% |
| 20 | win-btn-max | 2724,560,264,152 | 3023,361,255,236 | +299 | −199 | −9 | +84 | −3.4% | +55.3% |
| 21 | win-btn-max-hover | 2724,832,264,152 | 3023,721,255,244 | +299 | −111 | −9 | +92 | −3.4% | +60.5% |
| 22 | win-btn-max-pressed | 2724,1104,264,152 | 3023,1092,255,231 | +299 | −12 | −9 | +79 | −3.4% | +52.0% |
| 23 | win-btn-close | 3108,560,264,152 | 3367,361,258,236 | +259 | −199 | −6 | +84 | −2.3% | +55.3% |
| 24 | win-btn-close-hover | 3108,832,264,152 | 3367,721,258,244 | +259 | −111 | −6 | +92 | −2.3% | +60.5% |
| 25 | win-btn-close-pressed | 3108,1104,264,152 | 3366,1092,259,231 | +258 | −12 | −5 | +79 | −1.9% | +52.0% |
| 26 | win-glyph-min | 2340,1376,176,64 | 2716,1611,172,65 | +376 | +235 | −4 | +1 | −2.3% | +1.6% |
| 27 | win-glyph-max | 2636,1376,160,160 | 3065,1557,161,157 | +429 | +181 | +1 | −3 | +0.6% | −1.9% |
| 28 | win-glyph-close | 2916,1376,160,176 | 3423,1557,159,172 | +507 | +181 | −1 | −4 | −0.6% | −2.3% |

统计：

- 平均 |Δx| = **232.6 px**，平均 |Δy| = **131.0 px**，平均 |Δw| = 30.7 px，平均 |Δh| = 108.3 px
- 最大 |Δx| = **507 px**，最大 |Δy| = 235 px，最大 |Δw| = 176 px，最大 |Δh| = **803 px**
- **落在期望框内的元素 = 0 / 28**

**判读：**这不是「切偏了」，而是**模型根本没拿到坐标表**——本板是用第三轮那三条独立提示词逐条生成的（每条各画一张自己的版式），本板只是模型把三组元素按自己的习惯排成了「左滚动条 / 中滑轨 / 右三键」三列。因此：

- 元素**语义**全部正确（12+4+12 一个不多一个不少，三态齐全，三角/图标均为独立件）；
- 元素**相对位置**正确（左中右三列分区与要求一致）；
- 元素**尺寸**漂移（长轨/滑块拉长，窗口键变高变窄，三角图标偏大）；
- 绝对坐标不可对齐。

结论：**不能按表硬切，但可以按实测 bbox 切**（本报告即按实测 bbox 切的，见 §3）。若要求严格对齐坐标表，需要用 §6 的合体提示词重生成一次。

### 2.4 元素完整性

| 检查项 | 结果 |
|---|---|
| 箭头底板是否被塞进三角 | 否，箭头底板内部实心纯色，三角是独立的 `scroll-v-glyph-*` |
| 窗口三键底板是否空白 | 否（空白），横杠/方框/叉都是独立 `win-glyph-*` |
| 底板里是否混入图标 | 无 |
| 是否出现文字 / 数字 / 水印 | 无（全画布无非洋红的文字类连通域） |
| 是否有外投影 / 外发光 | 无（alpha bbox 外侧 3px 环带脏像素 = 0） |
| 是否有关闭键红色异常 | **有**：关闭键被画成橄榄黄（见 §2.5） |

### 2.5 色板贴合度（新件主导色 vs 现有 25 件对应色）

ΔE 为 CIE76（sRGB → Lab D65）。

| 新件 | 新件色 | 参照件 | 参照色 | ΔE | 最大通道差 |
|---|---|---|---|---|---|
| win-btn-min | #E3E3D3 | btn-normal | #EDEAD9 | **2.92** | 10 |
| win-btn-min-hover | #F6F4EE | btn-hover | #F8F5EE | **0.73** | 2 |
| win-btn-min-pressed | #DDDDCC | btn-pressed | #D5D5C2 | **3.11** | 10 |
| **win-btn-close** | **#A5A300** | btn-normal | #EDEAD9 | **66.74** | **217** |
| win-btn-close-hover | #DDDB00 | btn-hover | #F8F5EE | **83.91** | 238 |
| win-btn-close-pressed | #9E9C00 | btn-pressed | #D5D5C2 | **61.70** | 194 |
| scroll-v-arrow-up | #E5E4D5 | btn-normal | #EDEAD9 | **2.53** | 8 |
| scroll-v-arrow-up-hover | #F6F4EE | btn-hover | #F8F5EE | **0.73** | 2 |
| scroll-v-arrow-up-pressed | #CCCCBC | btn-pressed | #D5D5C2 | **3.50** | 9 |
| scroll-v-thumb | #E4E3D4 | btn-normal | #EDEAD9 | **2.85** | 9 |
| scroll-v-thumb-hover | #F6F4EE | btn-hover | #F8F5EE | 0.73 | 2 |
| scroll-v-thumb-pressed | #DDDDCC | btn-pressed | #D5D5C2 | 3.11 | 10 |
| slider-v-thumb | #E6E5D6 | btn-normal | #EDEAD9 | **2.23** | 7 |
| slider-v-thumb-hover | #F6F4EE | btn-hover | #F8F5EE | 0.73 | 2 |
| slider-v-thumb-pressed | #DCDCCC | btn-pressed | #D5D5C2 | 3.05 | 10 |
| scroll-v-track | #DCDCCC | track | #DDDACA | **1.19** | 2 |
| slider-v-track | #DBDBCC | track | #DDDACA | **1.22** | 2 |

**判定：**

- **同族（轻度偏暗）**：全部米色件，ΔE 0.73–3.50，最大通道差 ≤10。统一偏暗约 5–8 级，肉眼需并排才可辨，不需要归一化。
- **明显漂移**：`win-btn-close` 三态被画成**亮橄榄黄**（面 `#A5A300`，悬停 `#DBD900`），而 XP 惯例与提示词都要求**红色**。色相差 ~70°，这是**色相漂移**，不是亮度漂移，§5 的漂移色归一化**不处理也不应处理**。

---

## 三、切片

### 3.1 产出

按实测 bbox 在 8x 画布上裁框 → 预乘 alpha → `Image.BOX` 整块 1/8 面积平均 → 1x PNG。共 **28 件**：

| 组 | 文件 | 1x 尺寸 |
|---|---|---|
| 竖向滚动条 | scroll-v-track | 22×171 |
| | scroll-v-thumb / -hover / -pressed | 23×51 ×3 |
| | scroll-v-arrow-up / -hover / -pressed | 28×27 ×3 |
| | scroll-v-arrow-down / -hover / -pressed | 28×27 ×3 |
| | scroll-v-glyph-up / glyph-down | 20×11 ×2 |
| 竖向滑轨 | slider-v-track | 18×138 |
| | slider-v-thumb / -hover / -pressed | 55×29 ×3 |
| 窗口三键 | win-btn-min / max / close（每态） | 32×30 ×9 |
| | win-glyph-min / max / close | 22×8 / 20×20 / 20×22 |

切片约定（已落实）：

- 静态件固定尺寸，不做 9-slice；
- `scroll-v-track` 用 **repeat-y**：`slice_1x = 18 3 18 3`（端头斜面占 18px），中间 135 行实测行均值极差 ≤3；
- `slider-v-track` 用 repeat-y：`slice_1x = 8 3 8 3`；
- 箭头底板**整件使用**，三角由 `scroll-v-glyph-*` 叠上去；
- 窗口三键底板**整件使用**，图标由 `win-glyph-*` 叠上去。

### 3.2 manifest

`assets/xp-ui/manifest.json` 由 **25 条扩到 53 条**，新 28 条字段与原 25 条**完全同构**：

`file / size / source_file / source_box / source_size / bg_rgb / slice_source / slice_1x / border_width_css / purpose`

其中 `source_box` 与既有 25 条同一口径：**8x 画布上的 (x0, y0, x1, y1) 裁切框**；`source_size` 为其宽高；`slice_source` 是 1x 切片值 ×8。板级配置写在 `config.generated_board`（size / bg_hex / bg_std / scale=8 / downsample=box / normalize=false）。原 25 条一字未改。

### 3.3 紫边与洋红复检

| 判据 | 结果 |
|---|---|
| 深底 `#1b1b1b` 外沿 3px 环带，`(B−G)≥8 且 (R−G)≥4` | **0 px**（28 件合计） |
| 输出 PNG 最外 1px 行/列同判据（alpha>0 采样 3770 点） | **0 px，0.000%** |
| 洋红残留（alpha>0 且 R−G≥20 且 B−G≥20） | **0 px** |

### 3.4 三态 / 五态尺寸一致性

| 组 | 1x 尺寸 | 一致 |
|---|---|---|
| scroll-v-thumb 三态 | 23×51 / 23×51 / 23×51 | ✓ |
| scroll-v-arrow-up 三态 | 28×27 ×3 | ✓ |
| scroll-v-arrow-down 三态 | 28×27 ×3 | ✓ |
| slider-v-thumb 三态 | 55×29 ×3 | ✓ |
| win-btn-min 三态 | 32×30 ×3 | ✓ |
| win-btn-max 三态 | 32×30 ×3 | ✓ |
| win-btn-close 三态 | 32×30 ×3 | ✓ |
| 既有按钮五态 | 95×42 ×5 | ✓ |

状态切换不会引起 1px 跳位。

---

## 四、验收板

`assets/xp-ui/demo.html` 在原 I 区之后新增两区：

- **J 区「竖向滚动条」**（`#case-vscroll`）：320px 与 480px 两根长条（看平铺接缝）、滑块三态列、竖向滑轨三态、上/下箭头三态、三角图标单列；
- **K 区「窗口三键」**（`#case-winbtn2`）：min/max/close 各三态（forced 内联背景）、三键 + 图标叠加行、蓝色标题栏实测条。

截图（`assets/xp-ui/_shots/`）：

| 文件 | 尺寸 | 内容 |
|---|---|---|
| demo-1440-full.png | 1440×3018 | 整页（A–K 全部区） |
| demo-860-full.png | 860×3403 | 整页窄屏 |
| **zoom-J-vscroll.png** | 1480×1040 | 竖滚条 2×NEAREST 局部放大 |
| **zoom-K-winbtn2.png** | 1980×590 | 窗口三键 2×NEAREST 局部放大 |

### 平铺接缝

轨道贴图的首尾衔接（middle 段首行 vs 末行，逐通道）：

| 轨道 | cap | 中段行 | 首末行最大通道差 | 平均 |
|---|---|---|---|---|
| scroll-v-track（22×171） | 18 | 18–152 | **9** | 2.52 |
| slider-v-track（18×138） | 8 | 18–119 | **6** | 1.57 |

最大差 9/255 ≈ 3.5%，低于肉眼可辨阈值。放大图里 320px 与 480px 两根长条轨道连续，看不到周期性横缝。

> 建议：`border-image-repeat: stretch repeat` 保持现状；若将来把轨道压到 12px 宽以下，需重新验端头斜面（cap 18 会占满宽度）。

---

## 五、不合格项与兜底

| 不合格项 | 严重度 | 处理 |
|---|---|---|
| 元素绝对坐标与坐标表不符（0/28 落框，平均偏移 232×131px，尺寸漂移最大 +803px） | 中 | **不影响出件**（按实测 bbox 已切出）；若要严格对齐 → 用 §6 提示词**重生成** |
| `win-btn-close` 三态为橄榄黄（ΔE 61.70–83.91，色相差 ~70°） | 中 | **重生成**该键，或 CSS 端用红面替换；**归一化无效** |
| 长轨 / 滑块 / 窗口键比例与 1x 规格不同（168×568→174×1371 等） | 低 | 已按实测尺寸建 manifest 与 CSS；纯视觉差异，可接受 |

**归一化能不能救？** 不能救关闭键，也不需要救其他件（其余 ΔE ≤3.5，已在同族内）。

### 漂移色归一化：实现与量化（第二项交付）

**位置**：`tools/xp_ui_slice.py` 内新增归一化区块（第 287 行起），两张板脚本都暴露开关：

```
python tools/xp_ui_slice.py --normalize        # 原 25 件重跑时启用
python tools/xp_ui_slice_gen.py --normalize    # 8x 合体板切片时启用
```

**默认关闭**。不加 `--normalize` 时，现有 25 件产物与 manifest 的 `pixels/色值` 完全不变（本次即为默认关闭状态）。

**算法（纯平移，不重排色阶）**

1. 目标 ramp：用现有 1x 件实测色板 `#F5F5EB → #EDEAD9 → #A5A396 → #626355`，按亮度分位 30/50/70/90 切三段取带均值，得到参考三段均色 `REF_BANDS`。
2. 对待归一化的每张源板，同样按亮度分位切三段取带均值（只统计 `alpha ≥ 8` 的像素）。
3. `offset[i] = median_over_bands(REF_bands[i] − 源bands[i])`，i = R/G/B。用**中位数**而不是均值，避免长轨道亮面主导估计。
4. 全图做**整通道平移**。因为三通道平移量是常数，亮度序关系不变，**1px 外框与内高光层次自动保留**。
5. 饱和端点保护：`max(RGB) ≤ 3`（纯黑）与 `min(RGB) ≥ 250`（纯白）不动；`max−min ≥ 60` 的彩色像素只做**标量平移**（三通道同量），保持色相，因此图标色 `#3B412F` 与关闭键的橄榄黄不会被「洗成米色」。
6. 只作用于 `alpha > 0` 的精灵本体像素；洋红底与 `alpha = 0` 的像素 RGB 一律不动。

**合成漂移自测**（对现有 25 件人为加漂移，归一化后与原件比）：

| 漂移 | 估计 offsets (R,G,B) | 归一化前平均 ΔE | 归一化后平均 ΔE | 最大通道差（前→后） |
|---|---|---|---|---|
| D1 偏暖（R−14/B+16） | −14.3, −2.7, +15.5 | **10.46** | **1.33** | 16 → 16 |
| D2 提亮 +18 | −16.9, −18.6, −18.5 | **6.11** | **1.35** | 18 → 18 |
| D3 压暗 −22 | +21.5, +21.3, +21.5 | **8.31** | **0.86** | 22 → 22 |
| D4 降饱和 30% + 压暗 6 | +6.5, +5.3, +0.6 | **3.71** | **1.71** | 56 → 60 |
| D5 偏绿（G−7） | +9.5, −6.7, +7.5 | **9.39** | **1.21** | 10 → 10 |
| D6 组合（R−10/G+3/B+7） | −9.8, +3.3, +7.1 | **5.87** | **1.12** | 21 → 21 |

- 平均 ΔE 从 3.71–10.46 压到 **0.86–1.71**（降幅 **77%–90%**，D4 因含饱和度损失只能到 1.71）。
- D4 的「最大通道差 56→60」是**高饱和像素**在标量平移下的固有代价（保色相优先），但平均 ΔE 仍从 3.71 降到 1.71。
- 无漂移 sanity：`offsets = [−0.46, −0.66, −0.49]`，对原件最大改动 **1 级**，可认为恒等。
- 硬约束：`alpha` 变化像素 = **0**；`alpha = 0` 但 RGB 被改写的像素 = **0**。
- 端点层次：`check-on` 黑描边 (2,4,3) → (3,3,3)；`titlebar` 暗边 (67,74,65) → (68,73,63)；高光 (255,255,255) 保持不变。层次未被压平。

**结论**：归一化能把「米色整体偏暖/偏亮/偏暗/偏绿」压回同族（ΔE < 1.8），且不碰图标色、不碰透明度、不改现有 25 件（默认关闭）。它**不能**也不应该修色相漂移（如关闭键的橄榄黄）。

---

## 六、合体提示词（重生成用）

> 当前板是「三条独立提示词各出一张」的产物，所以坐标全部不对。要严格对齐，用下面这份**一张画布一次生成**的提示词。
>
> **两张版本，附图参考版优先**：能垫图就用 A 版（材质/色板一致性最好）；不能垫图才用 B 版（纯文字，需接受材质漂移）。
>
> 坐标表口径：**3840×2160 横向、8 倍绘制、三列分区**；画布四边 ≥160px 纯洋红、元素间距 ≥120px；放不下的列已按**错列**写明（左列用 4 个子列 + 三角图标另起一行）。

### A 版（附图参考版，优先）

Reference image: `D:\personal\trae\02-塔科夫\ui图标\xp风格ui` 里的按钮板那张（`XP-Style Button States — Textle_952bcd15.png`）。

```text
Create ONE single sprite sheet, 3840x2160 landscape (16:9), flat magenta background.

REFERENCE IMAGE RULES — highest priority, read twice:
- I am providing ONE reference image of Windows-XP-style UI controls. Borrow ONLY these four
  things: (1) surface material texture, (2) the cream color palette, (3) bevel thickness and
  the exact 1-pixel highlight/shadow geometry, (4) the pixel-level crispness of the edges.
- ABSOLUTELY DO NOT copy the reference image's layout, canvas arrangement, number of elements,
  grouping, spacing, grid, or ordering. Do not reproduce its button plate, its input field,
  its container, or its misc sheet. If the reference shows 12 controls, this output still
  contains EXACTLY the 28 sprites listed in the COORDINATE TABLE below, at EXACTLY those
  coordinates. The COORDINATE TABLE overrides the reference image completely.
- Treat the reference as a swatch book, never as a layout template.

CANVAS
- Exactly 3840 x 2160 pixels, landscape.
- Background: flat pure magenta #FF00FF. No gradient, no vignette, no noise, no paper texture.
- Keep at least 160 px of clean pure magenta on all four outer edges.
- Keep at least 120 px of clean pure magenta between any two sprites (the table already
  respects this; do not tighten it).

SCALE
- Draw everything at 8x: one logical UI pixel = an 8x8 solid block of source pixels.
- Bevel highlights and shadows are exactly 8 px wide at this scale (i.e. 1 logical px).
- Edges must be crisp and blocky. No anti-aliasing haze along the bevel, no soft blur.

COLOR PALETTE (measured from my existing 25 sprites — use these exact values)
- bright face      #F5F5EB
- normal face      #EDEAD9
- mid dark face    #A5A396
- outline / shadow #626355
- hover face       #F8F5EE
- pressed face     #D4D4C2
- glyph / icon ink #3B412F
- track inner      #DDDACA
Build every bevel as: 1px white-ish top/left highlight (#FBF9F0 -> #F5F5EB),
1px #626355 bottom/right shadow, 1px #626355 outer outline all around.
Pressed state inverts the bevel: shadow moves to top/left, highlight to bottom/right.
Never use warm beige, yellow, olive, green, or blue tints anywhere except the close key
described below.

LAYER RULES (strict)
1. Every bevel, shadow and highlight must live INSIDE the sprite's own rectangle.
   No pixel may fall outside the given x/y/w/h. No drop shadow, no outer glow, no halo.
2. Icons are SEPARATE sprites, not painted into the plates.
   The arrow plates and all nine window-key plates must be completely EMPTY inside:
   no triangle baked in, no minus bar, no square, no X, no dot, no text.
3. Every sprite is a closed shape: a 1px #626355 outline on all four sides, then the bevel,
   then the flat face. Corners are hard pixel steps, never rounded smoothly.
4. No text, no numbers, no letters, no watermark, no frame, no ruler, no labels anywhere.

COORDINATE TABLE — 28 sprites, all coordinates in 3840x2160 source pixels.
Format: name | x | y | w | h | resulting 1x size after 1/8 downsample.

LEFT COLUMN (vertical scrollbar) — 4 sub-columns, deliberately staggered, do not pack tighter:
scroll-v-track             | 420  | 560  | 168 | 568 | 21x71
scroll-v-thumb             | 708  | 560  | 168 | 248 | 21x31
scroll-v-thumb-hover       | 708  | 928  | 168 | 248 | 21x31
scroll-v-thumb-pressed     | 708  | 1296 | 168 | 248 | 21x31
scroll-v-arrow-up          | 996  | 560  | 216 | 200 | 27x25
scroll-v-arrow-up-hover    | 996  | 880  | 216 | 200 | 27x25
scroll-v-arrow-up-pressed  | 996  | 1200 | 216 | 200 | 27x25
scroll-v-arrow-down        | 1284 | 560  | 216 | 200 | 27x25
scroll-v-arrow-down-hover  | 1284 | 880  | 216 | 200 | 27x25
scroll-v-arrow-down-pressed| 1284 | 1200 | 216 | 200 | 27x25
scroll-v-glyph-up          | 420  | 1248 | 88  | 56  | 11x7
scroll-v-glyph-down        | 420  | 1424 | 88  | 56  | 11x7
(the two glyphs are placed on a separate row below the track because the left column
cannot stack 9 arrow plates plus a 568-tall track inside 2160 px without staggering)

MIDDLE COLUMN (vertical slider):
slider-v-track             | 1660 | 560  | 136 | 480 | 17x60
slider-v-thumb             | 1916 | 560  | 264 | 152 | 33x19
slider-v-thumb-hover       | 1916 | 832  | 264 | 152 | 33x19
slider-v-thumb-pressed     | 1916 | 1104 | 264 | 152 | 33x19

RIGHT COLUMN (window buttons, 3 columns x 3 rows):
win-btn-min                | 2340 | 560  | 264 | 152 | 33x19
win-btn-min-hover          | 2340 | 832  | 264 | 152 | 33x19
win-btn-min-pressed        | 2340 | 1104 | 264 | 152 | 33x19
win-btn-max                | 2724 | 560  | 264 | 152 | 33x19
win-btn-max-hover          | 2724 | 832  | 264 | 152 | 33x19
win-btn-max-pressed        | 2724 | 1104 | 264 | 152 | 33x19
win-btn-close              | 3108 | 560  | 264 | 152 | 33x19
win-btn-close-hover        | 3108 | 832  | 264 | 152 | 33x19
win-btn-close-pressed      | 3108 | 1104 | 264 | 152 | 33x19
win-glyph-min              | 2340 | 1376 | 176 | 64  | 22x8
win-glyph-max              | 2636 | 1376 | 160 | 160 | 20x20
win-glyph-close            | 2916 | 1376 | 160 | 176 | 20x22

SPECIAL SHAPES
- scroll-v-track and slider-v-track are vertical tracks: same bevel on all sides, with a
  REPEATABLE middle band. The top 18 logical px (144 src px) and bottom 18 logical px (144 src px)
  of scroll-v-track must contain the corner bevel; the middle band must be perfectly uniform
  left-to-right so it can tile vertically without a seam. Same idea for slider-v-track with a
  8 logical px (64 src px) cap.
- scroll-v-glyph-up / glyph-down: solid #3B412F triangles, no plate, no outline box.
- win-glyph-min: a single #3B412F horizontal bar. win-glyph-max: a #3B412F square outline.
  win-glyph-close: a #3B412F X.
- win-btn-close (all three states) is the ONLY non-cream sprite: deep red face
  #B03A2E, hover #C64A3A, pressed #8E2E24, bevel highlight #E8B0A6, outline #5A1C15.

CUTTING
- Cut each sprite at exactly x/y/w/h above on the 3840x2160 canvas, with zero extra padding.
- Downsample each crop by exactly 1/8 with an AREA/BOX filter (8x8 block average), giving the
  1x size in the last column. Do not use smooth interpolation.
- Cutting coordinates are identical to the values in the table; downsample factor is 1/8.

NEGATIVE — do not do any of the following:
no magenta in the output sprites, no magenta tint on the bevels, no purple fringe,
no smooth anti-aliased corners, no rounded iPhone-style corners, no glass/glossy/plastic
modern look, no gradients inside faces, no icons baked into plates, no text or watermark,
no reference-image layout, no additional decorative elements, no borders around the canvas,
no drop shadows outside sprites, no tint of yellow/olive/green/blue on any cream sprite,
no duplication (exactly 28 sprites, exactly one of each listed name).
```

### B 版（纯文字版，降级）

不能垫图时用；差别只在没有参考图那一段，其余全部相同。材质靠下面这段文字描述替身：

```text
[Use A-version text, but replace the REFERENCE IMAGE RULES block with:]

MATERIAL RULES (no reference image provided, so build the look from this description)
- Classic Windows-XP "Luna" bevel look: a flat matte cream face, hard 1px stepped bevel,
  a white-ish inner highlight on the top and left edges, a dark warm-grey shadow on the
  bottom and right edges, and a single 1px dark outline around the whole sprite.
- Faces are FLAT. No gradient, no gloss, no specular streak, no glass reflection.
- Surface must read as slightly grainy matte plastic at 8x: very low-amplitude, non-repeating
  noise inside the face only, and it must disappear when downsampled by 8.
- Bevels are stair-stepped, not smooth. Corners are 2-3 logical px staircase steps.
```

### 用法要点

1. 先试 A 版。A 版把参考图限制成「色卡」，坐标表放在末尾并明确声明覆盖参考图——这是防止模型把按钮板原样搬过来的关键。
2. 出图后按 §2 的流程复检：① 尺寸 3840×2160；② 四边 20px std < 3；③ 28 个元素逐个在期望框内找 bbox，误差应 ≤ ±3%；④ 底板空白、三角/图标独立。
3. 若 B 版出图后米色整体偏暖/偏暗，再跑 `--normalize`（见 §5，ΔE 可压到 <1.8）。
4. 关闭键要单独确认是**红色**（`#B03A2E`），这是本次唯一的色相事故。

---

## 七、改动清单

| 文件 | 动作 |
|---|---|
| `tools/xp_ui_slice.py` | 新增归一化区块 + `--normalize`（默认关闭）；`resize_premult` 增加 `resample` 参数 |
| `tools/xp_ui_slice_gen.py` | 新增（8x 合体板切片）；`source_box` 改为 `(x0,y0,x1,y1)` 口径与新 28 条字段同构；修正关闭键 purpose 描述（红面 → 实测橄榄黄） |
| `assets/xp-ui/*.png` | 新增 28 件 |
| `assets/xp-ui/manifest.json` | 25 → 53 条；`config.generated_board` |
| `assets/xp-ui/xp-ui.css` | 追加第二张板组件层（`.xp-vscroll` / `.xp-vslider` / `.xp-winbtn2`） |
| `assets/xp-ui/demo.html` | 新增 J、K 两区 |
| `assets/xp-ui/_shots/` | 新增 2 张整页 + 2 张局部放大 |

未改动：`index.html` / `style.css` / `app.js` / 原始 4 张源图。未 git commit。
