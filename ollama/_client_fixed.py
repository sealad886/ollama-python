# NOTE: This file shows the modified sections needed to integrate signing.
# Apply these changes into your existing ollama/_client.py (replace or merge
# the BaseClient and Client classes as appropriate). Keep the rest of the
# file (methods below Client) unchanged.
import ipaddress
import json
import os
import platform
import sys
import urllib.parse
from hashlib import sha256
from os import PathLike
from pathlib import Path
from typing import (
  Any,
  Callable,
  Dict,
  List,
  Literal,
  Mapping,
  Optional,
  Sequence,
  Type,
  TypeVar,
  Union,
  overload,
)

import anyio
from pydantic.json_schema import JsonSchemaValue

from ollama._utils import convert_function_to_tool

if sys.version_info < (3, 9):
  from typing import AsyncIterator, Iterator
else:
  from collections.abc import AsyncIterator, Iterator

from importlib import metadata

try:
  __version__ = metadata.version('ollama')
except metadata.PackageNotFoundError:
  __version__ = '0.0.0'

import httpx

from ollama._types import (
  ChatRequest,
  ChatResponse,
  CopyRequest,
  CreateRequest,
  DeleteRequest,
  EmbeddingsRequest,
  EmbeddingsResponse,
  EmbedRequest,
  EmbedResponse,
  GenerateRequest,
  GenerateResponse,
  Image,
  ListResponse,
  Message,
  Options,
  ProcessResponse,
  ProgressResponse,
  PullRequest,
  PushRequest,
  ResponseError,
  ShowRequest,
  ShowResponse,
  StatusResponse,
  Tool,
)

T = TypeVar('T')

# signing integration helper
from ._signing import prepare_signed_request

def _parse_host(host: Optional[str]) -> str:
    if not host:
        return "http://127.0.0.1:11434"
    if host.startswith("http://") or host.startswith("https://"):
        return host
    if ":" in host and not host.startswith("["):
        return f"http://{host}"
    return f"http://{host}"


class BaseClient:
    def __init__(
        self,
        client,
        host: Optional[str] = None,
        *,
        follow_redirects: bool = True,
        timeout: Any = None,
        headers: Optional[Mapping[str, str]] = None,
        **kwargs,
    ) -> None:
        base_url = _parse_host(host or None)
        # Save base_url so signing logic can inspect hostname.
        self._base_url = base_url

        self._client = client(
            base_url=base_url,
            follow_redirects=follow_redirects,
            timeout=timeout,
            headers={
                k.lower(): v
                for k, v in {
                    **(headers or {}),
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "User-Agent": f"ollama-python/{__version__} ({platform.machine()} {platform.system().lower()}) Python/{platform.python_version()}",
                }.items()
            },
            **kwargs,
        )


CONNECTION_ERROR_MESSAGE = "Failed to connect to Ollama. Please check that Ollama is downloaded, running and accessible. https://ollama.com/download"


class Client(BaseClient):
    def __init__(self, host: Optional[str] = None, **kwargs) -> None:
        super().__init__(httpx.Client, host, **kwargs)

    def _request_raw(self, *args, **kwargs):
        try:
            # Extract method and url provided to request
            method = args[0] if len(args) > 0 else kwargs.get("method")
            url = args[1] if len(args) > 1 else kwargs.get("url")

            # Intercept relative path requests and prepare signed request when needed
            if isinstance(url, str) and url.startswith("/"):
                headers = kwargs.get("headers") or {}
                path_with_ts, headers = prepare_signed_request(self._base_url, method, url, headers)
                # update args/kwargs to use the signed path and headers
                if len(args) > 1:
                    args = (args[0], path_with_ts) + args[2:]
                else:
                    kwargs["url"] = path_with_ts
                kwargs["headers"] = headers

            r = self._client.request(*args, **kwargs)
            r.raise_for_status()
            return r
        except httpx.HTTPStatusError as e:
            raise e  # preserve behavior; adapt to your project's ResponseError wrapper if needed
        except httpx.ConnectError:
            raise ConnectionError(CONNECTION_ERROR_MESSAGE) from None

    @overload
    def _request(
        self,
        cls: Type[T],
        *args,
        stream: Literal[False] = False,
        **kwargs,
    ) -> T: ...

    @overload
    def _request(
        self,
        cls: Type[T],
        *args,
        stream: Literal[True] = True,
        **kwargs,
    ) -> Iterator[T]: ...

    @overload
    def _request(
        self,
        cls: Type[T],
        *args,
        stream: bool = False,
        **kwargs,
    ) -> Union[T, Iterator[T]]: ...

    def _request(
        self,
        cls: Type[T],
        *args,
        stream: bool = False,
        **kwargs,
    ) -> Union[T, Iterator[T]]:
        if stream:

            def inner():
                with self._client.stream(*args, **kwargs) as r:
                    try:
                        r.raise_for_status()
                    except httpx.HTTPStatusError as e:
                        e.response.read()
                        raise ResponseError(e.response.text, e.response.status_code) from None

                    for line in r.iter_lines():
                        part = json.loads(line)
                        if err := part.get('error'):
                            raise ResponseError(err)
                        yield cls(**part)

            return inner()

        return cls(**self._request_raw(*args, **kwargs).json())

    # ... rest of methods would continue here but truncated for space