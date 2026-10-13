"""Server-only, short-lived receipts bound to saved approval challenges."""
import base64
import hashlib
import hmac
import json
import secrets
import time


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()


def b64(value):
    return base64.urlsafe_b64encode(value).rstrip(b'=').decode()


def receipt(key, tenant, user, connector, challenge):
    payload = {'tenant': tenant, 'user': user, 'connector': connector,
        'operation_id': challenge['operation_id'],
        'arguments_sha256': hashlib.sha256(canonical(challenge['arguments'])).hexdigest(),
        'exp': min(int(challenge['expires_at']), int(time.time()) + 300),
        'jti': secrets.token_urlsafe(24)}
    encoded = b64(canonical(payload))
    return encoded + '.' + b64(hmac.digest(key.encode(), encoded.encode(), 'sha256'))


def validate_challenge(value):
    if not isinstance(value, dict): raise ValueError('Missing approval challenge')
    for field in ('operation_id', 'title', 'summary'):
        if not isinstance(value.get(field), str) or not value[field] or len(value[field]) > 10000:
            raise ValueError('Invalid approval challenge')
    if not isinstance(value.get('arguments'), dict): raise ValueError('Invalid approval arguments')
    expires = value.get('expires_at')
    if isinstance(expires, bool) or not isinstance(expires, (int, float)) or not time.time() < expires <= time.time() + 600:
        raise ValueError('Invalid approval expiry')
    return value
