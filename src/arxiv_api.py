import time
import httpx
import feedparser

BASE_URL = "https://export.arxiv.org/api/query"
_RATE_LIMIT = 3.0
_last_requests: list[float] = []


class ArxivError(Exception):
    pass


class ArxivNetworkError(ArxivError):
    pass


class ArxivApiError(ArxivError):
    pass


def _throttle():
    now = time.monotonic()
    cutoff = now - 1.0
    global _last_requests
    _last_requests = [t for t in _last_requests if t > cutoff]
    if len(_last_requests) >= _RATE_LIMIT:
        sleep_for = _last_requests[0] + 1.0 - now
        if sleep_for > 0:
            time.sleep(sleep_for)
    _last_requests.append(time.monotonic())


def fetchArxiv(params: dict) -> str:
    _throttle()
    query_params = []
    for key in ("search_query", "id_list", "start", "max_results", "sortBy", "sortOrder"):
        value = params.get(key)
        if value is not None:
            query_params.append(f"{key}={value}")
    url = f"{BASE_URL}?{'&'.join(query_params)}" if query_params else BASE_URL
    try:
        response = httpx.get(url, timeout=30, follow_redirects=True)
        response.raise_for_status()
    except httpx.TimeoutException:
        raise ArxivNetworkError("Request to arXiv API timed out")
    except httpx.ConnectError:
        raise ArxivNetworkError("Could not connect to arXiv API")
    except httpx.HTTPStatusError as e:
        raise ArxivNetworkError(f"arXiv API returned HTTP {e.response.status_code}")
    return response.text


def parseAtomFeed(xml: str) -> list[dict]:
    feed = feedparser.parse(xml)
    if feed.bozo and not feed.entries:
        raise ArxivError("Failed to parse arXiv API response")

    entries = []
    for entry in feed.entries:
        if "/api/errors" in entry.id:
            raise ArxivApiError(entry.summary)

        pdf_url = None
        for link in entry.links:
            if link.rel == "related" and link.get("title") == "pdf":
                pdf_url = link.href
                break
        entries.append({
            "id": entry.id,
            "title": entry.title,
            "authors": [a.name for a in entry.authors],
            "abstract": entry.summary,
            "published": entry.published,
            "pdf_url": pdf_url,
        })
    return entries


def search(*, keyword=None, author=None, category=None, date_from=None, date_to=None, max_results=10, start=0):
    if not any([keyword, author, category, date_from, date_to]):
        raise ArxivError("At least one search parameter (keyword, author, category, date range) is required")

    terms = []
    if keyword:
        terms.append(f"all:{keyword}")
    if author:
        terms.append(f"au:{author}")
    if category:
        terms.append(f"cat:{category}")
    if date_from or date_to:
        date_from = date_from or "000001010000"
        date_to = date_to or "999912312359"
        terms.append(f"submittedDate:[{date_from}+TO+{date_to}]")

    search_query = "+AND+".join(terms) if terms else None

    params = {"start": start, "max_results": max_results}
    if search_query:
        params["search_query"] = search_query

    xml = fetchArxiv(params)
    return parseAtomFeed(xml)


def get_by_id(arxiv_id: str) -> dict | None:
    xml = fetchArxiv({"id_list": arxiv_id, "max_results": 1})
    results = parseAtomFeed(xml)
    return results[0] if results else None


def get_recent(category: str, max_results: int = 10) -> list[dict]:
    xml = fetchArxiv({
        "search_query": f"cat:{category}",
        "sortBy": "submittedDate",
        "sortOrder": "descending",
        "max_results": max_results,
    })
    return parseAtomFeed(xml)
