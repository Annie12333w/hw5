"""Connects the backend to the campus-customs MCP server over stdio.

All shop data and every database write goes through these MCP tools. The
backend has no shop-tools layer of its own.
"""

import json
import os
import sys
from contextlib import AsyncExitStack
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from .config import DRAFTS_PATH, INCOMING_PATH, MCP_SERVER_SCRIPT, REQUESTS_PATH, WORKING_DB


class ShopMCP:
    def __init__(self) -> None:
        self._stack = AsyncExitStack()
        self.session: ClientSession | None = None
        self.tools: dict[str, Any] = {}

    async def __aenter__(self) -> "ShopMCP":
        env = {**os.environ,
               "CAMPUS_DB_PATH": str(WORKING_DB),
               "CAMPUS_DRAFTS_PATH": str(DRAFTS_PATH),
               "CAMPUS_REQUESTS_PATH": str(REQUESTS_PATH),
               "CAMPUS_INCOMING_PATH": str(INCOMING_PATH)}
        params = StdioServerParameters(command=sys.executable, args=[str(MCP_SERVER_SCRIPT)], env=env)
        read, write = await self._stack.enter_async_context(stdio_client(params))
        self.session = await self._stack.enter_async_context(ClientSession(read, write))
        await self.session.initialize()
        listed = await self.session.list_tools()
        self.tools = {t.name: t for t in listed.tools}
        return self

    async def __aexit__(self, *exc) -> None:
        await self._stack.aclose()

    def input_schema(self, name: str) -> dict:
        tool = self.tools[name]
        return dict(getattr(tool, "inputSchema", None) or getattr(tool, "input_schema", None) or {})

    def description(self, name: str) -> str:
        return self.tools[name].description or ""

    async def call(self, name: str, arguments: dict) -> tuple[bool, Any]:
        """Call an MCP tool. Returns (ok, result) where result is parsed JSON when possible."""
        res = await self.session.call_tool(name, arguments)
        is_error = bool(getattr(res, "isError", None) or getattr(res, "is_error", None))
        structured = getattr(res, "structuredContent", None) or getattr(res, "structured_content", None)
        if structured is not None:
            # FastMCP wraps non-object returns as {"result": ...}
            result = structured.get("result", structured) if set(structured) == {"result"} else structured
        else:
            text = "".join(getattr(c, "text", "") for c in res.content)
            try:
                result = json.loads(text)
            except (json.JSONDecodeError, TypeError):
                result = text
        # A tool refusal ({"ok": false, ...}) is a valid answer the agent must read, so ok stays True.
        return (not is_error), result
