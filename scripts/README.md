# Maintained scripts

Current entry points build the adaptation, assemble SYSTEM, package BOOT 6 and support the working graphics configuration. Completed experiments are in [archive](../archive/README.md), with original paths and Git blob identities.

| Area | Entry points |
| --- | --- |
| Source checkout and adaptation | `fetch_sources.py`, `prepare_build.py`, `build-adaptation.sh` |
| SYSTEM assembly and validation | `assemble_system.py`, `validate_system.py`, `validate-artifacts.py` |
| Current BOOT | `ubuntu_boot_handoff.py`, `build-ubuntu-boot-handoff.sh`, `package-ubuntu-boot-handoff.py` |
| Graphics permission correction | `manage-graphics-permissions.py`, `package-graphics-permissions.py` |
| Current retained boot/graphics logs | `collect-ubuntu-handoff.py.in`, `collect-ubuntu-graphics.py`, `package-ubuntu-graphics.py` |
| Optional controlled mapper probe | `manage-graphics-probe.py`, `package-graphics-probe.py` |
| Recovery and installation support | `prepare_recovery.py`, `verify_recovery_test.py`, `prepare_ubuntu_install.py`, `install-ubuntu-twrp.ps1`, `check-recovery.ps1` |
| Firmware and source inspection | `inspect_stock_firmware.py`, `inspect_stock_dtb.py`, `audit_install_artifact.py`, `audit_kernel_boot_sources.py` |
| Kernel, device-tree and userspace analysis | `audit_kernel_symbols.py`, `audit_device_trees.py`, `audit-system-userspace.py`, `audit_boot_observability.py` |
| Immutable artifact transport | `github_artifacts.py`, `materialize-release-system.py` |
| Initial firmware/USB support | Maintained `package-*.py` tools and launchers listed in [Windows support](../tools/windows/README.md) |

## Shared dependencies

`prepare_boot_diagnostic.py` and `early_boot_diagnostic.py` remain shared BOOT build modules. Their CPIO, image and immutable-input functions are imported by the current builder. `tools/boot-diagnostic/init`, `config/early-boot-diagnostic.config` and the forced-initramfs patch remain required inputs; the old standalone diagnostic builders and launchers are archived.

`prepare_boot_update.py` supplies pinned baseline image inputs. `install-ubuntu-touch.ps1`, `flash-recovery-test.ps1`, `check-download-mode.ps1` and the verified BOOT templates supply the existing TWRP/BOOT guards. The original collector `collect-first-boot.py` remains a shared tool-verification, redaction and transport dependency for all current graphics collectors. Its old standalone launcher is archived; host regression coverage stays active.

## Running tools

See [Development](../docs/development.md) for build commands and validation boundaries. Windows launchers require complete prepared packages with pinned tools and image identities; a source checkout is not an installation package. The current BOOT upgrade package accepts exact BOOT 5 and retains BOOT 4 as its distinct rollback image.

Keep BOOT 6 and graphics correction 1 on the working handset while checking stability and remaining hardware. Historical diagnostic packages are reproduced from their recorded source revision, rather than run from the archive tree.
