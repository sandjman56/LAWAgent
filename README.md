# LAWAgent

LAWAgent is a modern legal analysis workspace that combines a high-tech frontend with a FastAPI backend. The Issue Spotter workflow surfaces risks, findings, and citations from uploaded documents or pasted text using OpenAI models.

## Project layout

```
app/
  main.py            # FastAPI application entry point
  config.py          # Pydantic settings loaded from the repo-level .env
  routers/
    issue_spotter.py # Upload/text endpoints for the Issue Spotter workflow
  services/
    analysis.py      # OpenAI orchestration and response shaping
  utils/
    extract.py       # PDF/DOC/DOCX text extraction helpers
  static/            # Frontend assets served at /
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
| `MAX_FILE_MB` | ❌ | `15` | Maximum allowed upload size in megabytes. |
| `MAX_PAGES` | ❌ | `100` | Maximum number of PDF pages processed. |
| `ALLOWED_ORIGINS` | ❌ | — | Optional comma-separated list of additional CORS origins. |

## API reference

Both endpoints live under `/api/issue-spotter` and return structured analysis payloads.

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

## Frontend experience

* Dark, glassmorphic theme with accessible focus states and support for `prefers-reduced-motion`.
* Inputs for document upload or pasted text, required instructions, optional analysis style, and JSON toggle.
* Progress indicator, structured result tabs (Summary, Findings, Citations, Raw JSON), copy/download utilities, and inline error messaging.

## Running tests

No automated test suite is bundled. After making changes, ensure linting or manual validation as needed and run the API locally with `uvicorn app.main:app --reload`.
