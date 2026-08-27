from __future__ import annotations

import asyncio
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable

from app.config import Settings
from app.safety import SafetyError, safe_path, validate_command


Approval = Callable[[str, dict[str, Any]], Awaitable[bool]]


@dataclass
class ToolContext:
    settings: Settings
    approve: Approval


class ToolRegistry:
    def __init__(self, settings: Settings, approve: Approval) -> None:
        self.context = ToolContext(settings, approve)
        self._tools = {
            "list_files": self._list_files,
            "read_file": self._read_file,
            "search_text": self._search_text,
            "write_file": self._write_file,
            "run_command": self._run_command,
        }

    def schemas(self) -> list[dict[str, Any]]:
        return [
            {"type": "function", "function": {"name": "list_files", "description": "列出工作区内的文件和目录。", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": []}}},
            {"type": "function", "function": {"name": "read_file", "description": "读取工作区内的文本文件。", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
            {"type": "function", "function": {"name": "search_text", "description": "在工作区文本文件中搜索字符串。", "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "path": {"type": "string"}}, "required": ["query"]}}},
            {"type": "function", "function": {"name": "write_file", "description": "创建或覆盖工作区内的文本文件。", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}}},
            {"type": "function", "function": {"name": "run_command", "description": "在工作区内运行一条开发命令。", "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}}},
        ]

    async def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        fn = self._tools.get(name)
        if not fn:
            return {"ok": False, "error": f"未知工具：{name}"}
        try:
            return await fn(arguments)
        except (OSError, UnicodeError, SafetyError, ValueError) as exc:
            return {"ok": False, "error": str(exc)}

    async def _list_files(self, args: dict[str, Any]) -> dict[str, Any]:
        root = safe_path(self.context.settings.workspace, args.get("path", "."))
        if not root.exists():
            raise ValueError("目录不存在。")
        if not root.is_dir():
            raise ValueError("目标不是目录。")
        entries = []
        for item in sorted(root.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))[:200]:
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
        hits = []
        for path in root.rglob("*"):
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
        allowed = await self.context.approve("write_file", {"path": str(path.relative_to(self.context.settings.workspace)), "content": content})
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
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self.context.settings.command_timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return {"ok": False, "error": "命令执行超时。", "timeout": True}
        return {"ok": proc.returncode == 0, "returncode": proc.returncode, "stdout": stdout.decode(errors="replace")[-8_000:], "stderr": stderr.decode(errors="replace")[-8_000:]}
