#!/usr/bin/env python3
"""Install only the two evidenced graphics udev rules in an offline rootfs."""
import argparse
import hashlib
import os
from pathlib import Path
import stat

RULE_FILENAME = "99-ubuntu-touch-s10plus-graphics.rules"
RULE_PATH = "/usr/lib/udev/rules.d/" + RULE_FILENAME
RULE_SHA256 = "2fa0e44d37bb3e71726b4099d1de124139bfcb8e17aab906cdaca1b8ee2a35da"
EXTRACTION = ('mkdir -p "$OUTPUT/rootfs/system"\ncd "$OUTPUT/rootfs"\n'
              'print_header "Extracting rootfs..."\n'
              'XZ_OPT="-T0" tar xpzf "../$file" --numeric-owner -C system\n')
REPACK = 'print_header "Repacking rootfs..."\nXZ_OPT="-1 -T0" tar cJf "../rootfs.tar.xz" system\ncd -'
DEVELOPMENT_DEFAULTS = '# Enable SSH and USB tethering, and disable secure ADBD'
HOOK = '''# Install the narrow, evidenced graphics rules before rootfs repacking.
[ "$OUTPUT" = "ota" ] && [ "$PWD" = "$HERE/ota/rootfs" ] || { echo "Unexpected graphics rootfs context" >&2; exit 1; }
python3 "$HERE/build/graphics_assembly.py" --root "$HERE/ota/rootfs/system" --rules "$HERE/build/99-ubuntu-touch-s10plus-graphics.rules" || exit 1

'''


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical_rules(path):
    path = Path(path)
    require(stat.S_ISREG(path.lstat().st_mode), "Graphics source must be a regular file")
    with path.open("rb") as stream:
        data = stream.read(4096)
    require(hashlib.sha256(data).hexdigest() == RULE_SHA256,
            "Graphics rules differ from the evidenced canonical LF payload")
    return data


def patch_preparation(text):
    """Fail closed if the pinned upstream extraction/repacking layout changes."""
    require(text.count(EXTRACTION) == text.count(REPACK) == text.count(DEVELOPMENT_DEFAULTS) == 1,
            "Upstream preparation layout changed")
    require(text.count('HERE=$(pwd)') == text.count('OUTPUT="$2"') == 1,
            "Upstream preparation root/output context changed")
    first, last = text.index(DEVELOPMENT_DEFAULTS), text.index(REPACK)
    require(text.index(EXTRACTION) < first < last, "Upstream preparation ordering changed")
    require("graphics_assembly.py" not in text, "Graphics hook already present")
    return text[:first] + '# Keep the rootfs original remote-access defaults.\n\n' + HOOK + text[last:]


def checked_directory(path):
    """Reject traversal, symlink and Windows junction ancestors before writing."""
    path = Path(path)
    require(path.is_absolute() and ".." not in path.parts, "Graphics rootfs must be an absolute path without traversal")
    for part in [*reversed(path.parents), path]:
        require(stat.S_ISDIR(part.lstat().st_mode)
                and not getattr(part, "is_junction", lambda: False)(),
                "Graphics rootfs contains a symlink, junction or non-directory")
    return path


def install_rules(root, source):
    data = canonical_rules(source)
    root = checked_directory(root)
    parent = checked_directory(root / "usr/lib/udev/rules.d")
    descriptor = None
    # Assembly runs on Linux. Descriptor-relative traversal prevents a symlink
    # swap between validation and leaf creation; the Windows path supports tests.
    if os.open in os.supports_dir_fd:
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        descriptor = os.open(parent.anchor, flags)
        try:
            for component in parent.parts[1:]:
                next_descriptor = os.open(component, flags, dir_fd=descriptor)
                os.close(descriptor)
                descriptor = next_descriptor
        except BaseException:
            os.close(descriptor)
            raise
    target = RULE_FILENAME if descriptor is not None else str(parent / RULE_FILENAME)
    options = {"dir_fd": descriptor} if descriptor is not None else {}
    try:
        try:
            info = os.stat(target, follow_symlinks=False, **options)
        except FileNotFoundError:
            info = None
        if info is not None:
            require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1,
                    "Graphics target must be a regular file with one link")
            fd = os.open(target, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), **options)
            with os.fdopen(fd, "rb") as stream:
                require(stream.read(4096) == data, "Conflicting graphics rules already exist")
            return {"path": RULE_PATH, "sha256": RULE_SHA256, "created": False}
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o644, **options)
        try:
            with os.fdopen(fd, "wb") as stream:
                if os.name != "nt":
                    os.fchmod(stream.fileno(), 0o644)
                stream.write(data)
        except BaseException:
            os.unlink(target, **options)
            raise
        return {"path": RULE_PATH, "sha256": RULE_SHA256, "created": True}
    finally:
        if descriptor is not None:
            os.close(descriptor)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--rules", required=True, type=Path)
    arguments = parser.parse_args()
    install_rules(arguments.root, arguments.rules)
