# R19.9 测试结果（test-results.md）

## 自动化

| 套件 | 结果 |
|---|---|
| 全量 pytest | **952 passed, 1 skipped** |
| Node 枪械引擎 | 28 passed, 0 failed |
| 浏览器验收 | `tools/r199_verify.py`（四枪属性条 + 设备型号选择/生成/应用） |

断言迁移（均为依据新需求、语义等价或更强的迁移，无删除/弱化）：
1. `test_r19_8`：手电/激光"功能开关"断言 → 型号选择契约（`cons.deviceIds`、
   `f.devices[key] = (f.devices[key] === id) ? "" : id`、`kind: "deviceId"` 终检、`lockedPaths` 预装）；
2. 版本串断言 R19.8 → R19.9（`index.html` 全部资源 `?v=` 与 `tools/serve.py` 的 `"rev"`）；
3. `test_r19_4` 的 `"基线 "` 字面量与段样式断言原样保留。

## 真实浏览器证据（1920×919）

- 四枪 5 条轨道宽均 **382px 完全一致**，数值列宽一致，**无截断**；
  基准竖线按各自域计算：ERG 71.5→71.5%、RV 82.4→11.77%、RH 227.8→18.22%、初速 605→37.37%。
- 初速四枪均有真实值：MCX 605 / M4A1 922 / AK-74 890 / Glock 17 377 m/s（基准同值同口径）。
- AK-74：手电 9 款、激光 17 款兼容型号；选中 → 生成 → 应用链路可用。
- 控制台 0 错误、外部请求 0。

## 截图

`docs/r19.9-audit/screenshots/`：bars-mcx / bars-m4a1 / bars-ak74 / bars-glock17 /
forge-devices / forge-devices-picked / forge-devices-results / forge-devices-applied。

## 未完成（如实）

1. 未做与 tarkov.dev 的联网交叉核验（离线约束）；本地数值一律标为"本地默认预设计算值"。
2. 3/4 权重方案因转接座取舍无法容纳所选型号——已显式报冲突，但"为必装件预留转接座后再优化其余"
   的更强求解未实现。
3. 瞄具档位列表仍用 R19.8 的 `forgeInstallCompat`（设备列表已改用引擎判据），极端枪械上可能偏宽。
