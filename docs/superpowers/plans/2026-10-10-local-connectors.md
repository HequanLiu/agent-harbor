# Local workspace connectors implementation plan

Goal: Support connectors in explicitly selected trusted_single_user_local mode.
Architecture: Pass explicit local permission from application composition into ConnectorWorkspaces; accept real SDK LocalWorkspace instances only. Wrap local workspaces with the existing owner and session scoped connector loader. Preserve Docker behavior and credential transport.

- [x] Add real application regression coverage: startup, local workspace resolution, skill installation, session selection and deselection, reserved names and owner isolation.
- [x] Run the regression before changes and confirm the existing Docker-only rejection.
- [x] Remove the application rejection; explicitly authorize real local workspaces in the adapter; wrap local workspaces after resolving tenant/owner.
- [x] Run connector, runtime and sandbox regression suites; inspect diff.
- [x] Update connector documentation and restore configured origins from installed connector metadata, keeping credentials unchanged.

Validation: .venv/Scripts/python.exe -m pytest -c apps/server/pytest.ini apps/server/tests/test_local_connectors.py apps/server/tests/test_connectors.py apps/server/tests/test_connector_selection.py apps/server/tests/test_runtime.py apps/server/tests/test_sandbox.py

Results: 189 passed, 2 optional cases skipped in the regression suite. The extended real local workspace test also passed with a loopback HTTP MCP server, verifying initialize, authorized tools/call and returned text. git diff --check passed. The running backend was not restarted; live MES business operations were not exercised.
