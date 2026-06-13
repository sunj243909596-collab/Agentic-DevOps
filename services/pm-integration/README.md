# services/pm-integration

DevManager-Agent — 自研需求平台 (PM) 集成 service。

**当前阶段 (S4 P0)**：仅含包骨架与 config 加载。同步逻辑、HTTP client、ARQ job 在后续 P3 阶段实现。

**配置**：

- `PM_API_BASE_URL`（必填）— PM 平台 REST API 根 URL，**末尾无斜杠**
- `PM_API_TOKEN`（必填）— Bearer token，**严禁硬编码**
- `PM_API_TIMEOUT_SECONDS`（默认 30）
- `PM_API_PAGE_SIZE`（默认 100）
- `PM_WEBHOOK_ENABLED`（默认 `false`，v1 禁用）

缺失必填项时 `PMIntegrationConfig.from_env()` 会 `RuntimeError` 失败（fail-fast）。

**本地快速验证**：

```bash
cd /root/WMOS\ 设计工场/Agentic-DevOps
uv sync
PM_API_BASE_URL=https://pm.example.com PM_API_TOKEN=dummy \
  python -m devmanager_pm_integration
# 期望输出：PMIntegrationConfig(base_url='https://pm.example.com', timeout_seconds=30, page_size=100, webhook_enabled=False)
```
