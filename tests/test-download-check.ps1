[CmdletBinding()]
param([Parameter(Mandatory = $true)][string]$SamloaderPath)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression.FileSystem
$publisherExe = (Resolve-Path -LiteralPath $SamloaderPath).Path
. (Join-Path $PSScriptRoot '..\scripts\check-download-mode.ps1')
$root = Join-Path ([IO.Path]::GetTempPath()) ('S10 download tests ' + [Guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory($root) | Out-Null
$binaryDirectory = Join-Path $root 'binary folder'
[IO.Directory]::CreateDirectory($binaryDirectory) | Out-Null
$exe = Join-Path $binaryDirectory 'samloader.exe'
Copy-Item -LiteralPath $publisherExe -Destination $exe
$script:FixtureMode = ''
$script:FixtureCalls = @()
$script:FixtureExe = $exe
$passed = 0

function Assert-Check {
    param([bool]$Condition, [string]$Description)
    if (-not $Condition) { throw ('FAIL: ' + $Description) }
}

function Write-FixturePit {
    param([string]$Path)
    $names = @('BOOT', 'RECOVERY', 'DTB', 'DTBO', 'VBMETA', 'SYSTEM', 'VENDOR', 'USERDATA')
    $sizes = @(57671680, 67633152, 8388608, 8388608, 65536, 5976883200, 1153433600, 107374182400)
    $bytes = New-Object byte[] (28 + 132 * $names.Count)
    [BitConverter]::GetBytes([uint32]0x12349876).CopyTo($bytes, 0)
    [BitConverter]::GetBytes([uint32]$names.Count).CopyTo($bytes, 4)
    [Text.Encoding]::ASCII.GetBytes('BEYOND2').CopyTo($bytes, 8)
    [Text.Encoding]::ASCII.GetBytes('EXYNOS').CopyTo($bytes, 16)
    [BitConverter]::GetBytes([uint16]3).CopyTo($bytes, 24)
    for ($i = 0; $i -lt $names.Count; $i++) {
        $offset = 28 + 132 * $i
        [BitConverter]::GetBytes([uint32]8).CopyTo($bytes, $offset + 4)
        [BitConverter]::GetBytes([uint32]($i + 1)).CopyTo($bytes, $offset + 8)
        [BitConverter]::GetBytes([uint32]1).CopyTo($bytes, $offset + 12)
        [BitConverter]::GetBytes([uint32]($sizes[$i] / 4096)).CopyTo($bytes, $offset + 24)
        [Text.Encoding]::ASCII.GetBytes($names[$i]).CopyTo($bytes, $offset + 36)
        [Text.Encoding]::ASCII.GetBytes(($names[$i].ToLowerInvariant() + '.img')).CopyTo($bytes, $offset + 68)
    }
    [IO.File]::WriteAllBytes($Path, $bytes)
}

$runner = {
    param([string]$Executable, [string[]]$Arguments, [int]$TimeoutSeconds)
    $script:FixtureCalls += ,@($Arguments)
    $result = [pscustomobject]@{ ExitCode = 0; TimedOut = $false; Stdout = ''; Stderr = 'PRIVATE-SERIAL-MARKER' }
    if ($Arguments[0] -eq '--version') {
        if ($script:FixtureMode -eq 'version') { $result.Stdout = 'samloader 9.9.9' }
        else { $result.Stdout = 'samloader 2.2.0' }
    } elseif ($Arguments[2] -eq 'detect') {
        $model = 'SM-G975F'
        if ($script:FixtureMode -eq 'model') { $model = 'SM-G998B' }
        if ($script:FixtureMode -eq 'unknown-model') { $model = '' }
        $result.Stdout = '{"modelName":"' + $model + '","serialNumber":"PRIVATE-SERIAL-MARKER","imei":"PRIVATE-IMEI-MARKER"}'
        if ($script:FixtureMode -eq 'json') { $result.Stdout = '{broken' }
        if ($script:FixtureMode -eq 'missing-model') { $result.Stdout = '{}' }
        if ($script:FixtureMode -eq 'detect') { $result.ExitCode = 1 }
        if ($script:FixtureMode -eq 'timeout') { $result.TimedOut = $true }
    } elseif ($Arguments[2] -eq 'dump-pit') {
        if ($script:FixtureMode -eq 'dump') { $result.ExitCode = 1 }
        elseif ($script:FixtureMode -eq 'bad-pit') { [IO.File]::WriteAllText($Arguments[4], 'invalid PIT') }
        else { Write-FixturePit $Arguments[4] }
    } elseif ($Arguments[0] -eq 'print-pit') {
        if ($script:FixtureMode -eq 'print') { $result.ExitCode = 1 }
        else { return Invoke-DownloadCheckNative -Executable $Executable -Arguments $Arguments -TimeoutSeconds $TimeoutSeconds }
    } else { throw 'unexpected_fixture_command' }
    return $result
}

function Invoke-Fixture {
    param([string]$Mode, [bool]$ExpectedSuccess, [string]$ExpectedError)
    $script:FixtureMode = $Mode
    $script:FixtureCalls = @()
    $destination = Join-Path $root ('result ' + $Mode)
    $result = Invoke-DownloadModeCheck -Executable $script:FixtureExe -Destination $destination -Runner $runner
    Assert-Check ($result.Success -eq $ExpectedSuccess) ($Mode + ': success')
    $zip = [IO.Compression.ZipFile]::OpenRead($result.ZipPath)
    try {
        $entry = $zip.GetEntry('download-mode-report.json')
        $reader = New-Object IO.StreamReader($entry.Open())
        try { $json = $reader.ReadToEnd() } finally { $reader.Dispose() }
        Assert-Check ($json -notmatch 'PRIVATE-SERIAL-MARKER|PRIVATE-IMEI-MARKER|serialNumber|imei') ($Mode + ': identifiers discarded')
        $report = $json | ConvertFrom-Json
        Assert-Check ($report.error -eq $ExpectedError) ($Mode + ': error category')
        Assert-Check (-not $report.partition_writes -and -not $report.erase_requested -and -not $report.reboot_requested) ($Mode + ': read-only report')
        Assert-Check (($null -ne $zip.GetEntry('beyond2lte.pit')) -eq $ExpectedSuccess) ($Mode + ': only valid PIT retained')
        if ($ExpectedSuccess) {
            Assert-Check ($report.pit.entry_count -eq 8 -and $report.pit.project_name -eq 'BEYOND2') ($Mode + ': binary PIT header')
            $reader = New-Object IO.StreamReader($zip.GetEntry('partition-table.txt').Open())
            try { $table = $reader.ReadToEnd() } finally { $reader.Dispose() }
            Assert-Check ($table -match 'Partition Name: DTB' -and $table -match 'Partition Name: RECOVERY') ($Mode + ': native PIT decode')
        }
    } finally { $zip.Dispose() }
    if ($script:FixtureCalls.Count -ge 3) {
        $dump = $script:FixtureCalls[2]
        Assert-Check ($dump[-1] -eq '--no-reboot' -and $dump[2] -eq 'dump-pit') ($Mode + ': no reboot')
    }
    return $result
}

try {
    $version = Invoke-DownloadCheckNative -Executable $exe -Arguments @('--version') -TimeoutSeconds 15
    Assert-Check ($version.ExitCode -eq 0 -and $version.Stdout.Trim() -eq 'samloader 2.2.0') 'real publisher executable CLI'
    $passed++
    $result = Invoke-Fixture 'success' $true $null
    Assert-Check ($result.Report.model_confirmed_by_usb) 'USB model confirmation retained'
    $passed++
    $result = Invoke-Fixture 'unknown-model' $true $null
    Assert-Check (-not $result.Report.model_confirmed_by_usb) 'older USB query does not invent a model'
    $passed++
    foreach ($case in @(
        @('version', 'version_failed'), @('model', 'wrong_model'),
        @('json', 'usb_response_invalid'), @('missing-model', 'usb_response_invalid'),
        @('detect', 'usb_detection_failed'), @('timeout', 'usb_detection_failed'),
        @('dump', 'pit_download_failed'), @('bad-pit', 'pit_invalid'), @('print', 'pit_decode_failed')
    )) {
        $null = Invoke-Fixture $case[0] $false $case[1]
        $passed++
    }
    $successZip = $result.ZipPath
    $originalHash = (Get-FileHash -LiteralPath $successZip).Hash
    $again = Invoke-Fixture 'unknown-model' $true $null
    Assert-Check ($again.ZipPath -ne $successZip -and (Get-FileHash -LiteralPath $successZip).Hash -eq $originalHash) 'retry preserves earlier reports'
    $passed++
    $badExe = Join-Path $root 'tampered.exe'
    [IO.File]::WriteAllText($badExe, 'not the publisher executable')
    $script:FixtureCalls = @()
    $result = Invoke-DownloadModeCheck $badExe (Join-Path $root 'bad exe') $runner
    Assert-Check (-not $result.Success -and $result.Report.error -eq 'executable_invalid' -and $script:FixtureCalls.Count -eq 0) 'hash failure stops before all commands'
    $passed++
    foreach ($arguments in @(
        @('flash', '-p', 'BOOT', 'boot.img'),
        @('print-pit'),
        @('--usb-backend', 'vcom', 'dump-pit', '--output', 'C:\test.pit'),
        @('--usb-backend', 'vcom', 'detect', '--json', '--verbose')
    )) {
        $thrown = $false
        try { $null = Invoke-DownloadCheckCommand $exe $arguments 'C:\test.pit' 15 $runner }
        catch { $thrown = $_.Exception.Message -eq 'command_not_allowed' }
        Assert-Check $thrown 'non-allowlisted command rejected'
        $passed++
    }
    $echoExe = Join-Path $root 'argument echo.exe'
    Add-Type -TypeDefinition @'
using System;
using System.Text;
using System.Threading;
public class DownloadArgumentEcho {
    public static void Main(string[] args) {
        if (args.Length > 0 && args[0] == "wait") Thread.Sleep(5000);
        foreach (string value in args) Console.WriteLine("[" + Convert.ToBase64String(Encoding.UTF8.GetBytes(value)) + "]");
    }
}
'@ -OutputAssembly $echoExe -OutputType ConsoleApplication
    $arguments = @('space in value', 'x"y', 'backslash\', 'C:\with space\', 'literal $value', 'literal `tick`', '')
    $result = Invoke-DownloadCheckNative $echoExe $arguments 15
    $lines = @($result.Stdout.TrimEnd([char]13, [char]10) -split '\r?\n')
    Assert-Check ($lines.Count -eq $arguments.Count) 'native argument count'
    for ($i = 0; $i -lt $arguments.Count; $i++) {
        $expected = '[' + [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($arguments[$i])) + ']'
        Assert-Check ($lines[$i] -ceq $expected) 'native argument bytes preserved'
    }
    $passed++
    $result = Invoke-DownloadCheckNative $echoExe @('wait') 1
    Assert-Check $result.TimedOut 'native process timeout terminates child'
    $passed++
    Write-Host ('PASS: ' + $passed + ' Windows Download-mode checks; no handset access in these tests.')
} finally { Remove-Item -LiteralPath $root -Recurse -Force }
