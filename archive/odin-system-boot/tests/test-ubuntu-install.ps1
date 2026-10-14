$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.IO.Compression.FileSystem
. (Join-Path $PSScriptRoot '..\scripts\install-ubuntu-touch.ps1')
$script:UtTestRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\out\Ubuntu install with spaces'))
$script:UtTestMode='';$script:UtTestWrites=@();$script:UtTestUsb=@();$script:UtTestPhysical=@();$script:UtTestUuidReads=0
$script:UtTestInventory=[IO.File]::ReadAllText((Join-Path $PSScriptRoot '..\docs\recovery-check-2026-10-13.json')) | ConvertFrom-Json

function Assert-UtTest {
    param([bool]$Condition,[string]$Description)
    if (-not $Condition) { throw ('FAIL: '+$Description) }
}

$preflight={
    param([string]$Root)
    $state=[IO.File]::ReadAllText((Join-Path $Root 'ubuntu-local-state.json')) | ConvertFrom-Json
    return [pscustomobject]@{
        success=$true;backup_verified=($script:UtTestMode -ne 'backup')
        boot_path=(Join-Path $state.prepared_directory 'boot.img');system_path=(Join-Path $state.prepared_directory 'system.img')
        stock_firmware_path=$state.stock_firmware_path
    }
}
$inventory={
    param([string]$Root)
    $report=($script:UtTestInventory.recovery_check | ConvertTo-Json -Depth 12) | ConvertFrom-Json
    if ($script:UtTestMode -eq 'vendor-mounted') { $report.selected_mounts+=@{target='/vendor'} }
    return [pscustomobject]@{Success=($script:UtTestMode -ne 'recovery');Report=$report}
}
$metadata={
    param([string]$Executable,[string[]]$Arguments,[string]$Operation)
    Assert-UtTest ($Arguments.Count -eq 3 -and $Arguments[0] -ceq '-d' -and $Arguments[1] -ceq 'shell') 'metadata uses USB only'
    $expected='/sbin/busybox hexdump -v -s 1128 -n 16 -e ''1/1 "%02x"'' /dev/block/sda31'
    if ($Operation -eq 'data-magic') { $expected='/sbin/busybox hexdump -v -s 1080 -n 2 -e ''1/1 "%02x"'' /dev/block/sda31' }
    Assert-UtTest ($Arguments[2] -ceq $expected) 'exact bounded BusyBox metadata query only reads'
    $value='53 ef'
    if ($Operation -eq 'data-uuid') {
        $script:UtTestUuidReads++
        $value='aa '*16
        if ($script:UtTestUuidReads -eq 2 -and $script:UtTestMode -ne 'same-uuid') { $value='bb '*16 }
    } elseif ($script:UtTestMode -eq 'not-ext4') { $value='00 00' }
    $code=0;$error=''
    if ($script:UtTestMode -eq 'metadata-command') { $code=1;$error='hexdump: read error' }
    if ($script:UtTestMode -eq 'metadata-hex') { $value='not metadata' }
    return [pscustomobject]@{ExitCode=$code;TimedOut=$false;Stdout=$value;Stderr=$error}
}
$physical={
    param([string]$Step)
    $script:UtTestPhysical+=$Step
    return ($script:UtTestMode -ne $Step+'-cancel')
}
$usb={
    param([string]$Executable,[string[]]$Arguments,[int]$Timeout)
    $script:UtTestUsb+=,@($Arguments)
    Assert-UtTest (($Arguments -join '|') -ceq '--usb-backend|vcom|detect|--json') 'no standalone PIT or other native operation'
    $model='SM-G975F';if ($script:UtTestMode -eq 'model') { $model='SM-G975U' }
    return [pscustomobject]@{ExitCode=[int]($script:UtTestMode -eq 'usb');TimedOut=$false;Stdout=('{"modelName":"'+$model+'","serialNumber":"PRIVATE-HANDSET"}');Stderr=''}
}
$flash={
    param([string]$Executable,[string[]]$Arguments)
    $script:UtTestWrites+=,@($Arguments)
    $state=[IO.File]::ReadAllText((Join-Path $script:UtTestRoot 'ubuntu-local-state.json')) | ConvertFrom-Json
    $expected=@('--usb-backend','vcom','flash','--partition','SYSTEM',(Join-Path $state.prepared_directory 'system.img'),
                '--partition','BOOT',(Join-Path $state.prepared_directory 'boot.img'),'--no-reboot')
    Assert-UtTest (($Arguments -join '|') -ceq ($expected -join '|')) 'only SYSTEM then BOOT with native size checks and no reboot'
    Assert-UtTest (($script:UtTestPhysical -join '|') -ceq 'format-data|download-mode') 'manual format and Download steps precede flash'
    Assert-UtTest ($script:UtTestUuidReads -eq 2) 'new filesystem UUID verified before flash'
    foreach ($path in @($Arguments[5],$Arguments[8],$state.stock_firmware_path)) {
        $reader=[IO.File]::OpenRead($path);$reader.Dispose()
        $blocked=$false
        try { $writer=[IO.File]::Open($path,[IO.FileMode]::Open,[IO.FileAccess]::Write,[IO.FileShare]::ReadWrite);$writer.Dispose() }
        catch [IO.IOException] { $blocked=$true }
        Assert-UtTest $blocked 'images and full retained firmware remain immutable during flash'
    }
    $result=[pscustomobject]@{ExitCode=0;Stdout='Initializing protocol...';Stderr=''}
    if ($script:UtTestMode -eq 'handshake') { $result.ExitCode=1;$result.Stderr='ERROR: Unexpected handshake response! Failed to receive handshake response.' }
    if ($script:UtTestMode -eq 'flash') { $result.ExitCode=1;$result.Stderr='Failed sending '+$Arguments[5]+' serial: PRIVATE-HANDSET' }
    return $result
}

