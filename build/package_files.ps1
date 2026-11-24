# EFT 互动地图 · 构建期运行文件清单与 staging 校验
#
# 这个文件只服务于打包，不参与运行期。
#
# 清单口径：
#   1. index.html 里实际引用的本地 script / link（以及 img src，当前没有）；
#   2. 运行期 JS 里直接写死的 data/、assets/ 文件（只收录“文件确实存在”的路径，
#      动态拼接目录仍由 assets 整目录覆盖）；
#   3. data/ 下的运行期 JSON / JS 显式清单（不用整目录，避免把备份和 raw 快照打进去）；
#   4. assets/ 整目录（图片资源由 data/JS 动态拼路径，逐文件列不现实），
#      再排除明确属于开发/源材料的子目录。
#
# 任何“看起来会进包、但实际不进包”的文件都必须在这里写明排除理由；
# 不允许靠“整目录复制时恰好没被引用”静默漏掉。

$script:RuntimeFiles = @(
    # ---- data/ 运行期数据（index.html / app.js / tasks.js / i18n.js 直接加载）----
    "data/ammo.json",
    "data/armor-bt.json",
    "data/armor-ricochet.json",
    "data/barriers.json",
    "data/bosses.json",
    "data/caliber-groups.json",
    "data/combat-targets.json",
    "data/editions.json",
    "data/flea-levels.json",
    # R62/R63：官方弹道模板（PenetrationPowerDiviation σ、Min/MaxFragmentsCount）。
    # app.js 的 ensureAmmoBallistic() 运行期直接 fetch 这个文件；同目录其余 game-truth
    # 文件（armor_items / armor_plates / globals_ballistic / meta）只服务构建期对照，
    # 见下方 ExcludePaths 排除条目。
    "data/game-truth/ammo_ballistic.json",
    # R79 三层行情：随包内置快照（免费档数据源），三模式各一份。
    "data/flea-prices.json",
    "data/flea-prices-pve.json",
    "data/flea-prices-pvps.json",
    # R305：游戏更新页的随包快照（tools/fetch_game_changes.py 生成）。
    # 缺它时「更新」页在离线状态下是空的，只有点过「检查更新」才有内容。
    "data/game-changes.json",
    "data/forge-constraints.json",
    "data/gun-compat.json",
    "data/gun-layout-calibration.json",
    "data/gun-platforms.json",
    "data/gun-presets.js",
    "data/gun-rates.json",
    "data/gun-stats.json",
    "data/gunslots.json",
    "data/gunsmith.json",
    "data/item-extra.json",
    "data/items.json",
    # R279：截图识别的短名表（tools/build_ocr_names.py 生成）。缺它时 matcher
    # 只剩全名匹配，游戏里印的短名（"BS"、"铝热剂"）几乎全识别不出来。
    "data/ocr-item-names.json",
    "data/maps.json",
    "data/meta.json",
    "data/roadnet.json",
    "data/satellite.json",
    "data/search-index.json",
    "data/season-documents.json",
    "data/task-images.json",
    "data/task-points.json",
    "data/wiki-maps.json",

    # i18n.js 运行期固定加载这 4 个；traders 是构建期翻译源，见下方排除。
    "data/i18n/ui-zh.json",
    "data/i18n/names.json",
    "data/i18n/items-zh.json",
    "data/i18n/poi-zh.json",

    # tasks.js 运行期按模式加载：tasks.<mode>.json + guides.<mode>.json，
    # 另外固定加载 traders / index / season。raw/ 是上游快照，见下方排除。
    "data/tasks/tasks.regular.json",
    "data/tasks/tasks.pve.json",
    "data/tasks/tasks.pvps.json",
    "data/tasks/guides.regular.json",
    "data/tasks/guides.pve.json",
    "data/tasks/guides.pvps.json",
    "data/tasks/traders.json",
    "data/tasks/index.json",
    "data/tasks/season.json",

    # index.html 目前没有 <script src="wiki-map.js">（官方图层面板的入口标签在前端改动里
    # 被移除，面板 DOM 仍在），但 build.ps1 仍要求产物里有这个文件、功能回退时需要它。
    # 因此按运行期文件显式收录；若后续确认彻底废弃，应同时删掉这条和 build.ps1 的必查项。
    "wiki-map.js",

    # 站点图标（index.html 的 <link rel="icon"> 指向它），根目录静态文件。
    "favicon.ico",

    # ---- 云账号（客户端）----
    # index.html 用 <script src="js/cloud.js"> 直接加载；菜单「云账号」的注册/登录/
    # 密码/设备列表全部由它渲染，漏了它菜单点开就是空壳。
    "js/cloud.js",
    # 云服务端证书（按 IP 校验 SAN + 指纹比对）；tools/serve.py 以
    # os.path.join(root, "assets", "cloud-ca.pem") 读取，运行期必需。
    # assets/ 整目录已覆盖，这里显式登记以防被后来的排除规则误伤。
    "assets/cloud-ca.pem",

    # ---- R84：XP 界面素材接入（本轮随包发布）----
    # 顶层菜单栏脚本（index.html 第 4 层脚本，负责菜单栏 / 上下文栏 / 状态栏）。
    "js/app-menubar.js",
    # R79 眼部防护新增的两个区域图标（配装「防护区域」列直接引用）。
    "assets/icons/zones/zone-eyes.png",
    "assets/icons/zones/zone-face-jaw.png",
    # XP 界面皮肤：CSS 两份 + 素材索引 + 53 张 PNG。
    # assets/ 整目录扫描已覆盖这些文件；这里逐条显式登记，是为了让「新界面的运行期依赖」
    # 一眼可见，并在素材被误删时让清单校验立刻失败（而不是打包后白屏）。
    # 明确不进包的 demo.html 与 _shots/ 见下方 ExcludePaths。
    "assets/xp-ui/xp-ui.css",
    "assets/xp-ui/xp-ui-app.css",
    # index.html 直接 <link> 的 styles/ 四份样式（design-tokens/ui-components 是 R19.24
    # 组件体系，modern-flat 是 R300 去位图覆盖层，market-dark 是 R302 市场暗色主题）。
    # 逐条显式登记：缺任意一个，VerifyOnly 必须失败，避免打包后整页样式退化。
    "styles/design-tokens.css",
    "styles/ui-components.css",
    "styles/modern-flat.css",
    "styles/market-dark.css",
    "assets/xp-ui/manifest.json",
    "assets/xp-ui/btn-disabled.png",
    "assets/xp-ui/btn-focus.png",
    "assets/xp-ui/btn-hover.png",
    "assets/xp-ui/btn-normal.png",
    "assets/xp-ui/btn-pressed.png",
    "assets/xp-ui/check-indeterminate.png",
    "assets/xp-ui/check-off.png",
    "assets/xp-ui/check-on.png",
    "assets/xp-ui/groupbox.png",
    "assets/xp-ui/input.png",
    "assets/xp-ui/plaque-1.png",
    "assets/xp-ui/plaque-2.png",
    "assets/xp-ui/plaque-3.png",
    "assets/xp-ui/progress-frame.png",
    "assets/xp-ui/radio-off.png",
    "assets/xp-ui/radio-on.png",
    "assets/xp-ui/scroll-h-thumb.png",
    "assets/xp-ui/scroll-h-track.png",
    "assets/xp-ui/scroll-v-arrow-down-hover.png",
    "assets/xp-ui/scroll-v-arrow-down-pressed.png",
    "assets/xp-ui/scroll-v-arrow-down.png",
    "assets/xp-ui/scroll-v-arrow-up-hover.png",
    "assets/xp-ui/scroll-v-arrow-up-pressed.png",
    "assets/xp-ui/scroll-v-arrow-up.png",
    "assets/xp-ui/scroll-v-glyph-down.png",
    "assets/xp-ui/scroll-v-glyph-up.png",
    "assets/xp-ui/scroll-v-thumb-hover.png",
    "assets/xp-ui/scroll-v-thumb-pressed.png",
    "assets/xp-ui/scroll-v-thumb.png",
    "assets/xp-ui/scroll-v-track.png",
    "assets/xp-ui/select-arrow.png",
    "assets/xp-ui/select.png",
    "assets/xp-ui/slider-v-thumb-hover.png",
    "assets/xp-ui/slider-v-thumb-pressed.png",
    "assets/xp-ui/slider-v-thumb.png",
    "assets/xp-ui/slider-v-track.png",
    "assets/xp-ui/tab-active.png",
    "assets/xp-ui/tab-inactive.png",
    "assets/xp-ui/thumb.png",
    "assets/xp-ui/titlebar.png",
    "assets/xp-ui/track.png",
    "assets/xp-ui/win-btn-close-hover.png",
    "assets/xp-ui/win-btn-close-pressed.png",
    "assets/xp-ui/win-btn-close.png",
    "assets/xp-ui/win-btn-max-hover.png",
    "assets/xp-ui/win-btn-max-pressed.png",
    "assets/xp-ui/win-btn-max.png",
    "assets/xp-ui/win-btn-min-hover.png",
    "assets/xp-ui/win-btn-min-pressed.png",
    "assets/xp-ui/win-btn-min.png",
    "assets/xp-ui/win-glyph-close.png",
    "assets/xp-ui/win-glyph-max.png",
    "assets/xp-ui/win-glyph-min.png"
)

