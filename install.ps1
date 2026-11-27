# masculine-awakening installer for Windows PowerShell
# Usage:
#   irm https://raw.githubusercontent.com/<owner>/masculine-awakening/main/install.ps1 | iex
#
# Note: output is English on purpose. Windows PowerShell 5.1 mis-decodes
# BOM-less UTF-8 scripts, so non-ASCII here would render as garbage.

$ErrorActionPreference = "Stop"

$Repo   = "ydaydayup/masculine-awakening"
$Branch = "main"
$Skill  = "masculine-awakening"

# A skill installed under the system temp directory disappears after a reboot
# or a disk cleanup, so refuse to put it there.
function Test-TempPath($p) {
    if (-not $p) { return $false }
    $t = [System.IO.Path]::GetTempPath()
    if ($p.StartsWith($t, [System.StringComparison]::OrdinalIgnoreCase)) { return $true }
    # GetTempPath may return the 8.3 short name (ADMINI~1), so also match by shape
    return ($p -match '(?i)[\\/](AppData[\\/]Local[\\/])?Temp[\\/]')
}

$DefaultDir = Join-Path $env:USERPROFILE ".workbuddy\skills"

Write-Host ""
Write-Host "masculine-awakening installer"
Write-Host ""

if ($env:WORKBUDDY_SKILLS) {
    $SkillsDir = $env:WORKBUDDY_SKILLS
} else {
    $SkillsDir = $DefaultDir
}

if (Test-TempPath $SkillsDir) {
    Write-Host "  ! target is inside the system temp directory, it would be wiped on reboot:"
    Write-Host "    $SkillsDir"
    Write-Host "  - falling back to $DefaultDir"
    $SkillsDir = $DefaultDir
}

$Tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("masculineawakening-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
New-Item -ItemType Directory -Path $Tmp -Force | Out-Null

try {
    $Zip = Join-Path $Tmp "pkg.zip"
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

    # Same idea as install.sh: try github.com first, fall back to codeload.
    $Cands = @(
        "https://github.com/$Repo/archive/refs/heads/$Branch.zip",
        "https://codeload.github.com/$Repo/zip/refs/heads/$Branch"
    )

    Write-Host "  - downloading $Repo"
    $Got = $false
    foreach ($u in $Cands) {
        try {
            Invoke-WebRequest -Uri $u -OutFile $Zip -UseBasicParsing
            $Got = $true
            break
        } catch {
            Write-Host "  - this source failed, trying the next one"
        }
    }
    if (-not $Got) { throw "all download sources failed, check your network" }

    Write-Host "  - extracting"
    $Extract = Join-Path $Tmp "src"
    Expand-Archive -LiteralPath $Zip -DestinationPath $Extract -Force

    $Src = Get-ChildItem -Path $Extract -Directory |
           ForEach-Object { Join-Path $_.FullName $Skill } |
           Where-Object { Test-Path $_ } |
           Select-Object -First 1

    if (-not $Src) { throw "package does not contain $Skill (CDN may still serve an old build)" }

    if (-not (Test-Path $SkillsDir)) {
        New-Item -ItemType Directory -Path $SkillsDir -Force | Out-Null
    }

    $Dest = Join-Path $SkillsDir $Skill
    if (Test-Path $Dest) {
        $Backup = $Dest + ".bak." + (Get-Date -Format "yyyyMMddHHmmss")
        Move-Item -LiteralPath $Dest -Destination $Backup
        Write-Host "  - previous version backed up to $Backup"
    }

    Copy-Item -LiteralPath $Src -Destination $Dest -Recurse -Force
    Write-Host "  - installed to $Dest"

    Write-Host ""
    Write-Host "Checking runtime..."

    $Py = $null
    foreach ($c in @("python", "py")) {
        if (Get-Command $c -ErrorAction SilentlyContinue) { $Py = $c; break }
    }

    if (-not $Py) {
        Write-Host "  ! Python not found. Install Python 3.9+ then run:"
        Write-Host "    pip install -r `"$Dest\requirements.txt`""
    } else {
        $Req = Join-Path $Dest "requirements.txt"

        $ok = $true
        foreach ($mod in @("numpy", "fastembed")) {
            & $Py -c "import $mod" 2>$null
            if ($LASTEXITCODE -ne 0) { $ok = $false }
        }

        if ($ok) {
            Write-Host "  - numpy, fastembed ready"
        } else {
            Write-Host "  ! missing dependencies, run:"
            Write-Host "    $Py -m pip install -r `"$Req`""
            Write-Host "    (first search downloads a ~100MB Chinese embedding model)"
        }

        $Chk = Join-Path $Dest "scripts\check.py"
        if (Test-Path $Chk) {
            Write-Host ""
            Write-Host "Data check:"
            & $Py $Chk
        }
    }

    $ModelCache = $env:FASTEMBED_CACHE_PATH
    if (-not $ModelCache) { $ModelCache = Join-Path $env:USERPROFILE ".workbuddy\.cache\fastembed" }

    Write-Host ""
    Write-Host "Model cache: $ModelCache"
    Write-Host "  first search downloads ~100MB, then it stays here."
    Write-Host "  (fastembed defaults to the system temp dir, which gets wiped on reboot)"

    Write-Host ""
    Write-Host "Done. Open WorkBuddy and just ask:"
    Write-Host "  `"What does Xiaosa Ge think about bride price?`""
    Write-Host ""
}
finally {
    if (Test-Path $Tmp) { Remove-Item -LiteralPath $Tmp -Recurse -Force -ErrorAction SilentlyContinue }
}
