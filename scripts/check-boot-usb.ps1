# Host-only USB observations while the phone attempts a normal Ubuntu boot.
# No ADB/Odin, device shell, driver/network changes, partition access or reboot.
[CmdletBinding()]
param([string]$PackageRoot)
$bootUsbDirectory = [IO.Path]::GetDirectoryName($MyInvocation.MyCommand.Path)
if ([string]::IsNullOrEmpty($PackageRoot)) { $PackageRoot = Join-Path $bootUsbDirectory '..' }
$bootUsbRoot = [IO.Path]::GetFullPath($PackageRoot)

function Get-BootUsbIdentifier {
    param([string]$InstanceId)
    if ($InstanceId -match '(?i)^USB\\(VID_([0-9a-f]{4})&PID_([0-9a-f]{4})(?:&MI_[0-9a-f]{2})?)\\') {
        return $Matches[1].ToUpperInvariant()
    }
    return $null
}

function Test-BootUsbCandidate {
    param([string]$InstanceId,[string]$Name)
    # Includes Samsung and the actual pinned Halium panic gadget 18D1:D001.
    # RNDIS/Halium names also cover usb-moded's other USB IDs.
    return ($InstanceId -match '(?i)^USB\\VID_(04E8|18D1|1D6B|0FCE)&PID_' -or
            ($InstanceId -match '(?i)^USB\\' -and $Name -match '(?i)Halium|GNU/Linux|RNDIS|Remote NDIS'))
}

function ConvertTo-BootUsbName {
    param([string]$Value)
    $Value = [regex]::Replace($Value,'(?i)(serialno|imei|imsi|meid)\s*[=:]\s*\S+','$1=<redacted>')
    $Value = [regex]::Replace($Value,'[\x00-\x1f]',' ')
    if ($Value.Length -gt 256) { $Value = $Value.Substring(0,256) }
    return $Value
}

function Get-BootUsbSnapshot {
    $snapshot = [ordered]@{date_utc=[DateTime]::UtcNow.ToString('o');devices=@();usb_network_adapters=@();errors=@()}
    try {
        foreach ($device in @(Get-PnpDevice -PresentOnly -ErrorAction Stop)) {
            if (-not (Test-BootUsbCandidate ([string]$device.InstanceId) ([string]$device.FriendlyName))) { continue }
            $snapshot.devices += [ordered]@{
                usb_id=Get-BootUsbIdentifier ([string]$device.InstanceId)
                class=ConvertTo-BootUsbName ([string]$device.Class)
                name=ConvertTo-BootUsbName ([string]$device.FriendlyName)
                status=ConvertTo-BootUsbName ([string]$device.Status)
            }
            if ($snapshot.devices.Count -ge 32) { break }
        }
    } catch { $snapshot.errors += 'pnp_query_unavailable' }
    try {
        foreach ($adapter in @(Get-CimInstance Win32_NetworkAdapter -ErrorAction Stop)) {
            if (-not (Test-BootUsbCandidate ([string]$adapter.PNPDeviceID) ([string]$adapter.Name))) { continue }
            $snapshot.usb_network_adapters += [ordered]@{
                usb_id=Get-BootUsbIdentifier ([string]$adapter.PNPDeviceID)
                description=ConvertTo-BootUsbName ([string]$adapter.Name)
                enabled=$adapter.NetEnabled
                connection_status=$adapter.NetConnectionStatus
            }
            if ($snapshot.usb_network_adapters.Count -ge 16) { break }
        }
    } catch { $snapshot.errors += 'usb_network_query_unavailable' }
    return $snapshot
}

function Invoke-BootUsbCheck {
    param([string]$Root)
    $ErrorActionPreference='Stop'
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $directory=Join-Path $Root ('boot-usb-check-'+[Guid]::NewGuid().ToString('N'))
    [IO.Directory]::CreateDirectory($directory) | Out-Null
    $report=[ordered]@{
        schema=1;collector_version=1;date_utc=[DateTime]::UtcNow.ToString('o');target_model='SM-G975F'
        observed_stage='user_requested_normal_boot_at_samsung_logo';host_read_only=$true
        phone_commands_requested=$false;driver_changes_requested=$false;network_changes_requested=$false
        partition_writes=$false;reboot_requested=$false;ubuntu_touch_boot_verified=$false
        snapshots=@();success=$false;error=$null
        note='USB evidence can show a running initramfs/rootfs. An absent USB interface does not prove the kernel never ran.'
    }
    try {
        Write-Host 'Lettura dei dispositivi USB presenti. Lascia il telefono sul logo, USB collegato.'
        for ($index=0;$index -lt 3;$index++) {
            if ($index -gt 0) { Start-Sleep -Seconds 5 }
            $report.snapshots += Get-BootUsbSnapshot
        }
        $report.success=(@($report.snapshots | Where-Object {$_.errors.Count -eq 0}).Count -gt 0)
        if (-not $report.success) { $report.error='windows_usb_queries_unavailable' }
    } catch { $report.error='windows_usb_collection_failed' }
    finally {
        [IO.File]::WriteAllText((Join-Path $directory 'boot-usb-report.json'),($report | ConvertTo-Json -Depth 8),(New-Object Text.UTF8Encoding($false)))
        $zip=Join-Path $Root 'ubuntu-boot-usb-report.zip';$number=1
        while (Test-Path -LiteralPath $zip) { $zip=Join-Path $Root ('ubuntu-boot-usb-report-'+$number+'.zip');$number++ }
        [IO.Compression.ZipFile]::CreateFromDirectory($directory,$zip,[IO.Compression.CompressionLevel]::Optimal,$false)
        # Only remove this fresh, collector-owned host folder.
        Remove-Item -LiteralPath $directory -Recurse -Force
    }
    Write-Host ('Invia questo file: '+$zip)
    return [pscustomobject]@{Success=$report.success;ZipPath=$zip;Report=$report}
}

if ($MyInvocation.InvocationName -ne '.') {
    try { $value=Invoke-BootUsbCheck -Root $bootUsbRoot;if ($value.Success) { exit 0 };exit 1 }
    catch { Write-Host 'Impossibile creare il rapporto. Estrai lo ZIP in una cartella scrivibile.';exit 2 }
}
