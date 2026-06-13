"""Skill 注册入口。"""

from devmanager_agents.registry import SkillRegistry
from devmanager_agents.skills.classify import register_classify_skill
from devmanager_agents.skills.code_read import register_code_read_skills
from devmanager_agents.skills.knowledge import register_knowledge_skill
from devmanager_agents.skills.linter import register_linter_skill
from devmanager_agents.skills.pr_metadata import register_pr_metadata_skill
from devmanager_agents.skills.rule_lookup import register_rule_lookup_skill


def default_registry() -> SkillRegistry:
    """构造注册了 9 个 skill 的默认 registry。"""
    reg = SkillRegistry()
    register_code_read_skills(reg)
    register_knowledge_skill(reg)
    register_rule_lookup_skill(reg)
    register_classify_skill(reg)
    register_linter_skill(reg)
    register_pr_metadata_skill(reg)
    return reg


__all__ = [
    "default_registry",
    "register_code_read_skills",
    "register_knowledge_skill",
    "register_rule_lookup_skill",
    "register_classify_skill",
    "register_linter_skill",
    "register_pr_metadata_skill",
]
