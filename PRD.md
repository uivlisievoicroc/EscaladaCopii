# EscaladaCopii PRD

Reverse-engineered product requirements for the current repository state. This document describes the product that exists in code, not a future roadmap.

## Product Summary

EscaladaCopii is a local, real-time lead-climbing competition system for running categories across one or more judging boxes. It lets an admin prepare categories from Excel listboxes, assign them to boxes, operate or supervise live judging, show contest displays, publish spectator views, compute rankings with lead-specific tiebreaks, export official results, and recover contest state during event-day failures.

The system is built for controlled LAN operation. The backend is the authoritative runtime for box state, timers, scoring, rankings, backups, audit logs, and admin security. The frontend is served as a single-page app with admin, judge, contest-display, and public spectator routes. A separate Android shell embeds the judge remote in a WebView and maps hardware volume buttons to hold updates.

## Users And Roles

**Admin**:
Configures categories, uploads listboxes, initializes boxes, sets timers and officials, manages judge access, controls live flow when needed, resolves tiebreaks, exports results, reviews audit events, and performs backup/restore operations.

**Judge**:
Operates one assigned box through the Judge Remote, controlling timer state, hold progress, registered time, and score submission.

**Viewer**:
Can view authorized box state without admin mutation permissions.

**Spectator**:
Uses unauthenticated public pages for live rankings, live climbing, and competition officials.

**Competition Official**:
Is represented as event metadata in public and export views, not as an authenticated application actor.

## Core Concepts

- A competition contains one or more categories.
- A category runs on one active box at a time.
- A box runs one route at a time for its category.
- A category contains competitors, optionally with club names.
- Each route has a configured maximum hold count.
- Each competitor can receive one score and optional registered time per route.
- Scores use lead-climbing notation: whole holds plus optional `+` progress represented internally as `.1`.
- A top is represented when the submitted score reaches the route hold total.

## Primary Workflows

### Admin Setup

1. The admin opens the Control Panel at `/`.
2. The admin unlocks admin actions using the configured admin security flow.
3. The admin uploads an `.xlsx` listbox with category name, route count, holds per route, and competitor rows.
4. The uploaded category appears as a local box/listbox in the Control Panel.
5. The admin sets timer duration, competition officials, judge password, and QR access for the box.
6. The admin initializes the route, which creates live backend state for that box and sends real-time updates to connected clients.

### Live Judging

1. The judge opens `/judge/:boxId`, authenticates with the box judge account, and connects to the box WebSocket.
2. The judge starts, pauses, resumes, or stops the timer.
3. The judge updates hold progress by whole hold or plus progress.
4. If time tiebreak is enabled, the judge can register the competitor's time.
5. The judge submits the score for the current competitor.
6. The backend marks that competitor as scored, resets per-attempt progress, returns timer state to idle, and advances to the next unmarked competitor.
7. Repeated submissions for already marked competitors are treated as score corrections without disrupting the active climber flow.

### Contest Display

1. A per-box contest display opens at `/contest/:boxId`.
2. It shows category, current route, timer, current competitor, preparing competitor, and hold progress.
3. It stays in sync through authenticated WebSocket snapshots and command echoes.
4. It interpolates timer display locally between authoritative server updates.

### Public Spectator Flow

1. Spectators open `/public`.
2. They can view live rankings across initiated boxes at `/public/rankings`.
3. They can choose a box and view live climbing at `/public/live-climbing/:boxId`.
4. They can view competition officials at `/public/officials`.
5. Public routes are unauthenticated and read-only.

### Ranking And Tiebreaks

1. The backend computes lead rankings from submitted scores and optional times.
2. Route performance compares top status, hold count, then plus progress.
3. Multi-route overall ranking uses per-route rank points and geometric mean aggregation.
4. If tiebreaks are disabled, ties remain shared.
5. If tiebreaks are enabled, previous-rounds tiebreak decisions can be applied to tied groups.
6. Time tiebreak is used only for tied groups that start on the podium.
7. If previous-rounds input partially splits a tied group, unresolved members remain pending until the required input is provided or the tie is intentionally kept.
8. Tiebreak decisions are persisted in box state and shown in rankings/export rows with tiebreak badges.

