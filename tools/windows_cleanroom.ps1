# Run inside a fresh Windows Sandbox. Only input and result folders are mapped.
$ErrorActionPreference='Stop'
$result='C:\ShogiResults'
$exe='C:\ShogiTest\ShogiAnalyzer\ShogiAnalyzer.exe'
function Environment-Snapshot {
    [ordered]@{
        time=(Get-Date).ToString('o')
        os=(Get-CimInstance Win32_OperatingSystem).Caption
        build=[Environment]::OSVersion.Version.ToString()
        python_commands=@(Get-Command python,python3,py,pip,pip3,php,node -ErrorAction SilentlyContinue | Select-Object Name,Source)
        python_registry=@('HKLM:\SOFTWARE\Python','HKLM:\SOFTWARE\WOW6432Node\Python','HKCU:\SOFTWARE\Python' | Where-Object {Test-Path $_})
        system_vcruntime140=(Test-Path "$env:windir\System32\vcruntime140.dll")
        system_vcruntime140_1=(Test-Path "$env:windir\System32\vcruntime140_1.dll")
    }
}
function Run-Captured([string]$file,[string]$arguments,[string]$name) {
    $process=New-Object System.Diagnostics.Process
    $process.StartInfo.FileName=$file
    $process.StartInfo.Arguments=$arguments
    $process.StartInfo.UseShellExecute=$false
    $process.StartInfo.RedirectStandardOutput=$true
    $process.StartInfo.RedirectStandardError=$true
    [void]$process.Start()
    $stdout=$process.StandardOutput.ReadToEndAsync()
    $stderr=$process.StandardError.ReadToEndAsync()
    if(-not $process.WaitForExit(60000)){throw "Timed out: $name"}
    $process.WaitForExit()
    [IO.File]::WriteAllText("$result\$name.stdout.txt",$stdout.GetAwaiter().GetResult())
    [IO.File]::WriteAllText("$result\$name.stderr.txt",$stderr.GetAwaiter().GetResult())
    if($process.ExitCode -ne 0){throw "Failed: $name, exit $($process.ExitCode)"}
}
try {
    $before=Environment-Snapshot
    $before | ConvertTo-Json -Depth 5 | Set-Content "$result\baseline.json" -Encoding UTF8
    if($before.python_commands.Count -or $before.python_registry.Count -or $before.system_vcruntime140 -or $before.system_vcruntime140_1){throw 'Expected a fresh OS without Python or system VC runtime'}
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [IO.Compression.ZipFile]::ExtractToDirectory('C:\ShogiInput\ShogiAnalyzer.zip','C:\ShogiTest')
    Run-Captured $exe '--self-check' 'direct-executable'
    Run-Captured $env:ComSpec '/d /c "C:\ShogiTest\ShogiAnalyzer\Start.bat --self-check"' 'start-bat'
    # A console is required for the probe's CTRL_BREAK shutdown test. This opens
    # only the application's test process; it performs no GUI automation.
    $probe=Start-Process -FilePath $exe -ArgumentList '--engine-python C:\ShogiInput\cleanroom_probe.py --exe C:\ShogiTest\ShogiAnalyzer\ShogiAnalyzer.exe --fixture C:\ShogiInput\fixture.kif --peer C:\ShogiInput\fake_usi.py --output C:\ShogiResults\probe.json' -PassThru
    if(-not $probe.WaitForExit(180000)){throw 'Application probe timeout'}
    $report=Get-Content "$result\probe.json" -Raw | ConvertFrom-Json
    if(-not $report.ok){throw 'Application probe failed (see probe.json)'}
    $after=Environment-Snapshot
    $after | ConvertTo-Json -Depth 5 | Set-Content "$result\after.json" -Encoding UTF8
    if($after.python_commands.Count -or $after.python_registry.Count -or $after.system_vcruntime140 -or $after.system_vcruntime140_1){throw 'Application installed an unexpected system runtime'}
    # Leave the extracted distribution untouched. Regression fixtures and the
    # mock engine configuration belong only to the probe's application-data.
    [ordered]@{ok=$true;direct_executable=$true;start_bat=$true;system_runtimes_installed=$false;kept_open_for_inspection=$true} | ConvertTo-Json | Set-Content "$result\summary.json" -Encoding UTF8
    @'
ShogiAnalyzer inspection environment

Open C:\ShogiTest\ShogiAnalyzer and double-click Start.bat.
Then open http://localhost:31145 in the Sandbox browser.

The extracted application has no initial settings or mock engine configured.
This Sandbox has networking DISABLED: real engine downloads cannot complete here.
Use a separate network-enabled fresh Sandbox to inspect the normal first-run setup.

Automated regression results are in C:\ShogiResults.
Only those automated tests use a controlled USI peer, NOT a real shogi engine.
Python / PHP / VC++ runtime have NOT been installed in this Windows OS.
The required VC++ DLLs are inside the application's _internal folder.

Keep this Windows Sandbox open until you finish inspecting it.
'@ | Set-Content "$env:USERPROFILE\Desktop\ShogiAnalyzer-inspection.txt" -Encoding UTF8
} catch {
    [ordered]@{ok=$false;error=$_.Exception.Message;detail=($_|Out-String)} | ConvertTo-Json -Depth 5 | Set-Content "$result\error.json" -Encoding UTF8
    exit 1
}
