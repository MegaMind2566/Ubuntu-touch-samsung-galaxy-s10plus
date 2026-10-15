#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$ROOT/build/early-diagnostic"
mkdir -p "$ROOT/out/early-build"
python3 "$ROOT/scripts/early_boot_diagnostic.py" inputs
python3 "$ROOT/scripts/prepare_boot_update.py" inputs --out "$ROOT/out"
python3 "$ROOT/scripts/prepare_build.py" --work "$WORK"
python3 "$ROOT/scripts/early_boot_diagnostic.py" configure --work "$WORK"
cp "$ROOT/out/boot-baseline/ramdisk.img" "$WORK/workdir/downloads/halium-boot-ramdisk.img"
cd "$WORK"
bash build/build.sh -b "$WORK/workdir" -o "$ROOT/out/early-build" 2>&1 | tee "$ROOT/out/early-diagnostic-build.log"
python3 "$ROOT/scripts/early_boot_diagnostic.py" finalize --work "$WORK"
python3 "$ROOT/tests/test_early_boot_diagnostic.py" --images "$ROOT/out/early-boot-diagnostic-images" --qemu qemu-aarch64
