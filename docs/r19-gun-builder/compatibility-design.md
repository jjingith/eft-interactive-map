# R19 槽位、父子关系与兼容性校验设计

实现位置：`gun_builder.js` 的 `buildTree` / `candidates` / `validate` / `sanitize`。
UI 侧的 `app.js` 只在渲染时调用它们，不重复实现规则。

---

## 1. 数据模型

```
枪械(items[gunId].slots[])
  └─ slot { id, sid, label, required, allow[itemId...] }
        └─ 装上的配件(items[itemId].slots[])   ← 递归
```

- 一个槽位用 `sid`（上游 slot nameId，如 `mod_muzzle`、`mod_handguard`）标识。
- 同一父件如果有两个同名 `sid`，第二个起加 `#n` 后缀（如 `mod_mount#1`），
  路径唯一化后才能当作 Map key 与 DOM id。
- 节点路径 = `父路径/sid`，根槽位没有前缀。这与 `data/gun-presets.json` 里
  `i`（path → itemId）的键格式**完全一致**，所以官方预设可以直接喂给引擎。

实测规模：163 把枪、987 个单层槽位；递归展开后 AK-74 是 13 个节点、M4A1 是 18 个。

---

## 2. 递归展开规则

`buildTree(ctx, gunId, installed)`：

1. 从枪械的 `slots[]` 开始，逐槽位建节点；
2. 如果该路径上**已装了配件**，就读那个配件的 `slots[]`，继续往下建（`depth + 1`）；
3. 没装就不展开 —— 装了护木才出现护木上的导轨槽，不装就不占位置。

这条"装了才展开"的规则同时保证了**父件卸载后子槽必然消失**：
树的形状由 `installed` 决定，父件一删，下一次 `buildTree` 就不会再走那条分支，
`validate` 立刻会把残留的子配件报成「槽位不存在」。

`app.js` 的 `rebuildGunTree()` 会按新树清理 `g.installed` 里树上已不存在的键，
所以界面上不会出现"看不见但还在算属性的幽灵配件"。

> 防止异常数据导致栈溢出：`walk()` 里对同一 `prefix + 名称` 的组合最多递归 3 层。

---

## 3. 候选集（`candidates`）

某槽位的候选 = `node.allow` 里去掉**已被别的槽位占用**的项，再标出阻塞原因：

| 情况 | 处理 |
|---|---|
| 物品库里没有这个 id | 直接跳过，不显示"数据缺失"占位行 |
| 同一 id 已装在**别的**槽位 | 仍然列出，但标 `blocked`（提示"同一配件已装在 X"）—— 见 §4 |
| 与已装件互斥（`conflictingItems`） | 标 `blocked`，并给出具体是哪一件 |

**候选只来自该槽位自己的 `allow`**，不会把所有配件混在一起。
这一点在参考站上是同样的：点 Muzzle 只出枪口，不会出枪托。

---

## 4. 「同一型号配件能否装多件」——本轮纠正的一条规则

R19 之前 `app.js` 的 `gunInstallCheck` 拒绝"同一 id 出现在两个槽位"。

但 `data/gun-presets.json` 里有 **32 条官方预设**就是这样：
M4A1 LVOA 的两个 `mod_mount_002` / `mod_mount_003` 是同型号导轨座，
EXPS3、SV-98 OV、Saiga-12K 也都是两个相同的战术设备 / 导轨。

真实游戏里这是**买了同一件物品两件**，完全合法。所以本轮：

- `validate()` 不再把重复占用算作错误，改为放进 `duplicates` 列表（供 UI 提示"×2"）；
- `cost()` 按**件数**计价，两件相同配件算两次；
- `gunInstallCheck()` 去掉这条拦截，只保留 `allow` 与 `conflictingItems` 两条硬约束。

对应测试改为「用真实官方预设验证重复合法 + 成本按件数」，不是简单删断言。

---

## 5. 校验与清洗

### `validate(ctx, gunId, installed)`

返回 `{ ok, errors[], duplicates[] }`，逐项检查：

| 检查 | 失败信息 |
|---|---|
| 枪械 id 在物品库 | 物品库里没有这把枪 |
| 每个路径在树上存在 | 槽位不存在（父件可能已更换） |
| 配件在该槽位 `allow` 里 | 不在该槽位的合法配件列表里 |
| 重复占用 | 只记录，不判错 |

实测：373 条官方预设 → **341 条完全合法**，其余 32 条全部是重复占用（即上一节的情况），
**没有一条是"路径不存在"或"不在 allow"**。这说明本地的槽位树与官方预设的路径格式对得上。

### `sanitize(ctx, gunId, installed)`

导入 / 恢复默认时用：反复 `validate` → 删掉报错的路径 → 再 `validate`，
直到干净（最多 12 轮）。返回 `{ installed, dropped[] }`。
`dropped` 会原样显示给用户，说明"清掉了谁、为什么"。

---

## 6. 与「用户预设」的区别

项目里有两套预设，不能混：

| | 用户预设（R6 起的 `weapon-presets.json`） | 装配预设（R19 新增） |
|---|---|---|
| 粒度 | 整套人物配装里的武器条目 | **单把枪的完整装配** |
| 存储 | `%APPDATA%\EFTMap`，走后端接口 | 浏览器 localStorage + JSON 文件 + URL 分享串 |
| 结构 | `{items: {path: itemId}}` | `{kind:"eftmap.gunbuild", version, gunId, slots:{path:itemId}}` |
| 用途 | 配装工作台里引用 | 配枪页保存/分享 |

R19 的装配预设带 `kind` 与 `version` 字段，导入时先校验 `kind` 再看结构，
避免把别的 JSON 误当装配塞进去。
