# Remote connector support

AgentHarbor imports the supported remote WorkBuddy ZIP subset without depending
on a separately installed MES MCP Python package. It stores metadata per current
Harbor tenant and user. Package import never runs scripts or local commands.
Only one HTTP(S) Streamable HTTP MCP plus `skills/<name>/SKILL.md` is accepted.
The bundled skill is installed through AgentScope's workspace skill API only
when the user selects the connector in the chat toolbar for an owned session.

## Configuration and ownership

The feature is disabled until these independent settings are supplied by the
operator (see `.env.example`; never commit real values):

- `HARBOR_CONNECTOR_TOKEN_KEY`: a dedicated Fernet encryption key, separate from
  login/session/download keys. Back it up independently of the encrypted SQLite
  data. Wrong/missing keys do not expose plaintext or silently replace grants.
- `HARBOR_CONNECTOR_ALLOWED_ORIGINS`: comma-separated exact HTTP(S) origins allowed
  for MCP, protected-resource metadata and OAuth issuer/endpoints. The connector
  cannot add its own approved origins. All actual TCP destinations are resolved,
  checked for public addresses, and pinned; environment proxies are disabled.
- `HARBOR_CONNECTOR_PUBLIC_URL`: Harbor's public API origin. Register
  `<origin>/harbor/connectors/oauth/callback` with the OAuth provider. HTTPS is
  required except for this loopback development callback.
- `HARBOR_CONNECTOR_BRIDGE_KEYS`: server-only JSON map from exact MCP resource URL
  to the separate trusted human-confirmation bridge key. Only the fixed MES
  `/drafts/{id}/confirm` route adds this header; tools and general proxy calls do
  not receive it. Never put this key in a package, frontend or workspace config.

OAuth uses discovery, public client registration, PKCE S256, a one-use state and
an HttpOnly SameSite=Lax callback cookie. The original Harbor session and active
user/tenant are checked again during callback. This does not weaken Harbor's
normal strict session cookie. Tokens, PKCE verifier and pending session material
are encrypted in `connectors.sqlite3`; list responses, SDK serialization and
workspace declarations contain none of them. Restored connector clients derive
from the server binding registry, not editable `.mcp` declarations. Refresh is
checked per tool invocation, guarded by SQLite leases with owner nonces and CAS.
An ambiguous/cancelled refresh invalidates its local grant instead of replaying a
possibly consumed rotating token.

Disconnect disables local invocation first and attempts remote refresh/access
revocation. A failed remote attempt stays encrypted in a retry queue; the page
reports that state and lets the user retry. Removing a connector requires a
successful revocation attempt. Bundled skill markdown already copied into a
workspace is retained on disconnect/removal; it contains no credentials and
cannot restore access. The user can remove that skill via normal skill controls.



### Desktop browser authorization

The desktop client opens the system browser through a native Tauri command.
The authenticated authorize request uses `external_browser=true` and returns a
one-use, 60-second browser handoff URL. Its ticket is carried in the URL fragment,
removed from browser history, and exchanged in a same-origin POST. The API sets
the callback cookie in the browser before redirecting to the OAuth provider.
The handoff and callback both recheck the original Harbor session and tenant;
no Harbor login token is placed in the browser URL. Return to the client after
authorization to refresh connector status.

Restart the backend and rebuild/restart the native desktop client after this
change; frontend hot reload alone cannot register the new native command.
Browser acceptance with a simulated provider:
`.venv/Scripts/python.exe scripts/smoke_connector_browser.py`
(requires Playwright and Microsoft Edge).

### Independent coding sandboxes

Harbor defaults to `HARBOR_WORKSPACE_MODE=docker`, independently of whether
connector settings are present. Missing Docker or an unavailable image fails
closed; it never falls back to host tools. To run without Docker, explicitly set
`HARBOR_WORKSPACE_MODE=trusted_single_user_local`. Connectors also work in this
mode when their key, allowed origins and public URL are configured. Session
selection, owner checks, encrypted grants and request-time authorization remain
in effect. Local coding tools execute with the backend process's host permissions;
this mode does not provide container isolation. Use Docker for untrusted users.
Changing the mode requires a backend restart and does not migrate Docker snapshots
into local workspace files.

Build with `.venv/Scripts/python.exe scripts/build_sandbox.py` and set
`HARBOR_SANDBOX_IMAGE=harbor-sandbox:dev`. The build context contains only SDK
source and fixed helper scripts, never Harbor `.env`, data or keys. Every
owner/agent/session gets its own container and internal network. Bash, Read,
Write, Edit, Glob, Grep, ordinary MCP servers and memory remain available.
Connector clients stay on the host and inject OAuth into fixed outgoing HTTP
calls; credentials never enter the sandbox, workspace declarations or image.

Workers have no host bind mounts or Docker socket. Their root filesystem is
read-only, `/workspace` is a 256 MiB tmpfs (8192 inodes), and `/tmp` is 32 MiB.
Memory is limited to 1 GiB, CPU to 2, PIDs to 256; Docker logs are capped at 1 MiB.
Execution output is capped while streaming at 1 MiB, file reads at 8 MiB and
writes at 32 MiB. Output overflow or execution timeout terminates the worker;
the next request starts a fresh one from its latest successful snapshot.

