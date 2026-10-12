param(
    [string]$Serial = '',
    [string]$Adb = 'adb',
    [string]$Output = '.\beyond2lte-device-report.json'
)
$ErrorActionPreference = 'Stop'

# Read-only ADB inventory. No reboot, root, unlock, wipe or flash commands.
if (-not (Get-Command $Adb -ErrorAction SilentlyContinue)) {
    throw 'ADB non trovato. Indica il percorso con -Adb oppure usa la cartella Android platform-tools.'
}
$devices = @(& $Adb devices | Select-Object -Skip 1 | Where-Object { $_ -match '^\S+\s+device\s*$' })
if ($LASTEXITCODE -ne 0) { throw 'Impossibile interrogare ADB.' }
if (-not $Serial) {
    if ($devices.Count -ne 1) { throw 'Serve un solo telefono autorizzato in ADB, oppure il parametro -Serial.' }
    $Serial = ($devices[0] -split '\s+')[0]
}
$adbArgs = @('-s', $Serial)
function Read-Adb([string[]]$Arguments) {
    $ErrorActionPreference = 'Continue'
    $lines = & $Adb @adbArgs @Arguments 2>&1
    $result = ($lines | ForEach-Object { $_.ToString() }) -join "`n"
    return @{ text = $result.Trim(); exit_code = $LASTEXITCODE }
}

$keys = @(
    'ro.product.model', 'ro.product.device', 'ro.board.platform', 'ro.hardware',
    'ro.build.version.release', 'ro.build.version.sdk', 'ro.build.display.id',
    'ro.build.version.security_patch', 'ro.boot.bootloader',
    'ro.vendor.build.fingerprint', 'ro.vendor.build.version.release',
    'ro.vendor.build.version.sdk', 'ro.vendor.build.security_patch',
    'ro.boot.flash.locked', 'ro.boot.vbmeta.device_state', 'ro.boot.verifiedbootstate',
    'ro.boot.warranty_bit', 'ro.boot.slot_suffix'
)
$properties = [ordered]@{}
foreach ($key in $keys) { $properties[$key] = Read-Adb -Arguments @('shell', 'getprop', $key) }
$model = $properties['ro.product.model'].text
$device = $properties['ro.product.device'].text
if ($model -notmatch '^SM-G975F(?:/DS)?$' -or $device -notmatch '^beyond2lte') {
    throw "Dispositivo diverso dal target: $model / $device. Nessun report generato."
}

# /sys/class/block/*/size is expressed in 512-byte sectors, including UFS.
$partitionCommand = @'
for n in boot BOOT recovery RECOVERY system SYSTEM vendor VENDOR userdata USERDATA dtbo DTBO vbmeta VBMETA; do
  for base in /dev/block/by-name /dev/block/platform/13d60000.ufs/by-name; do
    p="$base/$n"
    [ -e "$p" ] || continue
    dev=$(readlink -f "$p")
    block=${dev##*/}
    sectors=$(cat "/sys/class/block/$block/size" 2>/dev/null)
    logical=$(cat "/sys/class/block/$block/queue/logical_block_size" 2>/dev/null)
    printf '%s|%s|%s|%s\n' "$n" "$dev" "$sectors" "$logical"
    break
  done
done
'@
$partitionCommand = $partitionCommand -replace "`r`n", "`n"
$partitions = Read-Adb -Arguments @('shell', $partitionCommand)
$report = [ordered]@{
    captured_utc = [DateTime]::UtcNow.ToString('o')
    target = 'SM-G975F/DS beyond2lte'
    read_only = $true
    properties = $properties
    partitions = $partitions
    proc_partitions = Read-Adb -Arguments @('shell', 'cat', '/proc/partitions')
    kernel = Read-Adb -Arguments @('shell', 'uname', '-a')
    # Deliberately omit IMEI, phone numbers, accounts and ADB serial.
}
$report | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 -LiteralPath $Output
Write-Host "Report creato: $Output"
