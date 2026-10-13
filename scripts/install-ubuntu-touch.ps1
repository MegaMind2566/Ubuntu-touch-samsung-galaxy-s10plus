# First experimental UT boot: only SYSTEM and BOOT. Data format is a manual
# TWRP action after verified PC preparation; no automated wipe or retry.
[CmdletBinding()]
param([string]$PackageRoot)
$utInstallerDirectory = [IO.Path]::GetDirectoryName($MyInvocation.MyCommand.Path)
if ([string]::IsNullOrEmpty($PackageRoot)) { $PackageRoot = Join-Path $utInstallerDirectory '..' }
$utInstallerRoot = [IO.Path]::GetFullPath($PackageRoot)
. (Join-Path $utInstallerDirectory 'check-recovery.ps1')
. (Join-Path $utInstallerDirectory 'flash-recovery-test.ps1')

function Invoke-UtFlash {
    param([string]$Executable,[string]$SystemImage,[string]$BootImage,[scriptblock]$Runner)
    $arguments = @('--usb-backend','vcom','flash','--partition','SYSTEM',$SystemImage,'--partition','BOOT',$BootImage,'--no-reboot')
    if ($Runner) { return & $Runner $Executable $arguments }
    $info = New-Object Diagnostics.ProcessStartInfo
    $info.FileName = $Executable
    $info.Arguments = (($arguments | ForEach-Object { ConvertTo-DownloadCheckArgument $_ }) -join ' ')
    $info.UseShellExecute = $false; $info.RedirectStandardOutput = $true; $info.RedirectStandardError = $true
    if (-not ('S10UtNativeConsole' -as [type])) {
        Add-Type -TypeDefinition @'
using System;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Threading.Tasks;
public class S10UtNativeResult { public int ExitCode; public string Stdout; public string Stderr; }
public static class S10UtNativeConsole {
    private static async Task<string> Drain(StreamReader reader) {
        StringBuilder saved = new StringBuilder(); string line;
        while ((line = await reader.ReadLineAsync().ConfigureAwait(false)) != null) {
            Console.WriteLine(line); int remaining = 1048576 - saved.Length;
            if (remaining > 0) {
                saved.Append(line.Substring(0, Math.Min(remaining, line.Length)));
                if (saved.Length < 1048576) saved.Append('\n');
            }
        }
        return saved.ToString();
    }
    public static S10UtNativeResult Run(ProcessStartInfo info) {
        using (Process process = new Process()) {
            process.StartInfo = info;
            if (!process.Start()) throw new IOException("native_start_failed");
            Task<string> stdout = Drain(process.StandardOutput), stderr = Drain(process.StandardError);
            process.WaitForExit(); Task.WaitAll(stdout, stderr);
            return new S10UtNativeResult { ExitCode = process.ExitCode, Stdout = stdout.Result, Stderr = stderr.Result };
        }
    }
}
'@
    }
    return [S10UtNativeConsole]::Run($info)
}

function Invoke-UtMetadata {
    param([string]$Executable,[string]$Operation,[scriptblock]$Runner,[System.Collections.IList]$Trace)
    # Read only filesystem magic/UUID metadata, never personal files.
    # Recovery's reduced BusyBox od does not support desktop -A/-t options.
    # Invoke its known hexdump applet explicitly, with bounded offset/count.
    $queries = @{
        'data-magic' = '/sbin/busybox hexdump -v -s 1080 -n 2 -e ''1/1 "%02x"'' /dev/block/sda31'
        'data-uuid' = '/sbin/busybox hexdump -v -s 1128 -n 16 -e ''1/1 "%02x"'' /dev/block/sda31'
    }
    if (-not $queries.ContainsKey($Operation)) { throw 'metadata_query_not_allowed' }
    $step=[ordered]@{operation=$Operation;exit_code=$null;timed_out=$false;hex_valid=$false;error=$null;stderr=$null}
    try {
        if ($Runner) { $result = & $Runner $Executable @('-d','shell',$queries[$Operation]) $Operation }
        else { $result = Invoke-DownloadCheckNative $Executable @('-d','shell',$queries[$Operation]) 30 }
        $step.exit_code=$result.ExitCode;$step.timed_out=$result.TimedOut
        $step.stderr=Protect-RecoveryTestText ([string]$result.Stderr) @()
        if ($result.ExitCode -ne 0 -or $result.TimedOut) { $step.error='data_metadata_command_failed';throw $step.error }
        $value = [regex]::Replace($result.Stdout,'\s','')
        if (($Operation -eq 'data-magic' -and $value -cnotmatch '^[0-9a-f]{4}$') -or
            ($Operation -eq 'data-uuid' -and $value -cnotmatch '^[0-9a-f]{32}$')) { $step.error='data_metadata_invalid_hex';throw $step.error }
        $step.hex_valid=$true
        if ($Operation -eq 'data-magic' -and $value -cne '53ef') { $step.error='data_not_ext4';throw $step.error }
        return $value
    } catch {
        if (-not $step.error) { $step.error='data_metadata_unavailable' }
        throw
    } finally {
        # UUID/stdout never enter the diagnostic report.
        if ($null -ne $Trace) { $Trace.Add([pscustomobject]$step) | Out-Null }
    }
}

