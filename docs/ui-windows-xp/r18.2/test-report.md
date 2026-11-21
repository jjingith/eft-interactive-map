# R18.2 测试报告

日期：2026-10-24 · 环境：Windows / Python 3.14.3（`C:\Python314\python.exe`）/ Chrome（headless=new, CDP）
构建标记：`R18.2`

---

## 1. 测试命令与结果

| 命令 | 结果 |
|---|---|
| `python -m pytest -q`（R18.1 完成后基线） | **864 passed, 1 skipped** |
| `python -m pytest -q`（R18.2 完成后） | **877 passed, 1 skipped**（54.79 s） |
| `node --check app.js` | exit 0 |
| `python tools/build_gear_icons.py` | 候选 863 · 生成 859 · 缺失 4 |
| `python tools/build_slot_placeholders.py --fetch` | 10/10 生成，全部走 Alpha 主路径 |
| `python tools/r182_accept.py` | 16 张截图 · 0 控制台错误 · 0 外部请求 |

原始输出：`_pytest.txt`、`_accept.json`。
新增 13 个测试（`tests/test_r18_2_round.py`），**无删除 / 跳过 / 弱化既有测试**。

### 1.1 一处既有测试的等价迁移

`tests/test_r18_1_round.py::test_placeholder_pngs_are_black_on_white` 原断言
`manifest["round"] == "R18.1"`。R18.2 复用了同一份构建清单并推进了轮次字段，
断言语义迁移为「属于 R18 系列且格式合法」（`R18\.\d+`），
具体轮次由当轮测试（`test_r18_2_round.py`）单独断言 `== "R18.2"`。断言强度不变。

---

## 2. 产物层验证（离线可复现）

### 2.1 白底图标（859 张）

| 检查项 | 结果 |
|---|---|
| 目录 / 清单 | `assets/icons-items-white/` 859 个 PNG + `manifest.json` |
| 尺寸 | 全部 64×64 |
| 色彩模式 | 全部 `RGBA`（透明底） |
| 四角 alpha | 抽样 24 件，四角 alpha 均为 **0**（背景真被去掉，不是白底盖着） |
| 主体颜色层次 | 每件主体内部量化色 ≥ 3 种（是真贴图，不是涂色块） |
| 主体占比 | 1.2%–92%，与清单记录误差 < 6% |
| 主体亮度 | 抽样与原始 webp 对比，主体中位亮度不高于原图中位 + 60（未被「漂白」） |
| 清单完整性 | 863 候选 = 859 生成 + 4 缺失，每条缺失都有原因 |

### 2.2 枪械剪影（2 张）

| 指标 | `primary.png`（260×106） | `holster.png`（152×106） |
|---|---|---|
| 横向跨度 | 88.1%（x=15..243） | 85.5%（x=11..140） |
| 左右两端是否有墨迹 | 有（枪口 / 枪托托底） | 有（套筒前 / 握把） |
| 被包围的镂空面积 | 71 px（扳机护圈） | 211 px（扳机护圈） |
| 右端 25% 区域墨迹占比 | 14.1%（枪托） | 38.6%（握把） |
| 墨迹占比 | 17.8% | 36.5% |
| 四角 | 纯白 | 纯白 |
| 素材来源 | 预设 `5c0c1ce8…`（完整装配） | 预设 `5a88acfb…`（完整装配） |

> 判据说明：单看「跨度」无法区分「完整枪」和「被拉满画布的部件」，
> 所以另外加了「两端都有墨迹」「扳机护圈镂空存在」「右端有体积部件」三条几何特征。
> 最终是否「一眼看出是完整 AK / Glock」仍以截图为证（见 §3）。

---

## 3. 真实浏览器验收（`tools/r182_accept.py`，CDP）

视口 1600×900；开测前先点掉配置里已有的装备，保证从空槽状态开始
（`clearedNodes = 0`）。

### 3.1 右侧列表 10 个分类的图标

| 分类 | 取样图标数 | 加载成功 | 指向 `icons-items-white` | 容器背景 |
|---|---|---|---|---|
| 头盔 | 6 | 6 | 6 | `rgb(255,255,255)` |
| 护甲 | 6 | 6 | 6 | 同上 |
| 胸挂 | 6 | 6 | 6 | 同上 |
| 背包 | 6 | 6 | 6 | 同上 |
| 耳机 | 6 | 6 | 6 | 同上 |
| 眼镜 | 6 | 6 | 6 | 同上 |
| 面部 | 6 | 6 | 6 | 同上 |
| 主武器 1 | 3 | 3 | 3 | 同上 |
| 手枪 | 1 | 1 | 1 | 同上 |
| 近战武器 | 6 | 5 | 5 | 同上 |

- 近战那 1 项是上游缺图的 `6aa948d1…`（见 change-log §1.4），走两级回退后隐藏 `<img>`，
  表格里留一个白底空格子，不出现浏览器破损图标。
