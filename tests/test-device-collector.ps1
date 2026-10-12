$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
$testOutput = Join-Path ([System.IO.Path]::GetTempPath()) ('beyond2lte-test-' + [guid]::NewGuid().ToString() + '.json')
$global:CollectorTestWrongModel = $false

function Mock-Adb {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Parts)
    $global:LASTEXITCODE = 0
    if ($Parts[0] -eq 'devices') {
        'List of devices attached'
        "TEST-SERIAL`tdevice"
        return
    }
    if ($Parts.Count -lt 4 -or $Parts[0] -ne '-s' -or $Parts[2] -ne 'shell') { throw 'Unexpected ADB arguments' }
    if ($Parts[3] -eq 'getprop') {
        if ($Parts.Count -ne 5) { throw 'Property argument was lost' }
        switch ($Parts[4]) {
            'ro.product.model' { if ($global:CollectorTestWrongModel) { 'SM-OTHER' } else { 'SM-G975F' } }
            'ro.product.device' { 'beyond2lte' }
            'ro.vendor.build.version.release' { '12' }
            default { 'test-value' }
        }
    } elseif ($Parts[3] -eq 'cat') {
        if ($Parts[4] -ne '/proc/partitions') { throw 'Unexpected file read' }
        '8 0 100000 sda'
    } elseif ($Parts[3] -eq 'uname') {
        'Linux test-kernel 4.14.280'
    } elseif ($Parts[3].StartsWith('for n in')) {
        if ($Parts[3].Contains("`r")) { throw 'CRLF was not normalized' }
        'boot|/dev/block/sda|65536|4096'
    } else { throw 'Unexpected ADB shell command' }
}

try {
    $parseErrors = $null
    $tokens = $null
    $null = [System.Management.Automation.Language.Parser]::ParseFile((Join-Path $root 'scripts/collect-device.ps1'), [ref]$tokens, [ref]$parseErrors)
    if ($parseErrors.Count) { throw ($parseErrors | Out-String) }
    $null = [System.Management.Automation.Language.Parser]::ParseFile((Join-Path $root 'scripts/launch-device-check.ps1'), [ref]$tokens, [ref]$parseErrors)
    if ($parseErrors.Count) { throw ($parseErrors | Out-String) }
    & (Join-Path $root 'scripts/collect-device.ps1') -Adb 'Mock-Adb' -Output $testOutput
    $raw = Get-Content -Raw -LiteralPath $testOutput
    $report = $raw | ConvertFrom-Json
    if ($report.properties.'ro.vendor.build.version.release'.text -ne '12') { throw 'Property collection failed' }
    if (-not $report.read_only -or -not $report.partitions.text.StartsWith('boot|')) { throw 'Inventory collection failed' }
    if ($raw.Contains('TEST-SERIAL')) { throw 'ADB serial was saved' }
    Remove-Item -LiteralPath $testOutput
    $global:CollectorTestWrongModel = $true
    $rejected = $false
    try { & (Join-Path $root 'scripts/collect-device.ps1') -Adb 'Mock-Adb' -Output $testOutput } catch { $rejected = $true }
    if (-not $rejected -or (Test-Path -LiteralPath $testOutput)) { throw 'Wrong phone was not rejected' }
    Write-Host 'Device collector parse, arguments, metadata, serial omission and target guard: passed (mock ADB only).'
} finally {
    if (Test-Path -LiteralPath $testOutput) { Remove-Item -LiteralPath $testOutput }
    Remove-Variable -Name CollectorTestWrongModel -Scope Global -ErrorAction SilentlyContinue
}
