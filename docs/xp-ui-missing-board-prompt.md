# XP UI 缺件 · 4K 合体生图板（提示词 + 坐标表）

> 目标：一张 **3840×2160** 的 4K 合体图，一次画完 **44 件**缺件素材；纯洋红键色抠图后接回 `assets/xp-ui/`。
> 本文件里的提示词可直接复制给生图模型；坐标表用于裁切。
> 流程沿用上一张成功板 `docs/xp-ui-4k-board-report.md`：单张 4K、块状绘制、纯洋红底、坐标表、1px 硬边、1/8 或 1/2 降采样。
>
> 不适用的旧口径已在下面改掉，并写清原因。

---

## 0. 本板口径（与上一张板不同的两处，先看这里）

| 项 | 本板取值 | 说明 |
|---|---|---|
| 画布 | 3840×2160 横向 | 沿用上一张成功板 |
| 键色 | **#F51CF7 = RGB(245,28,247)** | 本项目实测四边均值；**不是**通用 `#FF00FF`。见 `docs/xp-ui-4k-board-report.md` §12 |
| 绘制倍数 | **2x**（1 逻辑像素 = 2×2 源像素） | 本批含 800px 宽的状态栏底板。若按上一张的 8x，单它就要 6400px，超出 3840；所以整板统一 2x，裁切后 1/2 降采样 |
| 四边留白 | ≥160px 纯洋红 | 沿用上一张 |
| 元素间距 | ≥64px 纯洋红 | 2x 下等于 32 逻辑像素，比上一张 8x 的 120px（≈15 逻辑像素）更宽 |
| 元素块 | 每件独立矩形，互不接触 | 本批要求「不可相互重叠」 |
| 文字 | 全图零文字；徽标中心留空 | 图标内也不画文字 |
| 硬阴影 | 只允许矩形内部的 1px 硬线 | 不许外投影、不许柔边 |

> **间距为什么改 64 而不是 120**：上一张是 8x，120 源像素只有 15 逻辑像素；本板 2x 的 64 源像素 = 32 逻辑像素，实际留白是上一张的两倍，裁切更安全。

---

## 1. 可直接复制的生图提示词

### 1.1 A 版（垫参考图，优先）

