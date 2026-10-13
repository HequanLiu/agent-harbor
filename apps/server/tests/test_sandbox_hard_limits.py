import asyncio
from types import SimpleNamespace
import pytest
from harbor.sandbox_backend import BoundedDockerBackend,SandboxOutputLimit
from harbor.sandbox_storage import SandboxSlots,persist_snapshot


def test_exec_stops_reading_and_kills_before_accumulating_unbounded_output():
    class Stream:
        reads=0
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def read_out(self):
            self.reads+=1
            return SimpleNamespace(stream=1,data=b'x'*65536)
    stream=Stream()
    class Execution:
        def start(self):return stream
        async def inspect(self):return {'ExitCode':0}
    class Container:
        killed=0
        async def exec(self,**kwargs):return Execution()
        async def kill(self):self.killed+=1
    container=Container();invalidated=[]
    backend=BoundedDockerBackend(container,'/workspace',lambda:invalidated.append(True))
    with pytest.raises(SandboxOutputLimit):asyncio.run(backend.exec_shell(['fixture']))
    assert stream.reads==17 and container.killed==1 and invalidated==[True]


def test_snapshot_failure_preserves_previous_blob_and_removes_partial(tmp_path):
    target=tmp_path/'workspace.tar';target.write_bytes(b'old-snapshot')
    async def chunks():
        yield b'a'*4
        yield b'b'*5
    with pytest.raises(ValueError,match='hard limit'):
        asyncio.run(persist_snapshot(chunks(),target,limit=8))
    assert target.read_bytes()==b'old-snapshot'
    assert not target.with_suffix('.pending').exists()
    assert not target.with_suffix('.lock').exists()


def test_persistent_slots_bound_owner_and_total_across_restarts(tmp_path):
    slots=SandboxSlots(tmp_path,maximum=2,per_owner=1)
    first=slots.reserve('owner-a','a'*32)
    assert slots.reserve('owner-a','a'*32)==first
    with pytest.raises(RuntimeError):slots.reserve('owner-a','b'*32)
    slots.reserve('owner-b','b'*32)
    restarted=SandboxSlots(tmp_path,maximum=2,per_owner=1)
    with pytest.raises(RuntimeError):restarted.reserve('owner-c','c'*32)
    assert restarted.reserve('owner-a','a'*32)==first
    with pytest.raises(ValueError):restarted.reserve('owner-c','a'*32)


def test_snapshot_lock_rejects_concurrent_writers(tmp_path):
    target=tmp_path/'workspace.tar';target.write_bytes(b'old')
    target.with_suffix('.lock').write_bytes(b'')
    async def chunks():yield b'new'
    with pytest.raises(FileExistsError):asyncio.run(persist_snapshot(chunks(),target))
    assert target.read_bytes()==b'old'
