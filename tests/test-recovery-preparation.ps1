$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression.FileSystem
. (Join-Path $PSScriptRoot '..\scripts\check-download-mode.ps1')
$root = Join-Path ([IO.Path]::GetTempPath()) ('S10 recovery preparation ' + [Guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory($root) | Out-Null

function Assert-RecoveryPreparation {
    param([bool]$Condition, [string]$Description)
    if (-not $Condition) { throw ('FAIL: ' + $Description) }
}

try {
    $package = Join-Path $PSScriptRoot '..\out\UbuntuTouch-S10plus-prepara-recovery-Windows.zip'
    $packageRoot = Join-Path $root 'packaged tools with spaces'
    [IO.Compression.ZipFile]::ExtractToDirectory([IO.Path]::GetFullPath($package), $packageRoot)
    $python = Join-Path $packageRoot 'tools\python\python.exe'
    $signature = Get-AuthenticodeSignature -LiteralPath $python
    Assert-RecoveryPreparation ($signature.Status -eq 'Valid' -and $signature.SignerCertificate.Subject -match 'Python Software Foundation') 'publisher runtime signature'
    $version = Invoke-DownloadCheckNative $python @('-I', '-c', 'import sys, lzma, ssl, hashlib; print(sys.version_info[:3])') 30
    Assert-RecoveryPreparation ($version.ExitCode -eq 0 -and $version.Stdout.Trim() -eq '(3, 14, 4)') 'embedded standard library and version'
    $code = @'
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(sys.argv[1]) / 'scripts'))
from prepare_recovery import download_original, prepare
root = Path(sys.argv[1])
image = download_original(root)
report = prepare(root, audit_image=image)
assert report['success'], report
assert not report['backup_verified'] and not report['handset_accessed']
assert report['recovery']['kernel_unchanged'] and report['recovery']['embedded_dtbo_unchanged']
assert report['recovery']['automatic_nuker_trigger_removed']
assert report['recovery']['nuker_script_replaced_by_no_op']
assert report['recovery']['all_other_ramdisk_contents_and_metadata_preserved']
assert report['vbmeta']['flags'] == 3 and report['vbmeta']['bytes'] == 65536
assert report['vbmeta']['algorithm'] == 'NONE' and not report['vbmeta']['cryptographic_signature']
print('PASS: embedded Windows runtime adapts the publisher recovery and creates bounded flags-3 vbmeta')
'@
    $audit = Invoke-DownloadCheckNative $python @('-I', '-c', $code, $packageRoot) 240
    Assert-RecoveryPreparation (-not $audit.TimedOut -and $audit.ExitCode -eq 0) ('real recovery preparation: ' + $audit.Stderr)
    Write-Host $audit.Stdout
    # Exercise the actual launcher with a selected file, so no chooser/USB
    # interaction is required in CI. Wrong firmware must produce a report.
    $wrong = Join-Path $root 'wrong firmware with spaces.zip'
    [IO.File]::WriteAllText($wrong, 'not the downloaded Samsung firmware')
    $launcher = Join-Path $packageRoot 'PREPARA-RECOVERY.cmd'
    $info = New-Object Diagnostics.ProcessStartInfo
    $info.FileName = $env:ComSpec
    $info.Arguments = '/d /s /c ""' + $launcher + '" "' + $wrong + '" <nul"'
    $info.WorkingDirectory = $root
    $info.UseShellExecute = $false
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    $process = New-Object Diagnostics.Process
    $process.StartInfo = $info
    try {
        Assert-RecoveryPreparation ($process.Start()) 'CMD starts'
        $stdout = $process.StandardOutput.ReadToEndAsync()
        $stderr = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit(60000)) { $process.Kill(); throw 'CMD timeout' }
        $process.WaitForExit()
        $outText = $stdout.GetAwaiter().GetResult()
        $errText = $stderr.GetAwaiter().GetResult()
        Assert-RecoveryPreparation ($process.ExitCode -eq 1) ('CMD propagates firmware rejection: ' + $outText + $errText)
    } finally { $process.Dispose() }
    $reportZip = Join-Path $packageRoot 'recovery-preparation-report-1.zip'
    Assert-RecoveryPreparation (Test-Path -LiteralPath $reportZip) 'CMD produces a new diagnostic report'
    $zip = [IO.Compression.ZipFile]::OpenRead($reportZip)
    try {
        Assert-RecoveryPreparation ($zip.Entries.Count -eq 1) 'only report in upload ZIP'
        $reader = New-Object IO.StreamReader($zip.GetEntry('recovery-preparation-report.json').Open())
        try { $report = $reader.ReadToEnd() | ConvertFrom-Json } finally { $reader.Dispose() }
        Assert-RecoveryPreparation ($report.error -eq 'stock_size_mismatch' -and -not $report.success) 'exact firmware guard'
        Assert-RecoveryPreparation (-not $report.handset_accessed -and -not $report.partition_writes -and -not $report.backup_verified) 'no false hardware/backup claim'
    } finally { $zip.Dispose() }
    Assert-RecoveryPreparation (-not (Test-Path (Join-Path $packageRoot 'recovery-local-state.json'))) 'failed preparation leaves no ready state'
    Write-Host 'PASS: publisher signatures, portable Python/LZMA/SSL, real recovery patch, vbmeta layout, spaced paths, CMD, wrong-firmware rejection and failure reports.'
} finally { Remove-Item -LiteralPath $root -Recurse -Force }
