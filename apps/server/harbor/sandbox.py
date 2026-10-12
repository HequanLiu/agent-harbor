"""Hardened SDK worker with bounded RAM filesystems and opaque snapshots."""
import asyncio
import hashlib
import os
from pathlib import Path
from urllib.parse import urlsplit
from agentscope.workspace import DockerWorkspace
from .sandbox_backend import BoundedDockerBackend
from .sandbox_storage import checked_snapshot,persist_snapshot

LOG_CONFIG={'Type':'json-file','Config':{'max-size':'1m','max-file':'1'}}

def sandbox_id(owner,agent,session):
    return hashlib.sha256(('harbor-sandbox-v1\0'+owner+'\0'+agent+'\0'+session).encode()).hexdigest()[:32]

def worker_config(image,workdir,network,proxy_ip):
    del workdir
    proxy='http://'+proxy_ip+':3128'
    return {'Image':image,'Cmd':['sleep','infinity'],'WorkingDir':'/workspace',
        'Env':['HTTP_PROXY='+proxy,'HTTPS_PROXY='+proxy,'http_proxy='+proxy,'https_proxy='+proxy,
            'NO_PROXY=127.0.0.1,localhost','no_proxy=127.0.0.1,localhost',
            'HOME=/workspace/.home','XDG_CACHE_HOME=/workspace/.cache','NPM_CONFIG_CACHE=/workspace/.npm'],
        'Labels':{'harbor.sandbox':'worker'},
        'HostConfig':{'NetworkMode':network,'ReadonlyRootfs':True,
            'Tmpfs':{'/workspace':'rw,nosuid,nodev,size=268435456,nr_inodes=8192',
                '/tmp':'rw,nosuid,nodev,size=33554432,nr_inodes=4096'},
            'CapDrop':['ALL'],'SecurityOpt':['no-new-privileges:true'],'PidsLimit':256,
            'Memory':1024*1024*1024,'NanoCpus':2_000_000_000,'Init':True,'LogConfig':LOG_CONFIG}}

