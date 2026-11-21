# 启动说明（当前版本 R18.2）

> 本项目是**纯本地静态站点 + Python 标准库 HTTP 服务**，运行期不联网、不装任何第三方库。
> 不存在"直接双击 index.html"的用法——浏览器会拦截本地数据读取，页面会自己提示改用本地服务。

---

## 0. 最快路径（记住这三行）

| 步骤 | 内容 |
|---|---|
| **打开文件夹** | `D:\personal\trae\02-塔科夫\eft-interactive-map` |
| **运行** | 双击 `启动项目.bat` |
| **访问** | `http://127.0.0.1:8787/`（脚本会自动帮你打开浏览器） |

页面加载后，按 **弹药 → 逐发模拟**，顶部执行条显示 `R18.2 构建 · …` 即为当前版本。

---

## 1. 从哪里启动

项目根目录（**必须是这个目录，不要进 `tools` 或 `dist`**）：

```
D:\personal\trae\02-塔科夫\eft-interactive-map
```

判断是否找对：该目录下能同时看到

```
index.html
app.js
combat_sim.js
style.css
theme-windows-xp.css     ← R18 主题层
启动项目.bat             ← R18.1 新增的一键启动（此后每轮沿用）
tools\serve.py           ← 真正的服务入口
tools\launcher.py        ← 带图形启动框的入口
data\                    ← 站点数据（items.json / maps.json …）
```

---

## 2. 执行什么命令

### 方式 A：双击 `启动项目.bat`（推荐，日常使用）

- 位置：`D:\personal\trae\02-塔科夫\eft-interactive-map\启动项目.bat`
- 双击即可，**不需要管理员权限**，不需要命令行，不需要激活虚拟环境。
- 脚本会自动完成：切到项目目录 → 找 Python（先试 `py -3`，再试 `python`）
  → 检查 `tools\serve.py` 与 `index.html` → 检查端口 → 启动服务 → 打开浏览器。
- 换端口：在本窗口输入 `启动项目.bat 8788`（或用命令行执行带参数形式）。

### 方式 B：命令行（排查问题时用）

CMD 或 PowerShell 都可以，**普通权限**即可：

```bat
cd /d "D:\personal\trae\02-塔科夫\eft-interactive-map"
py -3 tools\serve.py
```

没有 `py` 启动器时用：

```bat
cd /d "D:\personal\trae\02-塔科夫\eft-interactive-map"
python tools\serve.py
```

PowerShell 写法相同（`cd /d` 也可用 `Set-Location`）：

```powershell
Set-Location "D:\personal\trae\02-塔科夫\eft-interactive-map"
py -3 tools\serve.py
```

### 方式 C：带图形启动框（可配游戏目录 / 截图目录 / 声音提示）

```bat
cd /d "D:\personal\trae\02-塔科夫\eft-interactive-map"
py -3 tools\launcher.py
```

会弹出「设置与启动」小窗，点 **启动 WebUI** 才会真正起服务。
适合需要改设置的时候，日常快速启动用方式 A 更省事。

### 方式 D：发布包 `EFTMap.exe`

如果你用的是打包版（`release\` 或安装到 `%LOCALAPPDATA%\EFTMap` 的那份），
直接双击 `EFTMap.exe` → 点「启动 WebUI」。那条路径不需要装 Python。
**注意**：exe 是打包时冻结的代码，不包含源码目录里 R18.1 / R18.2 的改动，除非重新打包。

### 前置条件

| 项 | 要求 |
|---|---|
| Python | **3.9 或更高**（开发环境实测 3.14.3）。安装时勾选 `Add python.exe to PATH` |
| 第三方库 | **不需要任何**（只用标准库；`tkinter` 仅方式 C 需要，是 Python 自带组件） |
| 管理员权限 | **不需要** |
| 虚拟环境 | **不需要**，也**不要**建——项目没有依赖 |
| 联网 | 启动与运行**都不需要**。只有首次重新抓数据（`tools/fetch_data.py`）才需要联网 |
| 工作目录 | 不强制。`serve.py` 用 `__file__` 推导站点根目录，从任何目录调用都能跑；但**必须用 `python tools\serve.py` 这种"给脚本路径"的形式**，不要 `python -m serve`（模块内部的 `import config` 依赖 `tools` 在搜索路径里） |

---

## 3. 启动后访问哪里 / 怎么确认是 R18.2

**访问地址**：<http://127.0.0.1:8787/>

启动成功时，控制台会打印：

```
EFT 互动地图已启动：http://127.0.0.1:8787/
实时定位：监听截图目录 …            （或：未开启）
日志监控：跟随游戏目录 …\Logs …     （或：未开启）
配置文件：C:\Users\<你>\AppData\Roaming\EFTMap\eftmap.config.json
按 Ctrl+C 停止服务。
```

### 三种确认"当前跑的是 R18.2"的方法

1. **页面内标记（最直接）**
   打开 `弹药` → `逐发模拟`，顶部执行条第一行显示：

   ```
   R18.2 构建 · compat 加载中 · 配置改完后直接点这里；…
   ```

   如果不是 `R18.2`，就是浏览器缓存或跑了别的副本（见 §5.4）。

2. **资源版本号**
   页面按 `F12` → `Network` → 刷新，看这两个请求都带 `?v=r18.2`：

   ```
   app.js?v=r18.2
   theme-windows-xp.css?v=r18.2
   combat_sim.js?v=r18.2
   style.css?v=r18.2
   ```

   或在地址栏直接取：
   `view-source:http://127.0.0.1:8787/index.html` 搜索 `?v=`。

