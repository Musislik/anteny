@echo off
setlocal
if not "%~1"=="" (
    set "ANTENNA_PROFILE=%~1"
)
docker compose --profile kicad-export run --rm kicad
endlocal
