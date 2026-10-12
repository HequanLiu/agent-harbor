"""Bounded opaque snapshots; never unpack untrusted archives on the host."""
import hashlib
import os
from pathlib import Path
import re
import sqlite3
import time

WORKSPACE_BYTES = 256 * 1024 * 1024
SNAPSHOT_BYTES = 272 * 1024 * 1024

class SandboxSlots:
    def __init__(self, root, *, maximum=16, per_owner=4):
        if not 1 <= per_owner <= maximum <= 64:
            raise ValueError('Invalid persistent sandbox quota')
        self.root=Path(root).resolve()
        self.root.mkdir(parents=True,exist_ok=True)
        self.maximum,self.per_owner=maximum,per_owner
        self.database=self.root/'slots.sqlite3'
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS slots (id TEXT PRIMARY KEY, owner TEXT NOT NULL, created REAL NOT NULL)')
    def connect(self):
        return sqlite3.connect(self.database,timeout=30)
    def reserve(self,owner,identity):
        if not re.fullmatch(r'[a-f0-9]{32}',identity):
            raise ValueError('Invalid server sandbox identity')
        owner_hash=hashlib.sha256(owner.encode()).hexdigest()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            existing=db.execute('SELECT owner FROM slots WHERE id=?',(identity,)).fetchone()
            if existing:
                if existing[0]!=owner_hash:raise ValueError('Sandbox owner mismatch')
            else:
                count=db.execute('SELECT count(*) FROM slots').fetchone()[0]
                own=db.execute('SELECT count(*) FROM slots WHERE owner=?',(owner_hash,)).fetchone()[0]
                if count>=self.maximum or own>=self.per_owner:
                    raise RuntimeError('Persistent sandbox quota reached; operator must retire an old workspace before creating another')
                db.execute('INSERT INTO slots VALUES(?,?,?)',(identity,owner_hash,time.time()))
        folder=self.root/owner_hash/identity
        folder.mkdir(parents=True,exist_ok=True)
        return folder/'workspace.tar'

async def persist_snapshot(chunks,target,*,limit=SNAPSHOT_BYTES):
    target=Path(target)
    target.parent.mkdir(parents=True,exist_ok=True)
    lock=target.with_suffix('.lock')
    pending=target.with_suffix('.pending')
    fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    os.close(fd)
    total=0
    try:
        with pending.open('wb') as stream:
            async for chunk in chunks:
                if total+len(chunk)>limit:
                    raise ValueError('Sandbox snapshot exceeds hard limit')
                stream.write(chunk)
                total+=len(chunk)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(pending,target)
        return total
    finally:
        pending.unlink(missing_ok=True)
        lock.unlink(missing_ok=True)

def checked_snapshot(target,*,limit=SNAPSHOT_BYTES):
    path=Path(target)
    if not path.exists():return None
    if not path.is_file() or path.stat().st_size>limit:
        raise ValueError('Invalid or oversized sandbox snapshot')
    return path
