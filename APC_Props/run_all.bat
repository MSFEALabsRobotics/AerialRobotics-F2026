@echo off
REM Build every APC propeller in this folder, one folder each.
REM Safe to re-run: --resume skips whatever is already written.
setlocal
cd /d "%~dp0"

echo.
echo === What this machine can do ===
python apc_prop.py --check
if errorlevel 1 goto :nopython

echo.
echo === Building into ALL_PROPS ===
echo This takes 30 to 60 minutes for the full archive.
echo.
python apc_prop.py . ALL_PROPS --split --step-ruled --resume

echo.
echo Done. Each propeller has its own folder under ALL_PROPS.
echo A summary is in ALL_PROPS\summary.csv
pause
goto :eof

:nopython
echo.
echo Python did not run. Install it from python.org and tick
echo "Add python.exe to PATH", then run this file again.
pause
