# R19.16 交付报告：武器槽位布局校准器（Weapon Layout Calibrator）

**实际版本**：`R19.16-69775cd8`（`/api/build` 实测）；资源 `?v=r19.16`
**工具入口**：`http://127.0.0.1:8787/index.html?layoutCalibrator=1`
**校准数据**：`data/gun-layout-calibration.json`（备份 `data/gun-layout-calibration.json.bak.json`）
**工作区**：增量修改；未 `git reset` / commit / push，未覆盖 `release/`，未删除历史审计与测试。

---

## 一、交付物概览

| 组件 | 文件 | 作用 |
|---|---|---|
| 校准器界面 | `calibrator.js` / `calibrator.css` | 仅 `?layoutCalibrator=1` 激活；普通模式脚本入口直接 return，零副作用 |
| 共享引擎接口 | `app.js` 内 `window.GWCalib` | **暴露**（不复制）同一套 items / gunslots / 内置预设 / `window.GB` / `gwBuildLayout()` |
| 服务端接口 | `tools/serve.py` → `GET/POST /api/layout-calibration` | 只读写一个固定文件；路径服务端拼出 |
| 数据校验模块 | `tools/layoutcal.py` | 身份 / 坐标 / 冲突校验、原子写入、备份恢复 |

工具三栏：

1. **左**：163 把枪搜索列表 + 装配状态下拉（条件子槽位）+ 枪械信息（ID / 预设 / 槽位数 / 画布行数 / 已保存与未保存）。
2. **中**：六行九列基础网格 + 顶部扩展 + 行列编号 + 真实槽位卡片（可拖动）+ 「自动布局 / 校准预览」切换 + 差异列表。
3. **右**：槽位 ID、完整路径、父槽位、拥有者物品、安装物品、allow 清单、自动/校准坐标、topPad、角色、唯一身份键、行列输入框、备注。

---

## 二、数据契约（`slot-identity-schema.json`）

- **权威坐标 = 逻辑行列**（`logicalRow` = 显示行 − `topPad`；`col` 1..9）。顶部扩展只影响显示行，不移动人工坐标。
- 同时记录 `topPad` 与 `displayRow`（还原当时画布用）与 `autoRow/autoCol`（回溯自动布局用）。
- **唯一身份 = `slotPath|slotId|ownerItemId`**：同一 `slotId` 在不同父件下是不同安装结构（`ownerItemId` = 父槽安装件 ID），坐标绝不串用。
- 每条记录带 `role / source=manual / note / updatedAt`；每枪带 `history`（最近 50 次）。

## 三、保存机制（`calibration-save-load.json`）

- `POST /api/layout-calibration` actions：`save` / `save-all` / `clear` / `restore-backup` / `import`。
- 写盘流程：整包校验 → 备份上一版（`.bak.json`）→ 临时文件 + fsync + `os.replace` 原子替换。
- 服务端校验：枪械 ID 必须在 `data/gunslots.json`；行列范围 -6..6 / 1..9；同枪不允许两槽同格；导入校验 `schemaVersion`。
- 实测拒绝：未知枪械 ID、行号 99、两槽同格、`schemaVersion:99` 导入（已有数据不被覆盖）。
- **持久化实测**：浏览器保存 → 刷新页面 → 条目仍在（r5c2，带「已校准」标记）；**杀掉并重启本地服务** → `GET` 仍返回同一条目（文件在磁盘 `data/` 下，不是 localStorage）。
- 导出 = 浏览器下载同名 JSON；导入 = 同一校验通道；恢复上一版 = `restore-backup`（当前版另存 `.prev.json`）。

## 四、拖放与冲突（`drag-drop-tests.json`，真实 CDP 鼠标事件）

| 操作 | 实测 |
|---|---|
| 拖动 `mod_mount_000` r2c8 → r5c1 | 卡片落位，标记「未保存」，差异条显示 r2c8 → r5c1 |
| 撤销 / 重做 | 回到 r2c8 / 再到 r5c1 |
| 坐标输入 r5c2 | 立即生效并可保存 |
| 拖到枪械本体 r3c6 | **拒绝**：「目标是枪械本体占用区（r3c6–c8），不允许放置」 |
| 与 `mod_charge` 交换 | 两槽互换位置，**槽位数不变、零丢失** |

拖动只改视觉坐标：物品 ID / 槽位 ID / 父子关系 / allow / 配装 / 预设全部不变；界面右下常驻提示。切换枪械、清除、退出均走非阻塞三态确认（保存并切换 / 丢弃并切换 / 取消），不会静默丢修改。

## 五、条件子槽位（`conditional-slots.json`）

- 装配状态下拉读同一套内置预设，切换后按真实槽位树重建。
- 实测 SA-58：默认 17 槽 → AUT 预设 8 槽（真实条件槽位增减）。
- 条件子槽记录绑定「路径 + 槽位 ID + 拥有者物品 ID」，MPR45 子槽等不会跨父件串用坐标；只登记 `gwBuildLayout` 实际落位的真实槽位，不凭空建接口。

## 六、布局预览（`layout-preview.json`）

- 「自动布局」= 引擎原始坐标；「校准预览」= 应用人工坐标并标注差异。
- **本轮未把人工坐标写入主布局引擎**：`app.js` 不读取校准文件（测试锁定），人工坐标只在校准器预览生效。

## 七、回归（`regression-results.json`）

- 全量测试 **1105 passed / 1 skipped / 0 failed**（新增 `tests/test_r19_16_round.py` 24 项：数据校验 / 备份恢复 / 导入拒绝 / 身份含拥有者 / 浏览器证据 / 审计契约）。
- 普通页面（无参数）实测：校准器覆盖层 0、网格线 0、占位格 0、连接线 0；地图工作台正常。
- 主布局引擎未读取校准文件；枪匠大师 / 兼容性 / 弹药模拟链路未改动（既有测试全绿）。

## 八、真实浏览器验收（`browser-check.json` + 截图 15 张）

覆盖枪械（1920×919）：ASH-12(11 槽)、AXMC(22)、M10(19)、马林 MXLR(12)、AK-74N(13)、M4A1(16)、SA-58(17)、SV-98(7)；另拍 1384×805 视口。截图含主界面、各枪画布、拖动后、条件预设切换、坐标输入、保存后重载、普通页面对照。

## 九、未完成项 / 边界

1. **未批量应用校准坐标到正式布局引擎**（按任务书要求，留给后续 Agent 依据用户校准结果做规则归纳）。
2. 交换位置只支持单格槽位；枪械本体（跨 3 列）受保护不可拖（任务书允许工具明确支持时才放开）。
3. 同一把枪两个真实槽位不允许保存到同一格（服务端拒绝），任务书允许的「少数需重叠显示」结构未设计表达方式——如需要请给出数据表达规则。
4. 磁盘上现有 `data/gun-layout-calibration.json` 含一条验收过程产生的 AK-74N 样例记录（r5c2，`autoRow/autoCol=2/8`），可作为后续 Agent 的数据格式样例；`restore-backup` 可回退。

## 十、给后续 Agent 的接口说明

直接读 `data/gun-layout-calibration.json`：`guns[gunId].slots[slotPath|slotId|ownerItemId]` 即用户校准目标（`logicalRow/col` 为权威坐标）。归纳规则时保留 `autoRow/autoCol` 回溯、按 `ownerItemId` 区分同名槽位、冲突必须显式报告。
