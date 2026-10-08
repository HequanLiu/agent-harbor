"""Owner-scoped local workspace managers for the single-host edition."""
import asyncio
import hashlib
from pathlib import Path
import re

from agentscope.app.workspace_manager import LocalWorkspaceManager, WorkspaceManagerBase


class TenantWorkspaceManager(WorkspaceManagerBase):
    def __init__(self, basedir):
        super().__init__()
        self.basedir = Path(basedir)
        self.managers = {}

    async def get_workspace(self, user_id, agent_id, session_id, workspace_id=None):
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,160}', agent_id):
            raise ValueError('Invalid agent identifier')
        key = hashlib.sha256(user_id.encode()).hexdigest()
        if key not in self.managers:
            manager = LocalWorkspaceManager(str(self.basedir / key), default_mcps=[])
            if self._storage is not None:
                manager.bind_storage(self._storage)
            self.managers[key] = manager
        return await self.managers[key].get_workspace(user_id, agent_id, session_id, workspace_id)

    async def close(self, workspace_id):
        await asyncio.gather(*(m.close(workspace_id) for m in self.managers.values()))

    async def close_all(self):
        await asyncio.gather(*(m.close_all() for m in self.managers.values()))
        self.managers.clear()
