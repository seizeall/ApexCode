from pathlib import Path

import pytest

from app.safety import SafetyError, safe_path, validate_command


def test_safe_path_rejects_escape(tmp_path: Path) -> None:
    with pytest.raises(SafetyError):
        safe_path(tmp_path, "../outside.txt")


def test_validate_command_rejects_recursive_delete() -> None:
    with pytest.raises(SafetyError):
        validate_command("rm -rf .")
