#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def run(cmd: list[str], cwd: Path) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, cwd=cwd, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Export public snapshot via API internal generator.")
    parser.add_argument("--api-dir", type=Path, default=Path("repos/escalada-api"))
    parser.add_argument("--output", type=Path, default=Path("release/public_snapshot.json"))
    args = parser.parse_args()

    api_dir = args.api_dir.resolve()
    output = args.output.resolve()

    if not api_dir.exists():
        raise FileNotFoundError(f"API dir not found: {api_dir}")

    output.parent.mkdir(parents=True, exist_ok=True)
    run(
        [
            "poetry",
            "run",
            "python",
            "scripts/export_public_snapshot.py",
            "--output",
            str(output),
        ],
        cwd=api_dir,
    )


if __name__ == "__main__":
    main()
