from __future__ import annotations

import uuid
from pathlib import Path

from devmanager_db.daos.repository import RepositoryDAO
from devmanager_db.daos.setting import SettingDAO
from devmanager_db.models import AnalysisRun, Baseline, TriggerEvent
from devmanager_git.fetcher import (
    GitError,
    list_refs,
    list_tree,
    read_file,
)
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api_gateway.dependencies import get_db, require_auth
from api_gateway.schemas.models import PROVIDER_PATTERN, RepositoryResponse

router = APIRouter(prefix="/v1/repositories", tags=["repositories"])


class UpdateRepositoryIn(BaseModel):
    clone_url: str | None = Field(default=None, description="HTTPS clone URL")
    clear_clone_url: bool = False
    access_token: str | None = Field(default=None, description="GitLab PAT")
    clear_access_token: bool = False
    status: str | None = Field(default=None, pattern="^(active|disabled|archived)$")
    default_branch: str | None = None
    provider: str | None = Field(default=None, pattern=PROVIDER_PATTERN)


@router.get("", response_model=dict)
async def list_repositories(
    db: AsyncSession = Depends(get_db),
    _auth: str = Depends(require_auth),
) -> dict:
    repos = await RepositoryDAO(db).list_active()
    return {"items": [RepositoryResponse.model_validate(r) for r in repos]}


@router.get("/{repository_id}", response_model=RepositoryResponse)
async def get_repository(
    repository_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _auth: str = Depends(require_auth),
) -> RepositoryResponse:
    repo = await RepositoryDAO(db).get_by_id(repository_id)
    if repo is None:
        raise HTTPException(status_code=404, detail=f"Repository {repository_id} not found")
    return RepositoryResponse.model_validate(repo)


@router.patch("/{repository_id}", response_model=RepositoryResponse)
async def update_repository(
    repository_id: uuid.UUID,
    body: UpdateRepositoryIn,
    db: AsyncSession = Depends(get_db),
    _auth: str = Depends(require_auth),
) -> RepositoryResponse:
    dao = RepositoryDAO(db)
    existing = await dao.get_by_id(repository_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Repository {repository_id} not found")
    await dao.update(
        repository_id,
        clone_url=body.clone_url,
        clear_clone_url=body.clear_clone_url,
        access_token=body.access_token,
        clear_access_token=body.clear_access_token,
        status=body.status,
        default_branch=body.default_branch,
        provider=body.provider,
    )
    await db.commit()
    updated = await dao.get_by_id(repository_id)
    return RepositoryResponse.model_validate(updated)


@router.delete("/{repository_id}", status_code=204)
async def delete_repository(
    repository_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _auth: str = Depends(require_auth),
) -> Response:
    """Delete a repository. Refuses (409) if there are dependent runs / baselines / triggers
    — delete those first, or archive via PATCH {status: 'archived'} instead."""
    dao = RepositoryDAO(db)
    existing = await dao.get_by_id(repository_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Repository {repository_id} not found")

    # Count dependent rows
    runs_count = (
        await db.execute(
            select(AnalysisRun.run_id).where(AnalysisRun.repository_id == repository_id).limit(1)
        )
    ).first()
    bases_count = (
        await db.execute(
            select(Baseline.repository_id).where(Baseline.repository_id == repository_id).limit(1)
        )
    ).first()
    trigs_count = (
        await db.execute(
            select(TriggerEvent.event_id)
            .where(TriggerEvent.repository_id == repository_id)
            .limit(1)
        )
    ).first()
    if runs_count or bases_count or trigs_count:
        raise HTTPException(
            status_code=409,
            detail="仓库有历史运行 / 基线 / 触发事件，不能直接删除。"
            "请先用 PATCH status='archived' 归档，或先删除相关运行。",
        )
    await dao.delete(repository_id)
    await db.commit()
    return Response(status_code=204)


# ── File browser ──────────────────────────────────────────────────────────────


async def _resolve_repo_dir(db: AsyncSession, repository_id: uuid.UUID) -> Path:
    dao = RepositoryDAO(db)
    repo = await dao.get_by_id(repository_id)
    if repo is None:
        raise HTTPException(status_code=404, detail=f"Repository {repository_id} not found")
    workspace = await SettingDAO(db).get_value("git_workspace", "/tmp/devmanager/repos")
    repo_dir = Path(workspace) / str(repository_id)
    if not (repo_dir / "HEAD").exists():
        raise HTTPException(
            status_code=409,
            detail=(
                f"仓库尚未在本地克隆。仓库路径：{repo_dir}。"
                "请先触发一次 run 让 worker 完成 git clone。"
            ),
        )
    return repo_dir


@router.get("/{repository_id}/refs")
async def list_repository_refs(
    repository_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _auth: str = Depends(require_auth),
) -> dict:
    repo_dir = await _resolve_repo_dir(db, repository_id)
    refs = await list_refs(repo_dir)
    return {"items": refs}


@router.get("/{repository_id}/tree")
async def list_repository_tree(
    repository_id: uuid.UUID,
    ref: str = Query(..., description="分支名 / tag / SHA"),
    path: str = Query("", description="仓库内路径，'' = 根目录"),
    db: AsyncSession = Depends(get_db),
    _auth: str = Depends(require_auth),
) -> dict:
    repo_dir = await _resolve_repo_dir(db, repository_id)
    if path and (".." in path.split("/") or path.startswith("/")):
        raise HTTPException(status_code=400, detail="invalid path")
    try:
        items = await list_tree(repo_dir, ref, path)
        return {"ref": ref, "path": path, "items": items}
    except GitError as e:
        raise HTTPException(status_code=404, detail=f"path not found: {e}")


@router.get("/{repository_id}/file")
async def read_repository_file(
    repository_id: uuid.UUID,
    ref: str = Query(..., description="分支名 / tag / SHA"),
    path: str = Query(..., description="文件路径"),
    db: AsyncSession = Depends(get_db),
    _auth: str = Depends(require_auth),
) -> dict:
    repo_dir = await _resolve_repo_dir(db, repository_id)
    if ".." in path.split("/") or path.startswith("/"):
        raise HTTPException(status_code=400, detail="invalid path")
    try:
        return {"ref": ref, "path": path, **(await read_file(repo_dir, ref, path))}
    except GitError as e:
        raise HTTPException(status_code=404, detail=f"file not found: {e}")
