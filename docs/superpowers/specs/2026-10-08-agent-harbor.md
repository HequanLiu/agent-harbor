# AgentHarbor approved scope

Independent React/TypeScript frontend and FastAPI backend based on the supplied AgentScope examples. Preserve upstream licensing and an embedded source snapshot so installation does not depend on the original checkout.

Accounts have password-based authentication with revocable server sessions in HttpOnly cookies. A user can create tenants and tenant owners can add/remove existing accounts as members. Membership is verified on every request. AgentScope owner namespaces are derived server-side from tenant and user UUIDs, so members have private Agents, conversations, credentials and files inside each tenant. Shared resources and billing are future work.

Use SQLite for identity and AgentScope persistence, local persistent Qdrant for knowledge bases, and one Python process with an in-memory event bus. Keep the upstream management UI and add login and workspace management. Local workspaces are not an OS security sandbox; deployment for mutually untrusted tenants requires a sandbox workspace provider.

Acceptance: authentication and membership tests; forged identity/cross-tenant resource checks; frontend build; live HTTP health, authenticated Agent/session creation, persistence and local streaming fixture. A real model call requires user-configured credentials and is reported separately.
