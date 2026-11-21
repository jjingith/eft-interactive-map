<#
EFT 互动地图 · 发布三件套构建

用法：
    powershell -ExecutionPolicy Bypass -File build\build_release.ps1
    powershell -ExecutionPolicy Bypass -File build\build_release.ps1 -SkipBase   # dist\EFTMap 已就绪时跳过基础打包
    powershell -ExecutionPolicy Bypass -File build\build_release.ps1 -ReleaseDir release-0.2.7.1
        # 输出到独立目录（脚本会先清空该目录），用于保留 release\ 里的旧版/故障样本
    powershell -ExecutionPolicy Bypass -File build\build_release.ps1 -SkipBundledPrices
        # 复用现有 data\flea-prices*.json，不重生成内置行情快照

产出（release\ 下）：
    EFTMap-Portable-<版本>.zip     解压即用：双击 EFTMap.exe 打开无边框独立窗口
    EFTMap-AppWindow-<版本>.zip    加壳版：同上（保留 appmode.flag，兼容旧判定）
    EFTMap-Setup-<版本>.exe        一键安装器：装到 %LOCALAPPDATA%\EFTMap + 快捷方式 + 卸载项

# 客户端壳已并入产物：打包前把 tools\host\bin 的
# EFTMapDesktop.exe + Microsoft.Web.WebView2.Core.dll + WebView2Loader.dll
# 复制进 dist\EFTMap（与 EFTMap.exe 同级），因此 Portable / AppWindow / Setup
# 的 payload 都自带壳；双击 EFTMap.exe 会优先拉起该壳（R71）。
# 另外，build/build.ps1 现在已经会把完整站点 staging 后交给 PyInstaller，
# 因此 dist\EFTMap 的站点内容会与仓库当前版本一致；release 重建前请先跑
# build\verify_package_files.ps1 确认清单完整。

依赖：只有 PyInstaller（与基础打包同）+ PowerShell 自带的 Compress-Archive。
#>
[CmdletBinding()]
param(
    [switch]$SkipBase,
    # R280.1：本轮只改显示层，不需要重新生成内置行情快照；本机 D: 卷对
    # data\flea-prices*.json 的 os.replace 偶发 WinError 5，透传该开关复用现成快照。
    [switch]$SkipBundledPrices,
    # R280.1：允许把整套产物输出到独立目录，方便在保留旧版本/故障样本的同时出新包。
    # 例：-ReleaseDir release-0.2.7.1（相对项目根）；绝对路径也接受。
    [string]$ReleaseDir = ""
)

$ErrorActionPreference = "Stop"

$BuildDir = $PSScriptRoot
$Root = Split-Path -Parent $BuildDir
$Dist = Join-Path $Root "dist"
$Target = Join-Path $Dist "EFTMap"
if ($ReleaseDir) {
    if ([System.IO.Path]::IsPathRooted($ReleaseDir)) { $Release = $ReleaseDir }
    else { $Release = Join-Path $Root $ReleaseDir }
} else {
    $Release = Join-Path $Root "release"
}
$Staging = Join-Path $Root "build\_release"

# 版本号从 serve.py 读，保证发布物与运行期一致
$version = (Select-String -Path (Join-Path $Root "tools\serve.py") -Pattern '^VERSION\s*=\s*"([^"]+)"').Matches[0].Groups[1].Value
if (-not $version) { throw "没能从 tools\serve.py 读到 VERSION" }
Write-Host "版本：$version"
Write-Host "输出目录：$Release"

# 1) 基础 onedir 打包
if (-not $SkipBase) {
    # 用显式分支而不是数组 splatting：数组里的 '-SkipBundledPrices' 会被当成位置参数，
    # 触发 "A positional parameter cannot be found" (PowerShell 5.1)。
    if ($SkipBundledPrices) {
        & (Join-Path $BuildDir "build.ps1") -SkipBundledPrices
    } else {
        & (Join-Path $BuildDir "build.ps1")
    }
    if ($LASTEXITCODE -ne 0) { throw "build.ps1 失败" }
}
if (-not (Test-Path (Join-Path $Target "EFTMap.exe"))) { throw "dist\EFTMap 不存在，先跑 build.ps1" }

# 客户端壳与 EFTMap.exe 同目录：壳自己会以 --server-only 拉起 EFTMap.exe。
# 下面三个产物都基于 $Target，因此在这一步并入即可覆盖 Portable / AppWindow / Setup。
$HostBin = Join-Path $Root "tools\host\bin"
foreach ($name in @("EFTMapDesktop.exe", "Microsoft.Web.WebView2.Core.dll", "WebView2Loader.dll")) {
    $src = Join-Path $HostBin $name
    if (-not (Test-Path $src)) { throw "缺少客户端壳文件：$src" }
    Copy-Item -LiteralPath $src -Destination $Target -Force
    Write-Host "并入客户端壳：$name"
}
# R282：应用图标。壳的 exe 图标已由 tools/host/build.ps1 嵌入；这里把同一份 ico 放进产物，
# 供安装向导窗口（Tk 的 iconbitmap）与后续页面/快捷方式使用。
$appIcon = Join-Path $Root "assets\app.ico"
if (-not (Test-Path $appIcon)) { throw "缺少应用图标：$appIcon" }
$iconDir = Join-Path $Target "assets"
New-Item -ItemType Directory -Force -Path $iconDir | Out-Null
Copy-Item -LiteralPath $appIcon -Destination (Join-Path $iconDir "app.ico") -Force
Write-Host "并入应用图标：assets\app.ico"

