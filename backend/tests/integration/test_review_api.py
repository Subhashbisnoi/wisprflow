from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.features.extraction.providers.fake_provider import FakeProvider
from scripts.invoice_factory import render_pdf
from tests.conftest import sample_spec, upload, use_spec

PDF = "application/pdf"


@pytest.fixture
def bill(client: TestClient, auth: dict[str, Any], provider: FakeProvider) -> dict[str, Any]:
    """A bill whose printed total is wrong, so it starts with a `totals` error."""
    spec = sample_spec(total_override=None)
    extracted_spec = sample_spec()
    use_spec(provider, extracted_spec)
    provider.default.total.value = "26636.00"  # printed 25,636.00; misread by 1,000
    invoice_id = upload(client, auth["headers"], ("a.pdf", render_pdf(spec), PDF)).json()[
        "results"
    ][0]["invoice"]["id"]
    detail: dict[str, Any] = client.get(
        f"/api/v1/invoices/{invoice_id}", headers=auth["headers"]
    ).json()
    return detail


def _url(bill: dict[str, Any], suffix: str = "") -> str:
    return f"/api/v1/invoices/{bill['id']}{suffix}"


def test_correcting_a_field_revalidates_audits_and_bumps_version(
    client: TestClient, auth: dict[str, Any], bill: dict[str, Any]
) -> None:
    assert bill["error_count"] == 1
    assert any(f["rule_code"] == "totals" and f["severity"] == "error" for f in bill["findings"])

    response = client.patch(
        _url(bill, "/fields"),
        headers=auth["headers"],
        json={"version": bill["version"], "changes": [{"field": "total", "value": "25,636.00"}]},
    )
    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated["error_count"] == 0
    assert updated["version"] == bill["version"] + 1
    assert updated["field_confidence"]["total"] == 1.0

    events = client.get(_url(bill, "/audit-events"), headers=auth["headers"]).json()["items"]
    correction = next(e for e in events if e["action"] == "field_corrected")
    assert correction["field_name"] == "total"
    assert (correction["old_value"], correction["new_value"]) == ("26636.00", "25636.00")
    assert correction["actor_name"] == "Priya Sharma"


def test_stale_version_gets_409_and_nothing_is_overwritten(
    client: TestClient, auth: dict[str, Any], bill: dict[str, Any]
) -> None:
    first = client.patch(
        _url(bill, "/fields"),
        headers=auth["headers"],
        json={"version": bill["version"], "changes": [{"field": "invoice_number", "value": "A-1"}]},
    )
    assert first.status_code == 200
    second = client.patch(
        _url(bill, "/fields"),
        headers=auth["headers"],
        json={"version": bill["version"], "changes": [{"field": "invoice_number", "value": "B-2"}]},
    )
    assert second.status_code == 409
    error = second.json()["error"]
    assert error["code"] == "version_conflict"
    assert error["details"]["current_version"] == bill["version"] + 1
    current = client.get(_url(bill), headers=auth["headers"]).json()
    assert current["invoice_number"] == "A-1"


def test_invalid_field_values_are_rejected(
    client: TestClient, auth: dict[str, Any], bill: dict[str, Any]
) -> None:
    for field, value in (("total", "abc"), ("invoice_date", "31/31/2026"), ("cgst", "-5")):
        response = client.patch(
            _url(bill, "/fields"),
            headers=auth["headers"],
            json={"version": bill["version"], "changes": [{"field": field, "value": value}]},
        )
        assert response.status_code == 422, field
        assert response.json()["error"]["details"][0]["field"] == field
    unknown = client.patch(
        _url(bill, "/fields"),
        headers=auth["headers"],
        json={"version": bill["version"], "changes": [{"field": "company_id", "value": "x"}]},
    )
    assert unknown.status_code == 422


