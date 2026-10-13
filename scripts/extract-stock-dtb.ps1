param([string]$PackageRoot = (Split-Path -Parent $PSScriptRoot))
$ErrorActionPreference = 'Stop'

function Initialize-StockTarReader {
    if ('StockDtbTarReaderV3' -as [type]) { return }
    Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
public sealed class StockDtbTarScan {
    public List<string> Members = new List<string>();
    public bool ListingComplete;
    public bool Found;
    public string ImageName;
}
public static class StockDtbTarReaderV3 {
    static void ReadExact(Stream stream, byte[] bytes, int count) {
        int offset = 0;
        while (offset < count) {
            int read = stream.Read(bytes, offset, count - offset);
            if (read == 0) throw new InvalidDataException("Archivio TAR incompleto.");
            offset += read;
        }
    }
    static long Octal(byte[] bytes, int offset, int length) {
        long value = 0;
        for (int i = offset; i < offset + length; ++i) {
            byte ch = bytes[i];
            if (ch == 0 || ch == 32) continue;
            if (ch < 48 || ch > 55) throw new InvalidDataException("Campo TAR non supportato.");
            value = checked(value * 8 + ch - 48);
        }
        return value;
    }
    static string Text(byte[] bytes, int offset, int length) {
        int end = offset;
        while (end < offset + length && bytes[end] != 0) ++end;
        return Encoding.ASCII.GetString(bytes, offset, end - offset);
    }
    public static bool Extract(Stream stream, string outputDirectory, StockDtbTarScan scan) {
        byte[] header = new byte[512];
        byte[] buffer = new byte[1024 * 1024];
        for (int member = 0; member < 1000; ++member) {
            ReadExact(stream, header, 512);
            long sum = 0;
            bool zero = true;
            for (int i = 0; i < 512; ++i) {
                if (header[i] != 0) zero = false;
                sum += (i >= 148 && i < 156) ? 32 : header[i];
            }
            if (zero) { scan.ListingComplete = true; return false; }
            if (sum != Octal(header, 148, 8)) throw new InvalidDataException("Checksum TAR errato.");
            string name = Text(header, 0, 100);
            string prefix = Text(header, 345, 155);
            if (prefix.Length != 0) name = prefix + "/" + name;
            scan.Members.Add(name);
            long size = Octal(header, 124, 12);
            string normal = (name.StartsWith("./") ? name.Substring(2) : name).ToLowerInvariant();
            bool compressed = normal == "dtb.img.lz4" || normal == "dtb.bin.lz4" || normal == "dt.img.lz4";
            bool wanted = compressed || normal == "dtb.img" || normal == "dtb.bin" || normal == "dt.img";
            if (wanted && (header[156] != 0 && header[156] != 48))
                throw new InvalidDataException("Il DTB non e un file regolare.");
            if (wanted && (size < 4 || size > 32 * 1024 * 1024))
                throw new InvalidDataException("Dimensione DTB inattesa.");
            if (size > 16L * 1024 * 1024 * 1024)
                throw new InvalidDataException("Dimensione elemento TAR inattesa.");
            if (wanted) {
                string output = Path.Combine(outputDirectory, normal);
                using (FileStream target = new FileStream(output, FileMode.CreateNew, FileAccess.Write)) {
                    long remaining = size;
                    while (remaining != 0) {
                        int count = (int)Math.Min(buffer.Length, remaining);
                        ReadExact(stream, buffer, count);
                        target.Write(buffer, 0, count);
                        remaining -= count;
                    }
                }
                using (FileStream target = File.OpenRead(output)) {
                    byte[] magic = new byte[4]; ReadExact(target, magic, 4);
                    bool lz4 = magic[0] == 4 && magic[1] == 34 && magic[2] == 77 && magic[3] == 24;
                    bool fdt = magic[0] == 208 && magic[1] == 13 && magic[2] == 254 && magic[3] == 237;
                    bool table = magic[0] == 215 && magic[1] == 183 && magic[2] == 171 && magic[3] == 30;
                    string tag = Encoding.ASCII.GetString(magic);
                    if ((compressed && !lz4) || (!compressed && !fdt && !table && tag != "DTBH" && tag != "dtbh"))
                        throw new InvalidDataException("Formato del DTB inatteso.");
                }
                scan.Found = true; scan.ImageName = normal;
                return true;
            }
            long skip = checked(size + (512 - size % 512) % 512);
            while (skip != 0) {
                int count = (int)Math.Min(buffer.Length, skip);
                ReadExact(stream, buffer, count); skip -= count;
            }
        }
        throw new InvalidDataException("Troppi elementi nel pacchetto TAR.");
    }
}
'@
}

