# AgentHarbor Tauri desktop

Scope: package the existing frontend with Tauri 2, retaining the independently deployed Python backend and browser entry.

1. Test URL validation and hash route behavior; allow HTTPS remote APIs and HTTP loopback.
2. Introduce native HTTP transport with shared cookies, streamed responses and multipart uploads.
3. Configure native window, restricted capabilities, CSP, native document save dialogs, server selection and hash routes.
4. Build the Windows executable and NSIS installer. Verify native WebView login, tenant isolation, navigation and streaming against isolated local test data.

Session cookies remain in the native process cookie jar; restarting the application requires login. Only the server URL is stored in WebView localStorage. This release does not bundle Python, auto-start servers, or include an updater.
