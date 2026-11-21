# R79 · 眼部防护显示 + 任务外链清理

日期：2026-11-05　范围：`app.js` / `tasks.js` / 必要数据文件（未改 `index.html`、`style.css` 既有块）

---

## A. 带防护的眼部装备显示「眼部」

### 根因

1. **数据侧**：上游 tarkov.dev 对 `ItemPropertiesGlasses` 类不返回 `properties.zones`，所以 `data/items.json` 里眼镜的 `z` 为空（护面类部分面罩同样为空）；而游戏权威值在 `data/game-truth/armor_items.json` 的 `props.armorColliders` 里（6B34 护目镜 = `["Eyes"]`）。
2. **渲染侧**：`zoneText()` / `zonePartCount()` / `zoneIcon()` 本身支持 `Eyes → 眼部`（`ZONE_WORDS` 有映射），但眼镜（glasses）与护面（face）的候选表**根本没有「防护区域」列**；另外「仅眼部」组合缺 `zone-eyes.png` 图标。

### 修复

| 位置 | 内容 |
| --- | --- |
| `tools/r79_apply_zone_fallback.py`（新增） | 只给 `z` 为空的记录补 `armorColliders`，生成本次 16 件的 before/after 清单 |
| `data/items.json` | 16 件补 `z`：6 眼镜 + 9 面罩 + 破碎面具；6B34 = `["Eyes"]` |
| `tools/fetch_data.py` | 新增 `apply_truth_zone_fallback()`，重建数据时同样兜底，防止回退 |
| `app.js` L7109-7111 | 图标映射新增 `"面部\|眼部"`、`"眼部"` |
| `app.js` L11432-11438 | glasses / face 候选表加入 `zoneIcoCol`（「防护区域」列） |
| `app.js` L10869/L10872 | `LW_COL_DEFAULTS` 为 glasses / face 补 `zoneIco: 60` |
| `assets/icons/zones/zone-eyes.png`、`zone-face-jaw.png` | 新增图标，并登记 `tools/iconize.py` 的 `ZONE_JOBS` |
| `tests/test_r79_eyewear_eyes.py`（新增） | 覆盖「带眼部防护的 eyewear」+ 外链清理 |

### 运行验证（headless Chrome，1800×1100）

- 眼镜表共 40 行，表头：`名称 / 移动转身人机 / 防护区域 / 重量 / 跳蚤 24h / 跳蚤 7d`。
- 选中 **6B34防破片护目镜** 装备进眼镜槽后，该行「防护区域」格显示
  `assets/icons/zones/zone-eyes.png`（`alt="眼部"`，`naturalWidth=47`，加载成功）。
- 该表共有 6 行带「眼部」图标，其余无防护墨镜显示 `—`。
- 护面表共 124 行，其中 26 行带防护区域图标；抽样 `Atomic Defense CQCM 防弹面具（黑色）`
  显示 `zone-top-face-jaw-eyes.png`，`alt="头部、下颌、眼部、颅顶"`。

截图：

- [A-1 配装界面 · 6B34 已装备 + 右侧列表](evidence/A-1-glasses-6b34-eyes.png)
- [A-2 眼镜表「防护区域」列特写](evidence/A-2-glasses-zone-column.png)
- [A-3 护面表眼部防护图标](evidence/A-3-facecover-eyes.png)

---

## B. 任务界面 tarkov.dev 攻略外链清理

### 已删除

| 位置 | 内容 |
| --- | --- |
| `app.js` 任务行（约 L2890） | 删除 `if (g.href)` 分支与「tarkov.dev 攻略」链接及其文案 |
| `app.js` 任务点浮窗（约 L3526） | 删除 `appendTaskGuide(host, item)` 调用 |
| `app.js` | 删除 `appendTaskGuide` 函数（连同 `marker-pop-guide` 节点不再生成） |
| `app.js` L1516 | 运行时移除任务栏底部 `.task-source` 出处文案（不改 `index.html`，避开并行会话） |
| `data/task-points.json` | 删除全部 401 个 `"href"`（其中 296 个 tarkov.dev 任务链接） |
| `tools/fetch_eftarkov_tasks.py` | 不再生成 `href`；出处文案改为「任务名称与目标」 |

