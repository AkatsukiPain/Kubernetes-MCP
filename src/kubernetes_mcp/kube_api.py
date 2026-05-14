from __future__ import annotations

import asyncio
import base64
import json
import time
from pathlib import Path
from typing import Any

import httpx

from .config import Settings


class KubernetesApiError(RuntimeError):
    pass


class DeleteDisabledError(PermissionError):
    pass


class KubernetesApiClient:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._refresh_lock = asyncio.Lock()
        self._token_file_mtime_ns = self._read_token_file_mtime_ns()

    def _verify_option(self) -> bool | str:
        if self._settings.verify_ssl:
            return self._settings.ca_cert_path or True
        return False

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._settings.bearer_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _read_token_file_mtime_ns(self) -> int | None:
        token_path = self._settings.token_source.path
        if self._settings.token_source.kind != "file" or not token_path:
            return None

        try:
            return Path(token_path).expanduser().stat().st_mtime_ns
        except FileNotFoundError:
            return None

    def _jwt_expiry_timestamp(self, token: str) -> int | None:
        parts = token.split(".")
        if len(parts) != 3:
            return None

        payload = parts[1]
        payload += "=" * (-len(payload) % 4)
        try:
            decoded = base64.urlsafe_b64decode(payload.encode("ascii"))
            claims = json.loads(decoded.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None

        exp = claims.get("exp")
        return int(exp) if isinstance(exp, int) else None

    def _should_refresh_file_token(self) -> bool:
        if self._settings.token_source.kind != "file":
            return False

        current_mtime_ns = self._read_token_file_mtime_ns()
        if current_mtime_ns is not None and current_mtime_ns != self._token_file_mtime_ns:
            return True

        expires_at = self._jwt_expiry_timestamp(self._settings.bearer_token)
        if expires_at is None:
            return False

        return (expires_at - int(time.time())) <= 300

    async def _maybe_refresh_bearer_token(self) -> bool:
        if not self._should_refresh_file_token():
            return False
        return await self._refresh_bearer_token(self._settings.bearer_token, force=False)

    async def _send_request(
        self,
        method: str,
        resolved_path: str,
        *,
        params: dict[str, str] | None = None,
        body: dict[str, Any] | None = None,
    ) -> httpx.Response:
        async with httpx.AsyncClient(
            base_url=self._settings.kube_api_url,
            headers=self._headers(),
            verify=self._verify_option(),
            timeout=30.0,
        ) as client:
            return await client.request(method.upper(), resolved_path, params=params, json=body)

    async def _refresh_bearer_token(self, previous_token: str, *, force: bool) -> bool:
        async with self._refresh_lock:
            if not force and self._settings.bearer_token != previous_token:
                return True

            refreshed_token = self._settings.token_source.load_token()
            if not refreshed_token:
                return False

            token_changed = refreshed_token != self._settings.bearer_token
            self._settings.bearer_token = refreshed_token
            self._token_file_mtime_ns = self._read_token_file_mtime_ns()
            return token_changed or force

    async def request(
        self,
        method: str,
        path: str,
        *,
        namespace: str | None = None,
        params: dict[str, str] | None = None,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if method.upper() == "DELETE" and not self._settings.allow_delete:
            raise DeleteDisabledError(
                "DELETE operations are disabled. Set KUBE_ALLOW_DELETE=true to enable them."
            )

        resolved_path = self._resolve_path(path=path, namespace=namespace)
        await self._maybe_refresh_bearer_token()
        previous_token = self._settings.bearer_token
        response = await self._send_request(method, resolved_path, params=params, body=body)

        if response.status_code == 401 and await self._refresh_bearer_token(previous_token, force=True):
            response = await self._send_request(method, resolved_path, params=params, body=body)

        if response.status_code >= 400:
            raise KubernetesApiError(
                f"Kubernetes API error {response.status_code} for {resolved_path}: {response.text}"
            )

        if not response.content:
            return {"status": "ok"}

        return response.json()

    def _resolve_path(self, *, path: str, namespace: str | None) -> str:
        raw_path = path.strip()
        if raw_path.startswith("http://") or raw_path.startswith("https://"):
            raise ValueError("Use API-relative paths only, not full URLs")

        if raw_path.startswith("/"):
            return raw_path

        ns = namespace or self._settings.default_namespace
        return f"/api/v1/namespaces/{ns}/{raw_path}"
