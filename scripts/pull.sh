#!/usr/bin/env bash
# scripts/pull.sh — 包装 git pull，自动跑 code map 重生
# 用法: scripts/pull.sh [git pull 的其它参数]
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

PREV_HEAD="$(git rev-parse HEAD 2>/dev/null || echo '0000000000000000000000000000000000000000')"

# 真正的 git pull
git pull "$@"

NEW_HEAD="$(git rev-parse HEAD)"

# 没变化则跳过
if [ "$PREV_HEAD" = "$NEW_HEAD" ]; then
  echo "code-map: HEAD 未变 ($NEW_HEAD)，跳过 regen"
  exit 0
fi

echo "code-map: 检测到变更 ($PREV_HEAD -> $NEW_HEAD)，开始 regen…"

# 调 Python regen
cd "$REPO_ROOT"
uv run python -m api_gateway.routers.code_map.regen \
    --prev-head "$PREV_HEAD" \
    --new-head "$NEW_HEAD" \
    --maps-dir "$REPO_ROOT/docs/code-map" || true

echo "code-map: regen 完成（exit 0 即使部分失败 — 旧版已保留）"
