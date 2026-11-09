@echo off
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
