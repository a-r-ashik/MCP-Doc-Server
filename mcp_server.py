"""
MCP Documentation Server — v0.3.0

  1. get_docs          — Search official library documentation
  2. summarize_url     — Summarize ANY webpage by URL
  3. compare_libraries — Compare two libraries on a topic side-by-side
  4. get_code_examples — Extract ONLY code snippets from library docs

MCP concepts covered:
  - @mcp.tool() decorator
  - Tool docstrings (how Claude decides which tool to call)
  - Async tools
  - Helper functions shared across tools (DRY principle)
  - Error handling inside tools
  - Logging to stderr (never stdout — that breaks MCP protocol)
  - Windows-compatible asyncio event loop
"""

import asyncio
import json
import logging
import os
import sys

import httpx
from dotenv import load_dotenv
from fastmcp import FastMCP
from utils import clean_html_to_txt, get_response_from_llm

# ── Logging — MUST go to stderr. stdout is reserved for MCP JSON-RPC. ────────
logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("mcp_server")


if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

load_dotenv()

mcp = FastMCP("docs")

SERPER_URL = "https://google.serper.dev/search"

DOCS_URLS: dict[str, str] = {

    "langchain":   "langchain.com/docs",         
    "llama-index": "docs.llamaindex.ai",          
    "llamaindex":  "docs.llamaindex.ai",          
    "openai":      "cookbook.openai.com",         
    "uv":          "docs.astral.sh/uv",
    "pinecone":    "docs.pinecone.io",
    "chromadb":    "docs.trychroma.com",
    "anthropic":   "docs.anthropic.com",
    "mistral":     "docs.mistral.ai",
    "fastapi":     "fastapi.tiangolo.com",
    "pydantic":    "docs.pydantic.dev",
}

_JS_THRESHOLD = 500



