# R19.3 完整枪械图像审计（P1/P4）

## 数据链（根因证据）

| 项 | 值 |
|---|---|
| AK-74 枪械 id | `5bf3e03b0db834001d2c4a9c` |
| 旧浏览卡图片 | `assets/icons-items/5bf3e03b0db834001d2c4a9c.webp` —— 64px **本体（机匣）**图，253×64 截断在机匣尾 |
| 默认预设 id | `5c0c1ce886f77401c119d014`（data/gun-stats.json guns[id].preset，163/163 枪齐） |
| 完整渲染源 | `https://assets.tarkov.dev/5c0c1ce8…-base-image.webp`（316×127 透明底，含木托） |
| 新产物 | `assets/guns-full/{gunId}.png`（161 张）+ `assets/presets-full/{presetId}.png`（368 张）+ manifest |

结论：**不是映射错误、不是预设没加载**——EFT 枪托/握把是独立 mod，本体图天然不含枪托；
项目此前没有任何完整枪械图像资源。本轮用官方预设渲染补齐（不做配件叠放假合成）。

## 12 枪抽查审计表

| 枪械名称 | 枪械 ID | 图片来源 | 对应基础预设 | 是否完整 | 是否使用机匣图 | 验证结论 |
|---|---|---|---|---|---|---|
| AK-74 5.45x39 突击步枪 | 5bf3e03b0db834001d2c4a9c | assets/guns-full/5bf3e03b0db834001d2c4a9c.png | 5c0c1ce886f7（AK-74 5.45x39 突击步枪） | 是（预设整枪渲染 364x112，宽高比 3.25） | 否 | 通过 |
| 柯尔特 M4A1 5.56x45 卡宾枪 | 5447a9cd4bdc2dbd208b4567 | assets/guns-full/5447a9cd4bdc2dbd208b4567.png | 5af08cf886f7（柯尔特 M4A1 5.56x45 卡） | 是（预设整枪渲染 290x112，宽高比 2.59） | 否 | 通过 |
| HK MP5 9x19 冲锋枪（海军三发点射） | 5926bb2186f7744b1c6c6e60 | assets/guns-full/5926bb2186f7744b1c6c6e60.png | 59411aa786f7（HK MP5 9x19 冲锋枪（海军） | 是（预设整枪渲染 241x112，宽高比 2.15） | 否 | 通过 |
| 莫辛-纳甘 7.62x54R 栓动式步枪（狙击型） | 5ae08f0a5acfc408fb1398a1 | assets/guns-full/5ae08f0a5acfc408fb1398a1.png | 5b8683a486f7（莫辛-纳甘 7.62x54R 栓动式） | 是（预设整枪渲染 400x68，宽高比 5.88） | 否 | 通过 |
| MP-133 12 铅径泵动式霰弹枪 | 54491c4f4bdc2db1078b4568 | assets/guns-full/54491c4f4bdc2db1078b4568.png | 584148f22459（MP-133 12 铅径泵动式霰弹枪） | 是（预设整枪渲染 400x79，宽高比 5.06） | 否 | 通过 |
| 马卡洛夫9x18PM 手枪 | 5448bd6b4bdc2dfc2f8b4569 | assets/guns-full/5448bd6b4bdc2dfc2f8b4569.png | 584149672459（马卡洛夫9x18PM 手枪 默认） | 是（预设整枪渲染 139x112，宽高比 1.24） | 否 | 通过 |
| 德拉贡诺夫 SVDS 7.62x54R 半自动狙击步 | 5c46fbd72e2216398b5a8c9c | assets/guns-full/5c46fbd72e2216398b5a8c9c.png | 5c98be1e86f7（德拉贡诺夫 SVDS 7.62x54） | 是（预设整枪渲染 400x69，宽高比 5.80） | 否 | 通过 |
| SV-98 7.62x54R 栓动式狙击步枪 | 55801eed4bdc2d89578b4588 | assets/guns-full/55801eed4bdc2d89578b4588.png | 58414a162459（SV-98 7.62x54R 栓动式） | 是（预设整枪渲染 400x72，宽高比 5.56） | 否 | 通过 |
| RPK-16 5.45x39 轻机枪 | 5beed0f50db834001c062b12 | assets/guns-full/5beed0f50db834001c062b12.png | 5c0d1ec986f7（RPK-16 5.45x39 轻机枪） | 是（预设整枪渲染 400x106，宽高比 3.77） | 否 | 通过 |
| AS VAL“巨浪” 9x39 特种突击步枪 | 57c44b372459772d2b39b8ce | assets/guns-full/57c44b372459772d2b39b8ce.png | 5841482e2459（AS VAL“巨浪” 9x39 特种） | 是（预设整枪渲染 400x101，宽高比 3.96） | 否 | 通过 |
| 雷明顿 Model 870 12铅径泵动式霰弹枪 | 5a7828548dc32e5a9c28b516 | assets/guns-full/5a7828548dc32e5a9c28b516.png | 5ac4ad7586f7（雷明顿 Model 870 12铅径） | 是（预设整枪渲染 400x84，宽高比 4.76） | 否 | 通过 |
| Glock 17 9x19 手枪 | 5a7ae0c351dfba0017554310 | assets/guns-full/5a7ae0c351dfba0017554310.png | 5a88acfb86f7（Glock 17 9x19 手枪 默） | 是（预设整枪渲染 158x112，宽高比 1.41） | 否 | 通过 |
| FN P90 灾厄 | `6a78b7f8c2016eb33e0027cd` | 回退：白底物品图标 | 上游 404 | — | 是（回退态） | **缺失**，见下 |

浏览器核对：`tools/r193_accept.py` P1 spot —— 12/12 张整枪图加载成功（naturalWidth 大于 0），
截图 `screenshots/p1-caliber-fullguns.png`、`p1-class-view.png`、`p1-1264-caliber.png`。

## 全量 163 把覆盖情况

| 项 | 数量 |
|---|---|
| 枪械总数（data/gunslots.json） | 163 |
| 有 defaultPreset 且出图 | **161（98.8 percent）** |
| 缺失 | **2**：HK 416A5 RAL8000（`6a15ae2ae5267ba21c07f98f`）、FN P90 灾厄（`6a78b7f8c2016eb33e0027cd`）——上游 base-image HTTP 404（与 R18.2 起已知的 4 件 404 同源），运行期回退白底物品图标 |
| 官方预设整枪图 | 368/373（缺 5：上述 2 枪的预设 + 3 条合成 preset 占位 id `707265736574…`，上游无对应渲染） |

产物体积：guns-full 4.7MB + presets-full 11MB；源缓存 `build-cache/gun-images-src/`（gitignore）。
