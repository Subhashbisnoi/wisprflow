from datetime import date
from typing import Any

from fastapi.testclient import TestClient

from app.features.extraction.providers.fake_provider import FakeProvider
from scripts.invoice_factory import make_gstin, render_pdf
from tests.conftest import sample_spec, signup, upload, use_spec

PDF = "application/pdf"


def _upload_spec(
    client: TestClient, headers: dict[str, str], provider: FakeProvider, **kw: Any
) -> str:
    spec = sample_spec(**kw)
    use_spec(provider, spec)
    result = upload(client, headers, (f"{spec.invoice_number}.pdf", render_pdf(spec), PDF)).json()
    invoice_id: str = result["results"][0]["invoice"]["id"]
    return invoice_id


def test_other_tenant_cannot_see_or_touch_bills(
    client: TestClient, auth: dict[str, Any], provider: FakeProvider
) -> None:
    invoice_id = _upload_spec(client, auth["headers"], provider)
    other = signup(
        client, email="rahul@othercorp.in", company_name="Other Corp", company_gstin=None
    )
    h = other["headers"]

    assert client.get(f"/api/v1/invoices/{invoice_id}", headers=h).status_code == 404
    assert client.get(f"/api/v1/invoices/{invoice_id}/file", headers=h).status_code == 404
    assert client.get(f"/api/v1/invoices/{invoice_id}/audit-events", headers=h).status_code == 404
    patch = client.patch(
        f"/api/v1/invoices/{invoice_id}/fields",
        headers=h,
        json={"version": 1, "changes": [{"field": "total", "value": "1"}]},
    )
    assert patch.status_code == 404
    assert client.get("/api/v1/invoices", headers=h).json()["total"] == 0
    assert client.get("/api/v1/vendors", headers=h).json()["total"] == 0
    assert client.get("/api/v1/dashboard/summary", headers=h).json()["total_bills"] == 0


def test_list_filters_search_sort_and_pagination(
    client: TestClient, auth: dict[str, Any], provider: FakeProvider
) -> None:
    h = auth["headers"]
    small_vendor = make_gstin("27", "AAECS1111M")
    _upload_spec(client, h, provider, invoice_number="INV-1", invoice_date=date(2026, 7, 1))
    _upload_spec(client, h, provider, invoice_number="INV-2", invoice_date=date(2026, 8, 1))
    _upload_spec(
        client,
        h,
        provider,
        invoice_number="SM-3",
        invoice_date=date(2026, 9, 1),
        vendor_name="Shree Stationers",
        vendor_gstin=small_vendor,
        lines=sample_spec().lines[:1],
    )

    page = client.get(
        "/api/v1/invoices", headers=h, params={"page_size": 2, "sort": "invoice_date"}
    ).json()
    assert (page["total"], page["total_pages"], len(page["items"])) == (3, 2, 2)
    assert page["items"][0]["invoice_number"] == "INV-1"

    page2 = client.get(
        "/api/v1/invoices", headers=h, params={"page_size": 2, "page": 2, "sort": "invoice_date"}
    ).json()
    assert [i["invoice_number"] for i in page2["items"]] == ["SM-3"]

    search = client.get("/api/v1/invoices", headers=h, params={"search": "shree"}).json()
    assert [i["invoice_number"] for i in search["items"]] == ["SM-3"]

    dated = client.get(
        "/api/v1/invoices", headers=h, params={"date_from": "2026-07-15", "date_to": "2026-08-31"}
    ).json()
    assert [i["invoice_number"] for i in dated["items"]] == ["INV-2"]

    by_value = client.get("/api/v1/invoices", headers=h, params={"max_total": "15000"}).json()
    assert [i["invoice_number"] for i in by_value["items"]] == ["SM-3"]

    vendor_id = search["items"][0]["vendor"]["id"]
    by_vendor = client.get("/api/v1/invoices", headers=h, params={"vendor_id": vendor_id}).json()
    assert by_vendor["total"] == 1

    by_status = client.get("/api/v1/invoices", headers=h, params=[("status", "approved")]).json()
    assert by_status["total"] == 0

    bad = client.get("/api/v1/invoices", headers=h, params={"page_size": 500})
    assert bad.status_code == 422
    bad_sort = client.get("/api/v1/invoices", headers=h, params={"sort": "password"})
    assert bad_sort.status_code == 422


def test_vendor_rename_is_audited_and_listed(
    client: TestClient, auth: dict[str, Any], provider: FakeProvider
) -> None:
    _upload_spec(client, auth["headers"], provider)
    vendor = client.get("/api/v1/vendors", headers=auth["headers"]).json()["items"][0]
    assert vendor["legal_name"] == "Acme Traders Pvt Ltd"
    assert vendor["state_name"] == "Maharashtra"
    response = client.patch(
        f"/api/v1/vendors/{vendor['id']}", headers=auth["headers"], json={"display_name": "Acme"}
    )
    assert response.status_code == 200
    assert response.json()["display_name"] == "Acme"
    assert response.json()["legal_name"] == "Acme Traders Pvt Ltd"
    found = client.get("/api/v1/vendors", headers=auth["headers"], params={"search": "acme"}).json()
    assert found["total"] == 1


def test_dashboard_summary(
    client: TestClient, auth: dict[str, Any], provider: FakeProvider
) -> None:
    today = date.today()
    h = auth["headers"]
    first = _upload_spec(client, h, provider, invoice_number="D-1", invoice_date=today)
    _upload_spec(client, h, provider, invoice_number="D-2", invoice_date=today)
    detail = client.get(f"/api/v1/invoices/{first}", headers=h).json()
    client.post(f"/api/v1/invoices/{first}/approve", headers=h, json={"version": detail["version"]})

    summary = client.get("/api/v1/dashboard/summary", headers=h).json()
    kpis = summary["kpis"]
    assert kpis["bills_this_month"] == 2
    assert kpis["needs_review_count"] == 1
    assert kpis["approval_rate"] == 1.0
    assert float(kpis["pending_amount"]) == float(sample_spec().total)
    assert len(summary["monthly_spend"]) == 6
    assert summary["top_vendors"][0]["display_name"] == "Acme Traders Pvt Ltd"
