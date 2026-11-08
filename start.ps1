param(
    [string]$DataDirectory = "$env:APPDATA\Cether",
    [switch]$Build
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:CETHER_DATA_DIR = [System.IO.Path]::GetFullPath($DataDirectory)
$env:PYTHONPATH = Join-Path $root 'src'

if ($Build) {
    Push-Location (Join-Path $root 'src-tauri')
    try {
        cargo tauri dev
        exit $LASTEXITCODE
    }
    finally {
        Pop-Location
    }
}

$candidates = @(
    (Join-Path $root 'src-tauri\target\release\cether.exe'),
    (Join-Path $root 'src-tauri\target\debug\cether.exe')
)
$host = $candidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
if (-not $host) {
    throw 'Cether desktop host is not built. Run .\start.ps1 -Build to launch the development host.'
}
& $host
exit $LASTEXITCODE
