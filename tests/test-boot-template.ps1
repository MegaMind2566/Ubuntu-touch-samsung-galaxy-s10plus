# Windows 5.1 guard tests using the actual original and corrected BOOT images.
# Test callbacks simulate the phone only. No USB command is sent by this test.
$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.IO.Compression.FileSystem
$script:BootTestRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\out\BOOT handoff with spaces'))
. (Join-Path $script:BootTestRoot 'scripts\install-boot-update-2.ps1')
$script:BootTestInventory=[IO.File]::ReadAllText((Join-Path $PSScriptRoot '..\docs\evidence\recovery-check-2026-10-13.json')) | ConvertFrom-Json
$script:BootTestCase='';$script:BootTestMode='Apply';$script:BootTestOperations=@();$script:BootTestInventories=0;$script:BootTestCurrentReads=0

function Assert-BootTest {
    param([bool]$Condition,[string]$Description)
    if (-not $Condition) { throw ('FAIL: '+$Description) }
}
$bootPreflight={
    param([string]$Root)
    $state=[IO.File]::ReadAllText((Join-Path $Root 'ubuntu-local-state.json')) | ConvertFrom-Json
    return [pscustomobject]@{success=$true;backup_verified=($script:BootTestCase -ne 'backup')
        boot_path=(Join-Path $state.prepared_directory 'boot.img');system_path=(Join-Path $state.prepared_directory 'system.img');stock_firmware_path=$state.stock_firmware_path}
}
$bootInventory={
    param([string]$Root)
    $script:BootTestInventories++
    $report=($script:BootTestInventory.recovery_check | ConvertTo-Json -Depth 12) | ConvertFrom-Json
    if ($script:BootTestCase -eq 'mounted-system' -or ($script:BootTestCase -eq 'second-mounted' -and $script:BootTestInventories -eq 2)) {
        $report.selected_mounts+=@{target='/system_root'}
    }
    if ($script:BootTestCase -eq 'mounted-vendor') { $report.selected_mounts+=@{target='/vendor'} }
    if ($script:BootTestCase -eq 'encrypted-data') { $report.selected_mounts[0].source='/dev/block/dm-0' }
    $success=($script:BootTestCase -ne 'inventory' -and -not ($script:BootTestCase -eq 'second-inventory' -and $script:BootTestInventories -eq 2))
    return [pscustomobject]@{Success=$success;Report=$report}
}
$bootImageVerifier={
    param([string]$Root,[string]$Image)
    & (Join-Path $Root 'tools\python\python.exe') -I (Join-Path $Root 'scripts\verify_boot_update_2.py') --image $Image
    if ($LASTEXITCODE -ne 0) { throw 'actual_updated_image_failed' }
}
$bootActions={
    param([string]$Executable,[string[]]$Arguments,[string]$Action,[uint64]$Bytes)
    $script:BootTestOperations+=$Action
    Assert-BootTest ($Arguments[0] -ceq '-d') 'all remote actions select USB only'
    Assert-BootTest (($Arguments -join ' ') -notmatch 'sda25|sda26|mkfs|format|reboot|wipe') 'no SYSTEM/VENDOR write, erase or reboot command'
    $state=[IO.File]::ReadAllText((Join-Path $script:BootTestRoot 'ubuntu-local-state.json')) | ConvertFrom-Json
    $stage=''
    if (($Arguments -join ' ') -match '/data/ubuntu-touch-boot-update-[a-f0-9]{32}') { $stage=$Matches[0] }
    $previous=$script:BootPreviousHash;$expected=$script:BootUpdateHash
    if ($script:BootTestMode -ceq 'Restore') { $previous=$script:BootUpdateHash;$expected=$script:BootPreviousHash }
    $result=[pscustomobject]@{ExitCode=0;Stdout='';Stderr=''}
    switch ($Action) {
        'read-current' {
            $script:BootTestCurrentReads++
            $result.Stdout=$previous+'  -'
            if ($script:BootTestCase -eq 'current-boot' -or ($script:BootTestCase -eq 'second-boot' -and $script:BootTestCurrentReads -eq 2)) { $result.Stdout=('0'*64)+'  -' }
        }
        'data-space' {
            $free=113000000;if ($script:BootTestCase -eq 'space') { $free=1024 }
            $result.Stdout="Filesystem 1K-blocks Used Available Use% Mounted on`n/dev/block/sda31 114000000 1000000 $free 1% /data`n"
        }
        'push-boot' {
            $input=Join-Path $script:BootTestRoot 'boot-update-2\boot.img'
            if ($script:BootTestMode -ceq 'Restore') { $input=Join-Path $script:BootTestRoot 'boot-update-1\boot.img' }
            Assert-BootTest ($Arguments.Count -eq 5 -and $Arguments[1] -ceq 'push' -and $Arguments[2] -ceq '-Z' -and
                $Arguments[3] -ceq $input -and $Arguments[4] -ceq ($stage+'/boot.img')) 'only the selected pinned BOOT is staged'
            if ($script:BootTestCase -eq 'transfer') { $result.ExitCode=1 }
        }
        'size-boot' {
            $size=$Bytes;if ($script:BootTestCase -eq 'size') { $size=1024 }
            $result.Stdout=$stage+'/boot.img '+$size+' 0 81a4 0 0'
        }
        'hash-boot' {
            $result.Stdout=$expected+'  '+$stage+'/boot.img'
            if ($script:BootTestCase -eq 'hash') { $result.Stdout=('0'*64)+'  '+$stage+'/boot.img' }
        }
        'readback-boot' {
            $result.Stdout=$expected+'  -'
            if ($script:BootTestCase -eq 'readback') { $result.Stdout=('0'*64)+'  -' }
            if ($script:BootTestCase -eq 'readback-usb') { $result.ExitCode=1 }
        }
        'stage-cleanup' {
            Assert-BootTest ($Arguments[2] -ceq "/sbin/busybox rm -f '$stage/boot.img' && /sbin/busybox rmdir '$stage'") 'cleanup targets one owned temporary file and its empty folder'
        }
        'write-boot' {
            Assert-BootTest ($Arguments.Count -eq 3 -and $Arguments[1] -ceq 'shell' -and
                $Arguments[2] -ceq "/sbin/busybox dd if='$stage/boot.img' of=/dev/block/sda14 bs=4194304 && /sbin/busybox sync") 'exact physical BOOT target and owned input only'
            Assert-BootTest ($script:BootTestInventories -eq 2 -and $script:BootTestCurrentReads -eq 2 -and $script:BootTestOperations -contains 'hash-boot') 'recovery and unchanged current BOOT rechecked after transfer'
            $checkpoint=Join-Path $script:BootTestRoot ('ubuntu-boot-update-2-'+$script:BootTestMode.ToLowerInvariant()+'-state.json')
            Assert-BootTest (Test-Path -LiteralPath $checkpoint) 'write-intent checkpoint precedes raw write'
            $saved=[IO.File]::ReadAllText($checkpoint) | ConvertFrom-Json
            Assert-BootTest ($saved.write_started -and -not $saved.success) 'checkpoint remains incomplete during write'
            foreach ($path in @((Join-Path $state.prepared_directory 'boot.img'),(Join-Path $state.prepared_directory 'system.img'),
                    $state.stock_firmware_path,(Join-Path $script:BootTestRoot 'boot-update-2\boot.img'),
                    (Join-Path $script:BootTestRoot 'boot-update-1\boot.img'),
                    (Join-Path $script:BootTestRoot 'ubuntu-local-state.json'),(Join-Path $script:BootTestRoot 'tools\python\python.exe'),$Executable)) {
                $reader=[IO.File]::OpenRead($path);$reader.Dispose();$blocked=$false
                try { $writer=[IO.File]::Open($path,[IO.FileMode]::Open,[IO.FileAccess]::Write,[IO.FileShare]::ReadWrite);$writer.Dispose() }
                catch [IO.IOException] { $blocked=$true }
                Assert-BootTest $blocked 'inputs, backup, state and native tools stay immutable during write'
            }
            if ($script:BootTestCase -eq 'write') { $result.ExitCode=1;$result.Stderr='Simulated failure '+$state.stock_firmware_path }
        }
    }
    return $result
}

