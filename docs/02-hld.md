# Ledgerline - High-Level Design

Related: [PRD](01-prd.md) | [LLD](03-lld.md) | [Technical architecture](04-technical-architecture.md)

## 1. System context

```mermaid
flowchart LR
    AP["AP Executive / Reviewer<br/>(browser)"]
    FC["Finance Controller<br/>(browser)"]
    subgraph Ledgerline
        WEB["Web App<br/>React SPA"]
        API["Ledgerline API<br/>FastAPI"]
    end
    OAI["OpenAI API<br/>text + vision models"]
    PG[("PostgreSQL")]
    FS[("File storage<br/>local disk / S3 later")]

    AP -->|HTTPS| WEB
    FC -->|HTTPS| WEB
    WEB -->|"REST / JSON, JWT"| API
    API -->|SQL| PG
    API -->|read/write files| FS
    API -->|"HTTPS: structured extraction"| OAI
```

External dependencies:

| System | Purpose | Failure impact |
|--------|---------|----------------|
| OpenAI API | Turns invoice text or images into structured fields | New uploads wait in the retry and backoff loop, then go to `failed` (retryable). Review of existing bills is unaffected. |
| PostgreSQL | All business data and the audit trail | Full outage. Health check fails. |
| File storage | Original invoice documents | Previews and new extractions fail. Data stays intact. |

## 2. Main components

```mermaid
flowchart TB
    subgraph Frontend["Frontend (React + Vite)"]
        UI_AUTH[Auth pages]
        UI_UP[Upload]
        UI_RQ[Review queue + split view]
        UI_BILLS[Bills]
        UI_VEN[Vendors]
        UI_DASH[Dashboard]
        APICLIENT[API client + TanStack Query]
    end

    subgraph Backend["Backend (FastAPI modular monolith)"]
        direction TB
        MW["Middleware<br/>request id, JSON logging,<br/>global exception handler"]
        AUTH[Auth module<br/>JWT, bcrypt, tenant context]
        INV[Invoices module<br/>upload, list, detail, file]
        EXT[Extraction module<br/>PDF text reader, page renderer,<br/>LLMProvider]
        VAL[Validation engine<br/>one class per rule]
        VEN[Vendors module<br/>vendor matching]
        REV[Review module<br/>correct, approve, reject]
        AUD[Audit module]
        DASH[Dashboard module]
        JOBS[JobQueue<br/>in-process worker pool]
        STORE[FileStorage]
    end

    APICLIENT --> MW
    MW --> AUTH & INV & REV & VEN & AUD & DASH
    INV --> STORE
    INV --> JOBS
    JOBS --> EXT
    EXT --> STORE
    EXT --> VEN
    EXT --> VAL
    REV --> VAL
    REV --> VEN
    INV & EXT & REV & VEN --> AUD
```

| Component | Responsibility |
|-----------|----------------|
| **Auth** | Sign-up (creates company + admin), login, JWT issue and verify, and building the `TenantContext` (company id + user id) for every request. |
| **Invoices** | Accepts uploads, checks size and type, stores the file, creates the bill row (`queued`), enqueues the extraction job, and serves list, detail, and file streams. |
| **Extraction** | Worker-side pipeline: open file -> detect encryption or corruption -> read text layer -> choose text or vision path -> call `LLMProvider` -> normalise -> grounding confidence -> persist. |
| **Validation engine** | Runs every registered `ValidationRule` against a bill and stores findings. Stateless apart from the duplicate lookup port. |
| **Vendors** | Matches a bill to a vendor by GSTIN, auto-creating the vendor on first sight. Lists and edits vendors. |
| **Review** | Field corrections (with optimistic locking), re-validation, approve, and reject. |
| **Audit** | Append-only event log. Writes happen inside the caller's transaction. Serves the timeline. |
| **Dashboard** | Aggregate queries: KPIs, monthly spend, and top vendors. |
| **JobQueue** | Interface for background work. The MVP runs `InProcessJobQueue` (a thread pool) and can switch to a Redis queue later. |
| **FileStorage** | Interface over document storage. The MVP runs `LocalFileStorage`, with S3 later. |

## 3. How components talk

| From | To | Mechanism | Notes |
|------|----|-----------|-------|
| Browser | API | HTTPS REST/JSON, `Authorization: Bearer <JWT>` | Multipart for uploads. Blob download for previews. |
| API routes | Services | In-process calls through FastAPI DI | Services get repositories and other services through the constructor. |
| Services | Postgres | SQLAlchemy session (one per request or job) | One transaction per use case. Audit events go in the same transaction. |
| Invoices service | Job queue | `JobQueue.enqueue("extract_invoice", {invoice_id, company_id})` | Enqueued **after** commit, so the worker always sees the row. |
| Worker | Extraction service | Direct call inside a worker thread with its own DB session | The worker sets the tenant context from the job payload. |
| Extraction | OpenAI | HTTPS through the `LLMProvider` interface | Structured outputs (JSON schema), timeout, retry. |
| Frontend | API (status) | Polling every 2 s while any bill on screen is `queued` or `processing` | Swappable for SSE or WebSocket later. |

