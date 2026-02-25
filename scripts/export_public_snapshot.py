#!/usr/bin/env python3
"""Export public snapshot directly from internal runtime state (no HTTP self-pull)."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from escalada.api.live import _build_public_snapshot_payload


async def _generate_snapshot() -> dict:
    return await _build_public_snapshot_payload()


def main() -> None:
    parser = argparse.ArgumentParser(description="Export public snapshot JSON.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("public_snapshot.json"),
        help="Output JSON path.",
    )
    args = parser.parse_args()

    payload = asyncio.run(_generate_snapshot())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Public snapshot exported to {args.output}")


if __name__ == "__main__":
    main()

