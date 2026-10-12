#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python3 "$ROOT/scripts/fetch_sources.py" --dest "${1:-$ROOT/upstream}"
test -s "${1:-$ROOT/upstream}/samsung-exynos9820/deviceinfo-beyond2lte"
echo "Pinned source checkout complete. No images have been built."
