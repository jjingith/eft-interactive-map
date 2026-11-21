<#>
R75 · 安装器 PowerShell 控制台取证

安装器（`EFTMap-Setup-*.exe`）是 `--noconsole` 产物，但它内部 `subprocess.run(["powershell", ...])`
建快捷方式时，powershell.exe 是控制台子系统程序：父进程没有控制台，就会给子进程新建一个。

本脚本对比三种调用：
1. 旧写法（无 creationflags）→ 应出现可见 PowerShell 窗口；
2. 新写法（CREATE_NO_WINDOW）→ 不应出现；
3. 直接调用 installer.create_shortcut()（已经修好的生产函数）→ 不应出现，且快捷方式生成。

用法：
    powershell -ExecutionPolicy Bypass -File docs\r75-local-client-no-console\probe-installer-console.ps1
#>
[CmdletBinding()]
param(
    [string]$Repo = ""
)

$ErrorActionPreference = "Continue"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

if (-not $Repo) { $Repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot) }

Add-Type @'
using System;using System.Text;using System.Runtime.InteropServices;
public class R75Console {
    public delegate bool EnumProc(IntPtr h, IntPtr p);
    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc lp, IntPtr p);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowTextW(IntPtr h, StringBuilder s, int n);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetClassNameW(IntPtr h, StringBuilder s, int n);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
    public static string[] Visible() {
        var list = new System.Collections.Generic.List<string>();
        EnumWindows((h, p) => {
            var cls = new StringBuilder(256); GetClassNameW(h, cls, 256);
            if (cls.ToString() == "ConsoleWindowClass" && IsWindowVisible(h)) {
                uint pid; GetWindowThreadProcessId(h, out pid);
                var title = new StringBuilder(256); GetWindowTextW(h, title, 256);
                list.Add(string.Format("pid={0} title={1}", pid, title));
            }
            return true;
        }, IntPtr.Zero);
        return list.ToArray();
    }
}
'@

$py = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $py) { throw "找不到 python.exe" }
$pyw = Join-Path (Split-Path $py) "pythonw.exe"

function Probe([string]$label, [scriptblock]$action) {
    $before = @([R75Console]::Visible())
    & $action
    Start-Sleep -Milliseconds 900
    $after = @([R75Console]::Visible())
    $delta = @($after | Where-Object { $before -notcontains $_ })
    Write-Host "$label"
    Write-Host ("  可见控制台窗口增量：{0}" -f $delta.Count)
    if ($delta.Count -gt 0) { $delta | ForEach-Object { Write-Host ("    " + $_) } }
    Start-Sleep -Seconds 3
    return $delta.Count
}

$oldCode = "import subprocess; subprocess.run(['powershell','-NoProfile','-Command','Start-Sleep -Milliseconds 1500'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)"
$newCode = "import subprocess; subprocess.run(['powershell','-NoProfile','-Command','Start-Sleep -Milliseconds 1500'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))"

Probe "[1] 旧写法：无 creationflags（复现用户看到的窗口）" { & $pyw -c $oldCode }
Probe "[2] 新写法：CREATE_NO_WINDOW" { & $pyw -c $newCode }

$lnk = Join-Path $env:TEMP "eftmap-r75-shortcut.lnk"
$lnkLog = Join-Path $env:TEMP "eftmap-r75-shortcut.log"
$runner = Join-Path $env:TEMP "eftmap-r75-shortcut.py"
Remove-Item $lnk, $lnkLog, $runner -Force -ErrorAction SilentlyContinue
$body = @"
import sys, traceback
sys.path.insert(0, r'$Repo\tools')
try:
    import installer
    installer.create_shortcut(r'$lnk', r'$Repo\dist\EFTMap\EFTMapDesktop.exe', r'$Repo\dist\EFTMap', r'$Repo\dist\EFTMap\EFTMap.exe')
    open(r'$lnkLog', 'w', encoding='utf-8').write('ok')
except Exception:
    open(r'$lnkLog', 'w', encoding='utf-8').write(traceback.format_exc())
"@
[System.IO.File]::WriteAllText($runner, $body, (New-Object System.Text.UTF8Encoding($false)))

Probe "[3] installer.create_shortcut()（已修复的生产代码）" { & $pyw $runner; Start-Sleep -Seconds 2 }
Write-Host ("  快捷方式生成：{0}" -f (Test-Path $lnk))
Write-Host ("  执行结果：{0}" -f (Get-Content $lnkLog -ErrorAction SilentlyContinue))
Remove-Item $lnk, $lnkLog, $runner -Force -ErrorAction SilentlyContinue