function Invoke-BootFixture {
    param([string]$Case,[string]$ExpectedError,[bool]$Write,[string]$Mode='Apply')
    $script:BootTestCase=$Case;$script:BootTestMode=$Mode;$script:BootTestOperations=@();$script:BootTestInventories=0;$script:BootTestCurrentReads=0
    $checkpoint=Join-Path $script:BootTestRoot ('ubuntu-boot-update-2-'+$Mode.ToLowerInvariant()+'-state.json')
    if ($Case -ne 'retry' -and (Test-Path -LiteralPath $checkpoint)) { Remove-Item -LiteralPath $checkpoint }
    $result=Invoke-BootUpdateInstallation -Root $script:BootTestRoot -UpdateMode $Mode -PreflightRunner $bootPreflight -InventoryRunner $bootInventory -ImageVerifier $bootImageVerifier -ActionRunner $bootActions
    Assert-BootTest ($result -is [pscustomobject] -and $result -isnot [array]) 'diagnostic output does not contaminate the returned result'
    Assert-BootTest ($result.Success -eq ($Case -eq 'success')) ($Mode+'/'+$Case+': success')
    Assert-BootTest (([string]$result.Report.error) -ceq ([string]$ExpectedError)) ($Mode+'/'+$Case+': error stage')
    Assert-BootTest ($result.Report.boot_write_requested -eq $Write) ($Mode+'/'+$Case+': write gate')
    Assert-BootTest ($result.Report.target_partitions.Count -eq 1 -and $result.Report.target_partitions[0] -ceq 'BOOT' -and
        -not $result.Report.system_write_requested -and -not $result.Report.vendor_write_requested -and -not $result.Report.data_format_requested -and
        -not $result.Report.repartition_requested -and -not $result.Report.automatic_reboot_requested -and -not $result.Report.ubuntu_touch_boot_verified) 'BOOT only, no reset and no hardware-boot claim'
    if ($Case -eq 'success') {
        Assert-BootTest ($result.Report.boot_readback_verified -and $result.Report.staging_cleanup_succeeded) 'physical prefix verified before success'
        Assert-BootTest (($script:BootTestOperations | Where-Object { $_ -like 'write-*' }) -join '|' -ceq 'write-boot') 'one BOOT write only'
    }
    if ($Write -and -not $result.Success) {
        Assert-BootTest ($script:BootTestOperations -notcontains 'stage-cleanup') 'possible partial write preserves evidence and never retries'
        Assert-BootTest ($result.Report.partition_progress -ceq 'boot_unknown' -and -not $result.Report.boot_readback_verified) 'failed readback cannot be declared successful'
    }
    if (-not $Write -and $script:BootTestOperations -contains 'stage-create') { Assert-BootTest $result.Report.staging_cleanup_succeeded 'prewrite failures clean the owned stage only' }
    if ($Case -eq 'retry') { Assert-BootTest ($script:BootTestOperations.Count -eq 0 -and $script:BootTestInventories -eq 0) 'repeat execution stops before USB' }
    $zip=[IO.Compression.ZipFile]::OpenRead($result.ZipPath)
    try {
        Assert-BootTest ($zip.Entries.Count -eq 1) 'only sanitized report is shared'
        $reader=New-Object IO.StreamReader($zip.Entries[0].Open());try { $reportText=$reader.ReadToEnd() } finally { $reader.Dispose() }
        Assert-BootTest ($reportText -notmatch 'stock_firmware_path|serialNumber|aaaaaaaaaaaaaaaa|'+[regex]::Escape($script:BootTestRoot)) 'no serial, filesystem UUID or PC paths in report'
    } finally { $zip.Dispose() }
    return $result
}