```text
Create ONE single 4K sprite sheet, exactly 3840 x 2160 px landscape, containing EXACTLY 44 UI
sprites for a Windows XP (Luna) pixel-art control library. Every sprite sits in its own
rectangle at the exact coordinates in the COORDINATE TABLE below. This is one flat asset sheet,
not a UI mockup, not a screenshot, not a composition.

CANVAS + KEY COLOR (hard requirements)
- Background: one single flat magenta key color, exactly #F51CF7 = RGB(245,28,247).
  This value is measured from my existing asset library. Do NOT use #FF00FF, #FA05F9,
  the shorthand #F0F, or any other magenta. One uniform color from edge to edge.
- No gradient, vignette, noise, grain, paper texture, lighting, or shadow on the background.
- Keep at least 160 px of clean pure magenta on all four outer edges.
- Keep at least 64 px of clean pure magenta between any two sprites. Rectangles must never
  touch, overlap, merge, share an edge, or cast anything into the magenta gap.

SCALE + EDGE QUALITY
- The sheet is drawn at 2x: one logical UI pixel = a solid 2x2 block of source pixels.
  (2x is required because this batch contains panels up to 800 px wide; at 8x they would
   exceed the 3840 px canvas.)
- Hard edges only. No anti-aliasing, no feathering, no soft blends, no sub-pixel gradients.
- Every sprite is a closed, axis-aligned rectangle with crisp 90-degree pixel corners.
  The outer outline is exactly 1 logical px (2 source px).
- No drop shadow, no outer glow, no halo outside any sprite rectangle. The only permitted
  shadow is a 1 logical px hard dark line INSIDE the rectangle (bottom/right bevel, sunken
  field edge, or the 1 px hard line under a menu bar). Never blurred, never soft.

PALETTE (Windows XP Luna; use only these values)
- dialog / panel face        #ECE9D8
- light face / field face    #F7F5EE
- highlight top-left         #FFFFFF
- light bevel                #F5F5EB
- mid shadow                 #ACA899
- dark outline               #626355
- pressed face               #D4D4C2
- disabled face              #D9D6C8
- disabled ink               #69675B
- selection blue             #316AC5
- title bar blue             3 flat bands: #0A3F9E -> #1466E0 -> #4A9BFF (no smooth blend)
- icon / glyph ink           #3B412F
- progress fill blue         2 flat bands: #4B86DD -> #2B63B8 (no smooth blend)
- badge warn                 #B8860B / face #FFF7D6
Do not introduce warm beige, olive, green, purple or cyan tints anywhere. No magenta tint
on any bevel or face.

NO TEXT / NO GLOSS / NO FOG
- Draw absolutely no letters, numbers, words, labels, captions, watermarks or rulers.
- The two badge sprites must have a completely EMPTY center: no digits drawn. A number is
  layered later in CSS.
- No glossy glass/plastic shine, no specular sweep, no white fog, no modern "Web 2.0" gloss.
  Highlights are exactly the 1 px bevel lines described above, nothing else.
- Triangles, dots, bars and ticks are allowed (they are shapes, not text).

SPRITE CONSTRUCTION
- Panels (menu plates, context menu, dialog, status bar, table) must be 9-slice friendly:
  same bevel on all four sides; the middle band perfectly uniform so the sprite can stretch.
- Menu plates: 1 px #626355 outer outline, 1 px white top/left highlight, 1 px #ACA899
  bottom/right shadow, flat cream face, and a 4 px inner padding margin of the same face
  color. Separators are SEPARATE 1 px sprites (see table), never painted into the plate.
- Dialog box: flat cream body with the 1 px bevel. Top-left and top-right corners have a
  2 logical px step clip (XP style); bottom corners stay square. The title bar is a
  SEPARATE sprite, 38 logical px tall, blue 3-band, with no text and no window buttons.
- Table: header plate 32 px tall with a 1 px bottom shadow line; normal row and zebra row
  are 24 px tall with a 1 px top grid line; vertical and horizontal grid lines are SEPARATE
  1 px sprites.
- Status bar: 24 px tall bar, flat light cream #F7F5EE with a 1 px #ACA899 top edge; the
  field cell is 18 px tall and SUNKEN (dark line on top/left, white line on bottom/right);
  the separator is a 2 px vertical sunken line, a SEPARATE sprite.
- Progress fill: 17 px tall, hard 2-band blue, 1 px white top highlight and 1 px #2B63B8
  bottom line. The 100% variant fills the full width edge to edge with square ends. The
  indeterminate variant uses hard 45-degree stripes made of 4 px blocks (no soft blur).
- Badges: plate with 1 px #B8860B outline, 2 px corner step, flat #FFF7D6 face, EMPTY center.
- Empty-state illustration: a neutral, non-photoreal empty box / folded carton built from
  flat cream planes, 1 px #626355 outline, no perspective gradient, no text, no shadow
  beyond the 1 px hard line.
- Disabled controls: same geometry as the enabled versions, face #D9D6C8, ink #69675B,
  bevels flattened to #ACA899, no blue and no color accent.
- Scrollbars: arrow plates are square, 1 px beveled; the triangle glyph is solid #3B412F
  (a shape, not text). Thumbs use the same bevel with a 3 px inner margin. Tracks are
  repeatable: uniform middle band, bevel caps only at both ends.
- Range track: a sunken 15 px groove, uniform horizontally so it can stretch. The thumb is
  a 19x33 raised plate with a 1 px bevel and three 1 px horizontal grip lines (lines, not text).

REFERENCE IMAGE RULES (only for the reference version)
- I provide ONE reference image of my existing XP pixel controls. Borrow ONLY:
  surface material, cream palette, bevel thickness/geometry, and pixel crispness.
- Do NOT copy the reference layout, canvas arrangement, sprite count, grouping, spacing,
  grid or ordering. The COORDINATE TABLE below overrides the reference completely.
- The reference background color must be IGNORED. Its key color may be #FF00FF or a
  different magenta; this output must use exactly #F51CF7.

COORDINATE TABLE - 44 sprites, source pixels on the 3840x2160 canvas.
Format: name | x | y | w | h | final 1x size after 1/2 downsample.

GROUP A - COLUMN 1 (status bar background, dialog, table) + COLUMN 2 TOP (menus):
statusbar-bg                | 160  | 160  | 1600 | 48  | 800x24
dialog-box                  | 160  | 272  | 1440 | 960 | 720x480
dialog-head                 | 160  | 1296 | 1440 | 76  | 720x38
tbl-head                    | 160  | 1436 | 1200 | 64  | 600x32
tbl-row                     | 160  | 1564 | 1200 | 48  | 600x24
tbl-row-alt                 | 160  | 1676 | 1200 | 48  | 600x24
tbl-grid-h                  | 160  | 1788 | 1200 | 2   | 600x1
menu-panel-bg               | 1880 | 160  | 660  | 420 | 330x210
menu-panel-sep              | 1880 | 644  | 660  | 2   | 330x1
app-menu-panel-bg           | 1880 | 710  | 420  | 280 | 210x140
context-menu-bg             | 1880 | 1054 | 292  | 192 | 146x96
context-menu-sep            | 1880 | 1310 | 292  | 2   | 146x1
tbl-grid-v                  | 1880 | 1376 | 2    | 48  | 1x24

GROUP B - VERTICAL SCROLLBAR (column 2, deliberately staggered, do not pack tighter):
scroll-v-track              | 1880 | 1488 | 44   | 342 | 22x171
scroll-v-thumb              | 1988 | 1488 | 46   | 102 | 23x51
scroll-v-thumb-hover        | 1988 | 1654 | 46   | 102 | 23x51
scroll-v-thumb-pressed      | 1988 | 1820 | 46   | 102 | 23x51
scroll-v-arrow-up           | 2100 | 1488 | 44   | 54  | 22x27
scroll-v-arrow-up-hover     | 2100 | 1606 | 44   | 54  | 22x27
scroll-v-arrow-up-pressed   | 2100 | 1724 | 44   | 54  | 22x27
scroll-v-arrow-down         | 2208 | 1488 | 44   | 54  | 22x27
scroll-v-arrow-down-hover   | 2208 | 1606 | 44   | 54  | 22x27
scroll-v-arrow-down-pressed | 2208 | 1724 | 44   | 54  | 22x27

GROUP C - COLUMN 2 BOTTOM (status bar cell + horizontal scrollbar):
statusbar-cell              | 2400 | 1488 | 240  | 36  | 120x18
statusbar-sep               | 2704 | 1488 | 4    | 36  | 2x18
scroll-h-track              | 2400 | 1600 | 142  | 42  | 71x21
scroll-h-thumb              | 2400 | 1706 | 88   | 42  | 44x21
scroll-h-thumb-hover        | 2400 | 1812 | 88   | 42  | 44x21
scroll-h-thumb-pressed      | 2400 | 1918 | 88   | 42  | 44x21
scroll-h-arrow-left         | 2640 | 1600 | 42   | 42  | 21x21
scroll-h-arrow-right        | 2746 | 1600 | 42   | 42  | 21x21

GROUP D - FORM CONTROLS + BADGES + EMPTY STATE (column 3):
select-disabled             | 3200 | 160  | 408  | 66  | 204x33
progress-fill               | 3200 | 290  | 400  | 34  | 200x17
progress-fill-100           | 3200 | 388  | 400  | 34  | 200x17
progress-fill-indeterminate | 3200 | 486  | 400  | 34  | 200x17
range-track                 | 3200 | 584  | 416  | 30  | 208x15
range-thumb                 | 3200 | 678  | 38   | 66  | 19x33
range-thumb-hover           | 3200 | 808  | 38   | 66  | 19x33
range-thumb-pressed         | 3200 | 938  | 38   | 66  | 19x33
empty-box                   | 3200 | 1068 | 96   | 96  | 48x48
badge-md                    | 3200 | 1228 | 56   | 38  | 28x19
badge-sm                    | 3200 | 1330 | 40   | 28  | 20x14
check-disabled              | 3200 | 1422 | 48   | 48  | 24x24
radio-disabled              | 3200 | 1534 | 48   | 48  | 24x24

CUTTING
- Cut each sprite at exactly x/y/w/h above, with zero extra padding.
- Downsample each crop by exactly 1/2 with an AREA/BOX filter (2x2 block average) to get the
  final 1x size in the last column. Do not use smooth interpolation.
- Keep the cut rectangles exactly as listed; do not trim, rotate, mirror or rescale any sprite.

NEGATIVE - do not do any of these:
no magenta inside any sprite, no magenta fringe, no purple halo, no anti-aliased edges,
no soft shadows, no outer glow, no smooth gradients inside cream faces, no glass/gloss,
no text/numbers/letters anywhere, no digits inside badges, no icons baked into menu plates,
no window buttons painted on the dialog head, no copied reference layout, no extra sprites,
no canvas border, no vignette, no watermark, no overlapping rectangles,
no tightening of the 64 px magenta gaps, no merged or touching sprites.
```

