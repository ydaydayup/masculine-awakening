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

if ($env:WORKBUDDY_SKILLS) {
    $SkillsDir = $env:WORKBUDDY_SKILLS
} else {
    $SkillsDir = Join-Path $env:USERPROFILE ".workbuddy\skills"
}

Write-Host ""
Write-Host "masculine-awakening installer"
Write-Host ""

$Tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("bloggerkb-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
New-Item -ItemType Directory -Path $Tmp -Force | Out-Null

try {
    $Url = "https://github.com/$Repo/archive/refs/heads/$Branch.zip"
    $Zip = Join-Path $Tmp "pkg.zip"

    Write-Host "  - downloading $Repo"
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -Uri $Url -OutFile $Zip -UseBasicParsing

    Write-Host "  - extracting"
    $Extract = Join-Path $Tmp "src"
    Expand-Archive -LiteralPath $Zip -DestinationPath $Extract -Force

    $Src = Get-ChildItem -Path $Extract -Directory |
           ForEach-Object { Join-Path $_.FullName $Skill } |
           Where-Object { Test-Path $_ } |
           Select-Object -First 1

    if (-not $Src) { throw "package does not contain $Skill" }

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

    Write-Host ""
    Write-Host "Done. Open WorkBuddy and just ask:"
    Write-Host "  `"What does Xiaosa Ge think about bride price?`""
    Write-Host ""
}
finally {
    if (Test-Path $Tmp) { Remove-Item -LiteralPath $Tmp -Recurse -Force -ErrorAction SilentlyContinue }
}