def test_approval_blocked_by_errors_then_allowed_after_fix(
    client: TestClient, auth: dict[str, Any], bill: dict[str, Any]
) -> None:
    blocked = client.post(
        _url(bill, "/approve"), headers=auth["headers"], json={"version": bill["version"]}
    )
    assert blocked.status_code == 422
    assert blocked.json()["error"]["code"] == "approval_blocked"

    fixed = client.patch(
        _url(bill, "/fields"),
        headers=auth["headers"],
        json={"version": bill["version"], "changes": [{"field": "total", "value": "25636"}]},
    ).json()
    approved = client.post(
        _url(bill, "/approve"),
        headers=auth["headers"],
        json={"version": fixed["version"], "comment": "Checked against PO"},
    )
    assert approved.status_code == 200
    body = approved.json()
    assert body["status"] == "approved"
    assert body["reviewed_by_name"] == "Priya Sharma"
    assert body["review_comment"] == "Checked against PO"

    locked = client.patch(
        _url(bill, "/fields"),
        headers=auth["headers"],
        json={"version": body["version"], "changes": [{"field": "total", "value": "1"}]},
    )
    assert locked.status_code == 409 and locked.json()["error"]["code"] == "invalid_state"


def test_reject_requires_reason(
    client: TestClient, auth: dict[str, Any], bill: dict[str, Any]
) -> None:
    missing = client.post(
        _url(bill, "/reject"),
        headers=auth["headers"],
        json={"version": bill["version"], "reason": " "},
    )
    assert missing.status_code == 422
    rejected = client.post(
        _url(bill, "/reject"),
        headers=auth["headers"],
        json={"version": bill["version"], "reason": "Duplicate of AT/2026/0041"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    assert rejected.json()["rejection_reason"] == "Duplicate of AT/2026/0041"


def test_line_item_add_correct_remove(
    client: TestClient, auth: dict[str, Any], bill: dict[str, Any]
) -> None:
    version = bill["version"]
    added = client.post(
        _url(bill, "/line-items"),
        headers=auth["headers"],
        json={
            "version": version,
            "description": "Freight",
            "quantity": "1",
            "rate": "500",
            "amount": "500",
        },
    )
    assert added.status_code == 201
    body = added.json()
    assert len(body["line_items"]) == 3
    # Lines now exceed the subtotal by 500 -> arithmetic error appears.
    assert any(f["rule_code"] == "line_item_arithmetic" for f in body["findings"])

    item = body["line_items"][2]
    corrected = client.patch(
        _url(bill, f"/line-items/{item['id']}"),
        headers=auth["headers"],
        json={"version": body["version"], "changes": [{"field": "amount", "value": "600"}]},
    ).json()
    assert corrected["line_items"][2]["amount"] == "600.00"

    removed = client.delete(
        _url(bill, f"/line-items/{item['id']}"),
        headers=auth["headers"],
        params={"version": corrected["version"]},
    ).json()
    assert len(removed["line_items"]) == 2
    assert not any(f["rule_code"] == "line_item_arithmetic" for f in removed["findings"])
    actions = [
        e["action"]
        for e in client.get(_url(bill, "/audit-events"), headers=auth["headers"]).json()["items"]
    ]
    assert {"line_item_added", "line_item_corrected", "line_item_removed"} <= set(actions)


def test_correcting_vendor_gstin_relinks_vendor(
    client: TestClient, auth: dict[str, Any], bill: dict[str, Any]
) -> None:
    from scripts.invoice_factory import make_gstin

    new_gstin = make_gstin("27", "AAFCN4321K")
    updated = client.patch(
        _url(bill, "/fields"),
        headers=auth["headers"],
        json={
            "version": bill["version"],
            "changes": [{"field": "vendor_gstin", "value": new_gstin}],
        },
    ).json()
    assert updated["vendor"]["gstin"] == new_gstin
    vendors = client.get("/api/v1/vendors", headers=auth["headers"]).json()
    assert vendors["total"] == 2
