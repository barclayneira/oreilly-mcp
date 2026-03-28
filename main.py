from typing import Any
import httpx
from typing import Dict, List, Optional
from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from mcp.server.sse import SseServerTransport
from starlette.requests import Request
from starlette.routing import Mount, Route
from mcp.server import Server
import uvicorn
import os
import re
import yaml

mcp = FastMCP("oreilly-llm-connect")

API_BASE = "https://learning.oreilly.com/api/v2"
API_V1_BASE = "https://learning.oreilly.com/api/v1"
SEARCH_API_URL = f"{API_BASE}/search/"


def _get_headers() -> dict:
    return {"Authorization": f"Token {os.environ['ORM_JWT']}"}


def _strip_html(html: str) -> str:
    """Strip HTML tags and collapse whitespace for readable text."""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _make_ourn(content_id: str, content_type: str = "book") -> str:
    """Build an O'Reilly URN. content_type is 'book' or 'article'."""
    return f"urn:orm:{content_type}:{content_id}"


def _guess_content_type(content_id: str) -> str:
    """Guess content type from ID pattern. Articles typically have non-ISBN IDs."""
    # ISBNs are 10 or 13 digits starting with 97
    if re.match(r"^97[89]\d{10}$", content_id):
        return "book"
    # Could be either — try book first, fall back to article
    return "auto"


# ── Tool 1: Search (existing, cleaned up) ────────────────────

@mcp.tool()
async def search_content(
    query: str,
    formats: Optional[str] = None,
    topics: Optional[List[str]] = None,
    subjects: Optional[List[str]] = None,
    page: int = 0,
    include_facets: bool = False,
) -> Dict[str, Any]:
    """
    Search O'Reilly content and return relevant results with essential metadata.
    Use include_facets=true to discover available topics and subjects for filtering.
    formats: filter by content type e.g. "book", "video", "live-event", "course"
    topics: filter by topic slug e.g. "python", "machine-learning", "kubernetes"
    subjects: filter by subject slug e.g. "software-engineering", "data-science"
    """
    params = {
        "query": query,
        "include_facets": include_facets,
    }

    if formats:
        for i, fmt in enumerate(formats):
            params[f"formats[{i}]"] = fmt

    if topics:
        for i, topic in enumerate(topics):
            params[f"topics[{i}]"] = topic

    if subjects:
        for i, subject in enumerate(subjects):
            params[f"subjects[{i}]"] = subject

    if page > 0:
        params["page"] = page

    params["publishers[0]"] = "O'Reilly Media, Inc."

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                SEARCH_API_URL, params=params, headers=_get_headers()
            )

            if response.status_code == 400:
                error_data = response.json()
                return {
                    "error": f"Invalid search parameters: {error_data.get('error', 'Unknown error')}"
                }

            data = response.json()

            transformed_results = []
            for result in data.get("results", []):
                topics = [
                    t.get("slug") for t in result.get("topics_payload", [])
                ]
                transformed_results.append(
                    {
                        "id": result.get("archive_id"),
                        "title": result.get("title"),
                        "authors": result.get("authors", []),
                        "issued": result.get("issued", "")[:10],
                        "url": result.get("url"),
                        "web_url": result.get("web_url"),
                        "description": result.get("description"),
                        "popularity": result.get("popularity"),
                        "average_rating": result.get("average_rating"),
                        "topics": topics,
                    }
                )

            output: Dict[str, Any] = {"results": transformed_results}

            if include_facets:
                facets = data.get("facets", {})
                output["facets"] = {
                    "topics": [
                        {"slug": f.get("slug"), "count": f.get("count")}
                        for f in facets.get("topics", [])[:20]
                    ],
                    "subjects": [
                        {"slug": f.get("slug"), "count": f.get("count")}
                        for f in facets.get("subjects", [])[:20]
                    ],
                    "formats": [
                        {"slug": f.get("slug"), "count": f.get("count")}
                        for f in facets.get("formats", [])[:10]
                    ],
                }
                output["total_results"] = data.get("total", 0)
                output["page"] = data.get("page", 0)

            return yaml.dump(output, sort_keys=False)

    except httpx.RequestError as e:
        return {"error": f"Failed to connect to O'Reilly API: {str(e)}"}
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}


