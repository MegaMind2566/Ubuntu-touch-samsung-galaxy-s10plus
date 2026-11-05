$ErrorActionPreference='Stop'
$root=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
. (Join-Path $root 'scripts/check-boot-usb.ps1') -PackageRoot $root
function Assert-BootUsb([bool]$Condition,[string]$Message) { if (-not $Condition) { throw $Message } }
$privateId='USB\VID_18D1&PID_D001&MI_00\PRIVATE_SERIAL_FIXTURE'
$compositeId='USB\VID_1209&PID_0004\PRIVATE_SERIAL_FIXTURE'
Assert-BootUsb ((Get-BootUsbIdentifier $privateId) -ceq 'VID_18D1&PID_D001&MI_00') 'Serial must be stripped from USB IDs'
Assert-BootUsb (Test-BootUsbCandidate $privateId 'Failed to boot') 'Pinned Halium gadget must be retained'
Assert-BootUsb (Test-BootUsbCandidate $compositeId 'USB Composite Device') 'Observed normal-boot composite must be retained with a generic Windows name'
Assert-BootUsb (Test-BootUsbCandidate 'usb\vid_1209&pid_0004&mi_00\fixture' 'USB interface') 'Observed gadget interfaces must match case-insensitively'
Assert-BootUsb ((Get-BootUsbIdentifier $compositeId) -ceq 'VID_1209&PID_0004') 'Composite serial must be stripped'
foreach ($pidCode in @('0002','0003','0005')) {
    Assert-BootUsb (Test-BootUsbCandidate ('USB\VID_1209&PID_'+$pidCode+'\fixture') 'USB Composite Device') 'Recovered MTP/ADB/RNDIS configuration IDs must be retained'
    Assert-BootUsb (Test-BootUsbCandidate ('USB\VID_1209&PID_'+$pidCode+'&MI_01\fixture') 'ADB Interface') 'Documented gadget interface nodes must be retained'
}
foreach ($pidCode in @('0001','0006')) {
    Assert-BootUsb (-not (Test-BootUsbCandidate ('USB\VID_1209&PID_'+$pidCode+'\fixture') 'Unrelated mouse')) 'Other products from vendor 1209 must remain excluded'
}
Assert-BootUsb (-not (Test-BootUsbCandidate 'USB\VID_1209&PID_0003&MI_001\fixture' 'ADB Interface')) 'Interface suffix must contain exactly two hexadecimal digits'
Assert-BootUsb (-not (Test-BootUsbCandidate 'USB\VID_1209&PID_00040\fixture' 'USB Composite Device')) 'Product match must not accept longer lookalike IDs'
Assert-BootUsb (-not (Test-BootUsbCandidate 'USB\VID_9999&PID_0001\fixture' 'Unrelated mouse')) 'Unrelated USB device must be omitted'
Assert-BootUsb (-not (Test-BootUsbCandidate 'PCI\VEN_8086\fixture' 'Remote NDIS')) 'Names must not widen the query to non-USB devices'
Assert-BootUsb ((ConvertTo-BootUsbName 'serialno=PRIVATE_SERIAL_FIXTURE') -cnotmatch 'PRIVATE_SERIAL_FIXTURE') 'Explicit serial fields must be redacted'
Assert-BootUsb ((Get-BootUsbIdentifier 'malformed') -eq $null) 'Malformed ID must not be copied'

# A cached RNDIS adapter from an earlier connection is not live boot evidence.
function Get-PnpDevice {
    [CmdletBinding()]param([switch]$PresentOnly)
    return @(
        [pscustomobject]@{InstanceId=$privateId;FriendlyName='Halium initrd Failed to boot';Class='Net';Status='OK'},
        [pscustomobject]@{InstanceId=$compositeId;FriendlyName='USB Composite Device';Class='USB';Status='OK'}
    )
}
function Get-CimInstance {
    [CmdletBinding()]param([string]$ClassName)
    return @(
        [pscustomobject]@{PNPDeviceID=$privateId;Name='RNDIS';NetEnabled=$true;NetConnectionStatus=2},
        [pscustomobject]@{PNPDeviceID='USB\VID_18D1&PID_D001&MI_00\DISCONNECTED_SERIAL';Name='RNDIS';NetEnabled=$false;NetConnectionStatus=7}
    )
}
$snapshot=Get-BootUsbSnapshot
Assert-BootUsb ($snapshot.usb_network_adapters.Count -eq 1) 'Disconnected cached network adapter must be excluded'
Assert-BootUsb ($snapshot.devices.Count -eq 2) 'Live generic composite must be included in the snapshot'
Assert-BootUsb (@($snapshot.devices | Where-Object {$_.usb_id -ceq 'VID_1209&PID_0004'}).Count -eq 1) 'Snapshot must retain the observed gadget identity'
Assert-BootUsb (($snapshot | ConvertTo-Json -Depth 8) -cnotmatch 'PRIVATE_SERIAL_FIXTURE') 'Live snapshot must omit serial suffixes'

# Simulated snapshots exercise report serialization. The actual cmdlet calls
# are tested separately by the native CMD invocation on this disposable VM.
function Get-BootUsbSnapshot {
    return [ordered]@{date_utc=[DateTime]::UtcNow.ToString('o');devices=@(
        @{usb_id=(Get-BootUsbIdentifier $privateId);name='Halium initrd Failed to boot';class='USB';status='Error'}
    );usb_network_adapters=@();errors=@()}
}
function Start-Sleep { param([int]$Seconds) }
$folder=Join-Path $root ('out/USB fixture '+[Guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory($folder) | Out-Null
try {
    $result=Invoke-BootUsbCheck -Root $folder
    Assert-BootUsb $result.Success 'Simulated USB report should be collected'
    $json=$result.Report | ConvertTo-Json -Depth 8
    Assert-BootUsb ($json -cnotmatch 'PRIVATE_SERIAL_FIXTURE') 'Report must not contain the fixture serial'
    Assert-BootUsb (-not $result.Report.phone_commands_requested) 'Collector must not request phone commands'
    Assert-BootUsb (-not $result.Report.network_changes_requested) 'Collector must not request network changes'
    Assert-BootUsb (-not $result.Report.ubuntu_touch_boot_verified) 'USB fixture cannot certify Ubuntu userspace'
    Assert-BootUsb ($result.Report.snapshots.Count -eq 3) 'All three snapshots must be retained'
} finally { Remove-Item -LiteralPath $folder -Recurse -Force }
Write-Host 'USB filters, serial omission and report boundaries: passed'
