# Decision Log

Every assumption and design decision made while building the Ledgerline MVP. Each entry has an ID so other documents can reference it (for example "see D-014").

Format: **Decision** - what was decided. **Why** - the reasoning. **Alternatives** - what was considered and rejected.

## Interpreting the brief

| ID | Brief said | Interpreted as |
|----|------------|----------------|
| D-001 | "SQL Academy 2" | SQLAlchemy 2.x (typed `Mapped[]` ORM style). |
| D-002 | "React, TypeScript, and White" | React + TypeScript + **Vite**. |
| D-003 | "Education analysis document" | **Edge-case analysis** document (`docs/06-edge-case-analysis.md`). |
| D-004 | "Text that doesn't match the rate" | **Tax** that does not match the GST rate. |
| D-005 | "Two reviewers editing the same build" | Two reviewers editing the same **bill** (invoice). |
| D-006 | "The expired logic token" / "The login token" | Two cases: an **expired** login (JWT) token, and an **invalid or tampered** token. |
| D-007 | "Simple in-progress worker ... swap for Redis or mostly Redis later" | An **in-process** worker behind a `JobQueue` interface, swappable for a Redis-backed queue (RQ, Celery, or Arq) later. |
| D-008 | "intra-state invoices use CGST and SGST, while interstate invoices use GST" | Inter-state invoices use **IGST**. |
| D-009 | "a simple spen..." (truncated) | A simple **spend chart**: monthly approved spend for the last 6 months, plus the top vendors by spend. |
| D-010 | "Bill" and "invoice" | Used interchangeably. The UI says "Bill" (the AP term for a payable). The code and database say `invoice`. |
| D-011 | "Filters by value, vendors, and date" | Value means an amount range (min/max total). |
| D-012 | "Approval rate" | Approved bills divided by bills that reached a decision (approved + rejected) this month. |

## Product decisions

| ID | Decision | Why | Alternatives |
|----|----------|-----|--------------|
| D-020 | Every extracted bill goes to `needs_review`. Nothing is auto-approved. | An MVP AP tool must keep a human in the loop. Auto-approval needs months of accuracy data first. | Auto-approve bills with no findings and high confidence (deferred). |
| D-021 | A bill with any **error**-severity finding cannot be approved. The reviewer must correct the data or reject the bill. | Errors (duplicate, invalid GSTIN, totals that do not add up) are exactly what AP controls are meant to stop. | A soft block with an override reason (deferred; needs a role model). |
| D-022 | Rejection requires a reason (min 3 chars). Approval takes an optional comment. | Rejections are communicated back to vendors and need an explanation. | Optional reason. |
| D-023 | Vendors are auto-created only when the vendor GSTIN is **valid**. With no valid GSTIN, the bill stays unlinked and a warning is raised. | GSTIN is the only reliable unique key for an Indian vendor. Names vary ("ABC Pvt Ltd" vs "ABC Private Limited"). | Fuzzy name matching (deferred: it creates silent wrong matches). |
| D-024 | Vendor has `legal_name` (from the invoice) and `display_name` (brand name, editable). | Matches how AP teams refer to vendors ("Amazon" vs "Amazon Seller Services Pvt Ltd"). | A single name field. |
| D-025 | Signup creates a company and its first user with the `admin` role. Inviting more users is out of scope for the MVP. | Keeps the auth surface small. The `role` column exists so invites can be added without a migration. | Full user management. |
| D-026 | Failed extractions (corrupt file, provider outage) can be retried from the UI with "Retry extraction". | Transient failures should not force a re-upload. | Re-upload only. |
| D-027 | Duplicate detection is **vendor GSTIN + invoice number + total**, plus an exact-file check (SHA-256). Rejected bills are ignored as duplicates. | Matches the brief, and catches the same file uploaded twice even before extraction finishes. | Invoice number only (false positives across vendors). |
| D-028 | GST slabs accepted by the tax-rate rule: 0, 0.25, 3, 5, 12, 18, 28, 40 %. | Covers pre- and post-September-2025 (GST 2.0) slabs, so older invoices still validate. | Only the new slabs. |
| D-029 | Arithmetic tolerance: Rs 1.00 per line and on totals. A difference of up to Rs 1 between computed and stated total is reported as **info** ("round-off"). | Indian invoices routinely round the grand total to the nearest rupee. | Exact match (too many false errors). |
| D-030 | Fields with extraction confidence below 0.60 raise a **warning** asking the reviewer to verify. | Directs reviewer attention to the risky values first. | Hide confidence (loses the main reviewer aid). |

