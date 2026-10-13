# Read-only recovery inventory. No mount, reboot, flash, push or format.
[CmdletBinding()]
param([string]$PackageRoot)
$recoveryCollectorDirectory = [IO.Path]::GetDirectoryName($MyInvocation.MyCommand.Path)
if ([string]::IsNullOrEmpty($PackageRoot)) { $PackageRoot = Join-Path $recoveryCollectorDirectory '..' }
. (Join-Path $recoveryCollectorDirectory 'check-download-mode.ps1')

$script:RecoveryAdbHashes = @{
    'adb.exe' = 'b4a6b455702684652cccf7b46258b29e653538904359a58fd4931cf3ef286b3f'
    'AdbWinApi.dll' = 'c1d653030b4bde65d3e07e4d0b0979e17be56df1436cdd15528630f27808050d'
    'AdbWinUsbApi.dll' = '0710e894d9b40f71a670c13c694079d564c92c1279da382cfe4850983aaebe1b'
    'libwinpthread-1.dll' = 'f2044c755e39efc5d47f47c5a942178dd6d79dc8945bb182dc8753d10e2a4269'
}
$script:RecoveryProperties = @('ro.twrp.version','ro.product.model','ro.product.device','ro.hardware',
    'ro.bootloader','ro.boot.bootloader','ro.crypto.state','ro.crypto.type',
    'ro.boot.vbmeta.device_state','ro.boot.verifiedbootstate','ro.boot.flash.locked','ro.boot.slot_suffix')
$script:RecoverySizes = [ordered]@{
    boot = 57671680; recovery = 67633152; dtb = 8388608; dtbo = 8388608
    vbmeta = 65536; system = 5976883200; vendor = 1153433600; userdata = 119126622208
}
$script:RecoveryQueries = @{
    'version' = @('version')
    'state' = @('-d','get-state')
    'uid' = @('-d','shell','id -u')
    'properties' = @('-d','shell', ('for k in ' + ($script:RecoveryProperties -join ' ') + '; do printf "%s|%s\n" "$k" "$(getprop "$k")"; done'))
    'partitions' = @('-d','shell', 'for p in boot:sda14 recovery:sda15 dtb:sda12 dtbo:sda13 vbmeta:sda23 system:sda25 vendor:sda26 userdata:sda31; do n="${p%%:*}"; b="/dev/block/${p#*:}"; s=$(blockdev --getsize64 "$b" 2>/dev/null); printf "%s|%s|%s\n" "$n" "$b" "$s"; done')
    'mounts' = @('-d','shell','cat /proc/mounts')
    'fstab' = @('-d','shell','cat /etc/recovery.fstab')
    'data-state' = @('-d','shell','twrp get tw_is_encrypted; twrp get tw_is_decrypted; twrp get tw_mount_system_ro')
    'startup-hashes' = @('-d','shell','sha256sum /init.recovery.exynos9820.rc /sbin/nuker.sh')
    'recovery-hash' = @('-d','shell','head -c 57556992 /dev/block/sda15 | sha256sum')
    'vbmeta-hash' = @('-d','shell','head -c 65536 /dev/block/sda23 | sha256sum')
}

function Invoke-RecoveryQuery {
    param([string]$Executable, [string]$Query, [scriptblock]$Runner)
    if (-not $script:RecoveryQueries.ContainsKey($Query)) { throw 'query_not_allowed' }
    $arguments = $script:RecoveryQueries[$Query]
    if ($Runner) { return & $Runner $Executable $arguments $Query }
    return Invoke-DownloadCheckNative $Executable $arguments 45
}

