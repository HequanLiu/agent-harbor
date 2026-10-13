"""SQLite metadata and authenticated encryption for OAuth grants.

The encryption key is an independently configured secret, never saved here.
Every record is selected by tenant AND user, including pending authorization.
"""
from contextlib import contextmanager
import json
from pathlib import Path
import secrets
import sqlite3
import time
import uuid
from cryptography.fernet import Fernet


class ConnectorStore:
    def __init__(self, path, key):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.cipher = Fernet(key.encode() if isinstance(key,str) else key)
        with self.db() as db:
            db.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS connectors (
              tenant TEXT NOT NULL, owner TEXT NOT NULL, id TEXT NOT NULL,
              source TEXT NOT NULL, package TEXT NOT NULL, tools TEXT NOT NULL DEFAULT '[]', epoch INTEGER NOT NULL DEFAULT 0,
              PRIMARY KEY(tenant,owner,id), UNIQUE(tenant,owner,source));
            CREATE TABLE IF NOT EXISTS connector_grants (
              tenant TEXT NOT NULL, owner TEXT NOT NULL, connector TEXT NOT NULL,
              encrypted BLOB NOT NULL, generation TEXT NOT NULL, lease REAL NOT NULL DEFAULT 0, lease_owner TEXT,
              PRIMARY KEY(tenant,owner,connector));
            CREATE TABLE IF NOT EXISTS connector_revocations (
              tenant TEXT NOT NULL, owner TEXT NOT NULL, connector TEXT NOT NULL,
              id TEXT PRIMARY KEY, encrypted BLOB NOT NULL);
            CREATE TABLE IF NOT EXISTS connector_pending (
              state_hash TEXT PRIMARY KEY, encrypted BLOB NOT NULL, expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS connector_schedule_selections (
              tenant TEXT NOT NULL, owner TEXT NOT NULL, agent TEXT NOT NULL,
              schedule TEXT NOT NULL, connector_ids TEXT NOT NULL,
              PRIMARY KEY(tenant,owner,agent,schedule));
            CREATE TABLE IF NOT EXISTS connector_session_selections (
              tenant TEXT NOT NULL, owner TEXT NOT NULL, agent TEXT NOT NULL,
              session TEXT NOT NULL, PRIMARY KEY(tenant,owner,agent,session));
            CREATE TABLE IF NOT EXISTS connector_installs (
              tenant TEXT NOT NULL, owner TEXT NOT NULL, connector TEXT NOT NULL,
              agent TEXT NOT NULL, session TEXT NOT NULL,
              PRIMARY KEY(tenant,owner,connector,agent,session));
            ''')
            if 'epoch' not in {r['name'] for r in db.execute('PRAGMA table_info(connectors)')}:
                db.execute('ALTER TABLE connectors ADD COLUMN epoch INTEGER NOT NULL DEFAULT 0')
            if 'lease_owner' not in {r['name'] for r in db.execute('PRAGMA table_info(connector_grants)')}:
                db.execute('ALTER TABLE connector_grants ADD COLUMN lease_owner TEXT')

    @contextmanager
    def db(self):
        db=sqlite3.connect(self.path,timeout=15)
        db.row_factory=sqlite3.Row
        try:
            with db: yield db
        finally: db.close()

    def encrypt(self, value):
        return self.cipher.encrypt(json.dumps(value,separators=(',',':'),ensure_ascii=False).encode())

    def decrypt(self, value):
        return json.loads(self.cipher.decrypt(value))

    def install(self, tenant, owner, package):
        cid=uuid.uuid4().hex
        with self.db() as db:
            if db.execute('SELECT 1 FROM connectors WHERE tenant=? AND owner=? AND source=?',(tenant,owner,package['metadata']['source'])).fetchone():
                raise ValueError('This connector is already installed; remove it before importing a replacement')
            db.execute('INSERT INTO connectors(tenant,owner,id,source,package) VALUES(?,?,?,?,?)',
                       (tenant,owner,cid,package['metadata']['source'],json.dumps(package,ensure_ascii=False)))
        return self.public(self.get(tenant,owner,cid))

    def get(self, tenant, owner, cid):
        with self.db() as db:
            row=db.execute('SELECT * FROM connectors WHERE tenant=? AND owner=? AND id=?',(tenant,owner,cid)).fetchone()
            connected=db.execute('SELECT 1 FROM connector_grants WHERE tenant=? AND owner=? AND connector=?',(tenant,owner,cid)).fetchone()
        if not row: raise KeyError('Connector not found')
        result=dict(row); result['package']=json.loads(row['package']); result['tools']=json.loads(row['tools']); result['connected']=bool(connected)
        return result

    @staticmethod
    def public(row):
        package=row['package']; meta=package['metadata']
        return {'id':row['id'],'source':meta['source'],'name':meta.get('name',meta['source']),
                'description':meta.get('description',''),'version':meta['version'],'sha256':package['sha256'],
                'status':'connected' if row['connected'] else 'installed','skills':list(package['skills']),
                'tools':row['tools'],'url':package['mcp']['url'],'examples':meta.get('examples',[])}

    def list(self, tenant, owner):
        with self.db() as db:
            ids=[r['id'] for r in db.execute('SELECT id FROM connectors WHERE tenant=? AND owner=? ORDER BY source',(tenant,owner))]
        return [self.public(self.get(tenant,owner,cid)) for cid in ids]

    def save_grant(self, tenant, owner, cid, value, *, expected_generation=None, expected_epoch=None, lease_owner=None):
        self.get(tenant,owner,cid)
        encrypted=self.encrypt(value)
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            current=db.execute('SELECT epoch FROM connectors WHERE tenant=? AND owner=? AND id=?',(tenant,owner,cid)).fetchone()
            if not current or (expected_epoch is not None and current['epoch']!=expected_epoch):
                raise ValueError('Connector was disconnected during authorization')
            if expected_generation is None:
                db.execute('INSERT INTO connector_grants(tenant,owner,connector,encrypted,generation,lease) VALUES(?,?,?,?,?,0) ON CONFLICT(tenant,owner,connector) DO UPDATE SET encrypted=excluded.encrypted,generation=excluded.generation,lease=0,lease_owner=NULL',
                           (tenant,owner,cid,encrypted,secrets.token_hex(16)))
            else:
                result=db.execute('UPDATE connector_grants SET encrypted=?,lease=0,lease_owner=NULL,generation=? WHERE tenant=? AND owner=? AND connector=? AND generation=? AND (? IS NULL OR lease_owner=?)',
                                  (encrypted,secrets.token_hex(16),tenant,owner,cid,expected_generation,lease_owner,lease_owner))
                if result.rowcount!=1: raise ValueError('Connector was disconnected during refresh')

    def grant(self, tenant, owner, cid):
        with self.db() as db:
            row=db.execute('SELECT * FROM connector_grants WHERE tenant=? AND owner=? AND connector=?',(tenant,owner,cid)).fetchone()
        if not row: return None
        value=self.decrypt(row['encrypted']); value['_generation']=row['generation']; return value

    def claim_refresh(self, tenant, owner, cid, generation):
        lease_owner=secrets.token_hex(16)
        with self.db() as db:
            claimed=db.execute('UPDATE connector_grants SET lease=?,lease_owner=? WHERE tenant=? AND owner=? AND connector=? AND generation=? AND lease<?',
                              (time.time()+60,lease_owner,tenant,owner,cid,generation,time.time())).rowcount==1
        return lease_owner if claimed else None

    def release_refresh(self, tenant, owner, cid, generation, lease_owner):
        with self.db() as db:
            db.execute('UPDATE connector_grants SET lease=0,lease_owner=NULL WHERE tenant=? AND owner=? AND connector=? AND generation=? AND lease_owner=?',(tenant,owner,cid,generation,lease_owner))

    def disconnect(self, tenant, owner, cid):
        self.get(tenant,owner,cid)
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            grant=db.execute('SELECT encrypted FROM connector_grants WHERE tenant=? AND owner=? AND connector=?',(tenant,owner,cid)).fetchone()
            if grant: db.execute('INSERT INTO connector_revocations VALUES(?,?,?,?,?)',(tenant,owner,cid,uuid.uuid4().hex,grant['encrypted']))
            db.execute('DELETE FROM connector_grants WHERE tenant=? AND owner=? AND connector=?',(tenant,owner,cid))
            db.execute("UPDATE connectors SET tools='[]',epoch=epoch+1 WHERE tenant=? AND owner=? AND id=?",(tenant,owner,cid))
            # Delete pending attempts too; an in-flight callback must not reconnect.
            for row in db.execute('SELECT state_hash,encrypted FROM connector_pending').fetchall():
                p=self.decrypt(row['encrypted'])
                if (p['tenant'],p['owner'],p['connector'])==(tenant,owner,cid):
                    db.execute('DELETE FROM connector_pending WHERE state_hash=?',(row['state_hash'],))

    def remove(self, tenant, owner, cid):
        self.disconnect(tenant,owner,cid)
        with self.db() as db:
            db.execute('DELETE FROM connectors WHERE tenant=? AND owner=? AND id=?',(tenant,owner,cid))
            db.execute('DELETE FROM connector_installs WHERE tenant=? AND owner=? AND connector=?',(tenant,owner,cid))

    def pending(self, state_hash, value, *, ttl=600):
        with self.db() as db:
            db.execute('DELETE FROM connector_pending WHERE expires<?',(time.time(),))
            db.execute('INSERT INTO connector_pending VALUES(?,?,?)',(state_hash,self.encrypt(value),time.time()+ttl))

    def consume_pending(self, state_hash):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT encrypted FROM connector_pending WHERE state_hash=? AND expires>?',(state_hash,time.time())).fetchone()
            db.execute('DELETE FROM connector_pending WHERE state_hash=?',(state_hash,))
        if not row: raise ValueError('Authorization attempt expired or already used')
        return self.decrypt(row['encrypted'])

    def tools(self, tenant, owner, cid, tools):
        self.get(tenant,owner,cid)
        with self.db() as db:
            db.execute('UPDATE connectors SET tools=? WHERE tenant=? AND owner=? AND id=?',(json.dumps(tools,ensure_ascii=False),tenant,owner,cid))

    def bind(self, tenant, owner, cid, agent, session):
        self.get(tenant,owner,cid)
        with self.db() as db:
            db.execute('INSERT OR IGNORE INTO connector_installs VALUES(?,?,?,?,?)',(tenant,owner,cid,agent,session))

    def replace_bindings(self, tenant, owner, agent, session, connector_ids):
        if len(connector_ids)!=len(set(connector_ids)):
            raise ValueError('Duplicate connector selection')
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            for cid in connector_ids:
                row=db.execute('SELECT 1 FROM connectors c JOIN connector_grants g ON c.tenant=g.tenant AND c.owner=g.owner AND c.id=g.connector WHERE c.tenant=? AND c.owner=? AND c.id=?',(tenant,owner,cid)).fetchone()
                if not row: raise ValueError('Select only connected connectors owned by this account')
            db.execute('INSERT OR IGNORE INTO connector_session_selections VALUES(?,?,?,?)',(tenant,owner,agent,session))
            db.execute('DELETE FROM connector_installs WHERE tenant=? AND owner=? AND agent=? AND session=?',(tenant,owner,agent,session))
            db.executemany('INSERT INTO connector_installs VALUES(?,?,?,?,?)',
                           [(tenant,owner,cid,agent,session) for cid in connector_ids])

    def inherit_schedule(self, tenant, owner, agent, schedule, source, session):
        """Freeze source selection on first execution; initialize each run once."""
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            scope=(tenant,owner,agent)
            snapshot=db.execute('SELECT connector_ids FROM connector_schedule_selections WHERE tenant=? AND owner=? AND agent=? AND schedule=?',(*scope,schedule)).fetchone()
            if snapshot is None:
                ids=[r['connector'] for r in db.execute('SELECT connector FROM connector_installs WHERE tenant=? AND owner=? AND agent=? AND session=?',(*scope,source))]
                db.execute('INSERT INTO connector_schedule_selections VALUES(?,?,?,?,?)',(*scope,schedule,json.dumps(ids)))
            else:
                ids=json.loads(snapshot['connector_ids'])
            selected=db.execute('SELECT 1 FROM connector_session_selections WHERE tenant=? AND owner=? AND agent=? AND session=?',(*scope,session)).fetchone()
            current=[r['connector'] for r in db.execute('SELECT connector FROM connector_installs WHERE tenant=? AND owner=? AND agent=? AND session=?',(*scope,session))]
            if selected or current:
                ids=current
            for cid in ids:
                if not db.execute('SELECT 1 FROM connector_grants WHERE tenant=? AND owner=? AND connector=?',(tenant,owner,cid)).fetchone():
                    raise ValueError('定时任务所需连接器未授权或授权已撤销，请重新授权后重试')
            if not selected and not current:
                db.executemany('INSERT INTO connector_installs VALUES(?,?,?,?,?)',[(tenant,owner,cid,agent,session) for cid in ids])
            db.execute('INSERT OR IGNORE INTO connector_session_selections VALUES(?,?,?,?)',(*scope,session))
            return ids

    def bindings(self, tenant, owner, agent, session):
        with self.db() as db:
            return [r['connector'] for r in db.execute('SELECT connector FROM connector_installs WHERE tenant=? AND owner=? AND agent=? AND session=?',(tenant,owner,agent,session))]

    def queue_revocation(self, tenant, owner, cid, value):
        with self.db() as db:
            db.execute('INSERT INTO connector_revocations VALUES(?,?,?,?,?)',(tenant,owner,cid,uuid.uuid4().hex,self.encrypt(value)))

    def revocations(self, tenant, owner, cid):
        with self.db() as db:
            return [(r['id'],self.decrypt(r['encrypted'])) for r in db.execute('SELECT id,encrypted FROM connector_revocations WHERE tenant=? AND owner=? AND connector=?',(tenant,owner,cid))]

    def revoked(self, key):
        with self.db() as db: db.execute('DELETE FROM connector_revocations WHERE id=?',(key,))

    def invalidate_grant(self, tenant, owner, cid, generation):
        """A failed/ambiguous refresh must not reuse a possibly consumed token."""
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT encrypted FROM connector_grants WHERE tenant=? AND owner=? AND connector=? AND generation=?',(tenant,owner,cid,generation)).fetchone()
            if row:
                db.execute('INSERT INTO connector_revocations VALUES(?,?,?,?,?)',(tenant,owner,cid,uuid.uuid4().hex,row['encrypted']))
                db.execute('DELETE FROM connector_grants WHERE tenant=? AND owner=? AND connector=? AND generation=?',(tenant,owner,cid,generation))

    def installations(self, tenant, owner, cid):
        self.get(tenant,owner,cid)
        with self.db() as db:
            return [{'agent_id':r['agent'],'session_id':r['session']} for r in db.execute('SELECT agent,session FROM connector_installs WHERE tenant=? AND owner=? AND connector=? ORDER BY agent,session',(tenant,owner,cid))]