### 1.2 B 版（纯文字降级）

除下面这一段替换，其余正文与 A 版完全相同：

```text
REFERENCE IMAGE RULES
- No reference image is provided. Build the material and bevels from the PALETTE and
  SPRITE CONSTRUCTION sections only.
- The output must still use exactly #F51CF7 = RGB(245,28,247) as the single key color.
```

---

## 2. 分区坐标表（裁切用，中文核对版）

> 所有 `w/h` 都是 **2x 源像素**；最后一列是裁切后 1/2 降采样得到的 1x 素材尺寸。
> 三列/分区：左列 x=160 起（宽 1600），中列 x=1880 起（宽 1200），右列 x=3200 起（宽 480）。
> 四边留白 ≥160，元素间距 ≥64。

### 2.1 菜单 / 对话框 / 表格

| 文件名 | x | y | w | h | 1x 尺寸 | 用途 |
|---|---:|---:|---:|---:|---|---|
| `statusbar-bg.png` | 160 | 160 | 1600 | 48 | 800×24 | 状态栏底板（可横向拉伸） |
| `dialog-box.png` | 160 | 272 | 1440 | 960 | 720×480 | 对话框内容区底板 |
| `dialog-head.png` | 160 | 1296 | 1440 | 76 | 720×38 | 对话框标题栏 |
| `tbl-head.png` | 160 | 1436 | 1200 | 64 | 600×32 | 表头 |
| `tbl-row.png` | 160 | 1564 | 1200 | 48 | 600×24 | 普通数据行 |
| `tbl-row-alt.png` | 160 | 1676 | 1200 | 48 | 600×24 | 斑马行 |
| `tbl-grid-h.png` | 160 | 1788 | 1200 | 2 | 600×1 | 横向网格线 |
| `menu-panel-bg.png` | 1880 | 160 | 660 | 420 | 330×210 | 下拉菜单底板（含 4px 内边距） |
| `menu-panel-sep.png` | 1880 | 644 | 660 | 2 | 330×1 | 菜单分隔线 |
| `app-menu-panel-bg.png` | 1880 | 710 | 420 | 280 | 210×140 | 顶部菜单底板 |
| `context-menu-bg.png` | 1880 | 1054 | 292 | 192 | 146×96 | 右键菜单底板 |
| `context-menu-sep.png` | 1880 | 1310 | 292 | 2 | 146×1 | 右键菜单分隔线 |
| `tbl-grid-v.png` | 1880 | 1376 | 2 | 48 | 1×24 | 纵向网格线 |

