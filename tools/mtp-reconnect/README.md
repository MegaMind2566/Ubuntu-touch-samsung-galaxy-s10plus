# MTP reconnect user-session candidate

Source-only candidate prepared 5 November 2026. It has not yet passed Linux/private-bus CI or a handset reconnect trial. Nineteen interpreted parser/lifecycle fixtures passed on Windows; two real Gio/private-bus cases await free GitHub Actions. The required physical `USB_STATE` event source was confirmed on the phone with the candidate not running.

## Exact baseline and observed failure

The handset uses `mtp-server` and `libmtpserver1` version `0.1.0~20260518151229.67~4f4ce14+ubports24.04.2`, official [mtp source commit 4f4ce14c3b81bfabfd9ed3acfe158561c4c1c703](https://gitlab.com/ubports/development/core/mtp/-/commit/4f4ce14c3b81bfabfd9ed3acfe158561c4c1c703). The running watcher is a Python user service; the native server uses dbus-cpp/Boost, not Qt.

In `src/MtpServer.cpp:176`, a request-read `EIO` leaves the server loop. `server/server.cpp` then exits normally. The shipped `mtp-server.service` uses `Restart=always`, a 100 ms default delay, and a 60-start/30-second limit. After the guided physical disconnect, the native service reached `start-limit-hit`, `NRestarts=61`, while the watcher remained running. Windows still had a functioning MTP interface driver, but no portable-device namespace. This explains why an enumerated USB interface alone did not imply an available MTP server. The possible relationship to seven preceding suspend `EBUSY` attempts is unproven.

The shipped `debian/mtp-server-usb-moded-watcher` listens only to `sig_usb_current_state_ind`; it never sees a new event if the selected mode stays `mtp_adb`. Official usb-moded upstream `dd4f9303bd8c48c35071accfd046bb1b7b171771` exports `sig_usb_event_ind` with `USB connected`/`USB disconnected`, but those are cable-detector events preceding mode readiness. A continuous read-only monitor across one user-confirmed physical unplug/replug observed **no usb-moded D-Bus signals**, while kernel `android_usb/android0` emitted `DISCONNECTED`, `CONNECTED`, then `CONFIGURED`. The selected mode remained `mtp_adb`. That confirms the original watcher misses this handset's physical transition.

The unprivileged protocol-15/group-1 listener was verified. The device path was `/devices/virtual/android_usb/android0`, action `change`, subsystem `android_usb`. During disconnect the Android state file correctly showed `DISCONNECTED`, whereas UDC state still showed stale `configured`; at connect it showed `CONNECTED`/UDC `addressed`, then both became configured. The candidate uses the observed kernel event source and Android state bootstrap, not UDC state. The approximately 15.87-second disconnected interval was an observation of existing software, not candidate acceptance.

## Narrow correction

`mtp-usb-watcher.py` replaces only the user watcher command. It subscribes to kernel `NETLINK_KOBJECT_UEVENT` protocol 15/group 1 before reading `/sys/class/android_usb/android0/state`. Only complete kernel-sender-PID-zero events for `android_usb`, final device name `android0`, and exact `CONFIGURED`/`CONNECTED`/`DISCONNECTED` states are accepted. Userspace messages, truncated datagrams, malformed/duplicate properties and unrelated devices are ignored. A lost/erroring event source stops MTP and exits; no periodic health polling is used.

The native server may run only when the physical state is `CONFIGURED` and usb-moded currently reports `mtp` or `mtp_adb`. Disconnected, merely connected, busy, unknown or non-MTP mode requests `StopUnit`. A new ready edge calls `ResetFailedUnit` for **only** `mtp-server.service`, then `RestartUnit` to reopen its native device descriptor. `RestartUnit` also covers a rapid reconnect whose start could otherwise replace a queued stop before the old process exits. Repeated ready states do not interrupt an ongoing transfer. USB mode-owner loss stops MTP; its return requires a fresh read-only mode query.

Received events are drained in bounded batches and coalesced; any disconnect invalidates the previous descriptor before the final ready state is considered. The current Android state is read again before resetting the unit failure and after that acknowledgment, immediately before requesting restart. A historical `CONFIGURED` event or a disconnect during the mode/reset call cannot authorize a start from the old state. Kernel and mode proxies use no-auto-start flags; querying their state does not activate an absent service.

`mtp-server-reconnect.conf` sets `Restart=no`, removing the disconnected restart race even before the watcher handles the event. Connected server faults become visible and wait for a new legitimate ready edge; this is a deliberate trial limitation, not a hidden retry loop. `mtp-watcher-reconnect.conf` also sets `Restart=no`; setup or bus failures stay visible instead of repeatedly re-running setup. Both are ordinary user drop-ins. The helper refuses root execution and a kernel other than retained BOOT 6.

One-second Gio call timeouts bound the method acknowledgment wait; they do not prove a systemd start/stop job has completed. The installer and handset acceptance must read back actual active state and PID. A method timeout fails closed with a subsequent stop request; that request can itself fail and is reported without an automatic retry.

The binary, `/dev/mtp_usb`, USB mode/configuration, authentication, kernel settings and greeter are unchanged. A restarted native server evaluates `com.lomiri.LomiriGreeter.IsActive` itself before initially exposing storage. This preserves that existing implementation; it does not claim to improve its lock behavior or prove privacy by a parser fixture.

## Reviewed installation boundary

There is no phone installer in this directory. The parent task owns a private staged user-session installer and must verify `manifest.json` against the live native package and originals before applying this candidate. Required checks are Ubuntu 24.04, `beyond2lte`/SM-G975F identity, exact BOOT 6 kernel, non-root existing Lomiri user bus, exact native package version and hashes, and original unit `ExecStart` values. Reject symlinks, shared/writable staging directories and any preexisting target collision; keep an exact private backup and record promoted payload hashes.

The three new target files are `%h/.local/libexec/ut-s10-mtp-usb-watcher.py`, `%h/.config/systemd/user/mtp-server.service.d/90-ut-s10-mtp-reconnect.conf`, and `%h/.config/systemd/user/mtp-server-usb-moded-watcher.service.d/90-ut-s10-mtp-reconnect.conf`. The first carries `mtp-usb-watcher.py`; the two drop-ins carry their correspondingly named files. No package-managed file is overwritten. Stage all three first, promote atomically per file, reload the existing user manager, then restart only the original watcher. Verify unit definitions and hashes. If any promotion/reload/restart fails, restore the exact prior state before returning failure.

Live original watcher/unit hashes matched the source manifest; the unchanged native server ELF hash is also recorded. The existing two user-systemd parent directories were mode `0775`, owned by UID/GID 32011. The private installer must record those modes, tighten only those two directories to `0755` before promotion and restore exactly `0775` on rollback. Other observed parent modes and the non-root ownership requirements are recorded in the manifest.

Rollback removes only the three owned files after matching their recorded hashes, restores any exact installer backup, reloads the user manager and restarts only the original watcher. Never remove whole directories or reset unrelated failed units. A reconnected MTP roundtrip, lock-start privacy check, physical unplug/replug without mode flips, stable ADB and lack of a disconnected restart storm remain acceptance requirements. Do not repeat suspension until this reconnect regression is understood.

## Verification

Use the standard free public `.github/workflows/runtime-tools.yml` job. It runs the parser/lifecycle fixtures and real Gio calls against a private mock user-systemd bus. No test contacts the handset. No C++ compilation is required because the native MTP binary is unchanged.
