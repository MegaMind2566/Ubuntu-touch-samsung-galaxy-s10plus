#!/bin/bash
# Native Ubuntu arm64 package build only; never accesses or installs on a phone.
set -euo pipefail
export LC_ALL=C.UTF-8
PACKAGING=6391ffe9e12162de349fe595fdf8d92b5cbf443f
UPSTREAM=b8016a7210eba240788f262e1e4214576aa6fdd8
VERSION=1:14.0.0+r45-0ubports1+s10reconnect.20261105
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
OUTPUT_ROOT=${1:?Usage: build-linux-arm64.sh /absolute/output/directory}
JOBS=${JOBS:-2}
fail() { printf '%s\n' "$*" >&2; exit 1; }
[[ "$OUTPUT_ROOT" = /* ]] || fail "Output directory must be absolute."
[[ "$JOBS" =~ ^[1-9][0-9]?$ ]] || fail "JOBS must be 1..99."
for command in git sha256sum dpkg dpkg-query dpkg-checkbuilddeps dpkg-buildpackage quilt clang++ python3; do
    command -v "$command" >/dev/null || fail "Missing build tool: $command"
done
[[ $(dpkg --print-architecture) = arm64 ]] || fail "Use native arm64 userspace."
. /etc/os-release
[[ ${ID:-} = ubuntu && ${VERSION_ID:-} = 24.04 ]] || fail "Use Ubuntu 24.04 arm64."
[[ -z ${DEB_BUILD_OPTIONS:-} && -z ${DEB_BUILD_PROFILES:-} ]] || fail "Unset skipped-test build options/profiles."
[[ -n ${DEBFULLNAME:-} && -n ${DEBEMAIL:-} ]] || fail "Set DEBFULLNAME and DEBEMAIL for package provenance."
case "$DEBFULLNAME$DEBEMAIL" in *$'\n'*|*$'\r'*) fail "Invalid maintainer identity.";; esac
mkdir -p -- "$OUTPUT_ROOT"
JOB_DIR=$(mktemp -d "$OUTPUT_ROOT/adbd-reconnect.XXXXXXXX")
exec > >(tee "$JOB_DIR/build.log") 2>&1
trap 'status=$?; printf "exit_status=%s\n" "$status" > "$JOB_DIR/build-status.txt"; exit "$status"' EXIT
printf 'Build directory: %s\n' "$JOB_DIR"
dpkg-query -W > "$JOB_DIR/builder-package-versions.txt"
git -c core.autocrlf=false clone --depth 1 --branch android-14.0.0_r45 https://android.googlesource.com/platform/packages/modules/adb "$JOB_DIR/source"
git -c core.autocrlf=false clone --no-checkout https://gitlab.com/ubports/development/core/packaging/adbd.git "$JOB_DIR/packaging"
git -C "$JOB_DIR/packaging" checkout --detach "$PACKAGING"
[[ $(git -C "$JOB_DIR/packaging" rev-parse HEAD) = "$PACKAGING" ]] || fail "Packaging revision mismatch."
[[ $(git -C "$JOB_DIR/source" rev-parse HEAD) = "$UPSTREAM" ]] || fail "Android revision mismatch."
cp -a "$JOB_DIR/packaging/debian" "$JOB_DIR/source/debian"
cd -- "$JOB_DIR/source"
# Exact packaging contains a duplicate separator; this changes no dependency.
python3 - <<'PYTHON'
from pathlib import Path
p = Path('debian/control')
s = p.read_text()
assert s.count('liblz4-dev,,') == 1
p.write_text(s.replace('liblz4-dev,,', 'liblz4-dev,'))
PYTHON
printf '%s\n' 'Build-only packaging correction: liblz4-dev,, -> liblz4-dev,' > "$JOB_DIR/packaging-adjustments.txt"
export QUILT_PATCHES=debian/patches
quilt push -a
python3 "$SCRIPT_DIR/verify-adbd-reconnect.py" --source . --expect baseline --cxx clang++ --output "$JOB_DIR/baseline-tests"
cp "$SCRIPT_DIR/0001-adbd-functionfs-reconnect.patch" debian/patches/s10-functionfs-reconnect.patch
printf '\ns10-functionfs-reconnect.patch\n' >> debian/patches/series
quilt push
python3 "$SCRIPT_DIR/verify-adbd-reconnect.py" --source . --expect candidate --cxx clang++ --output "$JOB_DIR/candidate-tests"
S10_ADBD_VERSION="$VERSION" python3 - <<'PYTHON'
from datetime import datetime, timezone
import os
from pathlib import Path
version = os.environ['S10_ADBD_VERSION']
identity = f"{os.environ['DEBFULLNAME']} <{os.environ['DEBEMAIL']}>"
date = datetime(2026, 11, 5, tzinfo=timezone.utc).strftime('%a, %d %b %Y %H:%M:%S %z')
entry = f'''adbd ({version}) noble; urgency=medium

  * Local S10+ candidate: use explicit worker completion and retain FunctionFS
    control/bind state across transport reconnects; preserve secure auth.
  * Correct duplicate dependency separator in original packaging.

 -- {identity}  {date}

'''
p = Path('debian/changelog')
p.write_text(entry + p.read_text())
PYTHON
dpkg-checkbuilddeps
export SOURCE_DATE_EPOCH=1793836800
dpkg-buildpackage -us -uc -b -j"$JOBS"
cd -- "$JOB_DIR"
shopt -s nullglob
packages=( ./*.deb )
((${#packages[@]} >= 1)) || fail "No Debian package produced."
for package in "${packages[@]}"; do
    dpkg-deb -f "$package" Package Version Architecture Depends
done
sha256sum ./*.deb ./*.buildinfo ./*.changes > SHA256SUMS
printf '\nBUILD COMPLETE. Uninstalled candidate packages: %s\n' "$JOB_DIR"
