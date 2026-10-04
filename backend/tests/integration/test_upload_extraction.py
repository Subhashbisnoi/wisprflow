from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient

from app.features.extraction.providers.base import ProviderTransientError
from app.features.extraction.providers.fake_provider import FakeProvider
from scripts.invoice_factory import render_pdf, render_png, render_scanned_pdf
from tests.conftest import INTERSTATE_VENDOR_GSTIN, sample_spec, upload, use_spec

PDF = "application/pdf"


def _detail(client: TestClient, headers: dict[str, str], invoice_id: str) -> dict[str, Any]:
    response = client.get(f"/api/v1/invoices/{invoice_id}", headers=headers)
    assert response.status_code == 200, response.text
    data: dict[str, Any] = response.json()
    return data


def test_text_pdf_is_extracted_validated_and_vendor_created(
    client: TestClient, auth: dict[str, Any], provider: FakeProvider
) -> None:
    spec = sample_spec()
    use_spec(provider, spec)
    response = upload(client, auth["headers"], ("acme.pdf", render_pdf(spec), PDF))
    assert response.status_code == 202
    body = response.json()
    assert body["accepted"] == 1
    invoice_id = body["results"][0]["invoice"]["id"]

    detail = _detail(client, auth["headers"], invoice_id)
    assert provider.calls == ["text"]  # text layer first, no vision call (D-052)
    assert detail["status"] == "needs_review"
    assert detail["extraction_method"] == "text_layer"
    assert detail["invoice_number"] == "AT/2026/0042"
    assert Decimal(detail["total"]) == spec.total
    assert len(detail["line_items"]) == 2
    assert detail["field_confidence"]["total"] >= 0.95  # grounded in the text layer
    assert detail["vendor"]["display_name"] == "Acme Traders Pvt Ltd"
    # Only the expected info finding (round-off) on a clean invoice.
    assert detail["error_count"] == 0
    assert [f["rule_code"] for f in detail["findings"]] == ["totals"]

    audit = client.get(
        f"/api/v1/invoices/{invoice_id}/audit-events", headers=auth["headers"]
    ).json()
    actions = [e["action"] for e in audit["items"]]
    assert {"invoice_uploaded", "extraction_completed", "vendor_created", "vendor_linked"} <= set(
        actions
    )

    vendors = client.get("/api/v1/vendors", headers=auth["headers"]).json()
    assert vendors["total"] == 1 and vendors["items"][0]["bill_count"] == 1


def test_scanned_pdf_and_image_use_vision(
    client: TestClient, auth: dict[str, Any], provider: FakeProvider
) -> None:
    use_spec(provider, sample_spec())
    response = upload(
        client,
        auth["headers"],
        ("scan.pdf", render_scanned_pdf(sample_spec()), PDF),
        ("photo.png", render_png(sample_spec(invoice_number="X-2")), "image/png"),
    )
    assert response.json()["accepted"] == 2
    assert provider.calls == ["vision", "vision"]
    detail = _detail(client, auth["headers"], response.json()["results"][0]["invoice"]["id"])
    assert detail["extraction_method"] == "vision"
    assert max(detail["field_confidence"].values()) <= 0.90


def test_unsupported_and_oversized_files_are_rejected_individually(
    client: TestClient, auth: dict[str, Any], provider: FakeProvider
) -> None:
    use_spec(provider, sample_spec())
    big = b"%PDF-1.4\n" + b"0" * (3 * 1024 * 1024)  # limit is 2 MB in tests
    response = upload(
        client,
        auth["headers"],
        ("notes.docx", b"PK\x03\x04 not a pdf", "application/pdf"),
        ("huge.pdf", big, PDF),
        ("empty.pdf", b"", PDF),
        ("good.pdf", render_pdf(sample_spec()), PDF),
    )
    results = {r["filename"]: r for r in response.json()["results"]}
    assert results["notes.docx"]["error"]["code"] == "unsupported_file_type"
    assert results["huge.pdf"]["error"]["code"] == "file_too_large"
    assert "limit is 2.0 MB" in results["huge.pdf"]["error"]["message"]
    assert results["empty.pdf"]["status"] == "rejected"
    assert results["good.pdf"]["status"] == "accepted"


