#!/bin/sh
# Runs only with the already-verified TWRP BusyBox. Never execute SYSTEM code.
BB=/sbin/busybox
root=''
mounted=false
mark() { printf 'UT_INSPECT_4: %s=%s\n' "$1" "$2"; }
fail() { mark error "$1"; exit 1; }
cleanup() {
    result=$?
    trap - EXIT HUP INT TERM
    if [ "$mounted" = true ]; then
        if "$BB" umount "$root"; then mounted=false; else
            mark error temporary_unmount_failed
            mark cleanup_confirmed false
            exit 1
        fi
    fi
    if [ -n "$root" ]; then
        "$BB" rmdir "$root" || { mark cleanup_confirmed false; exit 1; }
    fi
    mark cleanup_confirmed true
    exit "$result"
}
trap cleanup EXIT
trap 'exit 1' HUP INT TERM
[ "$($BB id -u)" = 0 ] || fail recovery_not_root
[ ! -L /tmp ] && [ -d /tmp ] || fail temporary_directory_invalid
"$BB" awk '$2=="/tmp" && $3=="tmpfs" {found=1} END {exit !found}' /proc/mounts || fail temporary_directory_not_ram
"$BB" test -b /dev/block/sda25 || fail system_not_block_device
[ "$($BB blockdev --getsize64 /dev/block/sda25)" = 5976883200 ] || fail system_partition_size_mismatch
system_node=$($BB readlink -f /dev/block/sda25)
case "$system_node" in /dev/block/sda25|/dev/sda25) ;; *) fail system_node_mismatch;; esac
# Refuse even an existing read-only mount: do not alter TWRP's current mounts.
while read -r source point filesystem options rest; do
    case "$source" in /dev/*)
        source=$($BB readlink -f "$source")
        [ "$source" != "$system_node" ] || fail system_already_mounted
        ;;
    esac
done </proc/mounts
umask 077
root=$($BB mktemp -d /tmp/ut-userspace-4.XXXXXX) || fail temporary_directory_failed
mark mount_options ro,noload,nosuid,nodev,noexec
mark mount_requested true
if ! "$BB" mount -n -t ext4 -o ro,noload,nosuid,nodev,noexec /dev/block/sda25 "$root"; then
    # Account for a tool returning an error after a successful mount syscall.
    if "$BB" awk -v p="$root" '$2==p {found=1} END {exit !found}' /proc/mounts; then mounted=true; fi
    fail read_only_mount_failed
fi
mounted=true
"$BB" awk -v p="$root" '$2==p && $3=="ext4" {
    n=split($4,a,","); for(i=1;i<=n;i++) v[a[i]]=1;
    if(v["ro"] && v["nosuid"] && v["nodev"] && v["noexec"] &&
       (v["noload"] || v["norecovery"]) && !v["rw"]) found=1
} END {exit !found}' /proc/mounts || fail read_only_mount_unconfirmed
mark mount_verified_read_only true

# Interpret absolute symlinks relative to the inspected root, never TWRP's root.
# Bounded resolution also prevents loops and escaping via '..'.
resolve() {
    remaining=${1#/}
    prefix=''
    count=0
    while [ -n "$remaining" ]; do
        count=$((count+1))
        [ "$count" -le 80 ] || return 1
        component=${remaining%%/*}
        case "$remaining" in */*) remaining=${remaining#*/};; *) remaining='';; esac
        case "$component" in ''|.) continue;; ..) prefix=${prefix%/*}; continue;; esac
        candidate="$root$prefix/$component"
        if [ -L "$candidate" ]; then
            target=$($BB readlink "$candidate") || return 1
            printf 'LINK %s -> %s\n' "$prefix/$component" "$target"
            case "$target" in /*) prefix='';; esac
            remaining="${target#/}${remaining:+/$remaining}"
        else
            prefix="$prefix/$component"
        fi
    done
    resolved="$root$prefix"
}
inspect() {
    path=$1
    printf '\nFILE %s\n' "$path"
    resolve "$path" || { printf 'RESOLUTION_FAILED\n'; return; }
    printf 'RESOLVED %s\n' "${resolved#"$root"}"
    if [ ! -e "$resolved" ]; then printf 'MISSING\n'; return; fi
    "$BB" stat -c 'META mode=%a uid=%u gid=%g bytes=%s type=%F' "$resolved"
    [ -f "$resolved" ] || return 0
    "$BB" sha256sum "$resolved"
    printf 'HEADER_HEX '
    "$BB" head -c 4096 "$resolved" | "$BB" od -An -v -tx1
    # No binary dump beyond the bounded ELF/shebang header.
    signature=$($BB head -c 2 "$resolved")
    case "$path:$signature" in *:"#!"|/etc/*:*|*.service:*|*.target:*|*/os-release:*)
        printf 'TEXT_BEGIN\n'
        "$BB" head -c 32768 "$resolved"
        printf '\nTEXT_END\n'
        ;;
    esac
}
for path in /init /sbin/init /etc/init /bin/init /bin/sh /lib/systemd/systemd /usr/lib/systemd/systemd \
    /lib/ld-linux-aarch64.so.1 /lib/aarch64-linux-gnu/libc.so.6 \
    /usr/lib/aarch64-linux-gnu/systemd/libsystemd-shared-255.so \
    /usr/lib/lxc-android-config/common.sh /usr/lib/os-release /etc/os-release /etc/fstab /etc/systemd/system/default.target \
    /lib/systemd/system/default.target /lib/systemd/system/android-container.service \
    /usr/lib/systemd/system/default.target /usr/lib/systemd/system/android-container.service \
    /usr/lib/systemd/system/halium-android.service /usr/lib/systemd/system/systemd-journald.service \
    /usr/lib/systemd/system/lightdm.service /usr/lib/systemd/system/graphical.target \
    /etc/systemd/journald.conf; do
    inspect "$path"
done
printf '\nRELATED_LIBRARY_NAMES\n'
for directory in /usr/lib/aarch64-linux-gnu/systemd /usr/lib/aarch64-linux-gnu; do
    resolve "$directory" || continue
    [ -d "$resolved" ] || continue
    "$BB" ls -l "$resolved" | "$BB" grep -E 'libsystemd|libc[.]so|libcap|libpam|libmount|libseccomp' | "$BB" head -c 16384
done
printf '\nSYSTEM_UNIT_NAMES\n'
for directory in /usr/lib/systemd/system /lib/systemd/system /etc/systemd/system; do
    resolve "$directory" || continue
    [ -d "$resolved" ] || continue
    "$BB" ls -1 "$resolved" | "$BB" grep -E 'android|halium|lomiri|lightdm|journal|writable|mount|udev' | "$BB" head -c 16384
done
printf '\nMOUNTS_DURING_INSPECTION\n'
"$BB" head -c 65536 /proc/mounts
mark status complete
