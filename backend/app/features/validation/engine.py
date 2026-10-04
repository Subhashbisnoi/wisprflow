import logging

from app.features.validation.models import SEVERITY_ORDER, Severity
from app.features.validation.rules.base import FindingDraft, ValidationContext, ValidationRule
from app.features.validation.rules.duplicate_invoice import DuplicateInvoiceRule
from app.features.validation.rules.gstin_format import GstinFormatRule
from app.features.validation.rules.line_item_arithmetic import LineItemArithmeticRule
from app.features.validation.rules.low_confidence import LowConfidenceRule
from app.features.validation.rules.required_fields import RequiredFieldsRule
from app.features.validation.rules.tax_rate import TaxRateRule
from app.features.validation.rules.tax_type import TaxTypeRule
from app.features.validation.rules.totals import TotalsRule

logger = logging.getLogger("app.validation")


def default_rules() -> list[ValidationRule]:
    return [
        RequiredFieldsRule(),
        GstinFormatRule(),
        DuplicateInvoiceRule(),
        LineItemArithmeticRule(),
        TotalsRule(),
        TaxRateRule(),
        TaxTypeRule(),
        LowConfidenceRule(),
    ]


class ValidationEngine:
    def __init__(self, rules: list[ValidationRule] | None = None) -> None:
        self.rules = rules if rules is not None else default_rules()

    def evaluate(self, ctx: ValidationContext) -> list[FindingDraft]:
        drafts: list[FindingDraft] = []
        for rule in self.rules:
            try:
                drafts.extend(rule.evaluate(ctx))
            except Exception:
                # One broken rule must not hide the results of the others.
                logger.exception("validation rule crashed", extra={"rule": rule.code})
                drafts.append(
                    FindingDraft(
                        rule_code=rule.code,
                        severity=Severity.WARNING,
                        message="This check could not be completed. Review the bill manually.",
                    )
                )
        return sorted(drafts, key=lambda d: SEVERITY_ORDER[d.severity])