# 不扫描的顶层目录（它们不属于站点根，运行期不会被 index.html / JS 访问）：
#   .git/、.pytest_cache/、.shots/、.workbuddy/、__pycache__/
#     —— 版本控制/测试/调试缓存
#   build/、build-cache/、dist/、release/
#     —— 构建脚本、上游原始缓存、打包产物、发布产物
#   docs/、tests/、tools/
#     —— 开发文档、测试、构建期数据管线；运行期由 Python 打包产物自带所需模块
#
# 需要整目录扫描的运行期目录。assets 的图片路径大量是运行期拼出来的，
# 逐文件列不现实，因此整目录收录，再用 $script:ExcludePaths 排除开发材料。
$script:RuntimeDirs = @(
    "assets",
    # R300/R302：视觉覆盖层样式放在 styles/，index.html 直接 <link> 引用。
    # 原先只列 assets/，styles/ 里两个旧 CSS 是靠历史 staging 残留才进包，
    # 新增的 modern-flat.css / market-dark.css 会被静默漏掉 —— 整目录收录修正。
    "styles"
)

# 明确不随包发布的文件 / 目录。Prefix 按前缀匹配，Exact 按完整相对路径匹配。
# 每一条都必须写原因；新增排除时不要只写“不要”。
$script:ExcludePaths = @(
    @{ Prefix = "ui-showcase"; Reason = "开发用 UI 组件展示页/样式/脚本，index.html 不引用，运行期不需要" },
    @{ Exact = "README.md"; Reason = "仓库说明文档，不是运行期资源" },
    @{ Exact = "AGENT_HANDOFF.md"; Reason = "开发交接文档，不是运行期资源" },
    @{ Exact = "eftmap.config.json"; Reason = "仓库内示例/旧配置；运行期配置在 %APPDATA%\EFTMap，见 config.default_storage_dir()" },
    @{ Exact = ".gitignore"; Reason = "Git 配置，不是运行期资源" },
    @{ Exact = "启动项目.bat"; Reason = "源码目录开发启动脚本，打包后由 EFTMap.exe 启动" },

    # 构建期数据源 / 备份 / 原始快照：保留在仓库供增量构建与审计，但不进安装包。
    @{ Exact = "data/gun-presets.json"; Reason = "构建期源数据；index.html 运行期加载的是 data/gun-presets.js（同一数据的内联版）" },
    @{ Exact = "data/hd-item-icons.json"; Reason = "构建期图标索引；运行期 app.js 按固定文件名直接引用 assets/icons-hd，不读这个 JSON" },
    @{ Exact = "data/i18n/traders.json"; Reason = "构建期翻译源；i18n.js 运行期只加载 ui-zh/names/items-zh/poi-zh 四个文件" },
    @{ Prefix = "data/tasks/raw/"; Reason = "上游原始快照（tasks/guides/traders 的 raw 版本与中文中间产物），运行期由 data/tasks 根目录的成品文件代替" },
    @{ Exact = "data/tasks/diff-report.json"; Reason = "构建期数据 diff 报告，运行期不加载" },
    # game-truth 真值库：只有 ammo_ballistic.json 进包（app.js 运行期加载，已列入 RuntimeFiles）。
    # 其余四个是 r58b/r64 构建期对照源（armor-bt / armor-ricochet 的上游证据），
    # 前端与 tools/serve.py 运行期都不读，进包只会让产物虚胖 2 MB+。
    @{ Exact = "data/game-truth/armor_items.json"; Reason = "构建期真值源（r58b 抽取、r64 对照用），运行期不加载" },
    @{ Exact = "data/game-truth/armor_plates.json"; Reason = "构建期真值源（插板槽位参数），运行期不加载" },
    @{ Exact = "data/game-truth/globals_ballistic.json"; Reason = "构建期真值源（HeavyVests 技能参数已硬编码进 combat_sim.js），运行期不加载" },
    @{ Exact = "data/game-truth/meta.json"; Reason = "game-truth 抽取元信息，运行期不加载" },
    @{ Exact = "data/tasks/sources.json"; Reason = "构建期数据来源记录，运行期不加载" },

    # assets 里的源材料 / 调试产物：运行期只用生成后的成品图。
    @{ Prefix = "assets/icons/zones-orig/"; Reason = "防护区域原始素材；app.js 运行期只用 assets/icons/zones/zone-*.png 成品图" },
    @{ Prefix = "assets/icons/zones/hand/"; Reason = "手绘参考图与 README，仅供构建期生成 zone-*.png 使用" },
    @{ Prefix = "assets/icons/zones/parts/"; Reason = "区域零件源图，仅供构建期合成 zone-*.png 使用" },
    @{ Prefix = "assets/ui/placeholders/_debug/"; Reason = "槽位剪影调试联系表，运行期 app.js 只用 placeholders 根目录的成品 PNG" },
    @{ Prefix = "assets/ui/placeholders/_r293/"; Reason = "上一版槽位剪影迭代目录，运行期使用根目录成品 PNG" },
    @{ Prefix = "assets/ui/placeholders/_src/"; Reason = "槽位剪影源 WebP，运行期使用根目录去背后的成品 PNG" },

    # R84：XP 素材的开发附属物，运行期不加载。
    @{ Exact = "assets/xp-ui/demo.html"; Reason = "XP 素材组件展示页（开发调试用），index.html 不引用，运行期不需要" },
    @{ Prefix = "assets/xp-ui/_shots/"; Reason = "XP 素材验收截图目录，仅供开发审计，运行期不加载" }
)

