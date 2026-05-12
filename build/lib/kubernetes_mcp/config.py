from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile

import yaml

IN_CLUSTER_TOKEN_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/token"
IN_CLUSTER_CA_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
IN_CLUSTER_NAMESPACE_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/namespace"


@dataclass(slots=True)
class Settings:
    kube_api_url: str
    bearer_token: str
    default_namespace: str = "default"
    verify_ssl: bool = True
    ca_cert_path: str | None = None
    allow_delete: bool = False
    host: str = "0.0.0.0"
    port: int = 8000
    transport: str = "streamable-http"
    auth_source: str = "env"

    @classmethod
    def from_env(cls) -> "Settings":
        explicit_url = os.environ.get("KUBE_API_URL", "").rstrip("/")
        explicit_token = os.environ.get("KUBE_BEARER_TOKEN", "")
        verify_ssl = os.environ.get("KUBE_VERIFY_SSL", "true").lower() not in {"0", "false", "no"}
        ca_cert_path = os.environ.get("KUBE_CA_CERT_PATH") or None
        default_namespace = os.environ.get("KUBE_DEFAULT_NAMESPACE") or _read_text_if_exists(IN_CLUSTER_NAMESPACE_PATH) or "default"

        if explicit_url and explicit_token:
            return cls(
                kube_api_url=explicit_url,
                bearer_token=explicit_token,
                default_namespace=default_namespace,
                verify_ssl=verify_ssl,
                ca_cert_path=ca_cert_path,
                allow_delete=_env_truthy("KUBE_ALLOW_DELETE"),
                host=os.environ.get("MCP_HOST", "0.0.0.0"),
                port=int(os.environ.get("MCP_PORT", "8000")),
                transport=os.environ.get("MCP_TRANSPORT", "streamable-http"),
                auth_source="env",
            )

        kubeconfig_settings = _load_from_kubeconfig(default_namespace=default_namespace)
        if kubeconfig_settings is not None:
            kubeconfig_settings.allow_delete = _env_truthy("KUBE_ALLOW_DELETE")
            kubeconfig_settings.host = os.environ.get("MCP_HOST", "0.0.0.0")
            kubeconfig_settings.port = int(os.environ.get("MCP_PORT", "8000"))
            kubeconfig_settings.transport = os.environ.get("MCP_TRANSPORT", "streamable-http")
            return kubeconfig_settings

        incluster_settings = _load_incluster(default_namespace=default_namespace)
        if incluster_settings is not None:
            incluster_settings.allow_delete = _env_truthy("KUBE_ALLOW_DELETE")
            incluster_settings.host = os.environ.get("MCP_HOST", "0.0.0.0")
            incluster_settings.port = int(os.environ.get("MCP_PORT", "8000"))
            incluster_settings.transport = os.environ.get("MCP_TRANSPORT", "streamable-http")
            return incluster_settings

        raise ValueError(
            "Unable to discover Kubernetes credentials. Set KUBE_API_URL and KUBE_BEARER_TOKEN, or provide a valid KUBECONFIG, or run inside Kubernetes with a service account."
        )


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
    token = user.get("token")
    if not token and user.get("tokenFile"):
        token_path = Path(user["tokenFile"]).expanduser()
        if token_path.exists():
            token = token_path.read_text(encoding="utf-8").strip()

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
        default_namespace=context.get("namespace") or default_namespace,
        verify_ssl=not insecure_skip,
        ca_cert_path=cert_path,
        auth_source="kubeconfig",
    )


def _write_temp_pem(content: bytes) -> str:
    temp = NamedTemporaryFile(mode="wb", suffix=".crt", delete=False)
    temp.write(content)
    temp.flush()
    temp.close()
    return temp.name
