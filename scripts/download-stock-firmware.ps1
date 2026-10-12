param([string]$PackageRoot = (Split-Path -Parent $PSScriptRoot))
$ErrorActionPreference = 'Stop'

function Test-StockTarget($Target) {
    return $Target.model -eq 'SM-G975F' -and $Target.region -eq 'ITV' -and
        $Target.csc_family -eq 'OXM' -and $Target.pda -eq 'G975FXXSGHWC1' -and $Target.modem -eq 'G975FXXSGHWB3'
}

function Test-StockVersion([string]$Version, $Target) {
    $parts = $Version -split '/'
    return ($parts.Count -eq 3 -or $parts.Count -eq 4) -and $parts[0] -eq $Target.pda -and
        $parts[1] -match '^G975FOXM[A-Z0-9]+$' -and $parts[2] -eq $Target.modem -and
        ($parts.Count -eq 3 -or $parts[3] -eq $Target.pda)
}

function Quote-ProcessArgument([string]$Value) {
    # Win32 command-line quoting; no command shell is involved.
    $escaped = [regex]::Replace($Value, '(\\*)"', '$1$1\"')
    $escaped = [regex]::Replace($escaped, '(\\+)$', '$1$1')
    return '"' + $escaped + '"'
}

function Invoke-LocalProcess([string]$File, [string[]]$Arguments, [scriptblock]$OnLine = {}, [int]$TimeoutSeconds = 0) {
    $start = New-Object System.Diagnostics.ProcessStartInfo
    $start.FileName = $File
    $start.Arguments = (($Arguments | ForEach-Object { Quote-ProcessArgument $_ }) -join ' ')
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $start
    $lines = New-Object 'System.Collections.Generic.List[string]'
    $started = $false
    try {
        $null = $process.Start()
        $started = $true
        $errors = $process.StandardError.ReadToEndAsync()
        $clock = [System.Diagnostics.Stopwatch]::StartNew()
        $nextLine = $process.StandardOutput.ReadLineAsync()
        while ($true) {
            if ($nextLine.Wait(500)) {
                $line = $nextLine.Result
                if ($null -eq $line) { break }
                $lines.Add($line)
                & $OnLine $line
                $nextLine = $process.StandardOutput.ReadLineAsync()
            }
            if ($TimeoutSeconds -gt 0 -and $clock.Elapsed.TotalSeconds -ge $TimeoutSeconds) {
                throw 'Il server non risponde entro il tempo previsto.'
            }
        }
        $process.WaitForExit()
        return @{ lines = $lines.ToArray(); errors = $errors.Result; exit_code = $process.ExitCode }
    } catch {
        if ($started -and -not $process.HasExited) { $process.Kill(); $process.WaitForExit() }
        throw
    } finally { $process.Dispose() }
}

function Invoke-Samloader([string]$File, [string[]]$Arguments, [scriptblock]$OnLine = {}, [int]$TimeoutSeconds = 0) {
    if (-not $Arguments.Count -or $Arguments[0] -notin @('--version', 'check-update', 'download', 'verify-md5')) {
        throw 'Comando non consentito nel programma di download.'
    }
    return Invoke-LocalProcess -File $File -Arguments $Arguments -OnLine $OnLine -TimeoutSeconds $TimeoutSeconds
}

