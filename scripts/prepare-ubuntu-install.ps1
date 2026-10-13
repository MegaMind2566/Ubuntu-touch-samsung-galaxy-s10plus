[CmdletBinding()]
param([string]$PackageRoot,[string]$SystemArtifact,[string]$StockFirmware)
$ErrorActionPreference = 'Stop'
$ubuntuPreparationDirectory = [IO.Path]::GetDirectoryName($MyInvocation.MyCommand.Path)
if ([string]::IsNullOrEmpty($PackageRoot)) { $PackageRoot = Join-Path $ubuntuPreparationDirectory '..' }
$PackageRoot = [IO.Path]::GetFullPath($PackageRoot)

function Select-UbuntuInstallInput {
    param([string]$Title, [string]$Provided)
    if ($Provided) { return [IO.Path]::GetFullPath($Provided) }
    Add-Type -AssemblyName System.Windows.Forms
    $dialog = New-Object Windows.Forms.OpenFileDialog
    $dialog.Title = $Title; $dialog.Filter = 'File ZIP (*.zip)|*.zip'
    $dialog.CheckFileExists = $true; $dialog.Multiselect = $false
    try {
        if ($dialog.ShowDialog() -ne [Windows.Forms.DialogResult]::OK) { throw 'file_selection_cancelled' }
        return $dialog.FileName
    } finally { $dialog.Dispose() }
}

try {
    $python = Join-Path $PackageRoot 'tools\python\python.exe'
    if ((Get-FileHash -LiteralPath $python -Algorithm SHA256).Hash.ToLowerInvariant() -cne '7ca24f26d6e3f463419ee4f537ddd3acd312c38fe45e678cce08572f26a8bd1a') { throw 'python_invalid' }
    $SystemArtifact = Select-UbuntuInstallInput 'Seleziona beyond2lte-ubuntu24-system-1.zip scaricato da GitHub' $SystemArtifact
    if (-not $StockFirmware) {
        # Reuse the private stock path retained by the earlier preparation.
        # Search only sibling project folders, not the PC or personal files.
        foreach ($folder in @(Get-ChildItem -LiteralPath ([IO.Path]::GetDirectoryName($PackageRoot)) -Directory -Filter 'UbuntuTouch*')) {
            $statePath = Join-Path $folder.FullName 'recovery-local-state.json'
            if (Test-Path -LiteralPath $statePath) {
                try {
                    $state = [IO.File]::ReadAllText($statePath) | ConvertFrom-Json
                    if ($state.report.backup_verified -and (Test-Path -LiteralPath $state.stock_firmware_path)) { $StockFirmware = $state.stock_firmware_path; break }
                } catch { }
            }
        }
    }
    $StockFirmware = Select-UbuntuInstallInput 'Seleziona il firmware originale SM-G975F-ITV-G975FXXSGHWC1.zip' $StockFirmware
    & $python -I (Join-Path $PackageRoot 'scripts\prepare_ubuntu_install.py') --root $PackageRoot --artifact $SystemArtifact --stock-firmware $StockFirmware
    exit $LASTEXITCODE
} catch {
    Write-Host 'Preparazione non avviata. Seleziona i due ZIP corretti ed estrai completamente il pacchetto strumenti.'
    exit 2
}
