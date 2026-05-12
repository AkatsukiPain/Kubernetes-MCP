from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..kube_api import KubernetesApiClient
from ..models import ApplyRequest, DeleteRequest, ResourceQuery
from .common import apply_resource, delete_resource, get_resource


def register_namespace_tools(mcp: FastMCP, client: KubernetesApiClient) -> None:
    @mcp.tool(description="List all namespaces in the cluster, or get one namespace by name, using the core v1 Kubernetes API.")
    async def kube_get_namespace(
        name: str | None = Field(default=None, description="Optional namespace name. Omit it to list namespaces."),
        label_selector: str | None = Field(default=None, description="Optional label selector."),
    ) -> str:
        return await get_resource(
            client,
            api_version="v1",
            kind_plural="namespaces",
            name=name,
            label_selector=label_selector,
        )

    @mcp.tool(description="Create a namespace, replace a namespace, or patch an existing namespace.")
    async def kube_apply_namespace(request: ApplyRequest) -> str:
        return await apply_resource(
            client,
            api_version="v1",
            kind_plural="namespaces",
            name=request.name,
            method=request.method,
            manifest=request.manifest,
        )

    @mcp.tool(description="Delete a namespace. This stays blocked unless KUBE_ALLOW_DELETE=true.")
    async def kube_delete_namespace(request: DeleteRequest) -> str:
        return await delete_resource(
            client,
            api_version="v1",
            kind_plural="namespaces",
            name=request.name,
            propagation_policy=request.propagation_policy,
            grace_period_seconds=request.grace_period_seconds,
        )

    @mcp.tool(description="Generic namespace reader that accepts the shared ResourceQuery model for advanced filtering and consistent automation.")
    async def kube_get_namespace_advanced(query: ResourceQuery) -> str:
        return await get_resource(
            client,
            api_version="v1",
            kind_plural="namespaces",
            name=query.name,
            label_selector=query.label_selector,
            field_selector=query.field_selector,
        )
