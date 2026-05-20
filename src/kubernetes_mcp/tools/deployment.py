from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..kube_api import KubernetesApiClient, KubernetesApiError
from ..models import ApplyRequest, DeleteRequest, ResourceQuery
from .common import apply_resource, delete_resource, get_resource, get_resource_summary, get_unhealthy_resources, resource_path


def register_deployment_tools(mcp: FastMCP, client: KubernetesApiClient) -> None:
    @mcp.tool(description="Full-detail deployment reader. Prefer kube_get_deployment_summary first for low-token scanning, then kube_get_unhealthy_deployment when troubleshooting unhealthy deployments.")
    async def kube_get_deployment(
        namespace: str = Field(description="Target namespace, for example default."),
        name: str | None = Field(default=None, description="Optional deployment name. Omit it to list deployments."),
        label_selector: str | None = Field(default=None, description="Optional label selector, for example app=nginx."),
    ) -> str:
        return await get_resource(
            client,
            api_version="apps/v1",
            kind_plural="deployments",
            namespace=namespace,
            name=name,
            label_selector=label_selector,
        )

    @mcp.tool(description="Preferred first step for deployment checks. Returns a compact low-token summary with readiness, normalized status, and compact reason when present.")
    async def kube_get_deployment_summary(
        namespace: str = Field(description="Target namespace, for example default."),
        name: str | None = Field(default=None, description="Optional deployment name. Omit it to summarize deployments in the namespace."),
        label_selector: str | None = Field(default=None, description="Optional label selector, for example app=nginx."),
        limit: int = Field(default=100, ge=1, le=500, description="Maximum number of summarized items to return when listing."),
    ) -> str:
        return await get_resource_summary(
            client,
            api_version="apps/v1",
            kind_plural="deployments",
            namespace=namespace,
            name=name,
            label_selector=label_selector,
            limit=limit,
            summarize_item=_summarize_deployment,
        )

    @mcp.tool(description="Preferred troubleshooting follow-up after kube_get_deployment_summary. Returns focused diagnostics only for unhealthy deployments with much lower token cost than the full reader.")
    async def kube_get_unhealthy_deployment(
        namespace: str = Field(description="Target namespace, for example default."),
        name: str | None = Field(default=None, description="Optional deployment name. Omit it to scan deployments in the namespace."),
        label_selector: str | None = Field(default=None, description="Optional label selector, for example app=nginx."),
        limit: int = Field(default=50, ge=1, le=200, description="Maximum number of unhealthy deployments to return when listing."),
    ) -> str:
        return await get_unhealthy_resources(
            client,
            api_version="apps/v1",
            kind_plural="deployments",
            namespace=namespace,
            name=name,
            label_selector=label_selector,
            limit=limit,
            summarize_item=_summarize_deployment,
            is_unhealthy=_is_deployment_unhealthy,
            detail_item=_deployment_unhealthy_detail,
        )

    @mcp.tool(description="Troubleshooting helper that resolves a deployment selector to pods and returns recent pod logs for the deployment. Use this after kube_get_deployment_summary or kube_get_unhealthy_deployment when you need application error logs.")
    async def kube_get_deployment_logs(
        namespace: str = Field(description="Target namespace, for example default."),
        name: str = Field(description="Deployment name."),
        container: str | None = Field(default=None, description="Optional container name. Omit it to collect logs from all normal containers in each matched pod."),
        tail_lines: int = Field(default=200, ge=1, le=2000, description="Maximum recent log lines to return per container."),
        since_seconds: int | None = Field(default=3600, ge=1, le=604800, description="Optional time window in seconds for each log request. Default is the last hour."),
        previous: bool = Field(default=False, description="When true, fetch logs from the previous container instance after a restart or crash."),
        pod_limit: int = Field(default=5, ge=1, le=20, description="Maximum number of matching pods to collect logs from."),
        timestamps: bool = Field(default=True, description="When true, include Kubernetes log timestamps."),
    ) -> str:
        deployment_path = resource_path(api_version="apps/v1", kind_plural="deployments", namespace=namespace, name=name)

        try:
            deployment = await client.request("GET", deployment_path)
        except (KubernetesApiError, ValueError) as exc:
            return json.dumps({"error": str(exc)}, indent=2)

        selector = _deployment_label_selector(deployment)
        if not selector:
            return json.dumps(
                {
                    "error": f"Deployment {namespace}/{name} does not expose a supported spec.selector for log collection."
                },
                indent=2,
            )

        pods_path = resource_path(api_version="v1", kind_plural="pods", namespace=namespace)
        try:
            pod_list = await client.request("GET", pods_path, params={"labelSelector": selector})
        except (KubernetesApiError, ValueError) as exc:
            return json.dumps({"error": str(exc)}, indent=2)

        pods = sorted(
            pod_list.get("items") or [],
            key=_deployment_log_pod_sort_key,
        )
        selected_pods = pods[:pod_limit]

        items = []
        for pod in selected_pods:
            metadata = pod.get("metadata") or {}
            status = pod.get("status") or {}
            pod_name = metadata.get("name")
            container_names = _target_containers(pod, requested_container=container)

            if not pod_name:
                continue

            if container and not container_names:
                items.append(
                    {
                        "pod": pod_name,
                        "phase": status.get("phase"),
                        "node": (pod.get("spec") or {}).get("nodeName"),
                        "error": f"Container {container!r} was not found in pod {pod_name}.",
                    }
                )
                continue

            pod_entry = {
                "pod": pod_name,
                "phase": status.get("phase"),
                "podIP": status.get("podIP"),
                "node": (pod.get("spec") or {}).get("nodeName"),
                "containers": [],
            }

            for container_name in container_names:
                log_params = {
                    "container": container_name,
                    "tailLines": str(tail_lines),
                }
                if since_seconds is not None:
                    log_params["sinceSeconds"] = str(since_seconds)
                if previous:
                    log_params["previous"] = "true"
                if timestamps:
                    log_params["timestamps"] = "true"

                try:
                    logs = await client.request_text(
                        "GET",
                        f"/api/v1/namespaces/{namespace}/pods/{pod_name}/log",
                        params=log_params,
                    )
                    pod_entry["containers"].append(
                        {
                            "name": container_name,
                            "logs": logs,
                        }
                    )
                except (KubernetesApiError, ValueError) as exc:
                    pod_entry["containers"].append(
                        {
                            "name": container_name,
                            "error": str(exc),
                        }
                    )

            items.append(pod_entry)

        return json.dumps(
            {
                "namespace": namespace,
                "deployment": name,
                "selector": selector,
                "summary": {
                    "podsMatched": len(pods),
                    "podsReturned": len(items),
                    "container": container,
                    "tailLines": tail_lines,
                    "sinceSeconds": since_seconds,
                    "previous": previous,
                    "timestamps": timestamps,
                },
                "items": items,
            },
            indent=2,
        )

    @mcp.tool(description="Create a deployment, replace a deployment, or patch an existing deployment in a namespace.")
    async def kube_apply_deployment(request: ApplyRequest) -> str:
        return await apply_resource(
            client,
            api_version="apps/v1",
            kind_plural="deployments",
            namespace=request.namespace,
            name=request.name,
            method=request.method,
            manifest=request.manifest,
        )

    @mcp.tool(description="Delete a deployment in a namespace. This stays blocked unless KUBE_ALLOW_DELETE=true.")
    async def kube_delete_deployment(request: DeleteRequest) -> str:
        return await delete_resource(
            client,
            api_version="apps/v1",
            kind_plural="deployments",
            namespace=request.namespace,
            name=request.name,
            propagation_policy=request.propagation_policy,
            grace_period_seconds=request.grace_period_seconds,
        )

    @mcp.tool(description="Advanced full-detail deployment reader for consistent automation. Prefer kube_get_deployment_summary first, then kube_get_unhealthy_deployment for troubleshooting.")
    async def kube_get_deployment_advanced(query: ResourceQuery) -> str:
        return await get_resource(
            client,
            api_version="apps/v1",
            kind_plural="deployments",
            namespace=query.namespace,
            name=query.name,
            label_selector=query.label_selector,
            field_selector=query.field_selector,
        )


