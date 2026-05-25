from __future__ import annotations

import json
from typing import Any

from .kube_api import DeleteDisabledError, KubernetesApiClient, KubernetesApiError

RESOURCE_LIST_LIMIT = 20


def compact_json(data: Any, *, compact: bool = True) -> str:
    if compact:
        return json.dumps(data, separators=(",", ":"))
    return json.dumps(data, indent=2)


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


def _clean_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    if not metadata:
        return {}

    annotations = metadata.get("annotations") or {}
    filtered_annotations = {
        key: value
        for key, value in annotations.items()
        if not key.startswith("kubectl.kubernetes.io/")
    }

    cleaned = {
        "name": metadata.get("name"),
        "namespace": metadata.get("namespace"),
        "labels": metadata.get("labels") or None,
        "annotations": filtered_annotations or None,
        "creationTimestamp": metadata.get("creationTimestamp"),
        "deletionTimestamp": metadata.get("deletionTimestamp"),
        "finalizers": metadata.get("finalizers") or None,
        "generation": metadata.get("generation"),
    }
    return {key: value for key, value in cleaned.items() if value not in (None, {}, [])}


def _summarize_conditions(conditions: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if not conditions:
        return []
    summarized: list[dict[str, Any]] = []
    for condition in conditions[:10]:
        summarized.append(
            {
                key: condition.get(key)
                for key in ("type", "status", "reason", "message", "lastTransitionTime")
                if condition.get(key) is not None
            }
        )
    return summarized


def _summarize_container(container: dict[str, Any]) -> dict[str, Any]:
    ports = []
    for port in container.get("ports") or []:
        ports.append(
            {
                key: port.get(key)
                for key in ("name", "containerPort", "protocol")
                if port.get(key) is not None
            }
        )

    return {
        key: value
        for key, value in {
            "name": container.get("name"),
            "image": container.get("image"),
            "command": container.get("command"),
            "args": container.get("args"),
            "ports": ports or None,
        }.items()
        if value not in (None, [], {})
    }


def _clean_spec(spec: dict[str, Any] | None) -> dict[str, Any] | None:
    if not spec:
        return None

    selector = spec.get("selector")
    template = spec.get("template") or {}
    template_spec = template.get("spec") or {}
    containers = [_summarize_container(container) for container in template_spec.get("containers") or []]

    cleaned = {
        "replicas": spec.get("replicas"),
        "type": spec.get("type"),
        "clusterIP": spec.get("clusterIP"),
        "externalTrafficPolicy": spec.get("externalTrafficPolicy"),
        "serviceAccountName": spec.get("serviceAccountName") or template_spec.get("serviceAccountName"),
        "selector": selector,
        "ports": spec.get("ports"),
        "rules": spec.get("rules"),
        "hosts": spec.get("hosts"),
        "schedule": spec.get("schedule"),
        "suspend": spec.get("suspend"),
        "successfulJobsHistoryLimit": spec.get("successfulJobsHistoryLimit"),
        "failedJobsHistoryLimit": spec.get("failedJobsHistoryLimit"),
        "containers": containers or None,
        "restartPolicy": template_spec.get("restartPolicy"),
    }
    cleaned = {key: value for key, value in cleaned.items() if value not in (None, [], {})}
    return cleaned or None


def _clean_status(status: dict[str, Any] | None) -> dict[str, Any] | None:
    if not status:
        return None

    cleaned = {
        "phase": status.get("phase"),
        "replicas": status.get("replicas"),
        "readyReplicas": status.get("readyReplicas"),
        "availableReplicas": status.get("availableReplicas"),
        "updatedReplicas": status.get("updatedReplicas"),
        "observedGeneration": status.get("observedGeneration"),
        "podIP": status.get("podIP"),
        "podIPs": status.get("podIPs"),
        "hostIP": status.get("hostIP"),
        "nodeName": status.get("nodeName"),
        "startTime": status.get("startTime"),
        "conditions": _summarize_conditions(status.get("conditions")),
        "loadBalancer": status.get("loadBalancer"),
    }
    cleaned = {key: value for key, value in cleaned.items() if value not in (None, [], {})}
    return cleaned or None


def simplify_kubernetes_response(result: dict[str, Any], *, list_limit: int = RESOURCE_LIST_LIMIT) -> dict[str, Any]:
    items = result.get("items")
    if isinstance(items, list):
        simplified_items = [simplify_kubernetes_response(item, list_limit=list_limit) for item in items[:list_limit]]
        names = [
            item.get("metadata", {}).get("name")
            for item in simplified_items
            if isinstance(item, dict) and item.get("metadata", {}).get("name")
        ]
        response = {
            "apiVersion": result.get("apiVersion"),
            "kind": result.get("kind"),
            "summary": {
                "count": len(items),
                "displayed": len(simplified_items),
                "remaining": max(len(items) - len(simplified_items), 0),
                "names": names,
            },
            "items": simplified_items,
        }
        metadata = _clean_metadata(result.get("metadata"))
        if metadata:
            response["metadata"] = metadata
        return response

    response = {
        "apiVersion": result.get("apiVersion"),
        "kind": result.get("kind"),
        "metadata": _clean_metadata(result.get("metadata")),
        "spec": _clean_spec(result.get("spec")),
        "status": _clean_status(result.get("status")),
    }

    if "data" in result:
        response["dataKeys"] = sorted((result.get("data") or {}).keys())
    if "stringData" in result:
        response["stringDataKeys"] = sorted((result.get("stringData") or {}).keys())
    if "type" in result and result.get("kind") == "Secret":
        response["secretType"] = result.get("type")

    if not response.get("spec") and "rules" in result:
        response["rules"] = result.get("rules")

    return {key: value for key, value in response.items() if value not in (None, {}, [])}


async def safe_request(client: KubernetesApiClient, method: str, path: str, **kwargs: Any) -> str:
    try:
        result = await client.request(method, path, **kwargs)
    except DeleteDisabledError as exc:
        return compact_json({"error": str(exc), "allow_delete": False}, compact=client._settings.compact_json)
    except (KubernetesApiError, ValueError) as exc:
        return compact_json({"error": str(exc)}, compact=client._settings.compact_json)

    return compact_json(
        simplify_kubernetes_response(result, list_limit=client._settings.resource_list_limit),
        compact=client._settings.compact_json,
    )
