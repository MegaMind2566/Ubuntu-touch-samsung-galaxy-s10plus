param([string]$PackageRoot = (Split-Path -Parent $PSScriptRoot))
$ErrorActionPreference = 'Stop'

function Initialize-StockTarReader {
    if ('StockDtbTarReader' -as [type]) { return }
    Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
public static class StockDtbTarReader {
    static void ReadExact(Stream stream, byte[] bytes, int count) {
        int offset = 0;
        while (offset < count) {
            int read = stream.Read(bytes, offset, count - offset);
            if (read == 0) throw new InvalidDataException("Pacchetto AP incompleto.");
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
    public static string[] Extract(Stream stream, string output) {
        byte[] header = new byte[512];
        byte[] buffer = new byte[1024 * 1024];
        List<string> names = new List<string>();
        for (int member = 0; member < 1000; ++member) {
            ReadExact(stream, header, 512);
            long sum = 0;
            bool zero = true;
            for (int i = 0; i < 512; ++i) {
                if (header[i] != 0) zero = false;
                sum += (i >= 148 && i < 156) ? 32 : header[i];
            }
            if (zero) throw new FileNotFoundException("dtb.img.lz4 non trovato nel pacchetto AP.");
            if (sum != Octal(header, 148, 8)) throw new InvalidDataException("Checksum TAR errato.");
            string name = Text(header, 0, 100);
            string prefix = Text(header, 345, 155);
            if (prefix.Length != 0) name = prefix + "/" + name;
            names.Add(name);
            long size = Octal(header, 124, 12);
            bool wanted = name == "dtb.img.lz4" || name == "./dtb.img.lz4";
            if (wanted && (header[156] != 0 && header[156] != 48))
                throw new InvalidDataException("Il DTB non e un file regolare.");
            if (wanted && (size < 4 || size > 32 * 1024 * 1024))
                throw new InvalidDataException("Dimensione DTB inattesa.");
            if (size > 16L * 1024 * 1024 * 1024)
                throw new InvalidDataException("Dimensione elemento AP inattesa.");
            if (wanted) {
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
                    if (magic[0] != 4 || magic[1] != 34 || magic[2] != 77 || magic[3] != 24)
                        throw new InvalidDataException("Formato LZ4 del DTB inatteso.");
                }
                return names.ToArray();
            }
            long skip = checked(size + (512 - size % 512) % 512);
            while (skip != 0) {
                int count = (int)Math.Min(buffer.Length, skip);
                ReadExact(stream, buffer, count); skip -= count;
            }
        }
        throw new InvalidDataException("Troppi elementi nel pacchetto AP.");
    }
}
'@
}

function Start-StockDtbExtraction([string]$Root) {
    $reportPath = Join-Path $Root 'dtb-extraction-report.json'
    $report = [ordered]@{ captured_utc = [DateTime]::UtcNow.ToString('o'); model = 'SM-G975F'
        pda = 'G975FXXSGHWC1'; region = 'ITV'; csc_family = 'OXM'; modem = 'G975FXXSGHWB3'
        handset_modified = $false; install_ready = $false; dtb_extracted = $false }
    try {
        $sourceReport = Get-Content -Raw -LiteralPath (Join-Path $Root 'firmware-download-report.json') | ConvertFrom-Json
        foreach ($field in @('model', 'pda', 'region', 'csc_family', 'modem')) {
            if ($sourceReport.$field -ne $report[$field]) { throw ('Firmware diverso dal target: ' + $field) }
        }
        if (-not $sourceReport.firmware_download_complete -or -not $sourceReport.ap_md5_verified -or
            $sourceReport.firmware_zip_sha256 -notmatch '^[0-9a-f]{64}$') {
            throw 'Il controllo originale del firmware non risulta completato.'
        }
        $source = Join-Path $Root 'firmware\SM-G975F-ITV-G975FXXSGHWC1.zip'
        if ((Get-Item -LiteralPath $source).Length -ne $sourceReport.firmware_zip_bytes) {
            throw 'La dimensione del firmware completo e cambiata.'
        }
        $work = Join-Path $Root 'dtb-inspection-work'
        $bundle = Join-Path $Root 'dtb-inspection-inputs.zip'
        if ((Test-Path -LiteralPath $work) -or (Test-Path -LiteralPath $bundle)) {
            throw 'Esiste gia un risultato DTB. Conservalo e invialo in chat.'
        }
        Write-Host 'Controllo il firmware completo gia scaricato. Puo richiedere alcuni minuti.'
        $sha = (Get-FileHash -Algorithm SHA256 -LiteralPath $source).Hash.ToLowerInvariant()
        if ($sha -ne $sourceReport.firmware_zip_sha256) { throw 'Checksum dello ZIP completo diverso dal controllo originale.' }
        $report.firmware_zip_sha256 = $sha
        $report.firmware_zip_bytes = $sourceReport.firmware_zip_bytes
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        Initialize-StockTarReader
        $archive = [System.IO.Compression.ZipFile]::OpenRead($source)
        try {
            $entries = @($archive.Entries | Where-Object { $_.Name -like '*.tar.md5' })
            $report.packages = @($entries | ForEach-Object { @{ name = $_.Name; bytes = $_.Length } })
            $ap = @($entries | Where-Object { $_.FullName -eq $_.Name -and $_.Name -like 'AP_G975FXXSGHWC1_*.tar.md5' })
            if ($ap.Count -ne 1) { throw 'Pacchetto AP esatto non trovato.' }
            $null = New-Item -ItemType Directory -Path $work
            $output = Join-Path $work 'dtb.img.lz4'
            $stream = $ap[0].Open()
            try {
                Write-Host 'Estraggo il DTB dal pacchetto AP.'
                $report.ap_members_read_before_dtb = [StockDtbTarReader]::Extract($stream, $output)
            } finally { $stream.Dispose() }
        } finally { $archive.Dispose() }
        $report.ap_listing_complete = $false
        $report.stock_dtb = @{ name = 'dtb.img.lz4'; compressed_bytes = (Get-Item -LiteralPath $output).Length
            sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $output).Hash.ToLowerInvariant() }
        $report.dtb_extracted = $true
        $report | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 -LiteralPath $reportPath
        Copy-Item -LiteralPath $reportPath -Destination (Join-Path $work 'dtb-extraction-report.json')
        [System.IO.Compression.ZipFile]::CreateFromDirectory($work, $bundle)
        Remove-Item -LiteralPath $work -Recurse
        Write-Host 'Completato. Invia dtb-inspection-inputs.zip in chat.'
        return $true
    } catch {
        $report.error = $_.Exception.Message
        Write-Host ('Errore: ' + $report.error) -ForegroundColor Red
        Write-Host 'Il pacchetto va estratto nella stessa cartella di SCARICA-FIRMWARE.cmd.'
        Write-Host 'In caso di errore invia dtb-extraction-report.json.'
        return $false
    } finally {
        $report | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 -LiteralPath $reportPath
    }
}

if ($MyInvocation.InvocationName -ne '.') {
    if (-not (Start-StockDtbExtraction $PackageRoot)) { exit 1 }
}
