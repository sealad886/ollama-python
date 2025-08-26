#!/usr/bin/env python3
"""
Exercise the client's chat path while forcing real-key signing and observing
what the library would send to https://ollama.com.

This script:
 - Confirms a real key exists at ~/.ollama/id_ed25519 (the client's default).
 - Creates an httpx.MockTransport handler that prints the outgoing request:
     - method, url, query params
     - presence of ts and Authorization header
     - truncated Authorization token
     - request body (if any)
 - Instantiates ollama.Client(host="https://ollama.com", transport=MockTransport)
   so the client's normal signing hook runs (signing uses ~/.ollama id_ed25519).
 - Attempts to call client.chat(...) if available; if that fails it falls back to
   making a manual POST via client._request_raw("POST", "/v1/chat", json=...),
   which also goes through the client's signing path for relative URLs.
 - Prints the mocked response.

Run:
  pip install cryptography httpx pytest  # if needed
  python examples/chat_with_real_key_and_mock.py

Note: This script does not perform a real network request; it uses MockTransport
so you can inspect the exact request the client would send (including the
Authorization token produced from your real ~/.ollama key).
"""
from __future__ import annotations

import base64
import struct
import sys
import urllib.parse
from pathlib import Path
from typing import Optional

import httpx

import ollama

# Default key location the client will look for
DEFAULT_KEY = Path.home() / ".ollama" / "id_ed25519"


def _unpack_ssh_string(data: bytes):
    """Unpack a single SSH wire-format string (4-byte BE length + bytes)."""
    if len(data) < 4:
        raise ValueError("ssh-string too short")
    n = struct.unpack(">I", data[:4])[0]
    if len(data) < 4 + n:
        raise ValueError("ssh-string truncated")
    return data[4 : 4 + n], data[4 + n :]


def _parse_token(token: str) -> tuple[bytes, bytes]:
    """
    Parse '<pub_b64>:<sig_b64>' into (pubkey_raw, sig_raw).
    Returns raw public-key bytes and raw signature bytes (not full SSH blobs).
    """
    pub_b64, sig_b64 = token.split(":", 1)
    pub_blob = base64.b64decode(pub_b64)
    sig_blob = base64.b64decode(sig_b64)

    name1, rest = _unpack_ssh_string(pub_blob)
    if name1 != b"ssh-ed25519":
        raise ValueError("unexpected pubkey name")
    pubkey_raw, leftover = _unpack_ssh_string(rest)
    if leftover:
        raise ValueError("trailing bytes in pubkey blob")

    name2, rest = _unpack_ssh_string(sig_blob)
    if name2 != b"ssh-ed25519":
        raise ValueError("unexpected sig name")
    sig_raw, leftover2 = _unpack_ssh_string(rest)
    if leftover2:
        raise ValueError("trailing bytes in sig blob")

    return pubkey_raw, sig_raw


def make_mock_transport_handler():
    """
    Return a handler suitable for httpx.MockTransport that will:
      - print the request details
      - sanity-check ts and authorization presence
      - attempt to parse the Authorization token and print the public key length
      - return a simple JSON reply that resembles a chat response
    """

    def handler(request: httpx.Request) -> httpx.Response:
        print("=== MockTransport received request ===")
        print(f"Method: {request.method}")
        print(f"URL: {request.url}")
        parsed = urllib.parse.urlparse(str(request.url))
        print("Path:", parsed.path)
        qs = urllib.parse.parse_qs(parsed.query)
        print("Query params:", qs)
        if "ts" in qs:
            print("ts present:", qs["ts"][0])
        else:
            print("ts missing!")

        auth = request.headers.get("authorization")
        if auth:
            print("Authorization header present (truncated):", auth[:120] + ("..." if len(auth) > 120 else ""))
            try:
                pubkey_raw, sig_raw = _parse_token(auth)
                print(f"Parsed public key length: {len(pubkey_raw)} bytes")
                print(f"Parsed signature length:   {len(sig_raw)} bytes")
            except Exception as e:
                print("Failed to parse token:", e)
        else:
            print("No Authorization header present")

        # Print request body if JSON-like
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            try:
                print("Request JSON body:", request.read().decode("utf-8"))
            except Exception:
                # httpx Request.read() may exhaust; attempt to show .content if available
                print("Request content (raw):", getattr(request, "content", "<no content>"))
        else:
            # For other content types or empty bodies
            try:
                body = request.read().decode("utf-8")
                if body:
                    print("Request body:", body)
            except Exception:
                pass

        # Respond with a plausible chat-like JSON payload
        mock_json = {
            "id": "mock-chat-1",
            "object": "chat.completion",
            "choices": [{"message": {"role": "assistant", "content": "This is a mock reply from MockTransport"}}],
        }
        print("=== End of captured request ===\n")
        return httpx.Response(200, json=mock_json)

    return handler