# 备份文件用模式匹配：data 根目录下的 items/gunslots/gun-layout-calibration 都有
# 多代 .bak.json / .prev.json，逐个列容易漏掉新备份。
$script:ExcludeRegex = @(
    @{ Regex = "^data/(?:[^/]+/)*[^/]+\.bak\.json$"; Reason = "构建期备份文件，运行期不加载" },
    @{ Regex = "^data/(?:[^/]+/)*[^/]+\.prev\.json$"; Reason = "上一版校准/数据快照，运行期不加载" }
)

function Add-ExpectedFile {
    param(
        [System.Collections.Generic.HashSet[string]]$Set,
        [string]$Rel
    )
    $rel = $Rel.Replace("\", "/")
    if (-not $Set.Contains($rel)) {
        [void]$Set.Add($rel)
    }
}

function Test-Excluded {
    param([string]$Rel)
    $rel = $Rel.Replace("\", "/")
    foreach ($item in $script:ExcludePaths) {
        if ($item.ContainsKey("Exact") -and $rel -eq $item.Exact) { return $true }
        if ($item.ContainsKey("Prefix") -and $rel.StartsWith($item.Prefix)) { return $true }
    }
    foreach ($item in $script:ExcludeRegex) {
        if ($rel -match $item.Regex) { return $true }
    }
    return $false
}

function Get-IndexLocalRefs {
    param([string]$Root)
    $index = Join-Path $Root "index.html"
    if (-not (Test-Path -LiteralPath $index -PathType Leaf)) {
        throw "缺少 index.html：$index"
    }
    $html = Get-Content -LiteralPath $index -Raw -Encoding UTF8
    $patterns = @(
        '<script[^>]+src\s*=\s*["'']([^"'']+)["'']',
        '<link[^>]+href\s*=\s*["'']([^"'']+)["'']',
        '<img[^>]+src\s*=\s*["'']([^"'']+)["'']'
    )
    $out = New-Object "System.Collections.Generic.HashSet[string]"
    foreach ($pattern in $patterns) {
        $found = [regex]::Matches($html, $pattern, [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
        foreach ($m in $found) {
            $raw = $m.Groups[1].Value.Trim()
            if ($raw -match "^(?:https?:)?//") { continue }
            if ($raw -match "^(?:data|blob|javascript|mailto|about):") { continue }
            if ($raw.StartsWith("#")) { continue }
            $clean = $raw.Split("?")[0].Split("#")[0]
            $clean = $clean.Replace("\", "/")
            while ($clean.StartsWith("./")) { $clean = $clean.Substring(2) }
            $clean = $clean.TrimStart("/")
            if ($clean) { Add-ExpectedFile $out $clean }
        }
    }
    return @($out | Sort-Object -Unique)
}

# 只收录“JS 里直接写死、且文件真实存在”的 data/、assets/ 路径。
# 拼接出来的目录（assets/icons-items/ + id）由 assets 整目录覆盖；
# 拼接出来的文件名（data/tasks/tasks. + mode）由 RuntimeFiles 显式清单覆盖。
function Get-JsLocalRefs {
    param(
        [string]$Root,
        [string[]]$IndexRefs
    )
    $jsFiles = @($IndexRefs | Where-Object {
        $_.EndsWith(".js", [System.StringComparison]::OrdinalIgnoreCase) -and
        -not $_.StartsWith("data/")
    })
    $out = New-Object "System.Collections.Generic.HashSet[string]"
    $pattern = '["'']((?:data|assets)/[^"'']+)["'']'
    foreach ($rel in $jsFiles) {
        $path = Join-Path $Root $rel.Replace("/", "\")
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { continue }
        $text = Get-Content -LiteralPath $path -Raw -Encoding UTF8
        foreach ($m in [regex]::Matches($text, $pattern)) {
            $ref = $m.Groups[1].Value.Trim()
            $ref = $ref.Split("?")[0].Split("#")[0]
            $ref = $ref.Replace("\", "/")
            if ($ref.Contains("*") -or $ref.Contains("{") -or $ref.Contains("}") -or $ref.Contains("$")) { continue }
            if ((Test-Path -LiteralPath (Join-Path $Root $ref.Replace("/", "\")) -PathType Leaf)) {
                if (-not (Test-Excluded $ref)) { Add-ExpectedFile $out $ref }
            }
        }
    }
    return @($out | Sort-Object -Unique)
}

function Get-RuntimePackageFiles {
    param([string]$Root)
    $root = (Resolve-Path -LiteralPath $Root).ProviderPath
    $expected = New-Object "System.Collections.Generic.HashSet[string]"

    Add-ExpectedFile $expected "index.html"
    $indexRefs = Get-IndexLocalRefs $root
    foreach ($rel in $indexRefs) {
        if (-not (Test-Excluded $rel)) { Add-ExpectedFile $expected $rel }
    }
    foreach ($rel in $script:RuntimeFiles) {
        if (-not (Test-Excluded $rel)) { Add-ExpectedFile $expected $rel }
    }
    foreach ($rel in (Get-JsLocalRefs $root $indexRefs)) {
        Add-ExpectedFile $expected $rel
    }

    foreach ($dir in $script:RuntimeDirs) {
        $full = Join-Path $root $dir
        if (-not (Test-Path -LiteralPath $full -PathType Container)) {
            throw "缺少运行期资源目录：$dir"
        }
        foreach ($f in Get-ChildItem -LiteralPath $full -Recurse -File) {
            $rel = $f.FullName.Substring($root.Length + 1).Replace("\", "/")
            if (-not (Test-Excluded $rel)) { Add-ExpectedFile $expected $rel }
        }
    }

    # 清单里任何一条都必须在源仓库真实存在；否则是清单写错，不是“可选文件”。
    foreach ($rel in ($expected | Where-Object { -not $_.StartsWith("assets/") })) {
        $full = Join-Path $root $rel.Replace("/", "\")
        if (-not (Test-Path -LiteralPath $full -PathType Leaf)) {
            throw "运行文件清单指向不存在的文件：$rel"
        }
    }
    return @($expected | Sort-Object -Unique)
}

function Stage-RuntimePackage {
    param(
        [string]$Root,
        [string]$Destination
    )
    $root = (Resolve-Path -LiteralPath $Root).ProviderPath
    $dest = [System.IO.Path]::GetFullPath($Destination)
    # R280.1：旧 staging 改名挪开，不做递归删除（本机删除大目录会挂住非交互 PowerShell）。
    if (Test-Path -LiteralPath $dest) {
        $backup = "$dest.old." + [DateTime]::Now.ToString("yyyyMMddHHmmss")
        Move-Item -LiteralPath $dest -Destination $backup -Force
        Write-Warning "旧 staging 已挪开：$backup"
    }
    New-Item -ItemType Directory -Force -Path $dest | Out-Null

    $expected = Get-RuntimePackageFiles -Root $root

    # assets 整目录先复制，再按排除表删掉源材料/调试产物。
    foreach ($dir in $script:RuntimeDirs) {
        $src = Join-Path $root $dir
        $dst = Join-Path $dest $dir
        Copy-Item -LiteralPath $src -Destination $dst -Recurse -Force
    }

    foreach ($rel in $expected) {
        if ($rel.StartsWith("assets/")) { continue }
        $src = Join-Path $root $rel.Replace("/", "\")
        $dst = Join-Path $dest $rel.Replace("/", "\")
        $parent = Split-Path -Parent $dst
        if (-not (Test-Path -LiteralPath $parent -PathType Container)) {
            New-Item -ItemType Directory -Force -Path $parent | Out-Null
        }
        if (-not (Test-Path -LiteralPath $dst -PathType Leaf)) {
            Copy-Item -LiteralPath $src -Destination $dst -Force
        }
    }

    # R280.1：本机对刚复制出来的文件做 Remove-Item 会偶发 Access denied，甚至让
    # 非交互 PowerShell 挂住（assets/icons/zones/hand/ 下的 README/参考图反复中招）。
    # 构建期一律**不做 staging 内删除**：排除表里的素材留在 staging（~65 KB，
    # PyInstaller 会带进包，无运行期影响），由 Test-RuntimePackage 按排除表放行。
    # 空目录同样保留，$actual 只统计文件，不影响清单比对。
    # 这样打包流程不再有任何可能因文件占用而卡死的清理动作。
    return $expected
}

function Test-RuntimePackage {
    param(
        [string]$Root,
        [string]$Staging,
        [string[]]$Expected
    )
    if (-not $Expected) { $Expected = Get-RuntimePackageFiles -Root $Root }
    $staging = (Resolve-Path -LiteralPath $Staging).ProviderPath
    $expectedList = @($Expected | Sort-Object -Unique)
    $expectedSet = New-Object "System.Collections.Generic.HashSet[string]"
    foreach ($item in $expectedList) { [void]$expectedSet.Add($item) }

    $actual = New-Object "System.Collections.Generic.HashSet[string]" ([System.StringComparer]::OrdinalIgnoreCase)
    foreach ($f in @(Get-ChildItem -LiteralPath $staging -Recurse -File)) {
        [void]$actual.Add($f.FullName.Substring($staging.Length + 1).Replace("\", "/"))
    }

    $missing = @($expectedList | Where-Object {
        -not $actual.Contains($_)
    })
    # R280.1：明确列在排除表里的构建期素材，若因文件被占用没删掉，不算「未登记文件」。
    # 其余任何未登记文件仍然一律报错，清单护栏不放宽。
    $extra = @($actual | Where-Object {
        -not $expectedSet.Contains($_) -and -not (Test-Excluded $_)
    })

    if ($missing.Count -gt 0) {
        $show = @($missing | Select-Object -First 20)
        throw ("staging 缺少 {0} 个运行期文件：`n{1}`n{2}" -f
            $missing.Count,
            ($show -join "`n"),
            ($(if ($missing.Count -gt 20) { "……只显示前 20 个" } else { "" })))
    }
    if ($extra.Count -gt 0) {
        $show = @($extra | Select-Object -First 20)
        throw ("staging 出现 {0} 个未登记文件（要么补进清单，要么写明排除理由）：`n{1}`n{2}" -f
            $extra.Count,
            ($show -join "`n"),
            ($(if ($extra.Count -gt 20) { "……只显示前 20 个" } else { "" })))
    }

    Write-Host ("完整性校验通过：预期 {0} 个文件，staging 实际 {1} 个文件，缺失 0，未登记 0。" -f
        $expectedList.Count, $actual.Count)
}

# 打包完成后用：只检查“运行期清单里的文件在产物里都存在”，
# 不比较多余文件（PyInstaller 会额外放 Python 运行时和 DLL）。
function Test-ExpectedFilesPresent {
    param(
        [string]$Root,
        [string[]]$Expected
    )
    $root = (Resolve-Path -LiteralPath $Root).ProviderPath
    $actual = New-Object "System.Collections.Generic.HashSet[string]" ([System.StringComparer]::OrdinalIgnoreCase)
    foreach ($file in @(Get-ChildItem -LiteralPath $root -Recurse -File)) {
        [void]$actual.Add($file.FullName.Substring($root.Length + 1).Replace("\", "/"))
    }
    $missing = @($Expected | Where-Object { -not $actual.Contains($_) })
    if ($missing.Count -gt 0) {
        $show = @($missing | Select-Object -First 20)
        throw ("打包产物缺少 {0} 个运行期文件：`n{1}" -f $missing.Count, ($show -join "`n"))
    }
    Write-Host ("产物清单校验通过：{0} 个运行期文件全部存在。" -f $Expected.Count)
}
