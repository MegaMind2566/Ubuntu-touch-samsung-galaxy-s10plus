$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
. (Join-Path $root 'scripts/extract-stock-dtb.ps1')
Initialize-StockTarReader
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$temporary = Join-Path ([System.IO.Path]::GetTempPath()) ('stock dtb test ' + [guid]::NewGuid().ToString())
$null = New-Item -ItemType Directory -Path $temporary

function Put-Ascii([byte[]]$Bytes, [int]$Offset, [string]$Text) {
    $encoded = [Text.Encoding]::ASCII.GetBytes($Text)
    [Array]::Copy($encoded, 0, $Bytes, $Offset, $encoded.Length)
}

function Make-Tar([string]$DtbName = 'dtb.img.lz4', [bool]$BadChecksum = $false,
                  [byte]$DtbType = 48, [bool]$NoDtb = $false, [bool]$Raw = $false) {
    $memory = New-Object System.IO.MemoryStream
    try {
        $names = @('boot.img.lz4')
        if (-not $NoDtb) { $names += $DtbName }
        foreach ($name in $names) {
            $data = New-Object byte[] 256
            $data[0] = 4; $data[1] = 34; $data[2] = 77; $data[3] = 24
            if ($Raw -and $name -eq $DtbName) { $data[0] = 208; $data[1] = 13; $data[2] = 254; $data[3] = 237 }
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

function Reject-Tar([byte[]]$Data, [string]$Name, [bool]$RequireException = $true) {
    $directory = Join-Path $temporary $Name
    $null = New-Item -ItemType Directory -Path $directory
    $stream = New-Object System.IO.MemoryStream(,$Data)
    $scan = New-Object StockDtbTarScan
    $found = $false; $threw = $false
    try { $found = [StockDtbTarReaderV2]::Extract($stream, $directory, $scan) }
    catch { $threw = $true }
    finally { $stream.Dispose() }
    if ($found -or $scan.Found -or ($RequireException -and -not $threw)) { throw ('Invalid TAR accepted: ' + $Name) }
}

function Make-Fixture([string]$Name, [string]$Location, [bool]$Raw = $false) {
    $fixture = Join-Path $temporary $Name
    $firmware = Join-Path $fixture 'firmware'
    $null = New-Item -ItemType Directory -Path $firmware
    $source = Join-Path $firmware 'SM-G975F-ITV-G975FXXSGHWC1.zip'
    $zip = [IO.Compression.ZipFile]::Open($source, [IO.Compression.ZipArchiveMode]::Create)
    try {
        foreach ($part in @('BL', 'AP', 'CP')) {
            $version = if ($part -eq 'CP') { 'G975FXXSGHWB3' } else { 'G975FXXSGHWC1' }
            $entry = $zip.CreateEntry($part + '_' + $version + '_test.tar.md5')
            if ($part -eq $Location) {
                $dtbName = if ($Raw) { 'dtb.img' } else { 'dtb.img.lz4' }
                $data = Make-Tar -DtbName $dtbName -Raw $Raw
            } else { $data = Make-Tar -NoDtb $true }
            $stream = $entry.Open()
            try { $stream.Write($data, 0, $data.Length) } finally { $stream.Dispose() }
        }
    } finally { $zip.Dispose() }
    $sha = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant()
    $downloadReport = @{ model = 'SM-G975F'; region = 'ITV'; csc_family = 'OXM'; pda = 'G975FXXSGHWC1'
        modem = 'G975FXXSGHWB3'; firmware_download_complete = $true; ap_md5_verified = $true
        firmware_zip_sha256 = $sha; firmware_zip_bytes = (Get-Item -LiteralPath $source).Length }
    $downloadReport | ConvertTo-Json | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $fixture 'firmware-download-report.json')
    return $fixture
}

try {
    $tokens = $null; $errors = $null
    $null = [Management.Automation.Language.Parser]::ParseFile((Join-Path $root 'scripts/extract-stock-dtb.ps1'), [ref]$tokens, [ref]$errors)
    if ($errors.Count) { throw ($errors | Out-String) }
    Reject-Tar (Make-Tar -BadChecksum $true) 'bad-checksum'
    Reject-Tar (Make-Tar -DtbName '../dtb.img.lz4') 'path-traversal' -RequireException $false
    Reject-Tar (Make-Tar -DtbType 50) 'symlink'
    $full = Make-Tar
    Reject-Tar ([byte[]]$full[0..1700]) 'truncated'
    Reject-Tar (Make-Tar -DtbName 'dtb.img' -Raw $false) 'invalid-raw-format'

    foreach ($location in @('BL', 'AP', 'CP', 'NONE', 'RAW')) {
        $part = if ($location -eq 'RAW') { 'BL' } else { $location }
        $fixture = Make-Fixture ('folder with spaces ' + $location) $part ($location -eq 'RAW')
        $source = Join-Path $fixture 'firmware\SM-G975F-ITV-G975FXXSGHWC1.zip'
        $before = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash
        $oldWork = Join-Path $fixture 'dtb-inspection-work'
        $null = New-Item -ItemType Directory -Path $oldWork
        Set-Content -LiteralPath (Join-Path $oldWork 'keep.txt') -Value 'preserve earlier work'
        if (-not (Start-StockDtbExtraction $fixture)) { throw ('Valid inspection rejected: ' + $location) }
        if ((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash -ne $before) { throw 'Source ZIP changed' }
        if ((Get-Content -Raw -LiteralPath (Join-Path $oldWork 'keep.txt')).Trim() -ne 'preserve earlier work') {
            throw 'Earlier failed-attempt folder changed'
        }
        if (@(Get-ChildItem -Directory -LiteralPath $fixture -Filter 'dtb-inspection-work-*').Count) {
            throw 'Owned temporary directory left behind'
        }
        $reportPath = Join-Path $fixture 'dtb-extraction-report.json'
        $report = Get-Content -Raw -LiteralPath $reportPath | ConvertFrom-Json
        if ($report.tool_version -ne 2 -or -not $report.inspection_inputs_created -or
            $report.handset_modified -or $report.install_ready) { throw 'Incorrect completion flags' }
        $output = [IO.Compression.ZipFile]::OpenRead((Join-Path $fixture 'dtb-inspection-inputs.zip'))
        try {
            if ($location -eq 'NONE') {
                if ($report.dtb_extracted -or -not $report.search_complete -or $output.Entries.Count -ne 1) {
                    throw 'Missing DTB diagnostic bundle incorrect'
                }
                if ($report.archives_scanned.Count -ne 3) { throw 'Not all archives searched' }
                foreach ($scan in $report.archives_scanned) {
                    if (-not $scan.listing_complete -or -not $scan.members.Count) { throw 'Missing TAR member catalog' }
                }
            } else {
                $expected = if ($location -eq 'RAW') { 'dtb.img' } else { 'dtb.img.lz4' }
                if (-not $report.dtb_extracted -or $output.Entries.Count -ne 2 -or
                    $output.GetEntry($expected).Length -ne 256) { throw 'Incorrect DTB output' }
                if (-not $report.stock_dtb.package_name.StartsWith($part + '_')) { throw 'Incorrect source archive recorded' }
                if ($part -eq 'BL' -and $report.archives_scanned.Count -ne 1) { throw 'BL was not searched first' }
                if ($part -eq 'AP' -and (-not $report.archives_scanned[0].listing_complete -or
                    $report.archives_scanned[0].dtb_found)) { throw 'Empty BL fallback failed' }
            }
        } finally { $output.Dispose() }
        $savedReportSha = (Get-FileHash -LiteralPath $reportPath -Algorithm SHA256).Hash
        if (Start-StockDtbExtraction $fixture) { throw 'Existing output accepted for overwrite' }
        if ((Get-FileHash -LiteralPath $reportPath -Algorithm SHA256).Hash -ne $savedReportSha) { throw 'Successful report overwritten' }
    }

    $fixture = Make-Fixture 'guard checks' 'BL'
    $downloadPath = Join-Path $fixture 'firmware-download-report.json'
    $download = Get-Content -Raw -LiteralPath $downloadPath | ConvertFrom-Json
    $download.region = 'OTHER'
    $download | ConvertTo-Json | Set-Content -Encoding UTF8 -LiteralPath $downloadPath
    if (Start-StockDtbExtraction $fixture) { throw 'Wrong region accepted' }
    $download.region = 'ITV'; $download.firmware_zip_sha256 = ('0' * 64)
    $download | ConvertTo-Json | Set-Content -Encoding UTF8 -LiteralPath $downloadPath
    if (Start-StockDtbExtraction $fixture) { throw 'Changed firmware ZIP accepted' }
    if (@(Get-ChildItem -Directory -LiteralPath $fixture -Filter 'dtb-inspection-work-*').Count) { throw 'Guard failure left temporary work' }
    Write-Host 'Windows PowerShell 5.1: BL-first search, AP/other fallback, raw DTB, missing-DTB catalog, retry after failure, archive corruption/truncation, target/hash guards and source preservation passed.'
} finally { Remove-Item -LiteralPath $temporary -Recurse -Force }