def _deployment_ready(status: dict[str, Any], spec: dict[str, Any]) -> str:
    ready = int(status.get("readyReplicas") or 0)
    desired = int(spec.get("replicas") or 1)
    return f"{ready}/{desired}"


def _deployment_reason(status: dict[str, Any]) -> str | None:
    for condition in status.get("conditions") or []:
        if condition.get("type") == "Progressing" and condition.get("status") == "False":
            return condition.get("reason") or "ProgressDeadlineExceeded"
        if condition.get("type") == "Available" and condition.get("status") == "False":
            return condition.get("reason") or "Unavailable"
    return None


def _deployment_status(status: dict[str, Any], spec: dict[str, Any], metadata: dict[str, Any]) -> str:
    desired = int(spec.get("replicas") or 1)
    ready = int(status.get("readyReplicas") or 0)
    available = int(status.get("availableReplicas") or 0)
    updated = int(status.get("updatedReplicas") or 0)
    reason = _deployment_reason(status)

    if metadata.get("deletionTimestamp"):
        return "Terminating"
    if desired == 0:
        return "ScaledDown"
    if reason:
        return "Degraded"
    if available < desired or ready < desired or updated < desired:
        return "Progressing"
    return "Healthy"


def _summarize_deployment(item: dict[str, Any]) -> dict[str, Any]:
    metadata = item.get("metadata") or {}
    spec = item.get("spec") or {}
    status = item.get("status") or {}
    summary = {
        "ns": metadata.get("namespace"),
        "name": metadata.get("name"),
        "ready": _deployment_ready(status, spec),
        "status": _deployment_status(status, spec, metadata),
    }
    reason = _deployment_reason(status)
    if reason:
        summary["reason"] = reason
    return summary


