# Superseded tools

This archive preserves the source of completed experiments. It is separate from the maintained diagnostic and build paths. Each source appears once; firmware, portable runtimes and generated ZIPs are not copied into Git.

| Area | Why archived | Current replacement |
| --- | --- | --- |
| `boot-diagnostics/` | Completed diagnostic 1/2 standalone builders, packages, collectors and launchers. | Current BOOT 6 builder/observer; shared image/CPIO/input modules remain active. |
| `ubuntu-boot-4-inspector/` | Inspector pinned to an old BOOT 4 state. | Current BOOT 6 and graphics/session collectors. |
| `first-boot-check/` | Standalone first-boot add-on pinned to the original images. | Version-specific BOOT 6 collectors; shared transport/redaction helper and host tests stay active. |
| `upstream-reconnaissance/` | Initial unpinned latest/live-ref discovery. | Locked source checkout and current source/kernel/userspace audits. |
| `ubuntu-boot-5/` | BOOT 5 confirms systemd/Android execution but hits the USB configfs NULL panic. | BOOT 6 USB correction, RAM profiles and exact BOOT 4 rollback. |
| `ubuntu-boot-4/` | Completed BOOT 4 standalone upgrade. | Current BOOT 6 build and collectors. |
| `ubuntu-boot-3/` | Completed BOOT 3 standalone upgrade. | Current BOOT 6 build and collectors. |
| `boot-update-1/` | The standalone offset-fix package was applied and BOOT 1 still remained at the logo. | Both SAR fixes are in the current build; controlled BOOT diagnostic and BOOT 2 rollback. |
| `boot-update-2/` | The standalone init-handoff package was applied and BOOT 2 still remained at the logo. | Current diagnostic package, using the verified BOOT 2 kernel. |
| `odin-system-boot/` | The SYSTEM/BOOT Download-mode route failed during PIT transfer and was replaced by the tested TWRP route. | Maintained TWRP installer and shared image/preflight checks. |
| `userdata-format-fix/` | One-time add-on for the earlier data-format preflight. | Current preflight code; no repeated Format Data is part of the active investigation. |

The shared BOOT installer/verifier template and Windows guard fixtures remain active under `scripts/templates/` and `tests/`. The guarded TWRP path still imports common functions from `install-ubuntu-touch.ps1` and `flash-recovery-test.ps1`; those dependency files remain active even though the old Odin SYSTEM/BOOT launcher is archived.

## Reproducing a historical experiment

Archived workflows are outside `.github/workflows/`, so GitHub cannot execute them as current workflows. Their scripts retain the original source layout and package identities. For exact reproduction, check out the recorded historical revision in a separate working directory and use the original paths. Moving a source into this archive does not revalidate it for the current handset state.

[manifest.json](manifest.json) maps old paths to their new locations and records original Git blob identities. The initial archive uses source revision `8dd7a511131d113e5e5d541639c8bfd5e68512fb`. Later moves record their own `source_commit`; the completed BOOT 3 tools use `fc6ffd6b57bdfcf10dab781c7125d4905728cc4b`. Later current-status reports remain in [docs/evidence](../docs/evidence/README.md).

Completed BOOT 4 standalone launchers and host repackage sources use source revision `8758c3747d4cc7909463f6b2d1660169e450fd4f`. The shared builder, verified install templates and immutable image references remain maintained.

Completed BOOT 5 standalone apply/read/readme inputs use source revision `0703cda8ae8520900847f1d2fb89a2b67b6d5283`. The shared BOOT 4 rollback launcher remains maintained for BOOT 6.

## First graphical boot cleanup

The post-boot cleanup records source commit `70bf0d9701b951826c2c2a8d7e27c68d1dd77b84`. Archived files preserve their original bytes. The original full first-boot collector test is preserved here while its active file retains the shared host regressions. Current graphics packages, recovery guards, pinned build inputs and stock firmware support remain active. No firmware or generated runtime is stored in this archive.
