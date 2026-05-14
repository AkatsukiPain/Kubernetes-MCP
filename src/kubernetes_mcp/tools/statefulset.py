from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..kube_api import KubernetesApiClient
from ..models import ApplyRequest, DeleteRequest, ResourceQuery
from .common import apply_resource, delete_resource, get_resource, get_resource_summary, get_unhealthy_resources


def register_statefulset_tools(mcp: FastMCP, client: KubernetesApiClient) -> None:
    @mcp.tool(description="Full-detail statefulset reader. Prefer kube_get_statefulset_summary first for low-token scanning, then kube_get_unhealthy_statefulset when troubleshooting unhealthy statefulsets.")
    async def kube_get_statefulset(
        namespace: str = Field(description="Target namespace, for example default."),
        name: str | None = Field(default=None, description="Optional statefulset name. Omit it to list statefulsets."),
        label_selector: str | None = Field(default=None, description="Optional label selector."),
    ) -> str:
        return await get_resource(
            client,
            api_version="apps/v1",
            kind_plural="statefulsets",
            namespace=namespace,
            name=name,
            label_selector=label_selector,
        )

    @mcp.tool(description="Preferred first step for statefulset checks. Returns a compact low-token summary with readiness, normalized status, and compact reason when present.")
    async def kube_get_statefulset_summary(
        namespace: str = Field(description="Target namespace, for example default."),
        name: str | None = Field(default=None, description="Optional statefulset name. Omit it to summarize statefulsets in the namespace."),
        label_selector: str | None = Field(default=None, description="Optional label selector."),
        limit: int = Field(default=100, ge=1, le=500, description="Maximum number of summarized items to return when listing."),
    ) -> str:
        return await get_resource_summary(
            client,
            api_version="apps/v1",
            kind_plural="statefulsets",
            namespace=namespace,
            name=name,
            label_selector=label_selector,
            limit=limit,
            summarize_item=_summarize_statefulset,
        )

    @mcp.tool(description="Preferred troubleshooting follow-up after kube_get_statefulset_summary. Returns focused diagnostics only for unhealthy statefulsets with much lower token cost than the full reader.")
    async def kube_get_unhealthy_statefulset(
        namespace: str = Field(description="Target namespace, for example default."),
        name: str | None = Field(default=None, description="Optional statefulset name. Omit it to scan statefulsets in the namespace."),
        label_selector: str | None = Field(default=None, description="Optional label selector."),
        limit: int = Field(default=50, ge=1, le=200, description="Maximum number of unhealthy statefulsets to return when listing."),
    ) -> str:
        return await get_unhealthy_resources(
            client,
            api_version="apps/v1",
            kind_plural="statefulsets",
            namespace=namespace,
            name=name,
            label_selector=label_selector,
            limit=limit,
            summarize_item=_summarize_statefulset,
            is_unhealthy=_is_statefulset_unhealthy,
            detail_item=_statefulset_unhealthy_detail,
        )

    @mcp.tool(description="Create a statefulset, replace a statefulset, or patch an existing statefulset in a namespace.")
    async def kube_apply_statefulset(request: ApplyRequest) -> str:
        return await apply_resource(
            client,
            api_version="apps/v1",
            kind_plural="statefulsets",
            namespace=request.namespace,
            name=request.name,
            method=request.method,
            manifest=request.manifest,
        )

    @mcp.tool(description="Delete a statefulset in a namespace. This stays blocked unless KUBE_ALLOW_DELETE=true.")
    async def kube_delete_statefulset(request: DeleteRequest) -> str:
        return await delete_resource(
            client,
            api_version="apps/v1",
            kind_plural="statefulsets",
            namespace=request.namespace,
            name=request.name,
            propagation_policy=request.propagation_policy,
            grace_period_seconds=request.grace_period_seconds,
        )

    @mcp.tool(description="Advanced full-detail statefulset reader for consistent automation. Prefer kube_get_statefulset_summary first, then kube_get_unhealthy_statefulset for troubleshooting.")
    async def kube_get_statefulset_advanced(query: ResourceQuery) -> str:
        return await get_resource(
            client,
            api_version="apps/v1",
            kind_plural="statefulsets",
            namespace=query.namespace,
            name=query.name,
            label_selector=query.label_selector,
            field_selector=query.field_selector,
        )


def _statefulset_ready(status: dict[str, Any], spec: dict[str, Any]) -> str:
    ready = int(status.get("readyReplicas") or 0)
    desired = int(spec.get("replicas") or 1)
    return f"{ready}/{desired}"


def _statefulset_reason(status: dict[str, Any]) -> str | None:
    for condition in status.get("conditions") or []:
        if condition.get("status") == "False":
            return condition.get("reason") or condition.get("type")
    return None


def _statefulset_status(status: dict[str, Any], spec: dict[str, Any], metadata: dict[str, Any]) -> str:
    desired = int(spec.get("replicas") or 1)
    ready = int(status.get("readyReplicas") or 0)
    updated = int(status.get("updatedReplicas") or 0)
    reason = _statefulset_reason(status)

    if metadata.get("deletionTimestamp"):
        return "Terminating"
    if desired == 0:
        return "ScaledDown"
    if reason:
        return "Degraded"
    if ready < desired or updated < desired:
        return "Progressing"
    return "Healthy"


def _summarize_statefulset(item: dict[str, Any]) -> dict[str, Any]:
    metadata = item.get("metadata") or {}
    spec = item.get("spec") or {}
    status = item.get("status") or {}
    summary = {
        "ns": metadata.get("namespace"),
        "name": metadata.get("name"),
        "ready": _statefulset_ready(status, spec),
        "status": _statefulset_status(status, spec, metadata),
    }
    reason = _statefulset_reason(status)
    if reason:
        summary["reason"] = reason
    return summary


def _is_statefulset_unhealthy(item: dict[str, Any]) -> bool:
    return _summarize_statefulset(item).get("status") != "Healthy"


def _statefulset_unhealthy_detail(item: dict[str, Any]) -> dict[str, Any]:
    metadata = item.get("metadata") or {}
    spec = item.get("spec") or {}
    status = item.get("status") or {}
    conditions = [
        {
            key: condition.get(key)
            for key in ("type", "status", "reason", "message", "lastTransitionTime")
            if condition.get(key) is not None
        }
        for condition in status.get("conditions") or []
        if condition.get("status") != "True"
    ]

    detail = {
        "ns": metadata.get("namespace"),
        "name": metadata.get("name"),
        "ready": _statefulset_ready(status, spec),
        "status": _statefulset_status(status, spec, metadata),
        "replicas": {
            "desired": int(spec.get("replicas") or 1),
            "ready": int(status.get("readyReplicas") or 0),
            "current": int(status.get("currentReplicas") or 0),
            "updated": int(status.get("updatedReplicas") or 0),
        },
        "currentRevision": status.get("currentRevision"),
        "updateRevision": status.get("updateRevision"),
        "conditions": conditions,
    }
    reason = _statefulset_reason(status)
    if reason:
        detail["reason"] = reason
    return detail
