from __future__ import annotations

import argparse
import asyncio
import json

from app.agent.service import AgentService
from app.config import Settings


async def _run(prompt: str, mode: str) -> None:
    settings = Settings.from_env()
    service = AgentService(settings)

    async def approve(kind: str, payload: dict) -> bool:
        if mode == "full":
            print("自动允许：", kind)
            return True
        print("\n需要确认：", kind)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return input("允许这一次？[y/N] ").strip().lower() == "y"

    async def emit(event: dict) -> None:
        kind = event.get("type")
        if kind in {"step", "assistant", "error"}:
            print(f"\n[{kind}] {event.get('message', '')}")
        elif kind == "tool_start":
            print(f"\n[tool] {event['tool']} {json.dumps(event['arguments'], ensure_ascii=False)}")
        elif kind == "tool_result":
            print(f"[result] {json.dumps(event['result'], ensure_ascii=False)[:2000]}")

    await service.run(prompt, approve, emit, mode=mode)


def main() -> None:
    parser = argparse.ArgumentParser(description="本地 coding agent")
    parser.add_argument("prompt", nargs="?", help="要交给 Agent 的编程任务")
    parser.add_argument("--mode", choices=("full", "plan", "ask"), default="ask", help="运行模式：full 完全、plan 计划、ask 询问")
    args = parser.parse_args()
    prompt = args.prompt or input("任务：")
    asyncio.run(_run(prompt, args.mode))


if __name__ == "__main__":
    main()