3. **服务端健康检查**
   浏览器打开 <http://127.0.0.1:8787/api/health>，应返回 `"ok": true` 且
   `"root"` 就是你当前的项目目录：

   ```json
   { "ok": true, "app": "eft-interactive-map", "version": "0.1.0",
     "root": "D:\\personal\\trae\\02-塔科夫\\eft-interactive-map",
     "data": { "ready": true, "maps": 13 } }
   ```

   `"root"` 不对 → 说明你启动的不是这份代码（八成是 `dist\` 或安装版里的旧副本）。

---

## 4. 关闭与重新启动

### 关闭

| 场景 | 操作 |
|---|---|
| 用 `启动项目.bat` 或命令行启动 | 在**那个黑窗口**里按 `Ctrl + C`，或直接关闭窗口 |
| 用 `launcher.py` 启动 | 关掉启动框小窗，或在任务管理器结束对应 Python 进程 |
| 窗口已经找不到 / 僵死 | `netstat -ano \| findstr :8787` 查到 PID，再 `taskkill /PID <PID> /F` |

### 重新启动

- 直接再双击 `启动项目.bat` 即可。
- 如果上一次的窗口还没关，端口仍在监听，脚本会检测到并**只打开浏览器、不启动第二个服务**
  （避免出现两个服务抢同一端口）。
- 改了 `app.js` / CSS / 数据后：关掉服务 → 重新双击启动 → 浏览器里按 `Ctrl + F5` 强刷。

### 避免端口占用

- 同一时间只跑一个实例。脚本已经做了保护：端口在监听就复用，不再起第二个。
- 想同时跑两份（例如对比新旧版本）：显式换端口
  `启动项目.bat 8788`，然后访问 <http://127.0.0.1:8788/>。

---

## 5. 出现错误怎么办

### 5.1 端口被占用

症状：窗口打印 `[失败] 端口 8787 被占用。` 或 `端口 8787 已被占用。请关闭占用该端口的程序…`

```bat
netstat -ano | findstr :8787
taskkill /PID <上面查到的PID> /F
```

或者不杀进程，直接换端口：

```bat
启动项目.bat 8788
```

> 如果占着 8787 的是**别的程序**（不是本项目），双击 bat 会打开一个打不开的页面。
> 此时按提示换端口，别去关那个程序。

### 5.2 找不到启动文件

症状：`[失败] 找不到启动所需的文件。` / `根目录里找不到 index.html`

原因通常是：bat 被复制到了别的地方，或者项目目录被移动/改名。

- `启动项目.bat` **必须**和 `index.html` 在同一个目录；
- 该目录下必须有 `tools\serve.py`；
- 如果你确实把项目挪了位置，把整个文件夹（含 `assets`、`data`、`tools`）一起搬，不要只搬一部分。

### 5.3 服务启动失败 / 窗口一闪而过

`启动项目.bat` 在所有分支末尾都有 `pause`，窗口**不会**一闪而过，错误信息会停在那里。
常见情况：

| 现象 | 原因 | 处理 |
|---|---|---|
| `[失败] 没有找到可用的 Python` | 没装 Python，或安装时没勾 PATH | 重装 Python 并勾 `Add python.exe to PATH`；装完**重开**一个窗口 |
| `ModuleNotFoundError: No module named 'config'` | 用了 `python -m serve` 或在 `tools` 目录外直接跑 `serve.py` | 用 `python tools\serve.py`（给脚本路径，不是模块名） |
| `OSError: [WinError 10048]` | 端口被占（未经 bat 的端口检查时才会出现） | 见 §5.1 |
| 双击 bat 窗口闪一下就没了 | 极少见：bat 被改过、`pause` 被删 | 在 CMD 里手动执行 `启动项目.bat` 看完整输出 |
| 页面提示"请改用本地服务" | 直接双击了 `index.html`（`file://`） | 必须走 http，用 §2 的方式启动 |

### 5.4 浏览器仍加载旧版本

这是最容易误判的一条。按顺序排查：

1. **先看构建标记**：`弹药 → 逐发模拟` 顶部是否显示 `R18.2`。
   不显示就先别怀疑代码，按下面处理缓存。
2. **强制刷新**：`Ctrl + F5`（或 `Ctrl + Shift + R`）。
   Chrome 对已打开的标签页会走 memory cache，普通 F5 有时仍用旧脚本。
3. **确认只有一个服务**：`netstat -ano | findstr :8787`，PID 数量应为 1。
   如果之前用 `dist\` 或安装版跑过，它可能也占了 8787——关掉它再用源码目录启动。
4. **确认 `root` 指向当前目录**：打开 <http://127.0.0.1:8787/api/health>，
   `"root"` 必须是 `D:\personal\trae\02-塔科夫\eft-interactive-map`。
   指向 `dist` 或 `%LOCALAPPDATA%\EFTMap` → 你启动的是打包版的旧副本。
5. **换端口排除干扰**：`启动项目.bat 8788` → 访问 8788。
   如果 8788 上是 R18.2、8787 上不是，说明 8787 被另一个旧实例占着。
6. **无痕窗口验证**：`Ctrl + Shift + N` 打开无痕窗口访问 8787，
   能显示 R18.2 就说明是缓存问题，清一次该站点的缓存即可。

---

## 6. 一句话总结

```
文件夹：D:\personal\trae\02-塔科夫\eft-interactive-map
命令：  双击 启动项目.bat        （等价：py -3 tools\serve.py）
地址：  http://127.0.0.1:8787/
确认：  弹药 → 逐发模拟 → 顶部显示 "R18.2 构建"
停止：  在启动窗口按 Ctrl + C
```