### Export And Ceremony

1. Admin can save category rankings to disk as XLSX and PDF files.
2. Admin can export a lightweight per-box CSV.
3. Admin can export an official ZIP bundle containing overall and per-route XLSX/PDF files plus metadata.
4. A podium endpoint reads the saved overall Excel ranking and returns the top three competitors for award ceremony display.

### Operations And Recovery

1. The backend runs in JSON storage mode only.
2. Runtime state is kept in memory and persisted to `STORAGE_DIR/boxes/{boxId}.json`.
3. Audit events are appended to `STORAGE_DIR/events.ndjson`.
4. User accounts are stored in `STORAGE_DIR/users.json`.
5. Competition officials are stored in `STORAGE_DIR/competition_officials.json`.
6. Periodic backups write full box snapshots to `BACKUP_DIR`.
7. Admin can trigger an immediate backup, inspect last backup status, download current backup snapshots, and restore up to 50 snapshots per request.
8. Restore validates the full payload before applying state and broadcasts restored box updates.

## Functional Requirements

### Control Panel

- Must show admin security status: USB license, admin license, recovery override, unlock state, and live/polling status.
- Must allow admin unlock and lock.
- Must allow emergency recovery code activation when permitted by backend security rules.
- Must upload one category at a time from `.xlsx`.
- Must require category, route count, and per-route hold counts for upload.
- Must preserve competitor club data when present.
- Must allow category selection for scoring, judge access, setup, export, and public view actions.
- Must allow score modification for already marked competitors.
- Must allow opening award ceremony, judge view, public QR, and public rankings.
- Must allow setting judge passwords per box.
- Must allow setting global competition officials.
- Must provide an audit view with filtering by box id, limit, and optional payload display.

### Upload

- Must accept only `.xlsx` uploads.
- Must read the active sheet.
- Must treat row 1 as headers.
- Must read competitor name from column 1 and club from column 2.
- Must enforce a default max upload size of 5 MiB.
- Must read at most 1000 rows.
- Must accept at most 500 competitors.
- Must reject invalid category, route count, or holds count payloads.
- Must return a listbox object without directly mutating live contest state.

### Judge Remote

- Must require judge or admin access for box mutation commands.
- Must scope judge accounts to assigned box ids.
- Must show current climber, hold count, timer, route max score, and score modal.
- Must support timer start, pause, resume, and stop.
- Must support whole-hold and plus-hold updates.
- Must support hardware-key shortcuts for plus and whole-hold updates.
- Must persist registered time locally enough to survive refresh/reconnect until cleared.
- Must force re-authentication on auth failures.

### Android Judge Shell

- Must load an existing Judge Remote URL in a WebView.
- Must keep the screen awake during judging.
- Must map volume-up to plus-hold progress.
- Must map volume-down to whole-hold progress.
- Must reject public domains and non-HTTP schemes by default, allowing only LAN/private hosts, localhost, `.local`, or configured allowed hosts.

### Live Runtime

- Must serialize state mutations per box.
- Must create box state on first use.
- Must validate session id and box version for mutating commands to prevent stale updates.
- Must rate-limit commands when validation is enabled.
- Must broadcast command echoes and authoritative snapshots over WebSockets.
- Must compute server-side timer remaining by default.
- Must prevent legacy client timer sync from extending a running server-side timer.
- Must publish public updates for box status, flow, and ranking changes.

### Public Views

- Must expose initiated boxes to spectators.
- Must not expose full private competitor state in lightweight public box lists.
- Must provide live rankings through WebSocket with HTTP polling fallback.
- Must provide per-box live climbing through unauthenticated read-only WebSocket.
- Must respond to public WebSocket heartbeat messages.
- Must provide public competition officials.

### Security

- Must block admin password login.
- Must allow non-admin password login for judge/viewer users.
- Must issue JWTs and set them in an httpOnly cookie.
- Must allow trusted-network synthetic admin claims when no JWT is present.
- Must require admin RBAC plus admin unlock for admin actions.
- Must require a valid admin license for admin unlock.
- Must require either a valid USB license or an active recovery override for admin unlock.
- Must auto-lock admin actions when USB/admin license state becomes invalid.
- Must consume recovery codes one time only.
- Must rate-limit recovery attempts.
- Must audit recovery consume outcomes without logging the recovery code itself.
- Must fail startup in production when `JWT_SECRET` is missing or uses the default development value.

