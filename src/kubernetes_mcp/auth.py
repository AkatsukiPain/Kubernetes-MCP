from __future__ import annotations

import base64
import binascii
import secrets
from dataclasses import dataclass
from typing import Literal

from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


@dataclass(slots=True)
class EndpointAuth:
    mode: Literal["none", "basic", "password", "api_key"] = "none"
    basic_auth: str | None = None
    password: str | None = None
    api_key: str | None = None
    api_key_header: str = "x-api-key"

    @property
    def enabled(self) -> bool:
        return self.mode != "none"


class EndpointAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: Starlette, auth: EndpointAuth):
        super().__init__(app)
        self._auth = auth

    async def dispatch(self, request: Request, call_next) -> Response:
        if not self._is_authorized(request):
            headers = {}
            if self._auth.mode == "basic":
                headers["WWW-Authenticate"] = 'Basic realm="kubernetes-mcp"'
            elif self._auth.mode == "password":
                headers["WWW-Authenticate"] = 'Bearer realm="kubernetes-mcp"'
            elif self._auth.mode == "api_key":
                headers["WWW-Authenticate"] = f'APIKey realm="kubernetes-mcp", header="{self._auth.api_key_header}"'
            return JSONResponse({"error": "Unauthorized"}, status_code=401, headers=headers)

        return await call_next(request)

    def _is_authorized(self, request: Request) -> bool:
        if not self._auth.enabled:
            return True

        authorization = request.headers.get("authorization", "")

        if self._auth.mode == "basic" and self._auth.basic_auth:
            expected = self._auth.basic_auth
            if authorization.lower().startswith("basic "):
                token = authorization.split(" ", 1)[1].strip()
                try:
                    decoded = base64.b64decode(token).decode("utf-8")
                except (binascii.Error, UnicodeDecodeError):
                    return False
                return secrets.compare_digest(decoded, expected)
            return False

        if self._auth.mode == "password" and self._auth.password:
            if authorization.lower().startswith("bearer "):
                token = authorization.split(" ", 1)[1].strip()
                return secrets.compare_digest(token, self._auth.password)
            password_header = request.headers.get("x-mcp-password", "")
            return bool(password_header) and secrets.compare_digest(password_header, self._auth.password)

        if self._auth.mode == "api_key" and self._auth.api_key:
            header_value = request.headers.get(self._auth.api_key_header, "")
            if header_value and secrets.compare_digest(header_value, self._auth.api_key):
                return True
            if authorization.lower().startswith("bearer "):
                token = authorization.split(" ", 1)[1].strip()
                return secrets.compare_digest(token, self._auth.api_key)
            return False

        return False
