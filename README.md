# O'Reilly MCP Server

An [MCP](https://modelcontextprotocol.io/) server for the [O'Reilly Learning Platform](https://learning.oreilly.com/) that lets AI assistants search, browse, and read O'Reilly books, articles, and your personal annotations.

> **Requires an O'Reilly Learning Platform subscription.**

Built on [odewahn/orm-discovery-mcp](https://github.com/odewahn/orm-discovery-mcp) by Andrew Odewahn.

## Tools

| Tool | Description |
|------|-------------|
| `search_content` | Search the O'Reilly library by query, format, topic, or subject. Supports pagination and faceted filtering. |
| `get_book_info` | Get metadata, description, and chapter list for a book or article. |
| `get_table_of_contents` | Get the detailed, hierarchical table of contents for a book. |
| `read_chapter` | Read the full text of a specific chapter. |
| `get_annotations` | Retrieve your personal highlights and notes. |

## Setup

### 1. Get your API token

Your O'Reilly API token can be found at: [learning.oreilly.com/apidocs/mcp/content](https://learning.oreilly.com/apidocs/mcp/content/)

### 2. Install for Claude Code

```bash
claude mcp add oreilly \
  -s user \
  -e ORM_JWT=YOUR_TOKEN_HERE \
  -- uv run --with "httpx,mcp[cli],pyyaml" python main.py
```

Or clone and install locally:

```bash
git clone https://github.com/barclayneira/oreilly-mcp.git
cd oreilly-mcp
uv sync

claude mcp add oreilly \
  -s user \
  -e ORM_JWT=YOUR_TOKEN_HERE \
  -- /path/to/oreilly-mcp/.venv/bin/python /path/to/oreilly-mcp/stdio_server.py
```

### 3. Install for other MCP clients (SSE mode)

```bash
git clone https://github.com/barclayneira/oreilly-mcp.git
cd oreilly-mcp
uv sync

ORM_JWT=YOUR_TOKEN_HERE uv run main.py --port 8192
```

The SSE endpoint will be available at `http://localhost:8192/sse`.

## Usage Examples

**Search for books on a topic:**
> "Search O'Reilly for books about building AI agents"

**Browse a book's chapters:**
> "Show me the table of contents for AI Engineering by Chip Huyen"

**Read a specific chapter:**
> "Read the chapter on RAG and Agents from AI Engineering"

**Find your highlights:**
> "What have I highlighted recently on O'Reilly?"

## Differences from the Original

This fork extends [odewahn/orm-discovery-mcp](https://github.com/odewahn/orm-discovery-mcp) with:

- **4 new tools**: book metadata, table of contents, chapter reading, and annotations
- **Enhanced search**: topic/subject filtering, pagination, and faceted discovery
- **Article support**: auto-detects books vs. articles by ID format
- **stdio transport**: works with Claude Code via `claude mcp add`
- **Provenance metadata**: all responses include source URLs for citation

## License

MIT. See [LICENSE](LICENSE).