### Persistence, Backup, And Audit

- Must use JSON storage only; Postgres/Alembic migrations are no-ops in this build.
- Must atomically write box state and backup files.
- Must skip invalid/corrupt box state files on startup instead of crashing.
- Must start clean by default by clearing persisted box state unless `RESET_BOXES_ON_START=0` is configured.
- Must support periodic backups with configurable interval, retention, and directory.
- Must expose admin-only backup, restore, audit, and ops status endpoints.
- Must rotate audit logs by configured max file size.

## Non-Functional Requirements

- The event runtime must run with a single backend worker.
- The product is intended for controlled LAN operation, not public internet exposure.
- WebSocket clients must receive initial snapshots on connect.
- WebSocket heartbeat must detect dead connections.
- Public ranking pages must remain usable when WebSocket fails by falling back to polling.
- Frontend build output must be servable by the FastAPI backend.
- The system must preserve Romanian names and diacritics in storage, display, and exports.
- Admin security failures must produce explicit error codes that the UI can map to lock/recovery messages.

## Current Routes

### Frontend Routes

- `/` - Control Panel
- `/contest/:boxId` - Contest Display
- `/judge/:boxId` - Judge Remote
- `/rankings` - internal rankings page
- `/admin/audit` - full audit page
- `/public` - public hub
- `/public/rankings` - public live rankings
- `/public/officials` - public competition officials
- `/public/live-climbing/:boxId` - public per-box live climbing

### Backend API Surface

- `POST /api/cmd` - live box commands
- `GET /api/state/{box_id}` - private box snapshot
- `WS /api/ws/{box_id}` - authenticated per-box stream
- `GET /api/public/boxes` - initiated public boxes
- `GET /api/public/officials` - public officials
- `GET /api/public/snapshot` - public snapshot
- `GET /api/public/rankings` - public rankings snapshot
- `WS /api/public/ws` - aggregated public stream
- `WS /api/public/ws/{box_id}` - public per-box stream
- `POST /api/admin/upload` - listbox upload
- `GET/POST /api/admin/competition_officials` - admin officials management
- `POST /api/save_ranking` - save XLSX/PDF rankings
- `GET /api/podium/{category}` - podium data from saved ranking
- `GET /api/admin/backup/box/{box_id}` - per-box backup snapshot
- `GET /api/admin/backup/full` - full backup snapshot
- `GET /api/admin/backup/last` - last backup metadata or download
- `GET /api/admin/export/box/{box_id}` - CSV export
- `GET /api/admin/export/official/box/{box_id}` - official ZIP export
- `POST /api/admin/restore` - restore snapshots
- `GET /api/admin/audit/events` - audit event list
- `GET /api/admin/ops/status` - ops status
- `POST /api/admin/ops/backup/now` - immediate backup
- `GET /api/license/status` - license/security status
- `GET /api/license/events` - license/security SSE
- `POST /api/admin/unlock` - admin unlock
- `POST /api/admin/lock` - admin lock
- `POST /api/admin/recovery/consume` - consume recovery code
- `POST /api/auth/login` - judge/viewer login
- `POST /api/auth/logout` - logout
- `GET /api/auth/me` - current claims
- `POST /api/admin/auth/boxes/{box_id}/password` - set judge password

## Out Of Scope In Current Product

- Public internet deployment without network protections.
- Postgres, Docker runtime storage, or transactional database restore drills.
- Admin username/password login.
- Magic login tokens.
- Multi-worker backend operation.
- Public write actions.
- Direct listbox upload mutation of live state without admin initiation.

## Evidence Sources

- Root and package README files.
- `repos/escalada-core` contest state, command, and lead ranking modules.
- `repos/escalada-api` live, auth, license, backup, audit, public, ranking, and export routers.
- `repos/escalada-ui` route, Control Panel, Judge Remote, Contest Display, Public View, ranking, security, upload, export, and audit components.
- `repos/escalada-judge-android` WebView shell README and project structure.
- Existing backend/core/frontend tests and current API contracts.
