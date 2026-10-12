"""Owner/session isolation defaults to Docker, never silently to host tools."""
import asyncio
import hashlib
import os
from pathlib import Path
import re
from agentscope.app.workspace_manager import LocalWorkspaceManager, WorkspaceManagerBase
from .sandbox_storage import SandboxSlots

class TenantWorkspaceManager(WorkspaceManagerBase):
    def __init__(self,basedir):
        super().__init__()
        mode=os.getenv('HARBOR_WORKSPACE_MODE','docker')
        if mode not in {'docker','trusted_single_user_local'}:
            raise ValueError('Invalid HARBOR_WORKSPACE_MODE')
        self.trusted_local=mode=='trusted_single_user_local'
        self.basedir=Path(basedir)
        self.connectors=None
        self.managers={}
        self.sandboxes={}
        self.sandbox_owners={}
        self.sandbox_lock=asyncio.Lock()
        self.slots=None
        if not self.trusted_local:
            from .formatter_safety import install_formatter_data_only_policy
            install_formatter_data_only_policy()
            self.slots=SandboxSlots(self.basedir/'snapshots',
                maximum=int(os.getenv('HARBOR_SANDBOX_MAX_SNAPSHOTS','16')),
                per_owner=int(os.getenv('HARBOR_SANDBOX_MAX_SNAPSHOTS_PER_OWNER','4')))
    async def assign_workspace_id(self,*,user_id,agent_id,session_id):
        if self.trusted_local:
            return await super().assign_workspace_id(user_id=user_id,agent_id=agent_id,session_id=session_id)
        from .sandbox import sandbox_id
        return sandbox_id(user_id,agent_id,session_id)
    async def get_workspace(self,user_id,agent_id,session_id,workspace_id=None):
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,160}',agent_id):raise ValueError('Invalid agent identifier')
        if self.trusted_local:
            if self.connectors is not None:
                tenant,_,owner=user_id.partition('_')
                if not re.fullmatch(r'[a-f0-9]{32}',tenant) or not re.fullmatch(r'[a-f0-9]{32}',owner):raise ValueError('Invalid workspace owner')
                if not re.fullmatch(r'[A-Za-z0-9_-]{1,160}',session_id):raise ValueError('Invalid session identifier')
            key=hashlib.sha256(user_id.encode()).hexdigest()
            if key not in self.managers:
                manager=LocalWorkspaceManager(str(self.basedir/key),default_mcps=[])
                if self._storage is not None:manager.bind_storage(self._storage)
                self.managers[key]=manager
            workspace=await self.managers[key].get_workspace(user_id,agent_id,session_id,workspace_id)
            if self.connectors is not None:
                await self.connectors.prepare_schedule(workspace,self._storage,tenant,owner,agent_id,session_id)
                return self.connectors.wrap(workspace,tenant,owner)
            return workspace
        from .sandbox import HarborDockerWorkspace,sandbox_id
        tenant,_,owner=user_id.partition('_')
        if not re.fullmatch(r'[a-f0-9]{32}',tenant) or not re.fullmatch(r'[a-f0-9]{32}',owner):raise ValueError('Invalid workspace owner')
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,160}',session_id):raise ValueError('Invalid session identifier')
        identity=sandbox_id(user_id,agent_id,session_id)
        async with self.sandbox_lock:
            current=self.sandboxes.get(identity)
            if current is not None and not current.is_alive:
                await current.close()
                self.sandboxes.pop(identity,None)
                self.sandbox_owners.pop(identity,None)
            if identity not in self.sandboxes:
                if len(self.sandboxes)>=int(os.getenv('HARBOR_SANDBOX_MAX_ACTIVE','8')) or sum(value==user_id for value in self.sandbox_owners.values())>=int(os.getenv('HARBOR_SANDBOX_MAX_PER_OWNER','4')):
                    raise RuntimeError('Sandbox active capacity reached; close an existing workspace')
                snapshot=self.slots.reserve(user_id,identity)
                workspace=HarborDockerWorkspace(workspace_id=identity,snapshot_path=snapshot,image=os.getenv('HARBOR_SANDBOX_IMAGE','harbor-sandbox:dev'),env={},default_mcps=[])
                try:await workspace.initialize()
                except BaseException:
                    await workspace.close()
                    raise
                self.sandboxes[identity]=workspace
                self.sandbox_owners[identity]=user_id
            workspace=self.sandboxes[identity]
            if self.connectors is not None:
                await self.connectors.prepare_schedule(workspace,self._storage,tenant,owner,agent_id,session_id)
                return self.connectors.wrap(workspace,tenant,owner)
            return workspace
    async def close(self,workspace_id):
        workspace=self.sandboxes.get(workspace_id)
        if workspace is not None:
            await workspace.close()
            self.sandboxes.pop(workspace_id,None)
            self.sandbox_owners.pop(workspace_id,None)
        await asyncio.gather(*(manager.close(workspace_id) for manager in self.managers.values()))
    async def close_all(self):
        results=await asyncio.gather(*(self.close(identity) for identity in list(self.sandboxes)),return_exceptions=True)
        await asyncio.gather(*(manager.close_all() for manager in self.managers.values()))
        self.managers.clear()
        failure=next((result for result in results if isinstance(result,BaseException)),None)
        if failure is not None:raise failure
