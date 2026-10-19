# EFT 互动地图

> 《逃离塔科夫》互动地图：**免费、离线、无外挂性质**——底图与标注数据全部内置，运行期**不联网**。
> 官方发布页：<https://github.com/jjingith/eft-interactive-map>

双击 `EFTMap.exe` → 弹出「设置与启动」小窗 → 点**启动 WebUI**，跑完四步后自动打开浏览器进入地图界面
（勾上「自动启动 WebUI」则开窗即自动启动）。默认与游戏进程**零交互**：只读游戏自己写在磁盘上的截图与日志文件。
唯一的例外是可选的**自动截图**（默认关闭），它用模拟按键让游戏自己截图。

---

**目录**

- [快速开始](#快速开始)
- [界面用法](#界面用法)
- [收录地图](#收录地图)
- [实时定位 / 日志监控 / 自动截图](#实时定位--日志监控--自动截图)
- [从源码打包 exe](#从源码打包-exe)
- [出发布包（GitHub Releases）](#出发布包github-releases)
- [目录结构](#目录结构)
- [自测](#自测)
- [已知限制](#已知限制)
- [免费声明](#免费声明)
- [许可](#许可)
- [打赏](#打赏)
- [详细用法与数据（docs/USAGE.md）](docs/USAGE.md)

---

## 快速开始

### 方式 A：双击发布包（推荐）

1. 到 [Releases](https://github.com/jjingith/eft-interactive-map/releases) 下载发布包（三个版本任选，见下表），解压到任意目录；
2. 双击 `EFTMap.exe`，在「设置与启动」小窗里核对目录与开关（留空即用自动定位的结果）；
3. 点「启动 WebUI」——「检查数据 → 启动本地服务 → 载入资源 → 打开浏览器」四步跑完后，
   浏览器自动打开 `http://127.0.0.1:8787/`。

改完设置可以直接点小窗底部的「**保存配置**」再启动（表单本来也会在失焦 / 勾选时自动保存，
这个按钮只是为了让你看见「已经存好了」）。设置不会因为重新打包或换个发布包目录而丢失——
配置和自定义提示音存在**用户目录** `%APPDATA%\EFTMap\`（首次启动会自动从软件目录迁移旧配置，不删原文件）。

无需安装 Python，无需联网。全程只监听本机 `127.0.0.1`。

发布包有**三个版本**（同一份程序，只是分发 / 开界面方式不同）：

| 版本 | 形态 | 界面开在哪 |
| --- | --- | --- |
| `EFTMap-Setup-*.exe` | **一键安装**：向导装到 `%LOCALAPPDATA%\EFTMap`，自动建开始菜单 / 桌面快捷方式，并写出「控制面板 → 程序和功能」的卸载项 | 系统默认浏览器 |
| `EFTMap-Portable-*.zip` | **解压即用**：解压到任意目录，双击 `EFTMap.exe` | 系统默认浏览器 |
| `EFTMap-AppWindow-*.zip` | **解压即用（加壳版）**：同上，但界面开在一个**独立应用窗口** | 无地址栏 / 无标签页的独立窗口，用系统自带的 Edge 或 Chrome 内核（都没有时退回默认浏览器） |

加壳版里的 `EFTMap.exe` 行为与普通版完全一致，只是把「打开界面」改成开独立应用窗口——
判定方式就是资源目录里有没有 `appmode.flag`（发布包里已放好），源码运行时可加 `--app-window` 试同一效果。

### 方式 B：从源码运行

需要 Python 3.9+（开发环境实测 3.14），**不使用任何第三方库**。

```bash
# 1) 首次使用：联网拉取一次数据与底图（构建期唯一一次联网）
python tools/fetch_data.py

# 2) 启动（启动框 + 自动打开浏览器）
python tools/launcher.py
```

可选参数：

```bash
python tools/launcher.py --port 8788      # 换端口
python tools/launcher.py --no-browser     # 只起服务，不自动开浏览器
python tools/launcher.py --screenshots "D:\...\Screenshots"   # 指定截图目录（默认自动探测）
python tools/launcher.py --game-dir "E:\EFT"                  # 指定游戏目录（默认自动探测）
python tools/launcher.py --config-dir path\to\dir             # 配置与 sounds/ 落到别处（默认 %APPDATA%\EFTMap）
```

### 方式 C：只跑静态站点

不想用启动框、只想调试前端时：

```bash
python tools/serve.py                      # 默认 127.0.0.1:8787，自动开浏览器
python tools/serve.py --no-browser --port 8790
```

> 不要用 `file://` 直接打开 `index.html`：浏览器会拦截本地数据读取，页面会提示改用本地服务。

---

## 界面用法

网页框架是 Windows XP（Luna）风格的浅色窗体（菜单栏 + 左侧栏 + 地图区），地图区与上面的标记保持深色，方便看清底图与彩色标注。

- **顶部「战局与任务」菜单**：战局阶段、任务计数、自动截图 / 自动删除状态都收在这个下拉面板里，点开才展开。
- **地图切换**：左侧点选切换地图，上次看的那张会被记住。
- **平移 / 缩放**：按住左键拖动平移，滚轮缩放（0.5×–20×），右上角「复位」回整图；走矢量重绘，**放大不会变糊**。
- **自动居中 / 定位自动缩放**：实时定位一变就自动平移过去，手动拖动即切到「已锁定」，点一下恢复；可选按最近一次手动缩放比例自动缩放。**只在截图目录里出现新截图时才定位一次**，没新截图不动视角。
- **自动截图**（**默认关**）：在战局中且游戏窗口在前台时，按间隔模拟按下截图键，让游戏自己写图。
- **自动删除截图**（**默认关**）：读出位置后把多余的老截图删掉，只保留最新 1 张供定位。
- **声音提示**：战局开始 / 开始加载战局 / 开始匹配三个环节可各自选用自定义音频，不选则用内置；每行都有**「试听」**按钮，听到的就是当前配置生效的那个音。
- **图例 / 图层**：左侧按 6 组分类开关，每行显示该标记在当前地图上的数量；高级资源点另有独立分组（总开关 + 8 个子类）。
- **搜索 / 钉选 / 路线**：按名称子串聚合搜索，可把结果「钉选」到地图，或按直线连成「导航路线」。
- **楼层切换 / 标记浮窗 / 状态条**：多层图可切层；点任意标记在地图区**左上角固定位置**弹出简略浮窗（淡入淡出，物资类标记会带对应物资小图标）、左侧「标记详情」给完整信息；底部状态条显示当前地图、光标世界坐标与实时定位状态。
- **图标整体缩放**：右上角「图标」滑条（50%–300%）统一调整地图上**全部标记图标**的大小——4K 屏图标偏小就往右拖（本地保存，下次启动沿用）。**地名不受它影响**，跟着地图缩放走。

> 逐项细节见 [docs/USAGE.md](docs/USAGE.md)。

---

## 收录地图

内置 12 张常用图：塔科夫街区、中心区、海关、工厂、立交桥、实验室、迷宫、灯塔、储备站、海岸线、码头、森林
（各类标注合计约 1.2 万条；其中 10 张为上游矢量 SVG 底图，实验室 / 迷宫由构建期按上游瓦片拼成合成 SVG）。

> 各图标注数量、容器分类与全部数据细节见 [docs/USAGE.md](docs/USAGE.md)。

---

## 实时定位 / 日志监控 / 自动截图

这三块都只**读游戏写在磁盘上的截图与日志**，运行期**不联网**，也不读内存、不注入进程、不做透视 / 自瞄——**不是外挂**。

- **实时定位（已实现）**：轮询截图目录、解析**截图文件名里的坐标与朝向**，经 SSE 推给页面，以青色光点 + 朝向箭头显示玩家位置，支持自动居中与手动锁定。
- **日志监控（已实现）**：跟随游戏目录下 `Logs` 里最新的会话，从日志文本识别战局生命周期与任务事件，用于**进图自动切图**与统计本局任务（只统计本局、无条件级进度、不跨会话累计）。
- **自动截图（可选，默认关）**：在战局中且**游戏窗口在前台**时按间隔模拟按下游戏截图键，让游戏自己写图；配套的「自动删除截图」开关在读出位置后只保留最新 1 张。

---

## 从源码打包 exe

```powershell
# 普通 onedir（只出 dist\EFTMap）
powershell -ExecutionPolicy Bypass -File build\build.ps1
```

`build.ps1` 产出 `dist\EFTMap\EFTMap.exe`（PyInstaller onedir，站点文件随包分发，双击即用）；
脚本会在打包后自检 exe 与站点文件是否齐全，缺一即报错退出。

PyInstaller 仅在**构建期**需要，运行期不需要。

---

## 出发布包（GitHub Releases）

```powershell
# 发布三件套（release\ 下：Portable zip / AppWindow zip / Setup exe）
powershell -ExecutionPolicy Bypass -File build\build_release.ps1
```

`build_release.ps1` 先跑一遍 `build.ps1`，再在 `release\` 生成三个产物：

| 文件 | 形态 | 界面开在哪 |
| --- | --- | --- |
| `EFTMap-Portable-0.1.0.zip` | **解压即用**（约 20.0 MB）：解压到任意目录，双击 `EFTMap.exe` | 系统默认浏览器 |
| `EFTMap-AppWindow-0.1.0.zip` | **加壳版**（约 20.0 MB）：解压即用，界面开在**独立应用窗口** | 无地址栏 / 无标签页的独立窗口 |
| `EFTMap-Setup-0.1.0.exe` | **一键安装**（约 31.7 MB）：向导装到 `%LOCALAPPDATA%\EFTMap` + 快捷方式 + 卸载项 | 系统默认浏览器 |

出包方式：用 PowerShell 自带的 `Compress-Archive` 打两个 zip（加壳版那份多落一个 `_internal\appmode.flag`），
并用 `tools\installer.py` 打一个**单文件安装器 exe**（`dist\EFTMap` 作为 `payload` 打进包，装到位后再建快捷方式与卸载项）。

**版本号唯一真源在 `tools\serve.py` 的 `VERSION`**（当前 `0.1.0`）：`build_release.ps1` 从这里读出版本号来命名三件套，
改这一处即可重新出包。两个脚本都只用 PowerShell 自带命令，不装额外工具；PyInstaller 仅在**构建期**需要。

> 打包会先整个删掉 `dist\EFTMap`。**设置不受影响**：配置与 `sounds/` 在 `%APPDATA%\EFTMap\`，
> 不在发布包目录里，所以重新打包、换到别的目录解压都不会丢设置。

---

## 目录结构

```
eft-interactive-map/
├── index.html / style.css / app.js   # 前端（原生 JS/CSS，零依赖，无构建）
├── data/                             # maps.json（schema 7：图层 + 楼层波段 + 容器分类 + 钥匙名 + 高级资源点（含显卡）+ 瓦片图）+ meta.json
├── assets/maps/                      # 12 张底图 SVG（其中实验室 / 迷宫是构建期用 tiles/ 下的瓦片拼出的合成 SVG）
├── assets/icons/                     # 217 个图标素材（64×64 透明 PNG，由 tools/iconize.py 从 wiki 截图抠图导出）
├── tools/
│   ├── fetch_data.py                 # 构建期：拉数据与底图（联网一次）
│   ├── iconize.py                    # 构建期：把用户提供的原图抠成 assets/icons 的透明 PNG（备忘 / 可复现）
│   ├── coord.py                      # 世界坐标 → SVG 坐标的仿射系数
│   ├── floors.py                     # 构建期：由上游 layers 推出楼层波段与可选楼层表
│   ├── serve.py                      # 运行期：静态服务 + 健康检查 + SSE 实时定位 / 日志事件 / 自动截图 + 自动删除（VERSION 定义在此）
│   ├── screenshot.py                 # 运行期：截图文件名 → 坐标 / 朝向（纯解析，不读图片）+ 清理挑选规则
│   ├── eftlog.py                     # 运行期：跟随 Logs 会话，日志行 → 战局 / 任务事件（含截图键同步）
│   ├── keyinput.py                   # 运行期：模拟按键（SendInput）+ 前台窗口进程判定
│   ├── config.py                     # 运行期：配置读写（%APPDATA%\EFTMap\eftmap.config.json）+ 自定义提示音导入 + 旧位置迁移
│   ├── launcher.py                   # 运行期入口：设置与启动小窗（含「保存配置」按钮、自动截图/自动删除设置与按键同步）+ 四步编排
│   └── installer.py                  # 构建期：一键安装器（装到 %LOCALAPPDATA%\EFTMap + 快捷方式 + 卸载项），由 build_release.ps1 打成单文件 exe
├── build/build.ps1                   # PyInstaller 打包脚本（onedir）
├── build/build_release.ps1           # 发布三件套：Portable zip / AppWindow zip / Setup exe
├── tests/                            # pytest 单测（520 条，全离线）
├── docs/USAGE.md                     # 详细用法与全部数据（逐项详解 / 各图计数 / 容器分类）
├── docs/superpowers/                 # 设计规格与实施计划
└── release/                          # 发布产物（已 gitignore，不进仓库）
```

---

## 自测

```bash
python -m pytest tests -q     # 全量单测 → 520 passed, 1 skipped
node --check app.js           # 前端语法检查
```

- 覆盖范围：启动器编排（含加壳版开独立应用窗口）、安装器、配置持久化、日志解析、截图解析与删除、
  楼层与数据管道、服务端接口。
- **只有 `tools/fetch_data.py` 联网**，测试用本地样本与桩件，不触网。
- 坐标推导由不变量锁定：底图矩形的两个角点必须精确映射到 `(0,0)`/`(W,H)`，
  且每张图 ≥ 90% 的标注点落在 `viewBox` 内（推导写错会立刻失败）。
- 数据管线幂等：数据就绪时再跑一次不联网；拉取失败**不破坏已有数据**。

---

## 已知限制

- **不是外挂，但模拟按键有误判风险**：自动截图会向游戏发送模拟输入，可能与 BattlEye 产生误判；本工具不读内存、不注入进程、不改游戏文件，但**不保证**不被误判。
- **导航只是方向参考**：本工具没有导航网格（NavMesh），路线是直线，跨楼层会「穿墙」。
- **自动截图需游戏窗口在前台**：游戏不在前台时不发键（否则按键会打到别的窗口），更适合「游戏全屏、地图放副屏 / 手机上看」。
- **灯塔 / 森林 / 迷宫是单层图**：不显示楼层列表；其余 9 张为多层图。
- **码头**在上游数据里没有撤离点与地名，只有出生点（默认关闭）、散落物资、危险区、上锁与 Boss 刷新点。
- **实验室 / 迷宫没有矢量底图**：上游只给瓦片，本项目在构建期拼成合成 SVG；破冰船等其余瓦片图不收录。

---

## 免费声明

本软件**永久免费**，严禁任何形式的售卖、转卖或捆绑收费。若你是付费买到的，说明你被骗了——
请到官方发布页免费获取。不设付费版、不卖激活码、不提供「付费优先支持」。

《逃离塔科夫》（Escape from Tarkov）的商标与全部原始美术归 **Battlestate Games** 所有。
本项目不含任何游戏资源文件，不提供任何作弊、修改游戏或影响对局公平性的功能，也不与游戏进程发生任何交互，仅供个人免费使用。

版权所有人：**jiajun zhou**　·　官方发布页：<https://github.com/jjingith/eft-interactive-map>

---

## 许可

| 来源 | 内容 | 许可 | 义务 |
| --- | --- | --- | --- |
| [the-hideout/tarkov-dev](https://github.com/the-hideout/tarkov-dev) | 地图配置、翻译 | **MIT** | 保留版权与许可声明 |
| [json.tarkov.dev](https://json.tarkov.dev/) | 标注数据（撤离 / 转移 / 出生点 / 物资 / 危险区 / 上锁 / Boss / BTR）与楼层波段 | tarkov.dev 社区公开数据 | 署名 tarkov.dev |
| [json.tarkov.dev](https://json.tarkov.dev/) | 物品中文名（`/{mode}/items_zh`）：把上锁的门里的钥匙物品 id 解析成中文钥匙名，并筛出「高级资源点」的物品池 | tarkov.dev 社区公开数据 | 署名 tarkov.dev |
| [the-hideout/tarkov-dev-svg-maps](https://github.com/the-hideout/tarkov-dev-svg-maps) | 底图 SVG | **CC BY-NC-SA 4.0** | 署名 + **非商业** + 同许可再分发 |
| [assets.tarkov.dev](https://assets.tarkov.dev/) | 实验室 / 迷宫的**瓦片底图**（构建期按上游 `transform` / `bounds` 拼成合成 SVG，原样再分发） | tarkov.dev 社区公开数据 | 署名 tarkov.dev + **非商业** |

- 每个来源的 URL、sha256 与许可都记在 `data/meta.json` 里。
- `assets/maps/` 下的底图沿用 **CC BY-NC-SA 4.0**，因此**本项目的底图部分不得商用**，
  再分发时必须保持同一许可并署名。界面侧栏底部与 `data/meta.json` 均已注明来源。

---

## 打赏

本软件永久免费，也不靠它赚钱；如果你想支持一下，欢迎到 [爱发电](https://afdian.com/a/jiajun2160) 请我喝杯咖啡 ☕。

打赏完全自愿，**不会获得额外功能或优先支持**——软件对所有用户一视同仁，永久免费。
