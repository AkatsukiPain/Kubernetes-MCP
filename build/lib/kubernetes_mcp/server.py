from __future__ import annotations

import argparse

from mcp.server.fastmcp import FastMCP

from .auth import EndpointAuthMiddleware
from .config import Settings
from .kube_api import KubernetesApiClient
from .tools import register_tools


def create_mcp_server(settings: Settings | None = None) -> FastMCP:
    resolved_settings = settings or Settings.from_env()
    client = KubernetesApiClient(resolved_settings)
    mcp = FastMCP(
        "kubernetes-mcp",
        host=resolved_settings.host,
        port=resolved_settings.port,
    )
    register_tools(mcp, client)
    return mcp


def create_http_app(mcp: FastMCP, settings: Settings, transport: str):
    if transport == "streamable-http":
        app = mcp.streamable_http_app()
    elif transport == "sse":
        app = mcp.sse_app()
    else:
        raise ValueError(f"Unsupported HTTP transport: {transport}")

    if settings.endpoint_auth.enabled:
        app.add_middleware(EndpointAuthMiddleware, auth=settings.endpoint_auth)
    return app


def main() -> None:
    settings = Settings.from_env()
    parser = argparse.ArgumentParser(description="Kubernetes MCP server")
    parser.add_argument("--transport", default=settings.transport, choices=["stdio", "streamable-http", "sse"])
    parser.add_argument("--host", default=settings.host)
    parser.add_argument("--port", type=int, default=settings.port)
    args = parser.parse_args()

    settings.host = args.host
    settings.port = args.port
    settings.transport = args.transport

    mcp = create_mcp_server(settings)

    if args.transport == "stdio":
        mcp.run(transport="stdio")
        return

    import uvicorn

    app = create_http_app(mcp, settings, args.transport)
    config = uvicorn.Config(app, host=args.host, port=args.port, log_level="info")
    server = uvicorn.Server(config)
    server.run()


if __name__ == "__main__":
    main()