function Confirm-UtPhysicalStep {
    param([string]$Step,[scriptblock]$Runner)
    if ($Runner) { return [bool](& $Runner $Step) }
    if ($Step -eq 'format-data') {
        Write-Host ''
        Write-Host 'I file sono verificati. Ora prepara una memoria dati pulita in TWRP.'
        Write-Host 'QUESTO PASSAGGIO CANCELLA TUTTA LA MEMORIA INTERNA DEL TELEFONO.'
        Write-Host 'Sul telefono: Wipe > Format Data > scrivi yes > conferma.'
        Write-Host 'Alla fine torna alla schermata principale TWRP. Non usare Advanced Wipe.'
        $value = Read-Host 'Solo dopo Format Data completato premi INVIO; scrivi STOP per fermarti'
    } elseif ($Step -eq 'download-mode') {
        Write-Host ''
        Write-Host 'Sul telefono apri Reboot > Download e lascia collegato USB.'
        Write-Host 'Devi ritrovarti nella schermata Downloading.'
        $value = Read-Host 'Solo quando sei in Downloading premi INVIO; scrivi STOP per fermarti'
    } else { throw 'physical_step_invalid' }
    return ($value -ceq '')
}

function Invoke-UtInstallation {
    param([string]$Root,[scriptblock]$PreflightRunner,[scriptblock]$InventoryRunner,
          [scriptblock]$MetadataRunner,[scriptblock]$PhysicalRunner,[scriptblock]$UsbRunner,[scriptblock]$FlashRunner)
    $ErrorActionPreference = 'Stop'
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $Root = [IO.Path]::GetFullPath($Root)
    $directory = Join-Path $Root ('ubuntu-install-check-' + [Guid]::NewGuid().ToString('N'))
    [IO.Directory]::CreateDirectory($directory) | Out-Null
    $private = Join-Path $directory 'private-check.json'
    $python = Join-Path $Root 'tools\python\python.exe'
    $samloader = Join-Path $Root 'tools\samloader\samloader.exe'
    $adb = Join-Path $Root 'platform-tools\adb.exe'
    $locks = New-Object 'System.Collections.Generic.List[System.IO.FileStream]'
    $metadataSteps = New-Object System.Collections.ArrayList
    $report = [ordered]@{
        schema=1; installer_version=2; date_utc=[DateTime]::UtcNow.ToString('o'); model='SM-G975F'; pda='G975FXXSGHWC1'
        target_partitions=@('SYSTEM','BOOT'); local_images_verified=$false; stock_backup_verified=$false
        recovery_checks_passed=$false; data_format_acknowledged=$false; data_uuid_changed_after_format=$false
        download_mode_acknowledged=$false; model_confirmed_by_usb=$false; flash_invoked=$false
        flash_exit_code=$null; flash_tool_succeeded=$false; partition_data_sent='not_requested'
        automatic_erase_requested=$false; repartition_requested=$false; automatic_reboot_requested=$false
        current_pit_read_inside_flash_session=$true; native_size_checks_enabled=$true
        ubuntu_touch_boot_verified=$false; success=$false; error=$null; native_stdout=$null; native_stderr=$null
        data_metadata_steps=$metadataSteps
    }
    $reason='package_dependencies_invalid';$privateValues=@($Root,$directory,$python,$samloader,$adb)
    try {
        if ((Get-FileHash -LiteralPath $python -Algorithm SHA256).Hash.ToLowerInvariant() -cne $script:RecoveryTestPythonHash -or
            (Get-FileHash -LiteralPath $samloader -Algorithm SHA256).Hash.ToLowerInvariant() -cne $script:DownloadCheckExeHash) { throw $reason }
        $reason='preparation_state_invalid'
        $statePath=Join-Path $Root 'ubuntu-local-state.json'
        if ((Get-Item -LiteralPath $statePath).Length -gt 131072) { throw $reason }
        $state=[IO.File]::ReadAllText($statePath) | ConvertFrom-Json
        $prepared=[IO.Path]::GetFullPath([string]$state.prepared_directory)
        if ([IO.Path]::GetDirectoryName($prepared).TrimEnd('\') -ine $Root.TrimEnd('\') -or
            [IO.Path]::GetFileName($prepared) -notmatch '^prepared-ubuntu-[a-f0-9]{32}$') { throw $reason }
        $boot=Join-Path $prepared 'boot.img';$system=Join-Path $prepared 'system.img'
        $stock=[IO.Path]::GetFullPath([string]$state.stock_firmware_path)
        $privateValues+=@($prepared,$boot,$system,$stock)
        foreach ($path in @($boot,$system,$stock,$samloader,$python,$statePath)) {
            $locks.Add([IO.File]::Open($path,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read))
        }
        $reason='image_or_backup_verification_failed'
        if ($PreflightRunner) { $files=& $PreflightRunner $Root }
        else {
            & $python -I (Join-Path $Root 'scripts\prepare_ubuntu_install.py') --root $Root --verify-output $private | ForEach-Object { Write-Host $_ }
            $code=$LASTEXITCODE
            if (-not (Test-Path -LiteralPath $private)) { throw $reason }
            $files=[IO.File]::ReadAllText($private) | ConvertFrom-Json
            if ($code -ne 0) { throw $reason }
        }
        if ($files.success -ne $true -or $files.backup_verified -ne $true -or
            [IO.Path]::GetFullPath([string]$files.boot_path) -ine $boot -or
            [IO.Path]::GetFullPath([string]$files.system_path) -ine $system -or
            [IO.Path]::GetFullPath([string]$files.stock_firmware_path) -ine $stock) { throw $reason }
        if ($locks[0].Length -ne 53215232 -or $locks[1].Length -ne 5368709120 -or $locks[2].Length -ne 6364940601 -or
            (Get-FileHash -LiteralPath $boot -Algorithm SHA256).Hash.ToLowerInvariant() -cne '0992a55b228b97119139a845d9bd51821598fdb0fd18b4b823931f7f4ac8f0fc' -or
            (Get-FileHash -LiteralPath $system -Algorithm SHA256).Hash.ToLowerInvariant() -cne 'd23c80be74e3313e1a18272b7d27003a56a1ebc8593d5302738abe657a6e27c3') { throw $reason }
        $report.local_images_verified=$true;$report.stock_backup_verified=$true
        $reason='recovery_preflight_failed'
        if ($InventoryRunner) { $inventory=& $InventoryRunner $Root }
        else { $inventory=Invoke-RecoveryInventory -Root $Root }
        if (-not $inventory.Success) { throw $reason }
        foreach ($mount in $inventory.Report.selected_mounts) {
            if ($mount.target -cin @('/system','/system_root','/vendor')) { $reason='system_or_vendor_mounted';throw $reason }
        }
        $report.recovery_checks_passed=$true
        $reason='userdata_metadata_before_format_failed'
        $uuidBefore=Invoke-UtMetadata $adb 'data-uuid' $MetadataRunner $metadataSteps
        $reason='userdata_format_not_acknowledged'
        if (-not (Confirm-UtPhysicalStep 'format-data' $PhysicalRunner)) { throw $reason }
        $report.data_format_acknowledged=$true
        $reason='userdata_metadata_after_format_failed'
        $null=Invoke-UtMetadata $adb 'data-magic' $MetadataRunner $metadataSteps
        $uuidAfter=Invoke-UtMetadata $adb 'data-uuid' $MetadataRunner $metadataSteps
        $reason='userdata_format_not_completed'
        if ($uuidBefore -ceq $uuidAfter) { throw $reason }
        $report.data_uuid_changed_after_format=$true
        # UUID values stay in memory and are never saved in the report.
        $reason='download_mode_not_confirmed'
        if (-not (Confirm-UtPhysicalStep 'download-mode' $PhysicalRunner)) { throw $reason }
        $report.download_mode_acknowledged=$true
        $reason='usb_model_not_confirmed'
        $result=Invoke-DownloadCheckCommand $samloader @('--usb-backend','vcom','detect','--json') '' 30 $UsbRunner
        if ($result.ExitCode -ne 0 -or $result.TimedOut) { throw $reason }
        $device=$result.Stdout | ConvertFrom-Json
        if (([string]$device.modelName).Trim() -cnotin @('SM-G975F','SM-G975F/DS')) { throw $reason }
        $privateValues+=[string]$device.serialNumber;$report.model_confirmed_by_usb=$true
        # No standalone dump-pit here: all current geometry is already checked
        # in recovery. Native flash downloads PIT and checks sizes in this same
        # Odin session, avoiding a second handshake on the Samsung bootloader.
        Write-Host 'Scrittura di SYSTEM e poi BOOT. Non scollegare USB e non chiudere la finestra.'
        $reason='flash_failed';$report.flash_invoked=$true;$report.partition_data_sent='unknown'
        $native=Invoke-UtFlash $samloader $system $boot $FlashRunner
        $report.flash_exit_code=[int]$native.ExitCode
        $report.native_stdout=Protect-RecoveryTestText ([string]$native.Stdout) $privateValues
        $report.native_stderr=Protect-RecoveryTestText ([string]$native.Stderr) $privateValues
        if ($native.ExitCode -ne 0) {
            if (($native.Stdout+"`n"+$native.Stderr) -match 'Unexpected handshake response|Failed to receive handshake response|Failed to send handshake') {
                $reason='handshake_failed';$report.partition_data_sent='no_handshake_failed_before_session'
            }
            throw $reason
        }
        $report.flash_tool_succeeded=$true;$report.success=$true;$report.partition_data_sent='tool_reported_success'
        Write-Host 'INSTALLAZIONE COMPLETATA. Ora prova il primo avvio Ubuntu Touch.'
        Write-Host 'Tieni Volume Giu + Power fino allo schermo nero, poi rilascia tutti i tasti.'
        Write-Host 'Il primo avvio puo richiedere alcuni minuti. Invia una foto della schermata ottenuta.'
    } catch {
        $report.error=$reason;Write-Host ('Installazione fermata: '+$reason)
        if ($report.flash_invoked) { Write-Host 'Lascia il telefono in Download Mode e invia il rapporto. Non ripetere la scrittura.' }
        else { Write-Host 'Nessuna scrittura di BOOT/SYSTEM avviata. Invia il rapporto per il controllo.' }
    } finally {
        foreach ($handle in $locks) { $handle.Dispose() }
        if (Test-Path -LiteralPath $private) { Remove-Item -LiteralPath $private -Force }
        [IO.File]::WriteAllText((Join-Path $directory 'ubuntu-install-report.json'),($report | ConvertTo-Json -Depth 8),(New-Object Text.UTF8Encoding($false)))
        $zip=Join-Path $Root 'ubuntu-install-report.zip';$index=1
        while (Test-Path -LiteralPath $zip) { $zip=Join-Path $Root ('ubuntu-install-report-'+$index+'.zip');$index++ }
        [IO.Compression.ZipFile]::CreateFromDirectory($directory,$zip,[IO.Compression.CompressionLevel]::Optimal,$false)
        Remove-Item -LiteralPath $directory -Recurse -Force
    }
    Write-Host ('Invia questo rapporto: '+$zip)
    return [pscustomobject]@{ Success=$report.success;Report=$report;ZipPath=$zip }
}

if ($MyInvocation.InvocationName -ne '.') {
    try { $result=Invoke-UtInstallation -Root $utInstallerRoot; if ($result.Success) { exit 0 };exit 1 }
    catch { Write-Host 'Estrai completamente il pacchetto strumenti e completa prima PREPARA-UBUNTU-TOUCH.cmd.';exit 2 }
}
