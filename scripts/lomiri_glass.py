#!/usr/bin/env python3
"""Inspect Lomiri QML or prepare an isolated, hash-checked Glass Centers tree.

Neither command installs files, restarts Lomiri, changes services or connects to
D-Bus. A successful probe establishes a source match, not handset operation.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import stat
import subprocess
import sys
import tempfile


DEFAULT_PACKAGE = Path(__file__).resolve().parents[1] / "shell/lomiri-glass"
PACKAGES = (
    "lomiri", "qml-module-qmenumodel1", "qml-module-lomiri-settings-menus",
    "ayatana-indicator-power", "ayatana-indicator-sound",
    "ayatana-indicator-bluetooth", "ayatana-indicator-display",
    "ayatana-indicator-messages", "lomiri-indicator-network",
)
HEX256 = re.compile(r"[0-9a-f]{64}\Z")


class PreparationError(RuntimeError):
    """A checked input or operation does not satisfy the preparation contract."""


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_path(path: Path) -> Path:
    """Normalize without following symlinks, rejecting every existing link."""
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(mode):
            raise PreparationError(f"Symbolic links are not accepted: {current}")
    return absolute


def relative_name(name: str, prefix: str | None = None) -> str:
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_./-]+", name):
        raise PreparationError("Invalid package path")
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or ".git" in path.parts:
        raise PreparationError(f"Unsafe package path: {name}")
    if str(path) != name or not path.parts or (prefix and path.parts[0] != prefix):
        raise PreparationError(f"Unexpected package path: {name}")
    return name


def read_regular(path: Path) -> bytes:
    path = safe_path(path)
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError as exc:
        raise PreparationError(f"Required file missing: {path}") from exc
    if not stat.S_ISREG(mode):
        raise PreparationError(f"Expected a regular file: {path}")
    # O_NOFOLLOW prevents a final-component link introduced after the lstat.
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as stream:
        return stream.read()


def scan_tree(root: Path, *, ignore_git: bool = False) -> dict[str, str]:
    root = safe_path(root)
    if not root.is_dir():
        raise PreparationError(f"Expected a directory: {root}")
    result = {}
    for base, dirs, files in os.walk(root, followlinks=False):
        if ignore_git:
            dirs[:] = [name for name in dirs if name != ".git"]
            files = [name for name in files if name != ".git"]
        for name in dirs:
            path = Path(base) / name
            if not stat.S_ISDIR(path.lstat().st_mode):
                raise PreparationError(f"Non-directory or symbolic link in source: {path}")
        for name in files:
            path = Path(base) / name
            result[path.relative_to(root).as_posix()] = digest(read_regular(path))
    return result


def load_package(package_dir: Path) -> tuple[Path, dict, bytes, dict[str, str]]:
    package_dir = safe_path(package_dir)
    try:
        lock = json.loads(read_regular(package_dir / "upstream.lock.json"))
    except (ValueError, UnicodeError) as exc:
        raise PreparationError("Invalid upstream.lock.json") from exc
    if not isinstance(lock, dict) or lock.get("schema") != 1:
        raise PreparationError("Unsupported upstream lock schema")
    for field in ("repository", "ref", "commit"):
        if not isinstance(lock.get(field), str) or not lock[field]:
            raise PreparationError(f"Missing upstream identity field: {field}")
    if not re.fullmatch(r"[0-9a-f]{40}", lock["commit"]):
        raise PreparationError("Upstream commit must be an exact Git object identity")
    for field in ("files", "module_files"):
        entries = lock.get(field)
        if not isinstance(entries, dict) or not entries:
            raise PreparationError(f"Missing locked {field}")
        for name, expected in entries.items():
            relative_name(name, "qml" if field == "files" else None)
            if not isinstance(expected, str) or not HEX256.fullmatch(expected):
                raise PreparationError(f"Invalid SHA-256 for {name}")
    patch = read_regular(package_dir / "integration.patch")
    if digest(patch) != lock.get("patch_sha256"):
        raise PreparationError("Integration patch SHA-256 does not match the lock")
    validate_patch(patch, set(lock["files"]))
    module = scan_tree(package_dir / "qml/Glass")
    if module != lock["module_files"]:
        raise PreparationError("Glass module files or SHA-256 values do not match the lock")
    return package_dir, lock, patch, module


def validate_patch(patch: bytes, expected_paths: set[str]) -> None:
    try:
        text = patch.decode("utf-8")
    except UnicodeError as exc:
        raise PreparationError("Integration patch must contain UTF-8 text") from exc
    forbidden = (
        "new file mode ", "deleted file mode ", "old mode ", "new mode ",
        "rename from ", "rename to ", "copy from ", "copy to ",
        "GIT binary patch", "Binary files ", "--- /dev/null", "+++ /dev/null",
    )
    if any(line.startswith(forbidden) for line in text.splitlines()):
        raise PreparationError("Patch must only modify the locked regular QML files")
    headers = re.findall(r"^diff --git a/(\S+) b/(\S+)$", text, re.MULTILINE)
    old = re.findall(r"^--- a/(\S+)$", text, re.MULTILINE)
    new = re.findall(r"^\+\+\+ b/(\S+)$", text, re.MULTILINE)
    paths = [a for a, b in headers if a == b]
    # Accept normal unified diffs as well as git-format text diffs. Both must
    # have exactly one old/new pair for each locked path.
    if (not old or old != new or len(old) != len(set(old)) or set(old) != expected_paths
            or (headers and (len(headers) != len(paths) or paths != old))
            or sum(line.startswith("diff --git ") for line in text.splitlines()) != len(headers)):
        raise PreparationError("Patch paths do not exactly match the locked source files")


def source_root(source: Path) -> tuple[Path, str]:
    source = safe_path(source)
    if not source.is_dir():
        raise PreparationError("Source must be an existing directory")
    if (source / "qml/Shell.qml").exists():
        return safe_path(source / "qml"), "repository"
    if (source / "Shell.qml").exists():
        return source, "installed"
    raise PreparationError("Source has neither qml/Shell.qml nor Shell.qml")


def inspect_sources(qml_root: Path, lock: dict) -> dict[str, dict]:
    result = {}
    for name, expected in sorted(lock["files"].items()):
        path = qml_root / PurePosixPath(name).relative_to("qml")
        try:
            actual = digest(read_regular(path))
            result[name] = {
                "status": "match" if actual == expected else "mismatch",
                "expected_sha256": expected, "actual_sha256": actual,
            }
        except (OSError, PreparationError):
            # Avoid recording user-chosen absolute paths or exception strings.
            result[name] = {
                "status": "missing" if not path.exists() and not path.is_symlink() else "unsafe-or-unreadable",
                "expected_sha256": expected, "actual_sha256": None,
            }
    return result


def run_apply(workdir: Path, patch_path: Path, *, check: bool) -> None:
    """Apply only exact, line-numbered unified hunks, using Python stdlib.

    All files are validated in memory before any is written. The caller works
    on a disposable output tree and removes it if any write later fails.
    No git executable, discarded context lines or external patch tool is used.
    """
    patch_lines = read_regular(patch_path).splitlines(keepends=True)
    if not patch_lines or any(b"\r" in line or b"\x00" in line for line in patch_lines):
        raise PreparationError("Unsupported patch encoding or line endings")

    header = re.compile(rb"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@[^\n]*\n$")
    files: dict[str, list[tuple[int, int, int, int, list[tuple[bytes, bytes]]]]] = {}
    position = 0
    while position < len(patch_lines):
        # Git's optional per-file headers may be present, but are not needed
        # for the locked plain unified patch distributed with Lomiri Glass.
        git_path = None
        if patch_lines[position].startswith(b"diff --git "):
            match = re.fullmatch(rb"diff --git a/(\S+) b/\1\n", patch_lines[position])
            if not match:
                raise PreparationError("Unsupported Git patch header")
            git_path = match.group(1)
            position += 1
            if position < len(patch_lines) and patch_lines[position].startswith(b"index "):
                if not re.fullmatch(rb"index [0-9a-f]+\.\.[0-9a-f]+(?: [0-7]{6})?\n",
                                    patch_lines[position]):
                    raise PreparationError("Unsupported Git patch index")
                position += 1
        if position + 1 >= len(patch_lines):
            raise PreparationError("Truncated integration patch")
        old_name = re.fullmatch(rb"--- a/([A-Za-z0-9_./-]+)\n", patch_lines[position])
        new_name = re.fullmatch(rb"\+\+\+ b/([A-Za-z0-9_./-]+)\n", patch_lines[position + 1])
        if not old_name or not new_name or old_name.group(1) != new_name.group(1):
            raise PreparationError("Unsupported integration patch file headers")
        name = old_name.group(1).decode("ascii")
        relative_name(name, "qml")
        if name in files or (git_path is not None and git_path != old_name.group(1)):
            raise PreparationError("Repeated or mismatched integration patch path")
        position += 2
        hunks = []
        while position < len(patch_lines) and patch_lines[position].startswith(b"@@ "):
            match = header.fullmatch(patch_lines[position])
            if not match:
                raise PreparationError("Malformed unified-diff hunk")
            original_start = int(match.group(1))
            original_count = int(match.group(2)) if match.group(2) is not None else 1
            revised_start = int(match.group(3))
            revised_count = int(match.group(4)) if match.group(4) is not None else 1
            if (original_count and not original_start) or (revised_count and not revised_start):
                raise PreparationError("Invalid unified-diff line number")
            position += 1
            previous = following = 0
            changes = []
            while previous < original_count or following < revised_count:
                if position >= len(patch_lines):
                    raise PreparationError("Incomplete unified-diff hunk")
                entry = patch_lines[position]
                # The pinned patch represents some blank *context* lines as
                # an empty line instead of the conventional single-space
                # prefix. This is unambiguous and verified against the source.
                if entry == b"\n":
                    entry = b" \n"
                if len(entry) < 2 or entry[:1] not in (b" ", b"-", b"+") or not entry.endswith(b"\n"):
                    raise PreparationError("Unsupported or malformed unified-diff line")
                action, content = entry[:1], entry[1:]
                previous += action != b"+"
                following += action != b"-"
                if previous > original_count or following > revised_count:
                    raise PreparationError("Unified-diff hunk line count mismatch")
                changes.append((action, content))
                position += 1
            hunks.append((original_start, original_count, revised_start, revised_count, changes))
        if not hunks:
            raise PreparationError("Integration patch file contains no hunks")
        files[name] = hunks

    result: dict[Path, bytes] = {}
    for name, hunks in files.items():
        source_path = safe_path(workdir / name)
        original = read_regular(source_path).splitlines(keepends=True)
        revised: list[bytes] = []
        consumed = 0
        offset = 0
        for original_start, original_count, revised_start, revised_count, changes in hunks:
            requested = original_start - 1 if original_count else original_start
            nominal = requested + offset
            old_content = [content for action, content in changes if action != b"+"]
            if original_count:
                # Git's apply implementation also adjusts stale hunk line
                # numbers. Never drop context or search arbitrarily far:
                # require a full exact match within 24 lines of the expected
                # position and refuse equally close ambiguous matches.
                first = max(consumed, nominal - 24, 0)
                last = min(len(original) - original_count, nominal + 24)
                matches = [index for index in range(first, last + 1)
                           if original[index:index + original_count] == old_content]
                if not matches:
                    raise PreparationError(f"Integration patch is not applicable: {name} (context)")
                matches.sort(key=lambda index: abs(index - nominal))
                if len(matches) > 1 and abs(matches[0] - nominal) == abs(matches[1] - nominal):
                    raise PreparationError(f"Integration patch is ambiguous: {name}")
                start = matches[0]
            else:
                start = nominal
                if start < consumed or start > len(original):
                    raise PreparationError(f"Integration patch is not applicable: {name} (line number)")
            revised.extend(original[consumed:start])
            # The new-file offsets in the source-pinned patch are advisory:
            # like git apply, use the old-file positions and exact content to
            # prove applicability. Both hunk line counts are still enforced.
            cursor = start
            for action, content in changes:
                if action != b"+":
                    if cursor >= len(original) or original[cursor] != content:
                        raise PreparationError(f"Integration patch is not applicable: {name} (context)")
                    cursor += 1
                if action != b"-":
                    revised.append(content)
            consumed = cursor
            offset = start - requested
        revised.extend(original[consumed:])
        result[source_path] = b"".join(revised)

    if not check:
        for path, content in result.items():
            # O_NOFOLLOW additionally protects the destination file from a
            # final-component symlink introduced after the in-memory checks.
            fd = os.open(path, os.O_WRONLY | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0))
            with os.fdopen(fd, "wb") as stream:
                stream.write(content)


def contained(path: Path, parent: Path) -> bool:
    return path == parent or parent in path.parents


def tree_digest(files: dict[str, str]) -> str:
    return digest(json.dumps(files, sort_keys=True, separators=(",", ":")).encode())


def write_new_json(path: Path, value: dict) -> None:
    path = safe_path(path)
    if not path.parent.is_dir():
        raise PreparationError("The output parent directory must already exist")
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")


def prepare(source: Path, output: Path, package_dir: Path = DEFAULT_PACKAGE) -> dict:
    """Create a fresh output/qml tree, retaining the source byte-for-byte."""
    source = safe_path(source)
    output = safe_path(output)
    package_dir, lock, patch, module = load_package(package_dir)
    qml_root, layout = source_root(source)
    if output.exists():
        raise PreparationError("Output already exists; choose a new output directory")
    if not output.parent.is_dir():
        raise PreparationError("The output parent directory must already exist")
    if contained(output, source) or contained(source, output):
        raise PreparationError("Source and output must not contain one another")
    if contained(output, package_dir) or contained(package_dir, output):
        raise PreparationError("Package and output must not contain one another")
    originals = scan_tree(qml_root, ignore_git=True)
    checked = inspect_sources(qml_root, lock)
    if any(item["status"] != "match" for item in checked.values()):
        raise PreparationError("Source QML does not exactly match the locked upstream files")
    if (qml_root / "Panel/Glass").exists():
        raise PreparationError("Source already contains Panel/Glass; use an unmodified source tree")

    with tempfile.TemporaryDirectory(prefix="lomiri-glass-preflight-") as scratch:
        scratch = Path(scratch)
        patch_path = scratch / "integration.patch"
        patch_path.write_bytes(patch)
        for name in lock["files"]:
            destination = scratch / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(read_regular(qml_root / PurePosixPath(name).relative_to("qml")))
        run_apply(scratch, patch_path, check=True)

        output.mkdir(exist_ok=False)
        created_identity = (output.stat().st_dev, output.stat().st_ino)
        try:
            destination = output / "qml"
            # Never follow links while copying. The post-copy inventory rejects
            # any link introduced between initial inspection and this operation.
            shutil.copytree(qml_root, destination, symlinks=True,
                            ignore=shutil.ignore_patterns(".git"))
            copied = scan_tree(destination)
            if copied != originals:
                raise PreparationError("Source changed during copying")
            run_apply(output, patch_path, check=True)
            run_apply(output, patch_path, check=False)
            patched = scan_tree(destination)
            expected_modified = {str(PurePosixPath(name).relative_to("qml")) for name in lock["files"]}
            if set(patched) != set(originals):
                raise PreparationError("Patch unexpectedly created or removed files")
            actual_modified = {name for name in originals if originals[name] != patched[name]}
            if actual_modified != expected_modified:
                raise PreparationError("Patch modified an unexpected set of source files")
            shutil.copytree(package_dir / "qml/Glass", destination / "Panel/Glass", symlinks=True)
            if scan_tree(destination / "Panel/Glass") != module:
                raise PreparationError("Module changed during copying")
            prepared = scan_tree(destination)
            files = {
                name: {"kind": "modified", "original_sha256": checked[name]["actual_sha256"],
                       "prepared_sha256": prepared[str(PurePosixPath(name).relative_to("qml"))]}
                for name in sorted(lock["files"])
            }
            for name, sha in sorted(module.items()):
                files["qml/Panel/Glass/" + name] = {
                    "kind": "new", "original_sha256": None, "prepared_sha256": sha,
                }
            manifest = {
                "schema": 1, "kind": "isolated-qml-preparation",
                "created_utc": datetime.now(timezone.utc).isoformat(),
                "upstream": {key: lock[key] for key in ("repository", "ref", "commit")},
                "source_layout": layout, "patch_sha256": digest(patch),
                "original_tree_sha256": tree_digest(originals),
                "prepared_tree_sha256": tree_digest(prepared),
                "unchanged_files": len(originals) - len(expected_modified),
                "files": files, "source_modified": False,
                "installed": False, "hardware_validated": False,
                "validation": "Exact source/module hashes and strict Python unified-diff checks; no shell or D-Bus execution.",
            }
            write_new_json(output / "prepared-manifest.json", manifest)
            return manifest
        except BaseException:
            # Remove only the directory created in this call, never a replacement
            # or a pre-existing destination supplied by the user.
            try:
                info = output.lstat()
                if stat.S_ISDIR(info.st_mode) and (info.st_dev, info.st_ino) == created_identity:
                    shutil.rmtree(output)
            except FileNotFoundError:
                pass
            raise


def package_versions() -> dict[str, dict]:
    result = {name: {"status": "not-installed", "version": None} for name in PACKAGES}
    if shutil.which("dpkg-query") is None:
        return {name: {"status": "query-unavailable", "version": None} for name in PACKAGES}
    try:
        command = ["dpkg-query", "-W", "-f=${binary:Package}\t${Version}\t${db:Status-Abbrev}\n", *PACKAGES]
        completed = subprocess.run(command, capture_output=True, text=True, timeout=10, check=False)
        for line in completed.stdout.splitlines():
            fields = line.split("\t")
            if len(fields) == 3:
                name = fields[0].split(":", 1)[0]
                if name in result:
                    result[name] = {"status": "installed" if fields[2].startswith("ii") else "not-installed",
                                    "version": fields[1] or None}
    except (OSError, subprocess.TimeoutExpired):
        result = {name: {"status": "query-unavailable", "version": None} for name in PACKAGES}
    return result


def os_identity() -> dict[str, str]:
    allowed = {"NAME", "ID", "VERSION_ID", "VARIANT_ID", "PRETTY_NAME"}
    result = {}
    try:
        for line in Path("/etc/os-release").read_text(encoding="utf-8").splitlines():
            key, separator, value = line.partition("=")
            if separator and key in allowed:
                result[key] = value.strip('"\'')
    except OSError:
        pass
    return result


def inspect_cutout() -> dict:
    """Query the *active* libdeviceinfo profile, never guess S10+ pixels.

    Lomiri chooses its cutout-aware panel only when DisplayCutoutsCollapsed is
    defined. The physical rectangles must still be checked on the handset.
    """
    if shutil.which("device-info") is None:
        return {"status": "tool-unavailable", "collapsed_rectangles": [],
                "expanded_rectangles": [], "panel_height_px": None,
                "hardware_geometry_verified": False}

    def query(key: str) -> str:
        try:
            done = subprocess.run(["device-info", "get", key], capture_output=True,
                                  text=True, timeout=5, check=False)
            return done.stdout.strip()[:2048] if done.returncode == 0 else ""
        except (OSError, subprocess.TimeoutExpired):
            return ""

    def rectangles(data: str) -> list[list[int]]:
        if not data:
            return []
        parts = [part.strip().lstrip("- ") for part in data.split(",")]
        parsed = []
        for part in parts:
            if not re.fullmatch(r"[0-9]+(?:\s+[0-9]+){3}", part):
                return []
            x, y, width, height = (int(number) for number in part.split())
            if width <= 0 or height <= 0 or max(x, y, width, height) > 10000:
                return []
            parsed.append([x, y, width, height])
        return parsed

    raw_collapsed = query("DisplayCutoutsCollapsed")
    raw_expanded = query("DisplayCutoutsExpanded")
    collapsed = rectangles(raw_collapsed)
    expanded = rectangles(raw_expanded)
    panel_height = query("CollapsedPanelHeight")
    return {
        "status": "configured-unverified" if collapsed else "missing-or-invalid",
        "collapsed_rectangles": collapsed,
        "expanded_rectangles": expanded,
        "panel_height_px": int(panel_height) if re.fullmatch(r"[0-9]{1,5}", panel_height)
                                  else None,
        "hardware_geometry_verified": False,
    }


def probe(qml_root: Path, output: Path, package_dir: Path = DEFAULT_PACKAGE) -> dict:
    """Write a privacy-minimal read-only compatibility report to a new file."""
    qml_root = safe_path(qml_root)
    output = safe_path(output)
    if contained(output, qml_root):
        raise PreparationError("Probe report must be outside the inspected QML directory")
    _, lock, _, _ = load_package(package_dir)
    files = inspect_sources(qml_root, lock)
    matching = sum(info["status"] == "match" for info in files.values())
    architecture = platform.machine()
    if shutil.which("dpkg"):
        try:
            completed = subprocess.run(["dpkg", "--print-architecture"], capture_output=True,
                                       text=True, timeout=5, check=False)
            if completed.returncode == 0:
                architecture = completed.stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            pass
    report = {
        "schema": 1, "kind": "read-only-lomiri-qml-probe",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "os_release": os_identity(), "architecture": architecture,
        "packages": package_versions(), "files": files,
        "cutout_configuration": inspect_cutout(),
        "matching_files": matching, "expected_files": len(files),
        "all_expected_sources_match": matching == len(files),
        "upstream": {key: lock[key] for key in ("repository", "ref", "commit")},
        "installed": False, "hardware_validated": False,
        "validation": "A source match permits isolated preparation only. Cutout coordinates, native services and runtime compatibility require handset verification.",
    }
    write_new_json(output, report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    read = subparsers.add_parser("probe", help="Read system versions and locked QML hashes; write a new JSON report")
    read.add_argument("--qml-root", type=Path, default=Path("/usr/share/lomiri"))
    read.add_argument("--output", type=Path, required=True)
    read.add_argument("--package-dir", type=Path, default=DEFAULT_PACKAGE)
    stage = subparsers.add_parser("prepare", help="Prepare output/qml without modifying or installing the source")
    stage.add_argument("--source", type=Path, required=True)
    stage.add_argument("--output", type=Path, required=True)
    stage.add_argument("--package-dir", type=Path, default=DEFAULT_PACKAGE)
    args = parser.parse_args(argv)
    try:
        if args.command == "probe":
            result = probe(args.qml_root, args.output, args.package_dir)
            print(json.dumps({"report": str(args.output), "matching_files": result["matching_files"],
                              "expected_files": result["expected_files"],
                              "all_expected_sources_match": result["all_expected_sources_match"]}))
            return 0 if result["all_expected_sources_match"] else 2
        result = prepare(args.source, args.output, args.package_dir)
        print(json.dumps({"prepared": str(args.output), "changed_or_new_files": len(result["files"]),
                          "installed": False, "hardware_validated": False}))
        return 0
    except (OSError, PreparationError, ValueError) as exc:
        print(f"lomiri-glass: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
