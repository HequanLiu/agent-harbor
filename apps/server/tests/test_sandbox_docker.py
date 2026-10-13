import asyncio
import os
import uuid
from pathlib import Path
import pytest

pytestmark=pytest.mark.skipif(os.getenv('HARBOR_RUN_DOCKER_TESTS')!='1',reason='Opt-in isolated Docker acceptance; no model or MES calls')


def test_isolated_worker_coding_network_mcp_and_restart(tmp_path,monkeypatch):
    from harbor.sandbox import HarborDockerWorkspace
    from agentscope.mcp import MCPClient,StdioMCPConfig
    identity='acceptance'+uuid.uuid4().hex[:22]
    workspace_dir=tmp_path/'workspace';workspace_dir.mkdir()
    secret_file=tmp_path/'host-only-sentinel.txt';secret_file.write_text('harbor-host-sentinel')
    monkeypatch.setenv('HARBOR_CONNECTOR_TOKEN_KEY','host-key-sentinel')
    monkeypatch.setenv('HARBOR_CONNECTOR_BRIDGE_KEYS','host-bridge-sentinel')
    async def scenario():
        workspace=HarborDockerWorkspace(workspace_id=identity,host_workdir=str(workspace_dir),image='harbor-sandbox:dev')
        try:
            await workspace.initialize()
            from test_connectors import oauth_fixture
            from harbor.connectors.workspace import ConnectorWorkspaces,PREFIX
            store,cid,net,identity_store,oauth=oauth_fixture(tmp_path/'grants')
            state,_=await oauth.start('tenant_a','alice',cid,'harbor-session')
            await oauth.callback_exchange(state,'fixture-code',state)
            adapter=ConnectorWorkspaces(store,oauth,net,tmp_path/'connector-skills')
            await adapter.install(workspace,'tenant_a','alice',cid,'agent','session')
            await adapter.install(workspace,'tenant_a','alice',cid,'agent','session')
            assert 'test-skill' in [skill.name for skill in await workspace.list_skills(agent_id='agent')]
            backend=workspace.get_backend()
            await backend.write_file('/workspace/hello.txt',b'coding works')
            assert await backend.read_file('/workspace/hello.txt')==b'coding works'
            result=await backend.exec_shell(['python3','-c',"import os,pathlib; assert not any(k.startswith('HARBOR_') for k in os.environ); assert not pathlib.Path('/var/run/docker.sock').exists(); assert not pathlib.Path('/host-only-sentinel.txt').exists(); print('safe-env')"],timeout=10)
            assert result.exit_code==0 and b'safe-env' in result.stdout
            tools=await workspace.list_tools()
            assert {'Bash','Read','Write'} <= {tool.name for tool in tools}
            # Cannot change firewall even as root; Docker exec has no NET_ADMIN.
            result=await backend.exec_shell(['iptables','-P','OUTPUT','ACCEPT'],timeout=5)
            assert result.exit_code!=0
            for address in ['http://host.docker.internal:8017/harbor/health','http://169.254.169.254/latest/meta-data','http://172.17.0.1:8017/harbor/health']:
                result=await backend.exec_shell(['curl','--noproxy','*','--connect-timeout','2','--max-time','3',address],timeout=5)
                assert result.exit_code!=0
            result=await backend.exec_shell(['curl','--connect-timeout','5','--max-time','10','https://127.0.0.1/'],timeout=12)
            assert result.exit_code!=0
            result=await backend.exec_shell(['python3','-m','pip','install','--disable-pip-version-check','--index-url','https://pypi.org/simple','--target','/workspace/deps','colorama==0.4.6'],timeout=60)
            assert result.exit_code==0,result.stderr
            script=b'from mcp.server.fastmcp import FastMCP\nm=FastMCP("sandbox-fixture")\n@m.tool()\ndef add(a:int,b:int)->int:return a+b\nm.run()\n'
            await backend.write_file('/workspace/mock_mcp.py',script)
            client=MCPClient(name='sandbox-fixture',is_stateful=True,mcp_config=StdioMCPConfig(command='python3',args=['/workspace/mock_mcp.py']))
            await workspace.add_mcp(client,agent_id='agent',session_id='session')
            clients=await workspace.list_mcps(agent_id='agent',session_id='session')
            tool=await clients[0].get_tool('add')
            chunk=await tool(a=2,b=3)
            assert '5' in str(chunk)
            await workspace.close()
            workspace=HarborDockerWorkspace(workspace_id=identity,host_workdir=str(workspace_dir),image='harbor-sandbox:dev')
            await workspace.initialize()
            adapter.wrap(workspace,'tenant_a','alice')
            assert await workspace.get_backend().read_file('/workspace/hello.txt')==b'coding works'
            assert PREFIX+cid in [client.name for client in await workspace.list_mcps(agent_id='agent',session_id='session')]
            persisted=await workspace.get_backend().read_file('/workspace/.mcp')
            assert b'access_token' not in persisted and PREFIX.encode() not in persisted
            clients=await workspace.list_mcps(agent_id='agent',session_id='session')
            chunk=await (await clients[0].get_tool('add'))(a=4,b=5)
            assert '9' in str(chunk)
        finally:await workspace.close()
    asyncio.run(scenario())