function Read-StockZip([string]$Path, $Target) {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [System.IO.Compression.ZipFile]::OpenRead($Path)
    try {
        $entries = @($archive.Entries | Where-Object { $_.Name -like '*.tar.md5' })
        foreach ($entry in $entries) {
            if ($entry.FullName -ne $entry.Name) { throw 'Archivio con percorsi inattesi.' }
            if ($entry.Length -lt 1024) { throw 'Pacchetto TAR vuoto o incompleto.' }
        }
        $ap = @($entries | Where-Object { $_.Name -like ('AP_' + $Target.pda + '_*.tar.md5') })
        $bl = @($entries | Where-Object { $_.Name -like ('BL_' + $Target.pda + '_*.tar.md5') })
        $cp = @($entries | Where-Object { $_.Name -like ('CP_' + $Target.modem + '_*.tar.md5') })
        $csc = @($entries | Where-Object { $_.Name -match '^CSC_(?:OMC_)?OXM_G975FOXM[A-Z0-9]+_.*\.tar\.md5$' })
        if ($ap.Count -ne 1 -or $bl.Count -ne 1 -or $cp.Count -ne 1 -or $csc.Count -ne 1) {
            throw 'Il contenuto dello ZIP non corrisponde al firmware SM-G975F / ITV / OXM richiesto.'
        }
        return @{ ap_name = $ap[0].Name; packages = @($entries | ForEach-Object {
            @{ name = $_.Name; bytes = $_.Length }
        }) }
    } finally { $archive.Dispose() }
}