### 2.2 竖向滚动条（上一张板完全没画，重点核对）

| 文件名 | x | y | w | h | 1x 尺寸 | 用途 |
|---|---:|---:|---:|---:|---|---|
| `scroll-v-track.png` | 1880 | 1488 | 44 | 342 | 22×171 | 竖向轨道（中间可 repeat） |
| `scroll-v-thumb.png` | 1988 | 1488 | 46 | 102 | 23×51 | 滑块常态 |
| `scroll-v-thumb-hover.png` | 1988 | 1654 | 46 | 102 | 23×51 | 滑块 hover |
| `scroll-v-thumb-pressed.png` | 1988 | 1820 | 46 | 102 | 23×51 | 滑块 pressed |
| `scroll-v-arrow-up.png` | 2100 | 1488 | 44 | 54 | 22×27 | 上箭头底板 |
| `scroll-v-arrow-up-hover.png` | 2100 | 1606 | 44 | 54 | 22×27 | 上箭头 hover |
| `scroll-v-arrow-up-pressed.png` | 2100 | 1724 | 44 | 54 | 22×27 | 上箭头 pressed |
| `scroll-v-arrow-down.png` | 2208 | 1488 | 44 | 54 | 22×27 | 下箭头底板 |
| `scroll-v-arrow-down-hover.png` | 2208 | 1606 | 44 | 54 | 22×27 | 下箭头 hover |
| `scroll-v-arrow-down-pressed.png` | 2208 | 1724 | 44 | 54 | 22×27 | 下箭头 pressed |

