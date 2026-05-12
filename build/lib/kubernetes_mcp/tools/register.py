from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..kube_api import KubernetesApiClient
from .cluster import register_cluster_tools
from .configmap import register_configmap_tools
from .deployment import register_deployment_tools
from .generic import register_generic_tools
from .ingress import register_ingress_tools
from .job import register_job_tools
from .namespace import register_namespace_tools
from .node import register_node_tools
from .pod import register_pod_tools
from .secret import register_secret_tools
from .service import register_service_tools


def register_tools(mcp: FastMCP, client: KubernetesApiClient) -> None:
    register_cluster_tools(mcp, client)
    register_namespace_tools(mcp, client)
    register_node_tools(mcp, client)
    register_pod_tools(mcp, client)
    register_deployment_tools(mcp, client)
    register_service_tools(mcp, client)
    register_configmap_tools(mcp, client)
    register_secret_tools(mcp, client)
    register_job_tools(mcp, client)
    register_ingress_tools(mcp, client)
    register_generic_tools(mcp, client)
