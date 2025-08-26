"""
Helper to sign challenge bytes with the user's OpenSSH ed25519 private key
(~/.ollama/id_ed25519 by default). Produces tokens that match the Go client's
format: "<base64(pubkey_blob)>:<base64(signature_blob)>".

Only ed25519 keys are supported.

Install dependency when using signing:
  pip install cryptography
"""

from __future__ import annotations

import base64
import struct
from pathlib import Path
from typing import Optional

# Default location used by the Go client
DEFAULT_KEY_PATH = Path.home() / ".ollama" / "id_ed25519"


def _pack_ssh_string(b: bytes) -> bytes:
    """Return SSH wire-format string: 4-byte big-endian length + bytes."""
    return struct.pack(">I", len(b)) + b


def _ensure_cryptography_available():
    try:
        # Import inside function so module import doesn't require cryptography when signing is unused.
        from cryptography.hazmat.primitives.asymmetric import ed25519  # noqa: F401
        from cryptography.hazmat.primitives import serialization  # noqa: F401
    except Exception as exc:
        raise ImportError(
            "The 'cryptography' package is required for Ollama signing. "
            "Install it with: pip install cryptography"
        ) from exc


def sign_challenge(challenge: bytes, key_path: Optional[str] = None, password: Optional[bytes] = None) -> str:
    """
    Sign `challenge` and return the token matching the Go client:
      "<base64(ssh_pubkey_blob)>:<base64(ssh_signature_blob)>"

    Args:
      challenge: bytes to sign
      key_path: optional path to OpenSSH private key. Defaults to ~/.ollama/id_ed25519
      password: optional password bytes if the key is encrypted

    Raises:
      FileNotFoundError if the key file isn't found.
      ImportError if cryptography isn't installed.
      ValueError for unsupported key types.
    """
    _ensure_cryptography_available()
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    key_file = Path(key_path) if key_path else DEFAULT_KEY_PATH
    key_bytes = key_file.read_bytes()  # raises FileNotFoundError if missing

    # Load OpenSSH private key (accepts OpenSSH and PEM formats)
    private_key = serialization.load_ssh_private_key(key_bytes, password=password)

    if not isinstance(private_key, Ed25519PrivateKey):
        raise ValueError("Only ed25519 private keys are supported for Ollama signing")

    # Raw public key (32 bytes for ed25519)
    public_key = private_key.public_key()
    pubkey_raw = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )

    # Build SSH public-key blob: string "ssh-ed25519" + string(pubkey_raw)
    name = b"ssh-ed25519"
    pubkey_blob = _pack_ssh_string(name) + _pack_ssh_string(pubkey_raw)
    pubkey_b64 = base64.b64encode(pubkey_blob).decode("ascii")

    # Sign challenge (ed25519) -> 64 bytes
    sig_raw = private_key.sign(challenge)

    # Build SSH signature blob: string "ssh-ed25519" + string(sig_raw)
    sig_blob = _pack_ssh_string(name) + _pack_ssh_string(sig_raw)
    sig_b64 = base64.b64encode(sig_blob).decode("ascii")

    return f"{pubkey_b64}:{sig_b64}"
