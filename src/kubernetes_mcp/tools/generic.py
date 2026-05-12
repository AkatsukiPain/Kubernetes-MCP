from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..helpers import build_resource_path, safe_request
from ..kube_api import KubernetesApiClient
from ..models import ApplyRequest, DeleteRequest, RawRequest, ResourceQuery


def register_generic_tools(mcp: FastMCP, client: KubernetesApiClient) -> None:
    @mcp.tool(description="Read any Kubernetes resource by apiVersion and plural kind name. Use this when there is no dedicated tool file for that resource type.")
    async def kube_get_resource(query: ResourceQuery) -> str:
        path = build_resource_path(
            api_version=query.api_version,
            kind_plural=query.kind_plural,
            namespace=query.namespace,
            name=query.name,
        )
        params = {
            key: value
            for key, value in {
                "labelSelector": query.label_selector,
                "fieldSelector": query.field_selector,
            }.items()
            if value
        }
        return await safe_request(client, "GET", path, params=params or None)

    @mcp.tool(description="Create, replace, or patch any Kubernetes resource by apiVersion and plural kind name.")
    async def kube_apply_resource(request: ApplyRequest) -> str:
        path = build_resource_path(
            api_version=request.api_version,
            kind_plural=request.kind_plural,
            namespace=request.namespace,
            name=request.name,
        )
        return await safe_request(client, request.method, path, body=request.manifest)

    @mcp.tool(description="Delete any Kubernetes resource by apiVersion and plural kind name. This stays blocked unless KUBE_ALLOW_DELETE=true.")
    async def kube_delete_resource(request: DeleteRequest) -> str:
        path = build_resource_path(
            api_version=request.api_version,
            kind_plural=request.kind_plural,
            namespace=request.namespace,
            name=request.name,
        )
        body = {
            key: value
            for key, value in {
                "propagationPolicy": request.propagation_policy,
                "gracePeriodSeconds": request.grace_period_seconds,
            }.items()
            if value is not None
        } or None
        return await safe_request(client, "DELETE", path, body=body)

    @mcp.tool(description="Send a raw Kubernetes API request with an API-relative path for advanced cases that need full control.")
    async def kube_raw_request(request: RawRequest) -> str:
        return await safe_request(
            client,
            request.method,
            request.path,
            namespace=request.namespace,
            params=request.params,
            body=request.body,
        )
