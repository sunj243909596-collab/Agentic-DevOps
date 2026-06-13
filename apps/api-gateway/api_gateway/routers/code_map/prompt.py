"""LLM prompt template for code-map regeneration.

Sends a single user message containing:
  - the old ScopeGraph (or "v0 / no prior")
  - the changed files in this scope
  - the current directory tree (truncated if huge)

The LLM is asked to return ONLY a JSON object matching ScopeGraph schema
(no markdown, no prose).
"""
from __future__ import annotations

import json

from devmanager_llm import LLMMessage

from .schema import ScopeGraph

SYSTEM_PROMPT = """你是一个仓库结构分析助手。

你的任务是根据给定的"旧版代码地图"和"本次变更"，重新生成该 scope (顶层目录) 的完整模块图。

输出要求：
1. **仅输出 JSON**，不输出 markdown 围栏、不输出额外解释
2. JSON 必须严格符合以下 schema：
   - scope: 字符串（顶层目录名）
   - version: 整数（旧版号 + 1；若没有旧版则从 1 开始）
   - generated_at: ISO8601 时间字符串
   - head_sha: 字符串（用给定的 HEAD SHA）
   - generator: 字符串（模型名）
   - modules: 数组，每个元素含 id / path / name / kind / responsibility / entry_points / key_files
   - edges: 数组，每个元素含 from / to / via

字段语义：
- `kind` 取值：frontend-spa / backend / agent / lib / docs / test
- `entry_points`：进程/服务启动入口，最多 3 个
- `key_files`：核心源文件（不含 entry_points）
- `responsibility`：中文一句话职责
- `via`：如果是直接 import 关系，给出具体文件路径

要求：
- 保留旧版里仍然存在的模块
- 添加新出现的模块
- 删除已经不再存在的模块
- 更新依赖关系（edges）"""


def build_messages(
    *,
    scope: str,
    old_graph: ScopeGraph | None,
    changed_files: list[str] | None = None,
    file_tree: str = "",
    head_sha: str = "",
    generator: str = "claude-opus-4-8",
    max_tree_chars: int = 60_000,
) -> list[LLMMessage]:
    if max_tree_chars <= 0:
        raise ValueError(f"max_tree_chars must be > 0, got {max_tree_chars}")
    files = changed_files or []

    old_dump = (
        json.dumps(
            old_graph.model_dump(exclude_none=True),
            ensure_ascii=False,
            indent=2,
        )
        if old_graph
        else "（v0：无旧版地图）"
    )

    tree_section = file_tree
    if len(tree_section) > max_tree_chars:
        tree_section = tree_section[:max_tree_chars] + "\n... (truncated)"

    user = f"""scope = {scope}
head_sha = {head_sha}
generator = {generator}

# 旧版代码地图
{old_dump}

# 本次变更文件（{len(files)} 个）
{chr(10).join(files) if files else '（无变更 — 仍请重新审视整张图）'}

# 当前目录 tree
{tree_section}

请输出新的 ScopeGraph JSON。"""

    return [LLMMessage(role="user", content=user)]
