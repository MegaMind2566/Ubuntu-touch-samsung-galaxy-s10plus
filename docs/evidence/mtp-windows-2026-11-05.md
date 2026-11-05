# Windows MTP round trip - 5 November 2026

The user manually selected the compatible Windows MTP driver for this SM-G975F after an earlier incompatible `ts_wpdmtp` variant did not work. Windows then reported problem code **0**, using `wpdmtphw.inf` / `WUDFWpdMtp`; the authenticated ADB connection remained available. No INF editing or unsigned driver installation was used. This driver assignment followed the earlier [USB-mode acceptance](usb-saved-mode-acceptance-2026-11-05.json), whose unresolved-MTP entry records the state at that earlier point.

Actual copies used the Windows Shell WPD namespace over **MTP**, not ADB transfer. Two new **72,050-byte ASCII diagnostic files**, one for each direction, were checked independently against generated host data and authenticated ADB reads of the phone-side target:

| Direction | Bytes | SHA-256 |
| --- | --- | --- |
| Phone to PC | 72,050 | `d94b5fd308a65d60b3df7597eda0d6bffc78f41535fd452cda96151132282983` |
| PC to phone | 72,050 | `ad0eb227de63fbfa2c43f70dd9d6b266d99736904bb737f8601baa98107691fc` |

Both directions passed. Only generated diagnostic files were opened or copied; their phone-side files were removed after verification. No personal media, credentials or raw device journals are included. The [machine-readable record](mtp-windows-roundtrip-2026-11-05.json) preserves the result and identities.

This establishes one small-file transfer per direction on this handset and current Windows installation. Large files, throughput, repeated reconnects, other PCs and a general clean installation remain unverified. The missing kernel mass-storage charging fallback is separate from this successful MTP/ADB configuration. No firmware change was needed for this MTP test.
