<#>
R75 · 控制台窗口实测脚本

用法：
    powershell -ExecutionPolicy Bypass -File docs\r75-local-client-no-console\measure-console.ps1 -Exe dist\EFTMap\EFTMap.exe
    powershell -ExecutionPolicy Bypass -File docs\r75-local-client-no-console\measure-console.ps1 -Exe dist\EFTMap\EFTMapDesktop.exe -Seconds 25

判定口径（全部是操作系统事实，不是读代码推断）：
1. 新增 conhost.exe（进程级）：父子关系一并打印；
2. 新增可见控制台窗口（user32 EnumWindows + ConsoleWindowClass + IsWindowVisible）；
3. 壳自己的顶层窗口：class / 标题 / 扩展样式（0x80=TOOLWINDOW 不进任务栏，0x8=TOPMOST）；
4. 浏览器进程增量（msedge / chrome 主进程，排除 msedgewebview2）；
5. 启动后 60 秒内的全部 TCP 端点（用于「纯本地」取证）。
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Exe,
    [int]$Seconds = 25
)

$ErrorActionPreference = "Continue"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

Add-Type @'
using System;using System.Text;using System.Runtime.InteropServices;
public class R75Win {
    public delegate bool EnumProc(IntPtr h, IntPtr p);
    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc lp, IntPtr p);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowTextW(IntPtr h, StringBuilder s, int n);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetClassNameW(IntPtr h, StringBuilder s, int n);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
    [DllImport("user32.dll")] public static extern int GetWindowLong(IntPtr h, int idx);

    public static string[] ForPid(uint target) {
        var list = new System.Collections.Generic.List<string>();
        EnumWindows((h, p) => {
            uint pid; GetWindowThreadProcessId(h, out pid);
            if (pid != target) return true;
            var title = new StringBuilder(256); GetWindowTextW(h, title, 256);
            var cls = new StringBuilder(256); GetClassNameW(h, cls, 256);
            int ex = GetWindowLong(h, -20);
            list.Add(string.Format("hwnd=0x{0:X} visible={1} exstyle=0x{2:X8} class={3} title={4}",
                h.ToInt64(), IsWindowVisible(h) ? 1 : 0, ex, cls, title));
            return true;
        }, IntPtr.Zero);
        return list.ToArray();
    }

    public static string[] VisibleConsoles() {
        var list = new System.Collections.Generic.List<string>();
        EnumWindows((h, p) => {
            var cls = new StringBuilder(256); GetClassNameW(h, cls, 256);
            if (cls.ToString() == "ConsoleWindowClass" && IsWindowVisible(h)) {
                uint pid; GetWindowThreadProcessId(h, out pid);
                var title = new StringBuilder(256); GetWindowTextW(h, title, 256);
                list.Add(string.Format("console hwnd=0x{0:X} pid={1} title={2}", h.ToInt64(), pid, title));
            }
            return true;
        }, IntPtr.Zero);
        return list.ToArray();
    }
}
'@

$full = (Resolve-Path $Exe).Path
Write-Host "==== R75 控制台实测 ===="
Write-Host "目标：$full"

Get-Process EFTMap, EFTMapDesktop -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 2

$baseConhost = @(Get-CimInstance Win32_Process -Filter "Name='conhost.exe'" | Select-Object -ExpandProperty ProcessId)
$baseConsoles = @([R75Win]::VisibleConsoles())
$baseBrowser = @(Get-CimInstance Win32_Process |
                 Where-Object { $_.Name -eq 'msedge.exe' -or $_.Name -eq 'chrome.exe' } |
                 Select-Object -ExpandProperty ProcessId)

Start-Process $full | Out-Null
Start-Sleep -Seconds $Seconds

Write-Host "`n--- 1. 进程树（EFTMap*） ---"
Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^EFTMap' } |
    Select-Object Name, ProcessId, ParentProcessId | Format-Table -AutoSize | Out-String | Write-Host

Write-Host "--- 2. 新增 conhost.exe ---"
$new = @(Get-CimInstance Win32_Process -Filter "Name='conhost.exe'" |
         Where-Object { $baseConhost -notcontains $_.ProcessId })
