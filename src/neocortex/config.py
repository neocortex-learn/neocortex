"""Configuration management for Neocortex."""

from __future__ import annotations

import base64
import json
import socket
import uuid
from pathlib import Path

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from neocortex.models import AppConfig, Profile

_ENC_PREFIX = "enc:"
_SALT = b"neocortex-api-key-salt"


def _get_machine_fingerprint() -> str:
    mac = uuid.getnode()
    hostname = socket.gethostname()
    return f"{mac:012x}-{hostname}"


def _derive_fernet_key() -> bytes:
    fingerprint = _get_machine_fingerprint().encode()
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_SALT,
        iterations=480_000,
    )
    key_bytes = kdf.derive(fingerprint)
    return base64.urlsafe_b64encode(key_bytes)


def _encrypt(plaintext: str) -> str:
    fernet = Fernet(_derive_fernet_key())
    token = fernet.encrypt(plaintext.encode())
    return _ENC_PREFIX + token.decode()


def _decrypt(ciphertext: str) -> str:
    if not ciphertext.startswith(_ENC_PREFIX):
        return ciphertext
    raw = ciphertext[len(_ENC_PREFIX):]
    fernet = Fernet(_derive_fernet_key())
    try:
        token = raw.encode()
        return fernet.decrypt(token).decode()
    except Exception:
        token = base64.urlsafe_b64decode(raw)
        return fernet.decrypt(token).decode()


def get_data_dir() -> Path:
    data_dir = Path.home() / ".neocortex"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_notes_dir() -> Path:
    notes_dir = get_data_dir() / "notes"
    notes_dir.mkdir(parents=True, exist_ok=True)
    return notes_dir


def _config_path() -> Path:
    return get_data_dir() / "config.json"


def _profile_path() -> Path:
    return get_data_dir() / "profile.json"


def load_config() -> AppConfig:
    path = _config_path()
    if not path.exists():
        return AppConfig()
    data = json.loads(path.read_text(encoding="utf-8"))
    api_key = data.get("api_key")
    if api_key and isinstance(api_key, str) and api_key.startswith(_ENC_PREFIX):
        try:
            data["api_key"] = _decrypt(api_key)
        except Exception:
            import warnings
            warnings.warn("Failed to decrypt API key. Please reconfigure with: neocortex config --api-key <key>")
            data["api_key"] = None
    github_token = data.get("github_token")
    if github_token and isinstance(github_token, str) and github_token.startswith(_ENC_PREFIX):
        try:
            data["github_token"] = _decrypt(github_token)
        except Exception:
            import warnings
            warnings.warn("Failed to decrypt GitHub token. Please reconfigure with: neocortex config --github-token <token>")
            data["github_token"] = None
    return AppConfig.model_validate(data)


def save_config(config: AppConfig) -> None:
    data = config.model_dump(mode="json")
    if data.get("api_key") and not data["api_key"].startswith(_ENC_PREFIX):
        data["api_key"] = _encrypt(data["api_key"])
    if data.get("github_token") and not data["github_token"].startswith(_ENC_PREFIX):
        data["github_token"] = _encrypt(data["github_token"])
    path = _config_path()
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def load_profile() -> Profile:
    path = _profile_path()
    if not path.exists():
        return Profile()
    data = json.loads(path.read_text(encoding="utf-8"))
    return Profile.model_validate(data)


def save_profile(profile: Profile) -> None:
    path = _profile_path()
    data = profile.model_dump(mode="json")
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
