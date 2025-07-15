from django.db import models
from common.models import UUIDModel, Feeder, BusinessDistrict, DistributionTransformer, Band

class OpexCategory(UUIDModel, models.Model):
    name = models.CharField(max_length=100, unique=True)
    is_special = models.BooleanField(default=False)  # Special OPEX types like Salaries, NBET Invoice

    def __str__(self):
        return self.name
    
class GLBreakdown(UUIDModel, models.Model):
    name = models.CharField(max_length=150, unique=True)

    def __str__(self):
        return self.name


class Opex(UUIDModel, models.Model):
    district = models.ForeignKey(
        BusinessDistrict,
        on_delete=models.CASCADE,
        help_text="Which business district this OPEX belongs to"
    )
    date = models.DateField(
        help_text="Date of the expense"
    )
    purpose = models.TextField(
        help_text="What the expenditure was for"
    )
    payee = models.CharField(
        max_length=200,
        help_text="Who was paid"
    )
    gl_account_number = models.CharField(
        max_length=20,
        help_text="General ledger account number"
    )
    gl_breakdown = models.ForeignKey(
        GLBreakdown,
        on_delete=models.SET_NULL,
        null=True,
        help_text="GL breakdown mapping"
    )
    opex_category = models.ForeignKey(
        OpexCategory,
        on_delete=models.SET_NULL,
        null=True,
        help_text="Categorization of the OPEX (e.g. admin, technical, etc.)"
    )
    debit = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0.0,
        help_text="Amount sent from HQ (debit side)"
    )
    credit = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0.0,
        help_text="Actual expense amount (credit side)"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the record was created"
    )

    class Meta:
        ordering = ['-date']
        verbose_name = "OPEX"
        verbose_name_plural = "OPEX Records"

    def __str__(self):
        return (
            f"{self.district.name} | "
            f"{self.date:%Y-%m-%d} | "
            f"{self.opex_category.name if self.opex_category else 'Uncategorized'} | "
            f"₦{self.credit:,}"
        )





class MonthlyRevenueBilled(UUIDModel, models.Model):
    feeder = models.ForeignKey(Feeder, on_delete=models.CASCADE, related_name='financial_monthly_revenue_billed')
    month = models.DateField()
    amount = models.DecimalField(max_digits=15, decimal_places=2)

    created_at = models.DateTimeField(auto_now_add=True)