# ── Tool 2: Get book metadata and table of contents ──────────

@mcp.tool()
async def get_book_info(
    book_id: str,
) -> Dict[str, Any]:
    """
    Get detailed metadata and table of contents for an O'Reilly book or article.
    Use a book_id (ISBN) from search_content results (the 'id' field).
    Works for both books and articles — auto-detects the content type.
    Returns title, description, authors, chapters with reading times,
    and the book's table of contents.
    """
    # Try book first, fall back to article
    content_type = _guess_content_type(book_id)
    types_to_try = ["book", "article"] if content_type == "auto" else [content_type]

    try:
        async with httpx.AsyncClient() as client:
            meta_resp = None
            ourn = None
            for ct in types_to_try:
                ourn = _make_ourn(book_id, ct)
                meta_resp = await client.get(
                    f"{API_BASE}/epubs/{ourn}/",
                    headers=_get_headers(),
                    timeout=15.0,
                )
                if meta_resp.status_code == 200:
                    break

            if meta_resp is None or meta_resp.status_code != 200:
                return {"error": f"Content not found: {book_id} (tried {types_to_try})"}

            meta = meta_resp.json()

            # Get chapters
            chapters_resp = await client.get(
                f"{API_BASE}/epub-chapters/",
                params={"epub_identifier": ourn},
                headers=_get_headers(),
                timeout=15.0,
            )
            chapters = []
            if chapters_resp.status_code == 200:
                for ch in chapters_resp.json().get("results", []):
                    chapters.append({
                        "title": ch.get("title"),
                        "minutes": round(ch.get("minutes_required", 0), 1),
                        "pages": ch.get("virtual_pages"),
                        "reference_id": ch.get("reference_id"),
                    })

            # Build response
            description = meta.get("descriptions", {}).get("text/plain", "")
            if len(description) > 500:
                description = description[:500] + "..."

            result = {
                "title": meta.get("title"),
                "book_id": book_id,
                "isbn": meta.get("isbn"),
                "published": meta.get("publication_date"),
                "pages": meta.get("page_count"),
                "description": description,
                "web_url": f"https://learning.oreilly.com/library/view/{book_id}/",
                "chapters": chapters,
            }

            return yaml.dump(result, sort_keys=False)

    except Exception as e:
        return {"error": f"Failed to get book info: {str(e)}"}


# ── Tool 3: Read chapter content ─────────────────────────────

@mcp.tool()
async def read_chapter(
    book_id: str,
    chapter_file: str,
) -> Dict[str, Any]:
    """
    Read the full text content of a specific chapter from an O'Reilly book.
    Use book_id from search_content and chapter_file (e.g. 'ch06.html')
    from get_book_info's reference_id field.
    Returns the chapter text with HTML stripped for readability.
    """
    content_type = _guess_content_type(book_id)
    types_to_try = ["book", "article"] if content_type == "auto" else [content_type]

    try:
        async with httpx.AsyncClient() as client:
            resp = None
            ourn = None
            for ct in types_to_try:
                ourn = _make_ourn(book_id, ct)
                resp = await client.get(
                    f"{API_BASE}/epubs/{ourn}/files/{chapter_file}",
                    headers=_get_headers(),
                    timeout=30.0,
                )
                if resp.status_code == 200:
                    break

            if resp is None or resp.status_code != 200:
                return {
                    "error": (
                        f"Chapter not found: {chapter_file} in {book_id} "
                        f"(tried {types_to_try})"
                    )
                }

            html = resp.text
            text = _strip_html(html)

            # Include provenance
            web_url = f"https://learning.oreilly.com/library/view/{book_id}/{chapter_file}"

            # Truncate if very long to avoid overwhelming the context
            if len(text) > 50000:
                text = text[:50000] + f"\n\n[...truncated, {len(text)} chars total]"

            return {
                "book_id": book_id,
                "chapter": chapter_file,
                "web_url": web_url,
                "content_length": len(text),
                "content": text,
            }

    except Exception as e:
        return {"error": f"Failed to read chapter: {str(e)}"}


