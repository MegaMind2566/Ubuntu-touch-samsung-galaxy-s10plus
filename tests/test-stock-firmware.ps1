param([string]$RealTool = '')
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
. (Join-Path $root 'scripts/download-stock-firmware.ps1')
$target = Get-Content -Raw (Join-Path $root 'docs/stock-firmware-target-2026-10-12.json') | ConvertFrom-Json
$temporary = Join-Path ([System.IO.Path]::GetTempPath()) ('stock firmware test ' + [guid]::NewGuid().ToString())
$null = New-Item -ItemType Directory -Path $temporary

try {
    $parseErrors = $null; $tokens = $null
    $null = [System.Management.Automation.Language.Parser]::ParseFile((Join-Path $root 'scripts/download-stock-firmware.ps1'), [ref]$tokens, [ref]$parseErrors)
    if ($parseErrors.Count) { throw ($parseErrors | Out-String) }
    if (-not (Test-StockTarget $target)) { throw 'Correct screenshot target rejected' }
    foreach ($field in @('model', 'region', 'pda', 'modem')) {
        $bad = ($target | ConvertTo-Json | ConvertFrom-Json)
        $bad.$field = 'OTHER'
        if (Test-StockTarget $bad) { throw ('Wrong target accepted: ' + $field) }
    }
    $goodVersion = 'G975FXXSGHWC1/G975FOXMGHWA3/G975FXXSGHWB3'
    if (-not (Test-StockVersion $goodVersion $target) -or -not (Test-StockVersion ($goodVersion + '/G975FXXSGHWC1') $target)) {
        throw 'Exact firmware version rejected'
    }
    foreach ($version in @(
        'G975FXXSGHWI1/G975FOXMGHWA3/G975FXXSGHWB3',
        'G975FXXSGHWC1/G975FHUIHWA3/G975FXXSGHWB3',
        'G975FXXSGHWC1/G975FOXMGHWA3/G975FXXSGHWB4',
        'G975FXXSGHWC1/G975FOXMGHWA3/G975FXXSGHWB3/G975FXXSGHWI1'
    )) {
        if (Test-StockVersion $version $target) { throw ('Different server firmware accepted: ' + $version) }
    }
    $blocked = $false
    try { $null = Invoke-Samloader -File 'not-an-executable' -Arguments @('flash') } catch { $blocked = $true }
    if (-not $blocked) { throw 'Unexpected command was not rejected' }

    # Real child process: stop a misdirected server response before its write.
    $fake = Join-Path $temporary 'fake download.exe'
    Add-Type -TypeDefinition @'
using System;
using System.IO;
using System.Threading;
public class FakeFirmwareDownload {
    public static void Main(string[] args) {
        Console.WriteLine("Firmware Version: G975FXXSGHWI1/G975FOXMGHWA3/G975FXXSGHWB3");
        Console.Out.Flush();
        Thread.Sleep(3000);
        File.WriteAllText(args[0], "download should have been stopped");
    }
}
'@ -OutputAssembly $fake -OutputType ConsoleApplication
    $marker = Join-Path $temporary 'marker with spaces.txt'
    $blocked = $false
    try {
        $null = Invoke-LocalProcess -File $fake -Arguments @($marker) -OnLine {
            param($line)
            if ($line -match '^Firmware Version:\s*(\S+)') {
                if (-not (Test-StockVersion $Matches[1] $target)) { throw 'Different version stopped' }
            }
        }
    } catch { $blocked = $true }
    if (-not $blocked -or (Test-Path -LiteralPath $marker)) { throw 'Misdirected download process was not stopped before writing' }
    $blocked = $false
    try { $null = Invoke-LocalProcess -File $fake -Arguments @($marker) -TimeoutSeconds 1 } catch { $blocked = $true }
    if (-not $blocked -or (Test-Path -LiteralPath $marker)) { throw 'Unresponsive process was not stopped' }

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    foreach ($wrong in @($false, $true)) {
        $fixture = Join-Path $temporary ('catalog-' + $wrong + '.zip')
        $zip = [System.IO.Compression.ZipFile]::Open($fixture, [System.IO.Compression.ZipArchiveMode]::Create)
        try {
            $ap = if ($wrong) { 'AP_G975FXXSGHWI1_test.tar.md5' } else { 'AP_G975FXXSGHWC1_test.tar.md5' }
            foreach ($name in @($ap, 'BL_G975FXXSGHWC1_test.tar.md5', 'CP_G975FXXSGHWB3_test.tar.md5', 'CSC_OXM_G975FOXMGHWA3_test.tar.md5')) {
                $entry = $zip.CreateEntry($name); $stream = $entry.Open()
                try { $stream.Write((New-Object byte[] 2048), 0, 2048) } finally { $stream.Dispose() }
            }
        } finally { $zip.Dispose() }
        $rejected = $false
        try { $null = Read-StockZip -Path $fixture -Target $target } catch { $rejected = $true }
        if ($rejected -ne $wrong) { throw 'Firmware ZIP catalog guard failed' }
    }
    if ($RealTool) {
        $probe = Invoke-Samloader -File $RealTool -Arguments @('--version') -TimeoutSeconds 15
        if ($probe.exit_code -ne 0 -or ($probe.lines -join '') -ne 'samloader 2.2.0') { throw 'Real Windows executable version check failed' }
        $help = Invoke-Samloader -File $RealTool -Arguments @('download', '--help') -TimeoutSeconds 15
        if ($help.exit_code -ne 0 -or ($help.lines -join "`n") -notmatch '--version') { throw 'Real Windows CLI does not support the pinned version parameter' }
    }
    Write-Host 'Firmware target/catalog guards, native argument quoting, wrong-version process termination, timeout and real Windows CLI: passed.'
} finally { Remove-Item -LiteralPath $temporary -Recurse -Force }
