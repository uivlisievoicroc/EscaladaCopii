# Escalada Frontend (React + Vite)

Frontend UI for the Escalada real-time climbing competition system.

## Quick Start

```bash
npm install
npm run dev
```

For live admin/judge/public flows served by the backend on `:8000`:

```bash
npm run build
# Optional: write the build directly into escalada-api/frontend_dist
npm run build:api-dist
```

The backend can then serve the current UI build via `ESCALADA_FRONTEND_DIST=../escalada-ui/dist`.

## Tests

```bash
npm test -- --run
npm run smoke:build
# E2E
npx playwright test --reporter=list
```

## Formatting & Hooks

- Frontend formatting is enforced with Prettier via Husky + lint-staged.
- On commit, staged files in `src/` are automatically formatted.

Manual format:

```bash
npm run format
```

Backend API se rulează separat (repo `escalada-api`) dacă ai nevoie de live WS/HTTP.
