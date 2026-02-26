#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

BINARY_NAME = "EscaladaServer"

MACOS_START_COMMAND_NAME = "Start EscaladaServer.command"
MACOS_START_COMMAND_CONTENT = """#!/bin/bash
set -euo pipefail

PORT_MIN="${ESCALADA_PORT_MIN:-8000}"
PORT_MAX="${ESCALADA_PORT_MAX:-8100}"

DIR="$(cd "$(dirname "$0")" && pwd)"

# Prefer secret-file (dacă există), evită env accidental setat global.
SECRET_FILE="$HOME/Library/Application Support/EscaladaServer/secrets/usb_license_secret.txt"
if [ -s "$SECRET_FILE" ]; then
  unset USB_LICENSE_SECRET || true
fi

# Locate binary (onefile vs onedir)
BIN=""
if [ -x "$DIR/EscaladaServer" ] && [ -f "$DIR/EscaladaServer" ]; then
  BIN="$DIR/EscaladaServer"
elif [ -x "$DIR/EscaladaServer/EscaladaServer" ]; then
  BIN="$DIR/EscaladaServer/EscaladaServer"
else
  echo "Nu găsesc binarul EscaladaServer lângă acest fișier."
  echo "Așteptat: $DIR/EscaladaServer  sau  $DIR/EscaladaServer/EscaladaServer"
  read -r -p "Enter ca să ieși..."
  exit 1
fi

chmod +x "$BIN" 2>/dev/null || true

# Best-effort LAN IPv4 (default route interface)
iface="$(route get default 2>/dev/null | awk '/interface:/{print $2; exit}')"
lan_ip=""
if [ -n "$iface" ]; then
  lan_ip="$(ipconfig getifaddr "$iface" 2>/dev/null || true)"
fi
if [ -z "$lan_ip" ]; then
  for ifc in en0 en1; do
    lan_ip="$(ipconfig getifaddr "$ifc" 2>/dev/null || true)"
    [ -n "$lan_ip" ] && break
  done
fi
[ -z "$lan_ip" ] && lan_ip="127.0.0.1"

echo "Starting EscaladaServer..."
"$BIN" &
pid=$!

cleanup() {
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null || true
  fi
}
trap cleanup EXIT

selected=""
if command -v curl >/dev/null 2>&1; then
  for _ in $(seq 1 120); do
    for p in $(seq "$PORT_MIN" "$PORT_MAX"); do
      if curl -fsS --max-time 0.3 "http://127.0.0.1:${p}/api/runtime" >/dev/null 2>&1; then
        selected="$p"
        break
      fi
    done
    [ -n "$selected" ] && break
    sleep 0.25
  done
fi

echo ""
if [ -n "$selected" ]; then
  echo "LAN URL (pentru QR): http://${lan_ip}:${selected}/"
  open "http://${lan_ip}:${selected}/" >/dev/null 2>&1 || true
else
  echo "Nu am detectat automat portul. Uită-te în log pentru portul ales (8000..8100), apoi deschide:"
  echo "  http://${lan_ip}:<port>/"
fi

echo ""
echo "Ține această fereastră deschisă în timpul concursului."
echo "Stop: Ctrl+C sau închide fereastra."
wait "$pid"
"""


def run(cmd: list[str], cwd: Path | None = None, env: dict[str, str] | None = None) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, cwd=cwd, env=env, check=True)


def detect_platform_slug() -> str:
    system = platform.system().lower()
    if system.startswith("windows"):
        return "windows-x64"
    if system == "darwin":
        return "macos"
    if system == "linux":
        return "linux-x64"
    raise RuntimeError(f"Unsupported platform: {platform.system()}")


def archive_kind() -> str:
    return "zip" if platform.system().lower() in {"windows", "darwin"} else "tar.gz"


