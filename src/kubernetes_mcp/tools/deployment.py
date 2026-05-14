from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..kube_api import KubernetesApiClient
from ..models import ApplyRequest, DeleteRequest, ResourceQuery
from .common import apply_resource, delete_resource, get_resource, get_resource_summary, get_unhealthy_resources


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
