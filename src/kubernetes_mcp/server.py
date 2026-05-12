from __future__ import annotations

import argparse

from mcp.server.fastmcp import FastMCP

from .config import Settings
from .kube_api import KubernetesApiClient
from .tools import register_tools


def create_mcp_server(settings: Settings | None = None) -> FastMCP:
    resolved_settings = settings or Settings.from_env()
    client = KubernetesApiClient(resolved_settings)
    mcp = FastMCP("kubernetes-mcp")
    register_tools(mcp, client)
    return mcp


def main() -> None:
    settings = Settings.from_env()
    parser = argparse.ArgumentParser(description="Kubernetes MCP server")
    parser.add_argument("--transport", default=settings.transport, choices=["stdio", "streamable-http", "sse"])
    parser.add_argument("--host", default=settings.host)
    parser.add_argument("--port", type=int, default=settings.port)
    args = parser.parse_args()

    mcp = create_mcp_server(settings)

    if args.transport == "stdio":
        mcp.run(transport="stdio")
        return

    mcp.run(transport=args.transport, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
