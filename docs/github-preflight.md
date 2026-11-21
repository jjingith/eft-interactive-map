# GitHub 更新前审计（R18 收尾）

> 本轮**没有执行** `git add` / `git commit` / `git push`，也没有改写历史。
> 本文只记录真实状态与建议，等你确认后再动手。

审计时间：2026-10-23 · 项目：`D:\personal\trae\02-塔科夫\eft-interactive-map`

## 1. 当前状态

| 项 | 实际值 |
|---|---|
| 分支 | `main` |
| 最近提交 | `bf438df 文档：交接手册记录第十五轮提交与三件套发布状态` |
| 已跟踪文件被修改 | **21 个** |
| 未跟踪文件 | **5893 个**（`git status` 里压缩成 68 条目录项） |
| 未跟踪体积分布 | `assets/` 5402 · `docs/` 416 · `(根目录)` 35 · `tests/` 21 · `data/` 12 · `tools/` 7 |
| 工作区是否干净 | 否（大量未提交的历史轮次成果 + 本轮换肤） |

已跟踪的 21 个修改文件：

```
AGENT_HANDOFF.md      README.md             app.js
build/build.ps1       data/meta.json        data/roadnet.json
docs/USAGE.md         index.html            style.css
tests/test_autoshot.py    tests/test_config.py     tests/test_fetch_data.py
tests/test_keyinput.py    tests/test_launcher.py   tests/test_serve.py
tools/config.py       tools/fetch_data.py   tools/iconize.py
tools/keyinput.py     tools/launcher.py     tools/serve.py
```

未跟踪的重点内容（非全部）：

- `combat_sim.js`（逐发模拟引擎，R14–R18 的核心，一直没进版本库）
- `data/*.json` 12 个（ammo / items / gun-rates / gun-compat / gun-platforms / bosses / barriers / combat-targets / gunslots / caliber-groups / gun-presets …）
- `assets/icons-items/` 5356 个图标、`assets/icons-traders|zones|slot-glyphs`、`assets/icons-*`
- `tests/js/`（引擎场景脚本）、`tests/test_r1x*.py`（R10–R18 测试）
- `docs/r10..r18/`（每轮验收报告与截图）
- 本轮新增：`theme-windows-xp.css`、`docs/ui-windows-xp/`、`tests/test_r18_theme.py`、本文件

## 2. `git diff` 体检

```
$ git diff --stat | tail -1
21 files changed, 14978 insertions(+), 71 deletions(-)

$ git diff --check
（无输出，exit 0；只有 core.autocrlf 的 LF→CRLF 提示）
```

- `git diff --check` 干净：没有行尾空白、没有冲突标记。
- 注意 `app.js` 单文件 **+9469 行**未提交——这是 R10–R18 十轮功能累积，不是本轮换肤造成的。

## 3. 与 `release/` 有关的变更

```
$ git status --porcelain=v1 | grep -i release
（无输出）
```

- `.gitignore` 已包含 `release/`、`dist/`、`build/_work*`、`build/_release/`、`*.spec`。
- 本轮**没有**修改、覆盖或删除 `release/` 下任何内容；打包产物不进仓库。

## 4. 测试与浏览器验收（本轮实测）

| 项 | 结果 |
|---|---|
| `python -m pytest -q`（换肤前基线） | 844 passed, 1 skipped |
| `python -m pytest -q`（换肤后） | **853 passed, 1 skipped**（+9 条主题层测试；仅同步 2 处构建标记断言，未删/未弱化） |
| `node --check app.js` / `combat_sim.js` | exit 0 / exit 0 |
| 浏览器（Chrome CDP，1920×1080 / 1264×705） | 4 个视图全部浅色 Luna；弹窗未被裁切；拖拽/选弹/配装/配枪/地图缩放平移/标签切换全部正常 |
| 控制台与网络 | 0 控制台错误、0 未捕获异常、**0 外部请求** |
| 横向溢出 | 两个尺寸均无 |

截图证据：`docs/ui-windows-xp/before/` 与 `docs/ui-windows-xp/after/`（29 张）。

## 5. 敏感信息排查

扫描范围：所有已跟踪文件 + 全部未跟踪文本文件（`.py/.js/.json/.md/.html/.css/.ps1/.txt/...`），
匹配 `api_key|secret|password|token|bearer|PRIVATE KEY|AKIA…|ghp_…` 与绝对用户路径。

**结论：没有发现真实凭据（无 API Key / 无私钥 / 无 GitHub Personal Access Token 值）。**
命中项均为代码标识符（`token()` 函数、`gunRefToken`、`GUN_CAL_TOKEN` 正则）或说明文字。

需要人工确认的**隐私/环境痕迹**（不是凭据，但发布前建议处理）：

