# LAWAgent

LAWAgent is a modern legal analysis workspace that combines a high-tech frontend with a FastAPI backend. The Issue Spotter workflow surfaces risks, findings, and citations from uploaded documents or pasted text using OpenAI models.

## Project layout

```
app/
  main.py              # FastAPI application entry point
  config.py            # Pydantic settings loaded from the repo-level .env
  routers/
    issue_spotter.py   # Upload/text endpoints for the Issue Spotter workflow
    witness_finder.py  # Witness Finder search, ranking, and persistence endpoints
  services/
    analysis.py        # OpenAI orchestration for Issue Spotter
    openai_client.py   # Shared OpenAI chat + embedding helpers
    perplexity_client.py # Perplexity web search integration
    ranking.py         # Embedding-based similarity scoring helpers
  models/
    schemas.py         # Shared pydantic models for requests/responses
  store/
    saved_witnesses.py # Lightweight JSON persistence for saved candidates
  utils/
    extract.py         # PDF/DOC/DOCX text extraction helpers
  static/              # Frontend assets served at /
```

`main.py` mounts `app/static` so the site is available at `http://127.0.0.1:8000/` with `index.html` as a landing page and `issue-spotter.html` as the functional experience.

## Prerequisites

* Python 3.11+
* An OpenAI API key stored in the repository root `.env` file (`OPENAI_API_KEY=...`)

Install dependencies and start the development server:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Visit [http://127.0.0.1:8000/](http://127.0.0.1:8000/) for the landing page and Issue Spotter UI.

## Configuration

Settings are loaded from `.env` via `app/config.py`.

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENAI_API_KEY` | ✅ | — | API key used to call OpenAI chat completions. |
| `OPENAI_MODEL` | ❌ | `gpt-4o-mini` | Chat Completions model used for analysis and health checks. |
| `OPENAI_EMBEDDINGS_MODEL` | ❌ | `text-embedding-3-large` | Embedding model used to score Witness Finder candidates. |
| `PERPLEXITY_API_KEY` | ✅ (for Witness Finder) | — | API key for Perplexity web search. |
| `PERPLEXITY_MODEL` | ❌ | `llama-3.1-sonar-large-128k-online` | Default Perplexity search model. |
| `MAX_FILE_MB` | ❌ | `15` | Maximum allowed upload size in megabytes. |
| `MAX_PAGES` | ❌ | `100` | Maximum number of PDF pages processed. |
| `ALLOWED_ORIGINS` | ❌ | — | Optional comma-separated list of additional CORS origins. |

## Witness Finder setup

1. Generate API keys:
   * Create a Perplexity developer key from the [Perplexity dashboard](https://www.perplexity.ai).
   * Create an OpenAI API key with access to both chat and embedding models.
2. Copy `.env.example` to `.env` and fill in the placeholders:

   ```bash
   cp .env.example .env
   # Edit .env and set PERPLEXITY_API_KEY and OPENAI_API_KEY
   ```

3. Install dependencies and start the development server:

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   uvicorn app.main:app --reload
   ```

4. Navigate to [http://127.0.0.1:8000/witness_finder](http://127.0.0.1:8000/witness_finder) to use the Witness Finder UI.

### Witness Finder API endpoints

All routes are available under `/api/witness_finder`:

| Method & Path | Description |
|---------------|-------------|
| `POST /search` | Run Perplexity search, summarize with OpenAI, and return ranked candidates. |
| `POST /save` | Persist a candidate to the local JSON store. |
| `GET /saved` | Retrieve all saved candidates. |
| `DELETE /saved/{id}` | Remove a saved candidate by id. |

`POST /search` expects JSON input:

```json
{
  "industry": "Pharmaceuticals",
  "description": "Expert witness to discuss FDA submission practices",
  "name": "Dr. Smith",
  "limit": 8
}
```

The response includes the normalized query plus a ranked array of candidates with similarity scores, sources, and metadata.

## API reference

Issue Spotter endpoints live under `/api/issue-spotter` and return structured analysis payloads.

### Upload a document

```bash
curl -X POST \
  -F "file=@/path/to/document.pdf" \
  -F "instructions=Summarize potential litigation risks." \
  -F "style=Checklist with citations" \
  -F "return_json=true" \
  http://127.0.0.1:8000/api/issue-spotter/upload
```

### Analyze pasted text

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{
        "text": "Lorem ipsum...",
        "instructions": "Highlight issues in the financing documents.",
        "style": "Detailed memo",
        "return_json": true
      }' \
  http://127.0.0.1:8000/api/issue-spotter/text
```

### Response schema

```json
{
  "summary": "High-level synthesis of the document",
  "findings": [
    {
      "issue": "Issue title",
      "risk": "Risk description",
      "suggestion": "Suggested mitigation",
      "span": {"page": 3, "start": 120, "end": 180}
    }
  ],
  "citations": [
    {"page": 3, "snippet": "Quoted language"}
  ],
  "raw_json": {"original": "Model response"}
}
```

`raw_json` is included when the request asks for JSON output. The Issue Spotter frontend renders summary, findings, citations, and allows downloading the JSON payload.

### AI health check

The backend exposes `/api/health/ai` to verify that the OpenAI integration is working and to surface actionable diagnostics.

```bash
curl http://127.0.0.1:8000/api/health/ai
```

Responses:

* `{ "ok": true, "model": "gpt-4o-mini", "usage": { ... } }` — the configured model responded successfully.
* `{ "ok": false, "reason": "missing key" }` — the `OPENAI_API_KEY` is not configured.
* `{ "ok": false, "reason": "..." }` — the raw error from OpenAI (invalid key, bad model, rate limit, etc.).

The health check uses the same model specified by `OPENAI_MODEL`, helping diagnose configuration issues quickly.

When an AI request fails, the server logs capture detailed exception information (authentication errors, missing models, rate limits, and network issues) and the API returns user-friendly guidance instead of a generic failure message.

## Frontend experience

* Dark, glassmorphic theme with accessible focus states and support for `prefers-reduced-motion`.
* Inputs for document upload or pasted text, required instructions, optional analysis style, and JSON toggle.
* Progress indicator, structured result tabs (Summary, Findings, Citations, Raw JSON), copy/download utilities, and inline error messaging with detailed guidance (e.g., invalid key, model missing, rate limit).

## Running tests

No automated test suite is bundled. After making changes, ensure linting or manual validation as needed and run the API locally with `uvicorn app.main:app --reload`.
