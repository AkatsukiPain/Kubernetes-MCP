from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..kube_api import KubernetesApiClient
from ..models import ApplyRequest, DeleteRequest, ResourceQuery
from .common import apply_resource, delete_resource, get_resource


def register_node_tools(mcp: FastMCP, client: KubernetesApiClient) -> None:
    @mcp.tool(description="List all nodes in the cluster, or get one node by name, using the core v1 Kubernetes API.")
    async def kube_get_node(
        name: str | None = Field(default=None, description="Optional node name. Omit it to list nodes."),
        label_selector: str | None = Field(default=None, description="Optional label selector."),
        field_selector: str | None = Field(default=None, description="Optional field selector."),
    ) -> str:
        return await get_resource(
            client,
            api_version="v1",
            kind_plural="nodes",
            name=name,
            label_selector=label_selector,
            field_selector=field_selector,
        )

    @mcp.tool(description="Create a node object, replace a node object, or patch an existing node object.")
    async def kube_apply_node(request: ApplyRequest) -> str:
        return await apply_resource(
            client,
            api_version="v1",
            kind_plural="nodes",
            name=request.name,
            method=request.method,
            manifest=request.manifest,
        )

    @mcp.tool(description="Delete a node object. This stays blocked unless KUBE_ALLOW_DELETE=true.")
    async def kube_delete_node(request: DeleteRequest) -> str:
        return await delete_resource(
            client,
            api_version="v1",
            kind_plural="nodes",
            name=request.name,
            propagation_policy=request.propagation_policy,
            grace_period_seconds=request.grace_period_seconds,
        )

    @mcp.tool(description="Generic node reader that accepts the shared ResourceQuery model for advanced filtering and consistent automation.")
    async def kube_get_node_advanced(query: ResourceQuery) -> str:
        return await get_resource(
            client,
            api_version="v1",
            kind_plural="nodes",
            name=query.name,
            label_selector=query.label_selector,
            field_selector=query.field_selector,
        )