## Architecture decisions

| ID | Decision | Why | Alternatives |
|----|----------|-----|--------------|
| D-040 | A modular monolith (one FastAPI service + one React SPA) with feature-based folders. | Fastest to build and operate at MVP scale. The feature boundaries let modules be split out later. | Microservices (premature). |
| D-041 | **Synchronous** SQLAlchemy 2 with the psycopg 3 driver. FastAPI runs `def` endpoints in its threadpool. | Simpler code and tests. The workload is I/O on Postgres and OpenAI, not thousands of concurrent sockets. Workers are threads, and sync sessions fit them naturally. | Async SQLAlchemy (more complexity, little gain here). |
| D-042 | Layers: router -> service -> repository -> ORM model. Routers never touch the session. Services never build SQL. | Testability, and a clear place for every concern. | Fat routers. |
| D-043 | Dependency injection through FastAPI `Depends` factories in each feature's `dependencies.py`. | Native to FastAPI, overridable in tests via `app.dependency_overrides`. | A DI container library (an extra dependency). |
| D-044 | **Multi-tenancy:** shared database, shared schema, and a `company_id` column on every tenant table. Repositories are built with a `TenantContext` taken from the JWT and add `company_id` to every query. | The cheapest model that is safe when enforced in one place. The client never sends a `company_id`. | Schema-per-tenant (hard to migrate). Postgres RLS (planned as defence in depth). |
| D-045 | UUID (v4) primary keys. | Not guessable (no enumeration across tenants) and safe to generate in app code. | Bigint serial. |
| D-046 | Money is `NUMERIC(14,2)` in Postgres, `Decimal` in Python, and a **string** in JSON. | Avoids float rounding. Strings keep precision across the JS boundary. | Float (unsafe). Integer paise (awkward for LLM output). |
| D-047 | Optimistic locking: `invoices.version` integer, which the client echoes on every write. A mismatch returns `409 conflict`. | Two reviewers on the same bill must not silently overwrite each other. No long-held locks. | Pessimistic locks or "checked out by" (bad UX when someone leaves a tab open). |
| D-048 | `JobQueue` interface with an `InProcessJobQueue` (a thread pool fed by a `queue.Queue`). The bill's DB status is the durable source of truth. On startup, bills stuck in `queued`/`processing` are re-enqueued. | No Redis needed for the MVP, and no lost work on restart. | Celery + Redis now (more infrastructure for the demo). |
| D-049 | Extraction retries: up to 3 attempts with exponential backoff (2 s, 8 s) for transient provider errors (timeout, rate limit, 5xx). The OpenAI client itself has `max_retries=2` and a 60 s timeout. | Rides out short rate-limit bursts without hammering the provider. | No retry. |
| D-050 | `FileStorage` interface with `LocalFileStorage`. Files are stored under `storage/<company_id>/<invoice_id>/<sha256>.<ext>`. | Swappable for S3 or GCS. Tenant-scoped paths. | DB blobs. |
| D-051 | `LLMProvider` interface (`extract_from_text`, `extract_from_images`) with `OpenAIProvider` and a deterministic `FakeProvider` for tests and offline demos. | The brief asks for a swappable model vendor. Tests must not call the network. | Calling the OpenAI SDK directly from the service. |
| D-052 | The text layer goes first. If a PDF has at least 40 non-whitespace characters of text per page on average, the text goes to a text model for structuring. Otherwise pages are rendered to PNG (pypdfium2, 150 DPI, max 5 pages) and sent to the vision model. Images always go to vision. | Text-layer values are exact, and text calls are cheaper and faster. Vision only where unavoidable. | Always vision (costlier, OCR mistakes on digits). |
| D-053 | **Grounding check:** after text-layer extraction, if a field's value appears verbatim in the PDF text, its confidence is raised to at least 0.95. If it does not appear, its confidence is capped at 0.70. | Turns "the text layer gives exact values" into a measurable confidence signal. | Trust the model's self-reported confidence. |
| D-053b | Vision-path confidences are capped at 0.90. | In testing, the vision model reported confidence 1.0 on a GSTIN it had misread (one character dropped). Self-reported confidence on scans is over-optimistic, so scanned values should never look as certain as text-layer values. | Trust the model's self-reported confidence. |
| D-054 | Default models: `gpt-4.1-mini` for text structuring, `gpt-4.1` for vision. Both are configurable through env vars. Calls use structured outputs (a JSON schema), `temperature=0`. | Non-reasoning models are fast and deterministic for extraction. `gpt-4.1` has strong vision on dense documents. | gpt-5.x reasoning models (slower; can be switched via env). |
| D-055 | The validation engine is a list of `ValidationRule` classes, each with `code` and `evaluate(context) -> list[Finding]`. Findings are replaced on each run, not appended. | Adding a rule means adding one class. Re-running after a correction always gives the current truth. | One big function. |
| D-056 | Audit trail: an append-only `audit_events` table recording actor, action, field, old value, new value, timestamp, and metadata. Written in the same DB transaction as the change it describes. | An audit record must never exist without the change, or the change without the record. | Postgres triggers (lose actor context). |
| D-057 | Auth: JWT access tokens (HS256, 8 h expiry), bcrypt password hashing (cost 12). No refresh tokens in the MVP. | Standard and simple. A finance user logs in once per working day. | Refresh token rotation (deferred). Sessions plus cookies (CSRF handling). |
| D-058 | The token is stored in `localStorage` on the frontend and sent as `Authorization: Bearer`. | Simple for an SPA on a different port in dev. Risk noted: XSS can read it. Mitigated by React escaping and no `dangerouslySetInnerHTML`. | httpOnly cookie (preferred for production; see the roadmap). |
| D-059 | Pagination: `page` (1-based) and `page_size` (default 25, max 100). Responses have the shape `{items, page, page_size, total, total_pages}`. | Offset pagination fits a review queue where users jump pages and choose rows per page. | Cursor pagination (better at very large offsets; can be added per endpoint). |
| D-060 | Error response shape: `{"error": {"code", "message", "details", "request_id"}}` for every error, including validation (422) and unhandled (500). | One shape for the frontend to handle, plus a request id for support. | FastAPI defaults (inconsistent shapes). |
| D-061 | Structured JSON logs to stdout. Each line carries `timestamp, level, logger, message, request_id, company_id, user_id`, set through `contextvars`. | Twelve-factor. Ready for Loki, CloudWatch, or Datadog without changes. | Plain text logs. |
| D-062 | Upload limits: 15 MB per file, 20 files per request, and the types PDF, PNG, JPEG, and WEBP, detected by **magic bytes** rather than extension. | Protects memory and worker time. Extensions lie. | Unlimited uploads. |
| D-063 | Indexes on every filter column, compound with `company_id` first (for example `(company_id, status)`), plus a unique `(company_id, gstin)` on vendors. | Every query is tenant-scoped, so `company_id` leads every index. | Single-column indexes. |
| D-064 | The app uses the remote Postgres in `.env` (`DB_URL`). Tests use a separate local database (`TEST_DATABASE_URL`, default `postgresql://localhost/ledgerline_test`). Tests run against real Postgres, not SQLite. | Tests must exercise real Postgres behaviour (JSONB, NUMERIC, constraints) without touching shared data. | SQLite in-memory (behaviour differs). |
| D-065 | Settings accept both `DATABASE_URL` and `DB_URL` (the latter is what the provided `.env` uses). A plain `postgresql://` scheme is normalised to `postgresql+psycopg://`. | Works with the given `.env` unchanged. | Requiring a rename. |

