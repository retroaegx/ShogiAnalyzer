"""Launchers also keep Windows' running executable outside the replacement tree."""
from pathlib import Path

WINDOWS = r'''@echo off
setlocal DisableDelayedExpansion
set "SA_UPDATE_INSTALL=%~dp0"
if exist "%~dp0.UpdateRecovery.bat" goto recovery
if exist "%~dp0ShogiAnalyzer.exe" goto native
if exist "%~dp0.venv\Scripts\python.exe" goto venv
python "%~dp0installer\update.py" & pause & exit /b
:venv
"%~dp0.venv\Scripts\python.exe" "%~dp0installer\update.py" & pause & exit /b
:native
set "SA_UPDATE_JOB=%TEMP%\ShogiAnalyzer-update-%RANDOM%-%RANDOM%"
"%~dp0ShogiAnalyzer.exe" --prepare-update "%SA_UPDATE_JOB%"
if errorlevel 1 goto failed
rem Transfer execution outside this installation before it is replaced.
"%SA_UPDATE_JOB%\RunUpdate.bat"
:recovery
"%~dp0.UpdateRecovery.bat"
:failed
pause
exit /b 1
'''

POSIX = '''#!/bin/sh
main() {
    here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd) || return 1
    if [ -f "$here/.UpdateRecovery.sh" ]; then
        sh "$here/.UpdateRecovery.sh"
        return $?
    fi
    if [ -x "$here/ShogiAnalyzer" ]; then
        job=$(mktemp -d "${TMPDIR:-/tmp}/ShogiAnalyzer-update-XXXXXX") || return 1
        if ! "$here/ShogiAnalyzer" --prepare-update "$job"; then
            rmdir "$job" 2>/dev/null
            return 1
        fi
        "$job/ShogiAnalyzer" --update-job "$job/job.json"
        result=$?
        "$here/ShogiAnalyzer" --cleanup-update "$job"
        return "$result"
    fi
    if [ -x "$here/.venv/bin/python" ]; then
        "$here/.venv/bin/python" "$here/installer/update.py"
    else
        python3 "$here/installer/update.py"
    fi
}
main "$@"; exit "$?"
'''


def write_launchers(folder: Path, system: str):
    if system == 'win32':
        (folder/'Update.bat').write_text(WINDOWS, encoding='utf-8', newline='\r\n')
    else:
        for name in (('Update.sh', 'Update.command') if system == 'darwin' else ('Update.sh',)):
            (folder/name).write_text(POSIX, encoding='utf-8', newline='\n'); (folder/name).chmod(0o755)
    (folder/'.shogianalyzer-update.lock').touch(exist_ok=True)
