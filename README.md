# Document Intelligence

Personal photo and document library with semantic search and RAG Q&A.
Upload photos, receipts, notes or manuals. Each one is OCR'd, described, NER-tagged, embedded and categorized.
Find things by meaning ("mountain in the background", "black hoodie"), collect them into projects, and ask cited questions ("when does this warranty expire?").

**Stack:** FastAPI · LangChain (custom chunking) · Sentence-BERT · CLIP · FAISS / PostgreSQL + pgvector · spaCy · scikit-learn · Claude · Gemini · Google Cloud (Vision, Cloud Run, Pub/Sub, Cloud SQL, GCS, Secret Manager) · Terraform · GitHub Actions · Next.js

## Run locally

### Backend

```bash
cd backend
python3.12 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m spacy download en_core_web_sm
cp .env.example .env            # then fill it in (see below)
.venv/bin/uvicorn app.main:app --reload --port 8000
```

The first upload downloads the SBERT (~90 MB) and CLIP (~600 MB) models.

### Frontend

```bash
cd frontend
npm install
cp .env.local.example .env.local
npm run dev                      # http://localhost:3000
```

### Configuration

| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | Titles, captions and category suggestions on upload, plus Q&A answers. Without it, uploads still index and Q&A returns the best matching passage. |
| `GOOGLE_CLIENT_ID` / `NEXT_PUBLIC_GOOGLE_CLIENT_ID` | Google sign-in (OAuth client, type "Web", authorized origin `http://localhost:3000`). |
| `DEV_AUTH=true` / `NEXT_PUBLIC_DEV_AUTH=true` | Adds a "Dev login" button so you can test without Google. **Turn off in production.** |
| `OCR_BACKEND=vision` + `GOOGLE_APPLICATION_CREDENTIALS` | Google Cloud Vision OCR (enable the Vision API on your project). Use `none` to skip OCR. |
| `STORAGE_BACKEND=gcs` + `GCS_BUCKET` | Store files in Cloud Storage instead of `backend/data/files`. |
| `JWT_SECRET` | Long random string in production. |
| `GEMINI_API_KEY` (or `GEMINI_USE_VERTEX=true` on GCP) | Turns search like "receipts over 40 euros from last summer" into filters. Without it, a free rule parser handles dates, amounts and photo/document words. |
| `FAKE_MODELS=true` | Hash embeddings instead of SBERT/CLIP. Fast and needs no downloads, but quality is poor. Used by tests. |

### Cost guards

Every Claude and Vision call is checked against hard caps **before** it's made, then recorded with real token counts (`api_usage` table, `GET /usage`, sidebar meter).

- `MONTHLY_BUDGET_USD` (default $5) and `USER_DAILY_BUDGET_USD` (default $1). When a cap is hit, uploads still get indexed without AI captions, and Q&A returns HTTP 429.
- `OCR_MONTHLY_LIMIT` (default 900) keeps Google Vision inside its free tier.
- Requests are bounded: images are downscaled to 1092 px, OCR text is capped at 6k characters, history at 6 turns, `max_tokens` at 1000 and 1500, and there is 1 retry.
- Rate limits per user per minute: ask 10, search 60, upload 10, re-process 5. Uploads are also capped at 100 per day, 2,000 per library and 10 per request. Files are type-checked from their bytes, and image bombs are rejected.

The in-app caps work from local estimates. Also set a hard spend limit in the Anthropic Console (Settings → Limits) and a budget alert in Google Cloud Billing.

### Tests

```bash
cd backend && .venv/bin/pip install -r requirements-dev.txt && .venv/bin/python -m pytest -q
```

## How it works

```
upload ─► storage (local disk | GCS) ─► dispatch (background task | Pub/Sub → Cloud Run worker)
            0. claim          idempotent: duplicate Pub/Sub deliveries are no-ops
            1. OCR            Google Vision (images) / pypdf (PDFs); EXIF capture date
            2. describe       Claude vision → title, summary, visual caption, kind, category pick
            3. NER            spaCy + rules → expiry_date, purchase_date, total, serial, org, person, place…
            4. chunk + embed  LangChain SentenceWindowSplitter → Sentence-BERT → FAISS | pgvector
            5. visual embed   CLIP image embedding → FAISS | pgvector
            6. categorize     learned classifier / Claude / CLIP zero-shot → auto-file or suggest

search ─► Gemini (or local rules) → filters {date, kind, category, amount} + semantic text
          SBERT(text) over chunks ┐  filters applied in the same SQL query on pgvector
          CLIP(text) over images  ┴► Reciprocal Rank Fusion ─► results

ask ─► scope (one doc | project | selected results) ─► top chunks + NER fields ─► Claude ─► cited answer
```

### Categories