function Invoke-BootNativeEntry {
    param([string]$Cmd)
    $info=New-Object Diagnostics.ProcessStartInfo;$info.FileName=$env:ComSpec
    $info.Arguments='/d /s /c ""'+(Join-Path $script:BootTestRoot $Cmd)+'" <nul"'
    $info.UseShellExecute=$false;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
    $process=New-Object Diagnostics.Process;$process.StartInfo=$info
    try {
        Assert-BootTest ($process.Start()) 'actual native CMD starts'
        $out=$process.StandardOutput.ReadToEndAsync();$err=$process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit(60000)) { $process.Kill();throw 'test_entry_point_timeout' };$process.WaitForExit()
        $output=$out.GetAwaiter().GetResult()+$err.GetAwaiter().GetResult()
        Assert-BootTest ($process.ExitCode -eq 1 -and $output -match 'previous_boot_update_needs_review') ('native CMD mode/root/exit handling: '+$output)
    } finally { $process.Dispose() }
}

try {
    Assert-BootTest ($PSVersionTable.PSVersion.Major -eq 5 -and $PSVersionTable.PSVersion.Minor -eq 1) 'native Windows PowerShell 5.1'
    $prepared=Join-Path $script:BootTestRoot ('prepared-ubuntu-'+'a'*32);[IO.Directory]::CreateDirectory($prepared) | Out-Null
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot '..\out\boot-baseline\boot.img') -Destination (Join-Path $prepared 'boot.img')
    $stock=Join-Path $script:BootTestRoot 'fixture-stock.zip';$system=Join-Path $prepared 'system.img'
    foreach ($fixture in @(@($stock,[int64]6364940601),@($system,[int64]5368709120))) {
        [IO.File]::WriteAllBytes($fixture[0],@());& fsutil.exe sparse setflag $fixture[0] | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'sparse_fixture_failed' }
        $stream=[IO.File]::OpenWrite($fixture[0]);try { $stream.SetLength($fixture[1]) } finally { $stream.Dispose() }
    }
    # Sparse SYSTEM/stock substitutes are accepted only by the injected test
    # preflight. Production still hashes the actual original SYSTEM/full stock.
    $legacy=Join-Path $script:BootTestRoot 'ubuntu-boot-update-apply-state.json'
    [IO.File]::WriteAllText($legacy,'{"write_started":true,"success":true}')
    $legacyHash=(Get-FileHash -LiteralPath $legacy -Algorithm SHA256).Hash
    $state=@{schema=1;model='SM-G975F';pda='G975FXXSGHWC1';success=$true;backup_verified=$true;prepared_directory=$prepared;stock_firmware_path=$stock}
    [IO.File]::WriteAllText((Join-Path $script:BootTestRoot 'ubuntu-local-state.json'),($state | ConvertTo-Json))
    $null=Invoke-BootFixture 'success' $null $true
    $null=Invoke-BootFixture 'retry' 'previous_boot_update_needs_review' $false
    $null=Invoke-BootFixture 'success' $null $true 'Restore'
    $null=Invoke-BootFixture 'retry' 'previous_boot_update_needs_review' $false 'Restore'
    foreach ($case in @(
        @('backup','image_or_backup_verification_failed',$false),@('inventory','recovery_preflight_failed',$false),
        @('mounted-system','recovery_preflight_failed',$false),@('mounted-vendor','recovery_preflight_failed',$false),
        @('encrypted-data','recovery_preflight_failed',$false),@('current-boot','current_boot_not_expected',$false),
        @('space','insufficient_staging_space',$false),@('transfer','staging_transfer_failed',$false),
        @('size','staged_boot_verification_failed',$false),@('hash','staged_boot_verification_failed',$false),
        @('second-inventory','prewrite_recovery_changed',$false),@('second-mounted','prewrite_recovery_changed',$false),
        @('second-boot','prewrite_recovery_changed',$false),@('write','boot_write_failed',$true),
        @('readback','boot_readback_failed',$true),@('readback-usb','boot_readback_failed',$true)
    )) { $null=Invoke-BootFixture $case[0] $case[1] $case[2] }
    $null=Invoke-BootFixture 'current-boot' 'current_boot_not_expected' $false 'Restore'
    $null=Invoke-BootFixture 'readback' 'boot_readback_failed' $true 'Restore'
    foreach ($change in @(@('previous','boot-update-1\boot.img','previous_boot_image_mismatch'),@('new','boot-update-2\boot.img','updated_boot_mismatch'))) {
        $changed=Join-Path $script:BootTestRoot $change[1]
        $stream=[IO.File]::Open($changed,[IO.FileMode]::Open,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
        try { $savedByte=$stream.ReadByte();$stream.Position=0;$stream.WriteByte($savedByte -bxor 1) } finally { $stream.Dispose() }
        try {
            $null=Invoke-BootFixture $change[0] $change[2] $false
            Assert-BootTest ($script:BootTestOperations.Count -eq 0 -and $script:BootTestInventories -eq 0) 'changed local predecessor/new BOOT stops before USB'
        } finally {
            $stream=[IO.File]::Open($changed,[IO.FileMode]::Open,[IO.FileAccess]::Write,[IO.FileShare]::None)
            try { $stream.WriteByte($savedByte) } finally { $stream.Dispose() }
        }
    }
    Assert-BootTest ((Get-FileHash -LiteralPath $legacy -Algorithm SHA256).Hash -ceq $legacyHash) 'version 1 checkpoint preserved and does not block version 2'
    # Leave checkpoints for both modes so real CMD launches stop before any USB.
    $checkpoint=Join-Path $script:BootTestRoot 'ubuntu-boot-update-2-apply-state.json'
    if (-not (Test-Path -LiteralPath $checkpoint)) { [IO.File]::WriteAllText($checkpoint,'{"write_started":true,"success":false}') }
    Invoke-BootNativeEntry 'INSTALLA-CORREZIONE-AVVIO.cmd'
    Invoke-BootNativeEntry 'RIPRISTINA-BOOT-1.cmd'
    $owned='/data/ubuntu-touch-boot-update-'+('a'*32)
    foreach ($pair in @(@('write-system',$owned),@('write-vendor',$owned),@('write-boot','/data'),@('stage-cleanup','/data/../system'))) {
        $blocked=$false;try { $null=Get-BootUpdateArguments $pair[0] $pair[1] '' 53215232 } catch { $blocked=$true }
        Assert-BootTest $blocked 'unknown partitions and non-owned staging paths are rejected'
    }
    $stub=Join-Path $script:BootTestRoot 'local adb console stub.exe'
    Add-Type -TypeDefinition @'
using System;
public class S10BootUpdateFakeConsole {
    public static void Main(string[] args) { Console.WriteLine(string.Join("|",args));Console.Error.WriteLine("local stub error");Environment.Exit(1); }
}
'@ -OutputAssembly $stub -OutputType ConsoleApplication
    foreach ($action in @('push-boot','write-boot')) {
        $arguments=@(Get-BootUpdateArguments $action $owned (Join-Path $script:BootTestRoot 'boot-update-2\boot.img') 53215232)
        $native=Invoke-UtTwrpNative $stub $arguments
        Assert-BootTest ($native.ExitCode -eq 1 -and $native.Stdout.Trim() -ceq ($arguments -join '|') -and $native.Stderr -match 'local stub error') 'real native quoting, concurrent output and exit code; stub cannot access USB'
    }
    $newBoot=Join-Path $script:BootTestRoot 'boot-update-2\boot.img';$python=Join-Path $script:BootTestRoot 'tools\python\python.exe'
    $verifier=Join-Path $script:BootTestRoot 'scripts\verify_boot_update_2.py'
    & $python -I $verifier --image $newBoot
    Assert-BootTest ($LASTEXITCODE -eq 0) 'actual corrected image accepted on embedded Python'
    & $python -I $verifier --image (Join-Path $prepared 'boot.img')
    Assert-BootTest ($LASTEXITCODE -eq 1) 'old uncorrected BOOT cannot be mistaken for the update'
    & $python -I $verifier --image (Join-Path $script:BootTestRoot 'boot-update-1\boot.img')
    Assert-BootTest ($LASTEXITCODE -eq 1) 'version 1 cannot be mistaken for version 2'
    Write-Host 'PASS: 24 version 2 update/restore cases with actual pinned original/version 1/version 2 BOOT, embedded Python verification, physical BOOT target, unchanged-current-BOOT and recovery guards, staged hashes, readbacks, partial-write checkpoints, immutable inputs, versioned checkpoints, changed-local-image rejection, private reports and both real Windows 5.1 CMD launchers. USB/raw writes simulated; hardware Ubuntu boot unverified.'
} finally { Remove-Item -LiteralPath $script:BootTestRoot -Recurse -Force }
exit 0
