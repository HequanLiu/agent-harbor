# Upstream provenance

- Source: https://github.com/agentscope-ai/agentscope
- Local checkout supplied by user: `D:\GithubProject\agentscope`
- Source HEAD: `72f3f6fa0b2fc38b8517f408ab616f0f2bd229e6`
- Snapshot date: 2026-10-08
- Runtime version: `2.0.10.dev0`
- License: Apache-2.0, preserved at LICENSE and vendor/agentscope/LICENSE.

The source checkout had local modifications to `examples/agent_service/main.py`, `examples/web_ui/backend/src/index.ts`, `examples/web_ui/frontend/vite.config.ts`, and `pyproject.toml`. The runtime src/ and current pyproject.toml are included as a source snapshot. No `.env`, credentials, virtual environments, runtime workspaces or source Git metadata were copied.

Frontend source is adapted from examples/web_ui/frontend. AgentHarbor changes include its login page, workspace membership UI, branding, same-origin API routing and cookie authentication. The original example's Node health-check server is omitted; FastAPI handles the actual application API. The Python composition adopts SQL persistence and owner-scoped local workspace managers instead of the example's Redis/global local manager. Vendored runtime files are kept unmodified.

Upgrades: replace the reviewed vendor snapshot, preserve LICENSE, update this provenance file and dependency lock, and rerun identity/runtime/streaming/frontend checks. This snapshot strategy is intentional for a standalone development project; it is not an automatic upstream updater.
