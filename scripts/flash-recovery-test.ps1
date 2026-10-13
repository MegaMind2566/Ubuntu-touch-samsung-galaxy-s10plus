# Experimental first recovery test: exactly VBMETA and RECOVERY, no reboot.
[CmdletBinding()]
param([string]$PackageRoot)

$flashScriptDirectory = [IO.Path]::GetDirectoryName($MyInvocation.MyCommand.Path)
if ([string]::IsNullOrEmpty($PackageRoot)) { $PackageRoot = Join-Path $flashScriptDirectory '..' }
. (Join-Path $flashScriptDirectory 'check-download-mode.ps1')

$script:RecoveryTestHash = 'caecf1ef6c36392739377cfbe7d0c9ce37b255858e6dfd1a5cde2cad7a508b0e'
$script:RecoveryTestVbmetaHash = '9cce7c2d752df367292cc17b4e2d21834629360f40521cb1784233b87e3c0025'
$script:RecoveryTestPitHash = 'aa3555ff93ff568186d64aa0e71b6f50bcf2edf26aecec7c6d74410cf4e7b58a'
$script:RecoveryTestPythonHash = '7ca24f26d6e3f463419ee4f537ddd3acd312c38fe45e678cce08572f26a8bd1a'

function Invoke-RecoveryTestWrite {
    param([string]$Executable, [string[]]$Arguments, [string]$RecoveryPath, [string]$VbmetaPath, [scriptblock]$Runner)
    $expected = @('--usb-backend', 'vcom', 'flash', '--partition', 'VBMETA', $VbmetaPath,
                  '--partition', 'RECOVERY', $RecoveryPath, '--no-reboot')
    if ($Arguments.Count -ne $expected.Count) { throw 'write_command_not_allowed' }
    for ($i = 0; $i -lt $expected.Count; $i++) {
        if ($Arguments[$i] -cne $expected[$i]) { throw 'write_command_not_allowed' }
    }
    if ($Runner) { return & $Runner $Executable $Arguments }
    $info = New-Object Diagnostics.ProcessStartInfo
    $info.FileName = $Executable
    $info.Arguments = (($Arguments | ForEach-Object { ConvertTo-DownloadCheckArgument $_ }) -join ' ')
    $info.UseShellExecute = $false
    # Inherit the console for progress. Never timeout/kill an in-flight write.
    $process = New-Object Diagnostics.Process
    $process.StartInfo = $info
    try {
        if (-not $process.Start()) { throw 'flash_start_failed' }
        $process.WaitForExit()
        return [int]$process.ExitCode
    } finally { $process.Dispose() }
}

function Read-RecoveryTestPit {
    param([string]$Path)
    $header = Read-DownloadCheckPitHeader $Path
    if ($header.sha256 -cne $script:RecoveryTestPitHash -or $header.entry_count -ne 41 -or
        $header.size_bytes -ne 8192 -or $header.project_name -cne 'COM_TAR2' -or
        $header.cpu_bootloader_tag -cne 'LSI9820') { throw 'pit_mismatch' }
    $bytes = [IO.File]::ReadAllBytes($Path)
    $targets = @{}
    for ($i = 0; $i -lt $header.entry_count; $i++) {
        $offset = 28 + 132 * $i
        $name = [Text.Encoding]::ASCII.GetString($bytes, $offset + 36, 32).TrimEnd([char]0)
        if ($name -cin @('RECOVERY', 'VBMETA')) {
            if ($targets.ContainsKey($name)) { throw 'pit_target_duplicate' }
            $unitType = [BitConverter]::ToUInt32($bytes, $offset + 4)
            $size = [uint64][BitConverter]::ToUInt32($bytes, $offset + 24) * 4096
            $filename = [Text.Encoding]::ASCII.GetString($bytes, $offset + 68, 32).TrimEnd([char]0)
            if ($unitType -ne 8) { throw 'pit_target_type_invalid' }
            $targets[$name] = @{ size_bytes = $size; flash_filename = $filename }
        }
    }
    if ($targets.Count -ne 2 -or $targets.RECOVERY.size_bytes -ne 67633152 -or
        $targets.VBMETA.size_bytes -ne 65536 -or $targets.RECOVERY.flash_filename -cne 'recovery.img' -or
        $targets.VBMETA.flash_filename -cne 'vbmeta.img') { throw 'pit_target_layout_invalid' }
    return $header
}

