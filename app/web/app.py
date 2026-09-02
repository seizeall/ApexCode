from __future__ import annotations

import asyncio
import json
import os
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator
from dotenv import set_key

from app.agent.service import AgentService
from app.config import Settings
from app.tools.registry import ToolRegistry
from app.session_store import SessionStore
from app.safety import safe_path, SafetyError


PREVIEW_EXCLUDED_DIRS = {".git", ".venv", "node_modules", "__pycache__", "tmp"}
PREVIEW_INTERNAL_ENTRIES = {"app/web/static/index.html"}
PREVIEW_FILE_SUFFIXES = {
    ".css", ".gif", ".html", ".ico", ".jpeg", ".jpg", ".js", ".json", ".map",
    ".mjs", ".mp4", ".png", ".svg", ".ttf", ".txt", ".wasm", ".webm",
    ".webmanifest", ".woff", ".woff2", ".xml",
}


def preview_candidates(workspace: Path) -> list[dict[str, str]]:
    """Find renderable HTML entry points without traversing dependency or hidden trees."""
    root = workspace.resolve()
    found: list[Path] = []
    if not root.is_dir():
        return []
    for directory, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name not in PREVIEW_EXCLUDED_DIRS and not name.startswith(".")]
        if "index.html" in filenames:
            found.append(Path(directory) / "index.html")
            if len(found) >= 50:
                break

    def priority(path: Path) -> tuple[int, int, str]:
        relative = path.relative_to(root)
        parent_name = relative.parent.name.lower()
        build_rank = {"dist": 0, "build": 1, "out": 2, "public": 3}.get(parent_name, 4)
        root_rank = 0 if relative.as_posix() == "index.html" else 1
        return (build_rank, root_rank, relative.as_posix().lower())

    candidates = []
    for path in sorted(found, key=priority):
        relative = path.relative_to(root).as_posix()
        if relative in PREVIEW_INTERNAL_ENTRIES:
            continue
        candidates.append({"path": relative, "url": f"/preview/{quote(relative, safe='/')}"})
    return candidates


def preview_file_allowed(workspace: Path, target: Path) -> bool:
    relative = target.relative_to(workspace.resolve())
    return (
        target.suffix.lower() in PREVIEW_FILE_SUFFIXES
        and not any(part.startswith(".") or part in PREVIEW_EXCLUDED_DIRS for part in relative.parts)
    )


class MessageBody(BaseModel):
    prompt: str
    mode: str = "full"


class ApprovalBody(BaseModel):
    allowed: bool


class SessionUpdateBody(BaseModel):
    name: str


class SessionCreateBody(BaseModel):
    name: str = ""