> 箭头三角直接画在底板上（三角是形状，不是文字）。现有旧素材是 28×27 再压到 22×27；本板要求直接出 22×27，避免二次压缩发虚。

### 2.3 状态栏 + 横向滚动条

| 文件名 | x | y | w | h | 1x 尺寸 | 用途 |
|---|---:|---:|---:|---:|---|---|
| `statusbar-cell.png` | 2400 | 1488 | 240 | 36 | 120×18 | 状态栏嵌槽格 |
| `statusbar-sep.png` | 2704 | 1488 | 4 | 36 | 2×18 | 状态栏分隔竖线 |
| `scroll-h-track.png` | 2400 | 1600 | 142 | 42 | 71×21 | 横向轨道（可 repeat-x） |
| `scroll-h-thumb.png` | 2400 | 1706 | 88 | 42 | 44×21 | 横向滑块常态 |
| `scroll-h-thumb-hover.png` | 2400 | 1812 | 88 | 42 | 44×21 | 横向滑块 hover |
| `scroll-h-thumb-pressed.png` | 2400 | 1918 | 88 | 42 | 44×21 | 横向滑块 pressed |
| `scroll-h-arrow-left.png` | 2640 | 1600 | 42 | 42 | 21×21 | 左箭头 |
| `scroll-h-arrow-right.png` | 2746 | 1600 | 42 | 42 | 21×21 | 右箭头 |

### 2.4 表单 / 进度 / 徽标 / 空态

