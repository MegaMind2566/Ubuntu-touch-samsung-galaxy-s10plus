$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression.FileSystem
. (Join-Path $PSScriptRoot '..\scripts\check-recovery.ps1')
$checkTestRoot = Join-Path ([IO.Path]::GetTempPath()) ('S10 TWRP check ' + [Guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory($checkTestRoot) | Out-Null
$script:RecoveryReadMode = ''
$script:RecoveryReadCalls = @()

function Assert-RecoveryRead {
    param([bool]$Condition, [string]$Description)
    if (-not $Condition) { throw ('FAIL: ' + $Description) }
}

$readFixture = {
    param([string]$Executable, [string[]]$Arguments, [string]$Query)
    $script:RecoveryReadCalls += $Query
    $result = [pscustomobject]@{ ExitCode = 0; TimedOut = $false; Stdout = ''; Stderr = 'PRIVATE-ADB-SERIAL' }
    switch ($Query) {
        'version' { $result.Stdout = 'Android Debug Bridge version 1.0.41' + "`nVersion 37.0.1-TEST" }
        'state' {
            $result.Stdout = 'recovery'
            if ($script:RecoveryReadMode -eq 'no-device') { $result.ExitCode = 1 }
            if ($script:RecoveryReadMode -eq 'timeout') { $result.TimedOut = $true }
        }
        'uid' { $result.Stdout = '0'; if ($script:RecoveryReadMode -eq 'uid') { $result.Stdout = '2000' } }
        'properties' {
            $version = '3.7.0_9-2'; $model = 'SM-G975F'; $device = 'beyond2lte'
            if ($script:RecoveryReadMode -eq 'version-base') { $version = '3.7.0_9' }
            if ($script:RecoveryReadMode -eq 'android') { $version = '' }
            if ($script:RecoveryReadMode -eq 'model') { $model = 'SM-G975U'; $device = 'beyond2q' }
            $result.Stdout = 'ro.twrp.version|' + $version + "`nro.product.model|" + $model + "`nro.product.device|" + $device
            $result.Stdout += "`nro.serialno|PRIVATE-ADB-SERIAL`nro.crypto.state|encrypted`nro.crypto.type|file"
        }
        'partitions' {
            $blocks = @{boot='sda14';recovery='sda15';dtb='sda12';dtbo='sda13';vbmeta='sda23';system='sda25';vendor='sda26';userdata='sda31'}
            foreach ($name in $script:RecoverySizes.Keys) {
                $size = $script:RecoverySizes[$name]
                if ($script:RecoveryReadMode -eq 'size' -and $name -eq 'vbmeta') { $size = 131072 }
                $result.Stdout += $name + '|/dev/block/' + $blocks[$name] + '|' + $size + "`n"
            }
        }
        'startup-hashes' {
            $result.Stdout = "4417a4bb677735725dd659d8edb73203cad0ba128740bddcf3d3e45f2a08d0c8  /init.recovery.exynos9820.rc`n22ccc50125bd5d05f082065b034a7b46da05438528c152a78154d20727392c87  /sbin/nuker.sh"
            if ($script:RecoveryReadMode -eq 'unpatched') { $result.Stdout = 'unmodified startup' }
        }
        'recovery-hash' {
            $result.Stdout = 'caecf1ef6c36392739377cfbe7d0c9ce37b255858e6dfd1a5cde2cad7a508b0e  -'
            if ($script:RecoveryReadMode -eq 'hash') { $result.Stdout = ('0' * 64) + '  -' }
        }
        'vbmeta-hash' { $result.Stdout = '9cce7c2d752df367292cc17b4e2d21834629360f40521cb1784233b87e3c0025  -' }
        'mounts' { $result.Stdout = "/dev/block/sda26 /vendor ext4 ro,relatime 0 0`n/dev/block/dm-0 /data ext4 rw,relatime 0 0`n/dev/block/ignored /private ext4 rw 0 0" }
        'fstab' { $result.Stdout = '/data ext4 /dev/block/sda31 flags=fileencryption=ice' }
        'data-state' {
            $result.Stdout = "tw_is_encrypted = 1`ntw_is_decrypted = 0`ntw_mount_system_ro = 1"
            if ($script:RecoveryReadMode -eq 'optional') { $result.ExitCode = 1 }
        }
        default { throw 'unexpected_fixture_query' }
    }
    return $result
}

function Invoke-RecoveryReadCase {
    param([string]$Mode, [bool]$Success, [string]$ErrorCode)
    $script:RecoveryReadMode = $Mode; $script:RecoveryReadCalls = @()
    $result = Invoke-RecoveryInventory $script:RecoveryReadPackage $readFixture
    Assert-RecoveryRead ($result.Success -eq $Success -and ([string]$result.Report.error) -ceq ([string]$ErrorCode)) ($Mode + ': result')
    Assert-RecoveryRead (-not $result.Report.partition_writes -and -not $result.Report.erase_requested -and
        -not $result.Report.reboot_requested -and -not $result.Report.mount_changes_requested) 'read-only result'
    Assert-RecoveryRead (-not $result.Report.ubuntu_touch_boot_verified) 'no Ubuntu Touch boot claim'
    $zip = [IO.Compression.ZipFile]::OpenRead($result.ZipPath)
    try {
        Assert-RecoveryRead ($zip.Entries.Count -eq 1) 'report only'
        $reader = New-Object IO.StreamReader($zip.Entries[0].Open())
        try { $json = $reader.ReadToEnd() } finally { $reader.Dispose() }
        Assert-RecoveryRead ($json -notmatch 'PRIVATE-ADB-SERIAL|ro.serialno|/private|[A-Z]:\\') 'only selected metadata, without identifiers or paths'
    } finally { $zip.Dispose() }
    return $result
}

try {
    $script:RecoveryReadPackage = Join-Path $checkTestRoot 'package with spaces'
    [IO.Compression.ZipFile]::ExtractToDirectory([IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\out\UbuntuTouch-S10plus-controllo-recovery-Windows.zip')), $script:RecoveryReadPackage)
    $exe = Join-Path $script:RecoveryReadPackage 'platform-tools\adb.exe'
    $version = Invoke-DownloadCheckNative $exe @('version') 15
    Assert-RecoveryRead ($version.ExitCode -eq 0 -and $version.Stdout -match 'Version 37\.0\.1') 'real publisher executable and dependencies'
    $result = Invoke-RecoveryReadCase 'success' $true $null
    Assert-RecoveryRead ($result.Report.twrp_data_state.tw_is_encrypted -eq 1 -and
        $result.Report.twrp_data_state.tw_is_decrypted -eq 0 -and $result.Report.selected_mounts.Count -eq 2) 'encryption/mount metadata'
    Assert-RecoveryRead ($result.Report.installed_recovery_sha256 -eq 'caecf1ef6c36392739377cfbe7d0c9ce37b255858e6dfd1a5cde2cad7a508b0e' -and
        $result.Report.installed_vbmeta_sha256 -eq '9cce7c2d752df367292cc17b4e2d21834629360f40521cb1784233b87e3c0025') 'both installed image hashes'
    $null = Invoke-RecoveryReadCase 'version-base' $true $null
    $null = Invoke-RecoveryReadCase 'optional' $true $null
    foreach ($case in @(
        @('no-device','recovery_state_unavailable'), @('timeout','recovery_state_unavailable'),
        @('uid','recovery_uid_unavailable'), @('android','wrong_recovery_or_device'),
        @('model','wrong_recovery_or_device'), @('size','partition_size_mismatch'),
        @('unpatched','automatic_vendor_mutation_patch_unconfirmed'), @('hash','installed_image_hash_mismatch')
    )) { $null = Invoke-RecoveryReadCase $case[0] $false $case[1] }
    foreach ($query in @('flash','push','format','mount','reboot','shell')) {
        $blocked = $false
        try { $null = Invoke-RecoveryQuery $exe $query $readFixture } catch { $blocked = $_.Exception.Message -eq 'query_not_allowed' }
        Assert-RecoveryRead $blocked 'non-read-only query rejected'
    }
    # A changed bundled DLL must stop before any ADB/USB request, including
    # the native -File/CMD launcher. This exercises an actual host failure.
    [IO.File]::WriteAllText((Join-Path $script:RecoveryReadPackage 'platform-tools\AdbWinApi.dll'), 'invalid dependency')
    $null = Invoke-RecoveryReadCase 'package' $false 'adb_package_invalid'
    Assert-RecoveryRead ($script:RecoveryReadCalls.Count -eq 0) 'invalid dependency stops before USB'
    $launcher = Join-Path $script:RecoveryReadPackage 'CONTROLLA-RECOVERY.cmd'
    $info = New-Object Diagnostics.ProcessStartInfo
    $info.FileName = $env:ComSpec; $info.Arguments = '/d /s /c ""' + $launcher + '" <nul"'
    $info.UseShellExecute = $false; $info.RedirectStandardOutput = $true; $info.RedirectStandardError = $true
    $process = New-Object Diagnostics.Process; $process.StartInfo = $info
    try {
        Assert-RecoveryRead ($process.Start()) 'native CMD starts'
        $stdout = $process.StandardOutput.ReadToEndAsync(); $stderr = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit(60000)) { $process.Kill(); throw 'launcher_timeout' }
        $process.WaitForExit()
        Assert-RecoveryRead ($process.ExitCode -eq 1) ('native failure report: ' + $stdout.GetAwaiter().GetResult() + $stderr.GetAwaiter().GetResult())
    } finally { $process.Dispose() }
    Write-Host 'PASS: real official ADB, 12 recovery inventory scenarios, fixed read-only queries, image/patch/size guards, encryption metadata, sanitized reports and native CMD with spaces. USB hardware access is mocked in CI.'
} finally { Remove-Item -LiteralPath $checkTestRoot -Recurse -Force }