| D-066 | The duplicate rule only flags the **later** of two matching bills (it compares against rows uploaded earlier). | Two copies processed in parallel would otherwise flag each other, and both would be blocked from approval. Flagging only the later copy leaves the original approvable. | Flag both (the reviewer then has to un-block the original). |
| D-067 | Approval re-runs validation at decision time. If new errors appear (for example a duplicate uploaded meanwhile), approval is refused and the refreshed findings are saved. | Findings can go stale because of other bills. The control must hold at the moment money is committed. | Trust the last stored findings. |
| D-068 | A `SynchronousJobQueue` (same interface) runs jobs inline in tests and the seed script. | Deterministic tests with no sleeps or polling. The same code path as production apart from threading. | Mocking the queue (does not exercise the handler). |
| D-069 | The demo seed defaults to a deterministic offline `FakeProvider` that returns what is printed on each generated invoice. `--live` sends the samples through OpenAI instead. | The demo is reproducible, free and works offline, while still exercising the real PDF reading, grounding, matching, validation and review code. | Always calling OpenAI (cost, variability). |
| D-070 | Invoices and line items expose `pages_processed`, `extraction_model` and per-field confidence, so the UI can show *how* each value was obtained. | Reviewers trust and verify faster when they know a value came from the text layer rather than a scan. | Hide extraction metadata. |

