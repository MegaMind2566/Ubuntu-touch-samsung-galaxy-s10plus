# Superseded tools

This archive preserves the source of completed experiments. It is separate from the maintained diagnostic and build paths. Each source appears once; firmware, portable runtimes and generated ZIPs are not copied into Git.

| Area | Why archived | Current replacement |
| --- | --- | --- |
| `ubuntu-boot-3/` | BOOT 3 handset test completed; its pinned host repackage workflow targets the previous payload. | Maintained Ubuntu BOOT 4 builder/collector and guarded BOOT 3 rollback. |
| `boot-update-1/` | The standalone offset-fix package was applied and BOOT 1 still remained at the logo. | Both SAR fixes are in the current build; controlled BOOT diagnostic and BOOT 2 rollback. |
| `boot-update-2/` | The standalone init-handoff package was applied and BOOT 2 still remained at the logo. | Current diagnostic package, using the verified BOOT 2 kernel. |
| `odin-system-boot/` | The SYSTEM/BOOT Download-mode route failed during PIT transfer and was replaced by the tested TWRP route. | Maintained TWRP installer and shared image/preflight checks. |
| `userdata-format-fix/` | One-time add-on for the earlier data-format preflight. | Current preflight code; no repeated Format Data is part of the active investigation. |

The shared BOOT installer/verifier template and Windows guard fixtures remain active under `scripts/templates/` and `tests/`. The guarded TWRP path still imports common functions from `install-ubuntu-touch.ps1` and `flash-recovery-test.ps1`; those dependency files remain active even though the old Odin SYSTEM/BOOT launcher is archived.

## Reproducing a historical experiment

Archived workflows are outside `.github/workflows/`, so GitHub cannot execute them as current workflows. Their scripts retain the original source layout and package identities. For exact reproduction, check out the recorded historical revision in a separate working directory and use the original paths. Moving a source into this archive does not revalidate it for the current handset state.

[manifest.json](manifest.json) maps old paths to their new locations and records original Git blob identities. The initial archive uses source revision `8dd7a511131d113e5e5d541639c8bfd5e68512fb`. Later moves record their own `source_commit`; the completed BOOT 3 tools use `fc6ffd6b57bdfcf10dab781c7125d4905728cc4b`. Later current-status reports remain in [docs/evidence](../docs/evidence/README.md).