| 文件名 | x | y | w | h | 1x 尺寸 | 用途 |
|---|---:|---:|---:|---:|---|---|
| `select-disabled.png` | 3200 | 160 | 408 | 66 | 204×33 | 禁用下拉框 |
| `progress-fill.png` | 3200 | 290 | 400 | 34 | 200×17 | 进度填充 |
| `progress-fill-100.png` | 3200 | 388 | 400 | 34 | 200×17 | 100% 满格 |
| `progress-fill-indeterminate.png` | 3200 | 486 | 400 | 34 | 200×17 | 不确定态斜纹 |
| `range-track.png` | 3200 | 584 | 416 | 30 | 208×15 | 横向滑块轨道 |
| `range-thumb.png` | 3200 | 678 | 38 | 66 | 19×33 | 横向滑块拇指常态 |
| `range-thumb-hover.png` | 3200 | 808 | 38 | 66 | 19×33 | 拇指 hover |
| `range-thumb-pressed.png` | 3200 | 938 | 38 | 66 | 19×33 | 拇指 pressed |
| `empty-box.png` | 3200 | 1068 | 96 | 96 | 48×48 | 空态插图（中性空盒） |
| `badge-md.png` | 3200 | 1228 | 56 | 38 | 28×19 | 版本徽标底（数字位留空） |
| `badge-sm.png` | 3200 | 1330 | 40 | 28 | 20×14 | 小徽标底（数字位留空） |
| `check-disabled.png` | 3200 | 1422 | 48 | 48 | 24×24 | 禁用复选框 |
| `radio-disabled.png` | 3200 | 1534 | 48 | 48 | 24×24 | 禁用单选框 |

---

## 3. 尺寸是从哪量的（CSS 实测来源）

> 弹性面板（菜单 / 对话框 / 表格 / 状态栏）的「高度」由内容决定，表中给的是九宫格模板高度；宽度取 CSS 实测值。
> 所有固定控件尺寸（复选 24、单选 24、下拉 33、滚动条 22/21、range 15/33、徽标 14/19）都是直接量出来的。

| 素材 | 实测值 | 来源 |
|---|---|---|
| 菜单底板 | `width:330px`，`padding:8px 10px`；高度 `max-height:72vh`（弹性） | `style.css:183-197` |
| 顶部菜单底板 | `min-width:210px`，`padding:4px`，条目 `min-height:24px` | `assets/xp-ui/xp-ui-app.css:633-652` |
| 右键菜单底板 | `min-width:146px`，`padding:2px`；条目 `padding:5px 12px`，字号 12 | `style.css:520-540` |
| 对话框底板 | `720px`（`gw-prof-box`）/ `1180px`（`am-modal-box`）/ `1320px`（`lw-modal-box`）；高度弹性 | `style.css:6624-6628`、`4322-4331`、`2894-2905` |
| 对话框标题栏 | 38px（`titlebar.png` 高度） | `assets/xp-ui/xp-ui-app.css:1523+`；`style.css:2906-2912` |
| 表头 | `--lw-table-head-height:32px`；通用表头无固定高 | `style.css:1517`、`1437-1443` |
| 表格行 | `padding:3px 7px` + `font:11px/1.6` → 24px | `style.css:1447-1457` |
| 网格线 | 单元格 `border-right:1px` / 行 `border-top:1px` | `style.css:1451`、`1457` |
| 状态栏 | `height:24px`，`padding:0 6px` | `assets/xp-ui/xp-ui-app.css:1178-1195` |
| 状态栏格 | `height:18px`，`padding:0 6px`，`border:1px` | `assets/xp-ui/xp-ui-app.css:1197-1209` |
| 分隔竖线 | 由 `sb-cell` 的 1px 双色边框推导，独立件取 2px 宽 | 同上 |
| 进度填充 | 框 227×21，内条 `top:2px bottom:2px` → 17px | `assets/xp-ui/xp-ui.css:237-256` |
| 徽标（大） | `padding:2px 6px` + `font:11px/1.4` → 19px | `style.css:172-180` |
| 徽标（小） | `padding:0 3px` + `font-size:10px` + 1px 边框 → 14px | `style.css:1589-1595` |
| 复选框 / 单选 | 24×24 | `assets/xp-ui/xp-ui-app.css:242-260` |
| 下拉框 | 204×33（`select.png` 同尺寸） | `assets/xp-ui/xp-ui-app.css:205-231`；`manifest.json` |
| 竖向滚动条 | 宽 22；箭头 22×27；滑块 23×51；轨道 22×171 | `assets/xp-ui/xp-ui-app.css:367-453` |
| 横向滚动条 | 高 21；轨道 71×21；滑块 44×21；箭头暂无（当前 `display:none`） | `assets/xp-ui/xp-ui-app.css:455-459` |
| 横向滑块 | 轨道 15px（`track.png` 208×15）；拇指 19×33 | `assets/xp-ui/xp-ui-app.css:461-487`；`manifest.json` |
| 空态插图 | **无既有尺寸**（空态目前只有文字行）。取 48×48 作为唯一新增基准 | `style.css:576`（`.task-empty` 仅 padding/字号） |