## Frontend decisions

| ID | Decision | Why | Alternatives |
|----|----------|-----|--------------|
| D-080 | TanStack Query for server state, React Router for routing, plain React state for UI state. No Redux. | Server-state caching, polling, and invalidation are the main needs. | Redux Toolkit (more boilerplate). |
| D-081 | CSS Modules plus one token file (`src/styles/tokens.css`) of CSS custom properties for every colour, space, radius, shadow, and font size. | The single source of truth the brief requires. No runtime CSS-in-JS cost. | Tailwind (tokens spread across config and classes). |
| D-082 | Fonts are self-hosted through `@fontsource/inter` and `@fontsource/public-sans`. | Works offline. No third-party font request. | The Google Fonts CDN. |
| D-083 | Charts use Recharts with the token palette. | A small, declarative, well-known library. | Chart.js (an imperative API). |
| D-084 | Money is formatted with `Intl.NumberFormat('en-IN', {style: 'currency', currency: 'INR'})` (lakh grouping: Rs 1,23,456.00) in a tabular-numeral font feature. | Native, correct lakh and crore grouping. | A custom formatter. |
| D-085 | The document preview fetches the file with the auth header as a Blob, then shows it via an object URL (`<iframe>` for PDF, `<img>` for images). | The file endpoint is tenant-protected, so a plain `<img src>` cannot send the bearer token. | Signed URLs (deferred with S3). |
| D-086 | Colours were checked for WCAG AA: body text slate-900 on white (17:1), secondary text slate-600 on white (7.5:1), navy primary #1E3A5F with white text (11:1), teal accent #0F766E with white text (5.5:1), amber status text #92400E on #FEF3C7 (6.4:1), red status text #991B1B on #FEE2E2 (7.4:1). | The brief requires WCAG contrast. | Lighter brand colours (fail AA). |
| D-087 | Route-level code splitting (`React.lazy`) keeps Recharts out of the initial bundle (325 kB instead of 756 kB). | Faster first load for the pages used most (queue, review). | A single bundle. |
| D-088 | Chart colours `#2f5f9e` (approved) and `#1a9a8c` (pending) replaced the brand navy and teal *for chart marks only*. They passed a palette validator (lightness band, chroma, colour-blind separation, 3:1 contrast). The brand navy was too dark and too grey for data marks. The chart also has a screen-reader table. | Data marks need different properties from UI chrome. Accessibility checks were run, not eyeballed. | Brand navy and teal (failed the lightness and chroma checks). |
| D-089 | Filters, search and pagination live in the URL query string. | Shareable links ("bills from Acme last month"), and back and refresh keep state. | Component state only. |

## Out of scope for the MVP (deliberate)

| ID | Item | Note |
|----|------|------|
| D-100 | Payments, bank files, ERP sync (Tally, Zoho) | Approved bills are the hand-off point. |
| D-101 | Multi-level approval workflows and approval limits | A single reviewer approves. |
| D-102 | Email ingestion (forward invoices to an inbox) | Upload only. |
| D-103 | GSTN portal verification (live GSTIN status lookup) | Format and checksum only. |
| D-104 | User invites, SSO, password reset email | The schema supports roles. |
| D-105 | TDS computation, e-invoice IRN and QR verification | Candidates for the next phase. |
