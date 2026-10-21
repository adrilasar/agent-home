param([switch]$Remove)
$ErrorActionPreference = 'Stop'

$taskName = 'agent-home-sync'
if ($Remove) {
    $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if ($task) { $task | Unregister-ScheduledTask -Confirm:$false }
    return
}

$python = (& py -3 -c 'import sys; print(sys.executable)').Trim()
if ($LASTEXITCODE -ne 0) { throw 'Python 3.10 or newer is required (py -3).' }
$pythonw = Join-Path (Split-Path $python -Parent) 'pythonw.exe'
if (!(Test-Path -LiteralPath $pythonw)) { throw "Cannot find pythonw.exe: $pythonw" }
if (!(Test-Path "$HOME/.agent-home/state.json")) { throw 'Run install first.' }

$launcher = Join-Path "$HOME/.agent-home" 'windows_sync.pyw'
Copy-Item -LiteralPath "$PSScriptRoot/windows_sync.pyw" -Destination $launcher -Force
$action = New-ScheduledTaskAction -Execute $pythonw -Argument "`"$launcher`""
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes 15)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
    -Settings $settings -Description 'Personal instructions and skills from agent-home' -Force