def test_sandbox_denies_live_host_and_peer_resources(tmp_path):
    import threading
    from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
    from harbor.sandbox import HarborDockerWorkspace
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200);self.end_headers();self.wfile.write(b'host-private-fixture')
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('0.0.0.0',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    async def scenario():
        from urllib.request import urlopen
        assert await asyncio.to_thread(lambda:urlopen('http://127.0.0.1:'+str(server.server_port)).read())==b'host-private-fixture'
        instances=[]
        try:
            for name in ('alice','bob'):
                root=tmp_path/name;root.mkdir()
                workspace=HarborDockerWorkspace(workspace_id='peer'+uuid.uuid4().hex[:28],host_workdir=str(root),image='harbor-sandbox:dev')
                instances.append(workspace);await workspace.initialize()
            first,second=instances
            await second.get_backend().write_file('/workspace/peer-only.txt',b'peer-private-fixture')
            assert not await first.get_backend().file_exists('/workspace/peer-only.txt')
            await second.get_backend().exec_shell(['sh','-c','python3 -m http.server 8133 --bind 0.0.0.0 >/tmp/peer-server.log 2>&1 &'],timeout=5)
            info=await second._container.show()
            peer_ip=next(iter(info['NetworkSettings']['Networks'].values()))['IPAddress']
            for address in ['http://host.docker.internal:'+str(server.server_port),'http://'+peer_ip+':8133/peer-only.txt']:
                result=await first.get_backend().exec_shell(['curl','--noproxy','*','--connect-timeout','2','--max-time','3',address],timeout=5)
                assert result.exit_code!=0
                assert b'private-fixture' not in result.stdout
        finally:
            for workspace in instances:await workspace.close()
    try:asyncio.run(scenario())
    finally:server.shutdown();server.server_close();thread.join(timeout=2)


def test_bounded_disk_readonly_root_and_infinite_output_termination(tmp_path):
    from harbor.sandbox import HarborDockerWorkspace
    from harbor.sandbox_backend import SandboxOutputLimit
    async def scenario():
        workspace=HarborDockerWorkspace(workspace_id='bounds'+uuid.uuid4().hex[:26],host_workdir=str(tmp_path),image='harbor-sandbox:dev')
        try:
            await workspace.initialize()
            backend=workspace.get_backend()
            info=await workspace._container.show()
            assert not any(mount['Type']=='bind' for mount in info['Mounts'])
            assert info['HostConfig']['ReadonlyRootfs']
            result=await backend.exec_shell(['sh','-c','echo no > /etc/harbor-test'],timeout=5)
            assert result.exit_code!=0
            result=await backend.exec_shell(['dd','if=/dev/zero','of=/workspace/fill','bs=1M','count=300'],timeout=30)
            assert result.exit_code!=0 and b'No space left' in result.stderr
            await backend.exec_shell(['rm','/workspace/fill'],timeout=5)
            with pytest.raises(SandboxOutputLimit):
                await backend.exec_shell(['python3','-c',"import os\nwhile True: os.write(1,b'x'*65536)"],timeout=10)
            assert not workspace.is_alive
            state=await workspace._container.show()
            assert not state['State']['Running']
        finally:await workspace.close()
    asyncio.run(scenario())
