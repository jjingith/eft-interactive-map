# R70 台账：关于面板瘦身 / 弹药标签中文化 / 弹道副标题

host=HOMONAS user=MASTERJJ at=2026-11-04 22:34 +08:00

## 1. 结论

三项全部完成，pytest 全绿，dist 与三件套已重建；本台账记录的是 R70 版本
（`R19.35-e0fd7013`）。R71（双击 exe 入口修复）另出包，最终安装包以 R71 台账为准。

## 2. 改动文件

| 文件 | 改动 |
| --- | --- |
| `index.html` | 关于面板重写为紧凑链接清单；弹药 5 个标签的中文 `title` 同步；新增 `.am-head` 标题 + 副标题；资源版本串 `r19.34 → r19.35` |
| `data/i18n/ui-zh.json` | 4 条弹药标签中文改名 |
| `style.css` | 关于面板 `.about-links/.about-row/.about-meta` 样式；`.am-head/.am-title/.am-subtitle` 布局 |
| `theme-windows-xp.css` | 标题 Luna 蓝、副标题灰蓝、分隔线颜色 |
| `app.js` | `AM_BUILD = "R19.35"`；`renderMetaLine()` 数据版本统计压缩为单行 |
| `tools/serve.py` | rev `R19.34-` → `R19.35-` |
| `tests/test_r32_about.py` | 关于面板断言同步为新链接清单（保留全部许可署名，未放宽） |
| `tests/test_r40_armor_effdur.py` | 价格说明逐字文本改为新单行；面板截取改用 `<!-- R19.11` 边界 |
| `tests/test_r42_live_prices.py` | TTL 用例改以真实当前时间播种，修复 21:10 后必然过期的时钟依赖 |

## 3. 关于面板：改动前后

| 指标 | R69（改前） | R70（改后） |
| --- | --- | --- |
| 1440×900 面板尺寸 | 430 × 648 | **430 × 233**（高 −64.0%） |
| 1024×768 面板尺寸 | 430 × 553 | **430 × 233**（高 −57.9%） |
| 860×720 面板尺寸 | — | **430 × 233** |
| 结构 | 6 个 `h4` 段 + 4+6+3+1+3+2 条说明，约 20 行 | 引导 1 行 + **7 行链接** + 版本 1 行 |
| 横向溢出 | 0 | **0**（三档 `scrollWidth == clientWidth`，`docScrollWidth == innerWidth`） |

链接清单（每行「短标签 + 可点链接 + 一行说明」）：

| 短标签 | 链接 | 一行说明 |
| --- | --- | --- |
| 数据来源 | the-hideout/tarkov-dev | MIT |
| 底图 | tarkov-dev-svg-maps | CC BY-NC-SA 4.0 · 非商业 |
| 图标 | tarkov.dev 分类图标 | — |
| 任务 | tarkov.dev 任务数据 | 派生生成 · 未逐条复核 |
| 行情 | tarkov.dev 快照 | 构建期快照 · 非实时 · 买卖价同源 · 运行期不联网 |
| 商标 | Battlestate Games | 商标与美术归其所有 · 永久免费 · 严禁售卖 |
| 公式 | — | 甲伤 / 跳弹 / 穿透浮动按 0.13.x 反编译口径（R62） |
| 版本 | — | `版本 2026-10-20T15:10:05Z · regular · 13 图 · 146 撤离点 · 6408 物资点 · 643 Boss` |

许可署名逐条保留：`tarkov.dev`（the-hideout/tarkov-dev, MIT）、
`tarkov-dev-svg-maps`（CC BY-NC-SA 4.0，非商业）、tarkov.dev 分类图标、
Battlestate Games 商标与美术归属声明。

## 4. 弹药标签新旧对照

| data-tab | 实际视图 | 旧中文 | 新中文 |
| --- | --- | --- | --- |
| `ballistics` | 弹药详情 / 属性总表（200 行） | 弹道 | **子弹信息** |
| `drop-pen-dmg` | 穿透与伤害随距离衰减表 | 穿透·伤害衰减 | **穿透·伤害距离衰减** |
| `drop-bullet` | 弹速与弹道下沉 / 距离衰减表 | 3 米弹道下沉 | **弹道下坠** |
| `graph` | 伤害 × 穿透力散点/分析图 | 弹道曲线 | **分析表** |
| `sim` | 逐发击杀模拟器 | 逐发模拟 | 逐发模拟（不变） |

