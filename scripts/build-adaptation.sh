#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="${1:-$ROOT/build/port}"
mkdir -p "$ROOT/out"
python3 "$ROOT/scripts/prepare_build.py" --work "$WORK" 2>&1 | tee "$ROOT/out/build.log"
WORK="$(realpath "$WORK")"
cp "$WORK/source-manifest.json" "$ROOT/out/source-manifest.json"
trap 'if [[ -f "$WORK/workdir/downloads/KERNEL_OBJ/.config" ]]; then cp "$WORK/workdir/downloads/KERNEL_OBJ/.config" "$ROOT/out/kernel.config"; fi' EXIT
cd "$WORK"
bash build/build.sh -b "$WORK/workdir" -o "$ROOT/out" 2>&1 | tee -a "$ROOT/out/build.log"
cp "$WORK/workdir/tmp/partitions/boot.img" "$ROOT/out/boot.img"
cp "$WORK/workdir/downloads/KERNEL_OBJ/.config" "$ROOT/out/kernel.config"
sha256sum "$WORK/workdir/downloads/halium-boot-ramdisk.img" > "$ROOT/out/ramdisk.sha256"
python3 "$ROOT/scripts/validate-artifacts.py" "$ROOT/out"
