# R51 台账：任务目标物品数量（objective item count）角标

host=HOMONAS user=MASTERJJ at=2026-11-04 07:32:08 +08:00

## 结论

| 项 | 结果 |
|---|---|
| `count` 是否补上 | 是。`data/tasks/tasks.{regular,pve,pvps}.json` 的 objective item 现在带 `count`（items-with-count：regular 484 / pve 484 / pvps 472） |
| 真实界面角标 | 可见。真实 Chrome 打开 `http://127.0.0.1:8796/` 任务页，Prapor 任务「蛋卷冰淇淋 Ice Cream Cones」物品栏渲染 `×3` |
| 数据可复现 | 是。`python tools/fetch_tasks.py --offline --verify` → 10 个产物全部 MATCH（忽略时间戳），0 mismatch |
| 测试 | `1713 passed, 1 skipped`（103.12s），0 failed；基线 1708 passed / 1 skipped，新增 5 条用例 |
| dist / release | 未重建；未 git 提交 |

## 1. 数据链路

```
tarkov.dev 任务接口（构建期抓取）
  └─ data/tasks/raw/tasks.<mode>.json        # {"data":{"tasks":{taskId: {...}}}}
      └─ tools/fetch_tasks.py                # fetch_raw() → build() → norm_tasks()/norm_objectives()
          └─ data/tasks/tasks.<mode>.json    # 运行期只读产物
              └─ tasks.js                    # 任务列表右侧物品列渲染 .db4-item-n 角标
```

- 生成脚本：[tools/fetch_tasks.py](../../tools/fetch_tasks.py)。三模式入口 `main()`，`--offline` 只读 raw 快照重建，不联网、不写 raw。
- 上游 objective schema（实测 `tasks.regular.json` 1416 条目标）：`id / type / description / optional / count / items[] / item / questItem / maps / zones ...`。
  - `count` 在 **objective 级**，表示该目标的合计数量（击杀数、上交件数等），不是每个 item 的数量。
  - `items[]` 是候选物品 ID 列表；单物品目标是精确对应，多物品目标表示「列表内任一 / 某类合计 N 件」。
