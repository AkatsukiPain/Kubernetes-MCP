from __future__ import annotations

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

    def _verify_option(self) -> bool | str:
        if self._settings.verify_ssl:
            return self._settings.ca_cert_path or True
        return False

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
        headers = {
            "Authorization": f"Bearer {self._settings.bearer_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(
            base_url=self._settings.kube_api_url,
            headers=headers,
            verify=self._verify_option(),
            timeout=30.0,
        ) as client:
            response = await client.request(method.upper(), resolved_path, params=params, json=body)

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
