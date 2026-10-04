# Ledgerline - Low-Level Design

Related: [HLD](02-hld.md) | [Technical architecture](04-technical-architecture.md) | [Edge cases](06-edge-case-analysis.md)

Contents
1. [Layering rules](#1-layering-rules)
2. [Domain model class diagram](#2-domain-models)
3. [Repository layer](#3-repository-layer)
4. [Service layer](#4-service-layer)
5. [Extraction, LLM provider and job queue](#5-extraction-llm-provider-and-job-queue)
6. [Validation engine](#6-validation-engine)
7. [API layer](#7-api-layer)
8. [Database ERD, columns, keys and indexes](#8-database)
9. [Sequence diagrams](#9-sequence-diagrams)
10. [Error codes](#10-error-codes)

## 1. Layering rules

```mermaid
flowchart LR
    R["API router<br/>(Pydantic schemas in/out)"] --> S["Service<br/>(business rules, transactions)"]
    S --> RP["Repository<br/>(SQLAlchemy queries)"]
    RP --> M["Domain model<br/>(SQLAlchemy ORM)"]
    S --> P["Ports<br/>LLMProvider, JobQueue, FileStorage"]
```

- Routers depend only on services (injected through `Depends`) and Pydantic schemas.
- Services own the transaction boundary (`session.commit()`) and call repositories, ports, and other services.
- Repositories are the only place that builds queries. Tenant repositories are built with a `TenantContext` and always filter by `company_id`.
- Domain models carry no I/O.

## 2. Domain models

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

`AuditAction` values: `invoice_uploaded`, `extraction_started`, `extraction_completed`, `extraction_failed`, `extraction_retried`, `vendor_linked`, `vendor_created`, `vendor_updated`, `field_corrected`, `line_item_added`, `line_item_corrected`, `line_item_removed`, `invoice_approved`, `invoice_rejected`.

## 3. Repository layer

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

Line items and validation findings are child collections of `Invoice` (`cascade="all, delete-orphan"`), so they are replaced through the aggregate (`invoice.line_items = [...]`, `invoice.findings = [...]`) rather than through their own repositories. `DashboardRepository` is read-only and holds the `TenantContext` directly.

`UserRepository` is deliberately **not** tenant-scoped, because login looks up a user by email before any tenant is known. It is used only by `AuthService` and the auth dependency.

## 4. Service layer

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

## 5. Extraction, LLM provider and job queue

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

Errors raised by the extraction pipeline:

| Exception | Raised when | Job behaviour |
|-----------|-------------|---------------|
| `UnreadableDocumentError` | Corrupt PDF, undecodable image, zero pages | No retry. Bill set to `failed` with the reason. |
| `PasswordProtectedDocumentError` | PDF is encrypted and the empty password fails | No retry. `failed`, asking for an unlocked copy. |
| `ProviderTransientError` | Timeout, 429, 5xx, connection error | Retried with backoff (D-049). `failed` after the last attempt. |
| `ProviderPermanentError` | Auth error, invalid request, unparseable output | No retry. `failed`. |

## 6. Validation engine

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

| Rule (code) | Checks | Severity |
|-------------|--------|----------|
| `required_fields` | vendor name, vendor GSTIN, invoice number, invoice date, and total are present. Due date and buyer GSTIN are present. At least one line item. | error / warning / warning |
| `low_confidence` | Any header field with confidence below 0.60 (D-030) | warning |
| `gstin_format` | 15 chars, pattern `^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$`, valid state code, mod-36 checksum. The buyer GSTIN should equal the company GSTIN when one is set. | error (vendor) / error (buyer format) / warning (buyer not your company) |
| `duplicate_invoice` | An **earlier** non-rejected, non-failed bill with the same vendor GSTIN + invoice number + total, or the same file SHA-256. Only the later copy is flagged (D-066). | error |
| `line_item_arithmetic` | `qty x rate = amount` per line (within Rs 1). The sum of line amounts equals the subtotal (within Rs 1). | error |
| `totals` | `subtotal + cgst + sgst + igst = total`. A difference of Rs 1 or less is info (round-off). More than that is an error. | error / info |
| `tax_rate` | CGST equals SGST. The effective rate `tax / subtotal` is within 0.1 percentage points of a GST slab (D-028). | error / warning |
| `tax_type` | Vendor state (GSTIN digits 1-2) against place of supply (buyer GSTIN state, else company state). Same state: CGST+SGST and no IGST. Different states: IGST only. | error |

## 7. API layer

All routes are prefixed with `/api/v1`. All except auth and health require `Authorization: Bearer <jwt>`.

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

### Key schemas (Pydantic)

| Schema | Fields |
|--------|--------|
| `SignupRequest` | `company_name`, `company_gstin?`, `full_name`, `email`, `password` (min 8) |
| `LoginRequest` | `email`, `password` |
| `AuthResponse` | `access_token`, `token_type`, `expires_at`, `user: UserOut`, `company: CompanyOut` |
| `InvoiceListParams` | `status?` (repeatable), `vendor_id?`, `date_from?`, `date_to?`, `min_total?`, `max_total?`, `search?`, `ids?`, `sort` (`created_at`, `invoice_date`, `total`, `due_date`; prefix `-` for descending), `page`, `page_size` |
| `InvoiceSummaryOut` | id, status, filename, vendor (id, display name), invoice number, dates, total, error and warning counts, created_at |
| `InvoiceDetailOut` | All header fields + `field_confidence` + `line_items[]` + `findings[]` + `version` + reviewer info |
| `FieldCorrectionRequest` | `version`, `changes: [{field, value}]`. `field` is an enum of editable header fields. |
| `LineItemCorrectionRequest` | `version`, `changes: [{field, value}]` where field is description, hsn_sac, quantity, rate, or amount |
| `ApproveRequest` / `RejectRequest` | `version`, `comment?` / `version`, `reason` (3-1000 chars) |
| `Page[T]` | `items`, `page`, `page_size`, `total`, `total_pages` |
| `ErrorResponse` | `error: {code, message, details?, request_id}` |

## 8. Database

### 8.1 Entity relationship diagram

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

### 8.2 Keys, constraints and indexes

| Table | Constraint / index | Columns | Purpose |
|-------|--------------------|---------|---------|
| companies | PK | `id` | |
| users | PK | `id` | |
| users | `uq_users_email` UNIQUE | `email` | Login lookup. Email is globally unique (one user, one company in the MVP). |
| users | `ix_users_company_id` | `company_id` | List users of a tenant |
| users | FK | `company_id -> companies.id` ON DELETE CASCADE | |
| vendors | PK | `id` | |
| vendors | `uq_vendors_company_gstin` UNIQUE | `company_id, gstin` | Vendor matching. Prevents duplicate vendors under concurrent extraction. |
| vendors | `ix_vendors_company_display_name` | `company_id, display_name` | Sort and search vendor list |
| invoices | PK | `id` | |
| invoices | `ix_invoices_company_status` | `company_id, status` | Review queue filter |
| invoices | `ix_invoices_company_vendor` | `company_id, vendor_id` | Filter by vendor, vendor totals |
| invoices | `ix_invoices_company_invoice_date` | `company_id, invoice_date` | Date range filter, dashboard month |
| invoices | `ix_invoices_company_created_at` | `company_id, created_at` | Default sort |
| invoices | `ix_invoices_company_total` | `company_id, total` | Amount range filter |
| invoices | `ix_invoices_company_due_date` | `company_id, due_date` | Sort by due date |
| invoices | `ix_invoices_company_sha256` | `company_id, file_sha256` | Same-file duplicate check |
| invoices | `ix_invoices_duplicate_key` | `company_id, vendor_gstin, invoice_number` | Duplicate rule lookup |
| invoices | `ck_invoices_status` CHECK | `status IN (...)` | Enum integrity |
| invoices | FKs | `company_id`, `vendor_id` (SET NULL), `uploaded_by_id`, `reviewed_by_id` | |
| invoice_line_items | `ix_line_items_company_invoice` | `company_id, invoice_id, position` | Load lines in order |
| validation_findings | `ix_findings_company_invoice` | `company_id, invoice_id` | Load findings |
| validation_findings | `ix_findings_company_severity` | `company_id, severity` | Future reporting |
| validation_findings | `ck_findings_severity` CHECK | `severity IN ('error','warning','info')` | |
| audit_events | `ix_audit_company_invoice_created` | `company_id, invoice_id, created_at` | Bill timeline |
| audit_events | `ix_audit_company_entity` | `company_id, entity_type, entity_id, created_at` | Vendor or entity history |
| audit_events | `ix_audit_company_created` | `company_id, created_at` | Company-wide activity feed |

## 9. Sequence diagrams

### 9.1 Upload

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

### 9.2 Extraction (background job)

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

### 9.3 Validation

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

### 9.4 Review action: correct a field, then approve

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

## 10. Error codes

| HTTP | `error.code` | When |
|------|--------------|------|
| 400 | `bad_request` | Malformed input not caught by schema |
| 401 | `not_authenticated` | Missing token |
| 401 | `token_expired` | JWT `exp` in the past |
| 401 | `invalid_token` | Bad signature, malformed token, or the user no longer exists |
| 401 | `invalid_credentials` | Wrong email or password |
| 404 | `not_found` | Entity missing **or belongs to another tenant** (no existence leak) |
| 409 | `email_taken` | Signup with an existing email |
| 409 | `version_conflict` | Optimistic lock failure |
| 409 | `invalid_state` | Editing an approved, rejected, or processing bill. Retrying a non-failed bill. |
| 413 | `file_too_large` | Per-file result. Also returned when the whole request is too large. |
| 415 | `unsupported_file_type` | Per-file result |
| 422 | `validation_error` | Pydantic request validation. `details` lists field errors. |
| 422 | `approval_blocked` | Approve while error findings exist |
| 500 | `internal_error` | Unhandled. Logged with stack trace and request id. |
