from __future__ import annotations

import json
from typing import Any, Callable

from ..helpers import build_resource_path, safe_request
from ..kube_api import DeleteDisabledError, KubernetesApiClient, KubernetesApiError

SummaryBuilder = Callable[[dict[str, Any]], dict[str, Any]]
HealthCheck = Callable[[dict[str, Any]], bool]
DetailBuilder = Callable[[dict[str, Any]], dict[str, Any]]


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


async def get_resource_summary(
    client: KubernetesApiClient,
    *,
    api_version: str,
    kind_plural: str,
    summarize_item: SummaryBuilder,
    namespace: str | None = None,
    name: str | None = None,
    label_selector: str | None = None,
    field_selector: str | None = None,
    limit: int = 100,
) -> str:
    if name and not namespace:
        return _error_response("namespace is required when name is provided for namespaced resources")

    result = await _fetch_resource(
        client,
        api_version=api_version,
        kind_plural=kind_plural,
        namespace=namespace,
        name=name,
        label_selector=label_selector,
        field_selector=field_selector,
    )
    if isinstance(result, str):
        return result

    if name:
        return json.dumps(
            {
                "apiVersion": result.get("apiVersion"),
                "kind": result.get("kind"),
                "item": summarize_item(result),
            },
            indent=2,
        )

    items = result.get("items") or []
    summaries = [summarize_item(item) for item in items[:limit]]
    return json.dumps(
        {
            "apiVersion": result.get("apiVersion"),
            "kind": result.get("kind"),
            "summary": {
                "count": len(items),
                "displayed": len(summaries),
                "remaining": max(len(items) - len(summaries), 0),
            },
            "items": summaries,
        },
        indent=2,
    )


async def get_unhealthy_resources(
    client: KubernetesApiClient,
    *,
    api_version: str,
    kind_plural: str,
    summarize_item: SummaryBuilder,
    is_unhealthy: HealthCheck,
    detail_item: DetailBuilder,
    namespace: str | None = None,
    name: str | None = None,
    label_selector: str | None = None,
    field_selector: str | None = None,
    limit: int = 50,
) -> str:
    if name and not namespace:
        return _error_response("namespace is required when name is provided for namespaced resources")

    result = await _fetch_resource(
        client,
        api_version=api_version,
        kind_plural=kind_plural,
        namespace=namespace,
        name=name,
        label_selector=label_selector,
        field_selector=field_selector,
    )
    if isinstance(result, str):
        return result

    if name:
        unhealthy = is_unhealthy(result)
        return json.dumps(
            {
                "apiVersion": result.get("apiVersion"),
                "kind": result.get("kind"),
                "healthy": not unhealthy,
                "item": detail_item(result),
            },
            indent=2,
        )

    items = result.get("items") or []
    unhealthy_items = [item for item in items if is_unhealthy(item)]
    details = [detail_item(item) for item in unhealthy_items[:limit]]
    return json.dumps(
        {
            "apiVersion": result.get("apiVersion"),
            "kind": result.get("kind"),
            "summary": {
                "count": len(items),
                "unhealthy": len(unhealthy_items),
                "displayed": len(details),
                "remaining": max(len(unhealthy_items) - len(details), 0),
            },
            "items": details,
        },
        indent=2,
    )


async def _fetch_resource(
    client: KubernetesApiClient,
    *,
    api_version: str,
    kind_plural: str,
    namespace: str | None = None,
    name: str | None = None,
    label_selector: str | None = None,
    field_selector: str | None = None,
) -> dict[str, Any] | str:
    path = resource_path(api_version=api_version, kind_plural=kind_plural, namespace=namespace, name=name)
    params = {
        key: value
        for key, value in {
            "labelSelector": label_selector,
            "fieldSelector": field_selector,
        }.items()
        if value
    }

    try:
        return await client.request("GET", path, params=params or None)
    except DeleteDisabledError as exc:
        return json.dumps({"error": str(exc), "allow_delete": False}, indent=2)
    except (KubernetesApiError, ValueError) as exc:
        return json.dumps({"error": str(exc)}, indent=2)


def _error_response(message: str) -> str:
    return json.dumps({"error": message}, indent=2)