# R75：发布前校验 PE 子系统必须是 GUI(2)。CUI(3) 的 exe 双击会先弹一个控制台窗口，
# 这是「不像正常软件」的直接来源；把判据写进打包流程，避免以后谁改了打包参数又犯。
function Get-PeSubsystem([string]$Path) {
    $bytes = [System.IO.File]::ReadAllBytes((Resolve-Path -LiteralPath $Path).ProviderPath)
    $pe = [BitConverter]::ToInt32($bytes, 0x3C)
    return [BitConverter]::ToUInt16($bytes, $pe + 24 + 68)
}
foreach ($pair in @(
    @{ Path = (Join-Path $Target "EFTMap.exe"); Name = "EFTMap.exe" },
    @{ Path = (Join-Path $Target "EFTMapDesktop.exe"); Name = "EFTMapDesktop.exe" }
)) {
    $sub = Get-PeSubsystem $pair.Path
    if ($sub -ne 2) { throw "$($pair.Name) 的 PE 子系统是 $sub（应为 2=GUI），会弹控制台窗口" }
    Write-Host "PE 子系统校验：$($pair.Name) = GUI(2)"
}

# R280.1：递归删除大目录在本机会被安全钩子/文件占用挂住。改成「改名挪开」——
# 同卷 rename 是原子的，旧产物完整保留，脚本也不用等任何删除完成。
foreach ($_dir in @($Release, $Staging)) {
    if (Test-Path -LiteralPath $_dir) {
        $backup = "$_dir.old." + [DateTime]::Now.ToString("yyyyMMddHHmmss")
        Move-Item -LiteralPath $_dir -Destination $backup -Force
        Write-Host "旧目录已挪开：$backup"
    }
}
New-Item -ItemType Directory -Force -Path $Release, $Staging | Out-Null

# 2) 解压即用（普通版）
Write-Host "打包 Portable…"
Compress-Archive -Path $Target -DestinationPath (Join-Path $Release "EFTMap-Portable-$version.zip") -CompressionLevel Optimal

# 3) 加壳版：整站复制一份，往资源目录里落一个 appmode.flag
Write-Host "打包 AppWindow…"
$appDir = Join-Path $Staging "EFTMap"
Copy-Item -Recurse -Force $Target $appDir
$appInternal = Join-Path $appDir "_internal"
if (-not (Test-Path $appInternal)) { $appInternal = $appDir }
Set-Content -Path (Join-Path $appInternal "appmode.flag") -Value "1" -Encoding ascii
Compress-Archive -Path $appDir -DestinationPath (Join-Path $Release "EFTMap-AppWindow-$version.zip") -CompressionLevel Optimal

# 4) 一键安装器（单文件 exe；dist\EFTMap 作为 payload 打进包）
# 安装器 EXE 必须在构建期由 PyInstaller 写入 PE 资源（Manifest + 图标 + 版本）。
# 早期版本把「EndUpdateResourceW 返回 ERROR_ACCESS_DENIED」记成 D: 卷被过滤驱动拦截，
# 实际根因是**构建进程跑在受限沙箱里**（PE 资源写回被拦）。正常桌面会话下 C:/D: 都可用；
# 这里保留「临时目录构建 → 再拷回 release\」只为不覆盖正在运行的产物。
# 需要换位置时用 EFTMAP_SETUP_BUILD_DIR 指定。
$setupBuild = $env:EFTMAP_SETUP_BUILD_DIR
if (-not $setupBuild) { $setupBuild = Join-Path $env:TEMP "EFTMap-Setup-Build-$version" }
$setupOut = Join-Path $setupBuild "out"
$setupWork = Join-Path $setupBuild "work"
New-Item -ItemType Directory -Force -Path $setupOut, $setupWork | Out-Null
Write-Host "打包 Setup（临时输出：$setupBuild）…"
# 同 build.ps1：PyInstaller 的 INFO 走 stderr，$ErrorActionPreference="Stop" 会把它们
# 当成 NativeCommandError 终止脚本。全部输出重定向到日志，只看退出码。
$setupArgs = @(
    "-m", "PyInstaller",
    "--noconfirm", "--clean",
    "--onefile", "--noconsole",
    "--name", "EFTMap-Setup-$version",
    "--icon", $appIcon,
    "--distpath", $setupOut,
    "--workpath", $setupWork,
    "--specpath", $BuildDir,
    "--paths", (Join-Path $Root "tools"),
    "--add-data", "$Target;payload",
    (Join-Path $Root "tools\installer.py")
)
$setupLog = Join-Path $setupBuild "pyinstaller.log"
$prevEap = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& python @setupArgs *> $setupLog
$setupCode = $LASTEXITCODE
$ErrorActionPreference = $prevEap
if ($setupCode -ne 0) {
    Get-Content -LiteralPath $setupLog -Tail 40 | ForEach-Object { Write-Host $_ }
    throw "安装器打包失败（退出码 $setupCode），完整日志：$setupLog"
}

