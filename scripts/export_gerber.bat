@echo off
REM ==============================================================================
REM export_gerber.bat - Windows dávkový soubor pro export Gerber a Drill dat
REM ==============================================================================

set SCRIPT_DIR=%~dp0
set PROJECT_ROOT=%SCRIPT_DIR%..

cd /d "%PROJECT_ROOT%"
python "%SCRIPT_DIR%export_gerber.py" %*
