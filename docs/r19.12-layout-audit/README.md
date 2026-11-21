# R19.12 · 右侧候选栏修复（已并入 R19.11 合并修复）

本目录不重复存证：R19.12 任务的六项要求（当前槽位信息移到右栏顶部、隐藏不兼容复选框、
整条红色斜纹、不可安装、M4 一体式枪托/缓冲管、统一兼容性口径）已在
**`docs/r19.11-merged-audit/`** 中实现并验收。

- 交付报告：`../r19.11-merged-audit/report.md`（第 6 节专门覆盖本任务）
- 截图：`../r19.11-merged-audit/screenshots/D1…D9-*.png`、`Z-1384-panel.png`
- DOM / 样式测量：`../r19.11-merged-audit/panel-compat.json`、`m4-stock-chain.json`
- 自动化测试：`tests/test_r19_11_round.py`（右栏顺序 / 斜纹 CSS / 隐藏过滤 / 统一判据 / M4 枪托结构）

原任务书要求的路径 `docs/r19.12-layout-audit/` 保留本索引，避免同一批证据存两份。
