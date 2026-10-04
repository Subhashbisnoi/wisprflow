# Ledgerline - Product Requirements Document (MVP)

| | |
|---|---|
| Product | Ledgerline, accounts payable automation for Indian businesses |
| Version | MVP 1.0 |
| Status | Approved for build |
| Related | [HLD](02-hld.md), [LLD](03-lld.md), [Decision log](decision-log.md) |

## 1. Problem

Finance teams at Indian small and mid-size businesses receive hundreds of vendor invoices a month as PDFs, phone photos, and scans. Today they:

1. **Key data in by hand.** Someone types vendor, GSTIN, invoice number, dates, line items, CGST/SGST/IGST, and totals into a spreadsheet or the ERP. It takes 4 to 8 minutes per invoice and is error-prone.
2. **Miss compliance errors.** Invalid GSTINs, the wrong tax type (IGST charged on an intra-state supply), and tax amounts that do not match the GST slab all lead to blocked input tax credit (ITC).
3. **Pay duplicates.** The same invoice arrives by email and by courier and is paid twice. Industry studies put duplicate payments at 0.1 to 0.5 % of AP spend.
4. **Have no audit trail.** When an auditor asks "who changed this amount and why?", there is no answer.

## 2. Target users

| Persona | Role | Goals | Pain today |
|---------|------|-------|------------|
| **Priya, AP Executive** (primary) | Processes 300 to 600 invoices a month at a 50 to 500 person company | Clear the invoice pile quickly and accurately | Manual entry, chasing totals that do not match |
| **Rahul, Finance Controller** (secondary) | Approves bills, owns month-end close and audits | Confidence that what is approved is correct and compliant. Visibility of pending liabilities | No single view of pending amounts. No audit trail |
| **Auditor** (tertiary, read-only, future) | Statutory or internal audit | Evidence of controls | Reconstructing history from emails |

Target customers: Indian businesses with 50 to 2,000 employees, GST-registered, receiving 200 to 5,000 vendor invoices a month, and not yet on an enterprise AP suite.

## 3. Goals

- Reduce the time to process one invoice from about 6 minutes to **under 1 minute** of reviewer time.
- Catch GST compliance errors and duplicates **before** approval.
- Give every bill a complete, immutable audit trail.

## 4. MVP scope (in scope)

| # | Capability | Requirement summary |
|---|------------|---------------------|
| F1 | **Sign-up, login, company** | Sign up with company name (+ optional GSTIN), name, email, and password. This creates the company and an admin user. Login uses email and password and issues a JWT. All data is isolated per company. |
| F2 | **Upload** | Drag and drop several PDF, PNG, JPG, or WEBP files at once (up to 20 files, 15 MB each). A per-file status shows: uploading, queued, extracting, needs review, or failed. |
| F3 | **AI extraction** | The PDF text layer is read first. OpenAI Vision is used only for scanned PDFs and images. Fields extracted: vendor name, vendor GSTIN, buyer GSTIN, invoice number, invoice date, due date, line items (description, HSN/SAC, quantity, rate, amount), subtotal, CGST, SGST, IGST, total. Each field has a confidence score from 0 to 1. Extraction runs as a background job. |
| F4 | **Validation engine** | Rules: GSTIN format and checksum, duplicate (vendor + invoice number + amount, and the same file), line items sum to subtotal, subtotal + tax = total, tax matches a GST slab, intra-state uses CGST+SGST and inter-state uses IGST, required fields present, low-confidence fields. Each finding has a severity (error, warning, info) and a plain-English explanation. |
| F5 | **Review queue** | A dense table with status filter, search, and a pager with a rows-per-page dropdown. Clicking a bill opens a split view: the document preview on the left, editable fields and findings on the right. |
| F6 | **Correct, approve, reject** | Correct any field in place, which re-runs validation immediately. Approve (blocked while errors exist) or reject (with a mandatory reason). |
| F7 | **Audit trail** | Every upload, extraction, correction (field, old value to new value), approval, and rejection is recorded with who and when. Shown as a timeline per bill. |
| F8 | **Vendors** | A vendor is auto-created from the first invoice with a new valid GSTIN. The vendor list shows display (brand) name, legal name, GSTIN, state, bill count, and total spend. Display name is editable. |
| F9 | **Bills** | All bills, filterable by status, vendor, invoice date range, and amount range. Searchable and paginated. |
| F10 | **Dashboard** | KPI cards: total this month, pending amount, bills needing review, and approval rate. A monthly spend chart and top vendors. |

