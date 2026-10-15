#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$ROOT/build/ubuntu-handoff"
mkdir -p "$ROOT/out/ubuntu-handoff-build"
python3 "$ROOT/scripts/early_boot_diagnostic.py" inputs
python3 "$ROOT/scripts/ubuntu_boot_handoff.py" inputs
python3 "$ROOT/scripts/prepare_boot_update.py" inputs --out "$ROOT/out"
python3 "$ROOT/scripts/prepare_build.py" --work "$WORK"
python3 "$ROOT/scripts/ubuntu_boot_handoff.py" configure --work "$WORK"
cp "$ROOT/out/boot-baseline/ramdisk.img" "$WORK/workdir/downloads/halium-boot-ramdisk.img"
cd "$WORK"
bash build/build.sh -b "$WORK/workdir" -o "$ROOT/out/ubuntu-handoff-build" 2>&1 | tee "$ROOT/out/ubuntu-handoff-build.log"
python3 "$ROOT/scripts/ubuntu_boot_handoff.py" finalize --work "$WORK"
python3 "$ROOT/tests/test_ubuntu_boot_handoff.py" --images "$ROOT/out/ubuntu-boot-handoff-images" --qemu qemu-aarch64
