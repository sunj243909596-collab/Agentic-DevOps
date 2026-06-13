"""DevManager-Agent — 自研需求平台 (PM) integration package."""
from __future__ import annotations

from devmanager_pm_integration.config import PMIntegrationConfig, load_config
from devmanager_pm_integration.sync import run_full_sync, run_incremental_sync

__all__ = [
    "PMIntegrationConfig",
    "load_config",
    "run_full_sync",
    "run_incremental_sync",
]

__version__ = "0.1.0"