def run_sync_demo():
    if not DEFAULT_KEY.exists():
        print(f"Real key not found at {DEFAULT_KEY!s}. Place your id_ed25519 there to test live signing.")
        sys.exit(2)

    handler = make_mock_transport_handler()
    transport = httpx.MockTransport(handler)

    # Instantiate the Client and pass our mock transport in so all requests go to handler.
    # The client's signing logic will run because host is https://ollama.com and the path is relative.
    client = ollama.Client(host="https://ollama.com", transport=transport)

    # A conservative chat payload: many clients accept a 'messages' list with role/content.
    chat_payload = {"messages": [{"role": "user", "content": "Hello from test script"}]}

    # First try to call client.chat if it exists (best-effort). If the signature mismatches the actual API
    # this will raise — we capture and fall back to the manual POST which still exercises signing.
    if hasattr(client, "chat"):
        try:
            print("Attempting to call client.chat(...) (best-effort)...")
            # Try common calling conventions; adapt if your client expects different args.
            try:
                # Preferred: typical signature like client.chat(messages=[...])
                resp = client.chat(messages=chat_payload["messages"])
            except TypeError:
                # Fallback: maybe the client accepts a single dict
                resp = client.chat(chat_payload)
            # If chat returned a high-level object, try to extract json or dict-like
            try:
                print("client.chat returned:", getattr(resp, "json", lambda: resp)())
            except Exception:
                print("client.chat result:", resp)
            return
        except Exception as e:
            print("client.chat(...) call failed (falling back to manual POST):", repr(e))

    # Fallback: use lower-level request which still goes through the same signing hook
    print("Calling low-level POST to /v1/chat to demonstrate signing path...")
    try:
        # This will be intercepted by BaseClient._request_raw which appends ts and signs.
        resp = client._request_raw("POST", "/v1/chat", json=chat_payload)
        print("Response status:", resp.status_code)
        try:
            print("Response JSON:", resp.json())
        except Exception:
            print("Response content:", resp.content)
    except Exception as e:
        print("Request failed:", e)


async def run_async_demo():
    if not DEFAULT_KEY.exists():
        print(f"Real key not found at {DEFAULT_KEY!s}. Place your id_ed25519 there to test live signing.")
        return

    handler = make_mock_transport_handler()
    transport = httpx.MockTransport(handler)

    # AsyncClient should be available on the package; fall back if not.
    AsyncClientClass = getattr(ollama, "AsyncClient", None)
    if AsyncClientClass is None:
        print("ollama.AsyncClient not found in package; skipping async demo.")
        return

    async_client = AsyncClientClass(host="https://ollama.com", transport=transport)

    chat_payload = {"messages": [{"role": "user", "content": "Hello from async test script"}]}

    # Try high-level async chat() if present
    if hasattr(async_client, "chat"):
        try:
            print("Attempting to call async_client.chat(...) (best-effort)...")
            try:
                resp = await async_client.chat(messages=chat_payload["messages"])  # type: ignore
            except TypeError:
                resp = await async_client.chat(chat_payload)  # type: ignore
            try:
                # Try to show JSON result if possible
                print("async_client.chat returned:", getattr(resp, "json", lambda: resp)())
            except Exception:
                print("async_client.chat result:", resp)
            return
        except Exception as e:
            print("async chat call failed (falling back):", repr(e))

    # Fallback to low-level _request_raw (awaitable)
    print("Calling low-level POST to /v1/chat (async) to demonstrate signing path...")
    try:
        resp = await async_client._request_raw("POST", "/v1/chat", json=chat_payload)  # type: ignore
        print("Async response status:", resp.status_code)
        try:
            print("Async response JSON:", resp.json())
        except Exception:
            print("Async response content:", resp.content)
    except Exception as e:
        print("Async request failed:", e)


if __name__ == "__main__":
    import asyncio

    print("=== Sync demo ===")
    run_sync_demo()

    print("\n=== Async demo ===")
    asyncio.run(run_async_demo())
