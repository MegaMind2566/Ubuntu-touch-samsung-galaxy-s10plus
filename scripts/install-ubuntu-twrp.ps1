# Exact first UT installation through the already verified root TWRP.
# Reuses the completed data reset; no Download-mode protocol or new format.
[CmdletBinding()]
param([string]$PackageRoot)
$utTwrpDirectory=[IO.Path]::GetDirectoryName($MyInvocation.MyCommand.Path)
if ([string]::IsNullOrEmpty($PackageRoot)) { $PackageRoot=Join-Path $utTwrpDirectory '..' }
$utTwrpRoot=[IO.Path]::GetFullPath($PackageRoot)
. (Join-Path $utTwrpDirectory 'install-ubuntu-touch.ps1')

function Get-UtTwrpArguments {
    param([string]$Action,[string]$Stage,[string]$LocalImage)
    if ($Stage -cnotmatch '^/data/ubuntu-touch-first-boot-[a-f0-9]{32}$') { throw 'staging_path_invalid' }
    switch ($Action) {
        'push-system' { return @('-d','push','-Z',$LocalImage,($Stage+'/system.img')) }
        'push-boot' { return @('-d','push','-Z',$LocalImage,($Stage+'/boot.img')) }
        'data-clean' { $command='test ! -e /data/system && test ! -e /data/misc/vold' }
        'data-space' { $command='/sbin/busybox df -k /data' }
        'stage-create' { $command="test ! -e '$Stage' && /sbin/busybox mkdir -m 700 '$Stage'" }
        'size-system' { $command="/sbin/busybox stat -t '$Stage/system.img'" }
        'size-boot' { $command="/sbin/busybox stat -t '$Stage/boot.img'" }
        'hash-system' { $command="/sbin/busybox sha256sum '$Stage/system.img'" }
        'hash-boot' { $command="/sbin/busybox sha256sum '$Stage/boot.img'" }
        'write-system' { $command="/sbin/busybox dd if='$Stage/system.img' of=/dev/block/sda25 bs=4194304 && /sbin/busybox sync" }
        'write-boot' { $command="/sbin/busybox dd if='$Stage/boot.img' of=/dev/block/sda14 bs=4194304 && /sbin/busybox sync" }
        'readback-system' { $command='/sbin/busybox dd if=/dev/block/sda25 bs=4194304 count=1280 2>/dev/null | /sbin/busybox sha256sum' }
        'readback-boot' { $command='/sbin/busybox head -c 53215232 /dev/block/sda14 | /sbin/busybox sha256sum' }
        'stage-cleanup' { $command="/sbin/busybox rm -f '$Stage/system.img' '$Stage/boot.img' && /sbin/busybox rmdir '$Stage'" }
        default { throw 'twrp_action_not_allowed' }
    }
    return @('-d','shell',$command)
}

function Invoke-UtTwrpNative {
    param([string]$Executable,[string[]]$Arguments)
    # No timeout/kill while any remote write may still be running.
    $info=New-Object Diagnostics.ProcessStartInfo
    $info.FileName=$Executable;$info.Arguments=(($Arguments | ForEach-Object { ConvertTo-DownloadCheckArgument $_ }) -join ' ')
    $info.UseShellExecute=$false;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
    if (-not ('S10TwrpNativeConsole' -as [type])) {
        Add-Type -TypeDefinition @'
using System;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Threading.Tasks;
public class S10TwrpNativeResult { public int ExitCode; public string Stdout; public string Stderr; }
public static class S10TwrpNativeConsole {
    private static async Task<string> Drain(StreamReader reader) {
        StringBuilder saved=new StringBuilder(); string line;
        while ((line=await reader.ReadLineAsync().ConfigureAwait(false))!=null) {
            Console.WriteLine(line); int remaining=1048576-saved.Length;
            if (remaining>0) { saved.Append(line.Substring(0,Math.Min(remaining,line.Length))); if (saved.Length<1048576) saved.Append('\n'); }
        }
        return saved.ToString();
    }
    public static S10TwrpNativeResult Run(ProcessStartInfo info) {
        using (Process process=new Process()) {
            process.StartInfo=info;if (!process.Start()) throw new IOException("native_start_failed");
            Task<string> stdout=Drain(process.StandardOutput),stderr=Drain(process.StandardError);
            process.WaitForExit();Task.WaitAll(stdout,stderr);
            return new S10TwrpNativeResult {ExitCode=process.ExitCode,Stdout=stdout.Result,Stderr=stderr.Result};
        }
    }
}
'@
    }
    return [S10TwrpNativeConsole]::Run($info)
}