Only loopback and a dedicated HTTPS CONNECT proxy are reachable. A short-lived
NET_ADMIN helper installs default-deny firewall rules before code runs; workers
drop all capabilities and cannot change those rules. The proxy resolves and
pins public IPs, rejects private/link-local/reserved destinations, and has no
credentials or host mounts. Public HTTPS pip/npm downloads remain available;
stdio MCP launchers may need proxy variables explicitly passed in their config.

Graceful close streams an archive from inside the worker to an opaque host blob,
with a 272 MiB hard limit and atomic replacement. Restore streams it back and
unpacks only inside the bounded worker with safe path, entry and size checks.
No untrusted archive is unpacked on the host. External symlinks are rejected on
restore; create Python virtual environments with `python -m venv --copies`.
A failed snapshot preserves the previous blob and reports an error. Files since
the last successful close are not guaranteed after a crash or forced termination.

Persistent admission is durable SQLite: defaults are 16 slots globally and 4
per owner (`HARBOR_SANDBOX_MAX_SNAPSHOTS`,
`HARBOR_SANDBOX_MAX_SNAPSHOTS_PER_OWNER`). Closing a workspace retains its slot;
repeated creation cannot bypass disk limits. Each slot holds at most an old and
pending blob, bounding archive storage to 8.5 GiB with defaults. Active limits
remain 8 globally and 4 per owner (`HARBOR_SANDBOX_MAX_ACTIVE`,
`HARBOR_SANDBOX_MAX_PER_OWNER`). Run one Harbor ASGI worker. Operators must
retire old slots explicitly, and clean stale lock/pending files or orphan
containers after a hard crash. Reserve sufficient capacity for snapshots and
other application data before deployment.

Host model formatters reject URLSource attachments in new messages, restored
history, tool results and hints; inline Base64Source images/documents still work.
This prevents host file reads and arbitrary formatter URL fetches. Restart
Harbor when enabling this deployment; do not retain old host-local tool processes.

## UI and API

`/connectors` provides import, authorization, discovered tools,
disconnect and removal. Connected MES connectors link to the order editor at
`/connectors/:connectorId/orders/:draftId?`.

In chat, the connector menu follows the working-directory picker. It lists only
connected connectors and supports multiple selections per tenant/user/agent/session.
Saving prepares newly selected connector skills before replacing the binding set;
failed preparation preserves the old selection. Deselecting disables connector
tools but retains copied skill files. Reading selections does not start a sandbox.
Selections cannot change during a running reply.

All routes below are under `/harbor/connectors` and use the existing Harbor
principal. Client-provided tenant/user headers cannot change connector ownership.

| Route | Purpose |
| --- | --- |
| GET `/` | `{enabled,items}` |
| POST `/import` | ZIP bytes, `application/zip`, at most 5 MiB |
| POST `/{id}/authorize` | starts PKCE, returns authorization URL |
| GET `/oauth/callback` | browser callback; only this route is public and state-bound |
| GET `/{id}/tools` | authenticated MCP tool discovery |
| GET/PUT `/sessions/{agent_id}/{session_id}` | read/replace `{connector_ids: string[]}` for an owned session |
| POST `/{id}/install` | `{agent_id,session_id}` |
| GET `/{id}/installations` | valid owned installed targets |
| POST `/{id}/disconnect` | `{status,remote_revoked}` |
| DELETE `/{id}` | remove package after revocation |
| GET `/{id}/schema` | fixed MCP `/ui/schema` proxy |
| POST/GET/PATCH `/{id}/drafts[/{draft_id}]` | fixed draft API proxy |
| POST `/{id}/drafts/{draft_id}/validate`, `/confirm`, `/cancel`, `/sources` | draft actions |
| GET `/{id}/drafts/{draft_id}/events` | one SSE AG-UI `STATE_SNAPSHOT` event |
| GET `/{id}/operations/{operation_id}` | operation reconciliation |
| GET `/{id}/references` | bounded kind/q/page reference search |
| POST `/{id}/sources` | multipart `file`, at most 20 MiB |
| GET `/{id}/sources/{asset_id}` | source metadata only |
| GET `/drafts/{draft_id}/connection` | resolves draft UI link using current owner's grants |
| POST `/{id}/parse-source` | explicit human action: `{draft_id,asset_id,agent_id?,session_id?}` |

The AG-UI event is `data: {"type":"STATE_SNAPSHOT","snapshot":{"draft":...}}`
followed by a blank line. It uses no stateful/global middleware and does not alter
Harbor's existing chat protocol. REST writes may be followed by another snapshot
subscription.

Source parsing first verifies both remote resources and checks that the asset
is attached to the editable draft. One installed session is selected explicitly
(or automatically only when there is exactly one). The server supplies a fixed
parsing prompt to Harbor's existing chat registry under the owner namespace,
returns the chat URL with `orderDraftId`, and never invokes confirmation/commit.
The model reads the source with `mes_order_source_read` and patches the draft;
the user reviews the result through the chat result's server-resolved editor link.
This user action may use the selected agent's configured model. Tests mock the
scheduler and make no paid calls.