function Invoke-UtFixture {
    param([string]$Mode,[string]$Error,[bool]$Writes)
    $script:UtTestMode=$Mode;$script:UtTestWrites=@();$script:UtTestUsb=@();$script:UtTestPhysical=@();$script:UtTestUuidReads=0
    $result=Invoke-UtInstallation -Root $script:UtTestRoot -PreflightRunner $preflight -InventoryRunner $inventory -MetadataRunner $metadata -PhysicalRunner $physical -UsbRunner $usb -FlashRunner $flash
    Assert-UtTest ($result.Success -eq ($Mode -eq 'success')) ($Mode+': success')
    Assert-UtTest (([string]$result.Report.error) -ceq ([string]$Error)) ($Mode+': stage')
    Assert-UtTest ($result.Report.flash_invoked -eq $Writes -and $script:UtTestWrites.Count -eq [int]$Writes) ($Mode+': write only after all checks')
    Assert-UtTest (-not $result.Report.automatic_erase_requested -and -not $result.Report.automatic_reboot_requested -and -not $result.Report.repartition_requested) 'no automated erase, reboot or repartition'
    Assert-UtTest (-not $result.Report.ubuntu_touch_boot_verified) 'CI never claims hardware Ubuntu boot'
    Assert-UtTest ($result.Report.installer_version -eq 2) 'updated installer version recorded'
    if ($Mode -cin @('metadata-command','metadata-hex')) {
        Assert-UtTest ($script:UtTestPhysical.Count -eq 0 -and $script:UtTestUsb.Count -eq 0) 'failed metadata stops before any format prompt or Download request'
        Assert-UtTest ($result.Report.data_metadata_steps.Count -eq 1 -and $result.Report.data_metadata_steps[0].error) 'metadata failure diagnosed without saving UUID'
    }
    $zip=[IO.Compression.ZipFile]::OpenRead($result.ZipPath)
    try {
        Assert-UtTest ($zip.Entries.Count -eq 1 -and $zip.Entries[0].Name -ceq 'ubuntu-install-report.json') 'only sanitized JSON is shared'
        $reader=New-Object IO.StreamReader($zip.Entries[0].Open())
        try { $text=$reader.ReadToEnd() } finally { $reader.Dispose() }
        Assert-UtTest ($text -notmatch 'PRIVATE-HANDSET|serialNumber|stock_firmware_path|[A-Z]:\\|aaaaaaaaaaaaaaaa|bbbbbbbbbbbbbbbb') 'private paths, serial and filesystem UUID absent'
    } finally { $zip.Dispose() }
    return $result
}

function Invoke-UtNativeLauncher {
    param([string]$Launcher,[string]$Arguments)
    $info=New-Object Diagnostics.ProcessStartInfo
    $info.FileName=$env:ComSpec;$info.Arguments='/d /s /c ""'+$Launcher+'" '+$Arguments+' <nul"'
    $info.UseShellExecute=$false;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
    $process=New-Object Diagnostics.Process;$process.StartInfo=$info
    try {
        Assert-UtTest ($process.Start()) 'real CMD starts in path with spaces'
        $stdout=$process.StandardOutput.ReadToEndAsync();$stderr=$process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit(60000)) { $process.Kill();throw 'entry_point_timeout' }
        $process.WaitForExit()
        return [pscustomobject]@{ExitCode=$process.ExitCode;Stdout=$stdout.GetAwaiter().GetResult();Stderr=$stderr.GetAwaiter().GetResult()}
    } finally { $process.Dispose() }
}

