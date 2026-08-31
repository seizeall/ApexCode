from __future__ import annotations

import re
from pathlib import Path


class SafetyError(ValueError):
    """An operation would leave the configured workspace or is not allowed."""


def resolve_workspace(value: str | Path) -> Path:
    return Path(value).expanduser().resolve()


def safe_path(workspace: Path, value: str) -> Path:
    workspace = resolve_workspace(workspace)
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise SafetyError("目标路径无效。")
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
    blocked = (
        r"\bformat\s", r"\bshutdown\b", r"(?:^|[;&|])\s*(?:rm|del|erase|remove-item)\b",
        r"\bgit\s+clean\b", r"\bgit\s+reset\s+--hard\b", r"\bgit\s+checkout\s+--\b",
        r"(?:^|[;&|])\s*(?:cd|pushd|set-location)\s+", r"(?:^|[;&|])\s*start\s+",
    )
    if any(re.search(token, lowered) for token in blocked):
        raise SafetyError("该命令被安全策略拒绝。")
    if re.search(r"(?:^|[\\/])\.\.(?:[\\/]|$)", command) or re.search(r"\b(?:/etc/|/var/|c:\\windows)", lowered):
        raise SafetyError("命令包含可能离开工作区的路径。")