# ── Tool 4: Get table of contents ────────────────────────────

@mcp.tool()
async def get_table_of_contents(
    book_id: str,
) -> Dict[str, Any]:
    """
    Get the detailed table of contents for an O'Reilly book, including
    section-level headings and their hierarchy. More detailed than
    get_book_info's chapter list. Use book_id from search_content results.
    """
    content_type = _guess_content_type(book_id)
    types_to_try = ["book", "article"] if content_type == "auto" else [content_type]

    try:
        async with httpx.AsyncClient() as client:
            resp = None
            for ct in types_to_try:
                ourn = _make_ourn(book_id, ct)
                resp = await client.get(
                    f"{API_BASE}/epubs/{ourn}/table-of-contents/",
                    headers=_get_headers(),
                    timeout=15.0,
                )
                if resp.status_code == 200:
                    break

            if resp is None or resp.status_code != 200:
                return {"error": f"TOC not found for {book_id} (tried {types_to_try})"}

            toc = resp.json()

            entries = []
            for item in toc:
                # Extract the chapter filename from the URL
                url = item.get("url", "")
                filename = url.split("/")[-2] if url else ""
                # Extract reference from filename (e.g., 'chapter:ch06.html' -> 'ch06.html')
                ref_match = re.search(r"chapter:([^/]+)", url)
                ref = ref_match.group(1) if ref_match else ""

                entries.append({
                    "label": item.get("label", "").strip(),
                    "depth": item.get("depth", 0),
                    "chapter_file": ref,
                })

            return yaml.dump(
                {"book_id": book_id, "entries": entries},
                sort_keys=False,
            )

    except Exception as e:
        return {"error": f"Failed to get TOC: {str(e)}"}


# ── Tool 5: Get user highlights/annotations ───────────────────

@mcp.tool()
async def get_annotations(
    page_size: int = 100,
) -> Dict[str, Any]:
    """
    Get your O'Reilly highlights and annotations (bookmarks, notes).
    Returns all saved highlights with the source book/chapter info.
    Useful for finding content you've previously marked as important.
    """
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{API_V1_BASE}/annotations/all/",
                params={"page_size": page_size},
                headers=_get_headers(),
                timeout=15.0,
            )

            if resp.status_code != 200:
                return {"error": f"Annotations not available (HTTP {resp.status_code})"}

            data = resp.json()

            annotations = []
            for ann in data.get("results", data if isinstance(data, list) else []):
                annotations.append({
                    "highlight": ann.get("highlight", ""),
                    "note": ann.get("note", ""),
                    "book_title": ann.get("title", ""),
                    "chapter": ann.get("chapter_title", ""),
                    "book_url": ann.get("book_url", ""),
                    "created": ann.get("created_time", ""),
                })

            return yaml.dump(
                {"count": len(annotations), "annotations": annotations},
                sort_keys=False,
            )

    except Exception as e:
        return {"error": f"Failed to get annotations: {str(e)}"}


# ── SSE Server (unchanged) ───────────────────────────────────

def create_starlette_app(mcp_server: Server, *, debug: bool = False) -> Starlette:
    """Create a Starlette application that can serve the provided mcp server with SSE."""
    sse = SseServerTransport("/messages/")

    async def handle_sse(request: Request) -> None:
        async with sse.connect_sse(
            request.scope,
            request.receive,
            request._send,  # noqa: SLF001
        ) as (read_stream, write_stream):
            await mcp_server.run(
                read_stream,
                write_stream,
                mcp_server.create_initialization_options(),
            )

    return Starlette(
        debug=debug,
        routes=[
            Route("/sse", endpoint=handle_sse),
            Mount("/messages/", app=sse.handle_post_message),
        ],
    )


if __name__ == "__main__":
    mcp_server = mcp._mcp_server  # noqa: WPS437

    import argparse

    parser = argparse.ArgumentParser(description="Run MCP SSE-based server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8192, help="Port to listen on")
    args = parser.parse_args()

    starlette_app = create_starlette_app(mcp_server, debug=True)
    uvicorn.run(starlette_app, host=args.host, port=args.port)
