from __future__ import annotations

import asyncio
import json
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from app.agent.service import AgentService
from app.config import Settings
from app.tools.registry import ToolRegistry
from app.session_store import SessionStore
from app.safety import safe_path, SafetyError


class MessageBody(BaseModel):
    prompt: str
    mode: str = "ask"


class ApprovalBody(BaseModel):
    allowed: bool


class SessionUpdateBody(BaseModel):
    name: str


class SessionCreateBody(BaseModel):
    name: str = ""


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
                failed = result.startswith(("模型请求失败", "未配置", "达到最大", "工具调用次数"))
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

    @app.get("/api/config")
    async def config() -> dict[str, Any]:
        return {
            "workspace": str(cfg.workspace),
            "model": cfg.model,
            "configured": bool(cfg.api_key),
            "upload_limits": {
                "max_files": 200,
                "max_file_bytes": cfg.max_upload_file_bytes,
                "max_total_bytes": cfg.max_upload_total_bytes,
            },
        }

    @app.get("/api/sessions")
    async def list_sessions() -> dict[str, Any]:
        result = []
        for key, value in session_histories.items():
            first_prompt = next((str(item.get("content", "")) for item in value if item.get("role") == "user"), "")
            title = session_names.get(key, "").strip() or first_prompt[:42] or "新会话"
            result.append({"session_id": key, "message_count": len(value), "title": title, "name": session_names.get(key, "")})
        return {"sessions": result}

    @app.post("/api/workspace/upload")
    async def upload_workspace_files(files: list[UploadFile] = File(...), paths: list[str] = Form(default=[])) -> dict[str, Any]:
        """接收用户主动选择的文件；路径始终限制在当前工作区内。"""
        if not files:
            raise HTTPException(400, "没有选择文件。")
        if len(files) > 200:
            raise HTTPException(413, "一次最多上传 200 个文件。")
        uploaded: list[dict[str, Any]] = []
        pending: list[tuple[Path, str, bytes]] = []
        total_bytes = 0
        max_total = cfg.max_upload_total_bytes
        for index, upload_file in enumerate(files):
            relative = paths[index] if index < len(paths) and paths[index].strip() else (upload_file.filename or "")
            relative = relative.replace("\\", "/").lstrip("/")
            if not relative or relative.endswith("/"):
                raise HTTPException(400, "上传文件缺少有效路径。")
            try:
                destination = safe_path(cfg.workspace, relative)
            except SafetyError as exc:
                raise HTTPException(400, str(exc)) from exc
            content = await upload_file.read(cfg.max_upload_file_bytes + 1)
            if len(content) > cfg.max_upload_file_bytes:
                raise HTTPException(413, f"文件超过大小限制：{relative}")
            total_bytes += len(content)
            if total_bytes > max_total:
                raise HTTPException(413, "本次上传总大小超过限制。")
            pending.append((destination, relative, content))
        for destination, relative, content in pending:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
            uploaded.append({"path": relative, "bytes": len(content)})
        return {"ok": True, "files": uploaded}

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
        if body.mode not in {"full", "plan", "ask"}:
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