## 4. Data flow: upload to approval

```mermaid
flowchart TD
    A[Reviewer drops files on Upload page] --> B[POST /invoices multipart]
    B --> C{Type and size valid?}
    C -- no --> C1[Per-file error returned<br/>other files continue]
    C -- yes --> D[Store file in FileStorage<br/>sha256 computed]
    D --> E[Insert invoice status=queued<br/>audit: uploaded]
    E --> F[Commit, then enqueue extract job]
    F --> G[Worker picks job<br/>status=processing]
    G --> H{File readable?}
    H -- "corrupt / password" --> H1[status=failed + reason<br/>audit: extraction_failed]
    H -- yes --> I{PDF with text layer?}
    I -- yes --> J[LLM text model structures the text<br/>grounding check raises confidence]
    I -- "no: scan or image" --> K[Render pages to PNG<br/>LLM vision model]
    J --> L[Normalise fields, store line items<br/>and per-field confidence]
    K --> L
    L --> M[Vendor matching by GSTIN<br/>auto-create vendor if new]
    M --> N[Validation engine runs all rules<br/>findings replaced]
    N --> O[status=needs_review<br/>audit: extraction_completed]
    O --> P[Reviewer opens split view]
    P --> Q{Data correct?}
    Q -- no --> R[Correct field, version checked<br/>audit: field_corrected]
    R --> N
    Q -- yes --> S{Any error findings?}
    S -- yes --> T[Approve blocked<br/>correct or reject]
    T --> U[Reject with reason<br/>status=rejected, audit]
    S -- no --> V[Approve<br/>status=approved, audit]
```

### Bill lifecycle

```mermaid
stateDiagram-v2
    [*] --> queued: upload accepted
    queued --> processing: worker picks job
    processing --> needs_review: extraction + validation done
    processing --> failed: unreadable file or provider failure after retries
    processing --> queued: transient error, retry scheduled
    failed --> queued: retry extraction
    needs_review --> needs_review: field corrected (re-validated)
    needs_review --> approved: approve (no error findings)
    needs_review --> rejected: reject (reason required)
    approved --> [*]
    rejected --> [*]
```

## 5. High-level architecture

```mermaid
flowchart TB
    subgraph Client
        B[Browser: React SPA<br/>served by Vite in dev, CDN or Nginx in prod]
    end

    subgraph AppTier["Application tier (stateless, horizontally scalable)"]
        direction LR
        subgraph API1["API process"]
            R[Routers] --> S[Services] --> RP[Repositories]
            S --> Q[JobQueue]
            W[Worker threads] --> S
            Q --> W
        end
    end

    subgraph DataTier["Data tier"]
        PG[(PostgreSQL<br/>multi-tenant by company_id)]
        FS[(FileStorage<br/>local volume / S3)]
    end

    subgraph External
        OAI[OpenAI API]
    end

    B -- "HTTPS JSON + JWT" --> R
    RP --> PG
    S --> FS
    W --> OAI
```

**Target (scaled) architecture.** The same code, with the worker moved out of process. See [Technical architecture section 8](04-technical-architecture.md#8-scaling-horizontally).

```mermaid
flowchart LR
    LB[Load balancer] --> A1[API pod 1] & A2[API pod 2] & A3[API pod N]
    A1 & A2 & A3 -- enqueue --> RQ[(Redis queue)]
    RQ --> W1[Worker pod 1] & W2[Worker pod N]
    A1 & A2 & A3 & W1 & W2 --> PGP[(Postgres primary)]
    PGP --> PGR[(Read replica<br/>dashboard, lists)]
    A1 & A2 & A3 & W1 & W2 --> S3[(S3)]
    W1 & W2 --> OAI[OpenAI]
```

## 6. Key quality attributes

| Attribute | How it is achieved |
|-----------|--------------------|
| **Tenant isolation** | `company_id` comes from the JWT. Tenant-scoped repositories filter every query. Composite indexes lead with `company_id`. Covered by tests. |
| **Correctness of money** | `NUMERIC(14,2)` and `Decimal` end to end. Strings in JSON. |
| **Auditability** | Append-only `audit_events`, written in the same transaction as the change. |
| **Resilience** | Background jobs with retry and backoff. Durable status in the DB. Re-enqueue on restart. |
| **Swappability** | `LLMProvider`, `JobQueue`, and `FileStorage` interfaces. |
| **Observability** | JSON logs with request id and tenant. Consistent error envelope carrying `request_id`. |
