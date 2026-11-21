# R76 runtime evidence: taskbar / conhost / process tree / hotkey / focus.
# Usage: powershell -ExecutionPolicy Bypass -File docs/r76-window-parity/probe-runtime.ps1

$ErrorActionPreference = "Stop"
$base = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = (Resolve-Path (Join-Path $base "..\..")).Path
$run = Join-Path $base "run-clamp"
New-Item -ItemType Directory -Force -Path "$run\config","$run\logs","$run\shots","$run\userdata","$run\runtime" | Out-Null
Copy-Item "$repo\tools\host\bin\*" -Destination $run -Recurse -Force

# scale=2.0 + huge offset: size should be min(1920,1040)*20%*2 = 416, position clamped into work area.
$cfg = '{"overlay":{"enabled":true,"size_mode":"auto","scale":2.0,"shape":"square","opacity":0.9,"corner":"bottom-right","offset_x":800,"offset_y":800,"click_through":true,"exclude_from_capture":false,"labels":true,"follow":true}}'
Set-Content -Path "$run\config\eftmap.config.json" -Value $cfg -Encoding UTF8

Add-Type @"
using System;
using System.Text;
using System.Runtime.InteropServices;
public static class R76 {
    [DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte scan, int flags, int extra);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
    public static void HotkeyCtrlShiftM() {
        keybd_event((byte)0x11, 0, 0, 0); keybd_event((byte)0x10, 0, 0, 0);
        keybd_event((byte)0x4D, 0, 0, 0); keybd_event((byte)0x4D, 0, 2, 0);
        keybd_event((byte)0x10, 0, 2, 0); keybd_event((byte)0x11, 0, 2, 0);
    }
}
"@

# Stand-in for a fullscreen game: Notepad kept in the foreground.
$np = Start-Process notepad.exe -PassThru
$npHandle = [IntPtr]::Zero
for ($i = 0; $i -lt 20 -and $npHandle -eq [IntPtr]::Zero; $i++) {
    Start-Sleep -Milliseconds 300
    $np.Refresh()
    $npHandle = $np.MainWindowHandle
}
"notepad hwnd=$($npHandle.ToInt64())"

$p = Start-Process -FilePath "$run\EFTMapDesktop.exe" -ArgumentList @(
    '--root', $repo, '--backend-mode','dev','--python','python','--port','8813',
    '--config-dir',"$run\config",'--user-data',"$run\userdata",'--runtime-dir',"$run\runtime",
    '--log-dir',"$run\logs",'--log',"$run\logs\desktop.log",
    '--dump-json',"$run\logs\window-state.json",'--capture',"$run\shots",
    '--mini','--no-tray','--exit-after-ms','26000') -PassThru

Start-Sleep -Seconds 9

$conhost = Get-CimInstance Win32_Process -Filter "Name='conhost.exe'" |
    Where-Object { $_.ParentProcessId -eq $p.Id }
"conhost children of shell pid=$($p.Id): " + (@($conhost).Count)

"MainWindowTitle: " + (@(Get-Process -Id $p.Id).MainWindowTitle -join '|')

$children = Get-CimInstance Win32_Process | Where-Object { $_.ParentProcessId -eq $p.Id }
"children: " + (($children | ForEach-Object { "$($_.Name)#$($_.ProcessId)" }) -join ', ')

[void][R76]::SetForegroundWindow($npHandle)
Start-Sleep -Milliseconds 600
$fg1 = [IntPtr][R76]::GetForegroundWindow()
"foreground before hotkey: $($fg1.ToInt64()) notepad=$($npHandle.ToInt64()) match=$($fg1 -eq $npHandle)"
[R76]::HotkeyCtrlShiftM()
Start-Sleep -Milliseconds 600
$fg2 = [IntPtr][R76]::GetForegroundWindow()
"foreground after hide: $($fg2.ToInt64()) same=$($fg1 -eq $fg2)"
[R76]::HotkeyCtrlShiftM()
Start-Sleep -Milliseconds 600
$fg3 = [IntPtr][R76]::GetForegroundWindow()
"foreground after show: $($fg3.ToInt64()) same=$($fg1 -eq $fg3)"

$p.WaitForExit(40000) | Out-Null
"exit=" + $p.HasExited
try { $np | Stop-Process -Force } catch { }
