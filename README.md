# 🔌 MCP Documentation Server

> **An MCP learning project** — 4 tools, Windows-ready, 100% free APIs.  
> Connect to Claude Desktop and ask questions in plain language. Claude picks the right tool automatically.

---

## 🚀 What It Does

This server gives Claude Desktop the ability to **search real documentation pages** and answer questions about libraries — live, from the actual docs.

```
You ask → Claude picks a tool → Server searches docs → Groq writes the answer
```

---

## 🧰 4 Tools Available

| Tool | What It Does | Example Trigger |
|------|-------------|-----------------|
| `get_docs` | Search official library docs | *"How do I use ChromaDB with LlamaIndex?"* |
| `summarize_url` | Summarize any webpage by URL | *"Summarize this page: https://..."* |
| `compare_libraries` | Compare two libraries side-by-side | *"LangChain vs LlamaIndex for RAG?"* |
| `get_code_examples` | Return only working code snippets | *"Show me code for Anthropic streaming"* |

---

## 📚 Supported Libraries

```
langchain   llamaindex   openai     uv        pinecone
chromadb    anthropic    mistral    fastapi   pydantic
```

All case-insensitive — `LangChain`, `langchain`, `LANGCHAIN` all work.

---

## 🆓 Free APIs Required

| Service | Cost | Link |
|---------|------|------|
| **Groq** (LLM — Llama 3.3 70B) | Free forever | https://console.groq.com |
| **Serper** (Google Search API) | 2,500 free searches on signup | https://serper.dev |

No OpenAI key. No Anthropic key. No credit card needed.

---

## ⚡ Quick Start — Windows + VS Code

### 1. Clone and enter the project

```powershell
cd "E:\A I-E N G G\MCP-Server"
```

### 2. Set up your API keys

```powershell
# Copy the template
copy .env.example .env

# Open and fill in your keys
notepad .env
```

Your `.env` should look like:

```env
SERPER_API_KEY=your_serper_key_here
GROQ_API_KEY=your_groq_key_here
```

### 3. Install dependencies

```powershell
# Basic install (works for most libraries)
uv sync

# With Playwright — required for JS-heavy sites (LangChain, Pinecone, FastAPI)
uv sync --extra js
playwright install chromium
```

> **Don't have `uv`?** Install it first:
> ```powershell
> powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
> ```

### 4. Run the interactive client

```powershell
uv run client.py
```

You'll see a menu — choose a tool, type your question, get real answers from live docs.

---

## 🖥️ Connect to Claude Desktop

This is where the real power is. Claude automatically picks which tool to use based on your natural language — no manual tool selection needed.

### Step 1 — Find your uv path

```powershell
where.exe uv
# Example output: C:\Users\YourName\.local\bin\uv.exe
```

### Step 2 — Open Claude Desktop config

```powershell
notepad "$env:APPDATA\Claude\claude_desktop_config.json"
```

### Step 3 — Paste this config

```json
{
  "mcpServers": {
    "docs-server": {
      "command": "C:\\Users\\YOUR_NAME\\.local\\bin\\uv.exe",
      "args": [
        "run",
        "--directory",
        "E:\\A I-E N G G\\MCP-Server",
        "mcp_server.py"
      ],
      "cwd": "E:\\A I-E N G G\\MCP-Server",
      "env": {
        "SERPER_API_KEY": "your_serper_api_key_here",
        "GROQ_API_KEY": "your_groq_api_key_here"
      }
    }
  }
}
```

> ⚠️ Use **double backslashes** `\\` in all Windows paths inside JSON.

### Step 4 — Restart Claude Desktop

Right-click the system tray icon → **Quit** → Reopen

### Step 5 — Verify

Look for the 🔨 hammer icon at the bottom of the chat window. Click it — you should see all 4 tools listed.

**Try asking:**
- *"Get docs for langchain on RAG pipelines"*
- *Summarize this page for me: https://python.langchain.com/docs/introduction/"*
- *"Compare LangChain and LlamaIndex for building RAG pipelines"*
- *"Show me code examples for the Anthropic messages API"*

