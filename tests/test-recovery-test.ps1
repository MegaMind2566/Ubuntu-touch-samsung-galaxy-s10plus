$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression.FileSystem
. (Join-Path $PSScriptRoot '..\scripts\flash-recovery-test.ps1')
$testDirectory = Join-Path ([IO.Path]::GetTempPath()) ('S10 recovery test ' + [Guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory($testDirectory) | Out-Null
$script:RecoveryFixtureMode = ''
$script:RecoveryFixtureReads = @()
$script:RecoveryFixtureWrites = @()
$script:RecoveryFixturePit = [Convert]::FromBase64String([IO.File]::ReadAllText((Join-Path $PSScriptRoot 'fixtures\beyond2lte-pit.base64')))

function Assert-RecoveryTest {
    param([bool]$Condition, [string]$Description)
    if (-not $Condition) { throw ('FAIL: ' + $Description) }
}

$readRunner = {
    param([string]$Executable, [string[]]$Arguments, [int]$TimeoutSeconds)
    $script:RecoveryFixtureReads += ,@($Arguments)
    $result = [pscustomobject]@{ ExitCode = 0; TimedOut = $false; Stdout = ''; Stderr = 'PRIVATE-USB-MARKER' }
    if ($Arguments[0] -eq '--version') {
        $result.Stdout = 'samloader 2.2.0'
        if ($script:RecoveryFixtureMode -eq 'version') { $result.Stdout = 'samloader 9.0.0' }
    } elseif ($Arguments[2] -eq 'detect') {
        $model = 'SM-G975F'
        if ($script:RecoveryFixtureMode -eq 'model') { $model = 'SM-G975U' }
        if ($script:RecoveryFixtureMode -eq 'blank-model') { $model = '' }
        $result.Stdout = '{"modelName":"' + $model + '","serialNumber":"PRIVATE-USB-MARKER"}'
        if ($script:RecoveryFixtureMode -eq 'json') { $result.Stdout = '{invalid' }
        if ($script:RecoveryFixtureMode -eq 'detect') { $result.ExitCode = 1 }
        if ($script:RecoveryFixtureMode -eq 'timeout') { $result.TimedOut = $true }
    } elseif ($Arguments[2] -eq 'dump-pit') {
        $bytes = $script:RecoveryFixturePit.Clone()
        if ($script:RecoveryFixtureMode -eq 'pit') { $bytes[32] = $bytes[32] -bxor 1 }
        [IO.File]::WriteAllBytes($Arguments[4], $bytes)
        if ($script:RecoveryFixtureMode -eq 'dump') { $result.ExitCode = 1 }
    } else { throw 'unexpected_read' }
    return $result
}

$writeRunner = {
    param([string]$Executable, [string[]]$Arguments)
    $script:RecoveryFixtureWrites += ,@($Arguments)
    # An actual flash must receive immutable files while the native reader
    # can still open them. These mocked writes never access a USB device.
    $reader = [IO.File]::OpenRead($Arguments[8]); $reader.Dispose()
    $blocked = $false
    try {
        $writer = [IO.File]::Open($Arguments[8], [IO.FileMode]::Open, [IO.FileAccess]::Write, [IO.FileShare]::ReadWrite)
        $writer.Dispose()
    } catch [IO.IOException] { $blocked = $true }
    Assert-RecoveryTest $blocked 'image cannot change during native flash'
    if ($script:RecoveryFixtureMode -eq 'flash') { return 1 }
    return 0
}

$preflightRunner = {
    param([string]$Root)
    $state = [IO.File]::ReadAllText((Join-Path $Root 'recovery-local-state.json')) | ConvertFrom-Json
    return [pscustomobject]@{
        success = $true; backup_verified = ($script:RecoveryFixtureMode -ne 'backup')
        recovery_path = (Join-Path $state.prepared_directory 'recovery-test.img')
        vbmeta_path = (Join-Path $state.prepared_directory 'vbmeta-test.img')
        stock_firmware_path = $state.stock_firmware_path
    }
}

function Invoke-RecoveryFixture {
    param([string]$Mode, [string]$ExpectedError, [bool]$ExpectedWrite)
    $script:RecoveryFixtureMode = $Mode
    $script:RecoveryFixtureReads = @()
    $script:RecoveryFixtureWrites = @()
    $result = Invoke-RecoveryTest -Root $script:RecoveryFixtureRoot -ReadRunner $readRunner -WriteRunner $writeRunner -PreflightRunner $preflightRunner
    Assert-RecoveryTest ($result.Success -eq ($Mode -eq 'success')) ($Mode + ': success')
    Assert-RecoveryTest (([string]$result.Report.error) -ceq ([string]$ExpectedError)) ($Mode + ': failure stage')
    Assert-RecoveryTest ($result.Report.write_attempted -eq $ExpectedWrite) ($Mode + ': write stage')
    Assert-RecoveryTest ($script:RecoveryFixtureWrites.Count -eq [int]$ExpectedWrite) ($Mode + ': native flash count')
    Assert-RecoveryTest (-not $result.Report.recovery_boot_verified -and -not $result.Report.ubuntu_touch_boot_verified) 'no runtime success claim'
    Assert-RecoveryTest (-not $result.Report.reboot_requested -and -not $result.Report.erase_requested) 'no erase/reboot'
    if ($ExpectedWrite) {
        $flashArguments = $script:RecoveryFixtureWrites[0]
        Assert-RecoveryTest (($flashArguments[0..4] -join '|') -ceq '--usb-backend|vcom|flash|--partition|VBMETA') 'first write target'
        Assert-RecoveryTest ($flashArguments[6] -ceq '--partition' -and $flashArguments[7] -ceq 'RECOVERY' -and $flashArguments[9] -ceq '--no-reboot') 'second target and no reboot'
        Assert-RecoveryTest ($flashArguments.Count -eq 10) 'exact two-partition command without extra flags'
    }
    $zip = [IO.Compression.ZipFile]::OpenRead($result.ZipPath)
    try {
        Assert-RecoveryTest ($zip.Entries.Count -eq 1 -and $zip.Entries[0].Name -ceq 'recovery-test-report.json') 'sanitized report only'
        $reader = New-Object IO.StreamReader($zip.Entries[0].Open())
        try { $json = $reader.ReadToEnd() } finally { $reader.Dispose() }
        Assert-RecoveryTest ($json -notmatch 'PRIVATE-USB-MARKER|serialNumber|stock_firmware_path|recovery_path|[A-Z]:\\') 'USB identifiers and PC paths excluded'
    } finally { $zip.Dispose() }
    return $result
}

try {
    $script:RecoveryFixtureRoot = Join-Path $testDirectory 'prepared package with spaces'
    [IO.Compression.ZipFile]::ExtractToDirectory([IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\out\UbuntuTouch-S10plus-prepara-recovery-Windows.zip')), $script:RecoveryFixtureRoot)
    [IO.Compression.ZipFile]::ExtractToDirectory([IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\out\UbuntuTouch-S10plus-installa-recovery-test-Windows.zip')), (Join-Path $testDirectory 'addon'))
    Copy-Item -Path (Join-Path $testDirectory 'addon\*') -Destination $script:RecoveryFixtureRoot -Recurse -Force
    $embeddedPython = Join-Path $script:RecoveryFixtureRoot 'tools\python\python.exe'
    $publisherExe = Join-Path $script:RecoveryFixtureRoot 'tools\samloader\samloader.exe'
    $version = Invoke-DownloadCheckNative $publisherExe @('--version') 15
    Assert-RecoveryTest ($version.ExitCode -eq 0 -and $version.Stdout.Trim() -ceq 'samloader 2.2.0') 'real pinned native executable'
    $code = @'
import json,sys
from pathlib import Path
root=Path(sys.argv[1])
sys.path.insert(0,str(root/'scripts'))
from prepare_recovery import download_original,prepare
from verify_recovery_test import verify_images,STOCK_SHA256,VerificationError,verify_files
report=prepare(root,audit_image=download_original(root))
assert report['success']
directory=next(root.glob('prepared-recovery-*'))
verify_images(directory)
report['backup_verified']=True
report['stock_firmware']={'sha256':STOCK_SHA256}
state={'prepared_directory':str(directory),'stock_firmware_path':str(root/'fixture-stock.zip'),'report':report}
(root/'recovery-local-state.json').write_text(json.dumps(state))
try:
 verify_files(root)
except VerificationError as error:
 assert str(error)=='stock_firmware_missing_or_size_mismatch'
else:
 raise AssertionError('missing retained firmware was accepted')
print('PASS: exact real recovery/vbmeta pins on embedded Windows runtime; missing stock rejected')
'@
    $audit = Invoke-DownloadCheckNative $embeddedPython @('-I', '-c', $code, $script:RecoveryFixtureRoot) 300
    Assert-RecoveryTest (-not $audit.TimedOut -and $audit.ExitCode -eq 0) ('real image audit: ' + $audit.Stderr)
    Write-Host $audit.Stdout
    $stock = Join-Path $script:RecoveryFixtureRoot 'fixture-stock.zip'
    [IO.File]::WriteAllBytes($stock, @())
    # A sparse same-size placeholder is only used with the injected preflight
    # runner above. Production SHA-256 validation always rejects this file.
    & fsutil.exe sparse setflag $stock | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'sparse_fixture_failed' }
    $stream = [IO.File]::OpenWrite($stock)
    try { $stream.SetLength(6364940601) } finally { $stream.Dispose() }
    $null = Invoke-RecoveryFixture 'success' $null $true
    foreach ($case in @(
        @('version','version_failed',$false), @('model','model_not_confirmed',$false),
        @('blank-model','model_not_confirmed',$false), @('json','usb_response_invalid',$false),
        @('detect','usb_detection_failed',$false), @('timeout','usb_detection_failed',$false),
        @('dump','pit_read_failed',$false), @('pit','pit_mismatch',$false),
        @('backup','local_verification_failed',$false), @('flash','flash_failed',$true)
    )) { $null = Invoke-RecoveryFixture $case[0] $case[1] $case[2] }
    $state = [IO.File]::ReadAllText((Join-Path $script:RecoveryFixtureRoot 'recovery-local-state.json')) | ConvertFrom-Json
    $vbmetaPath = Join-Path $state.prepared_directory 'vbmeta-test.img'
    $original = [IO.File]::ReadAllBytes($vbmetaPath)
    $changed = $original.Clone(); $changed[1000] = 1
    [IO.File]::WriteAllBytes($vbmetaPath, $changed)
    $null = Invoke-RecoveryFixture 'tampered-image' 'verified_files_changed' $false
    Assert-RecoveryTest ($script:RecoveryFixtureReads.Count -eq 0) 'tampered file stops before USB'
    [IO.File]::WriteAllBytes($vbmetaPath, $original)
    foreach ($arguments in @(
        @('--usb-backend','vcom','flash','--partition','BOOT','boot.img','--no-reboot'),
        @('--usb-backend','vcom','flash','--partition','VBMETA','v.img','--partition','RECOVERY','r.img','--no-reboot','--erase'),
        @('--usb-backend','vcom','flash','--partition','VBMETA','v.img','--partition','RECOVERY','r.img')
    )) {
        $blocked = $false
        try { $null = Invoke-RecoveryTestWrite $publisherExe $arguments 'r.img' 'v.img' $writeRunner }
        catch { $blocked = $_.Exception.Message -eq 'write_command_not_allowed' }
        Assert-RecoveryTest $blocked 'write allowlist rejects extra or different targets'
    }
    # Exercise the real CMD and Windows PowerShell -File entry point. Missing
    # state must return a report and exit before any USB request or flash.
    Remove-Item -LiteralPath (Join-Path $script:RecoveryFixtureRoot 'recovery-local-state.json')
    $launcher = Join-Path $script:RecoveryFixtureRoot 'INSTALLA-RECOVERY-TEST.cmd'
    $info = New-Object Diagnostics.ProcessStartInfo
    $info.FileName = $env:ComSpec
    $info.Arguments = '/d /s /c ""' + $launcher + '" <nul"'
    $info.UseShellExecute = $false
    $info.RedirectStandardOutput = $true; $info.RedirectStandardError = $true
    $process = New-Object Diagnostics.Process; $process.StartInfo = $info
    try {
        Assert-RecoveryTest ($process.Start()) 'native CMD starts'
        $stdout = $process.StandardOutput.ReadToEndAsync(); $stderr = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit(60000)) { $process.Kill(); throw 'entry_point_timeout' }
        $process.WaitForExit()
        Assert-RecoveryTest ($process.ExitCode -eq 1) ('native CMD exit: ' + $stdout.GetAwaiter().GetResult() + $stderr.GetAwaiter().GetResult())
    } finally { $process.Dispose() }
    $newest = Get-ChildItem -LiteralPath $script:RecoveryFixtureRoot -Filter 'recovery-test-report*.zip' | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
    $zip = [IO.Compression.ZipFile]::OpenRead($newest.FullName)
    try {
        $reader = New-Object IO.StreamReader($zip.Entries[0].Open())
        try { $lastReport = $reader.ReadToEnd() | ConvertFrom-Json } finally { $reader.Dispose() }
        Assert-RecoveryTest (-not $lastReport.write_attempted -and $lastReport.steps.Count -eq 0) 'real launcher stops before USB on missing state'
    } finally { $zip.Dispose() }
    Write-Host 'PASS: 12 simulated success/failure cases, immutable flash inputs, exact targets, no reboot/erase, sanitized diagnostics and native CMD in a spaced path. No hardware write performed by CI.'
} finally { Remove-Item -LiteralPath $testDirectory -Recurse -Force }
