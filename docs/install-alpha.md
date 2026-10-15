# Installing v0.1.0-alpha.1

This guide describes the experimental **SM-G975F/DS Exynos (`beyond2lte`)** configuration that reached the first Ubuntu Touch graphical boot. Basic touch and Wi-Fi work on the development phone. The complete fresh-install sequence below has not yet been repeated end to end; this is an advanced manual release.

## Before starting

Use the **G975FXXSGHWC1 Android 12 / One UI 4.1 stock firmware/vendor baseline**, an unlocked bootloader and a known working Samsung Download Mode recovery path. Keep the full matching stock firmware and personal backups on the PC. Bootloader unlocking and **Format Data erase internal storage**.

The tools ZIP contains a prepared TWRP 3.7.0_9-2 recovery and a disabled-verification VBMETA. They match the development-phone pins. The recovery preparation disables the original automatic system/vendor modification path. The correction launcher requires that exact prepared recovery; the unmodified upstream image is a different file.

Establish the prepared recovery/VBMETA with your Samsung Download Mode flashing setup before following the image-install steps. The supplied `.img` files are raw partition images, not Odin AP tar files. This alpha does not include an automated stock-to-TWRP installer. The [TeamWin device page](https://twrp.me/samsung/samsunggalaxys10plus.html) describes the model's A-only/SAR layout and recovery installation requirements. Do not substitute recovery images from another S10 variant.

## Prepare the files on Windows

1. Download `SYSTEM.img.zst` and `UbuntuTouch-S10plus-v0.1.0-alpha.1-boot-and-tools-Windows.zip` from the same release. Compare their SHA-256 values with the release's `SHA256SUMS`.
2. Extract the complete ZIP on **NTFS or another filesystem supporting hard links and files larger than 5 GiB**. Keep at least 6 GB free for expansion. Put the compressed SYSTEM either inside that extracted folder or beside it; keep only one copy in those two locations.
3. Run **PREPARA-IMMAGINI-FIRMWARE.cmd**. It verifies the pinned Python runtime, BOOT and compressed input, then expands and hashes `images/system.img`. Existing conflicting images stop preparation; they are not overwritten. This step does not access the phone.
4. Continue only after the tool reports verified images. `images/` contains SYSTEM, BOOT, prepared RECOVERY and VBMETA. Each has a distinct partition target; do not select a partition based only on filename order.

## Install the Ubuntu images in prepared TWRP

1. Boot the **prepared TWRP** and keep USB connected. Decline recovery-app installation and automatic Android modifications.
2. For a fresh installation, use **Wipe > Format Data**, enter `yes`, then reboot to Recovery. Do this before copying the images onto internal storage. Data must be unencrypted ext4 and mounted in TWRP. Do not use Advanced Wipe to erase Vendor.
3. Transfer the verified `system.img` and `boot.img` to storage accessible to TWRP. Use **Install > Install Image** to flash `system.img` to **System Image** and `boot.img` to **Boot**. This release preserves the stock Android 12 Vendor partition.
4. Boot **System** once and allow a few minutes for Ubuntu to initialize userdata. At this stage the graphical session may remain on the boot screen, because the required permission correction has not been applied yet.
5. Return to prepared TWRP with USB connected and Data mounted. On Windows, run **APPLICA-CORREZIONE-GRAFICA-1.cmd** from the extracted release folder. It verifies the model/firmware, recovery, BOOT 6 and raw userdata before writing its own configuration. If it stops, preserve the report and investigate that result; do not bypass its checks.
6. After successful application, choose **Reboot > System**, decline the TWRP app and allow up to four minutes. The correction remains installed for later boots.

The correction requires the Ubuntu-created `system-data/etc` userdata layout. An empty freshly formatted Data partition is not an application target; that is why the first normal initialization boot comes before step 5.

## Check the result and collect evidence

Check the graphical screen, touch and Wi-Fi. For a report, return to TWRP and run **LEGGI-CORREZIONE-GRAFICA-1.cmd** before changing the configuration. The reader includes bounded correction, compositor, greeter and LightDM logs. It does not certify an end-to-end installation by itself.

**ANNULLA-CORREZIONE-GRAFICA-1.cmd** removes only the correction's verified configuration and preserves its logs. Undo takes effect after reboot and removes the access fix required by this alpha. Keep the correction installed on the working configuration.

## Recovery and support scope

Keep Download Mode and the full matching stock firmware available for manual restoration. BOOT 4 and older development diagnostics are historical experiments, not a known-working daily-use rollback. No modem, Vendor or stock firmware image is redistributed in this release.

Report the exact model, Samsung firmware, asset hashes, observed screen and generated logs with any test result. The [current status](status.md) tracks hardware validation separately from image checks and host tests.
