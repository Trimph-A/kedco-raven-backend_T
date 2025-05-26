from django.db import models
from common.models import UUIDModel, Feeder, DistributionTransformer, Band

class ExpenseCategory(UUIDModel, models.Model):
    name = models.CharField(max_length=100, unique=True)
    is_special = models.BooleanField(default=False)  # Special OPEX types like Salaries, NBET Invoice

    def __str__(self):
        return self.name
    
class GLBreakdown(UUIDModel, models.Model):
    name = models.CharField(max_length=150, unique=True)

    def __str__(self):
        return self.name


class Expense(UUIDModel, models.Model):
    district = models.ForeignKey('common.BusinessDistrict', on_delete=models.CASCADE)
    date = models.DateField()
    purpose = models.TextField()
    payee = models.CharField(max_length=200)
    gl_account_number = models.CharField(max_length=20)
    gl_breakdown = models.ForeignKey(GLBreakdown, on_delete=models.SET_NULL, null=True)
    opex_category = models.ForeignKey('ExpenseCategory', on_delete=models.SET_NULL, null=True)
    debit = models.DecimalField(max_digits=15, decimal_places=2, default=0.0)  # Sent from HQ
    credit = models.DecimalField(max_digits=15, decimal_places=2, default=0.0)  # Expense

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date']


class DailyCollection(UUIDModel, models.Model):
    COLLECTION_TYPE_CHOICES = (
        ('Prepaid', 'Prepaid'),
        ('Postpaid', 'Postpaid'),
    )

    feeder = models.ForeignKey(Feeder, on_delete=models.CASCADE)
    date = models.DateField()
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    collection_type = models.CharField(max_length=10, choices=COLLECTION_TYPE_CHOICES)
    vendor_name = models.CharField(max_length=255, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)


class MonthlyRevenueBilled(UUIDModel, models.Model):
    feeder = models.ForeignKey(Feeder, on_delete=models.CASCADE, related_name='financial_monthly_revenue_billed')
    month = models.DateField()
    amount = models.DecimalField(max_digits=15, decimal_places=2)

    created_at = models.DateTimeField(auto_now_add=True)


class SalesRepresentative(UUIDModel, models.Model):
    name = models.CharField(max_length=255)
    assigned_feeders = models.ManyToManyField(Feeder)
    slug = models.SlugField(unique=True)

    def __str__(self):
        return self.name


class SalesRepPerformance(UUIDModel, models.Model):
    sales_rep = models.ForeignKey(SalesRepresentative, on_delete=models.CASCADE)
    month = models.DateField()
    outstanding_billed = models.DecimalField(max_digits=15, decimal_places=2)
    current_billed = models.DecimalField(max_digits=15, decimal_places=2)
    collections = models.DecimalField(max_digits=15, decimal_places=2)
    daily_run_rate = models.DecimalField(max_digits=15, decimal_places=2)
    collections_on_outstanding = models.DecimalField(max_digits=15, decimal_places=2)
    active_accounts = models.PositiveIntegerField()
    suspended_accounts = models.PositiveIntegerField()
