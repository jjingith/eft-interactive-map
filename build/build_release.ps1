<#
EFT 互动地图 · 发布三件套构建

用法：
    powershell -ExecutionPolicy Bypass -File build\build_release.ps1
    powershell -ExecutionPolicy Bypass -File build\build_release.ps1 -SkipBase   # dist\EFTMap 已就绪时跳过基础打包

产出（release\ 下）：
    EFTMap-Portable-<版本>.zip     解压即用：界面开在系统默认浏览器
    EFTMap-AppWindow-<版本>.zip    加壳版：界面开在独立应用窗口（无地址栏，仍用 Edge/Chrome 内核）
    EFTMap-Setup-<版本>.exe        一键安装器：装到 %LOCALAPPDATA%\EFTMap + 快捷方式 + 卸载项

依赖：只有 PyInstaller（与基础打包同）+ PowerShell 自带的 Compress-Archive。
#>
[CmdletBinding()]
param(
    [switch]$SkipBase
)

$ErrorActionPreference = "Stop"

$BuildDir = $PSScriptRoot
$Root = Split-Path -Parent $BuildDir
$Dist = Join-Path $Root "dist"
$Target = Join-Path $Dist "EFTMap"
$Release = Join-Path $Root "release"
$Staging = Join-Path $Root "build\_release"

# 版本号从 serve.py 读，保证发布物与运行期一致
$version = (Select-String -Path (Join-Path $Root "tools\serve.py") -Pattern '^VERSION\s*=\s*"([^"]+)"').Matches[0].Groups[1].Value
if (-not $version) { throw "没能从 tools\serve.py 读到 VERSION" }
Write-Host "版本：$version"

# 1) 基础 onedir 打包
if (-not $SkipBase) {
    & (Join-Path $BuildDir "build.ps1")
    if ($LASTEXITCODE -ne 0) { throw "build.ps1 失败" }
}
if (-not (Test-Path (Join-Path $Target "EFTMap.exe"))) { throw "dist\EFTMap 不存在，先跑 build.ps1" }

if (Test-Path $Release) { Remove-Item -Recurse -Force $Release }
if (Test-Path $Staging) { Remove-Item -Recurse -Force $Staging }
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
Write-Host "打包 Setup…"
$setupWork = Join-Path $BuildDir "_work_installer"
python -m PyInstaller `
    --noconfirm --clean `
    --onefile --noconsole `
    --name "EFTMap-Setup-$version" `
    --distpath $Release `
    --workpath $setupWork `
    --specpath $BuildDir `
    --paths (Join-Path $Root "tools") `
    --add-data "$Target;payload" `
    (Join-Path $Root "tools\installer.py")
if ($LASTEXITCODE -ne 0) { throw "安装器打包失败（退出码 $LASTEXITCODE）" }

Remove-Item -Recurse -Force $Staging -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force $setupWork -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "发布产物（$Release）："
Get-ChildItem $Release -File | Sort-Object Name | ForEach-Object {
    "  {0}  （{1:N1} MB）" -f $_.Name, ($_.Length / 1MB)
}