---

## 🏗️ How It Works

```
Your question
      │
      ▼
Serper searches the docs site
      │
      ▼
httpx fetches the page (fast)
      │
      ├── JS-heavy page? → Playwright renders it in a real browser
      │
      ▼
trafilatura extracts clean text from HTML
      │
      ▼
Groq (Llama 3.3 70B) writes the answer
      │
      ▼
Answer returned to you
```

---

## 📁 Project Structure

```
MCP-Server/
├── mcp_server.py                      ← MCP server — all 4 tools live here
├── client.py                          ← Interactive test client
├── utils.py                           ← Shared helpers (Groq LLM + HTML cleaner)
├── pyproject.toml                     ← Dependencies for uv
├── requirements.txt                   ← Dependencies for pip
├── .env.example                       ← API key template → rename to .env
├── claude_desktop_config_EXAMPLE.json ← Ready-to-copy Claude Desktop config
└── README.md
```

---

## 🎓 MCP Concepts This Project Teaches

| Concept | Where To Find It |
|---------|-----------------|
| `@mcp.tool()` decorator | Every tool in `mcp_server.py` |
| Tool docstrings (how Claude picks tools) | The `"""..."""` block inside each tool |
| `async def` tools | All 4 tools |
| Shared helpers — DRY principle | `fetch_url()`, `_validate_library()` etc. |
| Parallel fetching with `asyncio.gather()` | Inside `compare_libraries` |
| `stdio` transport | `mcp.run(transport="stdio")` at the bottom |
| Windows asyncio fix | `WindowsSelectorEventLoopPolicy` at top of each file |
| Logging to `stderr` only | `logging.basicConfig(stream=sys.stderr)` |
| JS-heavy page fallback | `_fetch_with_playwright()` in `mcp_server.py` |
| Two-stage search fallback | `_fetch_docs_links()` — site search → open search |

---

## ❓ Why Queries Sometimes Return "No docs found"

This is a **Serper/Google indexing issue**, not a code bug.

The server sends: `site:docs.llamaindex.ai ChromaDB vector store`  
If Google hasn't indexed that page, Serper returns 0 results.

**Fix — use short keyword queries:**

```python
# ❌ Too long — often returns 0 Serper results
query = "How to connect to ChromaDB with LlamaIndex"

# ✅ Short keywords — Serper finds results reliably  
query = "ChromaDB vector store"
```

**In Claude Desktop** — Claude retries automatically with simpler queries.  
**In `client.py`** — you control the query string directly.

---

## 🔧 Troubleshooting

**Tools not showing in Claude Desktop:**
- Fully quit Claude Desktop — right-click tray → Quit (don't just close the window)
- Use the **full path** to `uv.exe` — run `where.exe uv` to find it
- Check JSON syntax — no trailing commas, double backslashes in paths
- Check logs: `%APPDATA%\Claude\logs\mcp-server-docs-server.log`

**"No documentation pages found":**
- Shorten your query to 3–5 keywords
- Check `SERPER_API_KEY` is set correctly in `.env`
- Some libraries (OpenAI, LlamaIndex) have indexing issues — try `anthropic`, `uv`, or `chromadb` to confirm the tool works

**Playwright errors:**
- Run `playwright install chromium` (only needed once per machine)
- Only needed for JS-heavy sites: LangChain, Pinecone, FastAPI
- Static sites like `uv`, `chromadb`, `anthropic` work without it

**`uv` not found:**
```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
# Then close and reopen the terminal
uv --version
```

---

## 📊 Serper Free Tier Usage

Each `uv run client.py` uses roughly **6–9 Serper searches**.  
2,500 free credits ≈ **300+ full test runs**.

When you run out, alternatives:
- **Brave Search API** — 2,000 free searches/month
- **SerpAPI** — 100 free searches/month

Both can replace Serper by updating the `search_web()` function in `mcp_server.py`.

---

## 📄 License

MIT — free to use, modify, and share.