def test_corrupt_pdf_fails_with_clear_message_and_no_llm_call(
    client: TestClient, auth: dict[str, Any], provider: FakeProvider
) -> None:
    response = upload(client, auth["headers"], ("broken.pdf", b"%PDF-1.7\n\x00\x01garbage", PDF))
    invoice_id = response.json()["results"][0]["invoice"]["id"]
    detail = _detail(client, auth["headers"], invoice_id)
    assert detail["status"] == "failed"
    assert "damaged" in detail["error_message"]
    assert provider.calls == []


def test_duplicate_upload_flags_only_the_later_copy(
    client: TestClient, auth: dict[str, Any], provider: FakeProvider
) -> None:
    spec = sample_spec()
    use_spec(provider, spec)
    first = upload(client, auth["headers"], ("a.pdf", render_pdf(spec), PDF)).json()
    second = upload(client, auth["headers"], ("a-again.pdf", render_pdf(spec), PDF)).json()
    first_detail = _detail(client, auth["headers"], first["results"][0]["invoice"]["id"])
    second_detail = _detail(client, auth["headers"], second["results"][0]["invoice"]["id"])
    assert not any(f["rule_code"] == "duplicate_invoice" for f in first_detail["findings"])
    dupes = [f for f in second_detail["findings"] if f["rule_code"] == "duplicate_invoice"]
    assert len(dupes) == 1 and dupes[0]["severity"] == "error"


def test_tax_type_error_on_interstate_invoice_with_cgst(
    client: TestClient, auth: dict[str, Any], provider: FakeProvider
) -> None:
    spec = sample_spec(vendor_gstin=INTERSTATE_VENDOR_GSTIN, inter_state=False)
    use_spec(provider, spec)
    invoice_id = upload(client, auth["headers"], ("ka.pdf", render_pdf(spec), PDF)).json()[
        "results"
    ][0]["invoice"]["id"]
    detail = _detail(client, auth["headers"], invoice_id)
    assert any(
        f["rule_code"] == "tax_type" and f["severity"] == "error" for f in detail["findings"]
    )


def test_transient_provider_errors_retry_then_fail_then_manual_retry_succeeds(
    client: TestClient, auth: dict[str, Any], provider: FakeProvider
) -> None:
    provider.error = ProviderTransientError("rate limited")
    invoice_id = upload(client, auth["headers"], ("a.pdf", render_pdf(sample_spec()), PDF)).json()[
        "results"
    ][0]["invoice"]["id"]
    detail = _detail(client, auth["headers"], invoice_id)
    assert detail["status"] == "failed"
    assert detail["extraction_attempts"] == 3  # D-049
    assert "Retry extraction" in detail["error_message"]

    provider.error = None
    use_spec(provider, sample_spec())
    retried = client.post(f"/api/v1/invoices/{invoice_id}/retry", headers=auth["headers"])
    assert retried.status_code == 200
    assert _detail(client, auth["headers"], invoice_id)["status"] == "needs_review"

    again = client.post(f"/api/v1/invoices/{invoice_id}/retry", headers=auth["headers"])
    assert again.status_code == 409 and again.json()["error"]["code"] == "invalid_state"


def test_file_endpoint_streams_original_document(
    client: TestClient, auth: dict[str, Any], provider: FakeProvider
) -> None:
    use_spec(provider, sample_spec())
    pdf = render_pdf(sample_spec())
    invoice_id = upload(client, auth["headers"], ("a.pdf", pdf, PDF)).json()["results"][0][
        "invoice"
    ]["id"]
    response = client.get(f"/api/v1/invoices/{invoice_id}/file", headers=auth["headers"])
    assert response.status_code == 200
    assert response.headers["content-type"] == PDF
    assert response.content == pdf
