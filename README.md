# EFT 互动地图（离线免费版）

《逃离塔科夫》互动地图，**免费、离线、无外挂性质**：本地网页版互动地图，双击 `EFTMap.exe` 后显示带进度的启动框，就绪后自动打开浏览器进入地图界面。

> 当前状态：**开发中（M1 进行中）**。安装、拉数据、启动与定位配置的完整说明将在功能完成后补入本文件。

## 与游戏的关系

本项目与游戏进程**零交互**：不读取游戏内存、不注入进程、不提供透视/自瞄等任何外挂类功能。实时定位采用社区公开做法——**监听截图目录并解析文件名中的坐标**。

## 文档

- 设计规格：[docs/superpowers/specs/2026-10-17-eft-interactive-map-design.md](docs/superpowers/specs/2026-10-17-eft-interactive-map-design.md)
- 实施计划：[docs/superpowers/plans/2026-10-17-eft-interactive-map-plan.md](docs/superpowers/plans/2026-10-17-eft-interactive-map-plan.md)

## 数据来源与许可

| 来源 | 内容 | 许可 |
| --- | --- | --- |
| [the-hideout/tarkov-dev](https://github.com/the-hideout/tarkov-dev) | 地图配置、翻译、标注数据 | MIT |
| [json.tarkov.dev](https://json.tarkov.dev/) | 标注点原始数据 | 源自 tarkov.dev 社区数据 |
| [the-hideout/tarkov-dev-svg-maps](https://github.com/the-hideout/tarkov-dev-svg-maps) | 底图 SVG | **CC BY-NC-SA 4.0**（署名 + 非商业 + 同许可） |

`assets/maps/` 下的底图沿用 CC BY-NC-SA 4.0，因此**本项目不得用于商业用途**。

## 免责

《逃离塔科夫》（Escape from Tarkov）商标与全部原始美术归 Battlestate Games 所有。本项目不含任何游戏资源文件，仅供个人免费使用。

本项目**永久免费、严禁售卖**。仓库不含任何游戏本体文件，也不提供任何作弊、修改游戏或影响对局公平性的功能。
