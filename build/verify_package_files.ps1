# EFT 互动地图 · 打包清单完整性校验（可单独运行）
#
# 用法：
#   powershell -ExecutionPolicy Bypass -File build\verify_package_files.ps1
#   powershell -ExecutionPolicy Bypass -File build\verify_package_files.ps1 -CheckOnly
#
# 行为：
#   1. 从 index.html 解析本地 script / link 引用；
#   2. 合并 package_files.ps1 里的运行期 data 清单、JS 直写路径、assets 整目录；
#   3. 把这份清单复制到 build\_staging_check（不碰 dist/、release/）；
#   4. 比较“预期文件”和“staging 实际文件”，缺失或出现未登记文件都让校验失败。
#
# 只读写 build/_staging_check，不修改站点源码、不修改发布目录。

[CmdletBinding()]
param(
    [string]$Root,
    [string]$Staging,
    [switch]$CheckOnly
)

$ErrorActionPreference = "Stop"

if (-not $Root) { $Root = Split-Path -Parent $PSScriptRoot }
if (-not $Staging) { $Staging = Join-Path $PSScriptRoot "_staging_check" }

. (Join-Path $PSScriptRoot "package_files.ps1")

Write-Host "运行文件清单：$PSScriptRoot\package_files.ps1"
Write-Host "站点根目录：$Root"

if ($CheckOnly) {
    if (-not (Test-Path -LiteralPath $Staging -PathType Container)) {
        throw "staging 不存在：$Staging（去掉 -CheckOnly 可重新生成）"
    }
    $expected = Get-RuntimePackageFiles -Root $Root
} else {
    $expected = Stage-RuntimePackage -Root $Root -Destination $Staging
}

Test-RuntimePackage -Root $Root -Staging $Staging -Expected $expected

$expectedBytes = 0
foreach ($rel in $expected) {
    $full = Join-Path $Staging $rel.Replace("/", "\")
    $expectedBytes += (Get-Item -LiteralPath $full).Length
}
Write-Host ("staging 路径：{0}" -f $Staging)
Write-Host ("staging 体积：{0:N1} MB" -f ($expectedBytes / 1MB))
