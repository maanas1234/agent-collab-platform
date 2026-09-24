"""Smoke test — connects like a real agent would, no LLM involved."""
import asyncio
import json

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


async def call(session, name, **kwargs):
    result = await session.call_tool(name, kwargs)
    if result.structuredContent is not None:
        return result.structuredContent
    return json.loads(result.content[0].text)


async def main():
    async with streamablehttp_client("http://localhost:8001/mcp") as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            joined = await call(session, "register_agent", display_name="TestAgent", agent_type="generic")
            print("joined:", joined)
            agent_id = joined["agent_id"]

            msg = await call(session, "post_message", agent_id=agent_id, text="Hello from test agent")
            print("post_message:", msg)

            task = await call(
                session, "propose_task", agent_id=agent_id,
                title="Build /shorten endpoint", description="POST endpoint", role="backend",
            )
            print("propose_task:", task)

            claim = await call(session, "claim_task", agent_id=agent_id, task_id=task["task_id"])
            print("claim_task:", claim)

            done = await call(session, "update_task_status", agent_id=agent_id, task_id=task["task_id"], status="done")
            print("update_task_status:", done)

            print("list_tasks:", await call(session, "list_tasks"))
            print("list_messages:", await call(session, "list_messages"))


asyncio.run(main())
