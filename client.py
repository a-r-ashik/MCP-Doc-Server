"""
client.py — MCP client that connects to the documentation server and
            tests ALL 4 tools with working queries.

Windows fix:
  - WindowsSelectorEventLoopPolicy set before any asyncio usage
  - Graceful per-tool error reporting so one failure doesn't crash all tests
  - Shows raw tool output so you can see exactly what the server returns

HOW TO RUN:
  uv run client.py
"""

import asyncio
import os
import sys

from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from utils import get_response_from_llm


if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

load_dotenv()


server_params = StdioServerParameters(
    command="uv",
    args=["run", "mcp_server.py"],
    env=None,
)

SYSTEM_PROMPT = """
Answer ONLY using the provided context. If info is missing, say you don't know.
Keep every 'SOURCE:' line exactly as given; list all sources at the end.
Be concise and accurate.
"""


async def run_tool(session: ClientSession, tool_name: str, arguments: dict, label: str) -> str:
    print(f"\n{'='*60}")
    print(f"🔧 TOOL: {tool_name}")
    print(f"📌 TEST: {label}")
    print(f"📥 Args: {arguments}")
    print("="*60, flush=True)

    try:
        res = await session.call_tool(tool_name, arguments=arguments)
        if not res.content:
            print("⚠️  No content returned.")
            return ""

        
        raw = ""
        for block in res.content:
            if hasattr(block, "text"):
                raw += block.text
            else:
                raw += str(block)

        
        preview = raw[:600] + ("…[truncated]" if len(raw) > 600 else "")
        print(f"📤 Result preview:\n{preview}")
        return raw

    except Exception as exc:
        print(f"❌ Tool call failed: {exc}")
        return ""


async def main() -> None:
    print("🔌 Connecting to MCP documentation server…", flush=True)

    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:

            await session.initialize()

            tools_response = await session.list_tools()
            tool_names = [t.name for t in tools_response.tools]
            print(f"✅ Available tools: {tool_names}", flush=True)

            # ── TOOL 1: get_docs ─────────────────────────────────────────
            # Key fix: use a SHORT, SIMPLE query — site-search works better
            # "ChromaDB vector store" finds results; long sentences often don't
            context = await run_tool(
                session,
                "get_docs",
                {"query": "ChromaDB vector store", "library": "llamaindex"},
                "LlamaIndex ChromaDB vector store (Playwright renders JS docs)",
            )

            # Feed the docs result to Groq for a final answer
            if context and "No documentation" not in context:
                print("\n🤖 Generating LLM answer from docs context…", flush=True)
                answer = get_response_from_llm(
                    user_prompt=f"Query: How to use ChromaDB with LlamaIndex?\n\nContext:\n{context[:4000]}",
                    system_prompt=SYSTEM_PROMPT,
                )
                print(f"\n💬 LLM Answer:\n{answer}")
            else:
                # Fallback: try chromadb docs directly
                print("\n🔄 Retrying with chromadb library directly…", flush=True)
                context2 = await run_tool(
                    session,
                    "get_docs",
                    {"query": "getting started", "library": "chromadb"},
                    "ChromaDB getting started (fallback)",
                )
                if context2 and "No documentation" not in context2:
                    answer = get_response_from_llm(
                        user_prompt=f"Query: How to use ChromaDB?\n\nContext:\n{context2[:4000]}",
                        system_prompt=SYSTEM_PROMPT,
                    )
                    print(f"\n💬 LLM Answer:\n{answer}")

            # ── TOOL 2: summarize_url ────────────────────────────────────
            # Playwright fetches JS-heavy pages — LangChain homepage works great
            await run_tool(
                session,
                "summarize_url",
                {"url": "https://python.langchain.com/docs/introduction/"},
                "Summarize LangChain introduction page",
            )

            # ── TOOL 3: compare_libraries ────────────────────────────────
            # Playwright handles both JS-heavy doc sites
            await run_tool(
                session,
                "compare_libraries",
                {
                    "library_a": "langchain",
                    "library_b": "llamaindex",
                    "topic": "RAG pipeline",
                },
                "LangChain vs LlamaIndex — RAG pipeline comparison",
            )

            # ── TOOL 4: get_code_examples ────────────────────────────────
            # anthropic docs are well-indexed by Serper — reliable for code examples
            await run_tool(
                session,
                "get_code_examples",
                {"query": "messages API", "library": "anthropic"},
                "Anthropic messages API code examples",
            )

            print(f"\n{'='*60}")
            print(" All 4 tools tested ✅ ")
            print("="*60)


if __name__ == "__main__":
    asyncio.run(main())
