# Build the standalone EFT price collector (PyInstaller onefile, console).
#
#   powershell -ExecutionPolicy Bypass -File tools\build_price_collector.ps1
#
# Output: dist\EFTPriceCollector\
#   EFTPriceCollector.exe   (bundled Python runtime, no client / no Python needed)
#   install.bat / uninstall.bat / README.txt
#
# The .bat files are written here as pure ASCII on purpose: double-click must not
# garble Chinese. All Chinese text is printed by the exe itself.

param(
  [string]$Python = "C:\Python314\python.exe"
)

$ErrorActionPreference = "Stop"

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = Split-Path -Parent $here
$out = Join-Path $repo "dist\EFTPriceCollector"
$work = Join-Path $repo "build\price-collector"
$script = Join-Path $here "price_collect.py"
$readme = Join-Path $here "price_collector_readme.txt"

if (-not (Test-Path $Python)) { throw "Python not found: $Python" }
if (-not (Test-Path $script)) { throw "Collector script not found: $script" }

New-Item -ItemType Directory -Force -Path $out | Out-Null

Write-Host "Building EFTPriceCollector.exe ..."
& $Python -m PyInstaller `
  --noconfirm --clean --onefile --console `
  --name EFTPriceCollector `
  --distpath $out --workpath $work --specpath $work `
  --paths $here `
  --exclude-module tkinter --exclude-module unittest --exclude-module pydoc `
  --exclude-module doctest --exclude-module sqlite3 `
  $script
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE" }

$exe = Join-Path $out "EFTPriceCollector.exe"
if (-not (Test-Path $exe)) { throw "Expected output missing: $exe" }

# install.bat (ASCII only)
$installBat = @'
@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Registering scheduled task EFTPriceCollector (every 30 minutes) ...
echo.
"%~dp0EFTPriceCollector.exe" --install
set RC=%ERRORLEVEL%
echo.
if "%RC%"=="0" (echo Done.) else (echo Failed, exit code %RC%.)
echo.
pause
exit /b %RC%
'@
Set-Content -Path (Join-Path $out "install.bat") -Value $installBat -Encoding Ascii

# uninstall.bat (ASCII only, asks before deleting data)
$uninstallBat = @'
@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo This removes the scheduled task and autostart entries.
set /p PURGE=Also delete collected price data? [y/N] 
echo.
if /i "%PURGE%"=="y" (
  "%~dp0EFTPriceCollector.exe" --uninstall --purge
) else (
  "%~dp0EFTPriceCollector.exe" --uninstall
)
set RC=%ERRORLEVEL%
echo.
if "%RC%"=="0" (echo Done.) else (echo Failed, exit code %RC%.)
echo.
pause
exit /b %RC%
'@
Set-Content -Path (Join-Path $out "uninstall.bat") -Value $uninstallBat -Encoding Ascii

if (Test-Path $readme) {
  Copy-Item $readme (Join-Path $out "README.txt") -Force
}

$size = (Get-Item $exe).Length
Write-Host ""
Write-Host ("Done. exe: {0}" -f $exe)
Write-Host ("Size: {0:N1} MB" -f ($size / 1MB))
