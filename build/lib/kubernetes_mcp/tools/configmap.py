from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..kube_api import KubernetesApiClient
from ..models import ApplyRequest, DeleteRequest, ResourceQuery
from .common import apply_resource, delete_resource, get_resource


def register_configmap_tools(mcp: FastMCP, client: KubernetesApiClient) -> None:
    @mcp.tool(description="List configmaps in a namespace, or get one configmap by name, using the core v1 Kubernetes API.")
    async def kube_get_configmap(
        namespace: str = Field(description="Target namespace, for example default."),
        name: str | None = Field(default=None, description="Optional configmap name. Omit it to list configmaps."),
        label_selector: str | None = Field(default=None, description="Optional label selector."),
    ) -> str:
        return await get_resource(
            client,
            api_version="v1",
            kind_plural="configmaps",
            namespace=namespace,
            name=name,
            label_selector=label_selector,
        )

    @mcp.tool(description="Create a configmap, replace a configmap, or patch an existing configmap in a namespace.")
    async def kube_apply_configmap(request: ApplyRequest) -> str:
        return await apply_resource(
            client,
            api_version="v1",
            kind_plural="configmaps",
            namespace=request.namespace,
            name=request.name,
            method=request.method,
            manifest=request.manifest,
        )

    @mcp.tool(description="Delete a configmap in a namespace. This stays blocked unless KUBE_ALLOW_DELETE=true.")
    async def kube_delete_configmap(request: DeleteRequest) -> str:
        return await delete_resource(
            client,
            api_version="v1",
            kind_plural="configmaps",
            namespace=request.namespace,
            name=request.name,
            propagation_policy=request.propagation_policy,
            grace_period_seconds=request.grace_period_seconds,
        )

    @mcp.tool(description="Generic configmap reader that accepts the shared ResourceQuery model for advanced filtering and consistent automation.")
    async def kube_get_configmap_advanced(query: ResourceQuery) -> str:
        return await get_resource(
            client,
            api_version="v1",
            kind_plural="configmaps",
            namespace=query.namespace,
            name=query.name,
            label_selector=query.label_selector,
            field_selector=query.field_selector,
        )
