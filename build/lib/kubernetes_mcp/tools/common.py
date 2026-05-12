from __future__ import annotations

from ..helpers import build_resource_path, safe_request
from ..kube_api import KubernetesApiClient


def resource_path(api_version: str, kind_plural: str, namespace: str | None = None, name: str | None = None) -> str:
    return build_resource_path(api_version=api_version, kind_plural=kind_plural, namespace=namespace, name=name)


async def get_resource(
    client: KubernetesApiClient,
    *,
    api_version: str,
    kind_plural: str,
    namespace: str | None = None,
    name: str | None = None,
    label_selector: str | None = None,
    field_selector: str | None = None,
) -> str:
    path = resource_path(api_version=api_version, kind_plural=kind_plural, namespace=namespace, name=name)
    params = {
        key: value
        for key, value in {
            "labelSelector": label_selector,
            "fieldSelector": field_selector,
        }.items()
        if value
    }
    return await safe_request(client, "GET", path, params=params or None)


async def apply_resource(
    client: KubernetesApiClient,
    *,
    api_version: str,
    kind_plural: str,
    method: str,
    manifest: dict,
    namespace: str | None = None,
    name: str | None = None,
) -> str:
    path = resource_path(api_version=api_version, kind_plural=kind_plural, namespace=namespace, name=name)
    return await safe_request(client, method, path, body=manifest)


async def delete_resource(
    client: KubernetesApiClient,
    *,
    api_version: str,
    kind_plural: str,
    name: str,
    namespace: str | None = None,
    propagation_policy: str | None = None,
    grace_period_seconds: int | None = None,
) -> str:
    path = resource_path(api_version=api_version, kind_plural=kind_plural, namespace=namespace, name=name)
    body = {
        key: value
        for key, value in {
            "propagationPolicy": propagation_policy,
            "gracePeriodSeconds": grace_period_seconds,
        }.items()
        if value is not None
    } or None
    return await safe_request(client, "DELETE", path, body=body)
