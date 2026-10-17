<#
EFT 互动地图 · 打包脚本（PyInstaller onedir）

用法：
    powershell -ExecutionPolicy Bypass -File build\build.ps1
    powershell -ExecutionPolicy Bypass -File build\build.ps1 -Run   # 打包完顺便启动

产出：dist\EFTMap\EFTMap.exe —— 双击即用，完全离线，站点文件随包分发。
#>
[CmdletBinding()]
param(
    [switch]$Run
)

$ErrorActionPreference = "Stop"

$BuildDir = $PSScriptRoot
$Root = Split-Path -Parent $BuildDir
$Dist = Join-Path $Root "dist"
$Work = Join-Path $Root "build\_work"
$Target = Join-Path $Dist "EFTMap"

Write-Host "仓库根目录：$Root"

# 覆盖 exe 前必须先结束正在运行的旧实例，否则会报“拒绝访问”
Get-Process -Name EFTMap -ErrorAction SilentlyContinue | ForEach-Object {
    Write-Host "结束正在运行的 EFTMap（pid=$($_.Id)）"
    $_ | Stop-Process -Force
}

if (Test-Path $Work) { Remove-Item -Recurse -Force $Work }
if (Test-Path $Target) { Remove-Item -Recurse -Force $Target }

python -m PyInstaller `
    --noconfirm --clean `
    --onedir --noconsole `
    --name EFTMap `
    --distpath $Dist `
    --workpath $Work `
    --specpath $BuildDir `
    --paths (Join-Path $Root "tools") `
    --add-data "$Root\index.html;." `
    --add-data "$Root\style.css;." `
    --add-data "$Root\app.js;." `
    --add-data "$Root\data;data" `
    --add-data "$Root\assets;assets" `
    (Join-Path $Root "tools\launcher.py")

if ($LASTEXITCODE -ne 0) { throw "PyInstaller 打包失败（退出码 $LASTEXITCODE）" }

# PyInstaller 6.x 把资源放进 _internal；5.x 放在 exe 同级，这里两种都兼容
$Internal = Join-Path $Target "_internal"
if (-not (Test-Path $Internal)) { $Internal = $Target }

$Exe = Join-Path $Target "EFTMap.exe"
$MustHave = @(
    $Exe,
    (Join-Path $Internal "index.html"),
    (Join-Path $Internal "style.css"),
    (Join-Path $Internal "app.js"),
    (Join-Path $Internal "data\maps.json"),
    (Join-Path $Internal "assets\maps")
)
foreach ($p in $MustHave) {
    if (-not (Test-Path $p)) { throw "打包产物缺少必需文件：$p" }
}

$svgCount = (Get-ChildItem (Join-Path $Internal "assets\maps") -Filter *.svg).Count
$sizeMB = [math]::Round(((Get-ChildItem $Target -Recurse -File | Measure-Object -Property Length -Sum).Sum / 1MB), 1)

Write-Host ""
Write-Host "打包完成：$Exe"
Write-Host "  底图 SVG：$svgCount 张"
Write-Host "  产物体积：$sizeMB MB"
Write-Host "  双击 $Exe 即可启动（启动框 → 自动打开浏览器）。"

if ($Run) {
    Write-Host "启动 $Exe"
    Start-Process $Exe
}