- 前端键名：[tasks.js](../../tasks.js#L2540-L2544) 已是 `it.count`，缺失时 `|| 1` 兜底，因此不会出现 `×1`；后端只需产出同名 `count`，无需改前端。

## 2. 补字段方式

修改 `norm_objectives()`（[tools/fetch_tasks.py](../../tools/fetch_tasks.py)）：

- 新增 `ITEM_COUNT_TYPES = ("giveItem", "findItem", "plantItem", "sellItem")`。
- 仅当目标 **恰好一个 item** 且类型属于上述物品类目标时，把 objective 的 `count` 写入该 item：`items:[{id,name,count}]`。
- 多物品目标**不**把总数写到每个 item（避免「52 个候选物品、合计交 3 件」被显示成每个物品 `×3`）；这类目标仍保留 objective 级 `count`，由任务目标行展示。
- 非物品目标（如 `shoot` 用武器击杀 20 次）不写 item.count，避免把击杀数标到武器图标上。
- 单物品目标的数量分布包含正常件数（2/3/5/10…）与货币金额（卢布 1,000,000、美元 8000 等），均来自上游真实 `count`，未做截断或伪造。
- 兼容性：item 缺少 `count` 时前端按 1 处理；已有 key 名、objective `count`、其它字段均未变。

顺带修复：重跑原本会用生成值覆盖 `data/tasks/traders.json`，丢失 R41 的展示增强字段（`portrait / nameZh / nameZhNote`，任务页头像与中文 tooltip 依赖）。现在重跑前会从现有文件保留这三个字段；验证结果为 `traders.json SAME`。

## 3. 可复现证据

命令：

```powershell
python tools/fetch_tasks.py --offline           # 重建
python tools/fetch_tasks.py --offline --verify  # 干跑比对，不写盘
```

`--verify` 实测输出（规范化 JSON 去掉 `generatedAt/fetchedAt` 后逐文件比对）：

```
tasks.regular.json       MATCH sha256=4b08b833d7991af6
guides.regular.json      MATCH sha256=2b0c9dcfcafe89d4
tasks.pve.json           MATCH sha256=712d9f633564e7cc
guides.pve.json          MATCH sha256=938040e02e5b24e3
tasks.pvps.json          MATCH sha256=de3b6711ef5089d7
guides.pvps.json         MATCH sha256=5636e8c653f97f0c
season.json              MATCH sha256=a208f96eb3c5d6e5
traders.json             MATCH sha256=dedaf3b74ae643be
sources.json             MATCH sha256=8f93bd3a81e7bc84
index.json               MATCH sha256=8a9dd70e77c3af57
verify: 10 files compared, 0 mismatch
verify: reproducible（除生成时间戳外与现有数据完全一致）
```

与重跑前备份逐文件比对（忽略时间戳）：只有 `tasks.regular/pve/pvps.json` 变化；`guides/index/traders/season/sources` 全部 SAME，说明补字段没有污染其它产物。

统计口径与样本（正则脚本统计生成产物）：

| 模式 | 任务 | 目标 | item 对象 | items-with-count | 可见角标 count>1 |
|---|---|---|---|---|---|
| regular | 503 | 1416 | 15210 | 484 | 198 |
| pve | 499 | 1384 | 15158 | 484 | 198 |
| pvps | 462 | 1304 | 11638 | 472 | 192 |

上游（regular raw）佐证：`count>1` 目标 442 条，其中带 items 263 条（单物品 198、多物品 65），无 items 179 条；单物品 198 条即本次新增可见角标的主要来源。

## 4. 界面实测

- 后端：`python tools/serve.py --port 8796 --host 127.0.0.1 --no-browser --no-position --no-logs --config-dir D:\Temp\r51-cfg`（未使用 8787–8795，未触碰 8791；测毕已停止）。
- 浏览器：真实 Chrome，`http://127.0.0.1:8796/`，模式 PvE，搜索「蛋卷冰淇淋」。
- 结果：Prapor 分组下任务「蛋卷冰淇淋 Ice Cream Cones」物品为 5.45x39 6L31 弹匣，显示角标 `×3`。
- 取证截图：
  - 全窗口（含地址栏与真实 Chrome 控制条）：`docs/r51-task-item-count/badge-icecream.png`
  - 裁剪清晰版（含 Prapor、任务名、×3）：`docs/r51-task-item-count/badge-icecream-crop.png`
- 备注：首次打开时角标为 0，是 Chrome 缓存了旧 JSON；`reload(ignoreCache)` 后角标为 55（当前筛选前）。这也说明数据确实来自本次重跑产物。

## 5. 测试

新增 [tests/test_r51_task_item_count.py](../../tests/test_r51_task_item_count.py)：

1. 单物品目标 → item.count 等于 objective.count；
2. 多物品目标 → 只在 objective 级保留 count；
3. 非物品目标（shoot）→ 不给 item 标数量；
4. 前端角标读取 `it.count` 且用 `.db4-item-n`；
5. 三模式真实产物至少各有一个 `count>1` 的 item。

全量回归：

```
python -m pytest tests -q
1713 passed, 1 skipped in 103.12s (0:01:43)
```

基线 1708 passed / 1 skipped / 0 failed；新增 5 条用例后 1713 passed，无失败，无降级。

## 6. 变更清单

- `tools/fetch_tasks.py`：单物品目标写入 item.count；新增 `--verify` 干跑比对；重跑保留 traders.json 展示增强字段。
- `data/tasks/tasks.regular.json`、`tasks.pve.json`、`tasks.pvps.json`：由脚本重跑生成（非手工改）。
- `tests/test_r51_task_item_count.py`：新增 5 条用例。
- `docs/r51-task-item-count/badge-icecream.png`、`badge-icecream-crop.png`：界面取证。
- 未重建 dist / release，未 git 提交。
