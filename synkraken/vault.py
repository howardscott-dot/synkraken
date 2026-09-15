from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from threading import Lock

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import keyring


class CredentialVault:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.lock = Lock()
        self.account = hashlib.sha256(str(directory.resolve()).encode()).hexdigest()

    def _key(self) -> bytes:
        encoded = os.environ.get('SYNKRAKEN_VAULT_KEY')
        if not encoded:
            try:
                backend = keyring.get_keyring()
                if type(backend).__module__ not in {'keyring.backends.macOS', 'keyring.backends.SecretService',
                                                   'keyring.backends.kwallet', 'keyring.backends.Windows'}:
                    raise ValueError('A supported OS keychain or explicit host-managed vault key is required')
                encoded = keyring.get_password('SynKraken vault', self.account)
                if not encoded:
                    if self.directory.exists() and any(self.directory.glob('*.enc')):
                        raise ValueError('Vault key is missing; restore the original key before opening this vault')
                    encoded = base64.urlsafe_b64encode(AESGCM.generate_key(bit_length=256)).decode()
                    keyring.set_password('SynKraken vault', self.account, encoded)
            except ValueError:
                raise
            except Exception:
                raise ValueError('Host keychain is unavailable. Unlock it or configure SYNKRAKEN_VAULT_KEY through the host secret manager') from None
        try:
            key = base64.b64decode(encoded, altchars=b'-_', validate=True)
            if len(key) != 32:
                raise ValueError()
            return key
        except Exception:
            raise ValueError('Vault key must encode exactly 32 bytes') from None

    def _path(self, reference: str) -> Path:
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,120}', reference):
            raise ValueError('Invalid credential reference')
        return self.directory / (reference + '.enc')

    def contains(self, reference: str) -> bool:
        return self._path(reference).is_file()

    def put(self, reference: str, secret: dict) -> None:
        path = self._path(reference)
        with self.lock:
            key = self._key()
            nonce = os.urandom(12)
            sealed = AESGCM(key).encrypt(nonce, json.dumps(secret).encode(), reference.encode())
            payload = json.dumps({'version': 1, 'nonce': base64.b64encode(nonce).decode(),
                                  'ciphertext': base64.b64encode(sealed).decode()})
            self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            os.chmod(self.directory, 0o700)
            fd, temporary = tempfile.mkstemp(dir=self.directory)
            try:
                with os.fdopen(fd, 'w') as handle:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, path)
            finally:
                Path(temporary).unlink(missing_ok=True)

    def get(self, reference: str) -> dict:
        with self.lock:
            try:
                payload = json.loads(self._path(reference).read_text())
                if payload['version'] != 1:
                    raise ValueError()
                clear = AESGCM(self._key()).decrypt(base64.b64decode(payload['nonce']),
                    base64.b64decode(payload['ciphertext']), reference.encode())
                return json.loads(clear)
            except (InvalidTag, KeyError, OSError, ValueError):
                raise ValueError('Credential vault could not be unlocked or verified') from None

    def encrypted_export(self) -> dict:
        return {'version': 1, 'entries': {path.name: json.loads(path.read_text())
                for path in self.directory.glob('*.enc')}}
