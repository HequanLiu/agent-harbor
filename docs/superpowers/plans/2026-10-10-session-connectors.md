# Session Connector Selection Implementation Plan

> **For agentic workers:** Use executing-plans to implement this plan task-by-task.

**Goal:** Move the connector menu above MCP Center, simplify connector management, and allow each chat session to select multiple connected connectors next to its working directory.

**Architecture:** Keep connector authorization at owner scope. Persist selection in the existing owner/agent/session binding table. Read selection without opening a workspace; prepare bundled skills on newly selected connectors, then atomically replace bindings. Deselection removes tool access but preserves existing workspace files. Serialize changes with the chat session lock.

**Tech Stack:** React, TanStack Query, Radix dropdown, FastAPI, SQLite.

- [x] Add regression tests for session ownership, multiple selections, deselection, disconnected connectors, failure atomicity, and workspace tool filtering.
- [x] Extend store, workspace installer and connector API with session selection.
- [x] Move sidebar entry; remove WorkBuddy copy and installation target UI.
- [x] Add a multi-select chat control with loading/error/empty/saving states and prevent sending during saves.
- [x] Run backend tests, frontend type checks/build and browser interaction verification.

Validation: 29 backend tests and 6 frontend connector tests passed. TypeScript and production build passed. Edge exercised the actual ChatContent with fixture APIs: multiselect, session isolation, deselection, failed-save preservation, running guard, and simplified management page. Real provider tool invocation and packaged desktop acceptance were not exercised.
