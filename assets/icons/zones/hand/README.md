# 手绘防护部位图 · 投放目录

把你自己画的部位图放进**这个目录**（`assets/icons/zones/hand/`），然后执行：

```bash
python tools/gen_zone_icons.py
```

工具会**自动按游戏数据拼出全部 33 张组合图**，覆盖 `assets/icons/zones/zone-*.png`。

## 要画哪些（11 张）

| 文件名 | 部位 | 覆盖的游戏 zone |
|---|---|---|
| `头顶.png` | 颅顶 | ParietalHead |
| `后脑.png` | 头后部 | BackHead |
| `面部.png` | 脸 | HeadCommon |
| `下颚.png` | 下巴/护颚 | Jaw |
| `眼部.png` | 护目镜区 | Eyes |
| `耳部.png` | 护耳 | Ears |
| `颈部.png` | 前后颈 | NeckFront / NeckBack |
| `肩部.png` | 左右上臂 | LeftUpperArm / RightUpperArm |
| `胸部.png` | 上胸+下胸+上背+下背+前后插板兜 | RibcageUp / RibcageLow / SpineTop / SpineDown / Plate_* |
| `侧面.png` | 左右腰侧 | LeftSideChestDown / RightSideChestDown / Plate_*_side_* |
| `腹股沟.png` | 骨盆+后腰 | Pelvis / PelvisBack |

## 画图要求

- **透明底 PNG**，只画该部位本身（画布紧凑即可，不必对齐）。
- 大小随意 —— 工具会**等比缩放**后放到人体正确位置，不会变形。
- 想多画就多画，少画就少画：**画一张顶一张**，没画的部位继续沿用现有素材版本，不会开天窗。
- 支持别名命名（`胸.png`、`chest.png`、`侧身.png` 等都能认）。

## `_参考/` 目录

放的是从现有素材抠出的**描摹底稿**（每部位已放大 8 倍），可以直接照着描。
这个子目录里的图不会被当作手绘稿使用。

## 注意

**不要**直接把图丢进上级 `assets/icons/zones/` —— 生成器每跑一次会清空该目录重建，手绘稿务必放这里。
