<#
EFT 互动地图 · 打包脚本（PyInstaller onedir）

用法：
    powershell -ExecutionPolicy Bypass -File build\build.ps1
    powershell -ExecutionPolicy Bypass -File build\build.ps1 -Run          # 打包完顺便启动
    powershell -ExecutionPolicy Bypass -File build\build.ps1 -VerifyOnly    # 只校验 staging，不碰 dist/
    powershell -ExecutionPolicy Bypass -File build\build.ps1 -SkipBundledPrices  # 跳过内置行情快照重新生成

R79：默认先用采集器最新数据重新生成三模式内置行情快照（data\flea-prices*.json），
数据缺失或超过 12 小时直接让打包失败，避免把陈旧行情发进安装包。

产出：dist\EFTMap\EFTMap.exe —— 双击即用，完全离线，站点文件随包分发。
#>
[CmdletBinding()]
param(
    [switch]$Run,
    [switch]$VerifyOnly,
    [switch]$SkipBundledPrices
)

$ErrorActionPreference = "Stop"

$BuildDir = $PSScriptRoot
$Root = Split-Path -Parent $BuildDir
$Dist = Join-Path $Root "dist"
$Work = Join-Path $Root "build\_work"
$Target = Join-Path $Dist "EFTMap"
$Staging = Join-Path $BuildDir "_staging"
$StagingCheck = Join-Path $BuildDir "_staging_check"
# R282：主程序图标（exe 资源）；壳的图标由 tools/host/build.ps1 单独写入。
$appIcon = Join-Path $Root "assets\app.ico"
if (-not (Test-Path $appIcon)) { throw "缺少应用图标：$appIcon" }

# 运行文件清单与 staging 校验只放在 build/package_files.ps1 一处，
# build.ps1 和 verify_package_files.ps1 共用，避免两套名单慢慢漂移。
. (Join-Path $BuildDir "package_files.ps1")

Write-Host "仓库根目录：$Root"

if ($VerifyOnly) {
    $expected = Stage-RuntimePackage -Root $Root -Destination $StagingCheck
    Test-RuntimePackage -Root $Root -Staging $StagingCheck -Expected $expected
    Write-Host "仅校验完成；未修改 dist/ 或 release/。"
    exit 0
}

# R79：内置行情快照必须来自采集器最新数据，不能让 11-08 那种陈旧文件进包。
# 生成失败（无采集数据或超过 12 小时）就直接中止打包；确需复用现有文件时加 -SkipBundledPrices。
if (-not $SkipBundledPrices) {
    Write-Host "重新生成三模式内置行情快照…"
    # 同下：Python 的进度/警告会走 stderr，Stop 会把它当致命错误
    $prevEapPrices = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & python (Join-Path $Root "tools\build_bundled_prices.py")
    $pricesCode = $LASTEXITCODE
    $ErrorActionPreference = $prevEapPrices
    if ($pricesCode -ne 0) {
        throw "内置行情快照生成失败（退出码 $pricesCode；数据缺失或已过期）。先跑采集器，或加 -SkipBundledPrices 复用现有 data\flea-prices*.json。"
    }
}

# 先把站点文件按清单 staging，并在动 dist/ 之前完成完整性校验。
$expected = Stage-RuntimePackage -Root $Root -Destination $Staging
Test-RuntimePackage -Root $Root -Staging $Staging -Expected $expected

# 覆盖 exe 前必须先结束正在运行的旧实例，否则会报“拒绝访问”
Get-Process -Name EFTMap -ErrorAction SilentlyContinue | ForEach-Object {
    Write-Host "结束正在运行的 EFTMap（pid=$($_.Id)）"
    $_ | Stop-Process -Force
}

# R280.1：旧 work/dist 目录改用改名挪开，避免本机对大目录 Remove-Item 被
# 安全钩子/文件占用挂住导致构建卡死；旧产物完整保留可随时回看。
foreach ($_dir in @($Work, $Target)) {
    if (Test-Path -LiteralPath $_dir) {
        $backup = "$_dir.old." + [DateTime]::Now.ToString("yyyyMMddHHmmss")
        Move-Item -LiteralPath $_dir -Destination $backup -Force
        Write-Host "旧目录已挪开：$backup"
    }
}

