"""Bound every Docker execution stream before it reaches host memory."""
import asyncio
from agentscope.tool import ExecResult
from agentscope.workspace._docker._docker_backend import DockerBackend

OUTPUT_BYTES=1024*1024
READ_BYTES=8*1024*1024
WRITE_BYTES=32*1024*1024

class SandboxOutputLimit(RuntimeError):
    pass

class BoundedDockerBackend(DockerBackend):
    def __init__(self,container,workdir,on_terminated=None):
        super().__init__(container,workdir)
        self._on_terminated=on_terminated
    async def _terminate(self):
        try:
            await self._container.kill()
        except Exception:
            pass
        finally:
            if self._on_terminated is not None:self._on_terminated()
    async def _limited_exec(self,command,*,cwd=None,timeout=None,limit=OUTPUT_BYTES):
        async def capture():
            execution=await self._container.exec(cmd=command,workdir=cwd or self._workdir)
            stdout,stderr,total=[],[],0
            async with execution.start() as stream:
                while True:
                    message=await stream.read_out()
                    if message is None:break
                    if total+len(message.data)>limit:
                        raise SandboxOutputLimit('Sandbox execution exceeded its output limit; worker terminated')
                    total+=len(message.data)
                    (stdout if message.stream==1 else stderr).append(message.data)
            state=await execution.inspect()
            code=state.get('ExitCode')
            return ExecResult(exit_code=code if code is not None else -1,stdout=b''.join(stdout),stderr=b''.join(stderr))
        try:
            return await asyncio.wait_for(capture(),timeout=min(timeout,300) if timeout is not None else 300)
        except (SandboxOutputLimit,asyncio.TimeoutError,asyncio.CancelledError):
            await self._terminate()
            raise
    async def exec_shell(self,command,*,cwd=None,timeout=None):
        return await self._limited_exec(command,cwd=cwd,timeout=timeout)
    async def read_file(self,path):
        program='import sys; sys.stdout.buffer.write(open(sys.argv[1],"rb").read('+str(READ_BYTES+1)+'))'
        result=await self._limited_exec(['python3','-c',program,path],timeout=30,limit=READ_BYTES)
        if result.exit_code!=0:raise OSError('Cannot read sandbox file')
        return result.stdout
    async def exec_input(self,command,chunks,*,timeout=90):
        async def run():
            execution=await self._container.exec(cmd=command,workdir=self._workdir,stdin=True)
            async with execution.start() as stream:
                async def send():
                    async for chunk in chunks:
                        await stream.write_in(chunk)
                async def receive():
                    total=0;out=[];err=[]
                    while True:
                        message=await stream.read_out()
                        if message is None:break
                        total+=len(message.data)
                        if total>OUTPUT_BYTES:raise SandboxOutputLimit('Sandbox input command output limit')
                        (out if message.stream==1 else err).append(message.data)
                    return out,err
                tasks=[asyncio.create_task(send()),asyncio.create_task(receive())]
                try:_,(out,err)=await asyncio.gather(*tasks)
                finally:
                    for task in tasks:task.cancel()
                    await asyncio.gather(*tasks,return_exceptions=True)
            state=await execution.inspect()
            return ExecResult(exit_code=state.get('ExitCode') if state.get('ExitCode') is not None else -1,stdout=b''.join(out),stderr=b''.join(err))
        try:return await asyncio.wait_for(run(),timeout=timeout)
        except BaseException:
            await self._terminate()
            raise
    async def write_file(self,path,data):
        if len(data)>WRITE_BYTES:raise ValueError('Sandbox file write exceeds 32 MiB')
        program="import os,sys\np=sys.argv[1];n=int(sys.argv[2])\nos.makedirs(os.path.dirname(p) or '.',exist_ok=True)\nwith open(p,'wb') as f:\n while n:\n  b=sys.stdin.buffer.read(min(n,65536))\n  if not b:raise RuntimeError('Truncated input')\n  f.write(b);n-=len(b)"
        async def chunks():
            for offset in range(0,len(data),65536):yield data[offset:offset+65536]
        result=await self.exec_input(['python3','-c',program,path,str(len(data))],chunks())
        if result.exit_code!=0:raise OSError('Cannot write sandbox file')