$builtExe = Join-Path $setupOut "EFTMap-Setup-$version.exe"
if (-not (Test-Path $builtExe)) { throw "临时目录里没有生成安装器：$builtExe" }
$setupExe = Join-Path $Release "EFTMap-Setup-$version.exe"
Copy-Item -LiteralPath $builtExe -Destination $setupExe -Force
$sub = Get-PeSubsystem $setupExe
if ($sub -ne 2) { throw "安装器的 PE 子系统是 $sub（应为 2=GUI）" }
Write-Host "PE 子系统校验：$([System.IO.Path]::GetFileName($setupExe)) = GUI(2)"

# R279-fix 防回归：安装器必须有 PE 资源目录（DataDirectory[2] 非 0）。
# 资源目录为空 = Manifest 没写进去 = 启动必弹「找不到序数 380」。
function Get-PeResourceRva([string]$Path) {
    $bytes = [System.IO.File]::ReadAllBytes((Resolve-Path -LiteralPath $Path).ProviderPath)
    $pe = [BitConverter]::ToInt32($bytes, 0x3C)
    $opt = $pe + 24
    $magic = [BitConverter]::ToUInt16($bytes, $opt)
    $dd = $opt + $(if ($magic -eq 0x20B) { 112 } else { 96 })
    return [BitConverter]::ToInt32($bytes, $dd + 2 * 8)
}
$resRva = Get-PeResourceRva $setupExe
if ($resRva -eq 0) {
    throw "安装器没有 PE 资源目录（Manifest 未嵌入），会造成序数 380 启动失败：$setupExe"
}
Write-Host "Manifest 资源目录校验：RVA=0x$('{0:X}' -f $resRva)（非 0，清单已嵌入）"

# 两个 zip 里必须真的有客户端壳，否则解压后双击还是回落到浏览器
Add-Type -AssemblyName System.IO.Compression.FileSystem
foreach ($zipName in @("EFTMap-Portable-$version.zip", "EFTMap-AppWindow-$version.zip")) {
    $zipPath = Join-Path $Release $zipName
    $zip = [System.IO.Compression.ZipFile]::OpenRead($zipPath)
    try {
        $hasShell = @($zip.Entries | Where-Object { $_.FullName -like "*\EFTMapDesktop.exe" }).Count -gt 0
    } finally { $zip.Dispose() }
    if (-not $hasShell) { throw "$zipName 里没有 EFTMapDesktop.exe" }
    Write-Host "产物校验：$zipName 含 EFTMapDesktop.exe"
}

# R280.1：不再在构建末尾做递归删除 —— 本机对大目录的 Remove-Item 会被安全
# 钩子/文件占用挂住，甚至让脚本不退出。两个目录都是纯中间产物，保留即可：
#   $Staging    = build\_release（AppWindow 变体暂存）
#   $setupBuild = %TEMP%\EFTMap-Setup-Build-<版本>（Setup 的 C: 盘构建目录）
# 下次构建前把旧目录改名挪开即可（脚本开头会新建）。
Write-Host "中间产物保留：$Staging / $setupBuild"

Write-Host ""
Write-Host "发布产物（$Release）："
Get-ChildItem $Release -File | Sort-Object Name | ForEach-Object {
    "  {0}  （{1:N1} MB）" -f $_.Name, ($_.Length / 1MB)
}

# ---------------------------------------------------------------- 校验和
# 发布页要能自证「下载的文件没被改过」。只对本版本的三件套出 SHA256，
# 不动 release/ 里的历史版本；格式与 sha256sum / certutil 都能直接校验：
#   sha256sum -c SHA256SUMS.txt        （Linux / Git Bash）
#   certutil -hashfile 文件名 SHA256   （Windows 手工比对）
$artifactNames = @(
    "EFTMap-Setup-$version.exe",
    "EFTMap-Portable-$version.zip",
    "EFTMap-AppWindow-$version.zip"
)
$sumLines = @()
foreach ($name in $artifactNames) {
    $file = Join-Path $Release $name
    if (-not (Test-Path -LiteralPath $file)) { throw "校验和阶段缺少产物：$name" }
    $hash = (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant()
    $sumLines += ("{0}  {1}" -f $hash, $name)
}
$sumFile = Join-Path $Release "SHA256SUMS.txt"
# 用 ASCII 无 BOM 写：带 BOM 会让 sha256sum 把文件名读成乱码。
[System.IO.File]::WriteAllText($sumFile, (($sumLines -join "`n") + "`n"),
                               (New-Object System.Text.UTF8Encoding($false)))
Write-Host ""
Write-Host "校验和已写出：$sumFile"
$sumLines | ForEach-Object { Write-Host "  $_" }

