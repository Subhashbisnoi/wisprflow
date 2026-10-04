# Ledgerline - User Flows

Related: [PRD](01-prd.md) | [HLD](02-hld.md)

Navigation map (left sidebar): **Dashboard**, **Upload**, **Review queue**, **Bills**, **Vendors**. The top bar shows the company name and the user menu (name, email, sign out).

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

## 1. Sign-up and login

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

## 2. Uploading invoices

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

## 3. Review queue

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

## 4. Correcting a field

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

## 5. Approving or rejecting

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

## 6. Vendor management

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

## 7. Dashboard

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
