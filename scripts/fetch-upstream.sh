#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="${1:-$ROOT/upstream}"
mkdir -p "$DEST"
URL="https://gitlab.com/ubports/porting/community-ports/android10/samsung-galaxy-s10/samsung-exynos9820.git"
if [[ ! -d "$DEST/samsung-exynos9820/.git" ]]; then
  git clone --branch halium-12 --single-branch "$URL" "$DEST/samsung-exynos9820"
else
  git -C "$DEST/samsung-exynos9820" fetch origin halium-12
fi
git -C "$DEST/samsung-exynos9820" checkout --detach FETCH_HEAD 2>/dev/null || true
test -s "$DEST/samsung-exynos9820/deviceinfo-beyond2lte"
test -s "$DEST/samsung-exynos9820/build.sh"
git -C "$DEST/samsung-exynos9820" rev-parse HEAD | tee "$DEST/upstream-revision.txt"
echo "Source checkout complete. No images have been built."