def sha256sum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def make_archive(source: Path, destination: Path, kind: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if kind == "zip":
        with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            if source.is_dir():
                for item in source.rglob("*"):
                    if item.is_file():
                        zf.write(item, item.relative_to(source.parent))
            else:
                zf.write(source, source.name)
        return

    if kind == "tar.gz":
        with tarfile.open(destination, "w:gz") as tf:
            tf.add(source, arcname=source.name)
        return

    raise RuntimeError(f"Unsupported archive kind: {kind}")


def make_archive_dir_contents(source_dir: Path, destination: Path, kind: str) -> None:
    """Archive the *contents* of a directory (not the directory itself)."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    if kind == "zip":
        with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for item in source_dir.rglob("*"):
                if item.is_file():
                    zf.write(item, item.relative_to(source_dir))
        return

    if kind == "tar.gz":
        with tarfile.open(destination, "w:gz") as tf:
            for item in source_dir.iterdir():
                tf.add(item, arcname=item.name)
        return

    raise RuntimeError(f"Unsupported archive kind: {kind}")


def parse_version() -> str:
    tag = os.getenv("GITHUB_REF_NAME", "").strip()
    if tag.startswith("v") and len(tag) > 1:
        return tag[1:]
    return "local"


def build_frontend(ui_dir: Path, api_dir: Path) -> None:
    run(["npm", "ci"], cwd=ui_dir)
    run(["npm", "run", "build"], cwd=ui_dir)

    source_dist = ui_dir / "dist"
    target_dist = api_dir / "frontend_dist"

    if not source_dist.exists():
        raise FileNotFoundError(f"Frontend dist not found: {source_dist}")

    if target_dist.exists():
        shutil.rmtree(target_dist)

    shutil.copytree(source_dist, target_dist)
    print(f"Copied frontend dist -> {target_dist}")


def install_python_dependencies(api_dir: Path, core_dir: Path) -> None:
    run(["poetry", "install", "--with", "dev"], cwd=api_dir)
    run(["poetry", "run", "pip", "install", "-e", str(core_dir)], cwd=api_dir)
    run(["poetry", "run", "pip", "install", "pyinstaller"], cwd=api_dir)


def run_smoke(orch_root: Path, api_dir: Path, port_min: int, port_max: int) -> None:
    env = os.environ.copy()
    env["ESCALADA_SMOKE_NON_HARDWARE"] = "1"
    run(
        [
            sys.executable,
            str(orch_root / "scripts" / "smoke_runtime.py"),
            "--target",
            "source",
            "--api-dir",
            str(api_dir),
            "--port-min",
            str(port_min),
            "--port-max",
            str(port_max),
        ],
        cwd=orch_root,
        env=env,
    )


def run_pyinstaller_for_mode(
    orch_root: Path,
    api_dir: Path,
    mode: str,
    dist_dir: Path,
    work_dir: Path,
) -> Path:
    spec_path = orch_root / "packaging" / "pyinstaller.spec"
    env = os.environ.copy()
    env["ESCALADA_API_DIR"] = str(api_dir)
    env["ESCALADA_PYI_MODE"] = mode

    if dist_dir.exists():
        shutil.rmtree(dist_dir)
    if work_dir.exists():
        shutil.rmtree(work_dir)

    run(
        [
            "poetry",
            "run",
            "pyinstaller",
            "--noconfirm",
            "--clean",
            str(spec_path),
            "--distpath",
            str(dist_dir),
            "--workpath",
            str(work_dir),
        ],
        cwd=api_dir,
        env=env,
    )

    if mode == "onefile":
        exe_name = f"{BINARY_NAME}.exe" if platform.system().lower().startswith("windows") else BINARY_NAME
        return dist_dir / exe_name

    return dist_dir / BINARY_NAME


def write_checksums(files: list[Path], output_file: Path) -> None:
    lines = [f"{sha256sum(path)}  {path.name}" for path in files]
    output_file.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    root = Path(__file__).resolve().parents[1]

    parser = argparse.ArgumentParser(description="Build Escalada release artifacts.")
    parser.add_argument("--api-dir", type=Path, default=root / "repos" / "escalada-api")
    parser.add_argument("--ui-dir", type=Path, default=root / "repos" / "escalada-ui")
    parser.add_argument("--core-dir", type=Path, default=root / "repos" / "escalada-core")
    parser.add_argument("--mode", choices=["onedir", "onefile", "both"], default="both")
    parser.add_argument("--release-dir", type=Path, default=None)
    parser.add_argument("--port-min", type=int, default=int(os.getenv("ESCALADA_PORT_MIN", "8000")))
    parser.add_argument("--port-max", type=int, default=int(os.getenv("ESCALADA_PORT_MAX", "8100")))
    args = parser.parse_args()

    api_dir = args.api_dir.resolve()
    ui_dir = args.ui_dir.resolve()
    core_dir = args.core_dir.resolve()
    platform_slug = detect_platform_slug()
    version = parse_version()

    release_dir = (args.release_dir.resolve() if args.release_dir else (root / "release" / platform_slug))
    release_dir.mkdir(parents=True, exist_ok=True)

    for required in [api_dir, ui_dir, core_dir]:
        if not required.exists():
            raise FileNotFoundError(f"Missing required directory: {required}")

    build_frontend(ui_dir=ui_dir, api_dir=api_dir)
    install_python_dependencies(api_dir=api_dir, core_dir=core_dir)
    run_smoke(orch_root=root, api_dir=api_dir, port_min=args.port_min, port_max=args.port_max)

    modes = ["onedir", "onefile"] if args.mode == "both" else [args.mode]
    archives: list[Path] = []
    kind = archive_kind()

    for mode in modes:
        dist_dir = root / "dist" / mode
        work_dir = root / "build" / mode
        built_path = run_pyinstaller_for_mode(
            orch_root=root,
            api_dir=api_dir,
            mode=mode,
            dist_dir=dist_dir,
            work_dir=work_dir,
        )

        if not built_path.exists():
            raise FileNotFoundError(f"PyInstaller output not found for mode={mode}: {built_path}")

        stem = f"{BINARY_NAME}-{version}-{platform_slug}-{mode}"
        extension = ".zip" if kind == "zip" else ".tar.gz"
        archive_path = release_dir / f"{stem}{extension}"
        if platform.system().lower() == "darwin":
            with tempfile.TemporaryDirectory(prefix=f"escalada_bundle_{mode}_") as tmp_dir:
                bundle_root = Path(tmp_dir)
                bundled_target = bundle_root / built_path.name
                if built_path.is_dir():
                    shutil.copytree(built_path, bundled_target)
                else:
                    shutil.copy2(built_path, bundled_target)

                launcher_path = bundle_root / MACOS_START_COMMAND_NAME
                launcher_path.write_text(MACOS_START_COMMAND_CONTENT, encoding="utf-8")
                try:
                    launcher_path.chmod(0o755)
                except Exception:
                    pass

                make_archive_dir_contents(source_dir=bundle_root, destination=archive_path, kind=kind)
        else:
            make_archive(source=built_path, destination=archive_path, kind=kind)
        archives.append(archive_path)
        print(f"Created artifact: {archive_path}")

    checksums_path = release_dir / "SHA256SUMS.txt"
    write_checksums(archives, checksums_path)
    print(f"Wrote checksums: {checksums_path}")


if __name__ == "__main__":
    main()
