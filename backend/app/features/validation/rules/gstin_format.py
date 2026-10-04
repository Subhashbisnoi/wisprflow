from app.features.validation.gstin import check_gstin, normalize_gstin
from app.features.validation.models import Severity
from app.features.validation.rules.base import FindingDraft, ValidationContext, ValidationRule


class GstinFormatRule(ValidationRule):
    code = "gstin_format"

    def evaluate(self, ctx: ValidationContext) -> list[FindingDraft]:
        findings: list[FindingDraft] = []
        vendor = normalize_gstin(ctx.invoice.vendor_gstin)
        buyer = normalize_gstin(ctx.invoice.buyer_gstin)

        if vendor:
            check = check_gstin(vendor)
            if not check.valid:
                findings.append(
                    self.finding(
                        Severity.ERROR,
                        f"Vendor GSTIN '{vendor}' is not valid: {check.reason}. Verify it "
                        "against the invoice; input tax credit cannot be claimed on an invalid "
                        "GSTIN.",
                        "vendor_gstin",
                    )
                )

        if buyer:
            check = check_gstin(buyer)
            if not check.valid:
                findings.append(
                    self.finding(
                        Severity.ERROR,
                        f"Buyer GSTIN '{buyer}' is not valid: {check.reason}.",
                        "buyer_gstin",
                    )
                )
            elif ctx.company_gstin and buyer != ctx.company_gstin:
                findings.append(
                    self.finding(
                        Severity.WARNING,
                        f"Buyer GSTIN '{buyer}' does not match your company GSTIN "
                        f"'{ctx.company_gstin}'. This invoice may be addressed to another "
                        "entity.",
                        "buyer_gstin",
                    )
                )
        return findings