## Verification boundary

Run the server suite with the repository virtualenv and
`PYTHONPATH=apps/server;vendor/agentscope/src` on Windows. Connector tests cover
package restrictions, encrypted persistence/restart, user/tenant isolation,
PKCE state/replay, owner recheck, refresh races, SSRF IP pinning, reserved SDK
exclusion, no secret serialization, private bridge injection, multipart
proxy, AG-UI snapshots, source parsing through a mocked scheduler, and complete
Docker and explicitly trusted local connector integration preserving coding tools and rejecting
reserved MCP shadowing. Formatter tests cover all 22 shipped provider variants;
optional XAI inline tests skip if its SDK is absent.

Frontend TypeScript, focused lint and Node tests pass. A real Chromium browser
run against the full Vite application with intercepted fixture APIs passed blank
draft creation, style/color/size, PO quantities, BOM decimals, save, multipart
upload/attachment, missing-install guidance, validation/review confirmation
gates, edit invalidation and committed-field locking. Evidence is in
`.runtime/order-editor-browser-report.json` and its two screenshots. The fixture
blocked external network and made no paid/model/MES calls. The full Vite production
build reached module transformation but failed in chunk rendering because of
system memory pressure. No real OAuth provider, deployed HTTPS DNS/TLS, browser
popup/cookie flow, deployed MES MCP tool call, paid model parsing or production order
submission has been accepted. These require configured test endpoints and real
user/browser acceptance before deployment.

Real isolated Docker acceptance is opt-in with `HARBOR_RUN_DOCKER_TESTS=1` and
`pytest apps/server/tests/test_sandbox_docker.py -q`. It checks file read/write, read-only root, tmpfs ENOSPC, infinite-output termination,
Python execution, no inherited secret environment/socket, inability to change
firewall rules, denied host/metadata requests, public PyPI installation, an actual
in-container stdio MCP tool call, and preserved files/MCP after container restart.
It uses only fixture data and does not call an LLM or MES.

Final verification: 201 server test cases passed across batches. The single-process run reported 200 passed, one MemoryError in the existing runtime test and five skips; rerunning the runtime file separately passed both tests. The skips are two optional XAI SDK cases and three opt-in Docker cases; all three Docker cases passed when explicitly enabled. On this memory-constrained Windows host, set OPENBLAS_NUM_THREADS=1, OMP_NUM_THREADS=1 and MKL_NUM_THREADS=1 for testing. This does not replace a production build or deployed end-to-end acceptance.

### Local HTTP development

Use MCP `http://localhost:8086` and Harbor `http://localhost:8017`. Set
`HARBOR_CONNECTOR_ALLOWED_ORIGINS=http://localhost:8086` and register
`http://localhost:8017/harbor/connectors/oauth/callback` in MES MCP.
Package import and transport accept HTTP as well as HTTPS. Explicitly allowlisted
localhost, 127.0.0.1 and ::1 targets may resolve to loopback; other hostnames
still require public DNS destinations. OAuth, exact origin checks and DNS pinning
remain enabled. The MCP SDK supports local HTTP issuers on localhost/127.0.0.1.

### Session selection verification (2026-10-10)

29 backend connector/authorization/selection tests and 6 frontend connector tests passed.
TypeScript and the Vite production build passed (bundle-size warning remains).
Run `python scripts/smoke_session_connectors.py` with Playwright/Edge installed
and Vite on port 5187, or pass another Vite base URL as the first argument.
The browser test mounts the real chat component with fixture APIs and verifies
multiselect, session isolation, deselection, failed-save preservation, the running
reply guard and the simplified connector page. It does not call a real provider
or verify an installed desktop package.

## 定时任务的连接器继承

从聊天创建的定时任务，在首次加载执行工作区时，将来源会话所选的连接器保存为任务快照。此后每次新建执行会话都会继承该快照，工作区同时准备 MCP 客户端和 Skill；无需逐次手动勾选。旧任务也通过已有的 `source_session_id` 自动兼容。

继承只发生在存储中标记为定时任务来源的会话，且来源会话、任务与执行会话须属于相同用户及 Agent。普通会话不会继承。已手动设置的执行会话选择（包括清空）予以保留。任务快照独立于来源聊天后续的选择变动；本次未新增任务编辑页的连接器选择控件。从页面创建且没有来源会话的任务不能自动推断连接器。

快照不保存授权令牌。实际使用仍检查当前授权，撤销授权后不得继续调用。首次执行前的来源会话选择决定快照，因此设置任务后应保留所需连接器直至首次执行。

2026-10-12 验证：29 项连接器/运行时测试通过，包含真实调度器连续创建两个不同执行会话并加载 MCP 与 Skill；现有打样巡检执行会话已通过真实邮件 MCP `tools/list` 验证，包含 `email_search`、`email_read`。该验证未执行邮件巡检或发送提醒，定时巡检及提醒的业务结果需以实际运行记录为准。
