$ErrorActionPreference='Stop'
$root=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
. (Join-Path $root 'scripts/check-boot-usb.ps1') -PackageRoot $root
function Assert-BootUsb([bool]$Condition,[string]$Message) { if (-not $Condition) { throw $Message } }
$privateId='USB\VID_18D1&PID_D001&MI_00\PRIVATE_SERIAL_FIXTURE'
Assert-BootUsb ((Get-BootUsbIdentifier $privateId) -ceq 'VID_18D1&PID_D001&MI_00') 'Serial must be stripped from USB IDs'
Assert-BootUsb (Test-BootUsbCandidate $privateId 'Failed to boot') 'Pinned Halium gadget must be retained'
Assert-BootUsb (-not (Test-BootUsbCandidate 'USB\VID_9999&PID_0001\fixture' 'Unrelated mouse')) 'Unrelated USB device must be omitted'
Assert-BootUsb (-not (Test-BootUsbCandidate 'PCI\VEN_8086\fixture' 'Remote NDIS')) 'Names must not widen the query to non-USB devices'
Assert-BootUsb ((ConvertTo-BootUsbName 'serialno=PRIVATE_SERIAL_FIXTURE') -cnotmatch 'PRIVATE_SERIAL_FIXTURE') 'Explicit serial fields must be redacted'
Assert-BootUsb ((Get-BootUsbIdentifier 'malformed') -eq $null) 'Malformed ID must not be copied'

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
