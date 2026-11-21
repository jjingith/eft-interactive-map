# R18.1 测试报告

日期：2026-10-24 · 环境：Windows / Python 3.14（`C:\Python314\python.exe`）/ Node 22 / Chrome（headless=new, CDP）
构建标记：`R18.1`（`app.js` 的 `AM_BUILD`，逐发模拟器顶部执行条可见）

---

## 1. 命令与结果

| 命令 | 结果 |
|---|---|
| `python -m pytest -q`（**修改前基线**） | **853 passed, 1 skipped**（48.84 s） |
| `python -m pytest -q`（R18.1 全部完成后） | **864 passed, 1 skipped**（52.80 s） |
| `node --check app.js` / `node --check combat_sim.js` | exit 0 / exit 0 |
| `python tools/r181_accept.py --port 8801` | 34 张截图 · 0 控制台错误 · 0 外部请求 |

基线输出原件：`_baseline_pytest.txt`；完成后输出原件：`_final_pytest.txt`。
**无删除 / 跳过 / 弱化既有测试**；新增 11 个测试（`tests/test_r18_1_round.py`）。

### 1.1 两个既有测试的等价迁移（说明）

| 测试 | 原断言 | 迁移后 | 理由 |
|---|---|---|---|
| `test_r17_fixes.py::test_ui_ammo_list_reload_hooks` | `AM_BUILD = "R18"` 硬编码 + `v=r18` | 用正则取出 `AM_BUILD` 值，断言 `index.html` 的 `?v=<值小写>` 存在 | 原来每轮升级都要改测试。真正的不变量是「构建标记与资源版本参数同步」，迁移后断言强度不变而且不再随轮次失效 |
| `test_r10_armor_table.py::test_r20_badges_and_balaclava_placeholder_static` | 面部空槽必须有 `BALACLAVA_ITEM_ID` + `.lw-sil-face` 灰度特例 | 面部必须有 `assets/ui/placeholders/face.png`；`silKey` 含 `face` 映射；`manifest` 里 face 的来源装备仍是巴拉克拉瓦头套；CSS 不得再有 `filter: grayscale(1)` | R18.1 把面部并入统一剪影（素材仍是巴拉克拉瓦头套的真实轮廓）。不变的是「面部空槽必须有一张真实存在的本地占位图形」 |

---

## 2. 真实浏览器验收

工具：`tools/r181_accept.py`（CDP，纯标准库）。所有结论取自浏览器 **computed style / DOM 实测值 /
canvas 像素统计**，不是"看起来没问题"。原始数据：`_accept.json`。
两个视口各自独立跑完整流程：**1920×1080** 与 **1264×705**。

### 2.1 空槽剪影（11 个槽位 × 2 视口）

全部加载成功（`complete && naturalWidth > 0`），`src` 指向 `assets/ui/placeholders/`，
`mix-blend-mode: multiply` 生效：

| 槽位 | 文件 | naturalWidth |
|---|---|---|
| helmet | helmet.png | 76 |
| glasses / headphones / face | 各自 png | 63 |
| armor / rig / backpack / melee | 各自 png | 106 |
| primary1 / primary2 | primary.png（同一文件） | 260 |
| holster | holster.png | 152 |

浏览器内 canvas 像素统计（证明是"白底黑图形"而不是透明图或黑块）：

| 槽位 | 白 | 黑 | 中间色 |
|---|---|---|---|
| helmet | 44.3% | 49.5% | 6.2% |
| glasses | 82.6% | 13.2% | 4.2% |
| headphones | 64.5% | 25.3% | 10.1% |
| face | 57.9% | 36.9% | 5.2% |
| armor | 51.2% | 45.4% | 3.5% |
| rig | 51.7% | 42.0% | 6.4% |
| primary1/2 | 81.3% | 13.5% | 5.3% |
| backpack | 60.5% | 36.4% | 3.0% |
| holster | 68.9% | 25.0% | 6.1% |
| melee | 87.6% | 10.0% | 2.3% |

（中间色是 4× 超采样缩下来的抗锯齿边缘，均 <11%。四角像素离线校验同样为纯白，见 2.6。）

### 2.2 装备选中 / 卸下

| 步骤 | 实测 |
|---|---|
| 空槽 | 11 个槽位全部显示 `lw-sil`，无 `lw-cell-icon` |
| 点第一行装 Altyn 头盔 | helmet 槽：`lw-sil` 消失，`lw-cell-icon` = `assets/icons-items/5aa7e276e5b5b000171d0647.webp`（**真实物品图标**，不是剪影）；其余 10 槽不变 |
| 点节点上的 × 卸下 | helmet 槽恢复 `assets/ui/placeholders/helmet.png`，图标消失 |
| 再装一件护甲（6B5-15 Uley） | armor 槽切到真实物品图标 `5fd4c474dd870108a754b241.webp` |

