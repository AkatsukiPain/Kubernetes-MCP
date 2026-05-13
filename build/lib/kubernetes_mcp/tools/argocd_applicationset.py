from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..kube_api import KubernetesApiClient
from ..models import ApplyRequest, DeleteRequest, ResourceQuery
from .common import apply_resource, delete_resource, get_resource

ARGOCD_API_VERSION = "argoproj.io/v1alpha1"
ARGOCD_APPLICATIONSETS = "applicationsets"


def register_argocd_applicationset_tools(mcp: FastMCP, client: KubernetesApiClient) -> None:
    @mcp.tool(description="List Argo CD ApplicationSets in a namespace, or get one ApplicationSet by name, using the argoproj.io/v1alpha1 CRD API.")
    async def kube_get_argocd_applicationset(
        namespace: str = Field(description="Target namespace, usually argocd."),
        name: str | None = Field(default=None, description="Optional Argo CD ApplicationSet name. Omit it to list ApplicationSets."),
        label_selector: str | None = Field(default=None, description="Optional label selector."),
        field_selector: str | None = Field(default=None, description="Optional field selector."),
    ) -> str:
        return await get_resource(
            client,
            api_version=ARGOCD_API_VERSION,
            kind_plural=ARGOCD_APPLICATIONSETS,
            namespace=namespace,
            name=name,
            label_selector=label_selector,
            field_selector=field_selector,
        )

    @mcp.tool(description="Create an Argo CD ApplicationSet, replace it, or patch an existing ApplicationSet in a namespace.")
    async def kube_apply_argocd_applicationset(request: ApplyRequest) -> str:
        return await apply_resource(
            client,
            api_version=ARGOCD_API_VERSION,
            kind_plural=ARGOCD_APPLICATIONSETS,
            namespace=request.namespace,
            name=request.name,
            method=request.method,
            manifest=request.manifest,
        )

    @mcp.tool(description="Delete an Argo CD ApplicationSet in a namespace. This stays blocked unless KUBE_ALLOW_DELETE=true.")
    async def kube_delete_argocd_applicationset(request: DeleteRequest) -> str:
        return await delete_resource(
            client,
            api_version=ARGOCD_API_VERSION,
            kind_plural=ARGOCD_APPLICATIONSETS,
            namespace=request.namespace,
            name=request.name,
            propagation_policy=request.propagation_policy,
            grace_period_seconds=request.grace_period_seconds,
        )

    @mcp.tool(description="Generic Argo CD ApplicationSet reader that accepts the shared ResourceQuery model for advanced filtering and consistent automation.")
    async def kube_get_argocd_applicationset_advanced(query: ResourceQuery) -> str:
        return await get_resource(
            client,
            api_version=ARGOCD_API_VERSION,
            kind_plural=ARGOCD_APPLICATIONSETS,
            namespace=query.namespace,
            name=query.name,
            label_selector=query.label_selector,
            field_selector=query.field_selector,
        )
