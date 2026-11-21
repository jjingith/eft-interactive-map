# R76 full-desktop screenshot: shows mini window shape / position on screen.
# Usage: powershell -File probe-screen.ps1 -tag circle -shape circle -scale 1.0 -ox 0 -oy 0 -port 8815
param(
    [string]$tag = "circle",
    [string]$shape = "circle",
    [double]$scale = 1.0,
    [int]$ox = 0,
    [int]$oy = 0,
    [int]$port = 8815
)

$ErrorActionPreference = "Stop"
$base = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = (Resolve-Path (Join-Path $base "..\..")).Path
$run = Join-Path $base "run-screen-$tag"
New-Item -ItemType Directory -Force -Path "$run\config","$run\logs","$run\shots","$run\userdata","$run\runtime" | Out-Null
Copy-Item "$repo\tools\host\bin\*" -Destination $run -Recurse -Force

$cfg = '{"overlay":{"enabled":true,"size_mode":"auto","scale":' + $scale + ',"shape":"' + $shape +
       '","opacity":0.9,"corner":"bottom-right","offset_x":' + $ox + ',"offset_y":' + $oy +
       ',"click_through":true,"exclude_from_capture":false,"labels":true,"follow":true}}'
Set-Content -Path "$run\config\eftmap.config.json" -Value $cfg -Encoding UTF8

$p = Start-Process -FilePath "$run\EFTMapDesktop.exe" -ArgumentList @(
    '--root', $repo, '--backend-mode','dev','--python','python','--port',$port,
    '--config-dir',"$run\config",'--user-data',"$run\userdata",'--runtime-dir',"$run\runtime",
    '--log-dir',"$run\logs",'--log',"$run\logs\desktop.log",
    '--dump-json',"$run\logs\window-state.json",'--capture',"$run\shots",
    '--mini','--no-tray','--exit-after-ms','22000') -PassThru

Start-Sleep -Seconds 12

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$bmp = New-Object System.Drawing.Bitmap($bounds.Width, $bounds.Height)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
$out = Join-Path $base "desktop-$tag.png"
$bmp.Save($out, [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose()
$bmp.Dispose()
"screenshot: $out"

$p.WaitForExit(40000) | Out-Null
Get-Content "$run\logs\window-state.json" | Select-String -Pattern '"mini"' | ForEach-Object { $_.Line.Substring(0, [Math]::Min(600, $_.Line.Length)) }
