# 第十四轮交付报告：弹药散点图修正与逐发击杀模拟器

- 日期：2026-10-22（夜间自主任务）
- 项目：`02-塔科夫/eft-interactive-map`
- 结论：**四阶段全部完成**；全量回归 **732 passed / 1 skipped / 0 failed**；真实浏览器闭环验收通过；运行期零外部网络请求。

---

## 1. 阶段A：BALLISTICS 散点图修正（完成）

- 根因修正：散点纵轴不再使用整数化的离散评级，恢复三模式图表（伤/穿散点、穿透概率曲线、最高防护等级离散图）。
- 散点标记使用本地图标素材（有效 199/200；`.50 AE FMJ Bull` 上游 CDN 已删除 404，回退为按组着色圆点，属设计内降级）。
- 悬停 tooltip、点击打开弹药详情弹窗、搜索联动均已浏览器验证。
- 证据：`graph/01–07` 截图、`graph/icon-stats.json`。

## 2. 阶段B：公式核对与数据审计（完成）

- Desmos `m8cmsfokkl` 穿透概率模型自官方状态 JSON 原样转录归档（`desmos-m8cmsfokkl-state.json`），测试互证通过。
- 视频《塔科夫护甲》47 张抽帧逐帧审阅（`video-notes.md`）。
- fandom Ballistics / Health_system 真实 Chrome+代理实访核对（`fandom-notes.md`），补齐材质毁损系数表。
- 审计总表：`data-audit.json`（verified / estimated / missing 分级标注）。

## 3. 阶段C：combat_sim.js 纯计算引擎（完成）

- UMD 纯计算引擎（无 DOM/网络依赖）：弹序/弹位、障碍物层逐层判定、分部位 HP、插板独立耐久、软内衬、穿透判定种子随机可复现、混压弹匣顺序耗尽即停、射速 Δt=60000/RPM、多弹丸逐颗判定、击杀发溢出全额均摊（0.49×/1.05× 仅作用于对已摧毁部位的后续命中）。
- 飞行模型与弹药页 DROP 视图同源（amFactor = 0.5+0.5·v(d)/v0）。
- 单元测试：`tests/test_r14_sim.py` 12 项（node 子进程跑 `tests/js/combat_sim_test.js` 场景）。

## 4. 阶段D：逐发击杀模拟器 UI（完成）

### 4.1 实现内容

- 新增「逐发模拟」tab（`index.html`：`data-tab="sim"`、`#am-sim` 容器、`combat_sim.js` 先于 `app.js` 加载）。
- 六区面板：混压弹匣编辑器（≤120 发，按装入顺序分段显示）/ 射击参数（射速/距离/种子/次数）/ 目标预设（`data/combat-targets.json` 懒加载：PMC 440、Scav 三血池 420/435/530、Boss Scourge 750、护卫 570）/ 目标护甲层（插板/头盔/内衬/障碍物 + 快捷预设）/ 命中分布（固定部位或按权重）/ 执行与结果。
- 逐发日志 12 列：#/时刻/弹药/部位/弹丸/穿透概率/掷点/结果/入体伤害/甲损/层后耐久/溢出；死亡行红底标注 +「⚠ 第 N 发击杀 — 死亡终止（死因），后续 X 发未射出」。
- 多次模拟（≤100 局，种子逐次 +1）：击杀率/平均发数/平均耗时，行点击回看该局单发详情（确定性复现）。
- 样式全部限制在 `.am-workbench .am-sim` 作用域；前端 ES5。

### 4.2 验收中发现并修复的真 Bug

**加权命中分布恒中首键**：引擎 `pickPart()` 将 `rng()`（[0,1)）与未归一化的原始百分比权重累加值比较，首个部位权重 ≥1 时必然命中（UI 传 5/30/15… 百分比 → 永远打头）。
修复：`combat_sim.js` `pickPart()` 按权重总和归一化后再抽签；补引擎场景测试 `test_dist_mode_raw_weights_normalized`（200 发 ×3 组对照：head 5% / 95% / 50-50 归一化）。
浏览器复测：×20 局死因分布 chest×10 / head×7 / overflow×3，平均发数 1.0（病态）→ 6.3（合理）。

### 4.3 浏览器验收证据（CDP 真实操作，DOM 断言 + 截图）

| 截图 | 验证点 |
|---|---|
| `sim/01-empty-panel.png` | 禁缓存重载后空面板：6 区、0 弹匣筹码、combat_sim.js 已载 |
| `sim/02-single-kill-log.png` | 单次模拟 M995×30 vs PMC+4级板：第 4 发击杀、日志列齐全 |
| `sim/03-multi-run.png` | 固定胸 ×20：击杀率 100%、平均 3.1 发 |
| `sim/04-mixed-magazine.png` | 混压弹匣 M856A1×2→M995×3 vs 4级板：顺序消耗、第1发钝伤（掷点0.980>65.2%）、板耐久 40→0、穿透概率随耐久下降 65.2%→92.9%→98.1%→98.9%、第4发击杀终止剩1发 |
| `sim/05-weighted-dist.png` | dist 权重 5/30/15/10/10/15/15 ×20：死因分布合理 |
| `sim/06-multi-row-detail.png` | 多次模拟行点击回看详情，与原局逐发一致 |

