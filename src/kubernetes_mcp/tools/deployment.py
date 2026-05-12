from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..kube_api import KubernetesApiClient
from ..models import ApplyRequest, DeleteRequest, ResourceQuery
from .common import apply_resource, delete_resource, get_resource


def register_deployment_tools(mcp: FastMCP, client: KubernetesApiClient) -> None:
    @mcp.tool(description="List deployments in a namespace, or get one deployment by name, through the apps/v1 Kubernetes API.")
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

    @mcp.tool(description="Generic deployment reader that accepts the shared ResourceQuery model for advanced filtering and consistent automation.")
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
