# Userdata runtime trial

These diagnostics support a guarded trial of the ARM64 candidate packages built
by the public repository's free GitHub runners. They are not a SYSTEM image,
package-manager upgrade or general installer for other phones.

The trial stages the complete extracted packages and original data identities in
a root-owned, non-writable userdata directory. Separate systemd drop-ins select
the staged daemon executables. Existing authentication and service dependencies
remain in the original units; no replacement libraries or `LD_LIBRARY_PATH` are
used. Every installed ELF dependency must first resolve against the handset.

For a private repowerd configuration directory, copy the exact original
`config-default.xml` as well as the separately pinned device profile. Setting
`REPOWERD_DEVICE_CONFIG_DIR` replaces the normal configuration directory; a
directory containing only the device XML is insufficient.

`diagnose.py` records hashes of actual running daemon executables, selected
startup messages, existing Android power-descriptor targets and bounded suspend
counters. It never opens `wakeup_count` or `autosleep`, enables Android autosuspend,
writes sysfs, or changes any preference. A boot-time caller must impose a service
deadline and keep the resulting local diagnostics separate from public evidence.

Rollback removes only the trial's two named drop-ins and diagnostic enablement,
then reboots into the retained baseline. Original daemons, BOOT and SYSTEM files
remain intact. If a later trial enables Android's autosuspend loop, a reboot is
required: removing a drop-in alone does not reset that process-lifetime latch.

Binary build success, runtime selection, USB reconnect, physical display response
and actual suspend/resume are distinct acceptance results. No status is promoted
until the corresponding evidence has been collected.
