#!/usr/bin/env bash
# ==============================================================================
# export_gerber.sh - Pohodlný skript pro export Gerber a Drill dat z KiCad 8
# Spouští scripts/export_gerber.py s automatickou detekcí kicad-cli / Dockeru.
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${PROJECT_ROOT}"
python3 "${SCRIPT_DIR}/export_gerber.py" "$@"
