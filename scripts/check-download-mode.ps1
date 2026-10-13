# Download-mode inventory only. No partition write, erase or reboot command.
[CmdletBinding()]
param(
    [string]$SamloaderPath,
    [string]$OutputDirectory
)

# With Windows PowerShell 5.1 -File, script automatic variables can be empty
# during default-parameter evaluation. Resolve defaults inside the body.
$collectorScriptDirectory = [IO.Path]::GetDirectoryName($MyInvocation.MyCommand.Path)
if ([string]::IsNullOrEmpty($collectorScriptDirectory)) { throw 'collector_directory_unavailable' }
if ([string]::IsNullOrEmpty($SamloaderPath)) {
    $SamloaderPath = Join-Path $collectorScriptDirectory '..\tools\samloader\samloader.exe'
}
if ([string]::IsNullOrEmpty($OutputDirectory)) {
    $OutputDirectory = Join-Path $collectorScriptDirectory '..'
}

$script:DownloadCheckExeHash = 'b83b8244ecc86ecb4f5efc08e1604214d869838ca59b329e02a34e70832d175b'

function ConvertTo-DownloadCheckArgument {
    param([AllowEmptyString()][string]$Value)
    if ($Value.IndexOf([char]0) -ge 0) { throw 'invalid_native_argument' }
    $escaped = [regex]::Replace($Value, '(\\*)"', '$1$1\"')
    $escaped = [regex]::Replace($escaped, '(\\+)$', '$1$1')
    return '"' + $escaped + '"'
}

function Invoke-DownloadCheckNative {
    param([string]$Executable, [string[]]$Arguments, [int]$TimeoutSeconds)
    $info = New-Object System.Diagnostics.ProcessStartInfo
    $info.FileName = $Executable
    $info.Arguments = (($Arguments | ForEach-Object { ConvertTo-DownloadCheckArgument $_ }) -join ' ')
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $info
    try {
        if (-not $process.Start()) { throw 'native_start_failed' }
        $stdout = $process.StandardOutput.ReadToEndAsync()
        $stderr = $process.StandardError.ReadToEndAsync()
        $timedOut = -not $process.WaitForExit($TimeoutSeconds * 1000)
        if ($timedOut) { $process.Kill() }
        $process.WaitForExit()
        $outText = $stdout.GetAwaiter().GetResult()
        $errText = $stderr.GetAwaiter().GetResult()
        if ($outText.Length -gt 1048576 -or $errText.Length -gt 1048576) { throw 'native_output_limit' }
        return [pscustomobject]@{ ExitCode = $process.ExitCode; TimedOut = $timedOut; Stdout = $outText; Stderr = $errText }
    } finally { $process.Dispose() }
}

function Invoke-DownloadCheckCommand {
    param([string]$Executable, [string[]]$Arguments, [string]$PitPath, [int]$TimeoutSeconds, [scriptblock]$Runner)
    $allowed = $false
    if ($Arguments.Count -eq 1 -and $Arguments[0] -ceq '--version') { $allowed = $true }
    if ($Arguments.Count -eq 4 -and ($Arguments -join '|') -ceq '--usb-backend|vcom|detect|--json') { $allowed = $true }
    if ($Arguments.Count -eq 6 -and $Arguments[0] -ceq '--usb-backend' -and $Arguments[1] -ceq 'vcom' -and
        $Arguments[2] -ceq 'dump-pit' -and $Arguments[3] -ceq '--output' -and
        $Arguments[4] -ceq $PitPath -and $Arguments[5] -ceq '--no-reboot') { $allowed = $true }
    if ($Arguments.Count -eq 3 -and $Arguments[0] -ceq 'print-pit' -and $Arguments[1] -ceq '--file' -and
        $Arguments[2] -ceq $PitPath) { $allowed = $true }
    if (-not $allowed) { throw 'command_not_allowed' }
    if ($Runner) { return & $Runner $Executable $Arguments $TimeoutSeconds }
    return Invoke-DownloadCheckNative -Executable $Executable -Arguments $Arguments -TimeoutSeconds $TimeoutSeconds
}

function Read-DownloadCheckPitHeader {
    param([string]$Path)
    $file = Get-Item -LiteralPath $Path -ErrorAction Stop
    if ($file.Length -lt 28 -or $file.Length -gt 1048576) { throw 'pit_size_invalid' }
    $bytes = [System.IO.File]::ReadAllBytes($file.FullName)
    if ([BitConverter]::ToUInt32($bytes, 0) -ne 0x12349876) { throw 'pit_magic_invalid' }
    $count = [BitConverter]::ToUInt32($bytes, 4)
    if ($count -lt 1 -or $count -gt 512 -or $bytes.Length -lt (28 + 132 * $count)) { throw 'pit_entries_invalid' }
    $project = [Text.Encoding]::ASCII.GetString($bytes, 8, 8).TrimEnd([char]0)
    $cpu = [Text.Encoding]::ASCII.GetString($bytes, 16, 8).TrimEnd([char]0)
    if ($project -notmatch '^[A-Za-z0-9_\- ]{0,8}$' -or $cpu -notmatch '^[A-Za-z0-9_\- ]{0,8}$') { throw 'pit_tags_invalid' }
    return [ordered]@{
        entry_count = $count; project_name = $project; cpu_bootloader_tag = $cpu
        size_bytes = $bytes.Length; sha256 = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
    }
}

