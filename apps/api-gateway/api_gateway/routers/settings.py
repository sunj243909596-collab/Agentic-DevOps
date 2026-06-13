from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api_gateway.dependencies import get_db, require_auth
from devmanager_db.daos.audit_event import AuditEventDAO
from devmanager_db.daos.setting import SettingDAO
from devmanager_db.models import Setting
from devmanager_db.secrets import encrypt_secret

router = APIRouter(prefix="/v1/settings", tags=["settings"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class SettingOut(BaseModel):
    key: str
    value: str
    description: str | None = None
    updated_at: str
    updated_by: str | None = None
    is_secret: bool = False
    is_set: bool = False           # for secret fields, True if a value is stored

    @classmethod
    def from_orm_safe(cls, s: Setting, *, is_secret: bool = False) -> "SettingOut":
        return cls(
            key=s.key,
            # Never expose secret values directly
            value="" if is_secret else s.value,
            description=s.description,
            updated_at=s.updated_at.isoformat() if s.updated_at else "",
            updated_by=s.updated_by,
            is_secret=is_secret,
            is_set=bool(s.value) if is_secret else True,
        )


class UpdateSettingsIn(BaseModel):
    items: dict[str, str] = Field(
        ..., description="key → 新 value；只改提供的 key"
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

# Keys whose values are filesystem paths — when they change, attempt migration
_PATH_KEYS = {"git_workspace", "git_hunks_dir"}

# Keys whose values are secrets and must be encrypted at rest
_SECRET_KEYS = {"llm_api_key"}


def _validate_path(key: str, value: str) -> str:
    """Reject obviously bad paths. Return the absolute, normalized path."""
    p = Path(value).expanduser()
    if not p.is_absolute():
        raise HTTPException(
            status_code=400,
            detail=f"配置项 {key} 必须是绝对路径（当前：{value}）",
        )
    return str(p)


def _validate_provider(key: str, value: str) -> str:
    from devmanager_llm import PROVIDERS
    if value not in PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail=f"未知的 LLM provider: {value!r}。可选: {list(PROVIDERS)}",
        )
    return value


def _validate_base_url(key: str, value: str) -> str:
    """Validate a custom LLM base URL. Empty = use provider default."""
    v = (value or "").strip()
    if not v:
        return ""
    # Basic scheme + host check. We don't want to import urllib just to
    # enforce this; a permissive regex is enough — the SDK will reject
    # anything malformed at call time with a clearer error.
    import re
    if not re.match(r"^https?://[^\s/$.?#].[^\s]*$", v, re.IGNORECASE):
        raise HTTPException(
            status_code=400,
            detail=f"配置项 {key} 不是合法 URL: {value!r}（需以 http:// 或 https:// 开头）",
        )
    # Strip trailing slash — SDKs are picky about double slashes in path
    return v.rstrip("/")


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("", response_model=dict)
async def list_settings(
    db: AsyncSession = Depends(get_db),
    _auth: str = Depends(require_auth),
) -> dict:
    rows = await SettingDAO(db).list_all()
    return {"items": [SettingOut.from_orm_safe(s, is_secret=s.key in _SECRET_KEYS) for s in rows]}


@router.put("", response_model=dict)
async def update_settings(
    body: UpdateSettingsIn,
    db: AsyncSession = Depends(get_db),
    _auth: str = Depends(require_auth),
) -> dict:
    """Update one or more settings. For path keys, also mv existing data to the new location."""
    dao = SettingDAO(db)
    migration_log: list[dict[str, Any]] = []

    for k, v in body.items.items():
        # Pre-validate
        if k in _PATH_KEYS:
            new_value = _validate_path(k, v)
        elif k == "llm_provider":
            new_value = _validate_provider(k, v)
        elif k == "llm_base_url":
            new_value = _validate_base_url(k, v)
        elif k in _SECRET_KEYS:
            new_value = encrypt_secret(v)
        else:
            new_value = v

        # Compare against current (after encryption for secret keys)
        cur = await dao.get(k)
        if cur is not None and cur.value == new_value:
            continue  # no change

        # For path keys, attempt mv from old → new if old exists
        if k in _PATH_KEYS and cur is not None and cur.value:
            old_p = Path(cur.value).expanduser()
            new_p = Path(new_value)
            if old_p.exists() and old_p != new_p:
                if new_p.exists():
                    raise HTTPException(
                        status_code=409,
                        detail=f"目标路径 {new_p} 已存在，无法迁移。请先手动处理冲突。",
                    )
                try:
                    new_p.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(old_p), str(new_p))
                    migration_log.append({
                        "key": k,
                        "from": str(old_p),
                        "to": str(new_p),
                        "migrated": True,
                    })
                except Exception as exc:
                    raise HTTPException(
                        status_code=500,
                        detail=f"迁移 {old_p} → {new_p} 失败：{exc}",
                    )
            elif not old_p.exists() and not new_p.exists():
                # Nothing to migrate; just ensure target parent exists
                new_p.parent.mkdir(parents=True, exist_ok=True)
                migration_log.append({
                    "key": k, "from": str(old_p), "to": str(new_p),
                    "migrated": False, "note": "源目录不存在，仅创建目标父目录",
                })

        await dao.set_value(k, new_value, updated_by="ui")

    await db.commit()

    # Audit log
    try:
        audit = AuditEventDAO(db)
        for k, v in body.items.items():
            await audit.append(
                actor="ui",
                workflow_id=__import__("uuid").UUID(int=0),
                event_type="settings.updated",
                event_timestamp=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
                metadata={"key": k, "value": v, "migration": migration_log},
            )
    except Exception:
        pass  # audit best-effort
    await db.commit()

    rows = await dao.list_all()
    return {
        "items": [SettingOut.from_orm_safe(s, is_secret=s.key in _SECRET_KEYS) for s in rows],
        "migration": migration_log,
    }
