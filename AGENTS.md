# Repository instructions

This repository develops Ubuntu Touch 24.04 / Halium 12 for the Samsung Galaxy S10+ Exynos SM-G975F/DS (`beyond2lte`). Read `docs/status.md` before selecting the next hardware experiment.

- Keep the README focused on the goal, verified progress and current next step. Put detailed development instructions in `docs/development.md` and compact dated experiment records in `docs/evidence/`.
- Distinguish successful builds, simulated tests, physical readback and runtime execution. Recovery logs describe the recovery kernel unless previous-boot evidence is explicitly identified.
- Maintain reusable code in `scripts/`, BOOT templates in `scripts/templates/` and package launchers in `tools/windows/`. Run generated Windows tools from their complete prepared package.
- Archive a superseded standalone tool after checking active imports, packaging paths and workflows. Update `archive/manifest.json` and replacement links in the same change. Retain shared dependencies while current packages use them.
- Keep firmware, generated images, portable runtimes and extracted kernel ELF files out of Git. Record hashes, source revisions and immutable artifact references instead.
- Update `docs/status.md` and the relevant evidence after each hardware result. State the next experiment and any uncertainty that affects it.

The user's publication decision is to make the repository public after a confirmed Ubuntu Touch graphical boot on the test handset. Record the observed boot and tested image identities, update the public status, and keep untested hardware features explicitly marked. The current diagnostic ramdisk does not start Ubuntu; its execution alone does not meet that criterion.
