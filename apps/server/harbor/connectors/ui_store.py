"""Encrypted, owner-scoped MCP call snapshots and short-lived UI handles."""
import hashlib
import secrets
import time


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


class UIStore:
    def __init__(self, store):
        self.store = store
        with store.db() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS connector_ui_records (
                token TEXT PRIMARY KEY, kind TEXT NOT NULL, tenant TEXT NOT NULL,
                owner TEXT NOT NULL, encrypted BLOB NOT NULL, expires REAL NOT NULL)''')
            db.execute('''CREATE TABLE IF NOT EXISTS connector_ui_approval_audit (
                id TEXT PRIMARY KEY, tenant TEXT, owner TEXT, connector TEXT,
                operation TEXT, decision TEXT, created REAL)''')

    def audit(self, token, tenant, owner, connector, operation, decision):
        with self.store.db() as db:
            db.execute('INSERT INTO connector_ui_approval_audit VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET decision=excluded.decision',
                (digest(token), tenant, owner, connector, operation, decision, time.time()))

    def put(self, kind, tenant, owner, value, ttl=0):
        token = secrets.token_urlsafe(32)
        with self.store.db() as db:
            db.execute('INSERT INTO connector_ui_records VALUES(?,?,?,?,?,?)',
                (digest(token), kind, tenant, owner, self.store.encrypt(value), time.time() + ttl if ttl else 0))
        return token

    def get(self, kind, tenant, owner, token):
        with self.store.db() as db:
            row = db.execute('SELECT encrypted FROM connector_ui_records WHERE token=? AND kind=? AND tenant=? AND owner=? AND (expires=0 OR expires>?)',
                (digest(token), kind, tenant, owner, time.time())).fetchone()
        if row is None: raise KeyError('UI association not found or expired')
        return self.store.decrypt(row['encrypted'])

    def delete(self, kind, tenant, owner, token):
        with self.store.db() as db:
            db.execute('DELETE FROM connector_ui_records WHERE token=? AND kind=? AND tenant=? AND owner=?', (digest(token), kind, tenant, owner))

    def take(self, kind, tenant, owner, token):
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT encrypted FROM connector_ui_records WHERE token=? AND kind=? AND tenant=? AND owner=? AND expires>?',
                (digest(token), kind, tenant, owner, time.time())).fetchone()
            if row is None: raise KeyError('Approval expired or already decided')
            db.execute('DELETE FROM connector_ui_records WHERE token=?', (digest(token),))
        return self.store.decrypt(row['encrypted'])

    def record(self, tenant, owner, cid, agent, session, tool, arguments, result):
        row = self.store.get(tenant, owner, cid)
        uri = (tool.get('_meta') or {}).get('ui', {}).get('resourceUri')
        if not isinstance(uri, str) or not uri.startswith('ui://'): raise ValueError('Invalid MCP App resource')
        value = {'connector': cid, 'agent_id': agent, 'session_id': session,
            'epoch': row['epoch'], 'resource_uri': uri, 'resource_version': row['package']['sha256'],
            'tool_name': tool['name'], 'tool': tool, 'tool_input': arguments, 'tool_result': result}
        self.validate(tenant, owner, value)
        return self.put('call', tenant, owner, value)

    def validate(self, tenant, owner, value):
        row = self.store.get(tenant, owner, value['connector'])
        if row['package']['sha256'] != value['resource_version']:
            raise ValueError('Connector package version changed')
        if not row['connected'] or row['epoch'] != value['epoch']:
            raise ValueError('Connector authorization changed')
        if value['connector'] not in self.store.bindings(tenant, owner, value['agent_id'], value['session_id']):
            raise ValueError('Connector is no longer selected in this chat')
        return value

    def call(self, tenant, owner, token):
        return self.validate(tenant, owner, self.get('call', tenant, owner, token))

    def session(self, tenant, owner, token):
        return self.validate(tenant, owner, self.get('session', tenant, owner, token))

    def sandbox(self, token):
        with self.store.db() as db:
            row = db.execute('SELECT tenant,owner,encrypted FROM connector_ui_records WHERE token=? AND kind=? AND expires>?',
                (digest(token), 'sandbox', time.time())).fetchone()
        if row is None: raise KeyError('Sandbox expired')
        value = self.store.decrypt(row['encrypted'])
        return row['tenant'], row['owner'], self.session(row['tenant'], row['owner'], value['session'])
