# AgentHarbor Implementation Plan

Goal: ship the approved local full-stack multi-tenant foundation at D:/my-project/agent-harbor.
Architecture: apps/web uses a same-origin /api proxy to apps/server. An ASGI authentication boundary replaces untrusted identity headers before dispatch to the embedded AgentScope application. SQLite persists identities and runtime state separately.
Tech stack: React, TypeScript, Vite, FastAPI, SQLite, AgentScope, Qdrant.

- [x] Copy frontend and vendor runtime, record source revision and changed source files.
- [x] apps/server/tests/test_auth.py: test registration, password rejection, owner-only member changes, logout revocation, forged user header and cross-tenant access. Run pytest and observe missing implementation.
- [x] apps/server/harbor/identity.py: SQLite accounts/memberships/sessions, scrypt password verification, hash session tokens, enforce expiry, transactional registration, owner-only member administration.
- [x] apps/server/harbor/auth.py: identity API and pure ASGI boundary, validate origins for cookie mutations, validate tenant membership and replace X-User-ID. Preserve streaming and upload bodies.
- [x] apps/server/harbor/app.py: compose upstream SQL storage, persistent vector store, independent workspaces, health endpoint and auth routes; expose one localhost service.
- [x] apps/web/src/pages/setup/index.tsx: login/registration. apps/web/src/pages/tenants/index.tsx: create/switch tenants and member administration. Update client URL resolution, XHR uploads and credentials; clear query cache on identity changes.
- [x] scripts/setup.ps1 and dev.ps1: reproducible installation and hidden child processes with cleanup; .env.example and README document runtime scope and verification.
- [x] Run pytest, frontend build, HTTP checks, persistence restart checks and streaming fixture checks; install to requested directory and rerun target health/build checks.
