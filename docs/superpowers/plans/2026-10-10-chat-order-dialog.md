# Chat order dialog implementation plan

**Goal:** Render MES drafts as chat cards that open the existing editor in a modal without navigating away.

**Architecture:** Keep the route page as a thin wrapper around a shared OrderEditorSession. Pass draft identity and saved-state callbacks explicitly. Cards use validated MCP draft snapshots for initial summaries and update from accepted editor snapshots. Modal close requests preserve unsaved input unless the user chooses to discard it; in-flight writes block closing.

**Tech stack:** React, TypeScript, Radix Dialog, existing connector APIs.

- [x] Extract validated draft snapshot parsing and test structured/plain tool responses and invalid data.
- [x] Decouple OrderEditorSession from route parameters; expose draft and dirty/busy changes while preserving save/validate/confirm APIs.
- [x] Replace MesDraftLink navigation with a summary card and responsive modal; protect closing, restore focus, refresh saved summaries.
- [x] Run existing frontend tests and production build. Browser inventory returned no available browsers; real MES and responsive visual acceptance remain unverified.

Acceptance: clicking a card keeps the chat URL unchanged; existing drafts load without creating a new one; save updates the card; validation precedes explicit confirmation; dismissing with edits offers continue/discard; desktop dialog and narrow-screen panel scroll independently of chat.
