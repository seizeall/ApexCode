from __future__ import annotations

import os
import re
from pathlib import Path


class SafetyError(ValueError):
    """An operation would leave the configured workspace or is not allowed."""


def resolve_workspace(value: str | Path) -> Path:
    return Path(value).expanduser().resolve()


def safe_path(workspace: Path, value: str) -> Path:
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = workspace / candidate
    candidate = candidate.resolve()
    try:
        candidate.relative_to(workspace)
    except ValueError as exc:
        raise SafetyError("目标路径不在工作区内。") from exc
    return candidate


def validate_command(command: str) -> None:
    if not command.strip():
        raise SafetyError("命令不能为空。")
    if len(command) > 2_000:
        raise SafetyError("命令长度超过限制。")
    lowered = command.lower()
    blocked = (r"\bformat\s", r"\bshutdown\b", r"\brm\s+-rf\b", r"\bdel\s+/s\b", r"remove-item\s+-recurse")
    if any(re.search(token, lowered) for token in blocked):
        raise SafetyError("该命令被安全策略拒绝。")