async def search_web(query: str, num_results: int = 3) -> dict:
    payload = json.dumps({"q": query, "num": num_results})
    headers = {
        "X-API-KEY": os.getenv("SERPER_API_KEY", ""),
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(SERPER_URL, headers=headers, data=payload, timeout=30.0)
        response.raise_for_status()
        return response.json()


async def _fetch_with_httpx(url: str) -> str:
    async with httpx.AsyncClient(follow_redirects=True) as client:
        response = await client.get(url, timeout=30.0)
        response.raise_for_status()
        return response.text


async def _fetch_with_playwright(url: str) -> str:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.warning("playwright not installed. Run: pip install playwright && playwright install chromium")
        return ""
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        try:
            await page.goto(url, wait_until="networkidle", timeout=30_000)
            content = await page.inner_text("body")
        finally:
            await browser.close()
    return content


async def fetch_url(url: str) -> str:
    logger.info("Fetching: %s", url)
    try:
        raw_html = await _fetch_with_httpx(url)
    except Exception as exc:
        logger.warning("httpx failed for %s: %s", url, exc)
        raw_html = ""

    if len(raw_html.strip()) < _JS_THRESHOLD:
        logger.info("JS-heavy page, switching to Playwright: %s", url)
        raw_html = await _fetch_with_playwright(url)

    if not raw_html:
        return ""

    cleaned = clean_html_to_txt(raw_html)
    if cleaned:
        return cleaned

    system_prompt = (
        "You are an AI web scraper. Return only clean readable text. "
        "Remove all HTML tags, scripts, styles, and navigation elements."
    )
    chunks = [raw_html[i: i + 4000] for i in range(0, len(raw_html), 4000)]
    parts: list[str] = []
    for chunk in chunks:
        try:
            result = get_response_from_llm(user_prompt=chunk, system_prompt=system_prompt, model="llama-3.3-70b-versatile")
            if result:
                parts.append(result)
        except Exception as exc:
            logger.warning("LLM chunk cleaning failed: %s", exc)
    return "\n".join(parts)


def _validate_library(library: str) -> tuple[str, str]:
    key = library.strip().lower()
    if key not in DOCS_URLS:
        supported = ", ".join(sorted(DOCS_URLS.keys()))
        raise ValueError(f"Library '{library}' not supported. Supported: {supported}")
    return key, DOCS_URLS[key]


async def _fetch_docs_links(site: str, query: str) -> list[str]:

    results = await search_web(f"site:{site} {query}", num_results=3)
    links = [r.get("link", "") for r in results.get("organic", []) if r.get("link")]

    if links:
        return links


    logger.info("site: search returned 0 results for %s — trying open search fallback", site)
    results2 = await search_web(f"{query} {site} documentation", num_results=5)
    links2 = [
        r.get("link", "")
        for r in results2.get("organic", [])
        if r.get("link") and site.split("/")[0] in r.get("link", "")
    ]
    return links2


async def _fetch_all_links(links: list[str]) -> list[tuple[str, str]]:
    results = await asyncio.gather(*[fetch_url(link) for link in links], return_exceptions=True)
    return [
        (link, content)
        for link, content in zip(links, results)
        if not isinstance(content, Exception) and content
    ]


# ═════════════════════════════════════════════════════════════════════════════
# TOOL 1 — get_docs
# Teaches: basic @mcp.tool(), Serper search, HTML fetching, parallel fetching
# ═════════════════════════════════════════════════════════════════════════════
  
@mcp.tool()
async def get_docs(query: str, library: str) -> str:
    """
    Search the official documentation for a given library and return
    relevant cleaned content with source links.

    Use this when the user asks HOW to do something with a specific library,
    needs a feature explanation, or wants reference information from official docs.

    Supported libraries (case-insensitive):
        langchain, llama-index, llamaindex, openai, uv, pinecone,
        chromadb, anthropic, mistral, fastapi, pydantic

    Args:
        query:   What to search for. Be specific.
                 Example: "how to add memory to a LangChain agent"
        library: Library name. Case-insensitive.
                 Example: "LangChain", "OPENAI", "uv"

    Returns:
        Cleaned documentation text with SOURCE labels.
    """
    _, site = _validate_library(library)
    links = await _fetch_docs_links(site, query)
    if not links:
        return "No documentation pages found for your query."
    pairs = await _fetch_all_links(links)
    if not pairs:
        return "Pages fetched but returned no readable content."
    return "\n\n".join(f"SOURCE: {url}\n{content}" for url, content in pairs)


# ═════════════════════════════════════════════════════════════════════════════
# TOOL 2 — summarize_url
# Teaches: direct URL input, reusing helpers, LLM prompt engineering
# Free: Groq free tier for summarisation
# ═════════════════════════════════════════════════════════════════════════════
@mcp.tool()
async def summarize_url(url: str) -> str:
    """
    Fetch ANY public webpage by URL and return a clean concise summary.

    Use this when the user provides a specific URL and wants to know what
    is on that page — blog post, changelog, GitHub README, docs page, article.

    Do NOT use for general library searches — use get_docs for that.

    Args:
        url: Full URL of the page.
             Example: "https://docs.astral.sh/uv/guides/publish/"

    Returns:
        Concise bullet-point summary of the page content with the source URL.
    """
    content = await fetch_url(url)
    if not content:
        return f"Could not retrieve content from: {url}"

    system_prompt = (
        "You are a helpful assistant. "
        "Summarise the following webpage content in clear concise bullet points. "
        "Focus on the key concepts, steps, or information. "
        "Keep the summary under 300 words."
    )
    summary = get_response_from_llm(
        user_prompt=content[:6000],
        system_prompt=system_prompt,
        model="llama-3.3-70b-versatile",
    )
    return f"SOURCE: {url}\n\n{summary}" if summary else content[:2000]


# ═════════════════════════════════════════════════════════════════════════════
# TOOL 3 — compare_libraries
# Teaches: parallel asyncio.gather() across tools, structured prompt engineering,
#          combining multiple data sources inside one tool
# Free: Serper + Groq free tier
# ═════════════════════════════════════════════════════════════════════════════
@mcp.tool()
async def compare_libraries(library_a: str, library_b: str, topic: str) -> str:
    """
    Compare two libraries side-by-side on a specific topic using their
    official documentation as the only source of truth.

    Use this when the user asks:
      - "LangChain vs LlamaIndex for RAG pipelines"
      - "Difference between FastAPI and pydantic?"
      - "Pinecone or ChromaDB for vector search?"

    Both libraries must be in the supported list.

    Args:
        library_a: First library name (case-insensitive).
        library_b: Second library name (case-insensitive).
        topic:     The specific topic to compare.
                   Example: "vector store integration"

    Returns:
        Structured side-by-side comparison with sources.
    """
    _, site_a = _validate_library(library_a)
    _, site_b = _validate_library(library_b)


    links_a, links_b = await asyncio.gather(
        _fetch_docs_links(site_a, topic),
        _fetch_docs_links(site_b, topic),
    )

   
    pairs_a, pairs_b = await asyncio.gather(
        _fetch_all_links(links_a[:2]),
        _fetch_all_links(links_b[:2]),
    )

    if not pairs_a and not pairs_b:
        return "Could not retrieve documentation for either library."

    context_a = "\n\n".join(f"SOURCE: {u}\n{c}" for u, c in pairs_a) or f"No docs found for {library_a}."
    context_b = "\n\n".join(f"SOURCE: {u}\n{c}" for u, c in pairs_b) or f"No docs found for {library_b}."

    system_prompt = (
        "You are a technical writer. Using ONLY the documentation excerpts provided, "
        "write a clear side-by-side comparison. Structure your response as:\n"
        "1. Overview of each library's approach\n"
        "2. Key differences\n"
        "3. When to choose which\n"
        "4. Sources\n"
        "Be factual. Do not add opinions not backed by the docs."
    )
    user_prompt = (
        f"Topic: {topic}\n\n"
        f"=== {library_a.upper()} DOCS ===\n{context_a[:3000]}\n\n"
        f"=== {library_b.upper()} DOCS ===\n{context_b[:3000]}"
    )

    comparison = get_response_from_llm(
        user_prompt=user_prompt,
        system_prompt=system_prompt,
        model="llama-3.3-70b-versatile",
    )
    return comparison or "Comparison could not be generated. Try a more specific topic."


# ═════════════════════════════════════════════════════════════════════════════
# TOOL 4 — get_code_examples
# Teaches: targeted prompt engineering for a specific output type (code),
#          search query enrichment, tool specialisation
# Free: Serper + Groq free tier
# ═════════════════════════════════════════════════════════════════════════════
@mcp.tool()
async def get_code_examples(query: str, library: str) -> str:
    """
    Search official library documentation and return ONLY working code
    examples — no prose, just code blocks with brief comments.

    Use this when the user wants to SEE how something is implemented,
    asks for a code snippet, or says "show me an example of...".

    Do NOT use for general explanations — use get_docs for that.

    Supported libraries (case-insensitive):
        langchain, llama-index, llamaindex, openai, uv, pinecone,
        chromadb, anthropic, mistral, fastapi, pydantic

    Args:
        query:   What code to find.
                 Example: "streaming response with OpenAI"
        library: Library name. Case-insensitive.
                 Example: "openai"

    Returns:
        Code blocks from official documentation with source links.
    """
    _, site = _validate_library(library)


    enriched_query = f"{query} example code snippet"
    links = await _fetch_docs_links(site, enriched_query)

    if not links:
        return f"No code example pages found for '{query}' in {library} docs."

    pairs = await _fetch_all_links(links)
    if not pairs:
        return "Pages fetched but returned no readable content."

    raw_context = "\n\n".join(f"SOURCE: {url}\n{content}" for url, content in pairs)

    system_prompt = (
        "You are a code extractor. From the documentation text, extract ALL relevant code examples. "
        "For each code block:\n"
        "  - Keep the code exactly as written\n"
        "  - Add a one-line comment above explaining what it does\n"
        "  - Include the SOURCE URL it came from\n"
        "Return ONLY code blocks with their comments and sources. "
        "No prose. If no code is found, say so clearly."
    )

    code_output = get_response_from_llm(
        user_prompt=raw_context[:6000],
        system_prompt=system_prompt,
        model="llama-3.3-70b-versatile",
    )
    return code_output or "No code examples found in the retrieved documentation."



def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
