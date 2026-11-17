#!/usr/bin/env bash
set -e
docker compose --profile kicad-export run --rm kicad
