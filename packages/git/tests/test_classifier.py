from __future__ import annotations

from devmanager_git.classifier import (
    compute_risk_tags,
    detect_language,
    is_generated,
    is_test_file,
    is_vendor,
)


def test_detect_language_python():
    assert detect_language("src/foo.py") == "python"


def test_detect_language_typescript():
    assert detect_language("web/app.tsx") == "typescript"


def test_detect_language_unknown():
    assert detect_language("binary.exe") == "unknown"


def test_detect_language_dockerfile():
    assert detect_language("Dockerfile") == "dockerfile"


def test_is_vendor_node_modules():
    assert is_vendor("node_modules/lodash/index.js")


def test_is_vendor_vendor_dir():
    assert is_vendor("vendor/github.com/pkg/errors/errors.go")


def test_is_not_vendor():
    assert not is_vendor("src/myapp/main.py")


def test_is_generated_pb():
    assert is_generated("proto/foo_pb2.py")


def test_is_generated_min_js():
    assert is_generated("static/app.min.js")


def test_is_not_generated():
    assert not is_generated("src/models/user.py")


def test_is_test_file_pytest():
    assert is_test_file("tests/test_user.py")


def test_is_test_file_go():
    assert is_test_file("pkg/auth/auth_test.go")


def test_is_not_test_file():
    assert not is_test_file("src/auth/auth.go")


def test_risk_tags_large_change():
    tags = compute_risk_tags("src/foo.py", 300, 250, False, False, False, False)
    assert "large_change" in tags


def test_risk_tags_config():
    tags = compute_risk_tags("config/app.yaml", 5, 0, False, False, False, False)
    assert "config" in tags


def test_risk_tags_dependency():
    tags = compute_risk_tags("requirements.txt", 3, 1, False, False, False, False)
    assert "dependency" in tags


def test_risk_tags_binary():
    tags = compute_risk_tags("assets/logo.png", 0, 0, True, False, False, False)
    assert "binary" in tags
