# Ledgerline

**Accounts payable automation for Indian businesses.**

A finance team uploads vendor invoices as PDFs or phone photos. Ledgerline reads every field with AI, checks each invoice for GST compliance errors, arithmetic mistakes and duplicates, and places it in a review queue. A reviewer corrects anything that is wrong, then approves or rejects the bill. Every change is recorded in an audit trail that shows who changed what, from which value to which, and when.

**[Watch the demo video](https://www.youtube.com/watch?v=avyh8P1E02o&t=2s)**

| | |
|---|---|
| **Demo video** | [youtube.com/watch?v=avyh8P1E02o](https://www.youtube.com/watch?v=avyh8P1E02o&t=2s) |
| **Live backend API** | [apiwish.collabup.co.in](https://apiwish.collabup.co.in): [health check](https://apiwish.collabup.co.in/api/v1/health), [interactive API docs](https://apiwish.collabup.co.in/docs) |
| **Backend** | Python 3.12, FastAPI, SQLAlchemy 2, Alembic, Pydantic v2, PostgreSQL |
| **Frontend** | React 19, TypeScript, Vite, TanStack Query, CSS Modules with a single design-token file |
| **AI** | OpenAI (`gpt-4.1-mini` for PDF text, `gpt-4.1` for scans), behind a swappable provider interface |
| **Quality** | 88 backend tests on real Postgres, Vitest, Ruff, mypy (strict), ESLint, Prettier |
| **Demo login** | `demo@ledgerline.in` / `Demo@12345` (after `make seed`) |

```bash
cp .env.example .env      # add DB_URL and OPENAI_API_KEY
make setup && make migrate && make seed
make backend              # http://localhost:8000  (API docs at /docs)
make frontend             # http://localhost:5173
```

**Contents**

- [Why Ledgerline exists](#why-ledgerline-exists)
- [Where it sits](#where-it-sits)
- [How it is built](#how-it-is-built)
- [The life of a bill](#the-life-of-a-bill)
- [Upload](#upload)
- [Extraction](#extraction)
- [Validation](#validation)
- [Review, approval and the audit trail](#review-approval-and-the-audit-trail)
- [Data model](#data-model)
- [Inside the code](#inside-the-code)
- [Errors, logging and security](#errors-logging-and-security)
- [What a user does](#what-a-user-does)
- [Edge cases](#edge-cases)
- [Scaling later](#scaling-later)
- [Running it locally](#running-it-locally)
- [Documentation](#documentation)
- [Screenshots](#screenshots)

---

## Why Ledgerline exists

Finance teams at Indian small and mid-size businesses receive hundreds of vendor invoices a month. Today someone types each one into a spreadsheet or ERP, which takes 4 to 8 minutes an invoice. Compliance errors slip through: an invalid GSTIN, IGST charged on a same-state purchase, or tax that doesn't match the GST slab. Any of these can cost the company its input tax credit. The same invoice arrives by email and by courier and gets paid twice. And when an auditor asks who changed an amount, nobody can say.

Ledgerline targets a reviewer time of **under one minute per bill**. It catches compliance errors and duplicates **before** approval, and gives every bill a complete history. The MVP scope, out-of-scope items and success metrics are in the [product requirements](docs/01-prd.md).

## Where it sits

Ledgerline is a web app in front of one API. The API relies on three things it does not own:

- **PostgreSQL** for all business data and the audit trail.
- **File storage** for the original documents.
- **OpenAI** to turn invoice text or images into structured fields.

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

The failure modes are deliberately different. If OpenAI is slow or down, new uploads wait and retry, but reviewers keep working on bills that were already extracted. If Postgres is down, everything stops and the health check reports it.

## How it is built

The backend is a **modular monolith**: one FastAPI service, organised by feature (auth, invoices, extraction, validation, vendors, review, audit, dashboard). It runs as a single process for the MVP, but nothing in it assumes a single machine.

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

Each feature owns its own models, schemas, repository, service, dependency wiring and router. The main components and how they call each other:

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

| Component | What it is responsible for |
|-----------|----------------------------|
| **Auth** | Sign-up (creates the company and its first admin), login, issuing and verifying login tokens (JWTs), and the tenant context for every request |
| **Invoices** | Accepting uploads, checking size and real file type, storing the file, creating the bill, queueing extraction, and serving lists, details and the original document |
| **Extraction** | Reading the document, choosing text-layer or vision, calling the AI provider, cleaning the values and scoring confidence |
| **Validation** | Running every rule against a bill and storing the findings |
| **Vendors** | Matching a bill to a vendor by GSTIN, creating the vendor the first time it appears, listing and renaming vendors |
| **Review** | Field corrections with conflict protection, re-validation, approve and reject |
| **Audit** | An append-only record of every change, written in the same transaction as the change itself |
| **Dashboard** | Monthly totals, pending amounts, approval rate and spend charts |

Inside every feature, code follows the same strict layering. Routes only talk to services. Services hold the business rules and own the database transaction. Repositories are the only place that builds queries. External services (the AI provider, the job queue, file storage) are reached through interfaces, so each can be replaced without touching business logic.

```mermaid
flowchart LR
    R["API router<br/>(Pydantic schemas in/out)"] --> S["Service<br/>(business rules, transactions)"]
    S --> RP["Repository<br/>(SQLAlchemy queries)"]
    RP --> M["Domain model<br/>(SQLAlchemy ORM)"]
    S --> P["Ports<br/>LLMProvider, JobQueue, FileStorage"]
```

## The life of a bill

From the moment a file is dropped on the Upload page to the moment it is approved, a bill goes through these steps:

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

Each bill's status is stored in the database and moves only along these transitions:

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

| Status | Meaning |
|--------|---------|
| `queued` | Uploaded and waiting for a worker |
| `processing` | A worker is reading it now |
| `needs_review` | Extracted and validated, waiting for a human decision. **Nothing is approved automatically.** |
| `approved` / `rejected` | Final. The bill becomes read-only. |
| `failed` | The file could not be read, or the AI service kept failing. The reason is shown, with a **Retry extraction** button. |

## Upload

A reviewer can drop up to 20 files at once (PDF, PNG, JPG or WEBP, up to 15 MB each). The file type is decided from the file's first bytes, never from its name, so a renamed `.docx` is rejected. Each file is accepted or rejected on its own, so one bad file doesn't fail the batch. The file's fingerprint (SHA-256 hash) is recorded so exact duplicates can be spotted later. The extraction job is queued only **after** the database commit, so a worker never looks for a bill that isn't saved yet.

```mermaid
sequenceDiagram
    autonumber
    actor U as Reviewer
    participant FE as React Upload page
    participant API as InvoicesRouter
    participant DEP as Auth dependency
    participant SVC as InvoiceService
    participant ST as FileStorage
    participant REPO as InvoiceRepository
    participant AUD as AuditService
    participant DB as Postgres
    participant Q as JobQueue

    U->>FE: Drop 3 files
    FE->>API: POST /api/v1/invoices (multipart, Bearer JWT)
    API->>DEP: get_tenant()
    DEP-->>API: TenantContext(company_id, user_id)
    API->>SVC: upload_many(files)
    loop each file
        SVC->>SVC: read with size cap (15 MB), sniff magic bytes
        alt invalid type or too large
            SVC-->>SVC: UploadResult(error=unsupported_file_type or file_too_large)
        else valid
            SVC->>SVC: sha256(bytes)
            SVC->>REPO: add(Invoice status=queued)
            SVC->>ST: save(company/invoice/sha.ext, bytes)
            SVC->>AUD: record(invoice_uploaded)
        end
    end
    SVC->>DB: COMMIT
    loop each accepted invoice
        SVC->>Q: enqueue("extract_invoice", {invoice_id, company_id})
    end
    SVC-->>API: list of UploadResult
    API-->>FE: 202 {results: [...]}
    loop every 2 s while queued or processing
        FE->>API: GET /invoices?ids=...
        API-->>FE: statuses
    end
```

The Upload page shows a progress bar for each file, then polls every two seconds until extraction finishes. Each row ends as ready for review (with its error and warning counts), or failed with a readable reason and a Retry button.

## Extraction

Extraction runs in the background, so the upload request returns immediately. The key rule is **text layer first**. A PDF exported from accounting software contains its actual text, which gives exact values. Ledgerline reads that text and asks a small, fast text model (`gpt-4.1-mini`) to structure it. Only scanned PDFs and photos, which have no text, go to the vision model (`gpt-4.1`). The page images are rendered at 150 DPI, with at most 5 pages sent.

```mermaid
sequenceDiagram
    autonumber
    participant Q as InProcessJobQueue worker thread
    participant EX as ExtractionService
    participant REPO as InvoiceRepository
    participant ST as FileStorage
    participant DR as DocumentReader
    participant LLM as LLMProvider (OpenAI)
    participant GR as ConfidenceGrounder
    participant VM as VendorMatchingService
    participant VS as ValidationService
    participant AUD as AuditService
    participant DB as Postgres

    Q->>EX: process(invoice_id) with new Session + TenantContext
    EX->>REPO: get_for_update(invoice_id)
    EX->>DB: status=processing, attempts+1, COMMIT
    EX->>ST: read(storage_key)
    EX->>DR: read(bytes, content_type)
    alt corrupt or password-protected
        DR-->>EX: UnreadableDocumentError / PasswordProtectedDocumentError
        EX->>DB: status=failed, error_message, audit extraction_failed, COMMIT
    else PDF with text layer
        DR-->>EX: DocumentContent(method=text_layer, text)
        EX->>LLM: extract_from_text(text)
        LLM-->>EX: ExtractedInvoice
        EX->>GR: ground(result, text)
        GR-->>EX: confidence adjusted
    else scanned PDF or image
        DR-->>EX: DocumentContent(method=vision, images<=5)
        EX->>LLM: extract_from_images(images)
        LLM-->>EX: ExtractedInvoice
    end
    EX->>EX: normalise (dates, decimals, GSTIN upper-case)
    EX->>REPO: apply header fields + replace line items
    EX->>VM: match(invoice)
    VM-->>EX: vendor linked or created (audit vendor_created)
    EX->>VS: validate(invoice)
    VS-->>EX: findings
    EX->>DB: status=needs_review, audit extraction_completed, COMMIT
    Note over Q,EX: ProviderTransientError -> rollback, status=queued,<br/>re-enqueue after backoff (2 s, 8 s). After 3 attempts -> failed.
```

Every extracted field carries a **confidence score**, and Ledgerline does not simply trust the model's own estimate:

- **Text-layer values are checked against the PDF text.** A value that literally appears in the document is raised to at least 0.95. A value that doesn't appear (one the model inferred) is capped at 0.70.
- **Vision values are capped at 0.90.** In testing, the vision model misread one character of a GSTIN while claiming full confidence, so scans never look as certain as text.
- **Cleaning before saving.** Dates in Indian day-first formats, amounts with lakh commas or a ₹ sign, and lowercase or spaced GSTINs are all normalised. Anything that can't be parsed is kept in its raw form and marked confidence 0.

The AI vendor is hidden behind an `LLMProvider` interface. There is a real `OpenAIProvider` and a deterministic `FakeProvider`, which the tests and the offline demo seed use. Background jobs sit behind a `JobQueue` interface, and documents behind `FileStorage`:

```mermaid
classDiagram
    direction LR
    class LLMProvider {
        <<abstract>>
        +name str
        +extract_from_text(text str) ExtractedInvoice
        +extract_from_images(images list~bytes~) ExtractedInvoice
    }
    class OpenAIProvider {
        -OpenAI client
        -str text_model
        -str vision_model
        +extract_from_text(text) ExtractedInvoice
        +extract_from_images(images) ExtractedInvoice
    }
    class FakeProvider {
        +ExtractedInvoice fixed_result
        +extract_from_text(text) ExtractedInvoice
        +extract_from_images(images) ExtractedInvoice
    }
    class ExtractedInvoice {
        <<Pydantic>>
        +ExtractedField vendor_name
        +ExtractedField vendor_gstin
        +ExtractedField buyer_gstin
        +ExtractedField invoice_number
        +ExtractedField invoice_date
        +ExtractedField due_date
        +list~ExtractedLineItem~ line_items
        +ExtractedField subtotal
        +ExtractedField cgst
        +ExtractedField sgst
        +ExtractedField igst
        +ExtractedField total
    }
    class ExtractedField {
        <<Pydantic>>
        +str value
        +float confidence
    }
    class DocumentReader {
        +read(data bytes, content_type str) DocumentContent
    }
    class DocumentContent {
        <<dataclass>>
        +int page_count
        +str text
        +list~bytes~ images
        +ExtractionMethod method
    }
    class ConfidenceGrounder {
        +ground(result ExtractedInvoice, text str) ExtractedInvoice
    }
    class JobQueue {
        <<abstract>>
        +register(name str, handler JobHandler) None
        +enqueue(name str, payload dict) None
        +start() None
        +stop() None
    }
    class InProcessJobQueue {
        -Queue queue
        -list~Thread~ workers
        -int max_attempts
        +enqueue(name, payload) None
    }
    class FileStorage {
        <<abstract>>
        +save(key str, data bytes) None
        +read(key str) bytes
        +exists(key str) bool
    }
    class LocalFileStorage {
        -Path root
    }

    LLMProvider <|-- OpenAIProvider
    LLMProvider <|-- FakeProvider
    LLMProvider ..> ExtractedInvoice
    ExtractedInvoice *-- ExtractedField
    DocumentReader ..> DocumentContent
    JobQueue <|-- InProcessJobQueue
    FileStorage <|-- LocalFileStorage
```

The job queue is currently a small in-process thread pool. It is built to survive restarts and outages:

```mermaid
flowchart LR
    subgraph API_Process["API process"]
        R[POST /invoices] -->|"commit, then enqueue"| Q[(queue.Queue)]
        subgraph Pool["Worker threads (EXTRACTION_WORKERS, default 3)"]
            W1[worker 1]
            W2[worker 2]
            W3[worker 3]
        end
        Q --> W1 & W2 & W3
        W1 & W2 & W3 --> H[handler: extract_invoice]
        H --> ES[ExtractionService.process]
        H -.->|"transient error: Timer(backoff) re-enqueue"| Q
        L[lifespan startup] -->|"re-enqueue queued/processing bills"| Q
    end
    ES --> DB[(Postgres)]
```

- **Durable.** The bill's status in Postgres is the source of truth. On startup, any bill left in `queued` or `processing` is put back on the queue, so a restart loses no work.
- **Retries.** Timeouts, rate limits and server errors from OpenAI are retried twice by the SDK, then up to 3 job attempts with waits of 2 s and 8 s. After that the bill becomes `failed`, with a message that the AI service is busy, and can be retried from the UI.
- **Safe to re-run.** Line items and findings are replaced, never appended, so running a job twice gives the same result.
- **Ready for Redis.** Job payloads are plain JSON, so swapping in RQ, Arq or Celery means writing one new queue class and running workers as a separate process. No business code changes.

## Validation

After extraction, and again after every correction, the validation engine runs a list of independent rules. Each rule is its own class behind one shared interface. Adding a check means adding one class.

```mermaid
classDiagram
    direction TB
    class ValidationRule {
        <<abstract>>
        +code str
        +evaluate(ctx ValidationContext) list~FindingDraft~
    }
    class ValidationContext {
        <<dataclass>>
        +InvoiceSnapshot invoice
        +str company_gstin
        +DuplicateLookup duplicates
    }
    class InvoiceSnapshot {
        <<dataclass>>
        +UUID id
        +header fields
        +list~LineSnapshot~ lines
        +dict field_confidence
        +str file_sha256
    }
    class DuplicateLookup {
        <<Protocol>>
        +find_duplicates(vendor_gstin, invoice_number, total, exclude_id) list
        +find_by_sha256(sha256, exclude_id) list
    }
    class FindingDraft {
        <<dataclass>>
        +str rule_code
        +Severity severity
        +str field
        +str message
    }
    class ValidationEngine {
        -list~ValidationRule~ rules
        +evaluate(ctx) list~FindingDraft~
    }
    class RequiredFieldsRule
    class LowConfidenceRule
    class GstinFormatRule
    class DuplicateInvoiceRule
    class LineItemArithmeticRule
    class TotalsRule
    class TaxRateRule
    class TaxTypeRule

    ValidationRule <|-- RequiredFieldsRule
    ValidationRule <|-- LowConfidenceRule
    ValidationRule <|-- GstinFormatRule
    ValidationRule <|-- DuplicateInvoiceRule
    ValidationRule <|-- LineItemArithmeticRule
    ValidationRule <|-- TotalsRule
    ValidationRule <|-- TaxRateRule
    ValidationRule <|-- TaxTypeRule
    ValidationEngine o-- ValidationRule
    ValidationEngine ..> ValidationContext
    ValidationContext *-- InvoiceSnapshot
    ValidationContext --> DuplicateLookup
    ValidationRule ..> FindingDraft
```

| Rule | What it checks | Severity |
|------|----------------|----------|
| Required fields | Vendor name, vendor GSTIN, invoice number, date and total are present. Due date, buyer GSTIN and at least one line item are recommended. | error / warning |
| GSTIN format | 15 characters, the official pattern, a valid state code, and the mod-36 check digit. The buyer GSTIN should match your company. | error / warning |
| Duplicate | An earlier bill with the same vendor GSTIN, invoice number and total, or the exact same file | error |
| Line-item arithmetic | Quantity × rate = amount on every line, and the lines add up to the subtotal (₹1 tolerance) | error |
| Totals | Subtotal + CGST + SGST + IGST = total. A gap of up to ₹1 is reported as normal round-off. | error / info |
| Tax rate | CGST equals SGST, and the effective rate matches a GST slab (0, 0.25, 3, 5, 12, 18, 28 or 40 %) | error / warning |
| Tax type | Same-state supply means CGST + SGST; different states means IGST. The states come from the GSTINs. | error |
| Low confidence | Any field read with confidence below 60 % | warning |

Severities have a clear meaning. **Errors block approval**: the reviewer must correct the data or reject the bill. **Warnings** need a look but don't block. **Info** is context only, such as "this ₹0.40 difference looks like round-off". Every finding is a plain-English sentence with the actual numbers, for example: *"Line items add up to ₹68,700.00 but the subtotal says ₹63,000.00 (difference ₹5,700.00)."*

Each run replaces the previous findings, so what you see always reflects the current data:

```mermaid
sequenceDiagram
    autonumber
    participant C as Caller (ExtractionService / ReviewService)
    participant VS as ValidationService
    participant ENG as ValidationEngine
    participant R as Rules (8 classes)
    participant DL as DuplicateLookup (InvoiceRepository)
    participant FR as Invoice aggregate

    C->>VS: validate(invoice)
    VS->>VS: build InvoiceSnapshot + ValidationContext(company_gstin, duplicates=DL)
    VS->>ENG: evaluate(ctx)
    loop each rule in registry order
        ENG->>R: evaluate(ctx)
        opt DuplicateInvoiceRule
            R->>DL: find_duplicates(gstin, number, total, exclude_id)
            R->>DL: find_by_sha256(sha, exclude_id)
        end
        R-->>ENG: list of FindingDraft
    end
    ENG-->>VS: all drafts (sorted by severity)
    VS->>FR: invoice.findings = new findings (delete-orphan removes the old run)
    VS->>VS: invoice.error_count, warning_count = counts
    VS-->>C: findings (caller commits)
```

## Review, approval and the audit trail

The reviewer works in a split view: the original document on the left, and the findings, extracted fields, line items and history on the right. Clicking any value turns it into an input. Enter saves and Escape cancels. Saving records an audit event, marks the field as human-verified, re-matches the vendor if the GSTIN changed, and re-runs validation. The new findings appear immediately.

```mermaid
sequenceDiagram
    autonumber
    actor U as Reviewer
    participant FE as Split view
    participant API as ReviewRouter
    participant RS as ReviewService
    participant REPO as InvoiceRepository
    participant VM as VendorMatchingService
    participant VS as ValidationService
    participant AUD as AuditService
    participant DB as Postgres

    U->>FE: Edit "Total" 11,800 -> 11,700, press Enter
    FE->>API: PATCH /invoices/{id}/fields {version: 3, changes: [{field: total, value: "11700"}]}
    API->>RS: correct_fields(id, 3, changes)
    RS->>REPO: get_for_update(id) (SELECT ... FOR UPDATE)
    alt invoice.version != 3
        RS-->>API: ConflictError
        API-->>FE: 409 {code: version_conflict}
        FE-->>U: "Changed by someone else. Reloaded latest."
    else not editable (approved or rejected)
        RS-->>API: 409 invalid_state
    else ok
        RS->>RS: parse value by field type (Decimal / date / GSTIN)
        RS->>AUD: record(field_corrected, field=total, old=11800.00, new=11700.00)
        RS->>RS: confidence[total] = 1.0 (human-verified)
        opt vendor_gstin changed
            RS->>VM: match(invoice)
        end
        RS->>VS: validate(invoice)
        RS->>DB: version = 4, COMMIT
        RS-->>API: InvoiceDetail
        API-->>FE: 200 detail (new findings, version 4)
    end

    U->>FE: Click Approve
    FE->>API: POST /invoices/{id}/approve {version: 4}
    API->>RS: approve(id, 4, comment)
    RS->>REPO: get_for_update(id)
    alt error findings exist
        RS-->>API: 422 approval_blocked
    else
        RS->>DB: status=approved, reviewed_by, reviewed_at, version=5
        RS->>AUD: record(invoice_approved)
        RS->>DB: COMMIT
        API-->>FE: 200 detail
    end
```

Two reviewers may open the same bill at once. Every bill has a **version number**, and every edit, approval or rejection must send the version the reviewer last saw. If someone else has saved in the meantime, the second write is refused with a clear message, and the screen reloads to show the latest data and who changed what. Nothing is silently overwritten.

Approval re-runs validation at the moment of approval, so a duplicate uploaded a minute ago still blocks it. Rejection always requires a reason. Every upload, extraction, correction, vendor change, approval and rejection is stored as an audit event in the same database transaction as the change itself. There can never be a change without its record, or a record without its change.

## Data model

Every table except `companies` carries a `company_id`. That is how one database safely serves many companies: the company is always taken from the user's login token, never from anything the browser sends.

```mermaid
erDiagram
    companies ||--o{ users : "employs"
    companies ||--o{ vendors : "buys from"
    companies ||--o{ invoices : "receives"
    companies ||--o{ invoice_line_items : "owns"
    companies ||--o{ validation_findings : "owns"
    companies ||--o{ audit_events : "owns"
    vendors |o--o{ invoices : "billed by"
    users ||--o{ invoices : "uploaded"
    users |o--o{ invoices : "reviewed"
    invoices ||--o{ invoice_line_items : "contains"
    invoices ||--o{ validation_findings : "has"
    invoices |o--o{ audit_events : "history"
    users |o--o{ audit_events : "acted"

    companies {
        uuid id PK
        varchar_200 name "NOT NULL"
        varchar_15 gstin "NULL"
        varchar_2 state_code "NULL, from GSTIN"
        timestamptz created_at "NOT NULL default now()"
        timestamptz updated_at "NOT NULL default now()"
    }
    users {
        uuid id PK
        uuid company_id FK "NOT NULL -> companies.id"
        varchar_320 email UK "NOT NULL, lower-cased"
        varchar_200 full_name "NOT NULL"
        varchar_255 password_hash "NOT NULL, bcrypt"
        varchar_20 role "NOT NULL admin or reviewer"
        boolean is_active "NOT NULL default true"
        timestamptz last_login_at "NULL"
        timestamptz created_at "NOT NULL"
        timestamptz updated_at "NOT NULL"
    }
    vendors {
        uuid id PK
        uuid company_id FK "NOT NULL"
        varchar_15 gstin "NOT NULL, UK with company_id"
        varchar_300 legal_name "NOT NULL"
        varchar_300 display_name "NOT NULL"
        varchar_2 state_code "NOT NULL"
        timestamptz created_at "NOT NULL"
        timestamptz updated_at "NOT NULL"
    }
    invoices {
        uuid id PK
        uuid company_id FK "NOT NULL"
        uuid vendor_id FK "NULL -> vendors.id"
        uuid uploaded_by_id FK "NOT NULL -> users.id"
        uuid reviewed_by_id FK "NULL -> users.id"
        varchar_20 status "NOT NULL"
        varchar_255 original_filename "NOT NULL"
        varchar_500 storage_key "NOT NULL"
        varchar_100 content_type "NOT NULL"
        integer file_size_bytes "NOT NULL"
        char_64 file_sha256 "NOT NULL"
        integer page_count "NULL"
        varchar_20 extraction_method "NULL text_layer or vision"
        integer extraction_attempts "NOT NULL default 0"
        text error_message "NULL"
        varchar_300 vendor_name "NULL"
        varchar_32 vendor_gstin "NULL, raw may be invalid"
        varchar_32 buyer_gstin "NULL"
        varchar_100 invoice_number "NULL"
        date invoice_date "NULL"
        date due_date "NULL"
        char_3 currency "NOT NULL default INR"
        numeric_14_2 subtotal "NULL"
        numeric_14_2 cgst "NULL"
        numeric_14_2 sgst "NULL"
        numeric_14_2 igst "NULL"
        numeric_14_2 total "NULL"
        jsonb field_confidence "NOT NULL default {}"
        jsonb raw_extraction "NULL"
        integer error_count "NOT NULL default 0"
        integer warning_count "NOT NULL default 0"
        text rejection_reason "NULL"
        text review_comment "NULL"
        timestamptz reviewed_at "NULL"
        integer version "NOT NULL default 1, optimistic lock"
        timestamptz created_at "NOT NULL"
        timestamptz updated_at "NOT NULL"
    }
    invoice_line_items {
        uuid id PK
        uuid company_id FK "NOT NULL"
        uuid invoice_id FK "NOT NULL ON DELETE CASCADE"
        integer position "NOT NULL"
        text description "NULL"
        varchar_20 hsn_sac "NULL"
        numeric_14_3 quantity "NULL"
        numeric_14_2 rate "NULL"
        numeric_14_2 amount "NULL"
        jsonb confidence "NOT NULL default {}"
        timestamptz created_at "NOT NULL"
        timestamptz updated_at "NOT NULL"
    }
    validation_findings {
        uuid id PK
        uuid company_id FK "NOT NULL"
        uuid invoice_id FK "NOT NULL ON DELETE CASCADE"
        varchar_50 rule_code "NOT NULL"
        varchar_10 severity "NOT NULL error, warning or info"
        varchar_100 field "NULL"
        text message "NOT NULL"
        timestamptz created_at "NOT NULL"
    }
    audit_events {
        uuid id PK
        uuid company_id FK "NOT NULL"
        uuid invoice_id FK "NULL"
        varchar_30 entity_type "NOT NULL invoice, vendor, line_item"
        uuid entity_id "NOT NULL"
        varchar_40 action "NOT NULL"
        uuid actor_user_id FK "NULL means system"
        varchar_100 field_name "NULL"
        text old_value "NULL"
        text new_value "NULL"
        jsonb details "NOT NULL default {}"
        timestamptz created_at "NOT NULL"
    }
```

The code-level view of the same model:

```mermaid
classDiagram
    direction LR
    class Base {
        <<SQLAlchemy DeclarativeBase>>
    }
    class TimestampMixin {
        +datetime created_at
        +datetime updated_at
    }
    class TenantMixin {
        +UUID company_id
    }
    class Company {
        +UUID id
        +str name
        +str gstin
        +str state_code
    }
    class User {
        +UUID id
        +UUID company_id
        +str email
        +str full_name
        +str password_hash
        +UserRole role
        +bool is_active
        +datetime last_login_at
    }
    class Vendor {
        +UUID id
        +UUID company_id
        +str gstin
        +str legal_name
        +str display_name
        +str state_code
    }
    class Invoice {
        +UUID id
        +UUID company_id
        +UUID vendor_id
        +InvoiceStatus status
        +str original_filename
        +str storage_key
        +str content_type
        +int file_size_bytes
        +str file_sha256
        +int page_count
        +ExtractionMethod extraction_method
        +int extraction_attempts
        +str error_message
        +str vendor_name
        +str vendor_gstin
        +str buyer_gstin
        +str invoice_number
        +date invoice_date
        +date due_date
        +Decimal subtotal
        +Decimal cgst
        +Decimal sgst
        +Decimal igst
        +Decimal total
        +dict field_confidence
        +dict raw_extraction
        +int error_count
        +int warning_count
        +str rejection_reason
        +str review_comment
        +datetime reviewed_at
        +int version
        +is_editable() bool
    }
    class InvoiceLineItem {
        +UUID id
        +UUID company_id
        +UUID invoice_id
        +int position
        +str description
        +str hsn_sac
        +Decimal quantity
        +Decimal rate
        +Decimal amount
        +dict confidence
    }
    class ValidationFinding {
        +UUID id
        +UUID company_id
        +UUID invoice_id
        +str rule_code
        +Severity severity
        +str field
        +str message
    }
    class AuditEvent {
        +UUID id
        +UUID company_id
        +UUID invoice_id
        +str entity_type
        +UUID entity_id
        +AuditAction action
        +UUID actor_user_id
        +str field_name
        +str old_value
        +str new_value
        +dict details
        +datetime created_at
    }
    class InvoiceStatus {
        <<enumeration>>
        queued
        processing
        needs_review
        approved
        rejected
        failed
    }
    class Severity {
        <<enumeration>>
        error
        warning
        info
    }
    class ExtractionMethod {
        <<enumeration>>
        text_layer
        vision
    }

    Base <|-- Company
    Base <|-- User
    Base <|-- Vendor
    Base <|-- Invoice
    Base <|-- InvoiceLineItem
    Base <|-- ValidationFinding
    Base <|-- AuditEvent
    TimestampMixin <|.. Company
    TimestampMixin <|.. User
    TimestampMixin <|.. Vendor
    TimestampMixin <|.. Invoice
    TimestampMixin <|.. InvoiceLineItem
    TenantMixin <|.. User
    TenantMixin <|.. Vendor
    TenantMixin <|.. Invoice
    TenantMixin <|.. InvoiceLineItem
    TenantMixin <|.. ValidationFinding
    TenantMixin <|.. AuditEvent

    Company "1" --> "*" User
    Company "1" --> "*" Vendor
    Company "1" --> "*" Invoice
    Vendor "0..1" --> "*" Invoice
    Invoice "1" *-- "*" InvoiceLineItem
    Invoice "1" *-- "*" ValidationFinding
    Invoice "1" --> "*" AuditEvent
    User "1" --> "*" AuditEvent : actor
    Invoice --> InvoiceStatus
    ValidationFinding --> Severity
    Invoice --> ExtractionMethod
```

A few choices matter for correctness:

- **Money** is `NUMERIC(14,2)` in Postgres, `Decimal` in Python, and a string in JSON, so no rounding happens anywhere.
- **Indexes** exist for every filter column, always with `company_id` first (for example `(company_id, status)` for the review queue).
- **Vendors** are unique per company and GSTIN, which also stops two parallel extractions from creating the same vendor twice.
- **Enum columns** carry database CHECK constraints.

The full list of keys, constraints and indexes is in [LLD section 8](docs/03-lld.md#8-database).

## Inside the code

Repositories hide every database query. Tenant repositories are created with the current company and add the `company_id` filter to every query automatically. Asking for another company's bill returns "not found", so the API doesn't even reveal that the bill exists.

```mermaid
classDiagram
    direction TB
    class TenantContext {
        <<dataclass, frozen>>
        +UUID company_id
        +UUID user_id
    }
    class BaseRepository~T~ {
        #Session session
        #type~T~ model
        +add(entity T) T
        +flush() None
    }
    class TenantRepository~T~ {
        #TenantContext tenant
        +get(id UUID) T
        +get_or_raise(id UUID) T
        #scoped() Select
    }
    class CompanyRepository {
        +get(id UUID) Company
    }
    class UserRepository {
        +get_by_email(email str) User
        +get(id UUID) User
    }
    class VendorRepository {
        +get_by_gstin(gstin str) Vendor
        +list_with_stats(search, page) Page~VendorRow~
        +stats_for(id UUID) VendorRow
    }
    class InvoiceRepository {
        +get_for_update(id UUID) Invoice
        +search(filters InvoiceFilters, page PageParams) Page~Invoice~
        +find_duplicates(vendor_gstin, invoice_number, total, exclude_id) list~Invoice~
        +find_by_sha256(sha256, exclude_id) list~Invoice~
        +list_ids_by_status(statuses) list~tuple~
    }
    class LineItemRepository {
        +get_for_invoice(invoice_id, item_id) InvoiceLineItem
    }
    class AuditRepository {
        +add_event(event AuditEvent) AuditEvent
        +list_for_invoice(invoice_id, page) Page~AuditEvent~
    }
    class DashboardRepository {
        +total_between(start, end) tuple
        +status_summary() dict
        +decisions_between(start, end) tuple
        +monthly_spend(since) list~MonthSpend~
        +top_vendors(since, limit) list~VendorSpend~
    }
    BaseRepository <|-- TenantRepository
    BaseRepository <|-- CompanyRepository
    BaseRepository <|-- UserRepository
    TenantRepository <|-- VendorRepository
    TenantRepository <|-- InvoiceRepository
    TenantRepository <|-- LineItemRepository
    TenantRepository <|-- AuditRepository
    TenantRepository <|-- DashboardRepository
    TenantRepository --> TenantContext
```

Services hold the business logic and receive their dependencies through their constructors, wired up by FastAPI's dependency injection. In tests, those dependencies are swapped for fakes.

```mermaid
classDiagram
    direction LR
    class PasswordHasher {
        +hash(raw str) str
        +verify(raw str, hashed str) bool
    }
    class TokenService {
        +issue(user User) AccessToken
        +decode(token str) TokenClaims
    }
    class AuthService {
        +signup(cmd SignupRequest) AuthResult
        +login(email, password) AuthResult
    }
    class AuditService {
        +record(action, invoice_id, entity_type, entity_id, field, old, new, details) AuditEvent
        +timeline(invoice_id, page) Page~AuditEvent~
    }
    class InvoiceService {
        +upload_many(files list~IncomingFile~) list~UploadOutcome~
        +list_invoices(filters, page) Page~Invoice~
        +get(id) Invoice
        +open_file(id) StoredFile
        +retry_extraction(id) Invoice
    }
    class ExtractionService {
        +process(invoice_id UUID) None
    }
    class VendorMatchingService {
        +match(invoice Invoice) MatchResult
    }
    class VendorService {
        +list_vendors(search, page) Page~VendorRow~
        +get(id) VendorRow
        +update(id, cmd VendorUpdate) Vendor
    }
    class ValidationService {
        +validate(invoice Invoice) list~ValidationFinding~
    }
    class ReviewService {
        +correct_fields(id, version, changes) InvoiceDetail
        +add_line_item(id, version, data) InvoiceDetail
        +correct_line_item(id, item_id, version, changes) InvoiceDetail
        +remove_line_item(id, item_id, version) InvoiceDetail
        +approve(id, version, comment) InvoiceDetail
        +reject(id, version, reason) InvoiceDetail
    }
    class DashboardService {
        +summary() DashboardSummary
    }

    AuthService --> PasswordHasher
    AuthService --> TokenService
    AuthService --> UserRepository
    AuthService --> CompanyRepository
    InvoiceService --> InvoiceRepository
    InvoiceService --> FileStorage
    InvoiceService --> JobQueue
    InvoiceService --> AuditService
    ExtractionService --> DocumentReader
    ExtractionService --> LLMProvider
    ExtractionService --> InvoiceNormalizer
    ExtractionService --> ConfidenceGrounder
    ExtractionService --> VendorMatchingService
    ExtractionService --> ValidationService
    ExtractionService --> AuditService
    ReviewService --> InvoiceRepository
    ReviewService --> ValidationService
    ReviewService --> VendorMatchingService
    ReviewService --> AuditService
    VendorMatchingService --> VendorRepository
    VendorMatchingService --> AuditService
    ValidationService --> ValidationEngine
    ValidationService --> InvoiceRepository : DuplicateLookup
    AuditService --> AuditRepository
    DashboardService --> DashboardRepository
```

The API layer is thin. Each router validates input with Pydantic, calls one service method, and returns a Pydantic response.

```mermaid
classDiagram
    direction LR
    class AuthRouter {
        POST /auth/signup
        POST /auth/login
        GET /auth/me
    }
    class InvoicesRouter {
        POST /invoices  multipart files[]
        GET /invoices  filters + page
        GET /invoices/:id
        GET /invoices/:id/file
        POST /invoices/:id/retry
    }
    class ReviewRouter {
        PATCH /invoices/:id/fields
        POST /invoices/:id/line-items
        PATCH /invoices/:id/line-items/:item_id
        DELETE /invoices/:id/line-items/:item_id
        POST /invoices/:id/approve
        POST /invoices/:id/reject
    }
    class AuditRouter {
        GET /invoices/:id/audit-events
    }
    class VendorsRouter {
        GET /vendors
        GET /vendors/:id
        PATCH /vendors/:id
    }
    class DashboardRouter {
        GET /dashboard/summary
    }
    class HealthRouter {
        GET /health
    }
    class Dependencies {
        <<FastAPI Depends>>
        +get_db() Session
        +get_current_user() CurrentUser
        +get_tenant() TenantContext
        +get_invoice_service() InvoiceService
        +get_review_service() ReviewService
        +get_vendor_service() VendorService
        +get_audit_service() AuditService
        +get_dashboard_service() DashboardService
    }
    AuthRouter ..> Dependencies
    InvoicesRouter ..> Dependencies
    ReviewRouter ..> Dependencies
    AuditRouter ..> Dependencies
    VendorsRouter ..> Dependencies
    DashboardRouter ..> Dependencies
```

| Endpoint | Purpose |
|----------|---------|
| `POST /api/v1/auth/signup`, `POST /auth/login`, `GET /auth/me` | Create a company and admin, sign in, get the current user |
| `POST /api/v1/invoices` | Upload one or more files (multipart) |
| `GET /api/v1/invoices` | List bills, with status, vendor, date range, amount range, search, sort and pagination |
| `GET /api/v1/invoices/{id}`, `GET /invoices/{id}/file` | Bill detail, and the original document |
| `PATCH /invoices/{id}/fields`, `POST/PATCH/DELETE /invoices/{id}/line-items` | Corrections (each carries the bill's version) |
| `POST /invoices/{id}/approve`, `POST /invoices/{id}/reject`, `POST /invoices/{id}/retry` | Decisions, and retrying extraction |
| `GET /invoices/{id}/audit-events` | The bill's history |
| `GET /api/v1/vendors`, `GET/PATCH /vendors/{id}` | Vendor list (with spend), detail, rename |
| `GET /api/v1/dashboard/summary` | KPIs, monthly spend, top vendors |

Every list endpoint is paginated with the same response shape: `items`, `page`, `page_size`, `total`, `total_pages`. Interactive API documentation is at `http://localhost:8000/docs`.

## Errors, logging and security

Every error, whether a business rule, invalid input or an unexpected crash, comes back in one consistent shape: `{"error": {"code", "message", "details", "request_id"}}`. The frontend can then handle each case by its `code`: `token_expired` sends you to the login page, `version_conflict` reloads the bill, and `validation_error` shows a message under the field.

```mermaid
flowchart TD
    E[Exception raised] --> T{Type}
    T -- "AppError subclass<br/>(NotFound, Conflict, ...)" --> A[HTTP status from class<br/>code + message]
    T -- RequestValidationError --> V["422 validation_error<br/>details = field errors"]
    T -- "HTTPException (framework)" --> H[status preserved<br/>code derived]
    T -- anything else --> U["500 internal_error<br/>generic message, stack logged"]
    A & V & H & U --> R["JSON envelope<br/>{error: {code, message, details, request_id}}"]
```

- **Logging.** Logs are structured JSON on standard output. Every line carries the request ID and company, and the request ID is also returned to the browser, so a support question can be traced end to end. Passwords, tokens and invoice contents are never logged.
- **Configuration.** All settings come from environment variables through one typed settings class, which refuses to start if something required is missing. Secrets never appear in logs.
- **Security:**
  - passwords hashed with bcrypt
  - login tokens that expire after 8 hours
  - company isolation enforced in the repository layer and covered by tests
  - uploads checked by real file type and size
  - CORS limited to known origins

## What a user does

The sidebar gives five destinations, and almost everything leads to the bill split view:

```mermaid
flowchart LR
    LOGIN[Login] --> DASH[Dashboard]
    SIGNUP[Sign up] --> DASH
    DASH --> UP[Upload]
    DASH --> RQ[Review queue]
    DASH --> BILLS[Bills]
    DASH --> VEN[Vendors]
    UP --> RQ
    RQ --> SPLIT[Bill split view]
    BILLS --> SPLIT
    VEN --> BILLS
```

**Signing up and signing in.** Signing up creates the company and makes you its administrator. If your session expires, you are sent back to the login page and returned to where you were afterwards.

```mermaid
flowchart TD
    START([User opens app]) --> HAS{Valid token<br/>in storage?}
    HAS -- yes --> ME[GET /auth/me]
    ME -- 200 --> DASH([Dashboard])
    ME -- "401 token_expired / invalid_token" --> CLEAR[Clear token] --> LOGIN
    HAS -- no --> LOGIN[Login page]
    LOGIN --> CHOICE{Has account?}
    CHOICE -- no --> SIGNUP[Sign-up page:<br/>company name, company GSTIN optional,<br/>full name, work email, password]
    SIGNUP --> SV{Client validation<br/>email format, password 8+,<br/>GSTIN format if given}
    SV -- invalid --> SIGNUP
    SV -- valid --> SPOST[POST /auth/signup]
    SPOST -- "409 email_taken" --> SERR[Inline error:<br/>'An account with this email exists'] --> SIGNUP
    SPOST -- "201" --> STORE[Store token + user + company] --> DASH
    CHOICE -- yes --> LFORM[Email + password]
    LFORM --> LPOST[POST /auth/login]
    LPOST -- "401 invalid_credentials" --> LERR[Inline error:<br/>'Email or password is incorrect'] --> LFORM
    LPOST -- 200 --> STORE
```

**Uploading.** Files are checked in the browser first, uploaded with progress bars, then tracked live until they are ready or have failed.

```mermaid
flowchart TD
    A([Upload page]) --> B[Drag files onto drop zone<br/>or click Browse]
    B --> C{Client pre-check<br/>type in PDF, PNG, JPG, WEBP<br/>size up to 15 MB, max 20 files}
    C -- fails --> C1[Row shows 'Rejected' + reason<br/>file not sent]
    C -- passes --> D[Rows show 'Uploading' + progress bar]
    D --> E[POST /invoices multipart]
    E --> F{Per-file result}
    F -- error --> F1[Row: 'Failed' + server reason]
    F -- accepted --> G[Row: 'Queued']
    G --> H[Poll every 2 s<br/>GET /invoices?ids=...]
    H --> I{Status}
    I -- processing --> J[Row: 'Extracting'] --> H
    I -- needs_review --> K[Row: 'Ready for review'<br/>shows vendor, total, error/warning counts]
    I -- failed --> L[Row: 'Extraction failed' + reason<br/>Retry button]
    L -- Retry --> M[POST /invoices/:id/retry] --> G
    K --> N[Click row or 'Open review queue'] --> O([Bill split view])
```

**Working the review queue.** Bills that need a decision are shown oldest first. Search, status filter and rows per page are kept in the URL, so a filtered view can be bookmarked or shared.

```mermaid
flowchart TD
    A([Review queue]) --> B[Table defaults to status = Needs review<br/>sorted oldest first]
    B --> C{User action}
    C -- "Change status filter" --> D[Refetch page 1]
    C -- "Type in search<br/>vendor, invoice no., filename" --> E[Debounce 300 ms, refetch page 1]
    C -- "Change rows per page<br/>10 / 25 / 50 / 100" --> F[Refetch page 1]
    C -- "Next / previous page" --> G[Refetch page N]
    D & E & F & G --> B
    B --> H{Result}
    H -- loading --> H1[Skeleton rows]
    H -- empty --> H2["Empty state:<br/>'No bills need review' + link to Upload"]
    H -- error --> H3[Error state + Retry]
    C -- "Click a row" --> I([Split view:<br/>left document preview,<br/>right fields + findings + timeline])
```

**Correcting a field.** Click, type, press Enter. If someone else changed the bill first, you see their version instead of overwriting it.

```mermaid
flowchart TD
    A([Split view]) --> B[Fields panel: each field shows value,<br/>confidence badge, finding marker]
    B --> C[Click field or pencil icon]
    C --> D[Field becomes input<br/>typed: date picker, amount, text]
    D --> E{Enter / Save or Escape}
    E -- Escape --> B
    E -- Save --> F{Client check<br/>amount numeric, date valid}
    F -- invalid --> D
    F -- valid --> G["PATCH /invoices/:id/fields<br/>{version, changes}"]
    G -- "200" --> H[Field updated, confidence = verified,<br/>findings list re-rendered from response,<br/>timeline gains 'Total changed 11,800 to 11,700']
    G -- "409 version_conflict" --> I[Toast: 'Someone else updated this bill.<br/>Showing the latest version.'<br/>refetch bill]
    G -- "409 invalid_state" --> J[Toast: 'This bill is already approved/rejected']
    G -- "422 validation_error" --> K[Inline error under field]
    H --> B
```

**Approving or rejecting.** Approve stays disabled while errors remain. Reject asks for a reason, and offers common ones to pick from. After a decision, the next bill in the queue opens automatically.

```mermaid
flowchart TD
    A([Split view, status = Needs review]) --> B{Error findings?}
    B -- yes --> C[Approve disabled<br/>tooltip: 'Resolve N errors or reject']
    B -- no --> D[Approve enabled]
    D --> E[Click Approve] --> F[Modal: optional comment, Confirm]
    F --> G[POST /invoices/:id/approve]
    G -- 200 --> H[Status badge 'Approved', fields read-only,<br/>toast, go to next bill in queue]
    G -- "409 version_conflict" --> I[Refetch + toast]
    G -- "422 approval_blocked" --> C
    A --> J[Click Reject] --> K[Modal: reason required, 3+ chars]
    K --> L[POST /invoices/:id/reject]
    L -- 200 --> M[Status 'Rejected', reason shown,<br/>toast, next bill]
    L -- 409 --> I
```

**Managing vendors.** Vendors appear by themselves the first time a valid GSTIN is seen. You can rename a vendor to the brand name your team actually uses; the legal name stays as printed on the invoice.

```mermaid
flowchart TD
    X[Extraction finds vendor GSTIN] --> Y{Vendor with this GSTIN<br/>exists in company?}
    Y -- yes --> Z[Link bill to vendor]
    Y -- "no, GSTIN valid" --> W[Create vendor:<br/>legal name = extracted name,<br/>display name = same, state from GSTIN<br/>audit: vendor_created] --> Z
    Y -- "no GSTIN / invalid" --> V[Leave unlinked, warning finding]

    A([Vendors page]) --> B[Table: display name, legal name, GSTIN,<br/>state, bills, total spend]
    B --> C{Action}
    C -- search --> B
    C -- "Click vendor" --> D[Drawer: details + recent bills]
    D --> E[Edit display name] --> F[PATCH /vendors/:id] --> G[Toast + table refresh]
    D --> H["'View all bills'"] --> I([Bills page filtered by vendor])
```

**Reading the dashboard.** This month's total, the pending amount, bills needing review and the approval rate, plus a six-month spend chart and the top vendors. Each card links to the matching list.

```mermaid
flowchart TD
    A([Dashboard]) --> B[GET /dashboard/summary]
    B --> C{State}
    C -- loading --> C1[Card skeletons]
    C -- error --> C2[Error panel + Retry]
    C -- "no bills yet" --> C3[Empty state: 'Upload your first bills' + button]
    C -- data --> D[KPI cards:<br/>Total this month, Pending amount,<br/>Needs review count, Approval rate]
    D --> E[Monthly spend chart, last 6 months]
    D --> F[Top vendors table]
    D -- "Click 'Needs review'" --> G([Review queue])
    D -- "Click 'Pending amount'" --> H([Bills filtered to Needs review])
    F -- "Click vendor" --> I([Bills filtered by vendor])
```

## Edge cases

What happens when things go wrong is designed, not left to chance. The full table is in the [edge-case analysis](docs/06-edge-case-analysis.md). In short:

| Situation | What Ledgerline does |
|-----------|----------------------|
| Corrupt or password-protected PDF | Marked failed straight away, with a plain explanation (for example "remove the password and upload again"). No AI call is made. |
| Scanned image with no text layer | Sent to the vision model. Confidence is capped and uncertain fields are highlighted. |
| Multi-page invoice | Text from every page is read. Scans send up to 5 pages, and the screen says if more pages exist. |
| Same invoice uploaded twice | The later copy gets a duplicate error naming the original, and cannot be approved. |
| Invalid GSTIN | An error that names the exact problem, such as a bad check digit. No vendor is created until it is corrected. |
| Line items don't add up / tax doesn't match the rate | An error or warning that shows both the computed and the stated amounts |
| Vendor not seen before | Created automatically from a valid GSTIN and recorded in the bill's history |
| OpenAI timeout or rate limit | Retried with increasing waits. After the last attempt, marked failed with a Retry button. Other bills are unaffected. |
| Very large files | Rejected individually (15 MB limit) without failing the rest of the batch |
| Two reviewers on one bill | The version check refuses the second write, and that reviewer sees the latest data |
| Expired or tampered login token | The request is refused, and the user is sent to the login page and returned to where they were |

## Scaling later

Nothing in the MVP stops it growing. The API is stateless and login tokens are self-contained, so more API servers can run behind a load balancer. The next steps are moving the job queue to Redis with separate worker servers, moving documents to S3, and adding a read-only database copy for reports.

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

Every index starts with `company_id`, so very large customers can later be moved to their own partitions or databases without changing queries. More detail is in [technical architecture section 8](docs/04-technical-architecture.md#8-scaling-horizontally).

## Running it locally

In development, Vite serves the React app and forwards `/api` calls to the FastAPI server. That server runs the extraction workers inside the same process.

```mermaid
flowchart LR
    BR[Browser :5173] --> VITE[Vite dev server :5173]
    VITE -- "proxy /api" --> API[Uvicorn :8000<br/>FastAPI + worker threads]
    API --> PG[(Postgres from DB_URL)]
    API --> DISK[(./backend/storage)]
    API --> OAI[OpenAI]
```

**Prerequisites:** Python 3.12, [uv](https://docs.astral.sh/uv/) (or pip), Node 20 or newer, and PostgreSQL 14 or newer.

```bash
cp .env.example .env   # fill in DB_URL and OPENAI_API_KEY
make setup             # backend virtualenv (backend/.venv) + frontend packages
make migrate           # create the database schema
make seed              # demo company, user and 18 sample bills (offline, no OpenAI cost)
                       # or: make seed-live  (sends the samples through OpenAI)
make backend           # http://localhost:8000
make frontend          # http://localhost:5173
```

The seed creates bills for every scenario:

- a duplicate
- an invalid GSTIN
- line items that don't add up
- an unusual tax rate
- the wrong tax type
- a multi-page invoice
- a scanned invoice
- a corrupt file
- approved and rejected history, so the dashboard has data

It also writes ready-to-upload files to [`samples/`](samples/), so you can drop them on the Upload page and watch real OpenAI extraction. Re-running the seed resets **only** the demo company.

### Deploying the API to EC2 (recommended)

The live backend at **https://apiwish.collabup.co.in** runs this setup on Amazon Linux 2023: Nginx with a Let's Encrypt certificate in front of Uvicorn on `127.0.0.1:8001`, sharing the instance with another app.

On a regular server the API runs as designed: real background workers, 15 MB uploads, no request time limit, and automatic recovery of in-progress bills after a restart. [`deploy/ec2/`](deploy/ec2/README.md) has everything needed for Ubuntu without Docker: a setup script, a deploy script with automatic rollback, a systemd unit, Nginx with HTTPS, and pinned, hash-checked dependencies.

```bash
git clone https://github.com/Subhashbisnoi/wisprflow.git && cd wisprflow
sudo ./deploy/ec2/setup.sh --domain api.yourdomain.com --email you@yourdomain.com
# fill in /etc/ledgerline/ledgerline.env, run the same command again, and you're live
sudo /opt/ledgerline/deploy/ec2/deploy.sh   # later updates
```

### Deploying to Vercel

The backend and frontend deploy as **two Vercel projects** from this repository.

**1. API project.** Set *Root Directory* to `backend`. Vercel imports `app` from `app/asgi.py` (configured in `pyproject.toml` under `[tool.vercel]`), and `backend/vercel.json` allows up to 60 s per request. Set these environment variables:

| Variable | Value |
|----------|-------|
| `DB_URL` | Your Postgres URL |
| `OPENAI_API_KEY` | Your OpenAI key |
| `JWT_SECRET` | A long random string. Required: every instance must sign tokens with the same secret. |
| `APP_ENV` | `production` |
| `STORAGE_BACKEND` | `database`. Vercel's filesystem is read-only and not shared between instances, so documents are kept in Postgres. |
| `JOB_QUEUE_BACKEND` | `sync`. Vercel freezes the function after the response, so extraction runs inside the upload request (about 5 to 10 s per file). |
| `MAX_UPLOAD_MB` | `4`. Vercel limits request bodies to 4.5 MB. |
| `DB_POOL_SIZE` | `2`. Keeps connection use low across many instances. |
| `CORS_ORIGINS` | The frontend URL, for example `https://ledgerline.vercel.app` |

Run migrations from your machine against the same database before the first deploy: `make migrate`.

**2. Web project.** Set *Root Directory* to `frontend`. Vite is auto-detected, and `frontend/vercel.json` sends every page route to the SPA. Set these environment variables:

| Variable | Value |
|----------|-------|
| `VITE_API_BASE_URL` | The API URL plus `/api/v1`, for example `https://ledgerline-api.vercel.app/api/v1` |
| `VITE_MAX_UPLOAD_MB` | `4` |

**On Vercel:**

- The upload page sends one file per request, so each request stays within the time limit.
- If a function is cut off mid-extraction, the bill shows **Retry extraction** after 5 minutes.
- For heavier volume, run the API on a long-running host (Render, Railway, Fly) with `JOB_QUEUE_BACKEND=in_process` (or Redis), and move documents to S3.

### Environment variables

Settings are read from `.env` at the repository root (or `backend/.env`). The template is [`.env.example`](.env.example).

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `DB_URL` / `DATABASE_URL` | yes | | PostgreSQL connection URL |
| `OPENAI_API_KEY` | yes* | | OpenAI key. *Not needed with `LLM_PROVIDER=fake`. |
| `JWT_SECRET` | in production | random in dev | Secret used to sign login tokens. Without it, development logins reset on every restart. |
| `LLM_PROVIDER` | no | `openai` | `openai`, or `fake` for offline use |
| `OPENAI_TEXT_MODEL` / `OPENAI_VISION_MODEL` | no | `gpt-4.1-mini` / `gpt-4.1` | Models for PDF text and for scans |
| `OPENAI_TIMEOUT_SECONDS` | no | `60` | Timeout per AI call |
| `JWT_EXPIRE_MINUTES` | no | `480` | Session length |
| `APP_ENV` / `LOG_LEVEL` | no | `development` / `INFO` | Environment and log verbosity |
| `STORAGE_DIR` | no | `backend/storage` | Where uploaded documents are kept |
| `MAX_UPLOAD_MB` / `MAX_FILES_PER_UPLOAD` | no | `15` / `20` | Upload limits |
| `EXTRACTION_WORKERS` / `EXTRACTION_MAX_ATTEMPTS` | no | `3` / `3` | Background workers and retry attempts |
| `CORS_ORIGINS` | no | `http://localhost:5173` | Browser origins allowed to call the API |
| `STORAGE_BACKEND` | no | `local` | `local` (disk at `STORAGE_DIR`) or `database` (Postgres; for Vercel) |
| `JOB_QUEUE_BACKEND` | no | `in_process` | `in_process` (background workers) or `sync` (extract inside the upload request; for Vercel) |
| `DB_POOL_SIZE` | no | `10` | Database connections per instance |
| `TEST_DATABASE_URL` | tests | `postgresql://localhost/ledgerline_test` | A **separate** database that the tests wipe and rebuild |

### Tests and code quality

```bash
make test   # backend: pytest (unit + API tests on real Postgres); frontend: Vitest
make lint   # Ruff, mypy (strict), ESLint, Prettier, TypeScript
```

Backend tests need an empty local database: run `createdb ledgerline_test` once. The tests apply the real migration, use the fake AI provider and an inline job queue, and cover:

- every validation rule and the GSTIN check digit
- PDF, scan and corrupt-file handling
- value cleaning and confidence grounding
- expired and tampered tokens
- upload, retries and failure
- corrections with conflict protection
- approve and reject
- pagination and filters
- isolation between companies

### Project structure

```text
backend/
  app/core/             config, database, logging, errors, security, pagination, tenancy
  app/features/<name>/  models, schemas, repository, service, dependencies, router
  app/infrastructure/   job queue and file storage implementations
  alembic/              database migrations
  scripts/              demo seed and sample invoice generator
  tests/                unit and integration tests
frontend/
  src/components/ui/    Button, Input, Select, Card, Table, Pager, Modal, Drawer, Toast, Badge, states
  src/features/<name>/  auth, upload, review, bills, vendors, dashboard
  src/styles/tokens.css every colour, spacing value and font size
deploy/ec2/              EC2 deployment: setup and deploy scripts, systemd unit, Nginx config
docs/                   design documents and screenshots
samples/                generated invoices for manual upload
```

## Documentation

| Document | Contents |
|----------|----------|
| [Product requirements](docs/01-prd.md) | Problem, users, MVP scope, out of scope, success metrics |
| [High-level design](docs/02-hld.md) | System context, components, interactions, data flow, architecture |
| [Low-level design](docs/03-lld.md) | Class diagrams, full ERD with keys and indexes, sequence diagrams, error codes |
| [Technical architecture](docs/04-technical-architecture.md) | Stack choices, folder structure, background jobs, configuration, logging, scaling |
| [User flows](docs/05-user-flows.md) | Every user journey as a flow diagram |
| [Edge-case analysis](docs/06-edge-case-analysis.md) | What the system does when things go wrong |
| [Decision log](docs/decision-log.md) | Every assumption and design decision, with the alternatives considered |

## Screenshots

All screenshots are from the seeded demo company (`make seed`), except the upload and empty-dashboard shots, which use a fresh company with real OpenAI extraction. The files are in [`docs/screenshots/`](docs/screenshots/).

### Sign-in and onboarding

**Sign in, with the demo account shortcut**

![Sign in, with the demo account shortcut](docs/screenshots/login.png)

**Company sign-up (creates the company and its admin)**

![Company sign-up (creates the company and its admin)](docs/screenshots/signup.png)

### Dashboard

**KPI cards, monthly spend (approved vs pending) and top vendors**

![KPI cards, monthly spend (approved vs pending) and top vendors](docs/screenshots/dashboard.png)

**Empty state for a brand-new company**

![Empty state for a brand-new company](docs/screenshots/dashboard-empty.png)

### Upload

**Multi-file drag and drop with per-file progress**

![Multi-file drag and drop with per-file progress](docs/screenshots/upload-in-progress.png)

**Live statuses after extraction: ready, issues found, failed with a readable reason and Retry**

![Live statuses after extraction: ready, issues found, failed with a readable reason and Retry](docs/screenshots/upload-done.png)

### Review queue

**Dense queue with search, status filter, issue counts and pager**

![Dense queue with search, status filter, issue counts and pager](docs/screenshots/review-queue.png)

### Bill split view: one screen per validation scenario

**Duplicate detected (same file as an approved bill); approval blocked**

![Duplicate detected (same file as an approved bill); approval blocked](docs/screenshots/bill-duplicate.png)

**Invalid vendor GSTIN (checksum fails); vendor not auto-created**

![Invalid vendor GSTIN (checksum fails); vendor not auto-created](docs/screenshots/bill-invalid-gstin.png)

**IGST charged on an intra-state supply**

![IGST charged on an intra-state supply](docs/screenshots/bill-wrong-tax-type.png)

**Scanned PDF read by the vision path; low-confidence fields flagged**

![Scanned PDF read by the vision path; low-confidence fields flagged](docs/screenshots/bill-scanned-vision.png)

**Correcting a field in place (Enter saves, Escape cancels)**

![Correcting a field in place (Enter saves, Escape cancels)](docs/screenshots/bill-editing-field.png)

**Audit trail: who did what, and when**

![Audit trail: who did what, and when](docs/screenshots/bill-audit-timeline.png)

**Approve with an optional comment**

![Approve with an optional comment](docs/screenshots/approve-modal.png)

**Reject with a mandatory reason (common reasons offered)**

![Reject with a mandatory reason (common reasons offered)](docs/screenshots/reject-modal.png)

### Bills and vendors

**All bills**

![All bills](docs/screenshots/bills.png)

**Filtered by amount, sorted by value**

![Filtered by amount, sorted by value](docs/screenshots/bills-filtered.png)

**Vendors, auto-created from invoices**

![Vendors, auto-created from invoices](docs/screenshots/vendors.png)

**Vendor drawer: rename the brand name, recent bills**

![Vendor drawer: rename the brand name, recent bills](docs/screenshots/vendor-drawer.png)

