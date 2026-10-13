[CmdletBinding()]
param([string]$PackageRoot, [string]$StockFirmware)
$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrEmpty($PackageRoot)) {
    $PackageRoot = Join-Path ([IO.Path]::GetDirectoryName($MyInvocation.MyCommand.Path)) '..'
}
$PackageRoot = [IO.Path]::GetFullPath($PackageRoot)
try {
    $python = Join-Path $PackageRoot 'tools\python\python.exe'
    $expectedHash = '7ca24f26d6e3f463419ee4f537ddd3acd312c38fe45e678cce08572f26a8bd1a'
    if ((Get-FileHash -LiteralPath $python -Algorithm SHA256).Hash.ToLowerInvariant() -cne $expectedHash) {
        throw 'Python runtime hash mismatch'
    }
    if ([string]::IsNullOrEmpty($StockFirmware)) {
        $expectedName = 'SM-G975F-ITV-G975FXXSGHWC1.zip'
        $parent = [IO.Directory]::GetParent($PackageRoot.TrimEnd('\')).FullName
        $candidates = @((Join-Path $PackageRoot ('firmware\' + $expectedName)), (Join-Path $parent ('firmware\' + $expectedName)))
        foreach ($directory in @(Get-ChildItem -LiteralPath $parent -Directory -Filter 'UbuntuTouch*')) {
            $candidates += Join-Path $directory.FullName ('firmware\' + $expectedName)
        }
        foreach ($candidate in $candidates) {
            if (Test-Path -LiteralPath $candidate -PathType Leaf) { $StockFirmware = $candidate; break }
        }
    }
    if ([string]::IsNullOrEmpty($StockFirmware)) {
        Add-Type -AssemblyName System.Windows.Forms
        $dialog = New-Object System.Windows.Forms.OpenFileDialog
        $dialog.Title = 'Seleziona il firmware originale SM-G975F ITV HWC1 gia scaricato'
        $dialog.Filter = 'Firmware Samsung ZIP (*.zip)|*.zip'
        $dialog.FileName = 'SM-G975F-ITV-G975FXXSGHWC1.zip'
        $dialog.InitialDirectory = [IO.Directory]::GetParent($PackageRoot.TrimEnd('\')).FullName
        try {
            if ($dialog.ShowDialog() -ne [Windows.Forms.DialogResult]::OK) {
                Write-Host 'Preparazione annullata. Nessuna operazione sul telefono.'
                exit 1
            }
            $StockFirmware = $dialog.FileName
        } finally { $dialog.Dispose() }
    }
    if (-not (Test-Path -LiteralPath $StockFirmware -PathType Leaf)) { throw 'Stock firmware file missing' }
    $scriptPath = Join-Path $PackageRoot 'scripts\prepare_recovery.py'
    & $python -I $scriptPath --root $PackageRoot --stock-firmware $StockFirmware
    exit $LASTEXITCODE
} catch {
    Write-Host 'Avvio non riuscito. Estrai tutto lo ZIP in una cartella scrivibile e riprova.'
    exit 2
}
