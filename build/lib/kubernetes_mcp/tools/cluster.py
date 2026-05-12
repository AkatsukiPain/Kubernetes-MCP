from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..helpers import safe_request
from ..kube_api import KubernetesApiClient


def register_cluster_tools(mcp: FastMCP, client: KubernetesApiClient) -> None:
    @mcp.tool(description="Check Kubernetes API health and confirm the current RBAC identity can reach the cluster.")
    async def kube_health() -> str:
        return await safe_request(client, "GET", "/version")

    @mcp.tool(description="Read the Kubernetes API discovery document for core APIs.")
    async def kube_get_core_api_versions() -> str:
        return await safe_request(client, "GET", "/api")

    @mcp.tool(description="Read the Kubernetes API discovery document for grouped APIs.")
    async def kube_get_grouped_api_versions() -> str:
        return await safe_request(client, "GET", "/apis")
