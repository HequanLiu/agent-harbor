"""AgentScope adapter: connector tokens exist only inside one HTTP invocation."""
from contextlib import asynccontextmanager
from types import MethodType
import re
from pathlib import Path
from pydantic import PrivateAttr
from agentscope.mcp import MCPClient, HttpMCPConfig
from agentscope.workspace import LocalWorkspace
from mcp.client.streamable_http import streamable_http_client


PREFIX='harbor_connector_'


class ConnectorMCPClient(MCPClient):
    _oauth=PrivateAttr()
    _network=PrivateAttr()
    _owner=PrivateAttr()
    _tenant=PrivateAttr()
    _connector=PrivateAttr()

    def bind(self,oauth,network,tenant,owner,cid):
        self._oauth,self._network,self._tenant,self._owner,self._connector=oauth,network,tenant,owner,cid
        return self

    def _create_http_client(self):
        return self._connector_transport()

    @asynccontextmanager
    async def _connector_transport(self):
        token=await self._oauth.access(self._tenant,self._owner,self._connector)
        # Use trusted database config, not a workspace file that the model can edit.
        row=self._oauth.store.get(self._tenant,self._owner,self._connector)
        url=self._network.check(row['package']['mcp']['url'])
        async with self._network.client(self.mcp_config.timeout) as client:
            client.headers['Authorization']='Bearer '+token
            async with streamable_http_client(url=url,http_client=client) as transport:
                yield transport


def make_client(oauth,network,tenant,owner,cid):
    package=oauth.store.get(tenant,owner,cid)['package']
    return ConnectorMCPClient(name=PREFIX+cid,is_stateful=False,
        mcp_config=HttpMCPConfig(url=package['mcp']['url'],timeout=package['mcp']['timeout_seconds']),
        disable_tools=package['mcp']['disabled_tools']).bind(oauth,network,tenant,owner,cid)


class ConnectorWorkspaces:
    def __init__(self,store,oauth,network,skill_root,*,allow_trusted_local=False):
        self.store,self.oauth,self.network=store,oauth,network
        self.skill_root=Path(skill_root).resolve()
        self.allow_trusted_local=allow_trusted_local

    def wrap(self,workspace,tenant,owner):
        if getattr(workspace,'_harbor_connector_owner',None)==(tenant,owner): return workspace
        if getattr(workspace,'_harbor_connector_owner',None) is not None: raise ValueError('Connector workspace owner mismatch')
        if not getattr(workspace,'harbor_isolated_workspace',False) and not (
            self.allow_trusted_local and isinstance(workspace,LocalWorkspace)
        ):
            raise ValueError('Connectors require an isolated Docker workspace or explicitly trusted local workspace')
        manager=self
        original_mcps=workspace.list_mcps
        original_add=workspace.add_mcp
        async def list_mcps(this,*,agent_id=None,session_id=None):
            # Never let an editable declaration shadow a server-controlled
            # connector name, in either Docker or trusted local mode.
            async with this._mcp_lock:
                for key,specs in this._mcp_specs.items():
                    this._mcp_specs[key]=[s for s in specs if not s.name.startswith(PREFIX)]
                this.default_mcps=[s for s in this.default_mcps if not s.name.startswith(PREFIX)]
                for clients in this._mcp_instances.values():
                    for name in list(clients):
                        if name.startswith(PREFIX):clients.pop(name)
            clients=await original_mcps(agent_id=agent_id,session_id=session_id)
            allowed=set(manager.store.bindings(tenant,owner,agent_id or '',session_id or ''))
            return [c for c in clients if not c.name.startswith(PREFIX)]+[
                make_client(manager.oauth,manager.network,tenant,owner,cid)
                for cid in sorted(allowed) if manager.store.grant(tenant,owner,cid)]
        async def add_mcp(this,client,**kwargs):
            if client.name.startswith(PREFIX):raise ValueError('Reserved connector name')
            return await original_add(client,**kwargs)
        workspace.add_mcp=MethodType(add_mcp,workspace)
        workspace.list_mcps=MethodType(list_mcps,workspace)
        workspace._harbor_connector_owner=(tenant,owner)
        return workspace

    async def prepare_schedule(self,workspace,storage,tenant,owner,agent,session):
        """Only persisted schedule origins may inherit owner-scoped connectors."""
        from agentscope.app.storage import ScheduleOrigin
        if storage is None: return
        user=f'{tenant}_{owner}'
        record=await storage.get_session(user,agent,session)
        if record is None or not isinstance(record.origin,ScheduleOrigin): return
        schedule=await storage.get_schedule(user,record.origin.schedule_id)
        if schedule is None or schedule.agent_id!=agent: return
        source=schedule.data.source_session_id
        if not source: return
        if await storage.get_session(user,agent,source) is None: return
        ids=self.store.inherit_schedule(tenant,owner,agent,record.origin.schedule_id,source,session)
        for cid in ids:
            # Prepare skills inside this execution's workspace as well as MCPs.
            await self.install(workspace,tenant,owner,cid,agent,session,bind=False)

    async def install(self,workspace,tenant,owner,cid,agent,session,*,bind=True):
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,160}',agent) or not re.fullmatch(r'[A-Za-z0-9_-]{1,160}',session): raise ValueError('Invalid workspace identity')
        # Verifies membership and connection before installing anything.
        await self.oauth.access(tenant,owner,cid)
        row=self.store.get(tenant,owner,cid)
        self.wrap(workspace,tenant,owner)
        # Safe package contains only validated markdown, never scripts or executables.
        import frontmatter
        existing={skill.name:skill for skill in await workspace.list_skills(agent_id=agent)}
        for name,text in row['package']['skills'].items():
            if name in existing:
                document=frontmatter.loads(text)
                if existing[name].markdown!=document.content or existing[name].description!=document['description']:
                    raise ValueError('An existing skill has different content; remove it before installing this connector')
                continue
            target=self.skill_root/tenant/owner/cid/name
            if not target.resolve().is_relative_to(self.skill_root): raise ValueError('Invalid skill destination')
            target.mkdir(parents=True,exist_ok=True)
            (target/'SKILL.md').write_text(text,encoding='utf-8')
            await workspace.add_skill(str(target),agent_id=agent)
        # Bindings, not editable .mcp files, are the source of connector clients.
        # wrap().list_mcps integrates these transient SDK instances into tool discovery.
        if bind: self.store.bind(tenant,owner,cid,agent,session)
