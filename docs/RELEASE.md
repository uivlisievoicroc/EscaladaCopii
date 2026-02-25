# RELEASE

## Ownership model
Release source of truth is in orchestrator repo:

- Workflow: `.github/workflows/release.yml`
- Build script: `scripts/build_release.py`
- Smoke script: `scripts/smoke_runtime.py`
- PyInstaller spec: `packaging/pyinstaller.spec`

Runtime code stays in `repos/escalada-api`.

## Local build commands

From orchestrator root:

```bash
python scripts/build_release.py \
  --api-dir repos/escalada-api \
  --ui-dir repos/escalada-ui \
  --core-dir repos/escalada-core \
  --mode both \
  --release-dir release/local
```

Output:
- `release/<target>/...onedir...`
- `release/<target>/...onefile...`
- `release/<target>/SHA256SUMS.txt`

## CI release flow (tagged)
1. Push tag `vX.Y.Z` to orchestrator repo.
2. GitHub Actions `Release` workflow runs matrix builds on:
- `windows-latest`
- `macos-latest`
- `ubuntu-latest`
3. Smoke checks run before packaging (non-hardware USB mode).
4. Artifacts and checksums are uploaded.
5. Assets are attached to GitHub Release for the same tag.

## Checksum verification

macOS/Linux:
```bash
cd release/<target>
shasum -a 256 -c SHA256SUMS.txt
```

Windows PowerShell:
```powershell
Get-Content SHA256SUMS.txt
# Compare with:
Get-FileHash .\artifact-name.zip -Algorithm SHA256
```

## Notes
- macOS code signing/notarization is optional in this phase; unsigned app guidance is in `docs/RUN.md`.
- Windows firewall prompt is expected on first run; allow private network access for LAN usage.

## Release checklist
1. Ensure `main` CI is green.
2. Run local release build once.
3. Verify checksums.
4. Tag version `vX.Y.Z`.
5. Confirm all OS artifacts in GitHub Release.
6. Do one LAN smoke run on real venue hardware.