try {
    $prepared=Join-Path $script:UtTestRoot ('prepared-ubuntu-'+'a'*32)
    $python=Join-Path $script:UtTestRoot 'tools\python\python.exe'
    $samloader=Join-Path $script:UtTestRoot 'tools\samloader\samloader.exe'
    $version=Invoke-DownloadCheckNative $samloader @('--version') 15
    Assert-UtTest ($version.ExitCode -eq 0 -and $version.Stdout.Trim() -ceq 'samloader 2.2.0') 'actual pinned samloader executable starts'
    Assert-UtTest ((Get-AuthenticodeSignature -LiteralPath $python).Status -eq 'Valid') 'publisher Python signature valid'
    $stock=Join-Path $script:UtTestRoot 'fixture-stock.zip'
    [IO.File]::WriteAllBytes($stock,@());& fsutil.exe sparse setflag $stock | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'sparse_fixture_failed' }
    $stream=[IO.File]::OpenWrite($stock);try { $stream.SetLength(6364940601) } finally { $stream.Dispose() }
    # Full-stock contents are substituted only by the injected test preflight.
    # Production verify_stock rejects this sparse placeholder by its hash.
    $state=@{schema=1;model='SM-G975F';pda='G975FXXSGHWC1';success=$true;backup_verified=$true;prepared_directory=$prepared;stock_firmware_path=$stock}
    [IO.File]::WriteAllText((Join-Path $script:UtTestRoot 'ubuntu-local-state.json'),($state | ConvertTo-Json))
    $null=Invoke-UtFixture 'success' $null $true
    foreach ($case in @(
        @('backup','image_or_backup_verification_failed',$false),@('recovery','recovery_preflight_failed',$false),
        @('vendor-mounted','system_or_vendor_mounted',$false),@('format-data-cancel','userdata_format_not_acknowledged',$false),
        @('same-uuid','userdata_format_not_completed',$false),@('not-ext4','userdata_metadata_after_format_failed',$false),
        @('metadata-command','userdata_metadata_before_format_failed',$false),@('metadata-hex','userdata_metadata_before_format_failed',$false),
        @('download-mode-cancel','download_mode_not_confirmed',$false),@('model','usb_model_not_confirmed',$false),
        @('usb','usb_model_not_confirmed',$false),@('handshake','handshake_failed',$true),@('flash','flash_failed',$true)
    )) { $result=Invoke-UtFixture $case[0] $case[1] $case[2]
        if ($case[0] -eq 'handshake') { Assert-UtTest ($result.Report.partition_data_sent -ceq 'no_handshake_failed_before_session') 'known pre-session failure distinguished' }
        if ($case[0] -eq 'flash') { Assert-UtTest ($result.Report.partition_data_sent -ceq 'unknown') 'later failure does not invent write progress' }
    }
    $boot=Join-Path $prepared 'boot.img';$stream=[IO.File]::OpenWrite($boot)
    try { $stream.WriteByte(88) } finally { $stream.Dispose() }
    $null=Invoke-UtFixture 'tampered' 'image_or_backup_verification_failed' $false
    Assert-UtTest ($script:UtTestPhysical.Count -eq 0 -and $script:UtTestUsb.Count -eq 0) 'tampered image stops before format or USB'
    $stream=[IO.File]::OpenWrite($boot);try { $stream.WriteByte(65) } finally { $stream.Dispose() }
    $stub=Join-Path $script:UtTestRoot 'local flash console stub.exe'
    Add-Type -TypeDefinition @'
using System;
public class S10UtFakeConsole {
    public static void Main(string[] args) {
        Console.WriteLine(string.Join("|",args));
        Console.Error.WriteLine("ERROR: Unexpected handshake response!");
        Environment.Exit(1);
    }
}
'@ -OutputAssembly $stub -OutputType ConsoleApplication
    $native=Invoke-UtFlash $stub 'system image.img' 'boot image.img'
    Assert-UtTest ($native.ExitCode -eq 1 -and $native.Stdout.Trim() -ceq '--usb-backend|vcom|flash|--partition|SYSTEM|system image.img|--partition|BOOT|boot image.img|--no-reboot' -and $native.Stderr -match 'Unexpected handshake') 'actual native argument quoting, concurrent streams and exit status'
    Remove-Item -LiteralPath (Join-Path $script:UtTestRoot 'ubuntu-local-state.json')
    $native=Invoke-UtNativeLauncher (Join-Path $script:UtTestRoot 'INSTALLA-UBUNTU-TOUCH.cmd') ''
    Assert-UtTest ($native.ExitCode -eq 1 -and $native.Stdout -match 'preparation_state_invalid') ('native installer: '+$native.Stdout+$native.Stderr)
    $native=Invoke-UtNativeLauncher (Join-Path $script:UtTestRoot 'PREPARA-UBUNTU-TOUCH.cmd') '-SystemArtifact "missing system.zip" -StockFirmware "missing stock.zip"'
    Assert-UtTest ($native.ExitCode -eq 1 -and $native.Stdout -match 'Preparazione fermata') ('native preparer: '+$native.Stdout+$native.Stderr)
    Assert-UtTest (-not (Test-Path -LiteralPath (Join-Path $script:UtTestRoot 'ubuntu-local-state.json'))) 'native failed preparation cannot retain a ready state'
    Write-Host 'PASS: actual boot/SYSTEM hashes, 15 staged success/failure cases, reduced BusyBox metadata queries, precise metadata/confirmation failures, immutable inputs, manual fresh-data proof, exact SYSTEM/BOOT command, native collector and both CMD entry points. USB and writes simulated; hardware boot remains unverified.'
} finally { Remove-Item -LiteralPath $script:UtTestRoot -Recurse -Force }