function Invoke-RecoveryInventory {
    param([string]$Root, [scriptblock]$Runner)
    $ErrorActionPreference = 'Stop'
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $Root = [IO.Path]::GetFullPath($Root)
    $directory = Join-Path $Root ('recovery-check-' + [Guid]::NewGuid().ToString('N'))
    [IO.Directory]::CreateDirectory($directory) | Out-Null
    $tools = Join-Path $Root 'platform-tools'
    $exe = Join-Path $tools 'adb.exe'
    $report = [ordered]@{
        schema = 1; collector_version = 1; date_utc = [DateTime]::UtcNow.ToString('o')
        target_model = 'SM-G975F'; expected_firmware = 'G975FXXSGHWC1'; adb_usb_only = $true
        partition_writes = $false; erase_requested = $false; reboot_requested = $false
        mount_changes_requested = $false; recovery_boot_confirmed_by_adb = $false
        ubuntu_touch_boot_verified = $false; success = $false; error = $null
        properties = @{}; partitions = @{}; selected_mounts = @(); twrp_data_state = @{}
        steps = @(); optional_query_failures = @()
    }
    $reason = 'adb_package_invalid'
    try {
        foreach ($name in $script:RecoveryAdbHashes.Keys) {
            if ((Get-FileHash -LiteralPath (Join-Path $tools $name) -Algorithm SHA256).Hash.ToLowerInvariant() -cne $script:RecoveryAdbHashes[$name]) { throw $reason }
        }
        $reason = 'adb_version_invalid'
        $result = Invoke-RecoveryQuery $exe 'version' $Runner
        if ($result.ExitCode -ne 0 -or $result.TimedOut -or $result.Stdout -notmatch 'Version 37\.0\.1') { throw $reason }
        Write-Host 'Controllo del collegamento USB alla recovery...'
        foreach ($query in @('state','uid','properties')) {
            $reason = 'recovery_' + $query + '_unavailable'
            $result = Invoke-RecoveryQuery $exe $query $Runner
            $report.steps += @{ operation = $query; exit_code = $result.ExitCode; timed_out = $result.TimedOut }
            if ($result.ExitCode -ne 0 -or $result.TimedOut) { throw $reason }
            if ($query -eq 'state' -and $result.Stdout.Trim() -cnotin @('device','recovery')) { throw $reason }
            if ($query -eq 'uid' -and $result.Stdout.Trim() -cne '0') { throw $reason }
            if ($query -eq 'properties') {
                foreach ($line in ($result.Stdout -split '\r?\n')) {
                    $fields = $line.Split('|', 2)
                    if ($fields.Count -eq 2 -and $fields[0] -cin $script:RecoveryProperties) {
                        if ($fields[1].Length -gt 256 -or $fields[1] -match '[\x00-\x1f]') { throw $reason }
                        $report.properties[$fields[0]] = $fields[1]
                    }
                }
            }
        }
        $reason = 'wrong_recovery_or_device'
        $props = $report.properties
        if ($props['ro.twrp.version'] -cnotin @('3.7.0_9','3.7.0_9-2') -or $props['ro.product.device'] -cnotin @('beyond2','beyond2lte') -or
            ($props['ro.product.model'] -cnotin @('SM-G975F','SM-G975F/DS') -and
             $props['ro.bootloader'] -cne 'G975FXXSGHWC1' -and $props['ro.boot.bootloader'] -cne 'G975FXXSGHWC1')) { throw $reason }
        $report.recovery_boot_confirmed_by_adb = $true
        Write-Host 'Lettura delle dimensioni delle partizioni...'
        $reason = 'partition_sizes_unavailable'
        $result = Invoke-RecoveryQuery $exe 'partitions' $Runner
        $report.steps += @{ operation = 'partitions'; exit_code = $result.ExitCode; timed_out = $result.TimedOut }
        if ($result.ExitCode -ne 0 -or $result.TimedOut) { throw $reason }
        foreach ($line in ($result.Stdout -split '\r?\n')) {
            if ($line -cmatch '^([a-z]+)\|(/dev/block/sda[0-9]+)\|([0-9]+)$' -and $script:RecoverySizes.Contains($Matches[1])) {
                $report.partitions[$Matches[1]] = @{ block_device = $Matches[2]; bytes = [uint64]$Matches[3] }
            }
        }
        $reason = 'partition_size_mismatch'
        foreach ($name in $script:RecoverySizes.Keys) {
            if (-not $report.partitions.ContainsKey($name) -or $report.partitions[$name].bytes -ne $script:RecoverySizes[$name]) { throw $reason }
        }
        Write-Host 'Verifica in lettura della recovery e di VBMETA installate...'
        foreach ($query in @('startup-hashes','recovery-hash','vbmeta-hash','mounts','fstab','data-state')) {
            $reason = 'recovery_' + $query.Replace('-','_') + '_unavailable'
            $result = Invoke-RecoveryQuery $exe $query $Runner
            $report.steps += @{ operation = $query; exit_code = $result.ExitCode; timed_out = $result.TimedOut }
            if ($result.ExitCode -ne 0 -or $result.TimedOut) {
                if ($query -cin @('fstab','data-state')) { $report.optional_query_failures += $query; continue }
                throw $reason
            }
            switch ($query) {
                'startup-hashes' {
                    $hashes = @{}
                    foreach ($line in ($result.Stdout -split '\r?\n')) {
                        if ($line -cmatch '^([0-9a-f]{64})\s+(/init\.recovery\.exynos9820\.rc|/sbin/nuker\.sh)$') { $hashes[$Matches[2]] = $Matches[1] }
                    }
                    $reason = 'automatic_vendor_mutation_patch_unconfirmed'
                    if ($hashes['/init.recovery.exynos9820.rc'] -cne '4417a4bb677735725dd659d8edb73203cad0ba128740bddcf3d3e45f2a08d0c8' -or
                        $hashes['/sbin/nuker.sh'] -cne '22ccc50125bd5d05f082065b034a7b46da05438528c152a78154d20727392c87') { throw $reason }
                    $report.automatic_vendor_mutation_patch_confirmed = $true
                }
                { $_ -cin @('recovery-hash','vbmeta-hash') } {
                    $reason = 'installed_image_hash_mismatch'
                    if ($result.Stdout.Trim() -cnotmatch '^([0-9a-f]{64})\s+-?$') { throw $reason }
                    $hash = $Matches[1]
                    if ($query -eq 'recovery-hash') {
                        if ($hash -cne 'caecf1ef6c36392739377cfbe7d0c9ce37b255858e6dfd1a5cde2cad7a508b0e') { throw $reason }
                        $report.installed_recovery_sha256 = $hash
                    } else {
                        if ($hash -cne '9cce7c2d752df367292cc17b4e2d21834629360f40521cb1784233b87e3c0025') { throw $reason }
                        $report.installed_vbmeta_sha256 = $hash
                    }
                }
                'mounts' {
                    foreach ($line in ($result.Stdout -split '\r?\n')) {
                        $fields = $line -split ' '
                        if ($fields.Count -ge 4 -and $fields[1] -cin @('/system','/system_root','/vendor','/data','/metadata','/cache','/efs')) {
                            $report.selected_mounts += @{ source = $fields[0]; target = $fields[1]; filesystem = $fields[2]; options = $fields[3] }
                        }
                    }
                }
                'fstab' {
                    $report.recovery_fstab_lines = @($result.Stdout -split '\r?\n' | Where-Object { $_.Trim() -and -not $_.Trim().StartsWith('#') })
                }
                'data-state' {
                    foreach ($line in ($result.Stdout -split '\r?\n')) {
                        if ($line -cmatch '^(tw_is_encrypted|tw_is_decrypted|tw_mount_system_ro) = ([01])$') { $report.twrp_data_state[$Matches[1]] = [int]$Matches[2] }
                    }
                }
            }
        }
        $report.success = $true
        Write-Host 'Controllo completato. Il telefono resta in TWRP.'
    } catch {
        $report.error = $reason
        Write-Host ('Controllo fermato: ' + $reason)
        Write-Host 'Nessuna installazione o cancellazione eseguita.'
        if ($reason -eq 'recovery_state_unavailable') {
            Write-Host 'Lascia TWRP aperta, controlla cavo/porta USB e chiudi altri programmi che usano il telefono.'
        }
    } finally {
        # Selected properties, static recovery fstab and block/mount/hash
        # metadata only. No enumeration, raw stderr, serial/IMEI or PC paths.
        [IO.File]::WriteAllText((Join-Path $directory 'recovery-check-report.json'), ($report | ConvertTo-Json -Depth 10), (New-Object Text.UTF8Encoding($false)))
        $zipPath = Join-Path $Root 'recovery-check-report.zip'
        $index = 1
        while (Test-Path -LiteralPath $zipPath) { $zipPath = Join-Path $Root ('recovery-check-report-' + $index + '.zip'); $index++ }
        [IO.Compression.ZipFile]::CreateFromDirectory($directory, $zipPath, [IO.Compression.CompressionLevel]::Optimal, $false)
        Remove-Item -LiteralPath $directory -Recurse -Force
    }
    Write-Host ('Invia questo file: ' + $zipPath)
    return [pscustomobject]@{ Success = $report.success; ZipPath = $zipPath; Report = $report }
}

if ($MyInvocation.InvocationName -ne '.') {
    try {
        $result = Invoke-RecoveryInventory -Root $PackageRoot
        if ($result.Success) { exit 0 }
        exit 1
    } catch {
        Write-Host 'Impossibile creare il rapporto. Estrai lo ZIP in una cartella scrivibile e riprova.'
        exit 2
    }
}