function Invoke-UtTwrpAction {
    param([string]$Executable,[string]$Action,[string]$Stage,[string]$LocalImage,
          [scriptblock]$Runner,[System.Collections.IList]$Trace,[string[]]$PrivateValues)
    $arguments=@(Get-UtTwrpArguments $Action $Stage $LocalImage)
    if ($Runner) { $result=& $Runner $Executable $arguments $Action }
    else { $result=Invoke-UtTwrpNative $Executable $arguments }
    if ($null -ne $Trace) { $Trace.Add([pscustomobject]@{
        operation=$Action;exit_code=$result.ExitCode
        stderr=(Protect-RecoveryTestText ([string]$result.Stderr) $PrivateValues)
    }) | Out-Null }
    if ($result.ExitCode -ne 0) { throw ('twrp_'+$Action+'_failed') }
    return $result
}

function Assert-UtTwrpInventory {
    param($Inventory)
    if (-not $Inventory.Success) { throw 'recovery_preflight_failed' }
    foreach ($mount in $Inventory.Report.selected_mounts) {
        if ($mount.target -cin @('/system','/system_root','/vendor')) { throw 'system_or_vendor_mounted' }
    }
    $data=@($Inventory.Report.selected_mounts | Where-Object { $_.target -ceq '/data' })
    if ($data.Count -ne 1 -or $data[0].filesystem -cne 'ext4' -or $data[0].options -notmatch '(^|,)rw(,|$)' -or
        $data[0].source -cnotin @('/dev/block/sda31','/dev/block/platform/13d60000.ufs/by-name/userdata')) { throw 'direct_ext4_userdata_required' }
}

