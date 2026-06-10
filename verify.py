#!/usr/bin/env python3
"""驗證 MCP 伺服器安裝是否正確"""

import asyncio
from mcp_server.server import mcp

print('Server:', mcp.name)
tools = asyncio.run(mcp.list_tools())
print('Tools:', [t.name for t in tools])
assert len(tools) == 13, f'Expected 13 tools, got {len(tools)}'
print('Setup OK')
