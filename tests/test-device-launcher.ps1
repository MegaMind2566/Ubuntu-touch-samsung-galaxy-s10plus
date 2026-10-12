$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
$tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ('beyond2lte-adb-test-' + [guid]::NewGuid().ToString())
$errorFile = Join-Path $root 'errore-controllo.txt'
New-Item -ItemType Directory -Path $tempRoot | Out-Null
try {
    $archive = Join-Path $tempRoot 'platform-tools.zip'
    Invoke-WebRequest -UseBasicParsing 'https://dl.google.com/android/repository/platform-tools_r37.0.1-win.zip' -OutFile $archive
    if ((Get-FileHash -Algorithm SHA256 $archive).Hash.ToLowerInvariant() -ne '45f4d63113e895ebde0c90f194099a4676b6ac653bd28d54314a9e022bbc1a99') { throw 'Official ADB archive checksum mismatch' }
    Expand-Archive -LiteralPath $archive -DestinationPath $tempRoot
    $adb = Join-Path $tempRoot 'platform-tools\adb.exe'
    & $adb version
    if ($LASTEXITCODE -ne 0) { throw 'Official ADB binary did not run on Windows' }
    # No phone is attached to this Windows CI runner. Verify that actual Windows
    # PowerShell 5.1 handles ADB daemon stderr and produces a clear missing-phone
    # error, instead of falsely treating daemon startup messages as failures.
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root 'scripts/launch-device-check.ps1') -Adb $adb -WaitSeconds 0
    if ($LASTEXITCODE -ne 1) { throw 'Missing-phone launcher status was not reported' }
    $message = Get-Content -Raw -LiteralPath $errorFile
    if ($message -notmatch '^Telefono non autorizzato o non rilevato\.') { throw ('Unexpected launcher failure: ' + $message) }
    & $adb kill-server
    Write-Host 'Official ADB runs; Windows launcher handles missing USB authorization correctly.'
} finally {
    if (Test-Path -LiteralPath $errorFile) { Remove-Item -LiteralPath $errorFile }
    if (Test-Path -LiteralPath $tempRoot) { Remove-Item -Recurse -Force -LiteralPath $tempRoot }
}
exit 0
