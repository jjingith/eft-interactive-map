# R19.3 瞄准类属性公式审计（P5）

> 来源：**EFTForge** `github.com/SouthHorizons76/EFTForge`（AGPL-3.0-or-later）。
> 已实际读取源码（非 README）：`backend/stats.py::_compute_stats / _calc_aiming_stats`、
> `frontend/modules/calculations.js`、`frontend/modules/stats-panel.js`、
> `backend/tests/data/stat_formula_golden.json`（11 组黄金向量）、`backend/tests/test_calculations.py`。
> 该项目自述这些公式"reproduces the game exactly"，数据源为 tarkov.dev 与 SP-Tushonka。
> **许可证说明**：本项目实现为**独立重写**（公式/算法本身不受版权保护，未复制其代码文字，
> 常量与结构为游戏机制事实）；本地副本仅存于 `build-cache/r193-eftforge/`（gitignore，作研究留档）。
> 若未来直接搬运其代码，须按 AGPL-3.0-or-later 开源并注明出处。

## 实现的公式（本地位置：`gun_builder.js compute()`，注释里同步记录）

### 1. 有效人机（EFTForge "effective ergo"，游戏用于瞄准的值）

```
eff = max(0, ergo × (1 + b))     # b = 装备人机修正（头盔/护甲等，十进制）
```
单位：人机点数。输入：整枪人机（373 预设验证过 verified）、b。

### 2. TrueErgoDelta（TED）—— 与过摆阈值的人机余量

```
ergoNeeded = W ≤ 3kg ? 0 : 100 × (1 − 3/W)
TED = min(max(eff,0),100) − ergoNeeded        # 负值 = 已会过摆
```
单位：点。来源：stats.py `true_ergo_delta()`。

### 3. OverSwing（过摆判定 + 摆动强度）

```
overswing = TED < 0
aimSway   = clamp(( W×(1−clamp(eff,0,100)/100) − 3 ) / (7−3), 0, 1) × 100%
```
3kg 开始过摆、7kg 满幅（EFTForge 页面描述与 stats.py 常量 `SWAY_START_KG/SWAY_FULL_KG` 一致）。
单位：布尔 + 百分比。

### 4. ArmStamina（手臂耐力持续时间）

```
armStamina = 80 / ( √( max(W×(1−√eff/25), 0) ) × 1.1 × (1 − 力量级×0.004) )   秒
```
80 点池（stats.py `ARM_STAMINA_CAPACITY`），0.4%/级 力量减免。
**显式假设**：站立、满水分（stats.py 注释）；力量等级是**模拟器输入**，FORGE 面板可调
（默认 10 = EFTForge 默认），界面标注当前值——不偷偷固定。

### 5. 精度 MOA（R19 以来"无法换算"的遗留问题，本轮解决）

```
MOA = (100/2.9089) × COI × (1 − ΣaccuracyModifier/100) × 弹药系数
COI = 已装枪管的 centerOfImpact（覆盖枪械基础值，EFTForge 同规则）
弹药系数：acc ≤ 0 → (100+|acc|)/100；acc > 0 → 100/(100+acc)
```
stats.py `MOA_K = 100/2.9089`（度 → MOA 换算）。

### 6. 满弹匣重量（影响 TED/过摆/耐力）

已装弹匣 cap × 所选弹药单发重量计入整枪重量后重算（stats.py `apply_full_mag_ammo` 同规则）。

### 7. ADS 时间 —— **仍未获得官方公式（如实）**

检索路径与结论：
- EFTForge 全库（475 文件）grep ads/aimTime/aimingTime：**无该指标**（其官网也未列）；
- db4tarkov 的 "ADS Time (beta)" 自标 beta、公式未公开；
- SPT 服务器资料与 tarkov.dev：无可核实的 AimSpeed 曲线系数（该公式在游戏客户端内）。
- 缺失的具体变量：客户端 AimSpeed 随人机/重量的分段曲线系数。
保留 R19.2 的社区拟合式 `max(0.2, 2.35 − 0.028 × eff)`，**conf = estimated**，
悬停说明单点校验（db4 AK-74 预设 ergo 67.5 → 0.460 vs 0.465s）与"非官方"性质。

### 8. 爆头有效距离 —— 几何估算（同 R19.2，假设已写明）

`0.08m(头部半径) / tan(散布角)`；不代表游戏命中概率模型，conf = estimated。

## 验证结果（`tools/_verify_forge.py`，node 运行引擎逐条重算）

### A. EFTForge 黄金向量（11 组，含负值/边界/力量 0~51/装备修正 ±0.35）

| 指标 | 结果 |
|---|---|
| TrueErgoDelta | 11/11，误差 < 0.01 |
| OverSwing 判定 | 11/11 一致 |
| AimSway | 11/11（0.0/0.0098/1.0 全中） |
| ArmStamina | 11/11（含 null 边界 case），误差 < 0.011 |

### B. 373 条官方预设回归（游戏内真值来自 data/gun-presets.json）

| 字段 | n | 平均残差 | 中位绝对误差 | p95 | 最大 |
|---|---|---|---|---|---|
| 人机工效 | 373 | +0.002 | 0.000 | 0.10 | 3.0 |
| 垂直后坐力 | 373 | −0.016 | 0.30 | 0.50 | 0.5 |
| 水平后坐力 | 373 | −0.014 | 0.30 | 0.50 | 0.5 |
| **MOA** | 373 | — | **0.01** | 13.77 | 20.66 |
| MOA（非霰弹 342 样本） | 342 | — | **0.01** | 3.43 | 8.6 |
| MOA（霰弹 31 样本） | 31 | — | 13.77（≈2× 系统性口径差异） | 20.65 | 20.66 |

结论：TED/OverSwing/AimSway/ArmStamina/**非霰弹 MOA** 全部按 verified 展示；
**霰弹枪的 MOA 引擎内单独降级为估算**（上游霰弹枪管 COI 与游戏内显示存在约 2 倍
口径差异，31 样本一致，机制未知，已写进字段 why）。

### C. 浏览器实测（accept P5）

- M4A1 默认装配：TED 72.0、OverSwing 否、Sway 0.0%、ArmStamina 55.1s、MOA 6.88
- 力量等级 10 → 30（FORGE 面板输入）：ArmStamina 55.1 → **60.1s**（参数生效）
- Glock 17：TED 91.0、MOA 11.69、ArmStamina 98.2s
- 截图 `screenshots/p5-hidden-stats.png`

## 多版本风险

公式提取自 EFTForge 当前版本（适配 EFT 0.16+ / 2025-2026 补丁线）；早期补丁
（0.12 时代社区过摆研究）的系数可能不同——本项目只采用当前版本一套，未混用旧公式。
游戏后续补丁若调整 3kg/7kg 阈值或耐力系数，需更新 `gun_builder.js` 中同名常量
（已集中放在公式注释旁，便于核对）。
