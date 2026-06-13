"""Pydantic models for the code-map system.

Single source of truth for module / edge / scope graph / card / index.
The disk JSON files in docs/code-map/ must round-trip through these models.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ModuleKind = Literal["frontend-spa", "backend", "agent", "lib", "docs", "test"]


class Module(BaseModel):
    id: str = Field(min_length=1, description="唯一 id = 目录相对路径")
    path: str = Field(min_length=1, description="仓库内绝对路径（相对仓库根）")
    name: str = Field(min_length=1, description="中文业务名")
    kind: ModuleKind = "lib"
    responsibility: str = ""
    entry_points: list[str] = Field(default_factory=list, max_length=3)
    key_files: list[str] = Field(default_factory=list)


class Edge(BaseModel):
    """`from` / `to` are reserved in pydantic — accept via aliases."""
    model_config = {"populate_by_name": True}

    from_: str = Field(alias="from")
    to: str
    via: str | None = None


class ScopeGraph(BaseModel):
    scope: str
    version: int = Field(ge=0)
    generated_at: str
    head_sha: str
    generator: str
    stale: bool = False
    stale_reason: str | None = None
    modules: list[Module]
    edges: list[Edge] = Field(default_factory=list)


class InterfaceEntry(BaseModel):
    """Structured view of a module's outbound surface."""
    exports: list[str] = Field(default_factory=list)
    imports: list[str] = Field(default_factory=list)
    consumes_api: list[str] = Field(default_factory=list)


class DepEdge(BaseModel):
    """Structured dependency reference used in depends_on / depended_on_by."""
    id: str = Field(min_length=1)
    kind: str = ""


class ModuleCard(BaseModel):
    scope: str
    module_id: str
    version: int = Field(ge=0)
    generated_at: str
    head_sha: str
    responsibility: str = ""
    interfaces: InterfaceEntry = Field(default_factory=InterfaceEntry)
    depends_on: list[DepEdge] = Field(default_factory=list)
    depended_on_by: list[DepEdge] = Field(default_factory=list)
    key_files: list[str] = Field(default_factory=list)
    notes: str = ""


class IndexFile(BaseModel):
    generated_at: str
    last_pull_at: str | None = None
    last_error: str | None = None
    scopes: dict[str, dict] = Field(default_factory=dict)
