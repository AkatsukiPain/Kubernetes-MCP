from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from .auth import EndpointAuth

IN_CLUSTER_TOKEN_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/token"
IN_CLUSTER_CA_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
IN_CLUSTER_NAMESPACE_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/namespace"


@dataclass(slots=True)
class TokenSource:
    kind: Literal["static", "file"]
    value: str | None = None
    path: str | None = None

    def load_token(self) -> str:
        if self.kind == "static":
            return (self.value or "").strip()

        if self.kind == "file":
            if not self.path:
                raise ValueError("Token file path is not configured")
            return Path(self.path).expanduser().read_text(encoding="utf-8").strip()

        raise ValueError(f"Unsupported token source kind: {self.kind}")


@dataclass(slots=True)
class Settings:
    kube_api_url: str
    bearer_token: str
    token_source: TokenSource = field(default_factory=lambda: TokenSource(kind="static", value=""))
    default_namespace: str = "default"
    verify_ssl: bool = True
    ca_cert_path: str | None = None
    allow_delete: bool = False
    compact_json: bool = True
    resource_list_limit: int = 20
    log_tail_lines: int = 80
    log_pod_limit: int = 3
    log_timestamps: bool = False
    host: str = "0.0.0.0"
    port: int = 8000
    transport: str = "streamable-http"
    auth_source: str = "env"
    endpoint_auth: EndpointAuth = field(default_factory=EndpointAuth)

    @classmethod
    def from_env(cls) -> "Settings":
        default_namespace = os.environ.get("KUBE_DEFAULT_NAMESPACE") or _read_text_if_exists(IN_CLUSTER_NAMESPACE_PATH) or "default"

        incluster_settings = _load_incluster(default_namespace=default_namespace)
        if incluster_settings is not None:
            incluster_settings.allow_delete = _env_truthy("KUBE_ALLOW_DELETE")
            incluster_settings.compact_json = _env_truthy("KUBE_MCP_COMPACT_JSON", default=True)
            incluster_settings.resource_list_limit = _env_int("KUBE_MCP_RESOURCE_LIST_LIMIT", 20, minimum=1)
            incluster_settings.log_tail_lines = _env_int("KUBE_MCP_LOG_TAIL_LINES", 80, minimum=1)
            incluster_settings.log_pod_limit = _env_int("KUBE_MCP_LOG_POD_LIMIT", 3, minimum=1)
            incluster_settings.log_timestamps = _env_truthy("KUBE_MCP_LOG_TIMESTAMPS")
            incluster_settings.host = os.environ.get("MCP_HOST", "0.0.0.0")
            incluster_settings.port = int(os.environ.get("MCP_PORT", "8000"))
            incluster_settings.transport = os.environ.get("MCP_TRANSPORT", "streamable-http")
            incluster_settings.endpoint_auth = _load_endpoint_auth()
            return incluster_settings

        explicit_url = os.environ.get("KUBE_API_URL", "").rstrip("/")
        explicit_token = os.environ.get("KUBE_BEARER_TOKEN", "")
        verify_ssl = os.environ.get("KUBE_VERIFY_SSL", "true").lower() not in {"0", "false", "no"}
        ca_cert_path = os.environ.get("KUBE_CA_CERT_PATH") or None

        if explicit_url and explicit_token:
            static_token = explicit_token.strip()
            return cls(
                kube_api_url=explicit_url,
                bearer_token=static_token,
                token_source=TokenSource(kind="static", value=static_token),
                default_namespace=default_namespace,
                verify_ssl=verify_ssl,
                ca_cert_path=ca_cert_path,
                allow_delete=_env_truthy("KUBE_ALLOW_DELETE"),
                compact_json=_env_truthy("KUBE_MCP_COMPACT_JSON", default=True),
                resource_list_limit=_env_int("KUBE_MCP_RESOURCE_LIST_LIMIT", 20, minimum=1),
                log_tail_lines=_env_int("KUBE_MCP_LOG_TAIL_LINES", 80, minimum=1),
                log_pod_limit=_env_int("KUBE_MCP_LOG_POD_LIMIT", 3, minimum=1),
                log_timestamps=_env_truthy("KUBE_MCP_LOG_TIMESTAMPS"),
                host=os.environ.get("MCP_HOST", "0.0.0.0"),
                port=int(os.environ.get("MCP_PORT", "8000")),
                transport=os.environ.get("MCP_TRANSPORT", "streamable-http"),
                auth_source="env",
                endpoint_auth=_load_endpoint_auth(),
            )

        raise ValueError(
            "Unable to discover Kubernetes credentials. Run inside Kubernetes with a service account, or set KUBE_API_URL and KUBE_BEARER_TOKEN."
        )


def _load_endpoint_auth() -> EndpointAuth:
    basic_auth = _load_http_secret("MCP_BASIC_AUTH", "BASIC_AUTH")
    password = _load_http_secret("MCP_PASSWORD", "PASSWORD")
    api_key = _load_http_secret("MCP_API_KEY", "API_KEY")
    api_key_header = (os.environ.get("MCP_API_KEY_HEADER", "x-api-key") or "x-api-key").strip()

    configured = [bool(basic_auth), bool(password), bool(api_key)]
    if sum(configured) > 1:
        raise ValueError("Configure only one endpoint auth mode: BASIC_AUTH, PASSWORD, or API_KEY")

    if basic_auth:
        return EndpointAuth(mode="basic", basic_auth=basic_auth)
    if password:
        return EndpointAuth(mode="password", password=password)
    if api_key:
        return EndpointAuth(mode="api_key", api_key=api_key, api_key_header=api_key_header.lower())
    return EndpointAuth()


def _load_http_secret(primary: str, fallback: str) -> str | None:
    value = os.environ.get(primary)
    if value is None:
        value = os.environ.get(fallback)
    if value is None:
        return None

    return value.rstrip("\r\n")


def _env_truthy(name: str, *, default: bool = False) -> bool:
    fallback = "true" if default else "false"
    return os.environ.get(name, fallback).lower() in {"1", "true", "yes"}


def _env_int(name: str, default: int, *, minimum: int | None = None, maximum: int | None = None) -> int:
    raw_value = os.environ.get(name)
    if raw_value is None:
        value = default
    else:
        try:
            value = int(raw_value)
        except ValueError as exc:
            raise ValueError(f"{name} must be an integer") from exc

    if minimum is not None:
        value = max(value, minimum)
    if maximum is not None:
        value = min(value, maximum)
    return value


def _read_text_if_exists(path: str) -> str | None:
    file_path = Path(path)
    if not file_path.exists():
        return None
    return file_path.read_text(encoding="utf-8").strip()


def _load_incluster(*, default_namespace: str) -> Settings | None:
    host = os.environ.get("KUBERNETES_SERVICE_HOST")
    port = os.environ.get("KUBERNETES_SERVICE_PORT", "443")
    token = _read_text_if_exists(IN_CLUSTER_TOKEN_PATH)
    if not host or not token:
        return None

    ca_path = IN_CLUSTER_CA_PATH if Path(IN_CLUSTER_CA_PATH).exists() else None
    namespace = _read_text_if_exists(IN_CLUSTER_NAMESPACE_PATH) or default_namespace
    return Settings(
        kube_api_url=f"https://{host}:{port}",
        bearer_token=token,
        token_source=TokenSource(kind="file", path=IN_CLUSTER_TOKEN_PATH),
        default_namespace=namespace,
        verify_ssl=True,
        ca_cert_path=ca_path,
        auth_source="incluster",
    )
