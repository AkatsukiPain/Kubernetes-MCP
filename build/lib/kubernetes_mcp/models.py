from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ResourceQuery(BaseModel):
    api_version: str = Field(..., description="Example: v1, apps/v1, batch/v1")
    kind_plural: str = Field(..., description="Plural resource name, example: pods, deployments, jobs")
    namespace: str | None = Field(default=None, description="Namespace to target. Omit for cluster-scoped APIs.")
    name: str | None = Field(default=None, description="Specific resource name. Omit to list resources.")
    label_selector: str | None = Field(default=None, description="Kubernetes label selector.")
    field_selector: str | None = Field(default=None, description="Kubernetes field selector.")


class ApplyRequest(BaseModel):
    api_version: str = Field(..., description="Example: v1 or apps/v1")
    kind_plural: str = Field(..., description="Plural resource name, example: configmaps, deployments")
    namespace: str | None = Field(default=None, description="Namespace for namespaced resources.")
    name: str | None = Field(default=None, description="Required for PATCH, optional for POST.")
    method: Literal["POST", "PATCH", "PUT"] = Field(..., description="Create or update method.")
    manifest: dict[str, Any] = Field(..., description="Kubernetes manifest body.")


class DeleteRequest(BaseModel):
    api_version: str = Field(..., description="Example: v1 or apps/v1")
    kind_plural: str = Field(..., description="Plural resource name, example: pods, configmaps")
    namespace: str | None = Field(default=None, description="Namespace for namespaced resources.")
    name: str = Field(..., description="Resource name to delete.")
    propagation_policy: Literal["Foreground", "Background", "Orphan"] | None = None
    grace_period_seconds: int | None = None


class RawRequest(BaseModel):
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
    path: str = Field(..., description="API-relative path, e.g. /api/v1/namespaces/default/pods")
    namespace: str | None = Field(default=None, description="Used only when path is relative, e.g. pods/my-pod")
    params: dict[str, str] | None = None
    body: dict[str, Any] | None = None