function Invoke-DownloadModeCheck {
    param([string]$Executable, [string]$Destination, [scriptblock]$Runner)
    $ErrorActionPreference = 'Stop'
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $Destination = [IO.Path]::GetFullPath($Destination)
    [IO.Directory]::CreateDirectory($Destination) | Out-Null
    $runDirectory = Join-Path $Destination ('download-check-' + [Guid]::NewGuid().ToString('N'))
    [IO.Directory]::CreateDirectory($runDirectory) | Out-Null
    $pitPath = Join-Path $runDirectory 'beyond2lte.pit'
    $report = [ordered]@{
        schema = 1; collector_version = 2; date_utc = [DateTime]::UtcNow.ToString('o')
        target_model = 'SM-G975F'; expected_samloader_version = '2.2.0'
        partition_writes = $false; erase_requested = $false; reboot_requested = $false
        detected_model = $null; model_confirmed_by_usb = $false; steps = @(); success = $false; error = $null
    }
    $success = $false
    $reason = 'executable_invalid'
    try {
        $hash = (Get-FileHash -LiteralPath $Executable -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($hash -cne $script:DownloadCheckExeHash) { throw 'executable_invalid' }
        $report.samloader_executable_sha256 = $hash
        $reason = 'version_failed'
        Write-Host 'Controllo dello strumento...'
        $result = Invoke-DownloadCheckCommand $Executable @('--version') $pitPath 15 $Runner
        $report.steps += [ordered]@{ operation = 'version'; exit_code = $result.ExitCode; timed_out = $result.TimedOut }
        if ($result.TimedOut -or $result.ExitCode -ne 0 -or $result.Stdout.Trim() -cne 'samloader 2.2.0') { throw $reason }
        $reason = 'usb_detection_failed'
        Write-Host 'Controllo del collegamento al telefono in Download Mode...'
        $result = Invoke-DownloadCheckCommand $Executable @('--usb-backend', 'vcom', 'detect', '--json') $pitPath 30 $Runner
        $report.steps += [ordered]@{ operation = 'detect'; exit_code = $result.ExitCode; timed_out = $result.TimedOut }
        if ($result.TimedOut -or $result.ExitCode -ne 0) { throw $reason }
        $reason = 'usb_response_invalid'
        $device = $result.Stdout | ConvertFrom-Json
        if (-not ($device.PSObject.Properties.Name -contains 'modelName')) { throw $reason }
        $model = ([string]$device.modelName).Trim()
        if ($model -and $model -notin @('SM-G975F', 'SM-G975F/DS')) { $reason = 'wrong_model'; throw $reason }
        if ($model) { $report.detected_model = $model; $report.model_confirmed_by_usb = $true }
        # The native detect response can include identifiers. Never persist that
        # response or its stderr; only the validated model above is retained.
        $reason = 'pit_download_failed'
        Write-Host 'Lettura della tabella delle partizioni...'
        $result = Invoke-DownloadCheckCommand $Executable @('--usb-backend', 'vcom', 'dump-pit', '--output', $pitPath, '--no-reboot') $pitPath 90 $Runner
        $report.steps += [ordered]@{ operation = 'dump-pit'; exit_code = $result.ExitCode; timed_out = $result.TimedOut }
        if ($result.TimedOut -or $result.ExitCode -ne 0) { throw $reason }
        $reason = 'pit_invalid'
        $report.pit = Read-DownloadCheckPitHeader $pitPath
        $reason = 'pit_decode_failed'
        $result = Invoke-DownloadCheckCommand $Executable @('print-pit', '--file', $pitPath) $pitPath 15 $Runner
        $report.steps += [ordered]@{ operation = 'print-pit-local'; exit_code = $result.ExitCode; timed_out = $result.TimedOut }
        if ($result.TimedOut -or $result.ExitCode -ne 0 -or $result.Stdout -notmatch '--- PIT Header ---') { throw $reason }
        [IO.File]::WriteAllText((Join-Path $runDirectory 'partition-table.txt'), $result.Stdout, (New-Object Text.UTF8Encoding($false)))
        $report.success = $true
        $success = $true
    } catch {
        # Do not put native stdout, stderr or arbitrary exception text in a report.
        $report.error = $reason
        if (Test-Path -LiteralPath $pitPath) { Remove-Item -LiteralPath $pitPath -Force }
        Write-Host 'Controllo non completato. Il rapporto contiene il punto in cui si e fermato.'
        if ($reason -eq 'usb_detection_failed') {
            Write-Host 'Controlla cavo, porta USB e driver Samsung. Chiudi Odin e Smart Switch.'
            Write-Host 'Driver ufficiale: https://developer.samsung.com/android-usb-driver'
        }
    } finally {
        [IO.File]::WriteAllText((Join-Path $runDirectory 'download-mode-report.json'), ($report | ConvertTo-Json -Depth 8), (New-Object Text.UTF8Encoding($false)))
        $zipPath = Join-Path $Destination 'download-mode-check.zip'
        $index = 1
        while (Test-Path -LiteralPath $zipPath) {
            $zipPath = Join-Path $Destination ('download-mode-check-' + $index + '.zip')
            $index++
        }
        [IO.Compression.ZipFile]::CreateFromDirectory($runDirectory, $zipPath, [IO.Compression.CompressionLevel]::Optimal, $false)
        Remove-Item -LiteralPath $runDirectory -Recurse -Force
    }
    if ($success) { Write-Host 'Controllo completato. Il telefono resta in Download Mode.' }
    Write-Host ('Invia questo file: ' + $zipPath)
    return [pscustomobject]@{ Success = $success; ZipPath = $zipPath; Report = $report }
}

if ($MyInvocation.InvocationName -ne '.') {
    try {
        $result = Invoke-DownloadModeCheck -Executable $SamloaderPath -Destination $OutputDirectory
        if ($result.Success) { exit 0 }
        exit 1
    } catch {
        Write-Host 'Impossibile creare il rapporto. Estrai lo ZIP in una cartella scrivibile e riprova.'
        exit 2
    }
}