function Invoke-RecoveryTest {
    param([string]$Root, [scriptblock]$ReadRunner, [scriptblock]$WriteRunner, [scriptblock]$PreflightRunner)
    $ErrorActionPreference = 'Stop'
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $Root = [IO.Path]::GetFullPath($Root)
    $runDirectory = Join-Path $Root ('recovery-test-' + [Guid]::NewGuid().ToString('N'))
    [IO.Directory]::CreateDirectory($runDirectory) | Out-Null
    $pitPath = Join-Path $runDirectory 'beyond2lte.pit'
    $privatePath = Join-Path $runDirectory 'private-file-check.json'
    $exe = Join-Path $Root 'tools\samloader\samloader.exe'
    $python = Join-Path $Root 'tools\python\python.exe'
    $locks = New-Object 'System.Collections.Generic.List[System.IO.FileStream]'
    $report = [ordered]@{
        schema = 1; test_tool_version = 1; date_utc = [DateTime]::UtcNow.ToString('o')
        model = 'SM-G975F'; pda = 'G975FXXSGHWC1'; detected_model = $null
        backup_verified = $false; local_files_verified = $false; pit_verified = $false
        target_partitions = @('VBMETA', 'RECOVERY'); write_attempted = $false
        flash_tool_succeeded = $false; flash_exit_code = $null; reboot_requested = $false
        erase_requested = $false; recovery_boot_verified = $false; ubuntu_touch_boot_verified = $false
        success = $false; error = $null; steps = @()
    }
    $reason = 'package_dependencies_invalid'
    try {
        if ((Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash.ToLowerInvariant() -cne $script:DownloadCheckExeHash -or
            (Get-FileHash -LiteralPath $python -Algorithm SHA256).Hash.ToLowerInvariant() -cne $script:RecoveryTestPythonHash) { throw $reason }
        $reason = 'local_verification_failed'
        $statePath = Join-Path $Root 'recovery-local-state.json'
        if ((Get-Item -LiteralPath $statePath).Length -gt 131072) { throw $reason }
        $state = [IO.File]::ReadAllText($statePath) | ConvertFrom-Json
        $parent = [IO.Path]::GetFullPath([string]$state.prepared_directory)
        if ([IO.Path]::GetDirectoryName($parent).TrimEnd('\') -ine $Root.TrimEnd('\') -or
            [IO.Path]::GetFileName($parent) -notmatch '^prepared-recovery-[a-f0-9]{32}$') { throw $reason }
        $recoveryPath = Join-Path $parent 'recovery-test.img'
        $vbmetaPath = Join-Path $parent 'vbmeta-test.img'
        $stockPath = [IO.Path]::GetFullPath([string]$state.stock_firmware_path)
        # Lock inputs before hashing and keep them locked until the native
        # flash completes. The independent verifier must return these paths.
        foreach ($path in @($recoveryPath, $vbmetaPath, $stockPath, $exe, $python, $statePath)) {
            $locks.Add([IO.File]::Open($path, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read))
        }
        Write-Host 'Controllo dei file preparati e del firmware di ripristino...'
        if ($PreflightRunner) { $files = & $PreflightRunner $Root }
        else {
            & $python -I (Join-Path $Root 'scripts\verify_recovery_test.py') --root $Root --output $privatePath | ForEach-Object { Write-Host $_ }
            $preflightCode = $LASTEXITCODE
            if (-not (Test-Path -LiteralPath $privatePath)) { throw $reason }
            $files = [IO.File]::ReadAllText($privatePath) | ConvertFrom-Json
            if ($preflightCode -ne 0) {
                if ([string]$files.error -match '^[a-z_]{1,80}$') { $reason = [string]$files.error }
                throw $reason
            }
        }
        if ($files.success -ne $true -or $files.backup_verified -ne $true) { throw $reason }
        if ([IO.Path]::GetFullPath([string]$files.recovery_path) -ine $recoveryPath -or
            [IO.Path]::GetFullPath([string]$files.vbmeta_path) -ine $vbmetaPath -or
            [IO.Path]::GetFullPath([string]$files.stock_firmware_path) -ine $stockPath) { throw $reason }
        $reason = 'verified_files_changed'
        if ($locks[0].Length -ne 57556992 -or $locks[1].Length -ne 65536 -or $locks[2].Length -ne 6364940601 -or
            (Get-FileHash -LiteralPath $recoveryPath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $script:RecoveryTestHash -or
            (Get-FileHash -LiteralPath $vbmetaPath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $script:RecoveryTestVbmetaHash -or
            (Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash.ToLowerInvariant() -cne $script:DownloadCheckExeHash -or
            (Get-FileHash -LiteralPath $python -Algorithm SHA256).Hash.ToLowerInvariant() -cne $script:RecoveryTestPythonHash) { throw $reason }
        $report.backup_verified = $true
        $report.local_files_verified = $true
        $report.recovery_sha256 = $script:RecoveryTestHash
        $report.vbmeta_sha256 = $script:RecoveryTestVbmetaHash
        $reason = 'version_failed'
        $result = Invoke-DownloadCheckCommand $exe @('--version') $pitPath 15 $ReadRunner
        $report.steps += @{ operation = 'version'; exit_code = $result.ExitCode; timed_out = $result.TimedOut }
        if ($result.TimedOut -or $result.ExitCode -ne 0 -or $result.Stdout.Trim() -cne 'samloader 2.2.0') { throw $reason }
        $reason = 'usb_detection_failed'
        Write-Host 'Controllo del modello tramite USB...'
        $result = Invoke-DownloadCheckCommand $exe @('--usb-backend', 'vcom', 'detect', '--json') $pitPath 30 $ReadRunner
        $report.steps += @{ operation = 'detect'; exit_code = $result.ExitCode; timed_out = $result.TimedOut }
        if ($result.TimedOut -or $result.ExitCode -ne 0) { throw $reason }
        $reason = 'usb_response_invalid'
        $device = $result.Stdout | ConvertFrom-Json
        $reason = 'model_not_confirmed'
        $model = ([string]$device.modelName).Trim()
        if ($model -cnotin @('SM-G975F', 'SM-G975F/DS')) { throw $reason }
        $report.detected_model = $model
        # Never retain detect stdout/stderr, serial numbers or arbitrary errors.
        $reason = 'pit_read_failed'
        Write-Host 'Ricontrollo della tabella delle partizioni...'
        $result = Invoke-DownloadCheckCommand $exe @('--usb-backend', 'vcom', 'dump-pit', '--output', $pitPath, '--no-reboot') $pitPath 90 $ReadRunner
        $report.steps += @{ operation = 'dump-pit'; exit_code = $result.ExitCode; timed_out = $result.TimedOut }
        if ($result.TimedOut -or $result.ExitCode -ne 0) { throw $reason }
        $reason = 'pit_mismatch'
        $report.pit = Read-RecoveryTestPit $pitPath
        $report.pit_verified = $true
        Write-Host ''
        Write-Host 'Controlli superati. Scrittura di VBMETA e RECOVERY.'
        Write-Host 'Non scollegare il cavo e non chiudere questa finestra durante la scrittura.'
        $reason = 'flash_failed'
        $arguments = @('--usb-backend', 'vcom', 'flash', '--partition', 'VBMETA', $vbmetaPath,
                       '--partition', 'RECOVERY', $recoveryPath, '--no-reboot')
        $report.write_attempted = $true
        $code = Invoke-RecoveryTestWrite $exe $arguments $recoveryPath $vbmetaPath $WriteRunner
        $report.flash_exit_code = $code
        if ($code -ne 0) { throw $reason }
        $report.flash_tool_succeeded = $true
        $report.success = $true
        Write-Host ''
        Write-Host 'SCRITTURA COMPLETATA. Il telefono resta in Download Mode.'
        Write-Host 'Avvia subito la recovery, mantenendo il cavo USB collegato al PC:'
        Write-Host '1. Volume Giu + Power fino allo schermo nero (circa 8-10 secondi).'
        Write-Host '2. Appena diventa nero, passa subito a Volume Su + Bixby + Power.'
        Write-Host '3. Al logo Samsung rilascia Power e Bixby; tieni Volume Su fino alla recovery.'
        Write-Host 'In TWRP scegli Keep Read Only. Se chiede la password, premi Cancel.'
        Write-Host 'Per questo test non usare Wipe, Format Data o Reboot System.'
    } catch {
        $report.error = $reason
        Write-Host ('Operazione fermata: ' + $reason)
        if ($report.write_attempted) {
            Write-Host 'La scrittura potrebbe essere parziale. Lascia il telefono in Download Mode e invia il rapporto.'
        } else {
            Write-Host 'Nessuna scrittura avviata. Invia il rapporto per il controllo.'
        }
    } finally {
        foreach ($lock in $locks) { $lock.Dispose() }
        # Only sanitized JSON goes into the upload. PC paths and raw USB output
        # are discarded; no PIT or images are included.
        foreach ($path in @($privatePath, $pitPath)) {
            if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Force }
        }
        [IO.File]::WriteAllText((Join-Path $runDirectory 'recovery-test-report.json'),
            ($report | ConvertTo-Json -Depth 8), (New-Object Text.UTF8Encoding($false)))
        $zipPath = Join-Path $Root 'recovery-test-report.zip'
        $index = 1
        while (Test-Path -LiteralPath $zipPath) {
            $zipPath = Join-Path $Root ('recovery-test-report-' + $index + '.zip'); $index++
        }
        [IO.Compression.ZipFile]::CreateFromDirectory($runDirectory, $zipPath, [IO.Compression.CompressionLevel]::Optimal, $false)
        Remove-Item -LiteralPath $runDirectory -Recurse -Force
    }
    Write-Host ('Invia questo rapporto e una foto della schermata del telefono: ' + $zipPath)
    return [pscustomobject]@{ Success = $report.success; Report = $report; ZipPath = $zipPath }
}

if ($MyInvocation.InvocationName -ne '.') {
    try {
        $result = Invoke-RecoveryTest -Root $PackageRoot
        if ($result.Success) { exit 0 }
        exit 1
    } catch {
        Write-Host 'Impossibile creare il rapporto. Estrai il pacchetto nella cartella della preparazione e riprova.'
        exit 2
    }
}
