from app.features.validation.models import Severity
from app.features.validation.rules.base import (
    FIELD_LABELS,
    FindingDraft,
    ValidationContext,
    ValidationRule,
)

LOW_CONFIDENCE_THRESHOLD = 0.60  # D-030


class LowConfidenceRule(ValidationRule):
    code = "low_confidence"

    def __init__(self, threshold: float = LOW_CONFIDENCE_THRESHOLD) -> None:
        self.threshold = threshold

    def evaluate(self, ctx: ValidationContext) -> list[FindingDraft]:
        findings: list[FindingDraft] = []
        for name, label in FIELD_LABELS.items():
            value = getattr(ctx.invoice, name)
            confidence = ctx.invoice.field_confidence.get(name)
            if value in (None, "") or confidence is None or confidence >= self.threshold:
                continue
            findings.append(
                self.finding(
                    Severity.WARNING,
                    f"{label} was read with low confidence ({confidence:.0%}). Check it against "
                    "the document.",
                    name,
                )
            )
        return findings
