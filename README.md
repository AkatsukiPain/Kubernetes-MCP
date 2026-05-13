# Kubernetes MCP

A Python MCP server that talks directly to the Kubernetes API using an RBAC-backed bearer token.

## What this project includes

- Direct Kubernetes API calls with `httpx`
- MCP tools organized under a single `tools/` package
- Resource-grouped tool files such as `pod.py`, `deployment.py`, `service.py`, and `namespace.py`
- Clear per-tool descriptions so MCP clients can present the tools cleanly
- MCP tools for health checks, reads, apply/update, delete, and raw requests
- Simplified Kubernetes responses so agents see concise summaries instead of full raw API payloads
- Delete guardrail controlled by `KUBE_ALLOW_DELETE`
- Kubernetes auth auto-discovery from `KUBECONFIG` or in-cluster service account
- Optional explicit env-var override for endpoint and bearer token
- Optional auth on the exposed MCP HTTP endpoint
- Custom host, port, and transport settings

## Project layout

```text
Kubernetes MCP/
├── .env.example
├── examples/
│   ├── rbac-editor-with-delete.yaml
│   └── rbac-reader.yaml
├── pyproject.toml
├── README.md
└── src/kubernetes_mcp/
    ├── __init__.py
    ├── __main__.py
    ├── config.py
    ├── helpers.py
    ├── kube_api.py
    ├── models.py
    ├── server.py
    └── tools/
        ├── __init__.py
        ├── cluster.py
        ├── common.py
        ├── configmap.py
        ├── deployment.py
        ├── generic.py
        ├── ingress.py
        ├── job.py
        ├── namespace.py
        ├── node.py
        ├── pod.py
        ├── register.py
        ├── secret.py
        └── service.py
```

## Requirements

- Python 3.12+
- Kubernetes credentials from one of these sources:
  - `KUBECONFIG`
  - in-cluster service account when running inside Kubernetes
  - explicit `KUBE_API_URL` + `KUBE_BEARER_TOKEN` env vars

## Environment variables

Copy `.env.example` and fill in your values:

```bash
cp .env.example .env
```

Discovery order:

1. Explicit `KUBE_API_URL` + `KUBE_BEARER_TOKEN`
2. `KUBECONFIG` or `~/.kube/config`
3. In-cluster service account (`KUBERNETES_SERVICE_HOST` + mounted token)

Optional variables:

- `KUBECONFIG` - override kubeconfig path
- `KUBE_API_URL` - explicit Kubernetes API base URL
- `KUBE_BEARER_TOKEN` - explicit bearer token
- `KUBE_DEFAULT_NAMESPACE` - default namespace for relative paths
- `KUBE_VERIFY_SSL` - `true` or `false` for explicit env mode
- `KUBE_CA_CERT_PATH` - CA certificate path for explicit env mode
- `KUBE_ALLOW_DELETE` - `true` to allow delete tool calls, otherwise deletes are blocked
- `MCP_BASIC_AUTH` or `BASIC_AUTH` - `username:password` for HTTP Basic auth on the MCP endpoint
- `MCP_PASSWORD` or `PASSWORD` - shared secret accepted as `Authorization: Bearer <secret>` or `X-Mcp-Password`
- `MCP_API_KEY` or `API_KEY` - shared API key accepted as `X-API-Key` or `Authorization: Bearer <key>`
- `MCP_API_KEY_HEADER` - custom header name for API key mode, default `x-api-key`
- `MCP_TRANSPORT` - `streamable-http`, `sse`, or `stdio`
- `MCP_HOST` - bind host, default `0.0.0.0`
- `MCP_PORT` - bind port, default `8000`

## Install

Using `uv`:

```bash
cd "/home/pain/Kubernetes MCP"
uv venv
source .venv/bin/activate
uv sync
```

Or with pip:

```bash
cd "/home/pain/Kubernetes MCP"
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Run

Using local `KUBECONFIG` with API key protection on the MCP endpoint:

```bash
export KUBECONFIG="$HOME/.kube/config"
export MCP_API_KEY="change-me"
export MCP_PORT=9000
python -m kubernetes_mcp --transport streamable-http --host 0.0.0.0 --port 9000
```

Using the default kubeconfig path automatically:

```bash
python -m kubernetes_mcp --transport stdio
```

Using explicit env vars:

```bash
export KUBE_API_URL="https://your-kubernetes-api:6443"
export KUBE_BEARER_TOKEN="replace-me"
python -m kubernetes_mcp --transport stdio
```

Running inside a pod with basic auth on the MCP endpoint:

```bash
export MCP_BASIC_AUTH="admin:change-me"
python -m kubernetes_mcp --transport streamable-http --host 0.0.0.0 --port 8000
```

## Exposed MCP tools

The tools are grouped by file so the project stays easy to extend:

- `tools/cluster.py` - cluster health and API discovery tools
- `tools/namespace.py` - namespace read/apply/delete tools
- `tools/node.py` - node read/apply/delete tools
- `tools/pod.py` - pod read/apply/delete tools
- `tools/deployment.py` - deployment read/apply/delete tools
- `tools/service.py` - service read/apply/delete tools
- `tools/configmap.py` - configmap read/apply/delete tools
- `tools/secret.py` - secret read/apply/delete tools
- `tools/job.py` - job read/apply/delete tools
- `tools/ingress.py` - ingress read/apply/delete tools
- `tools/generic.py` - fallback generic resource tools and raw API access

Examples:

### `kube_get_pod(namespace, name?, label_selector?, field_selector?)`
List pods in a namespace or fetch one pod by name.

### `kube_apply_deployment(request)`
Create, replace, or patch a deployment.

### `kube_delete_service(request)`
Delete a service only when `KUBE_ALLOW_DELETE=true`.

### `kube_get_namespace(name?, label_selector?)`
List namespaces or fetch one namespace.

### `kube_get_configmap(namespace, name?, label_selector?)`
List configmaps or fetch one configmap.

### `kube_get_secret(namespace, name?, label_selector?)`
List secrets or fetch one secret.

### `kube_get_job(namespace, name?, label_selector?)`
List jobs or fetch one job.

### `kube_get_node(name?, label_selector?, field_selector?)`
List cluster nodes or fetch one node.

### `kube_get_ingress(namespace, name?, label_selector?)`
List ingresses or fetch one ingress.

### `kube_raw_request(request)`
Advanced escape hatch for direct API-relative requests.

Example raw request input:

```json
{
  "method": "GET",
  "path": "/apis/apps/v1/namespaces/default/deployments"
}
```

## RBAC notes

This server does not bypass Kubernetes permissions. It can only do what the bearer token is allowed to do.

- Use `examples/rbac-reader.yaml` for read-only access
- Use `examples/rbac-editor-with-delete.yaml` only if you intentionally want mutating access
- Even with delete RBAC permissions, the MCP delete tool still stays blocked unless `KUBE_ALLOW_DELETE=true`

## MCP endpoint auth

This auth protects the exposed MCP HTTP server itself. It is separate from Kubernetes auth and RBAC.

Choose exactly one mode:

### Basic auth

```bash
export MCP_BASIC_AUTH="admin:change-me"
```

Client sends:

```http
Authorization: Basic <base64(username:password)>
```

### Shared password

```bash
export MCP_PASSWORD="change-me"
```

Client sends either:

```http
Authorization: Bearer change-me
```

or:

```http
X-Mcp-Password: change-me
```

### API key

```bash
export MCP_API_KEY="change-me"
export MCP_API_KEY_HEADER="x-api-key"
```

If the server runs in Kubernetes, make sure the secret value does not gain a trailing newline during creation. This build trims trailing `\r` and `\n` from HTTP auth env vars to avoid accidental 401s from newline-terminated secrets.

Client sends either:

```http
X-API-Key: change-me
```

or:

```http
Authorization: Bearer change-me
```

When testing from a shell, prefer reusing the existing env var instead of retyping the key:

```bash
curl -H "x-api-key: ${MCP_API_KEY}" ...
```

`stdio` transport is unchanged and does not use this HTTP auth layer.

## Docker

Build the image:

```bash
docker build -t kubernetes-mcp .
```

Run it with mounted kubeconfig:

```bash
docker run --rm -p 8000:8000 \
  -v "$HOME/.kube/config:/root/.kube/config:ro" \
  -e KUBE_ALLOW_DELETE=false \
  -e MCP_API_KEY="change-me" \
  kubernetes-mcp
```

Run it inside Kubernetes with the pod service account:

```bash
python -m kubernetes_mcp --transport streamable-http --host 0.0.0.0 --port 8000
```

Custom port example:

```bash
docker run --rm -p 9000:9000 \
  -v "$HOME/.kube/config:/root/.kube/config:ro" \
  -e MCP_PORT=9000 \
  kubernetes-mcp \
  python -m kubernetes_mcp --transport streamable-http --host 0.0.0.0 --port 9000
```

## Current auth support notes

- Works with explicit bearer token env vars
- Works with in-cluster service account auth
- Works with kubeconfig entries that provide a `token` or `tokenFile`
- Does not yet implement every kubeconfig auth style such as exec plugins

## Response shaping

This MCP now returns simplified JSON instead of the full raw Kubernetes object for normal tool calls.

Examples of what gets trimmed or summarized:

- list responses are capped to the first 20 items
- large metadata blocks are reduced to key fields like name, namespace, labels, timestamps, and finalizers
- workload specs are reduced to the fields agents usually need, such as replicas, selectors, ports, containers, and restart policy
- status is reduced to high-signal fields like phase, replica readiness, IPs, and summarized conditions
- configmaps and secrets return key names instead of full values

This makes tool outputs much smaller and easier for agents to reason over.

If a client still needs full fidelity for a niche case, the best next step would be adding a dedicated raw/full response mode rather than making every default response verbose again.

## Suggested next improvements

- Add an optional `full_response` flag for advanced/debug workflows
- Add audit logging for every mutating request
- Add resource-specific helper tools for pods, deployments, jobs, and logs
- Add server-side allowlists for namespaces or resource kinds
- Add tests with mocked Kubernetes API responses
