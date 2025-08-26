"""
Utilities to decide whether requests should be signed and to prepare the
signed request (append ts, build challenge, sign and set Authorization).

Behavior:
 - Sign if OLLAMA_AUTH environment variable is truthy, or if base_url hostname == "ollama.com".
 - Adds ts=<unix_seconds> to the path query params for signed requests.
 - Builds challenge string used for signing as "<METHOD>,<PATH>?ts=<ts>".
"""

from __future__ import annotations

import os
import time
import urllib.parse
from typing import Dict, Optional, Tuple

from ._auth import sign_challenge

OLLAMA_AUTH_ENV = "OLLAMA_AUTH"


def _env_truthy(name: str) -> bool:
    v = os.getenv(name)
    if not v:
        return False
    return v.lower() in ("1", "true", "yes", "on")


def should_sign(base_url: str) -> bool:
    """
    Decide whether to sign outgoing requests.

    - If OLLAMA_AUTH is truthy => sign
    - Or if base_url hostname equals "ollama.com" => sign
    """
    if _env_truthy(OLLAMA_AUTH_ENV):
        return True

    try:
        parsed = urllib.parse.urlparse(base_url)
        hostname = parsed.hostname or ""
        return hostname.lower() == "ollama.com"
    except Exception:
        return False


def prepare_signed_request(
    base_url: str,
    method: str,
    path: str,
    headers: Optional[Dict[str, str]],
    key_path: Optional[str] = None,
) -> Tuple[str, Dict[str, str]]:
    """
    If signing is not required returns (path, headers) unchanged.

    If required:
      - computes ts = current unix seconds
      - appends ts to path query params
      - constructs challenge: "<METHOD>,<PATH>?ts=<ts>"
      - signs challenge and sets headers['authorization'] = token
      - returns (path_with_ts, headers_copy)

    Note: path should be a relative URL path (for example '/api/generate' or '/v1?foo=bar').
    """
    if not should_sign(base_url):
        return path, {k.lower(): v for k, v in (headers or {}).items()}

    now = str(int(time.time()))
    parsed = urllib.parse.urlparse(path)
    q = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    q["ts"] = [now]
    new_query = urllib.parse.urlencode(q, doseq=True)
    path_with_ts = urllib.parse.urlunparse(parsed._replace(query=new_query))

    # Build challenge string: use the path component and ensure '?ts=...' is present.
    # Use parsed.path to avoid including scheme/host.
    challenge = f"{method},{parsed.path}?ts={now}" if parsed.query == "" else f"{method},{parsed.path}?{new_query}"

    token = sign_challenge(challenge.encode("utf-8"), key_path=key_path)

    headers_copy = {k.lower(): v for k, v in (headers or {}).items()}
    headers_copy["authorization"] = token

    return path_with_ts, headers_copy