### 运行验证（任务面板）

- 右侧任务/剧情面板：**54 行**，`<a>` 数量 **0**，`.task-source` 已不存在，面板文本无 `tarkov.dev` / `攻略`。
- 全页仅剩 **3 个** tarkov.dev 链接，全部位于菜单栏「关于」的 `.about-block` 内（聚合出处，允许保留）：

| 文案 | href | 归属 |
| --- | --- | --- |
| tarkov.dev 分类图标 | https://tarkov.dev/ | 关于页 |
| tarkov.dev 任务数据 | https://tarkov.dev/ | 关于页 |
| tarkov.dev 快照 | https://tarkov.dev/items | 关于页 |

截图：[B-1 右侧任务面板（无外链、无底部出处）](evidence/B-1-task-panel-no-external-links.png)

### 全站搜索结果（业务界面已无外链）

- `app.js` / `tasks.js` 剩余 16 + 2 处：全为**注释**与价格口径说明（如「上游 tarkov.dev 不提供 7 日均价」），不生成任何 `<a>`。
- `index.html` 9 处：3 处关于页链接（上表）、`task-source` 文案（运行时移除）、其余为设置说明文案与 `title` 提示，无任务攻略链接。
- `style.css` L1170 的 `.marker-pop-guide` 注释/规则已无对应节点（死样式，按并行约束未改动既有块）。
- `data/maps.json`、`data/meta.json`、`data/gun-compat.json` 等大量命中为**数据出处字段**（构建期 provenance），不是界面链接。

---

## 自测

```
pytest tests/test_r79_eyewear_eyes.py tests/test_r11_armor_grouping.py  → 14 passed
pytest tests/test_loadout_workbench.py                                  → 28 passed（全绿）
node --check app.js / tasks.js                                          → OK
```

---

## C. 右键监听器审计（原 `test_left_cards_right_click_unequip` 的「既有失败」）

**结论：6 处是 6 个独立用途，无重复绑定，不改绑定代码，改断言。**

| # | 位置 | 元素 | 用途 |
| --- | --- | --- | --- |
| 1 | `app.js` L9473 | `node`（左栏装备卡 / 附件子槽） | `bindCellUnequip` → `clearGearSlot` |
| 2 | `app.js` L10727 | `box`（插板格，仅 `state==="on"`） | 卸下该块插板 |
| 3 | `app.js` L16806 | `card`（配枪工作台装配卡） | `clearGunSlot` |
| 4 | `app.js` L17091 | `acell`（画布子弹格） | 清空已选弹药 |
| 5 | `app.js` L3129 | `el.taskList`（`#task-list` 容器，代理绑定） | 任务行右键 → `showTaskContextMenu` |
| 6 | `app.js` L3004 | `document`（capture） | 点别处收起任务菜单；**不 `preventDefault`** |

**为什么不是重复绑定**

- 第 5 处为**容器代理**：行节点每次重绘都是新节点，旧节点随之丢弃，不会叠绑；`initTaskPanel()` 仅在启动时调用一次。
- 第 6 处是 `ensureTaskContextMenu()` 内的一次性绑定，有 `if (el.taskContextMenu) return` 守卫，重复调用不会叠加。
- 两处职责不同：容器负责「弹出菜单」，document 负责「收起菜单」，不共享节点或逻辑。

**运行实测（headless Chrome，任务面板 54 行）**

```
首次右键任务行：  .task-context-menu 元素数 1，可见 true，菜单项 2
再右键另一行：    .task-context-menu 元素数 1，可见 true（复位，不新增）
右键空白处：      .task-context-menu 元素数 1，可见 false（收起）
```

即「右键一次只弹 1 个菜单」，无双重弹窗 / 双重逻辑。

**测试更新**：`tests/test_loadout_workbench.py::test_left_cards_right_click_unequip`
- 监听总数断言 `4 → 6`，并在注释中逐条说明 6 处的来源；
- 保留「不得全局拦截」约束：`window` 级仍必须为 0；`document` 级仅允许 1 处，且该段不得出现 `preventDefault`；
- 新增 `#task-list` 代理入口与 `showTaskContextMenu` 调用断言。

未打包、未 commit。
