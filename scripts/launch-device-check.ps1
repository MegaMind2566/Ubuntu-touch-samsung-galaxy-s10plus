param(
    [string]$Adb = '',
    [string]$Output = '',
    [ValidateRange(0,120)][int]$WaitSeconds = 60
)
$ErrorActionPreference = 'Stop'
$packageRoot = Split-Path -Parent $PSScriptRoot
if (-not $Adb) { $Adb = Join-Path $packageRoot 'platform-tools\adb.exe' }
if (-not $Output) { $Output = Join-Path $packageRoot 'beyond2lte-device-report.json' }
$errorFile = Join-Path $packageRoot 'errore-controllo.txt'

function Invoke-LocalAdb([string[]]$Arguments) {
    $ErrorActionPreference = 'Continue'
    $lines = & $Adb @Arguments 2>&1
    return @{ lines = @($lines | ForEach-Object { $_.ToString() }); exit_code = $LASTEXITCODE }
}

try {
    Write-Host 'Controllo Galaxy S10+ - lettura di firmware e partizioni.'
    Write-Host 'Collega il S10+ via USB, sblocca lo schermo e abilita Debug USB.'
    Write-Host 'Accetta sul telefono la richiesta di autorizzazione di questo PC.'
    Write-Host ''
    if (-not (Get-Command $Adb -ErrorAction SilentlyContinue)) { throw 'ADB non trovato. Estrai tutto lo ZIP prima di avviare il controllo.' }
    $server = Invoke-LocalAdb -Arguments @('start-server')
    $server.lines | Out-Host
    if ($server.exit_code -ne 0) { throw 'Impossibile avviare ADB sul PC.' }
    $deadline = (Get-Date).AddSeconds($WaitSeconds)
    do {
        $state = Invoke-LocalAdb -Arguments @('devices')
        if ($state.exit_code -ne 0) { throw 'Impossibile interrogare ADB.' }
        $authorized = @($state.lines | Where-Object { $_ -match '^\S+\s+device\s*$' })
        if ($authorized.Count -gt 1) { throw 'Collega soltanto il S10+. Sono presenti piu dispositivi autorizzati.' }
        if ($authorized.Count -eq 1) { break }
        if ((Get-Date) -ge $deadline) { throw 'Telefono non autorizzato o non rilevato. Controlla Debug USB, autorizzazione sul telefono e cavo dati. Per i driver consulta LEGGIMI.txt.' }
        Start-Sleep -Seconds 1
    } while ($true)
    & (Join-Path $PSScriptRoot 'collect-device.ps1') -Adb $Adb -Output $Output
    if (Test-Path -LiteralPath $errorFile) { Remove-Item -LiteralPath $errorFile }
    Write-Host ''
    Write-Host 'Controllo completato. Invia in chat questo file:'
    Write-Host $Output
} catch {
    $message = $_.Exception.Message
    $message | Set-Content -Encoding UTF8 -LiteralPath $errorFile
    Write-Host ''
    Write-Host ('Controllo non completato: ' + $message)
    Write-Host 'Puoi inviare errore-controllo.txt per verificare il problema.'
    exit 1
}