# 基础包在临时目录里生成，构建成功后再拷回 dist\EFTMap（避免直接覆盖正在运行的旧包）。
# 注：早期版本曾把「EndUpdateResourceW 被拒绝」记成本机 D: 卷的过滤驱动问题，
# 实际是**构建进程跑在受限沙箱里**导致 PE 资源写回被拦；在正常桌面会话下执行
# 时 C:/D: 都能正常写资源，所以这里不再区分卷。
$PyiBase = Join-Path $env:TEMP "EFTMap-Base-Build"
$PyiDist = Join-Path $PyiBase "dist"
$PyiWork = Join-Path $PyiBase "work"
$PyiStaging = Join-Path $PyiBase "runtime"
New-Item -ItemType Directory -Force -Path $PyiDist, $PyiWork | Out-Null
$PyiStageOld = "$PyiStaging.old." + [DateTime]::Now.ToString("yyyyMMddHHmmss")
if (Test-Path -LiteralPath $PyiStaging) {
    Move-Item -LiteralPath $PyiStaging -Destination $PyiStageOld -Force
}
Write-Host "把运行文件 staging 到本机临时目录：$PyiStaging"
Copy-Item -LiteralPath $Staging -Destination $PyiStaging -Recurse -Force
$built = Join-Path $PyiDist "EFTMap"
if (Test-Path -LiteralPath $built) {
    $oldBuilt = "$built.old." + [DateTime]::Now.ToString("yyyyMMddHHmmss")
    Move-Item -LiteralPath $built -Destination $oldBuilt -Force
}
Write-Host "基础打包临时输出：$PyiBase"

# PyInstaller 会把正常的 INFO 写到 stderr。本脚本开着 $ErrorActionPreference="Stop"，
# 直接调用会让 PowerShell 把每一行 INFO 当成 NativeCommandError 终止脚本
# （表现是「构建在 PyInstaller 那一步失败，但日志里只有 INFO 行」）。
# 因此：显式把全部输出流重定向到日志文件，再用退出码判定成败。
$pyiArgs = @(
    "-m", "PyInstaller",
    "--noconfirm", "--clean",
    "--onedir", "--noconsole",
    "--name", "EFTMap",
    "--distpath", $PyiDist,
    "--workpath", $PyiWork,
    "--specpath", $PyiBase,
    "--icon", $appIcon,
    "--paths", (Join-Path $Root "tools"),
    # onnxruntime.transformers.machine_info 里有一句可选的 `import torch`，
    # PyInstaller 会顺着它把整棵 torch（含 CUDA 运行库，约 3.9 GB）以及
    # PySide6 / pandas / scipy / sphinx 一并收进包：基础包从 ~390 MB 膨胀到
    # 4.7 GB，onefile 安装器还会撞上 PyInstaller 的 4 GB TOC 上限直接失败。
    # 这几个子包只服务模型转换/量化工具，运行期 OCR 只用 onnxruntime 推理。
    "--exclude-module", "onnxruntime.transformers",
    "--exclude-module", "onnxruntime.quantization",
    "--exclude-module", "onnxruntime.tools",
    "--exclude-module", "torch",
    "--exclude-module", "torchvision",
    "--exclude-module", "functorch",
    "--add-data", "$PyiStaging;.",
    "--add-data", "$Root\tools\live_prices.py;tools",
    "--add-data", "$Root\tools\r20_fetch_prices.py;tools",
    "--add-data", "$Root\tools\installer.py;tools",
    "--add-data", "$Root\tools\scan.py;tools",
    "--add-data", "$Root\tools\overlay.py;tools",
    "--hidden-import", "PIL", "--hidden-import", "PIL.Image",
    "--hidden-import", "PIL.ImageDraw",
    "--hidden-import", "PIL.ImageGrab", "--hidden-import", "PIL.ImageFont",
    (Join-Path $Root "tools\launcher.py")
)
$pyiLog = Join-Path $PyiBase "pyinstaller.log"
$prevEap = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& python @pyiArgs *> $pyiLog
$pyiCode = $LASTEXITCODE
$ErrorActionPreference = $prevEap

if ($pyiCode -ne 0) {
    Get-Content -LiteralPath $pyiLog -Tail 40 | ForEach-Object { Write-Host $_ }
    throw "PyInstaller 打包失败（退出码 $pyiCode），完整日志：$pyiLog"
}

if (-not (Test-Path (Join-Path $built "EFTMap.exe"))) {
    throw "C: 盘临时目录里没有生成基础包：$built"
}
New-Item -ItemType Directory -Force -Path $Target | Out-Null
Copy-Item -Path (Join-Path $built "*") -Destination $Target -Recurse -Force
Write-Host "基础包已拷回：$Target"

# PyInstaller 6.x 把资源放进 _internal；5.x 放在 exe 同级，这里两种都兼容
$Internal = Join-Path $Target "_internal"
if (-not (Test-Path $Internal)) { $Internal = $Target }

