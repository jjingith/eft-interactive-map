# R67 · 配装界面两个 UI 问题（名称截断 / 防护区域排序）

host=HOMONAS user=MASTERJJ at=2026-11-04 18:05 +08:00

本轮只改源码：**未重建 dist / release、未改打包脚本、未 git 提交**。

---

## 一、结论（根因 → 改法）

### 问题 1：右侧装备列表首行文字被截

**先判定「表头行」还是「第一行数据」**（护甲槽位候选表，108 行，1440×900 真实渲染）：

| 元素 | 外框高 | clientHeight | scrollHeight | 结论 |
|---|---|---|---|---|
| `.tbl-head`（表头行） | 32px | 30 | 30 | **纵向没有被截** |
| `.tbl-row`（任意数据行） | 80px | 77 | 77 | **纵向没有被截** |

所以「行高不够」不是真因。真因是**横向**截断：

- 护甲/弹挂用的是 R20.7e 的紧凑 23 列版式，名称列被钉成 **128px**；
- 名称格里还有 44px 物品图标 + 左右内边距 12px，**文本区只剩 ~64px**；
- 原规则是 `white-space: nowrap; overflow: hidden; text-overflow: ellipsis`，于是一行长名只剩 `6B43 屏…`。
  最长的候选名（canvas 实测自然宽 **326px**）在 64px 宽下要 5 行，两行也放不下。

**改法（3 处）**

