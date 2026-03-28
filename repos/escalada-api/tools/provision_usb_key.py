#!/usr/bin/env python3
"""Provision `competition.key` on a mounted USB stick."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - optional convenience
    load_dotenv = None

try:
    import psutil
except Exception as exc:  # pragma: no cover - runtime guard
    print(f"Error: psutil is required ({exc}).", file=sys.stderr)
    sys.exit(1)

from escalada.security.usb_license import build_expected_key
from escalada.security.usb_license import canonicalize_fs_name


def _normalize_mountpoint(value: str) -> str:
    cleaned = os.path.expanduser((value or "").strip())
    if not cleaned:
        return ""
    if os.name == "nt":
        cleaned = cleaned.replace("/", "\\")
        if len(cleaned) == 2 and cleaned[1] == ":":
            cleaned = f"{cleaned}\\"
    return os.path.normpath(cleaned)


def _same_mountpoint(left: str, right: str) -> bool:
    left_normalized = os.path.normcase(os.path.normpath(left or ""))
    right_normalized = os.path.normcase(os.path.normpath(right or ""))
    return left_normalized == right_normalized


def _find_partition(mountpoint: str):
    for partition in psutil.disk_partitions(all=False):
        if _same_mountpoint(partition.mountpoint, mountpoint):
            return partition
    return None


def _confirm_overwrite(path: Path) -> bool:
    answer = input(f"`{path}` already exists. Overwrite? [y/N]: ").strip().lower()
    return answer in {"y", "yes"}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate and write competition.key for a mounted USB stick.",
    )
    parser.add_argument(
        "mountpoint",
        help="Mounted USB path (examples: /Volumes/KEY, /media/user/KEY, E:\\)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing competition.key without prompting.",
    )
    args = parser.parse_args()

    if load_dotenv is not None:
        load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env", override=True)

    secret = (os.getenv("USB_LICENSE_SECRET") or "").strip()
    if not secret:
        print("Error: USB_LICENSE_SECRET is not set.", file=sys.stderr)
        return 1

    mountpoint = _normalize_mountpoint(args.mountpoint)
    if not mountpoint:
        print("Error: invalid mountpoint.", file=sys.stderr)
        return 1

    partition = _find_partition(mountpoint)
    if partition is None:
        print(
            f"Error: mountpoint `{mountpoint}` is not listed by psutil.disk_partitions().",
            file=sys.stderr,
        )
        return 1

    key_path = Path(partition.mountpoint) / "competition.key"

    try:
        usage = psutil.disk_usage(partition.mountpoint)
    except Exception as exc:
        print(f"Error: cannot read disk usage for `{partition.mountpoint}` ({exc}).", file=sys.stderr)
        return 1

    fs_name = canonicalize_fs_name(partition.fstype)
    total_bytes = int(usage.total)
    expected_key = build_expected_key(
        fs_name=fs_name,
        total_bytes=total_bytes,
        secret=secret,
    )

    if key_path.exists() and not args.force and not _confirm_overwrite(key_path):
        print("Aborted.")
        return 1

    try:
        key_path.write_text(f"{expected_key}\n", encoding="utf-8")
    except Exception as exc:
        print(f"Error: failed writing `{key_path}` ({exc}).", file=sys.stderr)
        return 1

    print("USB key provisioned successfully.")
    print(f"mountpoint: {partition.mountpoint}")
    print(f"filesystem: {fs_name or '(unknown)'}")
    print(f"total_bytes: {total_bytes}")
    print(f"written_file: {key_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
