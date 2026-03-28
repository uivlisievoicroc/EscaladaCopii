# EscaladaCopii Monorepo Guide

## Layout
- `repos/escalada-api`: FastAPI backend and runtime packaging assets.
- `repos/escalada-core`: pure contest/business logic package used by the API.
- `repos/escalada-ui`: React + Vite frontend.
- `repos/escalada-judge-android`: Android WebView shell for the judge flow.
- `scripts/` and `packaging/`: monorepo-level release/orchestration utilities.

## Working conventions
- Keep business rules in `repos/escalada-core`; API and UI should orchestrate rather than duplicate logic.
- Root workflows and release scripts assume the component layout under `repos/`.
- Component-local tooling stays in each component repo:
  - API/Core: Poetry
  - UI: npm/Vite
  - Judge Android: Gradle/Android Studio

## Local commands
```bash
# Core
cd repos/escalada-core
poetry install --with dev --no-root
poetry run pytest -q

# API
cd ../escalada-api
poetry install --with dev
poetry run pip install -e ../escalada-core
poetry run pytest tests -q

# UI
cd ../escalada-ui
npm install
npm test -- --run
npm run smoke:build
```

## Release flow
- Root release scripts expect `repos/escalada-api`, `repos/escalada-ui`, and `repos/escalada-core`.
- Use `python scripts/build_release.py --api-dir repos/escalada-api --ui-dir repos/escalada-ui --core-dir repos/escalada-core ...`.
- Do not reintroduce cross-repo GitHub checkout logic in root workflows; the monorepo already contains the sources.
