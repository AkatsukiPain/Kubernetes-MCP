from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..kube_api import KubernetesApiClient
from ..models import ApplyRequest, DeleteRequest, ResourceQuery
from .common import apply_resource, delete_resource, get_resource


def register_service_tools(mcp: FastMCP, client: KubernetesApiClient) -> None:
    @mcp.tool(description="List services in a namespace, or get one service by name, using the core v1 Kubernetes API.")
    async def kube_get_service(
        namespace: str = Field(description="Target namespace, for example default."),
        name: str | None = Field(default=None, description="Optional service name. Omit it to list services."),
        label_selector: str | None = Field(default=None, description="Optional label selector, for example app=nginx."),
    ) -> str:
        return await get_resource(
            client,
            api_version="v1",
            kind_plural="services",
            namespace=namespace,
            name=name,
            label_selector=label_selector,
        )

    @mcp.tool(description="Create a service, replace a service, or patch an existing service in a namespace.")
    async def kube_apply_service(request: ApplyRequest) -> str:
        return await apply_resource(
            client,
            api_version="v1",
            kind_plural="services",
            namespace=request.namespace,
            name=request.name,
            method=request.method,
            manifest=request.manifest,
        )

    @mcp.tool(description="Delete a service in a namespace. This stays blocked unless KUBE_ALLOW_DELETE=true.")
    async def kube_delete_service(request: DeleteRequest) -> str:
        return await delete_resource(
            client,
            api_version="v1",
            kind_plural="services",
            namespace=request.namespace,
            name=request.name,
            propagation_policy=request.propagation_policy,
            grace_period_seconds=request.grace_period_seconds,
        )

    @mcp.tool(description="Generic service reader that accepts the shared ResourceQuery model for advanced filtering and consistent automation.")
    async def kube_get_service_advanced(query: ResourceQuery) -> str:
        return await get_resource(
            client,
            api_version="v1",
            kind_plural="services",
            namespace=query.namespace,
            name=query.name,
            label_selector=query.label_selector,
            field_selector=query.field_selector,
        )
