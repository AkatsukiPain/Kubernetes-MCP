from __future__ import annotations

import base64
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Literal

import yaml

from .auth import EndpointAuth

IN_CLUSTER_TOKEN_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/token"
IN_CLUSTER_CA_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
IN_CLUSTER_NAMESPACE_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/namespace"


@dataclass(slots=True)
class TokenSource:
    kind: Literal["static", "file", "exec"]
    value: str | None = None
    path: str | None = None
    command: list[str] | None = None
    env: dict[str, str] = field(default_factory=dict)
    api_version: str | None = None
    install_hint: str | None = None

    def load_token(self) -> str:
        if self.kind == "static":
            return (self.value or "").strip()

        if self.kind == "file":
            if not self.path:
                raise ValueError("Token file path is not configured")
            return Path(self.path).expanduser().read_text(encoding="utf-8").strip()

        if self.kind == "exec":
            if not self.command:
                raise ValueError("Exec auth command is not configured")

            env = os.environ.copy()
            env.update(self.env)
            completed = subprocess.run(
                self.command,
                capture_output=True,
                text=True,
                check=True,
                env=env,
            )
            payload = yaml.safe_load(completed.stdout) or {}
            status = payload.get("status", {})
            token = (status.get("token") or "").strip()
            if not token:
                raise ValueError("Exec auth command did not return status.token")
            return token

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
    host: str = "0.0.0.0"
    port: int = 8000
    transport: str = "streamable-http"
    auth_source: str = "env"
    endpoint_auth: EndpointAuth = field(default_factory=EndpointAuth)

    @classmethod
    def from_env(cls) -> "Settings":
        explicit_url = os.environ.get("KUBE_API_URL", "").rstrip("/")
        explicit_token = os.environ.get("KUBE_BEARER_TOKEN", "")
        verify_ssl = os.environ.get("KUBE_VERIFY_SSL", "true").lower() not in {"0", "false", "no"}
        ca_cert_path = os.environ.get("KUBE_CA_CERT_PATH") or None
        default_namespace = os.environ.get("KUBE_DEFAULT_NAMESPACE") or _read_text_if_exists(IN_CLUSTER_NAMESPACE_PATH) or "default"

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
                host=os.environ.get("MCP_HOST", "0.0.0.0"),
                port=int(os.environ.get("MCP_PORT", "8000")),
                transport=os.environ.get("MCP_TRANSPORT", "streamable-http"),
                auth_source="env",
                endpoint_auth=_load_endpoint_auth(),
            )

        kubeconfig_settings = _load_from_kubeconfig(default_namespace=default_namespace)
        if kubeconfig_settings is not None:
            kubeconfig_settings.allow_delete = _env_truthy("KUBE_ALLOW_DELETE")
            kubeconfig_settings.host = os.environ.get("MCP_HOST", "0.0.0.0")
            kubeconfig_settings.port = int(os.environ.get("MCP_PORT", "8000"))
            kubeconfig_settings.transport = os.environ.get("MCP_TRANSPORT", "streamable-http")
            kubeconfig_settings.endpoint_auth = _load_endpoint_auth()
            return kubeconfig_settings

        incluster_settings = _load_incluster(default_namespace=default_namespace)
        if incluster_settings is not None:
            incluster_settings.allow_delete = _env_truthy("KUBE_ALLOW_DELETE")
            incluster_settings.host = os.environ.get("MCP_HOST", "0.0.0.0")
            incluster_settings.port = int(os.environ.get("MCP_PORT", "8000"))
            incluster_settings.transport = os.environ.get("MCP_TRANSPORT", "streamable-http")
            incluster_settings.endpoint_auth = _load_endpoint_auth()
            return incluster_settings

        raise ValueError(
            "Unable to discover Kubernetes credentials. Set KUBE_API_URL and KUBE_BEARER_TOKEN, or provide a valid KUBECONFIG, or run inside Kubernetes with a service account."
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


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "false").lower() in {"1", "true", "yes"}


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


def _load_from_kubeconfig(*, default_namespace: str) -> Settings | None:
    kubeconfig_path = Path(os.environ.get("KUBECONFIG", Path.home() / ".kube/config")).expanduser()
    if not kubeconfig_path.exists():
        return None

    data = yaml.safe_load(kubeconfig_path.read_text(encoding="utf-8")) or {}
    current_context_name = data.get("current-context")
    contexts = {item["name"]: item.get("context", {}) for item in data.get("contexts", [])}
    clusters = {item["name"]: item.get("cluster", {}) for item in data.get("clusters", [])}
    users = {item["name"]: item.get("user", {}) for item in data.get("users", [])}

    context = contexts.get(current_context_name)
    if not context:
        return None

    cluster = clusters.get(context.get("cluster"), {})
    user = users.get(context.get("user"), {})
    server = (cluster.get("server") or "").rstrip("/")

    token_source = _load_kubeconfig_token_source(user)
    if token_source is None:
        return None
    token = token_source.load_token()

    if not server or not token:
        return None

    cert_path = None
    if cluster.get("certificate-authority"):
        candidate = Path(cluster["certificate-authority"]).expanduser()
        cert_path = str(candidate) if candidate.exists() else None
    elif cluster.get("certificate-authority-data"):
        cert_path = _write_temp_pem(base64.b64decode(cluster["certificate-authority-data"]))

    insecure_skip = bool(cluster.get("insecure-skip-tls-verify", False))
    return Settings(
        kube_api_url=server,
        bearer_token=token,
        token_source=token_source,
        default_namespace=context.get("namespace") or default_namespace,
        verify_ssl=not insecure_skip,
        ca_cert_path=cert_path,
        auth_source="kubeconfig",
    )


def _load_kubeconfig_token_source(user: dict) -> TokenSource | None:
    token = (user.get("token") or "").strip()
    if token:
        return TokenSource(kind="static", value=token)

    token_file = user.get("tokenFile")
    if token_file:
        token_path = Path(token_file).expanduser()
        if token_path.exists():
            return TokenSource(kind="file", path=str(token_path))

    exec_config = user.get("exec") or {}
    command = exec_config.get("command")
    if command:
        args = exec_config.get("args") or []
        env = {
            item.get("name"): item.get("value", "")
            for item in (exec_config.get("env") or [])
            if item.get("name")
        }
        return TokenSource(
            kind="exec",
            command=[command, *args],
            env=env,
            api_version=exec_config.get("apiVersion"),
            install_hint=exec_config.get("installHint"),
        )

    return None


def _write_temp_pem(content: bytes) -> str:
    temp = NamedTemporaryFile(mode="wb", suffix=".crt", delete=False)
    temp.write(content)
    temp.flush()
    temp.close()
    return temp.name
