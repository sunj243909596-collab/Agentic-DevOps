"""`python -m devmanager_pm_integration` — 打印当前生效的 config（脱敏 token）。

用于本地快速验证 P0 骨架。
"""
from __future__ import annotations

from devmanager_pm_integration.config import load_config


def main() -> None:
    try:
        cfg = load_config()
    except RuntimeError as exc:
        print(f"[FAIL] {exc}")
        raise SystemExit(1)
    print(cfg)


if __name__ == "__main__":
    main()
