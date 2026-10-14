$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.IO.Compression.FileSystem
. (Join-Path $PSScriptRoot '..\scripts\install-ubuntu-twrp.ps1')
$script:TwrpTestRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\out\Ubuntu install with spaces'))
$script:TwrpTestInventory=[IO.File]::ReadAllText((Join-Path $PSScriptRoot '..\docs\evidence\recovery-check-2026-10-13.json')) | ConvertFrom-Json
$script:TwrpTestMode='';$script:TwrpTestOperations=@();$script:TwrpTestInventories=0;$script:TwrpTestUuids=0

function Assert-TwrpTest {
    param([bool]$Condition,[string]$Description)
    if (-not $Condition) { throw ('FAIL: '+$Description) }
}
$preflight={
    param([string]$Root)
    $state=[IO.File]::ReadAllText((Join-Path $Root 'ubuntu-local-state.json')) | ConvertFrom-Json
    return [pscustomobject]@{success=$true;backup_verified=($script:TwrpTestMode -ne 'backup')
        boot_path=(Join-Path $state.prepared_directory 'boot.img');system_path=(Join-Path $state.prepared_directory 'system.img');stock_firmware_path=$state.stock_firmware_path}
}
$inventory={
    param([string]$Root)
    $script:TwrpTestInventories++
    $report=($script:TwrpTestInventory.recovery_check | ConvertTo-Json -Depth 12) | ConvertFrom-Json
    if ($script:TwrpTestMode -eq 'mounted' -or ($script:TwrpTestMode -eq 'second-mounted' -and $script:TwrpTestInventories -eq 2)) { $report.selected_mounts+=@{target='/system_root'} }
    $success=($script:TwrpTestMode -ne 'inventory' -and -not ($script:TwrpTestMode -eq 'second-inventory' -and $script:TwrpTestInventories -eq 2))
    return [pscustomobject]@{Success=$success;Report=$report}
}
$metadata={
    param([string]$Executable,[string[]]$Arguments,[string]$Operation)
    $value='53ef'
    if ($Operation -eq 'data-uuid') {
        $script:TwrpTestUuids++;$value='aa'*16
        if ($script:TwrpTestMode -eq 'uuid-change' -and $script:TwrpTestUuids -eq 2) { $value='bb'*16 }
    }
    return [pscustomobject]@{ExitCode=0;TimedOut=$false;Stdout=$value;Stderr=''}
}
$actions={
    param([string]$Executable,[string[]]$Arguments,[string]$Action)
    $script:TwrpTestOperations+=$Action
    Assert-TwrpTest ($Arguments[0] -ceq '-d') 'all remote commands select USB only'
    $state=[IO.File]::ReadAllText((Join-Path $script:TwrpTestRoot 'ubuntu-local-state.json')) | ConvertFrom-Json
    $stage=''
    if (($Arguments -join ' ') -match '/data/ubuntu-touch-first-boot-[a-f0-9]{32}') { $stage=$Matches[0] }
    $result=[pscustomobject]@{ExitCode=0;Stdout='';Stderr=''}
    switch ($Action) {
        'data-space' {
            $free=113000000;if ($script:TwrpTestMode -eq 'space') { $free=1024 }
            $result.Stdout="Filesystem 1K-blocks Used Available Use% Mounted on`n/dev/block/sda31 114000000 1000000 $free 1% /data`n"
        }
        'data-clean' { if ($script:TwrpTestMode -eq 'android-data') { $result.ExitCode=1 } }
        'push-system' { if ($script:TwrpTestMode -eq 'transfer') { $result.ExitCode=1 } }
        'size-system' { $size='5368709120';if ($script:TwrpTestMode -eq 'size') { $size='1024' };$result.Stdout=$stage+'/system.img '+$size+' 0 81a4 0 0' }
        'size-boot' { $result.Stdout=$stage+'/boot.img 53215232 0 81a4 0 0' }
        'hash-system' { $result.Stdout='d23c80be74e3313e1a18272b7d27003a56a1ebc8593d5302738abe657a6e27c3  '+$stage+'/system.img';if ($script:TwrpTestMode -eq 'hash') { $result.Stdout='wrong hash' } }
        'hash-boot' { $result.Stdout='0992a55b228b97119139a845d9bd51821598fdb0fd18b4b823931f7f4ac8f0fc  '+$stage+'/boot.img' }
        'readback-system' { $result.Stdout='d23c80be74e3313e1a18272b7d27003a56a1ebc8593d5302738abe657a6e27c3  -';if ($script:TwrpTestMode -eq 'readback-system') { $result.Stdout='wrong readback' } }
        'readback-boot' { $result.Stdout='0992a55b228b97119139a845d9bd51821598fdb0fd18b4b823931f7f4ac8f0fc  -';if ($script:TwrpTestMode -eq 'readback-boot') { $result.Stdout='wrong readback' } }
        'stage-cleanup' {
            Assert-TwrpTest ($Arguments[2] -ceq "/sbin/busybox rm -f '$stage/system.img' '$stage/boot.img' && /sbin/busybox rmdir '$stage'") 'cleanup targets only the two owned temporary files and their empty folder'
        }
    }
    if ($Action -cin @('write-system','write-boot')) {
        $target='sda25';$file='system.img';if ($Action -eq 'write-boot') { $target='sda14';$file='boot.img' }
        Assert-TwrpTest ($Arguments.Count -eq 3 -and $Arguments[1] -ceq 'shell' -and
            $Arguments[2] -ceq "/sbin/busybox dd if='$stage/$file' of=/dev/block/$target bs=4194304 && /sbin/busybox sync") 'exact physical SYSTEM/BOOT target and owned input only'
        Assert-TwrpTest ($script:TwrpTestInventories -eq 2 -and $script:TwrpTestUuids -eq 2) 'prewrite recovery and unchanged filesystem checked'
        Assert-TwrpTest ($script:TwrpTestOperations -contains 'hash-system' -and $script:TwrpTestOperations -contains 'hash-boot') 'both transferred images verified before either partition write'
        Assert-TwrpTest (Test-Path -LiteralPath (Join-Path $script:TwrpTestRoot 'ubuntu-twrp-run-state.json')) 'write-intent checkpoint precedes raw write'
        foreach ($path in @((Join-Path $state.prepared_directory 'system.img'),(Join-Path $state.prepared_directory 'boot.img'),$state.stock_firmware_path)) {
            $reader=[IO.File]::OpenRead($path);$reader.Dispose();$blocked=$false
            try { $writer=[IO.File]::Open($path,[IO.FileMode]::Open,[IO.FileAccess]::Write,[IO.FileShare]::ReadWrite);$writer.Dispose() }
            catch [IO.IOException] { $blocked=$true }
            Assert-TwrpTest $blocked 'both inputs and full stock backup stay immutable during writes'
        }
        if ($script:TwrpTestMode -eq $Action) { $result.ExitCode=1;$result.Stderr='Simulated write error '+(Join-Path $state.prepared_directory 'system.img') }
    }
    return $result
}

