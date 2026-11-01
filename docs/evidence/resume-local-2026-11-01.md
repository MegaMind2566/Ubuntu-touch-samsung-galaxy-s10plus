# Local resumption — 1 November 2026

Development resumed locally from source commit `1b11800`. This record describes host checks and read-only Android identification; it is not a new Ubuntu Touch hardware acceptance result.

## Preserved inputs

- The existing alpha.1 Windows ZIP is 73,287,864 bytes and matches published SHA-256 `643bcc8c137060c87871d472c8bd35a6b03f55aa905fc2f4a92d833975acdedb`. ZIP CRC verification passed.
- All 12 available TWRP backup checksum sidecars matched their corresponding files. No files were extracted from DATA/EFS and no private backup content is published.
- The BOOT backup begins with the exact 57,344,000-byte BOOT 6 image: SHA-256 `2671343e619d99ba8e1809aba73209afb67bdc50e982451f09662765aa6cb4ad`.
- The first 5 GiB of the backed-up SYSTEM **does not** match the immutable alpha.1 SYSTEM digest. The backup's own checksum passes; the cause of the difference has not been established. Do not relabel it as the release image or use it as an assembly input without analysis.
- Backup integrity does not demonstrate a successful restore. The separate original `SYSTEM.img.zst` was not found in the bounded Desktop/Downloads search.

## Current handset, read only

ADB connectivity was restored with a transport reconnect. Read-only properties identify hardware SM-G975F / Exynos 9820. The running ROM is Android 16 / SDK36, ArtisanROM Quant3.1.1; it advertises software model SM-S731B. That software identity is not the physical model.

The current bootloader is `G975FXXUHHXJ1`, whereas the historical Ubuntu Touch baseline and guarded tools target `G975FXXSGHWC1`. No cross-baseline compatibility, downgrade or installation is established. No reboot, recovery change, partition write, root configuration change or Ubuntu runtime test was performed.

The next hardware operation must first resolve this baseline mismatch and preserve the current Android recovery route. Previous audio/TRRS, Wi-Fi and energy findings remain historical Ubuntu evidence.

## Host development

Windows checkout converted seven hash-pinned graphics payloads from LF to CRLF, making their existing digest checks fail. Explicit LF attributes now preserve the original pinned bytes; hash checks remain strict.

The offline source change now stages the exact, already reviewed correction1 udev rule for hwbinder/ion before rootfs repacking. Its canonical digest and helper digest are recorded in the assembly manifest; post-build validation requires the exact rule content in the image. The upstream tools commit is now captured correctly instead of producing a null manifest field. This deliberately does not enable the broader upstream70-exynos7904 overlay, claim that every overlay destination is fixed, or replace the original published image. Image ownership metadata is not validated by the new content check.

All 11 new graphics-assembly tests passed with no skips, including real Git Bash/gzip extraction/tar.xz repack and stopping before repack on conflict. Directory traversal, junction/symlink escapes, hardlink destinations and altered rule bytes were rejected; missing/changed image content was rejected through the validator fixture. An independent reviewer repeated all 11 tests successfully. These are host fixtures, not a Linux/fakeroot/ext4 build or hardware boot.

The unmodified Linux-oriented CI discovery cannot pass natively on this Windows host: some modules require POSIX `resource`, `fcntl`, device/file APIs or Linux tools. After the LF correction, focused native tests completed 57 passes with one symlink-privilege error. Native PowerShell5.1 mock-ADB collector tests passed four accepted targets and three rejected targets. These tests simulate USB/device responses and do not exercise a flash.

No new BOOT or SYSTEM image has been assembled, installed or published during this local resumption. Full Linux image assembly and physical validation remain required.

