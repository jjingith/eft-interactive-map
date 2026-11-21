# EFT 互动地图 · 桌面壳构建脚本（只用 Windows 自带 .NET Framework 4.8 的 csc.exe）
#
# 不联网、不装 SDK、不拉 NuGet：WebView2 的两个运行库随仓库放在 vendor/。
# 产物：bin/EFTMapDesktop.exe + bin/Microsoft.Web.WebView2.Core.dll + bin/WebView2Loader.dll
#
# 小地图不再是独立 exe：MiniHost.cs 只提供 MiniForm，由 DesktopShell.cs 的
# 主壳在同一进程创建第二个窗口。
#
# 用法：
#   powershell -ExecutionPolicy Bypass -File tools/host/build.ps1

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$csc = Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319\csc.exe"
if (-not (Test-Path $csc)) { throw "找不到 .NET Framework 4.8 的 csc.exe：$csc" }

$srcDir = Join-Path $here "src"
$src = @(
  (Join-Path $srcDir "MiniHost.cs"),
  (Join-Path $srcDir "DesktopShell.cs")
)
$manifest = Join-Path $srcDir "app.manifest"
# R282：应用图标。同一份 ico 同时写进 exe 资源（任务栏/资源管理器）与托管资源
# （窗体 / 托盘用 AppIcon() 读取），保证没有外部文件也能显示。
$repoRoot = Split-Path -Parent (Split-Path -Parent $here)
$appIcon = Join-Path $repoRoot "assets\app.ico"
if (-not (Test-Path $appIcon)) { throw "缺少应用图标：$appIcon" }
$outDir = Join-Path $here "bin"
$vendor = Join-Path $here "vendor"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
# 旧原型 MiniHost.exe 不再发布；避免 bin 目录里留下旧单窗 exe 被误用。
$legacyMiniHost = Join-Path $outDir "MiniHost.exe"
if (Test-Path $legacyMiniHost) { Remove-Item -LiteralPath $legacyMiniHost -Force }

$refs = @(
  (Join-Path $vendor "Microsoft.Web.WebView2.Core.dll"),
  (Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319\System.Web.Extensions.dll"),
  (Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319\System.Windows.Forms.dll"),
  (Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319\System.Drawing.dll"),
  (Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319\System.Core.dll")
)
foreach ($r in $refs) { if (-not (Test-Path $r)) { throw "缺少引用：$r" } }

$argsList = @(
  "/nologo", "/target:winexe", "/platform:x64", "/optimize+",
  "/out:$outDir\EFTMapDesktop.exe",
  "/win32manifest:$manifest",
  "/win32icon:$appIcon",
  "/resource:$appIcon,AppIcon"
) + ($refs | ForEach-Object { "/r:$_" }) + $src

& $csc $argsList
if ($LASTEXITCODE -ne 0) { throw "csc 编译失败，退出码 $LASTEXITCODE" }

Copy-Item (Join-Path $vendor "Microsoft.Web.WebView2.Core.dll") $outDir -Force
Copy-Item (Join-Path $vendor "WebView2Loader.dll") $outDir -Force

Get-ChildItem $outDir | Select-Object Name, Length | Format-Table -AutoSize
