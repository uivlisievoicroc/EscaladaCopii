#!/usr/bin/env python3
"""Generate one-time emergency recovery codes and persist only their hashes."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path

from escalada.security import recovery_codes

ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _generate_code() -> str:
    chunks = []
    for _ in range(4):
        chunks.append("".join(secrets.choice(ALPHABET) for _ in range(4)))
    return "-".join(chunks)


def _build_store(codes: list[str]) -> dict:
    return {
        "version": recovery_codes.STORE_VERSION,
        "created_at": _utcnow_iso(),
        "override_ttl_hours": recovery_codes.OVERRIDE_TTL_HOURS,
        "codes": [
            {
                "code_id": f"rc_{index:03d}",
                "hash": recovery_codes.hash_recovery_code(code),
                "used_at": None,
            }
            for index, code in enumerate(codes, start=1)
        ],
        "override": {
            "active_until": None,
            "activated_at": None,
            "activated_by_ip": None,
        },
    }


def _write_store(path: Path, store: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(
        json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    os.replace(tmp_path, path)
    try:
        os.chmod(path, 0o600)
    except Exception:
        pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate emergency recovery codes.")
    parser.add_argument(
        "--count", type=int, default=20, help="Number of codes to generate."
    )
    parser.add_argument(
        "--out",
        type=str,
        default="",
        help="Optional explicit path for recovery_codes.json (defaults to ESCALADA_SECRETS_DIR).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing file if present.",
    )
    args = parser.parse_args()

    if args.count <= 0:
        print("Error: --count must be > 0.", file=sys.stderr)
        return 1

    generated_codes = [_generate_code() for _ in range(args.count)]
    store = _build_store(generated_codes)

    output_path: Path
    if args.out.strip():
        output_path = Path(args.out.strip()).expanduser().resolve()
    else:
        output_path = recovery_codes.get_recovery_store_path()

    if output_path.exists() and not args.force:
        print(
            f"Error: `{output_path}` already exists. Use --force to overwrite.",
            file=sys.stderr,
        )
        return 1

    _write_store(output_path, store)

    print("==============================================")
    print("  PRINT THESE ON PAPER AND STORE SECURELY")
    print("  Codes are shown ONCE and never stored plain.")
    print("==============================================")
    print()
    for index, code in enumerate(generated_codes, start=1):
        print(f"{index:02d}. {code}")
    print()
    print(f"Hashed recovery store written to: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