class ConfigUpdateBody(BaseModel):
    base_url: str = Field(min_length=1, max_length=500)
    api_key: str = Field(default="", max_length=1000)
    model: str = Field(min_length=1, max_length=200)
    workspace: str = Field(min_length=1, max_length=1000)

    @field_validator("base_url", "api_key", "model", "workspace", mode="before")
    @classmethod
    def strip_values(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("API Base URL 必须是有效的 http 或 https 地址。")
        return value.rstrip("/")

    @field_validator("model")
    @classmethod
    def validate_model(cls, value: str) -> str:
        if not value or any(char in value for char in "\r\n"):
            raise ValueError("模型名称不能为空或包含换行。")
        return value

    @field_validator("workspace")
    @classmethod
    def validate_workspace(cls, value: str) -> str:
        if any(char in value for char in "\r\n\x00"):
            raise ValueError("工作区路径包含无效字符。")
        return value


@dataclass
class RunState:
    run_id: str
    session_id: str
    queue: asyncio.Queue[dict[str, Any] | None] = field(default_factory=asyncio.Queue)
    approvals: dict[str, asyncio.Future[bool]] = field(default_factory=dict)
    status: str = "queued"
    history: list[dict[str, Any]] = field(default_factory=list)
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    task: asyncio.Task[Any] | None = None


async def _never_approve(*_args: Any) -> bool:
    return False


def create_app(settings: Settings | None = None) -> FastAPI:
    cfg = settings or Settings.from_env()
    runs: dict[str, RunState] = {}
    sessions: dict[str, list[str]] = {}
    session_histories: dict[str, list[dict[str, Any]]] = {}
    session_names: dict[str, str] = {}
    store = SessionStore(cfg.session_file)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        for session_id, history_items in (await store.load()).items():
            if isinstance(session_id, str) and isinstance(history_items, list):
                sessions[session_id] = []
                session_histories[session_id] = history_items
        session_names.update(await store.metadata())
        yield

    app = FastAPI(title="ApexCode", docs_url="/api/docs", lifespan=lifespan)

    @app.middleware("http")
    async def isolate_preview_origin(request: Request, call_next):
        # The embedded renderer uses localhost while the workbench uses 127.0.0.1.
        # Keep generated page scripts away from Agent management APIs.
        if request.url.hostname == "localhost" and request.url.path.startswith("/api"):
            return JSONResponse({"detail": "预览页面不能访问 Agent 管理接口。"}, status_code=403)
        return await call_next(request)

    async def publish(run: RunState, event: dict[str, Any]) -> None:
        if event.get("type") == "error":
            run.status = "failed"
        elif event.get("type") == "approval_required":
            run.status = "waiting"
        elif event.get("type") in {"step", "tool_start", "approval_auto"}:
            run.status = "running"
        elif event.get("type") == "assistant":
            run.status = "running"
        await run.queue.put(event)

    async def worker(run: RunState, prompt: str, mode: str) -> None:
        run.status = "running"

        async def approve(kind: str, payload: dict[str, Any]) -> bool:
            if mode == "full":
                await publish(run, {"type": "approval_auto", "action": kind, "payload": payload})
                return True
            approval_id = uuid.uuid4().hex[:10]
            future: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
            run.approvals[approval_id] = future
            await publish(run, {"type": "approval_required", "approval_id": approval_id, "action": kind, "payload": payload})
            try:
                while not future.done():
                    if run.cancel_event.is_set():
                        return False
                    try:
                        return await asyncio.wait_for(asyncio.shield(future), timeout=.5)
                    except asyncio.TimeoutError:
                        continue
                return future.result()
            finally:
                run.approvals.pop(approval_id, None)

        async def emit(event: dict[str, Any]) -> None:
            await publish(run, event)

        try:
            result, run.history = await AgentService(cfg).run(prompt, approve, emit, session_histories.get(run.session_id), mode=mode, cancel_event=run.cancel_event)
            session_histories[run.session_id] = run.history
            await store.save(run.session_id, run.history)
            if run.cancel_event.is_set() or result == "任务已取消。":
                run.status = "cancelled"
            else:
                failed = result.startswith(("模型请求失败", "未配置", "工具调用次数"))
                run.status = "failed" if failed else "completed"
        except asyncio.CancelledError:
            run.cancel_event.set()
            run.status = "cancelled"
            result = "任务已取消。"
        except Exception as exc:
            run.status = "failed"
            result = f"任务执行失败：{exc}"
            await publish(run, {"type": "error", "message": result})
        finally:
            await publish(run, {"type": "done", "status": run.status, "message": result})
            await run.queue.put(None)

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(Path(__file__).parent / "static" / "index.html")

    @app.get("/static/{filename}")
    async def static_file(filename: str) -> FileResponse:
        path = Path(__file__).parent / "static" / filename
        if not path.is_file():
            raise HTTPException(404, "静态文件不存在。")
        return FileResponse(path)

    @app.get("/api/preview/candidates")
    async def list_preview_candidates() -> dict[str, Any]:
        return {"ok": True, "candidates": preview_candidates(cfg.workspace)}

    @app.get("/preview", include_in_schema=False)
    @app.get("/preview/", include_in_schema=False)
    async def preview_default() -> RedirectResponse:
        candidates = preview_candidates(cfg.workspace)
        if not candidates:
            raise HTTPException(404, "当前工作区没有可预览的 index.html。")
        return RedirectResponse(candidates[0]["url"])

    @app.get("/preview/{path:path}", include_in_schema=False)
    async def preview_file(path: str) -> FileResponse:
        try:
            target = safe_path(cfg.workspace, path)
            if target.is_dir():
                target = safe_path(cfg.workspace, str(Path(path) / "index.html"))
            if not target.is_file() or not preview_file_allowed(cfg.workspace, target):
                raise ValueError("预览资源不存在或不允许访问。")
            roots = [(cfg.workspace / item["path"]).resolve().parent for item in preview_candidates(cfg.workspace)]
            if not any(target == root or root in target.parents for root in roots):
                raise ValueError("资源不属于可预览的网站目录。")
        except (OSError, SafetyError, ValueError):
            raise HTTPException(404, "预览资源不存在或不允许访问。") from None
        return FileResponse(target, headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})

    @app.get("/api/config")
    async def config() -> dict[str, Any]:
        return {
            "workspace": str(cfg.workspace),
            "model": cfg.model,
            "base_url": cfg.base_url,
            "configured": bool(cfg.api_key),
        }

    @app.post("/api/config")
    async def update_config(body: ConfigUpdateBody) -> dict[str, Any]:
        nonlocal cfg
        if any(item.status in {"queued", "running", "waiting"} for item in runs.values()):
            raise HTTPException(409, "任务执行中，停止或完成任务后再切换工作区。")
        api_key = body.api_key or cfg.api_key
        if not api_key:
            raise HTTPException(400, "首次配置必须填写 API Key。")
        workspace = Path(body.workspace).expanduser()
        if not workspace.is_absolute():
            raise HTTPException(400, "工作区必须填写绝对路径。")
        workspace = workspace.resolve()
        try:
            workspace.mkdir(parents=True, exist_ok=True)
            probe = workspace / ".apexcode-write-test"
            probe.touch(exist_ok=False)
            probe.unlink()
        except OSError as exc:
            raise HTTPException(400, f"工作区不可写：{exc}") from exc
        config_file = Path(cfg.config_file or (cfg.workspace / ".env"))
        try:
            config_file.parent.mkdir(parents=True, exist_ok=True)
            config_file.touch(exist_ok=True)
            set_key(str(config_file), "CODING_AGENT_API_KEY", api_key, quote_mode="always")
            set_key(str(config_file), "CODING_AGENT_BASE_URL", body.base_url, quote_mode="always")
            set_key(str(config_file), "CODING_AGENT_MODEL", body.model, quote_mode="always")
            set_key(str(config_file), "CODING_AGENT_WORKSPACE", str(workspace), quote_mode="always")
        except OSError as exc:
            raise HTTPException(500, f"无法保存 API 配置：{exc}") from exc
        from dataclasses import replace
        cfg = replace(cfg, api_key=api_key, base_url=body.base_url, model=body.model, workspace=workspace, config_file=config_file)
        return {"configured": True, "base_url": cfg.base_url, "model": cfg.model, "workspace": str(cfg.workspace)}

    @app.get("/api/sessions")
    async def list_sessions() -> dict[str, Any]:
        result = []
        for key, value in session_histories.items():
            first_prompt = next((str(item.get("content", "")) for item in value if item.get("role") == "user"), "")
            title = session_names.get(key, "").strip() or first_prompt[:42] or "新会话"
            question_count = sum(1 for item in session_histories.get(key, []) if item.get("role") == "user")
            result.append({"session_id": key, "message_count": question_count, "title": title, "name": session_names.get(key, "")})
        return {"sessions": result}

    @app.get("/api/workspace/tree")
    async def tree(path: str = ".", depth: int = 2) -> dict[str, Any]:
        if depth < 0 or depth > 4:
            raise HTTPException(400, "目录展开层级必须在 0 到 4 之间。")
        try:
            root = safe_path(cfg.workspace, path)
            if not root.is_dir():
                raise ValueError("目标不是目录。")
            def walk(directory: Path, remaining: int) -> list[dict[str, Any]]:
                entries: list[dict[str, Any]] = []
                for item in sorted(directory.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))[:200]:
                    if item.name.startswith(".") or item.name in {"tmp", "node_modules", "__pycache__"}:
                        continue
                    record: dict[str, Any] = {"name": item.name, "type": "file" if item.is_file() else "directory", "path": str(item.relative_to(cfg.workspace))}
                    if item.is_dir() and remaining > 0:
                        record["children"] = walk(item, remaining - 1)
                    entries.append(record)
                return entries
            return {"ok": True, "path": str(root.relative_to(cfg.workspace) or "."), "entries": walk(root, depth)}
        except (OSError, SafetyError, ValueError) as exc:
            return {"ok": False, "error": str(exc)}

    @app.post("/api/sessions")
    async def create_session(body: SessionCreateBody | None = None) -> dict[str, str]:
        name = (body.name if body else "").strip()
        if len(name) > 80:
            raise HTTPException(400, "会话名称不能超过 80 个字符。")
        session_id = uuid.uuid4().hex[:12]
        sessions[session_id] = []
        session_histories[session_id] = []
        if name:
            session_names[session_id] = name
        await store.save(session_id, [])
        if name:
            await store.rename(session_id, name)
        return {"session_id": session_id}

    @app.patch("/api/sessions/{session_id}")
    async def rename_session(session_id: str, body: SessionUpdateBody) -> dict[str, Any]:
        if session_id not in sessions:
            raise HTTPException(404, "会话不存在。")
        name = body.name.strip()
        if not name:
            raise HTTPException(400, "会话名称不能为空。")
        if len(name) > 80:
            raise HTTPException(400, "会话名称不能超过 80 个字符。")
        session_names[session_id] = name
        await store.rename(session_id, name)
        return {"session_id": session_id, "name": name}

    @app.delete("/api/sessions/{session_id}")
    async def delete_session(session_id: str) -> dict[str, bool]:
        if session_id not in sessions:
            raise HTTPException(404, "会话不存在。")
        active = next((item for item in runs.values() if item.session_id == session_id and item.status in {"queued", "running", "waiting"}), None)
        if active:
            raise HTTPException(409, "任务执行中，完成或停止任务后再删除会话。")
        sessions.pop(session_id, None)
        session_histories.pop(session_id, None)
        session_names.pop(session_id, None)
        await store.delete(session_id)
        return {"deleted": True}

    @app.get("/api/sessions/{session_id}/history")
    async def history(session_id: str) -> dict[str, Any]:
        if session_id not in sessions:
            raise HTTPException(404, "会话不存在。")
        return {"session_id": session_id, "messages": session_histories.get(session_id, [])}

    @app.post("/api/sessions/{session_id}/messages")
    async def send_message(session_id: str, body: MessageBody) -> dict[str, str]:
        if session_id not in sessions:
            raise HTTPException(404, "会话不存在。")
        if not body.prompt.strip():
            raise HTTPException(400, "任务不能为空。")
        if body.mode not in {"full", "plan"}:
            raise HTTPException(400, "未知运行模式。")
        if len(body.prompt) > 20_000:
            raise HTTPException(413, "任务内容过长。")
        active = next((item for item in runs.values() if item.session_id == session_id and item.status in {"queued", "running", "waiting"}), None)
        if active:
            raise HTTPException(409, "当前会话已有任务在执行。")
        run_id = uuid.uuid4().hex[:12]
        run = RunState(run_id, session_id)
        runs[run_id] = run
        sessions[session_id].append(run_id)
        run.task = asyncio.create_task(worker(run, body.prompt.strip(), body.mode))
        return {"run_id": run_id}

    @app.post("/api/runs/{run_id}/cancel")
    async def cancel(run_id: str) -> dict[str, bool]:
        run = runs.get(run_id)
        if not run:
            raise HTTPException(404, "任务不存在。")
        run.cancel_event.set()
        if run.task and not run.task.done():
            run.task.cancel()
        return {"accepted": True}

    @app.get("/api/runs/{run_id}")
    async def run_status(run_id: str) -> dict[str, Any]:
        run = runs.get(run_id)
        if not run:
            raise HTTPException(404, "任务不存在。")
        return {"run_id": run.run_id, "session_id": run.session_id, "status": run.status}

    @app.get("/api/runs/{run_id}/events")
    async def events(run_id: str) -> StreamingResponse:
        run = runs.get(run_id)
        if not run:
            raise HTTPException(404, "任务不存在。")

        async def stream():
            yield f"data: {json.dumps({'type': 'status', 'status': run.status}, ensure_ascii=False)}\n\n"
            while True:
                item = await run.queue.get()
                if item is None:
                    break
                yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"

        return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.post("/api/runs/{run_id}/approvals/{approval_id}")
    async def approve(run_id: str, approval_id: str, body: ApprovalBody) -> dict[str, bool]:
        run = runs.get(run_id)
        future = run.approvals.get(approval_id) if run else None
        if not future:
            raise HTTPException(404, "确认请求不存在或已过期。")
        if not future.done():
            future.set_result(body.allowed)
        return {"accepted": True}

    return app


app = create_app()
