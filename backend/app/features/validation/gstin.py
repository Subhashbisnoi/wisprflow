"""GSTIN structure, state codes and the official mod-36 check digit."""

import re
from dataclasses import dataclass

GSTIN_PATTERN = re.compile(r"^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
_CHARSET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

STATE_CODES: dict[str, str] = {
    "01": "Jammu and Kashmir",
    "02": "Himachal Pradesh",
    "03": "Punjab",
    "04": "Chandigarh",
    "05": "Uttarakhand",
    "06": "Haryana",
    "07": "Delhi",
    "08": "Rajasthan",
    "09": "Uttar Pradesh",
    "10": "Bihar",
    "11": "Sikkim",
    "12": "Arunachal Pradesh",
    "13": "Nagaland",
    "14": "Manipur",
    "15": "Mizoram",
    "16": "Tripura",
    "17": "Meghalaya",
    "18": "Assam",
    "19": "West Bengal",
    "20": "Jharkhand",
    "21": "Odisha",
    "22": "Chhattisgarh",
    "23": "Madhya Pradesh",
    "24": "Gujarat",
    "25": "Daman and Diu",
    "26": "Dadra and Nagar Haveli and Daman and Diu",
    "27": "Maharashtra",
    "28": "Andhra Pradesh (old)",
    "29": "Karnataka",
    "30": "Goa",
    "31": "Lakshadweep",
    "32": "Kerala",
    "33": "Tamil Nadu",
    "34": "Puducherry",
    "35": "Andaman and Nicobar Islands",
    "36": "Telangana",
    "37": "Andhra Pradesh",
    "38": "Ladakh",
    "97": "Other Territory",
    "99": "Centre Jurisdiction",
}


def normalize_gstin(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = re.sub(r"[\s\-]", "", value).upper()
    return cleaned or None


def compute_check_digit(first14: str) -> str:
    total = 0
    for index, char in enumerate(first14):
        value = _CHARSET.index(char)
        factor = 2 if index % 2 else 1
        product = value * factor
        total += product // 36 + product % 36
    return _CHARSET[(36 - total % 36) % 36]


@dataclass(frozen=True)
class GstinCheck:
    valid: bool
    reason: str | None = None


def check_gstin(value: str | None) -> GstinCheck:
    """Return whether a GSTIN is valid and, if not, a plain-English reason."""
    gstin = normalize_gstin(value)
    if not gstin:
        return GstinCheck(False, "it is missing")
    if len(gstin) != 15:
        return GstinCheck(False, f"it has {len(gstin)} characters instead of 15")
    if not GSTIN_PATTERN.match(gstin):
        return GstinCheck(
            False,
            "it does not follow the GSTIN pattern (2-digit state code, 10-character PAN, "
            "entity number, 'Z', check character)",
        )
    if gstin[:2] not in STATE_CODES:
        return GstinCheck(False, f"'{gstin[:2]}' is not a valid state code")
    if compute_check_digit(gstin[:14]) != gstin[14]:
        return GstinCheck(False, "the check digit does not match")
    return GstinCheck(True)


def is_valid_gstin(value: str | None) -> bool:
    return check_gstin(value).valid


def state_code_of(gstin: str | None) -> str | None:
    normalized = normalize_gstin(gstin)
    if normalized and len(normalized) >= 2 and normalized[:2] in STATE_CODES:
        return normalized[:2]
    return None


def state_label(code: str | None) -> str:
    if not code:
        return "unknown state"
    return f"{STATE_CODES.get(code, 'unknown state')}, {code}"