function Invoke-TwrpFixture {
    param([string]$Mode,[string]$Error,[bool]$SystemWrite,[bool]$BootWrite)
    $script:TwrpTestMode=$Mode;$script:TwrpTestOperations=@();$script:TwrpTestInventories=0;$script:TwrpTestUuids=0
    $checkpoint=Join-Path $script:TwrpTestRoot 'ubuntu-twrp-run-state.json'
    if ($Mode -ne 'retry' -and (Test-Path -LiteralPath $checkpoint)) { Remove-Item -LiteralPath $checkpoint }
    $result=Invoke-UtTwrpInstallation -Root $script:TwrpTestRoot -PreflightRunner $preflight -InventoryRunner $inventory -MetadataRunner $metadata -ActionRunner $actions
    Assert-TwrpTest ($result.Success -eq ($Mode -eq 'success')) ($Mode+': success')
    Assert-TwrpTest (([string]$result.Report.error) -ceq ([string]$Error)) ($Mode+': error stage')
    Assert-TwrpTest ($result.Report.system_write_requested -eq $SystemWrite -and $result.Report.boot_write_requested -eq $BootWrite) ($Mode+': write gates')
    Assert-TwrpTest (-not $result.Report.data_format_requested -and -not $result.Report.download_mode_requested -and -not $result.Report.automatic_reboot_requested -and -not $result.Report.repartition_requested) 'no reset, Odin, automatic reboot or repartition'
    if ($Mode -eq 'success') {
        Assert-TwrpTest ($result.Report.system_readback_verified -and $result.Report.boot_readback_verified -and $result.Report.staging_cleanup_succeeded) 'both physical prefixes verified before success'
        Assert-TwrpTest (($script:TwrpTestOperations | Where-Object { $_ -like 'write-*' }) -join '|' -ceq 'write-system|write-boot') 'SYSTEM then BOOT only'
    }
    if ($SystemWrite -and -not $result.Success) { Assert-TwrpTest ($script:TwrpTestOperations -notcontains 'stage-cleanup') 'possible partial write preserves staged evidence and never retries' }
    $zip=[IO.Compression.ZipFile]::OpenRead($result.ZipPath)
    try {
        Assert-TwrpTest ($zip.Entries.Count -eq 1) 'only sanitized report shared'
        $reader=New-Object IO.StreamReader($zip.Entries[0].Open());try { $text=$reader.ReadToEnd() } finally { $reader.Dispose() }
        Assert-TwrpTest ($text -notmatch 'aaaaaaaaaaaaaaaa|bbbbbbbbbbbbbbbb|stock_firmware_path|serialNumber|C:\\PRIVATE|'+[regex]::Escape($script:TwrpTestRoot)) 'no filesystem UUID, device serial or PC paths in report'
    } finally { $zip.Dispose() }
    return $result
}

