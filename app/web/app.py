from __future__ import annotations

import asyncio
import json
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from app.agent.service import AgentService
from app.config import Settings
from app.tools.registry import ToolRegistry
from app.session_store import SessionStore


class MessageBody(BaseModel):
    prompt: str
    mode: str = "ask"


class ApprovalBody(BaseModel):
    allowed: bool


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
    store = SessionStore(cfg.session_file)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        for session_id, history_items in (await store.load()).items():
            if isinstance(session_id, str) and isinstance(history_items, list):
                sessions[session_id] = []
                session_histories[session_id] = history_items
        yield

    app = FastAPI(title="ApexCode", docs_url="/api/docs", lifespan=lifespan)

    async def publish(run: RunState, event: dict[str, Any]) -> None:
        if event.get("type") == "error":
            run.status = "failed"
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
        return {"workspace": str(cfg.workspace), "model": cfg.model, "configured": bool(cfg.api_key)}

    @app.get("/api/sessions")
    async def list_sessions() -> dict[str, Any]:
        return {"sessions": [{"session_id": key, "message_count": len(value)} for key, value in session_histories.items()]}

    @app.get("/api/workspace/tree")
    async def tree(path: str = ".") -> dict[str, Any]:
        registry = ToolRegistry(cfg, _never_approve)
        return await registry.call("list_files", {"path": path})

    @app.post("/api/sessions")
    async def create_session() -> dict[str, str]:
        session_id = uuid.uuid4().hex[:12]
        sessions[session_id] = []
        session_histories[session_id] = []
        return {"session_id": session_id}

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
        return {"accepted": True}

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
