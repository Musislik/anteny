#!/usr/bin/env bash
set -e
if [ -n "${1:-}" ]; then
  ANTENNA_PROFILE="$1" docker compose --profile kicad-export run --rm kicad
else
  docker compose --profile kicad-export run --rm kicad
fi