| 文件 | 内容性质 | 建议 |
|---|---|---|
| `AGENT_HANDOFF.md`（已跟踪，有改动） | 提到 `gh` CLI 路径 `C:\Users\Administrator\gh-cli\bin\gh.exe`、以及「环境变量里有 GitHub App 令牌，需先清 `GH_TOKEN`」这类运维笔记 | 发布到公开仓库前，删除具体本机路径与令牌相关描述 |
| `tests/test_screenshot_parse.py` | 测试样例里含 `C:\Users\imzjj\...`（个人 Windows 用户名） | 换成中性路径（如 `C:\Users\user\Pictures\EFT`）再发布 |
| `docs/r7-acceptance-report.html` | 截图说明里出现 `C:\Users\Administrator` | 可选：脱敏或接受（只是路径） |

令牌本身不在任何文件里；但**如果历史上曾把令牌写进某个已提交文件**，需要单独用
`git log -S"<片段>"` 排查并考虑 `git filter-repo` 清理（本轮未做，因为没有发现这种情况）。

## 6. 大文件 / 生成物 / 缓存

| 项 | 体积 | 判断 |
|---|---|---|
| `data/items.json` | 5.8 MB | **运行期必需**（物品库），建议保留；仓库变大可考虑 Git LFS |
| `assets/icons-items/` | 14.8 MB / 5356 文件 | **运行期必需**（弹药/物品图标）。若在意仓库体积，可用 LFS 或改为打包 zip + 构建期解包，但会动加载逻辑，本轮不建议 |
| `docs/r17-fixes/`、`docs/ui-windows-xp/` | 5.3 MB / 7.1 MB（截图） | 验收证据，可选提交；不想让仓库膨胀可只提交 md，截图放 release 附件 |
| `build-cache/` | — | 已在 `.gitignore`（上游原始数据缓存，不进仓库） |
| `dist/`、`release/`、`*.spec`、`eftmap.config.json`、`sounds/` | — | 已在 `.gitignore` |
| `__pycache__/`、`.pytest_cache/` | — | 已在 `.gitignore` |

`git ls-files -o` 中没有 >5MB 的其他文件（仅 `data/items.json`）。

## 7. `.gitignore` 是否需要补充

现状（摘要）：`__pycache__/`、`*.py[cod]`、`.venv/`、`.pytest_cache/`、`dist/`、`release/`、
`build/_work*/`、`*.spec`、`build-cache/`、`eftmap.config.json`、`sounds/`、`.vscode/`、`.idea/`、
`Thumbs.db`、`desktop.ini`。

判断：**本轮无需新增条目**。可选补充（取决于你的偏好）：

```gitignore
# 可选：不想把验收截图进仓库时
docs/**/screenshots/*.png
docs/ui-windows-xp/**/*.png
```

## 8. 是否适合分批提交

**强烈建议分批，不要 `git add .`。** 当前工作区混了 R10–R18 十轮成果，
一次性提交会让 review 完全无法进行，也会掩盖"这一轮到底改了什么"。

先做本地备份（不改变 Git 历史）：

```bat
:: 1) 完整工作区快照（含未跟踪文件）
git stash push -u -m "pre-r18-snapshot"      :: 需要回滚时用 stash pop
:: 或更稳妥：整目录压缩
powershell Compress-Archive -Path . -DestinationPath ..\eft-interactive-map-r18-backup.zip
```

> 注意：`git stash -u` 会把未跟踪文件收走，若中途要对比请先做 zip 备份。

## 9. 建议的分支与提交顺序

```
分支：feature/windows-xp-theme（从 main 拉出）
```

提交顺序（每步都先跑 `python -m pytest -q`）：

| # | 提交内容 | 建议信息 |
|---|---|---|
| 0 | `data/*.json` + `assets/icons-*`（历史轮次的数据与素材） | `data: 补充弹药/物品/护甲/Boss 数据与本地图标资源` |
| 1 | `combat_sim.js` + `tests/js/*`（引擎与其场景脚本） | `feat(sim): 逐发击杀模拟引擎（混压弹匣/护甲分层/命中率）` |
| 2 | `app.js` + `index.html` + `style.css` + `tools/*` + `build/*`（R10–R17 累积功能） | `feat: 配装工作台/配枪/弹药页/逐发模拟器功能累积` |
| 3 | `tests/test_r1*.py`（各轮功能测试） | `test: 补齐 R10–R17 功能回归用例` |
| 4 | **`theme-windows-xp.css` + `index.html`/`app.js` 的版本位 + `tests/test_r18_theme.py` + `docs/ui-windows-xp/`** | `style(theme): 全站 Windows XP Luna 换肤（纯视觉层，不改业务逻辑）` |
| 5 | `docs/r10..r18/` + `docs/github-preflight.md` + README 更新 | `docs: 各轮验收报告与 GitHub 前置审计` |
| 6 | 推送 | `git push -u origin feature/windows-xp-theme` |

要点：

- **第 2 步的 `app.js` 无法按轮次再细分**（十轮改动交织在同一文件里，历史版本已被覆盖）。
  如果一定要细分，只能按功能区块手工拆 diff，风险高、收益低——建议整体提交并在信息里写清范围。
- 第 4 步是把「换肤」独立成一条提交：它的文件集很小（1 个 CSS + 3 处版本位 + 1 个测试 + 文档），
  便于日后 `git revert` 单独回退主题。
- 不要用 `git checkout -- <file>` 之类的硬恢复去"拆"历史改动，会直接丢工作。