function Confirm-UtCompletedDataReset {
    param([string]$Root)
    # Exact reviewed report 10: fresh ext4 UUID was proved, then Odin failed
    # while reading PIT, before image payloads. No new erase is requested.
    foreach ($file in @(Get-ChildItem -LiteralPath $Root -Filter 'ubuntu-install-report*.zip' -File)) {
        if ($file.Length -ne 855) { continue }
        if ((Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant() -ceq
            'edc71291bba36652d8fd67afb1affb73f5bbcc6f3dfc40dfc54c7120f1566edb') { return $true }
    }
    return $false
}

function Invoke-UtTwrpInstallation {
    param([string]$Root,[scriptblock]$PreflightRunner,[scriptblock]$InventoryRunner,[scriptblock]$MetadataRunner,[scriptblock]$ActionRunner)
    $ErrorActionPreference='Stop';Add-Type -AssemblyName System.IO.Compression.FileSystem
    $Root=[IO.Path]::GetFullPath($Root)
    $directory=Join-Path $Root ('ubuntu-twrp-check-'+[Guid]::NewGuid().ToString('N'))
    [IO.Directory]::CreateDirectory($directory) | Out-Null
    $private=Join-Path $directory 'private-check.json'
    $python=Join-Path $Root 'tools\python\python.exe';$adb=Join-Path $Root 'platform-tools\adb.exe'
    $stage='/data/ubuntu-touch-first-boot-'+[Guid]::NewGuid().ToString('N')
    $statePath=Join-Path $Root 'ubuntu-twrp-run-state.json'
    $locks=New-Object 'System.Collections.Generic.List[System.IO.FileStream]'
    $trace=New-Object System.Collections.ArrayList;$metadata=New-Object System.Collections.ArrayList
    $report=[ordered]@{
        schema=1;installer_version=1;route='root_twrp_adb';date_utc=[DateTime]::UtcNow.ToString('o');model='SM-G975F';pda='G975FXXSGHWC1'
        target_partitions=@('SYSTEM','BOOT');local_images_verified=$false;stock_backup_verified=$false;recovery_checks_passed=$false
        previous_data_reset_verified=$false;fresh_data_metadata_passed=$false;userdata_uuid_unchanged=$false
        staged_images_verified=$false;prewrite_inventory_passed=$false;system_write_requested=$false;system_readback_verified=$false
        boot_write_requested=$false;boot_readback_verified=$false;staging_cleanup_succeeded=$false;partition_progress='not_requested'
        data_format_requested=$false;repartition_requested=$false;download_mode_requested=$false;automatic_reboot_requested=$false
        ubuntu_touch_boot_verified=$false;success=$false;error=$null;steps=$trace;data_metadata_steps=$metadata
    }
    $reason='package_dependencies_invalid';$stageCreated=$false
    $privateValues=@($Root,$directory,$private,$python,$adb,$stage)
    try {
        # An exclusive local lock prevents concurrent TWRP installer instances.
        $locks.Add([IO.File]::Open((Join-Path $Root 'ubuntu-twrp-session.lock'),[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None))
        if ((Get-FileHash -LiteralPath $python -Algorithm SHA256).Hash.ToLowerInvariant() -cne $script:RecoveryTestPythonHash) { throw $reason }
        foreach ($name in $script:RecoveryAdbHashes.Keys) {
            if ((Get-FileHash -LiteralPath (Join-Path $Root ('platform-tools\'+$name)) -Algorithm SHA256).Hash.ToLowerInvariant() -cne $script:RecoveryAdbHashes[$name]) { throw $reason }
        }
        $reason='previous_twrp_write_needs_review'
        if (Test-Path -LiteralPath $statePath) { throw $reason }
        $reason='completed_data_reset_report_missing'
        if (-not (Confirm-UtCompletedDataReset $Root)) { throw $reason }
        $report.previous_data_reset_verified=$true
        $reason='preparation_state_invalid'
        $readyPath=Join-Path $Root 'ubuntu-local-state.json'
        if ((Get-Item -LiteralPath $readyPath).Length -gt 131072) { throw $reason }
        $ready=[IO.File]::ReadAllText($readyPath) | ConvertFrom-Json
        $prepared=[IO.Path]::GetFullPath([string]$ready.prepared_directory)
        if ([IO.Path]::GetDirectoryName($prepared).TrimEnd('\') -ine $Root.TrimEnd('\') -or
            [IO.Path]::GetFileName($prepared) -cnotmatch '^prepared-ubuntu-[a-f0-9]{32}$') { throw $reason }
        $boot=Join-Path $prepared 'boot.img';$system=Join-Path $prepared 'system.img';$stock=[IO.Path]::GetFullPath([string]$ready.stock_firmware_path)
        $privateValues+=@($boot,$system,$stock,$prepared)
        foreach ($path in @($boot,$system,$stock,$readyPath,$python,$adb)) {
            $locks.Add([IO.File]::Open($path,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read))
        }
        $reason='image_or_backup_verification_failed'
        if ($PreflightRunner) { $files=& $PreflightRunner $Root }
        else {
            & $python -I (Join-Path $Root 'scripts\prepare_ubuntu_install.py') --root $Root --verify-output $private | ForEach-Object { Write-Host $_ }
            if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $private)) { throw $reason }
            $files=[IO.File]::ReadAllText($private) | ConvertFrom-Json
        }
        if (-not $files.success -or -not $files.backup_verified -or [IO.Path]::GetFullPath([string]$files.boot_path) -ine $boot -or
            [IO.Path]::GetFullPath([string]$files.system_path) -ine $system -or [IO.Path]::GetFullPath([string]$files.stock_firmware_path) -ine $stock) { throw $reason }
        if ($locks[1].Length -ne 53215232 -or $locks[2].Length -ne 5368709120 -or $locks[3].Length -ne 6364940601 -or
            (Get-FileHash -LiteralPath $boot -Algorithm SHA256).Hash.ToLowerInvariant() -cne '0992a55b228b97119139a845d9bd51821598fdb0fd18b4b823931f7f4ac8f0fc' -or
            (Get-FileHash -LiteralPath $system -Algorithm SHA256).Hash.ToLowerInvariant() -cne 'd23c80be74e3313e1a18272b7d27003a56a1ebc8593d5302738abe657a6e27c3') { throw $reason }
        $report.local_images_verified=$true;$report.stock_backup_verified=$true
        $reason='recovery_preflight_failed'
        if ($InventoryRunner) { $inventory=& $InventoryRunner $Root } else { $inventory=Invoke-RecoveryInventory -Root $Root }
        if (-not $inventory.Success) { throw $reason }
        $reason='recovery_mounts_invalid';Assert-UtTwrpInventory $inventory
        $report.recovery_checks_passed=$true
        $reason='fresh_userdata_required'
        $null=Invoke-UtMetadata $adb 'data-magic' $MetadataRunner $metadata
        $uuidBefore=Invoke-UtMetadata $adb 'data-uuid' $MetadataRunner $metadata
        $null=Invoke-UtTwrpAction $adb 'data-clean' $stage '' $ActionRunner $trace $privateValues
        $report.fresh_data_metadata_passed=$true
        $reason='insufficient_phone_staging_space'
        $space=Invoke-UtTwrpAction $adb 'data-space' $stage '' $ActionRunner $trace $privateValues
        if ($space.Stdout -notmatch '(?m)\b([0-9]+)\s+([0-9]+)\s+([0-9]+)\s+[0-9]+%\s+/data\s*$' -or
            [uint64]$Matches[3]*1024 -lt 5368709120+53215232+536870912) { throw $reason }
        $report.phone_staging_free_bytes=[uint64]$Matches[3]*1024
        $reason='staging_transfer_failed'
        $null=Invoke-UtTwrpAction $adb 'stage-create' $stage '' $ActionRunner $trace $privateValues;$stageCreated=$true
        Write-Host 'Copia di SYSTEM sul telefono: 5 GiB. Attendi la fine e lascia USB collegato.'
        $null=Invoke-UtTwrpAction $adb 'push-system' $stage $system $ActionRunner $trace $privateValues
        Write-Host 'Copia di BOOT sul telefono...'
        $null=Invoke-UtTwrpAction $adb 'push-boot' $stage $boot $ActionRunner $trace $privateValues
        $reason='staged_image_verification_failed'
        foreach ($item in @(@('system',5368709120,'d23c80be74e3313e1a18272b7d27003a56a1ebc8593d5302738abe657a6e27c3'),
                            @('boot',53215232,'0992a55b228b97119139a845d9bd51821598fdb0fd18b4b823931f7f4ac8f0fc'))) {
            $size=Invoke-UtTwrpAction $adb ('size-'+$item[0]) $stage '' $ActionRunner $trace $privateValues
            # Reduced recovery BusyBox supports terse -t, not custom -c.
            # Owned staging paths contain no whitespace; fields 0/1 are path/size.
            $fields=$size.Stdout.Trim() -split '\s+'
            if ($fields.Count -lt 3 -or $fields[0] -cne ($stage+'/'+$item[0]+'.img') -or $fields[1] -cne [string]$item[1]) { throw $reason }
            $hash=Invoke-UtTwrpAction $adb ('hash-'+$item[0]) $stage '' $ActionRunner $trace $privateValues
            $expected=[regex]::Escape([string]$item[2])+'\s+'+[regex]::Escape($stage+'/'+$item[0]+'.img')
            if ($hash.Stdout.Trim() -cnotmatch ('^'+$expected+'$')) { throw $reason }
        }
        $report.staged_images_verified=$true
        $reason='prewrite_recovery_changed'
        if ($InventoryRunner) { $inventory=& $InventoryRunner $Root } else { $inventory=Invoke-RecoveryInventory -Root $Root }
        Assert-UtTwrpInventory $inventory
        $uuidAfter=Invoke-UtMetadata $adb 'data-uuid' $MetadataRunner $metadata
        if ($uuidBefore -cne $uuidAfter) { throw $reason }
        $null=Invoke-UtTwrpAction $adb 'data-clean' $stage '' $ActionRunner $trace $privateValues
        $report.userdata_uuid_unchanged=$true;$report.prewrite_inventory_passed=$true
        # Persist before the first possible partition write; interrupted runs
        # cannot silently retry or reformat when the launcher is opened again.
        [IO.File]::WriteAllText($statePath,'{"write_started":true,"success":false}')
        $reason='system_write_failed';$report.system_write_requested=$true;$report.partition_progress='unknown'
        Write-Host 'Scrittura di SYSTEM. Non scollegare USB e non chiudere la finestra.'
        $null=Invoke-UtTwrpAction $adb 'write-system' $stage '' $ActionRunner $trace $privateValues
        $reason='system_readback_failed'
        $hash=Invoke-UtTwrpAction $adb 'readback-system' $stage '' $ActionRunner $trace $privateValues
        if ($hash.Stdout.Trim() -cnotmatch '^d23c80be74e3313e1a18272b7d27003a56a1ebc8593d5302738abe657a6e27c3\s+-$') { throw $reason }
        $report.system_readback_verified=$true;$report.partition_progress='system_verified_boot_not_requested'
        $reason='boot_write_failed';$report.boot_write_requested=$true;$report.partition_progress='system_verified_boot_unknown'
        Write-Host 'Scrittura di BOOT e verifica finale...'
        $null=Invoke-UtTwrpAction $adb 'write-boot' $stage '' $ActionRunner $trace $privateValues
        $reason='boot_readback_failed'
        $hash=Invoke-UtTwrpAction $adb 'readback-boot' $stage '' $ActionRunner $trace $privateValues
        if ($hash.Stdout.Trim() -cnotmatch '^0992a55b228b97119139a845d9bd51821598fdb0fd18b4b823931f7f4ac8f0fc\s+-$') { throw $reason }
        $report.boot_readback_verified=$true;$report.partition_progress='system_and_boot_readback_verified';$report.success=$true
        [IO.File]::WriteAllText($statePath,'{"write_started":true,"success":true}')
        Write-Host 'INSTALLAZIONE COMPLETATA E VERIFICATA. In TWRP scegli Reboot > System per il primo avvio.'
        Write-Host 'Se chiede di installare l app TWRP, scegli Do Not Install.'
        Write-Host 'Invia una foto della schermata ottenuta e il rapporto.'
    } catch {
        $report.error=$reason;Write-Host ('Installazione fermata: '+$reason)
        Write-Host 'Lascia il telefono in TWRP e invia il rapporto. Non ripetere la scrittura o Format Data.'
    } finally {
        if ($stageCreated -and ($report.success -or -not $report.system_write_requested)) {
            try {
                $null=Invoke-UtTwrpAction $adb 'stage-cleanup' $stage '' $ActionRunner $trace $privateValues
                $report.staging_cleanup_succeeded=$true
            } catch { $report.staging_cleanup_succeeded=$false }
        }
        foreach ($handle in $locks) { $handle.Dispose() }
        if (Test-Path -LiteralPath $private) { Remove-Item -LiteralPath $private -Force }
        [IO.File]::WriteAllText((Join-Path $directory 'ubuntu-twrp-install-report.json'),($report | ConvertTo-Json -Depth 8),(New-Object Text.UTF8Encoding($false)))
        $zip=Join-Path $Root 'ubuntu-twrp-install-report.zip';$index=1
        while (Test-Path -LiteralPath $zip) { $zip=Join-Path $Root ('ubuntu-twrp-install-report-'+$index+'.zip');$index++ }
        [IO.Compression.ZipFile]::CreateFromDirectory($directory,$zip,[IO.Compression.CompressionLevel]::Optimal,$false)
        Remove-Item -LiteralPath $directory -Recurse -Force
    }
    Write-Host ('Invia questo rapporto: '+$zip)
    return [pscustomobject]@{Success=$report.success;Report=$report;ZipPath=$zip}
}

if ($MyInvocation.InvocationName -ne '.') {
    try { $result=Invoke-UtTwrpInstallation -Root $utTwrpRoot;if ($result.Success) { exit 0 };exit 1 }
    catch { Write-Host 'Estrai questo aggiornamento nella cartella gia preparata. Lascia il telefono in TWRP.';exit 2 }
}