def _is_deployment_unhealthy(item: dict[str, Any]) -> bool:
    return _summarize_deployment(item).get("status") != "Healthy"


def _deployment_unhealthy_detail(item: dict[str, Any]) -> dict[str, Any]:
    metadata = item.get("metadata") or {}
    spec = item.get("spec") or {}
    status = item.get("status") or {}
    conditions = []
    for condition in status.get("conditions") or []:
        if condition.get("status") != "True" or condition.get("type") in {"Progressing", "Available"}:
            conditions.append(
                {
                    key: condition.get(key)
                    for key in ("type", "status", "reason", "message", "lastUpdateTime", "lastTransitionTime")
                    if condition.get(key) is not None
                }
            )

    detail = {
        "ns": metadata.get("namespace"),
        "name": metadata.get("name"),
        "ready": _deployment_ready(status, spec),
        "status": _deployment_status(status, spec, metadata),
        "replicas": {
            "desired": int(spec.get("replicas") or 1),
            "updated": int(status.get("updatedReplicas") or 0),
            "ready": int(status.get("readyReplicas") or 0),
            "available": int(status.get("availableReplicas") or 0),
            "unavailable": int(status.get("unavailableReplicas") or 0),
        },
        "conditions": conditions,
    }
    reason = _deployment_reason(status)
    if reason:
        detail["reason"] = reason
    return detail


def _deployment_label_selector(item: dict[str, Any]) -> str | None:
    selector = ((item.get("spec") or {}).get("selector") or {})
    parts: list[str] = []

    for key, value in sorted((selector.get("matchLabels") or {}).items()):
        parts.append(f"{key}={value}")

    for expression in selector.get("matchExpressions") or []:
        operator = expression.get("operator")
        key = expression.get("key")
        values = expression.get("values") or []
        if not key or not operator:
            continue
        if operator == "In" and values:
            parts.append(f"{key} in ({','.join(values)})")
        elif operator == "NotIn" and values:
            parts.append(f"{key} notin ({','.join(values)})")
        elif operator == "Exists":
            parts.append(key)
        elif operator == "DoesNotExist":
            parts.append(f"!{key}")

    return ",".join(parts) or None


def _deployment_log_pod_sort_key(item: dict[str, Any]) -> tuple[int, int, int, str]:
    metadata = item.get("metadata") or {}
    status = item.get("status") or {}
    phase = status.get("phase") or "Unknown"
    conditions = status.get("conditions") or []
    container_statuses = status.get("containerStatuses") or []

    ready_condition = next((condition for condition in conditions if condition.get("type") == "Ready"), None)
    is_ready = ready_condition is not None and ready_condition.get("status") == "True"
    restart_count = sum(int(container.get("restartCount") or 0) for container in container_statuses)
    has_waiting_or_terminated = any(
        (container.get("state") or {}).get("waiting") or (container.get("state") or {}).get("terminated")
        for container in container_statuses
    )
    is_healthy_phase = phase in {"Running", "Succeeded"}
    creation_timestamp = metadata.get("creationTimestamp") or ""

    unhealthy_rank = 0 if (not is_ready or not is_healthy_phase or has_waiting_or_terminated or restart_count > 0) else 1
    ready_rank = 0 if not is_ready else 1

    return (unhealthy_rank, ready_rank, -restart_count, creation_timestamp)


def _target_containers(pod: dict[str, Any], requested_container: str | None) -> list[str]:
    containers = [
        container.get("name")
        for container in ((pod.get("spec") or {}).get("containers") or [])
        if container.get("name")
    ]
    if requested_container:
        return [name for name in containers if name == requested_container]
    return containers
