# Legal Issue Spotter Backend

This FastAPI service powers the PDF upload, extraction, chunking, and issue spotting pipeline for the legal excerpt analyzer. It supports secure PDF ingestion, asynchronous text processing, chunk-based analysis, and a stubbed LLM workflow that can be swapped for a production provider.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export AUTH_TOKEN="super-secret-token"
export FRONTEND_ORIGIN="http://localhost:3000"
uvicorn app.main:app --reload
```

By default, files and derived text are stored under `./data/uploads`. The SQLite database lives at `./data/app.db`.

## Environment variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `AUTH_TOKEN` | ✅ | — | Bearer token expected in `Authorization: Bearer <token>` header. |
| `FRONTEND_ORIGIN` | ✅ | — | Allowed CORS origin for the frontend. |
| `DATA_DIR` | ❌ | `./data/uploads` | Root directory for upload storage. |
| `DATABASE_URL` | ❌ | `sqlite:///./data/app.db` | SQLModel database URL. Use a Postgres URL for production. |
| `MAX_UPLOAD_MB` | ❌ | `20` | Maximum upload size in megabytes. |
| `MAX_PAGES` | ❌ | `500` | Maximum number of PDF pages accepted. |
| `LLM_PROVIDER` | ❌ | — | Set to `openai` to enable live OpenAI calls (requires API key). |
| `OPENAI_API_KEY` | ❌ | — | API key used when `LLM_PROVIDER=openai`. |

## API walkthrough

### 1. Upload a PDF

```bash
curl -X POST \
  -H "Authorization: Bearer super-secret-token" \
  -F "file=@/path/to/document.pdf" \
  -F "notes=Initial complaint" \
  http://localhost:8000/api/uploads
```

Response:

```json
{
  "upload_id": "<uuid>",
  "filename": "document.pdf",
  "size_bytes": 1048576,
  "pages": 42,
  "status": "uploaded"
}
```

### 2. Check upload status

```bash
curl -H "Authorization: Bearer super-secret-token" \
  http://localhost:8000/api/uploads/<upload_id>/status
```

### 3. Trigger analysis

```bash
curl -X POST \
  -H "Authorization: Bearer super-secret-token" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Focus on defenses"}' \
  http://localhost:8000/api/analyze/<upload_id>
```

### 4. Poll analysis status and fetch results

```bash
curl -H "Authorization: Bearer super-secret-token" \
  http://localhost:8000/api/analyze/<analysis_id>/status

curl -H "Authorization: Bearer super-secret-token" \
  http://localhost:8000/api/analyze/<analysis_id>/result
```

## Notes

* Uploads are rate-limited to 30 requests per minute per IP using `slowapi`.
* PDF extraction prefers `pypdf` and falls back to `pdfminer.six` when needed. Extracted text is stored alongside the original document.
* The default LLM pipeline returns deterministic stub data so the API functions without external credentials. Provide `LLM_PROVIDER=openai` and `OPENAI_API_KEY` to use OpenAI's Chat Completions API instead.
* File deletions mark the upload as errored with `deleted by user` and remove the associated files from disk.
