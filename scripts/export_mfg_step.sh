#!/usr/bin/env bash
set -e
if [ -n "${1:-}" ]; then
  ANTENNA_PROFILE="$1" docker compose run --rm pipeline python scripts/export_mfg_step.py --profile "$1"
else
  docker compose run --rm pipeline python scripts/export_mfg_step.py
fi
