#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
echo "[1/3] Running unit & security test suite..."
python3 -m unittest discover -s tests -v

echo "[2/3] Running Nebius Token Factory model catalog selfcheck..."
python3 -m nemotron_forge.cli selfcheck

echo "[3/3] Executing 5-stage Nemotron Forge verification pipeline..."
python3 -m nemotron_forge.cli demo --mode simulated --seed 42 --out-dir artifacts
echo "Done. Artifacts written to artifacts/latest_run.json, artifacts/latest_run.md, and FEEDBACK.md."