## 5. Out of scope (MVP)

- Payments, payment runs, bank integration, and ERP sync (Tally, Zoho Books, SAP). Approved bills are exported later.
- Purchase orders and 2-way or 3-way matching.
- Multi-step approval chains, approval limits, and delegation.
- Email or WhatsApp ingestion.
- Live GSTIN verification against the GSTN portal, and e-invoice IRN/QR validation.
- TDS calculation and GSTR-2B reconciliation.
- User invites, SSO, password reset, and 2FA.
- A mobile app. The web app is desktop-first and usable on tablets.
- Multi-currency. INR only.

## 6. Functional requirements (detail)

### 6.1 Extraction
- **FR-1** The system must never call the vision model for a PDF that has a usable text layer (D-052).
- **FR-2** Each extracted header field and each line-item field carries a confidence score from 0 to 1.
- **FR-3** Extraction failures (corrupt file, password-protected file, provider outage after retries) set the bill to `failed` with a human-readable reason and a "Retry extraction" action.

### 6.2 Validation
- **FR-4** Validation runs after extraction and after every correction. Results replace earlier results.
- **FR-5** Severity semantics: **error** blocks approval. **warning** needs attention but does not block. **info** is context only.

### 6.3 Review
- **FR-6** Every write carries the bill `version`. Stale writes are rejected with a clear "this bill was changed by someone else" message (D-047).
- **FR-7** Approved and rejected bills are read-only.

### 6.4 Security and tenancy
- **FR-8** `company_id` is always derived from the JWT and never accepted from the client.
- **FR-9** Passwords are stored as bcrypt hashes. Tokens expire after 8 hours.

## 7. Non-functional requirements

| Area | Target |
|------|--------|
| Extraction latency | p50 under 15 s and p95 under 45 s per invoice (text layer usually under 8 s) |
| API latency | p95 under 300 ms for list and detail endpoints at 100k bills per tenant |
| Availability | 99.5 % (MVP, single region) |
| Accessibility | WCAG 2.1 AA contrast, keyboard navigable, labelled form controls |
| Auditability | 100 % of state-changing actions on a bill are audited |
| Data isolation | Zero cross-tenant reads (enforced in the repository layer and covered by tests) |

## 8. Success metrics

| Metric | Definition | MVP target (90 days after launch) |
|--------|------------|-----------------------------------|
| **Field accuracy** | Share of extracted fields not corrected by the reviewer | 95 % or more (text-layer PDFs), 85 % or more (scans) |
| **Reviewer time per bill** | Median time from opening a bill to approving or rejecting it | Under 60 s |
| **Straight-through share** | Bills approved with zero corrections | 60 % or more |
| **Errors caught** | Bills with at least one error finding that were corrected or rejected rather than approved | 100 % (enforced by D-021) |
| **Duplicates prevented** | Duplicate findings resulting in rejection | Tracked. Baseline in month 1 |
| **Extraction success rate** | Bills reaching `needs_review` without `failed` | 98 % or more |
| **Activation** | New companies uploading 10 or more bills in week 1 | 50 % or more |
| **Retention** | Companies active in month 3 | 70 % or more |

## 9. Release criteria

- All F1 to F10 work end to end against a real Postgres and the OpenAI API.
- Unit tests for every validation rule. Service and API tests for auth, upload, review, and tenancy.
- Linters (Ruff, mypy, ESLint, Prettier) pass.
- A demo seed script creates a company, a user, and sample bills that cover every finding type.
