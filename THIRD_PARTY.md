# Sources and attribution

The upstream repositories are fetched at the full commit IDs recorded in
`config/upstream.lock.json`. Their files retain their upstream copyright and
license terms; this project does not change or replace those terms.

| Component | Source | Use |
| --- | --- | --- |
| S10+ device configuration and overlays | UBports community Samsung Exynos 9820 port, `halium-12` | Build staging |
| Kernel 4.14.280 | UBports Samsung Exynos 9820 kernel, `halium-12.0` | Modified build staging; kernel COPYING applies |
| Build and packaging scripts | UBports halium-generic-adaptation-build-tools | Build staging |
| Non-dynamic ARM64 ramdisk | Halium/initramfs-tools-halium continuous release | Downloaded by upstream tools; checksum recorded per run |

The two AppArmor mail patches are the 4.14 patches linked from the
[UBports AppArmor porting guide](https://docs.ubports.com/en/latest/porting/configure_test_fix/Apparmor.html).
They preserve their author and sign-off headers:

- John Johansen / Seth Forshee / Danny Lin,
  [socket mediation](https://github.com/kdrag0n/proton_zf6/commit/559e4f447556e1ea0b24b035965023b6fba8f2f8).
- John Johansen / Seth Forshee / Danny Lin,
  [AF_UNIX mediation](https://github.com/kdrag0n/proton_zf6/commit/f076c3083d908253d32d26b49d64faaf4f80b442).

Kernel additions and patches are subject to the kernel's applicable license.
Toolchain binaries, ramdisk and later rootfs/vendor inputs are separate upstream
components. Source pinning alone does not freeze all binary downloads. The first
build records the ramdisk checksum; full binary input locking remains pending.
# Windows firmware download utility

The separate Windows downloader package uses samloader 2.2.0 from
https://github.com/topjohnwu/samloader-rs/releases/tag/2.2.0,
source commit `4dfea027767f3268e70dc130f169d459bd153cbf`.
Its original Windows x86_64 archive SHA-256 is
`0132de1b79e208138f980c467f9a7eaa2ffcb72aae14afc3ed13799803c9b9ed`.
Apache-2.0 and inherited Heimdall MIT notices are included from that source tag
under `third-party/samloader/` and in the generated package's licenses folder.
Only `--version`, `check-update`, `download` and local `verify-md5` are invoked
by the launcher. It never invokes the utility's device-access/flash commands.

Samsung stock firmware is downloaded on the user's PC from Samsung FUS. It
is not included in the open-source utility package or committed to this repo.

## Offline kernel and device-tree analysis

| Component | Pinned source | License / use |
| --- | --- | --- |
| vmlinux-to-elf 1.3.6 | [marin-m/vmlinux-to-elf](https://github.com/marin-m/vmlinux-to-elf), commit `19683fb95b29cd31362d49e6f48ab8368f96cbdf` | GPL-3.0-or-later; unmodified kernel symbol/ELF reconstruction tool in an isolated CI environment. |
| DTC / libfdt 1.8.1 | [dgibson/dtc](https://github.com/dgibson/dtc), commit `f3451d12532b9d382707c458a2ae2e5aa0e1eee4` | DTC tools: GPL-2.0-or-later; libfdt: GPL-2.0-or-later OR BSD-2-Clause. Unmodified tool build with upstream tests. |

These tools are fetched from their source repositories, not vendored into this
repository. Their source and license notices remain at the pinned revisions.
Generated ELF files and DTC executables are analysis/build artifacts. Firmware
identity and artifact references are recorded in the evidence reports.


## First alpha firmware package

The release combines separately licensed upstream components. Its image and runtime identities are recorded in [the release manifest](config/releases/v0.1.0-alpha.1.json) and [packaging evidence](docs/evidence/firmware-alpha-1-packaging-2026-10-15.json).

| Component | Origin and retained notices |
| --- | --- |
| Ubuntu Touch userspace / Halium adaptation | Upstream sources pinned in `config/upstream.lock.json`; SYSTEM assembly inputs and the existing image's package notices remain intact. |
| Prepared TWRP 3.7.0_9-2 for beyond2lte | [TeamWin download](https://eu.dl.twrp.me/beyond2lte/twrp-3.7.0_9-2-beyond2lte.img.html); the exact original and transformation are recorded in `scripts/prepare_recovery.py`. Recovery retains upstream component terms. |
| Python 3.14.4 Windows embedded runtime | [Official Python archive](https://www.python.org/ftp/python/3.14.4/python-3.14.4-embed-amd64.zip); complete archive members, including `tools/python/LICENSE.txt`, are retained. |
| Android Platform-Tools 37.0.1 for Windows | [Official Google archive](https://dl.google.com/android/repository/platform-tools_r37.0.1-win.zip); complete archive members, including `platform-tools/NOTICE.txt`, are retained. |

The release does not redistribute Samsung stock firmware or a Vendor image. The modified kernel's pinned source, build patches and build procedure remain available in this source repository. No single license statement here replaces the terms of the bundled components.
