#!/bin/sh
# Data-only, bounded inspection. No existing service or device is modified.
set -u
set -f
umask 077
ulimit -c 0
ulimit -f 2048
BASE=/userdata/ubuntu-touch-graphics-probe-1
ASSETS=$BASE/assets
LOG=$BASE/run-1
ARMED=$BASE/armed
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH

fail() { printf 'UT_GRAPHICS_PROBE_1: %s\n' "$1" >&2; exit 1; }
owned_dir() {
    [ -d "$1" ] && [ ! -L "$1" ] &&
    [ "$(stat -c '%u:%g:%a' "$1")" = "0:0:755" ]
}
[ "$(id -u)" = 0 ] || fail root_required
owned_dir "$BASE" || fail unsafe_base
owned_dir "$ASSETS" || fail unsafe_assets
for file in probe.sh mapper-probe.py; do
    [ -f "$ASSETS/$file" ] && [ ! -L "$ASSETS/$file" ] &&
    [ "$(stat -c '%u:%g:%a:%h' "$ASSETS/$file")" = "0:0:644:1" ] || fail unsafe_asset
done
[ -f "$ARMED" ] && [ ! -L "$ARMED" ] &&
[ "$(stat -c '%u:%g:%a:%h:%s' "$ARMED")" = "0:0:600:1:26" ] || fail unsafe_marker
[ "$(cat "$ARMED")" = UT_GRAPHICS_PROBE_1_ARMED ] || fail marker_mismatch
[ ! -e "$LOG" ] && [ ! -L "$LOG" ] || fail already_ran
for command in /usr/bin/python3 /usr/bin/timeout /usr/sbin/runuser /usr/bin/env; do
    [ -x "$command" ] || fail required_command_missing
done
mkdir -m 700 "$LOG" || fail log_creation_failed
rm -- "$ARMED" || fail marker_consumption_failed
SUMMARY=$LOG/01-summary.txt
printf 'UT_GRAPHICS_PROBE_1\nstarted_uptime=' >"$SUMMARY"
cat /proc/uptime >>"$SUMMARY"
printf 'Controlled UID comparison; runuser/PAM, environment and AppArmor can differ from live LightDM sessions.\n' >>"$SUMMARY"
trap 'rm -f -- "$LOG/.capture.tmp"' EXIT
trap 'printf "interrupted\n" >>"$SUMMARY"; exit 1' HUP INT TERM

# Every subprocess has a wall-clock timeout and a 1 MiB temporary file limit.
# Retain bounded head and tail so a loader's final error is not lost to strace.
# Unit RuntimeMaxSec bounds the whole process tree.
capture() {
    name=$1
    seconds=$2
    shift 2
    /usr/bin/timeout -k 1 "$seconds" "$@" >"$LOG/.capture.tmp" 2>&1
    result=$?
    if [ "$(stat -c '%s' "$LOG/.capture.tmp")" -gt 524288 ]; then
        {
            head -c 65536 "$LOG/.capture.tmp"
            printf '\n[output truncated; tail follows]\n'
            tail -c 458688 "$LOG/.capture.tmp"
        } >"$LOG/$name"
    else
        cat "$LOG/.capture.tmp" >"$LOG/$name"
    fi
    rm -f -- "$LOG/.capture.tmp"
    printf '%s exit=%s\n' "$name" "$result" >>"$SUMMARY"
    return 0
}

capture 02-inventory-start.json 10 /usr/bin/python3 -I "$ASSETS/mapper-probe.py" --inventory
capture 03-systemd.txt 5 /usr/bin/systemctl show lightdm.service lxc-android-config.service \
    -p ActiveState -p SubState -p MainPID -p Result -p ExecMainStatus -p FragmentPath -p DropInPaths

# Let the existing boot continue. No Before/Requires relationship with LightDM.
waited=0
while [ ! -S /run/mir_socket ] && [ "$waited" -lt 20 ]; do
    sleep 1
    waited=$((waited + 1))
done
printf 'mir_socket_wait_seconds=%s\n' "$waited" >>"$SUMMARY"

android_logs() {
    capture "$1" 6 /usr/bin/lxc-attach -n android -- /system/bin/logcat \
        -b all -d -t 500 -v threadtime \
        '*:S' 'GraphicBufferMapper:V' 'Gralloc4:V' 'Gralloc3:V' 'Gralloc2:V' \
        'Gralloc:V' 'gralloc:V' 'libc:E' 'linker:V' 'hwservicemanager:V' 'UTGraphicsProbe:V' \
        'HidlServiceManagement:V' 'vndksupport:V' 'libvndksupport:V' 'GrallocPassthrough:V'
}
android_logs 04-android-before.txt

probe_user() {
    who=$1
    home=$2
    filename=$3
    if [ -x /usr/bin/strace ]; then
        capture "$filename" 15 /usr/bin/strace -f -qq -s 160 \
            -e trace=openat,access,faccessat,newfstatat,readlink \
            /usr/sbin/runuser -u "$who" -- /usr/bin/env -i \
            PATH="$PATH" HOME="$home" USER="$who" LOGNAME="$who" \
            LD_PRELOAD=/usr/lib/aarch64-linux-gnu/libtls-padding.so \
            HYBRIS_LOGGING_LEVEL=debug HYBRIS_LD_DEBUG=1 \
            /usr/bin/python3 -I "$ASSETS/mapper-probe.py"
    else
        capture "$filename" 15 /usr/sbin/runuser -u "$who" -- /usr/bin/env -i \
            PATH="$PATH" HOME="$home" USER="$who" LOGNAME="$who" \
            LD_PRELOAD=/usr/lib/aarch64-linux-gnu/libtls-padding.so \
            HYBRIS_LOGGING_LEVEL=debug HYBRIS_LD_DEBUG=1 \
            /usr/bin/python3 -I "$ASSETS/mapper-probe.py"
    fi
}
probe_user root /root 05-root-probe.txt
probe_user phablet /home/phablet 06-phablet-probe.txt
probe_user lightdm /var/lib/lightdm 07-lightdm-probe.txt
android_logs 08-android-after.txt
capture 09-inventory-end.json 10 /usr/bin/python3 -I "$ASSETS/mapper-probe.py" --inventory
capture 10-journal.txt 6 /usr/bin/journalctl -b --no-pager -n 180 \
    -u lightdm.service -u lxc-android-config.service -u ubuntu-touch-graphics-probe.service
printf 'UT_GRAPHICS_PROBE_1: inspection completed\nuptime=' >"$LOG/11-complete.txt"
cat /proc/uptime >>"$LOG/11-complete.txt"
printf 'complete\n' >>"$SUMMARY"
exit 0