> 唯一「新增基准」是空态插图：现有 DOM 里没有图标，48×48 是给空态行高（约 18px）的 2.5 倍档，属于新定尺寸，不是从旧组件量的。

---

## 4. 「垫参考图」怎么垫（不改变键色）

### 4.1 用哪张

优先用上一轮已经切好的单件 PNG 拼一张参考条，材质最干净：

- `assets/xp-ui/btn-normal.png`（按钮斜面）
- `assets/xp-ui/input.png`（输入框凹槽）
- `assets/xp-ui/select.png` + `select-arrow.png`（下拉）
- `assets/xp-ui/check-off.png`（复选）
- `assets/xp-ui/progress-frame.png`（进度框）
- `assets/xp-ui/scroll-v-thumb.png`（滚动块）

也可以直接用原始板：`02-塔科夫/ui图标/xp风格ui/XP-Style Button States — Textle_952bcd15.png`（上一张成功板就是垫它）。

把参考图放在提示词前面，并在提示词里保留 A 版的 `REFERENCE IMAGE RULES` 段。

### 4.2 三条硬规则

1. **只借四样**：表面材质、奶油色板、倒角厚度与几何、像素锐度。不要借布局、数量、分组、间距、顺序。
2. **参考图的键色一律作废**。四张原始板的洋红并不相同（实测有 `245,28,247`、`250,5,249` 等），本板只认 `#F51CF7`。
3. **坐标表优先于参考图**。参考图上有 12 件也好、25 件也好，本板只画表里的 44 件，位置严格按表。

### 4.3 垫图时容易翻车的点

- 模型会把参考图的洋红「顺手」带过来 → 生成后先跑第 5 节的键色自查。
- 模型会复制参考图的水印/分割线 → 在 NEGATIVE 里已写死 `no watermark / no copied layout`。
- 模型会把参考图的阴影做成柔边 → 明确写了只许 1px 硬线，且在矩形内。

---

## 5. 生成后键色漂移怎么自查（量化）

### 5.1 目标值与容差

| 指标 | 合格线 | 说明 |
|---|---|---|
| 四边均值 μ | `R=245±4`、`G=28±4`、`B=247±4` | 与实测键色 `(245,28,247)` 比 |
| 单通道标准差 σ | `≤3`；G 通道允许 `≤5` | G 基数只有 28，相对波动天然偏大；上一轮实测 max std 2.63 |
| 四边条内像素 | ≥99% 与 K 的欧氏距离 `≤10` | 边条应几乎全是纯底色 |
| 单像素最大偏离 | `≤25` | 超过 25 的点只允许出现在元素外沿 1–2px，抠图会腐蚀掉 |
| 抠图后素材内部 | 与 K 距离 `≤12` 的像素数 = **0** | 素材内不许残留洋红 |
| 紫边 | 色相 280°–320° 且饱和度 >0.2 的像素数 = **0** | 防洋红混色 |

> 上一轮实测基线：`245,28,247` / 最大 std `2.63` / 绝对波动 `≤10` / 抠图容差 `25` → 洋红残留 `0`。
> 本板沿用同一口径；只要均值漂移超过上表，就按 5.3 处理。

### 5.2 采样与计算

`tools/xp_ui_slice.py` 的 `measure_key_color()` 就是从四边各取 20px 条带求均值。手动自查等价做法：

