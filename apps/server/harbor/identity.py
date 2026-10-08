"""Persistent accounts, tenants and revocable opaque sessions."""
from contextlib import contextmanager
import hashlib
import hmac
from pathlib import Path
import secrets
import sqlite3
import time
import uuid

from fastapi import HTTPException


def password_hash(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1)
    return f'{salt}:{digest.hex()}'


class IdentityStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL COLLATE NOCASE,
                    name TEXT NOT NULL, password_hash TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS tenants (id TEXT PRIMARY KEY, name TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS members (
                    tenant_id TEXT REFERENCES tenants(id), user_id TEXT REFERENCES users(id),
                    role TEXT NOT NULL CHECK(role IN ('owner', 'member')),
                    PRIMARY KEY(tenant_id, user_id)
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY, user_id TEXT REFERENCES users(id),
                    tenant_id TEXT REFERENCES tenants(id), expires REAL NOT NULL
                );
            ''')

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    def register(self, email, name, password, tenant_name):
        user_id, tenant_id = uuid.uuid4().hex, uuid.uuid4().hex
        hashed = password_hash(password)
        try:
            with self.db() as db:
                db.execute('INSERT INTO users VALUES (?,?,?,?)', (user_id, email.lower(), name, hashed))
                db.execute('INSERT INTO tenants VALUES (?,?)', (tenant_id, tenant_name))
                db.execute('INSERT INTO members VALUES (?,?,?)', (tenant_id, user_id, 'owner'))
        except sqlite3.IntegrityError:
            raise HTTPException(409, '该邮箱已注册') from None
        return user_id, tenant_id

    def login(self, email, password):
        with self.db() as db:
            user = db.execute('SELECT * FROM users WHERE email=?', (email.lower(),)).fetchone()
            # Equal work for unknown accounts to avoid a cheap timing oracle.
            stored = user['password_hash'] if user else '00' * 16 + ':' + '00' * 64
            computed = password_hash(password, stored.split(':')[0])
            if not hmac.compare_digest(stored, computed):
                raise HTTPException(401, '邮箱或密码不正确')
            member = db.execute('SELECT tenant_id FROM members WHERE user_id=? ORDER BY tenant_id LIMIT 1', (user['id'],)).fetchone()
            if not member:
                raise HTTPException(403, '该账号没有可用工作空间')
            return user['id'], member['tenant_id']

    @staticmethod
    def digest(token):
        return hashlib.sha256(token.encode()).hexdigest()

    def new_session(self, user_id, tenant_id):
        token = secrets.token_urlsafe(32)
        with self.db() as db:
            db.execute('DELETE FROM sessions WHERE expires < ?', (time.time(),))
            db.execute('INSERT INTO sessions VALUES (?,?,?,?)', (self.digest(token), user_id, tenant_id, time.time() + 86400))
        return token

    def authenticate(self, token):
        with self.db() as db:
            row = db.execute('''SELECT s.user_id, s.tenant_id, u.name, u.email
                FROM sessions s JOIN users u ON u.id=s.user_id
                WHERE s.token_hash=? AND s.expires>?''', (self.digest(token), time.time())).fetchone()
        if not row:
            raise HTTPException(401, '请登录 AgentHarbor')
        return dict(row)

    def revoke(self, token):
        with self.db() as db:
            db.execute('DELETE FROM sessions WHERE token_hash=?', (self.digest(token),))

    def membership(self, user_id, tenant_id, *, owner=False):
        with self.db() as db:
            row = db.execute('SELECT role FROM members WHERE user_id=? AND tenant_id=?', (user_id, tenant_id)).fetchone()
        if not row or (owner and row['role'] != 'owner'):
            raise HTTPException(403, '没有该工作空间的访问权限' if not owner else '仅空间所有者可以管理成员')
        return row['role']

    def me(self, principal):
        with self.db() as db:
            rows = db.execute('''SELECT t.id,t.name,m.role FROM tenants t JOIN members m
                ON m.tenant_id=t.id WHERE m.user_id=? ORDER BY t.name''', (principal['user_id'],)).fetchall()
        return {
            'user': {'id': principal['user_id'], 'email': principal['email'], 'name': principal['name']},
            'active_tenant_id': principal['tenant_id'], 'tenants': [dict(row) for row in rows],
        }

    def create_tenant(self, user_id, name):
        tenant_id = uuid.uuid4().hex
        with self.db() as db:
            db.execute('INSERT INTO tenants VALUES (?,?)', (tenant_id, name))
            db.execute('INSERT INTO members VALUES (?,?,?)', (tenant_id, user_id, 'owner'))
        return {'id': tenant_id, 'name': name, 'role': 'owner'}

    def switch(self, token, user_id, tenant_id):
        self.membership(user_id, tenant_id)
        with self.db() as db:
            db.execute('UPDATE sessions SET tenant_id=? WHERE token_hash=?', (tenant_id, self.digest(token)))

    def members(self, user_id, tenant_id):
        self.membership(user_id, tenant_id)
        with self.db() as db:
            return [dict(r) for r in db.execute('''SELECT u.id,u.name,u.email,m.role FROM members m
                JOIN users u ON u.id=m.user_id WHERE m.tenant_id=? ORDER BY u.name''', (tenant_id,))]

    def add_member(self, user_id, tenant_id, email):
        self.membership(user_id, tenant_id, owner=True)
        with self.db() as db:
            user = db.execute('SELECT id FROM users WHERE email=?', (email.lower(),)).fetchone()
            if not user:
                raise HTTPException(404, '请对方先注册账号，再添加为成员')
            try:
                db.execute('INSERT INTO members VALUES (?,?,?)', (tenant_id, user['id'], 'member'))
            except sqlite3.IntegrityError:
                raise HTTPException(409, '该用户已经是空间成员') from None

    def remove_member(self, user_id, tenant_id, member_id):
        self.membership(user_id, tenant_id, owner=True)
        with self.db() as db:
            row = db.execute('SELECT role FROM members WHERE tenant_id=? AND user_id=?', (tenant_id, member_id)).fetchone()
            if not row:
                raise HTTPException(404, '成员不存在')
            if row['role'] == 'owner':
                raise HTTPException(400, '不能移除空间所有者')
            db.execute('DELETE FROM members WHERE tenant_id=? AND user_id=?', (tenant_id, member_id))
