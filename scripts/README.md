# Maintained scripts

Current entry points build the adaptation, assemble SYSTEM, package BOOT 6 and support the working graphics configuration. Completed experiments are in [archive](../archive/README.md), with original paths and Git blob identities.

| Area | Entry points |
| --- | --- |
| Source checkout and adaptation | `fetch_sources.py`, `prepare_build.py`, `build-adaptation.sh` |
| SYSTEM assembly and validation | `assemble_system.py`, `validate_system.py`, `validate-artifacts.py` |
| Current BOOT | `ubuntu_boot_handoff.py`, `build-ubuntu-boot-handoff.sh`, `package-ubuntu-boot-handoff.py` |
| Graphics permission correction | `manage-graphics-permissions.py`, `package-graphics-permissions.py` |
| Experimental wired TRRS routing | `ut-s10-trrs-integrato.py` — guarded user-level legacy routing and auto-switch v4; insertion/removal and reboot persistence observed on the test handset ([status](../docs/status.md)). Headset microphone, UI label and default-sink stability remain unresolved. Offline regression: `tests/test_trrs_integrato.py` (61 cases) |
| Read-only energy inventory | `ut-s10-energia-diagnosi-v2.py` — bounded battery, charger and suspend-capability readings; [unplugged baseline](../docs/evidence/energy-unplugged-baseline-2026-10-24.md) and [connected inventory](../docs/evidence/energy-connected-inventory-2026-11-05.json). Brief USB charge progression and user-confirmed normal screen/touch wake observed on 5 November; sustained charging, positive kernel suspend and endurance remain unverified ([physical trial](../docs/evidence/screen-off-wake-2026-11-05.md)). Host regression: `tests/test_energy_inventory.py` |
| Clock-only suspend comparison | `ut-s10-suspend-clock.py` — one BOOTTIME/MONOTONIC bracket per snapshot; session-scoped HMAC boot token, bounded JSON comparison and explicit sampling uncertainty. No power controls, battery reads or polling. Regression: `tests/test_suspend_clock.py` |
| Saved USB mode after rescue | [`tools/usb-mode-restore`](../tools/usb-mode-restore/README.md) — one guarded public mode selection after rescue-off; authenticated ADB returned after one normal reboot on 5 November; a later ADB-offline reconnect regression remains open ([trial](../docs/evidence/screen-off-wake-2026-11-05.md)). Host regression: `tests/test_usb_saved_mode.py` |
| Recovered runtime source identities | [`tools/runtime-fixes`](../tools/runtime-fixes/README.md) — exact audio6, Wi-Fi and USB references for future image integration; identity check: `tests/test_runtime_fix_sources.py` |
| ADB reconnect candidate | [`patches/usb`](../patches/usb/README.md) — pinned source patch, real-method Linux fixtures and full Debian ARM64 build through free public GitHub Actions. Eight candidate fixture cases and package build passed; the staged handset loader resolved libraries without starting the daemon. Physical reconnect remains unverified ([record](../docs/evidence/runtime-arm64-build-2026-11-05.md)) |
| Automatic-brightness profile | [`tools/automatic-brightness`](../tools/automatic-brightness/README.md) — unchanged source-pinned Lineage tables for repowerd, guarded profile-only installation and exact rollback. No sysfs/GSettings/service mutation; 15 offline cases including ownership/mode rejection. Profile activation and physical response remain pending |
| Current retained boot/graphics logs | `collect-ubuntu-handoff.py.in`, `collect-ubuntu-graphics.py`, `package-ubuntu-graphics.py` |
| Optional controlled mapper probe | `manage-graphics-probe.py`, `package-graphics-probe.py` |
| Recovery and installation support | `prepare_recovery.py`, `verify_recovery_test.py`, `prepare_ubuntu_install.py`, `install-ubuntu-twrp.ps1`, `check-recovery.ps1` |
| Firmware and source inspection | `inspect_stock_firmware.py`, `inspect_stock_dtb.py`, `audit_install_artifact.py`, `audit_kernel_boot_sources.py` |
| Kernel, device-tree and userspace analysis | `audit_kernel_symbols.py`, `audit_device_trees.py`, `audit-system-userspace.py`, `audit_boot_observability.py` |
| Alpha release preparation and publication | `package-firmware-release.py`, `prepare-firmware-images.py`, `publish-firmware-release.py`; [manifest](../config/releases/v0.1.0-alpha.1.json) and [installation guide](../docs/install-alpha.md) |
| Immutable artifact transport | `github_artifacts.py`, `materialize-release-system.py` |
| Initial firmware/USB support | Maintained `package-*.py` tools and launchers listed in [Windows support](../tools/windows/README.md) |

The [Windows MTP round trip](../docs/evidence/mtp-windows-2026-11-05.md) was separately verified on 5 November after the user selected the compatible Windows driver. The USB collector only reads host state; it does not assign drivers. One small file in each direction passed SHA-256 checks, without a general clean-install, large-file or reconnect guarantee.

## Shared dependencies

`prepare_boot_diagnostic.py` and `early_boot_diagnostic.py` remain shared BOOT build modules. Their CPIO, image and immutable-input functions are imported by the current builder. `tools/boot-diagnostic/init`, `config/early-boot-diagnostic.config` and the forced-initramfs patch remain required inputs; the old standalone diagnostic builders and launchers are archived.

`prepare_boot_update.py` supplies pinned baseline image inputs. `install-ubuntu-touch.ps1`, `flash-recovery-test.ps1`, `check-download-mode.ps1` and the verified BOOT templates supply the existing TWRP/BOOT guards. The original collector `collect-first-boot.py` remains a shared tool-verification, redaction and transport dependency for all current graphics collectors. Its old standalone launcher is archived; host regression coverage stays active.

## Running tools

See [Development](../docs/development.md) for build commands and validation boundaries. Windows launchers require complete prepared packages with pinned tools and image identities; a source checkout is not an installation package. The current BOOT upgrade package accepts exact BOOT 5 and retains BOOT 4 as its distinct rollback image.

Keep BOOT 6 and graphics correction 1 on the working handset while checking stability and remaining hardware. Historical diagnostic packages are reproduced from their recorded source revision, rather than run from the archive tree.

The host-only [runtime-tools workflow](../.github/workflows/runtime-tools.yml) runs energy, clock, TRRS, saved USB mode, runtime-source identity and brightness-profile regressions on Linux without a handset. For example, use `python3 -m unittest discover -s tests -p test_energy_inventory.py -v` or the corresponding suite filename above. These checks use temporary files, fixture commands and simulated state; they do not prove charging, suspend, physical brightness or audio behavior. ARM64 compilation is restricted to the separate free public GitHub workflow.

For clock comparisons, obtain snapshots with `--snapshot --session TOKEN`, using the same fresh 32-hex-digit diagnostic nonce before and after the observation. Compare the two saved JSON files with `--compare before.json after.json`. The raw boot ID is never emitted; the HMAC token is comparable only within that diagnostic session. The tool rejects session/boot mismatches, missing clocks and invalid progress. BOOTTIME includes suspend while MONOTONIC excludes it ([kernel clock semantics](https://www.kernel.org/doc/html/latest/core-api/timekeeping.html)); their delta difference measures kernel-accounted suspend time within the reported sampling uncertainty. It does not establish deep sleep, successful UI wake or endurance. Device wall time is recorded for context and is not used in the calculation.