function Read-PreviousDtbDiagnostics([string]$Path) {
    if ((Get-Item -LiteralPath $Path).Length -gt 1048576) { return $null }
    Add-Type -AssemblyName System.IO.Compression
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = $null
    try {
        $archive = [IO.Compression.ZipFile]::OpenRead($Path)
        $entry = $archive.GetEntry('dtb-extraction-report.json')
        if ($archive.Entries.Count -ne 1 -or -not $entry -or $entry.Length -gt 1048576) { return $null }
        $stream = $entry.Open()
        $reader = New-Object System.IO.StreamReader($stream)
        try { $previous = $reader.ReadToEnd() | ConvertFrom-Json }
        finally { $reader.Dispose(); $stream.Dispose() }
        if ($previous.dtb_extracted -ne $false -or $previous.inspection_inputs_created -ne $true -or
            $previous.firmware_zip_sha256 -notmatch '^[0-9a-f]{64}$') { return $null }
        return @{ report = $previous; archive_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash }
    } catch { return $null }
    finally { if ($archive) { $archive.Dispose() } }
}

function Start-StockDtbExtraction([string]$Root) {
    $bundle = Join-Path $Root 'dtb-inspection-inputs.zip'
    $previous = $null
    if (Test-Path -LiteralPath $bundle) {
        $previous = Read-PreviousDtbDiagnostics $bundle
        if (-not $previous) {
            Write-Host 'Esiste gia dtb-inspection-inputs.zip. Conservalo e invialo in chat.'
            return $false
        }
    }
    $reportPath = Join-Path $Root 'dtb-extraction-report.json'
    $work = $null
    $report = [ordered]@{ tool_version = 3; captured_utc = [DateTime]::UtcNow.ToString('o'); model = 'SM-G975F'
        pda = 'G975FXXSGHWC1'; region = 'ITV'; csc_family = 'OXM'; modem = 'G975FXXSGHWB3'
        handset_modified = $false; install_ready = $false; dtb_extracted = $false
        inspection_inputs_created = $false; archives_scanned = @() }
    try {
        $sourceReport = Get-Content -Raw -LiteralPath (Join-Path $Root 'firmware-download-report.json') | ConvertFrom-Json
        foreach ($field in @('model', 'pda', 'region', 'csc_family', 'modem')) {
            if ($sourceReport.$field -ne $report[$field]) { throw ('Firmware diverso dal target: ' + $field) }
            if ($previous -and $previous.report.$field -ne $report[$field]) {
                throw 'Il precedente ZIP di controllo appartiene a un firmware diverso. Conservalo.'
            }
        }
        if (-not $sourceReport.firmware_download_complete -or -not $sourceReport.ap_md5_verified -or
            $sourceReport.firmware_zip_sha256 -notmatch '^[0-9a-f]{64}$') {
            throw 'Il controllo originale del firmware non risulta completato.'
        }
        $source = Join-Path $Root 'firmware\SM-G975F-ITV-G975FXXSGHWC1.zip'
        if ((Get-Item -LiteralPath $source).Length -ne $sourceReport.firmware_zip_bytes) {
            throw 'La dimensione del firmware completo e cambiata.'
        }
        if ($previous -and ($previous.report.firmware_zip_sha256 -ne $sourceReport.firmware_zip_sha256 -or
            $previous.report.firmware_zip_bytes -ne $sourceReport.firmware_zip_bytes)) {
            throw 'Il precedente ZIP di controllo appartiene a un archivio diverso. Conservalo.'
        }
        Write-Host 'Estrattore DTB v3: include il file Samsung dt.img.lz4.'
        Write-Host 'Verifico il firmware completo gia scaricato. Puo richiedere alcuni minuti.'
        $sha = (Get-FileHash -Algorithm SHA256 -LiteralPath $source).Hash.ToLowerInvariant()
        if ($sha -ne $sourceReport.firmware_zip_sha256) { throw 'Checksum dello ZIP completo diverso dal controllo originale.' }
        $report.firmware_zip_sha256 = $sha
        $report.firmware_zip_bytes = $sourceReport.firmware_zip_bytes
        if ($previous) {
            if ((Get-FileHash -Algorithm SHA256 -LiteralPath $bundle).Hash -ne $previous.archive_sha256) {
                throw 'Il precedente ZIP di controllo e cambiato durante la verifica. Conservalo.'
            }
            $backupName = 'dtb-inspection-inputs-report-only-' + [guid]::NewGuid().ToString('N') + '.zip'
            Move-Item -LiteralPath $bundle -Destination (Join-Path $Root $backupName)
            $report.previous_diagnostic_bundle = $backupName
        }
        Add-Type -AssemblyName System.IO.Compression
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        Initialize-StockTarReader
        $archive = [System.IO.Compression.ZipFile]::OpenRead($source)
        try {
            $entries = @($archive.Entries | Where-Object { $_.Name -like '*.tar.md5' })
            if (@($entries | Where-Object { $_.FullName -ne $_.Name }).Count) { throw 'Pacchetti firmware con percorsi inattesi.' }
            $report.packages = @($entries | ForEach-Object { @{ name = $_.Name; bytes = $_.Length } })
            $bl = @($entries | Where-Object { $_.Name -like 'BL_G975FXXSGHWC1_*.tar.md5' })
            $ap = @($entries | Where-Object { $_.Name -like 'AP_G975FXXSGHWC1_*.tar.md5' })
            if ($bl.Count -ne 1 -or $ap.Count -ne 1) { throw 'Pacchetti BL/AP esatti non trovati.' }
            $candidates = @($bl[0], $ap[0]) + @($entries | Where-Object {
                $_.FullName -ne $bl[0].FullName -and $_.FullName -ne $ap[0].FullName
            } | Sort-Object Length)
            $work = Join-Path $Root ('dtb-inspection-work-' + [guid]::NewGuid().ToString('N'))
            $null = New-Item -ItemType Directory -Path $work
            foreach ($entry in $candidates) {
                $scan = New-Object StockDtbTarScan
                $item = [ordered]@{ package_name = $entry.Name; members = @(); listing_complete = $false; dtb_found = $false }
                $report.archives_scanned += $item
                $stream = $entry.Open()
                try {
                    Write-Host ('Cerco il DTB in ' + $entry.Name)
                    $found = [StockDtbTarReaderV3]::Extract($stream, $work, $scan)
                } finally {
                    $item.members = @($scan.Members.ToArray())
                    $item.listing_complete = $scan.ListingComplete
                    $item.dtb_found = $scan.Found
                    $stream.Dispose()
                }
                if ($found) {
                    $output = Join-Path $work $scan.ImageName
                    $report.stock_dtb = @{ name = $scan.ImageName; bytes = (Get-Item -LiteralPath $output).Length
                        compressed = $scan.ImageName.EndsWith('.lz4')
                        sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $output).Hash.ToLowerInvariant()
                        package_name = $entry.Name }
                    $report.dtb_extracted = $true
                    break
                }
            }
        } finally { $archive.Dispose() }
        $report.search_complete = -not $report.dtb_extracted
        if (-not $report.dtb_extracted) {
            $report.note = 'Nessun DTB separato riconosciuto. Il bundle contiene gli elenchi completi dei pacchetti controllati.'
            Write-Host 'DTB separato non trovato. Salvo gli elenchi dei file per il controllo.'
        }
        $report.inspection_inputs_created = $true
        $report | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 -LiteralPath $reportPath
        Copy-Item -LiteralPath $reportPath -Destination (Join-Path $work 'dtb-extraction-report.json')
        [System.IO.Compression.ZipFile]::CreateFromDirectory($work, $bundle)
        Write-Host 'Controllo completato. Invia dtb-inspection-inputs.zip in chat.'
        return $true
    } catch {
        $report.error = $_.Exception.Message
        $report.inspection_inputs_created = $false
        Write-Host ('Errore: ' + $report.error) -ForegroundColor Red
        Write-Host 'In caso di errore invia dtb-extraction-report.json.'
        return $false
    } finally {
        $report | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 -LiteralPath $reportPath
        if ($work -and (Test-Path -LiteralPath $work)) { Remove-Item -LiteralPath $work -Recurse }
    }
}

if ($MyInvocation.InvocationName -ne '.') {
    if (-not (Start-StockDtbExtraction $PackageRoot)) { exit 1 }
}