try {
    $prepared=Join-Path $script:TwrpTestRoot ('prepared-ubuntu-'+'a'*32)
    $stock=Join-Path $script:TwrpTestRoot 'fixture-stock.zip'
    [IO.File]::WriteAllBytes($stock,@());& fsutil.exe sparse setflag $stock | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'sparse_fixture_failed' }
    $stream=[IO.File]::OpenWrite($stock);try { $stream.SetLength(6364940601) } finally { $stream.Dispose() }
    # The actual prepared images are used unchanged. A sparse stock substitute
    # is accepted only by the injected test preflight, never production code.
    $state=@{schema=1;model='SM-G975F';pda='G975FXXSGHWC1';success=$true;backup_verified=$true;prepared_directory=$prepared;stock_firmware_path=$stock}
    [IO.File]::WriteAllText((Join-Path $script:TwrpTestRoot 'ubuntu-local-state.json'),($state | ConvertTo-Json))
    $reset=Join-Path $script:TwrpTestRoot 'ubuntu-install-report-10.zip'
    [IO.File]::WriteAllBytes($reset,[Convert]::FromBase64String([IO.File]::ReadAllText((Join-Path $PSScriptRoot 'fixtures\ubuntu-install-report-10.base64'))))
    $null=Invoke-TwrpFixture 'success' $null $true $true
    $null=Invoke-TwrpFixture 'retry' 'previous_twrp_write_needs_review' $false $false
    Assert-TwrpTest ($script:TwrpTestOperations.Count -eq 0) 'repeat execution stops before USB'
    foreach ($case in @(
        @('backup','image_or_backup_verification_failed',$false,$false),@('inventory','recovery_preflight_failed',$false,$false),
        @('mounted','recovery_mounts_invalid',$false,$false),@('android-data','fresh_userdata_required',$false,$false),
        @('space','insufficient_phone_staging_space',$false,$false),@('transfer','staging_transfer_failed',$false,$false),
        @('size','staged_image_verification_failed',$false,$false),@('hash','staged_image_verification_failed',$false,$false),
        @('second-inventory','prewrite_recovery_changed',$false,$false),@('second-mounted','prewrite_recovery_changed',$false,$false),
        @('uuid-change','prewrite_recovery_changed',$false,$false),@('write-system','system_write_failed',$true,$false),
        @('readback-system','system_readback_failed',$true,$false),@('write-boot','boot_write_failed',$true,$true),
        @('readback-boot','boot_readback_failed',$true,$true)
    )) { $null=Invoke-TwrpFixture $case[0] $case[1] $case[2] $case[3] }
    Remove-Item -LiteralPath $reset
    $null=Invoke-TwrpFixture 'reset-proof' 'completed_data_reset_report_missing' $false $false
    foreach ($pair in @(@('write-vendor','/data/ubuntu-touch-first-boot-'+('a'*32)),@('write-system','/data'),@('stage-cleanup','/data/../system'))) {
        $blocked=$false;try { $null=Get-UtTwrpArguments $pair[0] $pair[1] '' } catch { $blocked=$true }
        Assert-TwrpTest $blocked 'unknown partitions and non-owned staging paths are rejected'
    }
    $stub=Join-Path $script:TwrpTestRoot 'local adb console stub.exe'
    Add-Type -TypeDefinition @'
using System;
public class S10TwrpFakeConsole {
    public static void Main(string[] args) { Console.WriteLine(string.Join("|",args));Console.Error.WriteLine("local stub error");Environment.Exit(1); }
}
'@ -OutputAssembly $stub -OutputType ConsoleApplication
    $nativeArguments=@(Get-UtTwrpArguments 'write-system' ('/data/ubuntu-touch-first-boot-'+('a'*32)) '')
    $native=Invoke-UtTwrpNative $stub $nativeArguments
    Assert-TwrpTest ($native.ExitCode -eq 1 -and $native.Stdout.Trim() -ceq ($nativeArguments -join '|') -and $native.Stderr -match 'local stub error') 'real native quoting, concurrent output and exit code; stub cannot access USB'
    $info=New-Object Diagnostics.ProcessStartInfo;$info.FileName=$env:ComSpec
    $info.Arguments='/d /s /c ""'+(Join-Path $script:TwrpTestRoot 'INSTALLA-UBUNTU-TWRP.cmd')+'" <nul"'
    $info.UseShellExecute=$false;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
    $process=New-Object Diagnostics.Process;$process.StartInfo=$info
    try {
        Assert-TwrpTest ($process.Start()) 'actual native CMD starts'
        $out=$process.StandardOutput.ReadToEndAsync();$err=$process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit(60000)) { $process.Kill();throw 'entry_point_timeout' };$process.WaitForExit()
        Assert-TwrpTest ($process.ExitCode -eq 1 -and $out.GetAwaiter().GetResult() -match 'completed_data_reset_report_missing') ('native CMD: '+$out.GetAwaiter().GetResult()+$err.GetAwaiter().GetResult())
    } finally { $process.Dispose() }
    Write-Host 'PASS: 18 staged cases using actual pinned BOOT/SYSTEM, completed-reset proof, transferred-image hashes, prewrite recovery/UUID guards, exact physical targets, readback verification, blocked repeats, immutable backups, owned-file cleanup and real native CMD/console. USB and raw partition writes simulated; Ubuntu hardware boot unverified.'
} finally { Remove-Item -LiteralPath $script:TwrpTestRoot -Recurse -Force }