1. `style.css` [L2194-2212](../../style.css#L2194-L2212)：名称格 `white-space: normal` + `word-break: break-word`
   + `display: -webkit-box; -webkit-line-clamp: 2` + `line-height: 1.35; max-height: 2.7em`，
   两行封顶、不溢出、不压下一行；垂直居中沿用单元格既有的 `align-items: center`。
   **行高不动、表头也不动**（表头纵向本来完整）。
2. `app.js` [L10375](../../app.js#L10375)：`LW_R20_WIDTHS.n` **128 → 232**。
   232 − 44（图标）− 7（图标右间距）− 12（左右内边距）≈ **169px** 可用文本区（实测最长单行宽 **167.5px**），
   最长名 326px 两行正好放下；128px 时即便允许换行也只有 ~65px/行，等于白改。
3. `app.js` [L10377-10379](../../app.js#L10377-L10379)：`LW_R20_WIDTHS.zoneIco` **52 → 76**。
   表头文案 + 排序箭头实测需要 69–74px，52px 时箭头被裁掉，排序方向看不见（问题 2 的视觉指示）。

### 问题 2：点「防护区域」列排序结果乱

**根因（实测 + 源码确认，两层）**

1. 三个防护区域列（`zoneIcoCol` / `zoneCol` / `helmetZoneCol`）的 `sortValue` 全都返回
   `r.zoneText` —— 中文部位名**拼接串**（"上胸、腹部、侧面…"），且没声明 `num`，
   于是 `sorted()` 走 `localeCompare(vb, "zh")` 的**字典序**。字符串序跟「覆盖部位多少」无关，
   点起来自然「乱」。
2. 配装表挂了 `opts.groupOf = baseClGroupRank`（按基础防弹等级固定分组主序，组序优先于列序）。
   即使把排序值换成「部位数量」，序列也会被组序切成一段段，**全局仍然不单调**。

**改法（4 处）**

1. `app.js` [L6669-6680](../../app.js#L6669-L6680)：新增 `zonePartCount(zs)` ——
   用 `zoneWord` 投影后**按不同部位词去重计数**（不直接数 `rec.z.length`：`z` 里同时有
   正反面 zone 与插板槽位，`RibcageUp`/`SpineTop` 都投影成「上胸」，直接数会重复计 2–3 次；
   缺口径与「防护区域」列展示的图标部位完全一致）。
2. `app.js` [L7811](../../app.js#L7811)：行对象新增 `zoneCount: zonePartCount(rec.z)`。
3. `app.js` [L10655](../../app.js#L10655)、[L10662](../../app.js#L10662)、[L10866](../../app.js#L10866)：
   三列统一改为 `num: true, bypassGroup: true, sortValue: function (r) { return r.zoneCount; }`
   （`num: true` 让首点即降序 = 「越多越靠前」，再点一次升序，箭头 ▲/▼ 沿用既有 `.tbl-sort`）。
4. `app.js` [L7975-8010](../../app.js#L7975-L8010)：`sorted()` 支持 `col.bypassGroup`
   （该列排序时跳过 `opts.groupOf`），并给数值相等 / 文本相等补了**与方向无关**的
   `tieBreak`（名称 `localeCompare(zh)` → 退化为 id），保证同数量行的次序可重复、两次排序集合一致。

> 顺带说明：护甲 23 列版式的「防护区域」表头 key 其实是 `zoneIco`（不是 `zoneText`），
> 三列都改到才能覆盖 armor/rig（`zoneIcoCol`）、plate（`zoneCol`）、helmet（`helmetZoneCol`）。

### 测试夹具同步

`tests/test_loadout_workbench.py` [L1042-1043](../../tests/test_loadout_workbench.py#L1042-L1043)：
node 侧 `gearRows` 夹具按名字白名单抽取函数，新增 `extractFn(src, "zonePartCount")`，
否则 `ReferenceError: zonePartCount is not defined`（首次全量跑就是这里挂的）。

---

## 二、实测数字（真实 Chrome，DevTools MCP，源码版 `python tools\serve.py --port 8799`）

页面：`http://127.0.0.1:8799/index.html` → 配装 → 护甲 → 护甲槽位候选（108 行）。
视口：CSS 1440×900 / 1024×768 / 860×720（DPR 0.667，截图 PNG 分别为 960×600 / 683×512 / 573×480）。

### 1) 名称格（问题 1）

| 指标 | 1440×900 | 1024×768 | 860×720 |
|---|---|---|---|
| 数据行外框 / `clientHeight` / `scrollHeight` | 80 / **77 / 77** | 80 / **77 / 77** | 80 / **77 / 77** |
| 表头外框 / `clientHeight` / `scrollHeight` | 32 / **30 / 30** | 32 / **30 / 30** | 32 / **30 / 30** |
| 名称列宽 | 232px | 232px | 232px |
| 名称文本溢出（`scrollHeight > clientHeight`）行数 | **0 / 108** | **0 / 108** | **0 / 108** |
| 文本行数分布（`height / line-height`，lh=16.2） | **2 行 92 / 1 行 16，最大 2** | 同上 | 同上 |
| 表宽 / 容器可视宽（容器内横向滚动） | 1434 / 978 | 1434 / 687 | 1434 / 830 |
| 页面级横向溢出 | `docW=1440 = innerWidth` | `docW=1024 = clientWidth` | `docW=859 = clientWidth` |
| 视口外溢元素（排除 `.tbl-scroll` 内部） | — | — | **0 个** |

- 「文本行数 = 2」的样例行（长名）：`6B43 屏障-Sh 防弹衣（数码丛林迷彩）`，
  名称 span `clientHeight = scrollHeight = 32`，`32 / 16.2 = 2.00` 行 —— 无截断。
- 1 行的 16 条是本来就放得下的短名（如 `5.11 Hexgrid 插板背心`，`ch=sh=16`）。
- 两行封顶没有把列表挤到必须滚动：行高维持 78px（外框 80），行数 108 不变，
  列表纵向滚动量与原版一致（`--lw-table-row-height` 未改，只改名称格排版）。

### 2) 防护区域排序（问题 2）

按**覆盖的不同部位个数**排序，首点降序（`num:true` → `sortDir=-1`）、再点升序，表头箭头 ▼ / ▲。

**降序前 10 行（名称 → 层数）**，单调不增（违例计数 **0**）：

```
6B43 屏障-Sh 防弹衣（数码丛林迷彩）                 → 6
First Spear Siege-R Optimized M.A.S.S. 插板胸挂 (黑色军团) → 6
FORT Gladiator-S（格斗-S）插板胸挂（无惧死亡）       → 6
FORT Redut-T5（堡垒-T5）防弹衣（烟雾迷彩）           → 6
IOTV Gen4 防弹衣（全面防护型，复合迷彩）             → 6
NFM THOR 一体式防弹护甲                              → 6
6B13 突击甲（丛林迷彩）                              → 5
6B13 突击甲（数码丛林迷彩）                          → 5
6B13 M 突击甲（圣诞特装版）                          → 5
6B13 M 突击甲（Killa 版）                            → 5
```

**再点一次升序前 10 行**，单调不减（违例计数 **0**）：

```
5.11 Hexgrid 插板背心                                → 1
5.11 Tactical TacTec 插板胸挂（丛林绿）              → 1
5.11 Tactical TacTec 插板胸挂（风暴灰）              → 1
Crye Precision AVS 插板胸挂（Tagilla 版）            → 1
Crye Precision JPC 插板胸挂（复合迷彩）              → 1
Eagle Allied Industries MBSS 插板胸挂（狼棕色）      → 1
Hexatac HPC 插板背心（复合迷彩）                      → 1
Hexatac HPC 插板背心（黑系复合迷彩）                  → 1
LBT 6094A Slick 插板背心（橄榄绿）                    → 1
LBT 6094A Slick 插板背心（黄褐色）                    → 1
```

- 排序方向指示：第一次点击 `防护区域▼`，第二次 `防护区域▲`；表头格
  `scrollWidth = clientWidth = 74`（改前 69/50，箭头被裁）。
- 两次结果的 id 集合完全相同：`sameSet = true`，**无丢行（108 → 108）、无重复**。
- 同值次序稳定：并列 6 层的 6 行按名称升序稳定排列（两遍一致）。
- 列宽同步：`zoneIco 52 → 76`，表宽 1306 → 1434（名称列 +104、防护区域列 +24）。
- 三个视口的 `descBad / ascBad` 均为 **0**。

### 3) 回归

```
python -m pytest tests -q
1736 passed, 1 skipped in 95.68s (0:01:35)
```

（与基线 1736 passed / 1 skipped 一致。输出中间那段 `socketserver` / `BrokenPipeError`
是测试自己起的 `serve.py` 在用例结束时被浏览器断开，pytest 结果为绿。）

---

## 三、截图

目录：`docs/r67-loadout-table/smoke/`（临时目录 `D:\Temp\2\` 的同名原图已清理）

| 文件 | 内容 |
|---|---|
| `r67-1440-before.png` | 1440×900，名称排序（默认），两行高的名称为主 |
| `r67-1440-zone-desc.png` | 1440×900，点「防护区域」后降序（名称列可见，前 10 行都是 6/5 层） |
| `r67-1440-zone-col.png` | 1440×900，同一次降序但横向滚动到「防护区域」列：表头 ▼ + 图标列 |
| `r67-1024-before.png` | 1024×768，名称排序，名称两行显示 |
| `r67-1024-zone-desc.png` | 1024×768，防护区域降序 |
| `r67-1024-zone-col.png` | 1024×768，防护区域列 + 箭头 |

---

## 四、局限

1. **名称列是固定 232px**。最长名实测自然宽 326px，两行刚好放下（可用文本区 ≈169px×2，实测最长行 167.5px）。
   若手工把名称列拖窄到 < 226px，长名会重新在第 2 行出现省略号 —— 由 `-webkit-line-clamp` 保证
   **不会溢出、不会压住下一行**，但字仍看不全。要彻底解决需要继续加宽名称列或压缩列数。
2. **表头窄列仍横向裁字**：`移动/转身/人机`（76px）、`前插板 / 后插板 / 左内衬…`（32px）
   的表头 `scrollWidth > clientWidth`。它们**纵向没有被截**（`ch = sh`），按你的要求本轮
   **不动表头**，只把「防护区域」表头加宽到能显示排序箭头。
3. **排序对缺失数据的处理**：`zoneCount` 由 `rec.z` 投影计数；`rec.z` 为空/缺失 → `0`，
   降序时排在最后、升序时排在最前。本轮 108 行里没有 `0` 值行（`nullCount = 0`）。
4. **同值次序**：按名称 `localeCompare(…,"zh")`，再退化为 id；与排序方向无关，所以升/降两遍
   遍历次序一致。若上游出现**同名**（不同 id）行，两者靠 id 兜底，仍可重复。
5. **只改源码**：`dist/` 与 `release/` 里的 `style.css` / `app.js` 还是旧版（本轮按要求不重建），
   打包后会一并生效。
