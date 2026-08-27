from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from app.agent.service import AgentService
from app.config import Settings
from app.tools.registry import ToolRegistry


class MessageBody(BaseModel):
    prompt: str


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


async def _never_approve(*_args: Any) -> bool:
    return False


def create_app(settings: Settings | None = None) -> FastAPI:
    cfg = settings or Settings.from_env()
    app = FastAPI(title="ApexCode", docs_url="/api/docs")
    runs: dict[str, RunState] = {}
    sessions: dict[str, list[str]] = {}
    session_histories: dict[str, list[dict[str, Any]]] = {}

    async def publish(run: RunState, event: dict[str, Any]) -> None:
        if event.get("type") == "error":
            run.status = "failed"
        elif event.get("type") == "assistant":
            run.status = "running"
        await run.queue.put(event)

    async def worker(run: RunState, prompt: str) -> None:
        run.status = "running"

        async def approve(kind: str, payload: dict[str, Any]) -> bool:
            approval_id = uuid.uuid4().hex[:10]
            future: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
            run.approvals[approval_id] = future
            await publish(run, {"type": "approval_required", "approval_id": approval_id, "action": kind, "payload": payload})
            try:
                return await asyncio.wait_for(future, timeout=300)
            except asyncio.TimeoutError:
                return False
            finally:
                run.approvals.pop(approval_id, None)

        async def emit(event: dict[str, Any]) -> None:
            await publish(run, event)

        result, run.history = await AgentService(cfg).run(prompt, approve, emit, session_histories.get(run.session_id))
        session_histories[run.session_id] = run.history
        failed = result.startswith(("模型请求失败", "未配置", "达到最大"))
        run.status = "failed" if failed else "completed"
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

    @app.post("/api/sessions/{session_id}/messages")
    async def send_message(session_id: str, body: MessageBody) -> dict[str, str]:
        if session_id not in sessions:
            raise HTTPException(404, "会话不存在。")
        if not body.prompt.strip():
            raise HTTPException(400, "任务不能为空。")
        run_id = uuid.uuid4().hex[:12]
        run = RunState(run_id, session_id)
        runs[run_id] = run
        sessions[session_id].append(run_id)
        asyncio.create_task(worker(run, body.prompt.strip()))
        return {"run_id": run_id}

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