### 2.3 配装悬停提示

| 锚点 | 首行文本 | 首行颜色 | 背景 | 对比度 | 是否被裁切 |
|---|---|---|---|---|---|
| `.lw-src`（来源区块） | `Ragman LL4 · 解锁兑换配方` | `rgb(0,0,0)` | `rgb(236,233,216)` | **17.21:1** | 否（rect 完全在视口内） |
| `.lw-plate-cell`（插板位） | `前插板：未安装（本位置合法插板 19 件）` | `rgb(0,0,0)` | `rgb(236,233,216)` | **17.21:1** | 否 |

正文行 `rgb(35,35,35)` → 12.88:1。两个锚点在 1920 与 1264 下都正常弹出且完整可见。

### 2.4 BALLISTICS graph

| 项 | 实测 |
|---|---|
| 坐标轴刻度（14 个 text 节点） | `fill = rgb(74,74,74)` |
| 轴标签（2 个） | `fill = rgb(35,35,35)` |
| 绘图区 | `fill = rgb(255,255,255)` |
| 图例 `.am-graph-lg` | `rgb(35,35,35)` |
| 说明 `.am-graph-note` | `rgb(35,35,35)` |
| 悬停提示·弹药名 | `rgb(0,0,0)` on `rgb(236,233,216)` → **17.21:1** |
| 悬停提示·次级信息 | `rgb(74,74,74)` → **7.26:1** |

### 2.5 弹药详情弹窗标题栏（4 种口径/分类组合）

| 探测 | 标题 | 标题栏后半段 | 颜色 | 对比度（蓝渐变中段） |
|---|---|---|---|---|
| 5.45 | 5.45x39毫米 7N39"针刺" | `5.45x39 · 子弹 · RIFLE ROUNDS` | `rgb(255,255,255)` | **5.72:1** |
| 7.62 | 7.62x25毫米 TT M995 | `7.62x25 · 子弹 · PISTOL/SMG` | `rgb(255,255,255)` | 5.72:1 |
| .357 | .357 Magnum FMJ | `.357 · 子弹 · PISTOL/SMG` | `rgb(255,255,255)` | 5.72:1 |
| 12/70 | 12/70 AP-20 穿甲独头弹 | `12g · 子弹 · SHOTGUN ROUNDS` | `rgb(255,255,255)` | 5.72:1 |

标题栏仍是 Luna 蓝渐变 `linear-gradient(rgb(20,102,224) 0%, rgb(10,63,158) 62%, rgb(8,50,124) 100%)`；
标题色 `rgb(255,255,255)`。弹窗结构与关闭行为未变（每轮都用 `.am-modal-x` 正常关闭）。

### 2.6 护甲 / 插板分组（DOM 实测）

护甲下拉：`total = 109`（108 件 + "无护甲"），`looseOptions = 1`（只有"无护甲"在 optgroup 之外），
分组顺序（两个视口一致）：

```
IV · 陶瓷 · 内衬 1      IV · 钛合金 · 内衬 1    IV · 复合材料 · 内衬 2
III · 钛合金 · 内衬 1   III · 装甲钢 · 内衬 2   III · 铝合金 · 内衬 1   III · 芳纶 · 内衬 52
II · 钛合金 · 内衬 1    II · 芳纶 · 内衬 37
无内衬 10
```

插板下拉（选中 Ferro Concepts FCPC V5 后，`zone = Front_plate`）：`total = 20`，
`looseOptions = 1`（"未安装"），分组顺序：

```
VI · 陶瓷 1   VI · 钛合金 1   VI · 装甲钢 1   VI · 超高分子量聚乙烯 2   VI · 复合材料 1
V · 陶瓷 1    V · 钛合金 1    V · 超高分子量聚乙烯 1   V · 复合材料 1
IV · 陶瓷 1   IV · 钛合金 1   IV · 装甲钢 1   IV · 超高分子量聚乙烯 1   IV · 复合材料 1   IV · 铝合金 1
III · 超高分子量聚乙烯 1   III · 复合材料 1
I · 超高分子量聚乙烯 1
```

- 等级降序、同级材质固定序、`无内衬` 收尾，均符合预期。
- 数据里没有 `I · 芳纶 · 内衬`、没有 II 级插板 → **没有生成对应空组**。
- `内衬数据未知` / `等级或材质缺失` 两个未知组当前为空（108 件护甲、38 件插板全部字段齐全）。

