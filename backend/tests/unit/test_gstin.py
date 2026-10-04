import pytest

from app.features.validation.gstin import (
    check_gstin,
    compute_check_digit,
    is_valid_gstin,
    normalize_gstin,
    state_code_of,
)
from scripts.invoice_factory import make_gstin


def test_known_public_example_is_valid() -> None:
    assert is_valid_gstin("27AAPFU0939F1ZV")


def test_generated_gstin_round_trips() -> None:
    gstin = make_gstin("29", "AAKCS5678F")
    assert is_valid_gstin(gstin)
    assert compute_check_digit(gstin[:14]) == gstin[14]


@pytest.mark.parametrize(
    ("value", "reason_fragment"),
    [
        (None, "missing"),
        ("27AAPFU0939F1Z", "14 characters"),
        ("27AAPFU0939F1ZVX", "16 characters"),
        ("2AAAPFU0939F1ZV", "pattern"),
        ("27AAPFU0939F1XV", "pattern"),
        ("00AAPFU0939F1ZV", "state code"),
        ("27AAPFU0939F1Z9", "check digit"),
    ],
)
def test_invalid_gstins_explain_why(value: str | None, reason_fragment: str) -> None:
    result = check_gstin(value)
    assert not result.valid
    assert result.reason is not None and reason_fragment in result.reason


def test_normalize_strips_spaces_and_uppercases() -> None:
    assert normalize_gstin(" 27aapfu 0939f-1zv ") == "27AAPFU0939F1ZV"
    assert normalize_gstin("   ") is None


def test_state_code() -> None:
    assert state_code_of("27AAPFU0939F1ZV") == "27"
    assert state_code_of("XXAAPFU0939F1ZV") is None
