from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..kube_api import KubernetesApiClient
from ..models import ApplyRequest, DeleteRequest, ResourceQuery
from .common import apply_resource, delete_resource, get_resource


def register_pod_tools(mcp: FastMCP, client: KubernetesApiClient) -> None:
    @mcp.tool(description="List pods in a namespace, or get one pod by name, using the Kubernetes API with the current RBAC identity.")
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

    @mcp.tool(description="Generic pod reader that accepts the shared ResourceQuery model for advanced filtering and consistent automation.")
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