### 4.4 可复现击杀案例

- `kill-case.json`：混压弹匣（5.56 M856A1×2 + M995×3）vs PMC（440 血）+ 4级复合插板（耐久40），固定胸、50m、600RPM、seed 12345。
- 结果：第 1 发钝伤 11.3（掷点 0.980 > 穿透概率 65.2%），第 2 发穿透 33.6，第 3 发 M995 穿透 37.5，第 4 发击杀（胸 0/85，溢出 35 分摊 6 部位），第 5 发未射出；板耐久 40→0。
- 可复现性：同配置复跑两次，逐发日志与汇总完全一致（页面内验证 `reproducible=true`）。

### 4.5 网络合规

- 运行期网络审计：禁缓存重载全页 172 个请求，**全部 127.0.0.1:8787 本地资源，外部请求 0**（含 sim tab 懒加载 `combat-targets.json`）。

## 5. 测试结果

- 全量：`python -m pytest tests -q` → **732 passed / 1 skipped**（基线 712 + 阶段C 15 + 引擎权重修复 1 + 阶段D UI 接线 4）。
- 本轮新增/修改测试：
  - `tests/test_r14_sim.py`（12 项 + 权重归一化 1 项）、`tests/js/combat_sim_test.js`（11 场景）
  - `tests/test_r14_simui.py`（4 项：targets schema、脚本加载顺序、app.js 接线、引擎归一化修复点）
- 未修改/未删除任何既有测试。

## 6. 网络访问与代理使用记录（合规要求）

| 项 | 结果 |
|---|---|
| 用户指定代理 127.0.0.1:7896 | **可用**（2026-10-23 用户确认正确端口为 7896，任务规则中曾写的 7890 为笔误；本轮经 Chrome 实访 fandom 页面与图片） |
| 笔误端口 127.0.0.1:7890 | 不可用（实测连接拒绝，未监听） |
| 实际成功访问 | desmos.com/calc-states/production/m8cmsfokkl（200，状态 JSON 归档）；escapefromtarkov.fandom.com /wiki/Ballistics、/wiki/Health_system、/wiki/Scourge（真实 Chrome+代理）；static.wikia.nocookie.net 7 张健康面板原图（Chrome canvas 同源导出） |
| 无法访问 | fandom 与 static.wikia CDN 拒绝 curl 指纹（403/HTML 错误页 ~5.9KB），仅真实浏览器可访问 |
| 本地直连 | localhost / 127.0.0.1 / CDP 9224/9226 一律 NO_PROXY 直连，未走代理 |
| 结论来源区分 | 引擎数值公式：视频帧读数 + fandom 实页（网页核对）；弹药 200 项数据/图标：本地 items.json 与历史本地资源（本地数据）；目标血池数值：fandom 图片人工读数（网页核对） |
| 对完成度影响 | 无阻塞；唯一受限点是 curl 无法直接抓 fandom（已用真实 Chrome 绕过） |

## 7. 修改文件清单

| 文件 | 变更 |
|---|---|
| `combat_sim.js` | 新增（阶段C 引擎）；阶段D 修复 `pickPart` 权重归一化 |
| `app.js` | 弹药视图新增 sim 分支 + 逐发模拟模块（约 700 行，未重写既有代码） |
| `index.html` | +sim tab 按钮、+#am-sim 容器、+combat_sim.js 引用（app.js 之前） |
| `style.css` | +`.am-workbench .am-sim` 作用域样式段 |
| `data/combat-targets.json` | 新增（6 目标预设，来源与修正说明内嵌） |
| `tests/test_r14_sim.py`、`tests/js/combat_sim_test.js`、`tests/test_r14_simui.py` | 新增/扩展 |
| `docs/r14-combat/*` | 审计、笔记、kill-case、22 张证据截图 |

未触碰：地图渲染、路线、任务、配装工作台、枪械构建页等既有功能；`data/` 既有数据文件；未推送远程仓库、未覆盖发布版本。

## 8. 缺口清单（如实记录）

1. 部分护甲机制仍为 estimated（抵抗系数公式、钝伤具体公式、跳弹角度阈值）——上游无公开数值，界面已标注。
2. 障碍物多层判定顺序按 fandom 定性描述实现（每层损失部分穿透力与伤害），系数无官方数值。
3. 溢出分摊采用均摊简化（fandom 仅确认 0.49×/1.05× 比例，未确认逐部位分配规则）。
4. 未实现骨折/流血等状态效果（任务书首版范围外，fandom 笔记已记录规则备查）。
5. `.50 AE FMJ Bull` 弹药图标上游 404，散点回退圆点显示。
6. 本地数据存在 7.62x25 TT 口径同名「M995/M856A1」弹药（上游新数据），模拟面板 200 项全列，验收脚本需精确匹配口径前缀。
