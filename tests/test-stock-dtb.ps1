$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
. (Join-Path $root 'scripts/extract-stock-dtb.ps1')
Initialize-StockTarReader
Add-Type -AssemblyName System.IO.Compression.FileSystem
$temporary = Join-Path ([System.IO.Path]::GetTempPath()) ('stock dtb test ' + [guid]::NewGuid().ToString())
$null = New-Item -ItemType Directory -Path $temporary

function Put-Ascii([byte[]]$Bytes, [int]$Offset, [string]$Text) {
    $encoded = [Text.Encoding]::ASCII.GetBytes($Text)
    [Array]::Copy($encoded, 0, $Bytes, $Offset, $encoded.Length)
}

function Make-Tar([string]$DtbName = 'dtb.img.lz4', [bool]$BadChecksum = $false, [byte]$DtbType = 48) {
    $memory = New-Object System.IO.MemoryStream
    try {
        foreach ($name in @('boot.img.lz4', $DtbName)) {
            $data = New-Object byte[] 256
            $data[0] = 4; $data[1] = 34; $data[2] = 77; $data[3] = 24
            $header = New-Object byte[] 512
            Put-Ascii $header 0 $name
            Put-Ascii $header 124 ([Convert]::ToString($data.Length, 8).PadLeft(11, '0'))
            Put-Ascii $header 148 '        '
            $header[156] = if ($name -eq $DtbName) { $DtbType } else { 48 }
            Put-Ascii $header 257 'ustar'
            $sum = ($header | Measure-Object -Sum).Sum
            Put-Ascii $header 148 ([Convert]::ToString([long]$sum, 8).PadLeft(6, '0'))
            $header[154] = 0; $header[155] = 32
            if ($BadChecksum) { $header[10] = $header[10] -bxor 1 }
            $memory.Write($header, 0, 512); $memory.Write($data, 0, $data.Length)
            $padding = (512 - $data.Length % 512) % 512
            $memory.Write((New-Object byte[] $padding), 0, $padding)
        }
        $memory.Write((New-Object byte[] 1024), 0, 1024)
        return ,$memory.ToArray()
    } finally { $memory.Dispose() }
}

function Reject-Tar([byte[]]$Data, [string]$Name) {
    $stream = New-Object System.IO.MemoryStream(,$Data)
    $blocked = $false
    try { $null = [StockDtbTarReader]::Extract($stream, (Join-Path $temporary ($Name + '.lz4'))) }
    catch { $blocked = $true }
    finally { $stream.Dispose() }
    if (-not $blocked) { throw ('Invalid TAR accepted: ' + $Name) }
}

try {
    $tokens = $null; $errors = $null
    $null = [Management.Automation.Language.Parser]::ParseFile((Join-Path $root 'scripts/extract-stock-dtb.ps1'), [ref]$tokens, [ref]$errors)
    if ($errors.Count) { throw ($errors | Out-String) }
    Reject-Tar (Make-Tar -BadChecksum $true) 'bad-checksum'
    Reject-Tar (Make-Tar -DtbName '../dtb.img.lz4') 'path-traversal'
    Reject-Tar (Make-Tar -DtbType 50) 'symlink'
    $full = Make-Tar
    Reject-Tar ([byte[]]$full[0..1700]) 'truncated'

    $fixture = Join-Path $temporary 'folder with spaces'
    $firmware = Join-Path $fixture 'firmware'
    $null = New-Item -ItemType Directory -Path $firmware
    $source = Join-Path $firmware 'SM-G975F-ITV-G975FXXSGHWC1.zip'
    $zip = [IO.Compression.ZipFile]::Open($source, [IO.Compression.ZipArchiveMode]::Create)
    try {
        $entry = $zip.CreateEntry('AP_G975FXXSGHWC1_test.tar.md5')
        $stream = $entry.Open()
        try { $stream.Write($full, 0, $full.Length) } finally { $stream.Dispose() }
    } finally { $zip.Dispose() }
    $sha = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant()
    $downloadReport = @{ model = 'SM-G975F'; region = 'ITV'; csc_family = 'OXM'; pda = 'G975FXXSGHWC1'
        modem = 'G975FXXSGHWB3'; firmware_download_complete = $true; ap_md5_verified = $true
        firmware_zip_sha256 = $sha; firmware_zip_bytes = (Get-Item -LiteralPath $source).Length }
    $downloadReport.firmware_zip_sha256 = ('0' * 64)
    $downloadReport | ConvertTo-Json | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $fixture 'firmware-download-report.json')
    if (Start-StockDtbExtraction $fixture) { throw 'Changed full firmware ZIP accepted' }
    $downloadReport.firmware_zip_sha256 = $sha
    $downloadReport | ConvertTo-Json | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $fixture 'firmware-download-report.json')
    if (-not (Start-StockDtbExtraction $fixture)) { throw 'Valid complete extraction rejected' }
    if ((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant() -ne $sha) { throw 'Source ZIP changed' }
    $output = [IO.Compression.ZipFile]::OpenRead((Join-Path $fixture 'dtb-inspection-inputs.zip'))
    try {
        if ($output.Entries.Count -ne 2 -or -not $output.GetEntry('dtb.img.lz4')) { throw 'Incorrect DTB output ZIP' }
        if ($output.GetEntry('dtb.img.lz4').Length -ne 256) { throw 'DTB extraction length mismatch' }
    } finally { $output.Dispose() }
    $report = Get-Content -Raw -LiteralPath (Join-Path $fixture 'dtb-extraction-report.json') | ConvertFrom-Json
    if (-not $report.dtb_extracted -or $report.handset_modified -or $report.install_ready) { throw 'Incorrect completion flags' }
    if (Start-StockDtbExtraction $fixture) { throw 'Existing output accepted for overwrite' }
    $downloadReport.region = 'OTHER'
    $downloadReport | ConvertTo-Json | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $fixture 'firmware-download-report.json')
    if (Start-StockDtbExtraction $fixture) { throw 'Wrong firmware region accepted' }
    Write-Host 'Windows PowerShell 5.1: TAR corruption, truncation, path traversal, symlink, target checks, complete streaming extraction and source preservation passed.'
} finally { Remove-Item -LiteralPath $temporary -Recurse -Force }
