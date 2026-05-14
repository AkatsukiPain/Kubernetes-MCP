from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..kube_api import KubernetesApiClient
from ..models import ApplyRequest, DeleteRequest, ResourceQuery
from .common import apply_resource, delete_resource, get_resource, get_resource_summary, get_unhealthy_resources


def register_pod_tools(mcp: FastMCP, client: KubernetesApiClient) -> None:
    @mcp.tool(description="Full-detail pod reader. Prefer kube_get_pod_summary first for low-token scanning, then kube_get_unhealthy_pod when troubleshooting unhealthy pods.")
    async def kube_get_pod(
        namespace: str = Field(description="Target namespace, for example default."),
        name: str | None = Field(default=None, description="Optional pod name. Omit it to list pods."),
        label_selector: str | None = Field(default=None, description="Optional label selector, for example app=nginx."),
        field_selector: str | None = Field(default=None, description="Optional field selector, for example status.phase=Running."),
    ) -> str:
        return await get_resource(
            client,
            api_version="v1",
            kind_plural="pods",
            namespace=namespace,
            name=name,
            label_selector=label_selector,
            field_selector=field_selector,
        )

    @mcp.tool(description="Preferred first step for pod checks. Returns a compact low-token summary with readiness, normalized status, restart count, and compact reason when present.")
    async def kube_get_pod_summary(
        namespace: str = Field(description="Target namespace, for example default."),
        name: str | None = Field(default=None, description="Optional pod name. Omit it to summarize pods in the namespace."),
        label_selector: str | None = Field(default=None, description="Optional label selector, for example app=nginx."),
        field_selector: str | None = Field(default=None, description="Optional field selector, for example status.phase=Running."),
        limit: int = Field(default=100, ge=1, le=500, description="Maximum number of summarized items to return when listing."),
    ) -> str:
        return await get_resource_summary(
            client,
            api_version="v1",
            kind_plural="pods",
            namespace=namespace,
            name=name,
            label_selector=label_selector,
            field_selector=field_selector,
            limit=limit,
            summarize_item=_summarize_pod,
        )

    @mcp.tool(description="Preferred troubleshooting follow-up after kube_get_pod_summary. Returns focused diagnostics only for unhealthy pods with much lower token cost than the full reader.")
    async def kube_get_unhealthy_pod(
        namespace: str = Field(description="Target namespace, for example default."),
        name: str | None = Field(default=None, description="Optional pod name. Omit it to scan pods in the namespace."),
        label_selector: str | None = Field(default=None, description="Optional label selector, for example app=nginx."),
        field_selector: str | None = Field(default=None, description="Optional field selector, for example status.phase!=Running."),
        limit: int = Field(default=50, ge=1, le=200, description="Maximum number of unhealthy pods to return when listing."),
    ) -> str:
        return await get_unhealthy_resources(
            client,
            api_version="v1",
            kind_plural="pods",
            namespace=namespace,
            name=name,
            label_selector=label_selector,
            field_selector=field_selector,
            limit=limit,
            summarize_item=_summarize_pod,
            is_unhealthy=_is_pod_unhealthy,
            detail_item=_pod_unhealthy_detail,
        )

    @mcp.tool(description="Create a pod, replace a pod, or patch an existing pod in a namespace.")
    async def kube_apply_pod(request: ApplyRequest) -> str:
        return await apply_resource(
            client,
            api_version="v1",
            kind_plural="pods",
            namespace=request.namespace,
            name=request.name,
            method=request.method,
            manifest=request.manifest,
        )

    @mcp.tool(description="Delete a pod in a namespace. This stays blocked unless KUBE_ALLOW_DELETE=true.")
    async def kube_delete_pod(request: DeleteRequest) -> str:
        return await delete_resource(
            client,
            api_version="v1",
            kind_plural="pods",
            namespace=request.namespace,
            name=request.name,
            propagation_policy=request.propagation_policy,
            grace_period_seconds=request.grace_period_seconds,
        )

    @mcp.tool(description="Advanced full-detail pod reader for consistent automation. Prefer kube_get_pod_summary first, then kube_get_unhealthy_pod for troubleshooting.")
    async def kube_get_pod_advanced(query: ResourceQuery) -> str:
        return await get_resource(
            client,
            api_version="v1",
            kind_plural="pods",
            namespace=query.namespace,
            name=query.name,
            label_selector=query.label_selector,
            field_selector=query.field_selector,
        )