if ($new.Count -eq 0) {
    Write-Host "（无）"
} else {
    foreach ($c in $new) {
        $parent = Get-CimInstance Win32_Process -Filter "ProcessId=$($c.ParentProcessId)"
        Write-Host ("conhost pid={0} parent={1} {2}" -f $c.ProcessId, $c.ParentProcessId, $parent.Name)
    }
}

Write-Host "--- 3. 新增可见控制台窗口 ---"
$nowConsoles = @([R75Win]::VisibleConsoles())
$delta = @($nowConsoles | Where-Object { $baseConsoles -notcontains $_ })
if ($delta.Count -eq 0) { Write-Host "（无）" } else { $delta | ForEach-Object { Write-Host $_ } }

Write-Host "--- 4. 壳的顶层窗口 ---"
$shell = Get-CimInstance Win32_Process -Filter "Name='EFTMapDesktop.exe'" | Select-Object -First 1
if ($shell) { [R75Win]::ForPid([uint32]$shell.ProcessId) | ForEach-Object { Write-Host $_ } }
else { Write-Host "（壳进程不存在）" }

Write-Host "--- 5. 浏览器进程增量（不含 msedgewebview2） ---"
$ourPids = @(Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^EFTMap' } |
             Select-Object -ExpandProperty ProcessId)
function Get-Ancestors([int]$procId) {
    $out = @(); $p = $procId
    for ($i = 0; $i -lt 4 -and $p; $i++) {
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$p" -ErrorAction SilentlyContinue
        if (-not $proc) { break }
        $out += $proc.ProcessId
        $p = $proc.ParentProcessId
    }
    return $out
}
$nowBrowser = @(Get-CimInstance Win32_Process |
                Where-Object { $_.Name -eq 'msedge.exe' -or $_.Name -eq 'chrome.exe' } |
                Select-Object -ExpandProperty ProcessId)
$added = @($nowBrowser | Where-Object { $baseBrowser -notcontains $_ })
$spawned = 0
if ($added.Count -eq 0) { Write-Host "（无）" }
else {
    foreach ($p in $added) {
        $pr = Get-CimInstance Win32_Process -Filter "ProcessId=$p"
        $chain = Get-Ancestors $p
        $mine = @($chain | Where-Object { $ourPids -contains $_ }).Count -gt 0
        if ($mine) { $spawned++ }
        Write-Host ("+ {0} pid={1} parent={2} 本次启动派生={3}" -f $pr.Name, $p, $pr.ParentProcessId, $mine)
        Write-Host ("  cmd: {0}" -f $pr.CommandLine)
    }
}
Write-Host ("由本次启动派生的浏览器主进程数：{0}" -f $spawned)

Write-Host "--- 6. 60 秒内的 TCP 端点（壳 + 后端 + WebView2） ---"
$seen = @{}
for ($i = 0; $i -lt 30; $i++) {
    $pids = @(Get-CimInstance Win32_Process |
              Where-Object { $_.Name -match '^EFTMap' -or $_.Name -eq 'msedgewebview2.exe' } |
              Select-Object -ExpandProperty ProcessId)
    foreach ($c in @(Get-NetTCPConnection -ErrorAction SilentlyContinue | Where-Object { $pids -contains $_.OwningProcess })) {
        $key = "$($c.RemoteAddress):$($c.RemotePort) [$($c.State)]"
        if ($seen.ContainsKey($key)) { $seen[$key]++ } else { $seen[$key] = 1 }
    }
    Start-Sleep -Seconds 2
}
$seen.GetEnumerator() | Sort-Object Name | ForEach-Object { Write-Host ("  {0} ×{1}" -f $_.Key, $_.Value) }
$off = @($seen.Keys | Where-Object { $_ -notmatch '^(127\.0\.0\.1|::1|0\.0\.0\.0|\[::\]|\[::1\]):' })
Write-Host ("非回环远端连接：{0}" -f $(if ($off.Count -eq 0) { "（无）" } else { $off -join ", " }))
