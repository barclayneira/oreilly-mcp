"""Stdio wrapper for the O'Reilly MCP server (for Claude Code integration)."""
from main import mcp

if __name__ == "__main__":
    mcp.run(transport="stdio")