function Start-StockDownload([string]$Root) {
    $reportPath = Join-Path $Root 'firmware-download-report.json'
    $report = [ordered]@{
        captured_utc = [DateTime]::UtcNow.ToString('o')
        model = 'SM-G975F'; region = 'ITV'; csc_family = 'OXM'
        pda = 'G975FXXSGHWC1'; modem = 'G975FXXSGHWB3'
        firmware_download_complete = $false; inspection_inputs_created = $false
        handset_modified = $false; stock_layout_inspected = $false; install_ready = $false
    }
    try {
        $settings = Get-Content -Raw -LiteralPath (Join-Path $Root 'package-settings.json') | ConvertFrom-Json
        $target = $settings.target
        if (-not (Test-StockTarget $target)) { throw 'Configurazione diversa dal target verificato.' }
        $tool = Join-Path $Root 'tools\samloader.exe'
        if ((Get-FileHash -Algorithm SHA256 -LiteralPath $tool).Hash.ToLowerInvariant() -ne $settings.samloader_exe_sha256) {
            throw 'Il programma di download non corrisponde alla copia verificata.'
        }
        $version = Invoke-Samloader -File $tool -Arguments @('--version') -TimeoutSeconds 15
        if ($version.exit_code -ne 0 -or ($version.lines -join '') -ne 'samloader 2.2.0') { throw 'Versione del programma inattesa.' }
        $tar = Get-Command tar.exe -ErrorAction SilentlyContinue
        if (-not $tar) { throw 'tar.exe non trovato. Questo pacchetto richiede Windows 10/11.' }
        $directory = Join-Path $Root 'firmware'
        $null = New-Item -ItemType Directory -Force -Path $directory
        $destination = Join-Path $directory 'SM-G975F-ITV-G975FXXSGHWC1.zip'
        Write-Host 'Firmware Samsung: SM-G975F / ITV / OXM / G975FXXSGHWC1'
        Write-Host 'Il telefono puo restare scollegato. Questa procedura lavora solo sul PC.'
        if (-not (Test-Path -LiteralPath $destination)) {
            $query = Invoke-Samloader -File $tool -Arguments @('check-update', '-m', $target.model, '-r', $target.region, '--all') -TimeoutSeconds 90
            if ($query.exit_code -ne 0) { throw 'Samsung non restituisce la lista firmware. Invia firmware-download-report.json.' }
            $available = @($query.lines | Where-Object { Test-StockVersion $_.Trim() $target } | ForEach-Object { $_.Trim() })
            $report.available_version_lines = @($query.lines | Where-Object { $_ -match '^G975F[A-Z0-9]+/' })
            if (-not $available.Count) { throw 'La versione esatta installata non risulta nella lista Samsung. Nessuna versione alternativa scaricata.' }
            $selected = $available[0]
            $report.requested_version = $selected
            $state = @{ seen = $false; version = '' }
            Write-Host 'Download del firmware completo. Puo richiedere diversi minuti; lascia aperta la finestra.'
            $download = Invoke-Samloader -File $tool -Arguments @('download', '-m', $target.model, '-r', $target.region, '-v', $selected, '-o', $destination) -OnLine {
                param($line)
                if ($line -match '^Firmware Version:\s*(\S+)\s*$') {
                    $state.seen = $true; $state.version = $Matches[1]
                    if (-not (Test-StockVersion $state.version $target)) {
                        throw 'Samsung ha proposto un firmware diverso. Download fermato.'
                    }
                    Write-Host ('Versione confermata dal server: ' + $state.version)
                }
            }
            if ($download.exit_code -ne 0 -or -not $state.seen) { throw 'Download non completato. Riesegui SCARICA-FIRMWARE.cmd per riprenderlo.' }
            $report.server_returned_version = $state.version
        }
        $catalog = Read-StockZip -Path $destination -Target $target
        $report.packages = $catalog.packages
        $report.firmware_zip_bytes = (Get-Item -LiteralPath $destination).Length
        $report.firmware_zip_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $destination).Hash.ToLowerInvariant()
        $report.firmware_download_complete = $true
        Write-Host 'Firmware completo salvato nella cartella firmware. Preparo i file di controllo.'

        $work = Join-Path $Root 'inspection-work'
        if (Test-Path -LiteralPath $work) { throw 'La cartella inspection-work esiste gia. Conserva il firmware e usa una nuova cartella per il controllo.' }
        $null = New-Item -ItemType Directory -Path $work
        $apPath = Join-Path $work $catalog.ap_name
        $archive = [System.IO.Compression.ZipFile]::OpenRead($destination)
        try { [System.IO.Compression.ZipFileExtensions]::ExtractToFile($archive.GetEntry($catalog.ap_name), $apPath, $false) }
        finally { $archive.Dispose() }
        $md5 = Invoke-Samloader -File $tool -Arguments @('verify-md5', $apPath)
        if ($md5.exit_code -ne 0) { throw 'La verifica MD5 del pacchetto AP non e riuscita.' }
        $images = @('boot.img.lz4', 'recovery.img.lz4', 'dtbo.img.lz4', 'vbmeta.img.lz4')
        $unpack = Invoke-LocalProcess -File $tar.Source -Arguments (@('-xf', $apPath, '-C', $work) + $images)
        if ($unpack.exit_code -ne 0) { throw 'Non riesco a estrarre le immagini stock dal pacchetto AP.' }
        Remove-Item -LiteralPath $apPath
        $report.ap_md5_verified = $true
        $report.stock_image_files = @($images | ForEach-Object {
            $image = Join-Path $work $_
            @{ name = $_; compressed_bytes = (Get-Item -LiteralPath $image).Length;
               sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $image).Hash.ToLowerInvariant() }
        })
        $report.inspection_inputs_created = $true
        $report | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 -LiteralPath $reportPath
        Copy-Item -LiteralPath $reportPath -Destination (Join-Path $work 'firmware-download-report.json')
        $bundle = Join-Path $Root 'firmware-inspection-inputs.zip'
        if (Test-Path -LiteralPath $bundle) { throw 'Esiste gia firmware-inspection-inputs.zip; conservalo.' }
        [System.IO.Compression.ZipFile]::CreateFromDirectory($work, $bundle)
        Remove-Item -LiteralPath $work -Recurse
        Write-Host 'Controllo preparato. Invia firmware-inspection-inputs.zip in chat.'
        Write-Host 'Conserva sul PC lo ZIP completo dentro firmware: servira per il ripristino.'
        return $true
    } catch {
        $report.error = $_.Exception.Message
        Write-Host ('Errore: ' + $report.error) -ForegroundColor Red
        Write-Host 'Invia firmware-download-report.json in chat.'
        return $false
    } finally {
        $report | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 -LiteralPath $reportPath
    }
}

if ($MyInvocation.InvocationName -ne '.') {
    if (-not (Start-StockDownload $PackageRoot)) { exit 1 }
}
