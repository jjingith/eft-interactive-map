# R19.3 测试与浏览器验收结果

## 自动化测试（2026-10-24/25 实跑）

| 套件 | 命令 | 结果 |
|---|---|---|
| 全量 Python | `python -m pytest -q` | **894 passed, 1 skipped** |
| Node 引擎 | `node tests/js/gun_builder_test.js` | **28 passed, 0 failed** |
| 公式验证 | `python tools/_verify_forge.py` | 黄金向量 11/11；373 预设回归（见 hidden-stats-formulas.md） |
| R19.3 新增 | `tests/test_r19_3_round.py` | 7 条（整枪图映射/选中黄色/对比度规则/公式接入/构建标记） |

旧测试迁移说明（无删减、无弱化）：
- `test_r19_2.test_hidden_attributes_in_engine`：R19.2 断言 OverSwing/EED/ArmStamina 为
  missing——R19.3 按任务要求实现后该断言过时，迁移为**更强**断言（黄金向量 11 组 +
  verified 字段 + MOA 1.99 + ADS 仍 estimated）。
- `test_r19_2.test_white_icons_wired_in_gun_view`：浏览卡从白底物品图标升级为整枪渲染，
  断言更新为 `setGunFullImg` + `setGearIcon` 回退链。
- `test_r19_2.test_build_marker_r19_2`：版本标记随轮次推进至 R19.3。
- 第三方参考文件 `build-cache/r193-eftforge/test_calculations.py`（EFTForge 的测试，
  AGPL 研究留档）被 pytest 误收集，改名 `eftforge_test_calculations.py`。

## 真实浏览器验收（tools/r193_accept.py，_accept.json）

| 项 | 1920×1080 | 1264×705 |
|---|---|---|
| P1 整枪卡 | 163 张卡，161 指向整枪渲染，12/12 抽查加载成功 | 同，无横向溢出 |
| P2 选中态 | 悬停 rgb(255,243,196) → 选中 rgb(255,233,168)+黑字 → 切视图返回仍黄 → 换选新卡黄 | 同 |
| P3 对比度 | 审计 0 处低对比（阈值 2.6:1） | — |
| P4 主图 | 进入=官方预设渲染 → 换件=标签"已改动 N 件"+差异条 → 恢复默认=回官方渲染 → 换枪无残留 | 同 |
| P5 隐藏属性 | TED/OverSwing/Sway/ArmStamina verified；力量 10→30 ArmStamina 55.1→60.1s | — |
| P6 布局 | FORGE 461px / 中栏 653px / 候选 806px；各区域边界见 layout-comparison.md | 无横向溢出 |
| 控制台 / 网络 | 0 错误 / 0 外部请求 | 0 / 0 |

截图目录 `screenshots/`：p1-caliber/p1-class/p1-1264（整枪浏览）、p2-1~p2-4（选中全流程）、
p3（审计）、p4-ak74-initial/mod1/mod2/reset、p4-m4a1（换枪）、p5-hidden-stats、
p6-builder-1920/1264、ref-vs-local-1920/1264。
对照图：`weapon-image-before-after.png`、`selected-hover-states.png`（任务书要求的两个命名文件）。

## 构建期 vs 运行期网络

- 构建期（一次性，走代理 7896）：EFTForge 源码与黄金向量（研究留档）、373 张预设整枪
  base-image（`build-cache/gun-images-src/`）。
- 运行期：**0 外部请求**（CDP Network 抓包验证，两视口）。

## 已知边界（如实）

1. 2 把枪无整枪图（上游 404）：HK 416A5 RAL8000、FN P90 灾厄——回退白底物品图标。
2. ADS 时间仍是估算（官方公式在客户端，公开渠道不可得）。
3. 霰弹枪 MOA 与游戏内显示存在约 2 倍系统性差异（31/31 样本一致），引擎内标估算。
4. 任意改装组合的照片级整枪合成无法离线实现（无几何来源），以"预设精确匹配整枪渲染 +
   改动标签 + 差异条"替代，不做假合成。