def _pod_ready(item: dict[str, Any]) -> str:
    status = item.get("status") or {}
    spec = item.get("spec") or {}
    total = len(spec.get("containers") or [])
    ready = 0
    for condition in status.get("conditions") or []:
        if condition.get("type") == "Ready" and condition.get("status") == "True":
            ready = total if total > 0 else 1
            break

    if total == 0:
        container_statuses = status.get("containerStatuses") or []
        total = len(container_statuses)
        ready = sum(1 for container in container_statuses if container.get("ready"))

    return f"{ready}/{total}" if total > 0 else "0/0"


def _pod_restart_count(status: dict[str, Any]) -> int:
    return sum(int(container.get("restartCount") or 0) for container in status.get("containerStatuses") or [])


def _pod_reason(status: dict[str, Any]) -> str | None:
    for container in status.get("containerStatuses") or []:
        state = container.get("state") or {}
        waiting = state.get("waiting") or {}
        terminated = state.get("terminated") or {}
        if waiting.get("reason"):
            return waiting.get("reason")
        if terminated.get("reason"):
            return terminated.get("reason")

    for condition in status.get("conditions") or []:
        if condition.get("type") == "PodScheduled" and condition.get("status") == "False":
            return condition.get("reason")
        if condition.get("type") == "Ready" and condition.get("status") != "True":
            return condition.get("reason")

    return None


def _pod_status(item: dict[str, Any]) -> str:
    metadata = item.get("metadata") or {}
    status = item.get("status") or {}
    phase = status.get("phase") or "Unknown"
    reason = _pod_reason(status)

    if metadata.get("deletionTimestamp"):
        return "Terminating"
    if reason in {"CrashLoopBackOff", "ImagePullBackOff", "ErrImagePull", "CreateContainerConfigError", "RunContainerError"}:
        return "Degraded"
    if phase == "Failed":
        return "Failed"
    if phase == "Pending":
        return "Pending"
    if phase == "Succeeded":
        return "Healthy"
    if phase == "Running":
        for condition in status.get("conditions") or []:
            if condition.get("type") == "Ready" and condition.get("status") != "True":
                return "Degraded"
        for container in status.get("containerStatuses") or []:
            if not container.get("ready"):
                return "Degraded"
        return "Healthy"
    return "Unknown"


def _summarize_pod(item: dict[str, Any]) -> dict[str, Any]:
    metadata = item.get("metadata") or {}
    status = item.get("status") or {}
    summary = {
        "ns": metadata.get("namespace"),
        "name": metadata.get("name"),
        "ready": _pod_ready(item),
        "status": _pod_status(item),
        "restarts": _pod_restart_count(status),
        "node": item.get("spec", {}).get("nodeName"),
    }
    reason = _pod_reason(status)
    if reason:
        summary["reason"] = reason
    return summary


def _is_pod_unhealthy(item: dict[str, Any]) -> bool:
    return _pod_status(item) != "Healthy"


def _pod_unhealthy_detail(item: dict[str, Any]) -> dict[str, Any]:
    metadata = item.get("metadata") or {}
    status = item.get("status") or {}
    containers = []
    for container in status.get("containerStatuses") or []:
        state = container.get("state") or {}
        waiting = state.get("waiting") or {}
        terminated = state.get("terminated") or {}
        running = state.get("running") or {}
        state_type = "waiting" if waiting else "terminated" if terminated else "running" if running else None
        state_detail = waiting or terminated or running
        containers.append(
            {
                "name": container.get("name"),
                "ready": container.get("ready"),
                "restarts": int(container.get("restartCount") or 0),
                "state": state_type,
                "reason": state_detail.get("reason"),
                "message": state_detail.get("message"),
            }
        )

    conditions = [
        {
            key: condition.get(key)
            for key in ("type", "status", "reason", "message", "lastTransitionTime")
            if condition.get(key) is not None
        }
        for condition in status.get("conditions") or []
        if condition.get("status") != "True" or condition.get("type") == "Ready"
    ]

    detail = {
        "ns": metadata.get("namespace"),
        "name": metadata.get("name"),
        "ready": _pod_ready(item),
        "status": _pod_status(item),
        "phase": status.get("phase"),
        "podIP": status.get("podIP"),
        "node": item.get("spec", {}).get("nodeName"),
        "conditions": conditions,
        "containers": containers,
    }
    reason = _pod_reason(status)
    if reason:
        detail["reason"] = reason
    return detail
