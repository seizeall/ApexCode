from __future__ import annotations

import asyncio
import difflib
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable

from pydantic import BaseModel, ConfigDict, ValidationError

from app.config import Settings
from app.safety import SafetyError, safe_path, validate_command


Approval = Callable[[str, dict[str, Any]], Awaitable[bool]]


@dataclass
class ToolContext:
    settings: Settings
    approve: Approval
    cancel_event: asyncio.Event | None = None


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ListFilesArgs(_Args):
    path: str = "."


class ReadFileArgs(_Args):
    path: str


class SearchTextArgs(_Args):
    query: str
    path: str = "."


class WriteFileArgs(_Args):
    path: str
    content: str


class RunCommandArgs(_Args):
    command: str


class ApplyPatchArgs(_Args):
    patch: str


class ToolRegistry:
    def __init__(self, settings: Settings, approve: Approval, cancel_event: asyncio.Event | None = None) -> None:
        self.context = ToolContext(settings, approve, cancel_event)
        self._tools = {
            "list_files": self._list_files,
            "read_file": self._read_file,
            "search_text": self._search_text,
            "write_file": self._write_file,
            "apply_patch": self._apply_patch,
            "run_command": self._run_command,
        }
        self._arg_models = {"list_files": ListFilesArgs, "read_file": ReadFileArgs, "search_text": SearchTextArgs, "write_file": WriteFileArgs, "apply_patch": ApplyPatchArgs, "run_command": RunCommandArgs}

    def schemas(self) -> list[dict[str, Any]]:
        return [
            {"type": "function", "function": {"name": "list_files", "description": "列出工作区内的文件和目录。", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": []}}},
            {"type": "function", "function": {"name": "read_file", "description": "读取工作区内的文本文件。", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
            {"type": "function", "function": {"name": "search_text", "description": "在工作区文本文件中搜索字符串。", "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "path": {"type": "string"}}, "required": ["query"]}}},
            {"type": "function", "function": {"name": "write_file", "description": "创建或覆盖工作区内的文本文件。", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}}},
            {"type": "function", "function": {"name": "apply_patch", "description": "将一个或多个 unified diff 补丁应用到工作区内的已有文件。", "parameters": {"type": "object", "properties": {"patch": {"type": "string"}}, "required": ["patch"]}}},
            {"type": "function", "function": {"name": "run_command", "description": "在工作区内运行一条开发命令。", "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}}},
        ]

    async def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if self.context.cancel_event and self.context.cancel_event.is_set():
            return {"ok": False, "cancelled": True, "error": "任务已取消。"}
        fn = self._tools.get(name)
        if not fn:
            return {"ok": False, "error": f"未知工具：{name}"}
        try:
            model = self._arg_models[name](**arguments)
            arguments = model.model_dump()
            return await fn(arguments)
        except (OSError, UnicodeError, SafetyError, ValueError, TypeError, KeyError, ValidationError) as exc:
            return {"ok": False, "error": str(exc)}

    async def _list_files(self, args: dict[str, Any]) -> dict[str, Any]:
        root = safe_path(self.context.settings.workspace, args.get("path", "."))
        if not root.exists():
            raise ValueError("目录不存在。")
        if not root.is_dir():
            raise ValueError("目标不是目录。")
        entries = []
        for item in sorted(root.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))[:200]:
            if item.name.startswith(".") or item.name in {"tmp", "node_modules", "__pycache__"}:
                continue
            entries.append({"name": item.name, "type": "file" if item.is_file() else "directory"})
        return {"ok": True, "path": str(root.relative_to(self.context.settings.workspace) or "."), "entries": entries}

    async def _read_file(self, args: dict[str, Any]) -> dict[str, Any]:
        path = safe_path(self.context.settings.workspace, args["path"])
        if not path.is_file():
            raise ValueError("文件不存在。")
        if path.stat().st_size > self.context.settings.max_file_bytes:
            raise ValueError("文件超过读取大小限制。")
        return {"ok": True, "path": str(path.relative_to(self.context.settings.workspace)), "content": path.read_text(encoding="utf-8")}

    async def _search_text(self, args: dict[str, Any]) -> dict[str, Any]:
        query = args["query"]
        root = safe_path(self.context.settings.workspace, args.get("path", "."))
        if not root.is_dir():
            raise ValueError("搜索目标不是目录。")
        hits = []
        for path in root.rglob("*"):
            if self.context.cancel_event and self.context.cancel_event.is_set():
                return {"ok": False, "cancelled": True, "error": "任务已取消。"}
            if not path.is_file() or path.stat().st_size > self.context.settings.max_file_bytes:
                continue
            if any(part in {".git", ".venv", "node_modules", "__pycache__"} for part in path.parts):
                continue
            try:
                for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                    if query.lower() in line.lower():
                        hits.append({"path": str(path.relative_to(self.context.settings.workspace)), "line": line_no, "text": line[:300]})
                        if len(hits) >= 100:
                            return {"ok": True, "hits": hits, "truncated": True}
            except (UnicodeDecodeError, OSError):
                continue
        return {"ok": True, "hits": hits, "truncated": False}

    async def _write_file(self, args: dict[str, Any]) -> dict[str, Any]:
        path = safe_path(self.context.settings.workspace, args["path"])
        content = args["content"]
        if len(content.encode("utf-8")) > self.context.settings.max_file_bytes:
            raise ValueError("写入内容超过大小限制。")
        old = path.read_text(encoding="utf-8") if path.is_file() and path.stat().st_size <= self.context.settings.max_file_bytes else ""
        diff = "".join(difflib.unified_diff(old.splitlines(keepends=True), content.splitlines(keepends=True), fromfile=str(path), tofile=str(path)))
        allowed = await self.context.approve("write_file", {"path": str(path.relative_to(self.context.settings.workspace)), "content": content, "diff": diff[-12_000:]})
        if not allowed:
            return {"ok": False, "cancelled": True, "error": "用户拒绝了文件修改。"}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return {"ok": True, "path": str(path.relative_to(self.context.settings.workspace)), "bytes": len(content.encode("utf-8"))}

    async def _run_command(self, args: dict[str, Any]) -> dict[str, Any]:
        command = args["command"]
        validate_command(command)
        allowed = await self.context.approve("run_command", {"command": command})
        if not allowed:
            return {"ok": False, "cancelled": True, "error": "用户拒绝了命令执行。"}
        proc = await asyncio.create_subprocess_shell(command, cwd=self.context.settings.workspace, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            deadline = time.monotonic() + self.context.settings.command_timeout
            while True:
                if self.context.cancel_event and self.context.cancel_event.is_set():
                    proc.kill()
                    await proc.communicate()
                    return {"ok": False, "cancelled": True, "error": "任务已取消。"}
                if time.monotonic() >= deadline:
                    proc.kill()
                    await proc.communicate()
                    return {"ok": False, "error": "命令执行超时。", "timeout": True}
                try:
                    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=.5)
                    break
                except asyncio.TimeoutError:
                    if proc.returncode is not None:
                        stdout, stderr = await proc.communicate()
                        break
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            return {"ok": False, "error": "命令执行超时。", "timeout": True}
        return {"ok": proc.returncode == 0, "returncode": proc.returncode, "stdout": stdout.decode(errors="replace")[-8_000:], "stderr": stderr.decode(errors="replace")[-8_000:]}

    async def _apply_patch(self, args: dict[str, Any]) -> dict[str, Any]:
        patch = args["patch"]
        operations = _parse_patch(patch)
        if not operations:
            raise ValueError("补丁中没有可应用的文件变更。")
        previews: list[dict[str, str]] = []
        updated: list[tuple[Path, str, str]] = []
        for relative, hunks, create in operations:
            path = safe_path(self.context.settings.workspace, relative)
            if create and path.exists():
                raise ValueError(f"补丁目标文件已存在：{relative}")
            if not create and not path.is_file():
                raise ValueError(f"补丁目标文件不存在：{relative}")
            if not create and path.stat().st_size > self.context.settings.max_file_bytes:
                raise ValueError(f"补丁目标文件超过读取大小限制：{relative}")
            old = "" if create else path.read_text(encoding="utf-8")
            new = _apply_hunks(old, hunks)
            if len(new.encode("utf-8")) > self.context.settings.max_file_bytes:
                raise ValueError(f"补丁结果超过文件大小限制：{relative}")
            diff = "".join(difflib.unified_diff(old.splitlines(keepends=True), new.splitlines(keepends=True), fromfile=relative, tofile=relative))
            previews.append({"path": relative, "diff": diff[-12_000:]})
            updated.append((path, old, new))
        allowed = await self.context.approve("apply_patch", {"files": previews})
        if not allowed:
            return {"ok": False, "cancelled": True, "error": "用户拒绝了文件补丁。"}
        for path, _, new in updated:
            path.write_text(new, encoding="utf-8")
        return {"ok": True, "files": [relative for relative, _, _ in operations]}


def _parse_patch(patch: str) -> list[tuple[str, list[list[str]], bool]]:
    """解析常见的 Codex/Unix unified diff，不接受删除文件操作。"""
    lines = patch.replace("\r\n", "\n").splitlines(keepends=True)
    if any(line.startswith("*** Delete File:") for line in lines):
        raise ValueError("为避免误删，暂不支持删除文件补丁。")
    operations: list[tuple[str, list[list[str]], bool]] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        relative = None
        create = False
        if line.startswith("*** Update File:"):
            relative = line.split(":", 1)[1].strip()
            index += 1
        elif line.startswith("*** Add File:"):
            relative = line.split(":", 1)[1].strip()
            create = True
            index += 1
        elif line.startswith("--- ") and index + 1 < len(lines) and lines[index + 1].startswith("+++ "):
            relative = lines[index + 1][4:].strip().split("\t", 1)[0]
            relative = relative[2:] if relative.startswith(("a/", "b/")) else relative
            index += 2
        else:
            index += 1
            continue
        hunks: list[list[str]] = []
        while index < len(lines):
            if lines[index].startswith(("*** Update File:", "*** Add File:")) or (lines[index].startswith("--- ") and index + 1 < len(lines) and lines[index + 1].startswith("+++ ")):
                break
            if lines[index].startswith("*** End Patch"):
                index += 1
                break
            if lines[index].startswith("@@"):
                index += 1
                hunk: list[str] = []
                while index < len(lines) and not lines[index].startswith("@@") and not lines[index].startswith("*** Update File:") and not lines[index].startswith("--- "):
                    current = lines[index]
                    if current.startswith((" ", "+", "-")):
                        hunk.append(current)
                    elif current.startswith("\\ No newline"):
                        pass
                    else:
                        break
                    index += 1
                hunks.append(hunk)
                continue
            if create and lines[index].startswith("+"):
                hunk: list[str] = []
                while index < len(lines) and lines[index].startswith("+"):
                    hunk.append(lines[index])
                    index += 1
                hunks.append(hunk)
                continue
            index += 1
        if not hunks:
            raise ValueError(f"补丁缺少变更区块：{relative}")
        operations.append((relative, hunks, create))
    return operations


def _apply_hunks(old: str, hunks: list[list[str]]) -> str:
    old_lines = old.splitlines(keepends=True)
    offset = 0
    for hunk in hunks:
        context = [line[1:] for line in hunk if line.startswith((" ", "-"))]
        # 查找上下文而不是盲信 @@ 行号，允许模型生成的行号轻微过时。
        start = _find_sequence(old_lines, context, offset)
        if start < 0:
            raise ValueError("补丁上下文与当前文件不匹配。")
        cursor = start
        replacement: list[str] = []
        for line in hunk:
            if line.startswith(" "):
                replacement.append(line[1:])
                cursor += 1
            elif line.startswith("-"):
                if cursor >= len(old_lines) or old_lines[cursor] != line[1:]:
                    raise ValueError("补丁要删除的内容与当前文件不匹配。")
                cursor += 1
            elif line.startswith("+"):
                replacement.append(line[1:])
        old_lines[start:cursor] = replacement
        offset = start + len(replacement)
    return "".join(old_lines)


def _find_sequence(lines: list[str], wanted: list[str], start: int) -> int:
    if not wanted:
        return min(start, len(lines))
    for index in range(start, len(lines) - len(wanted) + 1):
        if lines[index:index + len(wanted)] == wanted:
            return index
    return -1
