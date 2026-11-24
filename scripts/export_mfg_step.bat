@echo off
if "%~1"=="" (
  docker compose run --rm pipeline python scripts/export_mfg_step.py
) else (
  set "ANTENNA_PROFILE=%~1"
  docker compose run --rm pipeline python scripts/export_mfg_step.py --profile %~1
)
