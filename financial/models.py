from django.db import models
from common.models import Feeder, DistributionTransformer, Band

class ExpenseCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)
    is_special = models.BooleanField(default=False)  # Special OPEX types like Salaries, NBET Invoice

    def __str__(self):
        return self.name


class Expense(models.Model):
    category = models.ForeignKey(ExpenseCategory, on_delete=models.CASCADE)
    description = models.TextField()
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    month = models.DateField()  # Always store first day of the month
    feeder = models.ForeignKey(Feeder, on_delete=models.CASCADE, null=True, blank=True)
    transformer = models.ForeignKey(DistributionTransformer, on_delete=models.CASCADE, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)


class DailyCollection(models.Model):
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


class MonthlyRevenueBilled(models.Model):
    feeder = models.ForeignKey(Feeder, on_delete=models.CASCADE)
    month = models.DateField()
    amount = models.DecimalField(max_digits=15, decimal_places=2)

    created_at = models.DateTimeField(auto_now_add=True)


class SalesRepresentative(models.Model):
    name = models.CharField(max_length=255)
    assigned_transformers = models.ManyToManyField(DistributionTransformer)
    slug = models.SlugField(unique=True)

    def __str__(self):
        return self.name


class SalesRepPerformance(models.Model):
    sales_rep = models.ForeignKey(SalesRepresentative, on_delete=models.CASCADE)
    month = models.DateField()
    outstanding_billed = models.DecimalField(max_digits=15, decimal_places=2)
    current_billed = models.DecimalField(max_digits=15, decimal_places=2)
    collections = models.DecimalField(max_digits=15, decimal_places=2)
    daily_run_rate = models.DecimalField(max_digits=15, decimal_places=2)
    collections_on_outstanding = models.DecimalField(max_digits=15, decimal_places=2)
    active_accounts = models.PositiveIntegerField()
    suspended_accounts = models.PositiveIntegerField()
