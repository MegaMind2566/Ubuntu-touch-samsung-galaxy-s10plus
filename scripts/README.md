# Active scripts

The flat script directory preserves explicit sibling imports and the tested Windows package layout. Shared generated BOOT templates are grouped under `templates/`; superseded standalone packages are in [archive](../archive/README.md).

| Purpose | Main components |
| --- | --- |
| Adaptation and SYSTEM build | `fetch_sources.py`, `prepare_build.py`, `build-adaptation.sh`, `assemble_system.py`, `validate-artifacts.py`, `validate_system.py` |
| Firmware and image inspection | `inspect_stock_firmware.py`, `inspect_stock_dtb.py`, `audit_install_artifact.py`, `audit_kernel_boot_sources.py`, `audit_boot_observability.py` |
| New offline analysis | `audit_kernel_symbols.py`, `audit_device_trees.py` |
| Controlled diagnostic | `prepare_boot_diagnostic.py`, `package-boot-diagnostic.py`, `collect-boot-diagnostic.py` |
| Built-in initramfs diagnostic 2 | `early_boot_diagnostic.py`, `build-early-boot-diagnostic.sh`, `package-early-boot-diagnostic.py` |
| Ubuntu BOOT 6 USB correction and RAM profiles | `ubuntu_boot_handoff.py`, `build-ubuntu-boot-handoff.sh`, `package-ubuntu-boot-handoff.py`, `collect-ubuntu-handoff.py.in` |
| BOOT 6 retained graphics logs | `collect-ubuntu-graphics.py` version 2, `package-ubuntu-graphics.py`; TWRP-compatible metadata, read-only, no new BOOT |
| Shared immutable artifact transport | `github_artifacts.py`, `fetch_boot_diagnostic_inputs.py` |
| Recovery/TWRP support | `prepare_recovery.py`, `check-recovery.ps1`, `prepare_ubuntu_install.py`, `install-ubuntu-twrp.ps1` |
| Windows package creation | Maintained `package-*.py` scripts and the launchers in `tools/windows/` |

`install-ubuntu-touch.ps1`, `flash-recovery-test.ps1` and `check-download-mode.ps1` provide shared guards used by the tested TWRP/BOOT installers. They are retained as dependencies; moving their obsolete launchers does not justify removing those checks. `prepare_boot_update.py` still supplies the pinned baseline images used by build and diagnostic validation.

Generated installers and the diagnostic collector contain pinned substitutions supplied by their packager. Run them from the prepared Windows package, not from an unrendered template or source checkout. See [Development](../docs/development.md) for the build and analysis entry points.

The diagnostic 1 sources remain active as the immutable input and rollback reference for diagnostic 2. The second collector is rendered from the maintained collector template with version-specific pins, markers and log paths. The normal Ubuntu build uses only `patches/kernel/`; the additional built-in-initramfs patch is scoped to the diagnostic 2 and Ubuntu BOOT builders. The exact physical BOOT 5 is the BOOT 6 installer baseline; BOOT 4 remains the separate rollback payload. Completed BOOT 3/4/5 standalone launchers and superseded repackage sources are archived; the current full build validates BOOT 6. The read-only userspace inspector remains a baseline-4 diagnostic, not a required additional handset test.

`audit-system-userspace.py` verifies the original SYSTEM artifact and inspects init, systemd, dependencies, Android and mount units without writing its filesystem. `collect-ubuntu-userspace.py` and `inspect-ubuntu-userspace.sh` inspect BOOT 4 on TWRP through a guarded temporary read-only mount. BOOT 6 packages include extended handoff observation, so that separate inspection is optional.