### 2.7 Boss 装备池兼容（Tagilla）

```
目标类型 → Boss → Tagilla（总血 1220），Boss 列表 17 项
护甲下拉：armorTotal = 3（2 件 verified 白名单 + "无护甲"），2 个组
插板下拉：plateTotal = 2（1 块插板 + "未安装"），1 个组（VI · 钛合金）
pool-note：Tagilla 装备池（verified 白名单）：护甲 2 项 / 头盔 3 项；
           插板型号 wiki 未单列（missing）→ 按护甲插板位可选（estimated）
```

分组**没有**把全局 20 组插板放出来，Boss 白名单与护甲插板位兼容集合仍然生效。

### 2.8 全局健康度

| 项 | 1920×1080 | 1264×705 |
|---|---|---|
| 控制台错误（console.error / exception / log error） | 0 | 0 |
| 外部网络请求（非 `127.0.0.1:8801`） | 0 | 0 |
| 横向溢出（`scrollWidth > clientWidth`） | false | false |
| 页面内构建标记 | `R18.1 构建 · compat 加载中 · …` | 同左 |

---

## 3. 截图清单（`docs/ui-windows-xp/r18.1/`）

每个视口 17 张，两张共 34 张：

| 文件 | 验证的具体问题 |
|---|---|
| `{vp}-01-loadout-empty.png` | 全部空槽剪影：白底黑剪影、槽位名可读、卡片比例 |
| `{vp}-02-loadout-equipped.png` | 装备选中后切换为真实物品图标（头盔 / 护甲），其余槽位仍是剪影 |
| `{vp}-03-loadout-tooltip.png` | 来源区块悬停提示：标题黑字可读、不被裁切 |
| `{vp}-03b-loadout-armor.png` | 护甲槽装入后的真实图标 + 插板位出现 |
| `{vp}-03c-loadout-tip-plate.png` | 插板位悬停提示：首行「前插板：未安装…」黑字可读 |
| `{vp}-04-loadout-removed.png` | 卸下后恢复对应空槽剪影 |
| `{vp}-05-ammo-graph.png` | BALLISTICS graph 坐标轴 / 图例 / 绘图区在浅底下的对比度 |
| `{vp}-06-ammo-graph-tip.png` | 散点悬停提示里的弹药名称与次级信息可读 |
| `{vp}-07-ammo-detail-1..4.png` | 四种口径/分类的详情弹窗标题栏完整文字（含长名称） |
| `{vp}-08-sim-armor-groups.png` | 模拟器护甲选择器（未展开） |
| `{vp}-09-sim-plate-groups.png` | 插板位下拉与内衬 chips |
| `{vp}-09b-armor-open.png` | 护甲分组结构（**临时把 `size` 撑开取证的截图，拍完即还原，不改业务状态**） |
| `{vp}-09c-plate-open.png` | 插板分组结构（同上） |
| `{vp}-10-sim-boss.png` | Tagilla 装备池约束下的护甲 / 插板候选 |

辅助证据：

- `_placeholder-contact-sheet.png`：10 张剪影的构建期联系表（白底黑图形总览）。
- `_accept.json`：本次验收的全部原始实测值（含每个槽位像素占比、每个文本节点的 computed color、
  每次提示的矩形与对比度、两次视口的完整 DOM 结果）。
- `_baseline_pytest.txt` / `_final_pytest.txt`：修改前后全量测试原始输出。

---

## 4. 未覆盖 / 已知限制

1. **原生 `<select>` 的展开列表无法直接截图**：`-09b/-09c` 是临时把 `size` 属性撑到 14 拍下的，
   只用于展示 `optgroup` 结构，拍完立即还原。真实交互仍是原生下拉。
2. **剪影的画布比例绑定卡片内框**：本轮按当前 `style.css` 的网格轨道出图（76/106/260/152 等）。
   若以后调整卡片尺寸，需要重跑 `tools/build_slot_placeholders.py` 同步画布，否则白底会露边。
3. **`_src` 素材需构建期联网下载**：仓库里已带 10 张（296 KB），离线可直接重建；
   删除后需 `--fetch` 走代理重新获取。
4. **护甲搜索框与分组并存**：搜索是过滤选项，分组在过滤后进行；两者叠加时组内可能只剩 1 项，
   这是预期行为（不是空组）。
5. **`内衬数据未知` / `等级或材质缺失` 组当前无样本**：分组逻辑已实现并有单元测试覆盖标签生成，
   但真实数据里没有触发样本，因此没有对应截图。
