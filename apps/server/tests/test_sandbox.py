import asyncio
import pytest


def test_sandbox_identity_cannot_be_selected_by_client():
    from harbor.sandbox import sandbox_id
    assert sandbox_id('tenant_user','agent','session') == sandbox_id('tenant_user','agent','session')
    assert len({sandbox_id(*args) for args in [('t_u','a','s'),('t_v','a','s'),('t_u','b','s'),('t_u','a','q')]}) == 4


def test_worker_configuration_has_no_host_secrets_or_privileged_mounts(tmp_path):
    from harbor.sandbox import worker_config
    config=worker_config('worker-image',str(tmp_path),'private-network','172.20.0.2')
    host=config['HostConfig']
    assert host['CapDrop']==['ALL'] and 'no-new-privileges:true' in host['SecurityOpt']
    assert host['NetworkMode']=='private-network'
    assert not host.get('Binds') and host['ReadonlyRootfs'] is True
    assert 'size=268435456' in host['Tmpfs']['/workspace']
    assert not host.get('Privileged') and not host.get('PortBindings')
    assert all('TOKEN' not in value and 'KEY' not in value for value in config['Env'])
    assert host['PidsLimit']==256 and host['Memory']>0


def test_proxy_rejects_private_and_mixed_dns(monkeypatch):
    from harbor.sandbox_proxy import public_destination
    monkeypatch.setattr('socket.getaddrinfo',lambda *a,**k:[(2,1,6,'',('127.0.0.1',443))])
    with pytest.raises(ValueError): public_destination('host.example',443)
    monkeypatch.setattr('socket.getaddrinfo',lambda *a,**k:[(2,1,6,'',('8.8.8.8',443)),(2,1,6,'',('169.254.169.254',443))])
    with pytest.raises(ValueError): public_destination('host.example',443)
    monkeypatch.setattr('socket.getaddrinfo',lambda *a,**k:[(2,1,6,'',('8.8.8.8',443))])
    assert public_destination('public.example',443)=='8.8.8.8'
    with pytest.raises(ValueError): public_destination('public.example',22)


def test_proxy_denies_public_harbor_service_and_same_ip_alias(monkeypatch):
    from harbor.sandbox_proxy import public_destination
    monkeypatch.setenv('HARBOR_PROXY_DENY_HOSTS','harbor.example')
    monkeypatch.setattr('socket.getaddrinfo',lambda *a,**k:[(2,1,6,'',('8.8.8.8',443))])
    with pytest.raises(ValueError):public_destination('harbor.example',443)
    with pytest.raises(ValueError):public_destination('alias.example',443)


def test_manager_ignores_client_workspace_ids_and_caps_admission(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from harbor.workspaces import TenantWorkspaceManager
    class Worker:
        def __init__(self,**kwargs):self.workspace_id=kwargs['workspace_id'];self.snapshot_path=kwargs['snapshot_path'];self.is_alive=True
        async def initialize(self):pass
        async def close(self):pass
    monkeypatch.setattr('harbor.sandbox.HarborDockerWorkspace',Worker)
    monkeypatch.setenv('HARBOR_SANDBOX_MAX_ACTIVE','2')
    monkeypatch.setenv('HARBOR_SANDBOX_MAX_PER_OWNER','1')
    async def scenario():
        manager=TenantWorkspaceManager(tmp_path)
        owner='a'*32+'_'+'b'*32
        first=await manager.get_workspace(owner,'agent','session','../../forged')
        assert await manager.get_workspace(owner,'agent','session','other') is first
        with pytest.raises(RuntimeError,match='capacity'):
            await manager.get_workspace(owner,'agent','another',first.workspace_id)
        other=await manager.get_workspace('a'*32+'_'+'c'*32,'agent','session',first.workspace_id)
        assert other.workspace_id!=first.workspace_id
        assert other.snapshot_path!=first.snapshot_path
        await manager.close_all()
    asyncio.run(scenario())
