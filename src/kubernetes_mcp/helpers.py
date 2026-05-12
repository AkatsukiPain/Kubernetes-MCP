from __future__ import annotations

import json
from typing import Any

from .kube_api import DeleteDisabledError, KubernetesApiClient, KubernetesApiError


def build_resource_path(api_version: str, kind_plural: str, namespace: str | None, name: str | None) -> str:
    if "/" in api_version:
        group, version = api_version.split("/", 1)
        base = f"/apis/{group}/{version}"
    else:
        base = f"/api/{api_version}"

    if namespace:
        base = f"{base}/namespaces/{namespace}"

    path = f"{base}/{kind_plural}"
    if name:
        path = f"{path}/{name}"
    return path


async def safe_request(client: KubernetesApiClient, method: str, path: str, **kwargs: Any) -> str:
    try:
        result = await client.request(method, path, **kwargs)
    except DeleteDisabledError as exc:
        return json.dumps({"error": str(exc), "allow_delete": False}, indent=2)
    except (KubernetesApiError, ValueError) as exc:
        return json.dumps({"error": str(exc)}, indent=2)

    return json.dumps(result, indent=2)
