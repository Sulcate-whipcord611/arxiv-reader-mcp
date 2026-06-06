import re
from io import BytesIO
import httpx
from pdfminer.high_level import extract_text
from mcp.server.fastmcp import FastMCP
from .arxiv_api import search, get_by_id, get_recent, ArxivError

server = FastMCP(
    "arxiv-mcp-server",
    instructions="Search and retrieve papers from arXiv.",
)

_DATE_PATTERN = re.compile(r"^\d{10,12}$")


def _validate_max_results(v: int) -> str | None:
    if v < 1:
        return "max_results must be at least 1"
    if v > 30000:
        return "max_results cannot exceed 30000 (arXiv API limit)"
    return None


def _validate_date(v: str | None, name: str) -> str | None:
    if v is not None and not _DATE_PATTERN.match(v):
        return f"{name} must be in YYYYMMDDHHMM format (e.g. 202401010000)"
    return None


def _fmt(entries: list[dict]) -> str:
    lines = []
    for i, r in enumerate(entries, 1):
        lines.append(f"{i}. {r['title']}")
        lines.append(f"   ID: {r['id'].removeprefix('http://arxiv.org/abs/')}")
        lines.append(f"   Authors: {', '.join(r['authors'])}")
        lines.append(f"   Published: {r['published']}")
        if r["pdf_url"]:
            lines.append(f"   PDF: {r['pdf_url']}")
        lines.append("")
    return "\n".join(lines)


@server.tool(
    description="Search arXiv papers by keyword, author, category, and/or date range. "
    "Use when the user wants to find papers matching specific terms, by a specific author, "
    "in a specific category, or within a date range. Supports Boolean-like searches via keyword. "
    "Returns a numbered list with title, arXiv ID, authors, publication date, and PDF link.",
)
def search_arxiv(
    keyword: str | None = None,
    author: str | None = None,
    category: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    max_results: int = 10,
    start: int = 0,
) -> str:
    if not any([keyword, author, category, date_from, date_to]):
        return "Error: Provide at least one of: keyword, author, category, date_from, date_to"

    err = _validate_max_results(max_results)
    if err:
        return f"Error: {err}"

    if start < 0:
        return "Error: start must be 0 or greater"

    err = _validate_date(date_from, "date_from")
    if err:
        return f"Error: {err}"
    err = _validate_date(date_to, "date_to")
    if err:
        return f"Error: {err}"

    try:
        results = search(
            keyword=keyword,
            author=author,
            category=category,
            date_from=date_from,
            date_to=date_to,
            max_results=max_results,
            start=start,
        )
    except ArxivError as e:
        return f"Error: {e}"
    if not results:
        return "No results found."
    return _fmt(results)


@server.tool(
    description="Fetch a single paper by its arXiv ID (e.g. 2301.07041). "
    "Use when the user provides a specific arXiv ID and wants full metadata including "
    "title, authors, publication date, abstract, and PDF link. "
    "IDs can be with or without version suffix (e.g. 2301.07041v2).",
)
def get_paper(arxiv_id: str) -> str:
    if not arxiv_id or not arxiv_id.strip():
        return "Error: arxiv_id must not be empty"
    try:
        result = get_by_id(arxiv_id.strip())
    except ArxivError as e:
        return f"Error: {e}"
    if not result:
        return f"Error: No paper found with ID '{arxiv_id}'."
    return (
        f"Title: {result['title']}\n"
        f"ID: {result['id'].removeprefix('http://arxiv.org/abs/')}\n"
        f"Authors: {', '.join(result['authors'])}\n"
        f"Published: {result['published']}\n"
        f"Abstract: {result['abstract']}\n"
        f"PDF: {result['pdf_url']}"
    )


@server.tool(
    description="Get the most recent papers in a given category (e.g. cs.AI, quant-ph). "
    "Use when the user wants to see the latest submissions in a specific arXiv category, "
    "sorted by submission date (newest first). Ideal for 'what is new' style queries.",
)
def get_recent(category: str, max_results: int = 10) -> str:
    if not category or not category.strip():
        return "Error: category must not be empty (e.g. cs.AI, quant-ph)"

    err = _validate_max_results(max_results)
    if err:
        return f"Error: {err}"

    try:
        results = get_recent(category.strip(), max_results=max_results)
    except ArxivError as e:
        return f"Error: {e}"
    if not results:
        return f"No recent papers found in category '{category}'."
    return _fmt(results)


@server.tool(
    description="Search papers by query text, with optional category filter and date range. "
    "Simpler than search_arxiv - just a search query plus optional category and date_from. "
    "Use when the user provides a natural language query like 'papers about transformers' "
    "and optionally a category or start date. The query searches across all fields (title, abstract, authors).",
)
def search_papers(
    query: str,
    category: str | None = None,
    max_results: int = 10,
    date_from: str | None = None,
) -> str:
    if not query or not query.strip():
        return "Error: query must not be empty"

    if category is not None and not category.strip():
        return "Error: if provided, category must not be empty"

    err = _validate_max_results(max_results)
    if err:
        return f"Error: {err}"

    err = _validate_date(date_from, "date_from")
    if err:
        return f"Error: {err}"

    try:
        results = search(
            keyword=query.strip(),
            category=category.strip() if category else None,
            max_results=max_results,
            date_from=date_from,
        )
    except ArxivError as e:
        return f"Error: {e}"
    if not results:
        return "No results found."
    return _fmt(results)


@server.tool(
    description="Download the PDF for a given arXiv ID and extract its full text content. "
    "Use when the user needs to read the full paper text, not just the abstract. "
    "The arXiv ID is required (e.g. 2301.07041). Returns the extracted plain text from the PDF, "
    "which may contain formatting artifacts inherent to PDF text extraction.",
)
def fetch_pdf(arxiv_id: str) -> str:
    if not arxiv_id or not arxiv_id.strip():
        return "Error: arxiv_id must not be empty"

    aid = arxiv_id.strip()
    try:
        paper = get_by_id(aid)
    except ArxivError as e:
        return f"Error: {e}"
    if not paper:
        return f"Error: No paper found with ID '{aid}'."
    if not paper["pdf_url"]:
        return f"Error: No PDF URL available for ID '{aid}'."
    try:
        response = httpx.get(paper["pdf_url"], timeout=60, follow_redirects=True)
        response.raise_for_status()
    except httpx.TimeoutException:
        return "Error: PDF download timed out"
    except httpx.ConnectError:
        return "Error: Could not connect to download PDF"
    except httpx.HTTPStatusError as e:
        return f"Error: HTTP {e.response.status_code} downloading PDF"
    try:
        text = extract_text(BytesIO(response.content))
    except Exception as e:
        return f"Error extracting text from PDF: {e}"
    return text.strip() or "No text could be extracted from the PDF."


def main():
    server.run()


if __name__ == "__main__":
    main()
