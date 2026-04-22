Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($env:OS -ne "Windows_NT") {
    throw "This script builds a Windows EXE and must be run on native Windows."
}

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$DistRoot = Join-Path $ProjectRoot "dist"
$BuildRoot = Join-Path $ProjectRoot "build"
$OutputDir = Join-Path $DistRoot "foli-harvester"
$EntryPoint = Join-Path $ProjectRoot "foli_harvester\exe_entry.py"

Push-Location $ProjectRoot
try {
    python -m PyInstaller --version | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller is not available. Run: pip install -r requirements-build.txt"
    }

    python -m PyInstaller `
        --noconfirm `
        --clean `
        --onedir `
        --console `
        --name "foli-harvester" `
        --distpath $DistRoot `
        --workpath $BuildRoot `
        --specpath $BuildRoot `
        --paths $ProjectRoot `
        --collect-all libsql `
        $EntryPoint
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller build failed with exit code $LASTEXITCODE."
    }

    Copy-Item -Path (Join-Path $ProjectRoot ".env.example") `
        -Destination (Join-Path $OutputDir ".env.example") `
        -Force

    $Wrappers = @{
        "init-db.cmd" = "init-db"
        "collect.cmd" = "collect"
        "healthcheck.cmd" = "healthcheck"
        "fetch-gtfs-once.cmd" = "fetch-gtfs-once"
    }

    foreach ($Wrapper in $Wrappers.GetEnumerator()) {
        $WrapperPath = Join-Path $OutputDir $Wrapper.Key
        $Command = $Wrapper.Value
        $Content = @"
@echo off
setlocal
cd /d "%~dp0"
"%~dp0foli-harvester.exe" $Command %*
"@
        Set-Content -Path $WrapperPath -Value $Content -Encoding ASCII
    }

    Write-Host "Built portable Windows folder: $OutputDir"
    Write-Host "Copy .env.example to .env inside that folder before running with private credentials."
}
finally {
    Pop-Location
}