- **Suggestions instead of "Uncategorized".** Each item gets up to three ranked suggestions, from the learned classifier, Claude's pick and CLIP zero-shot. It's filed automatically only when the top suggestion is confident. Otherwise a one-tap suggestion chip appears, and **Accept all suggestions** files everything at once.
- **AI-proposed categories.** When Claude proposes a new category for one item, it stays a suggestion. When a second item proposes the same or a near-identical name (SBERT similarity ≥ 0.8), the category is created and both items are filed into it.
- **Merge suggestions.** Categories with similar names (SBERT) or similar photos (CLIP centroids) are suggested for merging.
- **Custom categories.** Each has a name, a color and an optional description. The description is passed to Claude and to zero-shot classification, so new uploads land in your own categories. Confirming or moving items trains the classifier.

### Code map (`backend/app/`)

- `ingest.py`: the pipeline. `tasks.py` dispatches it and `worker.py` is the Pub/Sub push endpoint.
- `vectors.py`: one interface over the FAISS files (`vector_index.py`) and pgvector.
- `query_parser.py`: Gemini structured output turns the query into `QueryFilters`. A free rule parser is the fallback.
- `search.py`: filters as SQL conditions, plus hybrid retrieval and RRF.
- `classifier.py`: suggestions, grouping and merges.
- `chunking.py`, `embeddings.py`, `ner.py`, `qa.py`, `describe.py`, `usage.py` (budgets) and `migrate.py` (additive schema sync).

## Public demo

With `DEMO_ENABLED=true`, the login page offers **Try the demo, no sign-up**. Each visitor gets a private sandbox copied from a template library. Copying reuses the stored files and recomputes embeddings locally, so it makes no paid API calls. Visitors can search, sort, upload and ask questions. Their changes are private, and the sandbox is deleted after 24 hours.

- **Guest limits:**
  - 15 questions and 5 uploads per sandbox.
  - A shared demo AI budget of $2 a month. Browsing and search keep working after it's used up.
  - New sandboxes: 5 per IP per hour and 200 per day.
- **Owner access:** only `OWNER_EMAILS` can sign in with Google. You get full access plus an **Edit demo library** button that switches you into the template account.
- **Seeding the template:** sign in as owner, click **Edit demo library**, and upload the files in `demo/samples/`. Describing all 15 items costs about $0.15 in Claude. Photos are CC0 or public domain (see `demo/samples/CREDITS.md`), and the documents are generated by `demo/make_documents.py` with fictional brands.

## Cloud deployment (GCP)

```
GitHub Actions ──WIF (no keys)──► Artifact Registry ─► Cloud Run: web · api · worker
                                                          api ──publish──► Pub/Sub ──push (OIDC)──► worker (scale to zero)
                                                          api, worker ──► Cloud SQL Postgres + pgvector · GCS · Secret Manager
                                                          api ──► Vertex AI Gemini (query parsing)   worker ──► Cloud Vision, Claude
```

Everything is in `infra/` (Terraform). Each service has its own service account with only the roles it needs. For example, the worker can read the bucket but not write to it, and only the Pub/Sub push identity can invoke the worker. CI authenticates through Workload Identity Federation, restricted to this repo's `main` branch, so there are no service-account keys.

**Costs to know about before applying:**
- Cloud SQL `db-f1-micro` is always on, at about $9–10 a month.
- Cloud Run, Pub/Sub, Artifact Registry and GCS are close to $0 at personal scale.
- Claude, Gemini and Vision are capped in-app by `MONTHLY_BUDGET_USD`.

**Deploy steps:**
1. Run `gcloud auth application-default login`.
2. In `infra/`, copy `terraform.tfvars.example` to `terraform.tfvars` and fill it in.
3. Run `terraform init && terraform apply`.
4. Add the Anthropic key without it entering Terraform state: `printf %s "$KEY" | gcloud secrets versions add di-anthropic-api-key --data-file=-`.
5. In GitHub → Settings → Actions → Variables, set `GCP_PROJECT`, `GCP_REGION`, `GCP_WIF_PROVIDER` and `GCP_DEPLOYER_SA` (from `terraform output`), plus `GOOGLE_CLIENT_ID`.
6. Push to `main`. CI runs the tests on SQLite and pgvector, the frontend build and `terraform validate`, then builds the images and deploys.
7. Add the web URL to your OAuth client's authorized JavaScript origins.

**Run the cloud configuration locally:**
1. Run `docker compose up -d`.
2. Start the backend with `DATABASE_URL=postgresql+psycopg://postgres:pg@localhost:5433/di` and `VECTOR_BACKEND=pgvector`.

**Tests against pgvector:** run `TEST_DATABASE_URL=postgresql+psycopg://... pytest`.