```python
from PIL import Image
import numpy as np

im = Image.open("board.png").convert("RGB")
a  = np.asarray(im, dtype=np.float32)
K  = np.array([245, 28, 247], dtype=np.float32)

strips = np.concatenate([
    a[:20, :, :].reshape(-1, 3),    # 上
    a[-20:, :, :].reshape(-1, 3),   # 下
    a[:, :20, :].reshape(-1, 3),    # 左
    a[:, -20:, :].reshape(-1, 3),   # 右
])
mu, sd = strips.mean(0), strips.std(0)
d = np.linalg.norm(strips - K, axis=1)

print("mean", mu.round(2), "std", sd.round(2))
print("dist(mean,K)", round(float(np.linalg.norm(mu - K)), 2))
print("within 10:", round(float((d <= 10).mean()), 4))
print("max dev:", round(float(d.max()), 2))
```

判读：

- `dist(mean,K) ≤ 7`（等价于三通道各 ±4）且 `std ≤3`（G ≤5）→ **合格**。
- `within 10 ≥ 0.99` → 底色干净；低于 0.99 说明有噪点/渐变。
- `max dev ≤ 25` → 可以直接进 `tools/xp_ui_slice.py`（默认容差 25）。
- 裁完后对每张 1x PNG 再查一次「内部 ≤12 的洋红像素」，应为 0。

### 5.3 漂移了怎么办

| 现象 | 判断 | 处理 |
|---|---|---|
| 整体均匀偏移（如 `250,40,250`） | 模型把键色当成 `#FF00FF` 的近似 | **重新生成**；不要用 PS 调色（会把元素边缘一起改掉） |
| 只有角落偏紫 | 背景光照/渐晕 | 重新生成，或在提示词里加重 `flat / no vignette` |
| 元素边缘带紫边 | 抗锯齿混色 | 靠 `tools/xp_ui_slice.py` 的 2px alpha 腐蚀 + 洋红去污；若仍残留，裁切时向内收 1px |
| 单像素噪声多、std >3 | 纹理/噪点 | 重新生成，不要提高抠图容差（>25 会吃进元素边缘） |
| 均值合格但素材内部有洋红 | 元素本身带洋红 | 该件重画；不要用色相替换硬修 |

**不要做的事**：为了迁就漂移把抠图容差从 25 调到 40+，或给素材套 CSS 滤镜去紫边。前者会吃掉 1px 斜面，后者会破坏 1px 硬边。

---

## 6. 生成后接入映射（供下一批替换用）

| 素材 | 接到哪 |
|---|---|
| `menu-panel-bg` / `app-menu-panel-bg` / `context-menu-bg` + sep | `.menu-panel`、`.app-menu-panel`、`.task-context-menu`（九宫格 + 独立分隔线） |
| `dialog-box` / `dialog-head` | `.lw-modal-box` / `.am-modal-box` / `.gw-prof-box` + `*-head` |
| `tbl-head` / `tbl-row` / `tbl-row-alt` / `tbl-grid-v/h` | `.tbl-head`、`.tbl-row`、`.tbl-cell` 边框线 |
| `statusbar-bg` / `statusbar-cell` / `statusbar-sep` | `#app-statusbar`、`.sb-cell` |
| `progress-fill` / `-100` / `-indeterminate` | `.gw-bar-fill`、`.xp-progress__bar` |
| `badge-sm` / `badge-md` | `.lw-badge`、`.build-rev`（数字继续用文字层） |
| `empty-box` | `.task-empty` / `.tbl-empty` / `.gw-empty` 的 `::before` |
| `check-disabled` / `radio-disabled` / `select-disabled` | `input:disabled`、`select:disabled` |
| `scroll-h-*` / `scroll-v-*` | `::-webkit-scrollbar-*`（横向箭头当前 `display:none`，接入时打开） |
| `range-track` / `range-thumb*` | `input[type=range]::-webkit-slider-runnable-track` / `-thumb` |

> 接入阶段仍遵守既有约束：只改 CSS、不动 DOM/交互/数据流、`?mini=1` 零影响、间距/字号/对比度回到 `docs/ui-component-spec.md`。
