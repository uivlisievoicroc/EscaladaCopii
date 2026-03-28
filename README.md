# EscaladaCopii

Monorepo local pentru clonarea și transformarea stack-ului Escalada.

## Structură
- `repos/escalada-api`: backend FastAPI și runtime server.
- `repos/escalada-core`: logica pură de concurs.
- `repos/escalada-ui`: frontend React + Vite.
- `repos/escalada-judge-android`: shell Android pentru judge remote.
- `scripts/` și `packaging/`: orchestrare, smoke checks și build-uri de release.

## Quick start
```bash
cd repos/escalada-ui
npm install
npm run build

cd ../escalada-api
poetry install --with dev
poetry run pip install -e ../escalada-core

export ESCALADA_FRONTEND_DIST=../escalada-ui/dist
export STORAGE_DIR=./data
poetry run uvicorn escalada.main:app --host 0.0.0.0 --port 8000 --workers 1
```

## Teste
```bash
cd repos/escalada-core
poetry run pytest -q

cd ../escalada-api
poetry run pytest tests/ -q

cd ../escalada-ui
npm test -- --run
npm run smoke:build
```

## Release local
```bash
python scripts/build_release.py \
  --api-dir repos/escalada-api \
  --ui-dir repos/escalada-ui \
  --core-dir repos/escalada-core \
  --mode both \
  --release-dir release/local
```
