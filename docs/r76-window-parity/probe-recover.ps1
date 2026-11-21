# R76 crash self-heal evidence: kill WebView2 processes, verify controller rebuild.
# Usage: powershell -ExecutionPolicy Bypass -File probe-recover.ps1

$ErrorActionPreference = "Stop"
$base = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = (Resolve-Path (Join-Path $base "..\..")).Path
$run = Join-Path $base "run-recover"
New-Item -ItemType Directory -Force -Path "$run\config","$run\logs","$run\shots","$run\userdata","$run\runtime" | Out-Null
Copy-Item "$repo\tools\host\bin\*" -Destination $run -Recurse -Force

$cfg = '{"overlay":{"enabled":true,"size_mode":"auto","scale":1.0,"shape":"circle","opacity":0.9,"corner":"bottom-right","click_through":true,"exclude_from_capture":false,"labels":true,"follow":true}}'
Set-Content -Path "$run\config\eftmap.config.json" -Value $cfg -Encoding UTF8

$p = Start-Process -FilePath "$run\EFTMapDesktop.exe" -ArgumentList @(
    '--root', $repo, '--backend-mode','dev','--python','python','--port','8817',
    '--config-dir',"$run\config",'--user-data',"$run\userdata",'--runtime-dir',"$run\runtime",
    '--log-dir',"$run\logs",'--log',"$run\logs\desktop.log",
    '--dump-json',"$run\logs\window-state.json",'--capture',"$run\shots",
    '--mini','--no-tray','--exit-after-ms','32000') -PassThru

Start-Sleep -Seconds 9
$wv = Get-CimInstance Win32_Process -Filter "Name='msedgewebview2.exe'" |
      Where-Object { $_.ParentProcessId -eq $p.Id }
"killing msedgewebview2 count=" + (@($wv).Count)
$wv | ForEach-Object { try { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue } catch { } }

Start-Sleep -Seconds 14
$rec = Select-String -Path "$run\logs\desktop.log" -Pattern "进程异常|已重建|自动恢复" | ForEach-Object { $_.Line }
"recovery log:"
$rec
$p.WaitForExit(50000) | Out-Null
"exit=" + $p.HasExited
