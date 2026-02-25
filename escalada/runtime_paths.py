"""Runtime paths and legacy migration helpers for packaged/server runs."""

from __future__ import annotations

import json
import logging
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

APP_NAME = "EscaladaServer"


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _is_truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _default_app_data_root() -> Path:
    home = Path.home()

    if sys.platform.startswith("win"):
        base = Path(os.getenv("APPDATA") or (home / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = home / "Library" / "Application Support"
    else:
        base = Path(os.getenv("XDG_DATA_HOME") or (home / ".local" / "share"))

    return base / APP_NAME


def app_data_root() -> Path:
    override = os.getenv("ESCALADA_APPDATA_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return _default_app_data_root().resolve()


def describe_runtime_paths() -> dict[str, str]:
    root = app_data_root()
    return {
        "app_data_dir": str(root),
        "storage_dir": str(Path(os.getenv("STORAGE_DIR", str(root / "storage"))).resolve()),
        "backup_dir": str(Path(os.getenv("BACKUP_DIR", str(root / "backups"))).resolve()),
        "exports_dir": str(Path(os.getenv("ESCALADA_EXPORTS_DIR", str(root / "exports" / "clasamente"))).resolve()),
        "log_file": str(Path(os.getenv("ESCALADA_LOG_FILE", str(root / "logs" / "escalada.log"))).resolve()),
        "secrets_dir": str(Path(os.getenv("ESCALADA_SECRETS_DIR", str(root / "secrets"))).resolve()),
    }


def ensure_runtime_dirs() -> dict[str, str]:
    paths = describe_runtime_paths()

    Path(paths["app_data_dir"]).mkdir(parents=True, exist_ok=True)
    Path(paths["storage_dir"]).mkdir(parents=True, exist_ok=True)
    Path(paths["backup_dir"]).mkdir(parents=True, exist_ok=True)
    Path(paths["exports_dir"]).mkdir(parents=True, exist_ok=True)
    Path(paths["secrets_dir"]).mkdir(parents=True, exist_ok=True)
    Path(paths["log_file"]).parent.mkdir(parents=True, exist_ok=True)

    return paths


def resolve_frontend_dist_dir() -> Path:
    env_override = os.getenv("ESCALADA_FRONTEND_DIST", "").strip()
    if env_override:
        return Path(env_override).expanduser().resolve()

    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        packaged = Path(meipass) / "frontend_dist"
        if packaged.exists():
            return packaged

    source_dir = Path(__file__).resolve().parents[1] / "frontend_dist"
    if source_dir.exists():
        return source_dir

    return source_dir


def _ensure_unique_legacy_target(path: Path, stamp: str) -> Path:
    target = path.with_name(f"{path.name}.legacy.{stamp}")
    suffix = 1
    while target.exists():
        target = path.with_name(f"{path.name}.legacy.{stamp}.{suffix}")
        suffix += 1
    return target


def _copy_entry(src: Path, dst: Path) -> None:
    if src.is_dir():
        dst.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dst, dirs_exist_ok=True)
        return

    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def _has_content(path: Path) -> bool:
    if path.is_file():
        return True
    if not path.is_dir():
        return False
    for _ in path.rglob("*"):
        return True
    return False


def _verify_copied(src: Path, dst: Path) -> None:
    if not dst.exists():
        raise RuntimeError(f"Missing copied destination: {dst}")

    if src.is_dir() and _has_content(src) and not _has_content(dst):
        raise RuntimeError(f"Copied directory has no content: {dst}")


def migrate_legacy_data(logger: logging.Logger, paths: dict[str, str] | None = None) -> None:
    runtime_paths = paths or ensure_runtime_dirs()
    root = Path(runtime_paths["app_data_dir"])
    marker_path = root / "migration_done.json"

    if marker_path.exists():
        return

    legacy_map: list[tuple[Path, Path]] = [
        (Path.cwd() / "data", Path(runtime_paths["storage_dir"])),
        (Path.cwd() / "backups", Path(runtime_paths["backup_dir"])),
        (Path.cwd() / "escalada" / "clasamente", Path(runtime_paths["exports_dir"])),
        (Path.cwd() / "escalada.log", Path(runtime_paths["log_file"])),
    ]
    existing = [(src, dst) for src, dst in legacy_map if src.exists()]
    if not existing:
        marker_payload = {
            "timestamp": _utc_stamp(),
            "status": "no_legacy_found",
            "cwd": str(Path.cwd()),
        }
        marker_path.write_text(json.dumps(marker_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return

    stamp = _utc_stamp()
    migration_backup_root = root / "migration_backups" / stamp
    migration_backup_root.mkdir(parents=True, exist_ok=True)
    logger.info("Starting one-time legacy migration (%s)", stamp)
    logger.info("Migration backup directory: %s", migration_backup_root)

    copied_entries: list[dict[str, Any]] = []

    for src, dst in existing:
        logger.info("Migration step: copy %s -> %s", src, dst)

        if dst.exists():
            backup_target = migration_backup_root / dst.name
            logger.info("Migration step: backup existing destination %s -> %s", dst, backup_target)
            _copy_entry(dst, backup_target)

        _copy_entry(src, dst)
        _verify_copied(src, dst)
        copied_entries.append({"source": str(src), "destination": str(dst)})

    marker_payload = {
        "timestamp": stamp,
        "status": "copied_verified",
        "cwd": str(Path.cwd()),
        "items": copied_entries,
    }
    marker_path.write_text(json.dumps(marker_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Migration step: wrote marker %s", marker_path)

    for src, _ in existing:
        legacy_target = _ensure_unique_legacy_target(src, stamp)
        logger.info("Migration step: rename legacy %s -> %s", src, legacy_target)
        src.rename(legacy_target)

    logger.info("Legacy migration completed successfully.")


def configure_runtime_environment(logger: logging.Logger) -> dict[str, str]:
    root = app_data_root()
    os.environ.setdefault("STORAGE_DIR", str(root / "storage"))
    os.environ.setdefault("BACKUP_DIR", str(root / "backups"))
    os.environ.setdefault("ESCALADA_EXPORTS_DIR", str(root / "exports" / "clasamente"))
    os.environ.setdefault("ESCALADA_LOG_FILE", str(root / "logs" / "escalada.log"))
    os.environ.setdefault("ESCALADA_SECRETS_DIR", str(root / "secrets"))

    paths = ensure_runtime_dirs()

    if not _is_truthy(os.getenv("ESCALADA_SKIP_LEGACY_MIGRATION")):
        migrate_legacy_data(logger=logger, paths=paths)

    return paths