class HarborDockerWorkspace(DockerWorkspace):
    harbor_isolated_workspace=True
    def __init__(self,*,image,snapshot_path=None,host_workdir=None,**kwargs):
        if snapshot_path is None:
            if host_workdir is None:raise ValueError('A server-owned snapshot path is required')
            snapshot_path=Path(host_workdir)/'workspace.tar'
        super().__init__(host_workdir=None,**kwargs)
        self.snapshot_path=Path(snapshot_path).resolve()
        self._harbor_image=image
        self._proxy=None
        self._network=None
        self._terminated=False
        self._snapshot_lock=asyncio.Lock()
    @property
    def is_persistent(self):return True
    @property
    def _gateway_log(self):return '/tmp/harbor-gateway.log'
    def _execution_terminated(self):
        self._terminated=True
        self.is_alive=False
    async def _build_or_reuse_image(self):
        await self._client.images.inspect(self._harbor_image)
        self._image_tag=self._harbor_image
    async def _restore_snapshot(self):
        snapshot=checked_snapshot(self.snapshot_path)
        if snapshot is None:return
        program="""import sys,tarfile
class Exact:
 def __init__(self,n):self.left=n
 def read(self,n=-1):
  if not self.left or n==0:return b''
  n=min(self.left,65536 if n<0 else n)
  data=sys.stdin.buffer.read(n)
  if not data:raise RuntimeError('Truncated snapshot')
  self.left-=len(data);return data
reader=Exact(int(sys.argv[1]));count=expanded=0
if not hasattr(tarfile,'data_filter'):raise RuntimeError('Safe archive filter unavailable')
with tarfile.open(fileobj=reader,mode='r|') as archive:
 for member in archive:
  count+=1
  if count>8192 or member.size<0:raise RuntimeError('Snapshot entry limit')
  if member.isfile():expanded+=member.size
  if expanded>268435456:raise RuntimeError('Snapshot expanded limit')
  archive.extract(member,path='/workspace',filter='data')
while reader.left:reader.read(min(65536,reader.left))
"""
        async def chunks():
            with snapshot.open('rb') as body:
                while chunk:=body.read(65536):yield chunk
        result=await self._backend.exec_input(['python3','-c',program,str(snapshot.stat().st_size)],chunks())
        if result.exit_code!=0:raise RuntimeError('Cannot restore sandbox snapshot')
    async def _save_snapshot(self):
        async with self._snapshot_lock:
            # Docker archive API does not reliably include tmpfs mounts. Stream
            # tar from inside the worker, never unpacking it on the host.
            execution=await self._container.exec(cmd=['tar','-C','/workspace','-cf','-','.'],workdir='/workspace')
            async with execution.start() as stream:
                async def chunks():
                    errors=0
                    while True:
                        message=await stream.read_out()
                        if message is None:break
                        if message.stream==1:yield message.data
                        else:
                            errors+=len(message.data)
                            if errors>65536:raise RuntimeError('Snapshot error output limit')
                    state=await execution.inspect()
                    if state.get('ExitCode')!=0:raise RuntimeError('Workspace changed or could not be snapshotted; previous snapshot preserved')
                await persist_snapshot(chunks(),self.snapshot_path)
    async def close(self):
        if self._container is not None and self.is_alive and not self._terminated:
            await asyncio.wait_for(self._save_snapshot(),timeout=90)
        await super().close()
    async def _create_and_start_container(self):
        name='hb_net_'+self.workspace_id
        try:self._network=await self._client.networks.get(name)
        except Exception:
            self._network=await self._client.networks.create({'Name':name,'Internal':True,'CheckDuplicate':True,'Labels':{'harbor.sandbox':'network'}})
        info=await self._network.show()
        if not info.get('Internal'):raise RuntimeError('Sandbox network must be internal')
        self._proxy=await self._client.containers.create_or_replace(name='hb_proxy_'+self.workspace_id,config={
            'Image':self._image_tag,'Cmd':['python3','/opt/harbor/sandbox_proxy.py'],
            'Labels':{'harbor.sandbox':'proxy'},
            'Env':['HARBOR_PROXY_DENY_HOSTS='+(urlsplit(os.getenv('HARBOR_CONNECTOR_PUBLIC_URL','')).hostname or '')],
            'HostConfig':{'NetworkMode':'bridge','CapDrop':['ALL'],'SecurityOpt':['no-new-privileges:true'],
                'ReadonlyRootfs':True,'PidsLimit':64,'Memory':128*1024*1024,'LogConfig':LOG_CONFIG}})
        await self._network.connect({'Container':self._proxy.id})
        await self._proxy.start()
        proxy_info=await self._proxy.show()
        proxy_ip=proxy_info['NetworkSettings']['Networks'][name]['IPAddress']
        config=worker_config(self._image_tag,None,name,proxy_ip)
        self._container=await self._client.containers.create_or_replace(name='hb_worker_'+self.workspace_id,config=config)
        await self._container.start()
        rules='set -eu; iptables -P OUTPUT DROP; iptables -P INPUT DROP; iptables -A OUTPUT -o lo -j ACCEPT; iptables -A INPUT -i lo -j ACCEPT; iptables -A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT; iptables -A OUTPUT -d '+proxy_ip+' -p tcp --dport 3128 -j ACCEPT; ip6tables -P OUTPUT DROP; ip6tables -P INPUT DROP'
        helper=await self._client.containers.create_or_replace(name='hb_firewall_'+self.workspace_id,config={
            'Image':self._image_tag,'Cmd':['sh','-c',rules],
            'HostConfig':{'NetworkMode':'container:'+self._container.id,'CapDrop':['ALL'],'CapAdd':['NET_ADMIN'],
                'SecurityOpt':['no-new-privileges:true'],'ReadonlyRootfs':True,'Memory':64*1024*1024,
                'PidsLimit':32,'LogConfig':LOG_CONFIG}})
        try:
            await helper.start()
            result=await helper.wait()
            if result.get('StatusCode')!=0:raise RuntimeError('Sandbox firewall initialization failed')
        finally:await helper.delete(force=True)
        self._backend=BoundedDockerBackend(self._container,'/workspace',self._execution_terminated)
        await self._restore_snapshot()
        result=await self._backend.exec_shell(['mkdir','-p','/workspace/.home','/workspace/.cache','/workspace/.npm'],timeout=10)
        if result.exit_code!=0:raise RuntimeError('Cannot initialize bounded workspace')
    async def _teardown_backend(self):
        if self._proxy is not None:
            try:await self._proxy.delete(force=True)
            except Exception:pass
            self._proxy=None
        network=self._network
        self._network=None
        if self._container is not None:
            try:await self._container.delete(force=True)
            except Exception:pass
            self._container=None
        if network is not None:
            try:await network.delete()
            except Exception:pass
        await super()._teardown_backend()