切换实测：5 个标签均进入对应视图，`#am-table` / `#am-graph` / `#am-sim`
显隐互斥，无内容串页；`aria-selected` 随切换更新；`title` 与 `#am-maxdist`
提示中的旧英文名同步改为新中文名（英文原名仍由 i18n 追加在 title 末尾）。

## 5. 弹道副标题

- 结构：`header.am-top > .am-head > h2.am-title(弹药与弹道) + span.am-subtitle(诺文斯克弹道学)`。
- 尺寸：标题块 84 × 26；副标题 73 × 12；与标签栏同高。
- 1440/1024/860 三档实测：`.am-head` 与 `#am-tabs` 同一行（`y` 相同），
  5 个标签 `top` 全部一致（1440/1024 = 42/73，860 = 73），无换行错位。
- 860 下搜索/提示换到第二行是原有 `flex-wrap` 行为，标签栏本身不受影响。

## 6. 测试

`C:\Python314\python.exe -m pytest tests -q`

```
1736 passed, 1 skipped in 97.28s (0:01:37)
```

三个过期断言均同步修改（未删除、未放宽）：
1. `test_r32_about.py`：改为校验 7 行短标签 + 全部许可署名 + 价格/统计单行；
2. `test_r40_armor_effdur.py`：价格说明改为新单行逐字文本，仍只允许出现一次；
3. `test_r42_live_prices.py`：TTL 用例改用真实当前时间播种（原 `FIXED_NOW` 在 21:10 后必然过期）。

## 7. 打包与三件套

- 清单预检：预期 **13241** / 实际 **13241** / 缺失 **0** / 未登记 **0**，staging **126.9 MB**（无新增文件）。
- `build.ps1`：dist 运行期文件 **13241** / **155.1 MB**；并入壳后 **14239** 文件 / **156.0 MB**。
- dist Rev：`R19.35-e0fd7013`（`/api/build` 200）。
- 源码与 dist 逐字节一致（SHA256）：

| 文件 | SHA256 |
| --- | --- |
| `index.html` | `8F34049EE4AA5D14691727D502A5CE3DF35B06790EAB51C5D09BAF4400214E52` |
| `app.js` | `6CEE64BD156BDE27B3FDC48A690C38B4F0CF65C2BE35B945CE1F3E9893A7AD3A` |
| `style.css` | `F1F5C671E537AE6FEE9336B7036FBD49919E656E55D51DE43DDD738CEBCA8F13` |
| `theme-windows-xp.css` | `5B0EA1289A03F2FCF1D7EBB2D7C8D8E506D432AAFE8C57B1E5293F758B774C73` |
| `data/i18n/ui-zh.json` | `E603583D213A8F6ABCEE7CC61D998D89CFC6875DA927D5E0A32BF33A2E72748A` |

三件套（`build_release.ps1 -SkipBase`，版本 0.1.0）：

| 产物 | 体积 | 字节 | SHA256 |
| --- | --- | --- | --- |
| `EFTMap-Portable-0.1.0.zip` | 116.9 MB | 122587105 | `7493119F29CD0634473BD7F1CF864BA69551D7244BB8ADBF5355041225989880` |
| `EFTMap-AppWindow-0.1.0.zip` | 116.9 MB | 122587244 | `34408AF05320CA2CEC5D23E70650BB4BCAD518FE13A82B93B5E917EBC59DD8BF` |
| `EFTMap-Setup-0.1.0.exe` | 127.3 MB | 133445988 | `1BCD590E1BEC7752AB7314C2B2A69233678BB5D0D15917E2FF22753140A9428C` |

## 8. 冒烟（真实 Chrome，dist 8789）

- 请求：240 条，全部 `200/304`，非 200/304 **0**，外部请求 **0**。
- 控制台：error **0**（仅 1 条既有的表单无 id/name 可访问性提示）。
- 截图（`docs/r70-about-ammo-tabs/smoke/`）：
  `r70-ammo-1440.png`（134770 B）、`r70-about-1440.png`（147366 B）、
  `r70-ammo-1024.png`（62275 B）、`r70-about-1024.png`（76906 B）、
  `r70-ammo-860.png`（53847 B）、`r70-about-860.png`（65684 B）。

## 9. 清理与版本

- 冒烟后端 8788/8789 与临时配置目录已清理；未改动 8787 上他人进程。
- **未 git 提交**，版本仍 `0.1.0`。
