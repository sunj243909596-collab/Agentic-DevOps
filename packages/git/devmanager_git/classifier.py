from __future__ import annotations

import re
from pathlib import PurePosixPath

_LANG_MAP: dict[str, str] = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".jsx": "javascript",
    ".java": "java",
    ".kt": "kotlin",
    ".go": "go",
    ".rs": "rust",
    ".c": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".h": "c",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".scala": "scala",
    ".sql": "sql",
    ".sh": "shell",
    ".bash": "shell",
    ".zsh": "shell",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".toml": "toml",
    ".xml": "xml",
    ".html": "html",
    ".css": "css",
    ".scss": "css",
    ".md": "markdown",
    ".rst": "rst",
    ".tf": "terraform",
    ".dockerfile": "dockerfile",
}

_VENDOR_PATTERNS = [
    re.compile(p)
    for p in [
        r"^vendor/",
        r"^node_modules/",
        r"^third_party/",
        r"/vendor/",
        r"/node_modules/",
    ]
]

_GENERATED_PATTERNS = [
    re.compile(p)
    for p in [
        r"\.pb\.go$",
        r"\.pb\.py$",
        r"_pb2\.py$",
        r"\.generated\.",
        r"/generated/",
        r"\.min\.js$",
        r"\.min\.css$",
        r"dist/",
        r"build/",
        r"__generated__/",
    ]
]

_TEST_PATTERNS = [
    re.compile(p)
    for p in [
        r"test[s]?/",
        r"_test\.go$",
        r"_test\.py$",
        r"\.test\.(ts|js|tsx|jsx)$",
        r"\.spec\.(ts|js|tsx|jsx)$",
        r"test_.*\.py$",
        r"/tests?/",
    ]
]

_CONFIG_EXTS = {".yaml", ".yml", ".toml", ".json", ".ini", ".cfg", ".conf", ".env"}
_DEP_FILES = {
    "package.json",
    "requirements.txt",
    "Pipfile",
    "pyproject.toml",
    "pom.xml",
    "build.gradle",
    "Cargo.toml",
    "go.mod",
    "go.sum",
    "Gemfile",
    "composer.json",
}


def detect_language(file_path: str) -> str:
    path = PurePosixPath(file_path)
    name_lower = path.name.lower()
    if name_lower == "dockerfile":
        return "dockerfile"
    ext = path.suffix.lower()
    return _LANG_MAP.get(ext, "unknown")


def is_vendor(file_path: str) -> bool:
    return any(p.search(file_path) for p in _VENDOR_PATTERNS)


def is_generated(file_path: str) -> bool:
    return any(p.search(file_path) for p in _GENERATED_PATTERNS)


def is_test_file(file_path: str) -> bool:
    return any(p.search(file_path) for p in _TEST_PATTERNS)


def compute_risk_tags(
    file_path: str,
    added: int,
    deleted: int,
    binary: bool,
    generated: bool,
    vendor: bool,
    test: bool,
) -> list[str]:
    tags: list[str] = []
    if binary:
        tags.append("binary")
    if generated:
        tags.append("generated")
    if vendor:
        tags.append("vendor")
    if test:
        tags.append("test")
    if added + deleted > 500:
        tags.append("large_change")
    path = PurePosixPath(file_path)
    if path.suffix.lower() in _CONFIG_EXTS:
        tags.append("config")
    if path.name in _DEP_FILES:
        tags.append("dependency")
    return tags
