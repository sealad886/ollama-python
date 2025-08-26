from __future__ import annotations

import struct
import urllib.parse
from pathlib import Path

import httpx
import pytest

from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization

import ollama

# Default key location the client will look for
DEFAULT_KEY = Path.home() / ".ollama" / "id_ed25519"


def _unpack_ssh_string(data: bytes):
    """
    Unpack a single SSH wire-format string: 4-byte big-endian length + bytes.
    Returns (extracted_bytes, remaining_bytes).
    """
    if len(data) < 4:
        raise ValueError("ssh-string too short")
    n = struct.unpack(">I", data[:4])[0]
    if len(data) < 4 + n:
        raise ValueError("ssh-string truncated")
    return data[4 : 4 + n], data[4 + n :]


def _parse_token_and_verify_signature(token: str, method: str, path: str, ts: str) -> None:
    """
    Given an Authorization token of the form '<pub_b64>:<sig_b64>', parse both
    SSH wire-format blobs, extract the public key and signature, and verify the
    signature against the expected challenge constructed as:
      f"{METHOD},{PATH}?ts={ts}"
    """
    import base64
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    assert ":" in token, "token missing ':' separator"
    pub_b64, sig_b64 = token.split(":", 1)
    pub_blob = base64.b64decode(pub_b64)
    sig_blob = base64.b64decode(sig_b64)

    # Parse public-key blob -> name, pubkey_raw
    name1, rest = _unpack_ssh_string(pub_blob)
    assert name1 == b"ssh-ed25519", f"unexpected pubkey name: {name1!r}"
    pubkey_raw, leftover = _unpack_ssh_string(rest)
    assert leftover == b"", "unexpected trailing bytes in public-key blob"
    assert len(pubkey_raw) == 32, "unexpected ed25519 pubkey length"

    # Parse signature blob -> name, sig_raw
    name2, rest = _unpack_ssh_string(sig_blob)
    assert name2 == b"ssh-ed25519", f"unexpected sig name: {name2!r}"
    sig_raw, leftover2 = _unpack_ssh_string(rest)
    assert leftover2 == b"", "unexpected trailing bytes in signature blob"
    assert len(sig_raw) == 64, "unexpected ed25519 signature length"

    # Reconstruct challenge the client should have signed
    challenge = f"{method},{path}?ts={ts}".encode("utf-8")

    # Verify signature
    pubkey = Ed25519PublicKey.from_public_bytes(pubkey_raw)
    # Will raise InvalidSignature if invalid
    pubkey.verify(sig_raw, challenge)


def _require_real_key():
    if not DEFAULT_KEY.exists():
        pytest.skip(f"Real Ollama key not present at {DEFAULT_KEY!s}; skipping test.")


def test_client_signing_with_real_key_sync():
    """
    Instantiate ollama.Client pointing to https://ollama.com and verify that requests
    are signed using the real key at ~/.ollama/id_ed25519.
    """
    _require_real_key()

    # Mock transport checks the outgoing request
    def handler(request: httpx.Request) -> httpx.Response:
        # Ensure ts query param present
        qs = urllib.parse.parse_qs(request.url.query)
        assert "ts" in qs, "ts query parameter missing from signed request"
        ts = qs["ts"][0]

        # Authorization header present
        auth = request.headers.get("authorization")
        assert auth, "Authorization header missing from signed request"

        # Reconstruct path (path component only) and verify signature
        _parse_token_and_verify_signature(auth, request.method, request.url.path, ts)

        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)

    # Create Client; pass transport through so httpx uses our mock handler.
    client = ollama.Client(host="https://ollama.com", transport=transport)

    # Trigger a relative-path request which the client should sign
    resp = client._request_raw("GET", "/v1/ping")
    assert resp.status_code == 200
    assert resp.json().get("ok") is True


@pytest.mark.asyncio
async def test_client_signing_with_real_key_async():
    """
    Async variant: instantiate ollama.AsyncClient and ensure requests are signed
    using the real key at ~/.ollama/id_ed25519.
    """
    _require_real_key()

    async def handler(request: httpx.Request) -> httpx.Response:
        qs = urllib.parse.parse_qs(request.url.query)
        assert "ts" in qs, "ts query parameter missing from signed request"
        ts = qs["ts"][0]

        auth = request.headers.get("authorization")
        assert auth, "Authorization header missing from signed request"

        _parse_token_and_verify_signature(auth, request.method, request.url.path, ts)

        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)

    async_client = ollama.AsyncClient(host="https://ollama.com", transport=transport)

    resp = await async_client._request_raw("GET", "/v1/ping")
    assert resp.status_code == 200
    assert resp.json().get("ok") is True
