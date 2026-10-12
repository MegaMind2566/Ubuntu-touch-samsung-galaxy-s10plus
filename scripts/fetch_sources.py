#!/usr/bin/env python3
"""Fetch exact upstream commits; never discard local edits or hide Git failures."""
import argparse
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def git(path, *args, capture=False):
    return subprocess.run(
        ["git", "-C", str(path), *args], check=True, text=True,
        stdout=subprocess.PIPE if capture else None,
    ).stdout


def read_lock():
    lock = json.loads((ROOT / "config/upstream.lock.json").read_text())
    if lock["schema"] != 1:
        raise ValueError("Unsupported source lock schema")
    for spec in lock["sources"].values():
        if not re.fullmatch(r"[0-9a-f]{40}", spec["commit"]):
            raise ValueError("Every source must have a full commit SHA")
        if Path(spec["directory"]).name != spec["directory"]:
            raise ValueError("Source directory must be a single path component")
    return lock


def checkout(spec, dest):
    dest = Path(dest).resolve()
    if (dest / ".git").exists():
        if git(dest, "status", "--porcelain", capture=True).strip():
            raise RuntimeError(f"Refusing to replace local changes in {dest}")
        actual_url = git(dest, "remote", "get-url", "origin", capture=True).strip()
        if actual_url.removesuffix(".git") != spec["url"].removesuffix(".git"):
            raise RuntimeError(f"Unexpected source remote in {dest}")
    else:
        if dest.exists() and any(dest.iterdir()):
            raise RuntimeError(f"Refusing nonempty, non-Git directory {dest}")
        dest.mkdir(parents=True, exist_ok=True)
        git(dest, "init", "--quiet")
        git(dest, "remote", "add", "origin", spec["url"])
    exists = subprocess.run(
        ["git", "-C", str(dest), "cat-file", "-e", spec["commit"] + "^{commit}"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    ).returncode == 0
    if not exists:
        git(dest, "fetch", "--depth=1", "--no-tags", "origin", spec["commit"])
    git(dest, "checkout", "--quiet", "--detach", spec["commit"])
    actual = git(dest, "rev-parse", "HEAD", capture=True).strip()
    if actual != spec["commit"]:
        raise RuntimeError(f"Pinned revision mismatch in {dest}")
    return dest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dest", type=Path, default=ROOT / "upstream")
    parser.add_argument("--include-kernel", action="store_true")
    args = parser.parse_args()
    lock = read_lock()
    selected = ["port", "tools"] + (["kernel"] if args.include_kernel else [])
    for name in selected:
        spec = lock["sources"][name]
        dest = checkout(spec, args.dest / spec["directory"])
        print(f"{name}: {spec['commit']} ({dest})", flush=True)
    args.dest.mkdir(parents=True, exist_ok=True)
    (args.dest / "upstream-revision.txt").write_text(lock["sources"]["port"]["commit"] + "\n")
    (args.dest / "source-manifest.json").write_text(json.dumps(lock, indent=2) + "\n")


if __name__ == "__main__":
    main()