## 10. 推送前仍需人工确认

1. **是否公开**：若是公开仓库，先处理第 5 节的 3 处个人路径 / 运维笔记。
2. **`data/items.json` 5.8MB + 14.8MB 图标**：是否接受仓库体积，或改用 Git LFS。
3. **验收截图是否进仓库**：`docs/r10..r18` 累计已超 12MB。
4. **`release/` 发布包与源码版本对齐**：当前 `release/` 仍是第 14 轮打包产物，
   本轮换肤没有重新打包；若要发布，需要重新执行 `build/build.ps1`。
5. **远程仓库地址与权限**：确认 `git remote -v` 指向你要更新的仓库，且当前账号有 push 权限
   （历史笔记里提到过 `GH_TOKEN` 抢占授权的问题，推送前确认识别到的账号）。
6. **提交信息语言**：本仓库历史用中文提交信息，建议保持一致。

## 11. 本轮（R18）改动清单（供第 4 步提交核对）

```
新增  theme-windows-xp.css           主题层（1780 行，含自动映射块）
改动  index.html                     引入主题层 + 资源版本升到 r18
改动  app.js                         仅 AM_BUILD: "R17S5" → "R18"
改动  tests/test_r17_fixes.py        构建标记断言同步 R18（等价，不弱化）
改动  tests/test_r17s5_empty_drag.py 同上（改为「标记与资源版本一致」的通用断言）
新增  tests/test_r18_theme.py        9 条主题层测试
新增  docs/ui-windows-xp/README.md + before/ + after/（29 张截图）
新增  docs/github-preflight.md       本文件
```

**未改动**：`combat_sim.js`、`data/*`、`tools/*`、`build/*`、地图/路线/任务逻辑、
任何计算与兼容性判断。

---

# 附：R18.1 收尾状态复检（2026-10-24）

> 本轮同样**没有执行** `git add` / `git commit` / `git push`，没有触碰 `release/`，
> 没有删除或清理任何未跟踪文件。以下只是复检结论。

## A.1 与 R18 收尾时的差异

| 项 | R18 收尾（10-23） | R18.1（10-24） | 说明 |
|---|---|---|---|
| 分支 | `main` | `main` | 未变 |
| 最近提交 | `bf438df` | `bf438df` | 未变（本轮未提交） |
| 已跟踪文件被修改 | 21 个 | **21 个** | 同一批，本轮在其上继续改 `app.js` / `index.html` / `style.css` |
| 未跟踪文件总数 | 5893 | **5958** | +65：本轮新增素材、脚本、测试、报告 |
| `git diff --stat` | 14 978 insertions | **15 087 insertions**, 71 deletions | 增量即本轮改动 |
| `git diff --check` | 干净 | **干净**（仅 CRLF 提示） | 无行尾空白、无冲突标记 |

## A.2 本轮新增的未跟踪内容（供提交时分类）

| 路径 | 性质 | 建议 |
|---|---|---|
| `assets/ui/placeholders/*.png`（10 张，约 29 KB） | 运行期静态资源（空槽剪影） | **必须提交**，缺失会导致空槽无图 |
| `assets/ui/placeholders/manifest.json` | 素材来源与处理参数记录 | **必须提交**（可审计、可复现） |
| `assets/ui/placeholders/_src/*.webp`（10 张，296 KB） | 构建期上游透明底原图 | 建议提交（离线可重建；删除后需联网重下） |
| `tools/build_slot_placeholders.py` | 构建期生成器（依赖 Pillow） | **必须提交** |
| `tools/r181_accept.py` | CDP 验收脚本（纯标准库） | 建议提交（后续每轮可复用） |
| `tests/test_r18_1_round.py` | 11 个新测试 | **必须提交** |
| `docs/ui-windows-xp/r18.1/`（34 张截图 + 2 份报告 + 2 份测试输出 + `_accept.json`） | 验收证据 | 建议提交 |

## A.3 仍需人工确认的老问题（与 R18 收尾一致，本轮未处理）

1. **`AGENT_HANDOFF.md` / `tests/test_screenshot_parse.py` / `docs/r7-acceptance-report.html`
   含本机绝对路径**（`D:/personal/trae/...`），提交前需脱敏。
2. `assets/icons-items/` 5356 个图标依赖上游 `assets.tarkov.dev` 素材，
   再分发许可仍未确认（与 `assets/icons-traders` 的处置方式不同，后者已改为自绘）。
3. `data/items.json` 5.4 MB、`data/maps.json` 2.1 MB 属于数据快照，
   建议单独一次提交并在信息里写明上游抓取日期。
4. 未跟踪文件 5958 个，**不要用 `git add .`**；按 A.2 + 已有的分批建议逐类添加。

## A.4 本轮明确未做的事

- 未 `git add` / `commit` / `push`（用户要求本轮只检查状态）。
- 未覆盖 `release/`、未重新打包 `dist/`。
- 未清理任何未跟踪文件或缓存目录。
- 未修改 `.gitignore`（`assets/ui/placeholders/_src/` 有意保留在版本库内）。
