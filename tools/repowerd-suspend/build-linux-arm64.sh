#!/bin/bash
# Run only in a prepared Ubuntu 24.04 arm64 builder. No phone access or installation.
set -euo pipefail
export LC_ALL=C.UTF-8
BASE=36575160752bdd0a983bee1b53e041ccc4ceaa60
PATCH_SHA256=a811a6547382f9f757678694f9582c1dc9988ef18f3743cd7680e9bb9b9c41c5
PACKAGE_VERSION=2025.09+s10hidl.20261105
ACTIVATION=${S10_ENABLE_AIDL_ACTIVATION:-0}
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PATCH="$SCRIPT_DIR/0001-upstream-system-suspend-hidl.patch"
OUTPUT_ROOT=${1:?Usage: build-linux-arm64.sh /absolute/output/directory}
JOBS=${JOBS:-2}
fail() { printf '%s\n' "$*" >&2; exit 1; }
[[ ${GITHUB_ACTIONS:-} = true ]] || fail "Use only the public GitHub Actions ARM64 workflow; local builds are disabled."
[[ "$OUTPUT_ROOT" = /* ]] || fail "Output directory must be absolute."
[[ "$ACTIVATION" = 0 || "$ACTIVATION" = 1 ]] || fail "Activation option must be 0 or 1."
if [[ "$ACTIVATION" = 1 ]]; then PACKAGE_VERSION=2025.09+s10hidlactivate.20261105; fi
[[ "$JOBS" =~ ^[1-9][0-9]?$ ]] || fail "JOBS must be 1..99."
for command in git sha256sum dpkg dpkg-query dpkg-vendor dpkg-checkbuilddeps dpkg-buildpackage pkg-config python3 cmake ctest; do
    command -v "$command" >/dev/null || fail "Missing build tool: $command"
done
[[ $(dpkg --print-architecture) = arm64 ]] || fail "Use an arm64 userspace; cross-builds are not validated."
[[ $(dpkg-vendor --query vendor) = Ubuntu ]] || fail "Use Ubuntu so upstream enables hybris."
. /etc/os-release
[[ ${ID:-} = ubuntu && ${VERSION_ID:-} = 24.04 ]] || fail "Use Ubuntu 24.04 arm64."
dpkg --validate-version "$PACKAGE_VERSION" || fail "Invalid candidate package version."
[[ -z ${DEB_BUILD_OPTIONS:-} && -z ${DEB_BUILD_PROFILES:-} ]] || fail "Unset skipped-test build options/profiles."
[[ -n ${DEBFULLNAME:-} && -n ${DEBEMAIL:-} ]] || fail "Set DEBFULLNAME and DEBEMAIL for package provenance."
case "$DEBFULLNAME$DEBEMAIL" in *$'\n'*|*$'\r'*) fail "Invalid maintainer identity.";; esac
printf '%s  %s\n' "$PATCH_SHA256" "$PATCH" | sha256sum -c -
pkg-config --exists libgbinder libandroid-properties deviceinfo gio-2.0 gio-unix-2.0 || fail "Missing compatible UBports/GLib development packages."
mkdir -p -- "$OUTPUT_ROOT"
JOB_DIR=$(mktemp -d "$OUTPUT_ROOT/repowerd-hidl.XXXXXXXX")
exec > >(tee "$JOB_DIR/build.log") 2>&1
trap 'status=$?; printf "exit_status=%s\n" "$status" > "$JOB_DIR/build-status.txt"; exit "$status"' EXIT
printf 'Candidate source=%s patch=%s version=%s\n' "$BASE" "$PATCH_SHA256" "$PACKAGE_VERSION"
printf 'Build directory: %s\n' "$JOB_DIR"
dpkg-query -W > "$JOB_DIR/builder-package-versions.txt"
pkg-config --modversion libgbinder libandroid-properties deviceinfo gio-2.0 gio-unix-2.0 > "$JOB_DIR/pkg-config-versions.txt"
git -c core.autocrlf=false clone --no-checkout https://gitlab.com/ubports/development/core/repowerd.git "$JOB_DIR/source"
cd -- "$JOB_DIR/source"
git config core.autocrlf false
git checkout --detach "$BASE"
[[ $(git rev-parse HEAD) = "$BASE" ]] || fail "Source revision mismatch."
git apply --check "$PATCH"
git apply "$PATCH"
if [[ "$ACTIVATION" = 1 ]]; then
    PATCH2="$SCRIPT_DIR/activation/0002-guarded-android-autosuspend.patch"
    EXPECTED_PATCH2=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["patch2_sha256"])' "$SCRIPT_DIR/activation/candidate.json")
    printf '%s  %s\n' "$EXPECTED_PATCH2" "$PATCH2" | sha256sum -c -
    git apply --check "$PATCH2"
    git apply "$PATCH2"
    python3 "$SCRIPT_DIR/activation/verify-adapter.py" --source . --output "$JOB_DIR/activation-tests"
fi
git diff --check
dpkg-checkbuilddeps
S10_HIDL_VERSION="$PACKAGE_VERSION" S10_HIDL_ACTIVATION="$ACTIVATION" python3 - <<'PY'
from datetime import datetime, timezone
import os
from pathlib import Path
version = os.environ['S10_HIDL_VERSION']
activation_note = " Guarded SDK32 AIDL activation candidate also applied." if os.environ["S10_HIDL_ACTIVATION"] == "1" else ""
identity = f"{os.environ['DEBFULLNAME']} <{os.environ['DEBEMAIL']}>"
date = datetime(2026, 11, 5, tzinfo=timezone.utc).strftime('%a, %d %b %Y %H:%M:%S %z')
entry = f'''repowerd ({version}) noble; urgency=medium

  * Local source-only S10+ candidate: unchanged upstream SystemSuspend HIDL
    backport d87b74538c368cd7bebef64c5b81c5c377ae3f88.
  * Runtime suspend behavior remains unvalidated.{activation_note}

 -- {identity}  {date}

'''
path = Path('debian/changelog')
path.write_text(entry + path.read_text(encoding='utf-8'), encoding='utf-8')
PY
git diff --check
export SOURCE_DATE_EPOCH=1793836800
dpkg-buildpackage -us -uc -b -j"$JOBS"
cd -- "$JOB_DIR"
shopt -s nullglob
packages=( ./*.deb )
((${#packages[@]} >= 3)) || fail "Expected matching daemon, data and tools packages."
for package in "${packages[@]}"; do
    printf '\nPackage: %s\n' "$package"
    dpkg-deb -f "$package" Package Version Architecture Depends
done
sha256sum ./*.deb ./*.buildinfo ./*.changes > SHA256SUMS
printf '\nBUILD COMPLETE. Uninstalled candidate packages: %s\n' "$JOB_DIR"