- 浏览器内 canvas 像素校验（从实际加载的 PNG 读）：四角 alpha 全为 0，
  透明像素占 41%–87%，不透明像素 10%–55% —— 是「透明底 + 原色物品」，不是深色方块。

### 3.2 行状态

| 状态 | 行背景 | 图标容器背景 |
|---|---|---|
| 普通行 | `rgb(255,255,255)` | `rgb(255,255,255)` |
| 悬停行 | `rgb(234,243,255)` | `rgb(255,255,255)` |
| 选中行（`aria-selected=true`） | `rgb(49,106,197)` | `rgb(255,255,255)` |

三种状态下图标区都是纯白，符合「图标区域统一白底」的要求；行本身的配色未改。

### 3.3 左侧空槽剪影（11 个槽位）

全部加载成功，`src` 指向 `assets/ui/placeholders/`：

```
helmet → helmet.png      glasses → glasses.png       headphones → headphones.png
face → face.png          armor → armor.png           rig → rig.png
primary1 → primary.png   primary2 → primary.png      backpack → backpack.png
holster → holster.png    melee → melee.png
```

### 3.4 枪械装 / 卸切换

| 步骤 | `lw-sil` | `lw-cell-icon` |
|---|---|---|
| 起始（已清空） | `primary.png` | — |
| 点第一行装上 | — | `5bfd297f0db834001a669119.png`（真实枪械物品图标） |
| 再点该行卸下 | `primary.png`（完整 AK 剪影恢复） | — |

> 枪械槽点行的语义是 **toggle**（点已装的那一行 = 卸下），验收脚本按当前状态分叉，
> 不假设起始为空。这条在 R18.1 的脚本里没体现，本轮修正。

### 3.5 布局与健康度

| 项 | 结果 |
|---|---|
| 横向溢出（`scrollWidth > clientWidth`） | false |
| 控制台错误 | 0 |
| 外部网络请求 | 0 |
| 页面构建标记 | `R18.2 构建 · compat 加载中 · …` |

---

## 4. 截图清单（`docs/ui-windows-xp/r18.2/`）

| 文件 | 验证的具体问题 |
|---|---|
| `before-after-icons.png` | 五类代表物品：原 webp（深色底） vs 白底 PNG，均按浏览器实际 30px 显示尺寸贴在白色行底上 |
| `before-after-gun-source.png` | **根因证据**：AK-74 本体 base-image（无枪托） vs 预设 base-image（完整） |
| `before-after-gun-silhouette.png` | **改前/改后剪影**：R18.1 的「机匣部件」 vs R18.2 的完整 AK-74 |
| `after-01-left-silhouettes.png` | 11 个空槽剪影（主武器 1/2 为完整 AK-74，手枪为完整 Glock 17） |
| `after-02-list-helmet.png` 等 10 张 | 右侧列表各分类的图标白底效果 |
| `after-03-hover-row.png` | 悬停行的图标背景 |
| `after-04-selected-row.png` | 选中（蓝底）行的图标背景 |
| `after-05-gun-slot-empty.png` | 主武器 1 空槽的完整 AK-74 剪影 |
| `after-06-gun-equipped.png` | 装上真实枪械后切为物品图标 |
| `after-07-gun-removed.png` | 卸下后恢复黑色完整剪影 |
| `_accept.json` | 本次验收的全部原始实测值 |

对照图由 `tools/r182_compare.py` 生成，可复现：
旧剪影是用**旧的源图 + 旧的填洞参数（4%）**重新渲染得到的，不是手工绘制或修图。

---

## 5. 未覆盖 / 已知限制

1. **4 件上游缺图物品**（HK 416A5 RAL 8000、FN P90 灾厄、杀人鲸匕首、NKVD 芬卡刀）：
   上游 `-base-image.webp` 返回 404，本地 `icons-items` 也没有对应图标。
   页面显示为白底空格子（不再显示破损图）。属于本地数据快照之后新增的物品，
   需要等上游出图后重跑 `tools/build_gear_icons.py`。
2. **图标视觉尺寸略小**：新 PNG 在 64px 画布内留了 4px 边距（主体 56px），
   缩到 30px 显示时比原来满幅的深色方块小约 12%。换来的是不贴边、不被裁切的观感，
   卡片与表格的网格尺寸完全未动。
3. **配装工作台之外的页面仍用原 webp**：弹药表、弹药图标、弹道散点图、配枪页
   沿用原 64px 带底色图（本轮范围只到配装）。若以后要统一，同一套
   `assets/icons-items-white/` 可直接复用，只需把对应 `itemIconUrl` 换掉。
4. **源图缓存 18 MB 不进仓库**：`build-cache/gear-icons-src/` 已在 `.gitignore` 里；
   仓库里只带成品 6.5 MB。重建需要一次联网（构建期，走代理）。