$Exe = Join-Path $Target "EFTMap.exe"
$MustHave = @(
    $Exe,
    (Join-Path $Internal "index.html"),
    (Join-Path $Internal "style.css"),
    (Join-Path $Internal "app.js"),
    (Join-Path $Internal "tasks.js"),
    (Join-Path $Internal "wiki-map.js"),
    (Join-Path $Internal "gun_builder.js"),
    (Join-Path $Internal "combat_sim.js"),
    (Join-Path $Internal "styles\design-tokens.css"),
    (Join-Path $Internal "styles\ui-components.css"),
    # R300/R302：去位图覆盖层与市场暗色主题，index.html 直接引用，缺一样会整页样式退化
    (Join-Path $Internal "styles\modern-flat.css"),
    (Join-Path $Internal "styles\market-dark.css"),
    (Join-Path $Internal "js\ui-components.js"),
    (Join-Path $Internal "js\game-mode.js"),
    (Join-Path $Internal "js\task-graph-layout.js"),
    # R305：游戏更新视图（独立模块 + 独立样式），index.html 直接引用。
    (Join-Path $Internal "js\changes.js"),
    (Join-Path $Internal "styles\changes.css"),
    # R307：小工具视图（独立模块 + 独立样式）。
    (Join-Path $Internal "js\tools-view.js"),
    (Join-Path $Internal "styles\tools.css"),
    (Join-Path $Internal "data\maps.json"),
    (Join-Path $Internal "data\items.json"),
    # R279：OCR 短名表 + ONNX 模型，缺一个「截图识别」就只剩框选、不出价格。
    (Join-Path $Internal "data\ocr-item-names.json"),
    (Join-Path $Internal "assets\ocr\det.onnx"),
    (Join-Path $Internal "assets\ocr\rec.onnx"),
    (Join-Path $Internal "assets\ocr\ppocr_keys_v1.txt"),
    (Join-Path $Internal "data\gunslots.json"),
    (Join-Path $Internal "data\roadnet.json"),
    (Join-Path $Internal "data\tasks\tasks.regular.json"),
    (Join-Path $Internal "data\i18n\ui-zh.json"),
    # R305：游戏更新页的随包快照；缺它离线打开「更新」页是空的。
    (Join-Path $Internal "data\game-changes.json"),
    # 行情抓取器以源码形式随包（serve.py 在冻结产物里用 --run-tool 交给
    # 同一份解释器执行，而不是把 EFTMap.exe 当 python 用）。
    (Join-Path $Internal "tools\live_prices.py"),
    (Join-Path $Internal "tools\r20_fetch_prices.py"),
    # 安装版的 Uninstall.exe 是 EFTMap.exe 副本，卸载逻辑靠 --run-tool 跑这份源码。
    (Join-Path $Internal "tools\installer.py"),
    # 截图识别宿主：全局热键 → 框选 → 透明浮窗。以前只在开发机的登录自启里，
    # 装好的客户端按 Ctrl+Alt+P 没反应就是这个原因（R278 起随包、随主程序起）。
    (Join-Path $Internal "tools\scan.py"),
    (Join-Path $Internal "tools\overlay.py"),
    # 站点图标（浏览器地址栏/标签页），index.html 的 <link rel="icon"> 指向它。
    (Join-Path $Internal "favicon.ico"),
    # 云账号：菜单「云账号」的脚本 + 内置证书（serve.py 按此路径读取）。
    (Join-Path $Internal "js\cloud.js"),
    (Join-Path $Internal "assets\cloud-ca.pem"),
    (Join-Path $Internal "assets\maps"),
    (Join-Path $Internal "assets\icons-items"),
    (Join-Path $Internal "assets\roadnet")
)
foreach ($p in $MustHave) {
    if (-not (Test-Path $p)) { throw "打包产物缺少必需文件：$p" }
}

# 完整清单的逐项存在性校验（不比较多余文件；PyInstaller 会额外放 Python 运行时）。
Test-ExpectedFilesPresent -Root $Internal -Expected $expected

$svgCount = (Get-ChildItem (Join-Path $Internal "assets\maps") -Filter *.svg).Count
$sizeMB = [math]::Round(((Get-ChildItem $Target -Recurse -File | Measure-Object -Property Length -Sum).Sum / 1MB), 1)

Write-Host ""
Write-Host "打包完成：$Exe"
Write-Host "  底图 SVG：$svgCount 张"
Write-Host "  产物体积：$sizeMB MB"
Write-Host "  双击 $Exe 即可启动（默认打开无边框独立窗口 EFTMapDesktop.exe）。"

if ($Run) {
    Write-Host "启动 $Exe"
    Start-Process $Exe
}
